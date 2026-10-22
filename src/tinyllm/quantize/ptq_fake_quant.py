"""Adapter PTQ cục bộ cho Llama/eager 4.49; các phép toán vẫn là FP32.

Attention forward follows Transformers 4.49 modeling_llama.py (Apache-2.0),
adding only post-RoPE K / post-projection V fake-quant before cache.update.
Original attention: Copyright 2022 EleutherAI and the HuggingFace Inc. team.
License: https://www.apache.org/licenses/LICENSE-2.0
"""
from contextlib import contextmanager
from copy import deepcopy
from types import MethodType
import json
from pathlib import Path

import torch
import torch.nn.functional as F
from torch.ao.quantization import FakeQuantize, MinMaxObserver, PerChannelMinMaxObserver, HistogramObserver
from transformers.models.llama.modeling_llama import apply_rotary_pos_emb, eager_attention_forward
from safetensors import safe_open
from safetensors.torch import load_file, save_file


FP32_REMAINDER = ["RMSNorm", "RoPE arithmetic", "attention QK matmul/scaling/mask/softmax/AV matmul",
                  "SiLU", "FFN gate multiply", "residual adds", "Linear accumulators", "logits"]


def default_config():
    return {"name": "w8a8kv8_static", "decoder_weight_bits": 8, "shared_weight_bits": 8,
            "activation_bits": 8, "key_bits": 8, "value_bits": 8,
            "enabled": {"W": True, "A": True, "K": True, "V": True}, "point_enabled": {},
            "weight_policy": "static_per_output_row_axis0",
            "activation_policy": "static_per_tensor", "activation_observer": "minmax",
            "kv_policy": "static_per_native_head_axis1_BHTD",
            "zero_point": 0, "rounding": "nearest_ties_to_even", "scale_dtype": "float32",
            "shared_embedding_lm_head": "one quantized weight; embedding row lookup and head projection",
            "fp32_remainder": FP32_REMAINDER}


def dynamic_token_fake_quant(value, bits):
    """Symmetric scale riêng từng vector hidden; không giảm theo token/batch."""
    if bits not in (4, 8) or value.dtype != torch.float32:
        raise ValueError("Dynamic A v0 yêu cầu FP32 và 4/8 bit")
    bound = (1 << (bits - 1)) - 1
    rows = value.reshape(-1, value.shape[-1])
    scales = (rows.abs().amax(dim=1) / bound).clamp_min(torch.finfo(torch.float32).eps)
    if not torch.isfinite(scales).all():
        raise ValueError("Dynamic scale không hữu hạn")
    zeros = torch.zeros(scales.shape, dtype=torch.int32, device=scales.device)
    return torch.fake_quantize_per_channel_affine(rows, scales, zeros, 0, -bound, bound).reshape(value.shape)


class QuantPoint:
    """Một FakeQuantize, observer và thống kê số lần gọi tại một điểm biểu diễn."""
    def __init__(self, kind, bits, axis=None, channels=1, observer="minmax", bins=2048, *, defer_qparams=False):
        if bits not in ((4, 8, 12, 16) if kind == "A" else (4, 8)):
            raise ValueError("W/K/V hỗ trợ 4/8 bit; A hỗ trợ thêm 12/16 bit")
        if observer not in ("minmax", "histogram_l2", "absolute_percentile_99.99"):
            raise ValueError("Observer không được hỗ trợ")
        if observer != "minmax" and (kind != "A" or bits != 8 or axis is not None):
            raise ValueError("Histogram/percentile chỉ dành cho A8 per-tensor")
        self.kind, self.bits, self.axis, self.channels = kind, bits, axis, channels
        self.observer, self.bins = observer, bins
        self.defer_qparams = defer_qparams
        bound = (1 << (bits - 1)) - 1
        self.kwargs = {"observer": (HistogramObserver if observer != "minmax" else
                                    MinMaxObserver if axis is None else PerChannelMinMaxObserver),
                  "dtype": torch.qint32 if bits > 8 else torch.qint8,
                  "qscheme": torch.per_tensor_symmetric if axis is None else torch.per_channel_symmetric,
                  "quant_min": -bound, "quant_max": bound, "reduce_range": False}
        if axis is not None:
            # PyTorch's fake-quant kernel rejects negative axes; Linear A tensors are [B,T,C].
            self.kwargs["ch_axis"] = 2 if kind == "A" and axis == -1 else axis
        if observer != "minmax":
            self.kwargs["bins"] = bins
        self.reset_observer()
        self.capture = None
        self.reset_counts()

    def reset_observer(self):
        # HistogramObserver.reset_min_max_vals is deliberately unimplemented in torch2.6.
        # Recreate the entire observer/FQ so repeated calibration starts with empty histograms.
        self.fq = FakeQuantize(**self.kwargs)
        self.fq.disable_fake_quant()
        self.fq.disable_observer()
        self.frozen = False
        self.freeze_calculations = 0

    def finish_observation(self):
        if self.observer == "minmax" and not self.defer_qparams:
            return
        observer = self.fq.activation_post_process
        if self.observer in ("minmax", "histogram_l2"):
            scale, zero = observer.calculate_qparams()
        else:
            # Nonnegative train histogram: upper edge of first bin whose CDF >=99.99%.
            # This is a conservative, bin-resolution approximation to the absolute percentile.
            histogram = observer.histogram.double()
            index = int(torch.searchsorted(histogram.cumsum(0), histogram.sum() * .9999))
            width = (observer.max_val - observer.min_val) / observer.bins
            threshold = observer.min_val + min(index + 1, observer.bins) * width
            scale = (threshold / self.fq.quant_max).clamp_min(observer.eps).reshape(1)
            zero = torch.zeros(1, dtype=torch.int32)
        self.fq.scale.resize_(scale.shape).copy_(scale)
        self.fq.zero_point.resize_(zero.shape).copy_(zero)
        self.freeze_calculations += 1

    def reset_counts(self):
        self.calls, self.tokens, self.last_shape = 0, 0, None

    def __call__(self, value, *, dynamic=False):
        if self.axis is not None and value.shape[self.axis] != self.channels:
            raise ValueError(f"Sai channel: {value.shape}, axis={self.axis}, cần {self.channels}")
        self.calls += 1
        self.tokens += value.shape[-2] if self.kind in ("K", "V") else 0
        self.last_shape = list(value.shape)
        if (self.defer_qparams or self.observer != "minmax") and self.fq.observer_enabled.item():
            if self.fq.fake_quant_enabled.item():
                raise ValueError("Deferred observation requires fake-quant off")
            observed = value.abs() if self.observer == "absolute_percentile_99.99" else value
            self.fq.activation_post_process(observed.detach())
            result = value  # Collect statistics only; calculate/copy qparams once at freeze.
        else:
            result = dynamic_token_fake_quant(value, self.bits) if dynamic else self.fq(value)
        if self.capture is not None:
            self.capture(value, result)
        return result

    def validate(self):
        scale, zp = self.fq.scale, self.fq.zero_point
        if scale.numel() != self.channels or zp.numel() != self.channels:
            raise ValueError(f"Sai số scale/zp: {scale.shape}, cần {self.channels}")
        if not torch.isfinite(scale).all() or not torch.all(scale > 0) or not torch.all(zp == 0):
            raise ValueError("Scale phải dương/hữu hạn, zero-point phải bằng 0")


class PTQAdapter:
    """Gắn forward trên instance, giữ nguyên Parameter gốc và weight tying."""
    def __init__(self, model, config=None):
        self.model, self.config = model, default_config() if config is None else deepcopy(config)
        if model.training:
            raise ValueError("Adapter v0 chỉ dùng model.eval()")
        if model.config._attn_implementation != "eager":
            raise ValueError("Adapter v0 yêu cầu attention eager")
        if self.config["activation_policy"] not in ("static_per_tensor", "static_per_input_channel", "dynamic_per_token"):
            raise ValueError("A policy không được hỗ trợ")
        if model.model.embed_tokens.weight is not model.lm_head.weight:
            raise ValueError("Embedding và LM head phải dùng cùng Parameter")
        self.config.setdefault("point_enabled", {})
        self.config.setdefault("activation_observer", "minmax")
        self.smooth = self.config.get("smoothquant", {"enabled": False})
        self.smooth_scales, self.smooth_stats = {}, {}
        self._collect_smooth_stats = False
        if self.smooth.get("enabled"):
            if not (0.0 <= float(self.smooth.get("alpha", -1)) <= 1.0):
                raise ValueError("SmoothQuant alpha phải nằm trong [0,1]")
            if self.config["activation_policy"] != "static_per_tensor":
                raise ValueError("SmoothQuant chỉ kết hợp với A per-tensor tĩnh trong thí nghiệm này")
        if self.config["activation_policy"] == "dynamic_per_token":
            if self.config["activation_observer"] != "minmax" or self.config["activation_bits"] not in (4, 8):
                raise ValueError("A động hỗ trợ 4/8 bit, không dùng Histogram")
        self.mode = "disabled"
        self.points, self.weights, self.bindings = {}, {}, []
        self.materialized = {}
        self._add_weight("shared_embedding_lm_head.weight", model.lm_head.weight,
                         self.config["shared_weight_bits"])
        for name, module in list(model.named_modules()):
            if isinstance(module, torch.nn.Linear):
                if name == "lm_head":
                    weight_name = "shared_embedding_lm_head.weight"
                else:
                    if name.rsplit(".", 1)[-1] not in {"q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"}:
                        raise ValueError(f"Linear ngoài phạm vi v0: {name}")
                    weight_name = name + ".weight"
                    self._add_weight(weight_name, module.weight, self.config["decoder_weight_bits"])
                if self.config["activation_policy"] == "static_per_input_channel":
                    activation = self._add_point(name + ".input", "A", self.config["activation_bits"], -1, module.in_features)
                else:
                    activation = self._add_point(name + ".input", "A", self.config["activation_bits"])
                original = module.forward
                def linear_forward(layer, x, *, _activation=activation, _weight=weight_name, _module_name=name):
                    if self._collect_smooth_stats and _module_name != "lm_head":
                        maximum = x.detach().abs().amax(dim=tuple(range(x.ndim - 1))).cpu()
                        if not torch.isfinite(maximum).all():
                            raise ValueError(f"SmoothQuant activation stats nonfinite: {_module_name}")
                        previous = self.smooth_stats.get(_module_name)
                        self.smooth_stats[_module_name] = maximum if previous is None else torch.maximum(previous, maximum)
                    smooth = self.smooth_scales.get(_module_name)
                    if smooth is not None:
                        x = x / smooth.to(device=x.device, dtype=x.dtype)
                    dynamic = (self.mode == "quantize" and self.config["activation_policy"] == "dynamic_per_token"
                               and bool(_activation.fq.fake_quant_enabled.item()))
                    return F.linear(_activation(x, dynamic=dynamic), self.quantized_weight(_weight), layer.bias)
                self._bind(module, original, linear_forward)
        embedding = model.model.embed_tokens
        def embedding_forward(layer, ids):
            return F.embedding(ids, self.quantized_weight("shared_embedding_lm_head.weight"),
                               layer.padding_idx, layer.max_norm, layer.norm_type,
                               layer.scale_grad_by_freq, layer.sparse)
        self._bind(embedding, embedding.forward, embedding_forward)
        for index, layer in enumerate(model.model.layers):
            attention = layer.self_attn
            kpoint = self._add_point(f"model.layers.{index}.self_attn.key_post_rope", "K",
                                     self.config["key_bits"], 1, model.config.num_key_value_heads)
            vpoint = self._add_point(f"model.layers.{index}.self_attn.value_post_projection", "V",
                                     self.config["value_bits"], 1, model.config.num_key_value_heads)
            def attention_forward(attn, hidden_states, position_embeddings, attention_mask,
                                  past_key_value=None, cache_position=None, *, _k=kpoint, _v=vpoint, **kwargs):
                input_shape = hidden_states.shape[:-1]
                hidden_shape = (*input_shape, -1, attn.head_dim)
                query = attn.q_proj(hidden_states).view(hidden_shape).transpose(1, 2)
                key = attn.k_proj(hidden_states).view(hidden_shape).transpose(1, 2)
                value = attn.v_proj(hidden_states).view(hidden_shape).transpose(1, 2)
                cos, sin = position_embeddings
                query, key = apply_rotary_pos_emb(query, key, cos, sin)
                key, value = _k(key), _v(value)
                if past_key_value is not None:
                    key, value = past_key_value.update(key, value, attn.layer_idx,
                                                       {"sin": sin, "cos": cos, "cache_position": cache_position})
                output, weights = eager_attention_forward(attn, query, key, value, attention_mask,
                                                           scaling=attn.scaling, dropout=0.0, **kwargs)
                return attn.o_proj(output.reshape(*input_shape, -1).contiguous()), weights
            self._bind(attention, attention.forward, attention_forward)
        if not set(self.config["point_enabled"]) <= set(self.points):
            raise ValueError("point_enabled có tên điểm không tồn tại")
        self.set_mode("disabled")

    def _add_point(self, name, kind, bits, axis=None, channels=1):
        point = QuantPoint(kind, bits, axis, channels,
                           self.config["activation_observer"] if kind == "A" else "minmax",
                           self.config.get("activation_histogram_bins", 2048), defer_qparams=True)
        self.points[name] = point
        return point

    def _add_weight(self, name, weight, bits):
        self.weights[name] = weight
        self._add_point(name, "W", bits, 0, weight.shape[0])

    def _bind(self, module, original, forward):
        patched = MethodType(forward, module)
        self.bindings.append((module, original, patched))
        module.forward = patched

    @contextmanager
    def native(self):
        """Oracle Transformers gốc trên cùng Parameter; luôn phục hồi adapter sau scope."""
        for module, original, _ in self.bindings:
            module.forward = original
        try:
            yield
        finally:
            for module, _, patched in self.bindings:
                module.forward = patched

    def restore(self):
        for module, original, _ in self.bindings:
            module.forward = original
        self.materialized.clear()

    def set_mode(self, mode):
        if mode not in ("disabled", "observe", "quantize"):
            raise ValueError(mode)
        if mode == "quantize" and not all(p.frozen for p in self.points.values()):
            raise ValueError("Cần freeze hoặc load qparams trước khi fake-quant")
        self.mode = mode
        self.materialized.clear()
        for name, point in self.points.items():
            point.fq.enable_observer(mode == "observe" and point.kind != "W")
            enabled = self.config["point_enabled"].get(name, self.config["enabled"][point.kind])
            point.fq.enable_fake_quant(mode == "quantize" and enabled)

    def set_enabled(self, groups):
        if not set(groups) <= {"W", "A", "K", "V"} or not all(isinstance(v, bool) for v in groups.values()):
            raise ValueError("Enabled groups phải là boolean W/A/K/V")
        self.config["enabled"].update(groups)
        self.set_mode(self.mode)  # Đổi config phải xóa W đã materialize và cập nhật tất cả flags.

    def set_point_enabled(self, name, enabled):
        if name not in self.points or not isinstance(enabled, bool):
            raise ValueError("Cần tên điểm hợp lệ và boolean")
        self.config["point_enabled"][name] = enabled
        self.set_mode(self.mode)

    @torch.inference_mode()
    def begin_calibration(self):
        if self.smooth.get("enabled") and not self.smooth_scales:
            raise ValueError("SmoothQuant stats must be collected/finalized before qparam calibration")
        for point in self.points.values():
            point.reset_observer()
            point.reset_counts()
        self.set_mode("observe")
        # W chỉ thu thống kê từ chính trọng số nguồn, không cập nhật theo batch.
        for name in self.weights:
            point = self.points[name]
            point.fq.enable_observer()
            point(self.effective_weight(name))
            point.fq.disable_observer()

    def begin_smooth_calibration(self):
        if not self.smooth.get("enabled"):
            raise ValueError("Config does not enable SmoothQuant")
        self.smooth_stats.clear()
        self.smooth_scales.clear()
        self._collect_smooth_stats = True
        self.set_mode("disabled")

    def finalize_smoothquant(self):
        if not self._collect_smooth_stats:
            raise ValueError("SmoothQuant stats were not collected")
        alpha = float(self.smooth["alpha"])
        expected = {name.removesuffix(".weight") for name in self.weights
                    if name != "shared_embedding_lm_head.weight"}
        if set(self.smooth_stats) != expected:
            raise ValueError("SmoothQuant statistics incomplete for decoder Linear points")
        for module_name in sorted(expected):
            weight = self.weights[module_name + ".weight"]
            activation_max = self.smooth_stats[module_name].to(weight.device)
            weight_max = weight.detach().abs().amax(dim=0)
            if not torch.isfinite(activation_max).all() or not torch.isfinite(weight_max).all():
                raise ValueError(f"SmoothQuant max nonfinite: {module_name}")
            # If either side has no signal, keep that channel unchanged (scale=1).
            valid = (activation_max > 0) & (weight_max > 0)
            scale = torch.ones_like(activation_max)
            scale[valid] = activation_max[valid].pow(alpha) / weight_max[valid].pow(1.0 - alpha)
            if not torch.isfinite(scale).all() or not torch.all(scale > 0):
                raise ValueError(f"SmoothQuant scale invalid: {module_name}")
            self.smooth_scales[module_name] = scale.detach().cpu().contiguous()
        self._collect_smooth_stats = False
        return {name: {"channels": len(scale), "unit_scale_channels": int((scale == 1).sum()),
                       "min": float(scale.min()), "max": float(scale.max())}
                for name, scale in self.smooth_scales.items()}

    def effective_weight(self, name):
        weight = self.weights[name]
        scale = self.smooth_scales.get(name.removesuffix(".weight"))
        return weight if scale is None else weight * scale.to(device=weight.device, dtype=weight.dtype).unsqueeze(0)

    def freeze(self):
        for name, point in self.points.items():
            observer = point.fq.activation_post_process
            if not torch.isfinite(observer.min_val).all() or observer.min_val.numel() == 0:
                raise ValueError(f"Điểm chưa calibration: {name}")
            if point.frozen:
                raise ValueError("Observer đã freeze; cần begin_calibration trước lần mới")
            point.finish_observation()
            point.validate()
            point.frozen = True
        self.set_mode("disabled")

    def quantized_weight(self, name):
        if self.mode != "quantize" or not self.points[name].fq.fake_quant_enabled.item():
            return self.effective_weight(name)
        if name not in self.materialized:
            self.materialized[name] = self.points[name](self.effective_weight(name)).detach()
        return self.materialized[name]

    def point_specs(self):
        return {name: {"kind": p.kind, "bits": p.bits, "quant_min": p.fq.quant_min,
                       "quant_max": p.fq.quant_max, "zero_point": 0, "axis": p.axis,
                       "scale_count": p.channels, "observer": p.observer,
                       "histogram_bins": p.bins if p.observer != "minmax" else None,
                       "freeze_calculations": p.freeze_calculations, "calls": p.calls, "tokens": p.tokens,
                       "last_shape": p.last_shape} for name, p in self.points.items()}

    def qparam_state(self):
        """Snapshot nhẹ cho phép kiểm evaluation không đổi scale/zp/observer."""
        return {name: {key: value.detach().clone() for key, value in point.fq.state_dict().items()}
                for name, point in self.points.items()}

    def save_qparams(self, path):
        if not all(p.frozen for p in self.points.values()):
            raise ValueError("Chỉ lưu tham số đã freeze")
        tensors = {}
        for name, point in self.points.items():
            point.validate()
            tensors[name + ".scale"] = point.fq.scale.clone().contiguous()
            tensors[name + ".zero_point"] = point.fq.zero_point.clone().contiguous()
        for name, scale in self.smooth_scales.items():
            tensors["smoothquant." + name] = scale.clone().contiguous()
        save_file(tensors, str(path), metadata={"ptq_contract": json.dumps(self.calibration_contract())})

    def calibration_contract(self):
        return {"activation_policy": self.config["activation_policy"],
                "weight_policy": self.config["weight_policy"], "kv_policy": self.config["kv_policy"],
                "smoothquant": ({"enabled": True, "alpha": float(self.smooth["alpha"]),
                    "statistics": self.smooth["statistics"], "fold": self.smooth["fold"],
                    "excluded": self.smooth["exclude"], "points": sorted(
                        name.removesuffix(".weight") for name in self.weights
                        if name != "shared_embedding_lm_head.weight")}
                    if self.smooth.get("enabled") else {"enabled": False}),
                "points": {name: {"kind": p.kind, "bits": p.bits, "axis": p.axis,
                                    "channels": p.channels, "observer": p.observer,
                                    "bins": p.bins if p.observer != "minmax" else None}
                           for name, p in self.points.items()}}

    def load_qparams(self, path, *, recompute_weights=False, load_static_for_dynamic=False):
        path = Path(path)
        with safe_open(str(path), framework="pt") as archive:
            header = archive.metadata() or {}
        if "ptq_contract" in header:
            source_contract = json.loads(header["ptq_contract"])
        else:
            # Original stage2 bundle: accept only its exact documented legacy MinMax semantics.
            config_path, metadata_path = path.parent / "config.json", path.parent / "metadata.json"
            if not config_path.exists() or not metadata_path.exists():
                raise ValueError("Legacy qparams thiếu provenance config/metadata")
            config = json.loads(config_path.read_text())
            metadata = json.loads(metadata_path.read_text())
            if config.get("activation_observer", "minmax") != "minmax":
                raise ValueError("Legacy bundle chỉ hỗ trợ MinMax")
            source_contract = {key: config[key] for key in ("activation_policy", "weight_policy", "kv_policy")}
            source_contract["points"] = {name: {"kind": spec["kind"], "bits": spec["bits"],
                "axis": spec["axis"], "channels": spec["scale_count"], "observer": "minmax", "bins": None}
                for name, spec in metadata["points"].items()}
        expected_contract = self.calibration_contract()
        ignore_static_a = load_static_for_dynamic and self.config["activation_policy"] == "dynamic_per_token"
        if load_static_for_dynamic and not ignore_static_a:
            raise ValueError("Explicit static-for-dynamic load requires dynamic A policy")
        if ignore_static_a and source_contract.get("activation_policy") not in ("static_per_tensor", "dynamic_per_token"):
            raise ValueError("Unsupported source A policy")
        for policy in ("activation_policy", "weight_policy", "kv_policy"):
            if policy == "activation_policy" and ignore_static_a:
                continue
            if source_contract.get(policy) != expected_contract[policy]:
                raise ValueError(f"Calibration policy mismatch: {policy}")
        if source_contract.get("smoothquant", {"enabled": False}) != expected_contract["smoothquant"]:
            raise ValueError("Calibration SmoothQuant contract mismatch")
        if source_contract.get("points", {}).keys() != expected_contract["points"].keys():
            raise ValueError("Calibration point mismatch")
        for name, expected_spec in expected_contract["points"].items():
            source_spec = source_contract["points"][name].copy()
            if ignore_static_a and expected_spec["kind"] == "A":
                if source_spec.get("kind") != "A":
                    raise ValueError(f"Calibration kind mismatch: {name}")
                continue  # No A scale/zero-point/observer is loaded or used by current-token quantization.
            if recompute_weights and expected_spec["kind"] == "W":
                source_spec["bits"] = expected_spec["bits"]
            if source_spec != expected_spec:
                raise ValueError(f"Calibration bits/observer/axis mismatch: {name}")
        tensors = load_file(str(path))
        expected = {name + suffix for name in self.points for suffix in (".scale", ".zero_point")}
        if self.smooth.get("enabled"):
            expected |= {"smoothquant." + name for name in expected_contract["smoothquant"]["points"]}
        if set(tensors) != expected:
            raise ValueError("Qparams không đủ hoặc khác cấu hình")
        if self.smooth.get("enabled"):
            smooth_scales = {}
            for module_name in expected_contract["smoothquant"]["points"]:
                value = tensors["smoothquant." + module_name]
                input_width = self.weights[module_name + ".weight"].shape[1]
                if value.ndim != 1 or value.numel() != input_width:
                    raise ValueError(f"SmoothQuant scale shape mismatch: {module_name}")
                if value.dtype != torch.float32 or not torch.isfinite(value).all() or not torch.all(value > 0):
                    raise ValueError(f"SmoothQuant scale values must be finite positive FP32: {module_name}")
                smooth_scales[module_name] = value.clone().contiguous()
            self.smooth_scales = smooth_scales
        for name, point in self.points.items():
            if ignore_static_a and point.kind == "A":
                point.fq.scale.fill_(1.0)
                point.fq.zero_point.zero_()
                point.frozen = True
                continue
            for key in ("scale", "zero_point"):
                target = getattr(point.fq, key)
                value = tensors[name + "." + key]
                target.resize_(value.shape).copy_(value)
            point.validate()
            point.frozen = True
        if recompute_weights:
            with torch.inference_mode():
                for name, weight in self.weights.items():
                    point = self.points[name]
                    point.reset_observer()
                    point.fq.enable_observer()
                    point(self.effective_weight(name))
                    point.fq.disable_observer()
                    point.finish_observation()
                    point.validate()
                    point.frozen = True
        self.set_mode("disabled")
