"""Regression coverage for frozen-parameter intermediate calibration."""
from copy import deepcopy
import math

import numpy as np
import pytest
import torch

from fp32_reference import ROOT, read_json
from ptq_eval import full_logits
from ptq_fake_quant import PTQAdapter, QuantPoint
import ptq_fake_quant as ptq
from ptq_intermediate_calibrate import TensorStats, IntermediateProfiler, full_signed_range, derived_qparams
from test_ptq_a_extensions import tiny_model
from transformers import DynamicCache, LlamaConfig, LlamaForCausalLM


def test_streaming_statistics_and_histogram_quantile_bounds():
    batches = [np.array([[-8., 0., 1.], [-2., 4., 8.]], dtype=np.float32),
               np.array([[-1., 0., 2.]], dtype=np.float32)]
    stats = TensorStats()
    for i, value in enumerate(batches):
        stats.update(torch.from_numpy(value), 'prefill' if i == 0 else 'decode', -1)
    actual = stats.summary()
    reference = np.concatenate(batches).astype(np.float64)
    assert actual['elements'] == reference.size
    assert actual['minimum'] == reference.min() and actual['maximum'] == reference.max()
    assert actual['mean'] == pytest.approx(reference.mean(), abs=2e-7)
    assert actual['std'] == pytest.approx(reference.std(), rel=2e-7)
    assert actual['zeros'] == 2
    assert actual['groups']['minimum'] == reference.min(0).tolist()
    assert actual['groups']['maximum'] == reference.max(0).tolist()
    assert sum(actual['abs_histogram'].values()) == reference.size
    ordered = sorted(abs(x) for x in reference.reshape(-1))
    for percentile, upper in actual['abs_percentile_upper_bounds'].items():
        rank = math.ceil(len(ordered) * float(percentile) / 100)
        exact = ordered[rank-1]
        assert exact <= upper <= max(ordered)
        if exact:
            assert upper <= exact * 1.125
    assert actual['phases']['decode']['elements'] == 3
    assert actual['minmax_scale_candidates']['signed_per_tensor']['4'] == 8/7
    assert actual['minmax_scale_candidates']['zero_point'] == 0


def test_masked_entries_never_enter_statistics():
    values = torch.tensor([[[[1., -3e38], [2., 3.]], [[4., -3e38], [5., 6.]]]])
    allowed = torch.tensor([[[[True, False], [True, True]]]])
    stats = TensorStats()
    stats.update(values, 'prefill', 1, allowed)
    result = stats.summary()
    assert result['elements'] == 6
    assert result['minimum'] == 1 and result['maximum'] == 6
    assert result['groups']['minimum'] == [1., 4.]
    assert result['groups']['maximum'] == [3., 6.]
    assert sum(result['abs_histogram'].values()) == 6


def test_zero_subnormal_and_nonfinite_statistics():
    stats = TensorStats()
    stats.update(torch.zeros(7), 'prefill')
    assert set(stats.summary()['abs_percentile_upper_bounds'].values()) == {0.}
    assert set(stats.summary()['minmax_scale_candidates']['signed_per_tensor'].values()) == {1.}
    assert set(stats.summary()['minmax_scale_candidates']['unsigned_per_tensor'].values()) == {1.}
    stats.update(torch.tensor([torch.finfo(torch.float32).tiny]), 'decode')
    assert stats.summary()['abs_percentile_upper_bounds']['100'] > 0
    with pytest.raises(ValueError, match='Nonfinite'):
        stats.update(torch.tensor([float('inf')]), 'decode')


def test_candidate_scales_cover_asymmetric_observed_range():
    stats = TensorStats()
    values = [-20., -1., 0., 3., 9.]
    stats.update(torch.tensor(values), 'prefill')
    candidates = stats.summary()['minmax_scale_candidates']['signed_per_tensor']
    assert candidates['5'] == 1.25
    for bits, scale in candidates.items():
        bits = int(bits)
        codes = [round(value/scale) for value in values]
        assert min(codes) >= -(1 << (bits-1))
        assert max(codes) <= (1 << (bits-1))-1


def test_v_cache_transfer_uses_native_head_scales_in_row_order():
    model = LlamaForCausalLM(LlamaConfig(vocab_size=17,hidden_size=12,intermediate_size=24,
        num_hidden_layers=1,num_attention_heads=3,num_key_value_heads=3,
        tie_word_embeddings=True,attn_implementation='eager')).eval()
    config = read_json(ROOT / 'candidates/w8a12kv8_smoothquant/config.json')
    adapter = PTQAdapter(model, config)
    for point in adapter.points.values():
        point.fq.scale.resize_(point.channels).fill_(1.)
    name = 'model.layers.0.self_attn.v_proj'
    adapter.points[name+'.input'].fq.scale.fill_(.5)
    adapter.points[name+'.weight'].fq.scale.copy_(torch.arange(1,13,dtype=torch.float32))
    adapter.points['model.layers.0.self_attn.value_post_projection'].fq.scale.copy_(torch.tensor([1.,2.,4.]))
    tensors, descriptions = derived_qparams(model, adapter)
    key = descriptions[name]['to_value_cache']['coefficient_tensor']
    expected = torch.tensor([.5,1.,1.5,2.,1.25,1.5,1.75,2.,1.125,1.25,1.375,1.5],dtype=torch.float64)
    torch.testing.assert_close(tensors[key], expected, rtol=0, atol=0)


@pytest.mark.parametrize('kind,bits', [('A',12), ('W',8), ('K',8), ('V',8)])
def test_full_signed_clipping_preserves_scale_and_matches_scalar_oracle(kind, bits):
    point = QuantPoint(kind, bits)
    point.fq.scale.fill_(0.25)
    point.fq.zero_point.zero_()
    point.fq.disable_observer()
    point.fq.enable_fake_quant()
    scale = point.fq.scale.clone()
    adapter = type('Adapter', (), {'points': {'x': point}, 'materialized': {'old': 1}})()
    full_signed_range(adapter)
    limit = 1 << (bits-1)
    values = torch.tensor([(-limit-1)*.25, -limit*.25, -.375, -.125, 0., .125, .375, limit*.25])
    expected = torch.tensor([max(-limit, min(limit-1, round(float(v)/.25)))*.25 for v in values])
    values, expected = values.reshape(1,1,1,-1), expected.reshape(1,1,1,-1)
    torch.testing.assert_close(point(values), expected, rtol=0, atol=0)
    assert torch.equal(point.fq.scale, scale) and not adapter.materialized


@torch.inference_mode()
def test_instrumentation_preserves_full_and_cached_logits_and_restores_callbacks():
    model = tiny_model()
    config = read_json(ROOT / 'candidates/w8a12kv8_smoothquant/config.json')
    adapter = PTQAdapter(model, deepcopy(config))
    ids = [1,4,8,3,2]
    adapter.begin_smooth_calibration(); full_logits(model, ids); adapter.finalize_smoothquant()
    adapter.begin_calibration(); full_logits(model, ids); adapter.freeze()
    full_signed_range(adapter)
    adapter.set_mode('quantize')
    frozen = {name: (p.fq.scale.clone(), p.fq.zero_point.clone()) for name,p in adapter.points.items()}
    source = {name: p.clone() for name,p in model.named_parameters()}
    smooth = {name: s.clone() for name,s in adapter.smooth_scales.items()}
    native = full_logits(model, ids)
    def cached():
        cache = DynamicCache()
        output = []
        for start,end in [(0,2),(2,3),(3,4),(4,5)]:
            result = model(input_ids=torch.tensor([ids[start:end]]), past_key_values=cache, use_cache=True)
            output.append(result.logits)
        return torch.cat(output, dim=1)
    native_cache = cached()
    original = ptq.eager_attention_forward
    original_rotary = ptq.apply_rotary_pos_emb
    profiler = IntermediateProfiler(model, adapter)
    with profiler.attached():
        assert torch.equal(native, full_logits(model, ids))
        profiler.phase = 'decode'
        assert torch.equal(native_cache, cached())
    assert ptq.eager_attention_forward is original
    assert ptq.apply_rotary_pos_emb is original_rotary
    assert all(p.capture is None for p in adapter.points.values())
    for name,p in adapter.points.items():
        assert torch.equal(p.fq.scale, frozen[name][0]) and torch.equal(p.fq.zero_point, frozen[name][1])
    assert all(torch.equal(p, source[name]) for name,p in model.named_parameters())
    assert all(torch.equal(s, smooth[name]) for name,s in adapter.smooth_scales.items())
    for i in range(2):
        prefix = f'model.layers.{i}'
        assert profiler.points[prefix+'.mlp.gate_product'].total.count == 10*24
        assert profiler.points[prefix+'.mlp.silu_output'].total.count == 10*24
        assert profiler.points[prefix+'.self_attn.query_post_rope'].total.count == 10*12
        assert profiler.points[prefix+'.self_attn.key_post_rope.before_quantize'].total.count == 10*4
        # 15 causal pairs full + (3+3+4+5) cached, with 3 query heads.
        assert profiler.points[prefix+'.self_attn.score'].total.count == 30*3
        assert profiler.points[prefix+'.self_attn.score_minus_max'].total.maximum == 0.
        assert profiler.points[prefix+'.self_attn.softmax_sum_reference'].total.minimum >= 1.
        assert profiler.points[prefix+'.self_attn.softmax_sum_reference'].total.maximum <= len(ids)
        assert profiler.points[prefix+'.self_attn.rope.query_cos_product'].total.count == 10*12
        assert profiler.points[prefix+'.input_layernorm.square'].total.count == 10*12
    tensors, descriptions = derived_qparams(model, adapter)
    for name,module in model.named_modules():
        if not isinstance(module, torch.nn.Linear):
            continue
        wname = 'shared_embedding_lm_head.weight' if name == 'lm_head' else name+'.weight'
        a = float(adapter.points[name+'.input'].fq.scale)
        w = adapter.points[wname].fq.scale.numpy().astype(np.float64)
        expected_scale = np.array([a * x for x in w])
        actual_scale = tensors[descriptions[name]['scale_tensor']].numpy()
        np.testing.assert_array_equal(actual_scale, expected_scale)
        assert descriptions[name]['zero_point'] == 0 and descriptions[name]['bits'] == 32
        if name.endswith('self_attn.v_proj'):
            source = name.removesuffix('v_proj')+'value_post_projection'
            vscale = float(adapter.points[source].fq.scale)
            coefficient = descriptions[name]['to_value_cache']['coefficient_tensor']
            np.testing.assert_array_equal(tensors[coefficient].numpy(), expected_scale/vscale)
    with pytest.raises(RuntimeError, match='probe'):
        with profiler.attached():
            raise RuntimeError('probe')
    assert ptq.eager_attention_forward is original
    assert ptq.apply_rotary_pos_emb is original_rotary
    assert all(p.capture is None for p in adapter.points.values())
