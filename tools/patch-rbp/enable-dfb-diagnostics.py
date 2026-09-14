#!/usr/bin/env python3
"""Enable DirectFB diagnostics in the verified RX3 1.20 PrimeBox player.
Only changes the five-byte quiet option string to debug; does not alter code.
Usage: python3 enable-dfb-diagnostics.py INPUT OUTPUT
"""
import hashlib
from pathlib import Path
import sys

CANONICAL_MD5 = '3706c68f7242779d46afa09f35a39acf'
OPTION_OFFSET = 0x443454 - 0x8000


def enable(data):
    if hashlib.md5(data).hexdigest() != CANONICAL_MD5:
        raise ValueError('expected the canonical patched RX3 1.20 player')
    if data[OPTION_OFFSET:OPTION_OFFSET + 6] != b'quiet\0':
        raise ValueError('DirectFB quiet option not found at the verified address')
    result = bytearray(data)
    result[OPTION_OFFSET:OPTION_OFFSET + 5] = b'debug'
    return bytes(result)


if __name__ == '__main__':
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    source, output = map(Path, sys.argv[1:])
    result = enable(source.read_bytes())
    with output.open('xb') as stream:
        stream.write(result)
    output.chmod(0o755)
    print('Diagnostic player SHA256:', hashlib.sha256(result).hexdigest())
