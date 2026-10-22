"""Oracle lượng tử hóa độc lập và lifecycle trên Llama nhỏ thật."""
from copy import deepcopy
from collections import Counter

import numpy as np
import pytest
import torch
from torch.ao.quantization import FakeQuantize
from transformers import LlamaConfig, LlamaForCausalLM

from ptq_eval import full_logits
from fp32_reference import ROOT, cached_logits, read_json
from ptq_fake_quant import PTQAdapter, QuantPoint, default_config
from ptq_validate import check_reload_logits, probe_cache


def manual_quantize(x, scales, axis, bound):
    values = x.numpy()
    output = np.empty_like(values)
    for index in np.ndindex(values.shape):
        scale = float(scales[0 if axis is None else index[axis]])
        integer = max(-bound, min(bound, round(float(values[index]) / scale)))
        output[index] = integer * scale
    return output


@pytest.mark.parametrize("bits", [4, 8])
@pytest.mark.parametrize("axis,kind,shape", [(None, "A", (2, 4)), (0, "W", (2, 4)), (1, "K", (1, 2, 2, 4)), (1, "V", (1, 2, 2, 4))])
def test_round_clamp_half_steps_and_axis(bits, axis, kind, shape):
    point = QuantPoint(kind, bits, axis, 1 if axis is None else 2)
    scales = torch.tensor([.25] if axis is None else [.25, .5])
    point.fq.scale.resize_(scales.shape).copy_(scales)
    point.fq.zero_point.resize_(scales.shape).zero_()
    point.fq.enable_fake_quant()
    source = torch.tensor([-1000., -2.5, -1.5, -.5, 0., .5, 1.5, 1000.]).repeat(int(np.prod(shape)) // 8).reshape(shape)
    # Giá trị đo theo scale, gồm negative/zero/halfstep và extrema ngoài miền.
    view = [1] * len(shape)
    if axis is not None:
        view[axis] = 2
    source = source * scales.reshape(view)
    result = point(source)
    expected = manual_quantize(source, scales, axis, (1 << (bits - 1)) - 1)
    np.testing.assert_array_equal(result.numpy(), expected)
    point.fq.disable_fake_quant()
    assert torch.equal(point(source), source)


@pytest.mark.parametrize("bits", [4, 8])
@pytest.mark.parametrize("axis,kind,shape", [(None, "A", (2, 4)), (0, "W", (2, 4)), (1, "K", (1, 2, 2, 4))])
def test_observer_scale_formula_zero_and_negative(bits, axis, kind, shape):
    channels = 1 if axis is None else 2
    point = QuantPoint(kind, bits, axis, channels)
    point.fq.enable_observer()
    values = torch.zeros(shape)
    point(values)
    expected_eps = torch.finfo(torch.float32).eps
    assert torch.equal(point.fq.scale, torch.full((channels,), expected_eps))
    assert torch.all(point.fq.zero_point == 0)
    values = -torch.arange(int(np.prod(shape)), dtype=torch.float32).reshape(shape)
    point(values)
    if axis is None:
        maxima = np.array([np.abs(values.numpy()).max()])
    else:
        maxima = np.abs(values.numpy()).max(axis=tuple(d for d in range(len(shape)) if d != axis))
    expected = np.maximum(maxima / ((1 << (bits - 1)) - 1), expected_eps)
    np.testing.assert_allclose(point.fq.scale.numpy(), expected, rtol=1e-7)
    assert torch.all(point.fq.zero_point == 0)


@pytest.fixture
def tiny_model():
    torch.manual_seed(1234)
    return LlamaForCausalLM(LlamaConfig(vocab_size=19, hidden_size=12, intermediate_size=24,
        num_hidden_layers=2, num_attention_heads=3, num_key_value_heads=1,
        tie_word_embeddings=True, attn_implementation="eager")).eval()


@torch.inference_mode()
def test_tied_weight_immutability_disable_reload_and_static_observers(tiny_model, tmp_path):
    model = tiny_model
    ids = [1, 4, 8, 3, 2]
    source = {name: value.clone() for name, value in model.named_parameters()}
    native = full_logits(model, ids).clone()
    adapter = PTQAdapter(model)
    assert model.model.embed_tokens.weight is model.lm_head.weight
    assert torch.equal(full_logits(model, ids), native)
    with pytest.raises(ValueError):
        adapter.set_mode("quantize")
    adapter.begin_calibration()
    full_logits(model, ids)
    adapter.freeze()
    adapter.save_qparams(tmp_path / "params.safetensors")
    adapter.set_mode("quantize")
    before = adapter.qparam_state()
    result = full_logits(model, ids).clone()
    # Chỉ một tensor W chung được sử dụng bởi lookup và head; Parameter gốc vẫn tied.
    shared = adapter.quantized_weight("shared_embedding_lm_head.weight")
    assert shared is adapter.quantized_weight("shared_embedding_lm_head.weight")
    assert shared.data_ptr() != model.lm_head.weight.data_ptr()
    assert adapter.points["shared_embedding_lm_head.weight"].calls == 2  # observe W một lần + FQ một lần
    lookup_ids = torch.tensor([ids])
    assert torch.equal(model.model.embed_tokens(lookup_ids), torch.nn.functional.embedding(lookup_ids, shared))
    hidden = torch.randn(1, 3, model.config.hidden_size)
    expected_head = torch.nn.functional.linear(adapter.points["lm_head.input"].fq(hidden), shared)
    assert torch.equal(model.lm_head(hidden), expected_head)
    full_logits(model, [1, 2, 3])
    for name, state in adapter.qparam_state().items():
        assert all(torch.equal(v, before[name][key]) for key, v in state.items())
    adapter.set_mode("disabled")
    assert torch.equal(full_logits(model, ids), native)
    adapter.restore()
    config = deepcopy(adapter.config)
    del adapter
    loaded = PTQAdapter(model, config)
    loaded.load_qparams(tmp_path / "params.safetensors")
    loaded.set_mode("quantize")
    assert torch.equal(full_logits(model, ids), result)
    for name, value in model.named_parameters():
        assert torch.equal(value, source[name])
    assert model.model.embed_tokens.weight is model.lm_head.weight
    loaded.set_enabled({"W": False})
    assert not loaded.materialized
    loaded.set_point_enabled("shared_embedding_lm_head.weight", True)
    assert loaded.quantized_weight("shared_embedding_lm_head.weight").data_ptr() != model.lm_head.weight.data_ptr()
    loaded.set_point_enabled("shared_embedding_lm_head.weight", False)
    assert loaded.quantized_weight("shared_embedding_lm_head.weight") is model.lm_head.weight
    loaded.set_mode("disabled")
    assert torch.equal(full_logits(model, ids), native)
    loaded.restore()


def test_uncalibrated_freeze_and_bad_channels_rejected(tiny_model):
    adapter = PTQAdapter(tiny_model)
    with pytest.raises(ValueError):
        adapter.freeze()
    with pytest.raises(ValueError):
        QuantPoint("K", 8, 1, 3)(torch.zeros(1, 9, 2, 4))
    with pytest.raises(ValueError):
        QuantPoint("W", 6)
    adapter.restore()

@torch.inference_mode()
def test_post_rope_pre_gqa_cache_append_once_on_tiny_llama(tiny_model):
    adapter = PTQAdapter(tiny_model)
    adapter.begin_calibration()
    full_logits(tiny_model, [1, 2, 3, 4, 5])
    adapter.freeze()
    adapter.set_mode("quantize")
    result = probe_cache(adapter, [1, 2, 3, 4, 5], 3)
    assert result["native_heads"] == 1 and result["query_heads"] == 3
    assert result["unchanged_prefix_tensors"] == 8
    assert result["new_tensors"] == 12
    assert result["post_rope_checks"] == result["post_projection_checks"] == 3
    assert all(p["calls"] == 3 and p["tokens"] == 5 for p in result["points"].values())
    adapter.restore()


@pytest.mark.parametrize("smooth", [False, True])
@torch.inference_mode()
def test_warm_weight_cache_skips_effective_work_and_invalidates(tiny_model, smooth, monkeypatch):
    model = tiny_model; config = default_config(); ids = [1, 4, 8, 3, 2]
    if smooth: config["smoothquant"] = read_json(ROOT / "configs/extra/w8a12kv8_smoothquant.json")["smoothquant"]
    source = {name: p.clone() for name, p in model.named_parameters()}
    native = full_logits(model, ids).clone(); adapter = PTQAdapter(model, config)
    if smooth:
        adapter.begin_smooth_calibration(); full_logits(model, ids); adapter.finalize_smoothquant()
    adapter.begin_calibration(); full_logits(model, ids); adapter.freeze(); adapter.set_mode("quantize")
    original = adapter.effective_weight; calls = []
    def effective(name): calls.append(name); return original(name)
    monkeypatch.setattr(adapter, "effective_weight", effective)
    expected = full_logits(model, ids).clone(); assert Counter(calls) == Counter({n: 1 for n in adapter.weights})
    calls.clear(); assert torch.equal(full_logits(model, ids), expected)
    assert np.isfinite(cached_logits(model, ids, 3)).all(); assert calls == []
    adapter.set_enabled({"W": True}); assert not adapter.materialized
    assert torch.equal(full_logits(model, ids), expected)
    assert Counter(calls) == Counter({n: 1 for n in adapter.weights})
    calls.clear(); name = "model.layers.0.self_attn.q_proj.weight"
    adapter.set_point_enabled(name, False)
    assert torch.equal(adapter.quantized_weight(name), original(name)); assert calls == [name]
    adapter.set_point_enabled(name, True); calls.clear()
    first = adapter.quantized_weight(name); assert adapter.quantized_weight(name) is first; assert calls == [name]
    adapter.set_mode("disabled"); calls.clear()
    torch.testing.assert_close(full_logits(model, ids), native, rtol=2e-6, atol=2e-6)
    assert calls and not adapter.materialized
    adapter.begin_calibration(); calls.clear(); full_logits(model, ids)
    assert calls and not adapter.materialized
    assert all(torch.equal(p, source[name]) for name, p in model.named_parameters())
    assert model.model.embed_tokens.weight is model.lm_head.weight
    adapter.restore()

@pytest.mark.parametrize("fault", [None, "shape", "nan", "inf", "small_error"])
def test_reload_exact_check_preserves_shape_finite_and_bitwise_contract(fault):
    expected = np.ones((2, 3), dtype=np.float32); actual = expected.copy()
    if fault == "shape": actual = actual[:1]
    elif fault == "nan": actual[0, 0] = expected[0, 0] = np.nan
    elif fault == "inf": actual[0, 0] = expected[0, 0] = np.inf
    elif fault == "small_error": actual[0, 0] += np.float32(1e-7)
    if fault is None: assert check_reload_logits(actual, expected) == {"bitwise_equal": True, "elements": 6}
    else:
        with pytest.raises(ValueError): check_reload_logits(actual, expected)

@pytest.mark.parametrize("kind,axis,shape", [("A", None, (1, 2, 3)), ("A", -1, (1, 2, 3)),
    ("W", 0, (2, 3)), ("K", 1, (1, 2, 2, 3)), ("V", 1, (1, 2, 2, 3))])
def test_deferred_minmax_matches_independent_fake_quant_zero_negative_extrema(kind, axis, shape):
    point = QuantPoint(kind, 8, axis, 1 if axis is None else shape[axis], defer_qparams=True)
    zero = torch.zeros(shape)
    negative = -torch.arange(np.prod(shape), dtype=torch.float32).reshape(shape)
    extreme = torch.linspace(-1e5, 3e4, int(np.prod(shape))).reshape(shape)
    for batches in ((zero,), (negative,), (zero, negative, extreme)):
        point.reset_observer(); point.fq.enable_observer()
        oracle = FakeQuantize(**point.kwargs); oracle.disable_fake_quant()
        for values in batches:
            assert torch.equal(point(values), values); oracle(values)
            assert point.fq.scale.numel() == 1 and point.fq.scale.item() == 1
        point.finish_observation()
        assert torch.equal(point.fq.scale, oracle.scale)
        assert torch.equal(point.fq.zero_point, oracle.zero_point)
        assert point.freeze_calculations == 1
