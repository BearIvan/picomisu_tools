"""Package a complete Source Java/JNI/ART dependency group for an isolated process."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--product', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--boot-image', action='store_true',
                        help='Include compiled Source boot images, Source linker and Source Bionic')
    args = parser.parse_args()
    for relative in ['system/framework/picomisu-framework-runtime-probe.jar',
                     'system/lib/libpicomisu_framework_runtime_probe.so',
                     'system/lib64/libpicomisu_framework_runtime_probe.so']:
        if (args.product / relative).exists():
            raise RuntimeError('Test artifact must be removed from system output: ' + relative)
    args.out.mkdir(parents=True, exist_ok=False)
    runtime = args.product / 'system/apex/com.android.runtime.debug'
    manifest = {'files': {}, 'source_paths': {}, 'boot_classpath': [],
                'system_libraries_used': [] if args.boot_image else ['libc.so', 'libm.so', 'libdl.so'],
                'system_partitions_modified': False, 'boot_image_used': args.boot_image,
                'test_artifacts_in_system_image': False}

    def copy(source, relative):
        if not source.is_file():
            raise RuntimeError('Missing Source artifact: ' + str(source))
        target = args.out / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        manifest['files'][relative] = hashlib.sha256(target.read_bytes()).hexdigest()
        try:
            manifest['source_paths'][relative] = str(source.relative_to(args.product))
        except ValueError:
            manifest['source_paths'][relative] = '@out/' + str(source.relative_to(args.product.parents[2]))

    environ = (args.product / 'root/init.environ.rc').read_text()
    boot = re.search(r'^\s*export BOOTCLASSPATH (\S+)', environ, re.MULTILINE).group(1).split(':')
    manifest['boot_classpath_locations'] = boot
    for location in boot:
        if location.startswith('/apex/com.android.runtime/'):
            relative = 'runtime/' + location.removeprefix('/apex/com.android.runtime/')
            source = runtime / location.removeprefix('/apex/com.android.runtime/')
        elif location.startswith('/apex/'):
            relative = location.lstrip('/')
            source = args.product / 'system' / relative
        elif location.startswith('/system/framework/'):
            relative = location.lstrip('/')
            source = args.product / relative
        else:
            raise RuntimeError('Unexpected Source bootclasspath path: ' + location)
        copy(source, relative)
        manifest['boot_classpath'].append(relative)
    jar = args.product.parents[2] / ('soong/.intermediates/frameworks/base/core/jni/picomisu_runtime/'
            'picomisu-framework-runtime-probe/android_common/dex/picomisu-framework-runtime-probe.jar')
    copy(jar, 'probe.jar')
    public_list = args.product / 'system/etc/public.libraries.txt'
    copy(public_list, 'system/etc/public.libraries.txt')
    public_libraries = [line.split() for line in public_list.read_text().splitlines()
                        if line.strip() and not line.lstrip().startswith('#')]
    for source in sorted((runtime / 'etc').rglob('*')):
        if source.is_file():
            copy(source, 'runtime/' + str(source.relative_to(runtime)))

    # Every boot JAR outside the updatable APEXes is compiled into the boot image.
    image_jars = [l for l in boot if l.startswith(('/apex/com.android.runtime/', '/system/'))]
    manifest['boot_image_jars'] = len(image_jars)
    for abi, directory, suffix in [('arm64', 'lib64', '64'), ('arm', 'lib', '32')]:
        if args.boot_image:
            images = sorted((args.product / 'system/framework' / abi).glob('boot*'))
            if len(images) != 3 * len(image_jars) or {f.suffix for f in images} != {'.art', '.oat', '.vdex'}:
                raise RuntimeError('Incomplete Source boot image group for ' + abi)
            for source in images:
                if source.suffix == '.vdex':
                    # The two architecture directories link to shared VDEX files.
                    # Use their real source path, also readable through Windows UNC.
                    source = args.product / 'system/framework' / source.name
                copy(source, 'system/framework/' + abi + '/' + source.name)
            copy(runtime / 'bin' / ('linker64' if abi == 'arm64' else 'linker'), abi + '/source-linker')
        search = [runtime / directory, args.product / 'system' / directory, runtime / directory / 'bionic']
        search.extend(sorted(p / directory for p in (args.product / 'system/apex').iterdir()
                             if p != runtime and (p / directory).is_dir()))

        def library(name):
            for folder in search:
                path = folder / name
                if path.is_file():
                    return path
            raise RuntimeError('Missing Source dependency: ' + name + ' for ' + abi)

        testdir = 'nativetest64' if abi == 'arm64' else 'nativetest'
        queue = [args.product / ('system/bin/app_process' + suffix),
                 args.product / 'data' / testdir / 'picomisu_framework_runtime_probe/libpicomisu_framework_runtime_probe.so']
        queue += [library(name) for name in [
            'libart.so', 'libart-compiler.so', 'libartpalette-system.so', 'libdexfile_external.so',
            'libion.so', 'libjavacore.so', 'libopenjdk.so', 'libopenjdkjvm.so', 'libjavacrypto.so']]
        queue += [library(entry[0]) for entry in public_libraries
                  if entry[0] not in manifest['system_libraries_used']
                  and (len(entry) == 1 or entry[1] == suffix)]
        seen = set()
        while queue:
            source = queue.pop()
            if source.name in seen:
                continue
            seen.add(source.name)
            copy(source, abi + '/' + source.name)
            dynamic = subprocess.check_output(['readelf', '-d', str(source)], text=True)
            if re.search(r'\((?:RUNPATH|RPATH)\)', dynamic):
                raise RuntimeError('Unexpected embedded native search path: ' + str(source))
            for name in re.findall(r'\(NEEDED\).*?\[([^\]]+)\]', dynamic):
                if name not in manifest['system_libraries_used']:
                    queue.append(library(name))
        symbols = subprocess.check_output(['readelf', '--dyn-syms', '--wide',
                str(args.out / abi / 'libpicomisu_framework_runtime_probe.so')], text=True)
        if not re.search(r'GLOBAL\s+DEFAULT\s+(?!UND\b)\S+\s+_ZN7android21defaultServiceManagerEv\b', symbols):
            raise RuntimeError('Local service manager interposition is missing')
    (args.out / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print('Packaged', len(manifest['files']), 'Source files with', len(boot), 'boot JARs')


if __name__ == '__main__':
    main()
