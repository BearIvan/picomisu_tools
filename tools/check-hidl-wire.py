"""Check HIDL wire compatibility of Source and factory Wi-Fi service classes and libraries.

Three checks, all static (nothing runs on the headset):
1. Every HIDL class under the given prefixes is compared between the factory and the Source
   JAR instruction by instruction: opcodes, registers, literals, branch offsets, array/switch
   payloads, try/catch tables and register counts; constant-pool indexes are resolved to the
   referenced method, field, type or string. Identical code means identical transaction codes,
   flags, interface tokens and struct offsets/sizes.
2. Interface hash chains: the 32-byte hashes that every Java Stub returns from getHashChain()
   in the factory and the Source JAR are compared with the hashes hidl-gen computes from the
   Source .hal files, with the donor current.txt files and with the factory vendor libraries
   (reported where the 32 bytes occur verbatim in a factory library).
3. Native: the small immediates (struct offsets and sizes) of selected functions of a factory
   and a Source library are compared (e.g. writeEmbeddedToParcel(StaLinkLayerStats)), and
   the defined dynamic symbols of factory and Source C++ interface libraries.
Usage (WSL):
  python3 tools/check-hidl-wire.py --factory-jar F --source-jar S --prefix vendor/qti/hardware/
      --hal-hashes H --current C [--current C2] --vendor-lib-dir D
      [--native NAME FACTORY_SO SOURCE_SO SYMBOL] [--symbols NAME FACTORY_SO SOURCE_SO] --json OUT
"""
import argparse
import importlib.util
import json
from pathlib import Path
import re
import struct
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('pico_scan', ROOT / 'tools/scan-api-consumers.py')
scan = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scan)
OBJDUMP = Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro/source/aosp-10/'
               'prebuilts/clang/host/linux-x86/clang-r353983c/bin/llvm-objdump')


def resolve(dex, kind, index):
    if kind == 'method':
        return 'M ' + '->'.join(dex.methods[index])
    if kind == 'field':
        return 'F ' + '->'.join(dex.fields[index])
    if kind == 'type':
        return 'T ' + dex.types[index]
    return 'S ' + repr(dex.strings[index])


def code_item(dex, offset):
    """Canonical text of one code item with constant-pool indexes resolved."""
    data = dex.data
    registers, ins, outs, tries, _, size = struct.unpack_from('<HHHHII', data, offset)
    units = struct.unpack_from('<%dH' % size, data, offset + 16)
    lines = ['regs=%d ins=%d outs=%d' % (registers, ins, outs)]
    pc = 0
    while pc < size:
        unit = units[pc]
        op = unit & 0xff
        if op == 0 and unit in (0x0100, 0x0200, 0x0300):
            if unit == 0x0100:
                width = units[pc + 1] * 2 + 4
            elif unit == 0x0200:
                width = units[pc + 1] * 4 + 2
            else:
                width = (units[pc + 1] * (units[pc + 2] | units[pc + 3] << 16) + 1) // 2 + 4
            lines.append('%04x payload %s' % (pc, ' '.join('%04x' % u for u in units[pc:pc + width])))
            pc += width
            continue
        width, kind = scan.WIDTH[op], scan.KIND[op]
        raw = list(units[pc:pc + width])
        if kind == 'string' and op == 0x1b:
            raw[1:3] = [resolve(dex, kind, raw[1] | raw[2] << 16)]
        elif kind:
            raw[1] = resolve(dex, kind, raw[1])
        lines.append('%04x %s' % (pc, ' '.join(x if isinstance(x, str) else '%04x' % x for x in raw)))
        pc += width
    if tries:
        at = offset + 16 + size * 2 + (2 if size % 2 else 0)
        handlers = at + tries * 8
        for index in range(tries):
            start, count, handler = struct.unpack_from('<IHH', data, at + index * 8)
            cursor = handlers + handler
            entries, cursor = sleb(data, cursor)
            catches = []
            for _ in range(abs(entries)):
                kind, cursor = scan.uleb(data, cursor)
                address, cursor = scan.uleb(data, cursor)
                catches.append('%s@%04x' % (dex.types[kind], address))
            if entries <= 0:
                address, cursor = scan.uleb(data, cursor)
                catches.append('<any>@%04x' % address)
            lines.append('try %04x+%d %s' % (start, count, ' '.join(catches)))
    return lines


def sleb(data, offset):
    value, shift = 0, 0
    while True:
        byte = data[offset]
        offset += 1
        value |= (byte & 127) << shift
        shift += 7
        if byte < 128:
            if byte & 64:
                value -= 1 << shift
            return value, offset


def load(jar, prefixes):
    classes, dexes = {}, []
    with zipfile.ZipFile(jar) as archive:
        for name in sorted(n for n in archive.namelist() if re.fullmatch(r'classes\d*\.dex', n)):
            dex = scan.Dex(archive.read(name))
            dexes.append(dex)
            at = dex.class_defs_at[1]
            for index, (clazz, access, superclass, interfaces, fields, methods) in enumerate(dex.classes()):
                if not clazz.startswith(prefixes):
                    continue
                static_off = struct.unpack_from('<I', dex.data, at + index * 32 + 28)[0]
                classes[clazz] = {
                    'dex': dex, 'access': access & ~0x20, 'super': superclass, 'interfaces': interfaces,
                    'fields': fields, 'static_values': compare_pico.static_values(dex, static_off),
                    'methods': {m: (flags, code_item(dex, code) if code else None)
                                for m, (flags, code) in methods.items()}}
    return classes


spec2 = importlib.util.spec_from_file_location('compare_pico', ROOT / 'tools/compare-pico-api.py')
compare_pico = importlib.util.module_from_spec(spec2)
spec2.loader.exec_module(compare_pico)


def compare_classes(factory, source):
    rows = []
    for clazz in sorted(set(factory) | set(source)):
        f, s = factory.get(clazz), source.get(clazz)
        if f is None or s is None:
            rows.append({'class': clazz, 'differences': ['missing in ' + ('factory' if f is None else 'source')]})
            continue
        differences = []
        for key in ('access', 'super', 'interfaces', 'fields', 'static_values'):
            if f[key] != s[key]:
                differences.append(key)
        for method in sorted(set(f['methods']) | set(s['methods'])):
            if f['methods'].get(method) != s['methods'].get(method):
                differences.append('method ' + method)
        rows.append({'class': clazz, 'differences': differences})
    return rows


def hash_chains(classes):
    """{interface descriptor string: [hex hashes]} from each Stub's getHashChain and interfaceChain."""
    chains = {}
    for clazz, record in classes.items():
        if not clazz.endswith('$Stub;'):
            continue
        hashes = record['methods'].get('getHashChain()Ljava/util/ArrayList;', (0, None))[1]
        names = record['methods'].get('interfaceChain()Ljava/util/ArrayList;', (0, None))[1]
        if not hashes or not names:
            continue
        chain = [re.search(r"S '(.*)'", line).group(1) for line in names if " S '" in line]
        payloads = []
        for line in hashes:
            if ' payload 0300' in line:
                units = [int(u, 16) for u in line.split(' payload ')[1].split()]
                data = b''.join(struct.pack('<H', u) for u in units[4:])
                payloads.append(data[:units[2] | units[3] << 16].hex())
        chains[chain[0]] = list(zip(chain, payloads))
    return chains


def native_immediates(path, symbol):
    """Immediate operands of one exported function, in instruction order."""
    names = subprocess.check_output([str(OBJDUMP.with_name('llvm-nm')), '-D', '-S', str(path)], text=True)
    match = re.search(r'^([0-9a-f]+) ([0-9a-f]+) \w ' + re.escape(symbol) + r'$', names, re.MULTILINE)
    if not match:
        raise RuntimeError('Symbol not found: ' + symbol + ' in ' + str(path))
    value, size = int(match.group(1), 16), int(match.group(2), 16)
    start = value & ~1
    # Android 32-bit ARM libraries are compiled to Thumb-2.
    thumb = Path(path).read_bytes()[4] == 1
    listing = subprocess.check_output([str(OBJDUMP), '-d', '--no-show-raw-insn'] +
                                      (['--triple=thumbv7'] if thumb else []) + [
                                       '--start-address=0x%x' % start,
                                       '--stop-address=0x%x' % (start + size), str(path)], text=True)
    body = [m.group(1) for m in re.finditer(r'^\s*[0-9a-f]+:\s+(.*)$', listing, re.MULTILINE)]
    # Struct offsets and sizes are small; PC-relative addresses and call targets depend on
    # the library layout and are left out.
    values = [int(t, 0) for text in body for t in re.findall(r'#(-?(?:0x)?[0-9a-f]+)', text)]
    return [v for v in values if abs(v) < 4096]


def defined_symbols(path):
    names = subprocess.check_output([str(OBJDUMP.with_name('llvm-nm')), '-D', '--defined-only', str(path)],
                                    text=True)
    # Generated interface classes and their toString()/Status helpers; template instances of
    # sp<>, std:: containers and construction vtables depend on the compiler and inlining.
    return {n for n in (line.split()[-1] for line in names.splitlines() if line.strip())
            if re.match(r'_ZN(K)?6vendor|_ZN7android8hardware8toString.*6vendor', n)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--factory-jar', type=Path, required=True)
    parser.add_argument('--source-jar', type=Path, required=True)
    parser.add_argument('--prefix', action='append', required=True)
    parser.add_argument('--hal-hashes', type=Path, required=True)
    parser.add_argument('--current', type=Path, action='append', required=True)
    parser.add_argument('--vendor-lib-dir', type=Path, action='append', default=[])
    parser.add_argument('--native', nargs=4, action='append', default=[],
                        metavar=('NAME', 'FACTORY', 'SOURCE', 'SYMBOL'))
    parser.add_argument('--layout-values', default='',
                        help='comma separated struct offsets/sizes of interest; native checks compare the '
                        'occurrences of these values instead of all small immediates')
    parser.add_argument('--symbols', nargs=3, action='append', default=[], metavar=('NAME', 'FACTORY', 'SOURCE'),
                        help='compare the defined dynamic symbols of a factory and a Source library')
    parser.add_argument('--json', type=Path, required=True)
    args = parser.parse_args()
    prefixes = tuple('L' + p for p in args.prefix)
    factory, source = load(args.factory_jar, prefixes), load(args.source_jar, prefixes)
    rows = compare_classes(factory, source)
    report = {'prefixes': args.prefix, 'classes': len(rows),
              'identical_instruction_level': sum(not r['differences'] for r in rows),
              'different': [r for r in rows if r['differences']]}
    generated = dict(reversed(line.split()) for line in args.hal_hashes.read_text().splitlines() if line.strip())
    recorded = {}
    for path in args.current:
        for line in path.read_text().splitlines():
            parts = line.split()
            if len(parts) == 2 and not line.startswith('#'):
                recorded.setdefault(parts[1], []).append(parts[0])
    libraries = [p for d in args.vendor_lib_dir for p in sorted(d.glob('*.so')) if p.is_file()]
    blobs = {p: p.read_bytes() for p in libraries}
    fchains, schains = hash_chains(factory), hash_chains(source)
    hashes, problems = {}, []
    for name in sorted(set(fchains) | set(schains)):
        fchain, schain = fchains.get(name), schains.get(name)
        own = dict(fchain or [])
        own_hash = own.get(name)
        entry = {'factory_chain_equals_source': fchain == schain, 'hash': own_hash,
                 'hidl_gen_from_source_hal': generated.get(name),
                 'recorded_in_current_txt': own_hash in recorded.get(name, []),
                 'factory_vendor_libraries': [str(p.name) for p, b in blobs.items()
                                              if own_hash and bytes.fromhex(own_hash) in b]}
        if name in generated:
            entry['source_hal_matches'] = generated[name] == own_hash
        hashes[name] = entry
        if (not entry['factory_chain_equals_source'] or not entry['recorded_in_current_txt']
                or entry.get('source_hal_matches') is False):
            problems.append(name)
    report['hash_chains'] = hashes
    natives = {}
    layout = {int(v) for v in args.layout_values.split(',') if v}
    for name, factory_so, source_so, symbol in args.native:
        f, s = native_immediates(factory_so, symbol), native_immediates(source_so, symbol)
        if layout:
            f, s = sorted(v for v in f if v in layout), sorted(v for v in s if v in layout)
        natives[name] = {'symbol': symbol, 'factory_immediates': f, 'source_immediates': s,
                         'equal': f == s and bool(f)}
        if f != s:
            problems.append('native ' + name)
    report['native_layouts'] = natives
    symbols = {}
    for name, factory_so, source_so in args.symbols:
        f, s = defined_symbols(factory_so), defined_symbols(source_so)
        symbols[name] = {'factory': len(f), 'source': len(s), 'equal': f == s,
                         'only_factory': sorted(f - s)[:20], 'only_source': sorted(s - f)[:20]}
        if f != s:
            problems.append('symbols ' + name)
    report['native_symbols'] = symbols
    report['problems'] = problems
    args.json.write_text(json.dumps(report, indent=1) + '\n')
    print(json.dumps({'classes': report['classes'], 'identical': report['identical_instruction_level'],
                      'interfaces': len(hashes), 'natives': {k: v['equal'] for k, v in natives.items()},
                      'symbols': {k: v['equal'] for k, v in symbols.items()},
                      'problems': problems}))
    raise SystemExit(1 if problems or report['different'] else 0)


if __name__ == '__main__':
    main()
