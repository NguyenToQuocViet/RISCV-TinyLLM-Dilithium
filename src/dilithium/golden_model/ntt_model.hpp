#ifndef GOLDEN_NTT_MODEL_HPP
#define GOLDEN_NTT_MODEL_HPP

#include <cstdint>

const int N = 256;
const int Q = 8380417;
const int ROOT = 1753;

typedef std::int32_t coeff_t;
typedef std::int64_t wide_t;

// Standard radix-2 NTT.
void golden_ntt(coeff_t a[N]);
void golden_invntt(coeff_t a[N]);

// NTT with two stages per loop.
void golden_ntt2x2(coeff_t a[N]);
void golden_invntt2x2(coeff_t a[N]);

// Pointwise multiplication in the NTT domain.
void golden_pointwise(coeff_t result[N],
                      const coeff_t a[N],
                      const coeff_t b[N]);

#endif
