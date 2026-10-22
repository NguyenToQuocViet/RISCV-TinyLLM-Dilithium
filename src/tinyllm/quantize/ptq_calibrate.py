#!/usr/bin/env python3
"""Thu train observers từ 64 cửa sổ train và 16 lượt cache train, freeze/save qparams."""
import argparse
from collections import Counter
from pathlib import Path
import time

import torch
from transformers import DynamicCache

from fp32_reference import (ROOT, configure_runtime, environment, load_model, read_json,
                            source_snapshot, write_json)
from ptq_eval import full_logits
from ptq_fake_quant import PTQAdapter, default_config


def calibration_cache_cases(records):
    return [{"id": r["id"], "role": "calibration", "calibration_index": i,
             "regimes": [{"prefill": 32, "decode": 64, "input_length": 96},
                         {"prefill": 448, "decode": 64, "input_length": 512}]}
            for i, r in enumerate(records[:8])]


@torch.inference_mode()
def stream_cache(model, ids, prefill, cache=None):
    """Không giữ logits toàn chuỗi khi chỉ cần observer hoặc kiểm cache."""
    cache = DynamicCache() if cache is None else cache
    for start, end in [(0, prefill)] + [(i, i + 1) for i in range(prefill, len(ids))]:
        output = model(input_ids=torch.tensor([ids[start:end]], dtype=torch.long),
                       attention_mask=torch.ones((1, end), dtype=torch.long),
                       position_ids=torch.arange(start, end).unsqueeze(0),
                       cache_position=torch.arange(start, end), past_key_values=cache, use_cache=True)
        if not torch.isfinite(output.logits).all():
            raise ValueError("Cache logits có NaN/Inf")
        cache = output.past_key_values
        del output
    return cache


@torch.inference_mode()
def calibrate(args):
    configure_runtime()
    model, _ = load_model(source_snapshot(args.cache_dir, args.offline))
    records = read_json(args.data_dir / "wikitext_calibration.json")
    config = read_json(args.config) if args.config else default_config()
    adapter = PTQAdapter(model, config)
    started = time.monotonic()
    smooth_report = None
    if config.get("smoothquant", {}).get("enabled"):
        adapter.begin_smooth_calibration()
        for index, record in enumerate(records):
            logits = full_logits(model, record["input_ids"])
            if not torch.isfinite(logits).all():
                raise ValueError("SmoothQuant statistics pass produced NaN/Inf")
            del logits
            if (index + 1) % 8 == 0:
                print(f"SMOOTHQUANT train stats {index + 1}/64", flush=True)
        smooth_report = adapter.finalize_smoothquant()
    adapter.begin_calibration()
    for index, record in enumerate(records):
        logits = full_logits(model, record["input_ids"])
        if not torch.isfinite(logits).all():
            raise ValueError("Calibration logits có NaN/Inf")
        del logits
        if (index + 1) % 8 == 0:
            print(f"CALIBRATION prefill {index + 1}/64", flush=True)
    cases = calibration_cache_cases(records)
    for case in cases:
        record = records[case["calibration_index"]]
        for regime in case["regimes"]:
            stream_cache(model, record["input_ids"][:regime["input_length"]], regime["prefill"])
            print(f"CALIBRATION cache {case['id']} prefill={regime['prefill']}", flush=True)
    specs = adapter.point_specs()
    # 64 x512 +8 x(96+512), K/V phải được quan sát cả prefill lẫn decode đúng 37632 token/layer.
    expected_kv_tokens = 64 * 512 + 8 * (96 + 512)
    if any(p["tokens"] != expected_kv_tokens for p in specs.values() if p["kind"] in ("K", "V")):
        raise ValueError("Coverage K/V calibration thiếu token")
    if any(p.fq.fake_quant_enabled.item() for p in adapter.points.values()):
        raise ValueError("Fake-quant phải tắt trong lúc thu thống kê ban đầu")
    print("CALIBRATION freeze observers", flush=True)
    adapter.freeze()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    adapter.save_qparams(args.output_dir / "qparams.safetensors")
    write_json(args.output_dir / "config.json", adapter.config)
    write_json(args.output_dir / "data_ids.json", {"prefill_ids": [r["id"] for r in records], "cache_cases": cases})
    report = {"status": "PASS", "environment": environment(), "full_prefill_windows": 64,
              "full_prefill_tokens": 64 * 512, "cache_runs": 16, "cache_decode_steps": 16 * 64,
              "kv_observed_tokens_per_layer": expected_kv_tokens, "calibration_only": True,
              "selection_statistics": False, "heldout_evaluated": False,
              "point_counts": dict(Counter(p["kind"] for p in specs.values())),
              "scales": sum(p.channels for p in adapter.points.values()),
              "qparams_bytes": (args.output_dir / "qparams.safetensors").stat().st_size,
              "points": adapter.point_specs(), "contract": adapter.calibration_contract(),
              "smoothquant_scales": smooth_report,
              "histogram_resolution": {name: {"bins": p.bins,
                  "minimum": float(p.fq.activation_post_process.min_val),
                  "maximum": float(p.fq.activation_post_process.max_val),
                  "bin_width": float((p.fq.activation_post_process.max_val - p.fq.activation_post_process.min_val) / p.bins),
                  "selected_symmetric_bound": float(p.fq.scale.item() * p.fq.quant_max)}
                  for name, p in adapter.points.items() if p.observer != "minmax"},
              "seconds": round(time.monotonic() - started, 3)}
    write_json(args.output_dir / "metadata.json", report)
    print(f"PASS calibration: {report['point_counts']}, scales={report['scales']}, seconds={report['seconds']}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    parser.add_argument("--cache-dir", type=Path, default=ROOT / ".cache/huggingface")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "calibration/w8a8kv8_static")
    calibrate(parser.parse_args())


if __name__ == "__main__":
    main()
