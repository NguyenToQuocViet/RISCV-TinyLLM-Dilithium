"""Test tách token 0, alpha SmoothQuant theo Linear và biên mã A8 của các biến thể A8."""
from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest
import torch
from safetensors import safe_open
from safetensors.torch import save_file
from transformers import DynamicCache, LlamaConfig, LlamaForCausalLM

import ptq_a8_variants as a8
import ptq_contract as contract
from fp32_reference import ROOT, read_json
from ptq_contract_runtime import ContractRuntime, RuntimeFormat
from ptq_contract_search import override_kv_scales
from ptq_eval import full_logits
from ptq_fake_quant import PTQAdapter, Position0Rows, default_config
from ptq_intermediate_calibrate import IntermediateProfiler, full_signed_range
from test_ptq_contract import _small_artifact_runtime, reference_clamp, reference_shift

IDS = [1, 4, 8, 3, 2, 5, 7]


@pytest.fixture
def tiny_model():
    torch.manual_seed(7)
    return LlamaForCausalLM(LlamaConfig(vocab_size=19, hidden_size=12, intermediate_size=24,
        num_hidden_layers=2, num_attention_heads=3, num_key_value_heads=1,
        tie_word_embeddings=True, attn_implementation="eager")).eval()


def smooth_adapter(model, alpha, token0=False):
    config = read_json(ROOT/"candidates/w8a8kv8_smoothquant_a09/config.json")
    config["smoothquant"]["alpha"] = alpha
    if token0:
        config["token0"] = {"enabled": True}
    return PTQAdapter(model, config)


@torch.inference_mode()
def calibrate(adapter, model, ids=IDS):
    adapter.begin_smooth_calibration()
    full_logits(model, ids)
    adapter.finalize_smoothquant()
    adapter.begin_calibration()
    full_logits(model, ids)
    adapter.freeze()


@torch.inference_mode()
def test_position0_mask_marks_only_the_first_prefill_row(tiny_model):
    tracker = Position0Rows(tiny_model)
    tiny_model(input_ids=torch.tensor([IDS]), use_cache=False)
    assert tracker.mask.tolist() == [[True] + [False]*6]
    tiny_model(input_ids=torch.tensor([IDS[:3], IDS[3:6]]), use_cache=False)
    assert tracker.mask.tolist() == [[True, False, False]]*2
    cache = DynamicCache()
    for start, stop, expected in ((0, 3, [True, False, False]), (3, 4, [False]), (4, 7, [False]*3)):
        tiny_model(input_ids=torch.tensor([IDS[start:stop]]), cache_position=torch.arange(start, stop),
                   past_key_values=cache, use_cache=True)
        assert tracker.mask.tolist() == [expected]
    # Không có cache_position: vị trí được tính từ độ dài cache.
    cache = DynamicCache()
    tiny_model(input_ids=torch.tensor([IDS[:3]]), past_key_values=cache, use_cache=True)
    assert tracker.mask.tolist() == [[True, False, False]]
    tiny_model(input_ids=torch.tensor([IDS[3:4]]), past_key_values=cache, use_cache=True)
    assert tracker.mask.tolist() == [[False]]
    # lm_head có thể chỉ giữ hàng cuối.
    tracker.mask = torch.tensor([[True, False, False]])
    assert tracker.rows_for(torch.zeros(1, 1, 4)).tolist() == [[False]]
    assert tracker.rows_for(torch.zeros(1, 3, 4)).tolist() == [[True, False, False]]
    tracker.remove()
    assert not tiny_model.model._forward_pre_hooks


def test_hook_exists_only_while_a_token0_adapter_is_bound(tiny_model):
    plain = smooth_adapter(tiny_model, 0.5)
    assert plain.position0 is None and not tiny_model.model._forward_pre_hooks
    plain.restore()
    adapter = smooth_adapter(tiny_model, 0.5, token0=True)
    assert len(tiny_model.model._forward_pre_hooks) == 1
    adapter.restore()
    assert adapter.position0 is None and not tiny_model.model._forward_pre_hooks
    with pytest.raises(ValueError, match="token0 chỉ dùng"):
        PTQAdapter(tiny_model, {**default_config(), "token0": {"enabled": True}})


@torch.inference_mode()
def test_alpha_map_with_equal_values_matches_scalar_alpha(tiny_model):
    adapter = smooth_adapter(tiny_model, 0.6)
    adapter.begin_smooth_calibration()
    full_logits(tiny_model, IDS)
    adapter.finalize_smoothquant()
    scalar = {name: value.clone() for name, value in adapter.smooth_scales.items()}
    names = sorted(scalar)
    assert len(names) == 14

    def finalize(alpha):
        adapter.begin_smooth_calibration()
        full_logits(tiny_model, IDS)
        return adapter.finalize_smoothquant(alpha)

    finalize({name: 0.6 for name in names})
    assert all(torch.equal(adapter.smooth_scales[name], scalar[name]) for name in names)
    report = finalize({**{name: 0.6 for name in names}, names[0]: 0.9})
    assert report[names[0]]["alpha"] == 0.9
    assert not torch.equal(adapter.smooth_scales[names[0]], scalar[names[0]])
    assert all(torch.equal(adapter.smooth_scales[name], scalar[name]) for name in names[1:])
    with pytest.raises(ValueError, match="alpha map"):
        finalize({names[0]: 0.5})
    with pytest.raises(ValueError, match=r"\[0,1\]"):
        finalize({**{name: 0.6 for name in names}, names[1]: 1.2})
    adapter.restore()


@torch.inference_mode()
def test_alpha_map_is_part_of_the_qparams_contract(tiny_model, tmp_path):
    adapter = smooth_adapter(tiny_model, 0.5)
    adapter.begin_smooth_calibration()
    full_logits(tiny_model, IDS)
    names = sorted(adapter.smooth_stats)
    alpha = {name: 0.5 for name in names}
    adapter.finalize_smoothquant(alpha)
    adapter.begin_calibration()
    full_logits(tiny_model, IDS)
    adapter.freeze()
    adapter.save_qparams(tmp_path/"q.safetensors")
    config = deepcopy(adapter.config)
    adapter.restore()
    loaded = PTQAdapter(tiny_model, config)
    loaded.load_qparams(tmp_path/"q.safetensors")
    loaded.restore()
    config["smoothquant"]["alpha"] = {**alpha, names[0]: 0.6}
    other = PTQAdapter(tiny_model, config)
    with pytest.raises(ValueError, match="SmoothQuant contract mismatch"):
        other.load_qparams(tmp_path/"q.safetensors")
    other.restore()


@torch.inference_mode()
def test_smoothquant_and_observers_skip_position0_and_a_separate_scale_covers_it(tiny_model):
    adapter = smooth_adapter(tiny_model, 0.5, token0=True)
    name = "model.layers.1.mlp.down_proj"
    captured = []
    handle = tiny_model.get_submodule(name).register_forward_pre_hook(lambda m, args: captured.append(args[0].clone()))
    adapter.begin_smooth_calibration()
    full_logits(tiny_model, IDS)
    x = captured[-1][0]
    assert torch.equal(adapter.smooth_stats[name], x[1:].abs().amax(0))
    assert not torch.equal(adapter.smooth_stats[name], x.abs().amax(0))
    adapter.finalize_smoothquant()
    smooth = adapter.smooth_scales[name]
    adapter.begin_calibration()
    full_logits(tiny_model, IDS)
    handle.remove()
    adapter.freeze()
    torch.testing.assert_close(adapter.points[name+".input"].fq.scale,
                               (x[1:]/smooth).abs().max().reshape(1)/127, rtol=1e-6, atol=0)
    torch.testing.assert_close(adapter.points[name+".input.token0"].fq.scale,
                               (x[:1]/smooth).abs().max().reshape(1)/127, rtol=1e-6, atol=0)
    specs = adapter.point_specs()
    assert specs[name+".input.token0"]["tokens"] == 1 and specs[name+".input"]["tokens"] == len(IDS)-1
    adapter.restore()


@torch.inference_mode()
def test_token0_with_the_regular_scale_matches_the_plain_adapter(tiny_model):
    adapter = smooth_adapter(tiny_model, 0.5, token0=True)
    calibrate(adapter, tiny_model)
    token0_names = [name for name in adapter.points if name.endswith(".input.token0")]
    assert len(token0_names) == 15  # 14 Linear decoder + lm_head
    differs = [not torch.equal(adapter.points[name].fq.scale, adapter.points[name.removesuffix(".token0")].fq.scale)
               for name in token0_names]
    assert any(differs)
    adapter.set_mode("quantize")
    separate = full_logits(tiny_model, IDS).clone()
    adapter.set_mode("disabled")
    for name in token0_names:
        adapter.points[name].fq.scale.copy_(adapter.points[name.removesuffix(".token0")].fq.scale)
    adapter.set_mode("quantize")
    equal_scales = full_logits(tiny_model, IDS).clone()
    assert not torch.equal(separate, equal_scales)
    adapter.restore()

    plain = smooth_adapter(tiny_model, 0.5)
    plain.smooth_scales = {name: scale.clone() for name, scale in adapter.smooth_scales.items()}
    for name, point in plain.points.items():
        source = adapter.points[name].fq
        point.fq.scale.resize_(source.scale.shape).copy_(source.scale)
        point.fq.zero_point.resize_(source.zero_point.shape).copy_(source.zero_point)
        point.frozen = True
    plain.set_mode("quantize")
    assert torch.equal(full_logits(tiny_model, IDS), equal_scales)
    plain.restore()


@torch.inference_mode()
def test_qparams_store_token0_scales_and_reject_mismatched_bundles(tiny_model, tmp_path):
    adapter = smooth_adapter(tiny_model, 0.5, token0=True)
    calibrate(adapter, tiny_model)
    adapter.save_qparams(tmp_path/"token0.safetensors")
    with safe_open(str(tmp_path/"token0.safetensors"), framework="pt") as archive:
        keys = set(archive.keys())
    assert {"lm_head.input.token0.scale", "model.layers.0.self_attn.q_proj.input.token0.scale"} <= keys
    config = deepcopy(adapter.config)
    scales = {name: point.fq.scale.clone() for name, point in adapter.points.items()}
    adapter.restore()
    loaded = PTQAdapter(tiny_model, config)
    loaded.load_qparams(tmp_path/"token0.safetensors")
    assert all(torch.equal(point.fq.scale, scales[name]) for name, point in loaded.points.items())
    loaded.restore()
    plain_config = deepcopy(config)
    del plain_config["token0"]
    plain = PTQAdapter(tiny_model, plain_config)
    with pytest.raises(ValueError, match="token0 contract mismatch"):
        plain.load_qparams(tmp_path/"token0.safetensors")
    calibrate(plain, tiny_model)
    plain.save_qparams(tmp_path/"plain.safetensors")
    plain.restore()
    again = PTQAdapter(tiny_model, config)
    with pytest.raises(ValueError, match="token0 contract mismatch"):
        again.load_qparams(tmp_path/"plain.safetensors")
    again.restore()


@torch.inference_mode()
def test_override_kv_scales_replaces_only_cache_points(tiny_model, tmp_path):
    adapter = PTQAdapter(tiny_model)
    adapter.begin_calibration()
    full_logits(tiny_model, IDS)
    adapter.freeze()
    before = {name: point.fq.scale.clone() for name, point in adapter.points.items()}
    kv = {name: before[name]*2 for name, point in adapter.points.items() if point.kind in ("K", "V")}
    assert len(kv) == 4
    save_file({name+".scale": value for name, value in kv.items()}, str(tmp_path/"kv.safetensors"))
    override_kv_scales(adapter, tmp_path/"kv.safetensors")
    for name, point in adapter.points.items():
        assert torch.equal(point.fq.scale, kv.get(name, before[name]))
    adapter.restore()


def naive_alpha_errors(x, weight, smooth_max, activation_max, alphas):
    x, weight = np.asarray(x, np.float64), np.asarray(weight, np.float64)
    weight_max = np.abs(weight).max(axis=0)
    result = {}
    for alpha in alphas:
        scale = np.ones(x.shape[1])
        for channel in range(x.shape[1]):
            if smooth_max[channel] > 0 and weight_max[channel] > 0:
                scale[channel] = smooth_max[channel]**alpha/weight_max[channel]**(1-alpha)
        a_scale = max(activation_max/scale)/127
        xq = np.clip(np.rint(x/scale/a_scale), -128, 127)*a_scale
        scaled = weight*scale
        row = np.abs(scaled).max(axis=1, keepdims=True)/127
        wq = np.clip(np.rint(scaled/row), -128, 127)*row
        result[alpha] = float(((xq@wq.T - x@weight.T)**2).sum())
    return result


def test_choose_alpha_uses_minimum_error_then_closest_to_half_then_smaller_alpha():
    assert a8.choose_alpha({0.3: 5., 0.4: 2., 0.5: 3.}) == 0.4
    assert a8.choose_alpha({0.3: 1., 0.5: 1., 0.9: 1.}) == 0.5
    assert a8.choose_alpha({0.4: 1., 0.6: 1., 0.9: 2.}) == 0.4
    assert a8.choose_alpha({0.7: 1., 1.0: 1.}) == 0.7


def test_alpha_search_errors_match_an_independent_implementation_and_select_the_same_alpha():
    rng = np.random.default_rng(5)
    x = rng.normal(size=(96, 16)).astype(np.float32)
    x[:, 3] *= 60  # kênh ngoại lệ
    x[:, 9] *= 12
    weight = rng.normal(size=(24, 16)).astype(np.float32)*np.linspace(0.2, 2., 16, dtype=np.float32)
    smooth_max = np.abs(x).max(axis=0)
    activation_max = smooth_max*1.1  # lượt đầy đủ có thể có max lớn hơn lượt SmoothQuant
    actual = a8.smooth_alpha_errors(torch.from_numpy(x), torch.from_numpy(weight),
                                    torch.from_numpy(smooth_max), torch.from_numpy(activation_max), a8.ALPHA_GRID)
    expected = naive_alpha_errors(x, weight, smooth_max, activation_max, a8.ALPHA_GRID)
    assert list(actual) == list(a8.ALPHA_GRID)
    for alpha in a8.ALPHA_GRID:
        assert actual[alpha] == pytest.approx(expected[alpha], rel=2e-3)
    assert len(set(round(value, 6) for value in expected.values())) > 1
    assert a8.choose_alpha(actual) == a8.choose_alpha(expected)


def test_alpha_search_tie_on_a_degenerate_linear_picks_alpha_closest_to_half():
    zero = torch.zeros(8, 4)
    errors = a8.smooth_alpha_errors(zero, torch.ones(3, 4), torch.zeros(4), torch.zeros(4), a8.ALPHA_GRID)
    assert set(errors.values()) == {0.0}
    assert a8.choose_alpha(errors) == 0.5


def runtime_with_token0(*, enabled=True, bits=8, smooth0=3., output0=2.):
    base = _small_artifact_runtime()
    coefficients = dict(base.coefficients)

    def pair(name, value):
        multiplier, shift = contract.encode_multiplier(value, 24)
        coefficients[name+".M"], coefficients[name+".shift"] = multiplier.to(torch.int32), shift.to(torch.int16)

    names = [key.removesuffix(".weight") for key in base.weights if key != "shared_embedding_lm_head.weight"]
    for name in names + ["lm_head"]:
        pair(name+".smooth_token0", smooth0)
        if name.endswith(".v_proj"):
            pair(name+".to_v_cache_token0", torch.full((2,), output0))
        else:
            pair(name+".output_token0", output0)
    config = {**base.config, "linear_input_bits": bits, "token0": {"enabled": enabled}}
    return ContractRuntime.from_tensors(config, base.weights, coefficients)


def test_runtime_linear_applies_token0_coefficients_only_to_position0_rows():
    runtime = runtime_with_token0()
    name = "lm_head"
    values = torch.tensor([[[50, -50, 20, -20], [5, 6, -7, 8], [40, -40, 40, -40]]], dtype=torch.int16)
    runtime.coefficients[name+".smooth.M"], runtime.coefficients[name+".smooth.shift"] = (
        torch.tensor(1 << 23, dtype=torch.int32), torch.tensor(23, dtype=torch.int8))
    output = {"": ([1 << 20, 1 << 19, 3 << 19, 2 << 20, 1 << 18, 1 << 27, 1 << 20], 20),
              "_token0": ([1 << 19, 5 << 18, 1 << 20, 3 << 20, 1 << 17, 1 << 26, 3 << 19], 21)}
    for suffix, (multipliers, shift) in output.items():
        runtime.coefficients[name+".output"+suffix+".M"] = torch.tensor(multipliers, dtype=torch.int32)
        runtime.coefficients[name+".output"+suffix+".shift"] = torch.full((7,), shift, dtype=torch.int8)
    smooth0 = contract.encode_multiplier(3., 24)
    token0 = torch.tensor([True, False, False])
    actual = runtime._linear(name, values, token0)[0].tolist()
    weight = runtime.weights["shared_embedding_lm_head.weight"].tolist()
    expected = []
    for row_index, row in enumerate(values[0].tolist()):
        first = row_index == 0
        source = [reference_clamp(reference_shift(code*int(smooth0[0]), int(smooth0[1])) if first else code, 8)
                  for code in row]
        multipliers, shift = output["_token0" if first else ""]
        expected.append([reference_clamp(reference_shift(sum(a*b for a, b in zip(source, w))*multipliers[o], shift), 8)
                         for o, w in enumerate(weight)])
    assert actual == expected
    assert reference_clamp(reference_shift(50*int(smooth0[0]), int(smooth0[1])), 8) == 127  # biên A8 ở hàng token 0
    assert runtime._linear(name, values)[0, 0].tolist() != actual[0]  # không có mask: dùng hệ số thường


def test_token0_runtime_full_and_cached_decode_codes_match_and_preserve_prefix():
    runtime = runtime_with_token0(smooth0=0.5, output0=3.)
    ids = [1, 3, 2, 6, 0, 5, 4]
    full = runtime(input_ids=torch.tensor([ids]))
    cached_logits, cached_codes, prefix_preserved = runtime.cached_outputs(ids, prefill_length=3, verify_prefix=True)
    assert torch.equal(cached_codes, full.logit_codes[0])
    assert torch.equal(cached_logits, full.logits[0])
    assert prefix_preserved is True
    disabled = runtime_with_token0(enabled=False, smooth0=0.5, output0=3.)
    plain = disabled(input_ids=torch.tensor([ids])).logit_codes
    assert not torch.equal(plain[0, 0], full.logit_codes[0, 0])  # hàng vị trí 0 đi qua hệ số riêng


def test_runtime_requires_token0_coefficients_when_the_artifact_enables_token0():
    base = _small_artifact_runtime()
    with pytest.raises(ValueError, match="smooth_token0"):
        ContractRuntime.from_tensors({**base.config, "token0": {"enabled": True}}, base.weights, base.coefficients)


def sim_linear_adapter(bits, rows0=None, delta0=None):
    points = {"lm_head.input": SimpleNamespace(fq=SimpleNamespace(scale=torch.tensor([0.5])))}
    baseline = SimpleNamespace(points=points, smooth_scales={}, config={"activation_bits": bits})
    if rows0 is not None:
        points["lm_head.input.token0"] = SimpleNamespace(fq=SimpleNamespace(scale=torch.tensor([delta0])))
        baseline.position0 = SimpleNamespace(rows_for=lambda x: rows0)
    return contract.ContractAdapter(None, baseline, {"lm_head.output": {}})


def test_linear_input_bits_clip_runtime_and_contract_adapter_codes():
    codes = torch.tensor([[[3000, -3000, 100, -100]]], dtype=torch.int16)
    # Mỗi hàng đọc trực tiếp một cột đầu vào (cột 0/1 là 3000/-3000), ba hàng còn lại bằng 0.
    weight = torch.tensor([[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]] + [[0]*4]*3, dtype=torch.int8)
    for bits, expected in ((8, [127, -128, 100, -100]), (12, [2047, -2048, 100, -100])):
        runtime = _small_artifact_runtime()
        runtime.weights["shared_embedding_lm_head.weight"] = weight
        runtime.formats["lm_head.output"] = RuntimeFormat(32, 1.)
        runtime.coefficients["lm_head.output.M"] = torch.full((7,), 1 << 23, dtype=torch.int32)
        runtime.coefficients["lm_head.output.shift"] = torch.full((7,), 23, dtype=torch.int8)
        runtime.coefficients["lm_head.smooth.M"] = torch.tensor(1 << 23, dtype=torch.int32)
        runtime.coefficients["lm_head.smooth.shift"] = torch.tensor(23, dtype=torch.int8)
        runtime.linear_input_bits = bits
        assert runtime._linear("lm_head", codes)[0, 0, :4].tolist() == expected

        adapter = sim_linear_adapter(bits)
        source, output = contract.Format(16, 0.5), contract.Format(32, 0.5)
        adapter.trial = {"integer_coefficients": True, "coefficient_bits": 24, "metrics": False}
        adapter.formats = {"model.norm.output": source, "lm_head.output": output}
        adapter.weights["shared_embedding_lm_head.weight"] = (
            weight, weight.double(), contract.Format(8, [1.]*7, 0))
        actual = adapter.linear(None, contract.decoded(codes, source), "lm_head", None)
        assert actual._contract[0][0, 0, :4].tolist() == expected


def test_contract_adapter_token0_rows_match_the_artifact_runtime_linear():
    rng = np.random.default_rng(11)
    weight = torch.from_numpy(rng.integers(-60, 61, (7, 4), dtype=np.int8))
    weight_scale = torch.tensor([.011, .013, .017, .019, .023, .029, .031], dtype=torch.float64)
    codes = torch.from_numpy(rng.integers(-3000, 3001, (1, 4, 4))).to(torch.int16)
    rows0 = torch.tensor([[True, False, False, False]])
    source, target = contract.Format(16, 0.25), contract.Format(16, 0.125)
    delta, delta0 = torch.tensor([0.5], dtype=torch.float64), torch.tensor([2.], dtype=torch.float64)

    def run_both(rows):
        runtime = _small_artifact_runtime()
        runtime.weights["shared_embedding_lm_head.weight"] = weight
        runtime.formats["lm_head.output"] = RuntimeFormat(16, 0.125)
        runtime.linear_input_bits = 8

        def pair(name, value):
            multiplier, shift = contract.encode_multiplier(value, 24)
            runtime.coefficients[name+".M"] = multiplier.to(torch.int32)
            runtime.coefficients[name+".shift"] = shift.to(torch.int16)

        pair("lm_head.smooth", 0.25/delta)
        pair("lm_head.output", delta*weight_scale/0.125)
        if rows is not None:
            pair("lm_head.smooth_token0", 0.25/delta0)
            pair("lm_head.output_token0", delta0*weight_scale/0.125)
        from_runtime = runtime._linear("lm_head", codes, None if rows is None else rows[0]).to(torch.int64)

        adapter = sim_linear_adapter(8, rows, 2.)
        adapter.trial = {"integer_coefficients": True, "coefficient_bits": 24, "metrics": False}
        adapter.formats = {"model.norm.output": source, "lm_head.output": target}
        adapter.weights["shared_embedding_lm_head.weight"] = (
            weight, weight.double(), contract.Format(8, weight_scale.tolist(), 0))
        from_adapter = adapter.linear(None, contract.decoded(codes, source), "lm_head", None)
        return from_runtime, from_adapter._contract[0].to(torch.int64)

    with_token0 = run_both(rows0)
    without = run_both(None)
    assert torch.equal(*with_token0) and torch.equal(*without)
    assert torch.equal(with_token0[0][:, 1:], without[0][:, 1:])  # hàng khác vị trí 0 không đổi
    assert not torch.equal(with_token0[0][:, 0], without[0][:, 0])  # hàng vị trí 0 dùng scale riêng


def test_contract_adapter_token0_full_and_cached_codes_match_and_preserve_prefix():
    torch.manual_seed(93)
    model = LlamaForCausalLM(LlamaConfig(vocab_size=32, hidden_size=576, intermediate_size=128,
        num_hidden_layers=2, num_attention_heads=9, num_key_value_heads=3, tie_word_embeddings=True,
        rms_norm_eps=1e-5, attn_implementation="eager")).eval()
    baseline = smooth_adapter(model, 0.5, token0=True)
    ids = [1, 7, 4, 9, 3, 5, 2]
    with torch.inference_mode():
        calibrate(baseline, model, ids)
        assert any(not torch.equal(point.fq.scale, baseline.points[name.removesuffix(".token0")].fq.scale)
                   for name, point in baseline.points.items() if name.endswith(".input.token0"))
        full_signed_range(baseline)
        baseline.set_mode("quantize")
        profiler = IntermediateProfiler(model, baseline)
        with profiler.attached():
            full_logits(model, ids)
        stats = {name: value.summary() for name, value in profiler.points.items()}
        adapter = contract.ContractAdapter(model, baseline, stats)
        points = {name: {"bits": 12} for name in adapter.inventory}
        for name, family in adapter.inventory.items():
            if family == "residual":
                points[name] = {"bits": 16, "policy": "per_channel"}
        adapter.set_trial({"points": points, "integer_coefficients": True, "coefficient_bits": 16,
            "mac_dtype": "float64", "metrics": False, "check_mac": True,
            "nonlinear": {"rms": {"seed_entries": 32, "t_fractional_bits": 24},
                          "rope": {"coefficient_bits": 12}, "silu": {"segments": 8, "threshold": 6},
                          "softmax": {"entries": 32, "c": 8, "probability_bits": 12}}})
        with adapter.attached():
            expected = full_logits(model, ids).clone()
            cache, rows = DynamicCache(), []
            for start, stop in [(0, 3), (3, 4), (4, 5), (5, 6), (6, 7)]:
                prefix = [(k.clone(), v.clone()) for k, v in zip(cache.key_cache, cache.value_cache)]
                result = model(input_ids=torch.tensor([ids[start:stop]]),
                               attention_mask=torch.ones((1, stop), dtype=torch.long),
                               position_ids=torch.arange(start, stop)[None],
                               cache_position=torch.arange(start, stop), past_key_values=cache, use_cache=True)
                cache = result.past_key_values
                rows.append(result.logits[0])
                for layer, (old_k, old_v) in enumerate(prefix):
                    assert torch.equal(cache.key_cache[layer][:, :, :start], old_k)
                    assert torch.equal(cache.value_cache[layer][:, :, :start], old_v)
            assert torch.equal(torch.cat(rows), expected)
        checks = adapter.mac_checks
        assert len(checks) == 15 and sum(item["different_accumulators"] for item in checks.values()) == 0
        # Mã đầu vào Linear bị cắt trong [-128, 127] của A8.
        assert baseline.config["activation_bits"] == 8
    baseline.restore()
