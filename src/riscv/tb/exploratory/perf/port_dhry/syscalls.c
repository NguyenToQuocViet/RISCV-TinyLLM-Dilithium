/*-----------------------------------------------------------------------------
 * File        : syscalls.c
 * Description : Minimal printf (%d %ld %u %x %s %c), strcpy and strcmp for Dhrystone on the perf bench (putchar MMIO).
 * Author      : Claude Code (Anthropic)
 * Date        : 2026-11-20
 *---------------------------------------------------------------------------*/

#include <stdarg.h>

#define PUTC_ADDR ((volatile unsigned int *)0x0001FFF8u)

static void put(char c) { *PUTC_ADDR = (unsigned char)c; }

static void put_uint(unsigned long v, unsigned base)
{
    char buf[12];
    int n = 0;
    do {
        unsigned d = v % base;
        buf[n++] = (char)(d < 10 ? '0' + d : 'a' + d - 10);
        v /= base;
    } while (v);
    while (n)
        put(buf[--n]);
}

static void vout(const char *f, va_list ap)
{
    for (; *f; ++f) {
        if (*f != '%') { put(*f); continue; }
        ++f;
        if (*f == 'l') ++f;
        switch (*f) {
        case 'd': { long v = va_arg(ap, long); if (v < 0) { put('-'); v = -v; } put_uint((unsigned long)v, 10); break; }
        case 'u': put_uint(va_arg(ap, unsigned long), 10); break;
        case 'x': put_uint(va_arg(ap, unsigned long), 16); break;
        case 'c': put((char)va_arg(ap, int)); break;
        case 's': { const char *s = va_arg(ap, const char *); while (*s) put(*s++); break; }
        case '%': put('%'); break;
        default: put('?'); break;
        }
    }
}

int printf(const char *f, ...)
{
    va_list ap;
    va_start(ap, f);
    vout(f, ap);
    va_end(ap);
    return 0;
}

char *strcpy(char *d, const char *s)
{
    char *r = d;
    while ((*d++ = *s++))
        ;
    return r;
}

int strcmp(const char *a, const char *b)
{
    while (*a && *a == *b) { ++a; ++b; }
    return (unsigned char)*a - (unsigned char)*b;
}

/* dhrystone.c defines an empty debug_printf; the link wraps the calls from
   dhrystone_main.c to this one so the final-value check is printed */
void __wrap_debug_printf(const char *f, ...)
{
    va_list ap;
    va_start(ap, f);
    vout(f, ap);
    va_end(ap);
}
