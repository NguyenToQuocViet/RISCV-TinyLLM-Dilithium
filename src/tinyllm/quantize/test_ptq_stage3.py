"""Oracles cho A động theo token và ngưỡng chọn ứng viên."""
from copy import deepcopy
import hashlib
from types import SimpleNamespace

import numpy as np
import pytest
import torch
from transformers import LlamaConfig, LlamaForCausalLM
from fp32_reference import ROOT
import ptq_finalize as finalize

from ptq_fake_quant import PTQAdapter, default_config, dynamic_token_fake_quant
from ptq_eval import full_logits
from ptq_experiment import quality_gate
from ptq_validate import assert_state_equal


@pytest.mark.parametrize("bits", [4, 8])
def test_dynamic_per_token_oracle_and_no_future_or_batch_dependence(bits):
    bound = (1 << (bits - 1)) - 1
    value = torch.tensor([[[bound * .25, -.625, .375, 0], [0, 0, 0, 0]],
                          [[bound * .5, -1.25, .75, 0], [1, -1, 0, .5]]], dtype=torch.float32)
    actual = dynamic_token_fake_quant(value, bits)
    expected = np.empty(value.shape, dtype=np.float32)
    for batch in range(2):
        for token in range(2):
            row = value[batch, token].numpy()
            scale = np.float32(max(float(max(abs(float(x)) for x in row)) / bound, np.finfo(np.float32).eps))
            for i, x in enumerate(row):
                expected[batch, token, i] = min(bound, max(-bound, round(float(x) / float(scale)))) * scale
    np.testing.assert_allclose(actual.numpy(), expected, atol=1e-7, rtol=1e-7)
    extended = torch.cat([value, torch.full((2, 1, 4), 100000.)], dim=1)
    assert torch.equal(dynamic_token_fake_quant(extended, bits)[:, :2], actual)
    changed_batch = value.clone(); changed_batch[1] *= 10000
    assert torch.equal(dynamic_token_fake_quant(changed_batch, bits)[0], actual[0])
    tokenwise = torch.cat([dynamic_token_fake_quant(value[:, i:i+1], bits) for i in range(2)], dim=1)
    assert torch.equal(tokenwise, actual)


@torch.inference_mode()
def test_dynamic_adapter_causality_static_buffers_and_bypass():
    torch.manual_seed(1234)
    model = LlamaForCausalLM(LlamaConfig(vocab_size=19, hidden_size=12, intermediate_size=24,
        num_hidden_layers=2, num_attention_heads=3, num_key_value_heads=1,
        tie_word_embeddings=True, attn_implementation="eager")).eval()
    native = full_logits(model, [1, 4, 8]).clone()
    config = default_config(); config['activation_policy'] = 'dynamic_per_token'
    adapter = PTQAdapter(model, config)
    adapter.begin_calibration(); full_logits(model, [1, 4, 8, 3, 2]); adapter.freeze()
    adapter.set_mode('quantize')
    before = adapter.qparam_state()
    short = full_logits(model, [1, 4, 8]).clone()
    long = full_logits(model, [1, 4, 8, 3, 2]).clone()
    torch.testing.assert_close(short, long[:3], rtol=1e-5, atol=2e-4)
    assert_state_equal(before, adapter)
    adapter.set_mode('disabled')
    assert torch.equal(full_logits(model, [1, 4, 8]), native)
    adapter.restore()


def test_quality_gate_thresholds_are_not_relaxed():
    reference = {'ppl': {'ppl': 20.0}, 'piqa': {'accuracy': 625/919}}
    assert quality_gate(21.0, 607/919, reference)['pass']
    assert not quality_gate(21.0001, 607/919, reference)['pass']
    assert not quality_gate(20.0, 606/919, reference)['pass']


@pytest.mark.parametrize("mismatch", ["config", "qparams"])
def test_finalizer_rejects_ppl_from_another_candidate(tmp_path, monkeypatch, mismatch):
    config = default_config()
    qparams = tmp_path / "qparams.safetensors"
    qparams.write_bytes(b"candidate qparams")
    ppl = {"config": deepcopy(config), "mode": "ppl", "status": "PASS", "ppl": {"ppl": 20.0},
           "qparams_sha256": hashlib.sha256(qparams.read_bytes()).hexdigest()}
    if mismatch == "config": ppl["config"]["activation_bits"] = 12
    else: ppl["qparams_sha256"] = "another candidate's qparams"
    files = {tmp_path / "wikitext_selection.json": [], tmp_path / "piqa_selection.json": [],
             tmp_path / "cache_cases.json": [], tmp_path / "config.json": config,
             tmp_path / "ppl.json": ppl, ROOT / "results/ptq/fp32.json": {"ppl": {"ppl": 20.0}}}
    args = SimpleNamespace(data_dir=tmp_path, config=tmp_path / "config.json", qparams=qparams,
                           ppl_result=tmp_path / "ppl.json", structural_only=False, cache_dir=tmp_path, offline=True)
    monkeypatch.setattr(finalize, "configure_runtime", lambda: None)
    monkeypatch.setattr(finalize, "read_json", files.__getitem__)
    monkeypatch.setattr(finalize, "source_snapshot", lambda *_: None)
    monkeypatch.setattr(finalize, "load_model", lambda _: (None, None))
    monkeypatch.setattr(finalize, "load_candidate", lambda *_: SimpleNamespace(config=config))
    with pytest.raises(ValueError, match="candidate config/qparams"): finalize.run(args)


def test_storage_counts_shared_weight_norms_metadata_and_native_kv_heads():
    from ptq_storage import storage_inventory
    model = LlamaForCausalLM(LlamaConfig(vocab_size=19, hidden_size=12, intermediate_size=24,
        num_hidden_layers=2, num_attention_heads=3, num_key_value_heads=1,
        tie_word_embeddings=True, attn_implementation='eager')).eval()
    adapter = PTQAdapter(model)
    inventory = storage_inventory(model,adapter,length=5)
    s=inventory['summary']
    assert s['model_parameters']==2784
    assert s['weight_payload_bytes']==2964 and s['fp32_weight_elements']==60
    assert s['weight_metadata_bytes']==203*8 and s['static_a_metadata_bytes']==15*8
    assert s['kv_payload_bytes']==80 and s['kv_metadata_bytes']==4*8
    assert s['total_persistent_bytes']==4820
    assert sum('aliases' in row for row in inventory['weights'])==1
    assert all(row['shape_BHTD']==[1,1,5,4] for row in inventory['cache'])
    adapter.restore()
