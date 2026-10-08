"""Check factory class path JARs against the Source build (config-driven).

Generalises tools/check-factory-bluetooth.py for JARs on the boot and system
server class paths. The config (default device/pico/PICOA8110/factory-bootclasspath.json)
lists every factory 5.13.7 class path JAR that is not part of AOSP, with its
provenance and decision:
  factory_binary        - the factory DEX is installed unchanged (dex_import);
  codelinaro_source     - built from the CodeLinaro donor, compared with the factory DEX;
  not_on_source_classpath - left out of the Source class paths (gaps reported only).

For each JAR the check covers, statically and against the built Source product:
- class path: Source init.environ.rc BOOTCLASSPATH/DEX2OATBOOTCLASSPATH/
  SYSTEMSERVERCLASSPATH equal the factory order for the kept JARs;
- DEX: a kept factory binary is installed with the identical classes.dex; a
  CodeLinaro build is compared class by class (declarations, access flags, static
  values, ordered code references) and by hidden-API flags with the factory DEX;
- linking: every class/method/field reference of the JAR that resolves on the
  factory class path resolves on the Source class path, with the same kind
  (static/instance, class/interface for invoke-interface) and no narrower access;
- class verification: kept classes do not extend final Source classes, do not
  override final Source methods and implement every abstract Source method their
  supertypes declare (as on the factory);
- AIDL: framework Binder interfaces the JAR implements or calls keep the factory
  transaction table;
- hidden API: flags of the JAR's own members (unchanged DEX or equal to factory)
  and the flags of the Source members it uses (informational: boot and system
  server code is not restricted);
- packages: kept boot JAR packages match build/make check_boot_jars whitelist;
- boot image: the Source product contains compiled boot image files for every
  kept boot JAR on both ABIs (factory oat/vdex are not used).
Accepted gaps (listed in the config with the reason) are reported separately and
must match the found gaps exactly. Nothing on the headset is accessed. Run in WSL:
taskset -c 0-7 python3 tools/check-factory-component.py [--config ...] [--planned]
--planned checks before the Source build contains the kept JARs: the planned
Source class paths are assembled from the current Source product plus the
factory files of the kept JARs.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import struct
import zipfile

spec = importlib.util.spec_from_file_location('factory_bluetooth', Path(__file__).with_name('check-factory-bluetooth.py'))
fbt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fbt)
scan, pico = fbt.scan, fbt.pico
spec = importlib.util.spec_from_file_location('pico_api', Path(__file__).with_name('compare-pico-api.py'))
api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(api)

ROOT = pico.ROOT
FACTORY = fbt.FACTORY
SOURCE = fbt.SOURCE
SOURCE_TREE = pico.PROJECT / 'source' / os.environ.get('PICO_SOURCE_TREE', 'aosp-10')
WHITELIST = SOURCE_TREE / 'build/make/core/tasks/check_boot_jars/package_whitelist.txt'
KEPT = ('factory_binary', 'codelinaro_source')

ACC_PUBLIC, ACC_PRIVATE, ACC_PROTECTED, ACC_STATIC, ACC_FINAL = 0x1, 0x2, 0x4, 0x8, 0x10
ACC_INTERFACE, ACC_ABSTRACT = 0x200, 0x400
INVOKE = {0x6e: 'virtual', 0x6f: 'super', 0x70: 'direct', 0x71: 'static', 0x72: 'interface',
          0x74: 'virtual', 0x75: 'super', 0x76: 'direct', 0x77: 'static', 0x78: 'interface'}
HIDDENAPI = {0: 'whitelist', 1: 'greylist', 2: 'blacklist', 3: 'greylist-max-o', 4: 'greylist-max-p',
             5: 'greylist-max-q'}
CORE = ('Ljava/', 'Ljavax/', 'Ldalvik/', 'Llibcore/', 'Lsun/', 'Lorg/json/', 'Lorg/xml/', 'Lorg/w3c/',
        'Lorg/xmlpull/', 'Lorg/apache/harmony/', 'Lcom/android/org/conscrypt/', 'Lorg/apache/http/')


def environ(tree):
    for rc in [tree / 'init.environ.rc', tree / 'root/init.environ.rc', tree / 'system/etc/init.environ.rc']:
        if rc.exists():
            text = rc.read_text()
            return {k: v.split(':') for k, v in re.findall(r'export (\w*CLASSPATH) (\S+)', text)}
    raise FileNotFoundError('init.environ.rc in ' + str(tree))


def location_path(tree, location):
    if location.startswith('/apex/'):
        return fbt.java_chain(tree, [location], [])[0][0]
    return tree / location.lstrip('/')


def visibility(flags):
    return 3 if flags & ACC_PUBLIC else 2 if flags & ACC_PROTECTED else 0 if flags & ACC_PRIVATE else 1


def dex_digest(path):
    with zipfile.ZipFile(path) as archive:
        names = sorted(n for n in archive.namelist() if re.fullmatch(r'classes\d*\.dex', n))
        return {n: hashlib.sha256(archive.read(n)).hexdigest() for n in names}


def class_members(dex):
    """Yield (class, access, super, interfaces, [(kind, member, flags, code)]) in class_data order."""
    data = dex.data
    n, at = dex.class_defs_at
    for index in range(n):
        clazz, access, superclass, interfaces, _, _, class_data, _ = struct.unpack_from('<8I', data, at + index * 32)
        members = []
        if class_data:
            sizes, cursor = [], class_data
            for _ in range(4):
                value, cursor = scan.uleb(data, cursor)
                sizes.append(value)
            for group, count in enumerate(sizes):
                item = 0
                for _ in range(count):
                    delta, cursor = scan.uleb(data, cursor)
                    item += delta
                    flags, cursor = scan.uleb(data, cursor)
                    if group < 2:
                        members.append(('fields', dex.fields[item][1], flags, 0))
                    else:
                        code, cursor = scan.uleb(data, cursor)
                        members.append(('methods', dex.methods[item][1], flags, code))
        yield (dex.types[clazz], access, dex.types[superclass] if superclass != 0xffffffff else None,
               dex.type_list(interfaces), members, index)


def hiddenapi_flags(path):
    """Hidden-API flags encoded in the DEX (map item 0xF000), {Lclass;->member: name}."""
    result = {}
    for blob in scan.dex_blobs(path):
        dex = scan.Dex(blob)
        map_off = struct.unpack_from('<I', blob, 52)[0]
        count = struct.unpack_from('<I', blob, map_off)[0]
        section = None
        for i in range(count):
            kind, _, _, offset = struct.unpack_from('<HHII', blob, map_off + 4 + i * 12)
            if kind == 0xf000:
                section = offset
        if section is None:
            continue
        for clazz, _, _, _, members, index in class_members(dex):
            offset = struct.unpack_from('<I', blob, section + 4 + index * 4)[0]
            if not offset:
                continue
            cursor = section + offset
            for kind, member, _, _ in members:
                value, cursor = scan.uleb(blob, cursor)
                name = HIDDENAPI.get(value & 7, str(value & 7))
                if value >> 3:
                    name += '+domain%d' % (value >> 3)
                result[clazz + '->' + member] = name
    return result


def jar_model(path):
    """References and declarations of one JAR."""
    refs, classes = set(), {}
    for blob in scan.dex_blobs(path):
        dex = scan.Dex(blob)
        for clazz, access, superclass, interfaces, members, _ in class_members(dex):
            classes[clazz] = {'access': access, 'super': superclass, 'interfaces': interfaces,
                              'methods': {m: f for k, m, f, _ in members if k == 'methods'},
                              'fields': {m: f for k, m, f, _ in members if k == 'fields'}}
            for base in [superclass] + interfaces:
                if base:
                    refs.add(('class', base, None, 'extends', clazz))
            for kind, member, flags, code in members:
                if kind != 'methods' or not code:
                    continue
                for ref in code_refs(dex, code):
                    refs.add(ref + (clazz,))
    own = set(classes)
    return {r for r in refs if r[1] not in own and r[1].startswith('L')}, classes


def code_refs(dex, code):
    data = dex.data
    size = struct.unpack_from('<I', data, code + 12)[0]
    insns = memoryview(data)[code + 16:code + 16 + size * 2].cast('H')
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
        if op in INVOKE:
            owner, member = dex.methods[insns[pc + 1]]
            yield ('methods', owner.lstrip('['), member, INVOKE[op])
        elif 0x52 <= op <= 0x6d:
            owner, member = dex.fields[insns[pc + 1]]
            yield ('fields', owner, member, 'static' if op >= 0x60 else 'instance')
        elif op in (0x1c, 0x1f, 0x20, 0x22, 0x23, 0x24, 0x25):
            clazz = dex.types[insns[pc + 1]].lstrip('[')
            if clazz.startswith('L'):
                yield ('class', clazz, None, 'code')
        pc += scan.WIDTH[op]


def resolve(chain, owner, member, kind):
    declaring = scan.resolve(owner, member, kind, [chain])
    return (declaring, chain[declaring][kind][member]) if declaring else (None, None)


def link_problem(ref, fchain, schain):
    """Return None when ref links on Source as on factory, else a short reason."""
    kind, owner, member, how, caller = ref
    if kind == 'class':
        if owner not in fchain or owner.startswith(CORE):
            return None
        if owner not in schain:
            return 'missing class'
        f, s = fchain[owner]['access'], schain[owner]['access']
        if f & ACC_PUBLIC and not s & ACC_PUBLIC and owner.rsplit('/', 1)[0] != caller.rsplit('/', 1)[0]:
            return 'class not public'
        if how == 'extends' and s & ACC_FINAL and not f & ACC_FINAL:
            return 'extends final class'
        if how == 'extends' and (s & ACC_INTERFACE) != (f & ACC_INTERFACE):
            return 'class/interface kind differs'
        return None
    fdecl, fflags = resolve(fchain, owner, member, kind)
    if fdecl is None or owner.startswith(CORE):
        return None
    sdecl, sflags = resolve(schain, owner, member, kind)
    if sdecl is None:
        return 'missing member'
    if bool(fflags & ACC_STATIC) != bool(sflags & ACC_STATIC):
        return 'static/instance differs'
    if how == 'interface' and not schain[owner]['access'] & ACC_INTERFACE:
        return 'invoke-interface on a class'
    if how == 'virtual' and schain[owner]['access'] & ACC_INTERFACE:
        return 'invoke-virtual on an interface'
    if visibility(sflags) < visibility(fflags):
        return 'narrower access'
    return None


def class_problems(classes, fchain, schain):
    """Final supertypes/methods and abstract methods left unimplemented on Source but not on factory."""
    def ancestors(clazz, chain):
        seen, pending, order = set(), [clazz], []
        while pending:
            item = pending.pop(0)
            if item in seen or item not in chain:
                continue
            seen.add(item)
            order.append(item)
            pending += [chain[item]['super']] if chain[item]['super'] else []
            pending += chain[item]['interfaces']
        return order

    def unimplemented(clazz, chain):
        order = ancestors(clazz, chain)
        concrete = {}
        for item in order:
            for member, flags in chain[item]['methods'].items():
                if not flags & ACC_ABSTRACT and not member.startswith('<'):
                    concrete.setdefault(member, item)
        missing = set()
        for item in order:
            for member, flags in chain[item]['methods'].items():
                if flags & ACC_ABSTRACT and member not in concrete:
                    missing.add(item + '->' + member)
        return missing

    problems = {}
    for clazz, record in classes.items():
        issues = []
        if not record['access'] & (ACC_ABSTRACT | ACC_INTERFACE):
            new = unimplemented(clazz, schain) - unimplemented(clazz, fchain)
            issues += ['abstract method not implemented: ' + m for m in sorted(new)]
        for base in ancestors(clazz, schain)[1:]:
            if base in classes:
                continue
            for member, flags in schain[base]['methods'].items():
                ff = fchain.get(base, {}).get('methods', {}).get(member)
                if member in record['methods'] and flags & ACC_FINAL and not (ff or 0) & ACC_FINAL \
                        and not flags & (ACC_PRIVATE | ACC_STATIC) and not member.startswith('<'):
                    issues.append('overrides final ' + base + '->' + member)
        if issues:
            problems[clazz] = issues
    return problems


def whitelist_patterns():
    lines = [line.strip() for line in WHITELIST.read_text().splitlines()
             if line.strip() and not line.startswith('#')]
    return re.compile(r'^(%s)$' % '|'.join(lines))


def boot_image_files(product, jar):
    names = {}
    for abi in ('arm64', 'arm'):
        for suffix in ('art', 'oat'):
            names[abi + '.' + suffix] = (product / 'system/framework' / abi / ('boot-%s.%s' % (jar, suffix))).is_file()
    names['vdex'] = (product / 'system/framework' / ('boot-%s.vdex' % jar)).is_file()
    return names


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--config', type=Path, default=ROOT / 'device/pico/PICOA8110/factory-bootclasspath.json')
    parser.add_argument('--report', type=Path, default=ROOT / 'validation/factory-bootclasspath.json')
    parser.add_argument('--planned', action='store_true')
    args = parser.parse_args()
    pico.guard_volume()
    config = json.loads(args.config.read_text())
    jars = config['jars']
    factory_env = environ(FACTORY)
    source_env = environ(SOURCE)
    kept = [name for name, entry in jars.items() if entry['decision'] in KEPT]
    problems = []

    # Class path composition.
    def expected(variable):
        return [loc for loc in factory_env[variable]
                if Path(loc).stem not in jars or Path(loc).stem in kept]
    classpaths = {}
    for variable in ('BOOTCLASSPATH', 'DEX2OATBOOTCLASSPATH', 'SYSTEMSERVERCLASSPATH'):
        want = expected(variable)
        have = source_env.get(variable, [])
        classpaths[variable] = {'factory': factory_env[variable], 'expected_source': want, 'source': have,
                                'matches': have == want}
        if have != want and not args.planned:
            problems.append('class path order ' + variable)

    def source_location(location):
        stem = Path(location).stem
        path = location_path(SOURCE, location)
        if args.planned and stem in jars and not path.exists():
            return location_path(FACTORY, location)
        return path

    fboot = [location_path(FACTORY, l) for l in factory_env['BOOTCLASSPATH']]
    fserver = [location_path(FACTORY, l) for l in factory_env['SYSTEMSERVERCLASSPATH']]
    sboot_locations = expected('BOOTCLASSPATH') if args.planned else source_env['BOOTCLASSPATH']
    sserver_locations = expected('SYSTEMSERVERCLASSPATH') if args.planned else source_env['SYSTEMSERVERCLASSPATH']
    sboot = [source_location(l) for l in sboot_locations]
    sserver = [source_location(l) for l in sserver_locations]
    missing_source_files = [str(p) for p in sboot + sserver if not p.exists()]
    if missing_source_files:
        problems.append('missing Source class path files')
    fchain_boot, schain_boot = scan.hierarchy(fboot), scan.hierarchy(sboot)
    fchain_all, schain_all = scan.hierarchy(fboot + fserver), scan.hierarchy(sboot + sserver)
    # Not-kept JARs are judged against the Source class paths plus the factory JARs they need.
    extra_factory = [location_path(FACTORY, '/system/framework/%s.jar' % n) for n, e in jars.items()
                     if e['decision'] not in KEPT]
    schain_candidates = scan.hierarchy(sboot + sserver + extra_factory)
    ftables, stables = fbt.aidl_tables(fboot + fserver), fbt.aidl_tables(sboot + sserver)
    fhidden = hiddenapi_flags(location_path(FACTORY, '/system/framework/framework.jar'))
    fhidden.update(hiddenapi_flags(location_path(FACTORY, '/system/framework/services.jar')))
    shidden = hiddenapi_flags(location_path(SOURCE, '/system/framework/framework.jar'))
    whitelist = whitelist_patterns()

    results = {}
    for name, entry in jars.items():
        factory_path = FACTORY / entry['factory_path']
        result = {'classpath': entry['classpath'], 'decision': entry['decision'],
                  'factory_sha256': pico.digest(factory_path)}
        if result['factory_sha256'] != entry['factory_sha256']:
            problems.append(name + ': factory file hash')
        server = entry['classpath'] == 'systemserver'
        fchain = fchain_all if server else fchain_boot
        if entry['decision'] in KEPT:
            schain = schain_all if server else schain_boot
        else:
            schain = schain_candidates
        source_path = SOURCE / 'system/framework' / (name + '.jar')
        checked_path = factory_path
        if entry['decision'] in KEPT:
            if source_path.exists():
                result['source_installed'] = True
                result['source_dex_sha256'] = dex_digest(source_path)
            else:
                result['source_installed'] = False
                if not args.planned:
                    problems.append(name + ': not installed in Source product')
            if entry['decision'] == 'factory_binary':
                result['factory_dex_sha256'] = dex_digest(factory_path)
                result['dex_identical'] = result.get('source_dex_sha256') == result['factory_dex_sha256']
                if result['source_installed'] and not result['dex_identical']:
                    problems.append(name + ': installed DEX differs from factory')
            elif source_path.exists():
                checked_path = source_path
                factory_classes, source_classes = api.load([factory_path]), api.load([source_path])
                names = sorted(set(factory_classes) | set(source_classes))
                rows = api.compare(factory_classes, source_classes, names)
                fh, sh = hiddenapi_flags(factory_path), hiddenapi_flags(source_path)
                flag_diffs = {k: {'factory': fh.get(k), 'source': sh.get(k)}
                              for k in sorted(set(fh) | set(sh)) if fh.get(k) != sh.get(k)}
                result['codelinaro_comparison'] = {
                    'classes': len(rows), 'identical': sum(1 for r in rows if not r['differences']),
                    'differences': {r['class']: r['differences'] for r in rows if r['differences']},
                    'hiddenapi_members': len(fh), 'hiddenapi_differences': flag_diffs}
                if any(r['differences'] for r in rows) or flag_diffs:
                    problems.append(name + ': CodeLinaro build differs from factory')
        refs, classes = jar_model(checked_path)
        link = defaultdict(list)
        for ref in sorted(refs, key=lambda r: (r[1], r[2] or '', r[0], r[3], r[4])):
            reason = link_problem(ref, fchain, schain)
            if reason:
                key = ref[1] + ('->' + ref[2] if ref[2] else '')
                link[key].append({'reason': reason, 'caller': ref[4], 'how': ref[3]})
        accepted = entry.get('accepted_gaps', {})
        found = sorted(link)
        result['references'] = len(refs)
        result['link_gaps'] = {k: {'reasons': sorted({x['reason'] for x in v}),
                                   'callers': sorted({x['caller'] for x in v})[:8]} for k, v in link.items()}
        result['accepted_gaps'] = sorted(k for k in found if k in accepted)
        result['unaccepted_gaps'] = sorted(k for k in found if k not in accepted)
        result['stale_accepted_gaps'] = sorted(k for k in accepted if k not in link)
        result['class_problems'] = class_problems(classes, fchain, schain)
        # AIDL tables of framework interfaces the JAR implements or calls.
        stubs = sorted({o[:-1] + '$Stub;' for _, o, _, _, _ in refs if o[:-1] + '$Stub;' in ftables} |
                       {o for _, o, _, _, _ in refs if o in ftables})
        table_diffs = {}
        for stub in stubs:
            f, s = ftables[stub], stables.get(stub)
            if s != f:
                table_diffs[stub] = sorted(k for k in set(f) | set(s or {}) if f.get(k) != (s or {}).get(k))
        result['aidl_interfaces_checked'] = len(stubs)
        result['aidl_table_differences'] = table_diffs
        # Hidden-API flags of the framework members the JAR uses (informational).
        used = Counter()
        for kind, owner, member, _, _ in refs:
            if member and kind != 'class':
                declaring, _ = resolve(schain, owner, member, kind)
                if declaring:
                    used[shidden.get(declaring + '->' + member, 'not-framework')] += 1
        result['source_member_flags_used'] = dict(sorted(used.items()))
        if entry['classpath'] == 'boot':
            bad = sorted({c.rsplit('/', 1)[0][1:].replace('/', '.') for c in classes
                          if '/' in c and not whitelist.match(c.rsplit('/', 1)[0][1:].replace('/', '.'))})
            result['packages_not_whitelisted'] = bad
            if entry['decision'] in KEPT and bad:
                problems.append(name + ': package whitelist')
            if entry['decision'] in KEPT and not args.planned:
                result['boot_image_files'] = boot_image_files(SOURCE, name)
                if not all(result['boot_image_files'].values()):
                    problems.append(name + ': boot image files')
        result['check_passes'] = not (result['unaccepted_gaps'] or result['stale_accepted_gaps'] or
                                      result['class_problems'] or table_diffs)
        if entry['decision'] in KEPT and not result['check_passes']:
            problems.append(name + ': link check')
        results[name] = result

    report = {'config': str(args.config.relative_to(ROOT)), 'planned': args.planned,
              'factory_tree': str(FACTORY), 'source_product': str(SOURCE),
              'classpaths': classpaths, 'missing_source_files': missing_source_files,
              'factory_framework_hiddenapi_members': len(fhidden), 'jars': results,
              'problems': problems, 'system_partitions_modified': False}
    args.report.write_text(json.dumps(report, indent=1, ensure_ascii=False) + '\n')
    summary = {name: {'decision': r['decision'], 'references': r['references'],
                      'unaccepted_gaps': len(r['unaccepted_gaps']), 'accepted_gaps': len(r['accepted_gaps']),
                      'class_problems': len(r['class_problems']), 'aidl': (r['aidl_interfaces_checked'],
                                                                            sorted(r['aidl_table_differences'])),
                      'passes': r['check_passes']} for name, r in results.items()}
    print(json.dumps({'classpaths': {k: v['matches'] for k, v in classpaths.items()}, 'jars': summary,
                      'problems': problems}, indent=1))


if __name__ == '__main__':
    main()
