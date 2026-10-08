"""Stage a factory-compatible VR preview with an explicit AOSP component allowlist.

This is a bring-up image, not a completed source port of the PICO framework.
Factory framework/APEX/graphics/platform APKs form one preserved binary layer.
No headset operations are performed here. Use --stage after the AOSP build.
"""
import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import zipfile

import importlib.util as _util
_spec = _util.spec_from_file_location('picomisu_env', Path(__file__).with_name('picomisu_env.py'))
env = _util.module_from_spec(_spec)
_spec.loader.exec_module(env)
ROOT = env.ROOT
VOLUME = env.VOLUME
PROJECT = env.WORK
SOURCE = env.SOURCE
# PICO_OUT_TREE selects another out dir of the same tree (e.g. caf-10-user for the user variant).
OUT = env.OUT
PRODUCT = OUT / 'target/product/PICOA8110'
# Host tools always come from the tree's main out dir (a variant out dir builds only the image).
HOST_OUT = env.HOST_OUT
HOST = HOST_OUT / 'bin'
STAGE = PROJECT / 'staging/vr-preview-01'
TREE = STAGE / 'root'
REPORTS = env.REPORTS / 'vr-integration'


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def guard_volume():
    env.guard_volume()


def read_symbols(path):
    output = subprocess.check_output(['readelf', '--dyn-syms', '--wide', str(path)], text=True)
    defined, undefined, weak = set(), set(), set()
    for line in output.splitlines():
        parts = line.split()
        if len(parts) < 8 or not parts[0].rstrip(':').isdigit():
            continue
        binding, index, name = parts[4], parts[6], parts[7].replace('@@', '@')
        if index == 'UND':
            (weak if binding == 'WEAK' else undefined).add(name)
        elif binding in ('GLOBAL', 'WEAK'):
            defined.add(name)
            defined.add(name.split('@')[0])
    return defined, undefined, weak


def needed(path):
    output = subprocess.check_output(['readelf', '-d', str(path)], text=True)
    return re.findall(r'\(NEEDED\).*?\[([^\]]+)\]', output)


def validate_elf(path, rules, factory, graph, factory_tree):
    if path.read_bytes()[:5] != b'\x7fELF\x02':
        raise RuntimeError('Expected an ARM64 ELF executable: ' + str(path))
    header = subprocess.check_output(['readelf', '-h', str(path)], text=True)
    if 'AArch64' not in header:
        raise RuntimeError('Wrong machine type: ' + str(path))
    allowed = set(rules['allowlisted_executable_shared_libraries'])
    requested = needed(path)
    if set(requested) - allowed:
        raise RuntimeError('Unreviewed executable dependencies: ' + str(set(requested) - allowed))
    providers, queue = {}, list(requested)
    while queue:
        name = queue.pop()
        if name in providers:
            continue
        bionic = '/apex/com.android.runtime/lib64/bionic/' + name
        system = '/system/lib64/' + name
        if name in ('libc.so', 'libdl.so', 'libm.so'):
            location = bionic
        elif name == 'ld-android.so':
            location = '/apex/com.android.runtime/bin/linker64'
        elif system in factory:
            location = system
        else:
            raise RuntimeError('Expected factory provider is not in the checked graph: ' + name)
        entry = graph['elf_files'].get(location)
        if entry is None and location in factory and factory[location]['kind'] == 'file':
            entry = {'analysis_copy': str(Path(factory_tree) / location.lstrip('/')),
                     'sha256': factory[location]['sha256']}
        if not entry:
            raise RuntimeError('Missing authenticated provider: ' + location)
        provider = Path(entry['analysis_copy'])
        if digest(provider) != entry['sha256']:
            raise RuntimeError('Factory ELF cache changed: ' + location)
        if location.startswith('/system/') and factory[location].get('sha256') != entry['sha256']:
            raise RuntimeError('Factory library differs from extracted image: ' + location)
        providers[name] = {'path': location, 'file': str(provider), 'sha256': entry['sha256']}
        queue.extend(needed(provider))
    for location in rules['additional_executable_symbol_providers']:
        entry = graph['elf_files'][location]
        provider = Path(entry['analysis_copy'])
        if digest(provider) != entry['sha256']:
            raise RuntimeError('Factory symbol provider changed')
        providers[location] = {'path': location, 'file': str(provider), 'sha256': entry['sha256']}
    exports = set()
    for provider in providers.values():
        exports.update(read_symbols(Path(provider['file']))[0])
    _, required, weak = read_symbols(path)
    missing = required - exports
    if missing:
        raise RuntimeError('Unresolved strong ELF imports in preserved factory runtime: ' + str(sorted(missing)))
    return {'direct_needed': requested, 'providers': providers, 'strong_imports': len(required),
            'unresolved_strong_imports': [], 'unresolved_weak_imports': sorted(weak - exports),
            'runtime_tested': False, 'class_layout_compatibility_proven': False}


def apk_identity(path):
    manifest = subprocess.check_output(
        [str(HOST / 'aapt2'), 'dump', 'xmltree', str(path), '--file', 'AndroidManifest.xml'], text=True)
    package = re.search(r'\bA: package="([^"]+)"', manifest)
    uid = re.search(r':sharedUserId\([^)]*\)="([^"]+)"', manifest)
    if not package:
        raise RuntimeError('Missing APK package name: ' + str(path))
    signer_jar = HOST_OUT / 'framework/apksigner.jar'
    java = SOURCE / 'prebuilts/jdk/jdk9/linux-x86/bin/java'
    verified = subprocess.run([str(java), '-jar', str(signer_jar), 'verify', '--verbose', '--print-certs',
                               '--min-sdk-version', '29', str(path)], check=True, capture_output=True, text=True)
    certificates = re.findall(r'Signer #\d+ certificate SHA-256 digest: ([0-9a-f]+)', verified.stdout)
    if not certificates:
        raise RuntimeError('APK has no verified signer')
    return {'package': package.group(1), 'shared_uid': uid.group(1) if uid else None,
            'signer_sha256': certificates, 'signature_verified': True}


def update_properties(path, changes):
    text = path.read_text()
    for key, value in changes.items():
        pattern = r'^' + re.escape(key) + r'=.*$'
        if re.search(pattern, text, re.MULTILINE):
            text = re.sub(pattern, lambda match: key + '=' + value, text, flags=re.MULTILINE)
        else:
            text += '\n' + key + '=' + value + '\n'
    path.write_text(text)


def stage():
    rules = json.loads((ROOT / 'device/pico/PICOA8110/vr-layer.json').read_text())
    extracted = json.loads((REPORTS / 'factory-system.json').read_text())
    if not extracted['complete']:
        raise RuntimeError('Factory extraction did not complete')
    factory = {entry['path']: entry for entry in extracted['entries']}
    graph = json.loads((ROOT / 'reports/vr-dependencies/factory-graph.json').read_text())
    if TREE.exists():
        raise RuntimeError('Preserve existing staging tree; validate it instead of overwriting')
    additions, replacements = {}, {}
    apk_report = json.loads((REPORTS / 'factory-apks.json').read_text())
    additional = json.loads((REPORTS / 'additional-factory-apks.json').read_text())
    if not apk_report['complete'] or not additional['complete'] or apk_report['factory_image_sha256'] != extracted['image_sha256']:
        raise RuntimeError('Factory APK verification is incomplete or stale')
    packages = [dict(package, origin='factory') for package in apk_report['packages']] + additional['packages']
    factory_packages = {package['package'] for package in packages}
    for name in rules['aosp_executable_allowlist']:
        source = PRODUCT / 'system/bin' / name
        target = '/system/bin/' + name
        if factory[target]['kind'] != 'file' or source.is_symlink():
            raise RuntimeError('Unexpected executable inode type: ' + name)
        validation = validate_elf(source, rules, factory, graph, extracted['tree'])
        destination = rules['aosp_executable_destination'] + '/' + name
        additions[destination] = {'source': str(source), 'sha256': digest(source),
                                  'metadata_from': target, 'type': 'executable', 'validation': validation}
    for name in rules['aosp_boot_executable_allowlist']:
        source = PRODUCT / 'system/bin' / name
        target = '/system/bin/' + name
        if name != 'servicemanager' or factory[target]['kind'] != 'file':
            raise RuntimeError('Unreviewed boot executable replacement: ' + name)
        validation = validate_elf(source, rules, factory, graph, extracted['tree'])
        source_interp = subprocess.check_output(['readelf', '-l', str(source)], text=True)
        factory_file = Path(extracted['tree']) / target.lstrip('/')
        factory_interp = subprocess.check_output(['readelf', '-l', str(factory_file)], text=True)
        pattern = r'\[Requesting program interpreter: ([^\]]+)\]'
        if re.findall(pattern, source_interp) != re.findall(pattern, factory_interp):
            raise RuntimeError('Boot executable interpreter differs from factory')
        validation['interpreter_matches_factory'] = True
        validation['service_registration_and_vr_on_device_tested'] = False
        replacements[target] = {'source': str(source), 'sha256': digest(source),
                                'factory_sha256': factory[target]['sha256'], 'validation': validation}
    for apk in rules['aosp_apk_allowlist']:
        candidates = list(PRODUCT.glob(f'*/app/{apk["module"]}/{apk["module"]}.apk'))
        if len(candidates) != 1:
            raise RuntimeError('Expected one built AOSP APK: ' + apk['module'])
        source = candidates[0]
        identity = apk_identity(source)
        if identity['package'] != apk['package'] or identity['shared_uid'] or identity['package'] in factory_packages:
            raise RuntimeError('AOSP APK would conflict with the factory platform: ' + str(identity))
        with zipfile.ZipFile(source) as archive:
            if 'classes.dex' not in archive.namelist():
                raise RuntimeError('AOSP APK must retain DEX; its source preopt cannot be used with factory ART')
        target = f'/system/app/Aosp{apk["module"]}/{apk["module"]}.apk'
        additions[target] = {'source': str(source), 'sha256': digest(source), 'identity': identity, 'type': 'apk'}
        packages.append(dict(identity, path=target, origin='aosp', sha256=digest(source)))
    platform = next(package for package in packages if package['package'] == 'android')
    for package in packages:
        if package['shared_uid'] == 'android.uid.system' and package['signer_sha256'] != platform['signer_sha256']:
            raise RuntimeError('Inconsistent platform signer: ' + package['path'])
    STAGE.mkdir(parents=True, exist_ok=True)
    (STAGE / 'owner.json').write_text(json.dumps({'tool': str(Path(__file__)), 'prototype': 'vr-preview-01'}) + '\n')
    shutil.copytree(extracted['tree'], TREE, symlinks=True)
    final = {key: dict(value) for key, value in factory.items()}
    for target, entry in replacements.items():
        shutil.copyfile(entry['source'], TREE / target.lstrip('/'))
        final[target]['sha256'] = entry['sha256']
        final[target]['bytes'] = Path(entry['source']).stat().st_size
        final[target]['origin'] = 'aosp'
    for target, entry in additions.items():
        folder = '/' + str(Path(target).parent).lstrip('/')
        destination = TREE / target.lstrip('/')
        destination.parent.mkdir(exist_ok=True)
        shutil.copyfile(entry['source'], destination)
        for relative, kind, mode in [(folder, 'directory', '0755'), (target, 'file', '0644')]:
            final[relative] = {'path': relative, 'kind': kind, 'uid': 0, 'gid': 0, 'mode': mode,
                               'bytes': destination.stat().st_size if kind == 'file' else 0,
                               'selinux': 'u:object_r:system_file:s0', 'capabilities': 0,
                               'xattrs': {'security.selinux': base64.b64encode(b'u:object_r:system_file:s0\0').decode()},
                               'origin': 'aosp'}
            if kind == 'file':
                final[relative]['sha256'] = entry['sha256']
                if entry['type'] == 'executable':
                    original = factory[entry['metadata_from']]
                    for key in ['uid', 'gid', 'mode', 'selinux', 'capabilities', 'xattrs']:
                        final[relative][key] = original[key]
    source_props = dict(line.split('=', 1) for line in (PRODUCT / 'system/build.prop').read_text().splitlines()
                        if '=' in line and not line.startswith('#'))
    changes = {'ro.build.display.id': 'PICO AOSP VR preview 01',
               'ro.build.id': 'VR_PREVIEW_01', 'ro.system.build.id': 'VR_PREVIEW_01',
               'ro.build.fingerprint': 'Pico/Phoenix_ovs/PICOA8110:10/VR_PREVIEW_01/2026092801:user/dev-keys',
               'ro.system.build.fingerprint': 'Pico/Phoenix_ovs/PICOA8110:10/VR_PREVIEW_01/2026092801:user/dev-keys',
               'ro.pico.aosp.preview': '1', 'ro.pico.aosp.tag': rules['aosp_tag'],
               'ro.pico.aosp.factory_vr': '5.13.7-SEKO-b9665',
               'ro.pico.aosp.build.id': 'PICO_AOSP_10_BRINGUP_2026092801',
               'ro.pico.aosp.build.utc': '1790603988',
               'ro.pico.aosp.base_spl': source_props['ro.build.version.security_patch']}
    update_properties(TREE / 'system/build.prop', changes)
    properties = '/system/build.prop'
    final[properties]['sha256'] = digest(TREE / properties.lstrip('/'))
    final[properties]['bytes'] = (TREE / properties.lstrip('/')).stat().st_size
    final[properties]['origin'] = 'generated-preview-properties'
    classpaths = json.loads((ROOT / 'reports/device/classpaths.json').read_text())
    environment = (TREE / 'init.environ.rc').read_text()
    for name, paths in classpaths.items():
        match = re.search(r'export ' + name + r' (\S+)', environment)
        if not match or match.group(1).split(':') != paths:
            raise RuntimeError('Factory classpath changed: ' + name)
    for name in rules['forbidden_factory_absent_blobs']:
        if any(Path(path).name == name for path in final):
            raise RuntimeError('Untrusted live-process blob must not enter factory layer: ' + name)
    for entry in final.values():
        entry.setdefault('origin', 'factory')
    report = {'created_at': datetime.now(timezone.utc).isoformat(), 'complete': True,
              'kind': 'hybrid-prototype', 'tree': str(TREE), 'rules': rules,
              'factory_image_sha256': extracted['image_sha256'],
              'aosp_replacements': replacements, 'aosp_additions': additions,
              'packages': packages, 'preview_properties': changes,
              'factory_security_and_ota_timestamp_metadata_preserved': True,
              'aosp_input_security_patch': source_props['ro.build.version.security_patch'],
              'hybrid_security_patch_coverage_verified': False,
              'entries': sorted(final.values(), key=lambda entry: entry['path']),
              'factory_boot_classpath_preserved': True, 'aosp_preopt_for_added_apks_packaged': False,
              'full_aosp_framework_port_complete': False, 'system_image_built': False,
              'on_device_vr_tested': False, 'headset_modified': False}
    (REPORTS / 'staging.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'staged': True, 'factory_packages': len(factory_packages),
                      'aosp_executables': [path for path, entry in additions.items() if entry['type'] == 'executable'],
                      'aosp_apks': [path for path, entry in additions.items() if entry['type'] == 'apk'],
                      'full_aosp_framework_port_complete': False}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', action='store_true', required=True)
    parser.parse_args()
    guard_volume()
    stage()


if __name__ == '__main__':
    main()
