#!/usr/bin/env python3
"""Finite, resumable numerical-contract search on selection; never heldout."""
import argparse
from contextlib import contextmanager
from copy import deepcopy
import math
import os
from pathlib import Path
import time

import numpy as np
import torch
from safetensors import safe_open
from safetensors.torch import load_file, save_file

from fp32_reference import ROOT, cached_logits, configure_runtime, environment, load_model, read_json, source_snapshot, write_json
from ptq_eval import aggregate_nll, evaluate_piqa, evaluate_ppl, full_logits, score_targets
from ptq_finalize import distribution_diagnostic, greedy
from ptq_fake_quant import PTQAdapter
from ptq_intermediate_calibrate import full_signed_range
from ptq_contract import (ContractAdapter, Format, compile_silu, decoded, encode,
                          encode_multiplier, fit_silu, rescale, rope_rom,
                          rms_seed_lut, round_divide_scalar, softmax_lut)


def atomic_json(path, value):
    temporary = path.with_suffix(".tmp")
    write_json(temporary, value)
    temporary.replace(path)


_QUALIFICATION_STATUSES = {"qualified_selection", "rejected_full_ppl",
                           "rejected_piqa_or_cache"}


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


def search_candidate_errors(report):
    errors = []
    if report.get("stages", {}).get("search") != "measured":
        errors.append("search stage is not measured")
    combinations = report.get("combinations")
    if not isinstance(combinations, dict) or not combinations:
        errors.append("no candidate combinations are available")
    return errors


def require_search_candidates(report):
    errors = search_candidate_errors(report)
    if errors:
        raise RuntimeError("qualification prerequisites are incomplete: " + "; ".join(errors))


def qualification_errors(report, *, require_stage=False):
    """Return missing or inconsistent selection evidence for every candidate."""
    errors = search_candidate_errors(report)
    stages = report.get("stages", {})
    if require_stage and stages.get("qualification") != "measured":
        errors.append("qualification stage is not measured")
    combinations = report.get("combinations")
    if not isinstance(combinations, dict) or not combinations:
        return errors

    for name, entry in combinations.items():
        if not isinstance(entry, dict):
            errors.append(f"{name}: candidate entry is not an object")
            continue
        status = entry.get("status")
        if status not in _QUALIFICATION_STATUSES:
            errors.append(f"{name}: missing or invalid terminal quality status")
            continue
        full_ppl = entry.get("full_ppl")
        if (not isinstance(full_ppl, dict)
                or not all(k in full_ppl for k in ("ppl", "nll", "tokens", "windows", "per_window"))
                or full_ppl.get("windows") != 64 or full_ppl.get("tokens") != 32704
                or len(full_ppl.get("per_window", [])) != 64
                or any(not isinstance(row, dict) or row.get("tokens") != 511
                       or not row.get("id") or not isinstance(row.get("nll"),(int,float))
                       or not math.isfinite(row["nll"])
                       for row in full_ppl.get("per_window", []))):
            errors.append(f"{name}: full-selection PPL evidence is incomplete")
            continue
        if any(not isinstance(full_ppl[field], (int,float)) or not math.isfinite(full_ppl[field])
               for field in ("ppl", "nll")):
            errors.append(f"{name}: full-selection PPL evidence contains an invalid result")
            continue
        if (len({row["id"] for row in full_ppl["per_window"]}) != 64
                or not math.isclose(sum(row["nll"] for row in full_ppl["per_window"]),
                                    full_ppl["nll"], rel_tol=1e-10, abs_tol=1e-7)
                or not math.isclose(math.exp(full_ppl["nll"]/full_ppl["tokens"]),
                                    full_ppl["ppl"], rel_tol=1e-10, abs_tol=1e-12)):
            errors.append(f"{name}: full-selection PPL aggregate does not match its 64 windows")
            continue
        relative_ppl = entry.get("relative_ppl_increase_vs_fp32")
        if not isinstance(relative_ppl, (int, float)) or not math.isfinite(relative_ppl):
            errors.append(f"{name}: relative full-selection PPL result is missing")
            continue
        if not math.isclose(relative_ppl, full_ppl["ppl"]/22.574714201210707-1,
                            rel_tol=1e-10, abs_tol=1e-12):
            errors.append(f"{name}: full-selection PPL ratio does not match the pinned FP32 reference")
            continue
        if status == "rejected_full_ppl":
            if relative_ppl <= .05:
                errors.append(f"{name}: rejected_full_ppl status contradicts its measured gate")
            continue
        if relative_ppl > .05:
            errors.append(f"{name}: non-PPL-rejected status violates the full-selection PPL gate")
            continue

        piqa = entry.get("piqa")
        piqa_drop = entry.get("piqa_drop_vs_fp32")
        cache = entry.get("cache")
        cache_relative = entry.get("cache_relative_ppl_increase")
        if (not isinstance(piqa, dict) or piqa.get("questions") != 919
                or len(piqa.get("per_question", [])) != 919
                or not isinstance(piqa_drop, (int, float)) or not math.isfinite(piqa_drop)):
            errors.append(f"{name}: PIQA quality evidence is incomplete")
            continue
        piqa_rows = piqa["per_question"]
        if (not isinstance(piqa.get("correct"), int)
                or not isinstance(piqa.get("accuracy"), (int,float)) or not math.isfinite(piqa["accuracy"])
                or any(not isinstance(row, dict) or "id" not in row or "correct" not in row for row in piqa_rows)
                or len({row["id"] for row in piqa_rows}) != 919
                or sum(bool(row["correct"]) for row in piqa_rows) != piqa.get("correct")
                or not math.isclose(piqa.get("accuracy", float("nan")), piqa["correct"]/919,
                                    rel_tol=1e-10, abs_tol=1e-12)
                or not math.isclose(piqa_drop, 625/919-piqa["accuracy"],
                                    rel_tol=1e-10, abs_tol=1e-12)):
            errors.append(f"{name}: PIQA aggregate does not match its 919 traceable questions or pinned reference")
            continue
        if not isinstance(cache, dict) or not isinstance(cache_relative, dict):
            errors.append(f"{name}: cache quality evidence is incomplete")
            continue
        runs = cache.get("runs")
        regimes = cache.get("regimes")
        if (not isinstance(runs, list) or len(runs) != 16
                or any(not isinstance(run, dict) or run.get("tokens") != 64
                       or not isinstance(run.get("nll"),(int,float)) or not math.isfinite(run["nll"])
                       for run in runs)
                or not isinstance(regimes, dict) or not {"32", "448"}.issubset(regimes)
                or any(not isinstance(regimes.get(regime), dict)
                       or regimes[regime].get("tokens") != 512
                       or any(not isinstance(regimes[regime].get(field),(int,float))
                              or not math.isfinite(regimes[regime][field]) for field in ("nll","ppl"))
                       for regime in ("32", "448"))):
            errors.append(f"{name}: cache evidence must contain 16 traceable runs and 512 targets per regime")
            continue
        prefill_counts = {prefill:sum(run.get("prefill") == prefill for run in runs) for prefill in (32,448)}
        case_counts = {}
        invalid_run = False
        for run in runs:
            if run.get("prefill") not in (32,448) or run.get("decode") != 64 or not run.get("id"):
                errors.append(f"{name}: cache run has invalid identity or regime")
                invalid_run = True
                break
            case_counts[run["id"]] = case_counts.get(run["id"],0)+1
        if invalid_run:
            continue
        if prefill_counts != {32:8,448:8} or len(case_counts) != 8 or set(case_counts.values()) != {2}:
            errors.append(f"{name}: cache runs do not preserve eight paired 32/448 records")
            continue
        for regime,prefill in (("32",32),("448",448)):
            regime_runs = [run for run in runs if run["prefill"] == prefill]
            total_nll = sum(run["nll"] for run in regime_runs)
            if (not math.isclose(total_nll,regimes[regime]["nll"],rel_tol=1e-10,abs_tol=1e-7)
                    or not math.isclose(math.exp(total_nll/512),regimes[regime]["ppl"],
                                        rel_tol=1e-10,abs_tol=1e-12)):
                errors.append(f"{name}: cache aggregate for prefill {prefill} does not match its eight runs")
                break
        if errors and errors[-1].startswith(f"{name}: cache aggregate"):
            continue
        if set(cache_relative) != {"32", "448"}:
            errors.append(f"{name}: cache PPL evidence must cover prefill 32 and 448")
            continue
        if any(not isinstance(value, (int, float)) or not math.isfinite(value)
               for value in cache_relative.values()):
            errors.append(f"{name}: cache PPL evidence contains an invalid result")
            continue
        cache_references = {"32":26.676072498453824,"448":12.019438254052904}
        if any(not isinstance(regimes[regime].get("ppl"), (int,float))
               or not math.isfinite(regimes[regime]["ppl"])
               or not math.isclose(cache_relative[regime],
                                regimes[regime]["ppl"]/cache_references[regime]-1,
                                rel_tol=1e-10, abs_tol=1e-12) for regime in ("32","448")):
            errors.append(f"{name}: cache PPL ratios do not match the pinned FP32 references")
            continue
        if "greedy" not in entry:
            errors.append(f"{name}: greedy selection check is missing")
            continue
        passed = piqa_drop <= .02 and max(cache_relative.values()) <= .05
        expected = "qualified_selection" if passed else "rejected_piqa_or_cache"
        if status != expected:
            errors.append(f"{name}: {status} status contradicts measured PIQA/cache gates")
    return errors


def require_qualification(report, *, require_stage=False):
    errors = qualification_errors(report, require_stage=require_stage)
    if errors:
        raise RuntimeError("selection qualification is incomplete: " + "; ".join(errors))


def require_export_artifacts(report, output_dir):
    """Check that the full weight bundle and every candidate export are usable."""
    output_dir = Path(output_dir)
    errors = []
    weights_path = output_dir / "weights.safetensors"
    prepared = report.get("prepared_weights")
    if not isinstance(prepared, dict):
        errors.append("prepared weight metadata is missing")
    if not weights_path.is_file() or weights_path.stat().st_size == 0:
        errors.append("weights.safetensors is missing or empty")
    elif isinstance(prepared, dict):
        try:
            with safe_open(str(weights_path), framework="pt", device="cpu") as bundle:
                keys = bundle.keys()
                byte_count = 0
                wrong_dtype = []
                for key in keys:
                    view = bundle.get_slice(key)
                    shape = view.get_shape()
                    if view.get_dtype() != "I8":
                        wrong_dtype.append(key)
                    byte_count += math.prod(shape)
                if len(keys) != prepared.get("matrices"):
                    errors.append("prepared weight matrix count does not match weights.safetensors")
                if byte_count != prepared.get("payload_bytes"):
                    errors.append("prepared weight payload count does not match weights.safetensors")
                if wrong_dtype:
                    errors.append("prepared weights are not all signed INT8")
        except Exception as exc:
            errors.append(f"weights.safetensors cannot be read: {exc}")

    combinations = report.get("combinations", {})
    for name, entry in combinations.items():
        directory = output_dir / name
        config_path = directory / "config.json"
        coefficient_path = directory / "coefficients.safetensors"
        validation = entry.get("coefficient_bundle_validation") if isinstance(entry, dict) else None
        if not isinstance(validation, dict) or validation.get("status") != "passed":
            errors.append(f"{name}: runtime coefficient equality check is missing")
        if not config_path.is_file() or config_path.stat().st_size == 0:
            errors.append(f"{name}: config.json is missing or empty")
        else:
            try:
                config = read_json(config_path)
                if config.get("quality_status") != entry.get("status"):
                    errors.append(f"{name}: exported quality status does not match qualification")
                if config.get("weights") != "../weights.safetensors":
                    errors.append(f"{name}: exported config has no valid shared weights mapping")
                elif not (directory/config["weights"]).is_file():
                    errors.append(f"{name}: shared weight mapping does not resolve to an artifact")
                if config.get("coefficients") != "coefficients.safetensors":
                    errors.append(f"{name}: exported config has no valid coefficient mapping")
                if not isinstance(config.get("frozen_source_qparams"), str) or not (directory/config["frozen_source_qparams"]).is_file():
                    errors.append(f"{name}: frozen source qparams mapping does not resolve to an artifact")
                if not isinstance(config.get("formats"), dict) or not config["formats"]:
                    errors.append(f"{name}: exported format mapping is missing")
                if config.get("software_adapter_role") != "host_preparation_simulator":
                    errors.append(f"{name}: exported software adapter role is missing")
                if config.get("software_adapter_loads_coefficient_bundle") is not False:
                    errors.append(f"{name}: adapter bundle-loading status is ambiguous")
                if config.get("coefficient_bundle_validation") != "export tensors are checked against deterministic runtime multiplier/table compilation":
                    errors.append(f"{name}: exported runtime coefficient check description is missing")
            except Exception as exc:
                errors.append(f"{name}: config.json cannot be read: {exc}")
        if not coefficient_path.is_file() or coefficient_path.stat().st_size == 0:
            errors.append(f"{name}: coefficients.safetensors is missing or empty")
        else:
            try:
                with safe_open(str(coefficient_path), framework="pt", device="cpu") as bundle:
                    if not bundle.keys():
                        errors.append(f"{name}: coefficients.safetensors contains no tensors")
            except Exception as exc:
                errors.append(f"{name}: coefficients.safetensors cannot be read: {exc}")
    if errors:
        raise RuntimeError("export artifacts are incomplete: " + "; ".join(errors))


def runtime_coefficient_bundle(config, formats, coefficient_sources, epsilon_values):
    """Recompile exactly the integer coefficients/tables consumed at runtime."""
    bits = config["coefficient_bits"]
    result = {}
    for key, value in coefficient_sources.items():
        multiplier, shift = encode_multiplier(value, bits)
        result[key+".M"] = multiplier.to(torch.int32).contiguous()
        result[key+".shift"] = shift_container(shift)

    rope_bits = config["nonlinear"]["rope"]["coefficient_bits"]
    cosine, sine = rope_rom(rope_bits)
    result["rope.cos"] = cosine.to(torch.int8 if rope_bits == 8 else torch.int16)
    result["rope.sin"] = sine.to(torch.int8 if rope_bits == 8 else torch.int16)

    softmax = config["nonlinear"]["softmax"]
    result["softmax.exp_lut"] = softmax_lut(softmax["c"], softmax["entries"]).to(torch.uint8)
    rms = config["nonlinear"]["rms"]
    seed_entries = rms.get("seed_entries", 64)
    result["rms.seed_lut"] = rms_seed_lut(seed_entries).to(torch.int16)
    for name, value in epsilon_values.items():
        result[name+".epsilon"] = torch.tensor(value, dtype=torch.int32)

    pwl_options = config["nonlinear"]["silu"]
    table = fit_silu(pwl_options["segments"], pwl_options.get("threshold", 8), bits)
    compiled_tables = {}
    for name in (f"model.layers.{index}.mlp" for index in range(30)):
        input_spec, output_spec = formats[name+".gate_proj.output"], formats[name+".silu_output"]
        input_format = Format(input_spec["bits"], input_spec["scale"], input_spec.get("axis"), not input_spec["signed"])
        output_format = Format(output_spec["bits"], output_spec["scale"], output_spec.get("axis"), not output_spec["signed"])
        compiled = compile_silu(input_format.scale, output_format, table, bits)
        compiled_tables[name] = compiled
        for key, value in compiled.items():
            result[name+".pwl."+key] = (shift_container(value) if key == "shifts"
                                         else torch.tensor(value, dtype=torch.int32))
    return result, table, compiled_tables


def require_runtime_bundle_match(config, exported_config, coefficient_sources, epsilon_values, bundle):
    expected, expected_reference, expected_compiled = runtime_coefficient_bundle(
        config, exported_config["formats"], coefficient_sources, epsilon_values)
    if set(bundle) != set(expected):
        missing = sorted(set(expected)-set(bundle))
        extra = sorted(set(bundle)-set(expected))
        raise RuntimeError(f"runtime coefficient bundle key mismatch; missing={missing[:4]}, extra={extra[:4]}")
    mismatches = [key for key, value in expected.items()
                  if value.dtype != bundle[key].dtype or value.shape != bundle[key].shape
                  or not torch.equal(value, bundle[key])]
    if mismatches:
        raise RuntimeError("exported coefficients differ from runtime compilation: " + ", ".join(mismatches[:8]))
    if exported_config.get("pwl_reference") != expected_reference:
        raise RuntimeError("exported PWL reference differs from the runtime fitter")
    if exported_config.get("pwl_compiled") != expected_compiled:
        raise RuntimeError("exported PWL tables differ from the runtime compiler")


def selection_summary(qualified):
    dimensions = ("boundary_payload_bytes_per_512", "runtime_coefficient_bundle_bytes",
                  "maximum_boundary_container_bits")
    pareto = []
    for name, entry in qualified.items():
        resource = entry["resources"]
        dominated = any(
            all(other["resources"][dimension] <= resource[dimension] for dimension in dimensions)
            and any(other["resources"][dimension] < resource[dimension] for dimension in dimensions)
            for other_name, other in qualified.items() if other_name != name)
        if not dominated:
            pareto.append(name)
    return {"qualified": list(qualified), "pareto": pareto,
            "default": min(pareto, key=lambda name: qualified[name]["resources"]["boundary_payload_bytes_per_512"]) if pareto else None,
            "basis": "minimum boundary payload among measured non-dominated qualified alternatives; no synthesis-area claim"}


class Campaign:
    def __init__(self, args):
        self.args = args
        args.output_dir.mkdir(parents=True, exist_ok=True)
        self.path = args.output_dir/"campaign.json"
        self.report = read_json(self.path) if self.path.exists() else {
            "backend": "stage_specific_integer_contract_simulation",
            "large_reduction_backends":{"isolated":"frozen FP32 reference MACs",
                                        "combined":"exact integer sums via FP64 with absolute-product bounds <2**53"},
            "heldout_used": False, "seed": 1234, "threads": 1,
            "thresholds": {"ppl_relative_to_fp32_max": .05, "piqa_drop_max": .02},
            "stages": {}, "isolated": {}, "family": {}, "combinations": {}}
        self.started = time.monotonic()
        self.selection = read_json(ROOT/"data/wikitext_selection.json")
        self.questions = read_json(ROOT/"data/piqa_selection.json")
        self.cases = read_json(ROOT/"data/cache_cases.json")
        self.reference = read_json(ROOT/"results/ptq/fp32.json")
        self.model, self.tokenizer = load_model(source_snapshot(args.cache_dir, args.offline))
        candidate = ROOT/"candidates/w8a12kv8_smoothquant"
        self.baseline = PTQAdapter(self.model, read_json(candidate/"config.json"))
        self.baseline.load_qparams(candidate/"qparams.safetensors", recompute_weights=False)
        full_signed_range(self.baseline)
        self.baseline.set_mode("quantize")
        self.statistics = read_json(ROOT/"results/numerical/intermediate_calibration.json")["points"]
        self.adapter = ContractAdapter(self.model, self.baseline, self.statistics)
        self.report.setdefault("environment", environment())
        self.report["backend"] = "stage_specific_integer_contract_simulation"
        self.report.setdefault("large_reduction_backends",{"isolated":"frozen FP32 reference MACs",
            "combined":"exact integer sums via FP64; absolute product sums <2**53"})

    def save(self):
        self.report["last_session_seconds"] = round(time.monotonic()-self.started, 3)
        atomic_json(self.path, self.report)

    @contextmanager
    def native_reference(self):
        current = [(module,module.forward) for module,_ in self.adapter.bindings]
        for module,original in reversed(self.adapter.bindings): module.forward = original
        try:
            with self.baseline.native(): yield
        finally:
            for module,forward in current: module.forward = forward

    def trial(self, name, *, points=None, nonlinear=None, integer=False, coefficient_bits=24):
        return {"name": name, "points": points or {}, "nonlinear": nonlinear or {},
                "integer_coefficients": integer, "coefficient_bits": coefficient_bits,
                "metrics": True}

    def quick(self, config, records=None):
        self.adapter.set_trial(config)
        started = time.monotonic()
        parts = []
        with torch.inference_mode():
            for record in self.selection[:1] if records is None else records:
                logits = full_logits(self.model, record["input_ids"])
                parts.append(score_targets(logits, record["input_ids"]))
        nll, tokens = sum(p[0] for p in parts), sum(p[1] for p in parts)
        result = {"nll": nll, "tokens": tokens, "ppl": math.exp(nll/tokens),
                  "seconds": round(time.monotonic()-started, 3),
                  "metrics": deepcopy(self.adapter.point_metrics)}
        if "baseline" in self.report:
            baseline = self.report["baseline"]["ppl"]["per_window"][:len(parts)]
            reference_nll = sum(v["nll"] for v in baseline)
            result["delta_mean_nll"] = (nll-reference_nll)/tokens
            result["relative_ppl_change_vs_frozen"] = math.expm1(result["delta_mean_nll"])
        print(f"{config['name']}: PPL={result['ppl']:.6f}, dNLL={result.get('delta_mean_nll',0):+.6g}, {result['seconds']:.2f}s", flush=True)
        return result

    def replay_stage(self):
        if self.report["stages"].get("replay") == "measured":
            return
        self.adapter.set_trial(self.trial("local_replay_capture"))
        self.adapter.collect_replay = True
        self.quick(self.adapter.trial)
        self.adapter.collect_replay = False
        rows = {}
        for name, value in self.adapter.replay.items():
            row = {}
            for bits in (8, 12, 16, 24):
                fmt = self.adapter.make_format(name, {"bits": bits})
                q, raw = encode(value, fmt)
                reconstructed = decoded(q, fmt)
                error = reconstructed.double()-value.double()
                row[str(bits)] = {"mse": float(error.square().mean()), "max_abs_error": float(error.abs().max()),
                    "zero_fraction": float((q == 0).double().mean()),
                    "clip_fraction": float(((raw < fmt.bounds[0]) | (raw > fmt.bounds[1])).double().mean())}
            source = self.adapter.make_format(name, {"bits": 24})
            source_q = encode(value, source)[0]
            target = self.adapter.make_format(name, {"bits": 8})
            ratio = source.broadcast(value)/target.broadcast(value)
            oracle = torch.round(source_q.double()*ratio).long().clamp(*target.bounds)
            row["coefficient_precision"] = {}
            for bits in (16, 24, 31):
                got = rescale(source_q, ratio, bits).clamp(*target.bounds)
                row["coefficient_precision"][str(bits)] = {"different_codes": int((got != oracle).sum()),
                                                          "elements": got.numel(), "max_code_error": int((got-oracle).abs().max())}
            rows[name] = row
        self.report["local_replay"] = rows
        self.report["stages"]["replay"] = "measured"
        self.adapter.replay.clear()
        self.save()

    def isolated_stage(self):
        rows = self.report["isolated"].setdefault("boundaries", {})
        for i, (name, family) in enumerate(self.adapter.inventory.items()):
            row = rows.setdefault(name, {"family": family, "trials": {}})
            for bits in (8, 12, 16):
                key = str(bits)
                if key not in row["trials"]:
                    row["trials"][key] = self.quick(self.trial(f"point:{i+1}/{len(self.adapter.inventory)}:{name}:{bits}", points={name: {"bits": bits}}))
                    self.save()
                if row["trials"][key]["delta_mean_nll"] <= .0005:
                    break
            if family == "residual" and row["trials"]["8"]["delta_mean_nll"] > .0005:
                for bits in (8, 12):
                    key = f"per_channel_{bits}"
                    if key not in row["trials"]:
                        row["trials"][key] = self.quick(self.trial(f"point:{name}:{key}", points={name:{"bits":bits,"policy":"per_channel"}}))
                        self.save()
                    if row["trials"][key]["delta_mean_nll"] <= .0005:
                        break
        nl = self.report["isolated"].setdefault("nonlinear", {})
        instances = []
        for name, module in self.model.named_modules():
            if name.endswith(("input_layernorm", "post_attention_layernorm")) or name == "model.norm":
                instances.append((name, {"seed_entries":64}, "rms"))
        for i in range(30):
            prefix = f"model.layers.{i}"
            instances += [(prefix+".self_attn.rope", {"coefficient_bits":16}, "rope"),
                          (prefix+".self_attn.softmax", {"c":8,"entries":32,"probability_bits":8}, "softmax"),
                          (prefix+".mlp.silu", {"segments":16,"threshold":8}, "silu")]
        for name, options, family in instances:
            if name not in nl:
                nl[name] = {"family":family, "options":options,
                            **self.quick(self.trial(f"nonlinear:{name}", nonlinear={name:options}))}
                self.save()
        self.report["stages"]["isolated"] = "measured"
        self.save()

    def family_stage(self):
        trials = []
        for family in sorted(set(self.adapter.inventory.values())):
            points = {n:{"bits":8} for n, f in self.adapter.inventory.items() if f == family}
            trials.append(self.trial(f"family:{family}:8", points=points))
        trials += [self.trial("nonlinear:rms64", nonlinear={"rms":{"seed_entries":64}}),
                   self.trial("nonlinear:rms64_t32", nonlinear={"rms":{"seed_entries":64,"t_fractional_bits":32}}),
                   self.trial("nonlinear:rms64_t24", nonlinear={"rms":{"seed_entries":64,"t_fractional_bits":24}}),
                   self.trial("nonlinear:rope16", nonlinear={"rope":{"coefficient_bits":16}}),
                   self.trial("nonlinear:rope12", nonlinear={"rope":{"coefficient_bits":12}}),
                   self.trial("nonlinear:rope8", nonlinear={"rope":{"coefficient_bits":8}})]
        for c in (6, 8, 10):
            trials.append(self.trial(f"nonlinear:softmax32_c{c}_p8", nonlinear={"softmax":{"entries":32,"c":c,"probability_bits":8}}))
        trials += [self.trial("nonlinear:softmax32_c8_p12", nonlinear={"softmax":{"entries":32,"c":8,"probability_bits":12}}),
                   self.trial("nonlinear:softmax32_c8_p16", nonlinear={"softmax":{"entries":32,"c":8,"probability_bits":16}})]
        for segments, threshold in ((8,6),(16,8),(32,8)):
            trials.append(self.trial(f"nonlinear:silu{segments}_t{threshold}", nonlinear={"silu":{"segments":segments,"threshold":threshold}}))
        for config in trials:
            name = config["name"]
            if name not in self.report["family"]:
                self.report["family"][name] = {"config":config, **self.quick(config, self.selection[:8])}
                self.save()
        soft = self.report["family"]
        cutoff = min((6,8,10),key=lambda c:soft[f"nonlinear:softmax32_c{c}_p8"]["delta_mean_nll"])
        if cutoff != 8:
            for pb in (12,16):
                config = self.trial(f"nonlinear:softmax32_c{cutoff}_p{pb}",nonlinear={"softmax":{"entries":32,"c":cutoff,"probability_bits":pb}})
                if config["name"] not in soft:
                    soft[config["name"]] = {"config":config,**self.quick(config,self.selection[:8])}
                    self.save()
        # Entries64 only when P precision alone leaves a material LUT error.
        best32 = min((n for n in soft if n.startswith("nonlinear:softmax32") and n.endswith("p16")),key=lambda n:soft[n]["delta_mean_nll"])
        if soft[best32]["delta_mean_nll"] > .002:
            best_cutoff = soft[best32]["config"]["nonlinear"]["softmax"]["c"]
            config = self.trial(f"nonlinear:softmax64_c{best_cutoff}_p16", nonlinear={"softmax":{"entries":64,"c":best_cutoff,"probability_bits":16}})
            if config["name"] not in soft:
                soft[config["name"]] = {"config":config, **self.quick(config,self.selection[:8])}
                self.save()
        soft_names = [n for n in soft if n.startswith("nonlinear:softmax") and n.endswith("p16")]
        best = min(soft_names,key=lambda n:soft[n]["delta_mean_nll"])
        best = min((n for n in soft_names if soft[n]["delta_mean_nll"] <= soft[best]["delta_mean_nll"]+.001),
                   key=lambda n:soft[n]["config"]["nonlinear"]["softmax"]["entries"])
        options = {**soft[best]["config"]["nonlinear"]["softmax"],"fused":True}
        options.pop("probability_bits",None)
        config = self.trial("nonlinear:softmax_fused",nonlinear={"softmax":options})
        if config["name"] not in soft:
            soft[config["name"]] = {"config":config,**self.quick(config,self.selection[:8])}
            self.save()
        rms_names = ("nonlinear:rms64_t24","nonlinear:rms64_t32","nonlinear:rms64")
        viable = [n for n in rms_names if soft[n]["delta_mean_nll"] <= soft["nonlinear:rms64"]["delta_mean_nll"]+.001]
        selected = min(viable,key=lambda n:soft[n]["config"]["nonlinear"]["rms"].get("t_fractional_bits",40))
        ft = soft[selected]["config"]["nonlinear"]["rms"].get("t_fractional_bits",40)
        config = self.trial(f"nonlinear:rms32_t{ft}",nonlinear={"rms":{"seed_entries":32,"t_fractional_bits":ft}})
        if config["name"] not in soft:
            soft[config["name"]] = {"config":config,**self.quick(config,self.selection[:8])}
            self.save()
        self.report["stages"]["family"] = "measured"
        self.save()

    def build_combinations(self):
        family = self.report["family"]
        soft_names = [n for n in family if n.startswith("nonlinear:softmax") and n.endswith(("p12","p16"))]
        soft_name = min(soft_names, key=lambda n: family[n]["delta_mean_nll"])
        soft_options = deepcopy(family[soft_name]["config"]["nonlinear"]["softmax"])
        rope_name = min((n for n in family if n.startswith("nonlinear:rope") and family[n]["delta_mean_nll"] <= .001), default="nonlinear:rope16", key=lambda n: family[n]["config"]["nonlinear"]["rope"]["coefficient_bits"])
        silu_name = min((n for n in family if n.startswith("nonlinear:silu")),key=lambda n: family[n]["delta_mean_nll"])
        nonlinear = {"rms":{"seed_entries":64}, "rope":deepcopy(family[rope_name]["config"]["nonlinear"]["rope"]),
                     "softmax":soft_options,"silu":deepcopy(family[silu_name]["config"]["nonlinear"]["silu"])}
        high = {n:{"bits":24 if f == "residual" else 16} for n,f in self.adapter.inventory.items()}
        for n,f in self.adapter.inventory.items():
            if f == "probability": high[n] = {"bits":soft_options["probability_bits"]}
        candidates = [self.trial("combined_high", points=high, nonlinear=deepcopy(nonlinear), integer=True)]
        candidates[0]["nonlinear"]["rope"] = {"coefficient_bits":16}
        rms_names = [n for n in ("nonlinear:rms64_t24","nonlinear:rms64_t32","nonlinear:rms64")
                     if family[n]["delta_mean_nll"] <= family["nonlinear:rms64"]["delta_mean_nll"]+.001]
        rms_name = min(rms_names,key=lambda n:family[n]["config"]["nonlinear"]["rms"].get("t_fractional_bits",40))
        nonlinear["rms"] = deepcopy(family[rms_name]["config"]["nonlinear"]["rms"])
        seed32 = next(n for n in family if n.startswith("nonlinear:rms32_t"))
        if family[seed32]["delta_mean_nll"] <= family[rms_name]["delta_mean_nll"]+.0005:
            nonlinear["rms"] = deepcopy(family[seed32]["config"]["nonlinear"]["rms"])
        low_soft = min((n for n in soft_names if family[n]["delta_mean_nll"] <= family[soft_name]["delta_mean_nll"]+.001),
                       key=lambda n:(family[n]["config"]["nonlinear"]["softmax"]["entries"],family[n]["config"]["nonlinear"]["softmax"]["probability_bits"]))
        nonlinear["softmax"] = deepcopy(family[low_soft]["config"]["nonlinear"]["softmax"])
        low_silu = min((n for n in family if n.startswith("nonlinear:silu") and family[n]["delta_mean_nll"] <= family[silu_name]["delta_mean_nll"]+.001),
                       key=lambda n:family[n]["config"]["nonlinear"]["silu"]["segments"])
        nonlinear["silu"] = deepcopy(family[low_silu]["config"]["nonlinear"]["silu"])
        chosen = {}
        for name, row in self.report["isolated"]["boundaries"].items():
            passing = [(key,result) for key,result in row["trials"].items() if result["delta_mean_nll"] <= .0005]
            key = min(passing,key=lambda item:(int(item[0].split('_')[-1]),"per_channel" in item[0]))[0] if passing else "16"
            chosen[name] = {"bits":int(key.split('_')[-1]), **({"policy":"per_channel"} if key.startswith("per_channel") else {})}
            if row["family"] == "probability": chosen[name] = {"bits":nonlinear["softmax"]["probability_bits"]}
        candidates.append(self.trial("combined_mixed",points=chosen,nonlinear=nonlinear,integer=True,coefficient_bits=16))
        # Conservative exception set: do not spend the entire quality budget on
        # individually small errors that add across thirty decoder layers.
        guarded = deepcopy(chosen)
        for name, spec in guarded.items():
            row = self.report["isolated"]["boundaries"][name]
            if spec["bits"] == 8 and row["trials"]["8"]["delta_mean_nll"] > .00003:
                spec["bits"] = 12
            if row["family"] == "residual" and self.statistics[name]["maximum"] > 1000:
                spec.update({"bits":16,"policy":"per_channel"})
        fused = deepcopy(nonlinear)
        fused["softmax"] = deepcopy(family["nonlinear:softmax_fused"]["config"]["nonlinear"]["softmax"])
        guarded = {name:spec for name,spec in guarded.items() if self.adapter.inventory[name] != "probability"}
        candidates.append(self.trial("combined_guarded_fused",points=guarded,nonlinear=fused,integer=True))
        for candidate in candidates:
            candidate["mac_dtype"] = "float64"
            candidate["mac_exactness_bound"] = "integer product absolute sums <2**53: Linear1536*2048*128; QK64*2**23*128; PV512*65535*128"
        return candidates

    def search_stage(self):
        for config in self.build_combinations():
            name = config["name"]
            if name not in self.report["combinations"]:
                config["check_mac"] = True
                result = self.quick(config, self.selection[:8])
                self.report["combinations"][name] = {"config":config,"quick":result,
                                                        "mac_samples":deepcopy(self.adapter.mac_checks)}
                self.adapter.mac_checks.clear()
                self.save()
        self.report["stages"]["search"] = "measured"
        self.save()

    def qualify_stage(self):
        # A stage with no actual candidates is not evidence of qualification.
        require_search_candidates(self.report)
        fp = self.reference
        for name, entry in self.report["combinations"].items():
            config = entry["config"]
            self.adapter.set_trial({**config,"metrics":False,"check_mac":False})
            if "full_ppl" not in entry:
                entry["full_ppl"] = evaluate_ppl(self.model,self.selection)
                entry["relative_ppl_increase_vs_fp32"] = entry["full_ppl"]["ppl"]/fp["ppl"]["ppl"]-1
                entry["relative_ppl_increase_vs_frozen"] = entry["full_ppl"]["ppl"]/self.report["baseline"]["ppl"]["ppl"]-1
                self.save()
            if entry["relative_ppl_increase_vs_fp32"] > .05:
                entry["status"] = "rejected_full_ppl"
                self.save()
                continue
            if "piqa" not in entry:
                entry["piqa"] = evaluate_piqa(self.model,self.questions)
                entry["piqa_drop_vs_fp32"] = fp["piqa"]["accuracy"]-entry["piqa"]["accuracy"]
                self.save()
            if "cache" not in entry:
                entry["cache"] = self.cache_diagnostics()
                entry["cache_relative_ppl_increase"] = {
                    regime: result["ppl"]/fp["cache"]["regimes"][regime]["ppl"]-1
                    for regime,result in entry["cache"]["regimes"].items()}
                for row,reference in zip(entry["cache"]["runs"],fp["cache"]["runs"]):
                    row["relative_ppl_increase_vs_fp32"] = math.expm1((row["nll"]-reference["nll"])/row["tokens"])
                self.save()
            passed = entry["piqa_drop_vs_fp32"] <= .02 and max(entry["cache_relative_ppl_increase"].values()) <= .05
            entry["status"] = "qualified_selection" if passed else "rejected_piqa_or_cache"
            if "greedy" not in entry:
                prompts = [record["input_ids"][:32] for record in self.selection[:2]]
                if "greedy_fp32" not in self.report:
                    with self.native_reference(): self.report["greedy_fp32"] = greedy(self.model,self.tokenizer,prompts,max_new=32)
                entry["greedy"] = greedy(self.model,self.tokenizer,prompts,max_new=32)
                self.save()
            self.save()
        # Require a terminal, gate-consistent result and the relevant evidence
        # for every candidate before persisting the stage as measured.
        require_qualification(self.report)
        self.report["stages"]["qualification"] = "measured"
        self.save()

    def cache_diagnostics(self):
        details = []
        for case in self.cases:
            record = self.selection[case["selection_index"]]
            for regime in case["regimes"]:
                prefill,decode = regime["prefill"],regime["decode"]
                ids = record["input_ids"][:regime["input_length"]]
                rows = sorted(set((0,prefill-1,prefill,len(ids)-2,len(ids)-1)))
                with self.native_reference(): reference = full_logits(self.model,ids)[rows].numpy().copy()
                full = full_logits(self.model,ids).numpy()
                cached = cached_logits(self.model,ids,prefill)
                nll,count = score_targets(cached,ids,prefill,prefill+decode)
                full_nll,_ = score_targets(full,ids,prefill,prefill+decode)
                difference = np.abs(full-cached)
                changed = full != cached
                delta_logits = float(self.adapter.formats["lm_head.output"].scale)
                code_difference = np.rint(full[changed].astype(np.float64)/delta_logits)-np.rint(cached[changed].astype(np.float64)/delta_logits)
                different_codes = int(np.count_nonzero(code_difference))
                if different_codes:
                    raise AssertionError(f"exact combined full/cache logit codes differ: {case['id']} prefill={prefill}, {different_codes} codes")
                details.append({"id":case["id"],**regime,"nll":nll,"tokens":count,"full_nll":full_nll,
                    "diagnostic_rows":rows,"full_fp32":distribution_diagnostic(reference,full[rows]),
                    "cache_fp32":distribution_diagnostic(reference,cached[rows]),
                    "full_cache":{"max_abs":float(difference.max()),"mean_abs":float(difference.mean()),
                                  "row_top1_agreement":float((full.argmax(-1)==cached.argmax(-1)).mean()),
                                  "different_logit_codes":different_codes,"logit_codes_bitwise_equal":different_codes == 0,
                                  "logit_elements":int(full.size)}})
                print(f"CONTRACT CACHE {case['id']} prefill={prefill} targets={count}",flush=True)
        return {"runs":details,"regimes":{str(p):aggregate_nll([(v["nll"],v["tokens"]) for v in details if v["prefill"] == p]) for p in (32,448)},
                **aggregate_nll([(v["nll"],v["tokens"]) for v in details])}

    def export_stage(self):
        # Do not prepare or expose candidate artifacts until qualification has
        # actually finished for every combination.
        require_qualification(self.report, require_stage=True)
        weights_path = self.args.output_dir/"weights.safetensors"
        if not weights_path.exists():
            weights = {}
            for weight_name,source in self.baseline.weights.items():
                fmt = Format(8,self.baseline.points[weight_name].fq.scale.double().tolist(),0)
                prepared = self.baseline.points[weight_name](self.baseline.effective_weight(weight_name))
                weights[weight_name] = encode(prepared,fmt)[0].to(torch.int8).contiguous()
            temporary = weights_path.with_suffix(".tmp")
            save_file(weights,str(temporary),metadata={"preparation":"pinned full-signed frozen PyTorch FQ; recover exact integer codes", "shared_embedding_lm_head":"one tensor"})
            temporary.replace(weights_path)
            del weights
        self.report["prepared_weights"] = {"path":"weights.safetensors","matrices":len(self.baseline.weights),
            "payload_bytes":sum(w.numel() for w in self.baseline.weights.values()),
            "preparation":"full-signed frozen baseline FQ codes; no FP64 source re-quantization"}
        # Export all measured alternatives, including explicitly rejected ones,
        # so their concrete format and resource costs can still be reviewed.
        for name, entry in self.report["combinations"].items():
            config = entry["config"]
            self.adapter.set_trial(config)
            formats = {n:f.dictionary() for n,f in self.adapter.formats.items()}
            bundle = {}
            coefficient_sources = {}

            def coefficient(key,value):
                value = torch.as_tensor(value, dtype=torch.float64)
                coefficient_sources[key] = value.clone()
                multiplier,shift = encode_multiplier(value,config["coefficient_bits"])
                bundle[key+".M"] = multiplier.to(torch.int32).contiguous()
                bundle[key+".shift"] = shift_container(shift)

            c = config["nonlinear"]["rope"]["coefficient_bits"]
            cosine,sine = rope_rom(c)
            bundle["rope.cos"] = cosine.to(torch.int8 if c == 8 else torch.int16)
            bundle["rope.sin"] = sine.to(torch.int8 if c == 8 else torch.int16)
            options = config["nonlinear"]["softmax"]
            bundle["softmax.exp_lut"] = softmax_lut(options["c"],options["entries"]).to(torch.uint8)
            seed_entries = config["nonlinear"]["rms"].get("seed_entries",64)
            bundle["rms.seed_lut"] = rms_seed_lut(seed_entries).to(torch.int16)
            pwl_options = config["nonlinear"]["silu"]
            table = fit_silu(pwl_options["segments"],pwl_options.get("threshold",8),config["coefficient_bits"])
            compiled = {}
            aligned_norms = {}
            incoming = {}
            epsilon_values = {}
            for n, module in self.model.named_modules():
                if isinstance(module,torch.nn.Linear):
                    a = self.baseline.points[n+".input"].fq.scale.double()
                    smoothing = self.baseline.smooth_scales.get(n,torch.tensor(1.)).double()
                    # Actual incoming format is determined by the dataflow map.
                    if n == "lm_head": source = "model.norm.output"
                    elif n.endswith(("q_proj","k_proj","v_proj")): source = n.rsplit(".self_attn.",1)[0]+".input_layernorm.output"
                    elif n.endswith("o_proj"): source = n.rsplit(".",1)[0]+".context"
                    elif n.endswith(("gate_proj","up_proj")): source = n.rsplit(".mlp.",1)[0]+".post_attention_layernorm.output"
                    else: source = n.rsplit(".",1)[0]+".gate_product"
                    delta = torch.as_tensor(self.adapter.formats[source].scale,dtype=torch.float64)
                    incoming[n] = source
                    coefficient(n+".smooth",delta/(smoothing*a))
                    wname = "shared_embedding_lm_head.weight" if n == "lm_head" else n+".weight"
                    raw_scale = a*self.baseline.points[wname].fq.scale.double()
                    if n+".output" in self.adapter.formats:
                        out_scale = torch.as_tensor(self.adapter.formats[n+".output"].scale,dtype=torch.float64)
                        coefficient(n+".output",raw_scale/out_scale)
                    if n.endswith("v_proj"):
                        scale = self.baseline.points[n.removesuffix("v_proj")+"value_post_projection"].fq.scale.double().repeat_interleave(64)
                        coefficient(n+".to_v_cache",raw_scale/scale)
                elif n.endswith(("input_layernorm","post_attention_layernorm")) or n == "model.norm":
                    if n == "model.norm": source = "model.layers.29.residual_after_ffn"
                    elif n.endswith("post_attention_layernorm"):
                        source = n.removesuffix("post_attention_layernorm")+"residual_after_attention"
                    else:
                        layer = int(n.split('.')[2])
                        source = "model.embed_tokens.output" if layer == 0 else f"model.layers.{layer-1}.residual_after_ffn"
                    fmt = self.adapter.formats[source]
                    if fmt.axis is not None:
                        aligned = self.adapter.make_format(source,{"bits":24})
                        coefficient(n+".align_input",torch.as_tensor(fmt.scale,dtype=torch.float64)/float(aligned.scale))
                    else: aligned = fmt
                    aligned_norms[n] = {"source":source,**aligned.dictionary()}
                    delta = float(aligned.scale)
                    ft = config["nonlinear"]["rms"].get("t_fractional_bits",40)
                    coefficient(n+".to_t",delta*delta*(1 << ft)/576)
                    coefficient(n+".gamma_output",module.weight.detach().double()*delta/float(self.adapter.formats[n+".output"].scale))
                    epsilon_values[n] = max(1,round(module.variance_epsilon*(1 << ft)))
                    bundle[n+".epsilon"] = torch.tensor(epsilon_values[n],dtype=torch.int32)
                    bound = 1 << (aligned.bits-1)
                    square_sum = 576*bound*bound
                    tm,ts = int(bundle[n+".to_t.M"]),int(bundle[n+".to_t.shift"])
                    numerator = square_sum*tm
                    tmax = (round_divide_scalar(numerator,1 << ts) if ts >= 0 else numerator << -ts)+int(bundle[n+".epsilon"])
                    aligned_norms[n]["internal_widths"] = {
                        "square_unsigned_bits":(bound*bound).bit_length(),
                        "sum_square_unsigned_bits":square_sum.bit_length(),
                        "sum_times_multiplier_unsigned_bits":numerator.bit_length(),
                        "t_unsigned_bits":tmax.bit_length(),"t_code_max":tmax,
                        "t_code_min":int(bundle[n+".epsilon"]),"t_fractional_bits":ft,
                        "m_unsigned_bits":18,"seed_unsigned_bits":14,"u1_unsigned_bits":15,
                        "seed_index_unsigned_bits":math.ceil(math.log2(seed_entries)),
                        "gamma_output_product_signed_bits":aligned.bits+14+config["coefficient_bits"]}
            delta_embed = self.baseline.points["shared_embedding_lm_head.weight"].fq.scale.double()
            coefficient("embedding.to_residual",delta_embed/float(self.adapter.formats["model.embed_tokens.output"].scale))
            for i in range(30):
                prefix = f"model.layers.{i}.mlp"
                sfmt,ofmt = self.adapter.formats[prefix+".gate_proj.output"],self.adapter.formats[prefix+".silu_output"]
                ctable = compile_silu(sfmt.scale,ofmt,table,config["coefficient_bits"])
                compiled[prefix] = ctable
                for key,value in ctable.items():
                    bundle[prefix+".pwl."+key] = (shift_container(value) if key == "shifts"
                                                   else torch.tensor(value,dtype=torch.int32))
                coefficient(prefix+".product",float(self.adapter.formats[prefix+".silu_output"].scale)*float(self.adapter.formats[prefix+".up_proj.output"].scale)/float(self.adapter.formats[prefix+".gate_product"].scale))
                attention = f"model.layers.{i}.self_attn"
                qp = torch.as_tensor(self.adapter.formats[attention+".q_proj.output"].scale,dtype=torch.float64).reshape(9,64)[:,0]
                kp = torch.as_tensor(self.adapter.formats[attention+".k_proj.output"].scale,dtype=torch.float64).reshape(3,64)[:,0]
                qpost = torch.as_tensor(self.adapter.formats[attention+".query_post_rope"].scale,dtype=torch.float64)
                kcache = self.baseline.points[attention+".key_post_rope"].fq.scale.double()
                vcache = self.baseline.points[attention+".value_post_projection"].fq.scale.double()
                score = torch.as_tensor(self.adapter.formats[attention+".score"].scale,dtype=torch.float64)
                coefficient(attention+".q_rope_to_qk",qp/qpost)
                coefficient(attention+".k_rope_to_cache",kp/kcache)
                coefficient(attention+".qk_to_score",qpost*kcache.repeat_interleave(3)/8/score)
                coefficient(attention+".score_to_index",score*(options["entries"]-1)/options["c"])
                probability_denominator = 1 if options.get("fused") else (1 << options["probability_bits"])-1
                coefficient(attention+".pv_to_context",vcache.repeat_interleave(3)/probability_denominator/float(self.adapter.formats[attention+".context"].scale))
                layer = f"model.layers.{i}"
                for target,left,right in (
                    (layer+".residual_after_attention", "model.embed_tokens.output" if i == 0 else f"model.layers.{i-1}.residual_after_ffn",attention+".o_proj.output"),
                    (layer+".residual_after_ffn",layer+".residual_after_attention",prefix+".down_proj.output")):
                    target_scale = torch.as_tensor(self.adapter.formats[target].scale,dtype=torch.float64)
                    for branch,source in (("left",left),("right",right)):
                        source_scale = torch.as_tensor(self.adapter.formats[source].scale,dtype=torch.float64)
                        coefficient(target+"."+branch+"_to_guard",source_scale/target_scale*(1 << 20))
            output = self.args.output_dir/name
            output.mkdir(exist_ok=True)
            coefficient_path = output/"coefficients.safetensors"
            coefficient_temporary = coefficient_path.with_suffix(".tmp")
            save_file(bundle,str(coefficient_temporary))
            coefficient_temporary.replace(coefficient_path)
            exported = {**config,"formats":formats,"pwl_reference":table,"pwl_compiled":compiled,
                "weights":"../weights.safetensors","coefficients":"coefficients.safetensors",
                "frozen_source_qparams":Path(os.path.relpath(ROOT/"candidates/w8a12kv8_smoothquant/qparams.safetensors",output)).as_posix(),
                "linear_input_sources":incoming,"aligned_norm_inputs":aligned_norms,
                "quality_status":entry.get("status","not_qualified"),"scale_source":"frozen train intermediate calibration",
                "software_adapter_role":"host_preparation_simulator",
                "software_adapter_loads_coefficient_bundle":False,
                "coefficient_bundle_validation":"export tensors are checked against deterministic runtime multiplier/table compilation",
                "nonlinear_contract":{"rms_t_fractional_bits":config["nonlinear"]["rms"].get("t_fractional_bits",40),"rms_m_fractional_bits":16,"rms_u_fractional_bits":14,
                                       "rms_newton_steps":1,"residual_alignment_guard_bits":20}}
            atomic_json(output/"config.json",exported)
            serialized_config = read_json(output/"config.json")
            serialized_coefficients = load_file(str(coefficient_path), device="cpu")
            require_runtime_bundle_match(config, serialized_config, coefficient_sources,
                                         epsilon_values, serialized_coefficients)
            entry["coefficient_bundle_validation"] = {
                "status":"passed","serialized_tensors":len(serialized_coefficients),
                "multiplier_shift_pairs":len(coefficient_sources),
                "tables":["rope.cos","rope.sin","softmax.exp_lut","rms.seed_lut","per-layer PWL"],
                "adapter_loaded_bundle":False,
                "runtime_comparison":"all serialized integer tensors equal recompilation from config formats and selected nonlinear options"}
            entry["resources"] = self.resources(config,bundle,formats,aligned_norms,output)
            if entry.get("status") == "qualified_selection" and "config_reload" not in entry:
                ids = self.selection[0]["input_ids"][:96]
                before = full_logits(self.model,ids).numpy().copy()
                before_cache = cached_logits(self.model,ids,32)
                loaded = read_json(output/"config.json")
                self.adapter.set_trial(loaded)
                after = full_logits(self.model,ids).numpy()
                after_cache = cached_logits(self.model,ids,32)
                if not np.array_equal(before,after) or not np.array_equal(before_cache,after_cache):
                    raise AssertionError("reloaded contract config failed bitwise reproducibility")
                entry["config_reload"] = {"full_bitwise_equal":True,"cache_bitwise_equal":True,"length":96,"prefill":32,
                    "artifact":"config.json only; coefficients.safetensors is validated separately",
                    "adapter_role":"host preparation/simulation adapter recompiles coefficients from config scales",
                    "coefficient_bundle_loaded_by_adapter":False}
            self.save()
        qualified = {n:e for n,e in self.report["combinations"].items() if e.get("status") == "qualified_selection"}
        self.report["selection"] = selection_summary(qualified)
        require_export_artifacts(self.report, self.args.output_dir)
        self.report["stages"]["export"] = "complete"
        self.save()

    def resources(self,config,bundle,formats,aligned_norms,output):
        rows = {}
        for name,spec in config["points"].items():
            family = self.adapter.inventory[name]
            if family in ("score","probability"): count = 9*512*512
            elif family == "k_pre": count = 512*192
            elif family in ("gate_up","silu","product"): count = 512*1536
            elif family == "logits": count = 512*49152
            else: count = 512*576
            container = 8 if spec["bits"] <= 8 else 16 if spec["bits"] <= 16 else 32
            rows[name] = {"logical_bits":spec["bits"],"container_bits":container,"elements":count,
                          "payload_bytes":math.ceil(count*spec["bits"]/8),"container_bytes":count*container//8}
        if config["nonlinear"]["softmax"].get("fused"):
            for i in range(30):
                prefix = f"model.layers.{i}.self_attn"
                rows[prefix+".exponential"] = {"logical_bits":8,"container_bits":8,"elements":9*512*512,
                    "payload_bytes":9*512*512,"container_bytes":9*512*512}
                rows[prefix+".denominator"] = {"logical_bits":17,"container_bits":32,"elements":9*512,
                    "payload_bytes":math.ceil(9*512*17/8),"container_bytes":9*512*4}

        scale_counts = {"per_tensor":0,"per_feature_or_head":0}
        scale_values = 0
        for spec in formats.values():
            count = int(np.asarray(spec["scale"]).size)
            scale_values += count
            scale_counts["per_tensor" if count == 1 else "per_feature_or_head"] += count
        coefficient_bytes = sum(t.numel()*t.element_size() for t in bundle.values())
        multiplier_bytes = sum(t.numel()*t.element_size() for name,t in bundle.items()
                               if name.endswith((".M", ".shift")))
        table_groups = {"rope_rom":0,"softmax_lut":0,"rms_seed_and_epsilon":0,"silu_pwl":0}
        for name,tensor in bundle.items():
            size = tensor.numel()*tensor.element_size()
            if name.startswith("rope."): group = "rope_rom"
            elif name.startswith("softmax."): group = "softmax_lut"
            elif name.startswith("rms.") or name.endswith(".epsilon"): group = "rms_seed_and_epsilon"
            elif ".pwl." in name: group = "silu_pwl"
            else: continue
            table_groups[group] += size
        maximum_shift_bits = max((8*t.element_size() for name,t in bundle.items()
                                  if name.endswith(".shift")), default=0)
        max_rms_widths = {}
        for description in aligned_norms.values():
            for name,width in description.get("internal_widths",{}).items():
                if name.endswith("_bits"):
                    max_rms_widths[name] = max(max_rms_widths.get(name,0),width)

        query_formats = [spec for name,spec in formats.items()
                         if name.endswith(".query_post_rope")]
        query_ranges = [integer_code_bounds(int(spec["bits"]), spec.get("signed", True))
                        for spec in query_formats]
        if query_ranges:
            q_code_range = (min(bounds[0] for bounds in query_ranges),
                            max(bounds[1] for bounds in query_ranges))
        else:
            q_code_range = integer_code_bounds(24)
        k_code_range = integer_code_bounds(8)
        qk_product_range = dot_product_code_bounds(q_code_range, k_code_range, 1)
        qk_accumulator_range = dot_product_code_bounds(q_code_range, k_code_range, 64)
        qk_product_bits = minimum_signed_width(*qk_product_range)
        qk_accumulator_bits = minimum_signed_width(*qk_accumulator_range)
        p_bits = config["nonlinear"]["softmax"].get("probability_bits",0)
        sequence_length = 512
        query_rows = 9*sequence_length
        dense_score_elements = query_rows*sequence_length
        causal_score_elements = 9*sequence_length*(sequence_length+1)//2
        fused = config["nonlinear"]["softmax"].get("fused")
        normalize_divisions = query_rows*64 if fused else dense_score_elements
        softmax_interface = ("E unsigned 8 plus S unsigned 17; no probability tensor" if fused
                             else f"P unsigned {p_bits}; one rounded normalization per dense score element")
        linear_input_conversions_per_token = 30*(4*576+2*576+1536)+576
        linear_output_conversions_per_token = 30*(576+192+192+576+1536+1536+576)+49152
        cache_scale_conversions_per_token = 30*2*3*64
        residual_branch_alignments_per_token = 30*2*2*576
        rms_gamma_conversions_per_token = 61*576
        source_qparams = ROOT/"candidates/w8a12kv8_smoothquant/qparams.safetensors"
        return {
            "measurement_scope":"batch 1, sequence length 512; logical tensor sizes and serialized files, not hardware measurement",
            "boundary_payload_bytes_per_512":sum(r["payload_bytes"] for r in rows.values()),
            "boundary_container_bytes_per_512":sum(r["container_bytes"] for r in rows.values()),
            "maximum_boundary_container_bits":max(r["container_bits"] for r in rows.values()),
            "boundary_inventory":rows,
            "shared_weight_payload_bytes":sum(w.numel() for w in self.baseline.weights.values()),
            "prepared_weight_safetensors_bytes":(self.args.output_dir/"weights.safetensors").stat().st_size,
            "kv_payload_bytes_512":30*3*512*64*2,
            "runtime_coefficient_bundle_bytes":coefficient_bytes,
            "runtime_multiplier_shift_bytes":multiplier_bytes,
            "runtime_table_bytes":sum(table_groups.values()),
            "runtime_table_breakdown_bytes":table_groups,
            "multiplier_shift_pairs":sum(name.endswith(".M") for name in bundle),
            "maximum_shift_container_bits":maximum_shift_bits,
            "scale_metadata":{"format_count":len(formats),"scale_value_count":scale_values,
                "per_tensor_scale_values":scale_counts["per_tensor"],
                "per_feature_or_head_scale_values":scale_counts["per_feature_or_head"],
                "hypothetical_float32_bytes":scale_values*4,"hypothetical_float64_bytes":scale_values*8,
                "meaning":"config.json metadata, not runtime SRAM; intended datapath uses exported fixed-point coefficients"},
            "frozen_source_qparams_bytes":source_qparams.stat().st_size,
            "exported_config_json_bytes":(output/"config.json").stat().st_size,
            "arithmetic_widths":{"linear_product_signed_bits":20,"linear_accumulator_container_bits":32,
                "linear_accumulator_bound_bits":30,"qk_product_container_bits":qk_product_bits,
                "qk_product_code_range":list(qk_product_range),
                "qk_accumulator_bound_bits":qk_accumulator_bits,
                "qk_accumulator_code_range":list(qk_accumulator_range),
                "pv_discrete_product_signed_bits":(p_bits+8 if p_bits else None),
                "pv_discrete_accumulator_bound_bits":((128*((1<<p_bits)-1+256)).bit_length()+1 if p_bits else None),
                "pv_fused_product_signed_bits":16 if fused else None,
                "pv_fused_accumulator_signed_bits":25 if fused else None,
                "residual_guard_branch_signed_bits":63,"residual_sum_signed_bits":64,
                "rms_max_observed_input_and_reduction_widths":max_rms_widths},
            "operation_counts_at_length_512":{"dense_score_elements":dense_score_elements,
                "causal_valid_score_elements":causal_score_elements,"softmax_interface":softmax_interface,
                "normalization_divisions_dense_backend":normalize_divisions,
                "discrete_probability_divisions_if_causal_skip":causal_score_elements if not fused else None,
                "fused_pv_divisions_per_context_feature":query_rows*64 if fused else None,
                "pv_multiply_accumulates_dense_backend":dense_score_elements*64,
                "pv_multiply_accumulates_if_causal_keys_skipped":causal_score_elements*64,
                "softmax_index_conversions_dense_backend":dense_score_elements,
                "linear_input_scale_conversions_per_output_token":linear_input_conversions_per_token,
                "linear_output_requant_conversions_per_output_token":linear_output_conversions_per_token,
                "kv_cache_scale_conversions_per_output_token":cache_scale_conversions_per_token,
                "residual_branch_alignments_per_output_token":residual_branch_alignments_per_token,
                "rms_gamma_conversions_per_output_token":rms_gamma_conversions_per_token,
                "rms_normalization_invocations_per_output_token":61,
                "silu_pwl_values_per_output_token":30*1536,
                "gate_product_values_per_output_token":30*1536},
            "peak_sram_bytes":None,"fpga_area":None,"power":None,
            "limitations":"Boundary bytes sum every interface as a full 512-token tensor, not concurrent peak SRAM. Dense score counts reflect the software shape; causal masking may reduce scheduled work. No packing, RTL synthesis, FPGA area, timing, or power measurement is included."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline",action="store_true")
    parser.add_argument("--cache-dir",type=Path,default=ROOT/".cache/huggingface")
    parser.add_argument("--output-dir",type=Path,default=ROOT/"results/numerical/contract_search")
    parser.add_argument("--stage",choices=("all","baseline","isolated","family","search","qualify","export"),default="all")
    args = parser.parse_args()
    configure_runtime()
    campaign = Campaign(args)
    # Independent disabled-adapter equality check, before baseline/full campaign.
    ids = campaign.selection[0]["input_ids"][:32]
    with torch.inference_mode(): expected = full_logits(campaign.model,ids)
    with campaign.adapter.attached(),torch.inference_mode():
        actual = full_logits(campaign.model,ids)
        if not torch.equal(actual,expected): raise AssertionError("disabled adapter changed baseline")
        campaign.report["disabled_adapter_bitwise_equal"] = True
        # baseline_stage runs without changing bindings; native baseline and
        # disabled adapter already proved identical above.
        if args.stage in ("all","baseline") and campaign.report["stages"].get("baseline") != "measured":
            started = time.monotonic()
            campaign.report["baseline"] = {"ppl":evaluate_ppl(campaign.model,campaign.selection)}
            campaign.report["baseline"]["seconds"] = round(time.monotonic()-started,3)
            campaign.report["stages"]["baseline"] = "measured"
            campaign.save()
        if args.stage in ("all","isolated"):
            campaign.replay_stage()
            campaign.isolated_stage()
        if args.stage in ("all","family"): campaign.family_stage()
        if args.stage in ("all","search"): campaign.search_stage()
        if args.stage in ("all","qualify"): campaign.qualify_stage()
        if args.stage in ("all","export"): campaign.export_stage()


if __name__ == "__main__":
    main()
