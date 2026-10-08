"""Check compiled bridge signatures, hidden API access and native ABI outputs.

This validates build artifacts only; it does not establish runtime VR compatibility.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    classes = args.out / 'target/common/obj/JAVA_LIBRARIES/framework_intermediates/classes.jar'
    javap = args.source / 'prebuilts/jdk/jdk9/linux-x86/bin/javap'
    declarations = subprocess.check_output(
        [str(javap), '-p', '-s', '-classpath', str(classes), 'android.view.Surface'], text=True)
    for signature in ('nativeSetPvrStatus(long, int);\n    descriptor: (JI)V',
                      'setPvrStatus(int);\n    descriptor: (I)V'):
        if signature not in declarations:
            raise RuntimeError('Missing compiled signature: ' + signature)
    flags = (args.out / 'soong/hiddenapi/hiddenapi-flags.csv').read_text().splitlines()
    public_entry = 'Landroid/view/Surface;->setPvrStatus(I)V'
    matches = [line.split(',')[1:] for line in flags if line.split(',')[0] == public_entry]
    if len(matches) != 1 or 'greylist' not in matches[0] or 'blacklist' in matches[0]:
        raise RuntimeError('PICO public bridge must remain callable by existing clients')
    product = args.out / 'target/product/PICOA8110/system'
    files = {}
    for directory, elf_class in [('lib', 1), ('lib64', 2)]:
        for name in ('libandroid_runtime.so', 'libgui.so'):
            path = product / directory / name
            data = path.read_bytes()
            if data[:4] != b'\x7fELF' or data[4] != elf_class:
                raise RuntimeError('Unexpected ELF class: ' + str(path))
            machine = int.from_bytes(data[18:20], 'little')
            if machine != (40 if elf_class == 1 else 183):
                raise RuntimeError('Unexpected ELF machine: ' + str(path))
            if name == 'libandroid_runtime.so' and b'nativeSetPvrStatus\0' not in data:
                raise RuntimeError('Missing JNI registration name: ' + str(path))
            files[directory + '/' + name] = hashlib.sha256(data).hexdigest()
    framework = product / 'framework/framework.jar'
    files['framework/framework.jar'] = hashlib.sha256(framework.read_bytes()).hexdigest()
    report = {'compiled_signatures_verified': True, 'public_method_hiddenapi_flags': matches[0],
              'arm32_arm64_outputs_verified': True, 'sha256': files,
              'runtime_tested': False, 'installed_on_device': False}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
