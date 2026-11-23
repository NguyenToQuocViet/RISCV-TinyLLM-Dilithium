/*-----------------------------------------------------------------------------
 * File        : p3_sha3.c
 * Description : SW test 3, SHA3-256 (FIPS 202) of three messages: "", "abc"
 *               and 200 bytes of 0xA3 (two blocks at rate 136). Digests go to
 *               SIG[0..23]; the program also compares them with the FIPS 202
 *               known answers and returns PASS or FAIL.
 *               -DBREAK_RC flips one bit of RC[0]; -DNO_SELFCHECK always
 *               returns PASS (negative control for the harness check).
 *               -DSKIP_EMPTY drops the "" message (shorter -O0 runs).
 * Author      : Claude Code (Anthropic)
 * Date        : 2026-11-20
 *---------------------------------------------------------------------------*/

#include "common.h"

#define RATE 136  /* SHA3-256: 1600 - 2*256 bits */

#ifdef BREAK_RC
#define RC0 0x0000000000000003ull
#else
#define RC0 0x0000000000000001ull
#endif

static const uint64_t RC[24] = {
    RC0,                   0x0000000000008082ull, 0x800000000000808Aull, 0x8000000080008000ull,
    0x000000000000808Bull, 0x0000000080000001ull, 0x8000000080008081ull, 0x8000000000008009ull,
    0x000000000000008Aull, 0x0000000000000088ull, 0x0000000080008009ull, 0x000000008000000Aull,
    0x000000008000808Bull, 0x800000000000008Bull, 0x8000000000008089ull, 0x8000000000008003ull,
    0x8000000000008002ull, 0x8000000000000080ull, 0x000000000000800Aull, 0x800000008000000Aull,
    0x8000000080008081ull, 0x8000000000008080ull, 0x0000000080000001ull, 0x8000000080008008ull,
};

/* rho offsets and pi lane order along the (1,0) lane cycle */
static const uint8_t ROTC[24] = {1, 3, 6, 10, 15, 21, 28, 36, 45, 55, 2, 14,
                                 27, 41, 56, 8, 25, 43, 62, 18, 39, 61, 20, 44};
static const uint8_t PILN[24] = {10, 7, 11, 17, 18, 3, 5, 16, 8, 21, 24, 4,
                                 15, 23, 19, 13, 12, 2, 20, 14, 22, 9, 6, 1};

static const uint8_t KAT[3][32] = {
    {0xa7, 0xff, 0xc6, 0xf8, 0xbf, 0x1e, 0xd7, 0x66, 0x51, 0xc1, 0x47, 0x56, 0xa0, 0x61, 0xd6, 0x62,
     0xf5, 0x80, 0xff, 0x4d, 0xe4, 0x3b, 0x49, 0xfa, 0x82, 0xd8, 0x0a, 0x4b, 0x80, 0xf8, 0x43, 0x4a},
    {0x3a, 0x98, 0x5d, 0xa7, 0x4f, 0xe2, 0x25, 0xb2, 0x04, 0x5c, 0x17, 0x2d, 0x6b, 0xd3, 0x90, 0xbd,
     0x85, 0x5f, 0x08, 0x6e, 0x3e, 0x9d, 0x52, 0x5b, 0x46, 0xbf, 0xe2, 0x45, 0x11, 0x43, 0x15, 0x32},
    {0x79, 0xf3, 0x8a, 0xde, 0xc5, 0xc2, 0x03, 0x07, 0xa9, 0x8e, 0xf7, 0x6e, 0x83, 0x24, 0xaf, 0xbf,
     0xd4, 0x6c, 0xfd, 0x81, 0xb2, 0x2e, 0x39, 0x73, 0xc6, 0x5f, 0xa1, 0xbd, 0x9d, 0xe3, 0x17, 0x87},
};

static uint64_t st[25];
static uint8_t msg[200];
static uint32_t digest[8];

/* 64-bit rotate written with 32-bit halves (no libgcc shift helper) */
static uint64_t rotl64(uint64_t v, unsigned n)
{
    uint32_t lo = (uint32_t)v, hi = (uint32_t)(v >> 32);
    if (n >= 32) {
        uint32_t t = lo;
        lo = hi;
        hi = t;
        n -= 32;
    }
    if (n) {
        uint32_t nlo = (lo << n) | (hi >> (32 - n));
        uint32_t nhi = (hi << n) | (lo >> (32 - n));
        lo = nlo;
        hi = nhi;
    }
    return ((uint64_t)hi << 32) | lo;
}

static void keccak_f(void)
{
    uint64_t bc[5], t;
    for (int r = 0; r < 24; r++) {
        /* theta */
        for (int x = 0; x < 5; x++)
            bc[x] = st[x] ^ st[x + 5] ^ st[x + 10] ^ st[x + 15] ^ st[x + 20];
        for (int x = 0; x < 5; x++) {
            t = bc[(x + 4) % 5] ^ rotl64(bc[(x + 1) % 5], 1);
            for (int y = 0; y < 25; y += 5)
                st[y + x] ^= t;
        }
        /* rho and pi */
        t = st[1];
        for (int i = 0; i < 24; i++) {
            int j = PILN[i];
            bc[0] = st[j];
            st[j] = rotl64(t, ROTC[i]);
            t = bc[0];
        }
        /* chi */
        for (int y = 0; y < 25; y += 5) {
            for (int x = 0; x < 5; x++)
                bc[x] = st[y + x];
            for (int x = 0; x < 5; x++)
                st[y + x] ^= (~bc[(x + 1) % 5]) & bc[(x + 2) % 5];
        }
        /* iota */
        st[0] ^= RC[r];
    }
}

static void sha3_256(const uint8_t *m, uint32_t len)
{
    uint8_t *s8 = (uint8_t *)st;  /* little-endian lane bytes */
    memset(st, 0, sizeof st);
    while (len >= RATE) {
        for (int i = 0; i < RATE; i++)
            s8[i] ^= m[i];
        keccak_f();
        m += RATE;
        len -= RATE;
    }
    for (uint32_t i = 0; i < len; i++)
        s8[i] ^= m[i];
    s8[len] ^= 0x06;       /* SHA3 domain bits 01 plus first pad bit */
    s8[RATE - 1] ^= 0x80;  /* last pad bit */
    keccak_f();
    memcpy(digest, st, 32);
}

static int run(int k, const uint8_t *m, uint32_t len)
{
    int ok = 1;
    sha3_256(m, len);
    for (int i = 0; i < 8; i++)
        SIG[8 * k + i] = digest[i];
    for (int i = 0; i < 32; i++)
        ok &= ((const uint8_t *)digest)[i] == KAT[k][i];
    return ok;
}

int main(void)
{
    int ok = 1;
    msg[0] = 'a';
    msg[1] = 'b';
    msg[2] = 'c';
#ifndef SKIP_EMPTY
    ok &= run(0, msg, 0);
#endif
    ok &= run(1, msg, 3);
    memset(msg, 0xA3, sizeof msg);
    ok &= run(2, msg, 200);
#ifdef NO_SELFCHECK
    (void)ok;
    return PASS;
#else
    return ok ? PASS : FAIL;
#endif
}
