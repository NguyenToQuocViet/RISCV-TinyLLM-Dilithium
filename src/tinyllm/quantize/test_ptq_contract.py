"""Independent numerical oracles for proposed integer interfaces and nonlinearities."""
from fractions import Fraction
import json
import math
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import numpy as np
import pytest
import torch
from safetensors.torch import save_file

import ptq_contract as contract
import ptq_contract_search as contract_search
from ptq_contract_runtime import ContractRuntime, RuntimeFormat, load_prepared_contract


def reference_divide(numerator, denominator):
    """Fraction.__round__ implements nearest/even independently of the DUT."""
    return round(Fraction(int(numerator), int(denominator)))


def reference_shift(value, shift):
    if shift >= 0:
        return reference_divide(value, 1 << shift)
    return int(value) * (1 << -shift)


def reference_clamp(value, bits, signed=True):
    lower = -(1 << (bits - 1)) if signed else 0
    upper = (1 << (bits - int(signed))) - 1
    return min(upper, max(lower, int(value)))


def reference_softmax_lut(entries, cutoff, exp_bits=8):
    limit = (1 << exp_bits) - 1
    values = [round(limit * math.exp(-cutoff * j / (entries - 1)))
              for j in range(entries)]
    values[-1] = 0
    return values


def reference_normalize_exponentials(values, probability_bits):
    total = sum(map(int, values))
    assert total > 0
    limit = (1 << probability_bits) - 1
    return [reference_divide(limit * int(value), total) for value in values]


@pytest.mark.parametrize('denominator', [1, 2, 3, 7, 256, 2**31+1, 2**62])
def test_signed_division_matches_fraction_including_ties(denominator):
    values = [-2**63, -2**62-1, -257, -15, -7, -3, -1, 0, 1, 3, 7, 15,
              257, 2**62+1, 2**63-1]
    expected = [reference_divide(n, denominator) for n in values]
    actual = contract.round_divide(torch.tensor(values), denominator)
    assert actual.tolist() == expected
    assert [contract.round_divide_scalar(n, denominator) for n in values] == expected


@pytest.mark.parametrize('shift', [-5, -1, 0, 1, 2, 12, 62, 63, 64, 80])
def test_signed_shift_matches_fraction(shift):
    values = [-65, -33, -17, -7, -3, -1, 0, 1, 3, 7, 17, 33, 65]
    if shift >= 0:
        values += [-2**63, -2**62-1, 2**62+1, 2**63-1]
    assert contract.round_shift(torch.tensor(values), shift).tolist() == [
        reference_shift(n, shift) for n in values]


@pytest.mark.parametrize('bits', [16, 24, 31])
def test_normalized_multiplier_precision_and_exact_product(bits):
    coefficients = np.r_[0., np.geomspace(1e-12, 1e12, 31),
                         -np.geomspace(1e-12, 1e12, 31)]
    multiplier, shift = contract.encode_multiplier(coefficients, bits)
    reconstructed = np.ldexp(multiplier.numpy().astype(np.float64), -shift.numpy())
    assert np.all(np.abs(reconstructed-coefficients) <= np.abs(coefficients)*2.**(-bits))
    assert int(multiplier.abs().max()) < 1 << bits
    values = torch.tensor([-1048577, -3, -1, 0, 1, 3, 1048577])[:, None]
    # Restrict the output to INT64; the separate wide-product case forces bigint.
    multiplier, shift = contract.encode_multiplier(coefficients[:32], bits)
    expected = [[reference_shift(int(x)*int(m), int(s))
                 for m, s in zip(multiplier, shift)] for x in values[:, 0]]
    assert contract.multiply_shift(values, multiplier, shift).tolist() == expected


def test_wide_product_rounds_before_narrowing():
    values = [2**40+3, -2**40-3, 2**44-1]
    multiplier, shift = 2**30-1, 42
    expected = [reference_shift(n*multiplier, shift) for n in values]
    assert contract.multiply_shift(torch.tensor(values), multiplier, shift).tolist() == expected


@pytest.mark.parametrize('bits', [8, 12, 16])
def test_quantizer_full_signed_endpoints_and_saturation(bits):
    lower, upper = -(1 << (bits-1)), (1 << (bits-1))-1
    scaled = [lower-1, lower, -3.5, -2.5, -.5, 0, .5, 2.5, 3.5, upper, upper+1]
    value = torch.tensor(scaled, dtype=torch.float64)*.125
    actual, raw = contract.encode(value, contract.Format(bits, .125))
    expected_raw = [round(v) for v in scaled]
    assert raw.tolist() == expected_raw
    assert actual.tolist() == [reference_clamp(v, bits) for v in expected_raw]


def test_carrier_requantizes_using_integer_codes_and_per_axis_scales():
    codes = torch.tensor([[[-128, -3, 0, 127], [1, 2, 3, 4]]])
    source = contract.Format(8, [.125, .25, .5, 1.], -1)
    carrier = contract.decoded(codes, source)
    actual, raw = contract.encode(carrier, contract.Format(12, .125), 16)
    expected = codes * torch.tensor([1, 2, 4, 8])
    assert torch.equal(raw, expected) and torch.equal(actual, expected)


@pytest.mark.parametrize('cutoff', [6, 8, 10])
@pytest.mark.parametrize('entries', [32, 64])
def test_softmax_lut_matches_independent_exp_rounding(cutoff, entries):
    assert contract.softmax_lut(cutoff, entries).tolist() == reference_softmax_lut(entries, cutoff)


@pytest.mark.parametrize('length', [1, 255, 256, 512])
@pytest.mark.parametrize('probability_bits', [8, 12, 16])
def test_uniform_softmax_preserves_proposed_rounding_semantics(length, probability_bits):
    scores = torch.zeros((1, 1, 1, length), dtype=torch.int64)
    allowed = torch.ones_like(scores, dtype=torch.bool)
    actual = contract.index_softmax(scores, .0625, allowed, probability_bits=probability_bits)
    expected = reference_normalize_exponentials([255]*length, probability_bits)
    assert actual.flatten().tolist() == expected
    if length == 512:
        assert bool((actual == 0).all()) == (probability_bits == 8)


def test_softmax_mask_and_integer_index_match_scalar_reference():
    values = [17, -1, -12, 10, -400, 16, 17]
    allowed = [True, True, True, False, True, True, True]
    lut = reference_softmax_lut(32, 8)
    maximum = max(v for v, valid in zip(values, allowed) if valid)
    exponential = [lut[min(31, reference_divide((maximum-v)*31, 128))] if valid else 0
                   for v, valid in zip(values, allowed)]
    expected = reference_normalize_exponentials(exponential, 12)
    actual = contract.index_softmax(torch.tensor(values)[None, None, None], .0625,
                                   torch.tensor(allowed)[None, None, None], probability_bits=12)
    assert actual.flatten().tolist() == expected
    with pytest.raises(ValueError, match='valid key'):
        contract.index_softmax(torch.tensor(values), .0625, torch.zeros(7, dtype=torch.bool))


@pytest.mark.parametrize('bits', [8, 12, 16])
def test_rope_rom_and_rotation_have_exact_scalar_integer_oracle(bits):
    positions = torch.tensor([[0, 1, 511]])
    codes = (torch.arange(2*3*64).reshape(1, 2, 3, 64)*19 % 4096)-2048
    limit = (1 << (bits-1))-1
    expected = np.empty(tuple(codes.shape), dtype=np.int64)
    for h in range(2):
        for t, position in enumerate(positions[0].tolist()):
            for j in range(32):
                phase = position*100000.**(-2*j/64)
                cosine, sine = round(math.cos(phase)*limit), round(math.sin(phase)*limit)
                a, b = int(codes[0, h, t, j]), int(codes[0, h, t, j+32])
                expected[0, h, t, j] = reference_divide(a*cosine-b*sine, limit)
                expected[0, h, t, j+32] = reference_divide(b*cosine+a*sine, limit)
    actual = contract.integer_rope(codes, positions, bits)
    np.testing.assert_array_equal(actual.numpy(), expected)
    assert torch.equal(actual[:, :, 0], codes[:, :, 0])


@pytest.mark.parametrize('t_fractional_bits', [24, 32, 40])
def test_rmsnorm_zero_constant_signed_outlier_against_real_reference(t_fractional_bits):
    rows = np.array([[0]*576, [100]*576, [-100]*576,
                     [32767]+[1]*575, [(-1)**j*(j % 101) for j in range(576)]], dtype=np.int64)
    gamma = np.linspace(.5, 1.5, 576)
    input_scale, output_scale = .03125, .001
    fmt = contract.Format(16, output_scale)
    actual = contract.rms_integer(torch.from_numpy(rows), input_scale,
                                  torch.from_numpy(gamma), fmt, coefficient_bits=24,
                                  t_fractional_bits=t_fractional_bits)
    real = rows.astype(np.float64)*input_scale
    expected = gamma*real/np.sqrt(np.mean(real*real, axis=-1, keepdims=True)+1e-5)
    reconstructed = actual.numpy()*output_scale
    # One Q14 Newton step + output rounding; input/output clipping is excluded.
    assert np.max(np.abs(reconstructed-expected)) < .005
    assert not np.any(actual[0].numpy())


@pytest.mark.parametrize('bits,container', [(8,8),(12,16),(16,16),(24,32),(32,32),
                                           (40,64),(48,64),(63,64)])
def test_logical_width_uses_a_container_that_contains_it(bits, container):
    description = contract.Format(bits, 1.).dictionary()
    assert description['container_bits'] == container
    assert description['container_bits'] >= description['bits']


@pytest.mark.parametrize('reduction', [576, 1536])
def test_fp64_code_reduction_matches_independent_integer_extrema_and_cancellation(reduction):
    rng = np.random.default_rng(17)
    activation = rng.integers(-2048, 2048, size=(4, reduction), dtype=np.int64)
    weight = rng.integers(-128, 128, size=(5, reduction), dtype=np.int64)
    activation[0] = -2048
    activation[1] = 2047
    activation[2] = np.resize(np.array([-2048,2047]), reduction)
    weight[0] = -128
    weight[1] = 127
    weight[2] = np.resize(np.array([127,-127]), reduction)
    expected = [[sum(int(a)*int(w) for a,w in zip(row,col)) for col in weight]
                for row in activation]
    actual = torch.from_numpy(activation).double() @ torch.from_numpy(weight).double().T
    assert actual.long().tolist() == expected
    assert reduction*2048*128 < 2**53


def test_silu_breakpoints_tails_and_approximation_error():
    table = contract.fit_silu(segments=16, threshold=8, coefficient_bits=24)
    points = sorted(set([-10., 10.]+table['breakpoints']+
                        [v-.001 for v in table['breakpoints']]+
                        [v+.001 for v in table['breakpoints']]))
    scale = 1/4096
    codes = torch.tensor([round(x/scale) for x in points])
    fmt = contract.Format(24, scale)
    actual = contract.silu_integer(codes, scale, fmt, table, 24).numpy()*scale
    x = codes.numpy()*scale
    expected = x/(1+np.exp(-x))
    assert np.max(np.abs(actual-expected)) < .04
    assert np.all(actual[x < -8] == 0)
    np.testing.assert_array_equal(actual[x >= 8], x[x >= 8])


def test_artifact_silu_promotes_int16_before_out_of_range_breakpoint_checks():
    # At this input scale, the +/-8 breakpoints sit just outside the INT16
    # container. The artifact runner stores 16-bit boundary outputs as INT16.
    input_scale = 1/4096
    output_format = contract.Format(16, 1/8192)
    table = contract.fit_silu(segments=32, threshold=8, coefficient_bits=24)
    compiled = contract.compile_silu(input_scale, output_format, table, 24)
    multiplier, shift = contract.encode_multiplier(input_scale/output_format.scale, 24)
    prefix = "model.layers.0.mlp.pwl."
    runtime = ContractRuntime.__new__(ContractRuntime)
    runtime.coefficients = {
        prefix+"breakpoints": torch.tensor(compiled["breakpoints"], dtype=torch.int32),
        prefix+"slopes": torch.tensor(compiled["slopes"], dtype=torch.int32),
        prefix+"intercepts": torch.tensor(compiled["intercepts"], dtype=torch.int32),
        prefix+"shifts": torch.tensor(compiled["shifts"], dtype=torch.int8),
        prefix+"positive.M": multiplier.to(torch.int32),
        prefix+"positive.shift": shift.to(torch.int8),
    }
    runtime.formats = {"model.layers.0.mlp.silu_output": RuntimeFormat(16, output_format.scale)}
    codes = torch.arange(-(1 << 15), 1 << 15, dtype=torch.int16)
    expected = contract.silu_integer(codes.to(torch.int64), input_scale, output_format, table, 24)
    actual_int16 = runtime._silu(0, codes)
    actual_int64 = runtime._silu(0, codes.to(torch.int64))
    assert torch.equal(actual_int16, expected)
    assert torch.equal(actual_int64, expected)


def test_artifact_silu_uses_serialized_positive_tail_multiplier_in_int16_range():
    root = Path(__file__).resolve().parent
    frozen = json.loads((root/"results/numerical/contract_search/combined_high/config.json").read_text())
    index = 2
    prefix = f"model.layers.{index}.mlp"
    input_scale = frozen["formats"][prefix+".gate_proj.output"]["scale"]
    output_spec = frozen["formats"][prefix+".silu_output"]
    output_format = contract.Format(output_spec["bits"],output_spec["scale"],output_spec.get("axis"),
                                    not output_spec["signed"])
    table = frozen["pwl_reference"]
    compiled = contract.compile_silu(input_scale,output_format,table,24)
    tail_start = compiled["breakpoints"][-1]
    assert -(1 << 15) <= tail_start < (1 << 15)-1
    runtime = ContractRuntime.__new__(ContractRuntime)
    key = prefix+".pwl."
    multiplier,shift = contract.encode_multiplier(input_scale/output_format.scale,24)
    runtime.coefficients = {key+"breakpoints":torch.tensor(compiled["breakpoints"],dtype=torch.int32),
        key+"slopes":torch.tensor(compiled["slopes"],dtype=torch.int32),
        key+"intercepts":torch.tensor(compiled["intercepts"],dtype=torch.int32),
        key+"shifts":torch.tensor(compiled["shifts"],dtype=torch.int8),
        key+"positive.M":multiplier.to(torch.int32),key+"positive.shift":shift.to(torch.int8)}
    runtime.formats = {prefix+".silu_output":RuntimeFormat(output_format.bits,output_format.scale,
                                                            output_format.axis,not output_format.unsigned)}
    codes = torch.arange(-(1 << 15),1 << 15,dtype=torch.int16)
    expected = contract.silu_integer(codes.to(torch.int64),input_scale,output_format,table,24)
    actual = runtime._silu(index,codes)
    assert torch.equal(actual,expected)
    tail_input = torch.tensor([tail_start+1],dtype=torch.int16)
    tail_output = runtime._silu(index,tail_input)
    assert int(tail_output) != 0
    changed = {name:value.clone() for name,value in runtime.coefficients.items()}
    changed[key+"positive.M"].zero_()
    mutated = ContractRuntime.__new__(ContractRuntime)
    mutated.coefficients,mutated.formats = changed,runtime.formats
    assert not torch.equal(mutated._silu(index,tail_input),tail_output)


def _small_artifact_runtime():
    hidden, intermediate, vocab, query_heads, kv_heads, head_dim = 4, 6, 7, 2, 1, 2
    formats = {}

    def add_format(name, bits=8, scale=1., axis=None, signed=True):
        formats[name] = contract.Format(bits, scale, axis, not signed).dictionary()

    add_format("model.embed_tokens.output")
    for layer in range(1):
        prefix = f"model.layers.{layer}"
        add_format(prefix+".input_layernorm.output")
        add_format(prefix+".post_attention_layernorm.output")
        add_format(prefix+".residual_after_attention")
        add_format(prefix+".residual_after_ffn")
        attention = prefix+".self_attn"
        add_format(attention+".q_proj.output", scale=[1.]*hidden, axis=-1)
        add_format(attention+".k_proj.output", scale=[1.]*kv_heads*head_dim, axis=-1)
        add_format(attention+".query_post_rope", scale=[1.]*query_heads, axis=1)
        add_format(attention+".score", scale=[1.]*query_heads, axis=1)
        add_format(attention+".probability_unmasked", bits=12, scale=1/4095, signed=False)
        add_format(attention+".context")
        add_format(attention+".o_proj.output")
        mlp = prefix+".mlp"
        for name, count in (("gate_proj.output", intermediate), ("up_proj.output", intermediate),
                            ("silu_output", intermediate), ("gate_product", intermediate),
                            ("down_proj.output", hidden)):
            add_format(mlp+"."+name)
    add_format("model.norm.output")
    add_format("lm_head.output")

    rng = np.random.default_rng(29)
    weights = {"shared_embedding_lm_head.weight": torch.from_numpy(rng.integers(-4, 5, (vocab, hidden), dtype=np.int8))}
    for name, shape in {
        "model.layers.0.self_attn.q_proj.weight":(hidden, hidden),
        "model.layers.0.self_attn.k_proj.weight":(kv_heads*head_dim, hidden),
        "model.layers.0.self_attn.v_proj.weight":(kv_heads*head_dim, hidden),
        "model.layers.0.self_attn.o_proj.weight":(hidden, hidden),
        "model.layers.0.mlp.gate_proj.weight":(intermediate, hidden),
        "model.layers.0.mlp.up_proj.weight":(intermediate, hidden),
        "model.layers.0.mlp.down_proj.weight":(hidden, intermediate),
    }.items():
        weights[name] = torch.from_numpy(rng.integers(-4, 5, shape, dtype=np.int8))

    coefficients = {}

    def pair(name, value):
        multiplier, shift = contract.encode_multiplier(value, 24)
        coefficients[name+".M"] = multiplier.to(torch.int32)
        coefficients[name+".shift"] = shift.to(torch.int16)

    pair("embedding.to_residual", torch.ones(vocab))
    linear_shapes = {
        "model.layers.0.self_attn.q_proj":hidden,
        "model.layers.0.self_attn.k_proj":kv_heads*head_dim,
        "model.layers.0.self_attn.v_proj":kv_heads*head_dim,
        "model.layers.0.self_attn.o_proj":hidden,
        "model.layers.0.mlp.gate_proj":intermediate,
        "model.layers.0.mlp.up_proj":intermediate,
        "model.layers.0.mlp.down_proj":hidden,
        "lm_head":vocab,
    }
    for name, _ in linear_shapes.items():
        pair(name+".smooth", 1.)
        if name.endswith(".v_proj"):
            pair(name+".to_v_cache", torch.ones(kv_heads*head_dim))
        else:
            pair(name+".output", 1.)
    pair("model.layers.0.self_attn.q_rope_to_qk", torch.ones(query_heads))
    pair("model.layers.0.self_attn.k_rope_to_cache", torch.ones(kv_heads))
    pair("model.layers.0.self_attn.qk_to_score", torch.ones(query_heads))
    pair("model.layers.0.self_attn.score_to_index", (32-1)/8)
    pair("model.layers.0.self_attn.pv_to_context", torch.full((query_heads,), 1/4095))
    for name in ("model.layers.0.residual_after_attention", "model.layers.0.residual_after_ffn"):
        pair(name+".left_to_guard", 1 << 20)
        pair(name+".right_to_guard", 1 << 20)
    for name in ("model.layers.0.input_layernorm", "model.layers.0.post_attention_layernorm", "model.norm"):
        pair(name+".to_t", (1 << 40)/hidden)
        pair(name+".gamma_output", torch.ones(hidden))
        coefficients[name+".epsilon"] = torch.tensor(round(1e-5*(1 << 40)), dtype=torch.int32)
    pwl = "model.layers.0.mlp.pwl."
    coefficients[pwl+"breakpoints"] = torch.tensor([-1000, 1000], dtype=torch.int32)
    coefficients[pwl+"slopes"] = torch.tensor([1], dtype=torch.int32)
    coefficients[pwl+"intercepts"] = torch.tensor([0], dtype=torch.int32)
    coefficients[pwl+"shifts"] = torch.tensor([0], dtype=torch.int16)
    pair("model.layers.0.mlp.pwl.positive", 1.)
    pair("model.layers.0.mlp.product", 1.)
    coefficients["rope.cos"] = torch.full((512, head_dim//2), (1 << 15)-1, dtype=torch.int16)
    coefficients["rope.sin"] = torch.zeros((512, head_dim//2), dtype=torch.int16)
    coefficients["softmax.exp_lut"] = contract.softmax_lut(8, 32).to(torch.uint8)
    coefficients["rms.seed_lut"] = contract.rms_seed_lut(64).to(torch.int16)
    config = {
        "artifact_format":"tinyllm_integer_contract_v1",
        "formats":formats,
        "model":{"layers":1,"hidden_size":hidden,"intermediate_size":intermediate,
                 "vocab_size":vocab,"query_heads":query_heads,"kv_heads":kv_heads,
                 "head_dim":head_dim,"rope_theta":100000.,"max_positions":512},
        "nonlinear":{"rms":{"seed_entries":64},"rope":{"coefficient_bits":16},
                     "softmax":{"entries":32,"c":8,"probability_bits":12},
                     "silu":{"segments":1,"threshold":8}},
        "nonlinear_contract":{"rms_t_fractional_bits":40},
        "aligned_norm_inputs":{},
    }
    return ContractRuntime.from_tensors(config, weights, coefficients)


def test_artifact_runtime_consumes_loaded_weight_multiplier_and_lut(monkeypatch):
    # A source checkpoint, qparams, or compile helper is not needed to execute
    # the prepared artifact. Mutations prove the three bundles are consumed.
    monkeypatch.setattr(contract, "fit_silu", lambda *_a, **_k: pytest.fail("runtime attempted SiLU fitting"))
    monkeypatch.setattr(contract, "compile_silu", lambda *_a, **_k: pytest.fail("runtime attempted SiLU compilation"))
    runtime = _small_artifact_runtime()
    ids = torch.tensor([[1, 3, 2]], dtype=torch.long)
    baseline = runtime(input_ids=ids).logit_codes

    changed_weights = {name:value.clone() for name,value in runtime.weights.items()}
    changed_weights["shared_embedding_lm_head.weight"][1, 0] += 1
    with_changed_weight = ContractRuntime.from_tensors(runtime.config, changed_weights, runtime.coefficients)
    assert not torch.equal(baseline, with_changed_weight(input_ids=ids).logit_codes)

    changed_coefficients = {name:value.clone() for name,value in runtime.coefficients.items()}
    changed_coefficients["lm_head.output.M"].zero_()
    with_changed_multiplier = ContractRuntime.from_tensors(runtime.config, runtime.weights, changed_coefficients)
    assert not torch.equal(baseline, with_changed_multiplier(input_ids=ids).logit_codes)

    score = torch.tensor([[[[0, -1, -2]], [[0, -1, -2]]]], dtype=torch.int64)
    allowed = torch.ones_like(score, dtype=torch.bool)
    normal = runtime._softmax(score, allowed, "model.layers.0.self_attn")
    changed_coefficients = {name:value.clone() for name,value in runtime.coefficients.items()}
    changed_coefficients["softmax.exp_lut"][1:] = 0
    with_changed_lut = ContractRuntime.from_tensors(runtime.config, runtime.weights, changed_coefficients)
    mutated = with_changed_lut._softmax(score, allowed, "model.layers.0.self_attn")
    assert not torch.equal(normal, mutated)


def test_artifact_runtime_linear_matches_independent_rowwise_integer_dot():
    runtime = _small_artifact_runtime()
    name = "lm_head"
    values = torch.tensor([[[1, -2, 3, -4]]], dtype=torch.int16)
    runtime.coefficients[name+".smooth.M"] = torch.tensor(1 << 23, dtype=torch.int32)
    runtime.coefficients[name+".smooth.shift"] = torch.tensor(23, dtype=torch.int8)
    multipliers = torch.tensor([1 << 20, 1 << 19, 3 << 19, 2 << 20,
                                1 << 18, 1 << 27, 1 << 20], dtype=torch.int32)
    shifts = torch.full((7,), 20, dtype=torch.int8)
    runtime.coefficients[name+".output.M"] = multipliers
    runtime.coefficients[name+".output.shift"] = shifts
    actual = runtime._linear(name, values)[0, 0].tolist()
    weight = runtime.weights["shared_embedding_lm_head.weight"].tolist()
    expected = []
    for row_index,row in enumerate(weight):
        accumulator = sum(int(code)*int(w) for code,w in zip(values[0,0].tolist(),row))
        scaled = reference_shift(accumulator*int(multipliers[row_index]),int(shifts[row_index]))
        expected.append(reference_clamp(scaled,8))
    assert actual == expected
    assert len(set(expected)) > 1
    assert 127 in expected or -128 in expected  # exercise destination saturation


def test_tiny_artifact_runtime_full_and_cached_decode_codes_match_and_preserve_prefix():
    runtime = _small_artifact_runtime()
    ids = [1, 3, 2, 6, 0, 5, 4]
    full = runtime(input_ids=torch.tensor([ids], dtype=torch.long))
    cached_logits, cached_codes, prefix_preserved = runtime.cached_outputs(
        ids, prefill_length=3, verify_prefix=True)
    assert torch.equal(cached_codes, full.logit_codes[0])
    assert torch.equal(cached_logits, full.logits[0])
    assert prefix_preserved is True


def test_artifact_runtime_loads_serialized_files_without_source_bundle(tmp_path, monkeypatch):
    monkeypatch.setattr(contract, "fit_silu", lambda *_a, **_k: pytest.fail("runtime attempted SiLU fitting"))
    monkeypatch.setattr(contract, "compile_silu", lambda *_a, **_k: pytest.fail("runtime attempted SiLU compilation"))
    fixture = _small_artifact_runtime()
    config = dict(fixture.config)
    config["weights"] = "weights.safetensors"
    config["coefficients"] = "coefficients.safetensors"
    assert "frozen_source_qparams" not in config
    assert "checkpoint" not in config
    save_file(fixture.weights, str(tmp_path/"weights.safetensors"))
    save_file(fixture.coefficients, str(tmp_path/"coefficients.safetensors"))
    (tmp_path/"config.json").write_text(json.dumps(config), encoding="utf-8")
    loaded = load_prepared_contract(tmp_path/"config.json")
    ids = torch.tensor([[1, 3, 2]], dtype=torch.long)
    assert torch.equal(fixture(input_ids=ids).logit_codes, loaded(input_ids=ids).logit_codes)
    assert not (tmp_path/"qparams.safetensors").exists()
    assert not (tmp_path/"model.safetensors").exists()

    child = r'''
import builtins, json, sys, torch
blocked = {"fp32_reference", "ptq_contract", "ptq_contract_search", "ptq_fake_quant",
           "ptq_intermediate_calibrate", "ptq_eval", "ptq_finalize", "transformers"}
original_import = builtins.__import__
def guarded_import(name, *args, **kwargs):
    if name.split(".", 1)[0] in blocked:
        raise RuntimeError("forbidden preparation/reference import: " + name)
    return original_import(name, *args, **kwargs)
builtins.__import__ = guarded_import
from ptq_contract_runtime import load_prepared_contract
runtime = load_prepared_contract(sys.argv[1])
output = runtime(input_ids=torch.tensor([[1, 3, 2]], dtype=torch.long), logits_to_keep=1)
print(json.dumps(output.logit_codes[0].tolist()))
'''
    completed = subprocess.run([sys.executable,"-c",child,str(tmp_path/"config.json")],
        cwd=Path(__file__).resolve().parent,text=True,capture_output=True,check=True)
    actual = json.loads(completed.stdout.strip().splitlines()[-1])
    expected = fixture(input_ids=ids,logits_to_keep=1).logit_codes[0].tolist()
    assert actual == expected


def test_artifact_runtime_aligns_per_channel_residual_before_rmsnorm():
    runtime = _small_artifact_runtime()
    norm = "model.layers.0.input_layernorm"
    source = RuntimeFormat(16,[1/32,1/128,3/128,1/64],axis=-1)
    scalar_scale = 1/64
    runtime.formats["model.embed_tokens.output"] = source
    aligned = contract.Format(24,scalar_scale).dictionary()
    runtime.config["aligned_norm_inputs"] = {norm:aligned}
    m,shift = contract.encode_multiplier(torch.tensor(source.scale,dtype=torch.float64)/scalar_scale,24)
    runtime.coefficients[norm+".align_input.M"] = m.to(torch.int32)
    runtime.coefficients[norm+".align_input.shift"] = shift.to(torch.int16)
    m,shift = contract.encode_multiplier(scalar_scale**2*(1 << 40)/4,24)
    runtime.coefficients[norm+".to_t.M"] = m.to(torch.int32)
    runtime.coefficients[norm+".to_t.shift"] = shift.to(torch.int16)
    output_scale = runtime._format(norm+".output").scale
    m,shift = contract.encode_multiplier(scalar_scale/output_scale,24)
    runtime.coefficients[norm+".gamma_output.M"] = m.to(torch.int32)
    runtime.coefficients[norm+".gamma_output.shift"] = shift.to(torch.int16)
    codes = torch.tensor([[[3,5,-3,-7]]],dtype=torch.int16)
    aligned_codes = torch.tensor([[[round(Fraction(int(value))*Fraction(scale)/Fraction(scalar_scale))
                                    for value,scale in zip(codes[0,0].tolist(),source.scale)]]],
                                 dtype=torch.int64).clamp(-(1 << 23),(1 << 23)-1)
    actual_aligned = runtime._apply(codes,norm+".align_input",clamp=(-(1 << 23),(1 << 23)-1))
    assert torch.equal(actual_aligned,aligned_codes)
    expected = contract.rms_integer(aligned_codes,scalar_scale,torch.ones(4),
        runtime._format(norm+".output"),seed_entries=64,coefficient_bits=24,epsilon=1e-5,t_fractional_bits=40)
    actual = runtime._rms(norm,codes,source)
    assert torch.equal(actual,expected)


@pytest.mark.parametrize('bits', [16, 24, 31])
def test_silu_compiled_affine_mac_matches_fraction_and_coefficient_budget(bits):
    table = contract.fit_silu(segments=8, threshold=6, coefficient_bits=bits)
    fmt = contract.Format(16, 1/1024)
    compiled = contract.compile_silu(1/512, fmt, table, bits)
    assert max(map(abs, compiled['slopes']+compiled['intercepts'])) < 1 << bits
    boundaries = compiled['breakpoints']
    values = sorted(set([boundaries[0]-1, boundaries[-1]+1]+
                        [b+offset for b in boundaries for offset in (-1, 0, 1)]))
    expected = []
    for value in values:
        if value < boundaries[0]:
            code = 0
        elif value >= boundaries[-1]:
            code = 2*value
        else:
            segment = sum(value >= b for b in boundaries[1:-1])
            numerator = value*compiled['slopes'][segment]+compiled['intercepts'][segment]
            code = reference_shift(numerator, compiled['shifts'][segment])
        expected.append(reference_clamp(code, fmt.bits))
    actual = contract.silu_integer(torch.tensor(values), 1/512, fmt, table, bits)
    assert actual.tolist() == expected


def test_projection_scales_are_common_within_each_split_half_pair():
    name = 'model.layers.0.self_attn.q_proj.output'
    lower = -np.arange(1, 577, dtype=np.float64)/100
    upper = np.arange(1, 577, dtype=np.float64)/200
    stats = {name: {'minimum': float(lower.min()), 'maximum': float(upper.max()),
                    'groups': {'minimum': lower.tolist(), 'maximum': upper.tolist()}}}
    adapter = contract.ContractAdapter(None, None, stats)
    fmt = adapter.make_format(name, {'bits': 8})
    scales = np.asarray(fmt.scale).reshape(9, 64)
    assert fmt.axis == -1
    assert np.all(scales == scales[:, :1])
    assert np.all(lower >= -128*np.asarray(fmt.scale))
    assert np.all(upper <= 127*np.asarray(fmt.scale))


def test_fused_softmax_trial_is_rejected_without_mutating_adapter_state():
    materialized = {"frozen": torch.tensor([3.])}
    baseline = SimpleNamespace(materialized=materialized)
    adapter = contract.ContractAdapter(None, baseline, {})
    old_trial = {"name": "current", "mac_dtype": "float32"}
    old_weights = {"cached": object()}
    old_formats = {"existing": contract.Format(8, 1.)}
    old_metrics = {"existing": {"elements": 4}}
    old_final_norm = (torch.tensor([7]), contract.Format(8, 1.))
    adapter.trial = old_trial
    adapter.weights = old_weights
    adapter.formats = old_formats
    adapter.point_metrics = old_metrics
    adapter.final_norm_codes = old_final_norm

    with pytest.raises(ValueError, match="fused Softmax-to-PV is unsupported"):
        adapter.set_trial({
            "mac_dtype": "float64",
            "integer_coefficients": True,
            "formats": {"replacement": {"bits": 12, "scale": 1., "signed": True}},
            "nonlinear": {"model.layers.0.self_attn.softmax": {"fused": True}},
        })

    assert adapter.trial is old_trial
    assert adapter.weights is old_weights and adapter.weights["cached"] is not None
    assert adapter.formats is old_formats
    assert adapter.point_metrics is old_metrics
    assert adapter.final_norm_codes is old_final_norm
    assert baseline.materialized is materialized and torch.equal(materialized["frozen"], torch.tensor([3.]))


def test_disabled_adapter_restores_full_cached_logits_and_frozen_parameters():
    from transformers import LlamaConfig, LlamaForCausalLM
    from fp32_reference import ROOT, cached_logits, read_json
    from ptq_eval import full_logits
    from ptq_fake_quant import PTQAdapter
    from ptq_intermediate_calibrate import IntermediateProfiler, full_signed_range

    torch.manual_seed(91)
    model = LlamaForCausalLM(LlamaConfig(vocab_size=32, hidden_size=64,
        intermediate_size=128, num_hidden_layers=2, num_attention_heads=1,
        num_key_value_heads=1, tie_word_embeddings=True,
        attn_implementation='eager')).eval()
    baseline = PTQAdapter(model, read_json(ROOT/'candidates/w8a12kv8_smoothquant/config.json'))
    ids = [1, 7, 4, 9, 3, 5, 2]
    with torch.inference_mode():
        baseline.begin_smooth_calibration()
        full_logits(model, ids)
        baseline.finalize_smoothquant()
        baseline.begin_calibration()
        full_logits(model, ids)
        baseline.freeze()
        full_signed_range(baseline)
        baseline.set_mode('quantize')
        profiler = IntermediateProfiler(model, baseline)
        with profiler.attached():
            expected = full_logits(model, ids).clone()
        expected_cache = cached_logits(model, ids, 2).copy()
        stats = {name: value.summary() for name, value in profiler.points.items()}
        frozen = {name: point.fq.scale.clone() for name, point in baseline.points.items()}
        parameters = {name: p.clone() for name, p in model.named_parameters()}
        forwards = [(module, module.forward) for module in model.modules()]
        adapter = contract.ContractAdapter(model, baseline, stats)
        with adapter.attached():
            assert torch.equal(full_logits(model, ids), expected)
            np.testing.assert_array_equal(cached_logits(model, ids, 2), expected_cache)
        assert all(module.forward == forward for module, forward in forwards)
        with pytest.raises(RuntimeError, match='scope probe'):
            with adapter.attached():
                raise RuntimeError('scope probe')
        assert all(module.forward == forward for module, forward in forwards)
        assert all(torch.equal(point.fq.scale, frozen[name]) for name, point in baseline.points.items())
        assert all(torch.equal(p, parameters[name]) for name, p in model.named_parameters())
        assert model.model.embed_tokens.weight is model.lm_head.weight
    baseline.restore()


def test_lm_head_tensor_view_still_uses_selected_integer_multiplier():
    from types import SimpleNamespace
    baseline = SimpleNamespace(points={'lm_head.input': SimpleNamespace(
        fq=SimpleNamespace(scale=torch.tensor([1.])))}, smooth_scales={})
    adapter = contract.ContractAdapter(None, baseline, {'lm_head.output': {}})
    source, output = contract.Format(16, 1/6), contract.Format(16, 1.)
    codes = torch.tensor([[[3]]])
    carrier = contract.decoded(codes, source)[:, :, :]
    assert not hasattr(carrier, '_contract')
    adapter.trial = {'integer_coefficients': True, 'coefficient_bits': 16, 'metrics': False}
    adapter.formats = {'model.norm.output': source, 'lm_head.output': output}
    adapter.final_norm_codes = codes, source
    adapter.weights['shared_embedding_lm_head.weight'] = (
        torch.tensor([[1]], dtype=torch.int8), torch.tensor([[1.]], dtype=torch.float64),
        contract.Format(8, [1.], 0))
    actual = adapter.linear(None, carrier, 'lm_head', None)
    # Ideal FP32 0.5 would round to zero. The selected 16-bit approximation
    # is 43691/2**18, so 3*M/2**18 is above one half and rounds to one.
    expected = reference_divide(3*43691, 1 << 18)
    assert expected == 1
    assert actual._contract[0].item() == expected
    adapter.final_norm_codes = None
    with pytest.raises(RuntimeError, match='missing integer source'):
        adapter.linear(None, carrier, 'lm_head', None)


def test_every_cache_code_survives_fp32_carrier_at_all_frozen_head_scales():
    from safetensors.torch import load_file
    from fp32_reference import ROOT
    params = load_file(str(ROOT/'candidates/w8a12kv8_smoothquant/qparams.safetensors'))
    scales = torch.cat([value.double() for name, value in params.items()
                        if name.endswith(('.key_post_rope.scale', '.value_post_projection.scale'))])
    codes = torch.arange(-128, 128).expand(len(scales), -1)
    fmt = contract.Format(8, scales.tolist(), 0)
    carrier = contract.decoded(codes, fmt).clone()  # cache concatenation loses metadata too
    assert not hasattr(carrier, '_contract')
    actual, _ = contract.encode(carrier, fmt)
    assert torch.equal(actual, codes)


def test_complete_discrete_simulation_matches_cached_codes_and_prefix():
    from transformers import DynamicCache, LlamaConfig, LlamaForCausalLM
    from fp32_reference import ROOT, read_json
    from ptq_eval import full_logits
    from ptq_fake_quant import PTQAdapter
    from ptq_intermediate_calibrate import IntermediateProfiler, full_signed_range

    torch.manual_seed(93)
    model = LlamaForCausalLM(LlamaConfig(vocab_size=32, hidden_size=576,
        intermediate_size=128, num_hidden_layers=2, num_attention_heads=9,
        num_key_value_heads=3, tie_word_embeddings=True, rms_norm_eps=1e-5,
        attn_implementation='eager')).eval()
    baseline = PTQAdapter(model, read_json(ROOT/'candidates/w8a12kv8_smoothquant/config.json'))
    ids = [1, 7, 4, 9, 3, 5, 2]
    with torch.inference_mode():
        baseline.begin_smooth_calibration(); full_logits(model, ids); baseline.finalize_smoothquant()
        baseline.begin_calibration(); full_logits(model, ids); baseline.freeze()
        full_signed_range(baseline); baseline.set_mode('quantize')
        profiler = IntermediateProfiler(model, baseline)
        with profiler.attached():
            full_logits(model, ids)
        stats = {name: value.summary() for name, value in profiler.points.items()}
        adapter = contract.ContractAdapter(model, baseline, stats)
        points = {name: {'bits': 12} for name in adapter.inventory}
        for name, family in adapter.inventory.items():
            if family == 'residual': points[name] = {'bits': 16, 'policy': 'per_channel'}
            if family == 'probability': points[name] = {'bits': 12}
        adapter.set_trial({'points': points, 'integer_coefficients': True,
            'coefficient_bits': 16, 'mac_dtype': 'float64', 'metrics': False,
            'nonlinear': {'rms': {'seed_entries': 32, 't_fractional_bits': 24},
                          'rope': {'coefficient_bits': 12},
                          'silu': {'segments': 8, 'threshold': 6},
                          'softmax': {'entries': 32, 'c': 8, 'probability_bits': 12}}})
        with adapter.attached():
            expected = full_logits(model, ids).clone()
            last_only = model(input_ids=torch.tensor([ids]), use_cache=False,
                              logits_to_keep=1).logits[0]
            assert torch.equal(last_only, expected[-1:])
            cache, rows = DynamicCache(), []
            for start, stop in [(0, 3), (3, 4), (4, 5), (5, 6), (6, 7)]:
                prefix = [(k.clone(), v.clone()) for k, v in zip(cache.key_cache, cache.value_cache)]
                result = model(input_ids=torch.tensor([ids[start:stop]]),
                    attention_mask=torch.ones((1, stop), dtype=torch.long),
                    position_ids=torch.arange(start, stop)[None],
                    cache_position=torch.arange(start, stop), past_key_values=cache,
                    use_cache=True)
                cache = result.past_key_values
                rows.append(result.logits[0])
                for layer, (old_k, old_v) in enumerate(prefix):
                    assert torch.equal(cache.key_cache[layer][:, :, :start], old_k)
                    assert torch.equal(cache.value_cache[layer][:, :, :start], old_v)
            assert torch.equal(torch.cat(rows), expected)
    baseline.restore()


def test_shift_export_uses_signed_int8_or_int16_without_wraparound():
    assert contract_search.shift_container([-128, 127]).dtype == torch.int8
    assert contract_search.shift_container([-129, 128]).dtype == torch.int16
    with pytest.raises(OverflowError, match='does not fit INT16'):
        contract_search.shift_container([-32769])


@pytest.mark.parametrize('name,rescale', [
    ('model.layers.0.self_attn.q_proj.smooth', True),
    ('model.layers.0.self_attn.q_proj.output', True),
    ('model.layers.0.residual_after_attention.left_to_guard', True),
    ('model.layers.0.input_layernorm.align_input', True),
    ('model.layers.0.self_attn.score_to_index', False),
    ('model.layers.0.input_layernorm.to_t', False),
    ('model.layers.0.input_layernorm.gamma_output', False),
    ('model.layers.0.mlp.pwl.positive', False),
])
def test_rescale_m16_does_not_reduce_frozen_nonlinear_coefficient_precision(name,rescale):
    assert contract_search.coefficient_precision(name,16,24) == (16 if rescale else 24)
    assert contract_search.coefficient_precision(name,24,24) == 24
    with pytest.raises(ValueError,match='frozen nonlinear M24'):
        contract_search.coefficient_precision(name,16,16)


def test_minimum_width_selection_uses_relative_ppl_threshold_from_unrounded_delta():
    factors = {
        "boundary_score_w8": {"quick": {"status": "complete", "delta_mean_nll_vs_combined_high": .00998}},
        "boundary_score_w12": {"quick": {"status": "complete", "delta_mean_nll_vs_combined_high": .009}},
        "boundary_context_w8": {"quick": {"status": "complete", "delta_mean_nll_vs_combined_high": .00994}},
        "boundary_context_w12": {"quick": {"status": "complete", "delta_mean_nll_vs_combined_high": .002}},
    }
    choices = contract_search.minimum_width_selection(factors, {"score", "context"})
    # .00998 is less than a 1% NLL delta, but expm1(.00998) is above 1% PPL.
    assert .00998 < .01 < math.expm1(.00998)
    assert choices["score"]["selected_bits"] == 12
    assert choices["score"]["tested"][0]["within_one_percent"] is False
    assert choices["context"]["selected_bits"] == 8
    assert choices["context"]["tested"][0]["within_one_percent"] is True
    with pytest.raises(RuntimeError, match="required factor Quick8 evidence is missing"):
        contract_search.minimum_width_selection({}, {"score"})


def test_combined_candidate_forces_residual_product_and_m16_policy():
    inventory = {
        "residual_a": "residual", "residual_b": "residual",
        "product": "product", "o_down_branch": "residual_branch",
        "probability": "probability", "score": "score", "gate": "gate_up",
    }
    base = {"name": "combined_high", "points": {name: {"bits": 24} for name in inventory},
            "nonlinear": {"rms": {"seed_entries": 64, "t_fractional_bits": 40},
                          "rope": {"coefficient_bits": 16},
                          "softmax": {"entries": 32, "c": 8, "probability_bits": 12},
                          "silu": {"segments": 32, "threshold": 8}},
            "coefficient_bits": 24, "scale_rescale_bits": 24}
    base["points"]["probability"] = {"bits": 12}
    factors = {
        "boundary_score_w8": {"quick": {"status": "complete", "delta_mean_nll_vs_combined_high": .002}},
        "boundary_score_w12": {"quick": {"status": "complete", "delta_mean_nll_vs_combined_high": .001}},
        "boundary_gate_up_w8": {"quick": {"status": "complete", "delta_mean_nll_vs_combined_high": .02}},
        "boundary_gate_up_w12": {"quick": {"status": "complete", "delta_mean_nll_vs_combined_high": .003}},
    }
    config, _ = contract_search.build_combined_candidate_config(base, inventory, factors)
    assert config["name"] == contract_search.COMBINED_CANDIDATE
    assert config["points"]["score"]["bits"] == 8
    assert config["points"]["gate"]["bits"] == 12
    assert config["points"]["residual_a"] == {"bits": 16}
    assert config["points"]["residual_b"] == {"bits": 16}
    assert config["points"]["product"] == {"bits": 16}
    assert config["points"]["o_down_branch"] == {"bits": 16}
    assert "policy" not in config["points"]["residual_a"]  # no axis means per-tensor
    assert config["points"]["probability"]["bits"] == 12  # fixed source point is untouched
    assert config["scale_rescale_bits"] == 16
    assert config["coefficient_bits"] == 24
    assert config["nonlinear"] == base["nonlinear"]


def test_quick8_scores_fresh_combined_candidate_and_stops_before_full(monkeypatch, tmp_path):
    from types import SimpleNamespace

    candidate = contract_search.COMBINED_CANDIDATE
    config_path = tmp_path / "combined" / "config.json"
    config_path.parent.mkdir()
    config_path.write_text("{}", encoding="utf-8")
    quick_baseline_ppl = 20.95995389152768
    baseline_rows = [{"id": f"w{i}", "nll": 511*math.log(quick_baseline_ppl), "tokens": 511} for i in range(8)]
    factor_quick = {"status": "complete", "per_window": [{"id": f"w{i}", "nll": 10., "tokens": 511}
                                                              for i in range(8)]}
    report = {"stages": {"baseline_reproduction": "measured", "combined_candidate_prepare": "complete"},
              "performance": {"selected_threads": 8}, "threads": 8,
              "prepared_candidate_artifacts": {
                  "boundary_context_w8": "artifacts/factor/config.json",
                  candidate: "combined/config.json"},
              "screening": {"initial_candidates": ["boundary_context_w8"],
                            "candidates": {"boundary_context_w8": {"quick": factor_quick}}},
              "baseline_reproduction": {"ppl": {"ppl": 22.821212629233703,
                                                  "per_window": baseline_rows}}}
    campaign = contract_search.ArtifactCampaign.__new__(contract_search.ArtifactCampaign)
    campaign.args = SimpleNamespace(output_dir=tmp_path)
    campaign.root = tmp_path
    campaign.report = report
    campaign.selection = [{"id": f"w{i}", "input_ids": [i]*512} for i in range(8)]
    campaign.started = 0.
    campaign.save = lambda: None
    scored = []
    monkeypatch.setattr(contract_search, "load_prepared_contract", lambda _path: object())
    monkeypatch.setattr(contract_search, "full_logits", lambda _runtime, ids: scored.append(ids[0]) or 20.1)
    monkeypatch.setattr(contract_search, "score_targets",
                        lambda logits, _ids: (511*math.log(logits), 511))
    monkeypatch.setattr(campaign, "_resources", lambda _path: {
        "packed_boundary_payload_proxy_bytes_per_512": 1,
        "runtime_multiplier_shift_payload_bytes": 2,
        "scale_metadata": {}, "per_channel_rms_alignment": {},
        "residual_arithmetic_widths": {}})

    campaign.run_combined_quick()

    assert scored == list(range(8))
    combined = report["screening"]["candidates"][candidate]["quick"]
    assert combined["windows"] == 8 and combined["tokens"] == 4088
    assert combined["ranking_only"] is True and combined["quality_gate"] is False
    quick_result = report["combined_quick_result"]
    assert quick_result["baseline_quick_ppl"] == pytest.approx(quick_baseline_ppl)
    assert quick_result["baseline_full_ppl"] == pytest.approx(22.821212629233703)
    assert quick_result["relative_ppl_increase"] == pytest.approx(combined["ppl"] / quick_baseline_ppl - 1)
    assert quick_result["relative_ppl_increase"] != pytest.approx(combined["ppl"] / 22.821212629233703 - 1)
    assert report["screening"]["candidates"]["boundary_context_w8"]["quick"] == factor_quick
    assert report["stages"]["combined_quick"] == "measured"
    assert "combined_full_ppl_result" not in report
    assert report["approval_gate"]["status"] == "pending_user_approval_for_full64"


def test_cli_removes_legacy_replay_search_and_qualification_stages():
    for stage in ("all", "baseline", "isolated", "family", "search", "qualify", "export",
                  "artifact-improve", "artifact-prepare-followup", "artifact-prepare-composition"):
        with pytest.raises(SystemExit):
            contract_search.main_parser().parse_args(["--stage", stage])


def test_factor_artifact_resume_keeps_only_unscored_windows(monkeypatch):
    campaign = contract_search.ArtifactCampaign.__new__(contract_search.ArtifactCampaign)
    candidate = contract_search.COMBINED_CANDIDATE
    quick_rows = [{"id": f"w{i}", "nll": float(i), "tokens": 1} for i in range(3)]
    campaign.report = {"screening": {"candidates": {candidate: {"quick": {
        "status": "in_progress", "per_window": quick_rows}}}}}
    campaign.root = Path(".")
    campaign.selection = [{"id": f"w{i}", "input_ids": [i, i+1]} for i in range(8)]
    campaign.report["prepared_candidate_artifacts"] = {candidate: "candidate/config.json"}
    campaign.save = lambda: None
    monkeypatch.setattr(contract_search, "read_json", lambda _path: {})
    monkeypatch.setattr(contract_search, "load_prepared_contract", lambda _path: object())
    scored = []
    monkeypatch.setattr(contract_search, "full_logits", lambda _runtime, ids: scored.append(ids[0]) or ids[0])
    monkeypatch.setattr(contract_search, "score_targets", lambda value, _ids: (float(value), 1))
    monkeypatch.setattr(campaign, "_resources", lambda _path: {
        "packed_boundary_payload_proxy_bytes_per_512": 1,
        "runtime_multiplier_shift_payload_bytes": 2,
        "scale_metadata": {}, "per_channel_rms_alignment": {}, "residual_arithmetic_widths": {}})
    campaign.report["baseline_reproduction"] = {"ppl": {"per_window": [
        {"id": f"w{i}", "nll": 0., "tokens": 1} for i in range(8)]}}

    campaign._screen_candidate(candidate)

    assert scored == [3, 4, 5, 6, 7]
    assert [row["id"] for row in campaign.report["screening"]["candidates"][candidate]["quick"]["per_window"]] == [
        f"w{i}" for i in range(8)]


def test_full_ppl_reuses_completed_quick8_and_scores_remaining_windows(monkeypatch):
    campaign = contract_search.ArtifactCampaign.__new__(contract_search.ArtifactCampaign)
    quick_rows = [{"id":f"w{i}","nll":float(i),"tokens":1} for i in range(8)]
    campaign.report = {"screening":{"candidates":{contract_search.COMBINED_CANDIDATE:{"quick":{
        "status":"complete","windows":8,"per_window":quick_rows}}}}}
    campaign.report["combined_full_ppl_result"] = {"name": contract_search.COMBINED_CANDIDATE}
    checkpoints = []
    campaign.save = lambda: checkpoints.append(json.loads(json.dumps(campaign.report)))
    records = [{"id":f"w{i}","input_ids":[i,i+1]} for i in range(10)]
    scored_ids = []

    def fake_logits(_runtime, ids):
        scored_ids.append(ids[0])
        return ids[0]

    monkeypatch.setattr(contract_search, "full_logits", fake_logits)
    monkeypatch.setattr(contract_search, "score_targets", lambda logits, _ids:(float(logits),1))
    owner = campaign.report["combined_full_ppl_result"]
    row = campaign._full_ppl(object(),owner,records)

    assert scored_ids == [8,9]
    assert [item["id"] for item in row["per_window"]] == [f"w{i}" for i in range(10)]
    assert row["nll"] == sum(range(10)) and row["tokens"] == 10
    assert row["windows"] == 10
    assert row["quick8_reuse"]["windows_reused"] == 8
    assert row["quick8_reuse"]["remaining_full_selection_windows"] == 2
    assert row["full_selection_windows_not_reused_from_quick8"] == 2
    assert campaign.report["combined_full_ppl_result"]["full_ppl"] is row
    assert len(checkpoints) >= 3
    assert [len(checkpoint["combined_full_ppl_result"]["full_ppl"]["per_window"])
            for checkpoint in checkpoints[-4:]] == [8, 9, 10, 10]
    completed = campaign._full_ppl(object(), owner, records)
    assert completed is row and scored_ids == [8, 9]


def test_explicit_full_ppl_uses_campaign_checkpoint_owner(monkeypatch, tmp_path):
    campaign = contract_search.ArtifactCampaign.__new__(contract_search.ArtifactCampaign)
    candidate = contract_search.COMBINED_CANDIDATE
    campaign.report = {
        "stages": {"combined_quick": "measured"},
        "combined_quick_result": {"candidate": candidate},
        "prepared_candidate_artifacts": {candidate: "candidate/config.json"},
    }
    campaign.root = tmp_path
    campaign.selection = [{"id": f"w{i}", "input_ids": [i]} for i in range(64)]
    campaign.reference = {"ppl": {"ppl": 22.574714201210707}}
    campaign.save = lambda: None
    monkeypatch.setattr(contract_search, "load_prepared_contract", lambda _path: object())
    seen = {}

    def fake_full(_runtime, owner, records):
        seen["owner_is_checkpoint"] = owner is campaign.report["combined_full_ppl_result"]
        assert owner["name"] == candidate
        assert len(records) == 64
        row = {"status": "complete", "windows": 64, "tokens": 32704,
               "ppl": 22.7, "per_window": [{"id": str(i)} for i in range(64)]}
        owner["full_ppl"] = row
        return row

    monkeypatch.setattr(campaign, "_full_ppl", fake_full)
    campaign.run_combined_full_ppl()
    assert seen["owner_is_checkpoint"] is True
    assert campaign.report["combined_full_ppl_result"]["full_ppl"]["windows"] == 64
    assert campaign.report["combined_full_ppl_result"]["ppl_gate_pass"] is True


def test_combined_qualification_uses_exact_fixed_gates():
    baselines = contract_search.CACHE_PPL_REFERENCES
    regimes = {key: {"ppl": value * 1.05} for key, value in baselines.items()}
    passed = contract_search.qualification_gates(
        contract_search.FULL_PPL_LIMIT, 607, regimes, 22.574714201210707)
    assert passed["pass"] is True
    assert passed["piqa"]["pass"] is True
    assert passed["piqa"]["minimum_correct"] == 607
    assert all(value["pass"] for value in passed["cache"].values())

    failed = contract_search.qualification_gates(
        contract_search.FULL_PPL_LIMIT, 606, regimes, 22.574714201210707)
    assert failed["pass"] is False
    assert failed["piqa"]["pass"] is False
    regimes["32"]["ppl"] = baselines["32"] * 1.050000001
    failed = contract_search.qualification_gates(
        contract_search.FULL_PPL_LIMIT, 607, regimes, 22.574714201210707)
    assert failed["pass"] is False
    assert failed["cache"]["32"]["pass"] is False


def test_distribution_diagnostic_uses_fp32_to_candidate_kl_direction():
    reference = np.array([[3.0, 0.0, -1.0], [1.0, 2.0, 0.0]], dtype=np.float32)
    candidate = np.array([[4.0, 0.0, -1.0], [2.0, 2.0, 0.0]], dtype=np.float32)

    def probabilities(row):
        values = np.exp(row.astype(np.float64)-np.max(row))
        return values/values.sum()

    divergences, reverse_divergences = [], []
    for ref_row, candidate_row in zip(reference, candidate):
        p, q = probabilities(ref_row), probabilities(candidate_row)
        divergences.append(float(np.sum(p*np.log(p/q))))
        reverse_divergences.append(float(np.sum(q*np.log(q/p))))
    expected = float(np.mean(divergences))
    reverse = float(np.mean(reverse_divergences))
    expected_agreement = float(np.mean(np.argmax(reference, axis=-1)
                                       == np.argmax(candidate, axis=-1)))
    actual = contract_search.distribution_diagnostic(torch.from_numpy(reference),
                                                       torch.from_numpy(candidate))
    numpy_actual = contract_search.distribution_diagnostic(reference, candidate)
    assert actual["mean_kl_fp32_to_candidate"] == pytest.approx(expected, abs=1e-12)
    assert actual["top1_agreement"] == expected_agreement == 0.5
    assert numpy_actual == actual
    assert not math.isclose(expected, reverse, rel_tol=1e-3)


@pytest.mark.parametrize("prefill,length,expected", [
    (32, 96, [0, 31, 32, 94, 95]),
    (448, 512, [0, 447, 448, 510, 511]),
])
def test_fixed_diagnostic_rows_include_first_decode_target(prefill, length, expected):
    assert contract_search.diagnostic_row_indices(prefill, length) == expected


def test_fp32_diagnostic_preparation_saves_only_the_fixed_80_rows(tmp_path, monkeypatch):
    report_path = tmp_path/"campaign.json"
    report_path.write_text(json.dumps({"combined_full_ppl_result": {"full_ppl": {
        "status": "complete", "windows": 64, "tokens": 32704, "ppl": 23.0}}}),
        encoding="utf-8")
    selection = [{"input_ids": list(range(512))} for _ in range(8)]
    cases = [{"id": f"cache{i}", "selection_index": i, "regimes": [
        {"prefill": 32, "input_length": 96},
        {"prefill": 448, "input_length": 512}]} for i in range(8)]
    actual_read_json = contract_search.read_json

    def read_json(path):
        if Path(path) == report_path:
            return actual_read_json(report_path)
        if Path(path) == Path(contract_search.ROOT/"data/wikitext_selection.json"):
            return selection
        if Path(path) == Path(contract_search.ROOT/"data/cache_cases.json"):
            return cases
        return actual_read_json(path)

    monkeypatch.setattr(contract_search, "read_json", read_json)
    monkeypatch.setattr(contract_search, "configure_runtime", lambda: None)
    monkeypatch.setattr(contract_search, "source_snapshot", lambda *_args: tmp_path)
    monkeypatch.setattr(contract_search, "load_model", lambda _snapshot: (object(), None))
    monkeypatch.setattr(contract_search, "full_logits", lambda _model, ids:
        torch.arange(len(ids)*4, dtype=torch.float32).reshape(len(ids), 4))
    args = SimpleNamespace(output_dir=tmp_path, cache_dir=tmp_path, offline=True)

    contract_search.prepare_fp32_diagnostic_rows(args)

    report = actual_read_json(report_path)
    details = report["diagnostic_reference"]
    tensors = contract_search.load_file(str(tmp_path/"qualification_fp32_rows.safetensors"))
    assert details["status"] == "complete" and details["rows"] == 80
    assert len(details["cases"]) == 16 and len(tensors) == 16
    assert tensors["case_0_32"].shape == (5, 4)
    assert tensors["case_0_32"][:, 0].tolist() == [0, 124, 128, 376, 380]


def make_qualification_campaign(tmp_path, monkeypatch, *, piqa_correct=607, cache_count=16,
                               reload_mismatch=False):
    candidate = contract_search.COMBINED_CANDIDATE
    campaign = contract_search.ArtifactCampaign.__new__(contract_search.ArtifactCampaign)
    campaign.root = tmp_path
    campaign.reference = {"ppl": {"ppl": 22.574714201210707}}
    campaign.selection = [{"input_ids": list(range(96))} for _ in range(64)]
    campaign.questions = [{"id": f"q{i}"} for i in range(919)]
    campaign.cases = [{"id": f"c{i}", "regimes": [
        {"prefill": 32, "decode": 64}, {"prefill": 448, "decode": 64}]} for i in range(8)]
    campaign.tokenizer = object()
    campaign.report = {
        "combined_full_ppl_result": {"full_ppl": {"status": "complete", "windows": 64,
            "tokens": 32704, "ppl": 23.1}},
        "prepared_candidate_artifacts": {candidate: "candidate/config.json"},
        "combined_quick_result": {"candidate": candidate},
        "diagnostic_reference": {"status": "complete", "cases": []},
        "stages": {},
    }
    for index, case in enumerate(campaign.cases):
        for regime in case["regimes"]:
            prefill = regime["prefill"]
            campaign.report["diagnostic_reference"]["cases"].append({
                "id": case["id"], "prefill": prefill, "key": f"case_{index}_{prefill}",
                "rows": [0, prefill-1, prefill, 94, 95]})
    campaign.save = lambda: None

    def piqa(_runtime, owner, key, records):
        correct = [i < piqa_correct for i in range(len(records))]
        answer = {"status": "complete", "questions": len(records), "choices": 2*len(records),
                  "correct": sum(correct),
                  "per_question": [{"id": item["id"], "correct": correct[i]}
                                   for i, item in enumerate(records)]}
        owner[key] = answer
        return answer

    def cache(_runtime, owner, key, selection, cases, **_kwargs):
        runs = [{"id": case["id"], "prefill": regime["prefill"], "tokens": 64,
                 "logit_codes_bitwise_equal": True, "cache_prefix_preserved": True,
                 "full_fp32_diagnostic": {"top1_agreement": 0.9,
                     "mean_kl_fp32_to_candidate": 0.01},
                 "cache_fp32_diagnostic": {"top1_agreement": 0.9,
                     "mean_kl_fp32_to_candidate": 0.01}}
                for case in cases for regime in case["regimes"]][:cache_count]
        regimes = {"32": {"ppl": 26.0}, "448": {"ppl": 12.0}}
        answer = {"status": "complete", "runs": runs, "regimes": regimes}
        owner[key] = answer
        return answer

    class TinyRuntime:
        def __init__(self, variant):
            self.cache_calls = 0
            self.variant = variant

        def __call__(self, **_kwargs):
            codes = torch.arange(96*4, dtype=torch.int16).reshape(1, 96, 4)
            if reload_mismatch and self.variant:
                codes[0, 0, 0] += 1
            return SimpleNamespace(logit_codes=codes)

        def cached_outputs(self, _ids, _prefill, *, verify_prefix=False):
            self.cache_calls += 1
            codes = torch.arange(96*4, dtype=torch.int16).reshape(96, 4)
            if reload_mismatch and self.variant:
                codes[0, 0] += 1
            return torch.zeros((96, 4)), codes, True if verify_prefix else None

    load_calls = []
    monkeypatch.setattr(contract_search, "load_prepared_contract",
                        lambda _path: load_calls.append(TinyRuntime(len(load_calls))) or load_calls[-1])
    monkeypatch.setattr(contract_search, "greedy", lambda _runtime, _tokenizer, prompts, max_new:
        [{"prompt_ids": ids, "generated_ids": [1], "generated_text": "x"} for ids in prompts])
    campaign.piqa = piqa
    campaign.cache = cache
    save_file({"rows": torch.zeros((1, 4), dtype=torch.float32)},
              str(tmp_path/"qualification_fp32_rows.safetensors"))
    return campaign, load_calls


def test_single_candidate_qualification_gates_checkpoints_and_reentry(tmp_path, monkeypatch):
    campaign, load_calls = make_qualification_campaign(tmp_path, monkeypatch)
    campaign.report["combined_full_ppl_result"]["full_ppl"]["status"] = "in_progress"
    with pytest.raises(RuntimeError, match="completed 64-window"):
        campaign.run_combined_qualification()
    assert not load_calls
    campaign.report["combined_full_ppl_result"]["full_ppl"]["status"] = "complete"

    campaign.run_combined_qualification()
    result = campaign.report["combined_qualification_result"]
    assert result["status"] == "software_selection_qualified"
    assert campaign.report["software_contract_selection"] == "software_selection_qualified"
    assert result["hard_checks"]["reload_bitwise_equal"] is True
    assert campaign.report["stages"]["combined_qualification"] == "complete"
    assert not (tmp_path/"qualification_fp32_rows.safetensors").exists()
    initial_loads = len(load_calls)
    campaign.run_combined_qualification()
    assert len(load_calls) == initial_loads


def test_incomplete_qualification_coverage_never_marks_candidate_complete(tmp_path, monkeypatch):
    campaign, _ = make_qualification_campaign(tmp_path, monkeypatch, cache_count=15)
    with pytest.raises(RuntimeError, match="all 16 fixed cases"):
        campaign.run_combined_qualification()
    assert campaign.report.get("stages", {}).get("combined_qualification") != "complete"


def test_quality_or_reload_failure_cannot_select_software_profile(tmp_path, monkeypatch):
    campaign, _ = make_qualification_campaign(tmp_path, monkeypatch,
                                              piqa_correct=606, reload_mismatch=True)
    campaign.run_combined_qualification()
    result = campaign.report["combined_qualification_result"]
    assert result["status"] == "rejected_quality_or_numerical_gate"
    assert result["gates"]["piqa"]["pass"] is False
    assert result["hard_checks"]["reload_bitwise_equal"] is False
    assert result["kept_for_software_profile"] is False


def test_successful_cli_recorder_records_exact_python_arguments(tmp_path):
    path = tmp_path/'campaign.json'
    path.write_text('{}',encoding='utf-8')
    argv = [sys.executable,'-u','ptq_contract_search.py','--stage','artifact-quick']
    contract_search.record_successful_cli(path,'test-phase',argv)
    result = json.loads(path.read_text(encoding='utf-8'))['cli_results']['test-phase']
    assert result['exit_status'] == 0
    assert result['argv'] == argv


def test_failed_cli_recorder_preserves_stage_error_and_exit_status(tmp_path):
    path = tmp_path/'campaign.json'
    path.write_text('{}', encoding='utf-8')
    argv = [sys.executable, '-u', 'ptq_contract_search.py', '--stage', 'artifact-quick']
    error = TypeError('resource summary failed after Quick8 checkpoints')
    contract_search.record_failed_cli(path, 'artifact-quick', error, argv)
    result = json.loads(path.read_text(encoding='utf-8'))['cli_failures'][0]
    assert result['exit_status'] == 1
    assert result['argv'] == argv
    assert result['error'] == 'TypeError: resource summary failed after Quick8 checkpoints'


def test_artifact_point_family_is_static_for_resource_summaries():
    campaign = contract_search.ArtifactCampaign.__new__(contract_search.ArtifactCampaign)
    assert campaign._point_family('model.layers.0.self_attn.q_proj.output') == 'q_pre'


def test_signed_qk_accumulator_bound_keeps_the_positive_endpoint():
    q_bounds = contract_search.integer_code_bounds(16)
    k_bounds = contract_search.integer_code_bounds(8)
    product = contract_search.dot_product_code_bounds(q_bounds, k_bounds, 1)
    accumulator = contract_search.dot_product_code_bounds(q_bounds, k_bounds, 64)
    assert product == (-32767*128, 32768*128)
    assert accumulator == (-32767*128*64, 32768*128*64)
    assert accumulator[1] == 2**28
    assert contract_search.minimum_signed_width(*accumulator) == 30
    assert accumulator[1] > (1 << (29-1))-1


def test_shared_weight_writer_recovers_fake_quant_codes_once_and_keeps_head_shared(tmp_path):
    matrices = {
        "model.layers.0.self_attn.q_proj.weight": torch.tensor(
            [[.25, -.75], [1.5, -.5]], dtype=torch.float32),
        "shared_embedding_lm_head.weight": torch.tensor(
            [[.125, -.375], [.75, .5], [-.625, 1.]], dtype=torch.float32),
    }

    class FakeQuantizer:
        def __init__(self, scales):
            self.fq = SimpleNamespace(scale=torch.tensor(scales, dtype=torch.float32))

        def __call__(self, value):
            return value

    class FrozenBaseline:
        def __init__(self):
            self.weights = matrices
            self.points = {"model.layers.0.self_attn.q_proj.weight": FakeQuantizer([.25, .5]),
                           "shared_embedding_lm_head.weight": FakeQuantizer([.125, .25, .5])}

        def effective_weight(self, name):
            return matrices[name]

    output = contract_search.prepare_shared_weights(FrozenBaseline(), tmp_path)
    actual = contract_search.load_file(str(output))
    assert set(actual) == set(matrices)
    assert actual["model.layers.0.self_attn.q_proj.weight"].tolist() == [[1, -3], [3, -1]]
    assert actual["shared_embedding_lm_head.weight"].tolist() == [[1, -3], [3, 2], [-1, 2]]
    before = output.read_bytes()

    changed = dict(matrices)
    changed["model.layers.0.self_attn.q_proj.weight"] = torch.full((2, 2), 17.)
    baseline = FrozenBaseline()
    baseline.effective_weight = lambda name: changed[name]
    contract_search.prepare_shared_weights(baseline, tmp_path)
    assert output.read_bytes() == before


def test_completed_factor_quick_resumes_after_prepared_factor_artifacts_are_pruned():
    campaign = contract_search.ArtifactCampaign.__new__(contract_search.ArtifactCampaign)
    expected_ids = [f"w{i}" for i in range(8)]
    campaign.selection = [{"id": item} for item in expected_ids]
    candidates = {}
    for name in contract_search.FACTOR_CANDIDATE_NAMES:
        rows = [{"id": item, "tokens": 511, "nll": 1.} for item in expected_ids]
        candidates[name] = {"quick": {"status": "complete", "windows": 8,
                                       "tokens": 8*511, "per_window": rows}}
    candidates[contract_search.COMBINED_CANDIDATE] = {}
    campaign.report = {
        "stages": {"baseline_reproduction": "measured", "factor_screen": "measured"},
        "screening": {"initial_candidates": list(contract_search.FACTOR_CANDIDATE_NAMES),
                      "initial_candidate_count": 28, "candidates": candidates},
        "prepared_candidate_artifacts": {contract_search.COMBINED_CANDIDATE:
                                          "artifacts/combined_candidate/config.json"},
    }
    campaign.run_factor_quick()

    campaign.report["screening"]["candidates"][contract_search.FACTOR_CANDIDATE_NAMES[0]]\
        ["quick"]["per_window"].pop()
    with pytest.raises(RuntimeError, match="Quick8 candidate screen is incomplete"):
        campaign.run_factor_quick()


def test_unfinished_factor_screen_still_requires_prepared_artifacts():
    campaign = contract_search.ArtifactCampaign.__new__(contract_search.ArtifactCampaign)
    campaign.selection = [{"id": f"w{i}"} for i in range(8)]
    campaign.report = {
        "stages": {"baseline_reproduction": "measured", "factor_screen": "in_progress"},
        "screening": {"initial_candidates": list(contract_search.FACTOR_CANDIDATE_NAMES),
                      "initial_candidate_count": 28, "candidates": {}},
        "prepared_candidate_artifacts": {},
    }
    with pytest.raises(RuntimeError, match="candidate artifact is missing"):
        campaign.run_factor_quick()


def test_reproduction_protocol_records_the_shared_weight_output_path(tmp_path):
    campaign_output = Path(contract_search.ROOT/"results/numerical/contract_improvement")
    protocol = contract_search.reproduction_protocol(campaign_output/"weights.safetensors")
    assert protocol["inputs"]["shared_integer_weights"] == \
        "src/tinyllm/quantize/results/numerical/contract_improvement/weights.safetensors"
    external = contract_search.reproduction_protocol(tmp_path/"weights.safetensors")
    assert external["inputs"]["shared_integer_weights"] == \
        str((tmp_path/"weights.safetensors").resolve())


def test_reused_combined_artifact_refreshes_weight_path_and_metadata(tmp_path):
    output = tmp_path/"campaign"
    candidate = contract_search.COMBINED_CANDIDATE
    config_path = output/"artifacts"/candidate/"config.json"
    config_path.parent.mkdir(parents=True)
    (output/"weights.safetensors").write_bytes(b"weights")
    config_path.write_text(json.dumps({"weights": "../../../contract_search/weights.safetensors"}))

    compiler = contract_search.ArtifactCompiler.__new__(contract_search.ArtifactCompiler)
    compiler.args = SimpleNamespace(output_dir=output)
    compiler.shared_weights = output/"weights.safetensors"
    compiler.report = {
        "stages": {"combined_candidate_prepare": "complete"},
        "prepared_candidate_artifacts": {candidate: f"artifacts/{candidate}/config.json"},
        "screening": {"candidates": {candidate: {"quick": {"per_window": [{"id": "w0"}]}}}},
        "artifact_preparation": {candidate: {"weights_shared_from": "../contract_search/weights.safetensors"}},
    }
    compiler.save = lambda: None

    assert compiler.prepare_combined_candidate() == config_path
    assert json.loads(config_path.read_text())["weights"] == "../../weights.safetensors"
    assert compiler.report["artifact_preparation"][candidate]["weights_shared_from"] == \
        contract_search._workspace_path(compiler.shared_weights)
