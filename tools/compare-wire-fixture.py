"""Run a generated wire-format fixture on the factory framework and compare with the Source run.

Generic form of compare-pico-api-runtime.py for fixtures produced by
generate-pico-api-fixture.py (e.g. QcomApiFixture/"qcom-api"). The Source run must have been
recorded by run-framework-runtime.py for the same probe JAR. Writes the given JSON report.
"""
import argparse
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('vr_policy', ROOT / 'tools/compare-vr-policy.py')
vr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vr)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--adb', required=True)
    parser.add_argument('--serial', required=True)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--fixture', required=True, help='class in org.picomisu.runtime')
    parser.add_argument('--prefix', required=True, help='line prefix printed by the fixture')
    parser.add_argument('--tables', type=Path, help='transaction tables used to generate the fixture')
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads((args.package / 'manifest.json').read_text())
    probe = args.package / 'probe.jar'
    source_report = json.loads((ROOT / 'reports/framework-bridge/framework-boot-image-test.json').read_text())
    if source_report['source_sha256'] != manifest['files'] or manifest['files']['probe.jar'] != vr.digest(probe):
        raise RuntimeError('Source runtime report refers to different artifacts')
    source = {abi: vr.policy_lines(source_report['results'][abi]['output'], args.prefix) for abi in ('arm64', 'arm')}
    expected = len(source['arm64'])
    factory = vr.run_factory(args, probe, args.fixture, args.prefix, expected)
    comparison, unexpected = {}, []
    for abi in ('arm64', 'arm'):
        f, s = factory['results'][abi]['lines'], source[abi]
        mismatched = sorted(k for k in set(f) | set(s) if f.get(k) != s.get(k))
        unexpected += [abi + ':' + k for k in mismatched]
        comparison[abi] = {'scenarios': len(s), 'matched': len(s) - len(mismatched),
                           'mismatched': {k: {'factory': f.get(k), 'source': s.get(k)} for k in mismatched}}
    config = json.loads((ROOT / 'config/aosp-patches.json').read_text())
    report = {'fixture': args.fixture, 'prefix': args.prefix,
              'component_commits': {p['path']: p['local_commit'] for p in config['projects']},
              'factory_framework_sha256': vr.FACTORY_JAR_SHA256,
              'source_framework_sha256': manifest['files']['system/framework/framework.jar'],
              'probe_sha256': manifest['files']['probe.jar'],
              'package': str(args.package.resolve().relative_to(ROOT)).replace('\\', '/'),
              'interfaces': ({k: {'methods': v['methods'], 'oneway': v['oneway']}
                              for k, v in json.loads(args.tables.read_text()).items()} if args.tables else None),
              'comparison': comparison, 'unexpected_differences': unexpected,
              'factory_run': {k: v for k, v in factory.items() if k != 'results'},
              'system_partitions_modified': False}
    args.report.write_text(json.dumps(report, indent=1, ensure_ascii=False) + '\n')
    print(json.dumps({abi: {k: v for k, v in c.items() if k != 'mismatched'} for abi, c in comparison.items()}))
    print(json.dumps({'unexpected': unexpected[:20]}))
    if unexpected or not all(factory[k] for k in ('fingerprint_unchanged', 'boot_completed', 'temporary_files_removed')):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
