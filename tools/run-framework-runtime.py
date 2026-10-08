"""Execute Source Java/JNI/ART on the verified headset in a temporary private directory."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess
import uuid

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--adb', required=True)
    parser.add_argument('--serial', required=True)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--expected-fixtures', type=int, choices=[9, 12, 19, 23, 24, 25, 26, 27, 28, 29, 30], default=9)
    args = parser.parse_args()
    state = json.loads((ROOT / 'outputs/vr-preview-01-installation/state.json').read_text())
    manifest = json.loads((args.package / 'manifest.json').read_text())
    use_image = manifest.get('boot_image_used') is True

    def adb(*arguments, timeout=30, check=True, redact=True):
        result = subprocess.run([args.adb, '-s', args.serial, *arguments], capture_output=True,
                                text=True, encoding='utf-8', errors='replace', timeout=timeout)
        output = (result.stdout + result.stderr).strip()
        if check and result.returncode:
            raise RuntimeError(output.replace(args.serial, '<device>'))
        if redact:
            output = output.replace(args.serial, '<device>')
        return result.returncode, output

    # A USB transport can equal ro.serialno; authenticate its original bytes.
    identity = adb('shell', 'getprop ro.serialno', redact=False)[1]
    if hashlib.sha256(identity.encode()).hexdigest() != state['device_serial_sha256']:
        raise RuntimeError('Unexpected hardware identity')
    if adb('shell', 'getprop ro.product.device')[1] != 'PICOA8110':
        raise RuntimeError('Unexpected model')
    if adb('shell', 'id -u')[1] != '2000':
        raise RuntimeError('Isolated runtime must run as ordinary shell UID')
    fingerprint = adb('shell', 'getprop ro.build.fingerprint')[1]
    for name, digest in manifest['files'].items():
        if hashlib.sha256((args.package / name).read_bytes()).hexdigest() != digest:
            raise RuntimeError('Package file changed: ' + name)
    remote = '/data/local/tmp/picomisu-framework-runtime-' + uuid.uuid4().hex
    report = {'system_partitions_modified': False, 'vr_services_replaced': False,
              'boot_image_requested': use_image, 'boot_image_used': False,
              'source_sha256': manifest['files'], 'results': {}}
    report_file = ROOT / ('reports/framework-bridge/framework-boot-image-test.json' if use_image
                         else 'reports/framework-bridge/framework-runtime-test.json')
    report_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        adb('shell', 'mkdir ' + remote)
        adb('push', str(args.package) + '/.', remote + '/', timeout=180)
        actual = adb('shell', 'find ' + remote + ' -type f -exec toybox sha256sum {} +')[1]
        device_hashes = {line.split(maxsplit=1)[1].removeprefix(remote + '/'): line.split()[0]
                         for line in actual.splitlines() if len(line.split()) == 2}
        for name, digest in manifest['files'].items():
            if device_hashes.get(name) != digest:
                raise RuntimeError('Uploaded artifact differs: ' + name)
        adb('shell', 'mkdir -p ' + remote + '/data/dalvik-cache/arm64 ' + remote + '/data/dalvik-cache/arm')
        print('Uploaded and verified Source runtime package', flush=True)
        boot = ':'.join(remote + '/' + name for name in manifest['boot_classpath'])
        for abi, suffix in [('arm64', '64'), ('arm', '32')]:
            directory = remote + '/' + abi
            executable = directory + '/app_process' + suffix
            preload = directory + '/libpicomisu_framework_runtime_probe.so'
            adb('shell', 'chmod 700 ' + executable)
            environment = {'LD_LIBRARY_PATH': directory, 'LD_PRELOAD': preload,
                           'ANDROID_ROOT': remote + '/system', 'ANDROID_RUNTIME_ROOT': remote + '/runtime',
                           'ANDROID_DATA': remote + '/data', 'BOOTCLASSPATH': boot,
                           'CLASSPATH': remote + '/probe.jar'}
            command = [executable, '-Ximage:' + remote + '/no-boot-image.art',
                       '-Xnoimage-dex2oat', '-Xcompiler:' + remote + '/no-dex2oat',
                       '-Xhidden-api-policy:disabled',
                       '-Xuse-stderr-logger',
                       '-Djava.library.path=' + directory, remote + '/system/bin',
                       'org.picomisu.runtime.FrameworkRuntimeProbe', preload]
            if use_image:
                loader = directory + '/source-linker'
                adb('shell', 'chmod 700 ' + loader)
                config = ('dir.picomisu = ' + remote + '\n[picomisu]\n'
                          'additional.namespaces = runtime,conscrypt,media,sphal\n'
                          'namespace.default.isolated = false\n'
                          'namespace.default.visible = true\n'
                          'namespace.default.search.paths = ' + directory + '\n')
                for namespace in ['runtime', 'conscrypt', 'media']:
                    config += ('namespace.' + namespace + '.isolated = false\n'
                               'namespace.' + namespace + '.visible = true\n'
                               'namespace.' + namespace + '.links = default\n'
                               'namespace.' + namespace + '.link.default.allow_all_shared_libs = true\n')
                vendorlib = 'lib64' if abi == 'arm64' else 'lib'
                config += ('namespace.sphal.isolated = false\n'
                           'namespace.sphal.visible = true\n'
                           'namespace.sphal.search.paths = /vendor/' + vendorlib + ':/odm/' + vendorlib + '\n'
                           'namespace.sphal.links = default\n'
                           'namespace.sphal.link.default.allow_all_shared_libs = true\n')
                local_config = args.package / ('isolated-linker-' + abi + '.txt')
                local_config.write_text(config)
                adb('push', str(local_config), remote + '/isolated-linker-' + abi + '.txt')
                environment['LD_CONFIG_FILE'] = remote + '/isolated-linker-' + abi + '.txt'
                command[1] = '-Ximage:' + remote + '/system/framework/boot.art'
                command.insert(2, '-Xbootclasspath-locations:' + ':'.join(manifest['boot_classpath_locations']))
                command.insert(3, '-Xnorelocate')
                command.insert(0, loader)
            child = 'echo runtime-pid $$; exec env '
            child += ' '.join(k + '=' + shlex.quote(v) for k, v in environment.items())
            child += ' ' + shlex.join(command)
            invocation = 'toybox timeout 300 sh -c ' + shlex.quote(child)
            print(abi + ': starting Source Java/JNI/ART', flush=True)
            code, output = adb('shell', invocation, timeout=360, check=False)
            report['results'][abi] = {'exit_code': code, 'output': output}
            if code or 'framework-runtime-probe passed=' + str(args.expected_fixtures) not in output:
                pid = re.search(r'^runtime-pid (\d+)$', output, re.MULTILINE)
                if pid:
                    report['results'][abi]['runtime_logcat'] = adb(
                            'shell', 'logcat -d --pid=' + pid.group(1), check=False)[1]
                raise RuntimeError('Source Java runtime failed for ' + abi + '\n' + output)
            if 'runtime-boot-classpath ' + boot not in output:
                raise RuntimeError('Unexpected Java bootclasspath')
            loaded = dict(re.findall(r'^runtime-library (\S+) (\S+)$', output, re.MULTILINE))
            for name in ['libart.so', 'libandroid_runtime.so', 'libgui.so']:
                if loaded.get(name) != directory + '/' + name:
                    raise RuntimeError('Factory library entered Source group: ' + name)
            report['results'][abi]['passed'] = args.expected_fixtures
            report['results'][abi]['source_libraries_verified'] = loaded
            if use_image:
                images = set(re.findall(r'^runtime-image (\S+)$', output, re.MULTILINE))
                expected_images = {remote + '/' + name for name in manifest['files']
                                   if name.startswith('system/framework/' + abi + '/')
                                   and name.endswith(('.art', '.oat'))}
                if len(expected_images) != 2 * manifest.get('boot_image_jars', 11) or images != expected_images:
                    raise RuntimeError('Source compiled boot image was not mapped: ' +
                                       ', '.join(sorted(expected_images.symmetric_difference(images))))
                mapped_libraries = set(re.findall(r'^runtime-mapped-library (\S+)$', output, re.MULTILINE))
                for name in ['libc.so', 'libdl.so', 'libm.so', 'libjavacore.so', 'libopenjdk.so']:
                    if directory + '/' + name not in mapped_libraries:
                        raise RuntimeError('Source runtime/Bionic library not mapped: ' + name)
                    if any(p.endswith('/' + name) and p != directory + '/' + name for p in mapped_libraries):
                        raise RuntimeError('Duplicate factory runtime/Bionic mapping: ' + name)
                report['results'][abi]['mapped_source_images'] = sorted(
                        name.removeprefix(remote + '/') for name in expected_images)
                report['results'][abi]['source_bionic_and_core_jni_verified'] = True
            print(abi + ': ' + str(args.expected_fixtures) + ' Java/JNI/ART fixtures passed', flush=True)
        report['boot_image_used'] = use_image
    except Exception as exc:
        report['error'] = str(exc)
        raise
    finally:
        report['fingerprint_unchanged'] = adb('shell', 'getprop ro.build.fingerprint')[1] == fingerprint
        report['boot_completed'] = adb('shell', 'getprop sys.boot_completed')[1] == '1'
        if not re.fullmatch(r'/data/local/tmp/picomisu-framework-runtime-[0-9a-f]{32}', remote):
            raise RuntimeError('Invalid cleanup directory')
        adb('shell', 'rm -rf ' + remote)
        report['temporary_files_removed'] = adb('shell', 'test ! -e ' + remote, check=False)[0] == 0
        report_file.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
