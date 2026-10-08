"""Compare the Source VR activity policy chain with the factory 5.13.7 framework.

1. Runs the shared org.picomisu.runtime.VrPolicyFixture from the Source probe JAR on the
   headset under the installed factory framework (plain app_process as the shell UID,
   temporary private directory, both ABIs) and compares its "vr-policy" lines with the
   Source run recorded by run-framework-runtime.py for the same probe JAR.
2. Compares the invoked methods and accessed fields of the ported factory methods in the
   authenticated factory framework.jar and the packaged Source framework.jar.

No system partition, setting or service is changed; the fixture uses local stubs.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shlex
import subprocess
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[1]
FACTORY_JAR = ROOT / 'reports/device/static/system__framework__framework.jar'
FACTORY_JAR_SHA256 = 'ea5998f856b692f8cd112b26d65e6a4f371dca825348bf5b247eabc56274ed0e'
REPORT = ROOT / 'validation/vr-policy-port.json'
POLICY_LINES = 78
# Known factory failures that the Source port handles instead of throwing.
EXPECTED_DIFFERENCES = {
    'thread.no-activity': ('exception:java.lang.NullPointerException', 'true',
                           'Record without an Activity: factory dereferences it, Source skips it'),
    'viewroot.no-activity-thread': ('exception:java.lang.NullPointerException', 'false',
                                    'No ActivityThread: factory dereferences it, Source renders normally'),
}
IGNORED_OWNERS = ('Ljava/lang/StringBuilder;', 'Landroid/util/Slog;', 'Landroid/util/Log;')
STATIC_TARGETS = [
    ('Landroid/view/ViewRootImpl;', 'drawSoftware(Landroid/view/Surface;Landroid/view/View$AttachInfo;'
                                    'IIZLandroid/graphics/Rect;Landroid/graphics/Rect;)Z'),
    ('Landroid/view/ExtViewRootImplImpl;', 'isSkipDrawVrActivity()Z'),
    ('Landroid/view/ExtViewRootImplImpl;', 'canSkipDraw()Z'),
    ('Landroid/app/ExtActivityThreadImpl;', 'isActivityForceRender(Landroid/view/ViewRootImpl;)Z'),
    ('Landroid/content/pm/ExtPackageParserImpl;', 'parseVrFlags(Landroid/content/pm/PackageParser$Package;)'
                                                  'Landroid/content/pm/PackageParser$Package;'),
    ('Landroid/content/pm/PackageParser;', 'parsePackage(Ljava/io/File;IZ)Landroid/content/pm/PackageParser$Package;'),
    ('Landroid/pico/utils/PicoSystemConfig;', 'readPicoConfig(I)V'),
    ('Landroid/pico/utils/PicoSystemConfig;', 'readPicoConfigFromXml(Ljava/io/File;I)V'),
]
STATIC_CLASSES = ['Landroid/content/pm/ExtActivityInfoImpl;', 'Landroid/content/pm/ExtApplicationInfoImpl;']
# Differences that follow from deliberate, documented scope limits.
STATIC_EXPECTED = {
    'Landroid/content/pm/PackageParser;->parsePackage': {
        'factory_only': {'Landroid/content/pm/PackageParserSmtBase;->verifyLibraryFiles('
                         'Landroid/content/pm/PackageParser$Package;)V'},
        'reason': 'Smartisan library-file verification is outside the VR chain'},
    'Landroid/view/ExtViewRootImplImpl;->canSkipDraw': {
        'source_only': set(), 'factory_only': set(),
        'reason': 'Source adds a null check for ActivityThread.currentActivityThread()'},
    'Landroid/app/ExtActivityThreadImpl;->isActivityForceRender': {
        'reason': 'Source adds a null check for ActivityClientRecord.activity'},
}


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'tools' / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def policy_lines(output, prefix='vr-policy'):
    return dict(re.findall(r'^' + prefix + r' (\S+?)=(.*)$', output, re.MULTILINE))


def run_factory(args, probe, fixture='VrPolicyFixture', prefix='vr-policy', expected=POLICY_LINES):
    state = json.loads((ROOT / 'outputs/vr-preview-01-installation/state.json').read_text())

    def adb(*arguments, timeout=60, check=True):
        result = subprocess.run([args.adb, '-s', args.serial, *arguments], capture_output=True,
                                text=True, encoding='utf-8', errors='replace', timeout=timeout)
        output = (result.stdout + result.stderr).strip().replace(args.serial, '<device>')
        if check and result.returncode:
            raise RuntimeError(output)
        return result.returncode, output

    identity = subprocess.run([args.adb, '-s', args.serial, 'shell', 'getprop ro.serialno'],
                              capture_output=True, text=True, timeout=30).stdout.strip()
    if hashlib.sha256(identity.encode()).hexdigest() != state['device_serial_sha256']:
        raise RuntimeError('Unexpected hardware identity')
    if adb('shell', 'getprop ro.product.device')[1] != 'PICOA8110':
        raise RuntimeError('Unexpected model')
    if adb('shell', 'id -u')[1] != '2000':
        raise RuntimeError('Factory fixture must run as the ordinary shell UID')
    installed = adb('shell', 'toybox sha256sum /system/framework/framework.jar')[1].split()[0]
    if installed != FACTORY_JAR_SHA256:
        raise RuntimeError('Installed framework.jar is not the authenticated factory JAR')
    fingerprint = adb('shell', 'getprop ro.build.fingerprint')[1]
    remote = '/data/local/tmp/picomisu-vr-policy-' + uuid.uuid4().hex
    result = {'installed_framework_sha256': installed, 'results': {}}
    try:
        adb('shell', 'mkdir ' + remote)
        adb('push', str(probe), remote + '/probe.jar', timeout=120)
        if adb('shell', 'toybox sha256sum ' + remote + '/probe.jar')[1].split()[0] != digest(probe):
            raise RuntimeError('Uploaded probe differs')
        for abi, executable in [('arm64', '/system/bin/app_process64'), ('arm', '/system/bin/app_process32')]:
            child = ('CLASSPATH=' + remote + '/probe.jar exec ' + executable
                     + ' -Xhidden-api-policy:disabled /system/bin org.picomisu.runtime.' + fixture)
            code, output = adb('shell', 'toybox timeout 300 sh -c ' + shlex.quote(child),
                               timeout=360, check=False)
            lines = policy_lines(output, prefix)
            result['results'][abi] = {'exit_code': code, 'lines': lines,
                                      'complete': '%s-fixture lines=%d' % (prefix, expected) in output}
            if code or not result['results'][abi]['complete']:
                result['results'][abi]['output'] = output[-4000:]
                raise RuntimeError('Factory fixture failed for ' + abi + '\n' + output[-4000:])
            print(abi + ': factory fixture produced %d lines' % len(lines), flush=True)
    finally:
        result['fingerprint_unchanged'] = adb('shell', 'getprop ro.build.fingerprint')[1] == fingerprint
        result['boot_completed'] = adb('shell', 'getprop sys.boot_completed')[1] == '1'
        if not re.fullmatch(r'/data/local/tmp/picomisu-vr-policy-[0-9a-f]{32}', remote):
            raise RuntimeError('Invalid cleanup directory')
        adb('shell', 'rm -rf ' + remote)
        result['temporary_files_removed'] = adb('shell', 'test ! -e ' + remote, check=False)[0] == 0
    return result


def method_refs(scan, jar, targets, classes):
    """Invoked methods (resolved to declaring class where defined in the JAR) and fields."""
    with zipfile.ZipFile(jar) as archive:
        blobs = [archive.read(n) for n in sorted(archive.namelist()) if re.fullmatch(r'classes\d*\.dex', n)]
    wanted = {owner + '->' + signature for owner, signature in targets}
    found = {}
    for blob in blobs:
        dex = scan.Dex(blob)
        for clazz, _, _, _, _, methods in dex.classes():
            for signature, (_, code) in methods.items():
                key = clazz + '->' + signature
                if (key not in wanted and clazz not in classes) or not code:
                    continue
                invoked, fields, _, strings, _ = dex.code_refs(code)
                calls = {o + '->' + s for o, s in (dex.methods[i] for i in invoked)
                         if not o.startswith(IGNORED_OWNERS)}
                found[key] = {'calls': sorted(calls),
                              'fields': sorted(o + '->' + s for o, s in (dex.fields[i] for i in fields)),
                              'strings': sorted(dex.strings[i] for i in strings)}
    return found


def static_comparison(source_jar):
    scan = load('pico_scan', 'scan-api-consumers.py')
    targets = STATIC_TARGETS
    factory = method_refs(scan, FACTORY_JAR, targets, STATIC_CLASSES)
    source = method_refs(scan, source_jar, targets, STATIC_CLASSES)
    rows = []
    for key in sorted(set(factory) | set(source)):
        short = key.split('(')[0]
        f, s = factory.get(key), source.get(key)
        row = {'method': key, 'in_factory': f is not None, 'in_source': s is not None}
        if f and s:
            # Source caches getExt() results; compare sets without repetitions.
            row['factory_only_calls'] = sorted(set(f['calls']) - set(s['calls']))
            row['source_only_calls'] = sorted(set(s['calls']) - set(f['calls']))
            row['factory_only_fields'] = sorted(set(f['fields']) - set(s['fields']))
            row['source_only_fields'] = sorted(set(s['fields']) - set(f['fields']))
            row['factory_only_strings'] = sorted(set(f['strings']) - set(s['strings']))
            row['source_only_strings'] = sorted(set(s['strings']) - set(f['strings']))
            expected = STATIC_EXPECTED.get(short, {})
            unexplained = (set(row['factory_only_calls']) - expected.get('factory_only', set())
                           or set(row['source_only_calls']) - expected.get('source_only', set()))
            row['calls_match_or_explained'] = not unexplained
            if expected.get('reason'):
                row['note'] = expected['reason']
        rows.append(row)
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--adb', required=True)
    parser.add_argument('--serial', required=True)
    parser.add_argument('--package', type=Path, required=True)
    args = parser.parse_args()
    if digest(FACTORY_JAR) != FACTORY_JAR_SHA256:
        raise RuntimeError('Factory framework.jar copy changed')
    manifest = json.loads((args.package / 'manifest.json').read_text())
    probe = args.package / 'probe.jar'
    source_report = json.loads((ROOT / 'reports/framework-bridge/framework-boot-image-test.json').read_text())
    if source_report['source_sha256'] != manifest['files']:
        raise RuntimeError('Source runtime report refers to different artifacts')
    if manifest['files']['probe.jar'] != digest(probe):
        raise RuntimeError('Probe JAR changed after the Source run')
    factory = run_factory(args, probe)
    comparison = {}
    unexpected = []
    for abi in ['arm64', 'arm']:
        source_lines = policy_lines(source_report['results'][abi]['output'])
        factory_lines = factory['results'][abi]['lines']
        if len(source_lines) != POLICY_LINES or len(factory_lines) != POLICY_LINES:
            raise RuntimeError('Incomplete policy output for ' + abi)
        rows = {}
        for key in sorted(set(source_lines) | set(factory_lines)):
            f, s = factory_lines.get(key), source_lines.get(key)
            if f == s:
                rows[key] = {'value': s, 'match': True}
            elif key in EXPECTED_DIFFERENCES and (f, s) == EXPECTED_DIFFERENCES[key][:2]:
                rows[key] = {'factory': f, 'source': s, 'match': False,
                             'expected_difference': EXPECTED_DIFFERENCES[key][2]}
            else:
                rows[key] = {'factory': f, 'source': s, 'match': False}
                unexpected.append(abi + ':' + key)
        comparison[abi] = {'scenarios': rows,
                           'matched': sum(1 for r in rows.values() if r['match']),
                           'expected_differences': sum(1 for r in rows.values()
                                                       if 'expected_difference' in r)}
    static = static_comparison(args.package / 'system/framework/framework.jar')
    config = json.loads((ROOT / 'config/aosp-patches.json').read_text())
    commits = {p['path']: p['local_commit'] for p in config['projects']}
    report = {
        'framework_commit': commits['frameworks/base'],
        'patches': ['patches/0034-pico-package-info-vr-extensions.patch',
                    'patches/0035-pico-package-parser-vr-metadata.patch',
                    'patches/0036-pico-activity-thread-force-render.patch',
                    'patches/0037-pico-view-root-vr-skip-draw.patch',
                    'patches/0038-vr-policy-runtime-fixtures.patch',
                    'patches/0058-pico-vr-chain-hooks.patch'],
        'factory_framework_sha256': FACTORY_JAR_SHA256,
        'source_framework_sha256': manifest['files']['system/framework/framework.jar'],
        'probe_sha256': manifest['files']['probe.jar'],
        'package': str(args.package.resolve().relative_to(ROOT)).replace('\\', '/'),
        'policy_scenarios_per_abi': POLICY_LINES,
        'factory_run': {k: v for k, v in factory.items() if k != 'results'},
        'comparison': comparison,
        'unexpected_differences': unexpected,
        'static_comparison': static,
        'static_unexplained': [r['method'] for r in static
                               if r.get('calls_match_or_explained') is False
                               or r['in_factory'] != r['in_source']],
        'ported_subset': {
            'IExtActivityInfo': 'complete factory interface',
            'IExtApplicationInfo': 'complete factory interface',
            'IExtPackageParser': 'complete factory interface (parseVrFlags, parseBaseApkCommon)',
            'ExtPackageParserUtils': 'complete (2D virtual-display configuration)',
            'PicoSystemConfig': 'complete',
            'IExtActivityThread': 'complete factory interface with ActivityThread hooks',
            'IExtViewRootImpl': 'complete factory interface with ViewRootImpl/ThreadedRenderer hooks and android.pico.ns',
        },
        'not_ported': ['ActivityInfoSmtBase Parcel data preceding the PICO extension',
                       'factory ExtImplFactory reflection; Source creates implementations directly'],
        'hardware_vr_qualified': False,
        'system_partitions_modified': False,
    }
    if unexpected:
        report['error'] = 'Unexpected factory/Source differences'
    REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps({abi: {k: v for k, v in c.items() if k != 'scenarios'} for abi, c in comparison.items()}))
    print(json.dumps({'unexpected': unexpected, 'static_unexplained': report['static_unexplained']}))
    if unexpected or not all(factory[k] for k in ('fingerprint_unchanged', 'boot_completed',
                                                  'temporary_files_removed')):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
