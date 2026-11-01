#include "ntt_model.hpp"

#include <cstdio>
#include <cstdlib>
#include <cstring>

#define TESTS 10000

static int compare_poly(const coeff_t expected[N],
                        const coeff_t actual[N])
{
    for (int i = 0; i < N; i++)
    {
        if (expected[i] != actual[i])
        {
            std::printf("Sai tai he so %d: %d != %d\n",
                        i, expected[i], actual[i]);
            return 1;
        }
    }

    return 0;
}

static void random_poly(coeff_t a[N])
{
    for (int i = 0; i < N; i++)
        a[i] = std::rand() % Q;
}

int main()
{
    coeff_t input[N];
    coeff_t radix2[N];
    coeff_t ntt2x2[N];

    std::srand(1);

    for (int test = 0; test < TESTS; test++)
    {
        random_poly(input);
        std::memcpy(radix2, input, sizeof(input));
        std::memcpy(ntt2x2, input, sizeof(input));

        golden_ntt(radix2);
        golden_ntt2x2(ntt2x2);

        if (compare_poly(radix2, ntt2x2))
        {
            std::printf("Forward NTT test %d: FAILED\n", test);
            return 1;
        }

        golden_invntt(radix2);
        golden_invntt2x2(ntt2x2);

        if (compare_poly(input, radix2) ||
            compare_poly(input, ntt2x2))
        {
            std::printf("Inverse NTT test %d: FAILED\n", test);
            return 1;
        }
    }

    std::printf("Golden model: PASS (%d tests)\n", TESTS);
    return 0;
}
