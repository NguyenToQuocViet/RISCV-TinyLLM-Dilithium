"""Independent static high-bit oracles, histogram lifecycle, provenance and cache contracts."""
from copy import deepcopy
from collections import Counter
import json

import numpy as np
import pytest
import torch
from torch.ao.quantization import FakeQuantize
from safetensors import safe_open
from safetensors.torch import load_file, save_file
from transformers import LlamaConfig, LlamaForCausalLM
from fp32_reference import ROOT, cached_logits, read_json
from ptq_calibrate import stream_cache

from ptq_eval import full_logits
from ptq_fake_quant import PTQAdapter, QuantPoint, default_config
from ptq_validate import assert_state_equal, probe_cache


@pytest.mark.parametrize('bits', [12, 16])
def test_high_bit_rounding_clamp_half_steps_and_observed_scale(bits):
    point = QuantPoint('A', bits)
    bound = (1 << (bits - 1)) - 1
    values = torch.tensor([-2*bound, -bound, -2.5, -1.5, -.5, 0, .5, 1.5, 2.5, bound, 2*bound]) * .25
    point.fq.scale.fill_(.25); point.fq.enable_fake_quant()
    actual = point(values)
    expected = np.array([min(bound,max(-bound,round(float(x)/.25)))*.25 for x in values], dtype=np.float32)
    np.testing.assert_array_equal(actual.numpy(), expected)
    assert point.fq.activation_post_process.dtype == torch.qint32
    point.fq.disable_fake_quant(); point.fq.enable_observer()
    point(torch.tensor([0., -12., 8.]))
    assert float(point.fq.scale) == pytest.approx(12/bound, rel=1e-7)
    assert point.fq.zero_point.item() == 0
    point.reset_observer(); point.fq.enable_observer(); point(torch.zeros(4))
    assert float(point.fq.scale) == torch.finfo(torch.float32).eps


def tiny_model():
    torch.manual_seed(1234)
    return LlamaForCausalLM(LlamaConfig(vocab_size=19,hidden_size=12,intermediate_size=24,
        num_hidden_layers=2,num_attention_heads=3,num_key_value_heads=1,
        tie_word_embeddings=True,attn_implementation='eager')).eval()


@pytest.mark.parametrize('observer,bits', [('histogram_l2',8),('absolute_percentile_99.99',8),('minmax',12),('minmax',16)])
@torch.inference_mode()
def test_static_lifecycle_recalibration_reload_native_cache(observer,bits,tmp_path):
    model=tiny_model(); ids=[1,4,8,3,2]
    weights={name: p.clone() for name,p in model.named_parameters()}
    native=full_logits(model,ids).clone()
    config=default_config(); config.update(activation_bits=bits,activation_observer=observer,activation_histogram_bins=128)
    adapter=PTQAdapter(model,config)
    assert torch.equal(full_logits(model,ids),native)
    for cycle in range(2):
        adapter.begin_calibration()
        point=adapter.points['lm_head.input']
        if observer!='minmax':
            assert point.fq.activation_post_process.histogram.sum()==0
            # Any calculate_qparams during observation is a hard failure.
            def forbidden():
                raise AssertionError('Histogram range search ran before freeze')
            original=point.fq.activation_post_process.calculate_qparams
            point.fq.activation_post_process.calculate_qparams=forbidden
        assert torch.equal(full_logits(model,ids),native)
        if observer!='minmax':
            point.fq.activation_post_process.calculate_qparams=original
            assert point.freeze_calculations==0 and point.fq.scale.item()==1
        adapter.freeze()
        assert point.freeze_calculations == 1
        with pytest.raises(ValueError): adapter.freeze()
        adapter.set_mode('quantize'); before=adapter.qparam_state()
        quantized=full_logits(model,ids).clone()
        cache=probe_cache(adapter,ids,3)
        assert cache['new_tensors']==12 and cache['unchanged_prefix_tensors']==8
        assert_state_equal(before,adapter)
        adapter.set_mode('disabled'); assert torch.equal(full_logits(model,ids),native)
    path=tmp_path/'params.safetensors'; adapter.save_qparams(path); adapter.restore()
    loaded=PTQAdapter(model,config); loaded.load_qparams(path); loaded.set_mode('quantize')
    assert torch.equal(full_logits(model,ids),quantized)
    assert all(torch.equal(p,weights[name]) for name,p in model.named_parameters())
    assert model.model.embed_tokens.weight is model.lm_head.weight
    loaded.restore()


@torch.inference_mode()
def test_common_loader_rejects_bits_policy_observer_axes_and_recomputes_w(tmp_path):
    model=tiny_model(); adapter=PTQAdapter(model)
    adapter.begin_calibration(); full_logits(model,[1,2,3,4]); adapter.freeze()
    path=tmp_path/'params.safetensors'; adapter.save_qparams(path); config=deepcopy(adapter.config); adapter.restore()
    for change in ({'activation_bits':12},{'key_bits':4},{'value_bits':4},
                   {'activation_observer':'histogram_l2'},{'activation_policy':'dynamic_per_token'}):
        candidate=PTQAdapter(model,{**config,**change})
        with pytest.raises(ValueError,match='mismatch'): candidate.load_qparams(path)
        candidate.restore()
    tensors=load_file(path)
    with safe_open(path,framework='pt') as archive: contract=json.loads(archive.metadata()['ptq_contract'])
    contract['points']['lm_head.input']['axis']=0
    bad=tmp_path/'bad.safetensors'; save_file(tensors,bad,metadata={'ptq_contract':json.dumps(contract)})
    candidate=PTQAdapter(model,config)
    with pytest.raises(ValueError,match='mismatch'): candidate.load_qparams(bad)
    candidate.restore()
    candidate=PTQAdapter(model,{**config,'decoder_weight_bits':4})
    with pytest.raises(ValueError,match='mismatch'): candidate.load_qparams(path)
    candidate.load_qparams(path,recompute_weights=True)
    name='model.layers.0.self_attn.q_proj.weight'
    expected=model.model.layers[0].self_attn.q_proj.weight.abs().amax(1)/7
    torch.testing.assert_close(candidate.points[name].fq.scale,expected,rtol=1e-7,atol=0)
    candidate.restore()


def test_absolute_percentile_bin_edge_oracle():
    point=QuantPoint('A',8,observer='absolute_percentile_99.99',bins=4)
    observer=point.fq.activation_post_process
    observer.min_val.fill_(0); observer.max_val.fill_(8)
    observer.histogram.copy_(torch.tensor([9999.,0.,0.,1.]))
    point.finish_observation()
    assert float(point.fq.scale)==pytest.approx(2/127,rel=1e-7)
    assert point.fq.zero_point.item()==0


def test_kl_direction_all_vocabulary_and_top1_oracle():
    import math
    from ptq_finalize import distribution_diagnostic
    p=np.array([[.7,.2,.1],[.1,.6,.3]],dtype=np.float64)
    q=np.array([[.2,.7,.1],[.1,.6,.3]],dtype=np.float64)
    result=distribution_diagnostic(np.log(p),np.log(q))
    expected=sum(p[i,j]*math.log(p[i,j]/q[i,j]) for i in range(2) for j in range(3))/2
    assert result['mean_kl_fp32_to_candidate']==pytest.approx(expected,rel=1e-12)
    assert result['top1_agreement']==.5 and result['vocabulary']==3


def test_activation_payload_uses_actual_input_width_and_all_static_bits():
    from ptq_storage import storage_inventory
    model=tiny_model();adapter=PTQAdapter(model)
    rows=storage_inventory(model,adapter,length=5)['activations']
    down=next(row for row in rows if row['point']=='model.layers.0.mlp.down_proj.input')
    assert down['shapes']=={'prefill':[1,5,24],'decode':[1,1,24]}
    assert down['static_width_comparison_bytes']=={'8':{'prefill':120,'decode':24},
        '12':{'prefill':180,'decode':36},'16':{'prefill':240,'decode':48}}
    adapter.restore()


@torch.inference_mode()
def test_legacy_bundle_only_matches_original_minmax_contract(tmp_path):
    model=tiny_model();adapter=PTQAdapter(model)
    adapter.begin_calibration();full_logits(model,[1,2,3,4]);adapter.freeze()
    tensors={name+suffix:getattr(point.fq,suffix[1:]).clone()
             for name,point in adapter.points.items() for suffix in ('.scale','.zero_point')}
    path=tmp_path/'qparams.safetensors';save_file(tensors,path)
    (tmp_path/'config.json').write_text(json.dumps(adapter.config))
    (tmp_path/'metadata.json').write_text(json.dumps({'points':adapter.point_specs()}))
    config=adapter.config;adapter.restore()
    loaded=PTQAdapter(model,config);loaded.load_qparams(path);loaded.restore()
    loaded=PTQAdapter(model,{**config,'activation_bits':16})
    with pytest.raises(ValueError,match='mismatch'):loaded.load_qparams(path)
    loaded.restore()


@torch.inference_mode()
def test_explicit_dynamic_load_ignores_static_a_but_keeps_static_contracts(tmp_path):
    model=tiny_model();adapter=PTQAdapter(model)
    adapter.begin_calibration();full_logits(model,[1,2,3,4]);adapter.freeze()
    path=tmp_path/'params.safetensors';adapter.save_qparams(path);config=deepcopy(adapter.config);adapter.restore()
    tensors=load_file(path)
    with safe_open(path,framework='pt') as archive:metadata=archive.metadata()
    for key,value in tensors.items():
        if '.input.' in key:
            value.fill_(1e6 if key.endswith('.scale') else 13)
    changed=tmp_path/'changed.safetensors';save_file(tensors,changed,metadata=metadata)
    dynamic={**config,'activation_policy':'dynamic_per_token'}
    candidate=PTQAdapter(model,dynamic)
    with pytest.raises(ValueError,match='mismatch'):candidate.load_qparams(path)
    candidate.load_qparams(path,load_static_for_dynamic=True);candidate.set_mode('quantize')
    expected=full_logits(model,[1,2,3,4]).clone();candidate.restore()
    candidate=PTQAdapter(model,dynamic)
    candidate.load_qparams(changed,load_static_for_dynamic=True);candidate.set_mode('quantize')
    assert torch.equal(full_logits(model,[1,2,3,4]),expected)
    assert all(p.fq.scale.item()==1 for p in candidate.points.values() if p.kind=='A')
    candidate.restore()
    wrong=PTQAdapter(model,{**dynamic,'key_bits':4})
    with pytest.raises(ValueError,match='mismatch'):wrong.load_qparams(path,load_static_for_dynamic=True)
    wrong.restore()
    static=PTQAdapter(model,config)
    with pytest.raises(ValueError,match='dynamic A'):static.load_qparams(path,load_static_for_dynamic=True)
    static.restore()


@torch.inference_mode()
def test_independent_whole_model_w4_oracle_rejects_stale_w8_scales():
    from ptq_validate import validate_weight_qparams
    model=tiny_model();config=default_config();config['decoder_weight_bits']=4
    adapter=PTQAdapter(model,config);adapter.begin_calibration();full_logits(model,[1,2,3,4]);adapter.freeze()
    result=validate_weight_qparams(adapter)
    assert result['decoder_tensors']==14 and result['shared_tensors']==1 and result['rows']==203
    adapter.points['model.layers.0.self_attn.q_proj.weight'].fq.scale.mul_(7/127)
    with pytest.raises(AssertionError):validate_weight_qparams(adapter)
    adapter.restore()


@pytest.mark.parametrize("variant", ["tensor", "channel", "histogram", "percentile", "smooth"])
@torch.inference_mode()
def test_adapter_deferred_calibration_matches_independent_oracles_and_resets(variant, monkeypatch):
    model = tiny_model(); config = default_config(); config["activation_histogram_bins"] = 128
    if variant == "channel": config["activation_policy"] = "static_per_input_channel"
    if variant == "histogram": config["activation_observer"] = "histogram_l2"
    if variant == "percentile": config["activation_observer"] = "absolute_percentile_99.99"
    if variant == "smooth": config["smoothquant"] = read_json(ROOT / "configs/extra/w8a12kv8_smoothquant.json")["smoothquant"]
    adapter = PTQAdapter(model, config)
    if variant == "smooth":
        adapter.begin_smooth_calibration(); full_logits(model, [1, 2, 3]); adapter.finalize_smoothquant()
    for ids in ([1, 4, 8, 3, 2], [2, 6, 7, 9]):
        oracles = {}
        for name, point in adapter.points.items():
            oracle = FakeQuantize(**point.kwargs); oracle.disable_fake_quant(); oracles[name] = oracle
            def observe(value, result, *, oracle=oracle, point=point):
                assert torch.equal(value, result)
                oracle(value.abs() if point.observer == "absolute_percentile_99.99" else value)
            point.capture = observe
        adapter.begin_calibration()
        calculations = Counter()
        for name, point in adapter.points.items():
            original = point.fq.activation_post_process.calculate_qparams
            def calculate(*, name=name, original=original):
                calculations[name] += 1
                return original()
            monkeypatch.setattr(point.fq.activation_post_process, "calculate_qparams", calculate)
            assert point.freeze_calculations == 0
        full_logits(model, ids); stream_cache(model, ids, 2)
        assert not calculations
        assert all(p.fq.scale.numel() == 1 and p.fq.scale.item() == 1 for p in adapter.points.values())
        adapter.freeze()
        for name, point in adapter.points.items():
            assert point.freeze_calculations == 1
            assert calculations[name] == (0 if point.observer == "absolute_percentile_99.99" else 1)
            oracle = oracles[name]
            if point.observer == "absolute_percentile_99.99":
                obs = oracle.activation_post_process
                histogram = obs.histogram.numpy().astype(np.float64)
                index = np.searchsorted(np.cumsum(histogram), histogram.sum() * .9999)
                threshold = np.float32(float(obs.min_val) + min(index + 1, obs.bins) * np.float32((float(obs.max_val) - float(obs.min_val)) / obs.bins))
                expected = max(np.float32(threshold / point.fq.quant_max), np.finfo(np.float32).eps)
                assert float(point.fq.scale) == expected
                assert torch.all(point.fq.zero_point == 0)
            else:
                assert torch.equal(point.fq.scale, oracle.scale), name
                assert torch.equal(point.fq.zero_point, oracle.zero_point), name
            point.capture = None
        adapter.set_mode("quantize"); before = adapter.qparam_state()
        assert torch.isfinite(full_logits(model, ids)).all()
        assert np.isfinite(cached_logits(model, ids, 2)).all()
        assert_state_equal(before, adapter)
    adapter.restore()
