#!/usr/bin/env python3
"""Qualify static candidates using reused full PPL, PIQA, cache diagnostics and reload."""
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
from ptq_eval import aggregate_nll, evaluate_piqa, full_logits, score_targets
from ptq_experiment import load_candidate, quality_gate
from ptq_fake_quant import PTQAdapter
from ptq_storage import storage_inventory
from ptq_validate import assert_state_equal, parameter_fingerprints, probe_cache


def distribution_diagnostic(reference, candidate):
    """Fixed rows, all vocabulary; KL direction FP32 || candidate."""
    p = F.log_softmax(torch.as_tensor(reference).double(), dim=-1)
    q = F.log_softmax(torch.as_tensor(candidate).double(), dim=-1)
    return {'rows': len(reference), 'vocabulary': reference.shape[-1],
        'top1_agreement': float((reference.argmax(-1)==candidate.argmax(-1)).mean()),
        'mean_kl_fp32_to_candidate': float((p.exp()*(p-q)).sum(-1).mean())}


@torch.inference_mode()
def focused_contracts(adapter, records):
    """Changed static configurations: disabled/native, full/cache, native KV append."""
    source = parameter_fingerprints(adapter.model)
    before = adapter.qparam_state(); details=[]
    for prefill, length in ((32,96),(448,512)):
        ids=records[0]['input_ids'][:length]
        adapter.set_mode('disabled')
        with adapter.native(): native=full_logits(adapter.model,ids).numpy()
        disabled=full_logits(adapter.model,ids).numpy()
        full_check=compare_logits(disabled,native)
        cached=cached_logits(adapter.model,ids,prefill)
        cache_check=compare_logits(cached,native)
        del native,disabled,cached
        adapter.set_mode('quantize')
        probe=probe_cache(adapter,ids,prefill)
        details.append({'prefill':prefill,'length':length,'disabled_full':full_check,
            'disabled_cache':cache_check,'quantized_cache_probe':probe})
    assert_state_equal(before,adapter)
    if parameter_fingerprints(adapter.model)!=source:
        raise ValueError('Source Parameters changed')
    return {'source_weights_unchanged':True,'static_state_unchanged':True,'cases':details}


@torch.inference_mode()
def candidate_cache(adapter, records, cases):
    details=[]
    for case in cases:
        record=records[case['selection_index']]
        for regime in case['regimes']:
            prefill,decode=regime['prefill'],regime['decode']; ids=record['input_ids'][:regime['input_length']]
            if len(ids)!=prefill+decode: raise ValueError('Cache split mismatch')
            rows=sorted(set([0,prefill-1,prefill,len(ids)-2,len(ids)-1]))
            with adapter.native(): reference=full_logits(adapter.model,ids)[rows].numpy().copy()
            full=full_logits(adapter.model,ids).numpy()
            cached=cached_logits(adapter.model,ids,prefill)
            if not np.isfinite(full).all() or not np.isfinite(cached).all(): raise ValueError('Nonfinite logits')
            nll,count=score_targets(cached,ids,prefill,prefill+decode)
            full_nll,_=score_targets(full,ids,prefill,prefill+decode)
            delta=np.abs(full-cached)
            details.append({'id':case['id'],**regime,'nll':nll,'tokens':count,'full_nll':full_nll,
                'diagnostic_rows':rows,'full_fp32':distribution_diagnostic(reference,full[rows]),
                'cache_fp32':distribution_diagnostic(reference,cached[rows]),
                'full_cache':{'elements':int(delta.size),'max_abs':float(delta.max()),
                    'mean_abs':float(delta.mean()),'row_top1_agreement':float((full.argmax(-1)==cached.argmax(-1)).mean())}})
            del full,cached,reference,delta
            print(f"FINAL CACHE {case['id']} prefill={prefill} targets={count}",flush=True)
    return {'regimes':{str(p):aggregate_nll([(r['nll'],r['tokens']) for r in details if r['prefill']==p])
                       for p in (32,448)},'runs':details}


@torch.inference_mode()
def greedy(model, tokenizer, prompts, max_new=64):
    details=[]
    for ids in prompts:
        cache=DynamicCache(); tokens=list(ids); generated=[]
        for step in range(min(max_new,512-len(tokens))):
            start=0 if step==0 else len(tokens)-1
            output=model(input_ids=torch.tensor([tokens[start:]]),attention_mask=torch.ones((1,len(tokens)),dtype=torch.long),
                position_ids=torch.arange(start,len(tokens)).unsqueeze(0),cache_position=torch.arange(start,len(tokens)),
                past_key_values=cache,use_cache=True)
            if not torch.isfinite(output.logits).all(): raise ValueError('Nonfinite greedy logits')
            next_id=int(output.logits[0,-1].argmax()); cache=output.past_key_values
            generated.append(next_id); tokens.append(next_id)
            if next_id==tokenizer.eos_token_id: break
        details.append({'prompt_ids':ids,'prompt_text':tokenizer.decode(ids),'generated_ids':generated,
            'generated_text':tokenizer.decode(generated),'total_tokens':len(tokens)})
    return details


@torch.inference_mode()
def run(args):
    configure_runtime(); started=time.monotonic()
    records=read_json(args.data_dir/'wikitext_selection.json')
    if not args.structural_only:
        reference=read_json(ROOT/'results/ptq/fp32.json')
        questions=read_json(args.data_dir/'piqa_selection.json')
        cases=read_json(args.data_dir/'cache_cases.json')
        ppl=read_json(args.ppl_result)
    model,tokenizer=load_model(source_snapshot(args.cache_dir,args.offline))
    adapter=load_candidate(model,read_json(args.config),args.qparams)
    if not args.structural_only:
        if (ppl['config']!=adapter.config or ppl['mode']!='ppl' or ppl['status']!='PASS'
            or ppl['qparams_sha256']!=hashlib.sha256(args.qparams.read_bytes()).hexdigest()):
            raise ValueError('PPL result does not match candidate config/qparams or completed full PPL mode')
        if ppl['ppl']['ppl']/reference['ppl']['ppl']>1.05: raise ValueError('Candidate failed PPL gate')
    report={'config':adapter.config,'environment':environment(),'heldout_evaluated':False,
        'structural_only':args.structural_only,'source_qparams':str(args.qparams)}
    if args.structural_only:
        report['contracts']=focused_contracts(adapter,records)
    else:
        report['ppl']=ppl['ppl']
        report['piqa']=evaluate_piqa(model,questions)
        report['cache']=candidate_cache(adapter,records,cases)
        report['quality_gate']=quality_gate(report['ppl']['ppl'],report['piqa']['accuracy'],reference)
        report['decode_gate']={key:{'ppl_ratio':r['ppl']/reference['cache']['regimes'][key]['ppl'],
            'pass':r['ppl']/reference['cache']['regimes'][key]['ppl']<=1.05} for key,r in report['cache']['regimes'].items()}
        report['kept']=report['quality_gate']['pass'] and all(r['pass'] for r in report['decode_gate'].values())
        prompts=[r['input_ids'][:32] for r in records[:2]]
        with adapter.native(): report['greedy_fp32']=greedy(model,tokenizer,prompts)
        report['greedy_candidate']=greedy(model,tokenizer,prompts)
    report['storage']=storage_inventory(model,adapter)
    args.candidate_dir.mkdir(parents=True,exist_ok=True)
    adapter.save_qparams(args.candidate_dir/'qparams.safetensors')
    write_json(args.candidate_dir/'config.json',adapter.config)
    expected=full_logits(model,records[0]['input_ids'][:96]).numpy().copy()
    expected_cache=cached_logits(model,records[0]['input_ids'][:96],32)
    config=adapter.config; adapter.restore(); del adapter
    loaded=PTQAdapter(model,read_json(args.candidate_dir/'config.json'))
    loaded.load_qparams(args.candidate_dir/'qparams.safetensors'); loaded.set_mode('quantize')
    actual=full_logits(model,records[0]['input_ids'][:96]).numpy()
    actual_cache=cached_logits(model,records[0]['input_ids'][:96],32)
    if not np.array_equal(actual,expected) or not np.array_equal(actual_cache,expected_cache):
        raise ValueError('Reload full/cache did not reproduce bitwise')
    report['reload']={'full_bitwise_equal':True,'cache_bitwise_equal':True,'length':96,'prefill':32}
    report['status']='PASS'; report['seconds']=round(time.monotonic()-started,3)
    write_json(args.output,report)
    print(f"PASS finalize {config['name']}: kept={report.get('kept')}, seconds={report['seconds']}",flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',type=Path,required=True); p.add_argument('--qparams',type=Path,required=True)
    p.add_argument('--ppl-result',type=Path); p.add_argument('--structural-only',action='store_true')
    p.add_argument('--candidate-dir',type=Path,required=True); p.add_argument('--output',type=Path,required=True)
    p.add_argument('--data-dir',type=Path,default=ROOT/'data');p.add_argument('--cache-dir',type=Path,default=ROOT/'.cache/huggingface')
    p.add_argument('--offline',action='store_true');args=p.parse_args()
    if not args.structural_only and args.ppl_result is None:p.error('--ppl-result required for quality qualification')
    run(args)


if __name__=='__main__': main()
