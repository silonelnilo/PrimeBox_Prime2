#!/usr/bin/env python3
"""Assemble a local, manual-test userspace bundle; never installs or flashes.
Requires pyelftools. Inputs are prepare-rx3.py output and a verified open payload.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import struct
import tarfile
from elftools.elf.elffile import ELFFile


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def elf_info(path):
    with path.open('rb') as stream:
        elf = ELFFile(stream)
        if elf.elfclass != 32 or elf['e_machine'] != 'EM_ARM' or not elf.little_endian:
            raise ValueError(f'not ARM32 little-endian: {path}')
        if elf['e_flags'] & 0x400:
            raise ValueError(f'hard-float ELF: {path}')
        dynamic = elf.get_section_by_name('.dynamic')
        needed = [t.needed for t in dynamic.iter_tags() if t.entry.d_tag == 'DT_NEEDED'] if dynamic else []
        symbols = elf.get_section_by_name('.dynsym')
        exports, imports = set(), set()
        if symbols:
            for sym in symbols.iter_symbols():
                if sym['st_info']['bind'] not in ('STB_GLOBAL', 'STB_WEAK'):
                    continue
                if sym['st_shndx'] != 'SHN_UNDEF':
                    exports.add(sym.name)
                elif sym['st_info']['bind'] == 'STB_GLOBAL':
                    imports.add(sym.name)
        definitions, requirements = set(), {}
        version = elf.get_section_by_name('.gnu.version_d')
        if version:
            for _, auxiliaries in version.iter_versions():
                definitions.update(a.name for a in auxiliaries)
        version = elf.get_section_by_name('.gnu.version_r')
        if version:
            for item, auxiliaries in version.iter_versions():
                requirements[item.name] = {a.name for a in auxiliaries}
        return needed, exports, imports, definitions, requirements


def validate_runtime(root, entrypoints):
    pending = list(entrypoints)
    checked = {}
    def library(name):
        for directory in ('lib', 'usr/lib'):
            path = root / directory / name
            if path.is_file() and path.resolve().is_relative_to(root.resolve()):
                return path.resolve()
        raise ValueError(f'missing dependency: {name}')
    while pending:
        path = pending.pop().resolve()
        if path in checked:
            continue
        info = elf_info(path)
        checked[path] = info
        pending.extend(library(name) for name in info[0])
    exports = set().union(*(info[1] for info in checked.values()))
    for path, info in checked.items():
        missing = info[2] - exports
        if missing:
            raise ValueError(f'{path.name}: unresolved imports {sorted(missing)}')
        for lib, versions in info[4].items():
            available = checked[library(lib)][3]
            if not versions <= available:
                raise ValueError(f'{path.name}: missing versions in {lib}: {sorted(versions - available)}')
    return [str(p.relative_to(root.resolve())) for p in sorted(checked)]


def abi_value(path, name, offset=0):
    with path.open('rb') as stream:
        elf = ELFFile(stream)
        matches = elf.get_section_by_name('.dynsym').get_symbol_by_name(name)
        if not matches:
            raise ValueError(f'missing DirectFB ABI marker: {path.name}')
        symbol = matches[0]
        section = elf.get_section(symbol['st_shndx'])
        return struct.unpack_from('<I', section.data(), symbol['st_value'] - section['sh_addr'] + offset)[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--staging', required=True, type=Path)
    parser.add_argument('--payload', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    source, payload, out = args.staging.resolve(), args.payload.resolve(), args.output.resolve()
    for line in (payload / 'SHA256SUMS.txt').read_text().splitlines():
        expected, name = line.split('  ', 1)
        item = payload / name
        if not item.resolve().is_relative_to(payload) or digest(item) != expected:
            raise ValueError(f'payload checksum mismatch: {name}')
    actual_abi = abi_value(payload / 'libdirectfb_fbdev-rot16.so', 'primebox_dfb_system_abi')
    expected_abi = abi_value(source / 'rootfs/usr/lib/libdirectfb-1.4.so.0', 'dfb_core_systems', 28)
    if actual_abi != expected_abi:
        raise ValueError(f'DirectFB plugin ABI {actual_abi} != RX3 {expected_abi}')
    out.mkdir(parents=True, exist_ok=False)
    data = out / 'data'
    root = data / 'rbx3-run'
    root.mkdir(parents=True)
    for directory in ('bin', 'lib', 'usr/lib', 'usr/share/alsa'):
        src = source / 'rootfs' / directory
        shutil.copytree(src, root / directory, symlinks=True, ignore=shutil.ignore_patterns('modules', 'udev', 'gfxdrivers'))
    # RX3's Vivante driver probes even with no-hardware, then fails on JC16.
    # Keep the software rasterizer in libdirectfb and an empty driver directory.
    (root / 'usr/lib/directfb-1.4-0/gfxdrivers').mkdir(parents=True, exist_ok=True)
    (root / 'usr/bin').mkdir(parents=True, exist_ok=True)
    for name in ('edb_streamd', 'kill_daemon', 'env'):
        src = source / 'rootfs/usr/bin' / name
        shutil.copy2(src, root / 'usr/bin' / name, follow_symlinks=False)
    for directory in ('dev', 'proc', 'sys', 'tmp', 'etc', 'usr/etc', 'root/pdj', 'root/settings', 'media/usb1/sda1'):
        (root / directory).mkdir(parents=True, exist_ok=True)
    for name in ('passwd', 'group', 'nsswitch.conf', 'hosts', 'resolv.conf', 'asound.conf'):
        src = source / 'rootfs/etc' / name
        if src.is_file() and not src.is_symlink():
            shutil.copy2(src, root / 'etc' / name)
    shutil.copytree(source / 'gui', root / 'root/gui', symlinks=True)
    stock = source / 'pdj/pdj/rbp'
    if hashlib.md5(stock.read_bytes()).hexdigest() != '4f2efcfc0c9e3f539289f863acfddcc6':
        raise ValueError('stock player does not match RX3 1.20')
    patcher = Path(__file__).resolve().parents[1] / 'patch-rbp/rbp_patch.py'
    subprocess.run(['python3', str(patcher), str(stock), '-o', str(data / 'rbp-audio')], check=True)
    if hashlib.md5((data / 'rbp-audio').read_bytes()).hexdigest() != '3706c68f7242779d46afa09f35a39acf':
        raise ValueError('patched player hash mismatch')
    for src in payload.iterdir():
        if src.is_file():
            shutil.copy2(src, data / src.name)
    shutil.copy2(data / 'rbp-audio', root / 'root/pdj/rbp')
    (data / 'rbp-audio').chmod(0o755)
    (root / 'root/pdj/rbp').chmod(0o755)
    for src, name in [('audioshim-jc16.so', 'audioshim.so'), ('knobshim2.so', 'knobshim.so'), ('fbshim-tsc.so', 'fbshim.so')]:
        shutil.copy2(data / src, root / 'usr/lib' / name)
        shutil.copy2(data / src, root / 'root/pdj' / name)
    module = root / 'usr/lib/directfb-1.4-0/systems/libdirectfb_fbdev.so'
    shutil.copy2(data / 'libdirectfb_fbdev-rot16.so', module)
    (root / 'usr/etc/directfbrc').write_text('no-hardware\nno-cursor\nsystem=fbdev\nfbdev=/dev/fb0\n')
    required = [root / 'root/gui/pset/imagedata/imagedata.dat', root / 'root/gui/pset/fontdata/NS_FONT_ID_ISO8859_w.bin', root / 'root/gui/system/fontdata/sazanami-gothic.ttf', root / 'bin/sh', root / 'usr/bin/env', root / 'lib/ld-linux.so.3']
    for path in required:
        if not path.is_file():
            raise ValueError(f'missing runtime resource: {path}')
    entrypoints = [root / 'root/pdj/rbp', root / 'usr/bin/edb_streamd', root / 'bin/busybox', module] + [root / 'usr/lib' / name for name in ('audioshim.so', 'knobshim.so', 'fbshim.so')]
    objects = validate_runtime(root, entrypoints)
    # Resolve only lexical, confined links. Some /proc and /dev targets are
    # intentionally supplied by runtime binds, so they need not exist here.
    for path in root.rglob('*'):
        if path.is_symlink() and not path.resolve().is_relative_to(root):
            raise ValueError(f'escaping runtime symlink: {path}')
        if path.name == 'aes256.key':
            raise ValueError('key must not be included in runtime bundle')
    report = {'payload_commit': (data / 'BUILD_COMMIT.txt').read_text().strip(), 'elf_dependency_closure': objects, 'checks': ['payload SHA256', 'stock and patched player hashes', 'ARM32 soft-float', 'strong imports', 'required symbol versions', 'fonts and resources', 'confined symlinks'], 'hardware_tested': False, 'usb_hotplug': 'disabled until Prime 2 buses are measured'}
    (out / 'VALIDATION.json').write_text(json.dumps(report, indent=2) + '\n')
    (out / 'README.txt').write_text('PrimeBox Prime 2 / JC16 — manual-test userspace bundle\n\nThis is a staged test candidate; it has NOT been run on Prime 2 hardware.\nNothing has been copied to the console or flashed.\n\nVerify SHA256SUMS.txt from this directory. Preserve existing /data files\nbefore copying the CONTENTS of data/ to /data on the console.\nNever run the stock Pioneer apl_start or firmware update scripts.\nThis bundle does not install a boot-menu entry or change SSH.\n\nManual start: sh /data/start-rb-jc16.sh\nRollback: sh /data/stop-rb-jc16.sh\n\nFirst verify display/process stability, then touch and controls, then audio.\nUSB hotplug is intentionally disabled pending measured host-bus mapping.\nKeep this bundle local: it contains proprietary RX3 userspace/resources.\n')
    with (out / 'SHA256SUMS.txt').open('w') as manifest:
        for path in sorted(out.rglob('*')):
            if path.is_file() and not path.is_symlink() and path != out / 'SHA256SUMS.txt':
                manifest.write(f'{digest(path)}  {path.relative_to(out)}\n')
    archive = out.with_suffix('.tar.gz')
    with tarfile.open(archive, 'w:gz', format=tarfile.PAX_FORMAT) as tar:
        tar.add(out, arcname=out.name)
    archive.with_suffix(archive.suffix + '.sha256').write_text(f'{digest(archive)}  {archive.name}\n')
    print(f'PASS: {len(objects)} ARM ELF objects and their required symbol versions')
    print(f'Bundle created: {archive}')


if __name__ == '__main__':
    main()
