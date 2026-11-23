/*-----------------------------------------------------------------------------
 * File        : p1_basic.c
 * Description : SW test 1, flow and memory layout, straight line (no loop):
 *               a code constant, an initialized .data word, a .rodata word
 *               and a .bss word (must read 0, not the data fill pattern).
 * Author      : Claude Code (Anthropic)
 * Date        : 2026-11-20
 *---------------------------------------------------------------------------*/

#include "common.h"

uint32_t g_data = 0xCAFE0001u;                       /* .data */
static const volatile uint32_t k_rodata[2] = {0x11111111u, 0xDEADBEEFu};  /* .rodata */
uint32_t g_bss;                                      /* .bss, cleared by start.S */

int main(void)
{
    SIG[0] = 0x12345678u;
    SIG[1] = g_data;
    SIG[2] = k_rodata[1];
    SIG[3] = g_bss;
#ifdef FORCE_FAIL
    return FAIL;
#else
    return PASS;
#endif
}
