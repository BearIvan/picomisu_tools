"""Compare Source PICO API classes with the factory 5.13.7 DEX, class by class.

For every requested class (and its nested/synthetic classes) the comparison covers:
access flags, superclass, interfaces, field and method declarations with access flags,
static final values, and for each method body the ordered sequence of referenced
methods, fields, types and strings (register allocation and branch layout are ignored).
With --hiddenapi the hidden-API flags from dexdumps output are compared too.

Usage (Windows host or WSL):
  python tools/compare-pico-api.py --source <jar-or-dex>... --prefix com/pvr/ --prefix com/pxr/net/
Exit code 1 when an unexplained difference remains; --json writes the full report.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import re
import struct
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
FACTORY = {'framework.jar': ROOT / 'reports/device/static/system__framework__framework.jar',
           'services.jar': ROOT / 'reports/device/static/system__framework__services.jar'}
DEXDUMP = Path(r'\\wsl.localhost\Ubuntu-24.04\mnt\wsl\PHYSICALDRIVE5p3\home\red_panda\RedPandaAndroid'
               r'\pico4-pro\out\aosp-10\host\windows-x86\bin\dexdumps.exe')

spec = importlib.util.spec_from_file_location('pico_scan', ROOT / 'tools/scan-api-consumers.py')
scan = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scan)


def ordered_refs(dex, code):
    """Referenced members/types/strings of one code item, in instruction order."""
    data = dex.data
    size = struct.unpack_from('<I', data, code + 12)[0]
    insns = memoryview(data)[code + 16:code + 16 + size * 2].cast('H')
    refs = []
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
                pc += (insns[pc + 1] * (insns[pc + 2] | insns[pc + 3] << 16) + 1) // 2 + 4
            else:
                pc += 1
            continue
        kind = scan.KIND[op]
        if kind == 'method':
            owner, member = dex.methods[insns[pc + 1]]
            refs.append('M ' + owner + '->' + member)
        elif kind == 'field':
            owner, member = dex.fields[insns[pc + 1]]
            refs.append('F ' + owner + '->' + member)
        elif kind == 'type':
            refs.append('T ' + dex.types[insns[pc + 1]])
        elif kind == 'string':
            index = insns[pc + 1] if op == 0x1a else insns[pc + 1] | insns[pc + 2] << 16
            refs.append('S ' + dex.strings[index])
        elif op == 0x12:
            refs.append('C %d' % (((unit >> 12) ^ 8) - 8))
        elif op in (0x13, 0x16):
            refs.append('C %d' % ((insns[pc + 1] ^ 0x8000) - 0x8000))
        elif op in (0x14, 0x17):
            refs.append('C %d' % (((insns[pc + 1] | insns[pc + 2] << 16) ^ 0x80000000) - 0x80000000))
        elif op == 0x15:
            refs.append('C %d' % ((((insns[pc + 1] << 16) ^ 0x80000000) - 0x80000000)))
        elif op == 0x18:
            refs.append('C %d' % sum(insns[pc + 1 + i] << (16 * i) for i in range(4)))
        elif op == 0x19:
            refs.append('C %d' % (insns[pc + 1] << 48))
        pc += scan.WIDTH[op]
    return refs


def static_values(dex, offset):
    """Decode an encoded_array of static field initial values into printable strings."""
    if not offset:
        return []
    data = dex.data
    count, pos = scan.uleb(data, offset)
    values = []
    for _ in range(count):
        header = data[pos]
        pos += 1
        kind, arg = header & 0x1f, header >> 5
        if kind == 0x1c or kind == 0x1d:
            raise ValueError('Nested static arrays are not expected')
        if kind == 0x1e:
            values.append('null')
            continue
        if kind == 0x1f:
            values.append(str(bool(arg)))
            continue
        raw = int.from_bytes(data[pos:pos + arg + 1], 'little')
        pos += arg + 1
        if kind == 0x17:
            values.append('"' + dex.strings[raw] + '"')
        elif kind == 0x18:
            values.append('type ' + dex.types[raw])
        elif kind in (0x10, 0x11):
            values.append('%s raw=%x' % ('float' if kind == 0x10 else 'double', raw))
        else:
            bits = (arg + 1) * 8
            if kind in (0x00, 0x02, 0x04, 0x06) and raw >= 1 << (bits - 1):
                raw -= 1 << bits
            values.append(str(raw))
    return values


def load(paths):
    """{class descriptor: record} for DEX/JAR inputs."""
    classes = {}
    for path in paths:
        path = Path(path)
        blobs = ([zipfile.ZipFile(path).read(n) for n in sorted(zipfile.ZipFile(path).namelist())
                  if re.fullmatch(r'classes\d*\.dex', n)] if path.suffix in ('.jar', '.apk', '.zip')
                 else [path.read_bytes()])
        for blob in blobs:
            dex = scan.Dex(blob)
            at = dex.class_defs_at[1]
            for index, (clazz, access, superclass, interfaces, fields, methods) in enumerate(dex.classes()):
                static_off = struct.unpack_from('<I', blob, at + index * 32 + 28)[0]
                record = {'access': access & ~0x20, 'super': superclass, 'interfaces': sorted(interfaces),
                          'fields': fields, 'static_values': static_values(dex, static_off),
                          'methods': {}}
                for signature, (flags, code) in methods.items():
                    record['methods'][signature] = {'access': flags,
                                                    'refs': ordered_refs(dex, code) if code else None}
                classes[clazz] = record
    return classes


def hiddenapi(paths):
    """{member key: flag name} from dexdumps output (factory flags are in the DEX)."""
    result = {}
    for path in paths:
        with zipfile.ZipFile(path) as archive, tempfile.TemporaryDirectory() as tmp:
            for name in [n for n in archive.namelist() if re.fullmatch(r'classes\d*\.dex', n)]:
                local = Path(tmp) / name
                local.write_bytes(archive.read(name))
                text = subprocess.run([str(DEXDUMP), str(local)], capture_output=True, text=True,
                                      errors='replace').stdout
                clazz = None
                for part in re.split(r'\n(?=    #\d+\s+: \(in )|\n(?=Class #)', text):
                    match = re.search(r"Class descriptor  : '([^']+)'", part)
                    if match:
                        clazz = match.group(1)
                        continue
                    member = re.search(r"name          : '([^']+)'\n      type          : '([^']+)'", part)
                    if member and clazz:
                        flag = re.search(r'hiddenapi     : 0x\w+ \(([A-Z-]+)\)', part)
                        separator = '' if '(' in member.group(2) else ':'
                        result[clazz + '->' + member.group(1) + separator + member.group(2)] = (
                            flag.group(1) if flag else 'WHITELIST')
    return result


def compare(factory, source, names, only=None):
    """only: optional {class: set(member keys)} restricting existing classes to listed members."""
    rows = []
    for clazz in names:
        f, s = factory.get(clazz), source.get(clazz)
        row = {'class': clazz, 'differences': []}
        selected = only.get(clazz) if only else None
        if f is None or s is None:
            row['differences'].append('missing in ' + ('factory' if f is None else 'source'))
            rows.append(row)
            continue
        for key in ('access', 'super', 'interfaces', 'static_values'):
            if selected is None and f[key] != s[key]:
                row['differences'].append({key: {'factory': f[key], 'source': s[key]}})
        for kind in ('fields', 'methods'):
            fm, sm = f[kind], s[kind]
            for member in sorted(set(fm) | set(sm)):
                if selected is not None and member not in selected:
                    continue
                if member not in sm or member not in fm:
                    row['differences'].append({kind[:-1]: member, 'only_in': 'factory' if member in fm else 'source'})
                    continue
                fa = fm[member] if kind == 'fields' else fm[member]['access']
                sa = sm[member] if kind == 'fields' else sm[member]['access']
                if fa != sa:
                    row['differences'].append({kind[:-1]: member, 'access': {'factory': hex(fa), 'source': hex(sa)}})
                if kind == 'methods' and fm[member]['refs'] != sm[member]['refs']:
                    row['differences'].append({'method': member, 'body': {
                        'factory': fm[member]['refs'], 'source': sm[member]['refs']}})
        rows.append(row)
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', nargs='+', required=True)
    parser.add_argument('--prefix', action='append', required=True, help='class descriptor prefix, e.g. com/pvr/')
    parser.add_argument('--jar', default='framework.jar', choices=sorted(FACTORY))
    parser.add_argument('--factory-path', type=Path, help='another factory JAR/APK to compare with')
    parser.add_argument('--only', type=Path, help='file of "Lclass;->member" lines (or "Lclass;" for a '
                        'whole class); existing classes are compared only on the listed members')
    parser.add_argument('--hiddenapi', action='store_true')
    parser.add_argument('--json', type=Path)
    args = parser.parse_args()
    factory_path = args.factory_path or FACTORY[args.jar]
    factory = load([factory_path])
    source = load(args.source)
    prefixes = tuple('L' + p for p in args.prefix)
    only = None
    if args.only:
        only = {}
        for line in args.only.read_text().split():
            clazz, _, member = line.partition('->')
            only.setdefault(clazz, set())
            if member:
                only[clazz].add(member)
        only = {c: (m or None) for c, m in only.items()}
        names = sorted(c for c in only if c.startswith(prefixes))
    else:
        names = sorted(c for c in set(factory) | set(source) if c.startswith(prefixes))
    rows = compare(factory, source, names, only)
    if args.hiddenapi:
        fh, sh = hiddenapi([factory_path]), hiddenapi(args.source)
        for row in rows:
            members = only.get(row['class']) if only else None
            for key in sorted(k for k in fh if k.startswith(row['class'] + '->')):
                if members is not None and key.split('->', 1)[1] not in members:
                    continue
                if key in sh and fh[key] != sh[key]:
                    row['differences'].append({'hiddenapi': key, 'factory': fh[key], 'source': sh[key]})
    clean = [r['class'] for r in rows if not r['differences']]
    report = {'classes': len(rows), 'identical': len(clean), 'rows': rows}
    if args.json:
        args.json.write_text(json.dumps(report, indent=1) + '\n')
    for row in rows:
        if row['differences']:
            print(row['class'])
            for difference in row['differences'][:12]:
                print('   ', json.dumps(difference)[:600])
    print(json.dumps({'classes': len(rows), 'identical': len(clean)}))
    sys.exit(0 if len(clean) == len(rows) else 1)


if __name__ == '__main__':
    main()
