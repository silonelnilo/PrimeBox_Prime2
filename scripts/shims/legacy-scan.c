/* Modern glibc headers redirect legacy parsing to C23 entry points even when
 * linking to RX3 glibc 2.13. These call sites use decimal/hex numbers and the
 * pre-C23 scanf formats; preserve the original libc parsing semantics.
 * Deliberately avoid stdlib/stdio headers that perform that redirection.
 */
#include <stdarg.h>
extern long legacy_strtol(const char *, char **, int) __asm__("strtol");
extern int legacy_vsscanf(const char *, const char *, va_list) __asm__("vsscanf");
long __isoc23_strtol(const char *s, char **end, int base)
{
    return legacy_strtol(s, end, base);
}
int __isoc23_sscanf(const char *s, const char *format, ...)
{
    va_list args;
    va_start(args, format);
    int result = legacy_vsscanf(s, format, args);
    va_end(args);
    return result;
}
