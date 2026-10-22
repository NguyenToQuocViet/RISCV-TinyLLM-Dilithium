"""Channel-wise A and SmoothQuant contracts on small independent Llama oracles."""
from copy import deepcopy
from types import SimpleNamespace
import json

import numpy as np
import pytest
import torch
import torch.nn.functional as F
from safetensors.torch import load_file, save_file
from transformers import LlamaConfig, LlamaForCausalLM

from fp32_reference import read_json, write_json
from ptq_eval import evaluate_ppl, full_logits
from ptq_fake_quant import PTQAdapter, QuantPoint, default_config
import ptq_experiment as experiment


def tiny_model():
    torch.manual_seed(1234)
    return LlamaForCausalLM(LlamaConfig(vocab_size=23, hidden_size=12, intermediate_size=24,
        num_hidden_layers=2, num_attention_heads=3, num_key_value_heads=1,
        tie_word_embeddings=True, attn_implementation="eager")).eval()


@pytest.mark.parametrize("bits", [8, 12])
def test_a_per_input_channel_scales_and_rounding(bits):
    point = QuantPoint("A", bits, axis=-1, channels=3)
    values = torch.tensor([[[1., 2., 4.], [-2., 1., -8.]]])
    point.fq.enable_observer()
    point(values)
    bound = (1 << (bits - 1)) - 1
    expected_scale = torch.tensor([2., 2., 8.]) / bound
    torch.testing.assert_close(point.fq.scale, expected_scale)
    assert point.fq.zero_point.numel() == 3 and torch.all(point.fq.zero_point == 0)
    point.fq.disable_observer(); point.fq.enable_fake_quant()
    actual = point(values)
    expected = np.empty(tuple(values.shape), dtype=np.float32)
    for i in range(values.shape[-1]):
        for j in range(values.shape[1]):
            q = max(-bound, min(bound, round(float(values[0, j, i]) / float(expected_scale[i]))))
            expected[0, j, i] = q * float(expected_scale[i])
    np.testing.assert_array_equal(actual.numpy(), expected)
    with pytest.raises(ValueError, match="Sai channel"):
        point(torch.zeros(1, 2, 4))


@pytest.mark.parametrize("bits", [8, 12])
@torch.inference_mode()
def test_smoothquant_invariance_source_tying_and_strict_reload(bits, tmp_path):
    model = tiny_model()
    config = {"name": f"sq{bits}", "decoder_weight_bits": 8, "shared_weight_bits": 8,
        "activation_bits": bits, "key_bits": 8, "value_bits": 8,
        "enabled": {"W": True, "A": True, "K": True, "V": True}, "point_enabled": {},
        "weight_policy": "static_per_output_row_axis0", "activation_policy": "static_per_tensor",
        "activation_observer": "minmax", "kv_policy": "static_per_native_head_axis1_BHTD",
        "zero_point": 0, "rounding": "nearest_ties_to_even", "scale_dtype": "float32",
        "shared_embedding_lm_head": "one quantized weight; embedding row lookup and head projection",
        "fp32_remainder": ["RMSNorm", "RoPE arithmetic", "attention QK matmul/scaling/mask/softmax/AV matmul",
            "SiLU", "FFN gate multiply", "residual adds", "Linear accumulators", "logits"],
        "smoothquant": {"enabled": True, "alpha": 0.5, "statistics": "train_max_abs_per_input_feature",
            "fold": "activation_divide_weight_multiply", "exclude": ["lm_head", "shared_embedding_lm_head.weight"]}}
    source = {n: p.detach().clone() for n, p in model.named_parameters()}
    ids = [1, 4, 8, 3, 2]
    native_logits = full_logits(model, ids).clone()
    adapter = PTQAdapter(model, config)
    adapter.begin_smooth_calibration()
    full_logits(model, ids)
    scales_summary = adapter.finalize_smoothquant()
    assert len(scales_summary) == 14
    assert "lm_head" not in adapter.smooth_scales
    from ptq_storage import storage_inventory
    inventory = storage_inventory(model, adapter, length=5)
    smooth_bytes = sum(scale.numel() for scale in adapter.smooth_scales.values()) * 4
    summary = inventory["summary"]
    assert summary["smoothquant_runtime_metadata_bytes"] == smooth_bytes
    assert summary["total_persistent_bytes"] == sum(summary[key] for key in (
        "weight_payload_bytes", "weight_metadata_bytes", "static_a_metadata_bytes",
        "smoothquant_runtime_metadata_bytes", "kv_payload_bytes", "kv_metadata_bytes"))
    assert inventory["smoothquant_metadata"]["runtime_scale_bytes_if_not_fused"] == smooth_bytes
    torch.testing.assert_close(full_logits(model, ids), native_logits, rtol=2e-6, atol=2e-6)

    # Check algebraic invariance at one actual Linear before quantization.
    name = "model.layers.0.self_attn.q_proj"
    module = model.get_submodule(name)
    x = torch.randn(1, 3, module.in_features)
    s = adapter.smooth_scales[name]
    original = F.linear(x, adapter.weights[name + ".weight"], module.bias)
    transformed = F.linear(x / s, adapter.effective_weight(name + ".weight"), module.bias)
    torch.testing.assert_close(transformed, original, rtol=2e-6, atol=2e-6)
    assert model.model.embed_tokens.weight is model.lm_head.weight
    assert all(torch.equal(p, source[n]) for n, p in model.named_parameters())

    adapter.begin_calibration()
    full_logits(model, ids)
    adapter.freeze()
    adapter.save_qparams(tmp_path / "params.safetensors")
    contract = adapter.calibration_contract()
    assert contract["smoothquant"]["alpha"] == 0.5
    adapter.set_mode("quantize")
    # With W fake-quant disabled, SmoothQuant still uses the folded W that balances x/s.
    adapter.set_enabled({"W": False})
    assert torch.equal(adapter.quantized_weight(name + ".weight"), adapter.effective_weight(name + ".weight"))
    adapter.set_enabled({"W": True})
    expected_logits = full_logits(model, ids).clone()
    adapter.restore()

    loaded = PTQAdapter(model, deepcopy(config))
    loaded.load_qparams(tmp_path / "params.safetensors")
    assert set(loaded.smooth_scales) == set(adapter.smooth_scales)
    loaded.set_mode("quantize")
    torch.testing.assert_close(full_logits(model, ids), expected_logits, rtol=0, atol=0)
    tensors = load_file(tmp_path / "params.safetensors")
    assert sum(k.startswith("smoothquant.") for k in tensors) == 14
    bad = deepcopy(config); bad["smoothquant"]["alpha"] = 0.25
    mismatch = PTQAdapter(model, bad)
    with pytest.raises(ValueError, match="SmoothQuant contract"):
        mismatch.load_qparams(tmp_path / "params.safetensors")
    mismatch.restore(); loaded.restore()
    assert all(torch.equal(p, source[n]) for n, p in model.named_parameters())

    scale_key = sorted(key for key in tensors if key.startswith("smoothquant."))[0]
    for corruption in ("shape", "nan", "zero"):
        corrupt = {key: value.clone() for key, value in tensors.items()}
        if corruption == "shape":
            corrupt[scale_key] = corrupt[scale_key][:-1]
        elif corruption == "nan":
            corrupt[scale_key].view(-1)[0] = float("nan")
        else:
            corrupt[scale_key].view(-1)[0] = 0.0
        corrupt_path = tmp_path / f"{corruption}.safetensors"
        save_file(corrupt, str(corrupt_path), metadata={"ptq_contract": json.dumps(contract)})
        invalid = PTQAdapter(model, deepcopy(config))
        message = "scale shape mismatch" if corruption == "shape" else "finite positive FP32"
        with pytest.raises(ValueError, match=message):
            invalid.load_qparams(corrupt_path)
        invalid.restore()


@pytest.mark.parametrize("policy", ["static_per_tensor", "static_per_input_channel", "dynamic_per_token"])
@torch.inference_mode()
def test_diagnose_actual_capture_and_independent_counts(tmp_path, monkeypatch, policy):
    args = SimpleNamespace(mode="diagnose", data_dir=tmp_path, config=tmp_path / "config.json",
        qparams=tmp_path / "qparams.safetensors", output=tmp_path / "report.json",
        cache_dir=tmp_path, offline=True)
    records = [{"id": "synthetic", "input_ids": [1, 2, 3, 4] * 4}]
    model = tiny_model(); config = default_config(); config["activation_policy"] = policy
    adapter = PTQAdapter(model, config)
    adapter.begin_calibration(); full_logits(model, [1, 2, 3, 4]); adapter.freeze()
    for point in adapter.points.values():
        if point.kind == "A":
            point.fq.scale.copy_(torch.linspace(.001, .02, point.channels))
    adapter.save_qparams(args.qparams); adapter.restore()
    write_json(tmp_path / "wikitext_selection.json", records)
    write_json(args.config, config)
    monkeypatch.setattr(experiment, "configure_runtime", lambda: None)
    monkeypatch.setattr(experiment, "source_snapshot", lambda *_: None)
    monkeypatch.setattr(experiment, "load_model", lambda _: (model, None))
    observed = {}
    original_loader = experiment.load_candidate
    def load(*values):
        candidate = original_loader(*values); observed["adapter"] = candidate
        return candidate
    monkeypatch.setattr(experiment, "load_candidate", load)
    expected = {}
    def score(model, records):
        for name, point in observed["adapter"].points.items():
            if point.kind != "A": continue
            capture = point.capture
            def audit(value, result, *, name=name, point=point, capture=capture):
                values = value.numpy().reshape(-1, value.shape[-1]); bound = point.fq.quant_max
                scales = point.fq.scale.numpy()
                clipped = zeroed = 0
                runtime_scales = []
                for row in values:
                    runtime = max(float(np.abs(row).max()) / bound, np.finfo(np.float32).eps)
                    runtime_scales.append(np.float32(runtime))
                    for index, x in enumerate(row):
                        scale = runtime_scales[-1] if policy == "dynamic_per_token" else scales[index if point.axis is not None else 0]
                        clipped += int(abs(x) > np.float32(scale * bound))
                        zeroed += int(x != 0 and round(float(np.float32(x / scale))) == 0)
                expected[name] = (values.size, clipped, zeroed, min(runtime_scales), max(runtime_scales))
                capture(value, result)
            point.capture = audit
        return evaluate_ppl(model, records)
    monkeypatch.setattr(experiment, "evaluate_ppl", score)
    experiment.run(args); rows = read_json(args.output)["activation_diagnostics"]
    assert rows and set(rows) == set(expected)
    for name, row in rows.items():
        assert (row["elements"], row["clipped"], row["zeroed_nonzero"]) == expected[name][:3]
        if policy == "static_per_input_channel":
            assert row["scale"] == {"count": observed["adapter"].points[name].channels,
                                    "min": pytest.approx(.001), "max": pytest.approx(.02)}
        elif policy == "dynamic_per_token":
            assert row["runtime_scale_min"] == pytest.approx(expected[name][3])
            assert row["runtime_scale_max"] == pytest.approx(expected[name][4])
        else: assert row["scale"] == pytest.approx(.001)
    assert sum(row["zeroed_nonzero"] for row in rows.values()) > 0
    if policy != "dynamic_per_token": assert sum(row["clipped"] for row in rows.values()) > 0
