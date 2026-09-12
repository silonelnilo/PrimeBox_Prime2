#!/usr/bin/env python3
"""Prepare a LOCAL RX3 userspace staging tree; never connects to the device.
Dependencies: pycryptodome, pycdlib. Inputs: official RX3 v1.20 + both GPL ZIPs.
Cramfs inode layout: Linux include/uapi/linux/cramfs_fs.h (little endian).
"""
import argparse
import io
import os
from pathlib import Path, PurePosixPath
import stat
import struct
import subprocess
import tarfile
import zipfile
import zlib
from Crypto.Cipher import AES
import pycdlib


def confined_name(name):
    path = PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts:
        raise ValueError(f'unsafe archive path: {name}')
    return path


def unpack_cramfs(image, destination):
    magic, length, flags = struct.unpack_from('<III', image)
    if magic != 0x28cd3d45 or flags & ~0x503:
        raise ValueError('unsupported cramfs format/features')
    if length > len(image):
        raise ValueError('truncated cramfs')
    links = []
    count = 0
    def inode(offset):
        a, b, c = struct.unpack_from('<III', image, offset)
        return a & 0xffff, b & 0xffffff, (c & 63) * 4, (c >> 6) * 4
    def content(size, offset):
        blocks = (size + 4095) // 4096
        start = offset + blocks * 4
        output = bytearray()
        for i in range(blocks):
            end, = struct.unpack_from('<I', image, offset + i * 4)
            if not start <= end <= len(image):
                raise ValueError('invalid cramfs block pointer')
            output.extend(zlib.decompress(image[start:end]) if end > start else bytes(4096))
            start = end
        if len(output) < size:
            raise ValueError('truncated cramfs file')
        return bytes(output[:size])
    def visit(path, node):
        nonlocal count
        mode, size, _, offset = node
        count += 1
        if stat.S_ISDIR(mode):
            path.mkdir(parents=True, exist_ok=True)
            pos = offset
            while pos < offset + size:
                child = inode(pos)
                name = image[pos + 12:pos + 12 + child[2]].rstrip(b'\0').decode()
                if not name or '/' in name or name in ('.', '..'):
                    raise ValueError('unsafe cramfs name')
                visit(path / name, child)
                pos += 12 + child[2]
            if pos != offset + size:
                raise ValueError('invalid cramfs directory length')
        elif stat.S_ISREG(mode):
            path.write_bytes(content(size, offset))
            path.chmod(mode & 0o777)
        elif stat.S_ISLNK(mode):
            links.append((path, content(size, offset).decode()))
        # Device nodes are intentionally omitted: runtime mounts supply them.
    visit(destination, inode(64))
    # Create links last and convert absolute chroot links to confined relative
    # links, so host-side inspection cannot resolve into the host filesystem.
    for path, target in links:
        if target.startswith('/'):
            resolved = destination / target.lstrip('/')
        else:
            resolved = Path(os.path.normpath(path.parent / target))
        if not resolved.is_relative_to(destination):
            raise ValueError(f'escaping symlink: {path}')
        path.symlink_to(os.path.relpath(resolved, path.parent))
    return count


def extract_regular_tar(blob, out):
    with tarfile.open(fileobj=io.BytesIO(blob), mode='r:gz') as archive:
        for member in archive:
            relative = confined_name(member.name)
            target = out / relative
            if not target.resolve().is_relative_to(out.resolve()):
                raise ValueError(f'escaping tar destination: {member.name}')
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            elif member.isfile():
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.extractfile(member).read())
                target.chmod(member.mode & 0o777)
            else:
                raise ValueError(f'unsupported tar entry: {member.name}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--firmware', required=True, type=Path)
    parser.add_argument('--gpl', required=True, nargs=2, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    # Concatenated source archive stays local and is removed after key recovery.
    source = out / 'gpl-source.tar.bz2'
    parts = {}
    for filename in args.gpl:
        with zipfile.ZipFile(filename) as archive:
            for name in archive.namelist():
                if name.endswith(('.tar.bz2.00', '.tar.bz2.01')):
                    parts[name[-2:]] = (filename, name)
    if set(parts) != {'00', '01'}:
        raise ValueError('both GPL source parts are required')
    with source.open('wb') as combined:
        for part in ('00', '01'):
            filename, name = parts[part]
            # AlphaTheta uses Deflate64 ZIP members, unsupported by zipfile.
            subprocess.run(['unzip', '-p', str(filename), name], stdout=combined, check=True)
    with tarfile.open(source, 'r:bz2') as archive:
        initramfs = archive.extractfile('pioneerdj_xdj_rx3/initramfs.tar.gz').read()
    with tarfile.open(fileobj=io.BytesIO(initramfs), mode='r:gz') as archive:
        keyfile = archive.extractfile('initramfs/usr/local/pdj/aes256.key').read()
    source.unlink()
    key = keyfile.split(b'\n')[0][:31].ljust(32, b'\0')
    with zipfile.ZipFile(args.firmware) as archive:
        names = [n for n in archive.namelist() if n.endswith('XDJRX3.UPD')]
        if len(names) != 1:
            raise ValueError('firmware must contain exactly one XDJRX3.UPD')
        encrypted = archive.read(names[0])
    if len(encrypted) != 69171216:
        raise ValueError('unexpected RX3 1.20 firmware size')
    body = encrypted[:-16]
    decoded = bytearray()
    for n in range(0, len(body), 512):
        iv = struct.pack('<I', n // 512) + bytes(12)
        decoded.extend(AES.new(key, AES.MODE_CBC, iv).decrypt(body[n:n + 512]))
    if decoded[32769:32774] != b'CD001':
        raise ValueError('invalid decoded ISO signature')
    iso = pycdlib.PyCdlib()
    iso.open_fp(io.BytesIO(decoded))
    images = {}
    for directory, _, files in iso.walk(rr_path='/'):
        for filename in files:
            if filename in ('rootfs.cramfs', 'pdj.tar.gz', 'gui.tar.gz', 'settings.tar.gz'):
                stream = io.BytesIO()
                iso.get_file_from_iso_fp(stream, rr_path=directory.rstrip('/') + '/' + filename)
                images[filename] = stream.getvalue()
    iso.close()
    rootfs = out / 'rootfs'
    print('Extracted cramfs nodes:', unpack_cramfs(images['rootfs.cramfs'], rootfs))
    # Do not retain the published key in the runtime bundle.
    for keypath in rootfs.rglob('aes256.key'):
        keypath.unlink()
    for name in ('pdj', 'gui', 'settings'):
        target = out / name
        target.mkdir()
        extract_regular_tar(images[name + '.tar.gz'], target)
    print('RX3 userspace staged:', out)


if __name__ == '__main__':
    main()
