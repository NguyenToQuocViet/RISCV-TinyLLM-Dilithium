#!/usr/bin/env python3
"""Thử PTQ trên quick/full selection bằng scorer chung; không mở heldout."""
import argparse
import hashlib
from pathlib import Path
import time

import torch

from fp32_reference import ROOT, configure_runtime, environment, load_model, read_json, source_snapshot, write_json
from ptq_eval import aggregate_nll, evaluate_ppl, evaluate_piqa
from ptq_fake_quant import PTQAdapter


def load_candidate(model, config, base_params):
    """A tĩnh/K/V dùng stats train; A động bỏ A đã lưu; W tính lại từ nguồn."""
    adapter = PTQAdapter(model, config)
    adapter.load_qparams(base_params, recompute_weights=True,
                        load_static_for_dynamic=config["activation_policy"] == "dynamic_per_token")
    adapter.set_mode("quantize")
    return adapter


def quality_gate(ppl, accuracy, reference):
    ratio = ppl / reference["ppl"]["ppl"]
    drop = reference["piqa"]["accuracy"] - accuracy
    return {"ppl_ratio": ratio, "accuracy_drop": drop, "ppl_pass": ratio <= 1.05,
            "accuracy_pass": drop <= .02, "pass": ratio <= 1.05 and drop <= .02}


@torch.inference_mode()
def run(args):
    configure_runtime()
    records = read_json(args.data_dir / "wikitext_selection.json")
    reference = read_json(ROOT / "results/ptq/fp32.json")
    questions = read_json(args.data_dir / "piqa_selection.json") if args.mode == "full" else None
    model, _ = load_model(source_snapshot(args.cache_dir, args.offline))
    config = read_json(args.config)
    adapter = load_candidate(model, config, args.qparams)
    started = time.monotonic()
    selected = records[:1] if args.mode == "diagnose" else records[:8] if args.mode == "quick" else records
    report = {"config": adapter.config, "environment": environment(), "mode": args.mode,
              "selection_ids": [r["id"] for r in selected], "heldout_evaluated": False,
              "source_qparams": str(args.qparams),
              "loaded_static_groups": ["W", "K", "V"] if config["activation_policy"] == "dynamic_per_token" else ["W", "A", "K", "V"],
              "qparams_sha256": hashlib.sha256(args.qparams.read_bytes()).hexdigest()}
    diagnostics = {}
    if args.mode == "diagnose":
        for name, point in adapter.points.items():
            if point.kind != "A":
                continue
            scale = point.fq.scale
            diagnostics[name] = {"elements": 0, "clipped": 0, "zeroed_nonzero": 0,
                                 "scale": (float(scale.item()) if scale.numel() == 1 else
                                           {"count": scale.numel(), "min": float(scale.min()), "max": float(scale.max())}),
                                 "max_abs_input": 0.0}
            def capture(value, result, *, _name=name, _point=point):
                row = diagnostics[_name]
                row["elements"] += value.numel()
                if adapter.config["activation_policy"] == "dynamic_per_token":
                    runtime = (value.abs().amax(dim=-1, keepdim=True) / _point.fq.quant_max).clamp_min(torch.finfo(torch.float32).eps)
                    bound = runtime * _point.fq.quant_max
                    row["runtime_scale_min"] = min(row.get("runtime_scale_min", float("inf")), float(runtime.min()))
                    row["runtime_scale_max"] = max(row.get("runtime_scale_max", 0.0), float(runtime.max()))
                else:
                    shape = [1] * value.ndim
                    if _point.axis is not None:
                        shape[_point.axis] = _point.channels
                    bound = _point.fq.scale.reshape(shape) * _point.fq.quant_max
                row["clipped"] += int((value.abs() > bound).sum())
                row["zeroed_nonzero"] += int(((result == 0) & (value != 0)).sum())
                row["max_abs_input"] = max(row["max_abs_input"], float(value.abs().max()))
            point.capture = capture
    report["ppl"] = evaluate_ppl(model, selected)
    if diagnostics:
        report["activation_diagnostics"] = diagnostics
    if args.mode in ("quick", "diagnose"):
        ref_rows = reference["ppl"]["per_window"][:len(selected)]
        report["fp32_quick"] = aggregate_nll([(r["nll"], r["tokens"]) for r in ref_rows])
        report["ppl_ratio"] = report["ppl"]["ppl"] / report["fp32_quick"]["ppl"]
        report["diagnostic_only"] = True
    elif args.mode == "full":
        report["piqa"] = evaluate_piqa(model, questions)
        report["quality_gate"] = quality_gate(report["ppl"]["ppl"], report["piqa"]["accuracy"], reference)
        args.candidate_dir.mkdir(parents=True, exist_ok=True)
        write_json(args.candidate_dir / "config.json", adapter.config)
        adapter.save_qparams(args.candidate_dir / "qparams.safetensors")
    if args.mode == "ppl":
        report["ppl_ratio"] = report["ppl"]["ppl"] / reference["ppl"]["ppl"]
        report["ppl_pass"] = report["ppl_ratio"] <= 1.05
        report["diagnostic_only"] = False
        report["quality_complete"] = False
    report["seconds"] = round(time.monotonic() - started, 3)
    report["status"] = "PASS"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_json(args.output, report)
    suffix = f"ratio={report['ppl_ratio']:.6f}" if args.mode in ("quick", "diagnose", "ppl") else f"PIQA={report['piqa']['accuracy']:.6f}, quality={report['quality_gate']}"
    print(f"PASS {config['name']} {args.mode}: PPL={report['ppl']['ppl']:.9f}, {suffix}, seconds={report['seconds']}", flush=True)
    adapter.restore()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["quick", "diagnose", "ppl", "full"])
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--candidate-dir", type=Path, default=ROOT / "candidates/current")
    parser.add_argument("--qparams", type=Path, default=ROOT / "calibration/w8a8kv8_static/qparams.safetensors")
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    parser.add_argument("--cache-dir", type=Path, default=ROOT / ".cache/huggingface")
    parser.add_argument("--offline", action="store_true")
    run(parser.parse_args())


if __name__ == "__main__":
    main()
