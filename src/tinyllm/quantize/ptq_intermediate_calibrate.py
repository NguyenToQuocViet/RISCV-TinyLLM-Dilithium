#!/usr/bin/env python3
"""Profile intermediate tensors on train with frozen W8A12KV8 SmoothQuant qparams."""
import argparse
from contextlib import contextmanager
import math
from pathlib import Path
import struct
import time

import torch
import torch.nn.functional as F
from safetensors.torch import save_file
from transformers.models.llama.modeling_llama import repeat_kv, rotate_half

from fp32_reference import ROOT, configure_runtime, environment, load_model, read_json, source_snapshot, write_json
from ptq_calibrate import calibration_cache_cases, stream_cache
from ptq_eval import full_logits
import ptq_fake_quant as ptq


# Absolute FP32 bit patterns are ordered. Retain the exponent and three mantissa
# bits: 8 histogram bins per normal exponent, including all finite FP32 values.
HIST_SHIFT = 20
HIST_BINS = 2040


class Moments:
    def __init__(self):
        self.calls = self.count = self.zeros = 0
        self.minimum, self.maximum = math.inf, -math.inf
        self.mean = self.m2 = 0.0

    def merge(self, count, minimum, maximum, mean, variance, zeros):
        total = self.count + count
        difference = mean - self.mean
        self.m2 += variance * count + difference**2 * self.count * count / total
        self.mean += difference * count / total
        self.count = total
        self.calls += 1
        self.zeros += zeros
        self.minimum, self.maximum = min(self.minimum, minimum), max(self.maximum, maximum)

    def summary(self):
        return {"calls": self.calls, "elements": self.count, "minimum": self.minimum,
                "maximum": self.maximum, "mean": self.mean,
                "std": math.sqrt(max(0.0, self.m2 / self.count)), "zeros": self.zeros}


class TensorStats:
    def __init__(self):
        self.total = Moments()
        self.phases = {}
        self.histogram = torch.zeros(HIST_BINS, dtype=torch.int64)
        self.group_min = self.group_max = None
        self.group_axis = None

    def update(self, value, phase, group_axis=None, mask=None):
        value = value.detach().float()
        mask = mask.expand_as(value) if mask is not None else None
        flat = value[mask] if mask is not None else value.reshape(-1)
        if flat.numel() == 0:
            raise ValueError("No unmasked elements to observe")
        minimum, maximum = map(float, torch.aminmax(flat))
        if not math.isfinite(minimum) or not math.isfinite(maximum):
            raise ValueError("Nonfinite intermediate tensor")
        variance, mean = map(float, torch.var_mean(flat, correction=0))
        packet = (flat.numel(), minimum, maximum, mean, variance, int((flat == 0).sum()))
        self.total.merge(*packet)
        self.phases.setdefault(phase, Moments()).merge(*packet)
        codes = flat.abs().contiguous().view(torch.int32).reshape(-1) >> HIST_SHIFT
        self.histogram += torch.bincount(codes, minlength=HIST_BINS)
        if group_axis is not None:
            grouped = value.movedim(group_axis, 0).flatten(1)
            if mask is None:
                lower, upper = torch.aminmax(grouped, dim=1)
            else:
                valid = mask.movedim(group_axis, 0).flatten(1)
                lower = grouped.masked_fill(~valid, math.inf).amin(1)
                upper = grouped.masked_fill(~valid, -math.inf).amax(1)
            self.group_axis = group_axis
            self.group_min = lower if self.group_min is None else torch.minimum(self.group_min, lower)
            self.group_max = upper if self.group_max is None else torch.maximum(self.group_max, upper)

    def summary(self):
        result = self.total.summary()
        cumulative = self.histogram.cumsum(0)
        max_abs = max(abs(self.total.minimum), abs(self.total.maximum))
        quantiles = {}
        for percentile in (50, 90, 99, 99.9, 99.99, 100):
            if math.ceil(self.total.count * percentile / 100) <= self.total.zeros:
                bound = 0.0
            else:
                rank = math.ceil(self.total.count * percentile / 100)
                index = int(torch.searchsorted(cumulative, rank))
                bound = struct.unpack('<f', struct.pack('<I', (index + 1) << HIST_SHIFT))[0]
                bound = min(bound, max_abs)
            quantiles[str(percentile)] = bound
        result.update({"phases": {name: phase.summary() for name, phase in self.phases.items()},
                       "abs_percentile_upper_bounds": quantiles,
                       "abs_histogram": {str(i): int(n) for i, n in enumerate(self.histogram) if n}})
        negative = max(0.0, -self.total.minimum)
        positive = max(0.0, self.total.maximum)
        result["minmax_scale_candidates"] = {
            "zero_point": 0,
            "signed_per_tensor": {str(b): max(negative / (1 << (b-1)), positive / ((1 << (b-1))-1)) or 1.0
                                  for b in range(2,33)}}
        if self.total.minimum >= 0:
            result["minmax_scale_candidates"]["unsigned_per_tensor"] = {
                str(b): positive / ((1 << b)-1) or 1.0 for b in range(1,33)}
        if self.group_min is not None:
            result["groups"] = {"axis": self.group_axis, "minimum": self.group_min.tolist(),
                                "maximum": self.group_max.tolist()}
        return result


def full_signed_range(adapter):
    """Keep loaded scales/s intact; change only the runtime clipping endpoints."""
    adapter.materialized.clear()
    for point in adapter.points.values():
        point.fq.quant_min = -(1 << (point.bits - 1))
        point.fq.quant_max = (1 << (point.bits - 1)) - 1
        # The pinned torch FakeQuantize forward reads its observer's endpoints.
        point.fq.activation_post_process.quant_min = point.fq.quant_min
        point.fq.activation_post_process.quant_max = point.fq.quant_max


class IntermediateProfiler:
    def __init__(self, model, adapter):
        self.model, self.adapter = model, adapter
        self.points = {}
        self.phase = "prefill"

    def observe(self, name, value, group_axis=None, mask=None):
        self.points.setdefault(name, TensorStats()).update(value, self.phase, group_axis, mask)

    def attention(self, module, query, key, value, attention_mask, scaling, dropout=0.0, **kwargs):
        # Same eager arithmetic/order as the pinned Transformers implementation.
        # Observers exclude masked entries, including the finite mask sentinel.
        prefix = f"model.layers.{module.layer_idx}.self_attn"
        self.observe(prefix + ".query_post_rope", query, 1)
        keys = repeat_kv(key, module.num_key_value_groups)
        values = repeat_kv(value, module.num_key_value_groups)
        dot = torch.matmul(query, keys.transpose(2, 3))
        scores = dot * scaling
        if attention_mask is not None:
            causal_mask = attention_mask[:, :, :, :keys.shape[-2]]
            allowed = causal_mask == 0
            scores = scores + causal_mask
        else:
            allowed = torch.ones_like(scores, dtype=torch.bool)
        self.observe(prefix + ".qk_unscaled", dot, 1, allowed)
        self.observe(prefix + ".score", scores, 1, allowed)
        shifted = scores - scores.max(-1, keepdim=True).values
        self.observe(prefix + ".score_minus_max", shifted, 1, allowed)
        exponentials = torch.exp(shifted)
        exp_sum = exponentials.sum(-1, keepdim=True)
        self.observe(prefix + ".softmax_exp_reference", exponentials, 1, allowed)
        self.observe(prefix + ".softmax_sum_reference", exp_sum, 1)
        self.observe(prefix + ".softmax_reciprocal_reference", exp_sum.reciprocal(), 1)
        probabilities = F.softmax(scores, dim=-1, dtype=torch.float32).to(query.dtype)
        self.observe(prefix + ".probability_unmasked", probabilities, 1, allowed)
        probabilities = F.dropout(probabilities, p=dropout, training=module.training)
        output = torch.matmul(probabilities, values)
        return output.transpose(1, 2).contiguous(), probabilities

    @contextmanager
    def attached(self):
        handles, old_captures = [], {}
        original_attention = ptq.eager_attention_forward
        original_rotary = ptq.apply_rotary_pos_emb
        active_layer = None

        def rotary(query, key, cos, sin, position_ids=None, unsqueeze_dim=1):
            cosine, sine = cos.unsqueeze(unsqueeze_dim), sin.unsqueeze(unsqueeze_dim)
            prefix = f"model.layers.{active_layer}.self_attn.rope"
            for name, value in (("query",query), ("key",key)):
                self.observe(prefix + f".{name}_cos_product", value * cosine, 1)
                self.observe(prefix + f".{name}_sin_product", rotate_half(value) * sine, 1)
            return original_rotary(query, key, cos, sin, position_ids, unsqueeze_dim)

        def attention_input(module, args, kwargs):
            nonlocal active_layer
            active_layer = module.layer_idx

        def output_hook(name, axis=-1):
            def capture(module, args, output):
                self.observe(name, output, axis)
            return capture

        def input_hook(name):
            def capture(module, args):
                self.observe(name, args[0], -1)
            return capture

        def norm_input(name):
            def capture(module, args):
                square = args[0].float().pow(2)
                mean_square = square.mean(-1, keepdim=True)
                self.observe(name + ".square", square)
                self.observe(name + ".sum_square_reference", square.sum(-1, keepdim=True))
                self.observe(name + ".mean_square", mean_square)
                self.observe(name + ".mean_square_plus_epsilon", mean_square + module.variance_epsilon)
                self.observe(name + ".inv_rms", torch.rsqrt(mean_square + module.variance_epsilon))
            return capture

        try:
            for name, module in self.model.named_modules():
                if isinstance(module, torch.nn.Linear):
                    handles.append(module.register_forward_hook(output_hook(name + ".output", None if name == "lm_head" else -1)))
                if name.endswith(("input_layernorm", "post_attention_layernorm")) or name == "model.norm":
                    handles.append(module.register_forward_hook(output_hook(name + ".output")))
                    handles.append(module.register_forward_pre_hook(norm_input(name)))
                if name.endswith("post_attention_layernorm"):
                    handles.append(module.register_forward_pre_hook(input_hook(name.removesuffix("post_attention_layernorm") + "residual_after_attention")))
                if name.endswith("mlp.act_fn"):
                    handles.append(module.register_forward_hook(output_hook(name.removesuffix("act_fn") + "silu_output")))
                if name.endswith("mlp.down_proj"):
                    handles.append(module.register_forward_pre_hook(input_hook(name.removesuffix("down_proj") + "gate_product")))
                if name.endswith("self_attn.o_proj"):
                    handles.append(module.register_forward_pre_hook(input_hook(name.removesuffix("o_proj") + "context")))
                if name.endswith("self_attn"):
                    handles.append(module.register_forward_pre_hook(attention_input, with_kwargs=True))
            handles.append(self.model.model.embed_tokens.register_forward_hook(output_hook("model.embed_tokens.output")))
            for index, layer in enumerate(self.model.model.layers):
                def layer_output(module, args, output, i=index):
                    self.observe(f"model.layers.{i}.residual_after_ffn", output[0], -1)
                handles.append(layer.register_forward_hook(layer_output))
            for name, point in self.adapter.points.items():
                if point.kind not in ("K", "V"):
                    continue
                old_captures[name] = point.capture
                def kv_capture(before, after, name=name, kind=point.kind):
                    if kind == "K":
                        self.observe(name + ".before_quantize", before, 1)
                    self.observe(name + ".after_quantize", after, 1)
                point.capture = kv_capture
            ptq.eager_attention_forward = self.attention
            ptq.apply_rotary_pos_emb = rotary
            yield self
        finally:
            ptq.eager_attention_forward = original_attention
            ptq.apply_rotary_pos_emb = original_rotary
            for name, capture in old_captures.items():
                self.adapter.points[name].capture = capture
            for handle in handles:
                handle.remove()


def derived_qparams(model, adapter):
    """Products/ratios of frozen FP32 reference scales, computed in FP64."""
    tensors, descriptions = {}, {}
    for name, module in model.named_modules():
        if not isinstance(module, torch.nn.Linear):
            continue
        weight_name = 'shared_embedding_lm_head.weight' if name == 'lm_head' else name + '.weight'
        delta_a = adapter.points[name + '.input'].fq.scale.double()
        delta_w = adapter.points[weight_name].fq.scale.double()
        raw_scale = delta_a * delta_w
        key = name + '.raw_accumulator.scale'
        tensors[key] = raw_scale
        descriptions[name] = {"scale_tensor": key, "scale_axis": "output_row", "zero_point": 0,
                              "bits": 32, "minimum_scale": float(raw_scale.min()),
                              "maximum_scale": float(raw_scale.max())}
        if name.endswith('self_attn.v_proj'):
            cache_name = name.removesuffix('v_proj') + 'value_post_projection'
            delta_v = adapter.points[cache_name].fq.scale.double().repeat_interleave(module.out_features // model.config.num_key_value_heads)
            coefficient = name + '.to_value_cache.reference_multiplier'
            tensors[coefficient] = raw_scale / delta_v
            descriptions[name]['to_value_cache'] = {"coefficient_tensor": coefficient,
                "target_scale_source": cache_name + '.scale', "target_zero_point": 0,
                "target_integer_range": [-128,127], "rounding": "nearest_ties_to_even"}
    return tensors, descriptions


@torch.inference_mode()
def calibrate(args):
    configure_runtime()
    started = time.monotonic()
    candidate = ROOT / "candidates/w8a12kv8_smoothquant"
    model, _ = load_model(source_snapshot(args.cache_dir, args.offline))
    adapter = ptq.PTQAdapter(model, read_json(candidate / "config.json"))
    adapter.load_qparams(candidate / "qparams.safetensors")
    full_signed_range(adapter)
    adapter.set_mode("quantize")
    records = read_json(args.data_dir / "wikitext_calibration.json")
    cases = calibration_cache_cases(records)

    # Check instrumentation on the real model once before collecting statistics.
    ids = records[0]["input_ids"][:32]
    expected = full_logits(model, ids)
    probe = IntermediateProfiler(model, adapter)
    with probe.attached():
        actual = full_logits(model, ids)
    if not torch.equal(expected, actual):
        raise ValueError("Instrumentation changed model logits")
    del expected, actual, probe
    print("PASS instrumentation: real-model logits unchanged", flush=True)

    profiler = IntermediateProfiler(model, adapter)
    profiler.phase = 'constants'
    for name,module in model.named_modules():
        if name.endswith(('input_layernorm','post_attention_layernorm')) or name == 'model.norm':
            profiler.observe(name + '.gamma', module.weight)
    positions = torch.arange(512).unsqueeze(0)
    cosine,sine = model.model.rotary_emb(torch.zeros(1,1,model.config.hidden_size), positions)
    profiler.observe('model.rotary_emb.cos', cosine, -1)
    profiler.observe('model.rotary_emb.sin', sine, -1)
    with profiler.attached():
        for index, record in enumerate(records):
            profiler.phase = "prefill"
            logits = full_logits(model, record["input_ids"])
            del logits
            print(f"INTERMEDIATE prefill {index + 1}/{len(records)}; {time.monotonic()-started:.1f}s", flush=True)
        for case in cases:
            record = records[case["calibration_index"]]
            for regime in case["regimes"]:
                # Split phases without changing stream_cache's cache semantics.
                profiler.phase = "cache_prefill"
                calls = 0
                def before_forward(module, inputs):
                    nonlocal calls
                    profiler.phase = "cache_prefill" if calls == 0 else "decode"
                    calls += 1
                handle = model.register_forward_pre_hook(before_forward)
                try:
                    stream_cache(model, record["input_ids"][:regime["input_length"]], regime["prefill"])
                finally:
                    handle.remove()
                print(f"INTERMEDIATE cache {case['id']} prefill={regime['prefill']}; {time.monotonic()-started:.1f}s", flush=True)

    expected_tokens = sum(len(r["input_ids"]) for r in records) + sum(
        regime["input_length"] for case in cases for regime in case["regimes"])
    for index in range(model.config.num_hidden_layers):
        for suffix in ("key_post_rope", "value_post_projection"):
            point = profiler.points[f"model.layers.{index}.self_attn.{suffix}.after_quantize"]
            expected_elements = expected_tokens * model.config.num_key_value_heads * model.config.hidden_size // model.config.num_attention_heads
            if point.total.count != expected_elements:
                raise ValueError("Missing cache calibration coverage")
    for name, module in model.named_modules():
        if isinstance(module, torch.nn.Linear):
            if profiler.points[name + ".output"].total.count != expected_tokens * module.out_features:
                raise ValueError(f"Missing Linear calibration coverage: {name}")
    tensors, linear_scales = derived_qparams(model, adapter)
    report = {"status": "PASS", "scope": "Intermediate ranges, minmax scale candidates, and derived frozen-scale coefficients; no new bit widths selected",
              "backend": "CPU eager FP32 fake-quant with full signed W8/A12/K8/V8 ranges",
              "environment": environment(), "candidate": str(candidate.relative_to(ROOT)),
              "model_config": {key: getattr(model.config,key) for key in (
                  'hidden_size','intermediate_size','num_hidden_layers','num_attention_heads',
                  'num_key_value_heads','vocab_size','rms_norm_eps','rope_theta')},
              "qparams_policy": "Existing scales/zero-points and SmoothQuant s frozen; no qparams rewritten",
              "fp32_remainder": adapter.config["fp32_remainder"],
              "full_prefill_windows": len(records), "cache_runs": sum(len(c['regimes']) for c in cases),
              "observed_tokens_per_layer": expected_tokens, "prefill_ids": [r['id'] for r in records],
              "cache_cases": cases, "selection_used": False, "heldout_used": False,
              "instrumentation_real_model_bitwise_equal": True,
              "derived_qparams": {"file": "intermediate_qparams.safetensors", "dtype": "float64_reference_not_RTL_format",
                                  "linear_outputs": linear_scales},
              "scale_candidates": {"policy": "Full signed minmax: max(max(0,-min)/2**(b-1), max(0,max)/(2**(b-1)-1)); all-zero tensor uses scale 1",
                  "bits": "2..32, not selected formats", "zero_point": 0,
                  "unsigned_policy": "max/(2**b-1) for observed-nonnegative tensors, b=1..32; not proof that unsigned is valid for all inputs",
                  "groups": "Per-channel/head min/max retained; apply the same formula to each group to instantiate scales",
                  "limitation": "These are observed-range candidate qparams, not approved formats or accuracy guarantees"},
              "analytical_domains": {"sin_cos": [-1,1], "square_sum_mean": "nonnegative",
                  "mean_square_plus_epsilon": {"minimum": model.config.rms_norm_eps},
                  "inv_rms": {"minimum_exclusive": 0, "maximum": 1/math.sqrt(model.config.rms_norm_eps)},
                  "score_minus_max": "nonpositive on allowed keys; each row has a zero",
                  "softmax_exp": [0,1], "softmax_sum": [1,512], "softmax_reciprocal": [1/512,1],
                  "probability": [0,1]},
              "reference_intermediates": "Softmax exp/sum/reciprocal and RMSNorm sum-square are reference arithmetic for profiling, not interception of native kernel internals or selected integer algorithms",
              "histogram": {"kind": "absolute_fp32_bits", "right_shift": HIST_SHIFT,
                  "bins": HIST_BINS, "percentiles": "Conservative upper bounds from histogram, capped by observed max",
                  "limitation": "Observed train distributions, not worst-case bounds or integer-model quality evidence"},
              "gamma_ranges": {name: {"minimum": float(module.weight.min()), "maximum": float(module.weight.max())}
                  for name, module in model.named_modules() if name.endswith(("input_layernorm", "post_attention_layernorm")) or name == "model.norm"},
              "points": {name: stats.summary() for name, stats in sorted(profiler.points.items())},
              "seconds": round(time.monotonic() - started, 3)}
    args.output_dir.mkdir(parents=True, exist_ok=True)
    save_file(tensors, args.output_dir / 'intermediate_qparams.safetensors', metadata={"scope": "Raw Linear accumulator scales and V-cache reference transfer ratios; fixed-point formats unselected"})
    write_json(args.output_dir / "intermediate_calibration.json", report)
    print(f"PASS intermediate calibration: {len(profiler.points)} points, {expected_tokens} tokens/layer; {report['seconds']}s", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    parser.add_argument("--cache-dir", type=Path, default=ROOT / ".cache/huggingface")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "results/numerical")
    parser.add_argument("--offline", action="store_true")
    calibrate(parser.parse_args())


if __name__ == "__main__":
    main()
