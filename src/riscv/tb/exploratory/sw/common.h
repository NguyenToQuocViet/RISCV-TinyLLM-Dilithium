/*-----------------------------------------------------------------------------
 * File        : common.h
 * Description : SW test helpers: signature words at 0x1_FF00 (62 words).
 * Author      : Claude Code (Anthropic)
 * Date        : 2026-11-20
 *---------------------------------------------------------------------------*/

#ifndef COMMON_H
#define COMMON_H

#include <stdint.h>
#include <stddef.h>

#ifndef SIG
#define SIG ((volatile uint32_t *)0x0001FF00u)
#endif
#define PASS 1
#define FAIL 2

void *memset(void *dst, int c, size_t n);
void *memcpy(void *dst, const void *src, size_t n);

#endif
