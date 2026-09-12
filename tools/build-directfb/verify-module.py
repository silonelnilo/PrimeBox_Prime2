#!/usr/bin/env python3
"""Validate the fbdev plugin against the RX3 runtime, with actionable errors."""
import os
import re
import subprocess
import sys


def validate(header, attributes, symbols, dynamic):
    errors = []
    for value in ('ELF32', 'ARM', 'Version5 EABI'):
        if value not in header:
            errors.append(f'missing ELF target marker: {value}')
    if 'Tag_ABI_VFP_args' in attributes or 'hard-float ABI' in header:
        errors.append('hard-float ABI is incompatible with RX3')
    versions = set(re.findall(r'GLIBC_(\d+(?:\.\d+)+)', symbols))
    if not versions:
        errors.append('no GLIBC version information found')
    for version in versions:
        if tuple(map(int, version.split('.'))) > (2, 7):
            errors.append(f'GLIBC_{version} exceeds target GLIBC_2.7 symbol ceiling')
    rows = [line.split() for line in symbols.splitlines() if line.split()]
    for symbol in ('fstat', '__fdelt_chk'):
        if not any(row[-1] == symbol and '.text' in row and 'g' in row for row in rows):
            errors.append(f'missing exported definition: {symbol}')
    # objdump -T prints the version BEFORE the symbol name.
    if not any(row[-1] == '__fxstat' and '*UND*' in row and '(GLIBC_2.4)' in row for row in rows):
        errors.append('missing __fxstat import at GLIBC_2.4')
    needed = re.findall(r'\(NEEDED\).*\[(.*?)\]', dynamic)
    for library in ('libdirect', 'libfusion', 'libdirectfb'):
        if f'{library}-1.4.so.0' not in needed:
            errors.append(f'missing RX3 dependency: {library}-1.4.so.0')
    if any(name.endswith('.so.6') and name.startswith(('libdirect', 'libfusion')) for name in needed):
        errors.append('unpatched DirectFB .so.6 dependency')
    if '(RPATH)' in dynamic or '(RUNPATH)' in dynamic:
        errors.append('build-time RPATH/RUNPATH must be removed')
    return errors


def main():
    module = sys.argv[1]
    cross = os.environ.get('CROSS', 'arm-linux-gnueabi-')
    def run(tool, *args):
        return subprocess.check_output([cross + tool, *args, module], text=True)
    header, attributes = run('readelf', '-h'), run('readelf', '-A')
    symbols, dynamic = run('objdump', '-T'), run('readelf', '-d')
    errors = validate(header, attributes, symbols, dynamic)
    if errors:
        print(symbols)
        print(dynamic)
        for error in errors:
            print('ERROR:', error, file=sys.stderr)
        return 1
    print('PASS: ARM EABI5 soft-float; GLIBC <= 2.7; fstat/__fdelt_chk exports; __fxstat@GLIBC_2.4; RX3 dependencies; no build RPATH')
    return 0


if __name__ == '__main__':
    sys.exit(main())
