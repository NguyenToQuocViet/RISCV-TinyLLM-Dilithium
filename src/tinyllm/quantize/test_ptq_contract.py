"""Independent numerical oracles for proposed integer interfaces and nonlinearities."""
from fractions import Fraction
import math

import numpy as np
import pytest
import torch

import ptq_contract as contract
import ptq_contract_search as contract_search


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


def test_fused_softmax_components_keep_the_original_lut_and_mask():
    from ptq_contract_fused import index_softmax_components
    scores = [17, -1, -12, 10, -400, 16, 17]
    valid = [True, True, True, False, True, True, True]
    lut = reference_softmax_lut(32, 8)
    maximum = max(v for v, allowed in zip(scores, valid) if allowed)
    expected = [lut[min(31, reference_divide((maximum-v)*31, 128))] if allowed else 0
                for v, allowed in zip(scores, valid)]
    e, s = index_softmax_components(torch.tensor(scores)[None, None, None], .0625,
                                   torch.tensor(valid)[None, None, None])
    assert e.flatten().tolist() == expected
    assert int(s) == sum(expected)
    with pytest.raises(ValueError, match='valid key'):
        index_softmax_components(torch.tensor(scores), .0625, torch.zeros(7, dtype=torch.bool))


@pytest.mark.parametrize('length', [1, 255, 256, 512])
def test_fused_pv_constant_v_and_full_signed_extrema(length):
    from ptq_contract_fused import fused_pv
    values = [-128, -127, -1, 0, 1, 126, 127]
    e = torch.full((1, 1, 1, length), 255, dtype=torch.int64)
    v = torch.tensor(values)[None, None, None].expand(1, 1, length, len(values))
    s = torch.full((1, 1, 1, 1), 255*length, dtype=torch.int64)
    assert fused_pv(e, s, v, 1.).flatten().tolist() == values


@pytest.mark.parametrize('bits', [16, 24, 31])
def test_fused_pv_exact_signed_ties_and_per_head_ratio(bits):
    from ptq_contract_fused import fused_pv
    e = torch.tensor([[[[255, 255]], [[255, 0]]]])
    v = torch.tensor([[[[-3, -1, 1, 3], [0, 0, 0, 0]],
                       [[-128, -1, 1, 127], [127, 127, 127, 127]]]])
    s = e.sum(-1, keepdim=True)
    ratios = torch.tensor([1., 1.5], dtype=torch.float64).reshape(1, 2, 1, 1)
    expected = [reference_divide(n, 2) for n in [-3, -1, 1, 3]]
    expected += [round(Fraction(n)*Fraction(3, 2)) for n in [-128, -1, 1, 127]]
    actual = fused_pv(e, s, v, ratios, bits)
    assert actual.flatten().tolist() == expected


def test_fused_pv_wide_denominator_and_left_shift_against_fraction():
    from ptq_contract_fused import fused_pv
    e = torch.tensor([[[[255, 128, 0], [1, 254, 255]]]])
    v = torch.tensor([[[[-128, 127], [3, -7], [19, 23]]]])
    s = e.sum(-1, keepdim=True)
    for ratio in (1e-30, 2.**40):
        m, shift = contract.encode_multiplier(ratio, 31)
        expected = []
        for row in e[0, 0].tolist():
            output = []
            for feature in range(2):
                a = sum(weight*int(v[0, 0, j, feature]) for j, weight in enumerate(row))
                numerator, denominator = a*int(m), sum(row)
                if int(shift) >= 0:
                    denominator *= 1 << int(shift)
                else:
                    numerator *= 1 << -int(shift)
                output.append(reference_divide(numerator, denominator))
            expected.append(output)
        assert fused_pv(e, s, v, ratio, 31)[0, 0].tolist() == expected


def test_fused_pv_random_rows_match_independent_integer_dot_and_fraction():
    from ptq_contract_fused import fused_pv
    rng = np.random.default_rng(71)
    ee = rng.integers(0, 256, size=(2, 512), dtype=np.int64)
    ee[:, 0] = 255
    vv = rng.integers(-128, 128, size=(512, 64), dtype=np.int64)
    expected = [[reference_divide(sum(int(ee[r, j])*int(vv[j, f]) for j in range(512)),
                                   sum(map(int, ee[r])))
                 for f in range(64)] for r in range(2)]
    e = torch.from_numpy(ee)[None, None]
    v = torch.from_numpy(vv)[None, None]
    got = fused_pv(e, e.sum(-1, keepdim=True), v, 1.)
    assert got[0, 0].tolist() == expected


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


def test_complete_simulation_fused_and_discrete_paths_match_cached_codes_and_prefix():
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
        for fused in (False, True):
            points = {name: {'bits': 12} for name in adapter.inventory}
            for name, family in adapter.inventory.items():
                if family == 'residual': points[name] = {'bits': 16, 'policy': 'per_channel'}
                if family == 'probability':
                    if fused: del points[name]
                    else: points[name] = {'bits': 12}
            adapter.set_trial({'points': points, 'integer_coefficients': True,
                'coefficient_bits': 16, 'mac_dtype': 'float64', 'metrics': False,
                'nonlinear': {'rms': {'seed_entries': 32, 't_fractional_bits': 24},
                              'rope': {'coefficient_bits': 12},
                              'silu': {'segments': 8, 'threshold': 6},
                              'softmax': {'entries': 32, 'c': 8, 'probability_bits': 12,
                                          'fused': fused}}})
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


def _qualified_campaign_report():
    full_ppl = 22.574714201210707*1.001
    full_nll = math.log(full_ppl)*32704
    cache_ppl_32 = 26.676072498453824*1.01
    cache_ppl_448 = 12.019438254052904*1.01
    piqa_rows = [{'id': str(i), 'correct': i < 625} for i in range(919)]
    cache_runs = [{'id': f'case-{i}', 'prefill': prefill, 'decode': 64, 'tokens': 64,
                   'nll': math.log(cache_ppl_32 if prefill == 32 else cache_ppl_448)*512/8}
                  for i in range(8) for prefill in (32, 448)]
    return {
        'stages': {'search': 'measured', 'qualification': 'measured'},
        'combinations': {'candidate': {
            'config': {'name': 'candidate'},
            'status': 'qualified_selection',
            'full_ppl': {'ppl': full_ppl, 'nll': full_nll, 'tokens': 32704,
                         'windows': 64, 'per_window': [{'id': str(i), 'tokens': 511, 'nll': full_nll/64} for i in range(64)]},
            'relative_ppl_increase_vs_fp32': .001,
            'piqa': {'accuracy': 625/919, 'questions': 919, 'correct': 625,
                     'per_question': piqa_rows},
            'piqa_drop_vs_fp32': 0.,
            'cache': {'runs': cache_runs,
                      'regimes': {'32': {'tokens': 512, 'ppl': cache_ppl_32, 'nll': math.log(cache_ppl_32)*512},
                                  '448': {'tokens': 512, 'ppl': cache_ppl_448, 'nll': math.log(cache_ppl_448)*512}}},
            'cache_relative_ppl_increase': {'32': .01, '448': .01},
            'greedy': {'runs': []},
        }},
    }


def test_qualification_does_not_mark_empty_search_as_measured():
    from types import SimpleNamespace
    campaign = contract_search.Campaign.__new__(contract_search.Campaign)
    campaign.report = {'stages': {'search': 'measured'}, 'combinations': {}}
    with pytest.raises(RuntimeError, match='no candidate combinations'):
        campaign.qualify_stage()
    assert 'qualification' not in campaign.report['stages']


def test_export_rejects_missing_qualification_before_writing_any_artifact(tmp_path):
    from types import SimpleNamespace
    campaign = contract_search.Campaign.__new__(contract_search.Campaign)
    campaign.args = SimpleNamespace(output_dir=tmp_path)
    campaign.report = {'stages': {'search': 'measured'}, 'combinations': {}}
    with pytest.raises(RuntimeError, match='qualification stage is not measured'):
        campaign.export_stage()
    assert list(tmp_path.iterdir()) == []
    assert 'export' not in campaign.report['stages']


def test_qualification_rejects_missing_candidate_status_or_quality_evidence():
    report = _qualified_campaign_report()
    del report['combinations']['candidate']['status']
    with pytest.raises(RuntimeError, match='missing or invalid terminal quality status'):
        contract_search.require_qualification(report, require_stage=True)

    report = _qualified_campaign_report()
    del report['combinations']['candidate']['cache_relative_ppl_increase']
    with pytest.raises(RuntimeError, match='cache quality evidence is incomplete'):
        contract_search.require_qualification(report, require_stage=True)


def test_export_artifact_guard_rejects_missing_files_and_quality_mapping(tmp_path):
    from safetensors.torch import save_file

    report = _qualified_campaign_report()
    report['prepared_weights'] = {'matrices': 1, 'payload_bytes': 1}
    report['combinations']['candidate']['resources'] = {}
    report['combinations']['candidate']['coefficient_bundle_validation'] = {'status': 'passed'}
    with pytest.raises(RuntimeError, match='weights.safetensors is missing or empty'):
        contract_search.require_export_artifacts(report, tmp_path)

    save_file({'shared_embedding_lm_head.weight': torch.tensor([[1]], dtype=torch.int8)},
              str(tmp_path/'weights.safetensors'))
    candidate_dir = tmp_path/'candidate'
    candidate_dir.mkdir()
    (candidate_dir/'config.json').write_text(
        '{"quality_status":"rejected_full_ppl","weights":"../weights.safetensors",'
        '"coefficients":"coefficients.safetensors","formats":{"x":{}},'
        '"software_adapter_role":"host_preparation_simulator",'
        '"software_adapter_loads_coefficient_bundle":false,'
        '"coefficient_bundle_validation":"export tensors are checked against deterministic runtime multiplier/table compilation"}')
    save_file({'coeff': torch.tensor([1], dtype=torch.int32)},
              str(candidate_dir/'coefficients.safetensors'))
    with pytest.raises(RuntimeError, match='quality status does not match qualification'):
        contract_search.require_export_artifacts(report, tmp_path)


def test_no_default_is_reported_when_no_qualified_candidate_passes():
    report = _qualified_campaign_report()
    report['combinations']['candidate']['status'] = 'rejected_full_ppl'
    report['combinations']['candidate']['relative_ppl_increase_vs_fp32'] = .06
    # Export may preserve a rejected candidate, but must not label it default.
    qualified = {name: entry for name, entry in report['combinations'].items()
                 if entry.get('status') == 'qualified_selection'}
    summary = contract_search.selection_summary(qualified)
    assert qualified == {}
    assert summary['qualified'] == [] and summary['pareto'] == []
    assert summary['default'] is None


def test_exported_integer_coefficients_and_tables_equal_runtime_compilers():
    config = {'coefficient_bits': 16, 'nonlinear': {
        'rope': {'coefficient_bits': 8},
        'softmax': {'c': 8, 'entries': 32},
        'rms': {'seed_entries': 32},
        'silu': {'segments': 8, 'threshold': 6},
    }}
    formats = {}
    for layer in range(30):
        prefix = f'model.layers.{layer}.mlp'
        formats[prefix+'.gate_proj.output'] = contract.Format(8, .125).dictionary()
        formats[prefix+'.silu_output'] = contract.Format(16, .0625).dictionary()
    sources = {'model.layers.0.q_proj.smooth': torch.tensor([.5, -1.25], dtype=torch.float64)}
    epsilons = {'model.norm': 168}
    expected, table, compiled = contract_search.runtime_coefficient_bundle(
        config, formats, sources, epsilons)
    exported = {'formats': formats, 'pwl_reference': table, 'pwl_compiled': compiled}
    contract_search.require_runtime_bundle_match(config, exported, sources, epsilons, expected)

    changed = dict(expected)
    changed['model.layers.0.q_proj.smooth.M'] = expected['model.layers.0.q_proj.smooth.M'].clone()
    changed['model.layers.0.q_proj.smooth.M'][0] += 1
    with pytest.raises(RuntimeError, match='differ from runtime compilation'):
        contract_search.require_runtime_bundle_match(config, exported, sources, epsilons, changed)


def test_shift_export_uses_signed_int8_or_int16_without_wraparound():
    assert contract_search.shift_container([-128, 127]).dtype == torch.int8
    assert contract_search.shift_container([-129, 128]).dtype == torch.int16
    with pytest.raises(OverflowError, match='does not fit INT16'):
        contract_search.shift_container([-32769])


def test_resource_accounting_separates_boundary_containers_tables_and_attention_work(tmp_path):
    from types import SimpleNamespace

    campaign = contract_search.Campaign.__new__(contract_search.Campaign)
    campaign.args = SimpleNamespace(output_dir=tmp_path)
    campaign.adapter = SimpleNamespace(inventory={'activation': 'activation'})
    campaign.baseline = SimpleNamespace(weights={'shared': torch.ones(2, dtype=torch.int8)})
    output = tmp_path/'candidate'
    output.mkdir()
    (tmp_path/'weights.safetensors').write_bytes(b'weights')
    (output/'config.json').write_text('{}')
    config = {'points': {'activation': {'bits': 8}},
              'nonlinear': {'softmax': {'fused': True, 'entries': 32, 'c': 8}}}
    bundle = {'linear.M': torch.ones(1, dtype=torch.int32),
              'linear.shift': torch.zeros(1, dtype=torch.int8),
              'rope.cos': torch.zeros(2, dtype=torch.int16),
              'softmax.exp_lut': torch.zeros(32, dtype=torch.uint8),
              'rms.seed_lut': torch.zeros(32, dtype=torch.int16),
              'model.layers.0.mlp.pwl.slopes': torch.zeros(8, dtype=torch.int32)}
    formats = {'activation': {'bits': 8, 'scale': 1., 'axis': None, 'signed': True},
               'model.layers.0.self_attn.query_post_rope':
                   {'bits': 16, 'scale': 1., 'axis': None, 'signed': True}}
    resources = campaign.resources(config, bundle, formats, {'norm': {'internal_widths': {'t_unsigned_bits': 49}}}, output)
    expected_dense_scores = 9*512*512
    expected_causal_scores = 9*512*513//2
    assert resources['boundary_inventory']['activation']['container_bytes'] == 512*576
    assert resources['runtime_multiplier_shift_bytes'] == 5
    assert resources['runtime_table_bytes'] == sum(resources['runtime_table_breakdown_bytes'].values())
    assert resources['operation_counts_at_length_512']['normalization_divisions_dense_backend'] == 9*512*64
    assert resources['operation_counts_at_length_512']['pv_multiply_accumulates_dense_backend'] == expected_dense_scores*64
    assert resources['operation_counts_at_length_512']['pv_multiply_accumulates_if_causal_keys_skipped'] == expected_causal_scores*64
    qk_widths = resources['arithmetic_widths']
    qk_maximum = (-2**15)*(-128)*64
    assert qk_maximum == 2**28
    assert qk_maximum > (1 << (29-1))-1
    assert qk_widths['qk_product_code_range'] == [-4194176, 4194304]
    assert qk_widths['qk_accumulator_code_range'] == [-268427264, 268435456]
    assert qk_widths['qk_accumulator_bound_bits'] == 30
    assert qk_maximum <= (1 << (qk_widths['qk_accumulator_bound_bits']-1))-1
    assert resources['peak_sram_bytes'] is None and resources['fpga_area'] is None
