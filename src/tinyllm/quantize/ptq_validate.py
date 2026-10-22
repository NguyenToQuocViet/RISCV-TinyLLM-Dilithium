#!/usr/bin/env python3
"""Kiểm adapter thật: disabled/original, vị trí K/V, cache, qparams và reload."""
import argparse
import hashlib
from pathlib import Path
import time

import numpy as np
import torch
import torch.nn.functional as F
from transformers import DynamicCache

from fp32_reference import (ROOT, cached_logits, compare_logits, configure_runtime,
                            environment, load_model, read_json, source_snapshot, write_json)
from ptq_calibrate import stream_cache
from ptq_eval import full_logits
from ptq_fake_quant import PTQAdapter


def parameter_fingerprints(model):
    """Oracle bất biến trọng số cho campaign này; không dùng để kiểm revision mỗi run."""
    return {name: hashlib.sha256(parameter.detach().numpy().tobytes()).hexdigest()
            for name, parameter in model.named_parameters()}


def validate_weight_qparams(adapter):
    """Independent NumPy source-row max oracle, including W4 /7 and shared W8 /127."""
    counts = {"decoder_tensors": 0, "shared_tensors": 0, "rows": 0}
    for name, weight in adapter.weights.items():
        shared = name == "shared_embedding_lm_head.weight"
        bits = adapter.config["shared_weight_bits" if shared else "decoder_weight_bits"]
        bound = (1 << (bits - 1)) - 1
        point = adapter.points[name]
        if point.bits != bits or point.fq.quant_min != -bound or point.fq.quant_max != bound:
            raise ValueError(f"Weight bit/range mismatch: {name}")
        rows = weight.detach().numpy()
        expected = np.maximum(np.abs(rows).max(axis=1) / np.float32(bound), np.finfo(np.float32).eps)
        np.testing.assert_allclose(point.fq.scale.numpy(), expected, rtol=1e-7, atol=0, err_msg=name)
        if not np.all(point.fq.zero_point.numpy() == 0):
            raise ValueError(f"Nonzero W zero-point: {name}")
        counts["shared_tensors" if shared else "decoder_tensors"] += 1
        counts["rows"] += len(expected)
    return {"pass": True, "oracle": "NumPy max(abs(source row))/signed bound, FP32 eps floor", **counts}


def assert_state_equal(before, adapter):
    after = adapter.qparam_state()
    if before.keys() != after.keys():
        raise ValueError("Danh sách điểm lượng tử hóa đổi khi eval")
    for name, state in before.items():
        if any(not torch.equal(value, after[name][key]) for key, value in state.items()):
            raise ValueError(f"Qparams/observer thay đổi khi eval: {name}")


def check_reload_logits(actual, expected):
    """Reload requires exact finite logits; no tolerance/error arrays are needed."""
    if actual.shape != expected.shape:
        raise ValueError(f"Sai shape logits: {actual.shape}, {expected.shape}")
    if not np.isfinite(actual).all() or not np.isfinite(expected).all():
        raise ValueError("Logits có NaN/Inf")
    if not np.array_equal(actual, expected):
        raise ValueError("Reload config/qparams không tái lập logits tới từng bit")
    return {"bitwise_equal": True, "elements": int(actual.size)}


@torch.inference_mode()
def disabled_gate(adapter, old_cases, selection, cache_cases, phase):
    adapter.set_mode("disabled")
    cases = [{"id": c["name"], "input_ids": c["input_ids"], "prefills": c["prefill_lengths"]}
             for c in old_cases]
    for case in cache_cases:
        record = selection[case["selection_index"]]
        for regime in case["regimes"]:
            cases.append({"id": f"{case['id']}:prefill{regime['prefill']}",
                          "input_ids": record["input_ids"][:regime["input_length"]],
                          "prefills": [regime["prefill"]]})
    results = []
    for case in cases:
        ids = case["input_ids"]
        with adapter.native():
            oracle = full_logits(adapter.model, ids).numpy()
        full = full_logits(adapter.model, ids).numpy()
        full_metrics = compare_logits(full, oracle)
        del full
        splits = []
        for prefill in case["prefills"]:
            actual = cached_logits(adapter.model, ids, prefill)
            splits.append({"prefill": prefill, **compare_logits(actual, oracle)})
            del actual
        results.append({"id": case["id"], "input_length": len(ids), "full": full_metrics, "cache": splits})
        del oracle
        print(f"DISABLED {phase} {case['id']} PASS", flush=True)
    return {"phase": phase, "cases": results,
            "elements": sum(r["full"]["elements"] + sum(s["elements"] for s in r["cache"]) for r in results),
            "cache_splits": sum(len(r["cache"]) for r in results)}


@torch.inference_mode()
def probe_cache(adapter, ids, prefill):
    """Theo dõi đầu vào mới trước cache; prefix cũ phải giữ nguyên tới từng bit."""
    model = adapter.model
    heads, dimension = model.config.num_key_value_heads, model.config.hidden_size // model.config.num_attention_heads
    pending, projected, rotary, hooks = {}, {}, {}, []
    checks = {"new_tensors": 0, "unchanged_prefix_tensors": 0, "post_rope_checks": 0,
              "post_projection_checks": 0}
    for point in adapter.points.values():
        if point.kind in ("K", "V"):
            point.reset_counts()
    first_attention = model.model.layers[0].self_attn
    hooks.append(first_attention.k_proj.register_forward_hook(lambda module, inputs, output: projected.update(K=output)))
    hooks.append(first_attention.v_proj.register_forward_hook(lambda module, inputs, output: projected.update(V=output)))
    hooks.append(model.model.rotary_emb.register_forward_hook(lambda module, inputs, output: rotary.update(pair=output)))

    for index in range(model.config.num_hidden_layers):
        for kind, suffix in (("K", "key_post_rope"), ("V", "value_post_projection")):
            point = adapter.points[f"model.layers.{index}.self_attn.{suffix}"]
            def capture(before, after, *, _index=index, _kind=kind):
                if before.ndim != 4 or before.shape[1] != heads:
                    raise ValueError("K/V bị nhân rộng GQA trước điểm FQ")
                if _index == 0:
                    raw = projected[_kind].view(1, -1, heads, dimension).transpose(1, 2)
                    if _kind == "K":
                        cos, sin = rotary["pair"]
                        half = dimension // 2
                        rotated = torch.cat((-raw[..., half:], raw[..., :half]), dim=-1)
                        expected = raw * cos.unsqueeze(1) + rotated * sin.unsqueeze(1)
                        checks["post_rope_checks"] += 1
                    else:
                        expected = raw
                        checks["post_projection_checks"] += 1
                    if not torch.equal(before, expected):
                        raise ValueError(f"Sai vị trí {_kind} trước FQ")
                pending[(_index, _kind)] = after
            point.capture = capture

    class AuditedCache(DynamicCache):
        def update(self, key_states, value_states, layer_idx, cache_kwargs=None):
            old_length = self.get_seq_length(layer_idx)
            old = None
            if old_length:
                old = (self.key_cache[layer_idx].clone(), self.value_cache[layer_idx].clone())
            for kind, tensor in (("K", key_states), ("V", value_states)):
                if tensor.shape[1] != heads or not torch.equal(tensor, pending.pop((layer_idx, kind))):
                    raise ValueError("Cache không nhận đúng tensor mới vừa FQ")
                checks["new_tensors"] += 1
            key, value = super().update(key_states, value_states, layer_idx, cache_kwargs)
            if old is not None:
                for actual, expected in zip((key, value), old):
                    if not torch.equal(actual[:, :, :old_length], expected):
                        raise ValueError("Append làm thay đổi prefix cache cũ")
                    checks["unchanged_prefix_tensors"] += 1
            return key, value

    try:
        stream_cache(model, ids, prefill, AuditedCache())
        if pending:
            raise ValueError("Tensor FQ không được cache tiêu thụ")
        counts = {}
        expected_calls = 1 + len(ids) - prefill
        for name, point in adapter.points.items():
            if point.kind in ("K", "V"):
                if point.calls != expected_calls or point.tokens != len(ids):
                    raise ValueError(f"FQ lặp/thiếu token cache mới: {name}")
                counts[name] = {"calls": point.calls, "tokens": point.tokens, "last_shape": point.last_shape}
        return {"prefill": prefill, "decode": len(ids) - prefill, "input_length": len(ids),
                "native_heads": heads, "query_heads": model.config.num_attention_heads,
                "head_dim": dimension, **checks, "points": counts}
    finally:
        for hook in hooks:
            hook.remove()
        for point in adapter.points.values():
            point.capture = None


@torch.inference_mode()
def validate_candidate(adapter, records):
    adapter.set_mode("quantize")
    for point in adapter.points.values():
        point.reset_counts()
    before = adapter.qparam_state()
    reference = None
    for index, record in enumerate(records[:2]):
        logits = full_logits(adapter.model, record["input_ids"])
        if not torch.isfinite(logits).all():
            raise ValueError("Candidate logits có NaN/Inf")
        if index == 0:
            reference = logits.numpy().copy()
        del logits
    coverage = {name: {"calls": p.calls, "tokens": p.tokens, "last_shape": p.last_shape}
                for name, p in adapter.points.items() if p.kind in ("K", "V")}
    if any(p["calls"] != 2 or p["tokens"] != 1024 for p in coverage.values()):
        raise ValueError("Full forward không cache chưa áp FQ K/V đủ hai cửa sổ")
    shared = adapter.quantized_weight("shared_embedding_lm_head.weight")
    ids = torch.tensor([[1, 2, 3]])
    lookup = adapter.model.model.embed_tokens(ids)
    if not torch.equal(lookup, F.embedding(ids, shared)):
        raise ValueError("Embedding lookup không dùng W chung đã FQ")
    hidden = torch.linspace(-1, 1, adapter.model.config.hidden_size).view(1, 1, -1)
    expected = F.linear(adapter.points["lm_head.input"].fq(hidden), shared)
    if not torch.equal(adapter.model.lm_head(hidden), expected):
        raise ValueError("LM head không dùng W chung đã FQ")
    if adapter.points["shared_embedding_lm_head.weight"].calls != 1:
        raise ValueError("W chung bị materialize hơn một lần")
    if adapter.model.model.embed_tokens.weight is not adapter.model.lm_head.weight:
        raise ValueError("Weight tying bị mất")
    probes = [probe_cache(adapter, records[0]["input_ids"][:length], prefill)
              for prefill, length in ((32, 96), (448, 512))]
    assert_state_equal(before, adapter)
    if any(p.fq.observer_enabled.item() for p in adapter.points.values()):
        raise ValueError("Observer còn bật khi eval")
    return {"selection_ids": [r["id"] for r in records[:2]], "full_no_cache_coverage": coverage,
            "cache_probes": probes, "static_qparams_unchanged": True,
            "shared_weight_materializations": 1, "weight_tying": True,
            "embedding_lookup_and_head_use_same_quantized_weight": True}, reference


@torch.inference_mode()
def validate(args):
    configure_runtime()
    model, _ = load_model(source_snapshot(args.cache_dir, args.offline))
    original = parameter_fingerprints(model)
    config = read_json(args.calibration_dir / "config.json")
    adapter = PTQAdapter(model, config)
    adapter.load_qparams(args.calibration_dir / "qparams.safetensors")
    records = read_json(args.data_dir / "wikitext_selection.json")
    old_cases = read_json(ROOT / "cases.json")
    cases = read_json(args.data_dir / "cache_cases.json")
    started = time.monotonic()
    report = {"environment": environment(), "heldout_evaluated": False,
              "quality_search_performed": False, "calibration_dir": str(args.calibration_dir),
              "before": disabled_gate(adapter, old_cases, records, cases, "before")}
    if config["decoder_weight_bits"] == 4:
        report["weight_qparam_oracle"] = validate_weight_qparams(adapter)
    report["candidate"], expected = validate_candidate(adapter, records)
    print("PASS candidate: no-cache KV, source tying, immutable qparams, two audited cache protocols", flush=True)
    report["after"] = disabled_gate(adapter, old_cases, records, cases, "after")
    if parameter_fingerprints(model) != original:
        raise ValueError("Trọng số nguồn bị thay đổi")
    report["source_weights_unchanged"] = True
    adapter.restore()
    del adapter
    loaded = PTQAdapter(model, read_json(args.calibration_dir / "config.json"))
    loaded.load_qparams(args.calibration_dir / "qparams.safetensors")
    loaded.set_mode("quantize")
    actual = full_logits(model, records[0]["input_ids"]).numpy()
    report["reload"] = check_reload_logits(actual, expected)
    if parameter_fingerprints(model) != original:
        raise ValueError("Reload làm thay đổi trọng số nguồn")
    loaded.set_mode("disabled")
    loaded.restore()
    report["status"] = "PASS"
    report["seconds"] = round(time.monotonic() - started, 3)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_json(args.output, report)
    print(f"PASS validation: before/after {report['before']['cache_splits']}+{report['after']['cache_splits']} cache splits, "
          f"reload bitwise, seconds={report['seconds']}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    parser.add_argument("--cache-dir", type=Path, default=ROOT / ".cache/huggingface")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--calibration-dir", type=Path, default=ROOT / "calibration/w8a8kv8_static")
    parser.add_argument("--output", type=Path, default=ROOT / "results/ptq/stage2_validation.json")
    validate(parser.parse_args())


if __name__ == "__main__":
    main()
