/*-----------------------------------------------------------------------------
 * File        : util.h
 * Description : Replaces riscv-tests benchmarks/common/util.h for the perf
 *               bench: mcycle reads the bench cycle counter MMIO, setStats is
 *               a no-op (BASE has no CSR).
 * Author      : Claude Code (Anthropic)
 * Date        : 2026-11-20
 *---------------------------------------------------------------------------*/

#ifndef PERF_UTIL_H
#define PERF_UTIL_H

#define read_csr(reg) (*(volatile unsigned long *)0x0001FFF4u)

static inline void setStats(int enable) { (void)enable; }

#endif
