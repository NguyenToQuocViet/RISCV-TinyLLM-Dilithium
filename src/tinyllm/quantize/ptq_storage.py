"""Payload lý thuyết từ tensor thực; không phải packing/buffer hoặc tài nguyên FPGA."""
import math


def enabled(adapter, name):
    point = adapter.points[name]
    return adapter.config.get('point_enabled', {}).get(name, adapter.config['enabled'][point.kind])


def storage_inventory(model, adapter, length=512):
    by_id = {id(weight): name for name, weight in adapter.weights.items()}
    weights, cache, metadata = [], [], []
    for name, parameter in model.named_parameters():
        point_name = by_id.get(id(parameter))
        quantized = point_name is not None and enabled(adapter, point_name)
        bits = adapter.points[point_name].bits if quantized else 32
        row = {'name': name, 'shape': list(parameter.shape), 'elements': parameter.numel(),
               'bits': bits, 'payload_bytes': math.ceil(parameter.numel() * bits / 8),
               'quant_point': point_name if quantized else None}
        if point_name == 'shared_embedding_lm_head.weight':
            row['aliases'] = ['model.embed_tokens.weight', 'lm_head.weight']
        weights.append(row)
    active_dynamic_a = []
    for name, point in adapter.points.items():
        if not enabled(adapter, name):
            continue
        if point.kind == 'A' and adapter.config['activation_policy'] == 'dynamic_per_token':
            active_dynamic_a.append(name)
            continue
        metadata.append({'point': name, 'kind': point.kind, 'scales': point.channels,
                         'scale_bits': 32, 'zero_points': point.channels, 'zero_point_bits': 32,
                         'bytes': point.channels * 8})
    for index in range(model.config.num_hidden_layers):
        for kind, suffix in (('K', 'key_post_rope'), ('V', 'value_post_projection')):
            name = f'model.layers.{index}.self_attn.{suffix}'
            point = adapter.points[name]
            bits = point.bits if enabled(adapter, name) else 32
            shape = [1, model.config.num_key_value_heads, length,
                     model.config.hidden_size // model.config.num_attention_heads]
            elements = math.prod(shape)
            cache.append({'point': name, 'kind': kind, 'shape_BHTD': shape, 'elements': elements,
                          'bits': bits, 'payload_bytes': math.ceil(elements * bits / 8)})
    activations = []
    for name, point in adapter.points.items():
        if point.kind != 'A':
            continue
        width = model.get_submodule(name.removesuffix('.input')).in_features
        bits = point.bits if enabled(adapter, name) else 32
        shapes = {'prefill': [1, length, width], 'decode': [1, 1, width]}
        activations.append({'point': name, 'bits': bits, 'shapes': shapes,
            'scale_axis': point.axis,
            'scale_count': point.channels,
            'payload_bytes': {mode: math.ceil(math.prod(shape)*bits/8) for mode,shape in shapes.items()},
            'static_width_comparison_bytes': {str(b): {mode: math.ceil(math.prod(shape)*b/8)
                for mode,shape in shapes.items()} for b in (8,12,16)}})
    summary = {'model_parameters': sum(p.numel() for p in model.parameters()),
               'weight_payload_bytes': sum(r['payload_bytes'] for r in weights),
               'weight_metadata_bytes': sum(r['bytes'] for r in metadata if r['kind']=='W'),
               'static_a_metadata_bytes': sum(r['bytes'] for r in metadata if r['kind']=='A'),
               'smoothquant_runtime_metadata_bytes': sum(scale.numel() for scale in adapter.smooth_scales.values()) * 4,
               'kv_payload_bytes': sum(r['payload_bytes'] for r in cache),
               'kv_metadata_bytes': sum(r['bytes'] for r in metadata if r['kind'] in ('K','V')),
               'fp32_weight_elements': sum(r['elements'] for r in weights if r['bits']==32)}
    summary['total_persistent_bytes'] = sum(summary[k] for k in ('weight_payload_bytes','weight_metadata_bytes',
        'static_a_metadata_bytes','smoothquant_runtime_metadata_bytes','kv_payload_bytes','kv_metadata_bytes'))
    summary['fp32_weight_payload_bytes'] = summary['model_parameters']*4
    summary['fp32_kv_payload_bytes'] = sum(r['elements']*4 for r in cache)
    smooth_count = sum(scale.numel() for scale in adapter.smooth_scales.values())
    return {'length': length, 'summary': summary, 'weights': weights, 'cache': cache,
            'static_metadata': metadata, 'activations': activations,
            'smoothquant_metadata': {'enabled': bool(adapter.smooth_scales), 'input_feature_scales': smooth_count,
                'runtime_scale_bytes_if_not_fused': smooth_count * 4,
                'excluded_shared_embedding_lm_head': True,
                'scope': 'Per-input-feature scale consumed by runtime activation x/s; required unless equivalent scaling is fused into the datapath. Not an A activation payload.'},
            'activation_payload_scope': 'Individual tensor payload / summed traffic; not peak resident buffer. Shapes from actual Linear in_features; prefill L and one-token decode.',
            'dynamic_a': {'active_points': active_dynamic_a, 'persistent_scale_bytes': 0,
                'rule': 'per current token/point, reduce only hidden components; FP32 scale, constant zero_point=0',
                'simulation_generated_scale_bytes_per_prefill': len(active_dynamic_a)*length*4,
                'simulation_generated_zero_bytes_per_prefill': len(active_dynamic_a)*length*4,
                'max_one_point_scale_workspace_bytes': length*4 if active_dynamic_a else 0,
                'max_one_point_zero_workspace_bytes': length*4 if active_dynamic_a else 0,
                'hardware_work': 'max reduction, scale/reciprocal, quantize; buffer/latency/scale representation require later integer/RTL contract'},
            'scope': 'logical packed payload plus FP32 scales/int32 explicit static zero-points; shared weight once; no alignment, buffers, packing implementation or FPGA costs',
            'fp32_remainder': adapter.config['fp32_remainder'],
            'fp32_point_exceptions': [n for n in adapter.points if not enabled(adapter,n)]}
