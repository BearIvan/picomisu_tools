"""Save the isolated SurfaceMonitor checkpoint and its full regression evidence."""
import argparse
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
MODES = ('boot-off', 'release', 'userdebug', 'vnd', 'no-transfer', 'no-sys',
         'custom', 'parameters', 'short-parameters', 'self', 'system',
         'render-thread', 'basic', 'quick', 'mixed', 'upgrade', 'downgrade')
SHORT_MODES = {'boot-off', 'release', 'vnd', 'no-transfer', 'self', 'system', 'render-thread'}


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def gtests(value):
    if isinstance(value, str):
        runs = set(re.findall(r'^\[ RUN\s+\]\s+(\S+)', value, re.MULTILINE))
        passed = set(re.findall(r'^\[\s+OK\s+\]\s+(\S+)', value, re.MULTILINE))
        if runs != passed:
            raise RuntimeError('Native test started without a matching success result')
        return passed
    if isinstance(value, dict):
        return set().union(*(gtests(item) for item in value.values()))
    return set()


def isolated(report, vr_key):
    if report.get('error') or report.get('system_partitions_modified') is not False:
        raise RuntimeError('Test did not finish without partition changes')
    if report.get(vr_key) is not False:
        raise RuntimeError('Installed VR services were changed')
    for key in ('fingerprint_unchanged', 'boot_completed', 'temporary_files_removed'):
        if report.get(key) is not True:
            raise RuntimeError('Missing test postcondition: ' + key)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--framework-package', type=Path, required=True)
    args = parser.parse_args()
    package = args.package.resolve()
    framework_package = args.framework_package.resolve()
    manifest = read(package / 'manifest.json')
    framework_manifest = read(framework_package / 'manifest.json')
    native = read(ROOT / 'reports/framework-bridge/bufferqueue-runtime-test.json')
    monitor = read(ROOT / 'reports/framework-bridge/surface-monitor-runtime-test.json')
    framework = read(ROOT / 'reports/framework-bridge/framework-boot-image-test.json')
    config = read(ROOT / 'config/aosp-patches.json')
    commits = {entry['path']: entry['local_commit'] for entry in config['projects']}
    if (manifest['files'] != native['test_library_sha256'] or
            manifest['files'] != monitor['source_sha256'] or
            framework_manifest['files'] != framework['source_sha256']):
        raise RuntimeError('Runtime report refers to another package')
    for directory, data in ((package, manifest), (framework_package, framework_manifest)):
        for relative, digest in data['files'].items():
            if hashlib.sha256((directory / relative).read_bytes()).hexdigest() != digest:
                raise RuntimeError('Changed package artifact: ' + relative)
    isolated(native, 'factory_vr_services_replaced')
    isolated(monitor, 'vr_services_replaced')
    isolated(framework, 'vr_services_replaced')
    if (monitor.get('properties_unchanged') is not True or
            monitor.get('real_display_requests_sent') is not False or
            monitor.get('real_remote_service_used') is not False):
        raise RuntimeError('Monitor isolation checks are incomplete')
    if framework.get('boot_image_used') is not True:
        raise RuntimeError('Source compiled boot images were not loaded')

    abi_evidence = read(ROOT / 'validation/surface-monitor-abi.json')
    abis = {}
    for abi in ('arm64', 'arm'):
        names = gtests(native['results'][abi])
        for key, value in native.items():
            if key.endswith('_' + abi):
                names |= gtests(value)
        if len(names) != 189 or native['monitored_producer_' + abi]['passed'] != 5:
            raise RuntimeError('Incomplete native/producer test coverage: ' + abi)
        results = monitor['results'][abi]
        if set(results) != set(MODES):
            raise RuntimeError('Incomplete monitor scenarios: ' + abi)
        for mode, result in results.items():
            expected = 2 if mode in SHORT_MODES else 6
            if result.get('matched') is not True or result.get('expected_snapshots') != expected:
                raise RuntimeError('Monitor state/trace comparison failed: ' + abi + '/' + mode)
        if (framework['results'][abi].get('passed') != 12 or
                framework['results'][abi].get('source_bionic_and_core_jni_verified') is not True):
            raise RuntimeError('Incomplete Source Java/JNI/ART/Bionic evidence: ' + abi)
        for library in ('libgui.so', 'libbinder.so'):
            key = abi + '/' + library
            if manifest['files'][key] != framework_manifest['files'][key]:
                raise RuntimeError('Native and Java tests used different graphics/Binder artifacts')
        if abi_evidence['abis'][abi]['source_sha256'] != manifest['files'][abi + '/libgui.so']:
            raise RuntimeError('Monitor ABI audit refers to another library')
        abis[abi] = {'native_gtests_passed': len(names), 'monitored_producer_gtests_passed': 5,
                     'monitor_scenarios_matched': len(results),
                     'monitor_state_snapshots_matched': sum(x['expected_snapshots'] for x in results.values()),
                     'java_jni_art_fixtures_passed': 12,
                     'source_sha256': {library: manifest['files'][abi + '/' + library]
                                       for library in ('libgui.so', 'libbinder.so')}}

    gui_audit = []
    for entry in read(ROOT / 'reports/framework-bridge/libgui-symbol-compatibility.json'):
        abi = 'arm64' if entry['abi'] == 64 else 'arm'
        if entry['aosp_sha256'] != manifest['files'][abi + '/libgui.so']:
            raise RuntimeError('GUI audit refers to another Source library')
        missing = {path: data['missing_in_aosp_libgui']
                   for path, data in entry['factory_consumers'].items()
                   if data['missing_in_aosp_libgui']}
        gui_audit.append({'abi': entry['abi'], 'factory_sha256': entry['factory_sha256'],
                          'aosp_sha256': entry['aosp_sha256'],
                          'inspected_factory_elf_count': entry['inspected_factory_elf_count'],
                          'changed_vtable_sizes': entry['changed_vtable_sizes'],
                          'full_abi_compatibility_proven': False,
                          'consumers_with_missing_symbols': missing,
                          'missing_used_symbol_count': len({s for symbols in missing.values() for s in symbols})
                          if entry['inspected_factory_elf_count'] else None})
    arm64 = next(entry for entry in gui_audit if entry['abi'] == 64)
    if (arm64['inspected_factory_elf_count'] != 493 or arm64['missing_used_symbol_count'] != 0 or
            any(entry['changed_vtable_sizes'] for entry in gui_audit)):
        raise RuntimeError('Unexpected used-symbol/vtable audit result')

    package_name = package.relative_to(ROOT).as_posix()
    framework_name = framework_package.relative_to(ROOT).as_posix()
    manifest_hash = hashlib.sha256((package / 'manifest.json').read_bytes()).hexdigest()
    evidence = {'native_commit': commits['frameworks/native'],
                'framework_commit': commits['frameworks/base'], 'art_commit': commits['art'],
                'patch': 'patches/0032-pico-surface-monitor.patch', 'package': package_name,
                'manifest_sha256': manifest_hash, 'framework_package': framework_name,
                'abis': abis, 'monitor_abi_evidence': 'validation/surface-monitor-abi.json',
                'remaining_used_arm64_gui_symbols': 0, 'unresolved_factory_prefix_bytes': 40,
                'system_partitions_modified': False, 'fingerprint_unchanged': True,
                'boot_completed': True, 'temporary_files_removed': True, 'properties_unchanged': True,
                'full_graphics_abi_proven': False, 'real_display_frequency_qualified': False,
                'real_remote_binder_qualified': False, 'hardware_vr_qualified': False,
                'scope': 'Source/factory process-local monitor state, parcel, service lookup and file traces; '
                         'mock producer/layer integration; compiled Source Java/JNI/ART/Bionic; '
                         'valid/default configuration inputs; no global graphics or VR replacement'}
    current_path = ROOT / 'validation/native-runtime-current.json'
    current = read(current_path)
    current.update(native_commit=commits['frameworks/native'], package=package_name,
                   manifest_sha256=manifest_hash, native_tests_total=sum(x['native_gtests_passed'] for x in abis.values()),
                   evidence_packages=[package_name, framework_name],
                   surface_monitor_evidence='validation/surface-monitor-port.json',
                   monitored_producer_tests_per_abi={'arm64': 5, 'arm': 5},
                   remaining_used_arm64_gui_symbols=0,
                   compiled_framework_commit=commits['frameworks/base'], art_commit=commits['art'],
                   framework_boot_image_evidence='validation/framework-boot-image.json',
                   scope=evidence['scope'])
    write(ROOT / 'validation/libgui-abi.json', gui_audit)
    write(ROOT / 'validation/surface-monitor-port.json', evidence)
    write(current_path, current)
    print('Recorded 378 native gtests, 148 monitor snapshots and 24 Source Java/JNI/ART fixtures; 0 used ARM64 GUI imports missing')


if __name__ == '__main__':
    main()
