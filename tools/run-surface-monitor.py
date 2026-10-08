"""Compare SurfaceMonitor in source/factory GUI using process-local services."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import uuid

ROOT = Path(__file__).resolve().parents[1]
MODES = ('boot-off', 'release', 'userdebug', 'vnd', 'no-transfer', 'no-sys',
         'custom', 'parameters', 'short-parameters', 'self', 'system',
         'render-thread', 'basic', 'quick', 'mixed', 'upgrade', 'downgrade')
FACTORY = {
    'arm64': {'libgui.so': '7b52e5bc29cf5d68c1b24ce6701535dcae64131e3c83b685713ea4a0b4b6dcc5',
              'libbinder.so': '9e5bdf585d73baddf17bbc646b4daea0e2b15d4fb6d8dc244d08412dd1be86a9'},
    'arm': {'libgui.so': '09e91a368003bf8112abaf4adc98f1a78df9ac88ada3f9c81f1eb12f51e68db0',
            'libbinder.so': '0d0459e40cde072ade682b87ff45da9333a30f2efdf908b92255ecd8924e6823'},
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--adb', required=True)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--modes', default=','.join(MODES))
    args = parser.parse_args()
    modes = args.modes.split(',')
    if len(set(modes)) != len(modes) or any(mode not in MODES for mode in modes):
        parser.error('Unsupported or repeated scenario')
    state = json.loads((ROOT / 'outputs/vr-preview-01-installation/state.json').read_text())
    rows = subprocess.check_output([args.adb, 'devices'], text=True).splitlines()[1:]
    verified = [row.split()[0] for row in rows if len(row.split()) == 2 and row.split()[1] == 'device'
                and hashlib.sha256(row.split()[0].encode()).hexdigest() == state['device_serial_sha256']]
    if len(verified) != 1:
        raise RuntimeError('Verified USB transport unavailable')
    serial = verified[0]

    def adb(*arguments, check=True, timeout=40):
        result = subprocess.run([args.adb, '-s', serial, *arguments], capture_output=True,
                                text=True, encoding='utf-8', errors='replace', timeout=timeout)
        output = (result.stdout + result.stderr).strip()
        if check and result.returncode:
            raise RuntimeError(output.replace(serial, '<device>'))
        return result.returncode, output

    identity = adb('shell', 'getprop ro.serialno')[1]
    if hashlib.sha256(identity.encode()).hexdigest() != state['device_serial_sha256']:
        raise RuntimeError('Unexpected hardware identity')
    if adb('shell', 'getprop ro.product.device')[1] != 'PICOA8110' or adb('shell', 'id -u')[1] != '2000':
        raise RuntimeError('Expected ordinary shell on the verified PICO')
    manifest = json.loads((args.package / 'manifest.json').read_text())
    for relative, digest in manifest['files'].items():
        if hashlib.sha256((args.package / relative).read_bytes()).hexdigest() != digest:
            raise RuntimeError('Package file changed: ' + relative)
    properties = ('sys.boot_completed', 'persist.sys.monitor', 'ro.build.type', 'sys.pvr.display.type')
    before = {key: adb('shell', 'getprop ' + key)[1] for key in properties}
    fingerprint = adb('shell', 'getprop ro.build.fingerprint')[1]
    remote = '/data/local/tmp/picomisu-surface-monitor-' + uuid.uuid4().hex
    report = {'system_partitions_modified': False, 'vr_services_replaced': False,
              'source_sha256': manifest['files'], 'results': {}, 'modes': modes,
              'real_display_requests_sent': False, 'real_remote_service_used': False}
    report_path = ROOT / 'reports/framework-bridge/surface-monitor-runtime-test.json'
    try:
        adb('shell', 'mkdir ' + remote)
        for abi in ('arm64', 'arm'):
            adb('push', str(args.package / abi), remote + '/', timeout=120)
        for relative, digest in manifest['files'].items():
            if adb('shell', 'toybox sha256sum ' + remote + '/' + relative)[1].split()[0] != digest:
                raise RuntimeError('Uploaded artifact differs: ' + relative)
        for abi in ('arm64', 'arm'):
            library_dir = 'lib64' if abi == 'arm64' else 'lib'
            for library, digest in FACTORY[abi].items():
                if adb('shell', 'toybox sha256sum /system/' + library_dir + '/' + library)[1].split()[0] != digest:
                    raise RuntimeError('Pinned factory dependency differs: ' + abi + '/' + library)
            directory = remote + '/' + abi
            probe = directory + '/picomisu_surface_monitor_probe'
            adb('shell', 'chmod 700 ' + probe)
            report['results'][abi] = {}
            for mode in modes:
                source = adb('shell', 'LD_LIBRARY_PATH=' + directory + ' ' + probe + ' ' + mode)[1]
                factory = adb('shell', 'LD_LIBRARY_PATH= ' + probe + ' ' + mode)[1]
                source_lines = [line for line in source.splitlines() if line.startswith('surface-monitor ')]
                factory_lines = [line for line in factory.splitlines() if line.startswith('surface-monitor ')]
                expected = 2 if mode in ('boot-off', 'release', 'vnd', 'no-transfer', 'self', 'system', 'render-thread') else 6
                summary = 'surface-monitor-probe passed=' + str(expected)
                report['results'][abi][mode] = {'source_output': source, 'factory_output': factory,
                                               'matched': source_lines == factory_lines,
                                               'expected_snapshots': expected}
                if not source_lines or source_lines != factory_lines or summary not in source or summary not in factory:
                    first_difference = next((i for i in range(min(len(source_lines), len(factory_lines)))
                                             if source_lines[i] != factory_lines[i]), None)
                    raise RuntimeError('SurfaceMonitor differs: ' + abi + '/' + mode +
                                       ', first differing trace line=' + str(first_difference))
                print(abi + '/' + mode + ': ' + str(expected) + ' state snapshots and Binder traces matched', flush=True)
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        report['properties_unchanged'] = all(adb('shell', 'getprop ' + key)[1] == value for key, value in before.items())
        report['fingerprint_unchanged'] = adb('shell', 'getprop ro.build.fingerprint')[1] == fingerprint
        report['boot_completed'] = adb('shell', 'getprop sys.boot_completed')[1] == '1'
        if not re.fullmatch(r'/data/local/tmp/picomisu-surface-monitor-[0-9a-f]{32}', remote):
            raise RuntimeError('Invalid cleanup directory')
        adb('shell', 'rm -rf ' + remote)
        report['temporary_files_removed'] = adb('shell', 'test ! -e ' + remote, check=False)[0] == 0
        report_path.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
