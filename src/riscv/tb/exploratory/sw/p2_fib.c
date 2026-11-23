/*-----------------------------------------------------------------------------
 * File        : p2_fib.c
 * Description : SW test 2, Fibonacci: iterative table fib(0..47) in SIG[0..47]
 *               and recursive fib(15) in SIG[48].
 * Author      : Claude Code (Anthropic)
 * Date        : 2026-11-20
 *---------------------------------------------------------------------------*/

#include "common.h"

#define N 48

uint32_t fib_table[N];
static volatile uint32_t rec_n = 15;  /* volatile: no compile-time folding */
static volatile uint32_t seed_one = 1;

uint32_t fib_rec(uint32_t n)
{
    if (n < 2)
        return n;
    return fib_rec(n - 1) + fib_rec(n - 2);
}

int main(void)
{
    fib_table[0] = 0;
    fib_table[1] = seed_one;
    for (int i = 2; i < N; i++)
        fib_table[i] = fib_table[i - 1] + fib_table[i - 2];
    for (int i = 0; i < N; i++)
        SIG[i] = fib_table[i];
    SIG[48] = fib_rec(rec_n);
    return PASS;
}
