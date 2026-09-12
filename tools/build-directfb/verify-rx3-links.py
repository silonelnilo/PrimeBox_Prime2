#!/usr/bin/env python3
"""Reject undefined strong ELF imports absent from the actual RX3 dependency tree."""
import os
from pathlib import Path
import re
import subprocess
import sys


def inspect(path):
    readelf = os.environ.get('CROSS', 'arm-linux-gnueabi-') + 'readelf'
    dynamic = subprocess.check_output([readelf, '-d', str(path)], text=True)
    symbols = subprocess.check_output([readelf, '--dyn-syms', '--wide', str(path)], text=True)
    exports, imports = set(), set()
    for line in symbols.splitlines():
        row = line.split()
        if len(row) < 8 or not row[0].endswith(':') or row[4] not in ('GLOBAL', 'WEAK'):
            continue
        name = row[7].split('@')[0]
        if row[6] != 'UND':
            exports.add(name)
        elif row[4] == 'GLOBAL':
            imports.add(name)
    return re.findall(r'\(NEEDED\).*\[(.*?)\]', dynamic), exports, imports


def main():
    root = Path(sys.argv[1]).resolve()
    pending = [Path(p).resolve() for p in sys.argv[2:]]
    checked, exports = {}, set()
    while pending:
        path = pending.pop()
        if path in checked:
            continue
        needed, definitions, imports = inspect(path)
        checked[path] = imports
        exports.update(definitions)
        for name in needed:
            for folder in ('lib', 'usr/lib'):
                candidate = root / folder / name
                if candidate.is_file():
                    pending.append(candidate.resolve())
                    break
            else:
                raise SystemExit(f'ERROR: {path.name} requires missing RX3 library {name}')
    errors = []
    for path, imports in checked.items():
        missing = imports - exports
        if missing:
            errors.append(f'{path.name}: {", ".join(sorted(missing))}')
    if errors:
        raise SystemExit('ERROR: unresolved RX3 imports\n' + '\n'.join(errors))
    print(f'PASS: all strong imports resolve in {len(checked)} RX3 ELF objects')


if __name__ == '__main__':
    main()
