#include "ntt_model.hpp"

// Reduce to the range 0..Q-1.
static coeff_t mod_q(wide_t value)
{
    value %= Q;
    if (value < 0)
        value += Q;
    return (coeff_t)value;
}

static coeff_t power_mod(coeff_t base, int exponent)
{
    coeff_t result = 1;

    while (exponent > 0)
    {
        if (exponent & 1)
            result = mod_q((wide_t)result * base);

        base = mod_q((wide_t)base * base);
        exponent >>= 1;
    }

    return result;
}

static int reverse_8_bits(int value)
{
    int result = 0;

    for (int i = 0; i < 8; i++)
    {
        result = (result << 1) | (value & 1);
        value >>= 1;
    }

    return result;
}

// Generate twiddle factors from ROOT.
static void make_zetas(coeff_t zetas[N])
{
    zetas[0] = 0;

    for (int i = 1; i < N; i++)
        zetas[i] = power_mod(ROOT, reverse_8_bits(i));
}

static void forward_stage(coeff_t a[N], int len,
                          int &k, const coeff_t zetas[N])
{
    int start;
    int j = 0;

    for (start = 0; start < N; start = j + len)
    {
        coeff_t zeta = zetas[++k];

        for (j = start; j < start + len; j++)
        {
            coeff_t t = mod_q((wide_t)zeta * a[j + len]);
            coeff_t old_a = a[j];

            a[j]       = mod_q((wide_t)old_a + t);
            a[j + len] = mod_q((wide_t)old_a - t);
        }
    }
}

static void inverse_stage(coeff_t a[N], int len,
                          int &k, const coeff_t zetas[N])
{
    int start;
    int j = 0;

    for (start = 0; start < N; start = j + len)
    {
        coeff_t zeta = mod_q(-zetas[--k]);

        for (j = start; j < start + len; j++)
        {
            coeff_t first  = a[j];
            coeff_t second = a[j + len];

            a[j]       = mod_q((wide_t)first + second);
            a[j + len] = mod_q((wide_t)zeta * (first - second));
        }
    }
}

static void divide_by_n(coeff_t a[N])
{
    // Compute the modular inverse of N.
    coeff_t inverse_n = power_mod(N, Q - 2);

    for (int i = 0; i < N; i++)
        a[i] = mod_q((wide_t)a[i] * inverse_n);
}

void golden_ntt(coeff_t a[N])
{
    coeff_t zetas[N];
    int k = 0;

    make_zetas(zetas);

    for (int len = N / 2; len >= 1; len /= 2)
        forward_stage(a, len, k, zetas);
}

void golden_invntt(coeff_t a[N])
{
    coeff_t zetas[N];
    int k = N;

    make_zetas(zetas);

    for (int len = 1; len < N; len *= 2)
        inverse_stage(a, len, k, zetas);

    divide_by_n(a);
}

void golden_ntt2x2(coeff_t a[N])
{
    coeff_t zetas[N];
    int k = 0;

    make_zetas(zetas);

    // Process two NTT stages per loop.
    for (int len = N / 2; len >= 1; len /= 4)
    {
        forward_stage(a, len, k, zetas);

        if (len > 1)
            forward_stage(a, len / 2, k, zetas);
    }
}

void golden_invntt2x2(coeff_t a[N])
{
    coeff_t zetas[N];
    int k = N;

    make_zetas(zetas);

    // Process two inverse NTT stages per loop.
    for (int len = 1; len < N; len *= 4)
    {
        inverse_stage(a, len, k, zetas);

        if (len * 2 < N)
            inverse_stage(a, len * 2, k, zetas);
    }

    divide_by_n(a);
}

void golden_pointwise(coeff_t result[N],
                      const coeff_t a[N],
                      const coeff_t b[N])
{
    for (int i = 0; i < N; i++)
        result[i] = mod_q((wide_t)a[i] * b[i]);
}
