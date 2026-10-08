"""Qualify the reconstructed PICO API against the factory 5.13.7 framework.

1. Runs org.picomisu.runtime.PicoApiFixture from the Source probe JAR on the headset under
   the installed factory framework (app_process as shell, both ABIs, temporary directory)
   and compares its "pico-api" lines (transaction codes, flags, data/reply parcel bytes,
   unmarshalled arguments, parcelable bytes) with the Source run recorded by
   run-framework-runtime.py for the same probe JAR.
2. Records the static class comparisons produced by compare-pico-api.py (--hiddenapi --json)
   for the Source framework.jar and services.jar.
Writes validation/pico-api-port.json. No system partition, setting or service is changed.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('vr_policy', ROOT / 'tools/compare-vr-policy.py')
vr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vr)
REPORT = ROOT / 'validation/pico-api-port.json'
# Class differences that cannot be removed at source level.
STATIC_EXPECTED = {
    'Landroid/pico/utils/Features;': 'disableSystemAlert inlines com.android.internal.R.id.spacer, whose '
                                     'value depends on the framework-res resource table layout',
    'Landroid/pico/utils/PicoUtilsDeprecated;': 'not needed by any factory consumer; not ported',
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--adb', required=True)
    parser.add_argument('--serial', required=True)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--framework-compare', type=Path, required=True)
    parser.add_argument('--services-compare', type=Path, required=True)
    parser.add_argument('--reconstruction', type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads((args.package / 'manifest.json').read_text())
    probe = args.package / 'probe.jar'
    source_report = json.loads((ROOT / 'reports/framework-bridge/framework-boot-image-test.json').read_text())
    if source_report['source_sha256'] != manifest['files'] or manifest['files']['probe.jar'] != vr.digest(probe):
        raise RuntimeError('Source runtime report refers to different artifacts')
    source_lines = {abi: vr.policy_lines(source_report['results'][abi]['output'], 'pico-api')
                    for abi in ('arm64', 'arm')}
    expected = len(source_lines['arm64'])
    factory = vr.run_factory(args, probe, 'PicoApiFixture', 'pico-api', expected)
    comparison, unexpected = {}, []
    for abi in ('arm64', 'arm'):
        f, s = factory['results'][abi]['lines'], source_lines[abi]
        mismatched = sorted(k for k in set(f) | set(s) if f.get(k) != s.get(k))
        unexpected += [abi + ':' + k for k in mismatched]
        comparison[abi] = {'scenarios': len(s), 'matched': len(s) - len(mismatched),
                           'mismatched': {k: {'factory': f.get(k), 'source': s.get(k)} for k in mismatched}}
    static = {}
    for jar, path in (('framework.jar', args.framework_compare), ('services.jar', args.services_compare)):
        data = json.loads(path.read_text())
        rows = [r for r in data['rows'] if r['differences']]
        static[jar] = {'classes': data['classes'], 'identical': data['identical'],
                       'different': {r['class']: STATIC_EXPECTED.get(r['class'], r['differences'])
                                     for r in rows}}
    unexplained = [c for s in static.values() for c, v in s['different'].items() if not isinstance(v, str)]
    config = json.loads((ROOT / 'config/aosp-patches.json').read_text())
    commits = {p['path']: p['local_commit'] for p in config['projects']}
    reconstruction = json.loads(args.reconstruction.read_text())
    report = {
        'framework_commit': commits['frameworks/base'],
        'soong_commit': commits.get('build/soong'),
        'patches': ['patches/0039-soong-pico-hiddenapi-whitelist.patch',
                    'patches/0040-pico-permissions.patch',
                    'patches/0041-qcom-wifiinfo-generation.patch',
                    'patches/0042-smartisan-applicationinfo-smtbase.patch',
                    'patches/0043-pico-aidl-interfaces-clients.patch',
                    'patches/0044-pico-features-utils-whitelist.patch',
                    'patches/0045-pico-api-runtime-fixture.patch'],
        'factory_framework_sha256': vr.FACTORY_JAR_SHA256,
        'source_framework_sha256': manifest['files']['system/framework/framework.jar'],
        'probe_sha256': manifest['files']['probe.jar'],
        'package': str(args.package.resolve().relative_to(ROOT)).replace('\\', '/'),
        'aidl_interfaces': {k: {'jar': v['jar'], 'methods': v['methods'], 'oneway': v['oneway'],
                                'transactions': v['transactions']} for k, v in reconstruction.items()},
        'runtime_comparison': comparison,
        'runtime_unexpected_differences': unexpected,
        'factory_run': {k: v for k, v in factory.items() if k != 'results'},
        'static_comparison': static,
        'static_unexplained': unexplained,
        'hidden_api': 'factory flags reproduced: com.pxr.net via hiddenapi-greylist-packages, '
                      'whitelisted PICO members and Manifest.permission fields via config/hiddenapi-whitelist.txt',
        'not_ported': ['server implementations (PxrNotificationService, PvrManagerService, IApiLayer, '
                       'IPxrNetworkManager and other services live in factory sys-JARs/apps)',
                       'com.pxr.bluetooth adapter/profile/device-manager classes (no consumers)',
                       'android.pico.ns (no consumers)', 'PicoUtilsDeprecated (no consumers)',
                       'ApplicationInfoMonitorEx', 'framework-res translations of new permission strings'],
        'hardware_qualified': False,
        'system_partitions_modified': False,
    }
    REPORT.write_text(json.dumps(report, indent=1, ensure_ascii=False) + '\n')
    print(json.dumps({abi: {k: v for k, v in c.items() if k != 'mismatched'} for abi, c in comparison.items()}))
    print(json.dumps({'unexpected': unexpected[:20], 'static_unexplained': unexplained}))
    if unexpected or unexplained or not all(factory[k] for k in ('fingerprint_unchanged', 'boot_completed',
                                                                  'temporary_files_removed')):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
