"""Integer arithmetic candidates for the numerical-contract experiment.

Integer elementwise primitives are exact. Combined candidates use FP64 code
GEMM with absolute-product sums below 2**53, hence exact integer reductions.
Sampled reductions are also checked against int64 dot products. This is an
integer-arithmetic simulation, not the future integer-kernel implementation.
"""
from contextlib import contextmanager
from dataclasses import dataclass
import math
from types import MethodType

import numpy as np
import torch
import torch.nn.functional as F
from transformers.models.llama.modeling_llama import apply_rotary_pos_emb, repeat_kv


def round_divide_scalar(n, d):
    """Exact signed nearest, ties-to-even division; d > 0."""
    if d <= 0:
        raise ValueError("positive denominator required")
    q, r = divmod(abs(int(n)), int(d))
    q += 2*r > d or (2*r == d and q % 2 == 1)
    return -q if n < 0 else q


def round_divide(n, d):
    n, d = torch.broadcast_tensors(torch.as_tensor(n, dtype=torch.int64),
                                   torch.as_tensor(d, dtype=torch.int64))
    if torch.any(d <= 0):
        raise ValueError("positive denominator required")
    if torch.any(n == torch.iinfo(torch.int64).min):
        return torch.tensor([round_divide_scalar(a, b) for a, b in zip(n.reshape(-1).tolist(), d.reshape(-1).tolist())], dtype=torch.int64).reshape(n.shape)
    a = n.abs()
    q, r = a // d, a % d
    return n.sign() * (q + ((r > d-r) | ((r == d-r) & (q % 2 == 1))))


def round_shift(n, shift):
    n, shift = torch.broadcast_tensors(torch.as_tensor(n, dtype=torch.int64),
                                       torch.as_tensor(shift, dtype=torch.int64))
    if torch.any(shift >= 63) or torch.any(n == torch.iinfo(torch.int64).min):
        return torch.tensor([round_divide_scalar(a, 1 << s) if s >= 0 else a << -s
                             for a, s in zip(n.reshape(-1).tolist(), shift.reshape(-1).tolist())], dtype=torch.int64).reshape(n.shape)
    positive = shift.clamp(0, 62)
    rounded = round_divide(n, torch.bitwise_left_shift(torch.ones_like(n), positive))
    if torch.any(shift < 0):
        largest = int(n.abs().max())
        if largest.bit_length()+max(0, -int(shift.min())) >= 63:
            return torch.tensor([round_divide_scalar(a, 1 << s) if s >= 0 else a << -s
                                 for a, s in zip(n.reshape(-1).tolist(), shift.reshape(-1).tolist())], dtype=torch.int64).reshape(n.shape)
    return torch.where(shift < 0, torch.bitwise_left_shift(n, (-shift).clamp(0, 62)), rounded)


def encode_multiplier(coefficient, bits=24):
    """c ~= M*2**(-shift), signed normalized M, |M| <= 2**bits-1."""
    if bits not in (16, 24, 31):
        raise ValueError("coefficient bits must be 16, 24, or 31")
    c = np.asarray(coefficient, dtype=np.float64)
    if not np.isfinite(c).all():
        raise ValueError("finite coefficients required")
    fraction, exponent = np.frexp(c)
    m = np.rint(fraction * (1 << bits)).astype(np.int64)
    overflow = np.abs(m) == (1 << bits)
    m = np.where(overflow, m // 2, m)
    shift = bits - exponent - overflow.astype(np.int64)
    shift = np.where(m == 0, 0, shift).astype(np.int64)
    return torch.from_numpy(np.array(m, copy=True)), torch.from_numpy(np.array(shift, copy=True))


def multiply_shift(value, multiplier, shift):
    """Exact product followed by one RNE, including bigint fallback when needed."""
    x, m, s = torch.broadcast_tensors(torch.as_tensor(value, dtype=torch.int64),
                                     torch.as_tensor(multiplier, dtype=torch.int64),
                                     torch.as_tensor(shift, dtype=torch.int64))
    maximum_product = int(x.abs().max()) * int(m.abs().max()) if x.numel() else 0
    left = max(0, -int(s.min())) if s.numel() else 0
    if maximum_product.bit_length() + left < 63:
        return round_shift(x*m, s)
    result = np.empty(x.shape, dtype=np.int64)
    for i, (a, b, sh) in enumerate(zip(x.reshape(-1).tolist(), m.reshape(-1).tolist(), s.reshape(-1).tolist())):
        product = a*b
        result.flat[i] = round_divide_scalar(product, 1 << sh) if sh >= 0 else product << -sh
    return torch.from_numpy(result)


def rescale(value, coefficient, bits=24):
    return multiply_shift(value, *encode_multiplier(coefficient, bits))


def signed_bounds(bits):
    return -(1 << (bits-1)), (1 << (bits-1))-1


def minmax_scale(lower, upper, bits, unsigned=False):
    lower, upper = np.asarray(lower, dtype=np.float64), np.asarray(upper, dtype=np.float64)
    if unsigned:
        scale = np.maximum(upper, 0) / ((1 << bits)-1)
    else:
        scale = np.maximum(np.maximum(-lower, 0)/(1 << (bits-1)),
                           np.maximum(upper, 0)/((1 << (bits-1))-1))
    return np.where(scale > 0, scale, 1.).tolist()


@dataclass
class Format:
    bits: int
    scale: object
    axis: int | None = None
    unsigned: bool = False

    @property
    def bounds(self):
        return (0, (1 << self.bits)-1) if self.unsigned else signed_bounds(self.bits)

    def broadcast(self, tensor):
        scale = torch.as_tensor(self.scale, dtype=torch.float64)
        if scale.ndim and self.axis is not None:
            shape = [1]*tensor.ndim
            shape[self.axis] = len(scale)
            scale = scale.reshape(shape)
        return scale

    def dictionary(self):
        lower,upper = self.bounds
        scale = np.asarray(self.scale,dtype=np.float64)
        return {"bits": self.bits, "signed": not self.unsigned, "scale": self.scale,
                "axis": self.axis, "zero_point": 0, "code_range": list(self.bounds),
                "real_range":{"minimum":(lower*scale).tolist(),"maximum":(upper*scale).tolist()},
                "container_bits": 8 if self.bits <= 8 else 16 if self.bits <= 16 else 32 if self.bits <= 32 else 64}


def decoded(codes, fmt):
    result = (codes.double() * fmt.broadcast(codes)).float()
    result._contract = (codes, fmt)
    return result


def encode(value, fmt, coefficient_bits=24):
    old = getattr(value, "_contract", None)
    if old is None:
        raw = torch.round(value.double()/fmt.broadcast(value)).to(torch.int64)
    else:
        codes, previous = old
        ratio = previous.broadcast(value)/fmt.broadcast(value)
        raw = rescale(codes, ratio, coefficient_bits)
    low, high = fmt.bounds
    return raw.clamp(low, high), raw


def softmax_lut(c=8, entries=32):
    lut = torch.round(255*torch.exp(-c*torch.arange(entries, dtype=torch.float64)/(entries-1))).long()
    lut[-1] = 0
    return lut


def index_softmax(score_codes, score_scale, allowed, *, c=8, entries=32,
                  probability_bits=12, coefficient_bits=24):
    """Return integer probability codes; masked entries are exactly zero."""
    allowed = torch.broadcast_to(allowed.bool(), score_codes.shape)
    if not allowed.any(-1).all():
        raise ValueError("every attention row must have a valid key")
    maximum = score_codes.masked_fill(~allowed, torch.iinfo(torch.int64).min).amax(-1, keepdim=True)
    difference = maximum-score_codes
    indices = rescale(difference, torch.as_tensor(score_scale, dtype=torch.float64)*(entries-1)/c,
                      coefficient_bits).clamp(0, entries-1)
    exponential = softmax_lut(c, entries)[indices].masked_fill(~allowed, 0)
    denominator = exponential.sum(-1, keepdim=True)
    if not torch.all(denominator >= 255):
        raise ArithmeticError("IndexSoftmax denominator invariant")
    return round_divide(exponential*((1 << probability_bits)-1), denominator)


def rope_rom(coefficient_bits=16):
    p = torch.arange(512, dtype=torch.float64)[:, None]
    omega = 100000. ** (-2*torch.arange(32, dtype=torch.float64)/64)
    bound = (1 << (coefficient_bits-1))-1
    phase = p*omega
    return torch.round(phase.cos()*bound).long(), torch.round(phase.sin()*bound).long()


def integer_rope(codes, positions, coefficient_bits=16):
    """BHTD split-half rotation. Input and output share one scale per head."""
    cosine, sine = rope_rom(coefficient_bits)
    c, s = cosine[positions].unsqueeze(1), sine[positions].unsqueeze(1)
    a, b = codes[..., :32], codes[..., 32:]
    bound = (1 << (coefficient_bits-1))-1
    return torch.cat((round_divide(a*c-b*s, bound), round_divide(b*c+a*s, bound)), -1)


def rms_seed_lut(seed_entries=64):
    """Runtime UQ0.14 reciprocal-square-root seeds for normalized m in [1,4)."""
    centers = 1+3*(torch.arange(seed_entries, dtype=torch.float64)+.5)/seed_entries
    return torch.round(centers.rsqrt()*(1 << 14)).long()


def rms_integer(codes, input_scale, gamma, output_format, *, seed_entries=64,
                coefficient_bits=24, epsilon=1e-5, t_fractional_bits=40):
    """LOD on real t in U*.Ft, Q16 m, UQ0.14 seed, exactly one NR step.

    Per-token wide reduction-to-t conversion uses Python ints. All vector MACs
    use checked int64 (bigint fallback in multiply_shift). Input scale scalar.
    """
    x = codes.reshape(-1, codes.shape[-1])
    d = x.shape[-1]
    delta = float(input_scale)
    eps_code = max(1, round(epsilon*(1 << t_fractional_bits)))
    mcoef, shift = encode_multiplier(delta*delta*(1 << t_fractional_bits)/d, coefficient_bits)
    mcoef, shift = int(mcoef), int(shift)
    square_sums = (x*x).sum(-1).tolist()
    ts = [(round_divide_scalar(total*mcoef, 1 << shift) if shift >= 0 else
           (total*mcoef) << -shift) + eps_code for total in square_sums]
    ks = [((t.bit_length()-1-t_fractional_bits)//2) for t in ts]
    ms = [round_divide_scalar(t, 1 << (t_fractional_bits+2*k-16)) if t_fractional_bits+2*k-16 >= 0 else
          t << -(t_fractional_bits+2*k-16) for t, k in zip(ts, ks)]
    m = torch.tensor(ms, dtype=torch.int64).clamp(1 << 16, (4 << 16)-1)
    index = ((m-(1 << 16))*seed_entries // (3 << 16)).clamp(0, seed_entries-1)
    seed = rms_seed_lut(seed_entries)[index]
    a = seed*seed  # UQ0.28
    b = round_shift(m*a, 28)  # UQ2.16
    u = round_shift(seed*((3 << 16)-b), 17)  # UQ0.14
    ratio = gamma.double()*delta/torch.as_tensor(output_format.scale, dtype=torch.float64)
    multiplier, out_shift = encode_multiplier(ratio, coefficient_bits)
    out_shift = out_shift.reshape(1, -1)+14+torch.tensor(ks)[:, None]
    result = multiply_shift(x*u[:, None], multiplier.reshape(1, -1), out_shift)
    return result.clamp(*output_format.bounds).reshape(codes.shape)


def fit_silu(segments=16, threshold=8, coefficient_bits=24):
    """Quantization-aware greedy nonuniform split on a fixed signed FP64 grid.

    PWL coefficients are Q*.20; output MAC has one RNE after slope*x+intercept.
    Candidate breakpoint splits are a fixed grid, not fitted on selection data.
    """
    grid = np.linspace(-threshold, threshold, 4097)
    truth = grid/(1+np.exp(-grid))
    frac = min(coefficient_bits-2, 20)

    def fit(left, right):
        xx, yy = grid[left:right+1], truth[left:right+1]
        slope, intercept = np.polyfit(xx, yy, 1)
        aa, bb = round(slope*(1 << frac)), round(intercept*(1 << frac))
        # Evaluate the actual per-segment common-shift MAC at the reference
        # signed grid (delta_in=delta_out=2**-12), including coefficient loss.
        ratio_a, ratio_b = aa/(1 << frac), bb*(1 << 12)/(1 << frac)
        _, exponent = math.frexp(max(abs(ratio_a),abs(ratio_b)))
        sh = coefficient_bits-exponent
        ma, mb = round(math.ldexp(ratio_a,sh)),round(math.ldexp(ratio_b,sh))
        if max(abs(ma),abs(mb)) >= (1 << coefficient_bits):
            sh -= 1
            ma, mb = round(math.ldexp(ratio_a,sh)),round(math.ldexp(ratio_b,sh))
        predicted = np.rint(np.ldexp(ma*np.rint(xx*(1 << 12))+mb,-sh))/(1 << 12)
        loss = float(np.square(yy-predicted).sum())
        return loss, aa, bb

    intervals = [(0, 4096)]
    while len(intervals) < segments:
        best = None
        for number, (left, right) in enumerate(intervals):
            original = fit(left, right)[0]
            for split in range(left+16, right-15, 16):
                improvement = original-fit(left, split)[0]-fit(split, right)[0]
                if best is None or improvement > best[0]:
                    best = improvement, number, split
        _, number, split = best
        left, right = intervals[number]
        intervals[number:number+1] = [(left, split), (split, right)]
    coefficients = [fit(left, right)[1:] for left, right in intervals]
    return {"threshold": threshold, "segments": segments, "fractional_bits": frac,
            "breakpoints": [float(grid[left]) for left, _ in intervals]+[float(threshold)],
            "slopes": [a for a, _ in coefficients], "intercepts": [b for _, b in coefficients]}


def compile_silu(input_scale, output_format, table, coefficient_bits=24):
    """Per-segment common shift; both signed coefficient magnitudes <2**bits."""
    frac = table["fractional_bits"]
    slopes = np.asarray(table["slopes"], dtype=np.float64)*float(input_scale)/((1 << frac)*float(output_format.scale))
    intercepts = np.asarray(table["intercepts"], dtype=np.float64)/((1 << frac)*float(output_format.scale))
    _, exponent = np.frexp(np.maximum(np.abs(slopes), np.abs(intercepts)))
    shift = coefficient_bits-exponent
    aa = np.rint(np.ldexp(slopes, shift)).astype(np.int64)
    bb = np.rint(np.ldexp(intercepts, shift)).astype(np.int64)
    overflow = np.maximum(np.abs(aa), np.abs(bb)) >= (1 << coefficient_bits)
    shift -= overflow.astype(np.int64)
    aa = np.rint(np.ldexp(slopes, shift)).astype(np.int64)
    bb = np.rint(np.ldexp(intercepts, shift)).astype(np.int64)
    return {"breakpoints": [math.ceil(v/float(input_scale)) for v in table["breakpoints"]],
            "slopes": aa.tolist(), "intercepts": bb.tolist(), "shifts": shift.tolist()}


def silu_integer(codes, input_scale, output_format, table, coefficient_bits=24):
    scale = float(input_scale)
    compiled = compile_silu(input_scale, output_format, table, coefficient_bits)
    breakpoints = torch.tensor(compiled["breakpoints"], dtype=torch.int64)
    index = torch.bucketize(codes.contiguous(), breakpoints[1:-1], right=True)
    slope, intercept, shifts = (torch.tensor(compiled[key]) for key in ("slopes", "intercepts", "shifts"))
    middle = round_shift(codes*slope[index]+intercept[index], shifts[index])
    positive = rescale(codes, scale/float(output_format.scale), coefficient_bits)
    result = torch.where(codes < breakpoints[0], 0,
                         torch.where(codes >= breakpoints[-1], positive, middle))
    return result.clamp(*output_format.bounds)


def inventory(stats):
    """Only real proposed stored/requant interfaces, not every profiling probe."""
    points = {}
    for name in stats:
        if name == "model.embed_tokens.output":
            family = "embedding"
        elif name == "lm_head.output":
            family = "logits"
        elif name.endswith("layernorm.output") or name == "model.norm.output":
            family = "norm"
        elif name.endswith(("q_proj.output", "k_proj.output")):
            family = "q_pre" if name.endswith("q_proj.output") else "k_pre"
        elif name.endswith("query_post_rope"):
            family = "q_post"
        elif name.endswith(".score"):
            family = "score"
        elif name.endswith("probability_unmasked"):
            family = "probability"
        elif name.endswith(".context"):
            family = "context"
        elif name.endswith(("o_proj.output", "down_proj.output")):
            family = "residual_branch"
        elif name.endswith(("residual_after_attention", "residual_after_ffn")):
            family = "residual"
        elif name.endswith(("gate_proj.output", "up_proj.output")):
            family = "gate_up"
        elif name.endswith("silu_output"):
            family = "silu"
        elif name.endswith("gate_product"):
            family = "product"
        else:
            continue
        points[name] = family
    return points


class ContractAdapter:
    """Host preparation/simulation adapter; it does not load exported coefficient bundles.

    Integer coefficients are recompiled from fixed config scales for simulated
    executions. This is not the integer-kernel golden model.
    """
    def __init__(self, model, baseline, statistics):
        self.model, self.baseline, self.statistics = model, baseline, statistics
        self.inventory = inventory(statistics)
        self.trial = {"name": "disabled", "points": {}, "nonlinear": {}}
        self.bindings = []
        self.formats = {}
        self.point_metrics = {}
        self.replay = {}
        self.collect_replay = False
        self.mac_checks = {}
        self.internal_formats = {}
        self.pwl_cache = {}
        self.weights = {}
        self.final_norm_codes = None

    def set_trial(self, trial):
        if trial.get("mac_dtype", "float32") != self.trial.get("mac_dtype", "float32"):
            self.weights.clear()
        self.trial = trial
        self.final_norm_codes = None
        if trial.get("integer_coefficients"):
            self.baseline.materialized.clear()
        if "formats" in trial:
            self.formats = {name:Format(spec["bits"],spec["scale"],spec.get("axis"),not spec["signed"])
                            for name,spec in trial["formats"].items()}
        else:
            self.formats = {name: self.make_format(name, spec) for name, spec in trial.get("points", {}).items()}
        self.point_metrics = {}

    def make_format(self, name, spec):
        if "scale" in spec:
            return Format(spec["bits"], spec["scale"], spec.get("axis"), spec.get("unsigned", False))
        stat = self.statistics[name]
        unsigned = name.endswith("probability_unmasked")
        bits = spec["bits"]
        if unsigned:
            return Format(bits, 1/((1 << bits)-1), None, True)
        axis = None
        if spec.get("policy") == "per_channel":
            lower, upper, axis = stat["groups"]["minimum"], stat["groups"]["maximum"], -1
        elif self.inventory[name] in ("q_pre", "k_pre"):
            g = stat["groups"]
            size = 9 if self.inventory[name] == "q_pre" else 3
            lower = np.asarray(g["minimum"]).reshape(size, 64).min(-1).repeat(64)
            upper = np.asarray(g["maximum"]).reshape(size, 64).max(-1).repeat(64)
            axis = -1
        elif self.inventory[name] in ("q_post", "score"):
            lower, upper, axis = stat["groups"]["minimum"], stat["groups"]["maximum"], 1
        else:
            lower, upper = stat["minimum"], stat["maximum"]
        scale = minmax_scale(lower, upper, bits)
        return Format(bits, scale, axis)

    def note(self, name, before, after, raw, fmt):
        if not self.trial.get("metrics", True):
            return
        low, high = fmt.bounds
        metrics = self.point_metrics.setdefault(name, {"elements": 0, "clipped": 0, "zeros": 0,
                                                       "squared_error": 0., "signal_square": 0.})
        metrics["elements"] += before.numel()
        metrics["clipped"] += int(((raw < low) | (raw > high)).sum())
        metrics["zeros"] += int((after == 0).sum())
        difference = before.double()-after.double()
        metrics["squared_error"] += float(difference.square().sum())
        metrics["signal_square"] += float(before.double().square().sum())

    def point(self, name, value):
        if self.collect_replay and name in self.inventory and name not in self.replay:
            sample = value.detach()
            if sample.ndim >= 3:
                dimension = 2 if sample.ndim == 4 else 1
                indices = torch.tensor(sorted(set((0, sample.shape[dimension]//2, sample.shape[dimension]-1))))
                sample = sample.index_select(dimension, indices)
                if sample.ndim == 4 and sample.shape[-1] > 64:
                    sample = sample.index_select(3, torch.tensor([0, sample.shape[-1]//2, sample.shape[-1]-1]))
            self.replay[name] = sample.clone()
        if name not in self.formats:
            return value
        fmt = self.formats[name]
        codes, raw = encode(value, fmt, self.trial.get("coefficient_bits", 24))
        result = decoded(codes, fmt)
        if name == "model.norm.output":
            self.final_norm_codes = codes,fmt
        self.note(name, value, result, raw, fmt)
        return result

    def active_nonlinear(self, family, name):
        values = self.trial.get("nonlinear", {})
        return values.get(name, values.get(family))

    def nonlinear_format(self, name):
        return self.formats.get(name, self.make_format(name, {"bits": 16}))

    def as_codes(self, value, fallback_name):
        if hasattr(value, "_contract"):
            return value._contract
        fmt = self.nonlinear_format(fallback_name)
        return encode(value, fmt)[0], fmt

    def linear(self, module, value, name, original):
        # Frozen baseline for isolated probes. Combined models use integer
        # smoothing/requant coefficients and code-domain simulated GEMM.
        if not self.trial.get("integer_coefficients"):
            return self.point(name+".output", original(value))
        input_name = name+".input"
        delta = self.baseline.points[input_name].fq.scale.double()
        smoothing = self.baseline.smooth_scales.get(name, torch.tensor(1.)).double()
        source_codes = getattr(value,"_contract",None)
        if source_codes is None and name == "lm_head" and self.final_norm_codes is not None:
            code,source = self.final_norm_codes
            if code.shape == value.shape:
                source_codes = code,source
            elif source.bits <= 16:
                # Transformers slices hidden_states before LM head; small-code
                # FP32 carriers have an injective, exact code recovery.
                source_codes = encode(value,source)[0],source
        if source_codes is not None:
            code, source = source_codes
            code = rescale(code, source.broadcast(value)/(smoothing*delta),
                           self.trial.get("coefficient_bits", 24)).clamp(-2048, 2047)
        else:
            raise RuntimeError(f"missing integer source metadata at {name}")
        weight_name = "shared_embedding_lm_head.weight" if name == "lm_head" else name+".weight"
        if weight_name not in self.weights:
            wfmt = Format(8, self.baseline.points[weight_name].fq.scale.double().tolist(), 0)
            prepared = self.baseline.points[weight_name](self.baseline.effective_weight(weight_name))
            wc = encode(prepared, wfmt)[0]
            dtype = torch.float64 if self.trial.get("mac_dtype") == "float64" else torch.float32
            self.weights[weight_name] = wc.to(torch.int8), wc.to(dtype), wfmt
        wc, wf, wfmt = self.weights[weight_name]
        accumulator = F.linear(code.to(wf.dtype), wf).round().long()
        if self.trial.get("check_mac") and name not in self.mac_checks:
            rows = code.reshape(-1, code.shape[-1])
            indices = [0, len(rows)//2, len(rows)-1]
            out = [0, len(wc)//2, len(wc)-1]
            actual = accumulator.reshape(-1, accumulator.shape[-1])[indices][:, out]
            exact = rows[indices] @ wc[out].long().T
            self.mac_checks[name] = {"samples": exact.numel(), "different_accumulators": int((exact != actual).sum()),
                                     "max_absolute_difference": int((exact-actual).abs().max())}
            if name+".output" in self.formats:
                target = self.formats[name+".output"]
                target_scale = torch.as_tensor(target.scale,dtype=torch.float64)
                if target_scale.ndim: target_scale = target_scale[out]
                ratio = delta*torch.as_tensor(wfmt.scale,dtype=torch.float64)[out]/target_scale
                fast_codes = rescale(actual,ratio,self.trial.get("coefficient_bits",24)).clamp(*target.bounds)
                exact_codes = rescale(exact,ratio,self.trial.get("coefficient_bits",24)).clamp(*target.bounds)
                self.mac_checks[name]["different_post_requant_codes"] = int((fast_codes != exact_codes).sum())
        raw_fmt = Format(32, (delta*torch.tensor(wfmt.scale,dtype=torch.float64)).tolist(), -1)
        return self.point(name+".output", decoded(accumulator, raw_fmt))

    def norm(self, module, value, name, original, input_name):
        options = self.active_nonlinear("rms", name)
        if not options:
            return self.point(name+".output", original(value))
        # RMS uses one scalar input scale. Per-channel residual is explicitly
        # aligned once to a 24-bit scalar norm-input format before reduction.
        if hasattr(value,"_contract"):
            codes, source = value._contract
        else:
            source = self.make_format(input_name,{"bits":24})
            codes = encode(value,source)[0]
        if source.axis is not None:
            saved = self.trial.get("aligned_norm_inputs",{}).get(name)
            scalar = Format(saved["bits"],saved["scale"],saved.get("axis")) if saved else self.make_format(input_name, {"bits": 24})
            codes = encode(value, scalar, self.trial.get("coefficient_bits", 24))[0]
            source = scalar
        self.internal_formats[name+".aligned_input"] = source.dictionary()
        output = self.nonlinear_format(name+".output")
        result = rms_integer(codes, source.scale, module.weight.detach(), output,
                             seed_entries=options.get("seed_entries", 64),
                             coefficient_bits=self.trial.get("coefficient_bits", 24),
                             t_fractional_bits=options.get("t_fractional_bits",40),
                             epsilon=module.variance_epsilon)
        if name == "model.norm":
            self.final_norm_codes = result,output
        return decoded(result, output)

    def residual_add(self, left, right, name):
        if name not in self.formats or not self.trial.get("integer_coefficients"):
            return self.point(name, left+right)
        fmt = self.formats[name]
        # Exact common-scale alignment with one RNE after the sum: keep 20
        # guard fractional bits in each converted branch, round the SUM once.
        guard = Format(63, (torch.as_tensor(fmt.scale,dtype=torch.float64)/(1 << 20)).tolist(), fmt.axis)
        lq = encode(left, guard, self.trial.get("coefficient_bits", 24))[1]
        rq = encode(right, guard, self.trial.get("coefficient_bits", 24))[1]
        codes = round_shift(lq+rq, 20).clamp(*fmt.bounds)
        return decoded(codes, fmt)

    def attention(self, module, hidden_states, position_embeddings, attention_mask,
                  past_key_value=None, cache_position=None, **kwargs):
        prefix = f"model.layers.{module.layer_idx}.self_attn"
        shape = hidden_states.shape[:-1]
        qv, kv, vv = module.q_proj(hidden_states), module.k_proj(hidden_states), module.v_proj(hidden_states)
        query = qv.view(*shape, -1, 64).transpose(1, 2)
        key = kv.view(*shape, -1, 64).transpose(1, 2)
        value = vv.view(*shape, -1, 64).transpose(1, 2)
        cosine, sine = position_embeddings
        options = self.active_nonlinear("rope", prefix+".rope")
        if options:
            rotated = []
            positions = cache_position.reshape(1, -1) if cache_position is not None else torch.arange(shape[-1])[None]
            for raw, name in ((qv, "q_proj"), (kv, "k_proj")):
                qc, fmt = self.as_codes(raw, prefix+"."+name+".output")
                qc = qc.view(*shape, -1, 64).transpose(1, 2)
                # Pair-compatible per-head projection scale repeated over64.
                scales = torch.as_tensor(fmt.scale,dtype=torch.float64)
                if scales.ndim:
                    scales = scales.reshape(-1, 64)[:, 0].tolist()
                rotated.append(decoded(integer_rope(qc, positions, options.get("coefficient_bits", 16)),
                                       Format(32, scales, 1 if isinstance(scales, list) else None)))
            query, key = rotated
        else:
            query, key = apply_rotary_pos_emb(query, key, cosine, sine)
        query = self.point(prefix+".query_post_rope", query)
        if self.trial.get("integer_coefficients"):
            for kind, raw in (("K", key), ("V", value)):
                point_name = prefix+(".key_post_rope" if kind == "K" else ".value_post_projection")
                fmt = Format(8, self.baseline.points[point_name].fq.scale.double().tolist(), 1)
                if kind == "V" and hasattr(vv, "_contract"):
                    vc, vf = vv._contract
                    raw = decoded(vc.view(*shape, -1, 64).transpose(1, 2),
                                  Format(32, torch.tensor(vf.scale,dtype=torch.float64).reshape(1, 3, 1, 64).tolist()))
                result = decoded(encode(raw, fmt, self.trial.get("coefficient_bits", 24))[0], fmt)
                if kind == "K": key = result
                else: value = result
        else:
            key = self.baseline.points[prefix+".key_post_rope"](key)
            value = self.baseline.points[prefix+".value_post_projection"](value)
        if past_key_value is not None:
            key, value = past_key_value.update(key, value, module.layer_idx,
                                               {"sin": sine, "cos": cosine, "cache_position": cache_position})
        keys, values = repeat_kv(key, module.num_key_value_groups), repeat_kv(value, module.num_key_value_groups)
        if self.trial.get("integer_coefficients") and prefix+".score" in self.formats:
            qcode, qformat = self.as_codes(query, prefix+".query_post_rope")
            kformat = Format(8, self.baseline.points[prefix+".key_post_rope"].fq.scale.double().tolist(), 1)
            kcode = encode(key, kformat)[0]
            dtype = torch.float64 if self.trial.get("mac_dtype") == "float64" else torch.float32
            dot = torch.matmul(qcode.to(dtype), repeat_kv(kcode, module.num_key_value_groups).to(dtype).transpose(2, 3)).round().long()
            score_format = self.formats[prefix+".score"]
            qs = qformat.broadcast(query)
            ks = torch.tensor(kformat.scale, dtype=torch.float64).repeat_interleave(module.num_key_value_groups).reshape(1, -1, 1, 1)
            ratio = qs*ks*module.scaling/score_format.broadcast(dot)
            scores = decoded(rescale(dot, ratio, self.trial.get("coefficient_bits", 24)).clamp(*score_format.bounds), score_format)
        else:
            scores = torch.matmul(query, keys.transpose(2, 3))*module.scaling
        allowed = torch.ones_like(scores, dtype=torch.bool) if attention_mask is None else attention_mask[:, :, :, :keys.shape[-2]] == 0
        # Do not quantize finite mask sentinels.
        scores = self.point(prefix+".score", scores)
        options = self.active_nonlinear("softmax", prefix+".softmax")
        fused = bool(options and options.get("fused"))
        if options:
            score_fmt = self.nonlinear_format(prefix+".score")
            score_codes = encode(scores, score_fmt, self.trial.get("coefficient_bits", 24))[0]
            if fused:
                from ptq_contract_fused import index_softmax_components, fused_pv
                exponential,denominator = index_softmax_components(score_codes,score_fmt.broadcast(scores),allowed,
                    c=options.get("c",8),entries=options.get("entries",32),coefficient_bits=self.trial.get("coefficient_bits",24))
                vf = Format(8,self.baseline.points[prefix+".value_post_projection"].fq.scale.double().tolist(),1)
                vc = repeat_kv(encode(value,vf)[0],module.num_key_value_groups)
                cf = self.nonlinear_format(prefix+".context")
                ratio = torch.as_tensor(vf.scale,dtype=torch.float64).repeat_interleave(module.num_key_value_groups).reshape(1,-1,1,1)/float(cf.scale)
                context_codes = fused_pv(exponential,denominator,vc,ratio,self.trial.get("coefficient_bits",24))
                context = decoded(context_codes.transpose(1,2).contiguous().clamp(*cf.bounds),cf)
                probabilities = None  # E/S is carried; no rounded P tensor exists.
            else:
                pb = options.get("probability_bits", 12)
                probabilities = decoded(index_softmax(score_codes, score_fmt.broadcast(scores), allowed,
                                          c=options.get("c", 8), entries=options.get("entries", 32),
                                          probability_bits=pb, coefficient_bits=self.trial.get("coefficient_bits", 24)),
                                        Format(pb, 1/((1 << pb)-1), None, True))
        else:
            probabilities = F.softmax(scores.masked_fill(~allowed, torch.finfo(scores.dtype).min), -1, dtype=torch.float32)
        if not fused:
            probabilities = self.point(prefix+".probability_unmasked", probabilities)
        if fused:
            pass
        elif self.trial.get("integer_coefficients") and hasattr(probabilities, "_contract"):
            pc, pf = probabilities._contract
            vf = Format(8, self.baseline.points[prefix+".value_post_projection"].fq.scale.double().tolist(), 1)
            vc = repeat_kv(encode(value, vf)[0], module.num_key_value_groups)
            dtype = torch.float64 if self.trial.get("mac_dtype") == "float64" else torch.float32
            dot = torch.matmul(pc.to(dtype), vc.to(dtype)).round().long().transpose(1, 2).contiguous()
            scales = (torch.tensor(vf.scale, dtype=torch.float64).repeat_interleave(module.num_key_value_groups)*float(pf.scale)).reshape(1, 1, -1, 1)
            accumulator_bits = (((1 << pf.bits)-1+256)*128).bit_length()+1
            context = decoded(dot, Format(accumulator_bits, scales.tolist()))
        else:
            context = torch.matmul(probabilities, values).transpose(1, 2).contiguous()
        context = self.point(prefix+".context", context)
        context_shape = (*shape, -1)
        reshaped = context.reshape(context_shape)
        if hasattr(context, "_contract"):
            cc, cf = context._contract
            reshaped._contract = cc.reshape(context_shape), cf
        return module.o_proj(reshaped), probabilities

    def mlp(self, module, value, prefix):
        gate, up = module.gate_proj(value), module.up_proj(value)
        options = self.active_nonlinear("silu", prefix+".silu")
        if options:
            codes, fmt = self.as_codes(gate, prefix+".gate_proj.output")
            ofmt = self.nonlinear_format(prefix+".silu_output")
            key = options.get("segments", 16), options.get("threshold", 8), self.trial.get("coefficient_bits", 24)
            if key not in self.pwl_cache:
                self.pwl_cache[key] = self.trial.get("pwl_reference") or fit_silu(*key)
            activated = decoded(silu_integer(codes, fmt.scale, ofmt, self.pwl_cache[key], key[-1]), ofmt)
        else:
            activated = module.act_fn(gate)
        activated = self.point(prefix+".silu_output", activated)
        product = activated*up
        if self.trial.get("integer_coefficients") and hasattr(activated, "_contract") and hasattr(up, "_contract"):
            ac, af = activated._contract
            uc, uf = up._contract
            product = decoded(ac*uc, Format(af.bits+uf.bits, (torch.as_tensor(af.scale,dtype=torch.float64)*torch.as_tensor(uf.scale,dtype=torch.float64)).tolist()))
        product = self.point(prefix+".gate_product", product)
        return module.down_proj(product)

    @contextmanager
    def attached(self):
        def bind(module, forward):
            original = module.forward
            module.forward = MethodType(forward, module)
            self.bindings.append((module, original))
        try:
            for name, module in self.model.named_modules():
                original = module.forward
                if isinstance(module, torch.nn.Linear):
                    def linear(m, x, _n=name, _o=original):
                        return self.linear(m, x, _n, _o)
                    bind(module, linear)
                elif name == "model.embed_tokens":
                    def embedding(m, ids, _o=original):
                        if not self.trial.get("integer_coefficients"):
                            return self.point("model.embed_tokens.output", _o(ids))
                        wname = "shared_embedding_lm_head.weight"
                        if wname not in self.weights:
                            wf = Format(8,self.baseline.points[wname].fq.scale.double().tolist(),0)
                            prepared = self.baseline.points[wname](self.baseline.effective_weight(wname))
                            wc = encode(prepared,wf)[0]
                            dtype = torch.float64 if self.trial.get("mac_dtype") == "float64" else torch.float32
                            self.weights[wname] = wc.to(torch.int8),wc.to(dtype),wf
                        wc,_,wf = self.weights[wname]
                        lookup = wc[ids].long()
                        source = Format(8,torch.as_tensor(wf.scale,dtype=torch.float64)[ids].unsqueeze(-1).tolist())
                        return self.point("model.embed_tokens.output",decoded(lookup,source))
                    bind(module, embedding)
                elif name.endswith(("input_layernorm", "post_attention_layernorm")) or name == "model.norm":
                    if name == "model.norm":
                        source = f"model.layers.{len(self.model.model.layers)-1}.residual_after_ffn"
                    elif name.endswith("post_attention_layernorm"):
                        source = name.removesuffix("post_attention_layernorm")+"residual_after_attention"
                    else:
                        index = int(name.split(".")[2])
                        source = "model.embed_tokens.output" if index == 0 else f"model.layers.{index-1}.residual_after_ffn"
                    def norm(m, x, _n=name, _o=original, _s=source):
                        return self.norm(m, x, _n, _o, _s)
                    bind(module, norm)
                elif name.endswith(".self_attn"):
                    def attention(m, hidden_states, position_embeddings, attention_mask=None, **kw):
                        return self.attention(m, hidden_states, position_embeddings, attention_mask, **kw)
                    bind(module, attention)
                elif name.endswith(".mlp"):
                    def mlp(m, x, _n=name):
                        return self.mlp(m, x, _n)
                    bind(module, mlp)
            for index, layer in enumerate(self.model.model.layers):
                def layer_forward(m, hidden_states, attention_mask=None, position_ids=None, past_key_value=None,
                                  output_attentions=False, use_cache=False, cache_position=None,
                                  position_embeddings=None, _i=index, **kw):
                    residual = hidden_states
                    hidden_states = m.input_layernorm(hidden_states)
                    hidden_states, weights = m.self_attn(hidden_states=hidden_states, attention_mask=attention_mask,
                        position_ids=position_ids, past_key_value=past_key_value, output_attentions=output_attentions,
                        use_cache=use_cache, cache_position=cache_position, position_embeddings=position_embeddings, **kw)
                    hidden_states = self.residual_add(residual, hidden_states, f"model.layers.{_i}.residual_after_attention")
                    residual = hidden_states
                    hidden_states = m.post_attention_layernorm(hidden_states)
                    hidden_states = m.mlp(hidden_states)
                    hidden_states = self.residual_add(residual, hidden_states, f"model.layers.{_i}.residual_after_ffn")
                    return (hidden_states, weights) if output_attentions else (hidden_states,)
                bind(layer, layer_forward)
            yield self
        finally:
            for module, original in reversed(self.bindings):
                module.forward = original
            self.bindings.clear()
