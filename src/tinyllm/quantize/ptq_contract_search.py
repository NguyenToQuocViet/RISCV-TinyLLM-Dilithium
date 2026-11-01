#!/usr/bin/env python3
"""Prepare and score one numerical-contract candidate from serialized artifacts."""
import argparse
from copy import deepcopy
import gc
import math
import os
from pathlib import Path
import sys
import time

import numpy as np
import torch
from safetensors.torch import load_file, save_file
from transformers import AutoTokenizer

from fp32_reference import (ROOT, configure_runtime, environment, load_model,
                            read_json, source_snapshot, write_json)
from ptq_eval import aggregate_nll, choose_answer, full_logits, score_targets
from ptq_finalize import distribution_diagnostic, greedy
from ptq_fake_quant import PTQAdapter
from ptq_intermediate_calibrate import full_signed_range
from ptq_contract import (ContractAdapter, Format, compile_silu, encode,
                          encode_multiplier, rope_rom, rms_seed_lut,
                          round_divide_scalar, softmax_lut)
from ptq_contract_runtime import load_prepared_contract

_SCALE_RESCALE_SUFFIXES = (".smooth", ".output", ".to_v_cache", ".to_residual",
                           ".align_input", ".left_to_guard", ".right_to_guard",
                           ".q_rope_to_qk", ".k_rope_to_cache", ".qk_to_score",
                           ".pv_to_context", ".product")
FACTOR_CANDIDATE_NAMES = (
    "residual_w20", "residual_w18", "residual_w16",
    "boundary_context_w12", "boundary_context_w8",
    "boundary_embedding_w12", "boundary_embedding_w8",
    "boundary_gate_up_w12", "boundary_gate_up_w8",
    "boundary_k_pre_w12", "boundary_k_pre_w8",
    "boundary_logits_w12", "boundary_logits_w8",
    "boundary_norm_w12", "boundary_norm_w8",
    "boundary_product_w12", "boundary_product_w8",
    "boundary_q_post_w12", "boundary_q_post_w8",
    "boundary_q_pre_w12", "boundary_q_pre_w8",
    "boundary_residual_branch_w12", "boundary_residual_branch_w8",
    "boundary_score_w12", "boundary_score_w8",
    "boundary_silu_w12", "boundary_silu_w8", "scale_rescale_m16",
)
COMBINED_CANDIDATE = "combined_min_1pct_residual16_m16"
FULL_PPL_REFERENCE = 22.574714201210707
CACHE_PPL_REFERENCES = {"32": 26.676072498453824, "448": 12.019438254052904}
FULL_PPL_LIMIT = FULL_PPL_REFERENCE * 1.05
CACHE_PPL_LIMITS = {key: value * 1.05 for key, value in CACHE_PPL_REFERENCES.items()}
PIQA_MINIMUM_CORRECT = 607


def diagnostic_row_indices(prefill, length):
    """Fixed full-vocabulary diagnostic positions for one cache case."""
    if not 1 <= prefill < length <= 512:
        raise ValueError("diagnostic cache lengths are outside the frozen protocol")
    return sorted(set((0, prefill-1, prefill, length-2, length-1)))


def qualification_gates(ppl, piqa_correct, cache_regimes, reference_ppl):
    """Apply the frozen PPL, PIQA-count, and cache PPL limits."""
    if not 0 <= piqa_correct <= 919:
        raise ValueError("PIQA correct count is outside the fixed 919-question set")
    if set(cache_regimes) != set(CACHE_PPL_LIMITS):
        raise ValueError("both fixed cache regimes are required")
    ppl_ratio = ppl / reference_ppl
    cache = {}
    for regime, limit in CACHE_PPL_LIMITS.items():
        reference = CACHE_PPL_REFERENCES[regime]
        ratio = cache_regimes[regime]["ppl"] / reference
        cache[regime] = {"ppl": cache_regimes[regime]["ppl"],
                         "fp32_ppl": reference, "limit": limit,
                         "ratio_to_fp32": ratio, "pass": ratio <= 1.05}
    piqa_drop = 625 / 919 - piqa_correct / 919
    return {"ppl": {"ppl": ppl, "fp32_ppl": reference_ppl,
                     "limit": reference_ppl * 1.05,
                     "ratio_to_fp32": ppl_ratio, "pass": ppl_ratio <= 1.05},
            "piqa": {"correct": piqa_correct, "questions": 919,
                     "minimum_correct": PIQA_MINIMUM_CORRECT,
                     "accuracy_drop_vs_fp32": piqa_drop,
                     "pass": piqa_correct >= PIQA_MINIMUM_CORRECT},
            "cache": cache,
            "pass": (ppl_ratio <= 1.05 and piqa_correct >= PIQA_MINIMUM_CORRECT
                     and all(item["pass"] for item in cache.values()))}


def prepare_fp32_diagnostic_rows(args):
    """Save only the fixed full-vocabulary FP32 rows needed for cache diagnostics."""
    output = Path(args.output_dir)
    path = output/"qualification_fp32_rows.safetensors"
    report_path = output/"campaign.json"
    report = read_json(report_path)
    if report.get("stages", {}).get("combined_qualification") == "complete":
        return
    full = report.get("combined_full_ppl_result", {}).get("full_ppl", {})
    if full.get("status") != "complete" or full.get("windows") != 64 or full.get("tokens") != 32704:
        raise RuntimeError("the fixed candidate must complete Full64 before diagnostics")
    if full["ppl"] / FULL_PPL_REFERENCE > 1.05:
        raise RuntimeError("Full64 failed the PPL gate; FP32 diagnostics are skipped")
    old = report.get("diagnostic_reference", {})
    if old.get("status") == "complete" and path.is_file():
        report.setdefault("stages", {})["diagnostic_reference"] = "measured"
        atomic_json(report_path, report)
        return

    selection = read_json(ROOT/"data/wikitext_selection.json")
    cases = read_json(ROOT/"data/cache_cases.json")
    if len(cases) != 8 or len(selection) < 8:
        raise RuntimeError("diagnostic selectors do not match the fixed 8-case protocol")
    report["diagnostic_reference"] = {"status": "in_progress", "rows": 0,
                                      "cases": [], "path": path.name}
    atomic_json(report_path, report)
    model, _ = load_model(source_snapshot(args.cache_dir, args.offline))
    tensors = {}
    case_rows = []
    with torch.inference_mode():
        for case_index, case in enumerate(cases):
            record = selection[case["selection_index"]]
            for regime in case["regimes"]:
                prefill, length = regime["prefill"], regime["input_length"]
                ids = record["input_ids"][:length]
                rows = diagnostic_row_indices(prefill, len(ids))
                logits = full_logits(model, ids)
                if not torch.isfinite(logits[rows]).all():
                    raise ValueError(f"nonfinite FP32 diagnostic logits: {case['id']} prefill={prefill}")
                key = f"case_{case_index}_{prefill}"
                tensors[key] = logits[rows].detach().cpu().contiguous()
                case_rows.append({"id": case["id"], "prefill": prefill,
                                  "length": len(ids), "rows": rows,
                                  "key": key, "vocabulary": int(logits.shape[-1])})
                del logits
                print(f"FP32 DIAGNOSTIC {len(case_rows)}/16 {case['id']} prefill={prefill}", flush=True)
    del model
    gc.collect()
    if len(case_rows) != 16 or sum(item["rows"] and len(item["rows"]) for item in case_rows) != 80:
        raise RuntimeError("fixed FP32 diagnostic row coverage is incomplete")
    temporary = path.with_suffix(".tmp")
    save_file(tensors, str(temporary))
    temporary.replace(path)
    report = read_json(report_path)
    report["diagnostic_reference"] = {"status": "complete", "rows": 80,
        "cases": case_rows, "path": path.name,
        "backend": "fp32_reference deterministic CPU FP32, eager attention, one intra-op thread",
        "model_loaded_separately_from_candidate": True}
    report.setdefault("stages", {})["diagnostic_reference"] = "measured"
    atomic_json(report_path, report)
    print("FP32 DIAGNOSTIC reference rows prepared: 80", flush=True)

def atomic_json(path, value):
    temporary = path.with_suffix(".tmp")
    write_json(temporary, value)
    temporary.replace(path)



def shift_container(shift):
    shift = torch.as_tensor(shift, dtype=torch.int64)
    low, high = int(shift.min()), int(shift.max())
    if low < -32768 or high > 32767:
        raise OverflowError("multiplier shift does not fit INT16")
    return shift.to(torch.int8 if low >= -128 and high <= 127 else torch.int16).contiguous()



def integer_code_bounds(bits, signed=True):
    if bits < 1:
        raise ValueError("integer format must have at least one bit")
    if signed:
        return -(1 << (bits - 1)), (1 << (bits - 1)) - 1
    return 0, (1 << bits) - 1



def dot_product_code_bounds(lhs_bounds, rhs_bounds, terms):
    if terms < 1:
        raise ValueError("dot product must contain at least one term")
    products = [lhs * rhs for lhs in lhs_bounds for rhs in rhs_bounds]
    return min(products) * terms, max(products) * terms



def minimum_signed_width(minimum, maximum):
    if minimum > maximum:
        raise ValueError("invalid integer range")
    width = 1
    while minimum < -(1 << (width - 1)) or maximum > (1 << (width - 1)) - 1:
        width += 1
    return width



def require_prepared_candidates(report, names_key, expected_count, maximum, label):
    """Refuse to advance a stage when candidate preparation is incomplete."""
    screening = report.get("screening", {})
    names = screening.get(names_key)
    artifacts = report.get("prepared_candidate_artifacts", {})
    if not isinstance(names, list) or len(names) != expected_count or len(set(names)) != len(names):
        raise RuntimeError(f"{label} candidate preparation is incomplete or duplicated")
    allocated = set(artifacts) | set(screening.get("candidates", {}))
    if len(allocated) > maximum:
        raise RuntimeError(f"{label} candidate budget exceeded")
    missing = [name for name in names if name not in artifacts]
    if missing:
        raise RuntimeError(f"{label} candidate artifact is missing: {missing[0]}")
    return names



def require_completed_quick_batch(report, names, expected_windows=8, expected_ids=None):
    """Check each allocated Quick8 candidate before marking its stage complete."""
    candidates = report.get("screening", {}).get("candidates", {})
    for name in names:
        quick = candidates.get(name, {}).get("quick", {})
        windows = quick.get("per_window", [])
        ids = [row.get("id") for row in windows]
        if (quick.get("status") != "complete" or len(windows) != expected_windows
                or len(set(ids)) != expected_windows
                or (expected_ids is not None and ids != list(expected_ids))):
            raise RuntimeError(f"{name}: Quick{expected_windows} candidate screen is incomplete")


def require_completed_factor_quick(report, expected_ids):
    """Accept pruned factor artifacts only when the recorded 28-case screen is complete."""
    screening = report.get("screening", {})
    names = screening.get("initial_candidates")
    if (names != list(FACTOR_CANDIDATE_NAMES)
            or screening.get("initial_candidate_count") != len(FACTOR_CANDIDATE_NAMES)):
        raise RuntimeError("the completed factor screen has an unexpected candidate set")
    artifacts = report.get("prepared_candidate_artifacts", {})
    allocated = set(artifacts) | set(screening.get("candidates", {}))
    if len(allocated) > 35:
        raise RuntimeError("factor Quick8 hard budget exceeded")
    require_completed_quick_batch(report, names, expected_ids=expected_ids)
    candidates = screening.get("candidates", {})
    for name in names:
        quick = candidates[name]["quick"]
        rows = quick["per_window"]
        if (quick.get("windows") != 8 or quick.get("tokens") != 8*511
                or any(item.get("tokens") != 511 for item in rows)):
            raise RuntimeError(f"{name}: factor Quick8 target coverage changed")
    return names


@torch.inference_mode()
def prepare_shared_weights(baseline, output_dir):
    """Write shared frozen-FQ INT8 codes only when absent from the output directory."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    weights_path = output_dir/"weights.safetensors"
    if weights_path.is_file():
        return weights_path
    weights = {}
    for weight_name in baseline.weights:
        fmt = Format(8, baseline.points[weight_name].fq.scale.double().tolist(), 0)
        prepared = baseline.points[weight_name](baseline.effective_weight(weight_name))
        weights[weight_name] = encode(prepared, fmt)[0].to(torch.int8).contiguous()
    temporary = weights_path.with_suffix(".tmp")
    try:
        save_file(weights, str(temporary), metadata={
            "preparation":"pinned full-signed frozen PyTorch FQ; recover exact integer codes",
            "shared_embedding_lm_head":"one tensor"})
        temporary.replace(weights_path)
    finally:
        if temporary.exists():
            temporary.unlink()
    return weights_path



def _workspace_path(path):
    path = Path(path).resolve()
    try:
        return path.relative_to(ROOT.parents[2].resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def reproduction_protocol(shared_weights=None):
    if shared_weights is None:
        shared_weights = ROOT/"results/numerical/contract_improvement/weights.safetensors"
    return {"heldout_used":False,
        "inputs":{"full_and_quick_ppl":"src/tinyllm/quantize/data/wikitext_selection.json",
            "piqa":"src/tinyllm/quantize/data/piqa_selection.json",
            "cache":"src/tinyllm/quantize/data/cache_cases.json",
            "fp32_references":"src/tinyllm/quantize/results/ptq/fp32.json",
            "combined_high_comparison":"src/tinyllm/quantize/results/numerical/contract_search/campaign.json",
            "combined_high_configuration":"src/tinyllm/quantize/results/numerical/contract_search/combined_high/config.json",
            "calibration":"src/tinyllm/quantize/results/numerical/intermediate_calibration.json",
            "frozen_w8a12kv8_qparams":"src/tinyllm/quantize/candidates/w8a12kv8_smoothquant/qparams.safetensors",
            "shared_integer_weights":_workspace_path(shared_weights)},
        "selectors":{"quick":"first 8 full selection windows, 512 input tokens each",
            "full_ppl":"all 64 full selection windows, 32704 targets",
            "piqa":"all 919 selection questions",
            "cache":"all 16 selection runs, 8 per each 32/448 prefill regime",
            "greedy":"first two selection prompts, first 32 tokens, up to 32 generated tokens"},
        "quality_gates":{"full_ppl_relative_to_fp32_max":0.05,
            "piqa_accuracy_drop_max":0.02,"cache_ppl_relative_to_fp32_max":0.05},
        "quick_role":"screening and shortlist ranking only; not a quality gate"}



def record_successful_cli(report_path, phase, argv=None):
    """Keep one concise successful invocation per reproducible campaign phase."""
    report_path = Path(report_path)
    report = read_json(report_path)
    result = {"argv":list(argv if argv is not None else sys.orig_argv),
        "working_directory":Path.cwd().as_posix(),"exit_status":0}
    report.setdefault("cli_results", {})[phase] = result
    report.setdefault("reproduction", reproduction_protocol(report_path.parent/"weights.safetensors"))
    atomic_json(report_path, report)


def record_failed_cli(report_path, phase, error, argv=None):
    """Retain a failed stage invocation while preserving its partial checkpoint."""
    report_path = Path(report_path)
    report = read_json(report_path)
    report.setdefault("cli_failures", []).append({
        "phase": phase,
        "argv": list(argv if argv is not None else sys.orig_argv),
        "working_directory": Path.cwd().as_posix(),
        "exit_status": 1,
        "error": f"{type(error).__name__}: {error}"})
    atomic_json(report_path, report)



def coefficient_precision(name, scale_rescale_bits, nonlinear_bits):
    """Select precision only for approved interface rescalers."""
    if scale_rescale_bits not in (16,24) or nonlinear_bits != 24:
        raise ValueError("only rescale M16/M24 and frozen nonlinear M24 are supported")
    return scale_rescale_bits if name.endswith(_SCALE_RESCALE_SUFFIXES) else nonlinear_bits



def profile_artifact_runtime(output_dir, thread_counts=(1, 2, 4, 8)):
    """Measure artifact load, cold/warm model, and scorer time independently."""
    output_dir = Path(output_dir)
    config_path = output_dir/"artifacts/combined_high/config.json"
    if not config_path.is_file():
        raise FileNotFoundError(f"prepared combined_high artifact not found: {config_path}")
    records = read_json(ROOT/"data/wikitext_selection.json")
    ids = records[0]["input_ids"][:512]
    if len(ids) != 512:
        raise ValueError("thread profile requires a complete 512-token selection window")
    try:
        torch.set_num_interop_threads(1)
    except RuntimeError as exc:
        raise RuntimeError("profile must start in a fresh process to fix inter-op threads at one") from exc
    rows = []
    reference_codes = None
    scores = []
    for threads in thread_counts:
        torch.set_num_threads(int(threads))
        started = time.monotonic()
        runtime = load_prepared_contract(config_path)
        load_seconds = time.monotonic()-started
        times, score_seconds, score = [], None, None
        with torch.inference_mode():
            for repetition in range(3):
                forward_started = time.monotonic()
                output = runtime(input_ids=torch.tensor([ids], dtype=torch.long),
                                 attention_mask=torch.ones((1, len(ids)), dtype=torch.long))
                elapsed = time.monotonic()-forward_started
                if reference_codes is None:
                    reference_codes = output.logit_codes[0].clone()
                elif not torch.equal(reference_codes, output.logit_codes[0]):
                    raise AssertionError(f"artifact logit codes changed at intra-op threads={threads}, repetition={repetition}")
                if repetition == 0:
                    cold_seconds = elapsed
                else:
                    times.append(elapsed)
                if repetition == 2:
                    scorer_started = time.monotonic()
                    score = score_targets(output.logits[0], ids)
                    score_seconds = time.monotonic()-scorer_started
                del output
        row = {"threads":int(threads),"interop_threads":1,"runtime_backend":"PyTorch CPU FP64 exact-code GEMM",
               "artifact_load_seconds":load_seconds,"cold_forward_seconds":cold_seconds,
               "warmed_forward_seconds":times,"warmed_forward_median_seconds":float(np.median(times)),
               "scorer_seconds":score_seconds,"scorer_nll":score[0],"scorer_targets":score[1],
               "code_equal_to_first_thread":True}
        rows.append(row); scores.append(score)
        print(f"PROFILE threads={threads} load={load_seconds:.3f}s cold={cold_seconds:.3f}s "
              f"warm_median={row['warmed_forward_median_seconds']:.3f}s scorer={score_seconds:.3f}s",flush=True)
        del runtime
        import gc
        gc.collect()
    if any(not math.isclose(score[0], scores[0][0], rel_tol=0, abs_tol=1e-9) for score in scores):
        raise AssertionError("scorer NLL changed across the tested CPU thread counts")
    selected = min(rows, key=lambda row:row["warmed_forward_median_seconds"])["threads"]
    return {"status":"measured","selector":"selection window 0; all 512 input tokens",
            "thread_counts":[int(v) for v in thread_counts],"selected_threads":selected,
            "code_shape":list(reference_codes.shape),"score_comparison":"same NLL within 1e-9 across thread counts",
            "runs":rows}



def minimum_width_selection(factor_candidates, families, threshold=0.01):
    """Choose the least tested boundary width whose measured Quick PPL rise is <= threshold."""
    selected = {}
    for family in sorted(families):
        trials = []
        for bits in (8, 12):
            name = f"boundary_{family}_w{bits}"
            entry = factor_candidates.get(name)
            if entry is None:
                raise RuntimeError(f"{name}: required factor Quick8 evidence is missing")
            quick = entry.get("quick", {})
            delta = quick.get("delta_mean_nll_vs_combined_high")
            if quick.get("status") != "complete" or not isinstance(delta, (int, float)) or not math.isfinite(delta):
                raise RuntimeError(f"{name}: completed factor Quick8 evidence is missing")
            relative_ppl = math.expm1(delta)
            trials.append({"candidate": name, "bits": bits, "delta_mean_nll": delta,
                           "relative_ppl_increase": relative_ppl,
                           "within_one_percent": relative_ppl <= threshold})
        passing = [trial for trial in trials if trial["within_one_percent"]]
        chosen = min(passing, key=lambda trial: trial["bits"]) if passing else None
        selected[family] = {"selected_bits": chosen["bits"] if chosen else None,
                            "selected_candidate": chosen["candidate"] if chosen else None,
                            "tested": trials,
                            "fallback": None if chosen else "retain combined_high width; no tested width passed"}
    return selected


def build_combined_candidate_config(base, inventory, factor_candidates, threshold=0.01):
    """Apply measured boundary choices and explicit fixed widths to a fresh candidate."""
    config = deepcopy(base)
    config.pop("formats", None)
    config["name"] = COMBINED_CANDIDATE
    config["points"] = deepcopy(base["points"])
    candidate_families = set(inventory.values()) - {"residual", "probability", "product", "residual_branch"}
    selected = minimum_width_selection(factor_candidates, candidate_families, threshold)
    for point, family in inventory.items():
        if family == "residual":
            config["points"][point] = {"bits": 16}
        elif family in ("product", "residual_branch"):
            config["points"][point] = {"bits": 16}
        elif family in selected and selected[family]["selected_bits"] is not None:
            config["points"][point] = {"bits": selected[family]["selected_bits"]}
    config["scale_rescale_bits"] = 16
    config["coefficient_bits"] = 24
    config["integer_coefficients"] = True
    config["metrics"] = False
    return config, selected


def main_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--cache-dir", type=Path, default=ROOT/".cache/huggingface")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--stage", choices=("profile", "artifact-prepare", "artifact-factor-quick",
        "artifact-prepare-combined",
        "artifact-baseline", "artifact-quick", "artifact-full",
        "artifact-prepare-diagnostics", "artifact-qualify"), required=True)
    parser.add_argument("--profile-threads", default="1,2,4,8")
    return parser


def main(argv=None):
    parser = main_parser()
    args = parser.parse_args(argv)
    args.output_dir_explicit = args.output_dir is not None
    if args.output_dir is None:
        args.output_dir = ROOT/"results/numerical/contract_improvement"
    if args.stage == "profile" or args.stage.startswith("artifact-"):
        if not args.output_dir_explicit:
            parser.error(f"--stage {args.stage} requires an explicit --output-dir")
    if args.stage == "profile":
        thread_counts = tuple(int(value) for value in args.profile_threads.split(","))
        if not thread_counts or any(value <= 0 for value in thread_counts):
            parser.error("--profile-threads must be comma-separated positive integers")
        args.output_dir.mkdir(parents=True, exist_ok=True)
        path = args.output_dir/"campaign.json"
        report = read_json(path) if path.exists() else {"stages": {}}
        report["performance"] = profile_artifact_runtime(args.output_dir, thread_counts)
        report.setdefault("stages", {})["profile"] = "measured"
        atomic_json(path, report)
        record_successful_cli(path, "profile")
        print(f"PROFILE selected intra-op threads={report['performance']['selected_threads']}", flush=True)
        return 0

    configure_runtime()
    if args.stage == "artifact-prepare":
        ArtifactCompiler(args).prepare_initial_artifacts()
        record_successful_cli(args.output_dir/"campaign.json", "artifact-prepare-factor-candidates")
        return 0
    if args.stage == "artifact-factor-quick":
        campaign = ArtifactCampaign(args)
        campaign.run_factor_quick()
        record_successful_cli(args.output_dir/"campaign.json", "artifact-factor-quick")
        return 0
    if args.stage == "artifact-prepare-combined":
        ArtifactCompiler(args).prepare_combined_candidate()
        record_successful_cli(args.output_dir/"campaign.json", "artifact-prepare-combined-candidate")
        return 0
    if args.stage == "artifact-prepare-diagnostics":
        try:
            prepare_fp32_diagnostic_rows(args)
        except Exception as exc:
            record_failed_cli(args.output_dir/"campaign.json", "artifact-prepare-diagnostics", exc)
            raise
        record_successful_cli(args.output_dir/"campaign.json", "artifact-prepare-diagnostics")
        return 0
    if args.stage in ("artifact-baseline", "artifact-quick", "artifact-full", "artifact-qualify"):
        campaign = ArtifactCampaign(args)
        if args.stage == "artifact-baseline":
            campaign.run_baseline()
            phase = "artifact-baseline"
        elif args.stage == "artifact-quick":
            try:
                campaign.run_combined_quick()
            except Exception as exc:
                record_failed_cli(args.output_dir/"campaign.json", "artifact-quick", exc)
                raise
            phase = "artifact-quick"
        elif args.stage == "artifact-full":
            campaign.run_combined_full_ppl()
            phase = "artifact-full-ppl"
        else:
            try:
                campaign.run_combined_qualification()
            except Exception as exc:
                record_failed_cli(args.output_dir/"campaign.json", "artifact-qualification", exc)
                raise
            phase = "artifact-qualification"
        record_successful_cli(args.output_dir/"campaign.json", phase)
        return 0
    parser.error(f"unsupported stage: {args.stage}")

class ArtifactCompiler:
    def __init__(self, args):
        self.args = args
        args.output_dir.mkdir(parents=True, exist_ok=True)
        self.path = args.output_dir/"campaign.json"
        self.report = read_json(self.path) if self.path.exists() else {
            "backend": "artifact_only_integer_code_execution; PyTorch CPU FP64 exact-code GEMM",
            "heldout_used": False, "seed": 1234, "threads": 1, "stages": {}}
        self.started = time.monotonic()
        self.selection = read_json(ROOT/"data/wikitext_selection.json")
        self.model, _ = load_model(source_snapshot(args.cache_dir, args.offline))
        candidate = ROOT/"candidates/w8a12kv8_smoothquant"
        self.baseline = PTQAdapter(self.model, read_json(candidate/"config.json"))
        self.baseline.load_qparams(candidate/"qparams.safetensors", recompute_weights=False)
        full_signed_range(self.baseline)
        self.baseline.set_mode("quantize")
        self.shared_weights = prepare_shared_weights(self.baseline, args.output_dir)
        self.statistics = read_json(ROOT/"results/numerical/intermediate_calibration.json")["points"]
        frozen_high = read_json(ROOT/"results/numerical/contract_search/combined_high/config.json")
        self.frozen_nonlinear = deepcopy(frozen_high["nonlinear"])
        self.frozen_silu_table = deepcopy(frozen_high["pwl_reference"])
        self.prepared_baseline_config = None
        self.prepared_baseline_coefficients = {}
        self._cache_prepared_baseline()
        self.adapter = ContractAdapter(self.model, self.baseline, self.statistics)
        self.report.setdefault("environment", environment())
        self.report["backend"] = "artifact_only_integer_code_execution; PyTorch CPU FP64 exact-code GEMM"
        prepared_weights = self.report.setdefault("prepared_weights", {})
        prepared_weights.update({
            "path":_workspace_path(self.shared_weights),
            "matrices":len(self.baseline.weights),
            "payload_bytes":sum(weight.numel() for weight in self.baseline.weights.values()),
            "preparation":"full-signed frozen baseline FQ codes; no FP64 source re-quantization",
        })
        self.report["reproduction"] = reproduction_protocol(self.shared_weights)

    def _refresh_prepared_weight_reference(self, config_path):
        config_path = Path(config_path)
        if not config_path.is_file():
            return
        config = read_json(config_path)
        relative = Path(os.path.relpath(self.shared_weights.resolve(), config_path.parent.resolve())).as_posix()
        if config.get("weights") != relative:
            config["weights"] = relative
            atomic_json(config_path, config)

    def _cache_prepared_baseline(self):
        config_path = self.args.output_dir/"artifacts/combined_high/config.json"
        if not config_path.is_file():
            return
        self.prepared_baseline_config = read_json(config_path)
        coefficients_path = config_path.parent/self.prepared_baseline_config["coefficients"]
        self.prepared_baseline_coefficients = load_file(str(coefficients_path),device="cpu")

    def save(self):
        self.report["last_session_seconds"] = round(time.monotonic()-self.started, 3)
        atomic_json(self.path, self.report)

    def prepare_artifact(self, config, output_dir, shared_weights):
        """Compile exact frozen scale ratios once, then serialize runtime inputs."""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        config = deepcopy(config)
        config.pop("formats", None)  # a width or policy edit must regenerate scales
        self.adapter.set_trial({**config, "metrics":False, "check_mac":False})
        formats = {name: fmt.dictionary() for name, fmt in self.adapter.formats.items()}
        bundle, coefficient_sources = {}, {}
        scale_bits = int(config.get("scale_rescale_bits", 24))
        nonlinear_bits = int(config.get("coefficient_bits", 24))
        if scale_bits not in (16, 24) or nonlinear_bits != 24:
            raise ValueError("this campaign permits scale M16/M24; nonlinear coefficient precision stays 24")
        frozen = self.frozen_nonlinear
        trial_nonlinear = config["nonlinear"]
        trial_rms = trial_nonlinear.get("rms", {})
        if (trial_rms.get("seed_entries", 64) != 64
                or trial_rms.get("t_fractional_bits", 40) != 40
                or trial_nonlinear.get("rope", {}).get("coefficient_bits") != frozen["rope"]["coefficient_bits"]
                or trial_nonlinear.get("softmax", {}) != frozen["softmax"]
                or trial_nonlinear.get("silu", {}) != frozen["silu"]):
            raise ValueError("only the combined_high nonlinear configuration is allowed in this campaign")

        use_frozen_artifacts = (config.get("name") != "combined_high"
                                and self.prepared_baseline_config is not None)
        reused_fixed_tensors = 0
        if use_frozen_artifacts:
            for name,value in self.prepared_baseline_coefficients.items():
                if (name.startswith(("rope.","softmax.","rms.")) or name.endswith(".epsilon")):
                    bundle[name] = value.clone()
                    reused_fixed_tensors += 1

        def coefficient(key, value):
            value = torch.as_tensor(value, dtype=torch.float64)
            coefficient_sources[key] = value.clone()
            bits = coefficient_precision(key, scale_bits, nonlinear_bits)
            multiplier, shift = encode_multiplier(value, bits)
            bundle[key+".M"] = multiplier.to(torch.int32).contiguous()
            bundle[key+".shift"] = shift_container(shift)

        rope_bits = config["nonlinear"]["rope"]["coefficient_bits"]
        if not use_frozen_artifacts:
            cosine, sine = rope_rom(rope_bits)
            bundle["rope.cos"] = cosine.to(torch.int8 if rope_bits == 8 else torch.int16)
            bundle["rope.sin"] = sine.to(torch.int8 if rope_bits == 8 else torch.int16)
        softmax = config["nonlinear"]["softmax"]
        if not use_frozen_artifacts:
            bundle["softmax.exp_lut"] = softmax_lut(softmax["c"], softmax["entries"]).to(torch.uint8)
        rms_options = config["nonlinear"]["rms"]
        seed_entries = rms_options.get("seed_entries", 64)
        if not use_frozen_artifacts:
            bundle["rms.seed_lut"] = rms_seed_lut(seed_entries).to(torch.int16)
        table = deepcopy(self.frozen_silu_table)
        if config.get("pwl_reference") not in (None, table):
            raise ValueError("SiLU reference must match the frozen combined_high table")
        reused_silu_layers = 0
        recompiled_silu_layers = 0
        aligned_norms = {}
        incoming = {}
        for name, module in self.model.named_modules():
            if isinstance(module, torch.nn.Linear):
                activation_scale = self.baseline.points[name+".input"].fq.scale.double()
                smoothing = self.baseline.smooth_scales.get(name, torch.tensor(1.)).double()
                if name == "lm_head":
                    source = "model.norm.output"
                elif name.endswith(("q_proj", "k_proj", "v_proj")):
                    source = name.rsplit(".self_attn.", 1)[0]+".input_layernorm.output"
                elif name.endswith("o_proj"):
                    source = name.rsplit(".", 1)[0]+".context"
                elif name.endswith(("gate_proj", "up_proj")):
                    source = name.rsplit(".mlp.", 1)[0]+".post_attention_layernorm.output"
                else:
                    source = name.rsplit(".", 1)[0]+".gate_product"
                source_scale = torch.as_tensor(self.adapter.formats[source].scale, dtype=torch.float64)
                incoming[name] = source
                coefficient(name+".smooth", source_scale/(smoothing*activation_scale))
                weight_name = "shared_embedding_lm_head.weight" if name == "lm_head" else name+".weight"
                raw_scale = activation_scale*self.baseline.points[weight_name].fq.scale.double()
                if name+".output" in self.adapter.formats:
                    target_scale = torch.as_tensor(self.adapter.formats[name+".output"].scale, dtype=torch.float64)
                    coefficient(name+".output", raw_scale/target_scale)
                if name.endswith("v_proj"):
                    cache_scale = self.baseline.points[name.removesuffix("v_proj")+"value_post_projection"].fq.scale.double().repeat_interleave(64)
                    coefficient(name+".to_v_cache", raw_scale/cache_scale)
            elif name.endswith(("input_layernorm", "post_attention_layernorm")) or name == "model.norm":
                if name == "model.norm":
                    source = f"model.layers.{len(self.model.model.layers)-1}.residual_after_ffn"
                elif name.endswith("post_attention_layernorm"):
                    source = name.removesuffix("post_attention_layernorm")+"residual_after_attention"
                else:
                    layer = int(name.split(".")[2])
                    source = "model.embed_tokens.output" if layer == 0 else f"model.layers.{layer-1}.residual_after_ffn"
                fmt = self.adapter.formats[source]
                if fmt.axis is not None:
                    aligned = self.adapter.make_format(source, {"bits":24})
                    coefficient(name+".align_input", torch.as_tensor(fmt.scale, dtype=torch.float64)/float(aligned.scale))
                else:
                    aligned = fmt
                aligned_norms[name] = {"source":source, **aligned.dictionary()}
                delta = float(aligned.scale)
                ft = rms_options.get("t_fractional_bits", 40)
                coefficient(name+".to_t", delta*delta*(1 << ft)/int(self.model.config.hidden_size))
                coefficient(name+".gamma_output", module.weight.detach().double()*delta/float(self.adapter.formats[name+".output"].scale))
                epsilon = max(1, round(module.variance_epsilon*(1 << ft)))
                bundle[name+".epsilon"] = torch.tensor(epsilon, dtype=torch.int32)
        embedding_scale = self.baseline.points["shared_embedding_lm_head.weight"].fq.scale.double()
        coefficient("embedding.to_residual", embedding_scale/float(self.adapter.formats["model.embed_tokens.output"].scale))
        for index in range(len(self.model.model.layers)):
            prefix = f"model.layers.{index}.mlp"
            gate_format, silu_format = self.adapter.formats[prefix+".gate_proj.output"], self.adapter.formats[prefix+".silu_output"]
            baseline_formats = (self.prepared_baseline_config or {}).get("formats", {})
            gate_name, silu_name = prefix+".gate_proj.output", prefix+".silu_output"
            same_silu_scales = (use_frozen_artifacts
                and np.array_equal(np.asarray(formats[gate_name]["scale"]),
                                   np.asarray(baseline_formats.get(gate_name,{}).get("scale")))
                and np.array_equal(np.asarray(formats[silu_name]["scale"]),
                                   np.asarray(baseline_formats.get(silu_name,{}).get("scale"))))
            pwl_fields = ("breakpoints","slopes","intercepts","shifts")
            positive_prefix = prefix+".pwl.positive"
            if same_silu_scales and all(prefix+".pwl."+field in self.prepared_baseline_coefficients
                                        for field in pwl_fields):
                for field in pwl_fields:
                    name = prefix+".pwl."+field
                    bundle[name] = self.prepared_baseline_coefficients[name].clone()
                for suffix in (".M",".shift"):
                    name = positive_prefix+suffix
                    bundle[name] = self.prepared_baseline_coefficients[name].clone()
                reused_silu_layers += 1
            else:
                pwl = compile_silu(gate_format.scale, silu_format, table, nonlinear_bits)
                for field, value in pwl.items():
                    bundle[prefix+".pwl."+field] = (shift_container(value) if field == "shifts"
                        else torch.tensor(value, dtype=torch.int32))
                coefficient(positive_prefix, float(gate_format.scale)/float(silu_format.scale))
                recompiled_silu_layers += 1
            coefficient(prefix+".product", float(silu_format.scale)*float(self.adapter.formats[prefix+".up_proj.output"].scale)/float(self.adapter.formats[prefix+".gate_product"].scale))
            attention = f"model.layers.{index}.self_attn"
            qpre = torch.as_tensor(self.adapter.formats[attention+".q_proj.output"].scale, dtype=torch.float64).reshape(int(self.model.config.num_attention_heads), -1)[:, 0]
            kpre = torch.as_tensor(self.adapter.formats[attention+".k_proj.output"].scale, dtype=torch.float64).reshape(3, -1)[:, 0]
            qpost = torch.as_tensor(self.adapter.formats[attention+".query_post_rope"].scale, dtype=torch.float64)
            kcache = self.baseline.points[attention+".key_post_rope"].fq.scale.double()
            vcache = self.baseline.points[attention+".value_post_projection"].fq.scale.double()
            score = torch.as_tensor(self.adapter.formats[attention+".score"].scale, dtype=torch.float64)
            coefficient(attention+".q_rope_to_qk", qpre/qpost)
            coefficient(attention+".k_rope_to_cache", kpre/kcache)
            coefficient(attention+".qk_to_score", qpost*kcache.repeat_interleave(3)/8/score)
            coefficient(attention+".score_to_index", score*(softmax["entries"]-1)/softmax["c"])
            probability_denominator = (1 << softmax["probability_bits"])-1
            coefficient(attention+".pv_to_context", vcache.repeat_interleave(3)/probability_denominator/float(self.adapter.formats[attention+".context"].scale))
            layer = f"model.layers.{index}"
            for target, left, right in (
                (layer+".residual_after_attention", "model.embed_tokens.output" if index == 0 else f"model.layers.{index-1}.residual_after_ffn", attention+".o_proj.output"),
                (layer+".residual_after_ffn", layer+".residual_after_attention", prefix+".down_proj.output")):
                target_scale = torch.as_tensor(self.adapter.formats[target].scale, dtype=torch.float64)
                coefficient(target+".left_to_guard", torch.as_tensor(self.adapter.formats[left].scale, dtype=torch.float64)/target_scale*(1 << 20))
                coefficient(target+".right_to_guard", torch.as_tensor(self.adapter.formats[right].scale, dtype=torch.float64)/target_scale*(1 << 20))
        model_config = self.model.config
        geometry = {"layers":len(self.model.model.layers), "hidden_size":int(model_config.hidden_size),
                    "intermediate_size":int(model_config.intermediate_size), "vocab_size":int(model_config.vocab_size),
                    "query_heads":int(model_config.num_attention_heads), "kv_heads":int(model_config.num_key_value_heads),
                    "head_dim":int(model_config.head_dim), "rope_theta":float(model_config.rope_theta),
                    "max_positions":512}
        if geometry != {"layers":30,"hidden_size":576,"intermediate_size":1536,
                        "vocab_size":49152,"query_heads":9,"kv_heads":3,
                        "head_dim":64,"rope_theta":100000.0,"max_positions":512}:
            raise ValueError(f"model geometry differs from the reviewed contract: {geometry}")
        prepared = {**config, "formats":formats, "model":geometry,
                    "artifact_format":"tinyllm_integer_contract_v1",
                    "scale_rescale_bits":scale_bits,
                    "scale_rescale_multiplier_keys":sorted(name for name in coefficient_sources if name.endswith(_SCALE_RESCALE_SUFFIXES)),
                    "nonlinear_multiplier_bits":nonlinear_bits,
                    "weights":Path(os.path.relpath(Path(shared_weights).resolve(), output_dir.resolve())).as_posix(),
                    "coefficients":"coefficients.safetensors",
                    "linear_input_sources":incoming,"aligned_norm_inputs":aligned_norms,
                    "runtime_role":"artifact_only_integer_code_execution",
                    "runtime_loads_source_checkpoint":False,"runtime_loads_source_qparams":False,
                    "runtime_compiles_coefficients_or_tables":False,
                    "preparation_reuse":{"fixed_rope_softmax_rms_tensor_count":reused_fixed_tensors,
                        "frozen_silu_layers_reused":reused_silu_layers,
                        "frozen_silu_layers_recompiled_for_changed_boundary_scale":recompiled_silu_layers},
                    "nonlinear_contract":{"rms_t_fractional_bits":rms_options.get("t_fractional_bits",40),
                        "rms_m_fractional_bits":16,"rms_u_fractional_bits":14,
                        "rms_newton_steps":1,"residual_alignment_guard_bits":20}}
        for stale in ("frozen_source_qparams", "software_adapter_role", "software_adapter_loads_coefficient_bundle",
                      "coefficient_bundle_validation", "pwl_reference", "pwl_compiled"):
            prepared.pop(stale, None)
        save_file(bundle, str(output_dir/"coefficients.safetensors"))
        write_json(output_dir/"config.json", prepared)
        return output_dir/"config.json"

    def prepare_baseline_artifact(self):
        config_path = ROOT/"results/numerical/contract_search/combined_high/config.json"
        output = self.args.output_dir/"artifacts/combined_high"
        if (output/"config.json").is_file():
            self._refresh_prepared_weight_reference(output/"config.json")
            self.report.setdefault("artifact_preparation", {})["baseline"] = "reused exact prepared combined_high artifact"
            self.report["artifact_preparation"]["weights_shared_from"] = _workspace_path(self.shared_weights)
            self.report["stages"]["artifact_prepare"] = "complete"
            self._cache_prepared_baseline()
            self.save()
            return output/"config.json"
        started = time.monotonic()
        self.prepare_artifact(read_json(config_path), output, self.shared_weights)
        self.report["artifact_preparation"] = {
            "baseline":"combined_high","weights_shared_from":_workspace_path(self.shared_weights),
            "preparation_seconds":round(time.monotonic()-started,3),
            "runtime_source_checkpoint":False,"runtime_source_qparams":False,
            "scale_rescale_bits":24,"nonlinear_multiplier_bits":24}
        self.report["stages"]["artifact_prepare"] = "complete"
        self._cache_prepared_baseline()
        self.save()
        return output/"config.json"

    def improvement_candidates(self):
        source = read_json(ROOT/"results/numerical/contract_search/combined_high/config.json")
        source.pop("formats",None)
        source["scale_rescale_bits"] = 24
        candidates = []

        def add(name, *, points=None, scale_bits=24):
            config = deepcopy(source)
            config["name"] = name
            config["points"] = deepcopy(points if points is not None else source["points"])
            config["scale_rescale_bits"] = scale_bits
            config["integer_coefficients"] = True
            config["metrics"] = False
            candidates.append(config)

        for bits in (20,18,16):
            points = deepcopy(source["points"])
            for name,family in self.adapter.inventory.items():
                if family == "residual":
                    points[name] = {"bits":bits}
            add(f"residual_w{bits}",points=points)
        boundary_families = sorted(set(self.adapter.inventory.values())-{"residual","probability"})
        for family in boundary_families:
            for bits in (12,8):
                points = deepcopy(source["points"])
                for name,current in self.adapter.inventory.items():
                    if current == family:
                        points[name] = {"bits":bits}
                add(f"boundary_{family}_w{bits}",points=points)
        add("scale_rescale_m16",scale_bits=16)
        if len(candidates) > 35:
            raise RuntimeError(f"initial Quick8 allocation exceeds the 35-config budget: {len(candidates)}")
        return candidates

    def prepare_initial_artifacts(self):
        self.prepare_baseline_artifact()
        entries = self.report.setdefault("prepared_candidate_artifacts", {})
        names = []
        for config in self.improvement_candidates():
            name = config["name"]
            output = self.args.output_dir/"artifacts/screening"/name
            if not (output/"config.json").is_file():
                self.prepare_artifact(config, output, self.shared_weights)
            else:
                self._refresh_prepared_weight_reference(output/"config.json")
            entries[name] = (output/"config.json").relative_to(self.args.output_dir).as_posix()
            names.append(name)
            print(f"PREPARED {name}", flush=True)
        screening = self.report.setdefault("screening", {})
        screening["initial_candidates"] = names
        screening["initial_candidate_count"] = len(names)
        self.report.pop("factor_artifact_retention", None)
        self.report["stages"]["initial_candidate_prepare"] = "complete"
        self.save()

    def prepare_combined_candidate(self):
        if self.report.get("stages", {}).get("combined_candidate_prepare") == "complete":
            relative = self.report.get("prepared_candidate_artifacts", {}).get(COMBINED_CANDIDATE)
            if relative and (self.args.output_dir/relative).is_file():
                self._refresh_prepared_weight_reference(self.args.output_dir/relative)
                prepared = self.report.setdefault("artifact_preparation", {}).setdefault(
                    COMBINED_CANDIDATE, {})
                prepared["weights_shared_from"] = _workspace_path(self.shared_weights)
                self.save()
                print(f"PREPARED {COMBINED_CANDIDATE} already exists; reusing its artifact", flush=True)
                return self.args.output_dir/relative
        existing = self.report.get("screening", {}).get("candidates", {}).get(COMBINED_CANDIDATE, {})
        existing_quick = existing.get("quick", {})
        if existing_quick.get("per_window"):
            raise RuntimeError("this candidate already has Quick checkpoints; resume with --stage artifact-quick")
        if self.report.get("stages", {}).get("factor_screen") != "measured":
            raise RuntimeError("the completed 28-candidate factor Quick8 screen is required")
        names = require_prepared_candidates(self.report, "initial_candidates", 28, 35, "factor")
        require_completed_quick_batch(self.report, names, expected_ids=[row["id"] for row in self.selection[:8]])
        if self.report.get("stages", {}).get("baseline_reproduction") != "measured":
            raise RuntimeError("the previously reproduced artifact baseline is required")
        factor_candidates = self.report.get("screening", {}).get("candidates", {})
        forced_factor_references = {}
        for factor_name in ("residual_w16", "scale_rescale_m16"):
            quick = factor_candidates.get(factor_name, {}).get("quick", {})
            delta = quick.get("delta_mean_nll_vs_combined_high")
            if quick.get("status") != "complete" or not isinstance(delta, (int, float)) or not math.isfinite(delta):
                raise RuntimeError(f"{factor_name}: required factor Quick8 evidence is missing")
            forced_factor_references[factor_name] = {
                "delta_mean_nll": delta, "relative_ppl_increase": math.expm1(delta)}
        base = read_json(ROOT/"results/numerical/contract_search/combined_high/config.json")
        config, widths = build_combined_candidate_config(base, self.adapter.inventory, factor_candidates)
        output = self.args.output_dir/"artifacts"/COMBINED_CANDIDATE
        path = self.prepare_artifact(config, output, self.shared_weights)
        relative = path.relative_to(self.args.output_dir).as_posix()
        self.report.setdefault("prepared_candidate_artifacts", {})[COMBINED_CANDIDATE] = relative
        self.report.setdefault("screening", {})["combined_candidate_name"] = COMBINED_CANDIDATE
        self.report["combined_candidate_selection"] = {
            "candidate": COMBINED_CANDIDATE,
            "criterion": "smallest tested width with math.expm1(delta_mean_nll_vs_combined_high) <= 0.01 on stored factor Quick8",
            "factor_selector": "first 8 selection windows; each contains 512 input tokens and 511 targets",
            "families": widths,
            "forced": {"residual": {"bits": 16, "scale_policy": "per_tensor",
                                      "factor_quick_reference": forced_factor_references["residual_w16"]},
                       "product": {"bits": 16}, "residual_branch": {"bits": 16},
                       "scale_rescale_coefficients": {"bits": 16,
                                                       "factor_quick_reference": forced_factor_references["scale_rescale_m16"]},
                       "nonlinear_coefficients": {"bits": 24, "configuration": "frozen combined_high"},
                       "probability": {"bits": 12, "configuration": "frozen combined_high"}},
            "nonlinear": deepcopy(config["nonlinear"]),
            "nonlinear_refit": False,
            "artifact": relative,
            "quick_result_reused": False}
        self.report.setdefault("stages", {})["combined_candidate_prepare"] = "complete"
        self.report.setdefault("artifact_preparation", {})[COMBINED_CANDIDATE] = {
            "source": "stored 28 factor Quick8 measurements and combined_high artifact config",
            "scale_rescale_bits": 16, "nonlinear_multiplier_bits": 24,
            "weights_shared_from": _workspace_path(self.shared_weights)}
        self.report["approval_gate"] = {
            "status": "combined_quick_pending",
            "checkpoint": "combined candidate prepared; candidate Quick8 has not run",
            "next_action": "run artifact-quick, then stop for user review before Full64",
            "quick8_is_a_quality_gate": False}
        self.save()
        print(f"PREPARED {COMBINED_CANDIDATE}: {relative}", flush=True)
        return path


class ArtifactCampaign:
    def __init__(self, args):
        self.args = args
        self.root = Path(args.output_dir)
        self.path = self.root/"campaign.json"
        self.report = read_json(self.path)
        baseline_config = self.root/"artifacts/combined_high/config.json"
        if baseline_config.is_file() and "baseline_resources" not in self.report:
            self.report["baseline_resources"] = self._resources(baseline_config)
        self.report.setdefault("reproduction", reproduction_protocol())
        profile = self.report.get("performance", {})
        if profile.get("status") != "measured":
            raise RuntimeError("artifact thread profile must be measured before scoring")
        self.threads = int(profile["selected_threads"])
        torch.set_num_threads(self.threads)
        self.started = time.monotonic()
        self.selection = read_json(ROOT/"data/wikitext_selection.json")
        self.questions = read_json(ROOT/"data/piqa_selection.json")
        self.cases = read_json(ROOT/"data/cache_cases.json")
        self.reference = read_json(ROOT/"results/ptq/fp32.json")
        self.saved = read_json(ROOT/"results/numerical/contract_search/campaign.json")
        self.tokenizer = AutoTokenizer.from_pretrained(
            source_snapshot(args.cache_dir, args.offline), local_files_only=True, trust_remote_code=False)
        self.report["backend"] = "artifact_only_integer_code_execution; PyTorch CPU FP64 exact-code GEMM"
        self.report["threads"] = self.threads
        self.report["teacher_model_loaded_during_measurement"] = False
        self.report["ptq_adapter_loaded_during_measurement"] = False

    def save(self):
        self.report["last_session_seconds"] = round(time.monotonic()-self.started, 3)
        atomic_json(self.path, self.report)

    def ppl(self, runtime, owner, key, records):
        row = owner.setdefault(key, {"status":"in_progress", "per_window":[]})
        if row.get("status") == "complete":
            return row
        done = {item["id"] for item in row["per_window"]}
        for record in records:
            if record["id"] in done:
                continue
            logits = full_logits(runtime, record["input_ids"])
            nll, tokens = score_targets(logits, record["input_ids"])
            row["per_window"].append({"id":record["id"], "nll":nll, "tokens":tokens})
            del logits
            print(f"ARTIFACT PPL {len(row['per_window'])}/{len(records)} {record['id']}", flush=True)
            self.save()
        row["per_window"].sort(key=lambda item: next(i for i,r in enumerate(records) if r["id"] == item["id"]))
        row.update(aggregate_nll([(item["nll"], item["tokens"]) for item in row["per_window"]]))
        row["windows"] = len(records)
        row["status"] = "complete"
        self.save()
        return row

    def piqa(self, runtime, owner, key, records):
        row = owner.setdefault(key, {"status":"in_progress", "per_question":[]})
        if row.get("status") == "complete":
            return row
        done = {item["id"] for item in row["per_question"]}
        for record in records:
            if record["id"] in done:
                continue
            scores, counts = [], []
            for choice in record["choices"]:
                logits = full_logits(runtime, choice["input_ids"])
                nll, count = score_targets(logits, choice["input_ids"], choice["answer_start"])
                scores.append(-nll)
                counts.append(count)
                del logits
            prediction = choose_answer(scores)
            row["per_question"].append({"id":record["id"], "label":record["label"],
                "prediction":prediction, "log_likelihoods":scores, "answer_tokens":counts,
                "correct":prediction == record["label"]})
            self.save()
            if len(row["per_question"]) % 25 == 0:
                print(f"ARTIFACT PIQA {len(row['per_question'])}/{len(records)}", flush=True)
        row["per_question"].sort(key=lambda item: next(i for i,r in enumerate(records) if r["id"] == item["id"]))
        correct = sum(item["correct"] for item in row["per_question"])
        row.update({"questions":len(records), "choices":2*len(records), "correct":correct,
            "accuracy":correct/len(records), "answer_tokens":sum(sum(x["answer_tokens"]) for x in row["per_question"]),
            "status":"complete"})
        self.save()
        return row

    def cache(self, runtime, owner, key, selection, cases, reference_rows=None, reference_cases=None):
        row = owner.setdefault(key, {"status":"in_progress", "runs":[]})
        if row.get("status") == "complete":
            return row
        completed = {(item["id"], item["prefill"]) for item in row["runs"]}
        total = sum(len(case["regimes"]) for case in cases)
        reference_by_case = {}
        if reference_rows is not None:
            if reference_cases is None or len(reference_cases) != 16:
                raise RuntimeError("fixed FP32 cache diagnostic rows are incomplete")
            reference_by_case = {(item["id"], item["prefill"]): item for item in reference_cases}
        for case_index, case in enumerate(cases):
            record = selection[case["selection_index"]]
            for regime in case["regimes"]:
                prefill, decode = regime["prefill"], regime["decode"]
                if (case["id"], prefill) in completed:
                    continue
                ids = record["input_ids"][:regime["input_length"]]
                full = runtime(input_ids=torch.tensor([ids], dtype=torch.long),
                    attention_mask=torch.ones((1,len(ids)), dtype=torch.long))
                cached_logits, cached_codes, preserved = runtime.cached_outputs(ids,prefill,verify_prefix=True)
                differing = int((full.logit_codes[0].to(torch.int32) != cached_codes.to(torch.int32)).sum())
                if differing:
                    raise AssertionError(f"full/cache code mismatch: {case['id']} prefill={prefill}")
                full_nll, _ = score_targets(full.logits[0], ids, prefill, prefill+decode)
                nll, tokens = score_targets(cached_logits, ids, prefill, prefill+decode)
                result = {"id":case["id"], **regime, "nll":nll, "tokens":tokens,
                    "full_nll":full_nll, "different_logit_codes":0,
                    "logit_codes_bitwise_equal":True, "cache_prefix_preserved":preserved}
                if reference_rows is not None:
                    reference_case = reference_by_case.get((case["id"], prefill))
                    expected_key = f"case_{case_index}_{prefill}"
                    if reference_case is None or reference_case["key"] != expected_key:
                        raise RuntimeError(f"FP32 diagnostic selector mismatch: {case['id']} prefill={prefill}")
                    positions = reference_case["rows"]
                    reference = reference_rows[expected_key]
                    if (len(reference) != len(positions) or reference.shape[-1] != full.logits.shape[-1]
                            or not torch.isfinite(reference).all()):
                        raise ValueError(f"invalid FP32 diagnostic tensor: {expected_key}")
                    full_selected = full.logits[0].index_select(0, torch.tensor(positions))
                    cache_selected = cached_logits.index_select(0, torch.tensor(positions))
                    full_diagnostic = distribution_diagnostic(reference, full_selected)
                    cache_diagnostic = distribution_diagnostic(reference, cache_selected)
                    result["diagnostic_rows"] = positions
                    result["full_fp32_diagnostic"] = full_diagnostic
                    result["cache_fp32_diagnostic"] = cache_diagnostic
                    if not all(math.isfinite(value) for diagnostic in (full_diagnostic, cache_diagnostic)
                               for value in (diagnostic["top1_agreement"], diagnostic["mean_kl_fp32_to_candidate"])):
                        raise ValueError(f"nonfinite distribution diagnostic: {expected_key}")
                    del reference, full_selected, cache_selected
                row["runs"].append(result)
                del full, cached_logits, cached_codes
                self.save()
                print(f"ARTIFACT CACHE {len(row['runs'])}/{total} {case['id']} prefill={prefill}", flush=True)
        row["runs"].sort(key=lambda item:(item["id"], item["prefill"]))
        row["regimes"] = {str(prefill):aggregate_nll([(item["nll"], item["tokens"])
            for item in row["runs"] if item["prefill"] == prefill]) for prefill in (32,448)}
        row.update(aggregate_nll([(item["nll"], item["tokens"]) for item in row["runs"]]))
        row["status"] = "complete"
        self.save()
        return row

    def baseline_reproduction_stage(self):
        if self.report.get("stages", {}).get("baseline_reproduction") == "measured":
            return
        config_path = self.root/"artifacts/combined_high/config.json"
        if not config_path.is_file():
            raise FileNotFoundError(f"prepared combined_high artifact missing: {config_path}")
        runtime = load_prepared_contract(config_path)
        result = self.report.setdefault("baseline_reproduction", {"status":"in_progress"})
        result["ppl"] = self.ppl(runtime,result,"ppl",self.selection)
        result["piqa"] = self.piqa(runtime,result,"piqa",self.questions)
        result["cache"] = self.cache(runtime,result,"cache",self.selection,self.cases)
        if "greedy" not in result:
            prompts = [record["input_ids"][:32] for record in self.selection[:2]]
            result["greedy"] = greedy(runtime,self.tokenizer,prompts,max_new=32)
            self.save()
        old = self.saved["combinations"]["combined_high"]
        old_ppl = {item["id"]:item["nll"] for item in old["full_ppl"]["per_window"]}
        new_ppl = {item["id"]:item["nll"] for item in result["ppl"]["per_window"]}
        old_piqa = {item["id"]:item["prediction"] for item in old["piqa"]["per_question"]}
        new_piqa = {item["id"]:item["prediction"] for item in result["piqa"]["per_question"]}
        old_cache = {(item["id"],item["prefill"]):item["nll"] for item in old["cache"]["runs"]}
        new_cache = {(item["id"],item["prefill"]):item["nll"] for item in result["cache"]["runs"]}
        same_ppl = old_ppl == new_ppl
        same_piqa = old_piqa == new_piqa
        same_cache = old_cache == new_cache
        same_greedy = [x["generated_ids"] for x in result["greedy"]] == [x["generated_ids"] for x in old["greedy"]]
        comparison = {"ppl_per_window_exact":same_ppl, "piqa_predictions_exact":same_piqa,
            "cache_run_nll_exact":same_cache, "greedy_token_ids_exact":same_greedy,
            "ppl_windows":len(new_ppl), "piqa_questions":len(new_piqa), "cache_runs":len(new_cache),
            "greedy_prompts":len(result["greedy"])}
        result["saved_baseline_comparison"] = comparison
        if not all((same_ppl,same_piqa,same_cache,same_greedy)):
            result["status"] = "mismatch"
            self.save()
            raise AssertionError(f"artifact baseline differs from saved combined_high: {comparison}")
        result["relative_ppl_increase_vs_fp32"] = result["ppl"]["ppl"]/self.reference["ppl"]["ppl"]-1
        result["piqa_drop_vs_fp32"] = self.reference["piqa"]["accuracy"]-result["piqa"]["accuracy"]
        result["cache_relative_ppl_increase"] = {regime:result["cache"]["regimes"][regime]["ppl"]/
            self.reference["cache"]["regimes"][regime]["ppl"]-1 for regime in ("32","448")}
        result["status"] = "confirmed"
        self.report.setdefault("stages",{})["baseline_reproduction"] = "measured"
        self.save()
        del runtime

    def run_baseline(self):
        self.baseline_reproduction_stage()
        print("BASELINE artifact reproduction confirmed", flush=True)

    def run_factor_quick(self):
        if self.report.get("stages", {}).get("baseline_reproduction") != "measured":
            raise RuntimeError("the previously reproduced artifact baseline is required")
        if self.report.get("stages", {}).get("factor_screen") == "measured":
            require_completed_factor_quick(
                self.report, expected_ids=[row["id"] for row in self.selection[:8]])
            print("FACTOR QUICK8 already complete; no scores were recomputed", flush=True)
            return
        names = require_prepared_candidates(self.report, "initial_candidates", 28, 35, "factor")
        with torch.inference_mode():
            for name in names:
                self._screen_candidate(name)
        require_completed_quick_batch(self.report, names,
            expected_ids=[row["id"] for row in self.selection[:8]])
        self.report.setdefault("stages", {})["factor_screen"] = "measured"
        self.save()
        print("FACTOR QUICK8 complete; no Full64 or qualification stage was started", flush=True)

    @staticmethod
    def _point_family(name):
        if name == "model.embed_tokens.output": return "embedding"
        if name == "lm_head.output": return "logits"
        if name.endswith("layernorm.output") or name == "model.norm.output": return "norm"
        if name.endswith("q_proj.output"): return "q_pre"
        if name.endswith("k_proj.output"): return "k_pre"
        if name.endswith("query_post_rope"): return "q_post"
        if name.endswith(".score"): return "score"
        if name.endswith("probability_unmasked"): return "probability"
        if name.endswith(".context"): return "context"
        if name.endswith(("o_proj.output", "down_proj.output")): return "residual_branch"
        if name.endswith(("residual_after_attention", "residual_after_ffn")): return "residual"
        if name.endswith(("gate_proj.output", "up_proj.output")): return "gate_up"
        if name.endswith("silu_output"): return "silu"
        if name.endswith("gate_product"): return "product"
        raise KeyError(f"unknown numerical boundary: {name}")

    def _resources(self, config_path):
        config = read_json(config_path)
        packed = container = 0
        maximum_container = 0
        rows = {}
        for name,spec in config["points"].items():
            family = self._point_family(name)
            if family in ("score", "probability"): count = 9*512*512
            elif family == "k_pre": count = 512*192
            elif family in ("gate_up", "silu", "product"): count = 512*1536
            elif family == "logits": count = 512*49152
            else: count = 512*576
            bits = int(spec["bits"])
            storage_bits = 8 if bits <= 8 else 16 if bits <= 16 else 32
            payload = math.ceil(count*bits/8)
            container_bytes = count*storage_bits//8
            rows[name] = {"family":family,"logical_bits":bits,
                "canonical_format_container_bits":storage_bits,
                "elements_per_512":count,"packed_payload_bytes":payload,
                "canonical_format_bytes":container_bytes}
            packed += payload
            container += container_bytes
            maximum_container = max(maximum_container, storage_bits)
        bundle_path = (config_path.parent/config["coefficients"]).resolve()
        weights_path = (config_path.parent/config["weights"]).resolve()
        bundle = load_file(str(bundle_path),device="cpu")
        multiplier_shift_bytes = sum(t.numel()*t.element_size() for name,t in bundle.items()
                                     if name.endswith((".M",".shift")))
        table_bytes = sum(t.numel()*t.element_size() for name,t in bundle.items()
                          if (name.startswith(("rope.","softmax.","rms."))
                              or name.endswith(".epsilon") or ".pwl." in name)
                          and not name.endswith((".M",".shift")))
        scale_sizes = {name:int(torch.as_tensor(spec["scale"]).numel())
                       for name,spec in config["formats"].items()}
        per_tensor_scales = sum(count == 1 for count in scale_sizes.values())
        per_channel_scales = sum(count for count in scale_sizes.values() if count > 1)
        baseline_path = self.root/"artifacts/combined_high/config.json"
        baseline = read_json(baseline_path) if baseline_path.is_file() else None
        baseline_scale_values = (sum(int(torch.as_tensor(spec["scale"]).numel())
                                     for spec in baseline["formats"].values()) if baseline else 0)
        align_keys = [name for name in bundle if name.endswith(".align_input.M")]
        align_values = sum(bundle[name].numel() for name in align_keys)

        # Bound the actual guard integers from each branch source format and
        # serialized M/shift pair. This reports logical widths the RTL must
        # carry without counting the INT64 software container as datapath width.
        branch_widths, branch_products, sum_widths = [], [], []
        for layer in range(int(config["model"]["layers"])):
            prefix = f"model.layers.{layer}"
            for kind in ("attention","ffn"):
                target = prefix+f".residual_after_{kind}"
                if kind == "attention":
                    left = "model.embed_tokens.output" if layer == 0 else f"model.layers.{layer-1}.residual_after_ffn"
                    right = prefix+".self_attn.o_proj.output"
                else:
                    left = prefix+".residual_after_attention"
                    right = prefix+".mlp.down_proj.output"
                bounds = []
                for branch,source in (("left_to_guard",left),("right_to_guard",right)):
                    fmt = config["formats"][source]
                    source_low,source_high = integer_code_bounds(int(fmt["bits"]),bool(fmt["signed"]))
                    multipliers = bundle[target+"."+branch+".M"].reshape(-1).tolist()
                    shifts = bundle[target+"."+branch+".shift"].reshape(-1).tolist()
                    branch_ranges = []
                    for multiplier,shift in zip(multipliers,shifts):
                        denominator_shift = int(shift)
                        products = (source_low*int(multiplier),source_high*int(multiplier))
                        product_low,product_high = min(products),max(products)
                        branch_products.append(minimum_signed_width(product_low,product_high))
                        def apply(value):
                            product = int(value)*int(multiplier)
                            return (round_divide_scalar(product,1 << denominator_shift)
                                    if denominator_shift >= 0 else product << -denominator_shift)
                        low,high = apply(source_low),apply(source_high)
                        branch_ranges.append((min(low,high),max(low,high)))
                    if len(branch_ranges) == 1:
                        branch_ranges *= int(config["model"]["hidden_size"])
                    bounds.append(branch_ranges)
                    branch_widths.extend(minimum_signed_width(*item) for item in branch_ranges)
                aggregate = [(bounds[0][i][0]+bounds[1][i][0],
                              bounds[0][i][1]+bounds[1][i][1])
                             for i in range(max(len(bounds[0]),len(bounds[1])))]
                sum_widths.extend(minimum_signed_width(*item) for item in aggregate)
        extra_align_operations = align_values
        alignment_invocations = len(align_keys)
        aligned_output_bits = 24
        fully_materialized_alignment_bytes = (alignment_invocations
            * 512 * int(config["model"]["hidden_size"]) * aligned_output_bits // 8)
        return {"measurement_scope":
                "512-token canonical exchange/format storage proxy; not Python runtime carriers or RSS, not a simultaneous buffer or RTL SRAM estimate",
            "packed_boundary_payload_proxy_bytes_per_512":packed,
            "canonical_boundary_format_bytes_per_512":container,
            "maximum_canonical_format_container_bits":maximum_container,
            "boundary_inventory":rows,
            "coefficient_bundle_bytes":bundle_path.stat().st_size,"shared_weight_bundle_bytes":weights_path.stat().st_size,
            "runtime_multiplier_shift_payload_bytes":multiplier_shift_bytes,
            "runtime_table_payload_bytes":table_bytes,
            "scale_metadata":{"format_count":len(scale_sizes),"per_tensor_scale_values":per_tensor_scales,
                "per_channel_or_head_scale_values":per_channel_scales,
                "total_scale_values":sum(scale_sizes.values()),
                "extra_scale_values_vs_combined_high":sum(scale_sizes.values())-baseline_scale_values,
                "hypothetical_float32_bytes":4*sum(scale_sizes.values()),
                "meaning":"configuration metadata, not runtime SRAM"},
            "per_channel_rms_alignment":{"alignment_vectors":alignment_invocations,
                "alignment_invocations_per_token":alignment_invocations,
                "alignment_values_per_token":align_values,
                "aligned_output_logical_bits":aligned_output_bits,
                "fully_materialized_aligned_payload_bytes_per_512":fully_materialized_alignment_bytes,
                "payload_scope":"24-bit logical code payload only if every per-norm aligned tensor for 512 tokens is materialized; tensors can be streamed/recomputed per norm, so this is not a concurrent peak-storage estimate",
                "serialized_multiplier_elements":align_values,
                "additional_integer_multiply_shift_operations_per_token":extra_align_operations,
                "alignment_multiplier_bytes":sum(bundle[name].numel()*bundle[name].element_size()
                    +bundle[name.removesuffix(".M")+".shift"].numel()*bundle[name.removesuffix(".M")+".shift"].element_size()
                    for name in align_keys)},
            "residual_arithmetic_widths":{"max_branch_guard_signed_bits":max(branch_widths,default=1),
                "max_guard_multiplier_product_signed_bits_before_rne":max(branch_products,default=1),
                "max_branch_magnitude_bits":max((width-1 for width in branch_widths),default=0),
                "max_two_branch_sum_signed_bits":max(sum_widths,default=1),
                "basis":"extrema from signed source code ranges and the serialized fixed-point M/shift pairs"},
            "coefficient_storage_note":"M tensors remain INT32 containers; multiplier precision reduction changes logical magnitude precision, not necessarily serialized bytes. A shared datapath sized for the 24-bit class does not shrink solely because a candidate uses 16-bit coefficients.",
            "scale_rescale_bits":config["scale_rescale_bits"],"nonlinear_multiplier_bits":config["nonlinear_multiplier_bits"],
            "limitations":"No concurrent-peak SRAM, packing, area, timing, or power is inferred."}

    def _screen_candidate(self, name):
        screening = self.report.setdefault("screening", {}).setdefault("candidates", {})
        if name in screening and screening[name].get("quick",{}).get("status") == "complete":
            return screening[name]
        if name not in screening and len(screening) >= 35:
            raise RuntimeError("Quick8 hard budget exceeded (35 candidates maximum)")
        artifacts = self.report.get("prepared_candidate_artifacts", {})
        if name not in artifacts:
            raise FileNotFoundError(f"candidate artifact was not prepared: {name}")
        config_path = self.root/artifacts[name]
        config = read_json(config_path)
        entry = screening.setdefault(name,{"config_name":name,"quick":{"status":"in_progress","per_window":[]}})
        runtime = load_prepared_contract(config_path)
        row = entry["quick"]
        done = {item["id"] for item in row["per_window"]}
        for record in self.selection[:8]:
            if record["id"] in done:
                continue
            logits = full_logits(runtime, record["input_ids"])
            nll,tokens = score_targets(logits, record["input_ids"])
            row["per_window"].append({"id":record["id"],"nll":nll,"tokens":tokens})
            del logits
            print(f"QUICK8 {name} {len(row['per_window'])}/8 {record['id']}",flush=True)
            self.save()
        row["per_window"].sort(key=lambda item:next(i for i,r in enumerate(self.selection[:8]) if r["id"]==item["id"]))
        row.update(aggregate_nll([(item["nll"],item["tokens"]) for item in row["per_window"]]))
        row["windows"] = len(row["per_window"])
        base = self.report["baseline_reproduction"]["ppl"]["per_window"][:8]
        row["delta_mean_nll_vs_combined_high"] = (row["nll"]-sum(x["nll"] for x in base))/row["tokens"]
        resources = self._resources(config_path)
        row["boundary_payload_proxy_bytes_per_512"] = resources["packed_boundary_payload_proxy_bytes_per_512"]
        row["runtime_multiplier_shift_payload_bytes"] = resources["runtime_multiplier_shift_payload_bytes"]
        row["scale_metadata"] = resources["scale_metadata"]
        row["per_channel_rms_alignment"] = resources["per_channel_rms_alignment"]
        row["residual_arithmetic_widths"] = resources["residual_arithmetic_widths"]
        row["status"] = "complete"
        entry["resources"] = resources
        self.save()
        del runtime
        return entry

    def _full_ppl(self, runtime, owner, records):
        row = owner.setdefault("full_ppl", {"status":"in_progress","per_window":[]})
        if row.get("status") == "complete": return row
        if not row["per_window"] and len(records) >= 8:
            quick = self.report.get("screening", {}).get("candidates", {}).get(owner["name"], {}).get("quick", {})
            quick_rows = quick.get("per_window", [])
            quick_by_id = {item["id"]:item for item in quick_rows}
            expected_ids = [record["id"] for record in records[:8]]
            if (quick.get("status") == "complete" and quick.get("windows") == 8
                    and len(quick_rows) == 8 and len(quick_by_id) == 8
                    and set(quick_by_id) == set(expected_ids)):
                row["per_window"] = [dict(quick_by_id[record_id]) for record_id in expected_ids]
                row["quick8_reuse"] = {"windows_reused":8,
                    "remaining_full_selection_windows":len(records)-8,
                    "basis":"same candidate artifact, full-selection records, and scorer as completed Quick8"}
                self.save()
        done = {item["id"] for item in row["per_window"]}
        for record in records:
            if record["id"] in done: continue
            logits = full_logits(runtime,record["input_ids"])
            nll,tokens = score_targets(logits,record["input_ids"])
            row["per_window"].append({"id":record["id"],"nll":nll,"tokens":tokens})
            del logits
            self.save()
            print(f"FULL64 {owner['name']} {len(row['per_window'])}/{len(records)} {record['id']}",flush=True)
        row["per_window"].sort(key=lambda item:next(i for i,r in enumerate(records) if r["id"]==item["id"]))
        row.update(aggregate_nll([(item["nll"],item["tokens"]) for item in row["per_window"]]))
        row["windows"] = len(records)
        row["full_selection_windows_not_reused_from_quick8"] = len(records)-row.get("quick8_reuse",{}).get("windows_reused",0)
        row["status"] = "complete"
        self.save()
        return row

    def run_combined_quick(self):
        if self.report.get("stages", {}).get("combined_candidate_prepare") != "complete":
            raise RuntimeError("run artifact-prepare-combined before Quick8")
        if self.report.get("stages", {}).get("baseline_reproduction") != "measured":
            raise RuntimeError("the previously reproduced artifact baseline is required")
        selection = self.report.get("screening", {})
        name = selection.get("combined_candidate_name", COMBINED_CANDIDATE)
        factor_names = set(selection.get("initial_candidates", []))
        if name in factor_names:
            raise RuntimeError("combined candidate identity collides with a measured factor")
        artifacts = self.report.get("prepared_candidate_artifacts", {})
        if name not in artifacts:
            raise FileNotFoundError(f"combined candidate artifact is missing: {name}")
        if artifacts[name] in {artifacts[key] for key in factor_names if key in artifacts}:
            raise RuntimeError("combined candidate must use its own prepared artifact")
        self.threads = int(self.report.get("performance", {}).get("selected_threads", 0))
        if self.threads != 8:
            raise RuntimeError(f"Quick8 requires the verified 8-thread profile; found {self.threads}")
        self.report.setdefault("backend", "artifact_only_integer_code_execution; PyTorch CPU FP64 exact-code GEMM")
        self.report["threads"] = self.threads
        self.report["teacher_model_loaded_during_measurement"] = False
        self.report["ptq_adapter_loaded_during_measurement"] = False
        if len(self.selection) < 8 or any(len(row["input_ids"]) != 512 for row in self.selection[:8]):
            raise RuntimeError("Quick8 requires the first eight complete 512-token selection windows")
        if "combined_candidate_name" not in selection:
            selection["combined_candidate_name"] = name
            self.save()
        with torch.inference_mode():
            entry = self._screen_candidate(name)
        require_completed_quick_batch(self.report, [name], expected_ids=[row["id"] for row in self.selection[:8]])
        quick = entry["quick"]
        expected_targets = 8 * 511
        if quick["tokens"] != expected_targets:
            raise RuntimeError(f"Quick8 target count changed: {quick['tokens']} != {expected_targets}")
        baseline = self.report["baseline_reproduction"]["ppl"]
        baseline_quick_ppl = aggregate_nll([
            (row["nll"], row["tokens"]) for row in baseline["per_window"][:8]])["ppl"]
        relative_from_ppl = quick["ppl"] / baseline_quick_ppl - 1
        relative_from_delta = math.expm1(quick["delta_mean_nll_vs_combined_high"])
        if not math.isclose(relative_from_ppl, relative_from_delta, rel_tol=1e-10, abs_tol=1e-12):
            raise AssertionError("Quick8 PPL ratio disagrees with its unrounded mean-NLL delta")
        quick["relative_ppl_increase_vs_combined_high"] = relative_from_delta
        quick["ranking_only"] = True
        quick["quality_gate"] = False
        self.report["combined_quick_result"] = {
            "candidate": name, "windows": quick["windows"], "targets": quick["tokens"],
            "ppl": quick["ppl"], "baseline_quick_ppl": baseline_quick_ppl,
            "baseline_full_ppl": baseline["ppl"],
            "relative_ppl_increase": relative_from_delta,
            "backend": self.report["backend"], "threads": self.threads,
            "reused_factor_candidate_scores": False,
            "full64_status": "not_run_waiting_for_explicit_user_approval"}
        self.report.setdefault("stages", {})["combined_quick"] = "measured"
        self.report["approval_gate"] = {
            "status": "pending_user_approval_for_full64",
            "checkpoint": "combined candidate Quick8 completed; no candidate Full64 or PIQA/cache/greedy qualification was started",
            "next_action": "report Quick8 and wait for explicit user approval before artifact-full",
            "quick8_is_a_quality_gate": False}
        self.save()
        print(f"COMBINED QUICK8 {name} PPL={quick['ppl']:.12f} targets={quick['tokens']} "
              f"delta_ppl={quick['relative_ppl_increase_vs_combined_high']:.6%}", flush=True)

    def run_combined_full_ppl(self):
        if self.report.get("stages", {}).get("combined_quick") != "measured":
            raise RuntimeError("explicit Full64 stage requires a completed combined Quick8")
        name = self.report.get("combined_quick_result", {}).get("candidate")
        if name != COMBINED_CANDIDATE:
            raise RuntimeError("Full64 is restricted to the prepared combined candidate")
        config_path = self.root/self.report["prepared_candidate_artifacts"][name]
        runtime = load_prepared_contract(config_path)
        owner = self.report.setdefault("combined_full_ppl_result", {"name": name})
        if owner.get("name") != name:
            raise RuntimeError("Full64 checkpoint belongs to a different candidate")
        row = self._full_ppl(runtime, owner, self.selection)
        del runtime
        if row["windows"] != 64 or row["tokens"] != 32704:
            raise RuntimeError(f"Full64 PPL result is incomplete: {row['windows']} windows, {row['tokens']} targets")
        owner["ppl_ratio_vs_fp32"] = row["ppl"] / self.reference["ppl"]["ppl"]
        owner["relative_ppl_increase_vs_fp32"] = owner["ppl_ratio_vs_fp32"] - 1
        owner["gate_limit"] = 0.05
        owner["ppl_gate_pass"] = owner["ppl_ratio_vs_fp32"] <= 1.05
        self.report.setdefault("stages", {})["combined_full_ppl"] = "measured"
        owner.setdefault("full_selection_wall_seconds", self.report.get("last_session_seconds"))
        self.report["approval_gate"] = {
            "status": "authorized_execution_completed",
            "checkpoint": "Full64 measured under the user-authorized fixed-candidate campaign",
            "quick8_is_a_quality_gate": False,
            "full64_ppl_gate_pass": owner["ppl_gate_pass"]}
        self.report.setdefault("combined_quick_result", {})["full64_status"] = "measured"
        if not owner["ppl_gate_pass"]:
            owner["selection_status"] = "rejected_full_ppl"
            owner["qualification_skipped"] = "dependent quality tests are gated on Full64 PPL"
            self.report["stages"]["combined_qualification"] = "skipped_full_ppl_gate"
            self.report["software_contract_selection"] = "rejected_full_ppl"
        elif self.report.get("stages", {}).get("combined_qualification") == "complete":
            owner["selection_status"] = self.report.get("software_contract_selection")
        else:
            owner["selection_status"] = "awaiting_remaining_quality_gates"
        self.save()
        print(f"COMBINED FULL64 {name} PPL={row['ppl']:.12f} "
              f"targets={row['tokens']} gate_pass={owner['ppl_gate_pass']}", flush=True)

    def run_combined_qualification(self):
        full_owner = self.report.get("combined_full_ppl_result", {})
        full = full_owner.get("full_ppl", {})
        if full.get("status") != "complete" or full.get("windows") != 64 or full.get("tokens") != 32704:
            raise RuntimeError("qualification requires completed 64-window/32704-target Full PPL")
        if full["ppl"] / self.reference["ppl"]["ppl"] > 1.05:
            raise RuntimeError("candidate failed Full64 PPL; remaining gates are not run")
        reference_path = self.root/"qualification_fp32_rows.safetensors"
        if self.report.get("stages", {}).get("combined_qualification") == "complete":
            if reference_path.is_file():
                reference_path.unlink()
            diagnostic = self.report.setdefault("diagnostic_reference", {})
            if (diagnostic.get("path") is not None
                    or not diagnostic.get("temporary_file_removed", False)):
                self.report["diagnostic_reference"]["temporary_file_removed"] = True
                self.report["diagnostic_reference"]["path"] = None
                self.save()
            return
        diagnostic = self.report.get("diagnostic_reference", {})
        if diagnostic.get("status") != "complete" or not reference_path.is_file():
            raise RuntimeError("run artifact-prepare-diagnostics before candidate qualification")
        name = self.report.get("combined_quick_result", {}).get("candidate")
        if name != COMBINED_CANDIDATE:
            raise RuntimeError("qualification is restricted to the fixed prepared candidate")
        config_path = self.root/self.report["prepared_candidate_artifacts"][name]
        runtime = load_prepared_contract(config_path)
        row = self.report.setdefault("combined_qualification_result", {"name": name})
        if row.get("name") != name:
            raise RuntimeError("qualification checkpoint belongs to another candidate")
        row["status"] = "in_progress"
        row["started_full_ppl"] = {"ppl": full["ppl"], "windows": full["windows"],
                                    "targets": full["tokens"]}
        self.save()

        piqa = self.piqa(runtime, row, "piqa", self.questions)
        expected_question_ids = [item["id"] for item in self.questions]
        actual_question_ids = [item["id"] for item in piqa["per_question"]]
        if (piqa["questions"] != 919 or piqa["choices"] != 1838
                or actual_question_ids != expected_question_ids):
            raise RuntimeError("PIQA qualification did not cover all fixed questions and choices")

        reference_rows = load_file(str(reference_path), device="cpu")
        cache = self.cache(runtime, row, "cache", self.selection, self.cases,
                           reference_rows=reference_rows,
                           reference_cases=diagnostic.get("cases"))
        expected_cache = {(case["id"], regime["prefill"])
                          for case in self.cases for regime in case["regimes"]}
        actual_cache = {(item["id"], item["prefill"]) for item in cache["runs"]}
        if (cache["status"] != "complete" or len(cache["runs"]) != 16
                or actual_cache != expected_cache
                or any(item["tokens"] != 64 for item in cache["runs"])):
            raise RuntimeError("cache qualification did not cover all 16 fixed cases")
        if any(not item["logit_codes_bitwise_equal"] or not item["cache_prefix_preserved"]
               for item in cache["runs"]):
            raise RuntimeError("cache codes differ from full forward or a prefix changed")
        if any("full_fp32_diagnostic" not in item or "cache_fp32_diagnostic" not in item
               for item in cache["runs"]):
            raise RuntimeError("full-vocabulary FP32 diagnostics are missing from a cache case")
        if any(sum(item["tokens"] for item in cache["runs"] if item["prefill"] == prefill) != 512
               for prefill in (32, 448)):
            raise RuntimeError("cache target coverage changed from 512 per prefill regime")

        prompts = [record["input_ids"][:32] for record in self.selection[:2]]
        greedy_result = row.get("greedy")
        if greedy_result is None:
            greedy_result = greedy(runtime, self.tokenizer, prompts, max_new=32)
            if (len(greedy_result) != 2 or any(len(item["prompt_ids"]) != 32
                                               or len(item["generated_ids"]) > 32
                                               for item in greedy_result)):
                raise RuntimeError("greedy qualification did not use the fixed prompts and token limit")
            row["greedy"] = greedy_result
            self.save()

        # Compare serialized-artifact reload using exact integer logit codes.
        reload_check = row.get("reload")
        if not (isinstance(reload_check, dict) and reload_check.get("status") == "passed"):
            probe_ids = self.selection[0]["input_ids"][:96]
            probe_prefill = 32
            expected_full = runtime(input_ids=torch.tensor([probe_ids], dtype=torch.long),
                                    attention_mask=torch.ones((1, len(probe_ids)), dtype=torch.long),
                                    use_cache=False).logit_codes.clone()
            _, expected_cache_codes, expected_prefix = runtime.cached_outputs(
                probe_ids, probe_prefill, verify_prefix=True)
            if expected_prefix is not True:
                raise AssertionError("candidate cache reload probe failed to preserve its prefix")
            del runtime
            gc.collect()
            reloaded = load_prepared_contract(config_path)
            actual_full = reloaded(input_ids=torch.tensor([probe_ids], dtype=torch.long),
                                   attention_mask=torch.ones((1, len(probe_ids)), dtype=torch.long),
                                   use_cache=False).logit_codes
            _, actual_cache_codes, actual_prefix = reloaded.cached_outputs(
                probe_ids, probe_prefill, verify_prefix=True)
            reload_check = {"full_codes_bitwise_equal": torch.equal(actual_full, expected_full),
                            "cache_codes_bitwise_equal": torch.equal(actual_cache_codes, expected_cache_codes),
                            "cache_prefix_preserved": actual_prefix is True,
                            "input_length": len(probe_ids), "prefill": probe_prefill}
            reload_check["status"] = ("passed" if all(reload_check[key] for key in
                ("full_codes_bitwise_equal", "cache_codes_bitwise_equal", "cache_prefix_preserved"))
                else "failed")
            del reloaded, expected_full, expected_cache_codes, actual_full, actual_cache_codes
            gc.collect()
            row["reload"] = reload_check
            self.save()

        gates = qualification_gates(full["ppl"], piqa["correct"], cache["regimes"],
                                    self.reference["ppl"]["ppl"])
        hard_checks = {
            "full_ppl_coverage": full["windows"] == 64 and full["tokens"] == 32704,
            "piqa_coverage": piqa["questions"] == 919 and piqa["choices"] == 1838,
            "cache_coverage": len(cache["runs"]) == 16,
            "full_cache_codes_equal": all(item["logit_codes_bitwise_equal"] for item in cache["runs"]),
            "cache_prefix_preserved": all(item["cache_prefix_preserved"] for item in cache["runs"]),
            "reload_bitwise_equal": all(reload_check[key] for key in
                ("full_codes_bitwise_equal", "cache_codes_bitwise_equal", "cache_prefix_preserved")),
            "diagnostics_finite": all(math.isfinite(diagnostic_value)
                for item in cache["runs"]
                for group in (item["full_fp32_diagnostic"], item["cache_fp32_diagnostic"])
                for diagnostic_value in (group["top1_agreement"], group["mean_kl_fp32_to_candidate"])),
            "greedy_finite_and_bounded": len(greedy_result) == 2 and all(
                len(item["generated_ids"]) <= 32 for item in greedy_result)}
        row["gates"] = gates
        row["hard_checks"] = hard_checks
        row["kept_for_software_profile"] = gates["pass"] and all(hard_checks.values())
        row["status"] = ("software_selection_qualified" if row["kept_for_software_profile"]
                          else "rejected_quality_or_numerical_gate")
        row["heldout_evaluated"] = False
        full_owner["selection_status"] = row["status"]
        self.report.setdefault("stages", {})["combined_qualification"] = "complete"
        self.report["software_contract_selection"] = row["status"]
        self.save()
        reference_path.unlink()
        self.report["diagnostic_reference"]["temporary_file_removed"] = True
        self.report["diagnostic_reference"]["path"] = None
        self.save()
        print(f"COMBINED QUALIFICATION {name} status={row['status']} "
              f"PIQA={piqa['correct']}/919 cache_runs={len(cache['runs'])}", flush=True)

if __name__ == "__main__":
    raise SystemExit(main())
