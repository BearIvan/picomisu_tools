"""Offline checks of the assembled Source trial image (source-trial-01).

Runs in WSL as the normal user after tools/assemble-source-image.py --stage,
--build and --readback. Reads the staged tree (byte-identical to the image,
proven by the readback) and the factory 5.13.7 trees; nothing touches the headset.

Checks:
  readback    every entry of the image equals the plan (content, owner, mode, capabilities)
  selinux     labels of carried factory files equal their factory labels, Source files keep
              their Source labels; init services on /system have an exec domain transition
  init        host_init_verifier on every system rc file; services point to existing binaries
  native      DT_NEEDED closure and strong symbols of every ELF of the image (Source APEX
              payloads extracted); factory-origin ELFs compared with the same resolution
              on the factory 5.13.7 system
  java        factory class path config (check-factory-component.py on the image), carried
              non-class-path JARs and carried/shadowed APKs link against the Source boot
              class path (+ uses-library), AIDL tables, permissions
  packages    PackageManagerService scan simulation over system/vendor/odm/product:
              duplicates, shared-user certificate consistency, platform signature, seinfo,
              package set equal to the factory one
  dexpreopt   no factory oat/odex/vdex, Source boot image for all boot JARs, APK compile status
  vintf       checkvintf --check-compat with the factory vendor/odm/product
  image       partition size, ext4 (e2fsck), AVB chain (from image.json)
Writes validation/source-trial-01.json and outputs/source-trial-01/verification.json.
"""
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import zipfile


def _load(name, file):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(file))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


asm = _load('source_image', 'assemble-source-image.py')
cfc = _load('factory_component', 'check-factory-component.py')
fbt, scan, pico = cfc.fbt, cfc.scan, cfc.pico

ROOT = asm.ROOT
STAGE, TREE, OUTPUT = asm.STAGE, asm.TREE, asm.OUTPUT
FACTORY, PARTITIONS = asm.FACTORY, asm.PARTITIONS
CHECK = STAGE / 'check'
HOST = asm.HOST
REPORT = (ROOT if asm.env.LEGACY else asm.env.WORK) / 'validation' / (asm.NAME + '.json')


def dynamic_symbols(path):
    """(defined, strong undefined, weak undefined); IFUNC rows are printed as '<OS specific>: 10'."""
    output = subprocess.run(['readelf', '--dyn-syms', '--wide', str(path)], capture_output=True, text=True).stdout
    defined, undefined, weak = set(), set(), set()
    for line in output.splitlines():
        parts = line.replace('<OS specific>: 10', 'IFUNC').replace('<processor specific>: 13', 'PROC13').split()
        if len(parts) < 8 or not parts[0].rstrip(':').isdigit():
            continue
        binding, index, name = parts[4], parts[6], parts[7].replace('@@', '@')
        if index == 'UND':
            (weak if binding == 'WEAK' else undefined).add(name)
        elif binding in ('GLOBAL', 'WEAK', 'UNIQUE'):
            defined.add(name)
            defined.add(name.split('@')[0])
    return defined, undefined, weak


def readelf_symbols(path, cache={}):
    if path not in cache:
        cache[path] = (dynamic_symbols(path), pico.needed(path))
    return cache[path]


def is_elf(path):
    try:
        with open(path, 'rb') as stream:
            return stream.read(4) == b'\x7fELF'
    except OSError:
        return False


def elf_class(path):
    with open(path, 'rb') as stream:
        return 'arm64' if stream.read(5)[4] == 2 else 'arm'


# --------------------------------------------------------------------------- APEX payloads

def extract_apexes(apex_dir, dest):
    """Unpack apex_payload.img of every .apex into dest/<apex name> (debugfs rdump, read only)."""
    dest.mkdir(parents=True, exist_ok=True)
    result = {}
    for apex in sorted(apex_dir.glob('*.apex')):
        with zipfile.ZipFile(apex) as archive:
            name = json.loads(archive.read('apex_manifest.json'))['name']
            target = dest / name
            if not target.exists():
                payload = dest / (apex.name + '.payload.img')
                payload.write_bytes(archive.read('apex_payload.img'))
                target.mkdir()
                subprocess.run(['debugfs', '-R', 'rdump / ' + str(target), str(payload)],
                               check=True, capture_output=True)
                payload.unlink()
        result[name] = target
    return result


def check_root(base, apexes, name):
    """A tree with system/* of base and system/apex/<name> = extracted payloads (for the Java tools)."""
    root = CHECK / name
    if root.exists():
        shutil.rmtree(root)
    (root / 'system/apex').mkdir(parents=True)
    for item in (base / 'system').iterdir():
        if item.name != 'apex':
            (root / 'system' / item.name).symlink_to(item)
    for apex, folder in apexes.items():
        (root / 'system/apex' / apex).symlink_to(folder)
    for item in base.iterdir():
        if item.is_file() and item.name.endswith('.rc'):
            (root / item.name).symlink_to(item)
    return root


# --------------------------------------------------------------------------- native

class Libraries:
    def __init__(self, base, apexes):
        self.dirs = {}
        for abi, lib in [('arm64', 'lib64'), ('arm', 'lib')]:
            # [system] default namespace search paths: /system/${LIB}, /product/${LIB}
            dirs = [base / 'system' / lib, PARTITIONS / 'product' / lib]
            for apex in apexes.values():
                dirs += [apex / lib, apex / lib / 'bionic']
            dirs += [base / 'system' / lib / 'vndk-29', base / 'system' / lib / 'vndk-sp-29']
            self.dirs[abi] = [d for d in dirs if d.is_dir()]

    def find(self, name, abi):
        for folder in self.dirs[abi]:
            candidate = folder / name
            if candidate.is_file():
                return candidate
        return None

    def check(self, path):
        abi = elf_class(path)
        (_, undefined, _), needed = readelf_symbols(path)
        providers, missing, pending, seen = [], [], list(needed), set()
        while pending:
            name = pending.pop(0)
            if name in seen:
                continue
            seen.add(name)
            found = self.find(name, abi)
            if found is None:
                missing.append(name)
                continue
            providers.append(found)
            pending += readelf_symbols(found)[1]
        defined = set()
        for provider in providers:
            defined |= readelf_symbols(provider)[0][0]
        unresolved = sorted(s for s in undefined if s not in defined and s.split('@')[0] not in defined)
        return {'abi': abi, 'missing': sorted(missing), 'unresolved': unresolved}


def native(plan, source_apex, factory_apex):
    tree_libs, factory_libs = Libraries(TREE, source_apex), Libraries(FACTORY, factory_apex)
    results, problems, accepted = {}, [], {}
    elfs = [e for e in plan['entries'] if e['kind'] == 'file' and is_elf(TREE / e['path'].lstrip('/'))]
    ld = ('/system/bin/linker', '/system/bin/linker64')
    for entry in elfs:
        path = TREE / entry['path'].lstrip('/')
        if entry['path'] in ld or '/apex/' in entry['path']:
            continue
        try:
            got = tree_libs.check(path)
        except subprocess.CalledProcessError:
            continue
        if not got['missing'] and not got['unresolved']:
            continue
        record = {'origin': entry['origin'], **got}
        if entry['origin'].startswith('factory'):
            base = factory_libs.check(FACTORY / entry['path'].lstrip('/'))
            record['factory_missing'] = base['missing']
            record['factory_unresolved'] = base['unresolved']
            record['new_missing'] = sorted(set(got['missing']) - set(base['missing']))
            record['new_unresolved'] = sorted(set(got['unresolved']) - set(base['unresolved']))
        else:
            record['new_missing'], record['new_unresolved'] = got['missing'], got['unresolved']
        if record['new_missing'] or record['new_unresolved']:
            results[entry['path']] = record
    return {'elf_files': len(elfs), 'with_new_gaps': results}


# --------------------------------------------------------------------------- Java

def libraries_map(bases):
    mapping = {}
    for base in bases:
        for xml in sorted(base.glob('etc/permissions/*.xml')):
            text = xml.read_text(errors='replace')
            for match in re.finditer(r'<library\s+name="([^"]+)"\s+file="([^"]+)"', text):
                mapping.setdefault(match.group(1), match.group(2))
    return mapping


def jar_file(root, location):
    if location.startswith('/apex/'):
        return fbt.java_chain(root, [location], [])[0][0]
    for prefix, base in [('/system/', root / 'system'), ('/product/', PARTITIONS / 'product'),
                         ('/vendor/', PARTITIONS / 'vendor'), ('/odm/', PARTITIONS / 'odm')]:
        if location.startswith(prefix):
            return base / location[len(prefix):]
    return root / location.lstrip('/')


def java(plan, source_root, factory_root):
    results = {}
    source_bcp = cfc.environ(source_root)['BOOTCLASSPATH']
    factory_bcp = cfc.environ(factory_root)['BOOTCLASSPATH']
    source_libs = libraries_map([TREE / 'system', PARTITIONS / 'product', PARTITIONS / 'vendor', PARTITIONS / 'odm'])
    factory_libs = libraries_map([FACTORY / 'system', PARTITIONS / 'product', PARTITIONS / 'vendor', PARTITIONS / 'odm'])
    sboot = [jar_file(source_root, l) for l in source_bcp]
    fboot = [jar_file(factory_root, l) for l in factory_bcp]
    schain_boot, fchain_boot = scan.hierarchy(sboot), scan.hierarchy(fboot)
    stables_boot, ftables_boot = fbt.aidl_tables(sboot), fbt.aidl_tables(fboot)
    source_perms = fbt.declared_permissions(TREE / 'system/framework/framework-res.apk')
    factory_perms = fbt.declared_permissions(FACTORY / 'system/framework/framework-res.apk')
    targets = [e for e in plan['entries'] if e['kind'] == 'file' and e['origin'] != 'source'
               and e['path'].endswith(('.apk', '.jar')) and e['path'] != '/system/framework/framework-res.apk']

    def one(entry):
        path = TREE / entry['path'].lstrip('/')
        factory_file = FACTORY / entry['path'].lstrip('/')
        if entry['origin'].startswith('product-shadow'):
            factory_file = PARTITIONS / plan['shadows'][entry['path'].lstrip('/')]['product_path'].split('/', 1)[1]
        if not any(scan.dex_blobs(path)):
            return entry['path'], {'dex': False}
        libraries = []
        if path.suffix == '.apk':
            badging = fbt.aapt('dump', 'badging', path)
            libraries = re.findall(r"uses-library(?:-not-required)?:'([^']+)'", badging)
        slibs = [jar_file(source_root, source_libs[n]) for n in libraries if n in source_libs]
        flibs = [jar_file(factory_root, factory_libs[n]) for n in libraries if n in factory_libs]
        schain = scan.hierarchy(sboot + slibs) if slibs else schain_boot
        fchain = scan.hierarchy(fboot + flibs) if flibs else fchain_boot
        refs = fbt.apk_refs(path)
        factory_ok = {r for r in refs if fbt.resolves(r, fchain)}
        gaps = sorted(('%s->%s' % (o, m) if m else o) for o, m, k in factory_ok if not fbt.resolves((o, m, k), schain))
        ftables = fbt.aidl_tables(fboot + flibs) if flibs else ftables_boot
        stables = fbt.aidl_tables(sboot + slibs) if slibs else stables_boot
        stubs = sorted({o[:-1] + '$Stub;' for o, _, _ in refs if o[:-1] + '$Stub;' in ftables} |
                       {o for o, _, _ in refs if o in ftables})
        table_diffs = {s: sorted(k for k in set(ftables[s]) | set(stables.get(s) or {})
                                 if ftables[s].get(k) != (stables.get(s) or {}).get(k))
                       for s in stubs if stables.get(s) != ftables[s]}
        record = {'origin': entry['origin'], 'dex': True, 'uses_library': libraries,
                  'missing_libraries': [n for n in libraries if n not in source_libs],
                  'missing_libraries_on_factory_too': [n for n in libraries if n not in source_libs and n not in factory_libs],
                  'external_references': len(refs), 'resolved_on_factory': len(factory_ok),
                  'unresolved_on_source': gaps, 'aidl_interfaces': len(stubs), 'aidl_table_differences': table_diffs}
        if path.suffix == '.apk':
            requested = fbt.requested_permissions(path)
            record['permissions_missing_in_source'] = sorted(p for p in requested
                                                            if p in factory_perms and p not in source_perms)
        return entry['path'], record
    with ThreadPoolExecutor(4) as pool:
        for path, record in pool.map(one, targets):
            results[path] = record
    return results


def bootclasspath(source_root, factory_root):
    cfc.SOURCE, cfc.FACTORY = source_root, factory_root
    argv = sys.argv
    sys.argv = ['check-factory-component.py', '--report', str(CHECK / 'factory-bootclasspath.json')]
    try:
        cfc.main()
    finally:
        sys.argv = argv
    report = json.loads((CHECK / 'factory-bootclasspath.json').read_text())
    return {'classpaths_match': {k: v['matches'] for k, v in report['classpaths'].items()},
            'problems': report['problems'],
            'jars': {n: {'decision': r['decision'], 'passes': r['check_passes'],
                         'unaccepted_gaps': len(r['unaccepted_gaps']), 'accepted_gaps': len(r['accepted_gaps']),
                         'dex_identical': r.get('dex_identical'), 'boot_image_files': r.get('boot_image_files')}
                     for n, r in report['jars'].items()}}


# --------------------------------------------------------------------------- packages

SCAN_ORDER = ['vendor/overlay', 'product/overlay', 'product_services/overlay', 'odm/overlay', 'oem/overlay',
              'system/framework', 'system/priv-app', 'system/app', 'vendor/priv-app', 'vendor/app',
              'odm/priv-app', 'odm/app', 'oem/app', 'product/priv-app', 'product/app']


def apk_list(base, prefix, scan_dir):
    folder = base / scan_dir.split('/', 1)[1] if prefix != 'system' else base / scan_dir
    if not folder.is_dir():
        return []
    if scan_dir.endswith('framework'):
        return [folder / 'framework-res.apk'] if (folder / 'framework-res.apk').exists() else []
    found = []
    for item in sorted(folder.iterdir()):
        if item.suffix == '.apk':
            found.append(item)
        elif item.is_dir():
            found += sorted(item.glob('*.apk'))
    return found


def mac_signers(files):
    import hashlib
    signers = {}
    for file in files:
        if file.exists():
            for match in re.finditer(r'<signer signature="([0-9a-fA-F]+)"\s*>.*?<seinfo value="([^"]+)"',
                                     file.read_text(), re.S):
                signers.setdefault(hashlib.sha256(bytes.fromhex(match.group(1))).hexdigest(), match.group(2))
    return signers


def simulate(base, label, mac_files):
    """PackageManagerService (r47) boot scan: first package name wins, the first member fixes the
    shared-user certificate, a later member with another certificate fails to install."""
    items = []
    for scan_dir in SCAN_ORDER:
        partition = scan_dir.split('/')[0]
        root = base if partition == 'system' else PARTITIONS / partition
        items += [(scan_dir, apk) for apk in apk_list(root if partition != 'system' else base, partition, scan_dir)]

    def identify(item):
        scan_dir, apk = item
        return scan_dir, apk, asm.package_name(apk), asm.shared_uid(apk), asm.signers(apk)
    with ThreadPoolExecutor(8) as pool:
        identified = list(pool.map(identify, items))
    installed, duplicates, failures, shared = {}, [], [], {}
    platform = None
    seinfo = mac_signers(mac_files)
    for scan_dir, apk, package, uid, certs in identified:
        if package == 'android':
            platform = certs
        if package in installed:
            duplicates.append({'package': package, 'skipped': str(apk), 'installed': installed[package]['path']})
            continue
        if uid:
            if uid in shared and shared[uid] != certs:
                failures.append({'package': package, 'path': str(apk), 'shared_uid': uid,
                                 'reason': 'INSTALL_PARSE_FAILED_INCONSISTENT_CERTIFICATES'})
                continue
            shared.setdefault(uid, certs)
        installed[package] = {'path': str(apk), 'scan_dir': scan_dir, 'shared_uid': uid, 'certs': certs,
                              'platform_signed': certs == platform,
                              'seinfo': seinfo.get(certs[0], 'default') if len(certs) == 1 else 'default'}
    return {'installed': installed, 'duplicates': duplicates, 'failures': failures,
            'shared_users': shared, 'platform_cert': platform}


def packages(plan):
    trial = simulate(TREE, 'trial', [TREE / 'system/etc/selinux/plat_mac_permissions.xml',
                                     PARTITIONS / 'vendor/etc/selinux/vendor_mac_permissions.xml',
                                     PARTITIONS / 'product/etc/selinux/product_mac_permissions.xml'])
    factory = simulate(FACTORY, 'factory', [FACTORY / 'system/etc/selinux/plat_mac_permissions.xml',
                                            PARTITIONS / 'vendor/etc/selinux/vendor_mac_permissions.xml',
                                            PARTITIONS / 'product/etc/selinux/product_mac_permissions.xml'])
    t, f = trial['installed'], factory['installed']
    changed_platform = sorted(p for p in t if p in f and f[p]['platform_signed'] and not t[p]['platform_signed'])
    changed_seinfo = {p: {'factory': f[p]['seinfo'], 'trial': t[p]['seinfo']} for p in t
                      if p in f and f[p]['seinfo'] != t[p]['seinfo']}
    return {'trial': {'installed': len(t), 'duplicates': trial['duplicates'], 'failures': trial['failures'],
                      'shared_users': {k: v for k, v in trial['shared_users'].items()},
                      'platform_cert': trial['platform_cert']},
            'factory': {'installed': len(f), 'failures': factory['failures'],
                        'platform_cert': factory['platform_cert']},
            'missing_vs_factory': sorted(set(f) - set(t)), 'extra_vs_factory': sorted(set(t) - set(f)),
            'lost_platform_signature': changed_platform, 'seinfo_changes': changed_seinfo,
            'not_platform_signed_pico_role': sorted(p for p, v in t.items() if not v['platform_signed']
                                                    and v['certs'] and v['certs'][0] in asm.config()['signing']['factory_cert_roles'])}


# --------------------------------------------------------------------------- SELinux / init

def selinux_labels(plan, readback):
    source_meta = {e['path']: e for e in json.loads((STAGE / 'source-metadata.json').read_text())['entries']}
    factory_meta = {e['path']: e for e in json.loads(asm.FACTORY_REPORT.read_text())['entries']}
    labels = readback['labels']
    factory_diff, source_diff = {}, {}
    for entry in plan['entries']:
        path = entry['path']
        label = labels.get(path)
        if entry['origin'].startswith('factory') and path in factory_meta:
            if factory_meta[path]['selinux'] != label:
                factory_diff[path] = {'factory': factory_meta[path]['selinux'], 'image': label}
        elif entry['origin'] in ('source', 'generated') and path in source_meta:
            if source_meta[path]['selinux'] != label:
                source_diff[path] = {'source': source_meta[path]['selinux'], 'image': label}
        elif entry['origin'] == 'trial-extra':
            expected = plan['extra_files'][path.lstrip('/')]['selinux']
            if expected != label:
                source_diff[path] = {'config': expected, 'image': label}
    unlabeled = sorted(p for p, l in labels.items() if l.split(':')[2] in ('unlabeled', 'default_t'))
    return {'factory_files_label_differences': factory_diff, 'source_files_label_differences': source_diff,
            'unlabeled': unlabeled, 'shadow_labels': {p: labels.get(p) for p in labels if p.startswith(
                ('/system/priv-app/Settings', '/system/app/QdcmFF', '/system/app/PowerOffAlarm'))}}


def rc_services(files):
    services = []
    for file, origin in files:
        current = None
        for line in file.read_text(errors='replace').splitlines():
            words = line.split()
            if not words or words[0].startswith('#'):
                continue
            if words[0] == 'service' and len(words) >= 3:
                current = {'name': words[1], 'path': words[2], 'rc': origin, 'seclabel': None, 'disabled': False}
                services.append(current)
            elif words[0] in ('on', 'import'):
                current = None
            elif current is not None and words[0] == 'seclabel':
                current['seclabel'] = words[1]
            elif current is not None and words[0] == 'disabled':
                current['disabled'] = True
    return services


def transitions():
    rules = set()
    cils = [TREE / 'system/etc/selinux/plat_sepolicy.cil', PARTITIONS / 'vendor/etc/selinux/vendor_sepolicy.cil',
            PARTITIONS / 'product/etc/selinux/product_sepolicy.cil', PARTITIONS / 'odm/etc/selinux/odm_sepolicy.cil']
    for cil in cils:
        if cil.exists():
            for match in re.finditer(r'\(typetransition (init(?:_\d+_\d+)?) (\S+) process (\S+)\)', cil.read_text()):
                rules.add(re.sub(r'_29_0$', '', match.group(2)))
    return rules


def init_check(readback):
    files = sorted(TREE.glob('*.rc')) + sorted((TREE / 'system/etc/init').glob('*.rc'))
    verifier = {}
    passwd = PARTITIONS / 'vendor/etc/passwd'
    for rc in files:
        if rc.name == 'ueventd.rc':
            continue
        arguments = [str(HOST / 'host_init_verifier'), str(rc)]
        if passwd.exists():
            arguments.append(str(passwd))
        result = subprocess.run(arguments, capture_output=True, text=True)
        if result.returncode != 0:
            verifier['/' + str(rc.relative_to(TREE))] = (result.stdout + result.stderr).strip().splitlines()[-5:]
    rc_files = [(f, '/' + str(f.relative_to(TREE))) for f in files]
    for part in ['vendor', 'odm']:
        rc_files += [(f, '/' + part + '/' + str(f.relative_to(PARTITIONS / part)))
                     for f in sorted((PARTITIONS / part / 'etc/init').rglob('*.rc'))]
    services = rc_services(rc_files)
    allowed = transitions()
    labels = readback['labels']
    factory_meta = {e['path']: e for e in json.loads(asm.FACTORY_REPORT.read_text())['entries']}
    problems = []
    for service in services:
        path = service['path']
        if path.startswith('/system/vendor/'):
            path = path[len('/system'):]
            if not (PARTITIONS / path.lstrip('/')).exists():
                problems.append({'service': service['name'], 'rc': service['rc'], 'path': path,
                                 'problem': 'vendor executable missing (also on factory)'})
            continue
        if not path.startswith('/system/'):
            continue
        resolved = path
        for _ in range(5):
            node = TREE / resolved.lstrip('/')
            if node.is_symlink():
                target = os.readlink(node)
                resolved = target if target.startswith('/') else str(Path(resolved).parent / target)
            else:
                break
        if resolved not in labels:
            on_factory = path in factory_meta
            problems.append({'service': service['name'], 'rc': service['rc'], 'path': path,
                             'problem': 'executable missing' + ('' if on_factory else ' (also on factory)'),
                             'regression': on_factory})
            continue
        exec_type = labels[resolved].split(':')[2]
        if service['seclabel'] is None and exec_type not in allowed:
            factory_label = factory_meta.get(resolved, {}).get('selinux', '')
            problems.append({'service': service['name'], 'rc': service['rc'], 'path': path,
                             'problem': 'no init domain transition for ' + exec_type,
                             'factory_label': factory_label,
                             'regression': factory_label.split(':')[2:3] != [exec_type] if factory_label else True})
    return {'rc_files_checked': len(files), 'host_init_verifier_failures': verifier,
            'services_total': len(services), 'system_services': sum(1 for s in services if s['path'].startswith('/system/')),
            'problems': problems}


# --------------------------------------------------------------------------- dexpreopt / VINTF

def dexpreopt(plan):
    compiled = [e['path'] for e in plan['entries'] if e['kind'] == 'file'
                and e['path'].endswith(('.odex', '.vdex', '.art', '.oat'))]
    foreign = [p for p in compiled if next(e for e in plan['entries'] if e['path'] == p)['origin'] != 'source']
    environ = cfc.environ(TREE)
    boot = [Path(l).stem for l in environ['DEX2OATBOOTCLASSPATH']]
    missing_boot = [(jar, abi) for jar in boot for abi in ('arm64', 'arm')
                    if not (TREE / 'system/framework' / abi / ('boot-%s.oat' % jar if jar != 'core-oj' else 'boot.oat')).exists()]
    apks = [e for e in plan['entries'] if e['kind'] == 'file' and e['path'].endswith('.apk')]
    status = defaultdict(list)
    for entry in apks:
        folder = (TREE / entry['path'].lstrip('/')).parent
        if (folder / 'oat').is_dir():
            status['preopted_source_boot_image'].append(entry['path'])
        elif entry['path'] == '/system/framework/framework-res.apk' or not any(scan.dex_blobs(TREE / entry['path'].lstrip('/'))):
            status['no_code'].append(entry['path'])
        else:
            status['compiled_on_device_first_boot'].append(entry['path'])
    stale = sorted(str(p.relative_to(PARTITIONS)) for part in ['product', 'vendor', 'odm']
                   for p in (PARTITIONS / part).rglob('oat') if p.is_dir())
    return {'factory_compiled_files_in_image': foreign, 'dex2oat_boot_jars': len(boot),
            'boot_image_missing': missing_boot, 'apks': {k: len(v) for k, v in status.items()},
            'first_boot_compile': sorted(status['compiled_on_device_first_boot']),
            'unchanged_partition_oat_dirs_compiled_against_factory_boot_image': stale,
            'first_boot_filters': {k: v for k, v in asm.read_props(TREE / 'system/build.prop').items()
                                   if k.startswith('pm.dexopt.')}}


def vintf():
    root = CHECK / 'vintf-root'
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    (root / 'system').symlink_to(TREE / 'system')
    for part in ['vendor', 'odm', 'product']:
        (root / part).symlink_to(PARTITIONS / part)
    result = subprocess.run([str(HOST / 'checkvintf'), '--check-compat', '--rootdir=' + str(root),
                             '--property', 'ro.product.first_api_level=29',
                             '--property', 'ro.boot.product.hardware.sku='], capture_output=True, text=True)
    factory_root = CHECK / 'vintf-factory-root'
    if factory_root.exists():
        shutil.rmtree(factory_root)
    factory_root.mkdir()
    (factory_root / 'system').symlink_to(FACTORY / 'system')
    for part in ['vendor', 'odm', 'product']:
        (factory_root / part).symlink_to(PARTITIONS / part)
    control = subprocess.run([str(HOST / 'checkvintf'), '--check-compat', '--rootdir=' + str(factory_root),
                              '--property', 'ro.product.first_api_level=29',
                              '--property', 'ro.boot.product.hardware.sku='], capture_output=True, text=True)
    return {'trial_exit_code': result.returncode, 'trial_output': (result.stdout + result.stderr).strip().splitlines()[-25:],
            'factory_control_exit_code': control.returncode,
            'factory_control_output': (control.stdout + control.stderr).strip().splitlines()[-10:]}


# --------------------------------------------------------------------------- main

def main():
    pico.guard_volume()
    plan = json.loads((STAGE / 'plan.json').read_text())
    image = json.loads((STAGE / 'image.json').read_text())
    readback = json.loads((STAGE / 'readback.json').read_text())
    if readback['image_sha256'] != image['files']['system.img']['sha256']:
        raise RuntimeError('Readback is not for the current image')
    source_apex = asm_apex = extract_apexes(TREE / 'system/apex', CHECK / 'source-apex')
    factory_apex = extract_apexes(FACTORY / 'system/apex', CHECK / 'factory-apex')
    source_root = check_root(TREE, source_apex, 'source-root')
    factory_root = check_root(FACTORY, factory_apex, 'factory-root')
    report = {'created_at': datetime.now(timezone.utc).isoformat(), 'name': asm.NAME,
              'image': image['files'], 'config_sha256': plan['config_sha256'],
              'origins': plan['origins'], 'headset_accessed': False}
    report['readback'] = {'entries': readback['entries_checked'], 'problems': readback['problems']}
    print('selinux', flush=True)
    report['selinux'] = selinux_labels(plan, readback)
    print('init', flush=True)
    report['init'] = init_check(readback)
    print('dexpreopt', flush=True)
    report['dexpreopt'] = dexpreopt(plan)
    print('vintf', flush=True)
    report['vintf'] = vintf()
    print('bootclasspath', flush=True)
    report['bootclasspath'] = bootclasspath(source_root, factory_root)
    print('packages', flush=True)
    report['packages'] = packages(plan)
    print('java', flush=True)
    report['java'] = java(plan, source_root, factory_root)
    print('native', flush=True)
    report['native'] = native(plan, source_apex, factory_apex)
    report['image_checks'] = {k: image[k] for k in ['partition_size', 'filesystem_size', 'e2fsck_exit_code',
                                                   'e2fsck_summary', 'avb_chain_verified', 'avb_root_flags',
                                                   'avb_root_rollback_index', 'avb_system_rollback_index',
                                                   'system_security_patch_property', 'current_boot_sha256',
                                                   'super_lp_metadata_rebuilt']}
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=1, ensure_ascii=False) + '\n')
    java_gaps = {p: r['unresolved_on_source'] for p, r in report['java'].items() if r.get('unresolved_on_source')}
    summary = {
        'readback_problems': len(readback['problems']),
        'selinux_factory_label_differences': len(report['selinux']['factory_files_label_differences']),
        'selinux_source_label_differences': len(report['selinux']['source_files_label_differences']),
        'unlabeled': len(report['selinux']['unlabeled']),
        'init_verifier_failures': sorted(report['init']['host_init_verifier_failures']),
        'init_problems': report['init']['problems'],
        'vintf_exit': report['vintf']['trial_exit_code'], 'vintf_factory_control_exit': report['vintf']['factory_control_exit_code'],
        'bootclasspath_problems': report['bootclasspath']['problems'],
        'package_failures': report['packages']['trial']['failures'],
        'missing_vs_factory': report['packages']['missing_vs_factory'],
        'extra_vs_factory': report['packages']['extra_vs_factory'],
        'lost_platform_signature': report['packages']['lost_platform_signature'],
        'java_gaps': {p: len(g) for p, g in java_gaps.items()},
        'native_new_gaps': {p: {'missing': r['new_missing'], 'unresolved': len(r['new_unresolved'])}
                            for p, r in report['native']['with_new_gaps'].items()},
        'dexpreopt': {k: report['dexpreopt'][k] for k in ['factory_compiled_files_in_image', 'boot_image_missing', 'apks']},
    }
    print(json.dumps(summary, indent=1))


if __name__ == '__main__':
    main()
