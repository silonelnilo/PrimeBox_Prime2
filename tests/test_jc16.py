import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('verify', ROOT / 'tools/build-directfb/verify-module.py')
verify = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verify)


class ModuleChecks(unittest.TestCase):
    header = 'Class: ELF32\nMachine: ARM\nFlags: 0x5000200, Version5 EABI, soft-float ABI'
    symbols = '''00001234 g DF .text 00000010 Base fstat
00001244 g DF .text 00000010 Base __fdelt_chk
00000000 DF *UND* 00000000 (GLIBC_2.4) __fxstat
'''
    dynamic = '\n'.join(f'(NEEDED) Shared library: [{lib}-1.4.so.0]' for lib in ('libdirect', 'libfusion', 'libdirectfb'))

    def check(self, symbols=None, attributes='', dynamic=None):
        return verify.validate(self.header, attributes, symbols if symbols is not None else self.symbols, dynamic if dynamic is not None else self.dynamic)

    def test_actual_objdump_column_order(self):
        self.assertEqual(self.check(), [])
        self.assertNotRegex(self.symbols, r'__fxstat.*GLIBC_2.4')

    def test_missing_or_wrong_version_import_rejected(self):
        self.assertTrue(self.check(self.symbols.replace('__fxstat', '__fxstat64')))
        self.assertTrue(self.check(self.symbols.replace('GLIBC_2.4', 'GLIBC_2.34')))

    def test_missing_export_hardfloat_and_build_rpath_rejected(self):
        self.assertTrue(self.check(self.symbols.replace('Base fstat', 'Base other')))
        self.assertTrue(self.check(attributes='Tag_ABI_VFP_args: VFP registers'))
        self.assertTrue(self.check(dynamic=self.dynamic + '\n(RUNPATH) [/tmp/directfb]'))
        self.assertTrue(self.check(dynamic=self.dynamic.replace('.so.0', '.so.6')))


class RuntimeChecks(unittest.TestCase):
    def test_process_selection_excludes_host_debuggers_and_near_matches(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cases = [
                ('101', '/data/rbx3-run', '/data/rbx3-run/lib/ld-2.13.so', ['/lib/ld-linux.so.3', '/root/pdj/rbp', '-a']),
                ('102', '/', '/usr/bin/gdbserver', ['gdbserver', '/root/pdj/rbp']),
                ('103', '/data/rbx3-run', '/data/rbx3-run/lib/ld-2.13.so', ['/lib/ld-linux.so.3', '/usr/bin/edb_streamd']),
                ('104', '/data/rbx3-run', '/data/rbx3-run/lib/ld-2.13.so', ['/lib/ld-linux.so.3', '/root/pdj/rbp-other']),
                ('105', '/', '/usr/sbin/sshd', ['sshd']),
            ]
            for pid, chroot, exe, args in cases:
                entry = root / pid
                entry.mkdir()
                (entry / 'root').symlink_to(chroot)
                (entry / 'exe').symlink_to(exe)
                (entry / 'cmdline').write_bytes(('\0'.join(args) + '\0').encode())
            result = subprocess.check_output(['sh', '-c', '. "$1"; primebox_pids "$2"', 'sh', str(ROOT / 'scripts/device/jc16-runtime.sh'), tmp], text=True)
            self.assertEqual(result.split(), ['101', '103'])

    def test_stop_attempts_both_services_and_reports_failure(self):
        source = (ROOT / 'scripts/device/stop-rb-jc16.sh').read_text()
        with tempfile.TemporaryDirectory() as tmp:
            source = source.replace('. /data/jc16-runtime.sh', 'primebox_pids() { :; }').replace('/proc/[0-9]*', tmp + '/[0-9]*')
            for fail in (False, True):
                prefix = '''sleep() { :; }
mountpoint() { return 1; }
chmod() { return 0; }
systemctl() { echo "SERVICE $*"; ''' + ('return 1;' if fail else 'return 0;') + ' }\n'
                result = subprocess.run(['sh', '-c', prefix + source], text=True, capture_output=True)
                self.assertIn('SERVICE start edisksd.service', result.stdout)
                self.assertIn('SERVICE start engine.service', result.stdout)
                self.assertEqual(result.returncode, int(fail))
                self.assertEqual('Engine OS services active' in result.stdout, not fail)

    def test_unexpected_copy_failure_after_service_stop_rolls_back(self):
        source = (ROOT / 'scripts/device/start-rb-jc16.sh').read_text()
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / 'data'
            proc = Path(tmp) / 'proc'
            dev = Path(tmp) / 'dev'
            for file in ['audioshim-jc16.so', 'rbp-audio', 'knobshim2.so', 'fbshim-tsc.so', 'libdirectfb_fbdev-rot16.so', 'usb-watch.sh', 'rbx3-run/lib/ld-linux.so.3', 'rbx3-run/usr/bin/edb_streamd']:
                path = data / file
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()
            (data / 'jc16-runtime.sh').write_text('primebox_pids() { :; }\n')
            (data / 'fix-dev.sh').write_text('exit 0\n')
            (data / 'stop-rb-jc16.sh').write_text('echo ROLLBACK\n')
            (proc / 'device-tree').mkdir(parents=True)
            (proc / 'device-tree/compatible').write_bytes(b'inmusic,jc16\0')
            (proc / 'asound').mkdir()
            (proc / 'asound/cards').write_text('JC16')
            for file in ['fb0', 'input/event0', 'snd/seq']:
                path = dev / file
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()
            source = source.replace('/data/', str(data) + '/').replace('/proc/', str(proc) + '/').replace('/dev/fb0', str(dev / 'fb0')).replace('/dev/input/event0', str(dev / 'input/event0')).replace('/dev/snd/seq', str(dev / 'snd/seq'))
            prefix = 'systemctl() { echo "SERVICE $*"; }\nsleep() { :; }\ncp() { return 23; }\n'
            result = subprocess.run(['sh', '-c', prefix + source], text=True, capture_output=True)
            self.assertEqual(result.returncode, 23, result.stderr)
            self.assertIn('SERVICE stop engine.service edisksd.service', result.stdout)
            self.assertIn('ROLLBACK', result.stdout)

    def test_failed_device_unmount_never_deletes_dev(self):
        source = (ROOT / 'scripts/device/fix-dev.sh').read_text()
        prefix = 'mountpoint() { return 0; }\numount() { return 12; }\nrm() { echo DELETE; }\n'
        result = subprocess.run(['sh', '-c', prefix + source], capture_output=True, text=True)
        self.assertEqual(result.returncode, 12)
        self.assertNotIn('DELETE', result.stdout)


if __name__ == '__main__':
    unittest.main()
