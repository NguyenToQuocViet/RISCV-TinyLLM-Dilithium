"""Exact integer primitives shared by preparation, simulation, and runtime."""
import numpy as np
import torch


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
