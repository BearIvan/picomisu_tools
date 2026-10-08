"""Check the factory Bluetooth component set against the Source build outputs.

Reads device/pico/PICOA8110/factory-bluetooth.json and verifies, statically:
- every preserved file exists in the factory 5.13.7 system tree (hash recorded);
- native: each preserved ELF's DT_NEEDED closure resolves in the preserved set or
  the Source system/APEX outputs, and every undefined symbol is defined in that
  closure; results are compared with the same resolution in the factory tree;
- Java: every framework class/method/field referenced by the preserved APKs
  resolves in the Source BOOTCLASSPATH plus their uses-library JARs, compared
  with the factory classpath;
- permissions requested by the APKs are declared by Source framework-res;
- SELinux/sysconfig/permission entries named in the config are present in Source.
Nothing on the headset is accessed.  Run inside WSL:
taskset -c 0-7 python3 tools/check-factory-bluetooth.py
"""
from collections import defaultdict
import importlib.util
import json
from pathlib import Path
import re
import struct
import subprocess

spec = importlib.util.spec_from_file_location('scan', Path(__file__).with_name('scan-api-consumers.py'))
scan = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scan)
pico = scan.pico

ROOT = pico.ROOT
CONFIG = ROOT / 'device/pico/PICOA8110/factory-bluetooth.json'
REPORT = ROOT / 'validation/factory-bluetooth.json'
FACTORY = scan.FACTORY_TREE
SOURCE = pico.PRODUCT
AAPT2 = pico.HOST / 'aapt2'
LIBRARY_JARS = {'javax.obex': 'system/framework/javax.obex.jar',
                'org.apache.http.legacy': 'system/framework/org.apache.http.legacy.jar'}


def lib_dirs(tree, abi):
    lib = 'lib64' if abi == 'arm64' else 'lib'
    dirs = [tree / 'system' / lib, tree / 'system' / lib / 'vndk-29', tree / 'system' / lib / 'vndk-sp-29']
    apex = tree / 'system/apex'
    if apex.is_dir():
        for item in sorted(apex.iterdir()):
            if item.is_dir():
                dirs += [item / lib, item / lib / 'bionic']
    return [d for d in dirs if d.is_dir()]


def abi_of(path):
    header = path.read_bytes()[:5]
    return 'arm64' if header[4] == 2 else 'arm'


def is_elf(path):
    with path.open('rb') as stream:
        return stream.read(4) == b'\x7fELF'


class Resolver:
    """ELF resolution in one tree; preserved factory files shadow the tree's own copies."""

    def __init__(self, tree, preserved):
        self.tree, self.preserved = tree, preserved
        self.cache = {}

    def find(self, name, abi):
        lib = 'lib64' if abi == 'arm64' else 'lib'
        for rel, path in self.preserved.items():
            if rel in ('system/%s/%s' % (lib, name),) and abi_of(path) == abi:
                return rel, path
        for directory in lib_dirs(self.tree, abi):
            candidate = directory / name
            if candidate.is_file():
                return str(candidate.relative_to(self.tree)), candidate
        return None, None

    def symbols(self, path):
        if path not in self.cache:
            self.cache[path] = (pico.read_symbols(path), pico.needed(path))
        return self.cache[path]

    def check(self, path):
        abi = abi_of(path)
        (_, undefined, _), needed = self.symbols(path)
        providers, missing, pending, seen = [], [], list(needed), set()
        while pending:
            name = pending.pop(0)
            if name in seen:
                continue
            seen.add(name)
            rel, found = self.find(name, abi)
            if found is None:
                missing.append(name)
                continue
            providers.append(rel)
            (_, _, _), sub = self.symbols(found)
            pending += sub
        defined = set()
        for rel in providers:
            _, found = self.find(Path(rel).name, abi)
            defined |= self.symbols(found)[0][0]
        unresolved = sorted(s for s in undefined if s not in defined and s.split('@')[0] not in defined)
        return {'abi': abi, 'needed': needed, 'providers': providers, 'missing_libraries': missing,
                'unresolved_symbols': unresolved}


def java_chain(tree, bootclasspath, libraries):
    paths = []
    for item in bootclasspath:
        if item.startswith('/apex/'):
            name, rest = item[len('/apex/'):].split('/', 1)
            candidates = [tree / 'system/apex' / name / rest] + [tree / 'system/apex' / d / rest for d in
                                                                  ('com.android.runtime.release', 'com.android.runtime.debug')
                                                                  if name == 'com.android.runtime']
            path = next((c for c in candidates if c.exists()), candidates[0])
        else:
            path = tree / item.lstrip('/')
        paths.append(path)
    paths += [tree / LIBRARY_JARS[name] for name in libraries]
    return paths, scan.hierarchy(paths)


def bootclasspath(tree):
    for rc in [tree / 'init.environ.rc', tree / 'system/etc/init.environ.rc', tree / 'root/init.environ.rc']:
        if rc.exists():
            match = re.search(r'export BOOTCLASSPATH (\S+)', rc.read_text())
            if match:
                return match.group(1).split(':')
    raise FileNotFoundError('init.environ.rc in ' + str(tree))


def apk_refs(path):
    """External class/method/field references of one APK (not defined in the APK itself)."""
    own, refs = set(), set()
    dexes = [scan.Dex(blob) for blob in scan.dex_blobs(path)]
    for dex in dexes:
        for clazz, *_ in dex.classes():
            own.add(clazz)
    for dex in dexes:
        for owner, member in dex.methods:
            refs.add((owner, member, 'methods'))
        for owner, member in dex.fields:
            refs.add((owner, member, 'fields'))
        for clazz in dex.types:
            refs.add((clazz, None, 'class'))
    return {r for r in refs if r[0].startswith('L') and r[0].rstrip(';').lstrip('L') and
            r[0] not in own and not r[0].startswith('[')}


def encoded_value(data, pos):
    """Decode one DEX encoded_value; returns (int value or None, next position)."""
    header = data[pos]
    kind, arg = header & 0x1f, header >> 5
    pos += 1
    if kind in (0x1e, 0x1f):
        return None, pos
    if kind == 0x1c:
        size, pos = scan.uleb(data, pos)
        for _ in range(size):
            _, pos = encoded_value(data, pos)
        return None, pos
    if kind == 0x1d:
        _, pos = scan.uleb(data, pos)
        size, pos = scan.uleb(data, pos)
        for _ in range(size):
            _, pos = scan.uleb(data, pos)
            _, pos = encoded_value(data, pos)
        return None, pos
    raw = data[pos:pos + arg + 1]
    value = int.from_bytes(raw, 'little', signed=kind in (0x00, 0x02, 0x04, 0x06))
    return (value if kind == 0x04 else None), pos + arg + 1


def aidl_tables(paths):
    """TRANSACTION_* codes of every AIDL Stub class in a class loader chain (first definition wins)."""
    tables = {}
    for path in paths:
        if not path.exists():
            continue
        for blob in scan.dex_blobs(path):
            dex = scan.Dex(blob)
            count, at = dex.class_defs_at
            for index, (clazz, _, _, _, fields, _) in enumerate(dex.classes()):
                if not clazz.endswith('$Stub;') or clazz in tables:
                    continue
                static_values = struct.unpack_from('<I', dex.data, at + index * 32 + 28)[0]
                statics = [name for name, flags in fields.items() if flags & 0x8]
                table = {}
                if static_values:
                    size, pos = scan.uleb(dex.data, static_values)
                    for name in statics[:size]:
                        value, pos = encoded_value(dex.data, pos)
                        if name.startswith('TRANSACTION_') and value is not None:
                            table[name.split(':')[0][len('TRANSACTION_'):]] = value
                tables[clazz] = table
    return tables


def resolves(ref, chain):
    owner, member, kind = ref
    if kind == 'class':
        return owner in chain
    return scan.resolve(owner, member, kind, [chain]) is not None


def aapt(*args):
    return subprocess.run([str(AAPT2), *map(str, args)], check=True, text=True, stdout=subprocess.PIPE).stdout


def declared_permissions(apk):
    tree = aapt('dump', 'xmltree', '--file', 'AndroidManifest.xml', apk)
    names, inside = set(), False
    for line in tree.splitlines():
        stripped = line.strip()
        if stripped.startswith('E: '):
            inside = stripped.startswith('E: permission ')
        elif inside and ':name(' in stripped:
            names.add(re.search(r'="([^"]+)"', stripped).group(1))
            inside = False
    return names


def requested_permissions(apk):
    return set(re.findall(r"uses-permission: name='([^']+)'", aapt('dump', 'permissions', apk)))


def main():
    pico.guard_volume()
    config = json.loads(CONFIG.read_text())
    preserved, files, problems = {}, {}, []
    for rel in config['preserve']:
        path = FACTORY / rel
        if not path.exists():
            problems.append('missing factory file ' + rel)
            continue
        real = path.resolve() if path.is_symlink() else path
        if path.is_symlink():
            files[rel] = {'symlink': str(path.readlink())}
            continue
        preserved[rel] = real
        files[rel] = {'sha256': pico.digest(real), 'size': real.stat().st_size}

    # Native closure: factory resolution vs Source resolution.
    factory_res, source_res = Resolver(FACTORY, preserved), Resolver(SOURCE, preserved)
    native, external = {}, defaultdict(set)
    for rel, path in preserved.items():
        if not is_elf(path):
            continue
        f, s = factory_res.check(path), source_res.check(path)
        for provider in s['providers']:
            if provider not in preserved:
                external[provider].add(rel)
        new_missing = sorted(set(s['missing_libraries']) - set(f['missing_libraries']))
        new_unresolved = sorted(set(s['unresolved_symbols']) - set(f['unresolved_symbols']))
        native[rel] = {'abi': s['abi'], 'needed': s['needed'],
                       'factory_missing_libraries': f['missing_libraries'],
                       'source_missing_libraries': s['missing_libraries'],
                       'factory_unresolved_symbols': len(f['unresolved_symbols']),
                       'source_only_missing_libraries': new_missing,
                       'source_only_unresolved_symbols': new_unresolved}
        if new_missing or new_unresolved:
            problems.append('native ' + rel)

    # Java references.
    apks = [rel for rel in preserved if rel.endswith('.apk')]
    java = {}
    factory_bcp, source_bcp = bootclasspath(FACTORY), bootclasspath(SOURCE)
    for rel in apks:
        badging = aapt('dump', 'badging', preserved[rel])
        libraries = re.findall(r"uses-library(?:-not-required)?:'([^']+)'", badging)
        fpaths, fchain = java_chain(FACTORY, factory_bcp, libraries)
        spaths, schain = java_chain(SOURCE, source_bcp, libraries)
        refs = apk_refs(preserved[rel])
        factory_ok = {r for r in refs if resolves(r, fchain)}
        gaps = sorted((r for r in factory_ok if not resolves(r, schain)), key=lambda r: (r[0], r[1] or ""))
        # Framework AIDL interfaces the APK implements or calls must keep the factory wire table.
        ftables, stables = aidl_tables(fpaths), aidl_tables(spaths)
        interfaces = sorted({o[:-1] + '$Stub;' for o, _, _ in refs if o[:-1] + '$Stub;' in ftables} |
                            {o for o, _, _ in refs if o in ftables})
        table_diffs = {}
        for stub in interfaces:
            f, s = ftables[stub], stables.get(stub)
            if s != f:
                table_diffs[stub] = {'factory_methods': len(f), 'source_methods': None if s is None else len(s),
                                     'differences': sorted(k for k in set(f) | set(s or {}) if f.get(k) != (s or {}).get(k))}
        java[rel] = {'uses_library': libraries,
                     'source_chain_missing_jars': [str(p.relative_to(SOURCE)) for p in spaths if not p.exists()],
                     'external_references': len(refs), 'resolved_in_factory': len(factory_ok),
                     'unresolved_in_source': ['%s->%s' % (o, m) if m else o for o, m, _ in gaps],
                     'aidl_interfaces_checked': len(interfaces),
                     'aidl_table_differences': table_diffs}
        if gaps or table_diffs:
            problems.append('java ' + rel)

    # Permissions.
    source_perms = declared_permissions(SOURCE / 'system/framework/framework-res.apk')
    factory_perms = declared_permissions(FACTORY / 'system/framework/framework-res.apk')
    permissions = {}
    for rel in apks:
        requested = requested_permissions(preserved[rel])
        missing = sorted(p for p in requested if p in factory_perms and p not in source_perms)
        permissions[rel] = {'requested': len(requested), 'factory_framework_declared_missing_in_source': missing}
        if missing:
            problems.append('permissions ' + rel)

    # SELinux and configuration entries.
    selinux = SOURCE / 'system/etc/selinux'
    checks = {
        'seapp bluetooth domain': ('plat_seapp_contexts', r'user=bluetooth\s.*domain=bluetooth'),
        'bt_logger file context': ('plat_file_contexts', r'^/system/bin/bt_logger\s'),
        'bluedroid data context': ('plat_file_contexts', r'^/data/misc/bluedroid'),
        'bt_logger domain': ('plat_sepolicy.cil', r'\(type bt_logger\)'),
    }
    config_checks = {}
    for label, (name, pattern) in checks.items():
        path = selinux / name
        present = path.exists() and re.search(pattern, path.read_text(errors='replace'), re.M) is not None
        factory_present = re.search(pattern, (FACTORY / 'system/etc/selinux' / name).read_text(errors='replace'), re.M) is not None
        config_checks[label] = {'factory': factory_present, 'source': present}
    def contexts(tree, name, pattern):
        text = (tree / 'system/etc/selinux' / name).read_text(errors='replace')
        # /dev/__properties__/<context> lines are generated per property context by the build.
        return {' '.join(line.split()) for line in text.splitlines()
                if re.search(pattern, line) and not line.startswith('/dev/__properties__/')}
    for name, pattern in [('plat_property_contexts', r'bluetooth_prop'), ('plat_file_contexts', r'bluetooth|bt_logger')]:
        missing = sorted(contexts(FACTORY, name, pattern) - contexts(SOURCE, name, pattern))
        config_checks[name + ' bluetooth entries'] = {'factory': True, 'source': not missing, 'missing': missing}
    sysconfig = '\n'.join(p.read_text(errors='replace') for p in (SOURCE / 'system/etc/sysconfig').glob('*.xml'))
    for package in ('com.android.bluetooth', 'org.codeaurora.bluetooth'):
        config_checks['hidden-api whitelist ' + package] = {
            'factory': True, 'source': ('hidden-api-whitelisted-app package="%s"' % package) in sysconfig}
    platform = (SOURCE / 'system/etc/permissions/platform.xml').read_text()
    config_checks['BLUETOOTH_STACK gid'] = {'factory': True, 'source': 'android.permission.BLUETOOTH_STACK' in platform}
    config_gaps = sorted(k for k, v in config_checks.items() if v['factory'] and not v['source'])

    # AOSP counterparts that the preserved set replaces.
    replaced = {}
    for rel in preserved:
        replaced[rel] = (SOURCE / rel).exists()

    report = {'config': str(CONFIG.relative_to(ROOT)), 'factory_tree': str(FACTORY), 'source_product': str(SOURCE),
              'files': files, 'native': native,
              'external_native_providers': {k: sorted(v) for k, v in sorted(external.items())},
              'java': java, 'permissions': permissions, 'configuration': config_checks,
              'configuration_missing_in_source': config_gaps,
              'source_counterpart_present': replaced,
              'problems': problems, 'system_partitions_modified': False}
    REPORT.write_text(json.dumps(report, indent=1, ensure_ascii=False) + '\n')
    summary = {'files': len(files), 'elf': len(native), 'external_providers': len(external),
               'java_gaps': {k: len(v['unresolved_in_source']) for k, v in java.items()},
               'aidl': {k: (v['aidl_interfaces_checked'], sorted(v['aidl_table_differences'])) for k, v in java.items()},
               'native_problems': [p for p in problems if p.startswith('native')],
               'permission_gaps': {k: v['factory_framework_declared_missing_in_source'] for k, v in permissions.items()},
               'config_gaps': config_gaps}
    print(json.dumps(summary, indent=1))


if __name__ == '__main__':
    main()
