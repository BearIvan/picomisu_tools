"""Test three AOSP command tools in a unique temporary directory on the headset.

This Windows-side smoke test never changes a ROM, reboots, installs an APK, or
uses su. It cleans up its own three files and its empty temporary directory.
Only fixed test strings and help/version output are collected, not device logs.
"""
import hashlib
import json
from pathlib import Path
import subprocess
import uuid

ROOT = Path(__file__).resolve().parents[1]
ADB = Path('C:/Users/RedPanda/AppData/Local/Android/Sdk/platform-tools/adb.exe')
PRODUCT = Path('//wsl.localhost/Ubuntu-24.04/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro/out/aosp-10/target/product/PICOA8110')


def run(*arguments, input=None):
    result = subprocess.run([str(ADB), *arguments], input=input, capture_output=True, check=True, timeout=90)
    return result.stdout


def main():
    connected = [line for line in run('devices').decode().splitlines()[1:] if line.endswith('\tdevice')]
    if len(connected) != 1:
        raise RuntimeError('Expected one authorized ADB device; no device modifications made')
    if run('shell', 'getprop', 'ro.product.device').decode().strip() != 'PICOA8110':
        raise RuntimeError('Connected device is not PICOA8110; no device modifications made')
    if run('shell', 'getprop', 'ro.build.version.incremental').decode().strip() != 'smartcm.1761817909':
        raise RuntimeError('Expected factory 5.13.7 runtime; no device modifications made')
    names = ['sh', 'toybox', 'logcat']
    local = {name: PRODUCT / 'system/bin' / name for name in names}
    if not all(path.is_file() for path in local.values()):
        raise RuntimeError('AOSP tools have not finished building; no device modifications made')
    factory_applets = set(run('exec-out', '/system/bin/toybox').decode().split())
    directory = '/data/local/tmp/pico-aosp-tools-' + uuid.uuid4().hex
    run('shell', 'mkdir', directory)
    copied = []
    results = {}
    cleaned = False
    try:
        for name, source in local.items():
            destination = directory + '/' + name
            run('push', str(source), destination)
            copied.append(destination)
            run('shell', 'chmod', '755', destination)
        results['sh'] = {'output': run('shell', directory + "/sh -c 'printf PICO_AOSP_SHELL_OK'").decode()}
        if results['sh']['output'] != 'PICO_AOSP_SHELL_OK':
            raise RuntimeError('AOSP shell did not execute the fixed smoke test')
        source_applets = set(run('exec-out', directory + '/toybox').decode().split())
        results['toybox'] = {'version': run('exec-out', directory + '/toybox', '--version').decode().strip(),
                             'missing_factory_applets': sorted(factory_applets - source_applets),
                             'factory_applets': sorted(factory_applets), 'aosp_applets': sorted(source_applets)}
        fixture = b'PICO_AOSP_VR_PREVIEW_01\n'
        checksum_command = directory + '/sh -c \'printf "%s\\n" PICO_AOSP_VR_PREVIEW_01 | ' + directory + "/toybox sha256sum'"
        checksum = run('shell', checksum_command).decode().split()[0]
        if checksum != hashlib.sha256(fixture).hexdigest():
            raise RuntimeError('AOSP Toybox/BoringSSL SHA-256 smoke test failed')
        results['toybox']['sha256_fixture_verified'] = True
        help_text = run('exec-out', directory + '/logcat', '--help').decode()
        if 'logcat' not in help_text.lower():
            raise RuntimeError('AOSP logcat help smoke test failed')
        results['logcat'] = {'help_command_exit_code': 0, 'device_logs_collected': False}
    finally:
        if copied:
            run('shell', 'rm', '--', *copied)
        run('shell', 'rmdir', directory)
        cleaned = True
    report = {'device': 'PICOA8110', 'factory_version': '5.13.7 SEKO b9665',
              'results': results, 'temporary_files_removed': cleaned,
              'rom_changed': False, 'apk_installed': False, 'rebooted': False,
              'tested_sha256': {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in local.items()}}
    (ROOT / 'reports/vr-integration/aosp-tools-smoke.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'tools_smoke_passed': True, 'temporary_files_removed': cleaned,
                      'missing_toybox_applets': results['toybox']['missing_factory_applets']}))


if __name__ == '__main__':
    main()
