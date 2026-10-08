"""Record the qualified frame-diagnostics checkpoint from matching test packages."""
import argparse
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write(path, data):
    path.write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')


def gtests(data):
    if isinstance(data, str):
        return set(re.findall(r'^\[ RUN\s+\]\s+(\S+)', data, re.MULTILINE))
    if isinstance(data, dict):
        return set().union(*(gtests(value) for value in data.values()))
    return set()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--framework-package', type=Path, required=True)
    args = parser.parse_args()
    package = args.package.resolve()
    framework_package = args.framework_package.resolve()
    manifest = read(package / 'manifest.json')
    framework_manifest = read(framework_package / 'manifest.json')
    report = read(ROOT / 'reports/framework-bridge/bufferqueue-runtime-test.json')
    framework = read(ROOT / 'reports/framework-bridge/framework-boot-image-test.json')
    config = read(ROOT / 'config/aosp-patches.json')
    commits = {entry['path']: entry['local_commit'] for entry in config['projects']}
    if manifest['files'] != report['test_library_sha256']:
        raise RuntimeError('Native report does not match this package')
    if framework_manifest['files'] != framework['source_sha256']:
        raise RuntimeError('Framework report does not match this package')
    for base, data in ((package, manifest), (framework_package, framework_manifest)):
        for relative, digest in data['files'].items():
            if hashlib.sha256((base / relative).read_bytes()).hexdigest() != digest:
                raise RuntimeError('Artifact changed: ' + relative)
    for evidence in (report, framework):
        if evidence.get('error') or evidence['system_partitions_modified']:
            raise RuntimeError('The checkpoint did not complete in isolation')
        for name in ('fingerprint_unchanged', 'boot_completed', 'temporary_files_removed'):
            if evidence.get(name) is not True:
                raise RuntimeError('Missing postcondition: ' + name)
    if framework.get('boot_image_used') is not True:
        raise RuntimeError('Compiled Source boot images were not loaded')

    abis = {}
    total_native = 0
    for abi in ('arm64', 'arm'):
        result = report['results'][abi]
        for name, count in (('factory_egl_image_tracker_fixtures_matched', 72),
                            ('factory_surface_client_fixtures_matched', 22),
                            ('factory_calling_tid_fixtures_matched', 8)):
            if result.get(name) != count:
                raise RuntimeError('Diagnostic fixture group incomplete: ' + abi + '/' + name)
        if not all(result.get(name) is True for name in (
                'egl_image_tracker_system_property_unchanged',
                'surface_client_layout_runtime_matched', 'calling_tid_query_intercepted')):
            raise RuntimeError('Diagnostic isolation/layout check absent: ' + abi)
        if framework['results'][abi].get('passed') != 12:
            raise RuntimeError('Source framework fixture group incomplete: ' + abi)
        names = gtests(result)
        for key, value in report.items():
            if key.endswith('_' + abi):
                names |= gtests(value)
        if len(names) != 184:
            raise RuntimeError('Unexpected unique native test coverage: ' + abi + '/' + str(len(names)))
        total_native += len(names)
        abis[abi] = {'tracker_fixtures_matched': 72, 'surface_client_fixtures_matched': 22,
                     'caller_query_fixtures_matched': 8, 'native_gtests_passed': len(names),
                     'java_jni_art_fixtures_passed': 12,
                     'source_sha256': {name: manifest['files'][abi + '/' + name]
                                       for name in ('libgui.so', 'libbinder.so')},
                     'system_property_unchanged': True, 'caller_query_intercepted': True}

    compatibility = read(ROOT / 'reports/framework-bridge/libgui-symbol-compatibility.json')
    gui_audit = []
    for result in compatibility:
        impacted = {path: entry['missing_in_aosp_libgui']
                    for path, entry in result['factory_consumers'].items()
                    if entry['missing_in_aosp_libgui']}
        abi = 'arm64' if result['abi'] == 64 else 'arm'
        if result['aosp_sha256'] != manifest['files'][abi + '/libgui.so']:
            raise RuntimeError('GUI audit is for another source library')
        gui_audit.append({'abi': result['abi'], 'factory_sha256': result['factory_sha256'],
                         'aosp_sha256': result['aosp_sha256'],
                         'inspected_factory_elf_count': result['inspected_factory_elf_count'],
                         'changed_vtable_sizes': result['changed_vtable_sizes'],
                         'full_abi_compatibility_proven': False,
                         'consumers_with_missing_symbols': impacted,
                         'missing_used_symbol_count': len(set(s for values in impacted.values() for s in values))
                                                    if result['inspected_factory_elf_count'] else None})
    arm64 = next(entry for entry in gui_audit if entry['abi'] == 64)
    if arm64['missing_used_symbol_count'] != 5 or any(entry['changed_vtable_sizes'] for entry in gui_audit):
        raise RuntimeError('Unexpected GUI compatibility result')
    write(ROOT / 'validation/libgui-abi.json', gui_audit)

    package_name = package.relative_to(ROOT).as_posix()
    framework_name = framework_package.relative_to(ROOT).as_posix()
    manifest_hash = hashlib.sha256((package / 'manifest.json').read_bytes()).hexdigest()
    evidence = {'native_commit': commits['frameworks/native'],
                'framework_commit': commits['frameworks/base'], 'art_commit': commits['art'],
                'patch': 'patches/0031-pico-frame-diagnostics.patch',
                'package': package_name, 'manifest_sha256': manifest_hash,
                'framework_package': framework_name, 'abis': abis,
                'tracker_abi_evidence': 'validation/egl-image-tracker-abi.json',
                'surface_client_abi_evidence': 'validation/surface-client-abi.json',
                'remaining_used_arm64_gui_symbols': 5,
                'system_partitions_modified': False, 'fingerprint_unchanged': True,
                'boot_completed': True, 'temporary_files_removed': True,
                'full_graphics_abi_proven': False, 'real_egl_lifecycle_qualified': False,
                'real_remote_caller_query_qualified': False,
                'scope': 'Actual source/factory tracker virtual calls and frame-history/query methods; '
                         'process-local property, clock and ioctl interception; compiled Source '
                         'Java/JNI/ART/Bionic group; no global graphics or VR replacement'}
    write(ROOT / 'validation/frame-diagnostics-port.json', evidence)

    current_path = ROOT / 'validation/native-runtime-current.json'
    current = read(current_path)
    current.update(native_commit=commits['frameworks/native'], package=package_name,
                   manifest_sha256=manifest_hash, native_tests_total=total_native,
                   evidence_packages=[package_name, framework_name],
                   frame_diagnostics_evidence='validation/frame-diagnostics-port.json',
                   factory_probe_fixtures_per_abi={abi: {name: count for name, count in report['results'][abi].items()
                       if name.startswith('factory_') and name.endswith('_fixtures_matched')}
                       for abi in ('arm64', 'arm')},
                   java_runtime_fixtures_per_abi={'arm64': 12, 'arm': 12},
                   compiled_boot_image_fixtures_per_abi={'arm64': 12, 'arm': 12},
                   framework_boot_image_evidence='validation/framework-boot-image.json',
                   compiled_framework_commit=commits['frameworks/base'], art_commit=commits['art'],
                   fingerprint_unchanged=True, boot_completed=True, temporary_files_removed=True,
                   system_partitions_modified=False, full_graphics_compatibility_proven=False)
    current['scope'] = ('Isolated native tests and source/factory fence, cache, dequeue, flags, '
                        'tracker and frame-history comparisons; process-local property, clock '
                        'and ioctl interception; Source Java/JNI on compiled Source boot images, '
                        'ART and Bionic; no global replacement, full private ABI, real freeze '
                        'or remote Binder/GPU/VR qualification')
    write(current_path, current)
    print('Recorded 204 diagnostic comparisons, 368 unique native tests and 24 Source Java/JNI/ART fixtures; 5 GUI imports remain')


if __name__ == '__main__':
    main()
