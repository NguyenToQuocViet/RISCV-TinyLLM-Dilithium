#!/usr/bin/env python3
"""Đánh giá A8 SmoothQuant per-tensor trên contract số nguyên: tách token 0 và alpha theo Linear.

Mọi biến thể giữ phần còn lại của contract v1 (points, nonlinear, scale_rescale_bits). Chỉ dùng
dữ liệu train để calibrate và chỉ đánh giá trên selection; không mở heldout.
Lệnh con: calibrate, alpha-search, prepare, quick, full.
"""
import argparse
from copy import deepcopy
import resource
import time
from pathlib import Path

import torch

from fp32_reference import (ROOT, configure_runtime, environment, load_model,
                            read_json, source_snapshot, write_json)
from ptq_calibrate import calibrate as calibrate_bundle, calibration_cache_cases, stream_cache
from ptq_contract_runtime import load_prepared_contract
from ptq_contract_search import ArtifactCampaign, ArtifactCompiler, atomic_json
from ptq_eval import full_logits
from ptq_fake_quant import PTQAdapter, smooth_scale

A8_RESULTS = ROOT/"results/numerical/a8_variants"
A8_CALIBRATION = ROOT/"calibration/a8_variants"
A12_CANDIDATE = ROOT/"candidates/w8a12kv8_smoothquant"
A8_SOURCE = ROOT/"candidates/w8a8kv8_smoothquant_a09"
V1_ARTIFACT_CONFIG = ROOT/"results/numerical/contract_improvement/artifacts/combined_min_1pct_residual16_m16/config.json"
ALPHA_MAP = A8_RESULTS/"alpha_map.json"
ALPHA_GRID = tuple(round(0.3 + 0.1*i, 1) for i in range(8))
ALPHA_SEARCH_WINDOWS = 8
THREADS = 8
FP32_QUICK8_PPL = 20.859254123803474
CANDIDATE_KEYS = ("points", "nonlinear", "integer_coefficients", "coefficient_bits", "metrics",
                  "mac_dtype", "mac_exactness_bound", "check_mac", "scale_rescale_bits")

VARIANTS = {
    "r_a8sq_a090": {"alpha": 0.9, "token0": False},
    "c1_a050": {"alpha": 0.5, "token0": True},
    "c1_a065": {"alpha": 0.65, "token0": True},
    "c1_a080": {"alpha": 0.8, "token0": True},
    "c1_a090": {"alpha": 0.9, "token0": True},
    "c3_alpha_map": {"alpha": "per_linear", "token0": False},
}


def bundle_dir(name):
    """Thư mục có config.json và qparams.safetensors; r_a8sq_a090 dùng thẳng bundle sẵn có."""
    return A8_SOURCE if name == "r_a8sq_a090" else A8_CALIBRATION/name


def variant_config(name):
    """Config calibration của biến thể, dẫn xuất từ bundle A8 alpha 0,9 sẵn có."""
    spec = VARIANTS[name]
    config = deepcopy(read_json(A8_SOURCE/"config.json"))
    if name == "r_a8sq_a090":
        return config
    config["name"] = name
    config["smoothquant"]["alpha"] = (read_json(ALPHA_MAP)["alpha"] if spec["alpha"] == "per_linear"
                                      else spec["alpha"])
    if spec["token0"]:
        config["token0"] = {"enabled": True}
        config["smoothquant"]["statistics"] = "train_max_abs_per_input_feature_excluding_position_0"
    return config


def candidate_config(name):
    """Cấu hình contract của biến thể: sao từ artifact v1; formats được sinh lại từ thống kê."""
    v1 = read_json(V1_ARTIFACT_CONFIG)
    config = {key: deepcopy(v1[key]) for key in CANDIDATE_KEYS}
    config["name"] = name
    return config


def choose_alpha(errors):
    """Alpha có sai số nhỏ nhất; khi bằng nhau chọn gần 0,5 nhất, rồi chọn alpha nhỏ hơn."""
    best = min(errors.values())
    return min((alpha for alpha, error in errors.items() if error == best),
               key=lambda alpha: (abs(alpha - 0.5), alpha))


def quantize_a8(value, scale):
    return torch.clamp(torch.round(value/scale), -128, 127)*scale


def quantize_w8_rows(weight):
    scale = (weight.abs().amax(dim=1, keepdim=True)/127).clamp_min(torch.finfo(torch.float32).eps)
    return torch.clamp(torch.round(weight/scale), -128, 127)*scale


def smooth_alpha_errors(x, weight, smooth_max, activation_max, alphas):
    """Tổng bình phương sai số của Q_a8(x/s) Q_w8(W s)^T so với x W^T cho từng alpha.

    x: [N, C] đầu vào FP32; weight: [O, C]. s tính từ smooth_max (thống kê của lượt SmoothQuant);
    scale A8 = max_kênh(activation_max / s) / 127 (thống kê của lượt calibration đầy đủ).
    """
    reference = x @ weight.T
    weight_max = weight.abs().amax(dim=0)
    errors = {}
    for alpha in alphas:
        scale = smooth_scale(smooth_max, weight_max, alpha)
        a_scale = ((activation_max/scale).amax()/127).clamp_min(torch.finfo(torch.float32).eps)
        output = quantize_a8(x/scale, a_scale) @ quantize_w8_rows(weight*scale).T
        errors[alpha] = float((output - reference).double().square().sum())
    return errors


def read_calibration(args):
    return read_json(ROOT/"data/wikitext_calibration.json")


@torch.inference_mode()
def alpha_search(args):
    configure_runtime()
    torch.set_num_threads(THREADS)
    started = time.monotonic()
    args.alpha_map.parent.mkdir(parents=True, exist_ok=True)
    model, _ = load_model(source_snapshot(args.cache_dir, args.offline))
    records = read_calibration(args)
    adapter = PTQAdapter(model, variant_config("r_a8sq_a090"))
    # Lượt 1: max theo kênh trên mọi hàng. s dùng 64 cửa sổ như finalize_smoothquant; scale A8 dùng thêm 16 lượt cache.
    adapter.begin_smooth_calibration()
    for index, record in enumerate(records):
        full_logits(model, record["input_ids"])
        if (index + 1) % 16 == 0:
            print(f"ALPHA stats windows {index + 1}/{len(records)}", flush=True)
    window_max = {name: value.clone() for name, value in adapter.smooth_stats.items()}
    for case in calibration_cache_cases(records):
        record = records[case["calibration_index"]]
        for regime in case["regimes"]:
            stream_cache(model, record["input_ids"][:regime["input_length"]], regime["prefill"])
    full_max = dict(adapter.smooth_stats)
    names = sorted(window_max)
    if len(names) != 210:
        raise ValueError(f"cần 210 Linear decoder, có {len(names)}")
    # Lượt 2: đầu vào FP32 của model gốc; cộng dồn sai số trong hook, không lưu activation.
    totals = {name: dict.fromkeys(ALPHA_GRID, 0.0) for name in names}
    rows = dict.fromkeys(names, 0)
    handles = []
    for name in names:
        module = model.get_submodule(name)

        def observe(layer, inputs, _name=name):
            x = inputs[0].detach()
            x = x.reshape(-1, x.shape[-1])
            for alpha, error in smooth_alpha_errors(x, layer.weight.detach(), window_max[_name],
                                                    full_max[_name], ALPHA_GRID).items():
                totals[_name][alpha] += error
            rows[_name] += x.shape[0]
        handles.append(module.register_forward_pre_hook(observe))
    try:
        with adapter.native():
            for index, record in enumerate(records[:ALPHA_SEARCH_WINDOWS]):
                full_logits(model, record["input_ids"])
                print(f"ALPHA error window {index + 1}/{ALPHA_SEARCH_WINDOWS}; {time.monotonic()-started:.0f}s",
                      flush=True)
    finally:
        for handle in handles:
            handle.remove()
    selected, errors = {}, {}
    for name in names:
        outputs = model.get_submodule(name).out_features
        errors[name] = {str(alpha): total/(rows[name]*outputs) for alpha, total in totals[name].items()}
        selected[name] = choose_alpha({alpha: total for alpha, total in totals[name].items()})
    histogram = {str(alpha): sum(value == alpha for value in selected.values()) for alpha in ALPHA_GRID}
    write_json(args.alpha_map, {
        "status": "PASS", "alpha": selected, "alpha_grid": list(ALPHA_GRID), "histogram": histogram,
        "mean_squared_error": errors, "error_windows": ALPHA_SEARCH_WINDOWS,
        "rows_per_linear": rows[names[0]],
        "selection_rule": "minimum mean squared output error; ties choose alpha closest to 0.5, then smaller alpha",
        "inputs": "FP32 inputs of the unmodified model on the first 8 train windows; no activations stored",
        "statistics": "s uses max over 64 train windows (as finalize_smoothquant); A8 scale uses max over 64 windows + 16 cache runs; all rows",
        "weights": "W8 per-output-row minmax of W*s", "activations": "A8 per-tensor, clipped to [-128, 127]",
        "environment": environment(), "heldout_used": False, "seconds": round(time.monotonic()-started, 1)})
    print(f"PASS alpha-search: histogram={histogram}; {time.monotonic()-started:.0f}s", flush=True)


def calibrate_variant(args):
    name = args.variant
    if name == "r_a8sq_a090":
        raise SystemExit("r_a8sq_a090 dùng thẳng candidates/w8a8kv8_smoothquant_a09; không calibrate lại")
    output = A8_CALIBRATION/name
    output.mkdir(parents=True, exist_ok=True)
    write_json(output/"config.json", variant_config(name))
    calibrate_bundle(argparse.Namespace(
        data_dir=ROOT/"data", cache_dir=args.cache_dir, offline=args.offline, threads=THREADS,
        config=output/"config.json", output_dir=output))


def peak_rss_mb():
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024


def prepare_variant(args):
    """Sinh artifact số nguyên của một biến thể và kiểm tra MAC trên một cửa sổ train."""
    name = args.variant
    torch.set_num_threads(THREADS)
    output = A8_RESULTS/"artifacts"/name
    if (output/"config.json").is_file() and not args.force:
        raise SystemExit(f"{output} đã có artifact; dùng --force để sinh lại")
    for stale in ("config.json", "coefficients.safetensors", "weights.safetensors"):
        (output/stale).unlink(missing_ok=True)
    started = time.monotonic()
    compiler = ArtifactCompiler(argparse.Namespace(
        output_dir=output, cache_dir=args.cache_dir, offline=args.offline,
        candidate_dir=bundle_dir(name), statistics_path=A8_RESULTS/name/"intermediate_calibration.json",
        kv_scale_source=A12_CANDIDATE/"qparams.safetensors"))
    config = candidate_config(name)
    path = compiler.prepare_artifact(config, output, compiler.shared_weights)
    prepared = read_json(path)
    spec = VARIANTS[name]
    if prepared["linear_input_bits"] != 8 or bool(prepared.get("token0")) != spec["token0"]:
        raise ValueError(f"artifact không khớp biến thể {name}")
    result = {"config": path.relative_to(A8_RESULTS).as_posix(), "preparation_seconds": round(time.monotonic()-started, 1),
              "linear_input_bits": prepared["linear_input_bits"], "token0": spec["token0"],
              "weights_bytes": (output/"weights.safetensors").stat().st_size,
              "coefficients_bytes": (output/"coefficients.safetensors").stat().st_size}
    if not args.skip_check_mac:
        result["check_mac"] = check_mac(compiler, config)
    result["peak_rss_mb"] = round(peak_rss_mb(), 1)
    campaign = A8_RESULTS/"campaign.json"
    report = read_json(campaign) if campaign.exists() else {"variants": {}}
    report.setdefault("variants", {}).setdefault(name, {"name": name})["artifact"] = result
    A8_RESULTS.mkdir(parents=True, exist_ok=True)
    atomic_json(campaign, report)
    print(f"PREPARED {name}: {result}", flush=True)


@torch.inference_mode()
def check_mac(compiler, config):
    """Mô phỏng ContractAdapter trên cửa sổ train 0: GEMM FP64 phải bằng tích số nguyên chính xác."""
    record = read_json(ROOT/"data/wikitext_calibration.json")[0]
    compiler.adapter.set_trial({**config, "metrics": False, "check_mac": True})
    with compiler.adapter.attached():
        full_logits(compiler.model, record["input_ids"])
    checks = compiler.adapter.mac_checks
    different = sum(item["different_accumulators"] for item in checks.values())
    post = sum(item.get("different_post_requant_codes", 0) for item in checks.values())
    if len(checks) != 211 or different or post:
        raise AssertionError(f"check_mac: {len(checks)} Linear, {different} accumulator lệch, {post} mã sau requant lệch")
    return {"window": "train 0", "linear_layers": len(checks), "different_accumulators": different,
            "different_post_requant_codes": post,
            "samples": sum(item["samples"] for item in checks.values())}


class A8Campaign(ArtifactCampaign):
    """Tái dùng ppl/_full_ppl/save của ArtifactCampaign; bỏ các điều kiện tiên quyết của campaign cũ."""
    def __init__(self, args):
        self.args = args
        self.root = A8_RESULTS
        self.path = self.root/"campaign.json"
        self.report = read_json(self.path) if self.path.exists() else {"variants": {}}
        self.threads = THREADS
        torch.set_num_threads(self.threads)
        self.started = time.monotonic()
        self.selection = read_json(ROOT/"data/wikitext_selection.json")
        self.reference = read_json(ROOT/"results/ptq/fp32.json")
        self.report.update({"backend": "artifact_only_integer_code_execution; PyTorch CPU FP64 exact-code GEMM",
                            "threads": self.threads, "heldout_used": False,
                            "teacher_model_loaded_during_measurement": False,
                            "ptq_adapter_loaded_during_measurement": False})

    def runtime(self, name):
        config_path = self.root/"artifacts"/name/"config.json"
        if not config_path.is_file():
            raise FileNotFoundError(f"artifact chưa được chuẩn bị: {name}")
        config = read_json(config_path)
        if config.get("linear_input_bits") != 8 or bool(config.get("token0")) != VARIANTS[name]["token0"]:
            raise ValueError(f"artifact không khớp biến thể {name}")
        return load_prepared_contract(config_path)

    def run_quick(self, name):
        entry = self.report.setdefault("screening", {}).setdefault("candidates", {}).setdefault(
            name, {"config_name": name})
        if entry.get("quick", {}).get("status") == "complete":
            return entry["quick"]
        started = time.monotonic()
        runtime = self.runtime(name)
        with torch.inference_mode():
            row = self.ppl(runtime, entry, "quick", self.selection[:8])
        if row["tokens"] != 8*511:
            raise RuntimeError(f"Quick8 target count changed: {row['tokens']}")
        row.update({"ranking_only": True, "quality_gate": False, "fp32_quick8_ppl": FP32_QUICK8_PPL,
                    "relative_ppl_increase_vs_fp32": row["ppl"]/FP32_QUICK8_PPL - 1,
                    "seconds": round(time.monotonic()-started, 1), "peak_rss_mb": round(peak_rss_mb(), 1)})
        self.save()
        del runtime
        print(f"QUICK8 {name} PPL={row['ppl']:.6f} vs FP32 {row['relative_ppl_increase_vs_fp32']:+.3%}", flush=True)
        return row

    def run_full(self, name):
        owner = self.report["variants"].setdefault(name, {"name": name})
        runtime = self.runtime(name)
        with torch.inference_mode():
            row = self._full_ppl(runtime, owner, self.selection)
        if row["windows"] != 64 or row["tokens"] != 32704:
            raise RuntimeError(f"Full64 chưa đủ: {row['windows']} cửa sổ, {row['tokens']} target")
        owner["ppl_ratio_vs_fp32"] = row["ppl"]/self.reference["ppl"]["ppl"]
        owner["relative_ppl_increase_vs_fp32"] = owner["ppl_ratio_vs_fp32"] - 1
        owner["ppl_gate_pass"] = owner["ppl_ratio_vs_fp32"] <= 1.05
        self.save()
        print(f"FULL64 {name} PPL={row['ppl']:.10f} ({owner['relative_ppl_increase_vs_fp32']:+.3%}) "
              f"gate={'PASS' if owner['ppl_gate_pass'] else 'FAIL'}", flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--cache-dir", type=Path, default=ROOT/".cache/huggingface")
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("calibrate", "prepare"):
        sub = commands.add_parser(command)
        sub.add_argument("--variant", choices=sorted(VARIANTS), required=True)
        if command == "prepare":
            sub.add_argument("--force", action="store_true")
            sub.add_argument("--skip-check-mac", action="store_true")
    search = commands.add_parser("alpha-search")
    search.add_argument("--alpha-map", type=Path, default=ALPHA_MAP)
    for command in ("quick", "full"):
        commands.add_parser(command).add_argument("--variants", nargs="+", choices=sorted(VARIANTS), required=True)
    args = parser.parse_args(argv)
    if args.command == "calibrate":
        calibrate_variant(args)
    elif args.command == "alpha-search":
        alpha_search(args)
    elif args.command == "prepare":
        configure_runtime()
        prepare_variant(args)
    else:
        configure_runtime()
        campaign = A8Campaign(args)
        for name in args.variants:
            (campaign.run_quick if args.command == "quick" else campaign.run_full)(name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
