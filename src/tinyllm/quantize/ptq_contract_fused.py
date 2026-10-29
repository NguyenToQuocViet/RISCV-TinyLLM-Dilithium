"""IndexSoftmax numerators consumed directly by an integer PV reduction.

The interface carries E (UINT8) and the shared S (UINT17), rather than rounded
probability codes. The exponential LUT and index calculation are unchanged.
"""
import numpy as np
import torch

from ptq_contract import (encode_multiplier, rescale, round_divide,
                          round_divide_scalar, softmax_lut)


def index_softmax_components(score_codes, score_scale, allowed, *, c=8,
                             entries=32, coefficient_bits=24):
    """Return E[B,H,Q,K], S[B,H,Q,1]; each row must contain a valid key."""
    allowed = torch.broadcast_to(allowed.bool(), score_codes.shape)
    if not allowed.any(-1).all():
        raise ValueError('every attention row must have a valid key')
    maximum = score_codes.masked_fill(~allowed, torch.iinfo(torch.int64).min).amax(-1, keepdim=True)
    difference = torch.where(allowed, maximum-score_codes, 0)
    coefficient = torch.as_tensor(score_scale, dtype=torch.float64)*(entries-1)/c
    index = rescale(difference, coefficient, coefficient_bits).clamp(0, entries-1)
    exponential = softmax_lut(c, entries)[index].masked_fill(~allowed, 0)
    total = exponential.sum(-1, keepdim=True)
    if not torch.all((total >= 255) & (total <= 512*255)):
        raise ArithmeticError('IndexSoftmax denominator invariant')
    return exponential, total


def fused_pv(exponential, total, value_codes, coefficient, coefficient_bits=24):
    """RNE(sum(E*qV)*M/(S*2**shift)), before final context saturation.

    Preconditions: <=512 keys, E in [0,255], V in [-128,127], and S=sum(E)>0.
    FP32 code GEMM is exact here: even the sum of absolute products is at most
    512*255*128=16711680 < 2**24. All subsequent arithmetic is integer.
    Positive shift expands the denominator; negative shift expands the numerator.
    """
    accumulator = torch.matmul(exponential.float(), value_codes.float()).round().long()
    multiplier, shift = encode_multiplier(coefficient, coefficient_bits)
    accumulator, multiplier, shift, total = torch.broadcast_tensors(
        accumulator, multiplier, shift, torch.as_tensor(total, dtype=torch.int64))
    if torch.any(total <= 0):
        raise ValueError('positive denominator required')
    if not accumulator.numel():
        return accumulator
    maximum_product = int(accumulator.abs().max())*int(multiplier.abs().max())
    numerator_left = max(0, -int(shift.min()))
    denominator_left = max(0, int(shift.max()))
    if (maximum_product.bit_length()+numerator_left < 63 and
            int(total.max()).bit_length()+denominator_left < 63):
        numerator = torch.bitwise_left_shift(accumulator*multiplier, (-shift).clamp_min(0))
        denominator = torch.bitwise_left_shift(total, shift.clamp_min(0))
        return round_divide(numerator, denominator)
    # An unusually small scale ratio can make S*2**shift wider than INT64 even
    # though the quotient fits. Preserve exact rounding instead of overflowing.
    result = np.empty(tuple(accumulator.shape), dtype=np.int64)
    fields = [x.reshape(-1).tolist() for x in (accumulator, multiplier, shift, total)]
    for i, (a, m, s, denominator) in enumerate(zip(*fields)):
        numerator = a*m
        if s >= 0:
            denominator <<= s
        else:
            numerator <<= -s
        result.flat[i] = round_divide_scalar(numerator, denominator)
    return torch.from_numpy(result)
