#!/usr/bin/env python3
"""Đo FP32 trên tập chọn PTQ; không mở tập để dành."""
import argparse
from pathlib import Path
import time

from fp32_reference import (ROOT, MODEL_ID, REVISION, ATOL, RTOL, configure_runtime,
                            environment, source_snapshot, load_model, read_json, write_json)
from ptq_eval import evaluate_ppl, evaluate_piqa, evaluate_cache, check_transformers_loss


def run_fp32(args):
    configure_runtime()
    model, _ = load_model(source_snapshot(args.cache_dir, args.offline))
    selection = read_json(args.data_dir / "wikitext_selection.json")
    questions = read_json(args.data_dir / "piqa_selection.json")
    cases = read_json(args.data_dir / "cache_cases.json")
    started = time.monotonic()
    report = {"model_id": MODEL_ID, "revision": REVISION, "candidate": "fp32",
              "environment": environment(), "batch": 1, "padding": False,
              "length": 512, "atol": ATOL, "rtol": RTOL, "heldout_evaluated": False,
              "thresholds": {"relative_ppl_increase_max": 0.05, "accuracy_drop_max": 0.02},
              "scoring": {"ppl": "sum NLL / sum targets, then exp; skip window token 0",
                          "piqa": "sum answer LL, tie choice0, no length normalization",
                          "decode": "64 targets including first after prompt"}}
    report["loss_check"] = check_transformers_loss(model, selection[0]["input_ids"])
    report["ppl"] = evaluate_ppl(model, selection)
    report["cache"] = evaluate_cache(model, selection, cases)
    report["piqa"] = evaluate_piqa(model, questions)
    report["seconds"] = round(time.monotonic() - started, 3)
    report["status"] = "PASS"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_json(args.output, report)
    print(f"PASS fp32: PPL={report['ppl']['ppl']:.6f}; "
          f"PIQA={report['piqa']['correct']}/{report['piqa']['questions']}; "
          f"decode targets={report['cache']['tokens']}; seconds={report['seconds']}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["fp32"])
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    parser.add_argument("--cache-dir", type=Path, default=ROOT / ".cache/huggingface")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--output", type=Path, default=ROOT / "results/ptq/fp32.json")
    run_fp32(parser.parse_args())


if __name__ == "__main__":
    main()
