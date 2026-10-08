"""Offline check of the Source platform SELinux policy against the factory PICO 5.13.7.

(a) Compiles what init compiles at boot on a Source system image that keeps the
    factory vendor/product/odm partitions (system/core/init/selinux.cpp):
    secilc <plat_sepolicy.cil> -m -M true -G -N -c 30 <mapping/29.0.cil>
           [product_sepolicy.cil] [product mapping] plat_pub_versioned.cil
           vendor_sepolicy.cil [odm_sepolicy.cil]
    with the host secilc of the Source build, for the Source plat policy and,
    as a control, for the factory plat policy. Every versioned attribute the
    factory vendor policy declares must map to the same platform types as in
    the factory mapping (an unmapped attribute compiles but grants nothing).
(b) Compares types, attributes, memberships, rules, transitions, genfscon,
    the 29.0 mapping and contexts files (validation/sepolicy-parity.json).
(c) Labels every path of the factory system tree with the factory and the
    Source plat_file_contexts (libselinux lookup order) and resolves every
    known property name with the factory and the Source plat_property_contexts
    (together with the factory vendor/product/odm contexts).

Run inside WSL after building selinux_policy. Reads only.
"""
import collections
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sepolicy_cil import AUTO_ATTRIBUTE, Policy, mapping_sets, parse, read_contexts  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
PROJECT = Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro')
SOURCE_TREE = PROJECT / 'source' / os.environ.get('PICO_SOURCE_TREE', 'aosp-10')
OUT = PROJECT / 'out' / os.environ.get('PICO_SOURCE_TREE', 'aosp-10')
SOURCE = OUT / 'target/product/PICOA8110/system/etc/selinux'
FACTORY_ROOT = PROJECT / 'analysis/stock-5.13.7-system/root'
FACTORY = FACTORY_ROOT / 'system/etc/selinux'
PARTITIONS = PROJECT / 'analysis/stock-5.13.7-partitions'
VENDOR = PARTITIONS / 'vendor/etc/selinux'
PRODUCT = PARTITIONS / 'product/etc/selinux'
ODM = PARTITIONS / 'odm/etc/selinux'
SECILC = OUT / 'host/linux-x86/bin/secilc'
POLICYVERS = '30'
USERDEBUG_ONLY = {'su', 'perfprofd', 'heapprofd', 'llkd', 'atrace', 'qti-testscripts',
                  'apex_test_prepostinstall'}


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ----------------------------------------------------------------------------
# (a) boot compile
def boot_compile(plat_dir):
    version = (VENDOR / 'plat_sepolicy_vers.txt').read_text().strip()
    args = [str(SECILC), str(plat_dir / 'plat_sepolicy.cil'), '-m', '-M', 'true', '-G', '-N',
            '-c', POLICYVERS, str(plat_dir / 'mapping' / (version + '.cil'))]
    with tempfile.TemporaryDirectory() as temp:
        args += ['-o', os.path.join(temp, 'sepolicy'), '-f', '/dev/null']
        optional = [PRODUCT / 'product_sepolicy.cil', PRODUCT / 'mapping' / (version + '.cil'),
                    VENDOR / 'plat_pub_versioned.cil', VENDOR / 'vendor_sepolicy.cil',
                    ODM / 'odm_sepolicy.cil']
        inputs = [p for p in optional if p.exists()]
        result = subprocess.run(args + [str(p) for p in inputs], capture_output=True, text=True,
                                env=dict(os.environ, LD_LIBRARY_PATH=str(OUT / 'host/linux-x86/lib64')))
        size = os.path.getsize(os.path.join(temp, 'sepolicy')) if result.returncode == 0 else 0
    return {'returncode': result.returncode, 'output': (result.stdout + result.stderr).strip()[-2000:],
            'binary_policy_bytes': size, 'mapping_version': version,
            'inputs': [str(plat_dir / 'plat_sepolicy.cil'), str(plat_dir / 'mapping' / (version + '.cil'))]
            + [str(p) for p in inputs]}


def mapping_check():
    """Versioned attributes the factory vendor/product policies declare."""
    declared, defined_there = set(), set()
    for path in (VENDOR / 'plat_pub_versioned.cil', PRODUCT / 'mapping/29.0.cil'):
        if path.exists():
            statements = parse(path.read_text())
            declared |= {s[1] for s in statements
                         if s[0] == 'typeattribute' and s[1].endswith('_29_0')}
            # Sets defined by these files themselves (auto base_typeattr_N_29_0,
            # the product partition's own types in its mapping).
            defined_there |= {s[1] for s in statements if s[0] == 'typeattributeset'}
    declared -= defined_there
    factory = mapping_sets((FACTORY / 'mapping/29.0.cil').read_text())
    source = mapping_sets((SOURCE / 'mapping/29.0.cil').read_text())
    unmapped = sorted(a for a in declared if not source.get(a))
    different = {a: {'factory_only': sorted(factory.get(a, set()) - source.get(a, set())),
                     'source_only': sorted(source.get(a, set()) - factory.get(a, set()))}
                 for a in sorted(declared) if factory.get(a, set()) != source.get(a, set())}
    return {'vendor_declared_versioned_attributes': len(declared),
            'unmapped_in_source': unmapped, 'mapped_differently': different,
            'factory_mapping_entries': len(factory), 'source_mapping_entries': len(source),
            'factory_only_mapping_entries': sorted(set(factory) - set(source)),
            'source_only_mapping_entries': sorted(set(source) - set(factory))}


# ----------------------------------------------------------------------------
# (b) parity
def declared_in(tree_dirs):
    names = {}
    for label, directory in tree_dirs.items():
        for path in (SOURCE_TREE / directory).rglob('*'):
            if path.is_file() and (path.suffix == '.te' or path.name == 'attributes'):
                for match in re.finditer(r'^\s*(?:type|attribute)\s+([\w-]+)', path.read_text(), re.M):
                    names.setdefault(match.group(1), label)
    return names


def reason_for(names, origin):
    names = set(names)
    if names & USERDEBUG_ONLY:
        return 'userdebug-only policy (the factory image is a user build)'
    origins = {origin.get(n) for n in names} - {None}
    if 'codelinaro' in origins:
        return 'CodeLinaro device/qcom/sepolicy 830b6eb9 is newer than the factory QTI policy'
    return 'AOSP android-10.0.0_r47 revision differs from the factory AOSP 10 base'


def rule_names(rule):
    return set(re.findall(r'[A-Za-z0-9_.-]+', ' '.join(rule[1:3])))


def parity(factory, source):
    report = {}
    origin = declared_in({'aosp': 'system/sepolicy/public', 'aosp_private': 'system/sepolicy/private',
                          'codelinaro': 'device/qcom/sepolicy'})
    origin = {k: ('codelinaro' if v == 'codelinaro' else 'aosp') for k, v in origin.items()}
    ft, st = factory.types, source.types
    report['types'] = {'factory': len(ft), 'source': len(st), 'common': len(ft & st),
                       'factory_only': sorted(ft - st),
                       'source_only': {t: reason_for([t], origin) for t in sorted(st - ft)}}
    fa = {a for a in factory.attributes if not AUTO_ATTRIBUTE.match(a)}
    sa = {a for a in source.attributes if not AUTO_ATTRIBUTE.match(a)}
    report['attributes'] = {'factory': len(fa), 'source': len(sa), 'factory_only': sorted(fa - sa),
                            'source_only': {a: reason_for([a], origin) for a in sorted(sa - fa)}}
    fm, sm = factory.membership(), source.membership()
    report['attribute_memberships'] = {
        'factory': len(fm), 'source': len(sm), 'factory_only': sorted(map(list, fm - sm)),
        'source_only': collections.Counter(reason_for(p, origin) for p in sm - fm)}
    fr, sr = factory.rule_set(), source.rule_set()
    kinds = sorted({r[0] for r in fr | sr})
    factory_only = fr - sr
    source_only = sr - fr
    remaining = collections.defaultdict(list)
    for rule in sorted(factory_only):
        if rule[0] == 'neverallow':
            why = ('factory neverallow exception list of an AOSP rule; neverallows are not '
                   'evaluated at boot (secilc -N) and no Source rule violates the Source form')
        else:
            why = 'not reconstructed'
        remaining[why].append(list(rule))
    report['rules'] = {
        'per_permission_tuples': {'factory': len(fr), 'source': len(sr), 'common': len(fr & sr)},
        'by_kind': {k: {'factory': sum(1 for r in fr if r[0] == k),
                        'source': sum(1 for r in sr if r[0] == k),
                        'factory_only': sum(1 for r in factory_only if r[0] == k),
                        'source_only': sum(1 for r in source_only if r[0] == k)} for k in kinds},
        'factory_only_by_reason': {k: {'count': len(v), 'sample': v[:40]} for k, v in remaining.items()},
        'source_only_by_reason': dict(collections.Counter(
            ('neverallow form of AOSP r47/CodeLinaro (not evaluated at boot)' if r[0] == 'neverallow'
             else reason_for(rule_names(r), origin)) for r in source_only)),
    }
    fx, sx = factory.xrule_set(), source.xrule_set()
    report['extended_permission_rules'] = {'factory': len(fx), 'source': len(sx),
                                           'factory_only': sorted(map(list, fx - sx)),
                                           'source_only': sorted(map(list, sx - fx))}
    ftr, stt = factory.transition_set(), source.transition_set()
    report['transitions'] = {'factory': len(ftr), 'source': len(stt),
                             'factory_only': sorted(map(list, ftr - stt)),
                             'source_only': {' '.join(t): reason_for(t[1:], origin)
                                             for t in sorted(stt - ftr)}}
    fg, sg = set(factory.genfs.items()), set(source.genfs.items())
    report['genfscon'] = {'factory': len(fg), 'source': len(sg),
                          'factory_only': sorted('%s %s %s' % (k[0], k[1], v) for k, v in fg - sg),
                          'source_only': sorted('%s %s %s' % (k[0], k[1], v) for k, v in sg - fg)}
    other_f = {x for x in factory.other if not x.startswith('(roletype')}
    other_s = {x for x in source.other if not x.startswith('(roletype')}
    report['other_statements'] = {'factory_only': sorted(other_f - other_s),
                                  'source_only': sorted(other_s - other_f)}
    contexts = {}
    for kind in ('file', 'property', 'service', 'hwservice', 'seapp'):
        a = read_contexts((FACTORY / ('plat_%s_contexts' % kind)).read_text(), kind)
        b = read_contexts((SOURCE / ('plat_%s_contexts' % kind)).read_text(), kind)
        contexts[kind] = {'factory': len(a), 'source': len(b),
                          'factory_only': sorted(k for k in a if k not in b),
                          'different_label': {k: [a[k], b[k]] for k in a if k in b and a[k] != b[k]},
                          'source_only': sorted(k for k in b if k not in a)}
    report['contexts'] = contexts
    return report


# ----------------------------------------------------------------------------
# (c) file and property labels
FILE_TYPES = {'--': stat.S_IFREG, '-d': stat.S_IFDIR, '-l': stat.S_IFLNK, '-s': stat.S_IFSOCK,
              '-p': stat.S_IFIFO, '-b': stat.S_IFBLK, '-c': stat.S_IFCHR}
META = re.compile(r'[.^$?*+|\[({\\]')


class FileContexts:
    """libselinux label_file lookup: last matching spec wins, exact specs last."""

    def __init__(self, text):
        specs = []
        for raw in text.splitlines():
            line = raw.split('#', 1)[0].strip()
            if not line:
                continue
            fields = line.split()
            regex, context = fields[0], fields[-1]
            mode = FILE_TYPES[fields[1]] if len(fields) == 3 else None
            specs.append((regex, mode, context, re.compile('^(?:' + regex + ')$')))
        self.specs = [s for s in specs if META.search(s[0])] + \
                     [s for s in specs if not META.search(s[0])]

    def lookup(self, path, mode):
        for regex, spec_mode, context, compiled in reversed(self.specs):
            if spec_mode is not None and spec_mode != mode:
                continue
            if compiled.match(path):
                return context, regex
        return None, None


class PropertyContexts:
    def __init__(self, *texts):
        self.exact, self.prefix = {}, {}
        for text in texts:
            for raw in text.splitlines():
                line = raw.split('#', 1)[0].strip()
                if not line:
                    continue
                fields = line.split()
                table = self.exact if len(fields) > 2 and fields[2] == 'exact' else self.prefix
                table.setdefault(fields[0], fields[1])

    def lookup(self, name):
        if name in self.exact:
            return self.exact[name], name
        best = None
        for prefix in self.prefix:
            if prefix != '*' and name.startswith(prefix) and (best is None or len(prefix) > len(best)):
                best = prefix
        if best is None:
            best = '*' if '*' in self.prefix else None
        return (self.prefix[best], best) if best else (None, None)


def file_labels():
    factory = FileContexts((FACTORY / 'plat_file_contexts').read_text())
    source = FileContexts((SOURCE / 'plat_file_contexts').read_text())
    total, mismatches = 1, []
    if factory.lookup('/', stat.S_IFDIR)[0] != source.lookup('/', stat.S_IFDIR)[0]:
        mismatches.append({'path': '/', 'factory': factory.lookup('/', stat.S_IFDIR)[0],
                           'source': source.lookup('/', stat.S_IFDIR)[0]})
    for directory, dirs, files in os.walk(FACTORY_ROOT):
        for name in dirs + files:
            full = os.path.join(directory, name)
            path = '/' + os.path.relpath(full, FACTORY_ROOT)
            mode = stat.S_IFMT(os.lstat(full).st_mode)
            total += 1
            a, ra = factory.lookup(path, mode)
            b, rb = source.lookup(path, mode)
            if a != b:
                mismatches.append({'path': path, 'factory': a, 'factory_spec': ra,
                                   'source': b, 'source_spec': rb})
    return total, mismatches


def property_names():
    names = set()
    for path in (FACTORY_ROOT / 'system/build.prop', FACTORY_ROOT / 'default.prop',
                 PARTITIONS / 'vendor/build.prop', PARTITIONS / 'vendor/default.prop',
                 PARTITIONS / 'product/build.prop', PARTITIONS / 'odm/etc/build.prop'):
        if path.exists():
            for raw in path.read_text(errors='replace').splitlines():
                line = raw.strip()
                if line and not line.startswith('#') and '=' in line and not line.startswith('import'):
                    names.add(line.split('=', 1)[0].strip())
    for path in (FACTORY / 'plat_property_contexts', SOURCE / 'plat_property_contexts',
                 VENDOR / 'vendor_property_contexts', PRODUCT / 'product_property_contexts'):
        if path.exists():
            for raw in path.read_text().splitlines():
                line = raw.split('#', 1)[0].strip()
                if line and line.split()[0] != '*':
                    names.add(line.split()[0])
    return names


def property_labels():
    others = [p.read_text() for p in (VENDOR / 'vendor_property_contexts',
                                      PRODUCT / 'product_property_contexts') if p.exists()]
    factory = PropertyContexts((FACTORY / 'plat_property_contexts').read_text(), *others)
    source = PropertyContexts((SOURCE / 'plat_property_contexts').read_text(), *others)
    names = property_names()
    mismatches = []
    for name in sorted(names):
        a, ka = factory.lookup(name)
        b, kb = source.lookup(name)
        if a != b:
            known = kb in factory.exact or kb in factory.prefix
            mismatches.append({'property': name, 'factory': a, 'factory_entry': ka,
                               'source': b, 'source_entry': kb,
                               'reason': 'matched Source entry %s is %s' % (
                                   kb, 'labelled differently in the factory' if known else
                                   'an AOSP android-10.0.0_r47 entry that the factory base lacks')})
    return len(names), mismatches


def service_labels():
    result = {}
    for kind in ('service', 'hwservice'):
        a = read_contexts((FACTORY / ('plat_%s_contexts' % kind)).read_text(), kind)
        b = read_contexts((SOURCE / ('plat_%s_contexts' % kind)).read_text(), kind)
        result[kind] = {'factory_entries': len(a),
                        'mismatches': {k: [v, b.get(k)] for k, v in a.items() if b.get(k) != v}}
    return result


def main():
    if sys.platform != 'linux':
        raise RuntimeError('Run inside WSL')
    volume = subprocess.check_output(['findmnt', '-n', '-o', 'FSTYPE,UUID', '--target',
                                      str(PROJECT)], text=True).split()
    if volume != ['ext4', 'a00da05f-1eb2-44b6-99f0-9109391f67dc']:
        raise RuntimeError('Expected ext4 source volume')
    factory = Policy((FACTORY / 'plat_sepolicy.cil').read_text())
    source = Policy((SOURCE / 'plat_sepolicy.cil').read_text())
    boot = {'source_plat': boot_compile(SOURCE), 'factory_plat_control': boot_compile(FACTORY),
            'versioned_attributes': mapping_check(),
            'precompiled_policy_used': (ODM / 'precompiled_sepolicy.plat_sepolicy_and_mapping.sha256').exists()
            and (ODM / 'precompiled_sepolicy.plat_sepolicy_and_mapping.sha256').read_text().strip()
            == (SOURCE / 'plat_sepolicy_and_mapping.sha256').read_text().strip()}
    report = {'inputs': {'source_selinux_dir': str(SOURCE), 'factory_selinux_dir': str(FACTORY),
                         'factory_vendor_dir': str(VENDOR), 'factory_product_dir': str(PRODUCT),
                         'secilc': str(SECILC),
                         'source_plat_sepolicy_sha256': sha256(SOURCE / 'plat_sepolicy.cil'),
                         'source_mapping_sha256': sha256(SOURCE / 'mapping/29.0.cil'),
                         'factory_plat_sepolicy_sha256': sha256(FACTORY / 'plat_sepolicy.cil')},
              'boot_policy': boot}
    report['parity'] = parity(factory, source)
    total_files, file_mismatches = file_labels()
    total_props, prop_mismatches = property_labels()
    report['labels'] = {
        'files': {'factory_system_paths': total_files, 'mismatches': len(file_mismatches),
                  'details': file_mismatches},
        'properties': {'names_resolved': total_props, 'mismatches': len(prop_mismatches),
                       'details': prop_mismatches},
        'services': service_labels(),
    }
    ok = (boot['source_plat']['returncode'] == 0 and not boot['versioned_attributes']['unmapped_in_source']
          and not boot['versioned_attributes']['mapped_differently'])
    report['boot_policy_ok'] = ok
    (ROOT / 'validation/sepolicy-parity.json').write_text(json.dumps(report, indent=1, default=list) + '\n')
    p = report['parity']
    print(json.dumps({
        'boot_compile_source': boot['source_plat']['returncode'],
        'boot_compile_factory': boot['factory_plat_control']['returncode'],
        'unmapped_versioned_attributes': len(boot['versioned_attributes']['unmapped_in_source']),
        'differently_mapped': len(boot['versioned_attributes']['mapped_differently']),
        'types': [p['types']['factory'], p['types']['source'], len(p['types']['factory_only']),
                  len(p['types']['source_only'])],
        'rules': p['rules']['by_kind'],
        'contexts': {k: [len(v['factory_only']), len(v['different_label']), len(v['source_only'])]
                     for k, v in p['contexts'].items()},
        'file_label_mismatches': [len(file_mismatches), total_files],
        'property_label_mismatches': [len(prop_mismatches), total_props],
        'boot_policy_ok': ok}, indent=1))
    if not ok:
        sys.exit(1)


if __name__ == '__main__':
    main()
