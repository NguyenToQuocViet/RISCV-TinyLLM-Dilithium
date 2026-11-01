"""Artifact-only integer-code execution for the frozen SmolLM2 contract.

Preparation writes config.json, coefficients.safetensors, and a shared INT8
weight bundle. This module loads those artifacts once and never reads the FP32
checkpoint, PTQ qparams, or any coefficient/table compilation code.
"""
from dataclasses import dataclass
import json
from pathlib import Path
from types import SimpleNamespace

import torch
import torch.nn.functional as F
from safetensors.torch import load_file

from ptq_integer import multiply_shift, round_divide, round_divide_scalar, round_shift


@dataclass(frozen=True)
class RuntimeFormat:
    bits: int
    scale: object
    axis: int | None = None
    signed: bool = True

    @property
    def bounds(self):
        return (-(1 << (self.bits-1)), (1 << (self.bits-1))-1) if self.signed else (0, (1 << self.bits)-1)

    @classmethod
    def from_json(cls, spec):
        return cls(int(spec["bits"]), spec["scale"], spec.get("axis"), bool(spec["signed"]))


class ArtifactCache:
    """Integer K/V codes retained between prefill and one-token decode calls."""
    def __init__(self, layer_count):
        self.keys = [None] * layer_count
        self.values = [None] * layer_count

    def get_seq_length(self, layer_idx=0):
        value = self.keys[layer_idx]
        return 0 if value is None else value.shape[-2]

    def update(self, key, value, layer_idx):
        key, value = key.to(torch.int8), value.to(torch.int8)
        previous_key, previous_value = self.keys[layer_idx], self.values[layer_idx]
        if previous_key is None:
            self.keys[layer_idx], self.values[layer_idx] = key, value
        else:
            self.keys[layer_idx] = torch.cat((previous_key, key), dim=-2)
            self.values[layer_idx] = torch.cat((previous_value, value), dim=-2)
        return self.keys[layer_idx], self.values[layer_idx]


class ContractRuntime:
    """Run a prepared contract using only serialized weights and coefficients."""
    def __init__(self, config, weights, coefficients):
        self.config = config
        self.formats = {name: RuntimeFormat.from_json(spec)
                        for name, spec in config["formats"].items()}
        self.weights = {name: value.contiguous() for name, value in weights.items()}
        self.coefficients = {name: value.contiguous() for name, value in coefficients.items()}
        self.model = config["model"]
        self.layer_count = int(self.model["layers"])
        self.hidden_size = int(self.model["hidden_size"])
        self.intermediate_size = int(self.model["intermediate_size"])
        self.vocab_size = int(self.model["vocab_size"])
        self.query_heads = int(self.model["query_heads"])
        self.kv_heads = int(self.model["kv_heads"])
        self.head_dim = int(self.model["head_dim"])
        self.groups = self.query_heads // self.kv_heads
        self.softmax = config["nonlinear"]["softmax"]
        if self.query_heads * self.head_dim != self.hidden_size or self.query_heads % self.kv_heads:
            raise ValueError("inconsistent attention geometry in artifact config")
        if not self.weights or not self.coefficients:
            raise ValueError("artifact weight and coefficient bundles must be nonempty")
        self._check_required_artifacts()

    @classmethod
    def from_config(cls, config_path):
        config_path = Path(config_path).resolve()
        with config_path.open(encoding="utf-8") as stream:
            config = json.load(stream)
        if config.get("artifact_format") != "tinyllm_integer_contract_v1":
            raise ValueError("unsupported or unprepared integer contract artifact")
        weights_path = (config_path.parent / config["weights"]).resolve()
        coefficients_path = (config_path.parent / config["coefficients"]).resolve()
        if not weights_path.is_file() or not coefficients_path.is_file():
            raise FileNotFoundError("contract weight or coefficient artifact is missing")
        weights = load_file(str(weights_path), device="cpu")
        coefficients = load_file(str(coefficients_path), device="cpu")
        return cls(config, weights, coefficients)

    @classmethod
    def from_tensors(cls, config, weights, coefficients):
        """Constructor used by small independent artifact fixtures."""
        return cls(config, weights, coefficients)

    def _check_required_artifacts(self):
        required_weights = {"shared_embedding_lm_head.weight"}
        required = {"rope.cos", "rope.sin", "softmax.exp_lut", "rms.seed_lut"}
        required.update(("embedding.to_residual.M", "embedding.to_residual.shift"))
        linear_names = ["lm_head"]
        for index in range(self.layer_count):
            prefix = f"model.layers.{index}"
            linear_names.extend((prefix+".self_attn."+name for name in
                                 ("q_proj", "k_proj", "v_proj", "o_proj")))
            linear_names.extend(prefix+".mlp."+name for name in
                                ("gate_proj", "up_proj", "down_proj"))
            attention = prefix+".self_attn"
            required.update(attention+"."+name+suffix for name in
                            ("q_rope_to_qk", "k_rope_to_cache", "qk_to_score",
                             "score_to_index", "pv_to_context") for suffix in (".M", ".shift"))
            for residual in (prefix+".residual_after_attention", prefix+".residual_after_ffn"):
                required.update(residual+"."+branch+suffix for branch in ("left_to_guard", "right_to_guard")
                                for suffix in (".M", ".shift"))
            mlp = prefix+".mlp"
            required.update(mlp+".product"+suffix for suffix in (".M", ".shift"))
            required.update(mlp+".pwl."+field for field in ("breakpoints", "slopes", "intercepts", "shifts"))
            required.update(mlp+".pwl.positive"+suffix for suffix in (".M", ".shift"))
        required.update(f"model.layers.{i}.{norm}.{suffix}"
                        for i in range(self.layer_count) for norm in ("input_layernorm", "post_attention_layernorm")
                        for suffix in ("to_t.M", "to_t.shift", "gamma_output.M", "gamma_output.shift", "epsilon"))
        required.update(("model.norm.to_t.M", "model.norm.to_t.shift",
                         "model.norm.gamma_output.M", "model.norm.gamma_output.shift", "model.norm.epsilon"))
        for layer in range(self.layer_count):
            for name in (f"model.layers.{layer}.input_layernorm",
                         f"model.layers.{layer}.post_attention_layernorm"):
                source = self.config.get("aligned_norm_inputs", {}).get(name, {})
                if source.get("axis") is not None:
                    required.update((name+".align_input.M", name+".align_input.shift"))
        final_source = self.config.get("aligned_norm_inputs", {}).get("model.norm", {})
        if final_source.get("axis") is not None:
            required.update(("model.norm.align_input.M", "model.norm.align_input.shift"))
        for name in linear_names:
            if name != "lm_head":
                required_weights.add(name+".weight")
            required.update((name+".smooth.M", name+".smooth.shift"))
            suffix = ".to_v_cache" if name.endswith(".v_proj") else ".output"
            required.update((name+suffix+".M", name+suffix+".shift"))
        missing_weights = sorted(required_weights - self.weights.keys())
        missing_coefficients = sorted(required - self.coefficients.keys())
        if missing_weights or missing_coefficients:
            missing = (["weight:"+key for key in missing_weights]
                       + ["coefficient:"+key for key in missing_coefficients])
            raise ValueError("artifact bundle is missing: " + ", ".join(missing[:8]))
        wrong_weight_dtype = [name for name in required_weights
                              if self.weights[name].dtype != torch.int8]
        if wrong_weight_dtype:
            raise TypeError("artifact weights must be signed INT8: " + ", ".join(wrong_weight_dtype[:8]))

    def _format(self, name):
        try:
            return self.formats[name]
        except KeyError as exc:
            raise KeyError(f"artifact format missing: {name}") from exc

    def _coefficient(self, name):
        try:
            return self.coefficients[name+".M"].to(torch.int64), self.coefficients[name+".shift"].to(torch.int64)
        except KeyError as exc:
            raise KeyError(f"artifact multiplier missing: {name}") from exc

    @staticmethod
    def _shaped_pair(pair, tensor, axis):
        multiplier, shift = pair
        if multiplier.ndim == 1 and multiplier.numel() != 1:
            shape = [1] * tensor.ndim
            shape[axis] = multiplier.numel()
            multiplier, shift = multiplier.reshape(shape), shift.reshape(shape)
        return multiplier, shift

    def _apply(self, value, coefficient, *, axis=-1, clamp=None):
        pair = self._shaped_pair(self._coefficient(coefficient), value, axis)
        result = multiply_shift(value, *pair)
        return result.clamp(*clamp) if clamp is not None else result

    def _embedding(self, ids):
        weight = self.weights["shared_embedding_lm_head.weight"]
        raw = weight[ids].to(torch.int64)
        multiplier = self.coefficients["embedding.to_residual.M"].to(torch.int64)[ids].unsqueeze(-1)
        shift = self.coefficients["embedding.to_residual.shift"].to(torch.int64)[ids].unsqueeze(-1)
        codes = multiply_shift(raw, multiplier, shift).clamp(*self._format("model.embed_tokens.output").bounds)
        return codes

    def _linear(self, name, value):
        source = self._apply(value, name+".smooth", axis=-1, clamp=(-2048, 2047))
        weight_name = "shared_embedding_lm_head.weight" if name == "lm_head" else name+".weight"
        try:
            weight = self.weights[weight_name]
        except KeyError as exc:
            raise KeyError(f"artifact weight missing: {weight_name}") from exc
        direct_cache = name.endswith(".v_proj")
        target = None if direct_cache else self._format(name+".output")
        output_dtype = (torch.int16 if not direct_cache and target.bits <= 16 else
                        torch.int32 if not direct_cache and target.bits <= 32 else torch.int64)
        output = torch.empty((*source.shape[:-1], weight.shape[0]), dtype=output_dtype)
        # Bound peak memory for the 49k-row tied output projection.
        chunk = 4096 if weight.shape[0] > 8192 else weight.shape[0]
        pair = self._coefficient(name+".to_v_cache" if direct_cache else name+".output")
        for start in range(0, weight.shape[0], chunk):
            stop = min(start+chunk, weight.shape[0])
            accumulator = F.linear(source.to(torch.float64), weight[start:stop].to(torch.float64)).round().to(torch.int64)
            multiplier, shift = pair
            if multiplier.ndim:
                multiplier, shift = multiplier[start:stop], shift[start:stop]
            bounds = (-(1 << 7), (1 << 7)-1) if direct_cache else target.bounds
            codes = multiply_shift(accumulator, multiplier, shift).clamp(*bounds)
            output[..., start:stop] = codes
        return output

    def _rms(self, name, codes, source_format):
        aligned = self.config.get("aligned_norm_inputs", {}).get(name)
        if source_format.axis is not None:
            if aligned is None:
                raise ValueError(f"per-channel RMS input lacks scalar alignment format: {name}")
            codes = self._apply(codes, name+".align_input", clamp=(-(1 << 23), (1 << 23)-1))
            source_format = RuntimeFormat.from_json(aligned)
        output_format = self._format(name+".output")
        x = codes.reshape(-1, codes.shape[-1])
        ft = int(self.config.get("nonlinear_contract", {}).get("rms_t_fractional_bits", 40))
        epsilon = int(self.coefficients[name+".epsilon"])
        to_t_m, to_t_s = self._coefficient(name+".to_t")
        to_t_m, to_t_s = int(to_t_m), int(to_t_s)
        square_sums = (x*x).sum(-1).tolist()
        ts = [(round_divide_scalar(total*to_t_m, 1 << to_t_s) if to_t_s >= 0 else
               (total*to_t_m) << -to_t_s) + epsilon for total in square_sums]
        ks = [(t.bit_length()-1-ft)//2 for t in ts]
        ms = [round_divide_scalar(t, 1 << (ft+2*k-16)) if ft+2*k-16 >= 0 else
              t << -(ft+2*k-16) for t, k in zip(ts, ks)]
        seed_entries = self.coefficients["rms.seed_lut"].numel()
        m = torch.tensor(ms, dtype=torch.int64).clamp(1 << 16, (4 << 16)-1)
        index = ((m-(1 << 16))*seed_entries // (3 << 16)).clamp(0, seed_entries-1)
        seed = self.coefficients["rms.seed_lut"].to(torch.int64)[index]
        a = seed*seed
        b = round_shift(m*a, 28)
        u = round_shift(seed*((3 << 16)-b), 17)
        gm, gs = self._coefficient(name+".gamma_output")
        shift = gs.reshape(1, -1)+14+torch.tensor(ks, dtype=torch.int64)[:, None]
        result = multiply_shift(x*u[:, None], gm.to(torch.int64).reshape(1, -1), shift)
        return result.clamp(*output_format.bounds).reshape(codes.shape)

    def _rope(self, codes, positions):
        if positions.ndim == 1:
            positions = positions.unsqueeze(0)
        if positions.numel() and (int(positions.min()) < 0 or int(positions.max()) >= self.coefficients["rope.cos"].shape[0]):
            raise ValueError("position is outside the prepared RoPE table")
        cosine = self.coefficients["rope.cos"].to(torch.int64)[positions].unsqueeze(1)
        sine = self.coefficients["rope.sin"].to(torch.int64)[positions].unsqueeze(1)
        a, b = codes[..., :self.head_dim//2], codes[..., self.head_dim//2:]
        bound = (1 << (int(self.config["nonlinear"]["rope"]["coefficient_bits"])-1))-1
        return torch.cat((round_divide(a*cosine-b*sine, bound),
                          round_divide(b*cosine+a*sine, bound)), dim=-1)

    def _softmax(self, scores, allowed, prefix):
        maximum = scores.masked_fill(~allowed, torch.iinfo(torch.int64).min).amax(-1, keepdim=True)
        difference = maximum-scores
        indices = self._apply(difference, prefix+".score_to_index", axis=1).clamp(0, self.softmax["entries"]-1)
        exponential = self.coefficients["softmax.exp_lut"].to(torch.int64)[indices].masked_fill(~allowed, 0)
        denominator = exponential.sum(-1, keepdim=True)
        if not torch.all(denominator >= 255):
            raise ArithmeticError("IndexSoftmax denominator invariant")
        bits = int(self.softmax["probability_bits"])
        return round_divide(exponential*((1 << bits)-1), denominator)

    def _attention(self, index, hidden, positions, past, use_cache, attention_mask):
        prefix = f"model.layers.{index}.self_attn"
        batch, seq, _ = hidden.shape
        projected = {}
        for name in ("q_proj", "k_proj", "v_proj"):
            projected[name] = self._linear(f"model.layers.{index}.self_attn.{name}", hidden)
        q = projected["q_proj"].view(batch, seq, self.query_heads, self.head_dim).transpose(1, 2)
        k = projected["k_proj"].view(batch, seq, self.kv_heads, self.head_dim).transpose(1, 2)
        v = projected["v_proj"]
        q = self._rope(q, positions)
        k = self._rope(k, positions)
        q = self._apply(q, prefix+".q_rope_to_qk", axis=1,
                        clamp=self._format(prefix+".query_post_rope").bounds)
        k = self._apply(k, prefix+".k_rope_to_cache", axis=1,
                        clamp=(-(1 << 7), (1 << 7)-1))
        v = v.view(batch, seq, self.kv_heads, self.head_dim).transpose(1, 2)
        if past is not None:
            k, v = past.update(k, v, index)
        key_length = k.shape[-2]
        repeated_k = k.repeat_interleave(self.groups, dim=1)
        repeated_v = v.repeat_interleave(self.groups, dim=1)
        dot = torch.matmul(q.to(torch.float64), repeated_k.to(torch.float64).transpose(-2, -1)).round().to(torch.int64)
        score = self._apply(dot, prefix+".qk_to_score", axis=1,
                            clamp=self._format(prefix+".score").bounds)
        qpositions = positions
        if qpositions.ndim == 1:
            qpositions = qpositions.unsqueeze(0).expand(batch, -1)
        key_positions = torch.arange(key_length, dtype=torch.int64)
        allowed = key_positions.reshape(1, 1, 1, -1) <= qpositions.reshape(batch, 1, seq, 1)
        if attention_mask is not None:
            mask = torch.as_tensor(attention_mask)
            if mask.ndim == 2:
                allowed &= mask[:, None, None, :key_length].bool()
        probabilities = self._softmax(score, allowed, prefix)
        pv = torch.matmul(probabilities.to(torch.float64), repeated_v.to(torch.float64)).round().to(torch.int64)
        pv = self._apply(pv, prefix+".pv_to_context", axis=1,
                         clamp=self._format(prefix+".context").bounds)
        context = pv.transpose(1, 2).contiguous().reshape(batch, seq, self.hidden_size)
        output = self._linear(f"model.layers.{index}.self_attn.o_proj", context)
        return output

    def _silu(self, index, codes):
        prefix = f"model.layers.{index}.mlp"
        key = prefix+".pwl."
        # A logical 16-bit input may be held in INT16, while a real-domain
        # breakpoint such as +/-8 can map just outside that container. Promote
        # before scalar comparisons so PyTorch cannot narrow-wrap the bound.
        codes = codes.to(torch.int64)
        breakpoints = self.coefficients[key+"breakpoints"].to(torch.int64)
        segment = torch.bucketize(codes.contiguous(), breakpoints[1:-1], right=True)
        slope = self.coefficients[key+"slopes"].to(torch.int64)[segment]
        intercept = self.coefficients[key+"intercepts"].to(torch.int64)[segment]
        shifts = self.coefficients[key+"shifts"].to(torch.int64)[segment]
        middle = round_shift(codes*slope+intercept, shifts)
        positive = self._apply(codes, prefix+".pwl.positive")
        output = torch.where(codes < breakpoints[0], 0,
                             torch.where(codes >= breakpoints[-1], positive, middle))
        return output.clamp(*self._format(prefix+".silu_output").bounds)

    def _residual(self, index, kind, left, right):
        name = f"model.layers.{index}.residual_after_{kind}"
        fmt = self._format(name)
        lhs = self._apply(left, name+".left_to_guard", clamp=None)
        rhs = self._apply(right, name+".right_to_guard", clamp=None)
        return round_shift(lhs+rhs, 20).clamp(*fmt.bounds)

    def _forward(self, input_ids, attention_mask=None, position_ids=None,
                 cache_position=None, past_key_values=None, use_cache=False,
                 logits_to_keep=0):
        ids = torch.as_tensor(input_ids, dtype=torch.long)
        if ids.ndim == 1:
            ids = ids.unsqueeze(0)
        if ids.ndim != 2 or ids.numel() == 0:
            raise ValueError("input_ids must have shape [batch, sequence]")
        batch, seq = ids.shape
        if batch != 1:
            raise ValueError("the prepared model contract supports batch size 1")
        if past_key_values is not None and not isinstance(past_key_values, ArtifactCache):
            raise TypeError("past_key_values must be an ArtifactCache")
        if use_cache and past_key_values is None:
            past_key_values = ArtifactCache(self.layer_count)
        past_length = 0 if past_key_values is None else past_key_values.get_seq_length(0)
        if cache_position is not None:
            positions = torch.as_tensor(cache_position, dtype=torch.int64).reshape(-1)
        elif position_ids is not None:
            positions = torch.as_tensor(position_ids, dtype=torch.int64)
            if positions.ndim == 2:
                positions = positions[0]
        else:
            positions = torch.arange(past_length, past_length+seq, dtype=torch.int64)
        if positions.numel() != seq:
            raise ValueError("position count must equal input sequence length")
        expected_positions = torch.arange(past_length, past_length+seq, dtype=torch.int64)
        if not torch.equal(positions.cpu(), expected_positions):
            raise ValueError("positions must be contiguous after the cached prefix")
        if past_length + seq > 512:
            raise ValueError("the prepared RoPE/cache contract is limited to 512 tokens")
        hidden = self._embedding(ids)
        for index in range(self.layer_count):
            residual = hidden
            norm_name = f"model.layers.{index}.input_layernorm"
            source = self._format("model.embed_tokens.output" if index == 0 else f"model.layers.{index-1}.residual_after_ffn")
            normalized = self._rms(norm_name, residual, source)
            attention = self._attention(index, normalized, positions, past_key_values, use_cache, attention_mask)
            hidden = self._residual(index, "attention", residual, attention)
            residual = hidden
            norm_name = f"model.layers.{index}.post_attention_layernorm"
            normalized = self._rms(norm_name, residual, self._format(f"model.layers.{index}.residual_after_attention"))
            prefix = f"model.layers.{index}.mlp"
            gate = self._linear(prefix+".gate_proj", normalized)
            up = self._linear(prefix+".up_proj", normalized)
            activated = self._silu(index, gate)
            product = multiply_shift(activated*up, *self._coefficient(prefix+".product"))
            product = product.clamp(*self._format(prefix+".gate_product").bounds)
            down = self._linear(prefix+".down_proj", product)
            hidden = self._residual(index, "ffn", residual, down)
        final_source = self._format(f"model.layers.{self.layer_count-1}.residual_after_ffn")
        normalized = self._rms("model.norm", hidden, final_source)
        logits = self._linear("lm_head", normalized)
        logits_format = self._format("lm_head.output")
        scale = torch.as_tensor(logits_format.scale, dtype=torch.float64)
        if scale.ndim:
            shape = [1] * logits.ndim
            shape[logits_format.axis] = scale.numel()
            scale = scale.reshape(shape)
        float_logits = (logits.to(torch.float64)*scale).to(torch.float32)
        cache = past_key_values
        if isinstance(logits_to_keep, int) and logits_to_keep > 0:
            float_logits = float_logits[:, -logits_to_keep:]
            logits = logits[:, -logits_to_keep:]
        elif isinstance(logits_to_keep, torch.Tensor):
            float_logits = float_logits.index_select(1, logits_to_keep.to(torch.long))
            logits = logits.index_select(1, logits_to_keep.to(torch.long))
        elif not isinstance(logits_to_keep, int) or logits_to_keep < 0:
            raise ValueError("logits_to_keep must be a nonnegative integer or position tensor")
        output = SimpleNamespace(logits=float_logits, logit_codes=logits,
                                 past_key_values=cache if use_cache else None)
        return output

    def __call__(self, *, input_ids, attention_mask=None, position_ids=None,
                 cache_position=None, past_key_values=None, use_cache=False,
                 logits_to_keep=0, **_kwargs):
        return self._forward(input_ids, attention_mask, position_ids,
                             cache_position, past_key_values, use_cache, logits_to_keep)

    def new_cache(self):
        return ArtifactCache(self.layer_count)

    @torch.inference_mode()
    def full_logits(self, ids):
        return self(input_ids=torch.tensor([ids], dtype=torch.long),
                    attention_mask=torch.ones((1, len(ids)), dtype=torch.long),
                    use_cache=False).logits[0]

    @torch.inference_mode()
    def cached_logits(self, ids, prefill_length):
        return self.cached_outputs(ids, prefill_length)[0].cpu().numpy()

    @torch.inference_mode()
    def cached_logit_codes(self, ids, prefill_length):
        return self.cached_outputs(ids, prefill_length)[1]

    @torch.inference_mode()
    def cached_outputs(self, ids, prefill_length, *, verify_prefix=False):
        if not 1 <= prefill_length <= len(ids):
            raise ValueError("invalid prefill length")
        cache = ArtifactCache(self.layer_count)
        logits_rows, code_rows = [], []
        prefix = None
        chunks = [(0, prefill_length)] + [(i, i+1) for i in range(prefill_length, len(ids))]
        for chunk_index, (start, end) in enumerate(chunks):
            out = self(input_ids=torch.tensor([ids[start:end]], dtype=torch.long),
                       attention_mask=torch.ones((1, end), dtype=torch.long),
                       position_ids=torch.arange(start, end).unsqueeze(0),
                       cache_position=torch.arange(start, end),
                       past_key_values=cache, use_cache=True)
            logits_rows.append(out.logits[0])
            code_rows.append(out.logit_codes[0])
            if verify_prefix and chunk_index == 0:
                prefix = [(key.clone(), value.clone()) for key, value in zip(cache.keys, cache.values)]
        prefix_preserved = None
        if prefix is not None:
            prefix_preserved = all(torch.equal(cache.keys[index][..., :prefill_length, :], key)
                                   and torch.equal(cache.values[index][..., :prefill_length, :], value)
                                   for index, (key, value) in enumerate(prefix))
            if not prefix_preserved:
                raise AssertionError("artifact KV cache prefix changed during decode")
        return torch.cat(logits_rows, dim=0), torch.cat(code_rows, dim=0), prefix_preserved


def load_prepared_contract(config_path):
    return ContractRuntime.from_config(config_path)
