"""Find factory 5.13.7 consumers of the framework/services API candidates.

Candidates come from API-GAPS.json (factory-only classes, added/widened members
and native declarations of framework.jar/services.jar).  Consumers are all
factory DEX containers (system, product, vendor, odm APK/JAR) and ELF files.
References are resolved through the effective factory classpath, so an
inherited member reached through an application class is attributed to its
declaring framework class.  Candidates are checked against the effective
Source BOOTCLASSPATH/SYSTEMSERVERCLASSPATH to recognise relocated classes and
members inherited from Source superclasses.

This is a static linkage/string audit: dynamic class names built at runtime,
inlined constant fields, resources, manifest permission names and behaviour of
method bodies are not proven by it.  Nothing on the headset is accessed.
Run inside WSL: taskset -c 0-7 python3 tools/scan-api-consumers.py
"""
from collections import Counter, defaultdict
import hashlib
import importlib.util
import json
import multiprocessing
import os
from pathlib import Path
import re
import struct
import subprocess
import zipfile

spec = importlib.util.spec_from_file_location('pico_assembler', Path(__file__).with_name('assemble-vr-system.py'))
pico = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pico)

ROOT = pico.ROOT
FACTORY_TREE = pico.PROJECT / 'analysis/stock-5.13.7-system/root'
PARTITIONS = pico.PROJECT / 'analysis/stock-5.13.7-partitions'
SOURCE_PRODUCT = pico.PRODUCT
REPORT = ROOT / 'validation/api-consumers.json'
WORKERS = 8
PAIR = {'/system/framework/framework.jar', '/system/framework/services.jar'}
VR = re.compile(r'pico|pvr|pxr|openxr|xrruntime|seethrough|vrex|(?:^|[^a-z])vr(?:[^a-z]|$)|Vr(?=[A-Z]|$)', re.I)
NATIVE_LIBRARIES = ['libandroid_runtime.so', 'libandroid_servers.so', 'libhwui.so']
MAX_REFERRERS = 5
INTERNAL = {'ported_pair', 'source_replaced_elf', 'source_counterpart_classpath_jar'}

# Dalvik instruction widths (code units) and index kinds for API 29 DEX.
WIDTH = [1] * 256
KIND = [None] * 256
for op, width in [(0x02, 2), (0x03, 3), (0x05, 2), (0x06, 3), (0x08, 2), (0x09, 3), (0x13, 2), (0x14, 3),
                  (0x15, 2), (0x16, 2), (0x17, 3), (0x18, 5), (0x19, 2), (0x1a, 2), (0x1b, 3), (0x1c, 2),
                  (0x1f, 2), (0x20, 2), (0x22, 2), (0x23, 2), (0x24, 3), (0x25, 3), (0x26, 3), (0x29, 2),
                  (0x2a, 3), (0x2b, 3), (0x2c, 3), (0xfa, 4), (0xfb, 4), (0xfc, 3), (0xfd, 3), (0xfe, 2),
                  (0xff, 2)]:
    WIDTH[op] = width
for op in range(0x2d, 0x3e):
    WIDTH[op] = 2
for op in list(range(0x44, 0x6e)) + list(range(0x90, 0xb0)) + list(range(0xd0, 0xe3)):
    WIDTH[op] = 2
for op in list(range(0x6e, 0x73)) + list(range(0x74, 0x79)):
    WIDTH[op], KIND[op] = 3, 'method'
for op in range(0x52, 0x6e):
    KIND[op] = 'field'
for op in (0x1c, 0x1f, 0x20, 0x22, 0x23, 0x24, 0x25):
    KIND[op] = 'type'
KIND[0x1a] = KIND[0x1b] = 'string'
KIND[0xfa] = KIND[0xfb] = 'method'
# Instructions whose destination register is vA (4 bits) or vAA (8 bits).
DEST4 = set([0x01, 0x04, 0x07, 0x12, 0x20, 0x21, 0x23] + list(range(0x52, 0x59)) + list(range(0x7b, 0x90))
            + list(range(0xb0, 0xd8)))
DEST8 = set([0x02, 0x05, 0x08] + list(range(0x0a, 0x1d)) + [0x22] + list(range(0x2d, 0x32))
            + list(range(0x44, 0x4b)) + list(range(0x60, 0x67)) + list(range(0x90, 0xb0)) + list(range(0xd8, 0xe3)))
WIDE = {0x04, 0x05, 0x06, 0x0b, 0x16, 0x17, 0x18, 0x19, 0x45, 0x53, 0x61}


FACTORY = ('Lcom/pico/util/ExtImplFactory;', 'getImpl(Ljava/lang/Class;[Ljava/lang/Object;)Lcom/pico/util/IExtBase;')


def ext_impl(interface):
    """Implementation class chosen by factory ExtImplFactory.get: IExtX -> ExtXImpl, nested
    Outer$IExtY -> OuterImpl$ExtYImpl, both after replacing IExt with Ext."""
    name = interface[1:-1]
    if '$' in name:
        outer, simple = name.rsplit('$', 1)
        return 'L' + outer.replace('IExt', 'Ext') + 'Impl$' + simple.replace('IExt', 'Ext') + 'Impl;'
    return 'L' + name.replace('IExt', 'Ext') + 'Impl;'


def uleb(data, offset):
    value = shift = 0
    while True:
        byte = data[offset]
        offset += 1
        value |= (byte & 127) << shift
        if byte < 128:
            return value, offset
        shift += 7


class Dex:
    """Minimal standard DEX reader: identifiers, class definitions and code references."""

    def __init__(self, data):
        if not data.startswith(b'dex\n'):
            raise ValueError('Expected standard DEX')
        self.data = data
        n, at = struct.unpack_from('<II', data, 56)
        strings = []
        for index in range(n):
            pos = struct.unpack_from('<I', data, at + index * 4)[0]
            _, pos = uleb(data, pos)
            strings.append(data[pos:data.index(b'\0', pos)].decode('utf-8', 'replace'))
        self.strings = strings
        n, at = struct.unpack_from('<II', data, 64)
        self.types = [strings[i] for i in struct.unpack_from('<%dI' % n, data, at)] if n else []
        n, at = struct.unpack_from('<II', data, 72)
        self.protos = []
        for index in range(n):
            _, returned, params = struct.unpack_from('<III', data, at + index * 12)
            self.protos.append('(' + ''.join(self.type_list(params)) + ')' + self.types[returned])
        n, at = struct.unpack_from('<II', data, 80)
        self.fields = [(self.types[o], strings[i] + ':' + self.types[t])
                       for o, t, i in (struct.unpack_from('<HHI', data, at + k * 8) for k in range(n))]
        n, at = struct.unpack_from('<II', data, 88)
        self.methods = [(self.types[o], strings[i] + self.protos[p])
                        for o, p, i in (struct.unpack_from('<HHI', data, at + k * 8) for k in range(n))]
        self.class_defs_at = struct.unpack_from('<II', data, 96)

    def type_list(self, offset):
        if not offset:
            return []
        count = struct.unpack_from('<I', self.data, offset)[0]
        return [self.types[i] for i in struct.unpack_from('<%dH' % count, self.data, offset + 4)]

    def classes(self):
        """Yield (descriptor, access, super, interfaces, fields, methods); methods carry code offsets."""
        data = self.data
        n, at = self.class_defs_at
        for index in range(n):
            clazz, access, superclass, interfaces, _, _, class_data, _ = struct.unpack_from('<8I', data, at + index * 32)
            fields, methods = {}, {}
            if class_data:
                sizes = []
                cursor = class_data
                for _ in range(4):
                    value, cursor = uleb(data, cursor)
                    sizes.append(value)
                for count in sizes[:2]:
                    item = 0
                    for _ in range(count):
                        delta, cursor = uleb(data, cursor)
                        item += delta
                        flags, cursor = uleb(data, cursor)
                        fields[self.fields[item][1]] = flags
                for count in sizes[2:]:
                    item = 0
                    for _ in range(count):
                        delta, cursor = uleb(data, cursor)
                        item += delta
                        flags, cursor = uleb(data, cursor)
                        code, cursor = uleb(data, cursor)
                        methods[self.methods[item][1]] = (flags, code)
            yield (self.types[clazz], access, self.types[superclass] if superclass != 0xffffffff else None,
                   self.type_list(interfaces), fields, methods)

    def code_refs(self, code):
        """Return method, field, type and string ids used by one code item, plus
        (field id, class descriptor) pairs where a register filled by new-instance or by
        the PICO ExtImplFactory.getImpl(IExtX.class, ...) result is stored."""
        data = self.data
        size = struct.unpack_from('<I', data, code + 12)[0]
        insns = memoryview(data)[code + 16:code + 16 + size * 2].cast('H')
        methods, fields, types, strings, stores = set(), set(), set(), set(), set()
        created = {}
        interface = impl = None
        pc = 0
        while pc < size:
            unit = insns[pc]
            op = unit & 0xff
            if op == 0 and unit:
                if unit == 0x0100:
                    pc += insns[pc + 1] * 2 + 4
                elif unit == 0x0200:
                    pc += insns[pc + 1] * 4 + 2
                elif unit == 0x0300:
                    width = insns[pc + 1]
                    count = insns[pc + 2] | insns[pc + 3] << 16
                    pc += (count * width + 1) // 2 + 4
                else:
                    pc += 1
                continue
            kind = KIND[op]
            if op in DEST4 or op in DEST8 or op in (0x03, 0x06, 0x09):
                target = (unit >> 8) & 0xf if op in DEST4 else insns[pc + 1] if op in (0x03, 0x06, 0x09) else unit >> 8
                created.pop(target, None)
                if op in WIDE:
                    created.pop(target + 1, None)
            if op == 0x0c and impl:
                created[unit >> 8], impl = impl, None
            if kind == 'method':
                methods.add(insns[pc + 1])
                if op == 0x71 and self.methods[insns[pc + 1]] == FACTORY and interface:
                    impl = ext_impl(self.types[interface])
            elif kind == 'field':
                fields.add(insns[pc + 1])
                register = (unit >> 8) & 0xf if op == 0x5b else unit >> 8 if op == 0x69 else None
                if register in created:
                    stores.add((insns[pc + 1], created[register]))
            elif kind == 'type':
                types.add(insns[pc + 1])
                if op == 0x22:
                    created[unit >> 8] = self.types[insns[pc + 1]]
                elif op == 0x1c:
                    interface = insns[pc + 1]
            elif kind == 'string':
                strings.add(insns[pc + 1] if op == 0x1a else insns[pc + 1] | insns[pc + 2] << 16)
            pc += WIDTH[op]
        return methods, fields, types, strings, stores


def dex_blobs(path):
    with zipfile.ZipFile(path) as archive:
        names = sorted((n for n in archive.namelist() if re.fullmatch(r'classes\d*\.dex', n)),
                       key=lambda n: int(n[7:-4] or 1))
        return [archive.read(name) for name in names]


def hierarchy(paths, definers=None):
    """Class declarations of a class loader chain; the first definition wins, as at runtime."""
    result = {}
    for path in paths:
        if not path.exists():
            continue
        for blob in dex_blobs(path):
            for clazz, access, superclass, interfaces, fields, methods in Dex(blob).classes():
                if definers is not None:
                    definers[clazz].append('/system/' + str(path).split('/system/', 1)[-1])
                if clazz not in result:
                    result[clazz] = {'super': superclass, 'interfaces': interfaces, 'access': access,
                                     'fields': fields, 'methods': {k: v[0] for k, v in methods.items()},
                                     'jar': str(path)}
    return result


def resolve(owner, member, kind, chains):
    """Find the declaring class of a member reference in a sequence of class maps."""
    def lookup(clazz):
        for chain in chains:
            if clazz in chain:
                return chain[clazz]
        return None
    seen, pending, interfaces = set(), [owner], []
    while pending:
        clazz = pending.pop(0)
        if clazz in seen:
            continue
        seen.add(clazz)
        record = lookup(clazz)
        if record is None:
            continue
        if member in record[kind]:
            return clazz
        interfaces.extend(record['interfaces'])
        if record['super']:
            pending.append(record['super'])
        if not pending and interfaces:
            pending, interfaces = interfaces, []
    return None


# Globals shared with forked workers.
G = {}


def load_candidates():
    gaps = json.loads((ROOT / 'API-GAPS.json').read_text())
    candidates = {}
    for jar, data in gaps['jars'].items():
        for clazz in data['classes_added_in_factory_jar']:
            candidates[(jar, 'class', clazz)] = {}
        natives = {(c, m) for c, ms in data['added_native_declarations'].items() for m in ms}
        for clazz, delta in data['existing_class_declaration_changes'].items():
            for kind in ['methods', 'fields']:
                change = delta.get(kind, {})
                for member in change.get('added_in_factory', []):
                    candidates[(jar, kind[:-1], clazz + '->' + member)] = {'native': (clazz, member) in natives}
                for member, flags in change.get('access_flags_changed', {}).items():
                    if flags['factory'] & 1 and not flags['aosp'] & 1:
                        candidates[(jar, kind[:-1] + '_visibility', clazz + '->' + member)] = {}
    return gaps, candidates


def factory_file(path):
    for base in [FACTORY_TREE, FACTORY_TREE / 'system']:
        candidate = base / path.lstrip('/')
        if candidate.is_file() and not candidate.is_symlink():
            return candidate
    raise FileNotFoundError(path)


def extract_partitions():
    """Read-only debugfs rdump of verified product/vendor/odm images into a cache."""
    verified = json.loads((ROOT / 'reports/baseline-5.13.7/verification.json').read_text())
    PARTITIONS.mkdir(parents=True, exist_ok=True)
    for partition in ['product', 'vendor', 'odm']:
        marker = PARTITIONS / (partition + '.json')
        expected = verified['images'][partition]['sha256']
        if marker.exists() and json.loads(marker.read_text())['image_sha256'] == expected:
            continue
        image = pico.PROJECT / 'stock/5.13.7-SEKO' / (partition + '.img')
        if pico.digest(image) != expected:
            raise RuntimeError('Factory partition changed: ' + partition)
        target = PARTITIONS / partition
        if target.exists():
            raise RuntimeError('Preserve unverified partition cache: ' + str(target))
        target.mkdir()
        subprocess.run(['/usr/sbin/debugfs', '-R', f'rdump / "{target}"', str(image)],
                       check=True, capture_output=True, text=True)
        inventory = json.loads((ROOT / f'reports/baseline-5.13.7/{partition}-files.json').read_text())
        for entry in inventory:
            if entry['mode'].startswith('100'):
                local = target / entry['path'].lstrip('/')
                if not local.is_file() or local.stat().st_size != entry['bytes']:
                    raise RuntimeError('Incomplete partition extraction: ' + partition + entry['path'])
        marker.write_text(json.dumps({'image_sha256': expected, 'files_checked': True}) + '\n')


def inventory():
    """Factory DEX containers and ELF files with their device paths."""
    containers, elves = [], []
    roots = [('', FACTORY_TREE)] + [('/' + p, PARTITIONS / p) for p in ['product', 'vendor', 'odm']]
    for prefix, base in roots:
        for directory, dirnames, files in os.walk(base):
            if prefix == '' and Path(directory) == FACTORY_TREE:
                dirnames[:] = [d for d in dirnames if d == 'system']
            for name in files:
                local = Path(directory) / name
                if local.is_symlink():
                    continue
                device = prefix + '/' + str(local.relative_to(base))
                if prefix == '' and device.startswith('/system/product/'):
                    continue
                if name.endswith(('.apk', '.jar')):
                    containers.append((device, str(local)))
                elif name.endswith('.so') or '/bin/' in device:
                    with local.open('rb') as stream:
                        if stream.read(4) == b'\x7fELF':
                            elves.append((device, str(local)))
    return sorted(containers), sorted(elves)


def scan_container(item):
    """References from one APK/JAR to candidate classes/members, attributed to referring methods."""
    device, local = item
    boot = G['factory_boot']
    server_scope = device in G['server_jars'] or device == '/system/framework/services.jar'
    chains = [boot, G['factory_server']] if server_scope else [boot]
    try:
        blobs = dex_blobs(local)
    except zipfile.BadZipFile:
        return device, {'error': 'bad zip'}
    if not blobs:
        return device, {'dex': 0}
    dexes = [Dex(blob) for blob in blobs]
    own = {}
    parsed = []
    for dex in dexes:
        for record in dex.classes():
            parsed.append((dex, record))
            clazz = record[0]
            # A class counts when this container supplies the runtime definition: it is absent
            # from the parent loaders, or this JAR is the classpath entry that defines it first.
            winner = next((chain[clazz]['jar'] for chain in chains if clazz in chain), None)
            if device in PAIR or winner is None or winner == local:
                own.setdefault(clazz, {'super': record[2], 'interfaces': record[3], 'fields': record[4],
                                       'methods': {k: v[0] for k, v in record[5].items()}})
    local_chains = chains if device in PAIR else [own] + chains
    # Application class loaders see only the boot classpath; services.jar candidates are
    # reachable from the system_server class path alone.
    classes = G['class_names'] if server_scope or device in PAIR else G['boot_class_names']
    members = G['members'] if server_scope or device in PAIR else G['boot_members']
    stores = defaultdict(set)
    dotted = G['dotted']
    hits = defaultdict(lambda: defaultdict(set))
    member_cache = {}

    def member_target(owner, member, kind):
        key = (owner, member, kind)
        if key not in member_cache:
            declaring = resolve(owner, member, kind, local_chains)
            member_cache[key] = declaring
        return member_cache[key]

    def note(key, referrer, how):
        if device in PAIR or key[1].split('->')[0] not in own:
            hits[key][how].add(referrer)

    for dex, (clazz, access, superclass, interfaces, fields, methods) in parsed:
        if device not in PAIR and clazz not in own:
            continue
        header = clazz + '<class>'
        for t in [superclass] + interfaces + [f.split(':', 1)[1].lstrip('[') for f in fields]:
            if t in classes:
                note(('class', t), header, 'declaration')
        for signature, (flags, code) in methods.items():
            referrer = clazz + '->' + signature
            for t in re.findall(r'L[^;]+;', signature[signature.index('('):]):
                if t in classes:
                    note(('class', t), referrer, 'signature')
            if device not in PAIR and not flags & 0x0a and not signature.startswith('<'):
                declaring = resolve(superclass, signature, 'methods', local_chains) if superclass else None
                if declaring and ('method', declaring + '->' + signature) in members:
                    note(('method', declaring + '->' + signature), referrer, 'override')
            if not code:
                continue
            m_ids, f_ids, t_ids, s_ids, stored = dex.code_refs(code)
            if device in PAIR:
                for field_index, created in stored:
                    if created in classes:
                        owner, member = dex.fields[field_index]
                        declaring = member_target(owner, member, 'fields') or owner
                        stores[referrer].add((declaring + '->' + member, created))
            for index in t_ids:
                t = dex.types[index].lstrip('[')
                if t in classes:
                    note(('class', t), referrer, 'code')
            for kind, table, ids in (('methods', dex.methods, m_ids), ('fields', dex.fields, f_ids)):
                for index in ids:
                    owner, member = table[index]
                    owner = owner.lstrip('[')
                    if owner in classes:
                        note(('class', owner), referrer, 'code')
                    if owner not in G['member_owners'] and owner not in own:
                        continue
                    declaring = member_target(owner, member, kind)
                    if declaring is None:
                        continue
                    if declaring in classes and declaring != owner:
                        note(('class', declaring), referrer, 'code')
                    key = (kind[:-1], declaring + '->' + member)
                    if key in members:
                        note(key, referrer, 'code')
                    visibility = (kind[:-1] + '_visibility', declaring + '->' + member)
                    if visibility in members:
                        note(visibility, referrer, 'code')
            # Dotted names are unscoped on purpose: an application string naming a system_server
            # class is usually its Binder interface descriptor, which still needs that service.
            names = [dex.strings[i] for i in s_ids]
            named = {dotted[s] for s in names if s in dotted}
            named |= {s for s in names if s in classes}
            for owned in named:
                note(('class', owned), referrer, 'string')
            owners = named | {dex.types[i] for i in t_ids}
            for s in names:
                for owner in G['member_names'].get(s, ()):
                    if owner[0] in owners:
                        note((owner[1], owner[0] + '->' + owner[2]), referrer, 'reflection_string')
    result = {'dex': len(blobs), 'hits': {},
              'stores': {k: sorted(v) for k, v in stores.items()}}
    for key, kinds in hits.items():
        result['hits']['|'.join(key)] = {how: sorted(referrers) for how, referrers in kinds.items()}
    return device, result


STRINGS = re.compile(rb'[\x20-\x7e]{3,}')


def scan_elf(item):
    """JNI evidence: class/member/descriptor strings; imports from replaced runtime libraries."""
    device, local = item
    data = Path(local).read_bytes()
    strings = set(STRINGS.findall(data))
    evidence = {}
    for clazz, slash in G['slash_classes'].items():
        if slash in strings:
            evidence.setdefault('class|' + clazz, []).append('class_string')
    for key, (slash, name, descriptor) in G['jni_members'].items():
        if slash in strings and name in strings and descriptor in strings:
            evidence.setdefault(key, []).append('jni_name_and_descriptor')
    imports = {}
    try:
        needed = pico.needed(Path(local))
    except subprocess.CalledProcessError:
        needed = []
    wanted = [lib for lib in needed if lib in NATIVE_LIBRARIES]
    if wanted:
        _, undefined, weak = pico.read_symbols(Path(local))
        imports = {'needed': wanted, 'undefined': sorted(undefined | weak)}
    return device, {'evidence': evidence, 'imports': imports, 'is64': data[4] == 2}


def native_exports(root):
    result = {}
    for bits, directory in [(64, 'lib64'), (32, 'lib')]:
        for lib in NATIVE_LIBRARIES:
            path = root / directory / lib
            if path.exists():
                defined, _, _ = pico.read_symbols(path)
                result[(bits, lib)] = defined
    return result


def counterpart(device):
    return (SOURCE_PRODUCT / device.lstrip('/')).exists()


def classify_consumer(device, packages):
    if device in PAIR:
        return 'ported_pair'
    if device in G['extra_classpath']:
        # Source builds its own telephony-common, wifi-service, ...; their factory
        # references describe OEM changes of those JARs, not a preserved consumer.
        return 'source_counterpart_classpath_jar' if counterpart(device) else 'preserved_factory_classpath_jar'
    if device.endswith('.apk'):
        return 'factory_app'
    if device.endswith('.jar'):
        return 'factory_jar'
    return 'factory_elf'


def main():
    pico.guard_volume()
    gaps, candidates = load_candidates()
    extract_partitions()
    device_paths = json.loads((ROOT / 'reports/device/classpaths.json').read_text())
    factory_boot_paths = [p for p in device_paths['BOOTCLASSPATH'] if not p.startswith('/apex/')]
    factory_server_paths = device_paths['SYSTEMSERVERCLASSPATH']
    definers = defaultdict(list)
    G['factory_boot'] = hierarchy([factory_file(p) for p in factory_boot_paths], definers)
    G['factory_server'] = hierarchy([factory_file(p) for p in factory_server_paths], definers)
    G['server_jars'] = set(factory_server_paths)
    G['extra_classpath'] = {p for p in factory_boot_paths + factory_server_paths} - PAIR
    environ = (SOURCE_PRODUCT / 'root/init.environ.rc').read_text()
    source_boot = re.search(r'export BOOTCLASSPATH (\S+)', environ).group(1).split(':')
    source_server = re.search(r'export SYSTEMSERVERCLASSPATH (\S+)', environ).group(1).split(':')

    def source_file(path):
        if path.startswith('/apex/com.android.runtime/'):
            path = path.replace('/apex/com.android.runtime/', '/system/apex/com.android.runtime.debug/')
        elif path.startswith('/apex/'):
            path = '/system' + path
        return SOURCE_PRODUCT / path.lstrip('/')
    source_boot_map = hierarchy([source_file(p) for p in source_boot])
    source_server_map = hierarchy([source_file(p) for p in source_server])

    class_names = {key[2] for key in candidates if key[1] == 'class'}
    members = {(key[1], key[2]) for key in candidates if key[1] != 'class'}
    G['class_names'] = class_names
    G['members'] = members
    G['boot_class_names'] = {key[2] for key in candidates if key[1] == 'class' and key[0] == 'framework.jar'}
    G['boot_members'] = {(key[1], key[2]) for key in candidates if key[1] != 'class' and key[0] == 'framework.jar'}
    G['member_owners'] = {m.split('->')[0] for _, m in members} | set(G['factory_boot']) | set(G['factory_server'])
    G['dotted'] = {c[1:-1].replace('/', '.'): c for c in class_names}
    names = defaultdict(set)
    for kind, member in members:
        owner, rest = member.split('->')
        name = re.split(r'[(:]', rest)[0]
        if len(name) > 3 and not name.startswith(('<', 'access$', 'lambda$')):
            names[name].add((owner, kind, rest))
    G['member_names'] = names
    G['slash_classes'] = {c: c[1:-1].encode() for c in class_names if '$$Lambda$' not in c}
    jni = {}
    for kind, member in members:
        owner, rest = member.split('->')
        if kind == 'method':
            name, descriptor = rest[:rest.index('(')], rest[rest.index('('):]
        elif kind == 'field':
            name, descriptor = rest.split(':', 1)
        else:
            continue
        if len(name) > 3:
            jni[kind + '|' + member] = (owner[1:-1].encode(), name.encode(), descriptor.encode())
    G['jni_members'] = jni

    containers, elves = inventory()
    print(json.dumps({'containers': len(containers), 'elf_files': len(elves), 'candidates': len(candidates)}), flush=True)
    with multiprocessing.get_context('fork').Pool(WORKERS) as pool:
        dex_results = {}
        for count, (device, result) in enumerate(pool.imap_unordered(scan_container, containers, chunksize=1), 1):
            dex_results[device] = result
            if count % 25 == 0:
                print(json.dumps({'containers_scanned': count}), flush=True)
        elf_results = {}
        for count, (device, result) in enumerate(pool.imap_unordered(scan_elf, elves, chunksize=8), 1):
            elf_results[device] = result
            if count % 500 == 0:
                print(json.dumps({'elf_scanned': count}), flush=True)

    packages = {}
    for report in ['reports/vr-integration/factory-apks.json', 'reports/vr-integration/additional-factory-apks.json']:
        for package in json.loads((ROOT / report).read_text())['packages']:
            packages[package['path']] = package['package']

    # Per-candidate consumer lists.
    consumers = defaultdict(list)
    for device, result in dex_results.items():
        for key, kinds in result.get('hits', {}).items():
            referrers = sorted({r for rs in kinds.values() for r in rs})
            consumers[key].append({'consumer': device, 'package': packages.get(device),
                                   'category': classify_consumer(device, packages),
                                   'source_counterpart_built': counterpart(device),
                                   'kinds': sorted(kinds), 'referrer_count': len(referrers),
                                   'referrers': referrers if device in PAIR else referrers[:MAX_REFERRERS]})
    for device, result in elf_results.items():
        # A factory ELF that Source builds at the same path (JNI/runtime libraries) is the
        # counterpart of the ported framework, not a preserved consumer.
        category = 'source_replaced_elf' if counterpart(device) else 'factory_elf'
        for key, kinds in result['evidence'].items():
            consumers[key].append({'consumer': device, 'category': category, 'kinds': kinds,
                                   'referrer_count': 0, 'referrers': []})

    def defined_in_source(jar, kind, name):
        maps = [source_boot_map] + ([source_server_map] if jar == 'services.jar' else [])
        if kind == 'class':
            for chain in maps:
                if name in chain:
                    return chain[name]['jar'].split('/system/', 1)[-1]
            return None
        owner, member = name.split('->')
        plural = 'methods' if kind.startswith('method') else 'fields'
        declaring = resolve(owner, member, plural, maps)
        if declaring is None:
            return None
        if kind.endswith('_visibility'):
            record = next(chain[declaring] for chain in maps if declaring in chain)
            if not record[plural][member] & 1:
                return None
        return declaring + ' (' + next(chain[declaring]['jar'] for chain in maps if declaring in chain).split('/system/', 1)[-1] + ')'

    # Transitive closure: referrers inside the ported pair propagate need from needed candidates.
    # A needed field also needs the added classes instantiated by the pair methods storing it,
    # e.g. ActivityInfo.mExt -> ExtActivityInfoImpl created in the ActivityInfo constructors.
    stored = defaultdict(list)
    for device in PAIR:
        for method, pairs in dex_results.get(device, {}).get('stores', {}).items():
            for field, clazz in pairs:
                stored[clazz].append((field, method))
    keys = {key: '|'.join(key[1:]) for key in candidates}

    def host(key):
        name = key[2].split('->')[0]
        outer = re.sub(r'\$.*;$', ';', name)
        return name, outer

    decisions = {}
    for key in candidates:
        external = [c for c in consumers.get(keys[key], []) if c['category'] not in INTERNAL]
        cats = {c['category'] for c in external}
        if defined_in_source(key[0], key[1], key[2]):
            decisions[key] = 'present_in_source'
        elif cats - {'preserved_factory_classpath_jar'}:
            decisions[key] = 'needed'
        elif cats:
            decisions[key] = 'needed_by_preserved_factory_component'
        else:
            decisions[key] = None
    rank = {'needed': 2, 'needed_by_preserved_factory_component': 1}
    index = {}
    for key in candidates:
        if key[1] == 'class':
            index.setdefault(('class', key[2]), key)
        else:
            index.setdefault((key[1], key[2]), key)
    changed = True
    via = {}
    while changed:
        changed = False
        for key in candidates:
            if decisions[key] in ('present_in_source', 'needed'):
                continue
            best = rank.get(decisions[key], 0)
            reason = None
            internal = [c for c in consumers.get(keys[key], []) if c['category'] == 'ported_pair']
            for consumer in internal:
                for referrer in consumer['referrers']:
                    owner = referrer.split('->')[0].split('<')[0]
                    owner = owner if owner.endswith(';') else owner
                    sources = [index.get(('class', owner)), index.get(('class', re.sub(r'\$.*;$', ';', owner)))]
                    if '->' in referrer:
                        sources.append(index.get(('method', referrer)))
                    for source in filter(None, sources):
                        level = rank.get(decisions.get(source), 0)
                        if level > best:
                            best, reason = level, referrer
            if key[1] == 'class':
                for field, method in stored.get(key[2], ()):
                    source = index.get(('field', field)) or index.get(('class', field.split('->')[0]))
                    if source and source != key and rank.get(decisions.get(source), 0) > best:
                        best, reason = rank[decisions[source]], method + ' (stores it in ' + field + ')'
            # Members and inner/lambda classes of a needed added class follow the class.
            name, outer = host(key)
            for owner in {name, outer}:
                source = index.get(('class', owner))
                if source and source != key and rank.get(decisions.get(source), 0) > best:
                    best, reason = rank[decisions[source]], owner + ' (enclosing added class)'
            if best > rank.get(decisions[key], 0):
                decisions[key] = [None, 'needed_by_preserved_factory_component', 'needed'][best]
                via[key] = reason
                changed = True

    entries = []
    for key in sorted(candidates):
        items = consumers.get(keys[key], [])
        internal = [c for c in items if c['category'] == 'ported_pair']
        native_side = [c['consumer'] for c in items if c['category'] == 'source_replaced_elf']
        counterparts = sorted({c['consumer'] for c in items if c['category'] == 'source_counterpart_classpath_jar'})
        external = [c for c in items if c['category'] not in INTERNAL]
        decision = decisions[key]
        if decision is None:
            decision = 'not_needed'
            reason = ('only referenced inside factory framework/services by code that is not required by any consumer'
                      if internal else 'no static reference by any factory consumer or ELF')
        elif decision == 'present_in_source':
            reason = 'defined or inherited in Source effective classpath: ' + defined_in_source(key[0], key[1], key[2])
        elif key in via:
            reason = 'required transitively by ' + via[key]
        else:
            reason = 'referenced by ' + ', '.join(sorted({c['category'] for c in external}))
        text = key[2] + ' ' + ' '.join(c['consumer'] + ' ' + (c.get('package') or '') for c in external)
        entry = {'jar': key[0], 'kind': key[1], 'name': key[2], 'decision': decision, 'reason': reason,
                 'vr_related': bool(VR.search(text)),
                 'compiler_generated': bool(re.search(r'\$\$Lambda\$|lambda\$|access\$|\$\d+;|-\$\$', key[2])),
                 'external_consumers': external,
                 'factory_definers': definers.get(key[2], []) if key[1] == 'class' else None,
                 'internal_referrer_count': sum(c['referrer_count'] for c in internal),
                 'internal_referrers': sorted({r for c in internal for r in c['referrers']})[:MAX_REFERRERS]}
        if counterparts:
            entry['source_counterpart_jar_referrers'] = counterparts
        if native_side:
            entry['source_replaced_elf_evidence'] = native_side
        if candidates[key].get('native'):
            entry['native'] = True
        entries.append(entry)

    # Native imports of runtime libraries that Source replaces.
    source_exports = native_exports(SOURCE_PRODUCT / 'system')
    factory_exports = native_exports(FACTORY_TREE / 'system')
    native_gaps = defaultdict(lambda: {'consumers': set()})
    for device, result in elf_results.items():
        imports = result['imports']
        if not imports:
            continue
        bits = 64 if result['is64'] else 32
        for symbol in imports['undefined']:
            base = symbol.split('@')[0]
            for lib in imports['needed']:
                if base in factory_exports.get((bits, lib), ()) and base not in source_exports.get((bits, lib), ()):
                    native_gaps[(bits, lib, base)]['consumers'].add((device, counterpart(device)))
    native_rows = [{'abi': 'arm64' if bits == 64 else 'arm', 'library': lib, 'symbol': symbol, 'demangled': None,
                    'factory_only_consumers': sorted(d for d, built in value['consumers'] if not built),
                    'source_replaced_consumers': sorted(d for d, built in value['consumers'] if built),
                    'vr_related': bool(VR.search(' '.join(d for d, _ in value['consumers']) + symbol))}
                   for (bits, lib, symbol), value in sorted(native_gaps.items())]
    for row in native_rows:
        row['decision'] = 'needed' if row['factory_only_consumers'] else 'not_needed_if_consumers_replaced_by_source'
    if native_rows:
        demangled = subprocess.run(['c++filt'], input='\n'.join(r['symbol'] for r in native_rows),
                                   capture_output=True, text=True, check=True).stdout.splitlines()
        for row, name in zip(native_rows, demangled):
            row['demangled'] = name

    def group(name):
        package = name.split('->')[0][1:-1].split('/')[:-1]
        return '.'.join(package[:3] if package[0] == 'com' else package[:2])

    groups = defaultdict(lambda: defaultdict(int))
    for entry in entries:
        g = groups[(entry['jar'], group(entry['name']))]
        g[entry['decision']] += 1
        g['total'] += 1
        if entry['vr_related'] and entry['decision'].startswith('needed'):
            g['vr_related_needed'] += 1
    decision_totals = defaultdict(lambda: defaultdict(int))
    for entry in entries:
        decision_totals[entry['jar'] + ' ' + entry['kind']][entry['decision']] += 1
    consumer_totals = defaultdict(lambda: defaultdict(int))
    for entry in entries:
        if entry['decision'] in ('needed', 'needed_by_preserved_factory_component'):
            for c in entry['external_consumers']:
                consumer_totals[c['consumer']][entry['kind']] += 1

    # All native declarations of API-NATIVE-GAPS.md; those in added classes follow the class.
    decided = {(entry['jar'], entry['kind'], entry['name']): entry for entry in entries}
    natives = []
    for jar, data in gaps['jars'].items():
        for clazz, signatures in sorted(data['added_native_declarations'].items()):
            for signature in signatures:
                entry = decided.get((jar, 'method', clazz + '->' + signature)) or decided[(jar, 'class', clazz)]
                natives.append({'jar': jar, 'method': clazz + '->' + signature, 'decision': entry['decision'],
                                'decided_by': entry['kind'], 'reason': entry['reason']})
    report = {
        'snapshot': gaps['snapshot'], 'pico_build': gaps['pico_build'], 'aosp_tag': gaps['aosp_tag'],
        'api_gaps_sha256': hashlib.sha256((ROOT / 'API-GAPS.json').read_bytes()).hexdigest(),
        'source_component_commits': gaps['source_component_commits'],
        'factory_system_image_sha256': json.loads((pico.REPORTS / 'factory-system.json').read_text())['image_sha256'],
        'factory_effective_classpath': {'boot': factory_boot_paths, 'system_server': factory_server_paths,
                                        'apex_boot_jars_not_scanned': [p for p in device_paths['BOOTCLASSPATH'] if p.startswith('/apex/')]},
        'source_effective_classpath': {'boot': source_boot, 'system_server': source_server},
        'decision_definitions': {
            'needed': 'statically referenced (code, override, declaration, reflection string or JNI name+descriptor) by a factory APK, a JAR outside the effective classpath, or a factory ELF; or required by such a candidate',
            'needed_by_preserved_factory_component': 'referenced only by factory classpath JARs outside framework/services (sys-*, sysmonitor-*, vrex-*, devicemiddlewareimpl, Qualcomm boot JARs); needed if those JARs are preserved instead of ported',
            'not_needed': 'no static consumer outside factory framework/services; internal referrers, factory JARs/ELF that Source rebuilds at the same path (source_counterpart_jar_referrers, source_replaced_elf_evidence) and behavioural hooks are listed but do not create need',
            'present_in_source': 'class defined in another JAR of the Source effective classpath, or member resolved through a Source superclass/interface'},
        'scope': {'dex_containers': len(containers), 'containers_with_dex': sum(1 for r in dex_results.values() if r.get('dex')),
                  'elf_files': len(elves), 'candidates': len(candidates), 'native_import_libraries': NATIVE_LIBRARIES,
                  'partitions': ['system', 'product', 'vendor', 'odm']},
        'limitations': [
            'Static analysis: runtime-built names, inlined static final constants, resources and manifest permission strings are not traced.',
            'APEX payload JARs and APK split/dynamic code downloaded at runtime are not scanned.',
            'ELF JNI evidence is string co-occurrence of class, name and descriptor, not a decoded registration table.',
            'not_needed does not remove behavioural hooks inside ported framework/services methods, for example the VR skip-draw policy.',
            'A consumer reference proves linkage need, not that the consumer path is exercised during VR use.'],
        'summary': {'by_jar_and_kind': {k: dict(v) for k, v in sorted(decision_totals.items())},
                    'groups': [{'jar': jar, 'group': name, **dict(values)} for (jar, name), values in sorted(groups.items())],
                    'top_consumers': [{'consumer': c, 'package': packages.get(c), **dict(v)} for c, v in
                                      sorted(consumer_totals.items(), key=lambda kv: -sum(kv[1].values()))[:40]],
                    'native_import_gaps': len(native_rows),
                    'native_declarations': dict(sorted(Counter(row['decision'] for row in natives).items()))},
        'native_declarations': natives,
        'candidates': entries,
        'native_import_gaps': native_rows,
        'containers_without_dex': sorted(d for d, r in dex_results.items() if not r.get('dex')),
        'headset_modified': False,
    }
    # One compact line per candidate/native row keeps the report reviewable in Git diffs.
    lines = []
    for name, value in report.items():
        if name in ('candidates', 'native_import_gaps', 'native_declarations'):
            rows = ',\n'.join('  ' + json.dumps(row, separators=(',', ':')) for row in value)
            lines.append(' ' + json.dumps(name) + ': [\n' + rows + '\n ]')
        else:
            lines.append(' ' + json.dumps(name) + ': ' + json.dumps(value, indent=1).replace('\n', '\n '))
    REPORT.write_text('{\n' + ',\n'.join(lines) + '\n}\n')
    json.loads(REPORT.read_text())
    print(json.dumps(report['summary']['by_jar_and_kind'], indent=1))
    print(json.dumps({'native_import_gaps': len(native_rows)}))


if __name__ == '__main__':
    main()
