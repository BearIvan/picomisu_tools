"""Compare every AIDL transaction table of the factory framework with the Source build.

Tables are read from the TRANSACTION_* static values of each $Stub class of the
factory 5.13.7 and Source BOOTCLASSPATH JARs and services.jar.  For each
interface present in both, the report lists factory-only and Source-only
methods and the first transaction code whose method differs (codes after it
are shifted, so a factory binary talking to the Source side would dispatch
the wrong method).

With --signatures the generated $Stub$Proxy classes of both sides are also
disassembled (host dexdumps) and every common transaction is compared by its
full method signature, parameter directions (in/out/inout) and oneway flag, as
reconstruct-pico-aidl.py derives them.  A method with the same name and code
but another signature (a parameter added or changed in place) marshals a
different Parcel, which the name/code tables cannot show.  Nothing on the
headset is accessed.  Run inside WSL:
taskset -c 0-7 python3 tools/compare-aidl-tables.py [--signatures]
"""
import argparse
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import tempfile
import zipfile

spec = importlib.util.spec_from_file_location('bt', Path(__file__).with_name('check-factory-bluetooth.py'))
bt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bt)
spec = importlib.util.spec_from_file_location('pico_aidl', Path(__file__).with_name('reconstruct-pico-aidl.py'))
aidl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(aidl)

REPORT = bt.ROOT / 'validation/aidl-table-parity.json'
DEXDUMP = bt.pico.HOST / 'dexdumps'
# Stable-AIDL bookkeeping methods have no fixed transaction in these tables.
META = ('getInterfaceVersion', 'getInterfaceHash')


def jars(tree):
    paths, _ = bt.java_chain(tree, bt.bootclasspath(tree), [])
    return paths + [tree / 'system/framework/services.jar']


def proxies(paths):
    """{Stub$Proxy descriptor: dexdump text} of a class loader chain (first definition wins)."""
    result = {}
    for path in paths:
        if not path.exists():
            continue
        with zipfile.ZipFile(path) as archive, tempfile.TemporaryDirectory() as tmp:
            for name in sorted((n for n in archive.namelist() if re.fullmatch(r'classes\d*\.dex', n)),
                               key=lambda n: int(n[7:-4] or 1)):
                dex = Path(tmp) / name
                dex.write_bytes(archive.read(name))
                text = subprocess.run([str(DEXDUMP), '-d', str(dex)], capture_output=True, text=True,
                                      errors='replace', check=True).stdout
                for block in re.split(r'\n(?=Class #\d+)', text):
                    match = re.search(r"Class descriptor  : '([^']+\$Stub\$Proxy;)'", block)
                    if match and match.group(1) not in result:
                        result[match.group(1)] = block
    return result


def signatures(block):
    """{code: (name, signature, oneway, directions)} of one generated Proxy class."""
    methods = aidl.methods
    aidl.methods = lambda b: (m for m in methods(b) if m[0] not in META)
    try:
        return {e['code']: (e['name'], e['signature'], e['oneway'], [p['direction'] for p in e['params']])
                for e in aidl.analyze_proxy(block)}
    finally:
        aidl.methods = methods


def compare_signatures(factory_paths, source_paths, common):
    factory, source = proxies(factory_paths), proxies(source_paths)
    compared, differing, skipped = 0, {}, []
    for stub in sorted(common):
        proxy = stub[:-1] + '$Proxy;'
        if proxy not in factory or proxy not in source:
            skipped.append(stub)
            continue
        compared += 1
        try:
            f, s = signatures(factory[proxy]), signatures(source[proxy])
        except (StopIteration, KeyError, AttributeError) as error:
            differing[stub] = [{'error': 'unparsed proxy: %r' % error}]
            continue
        rows = [{'code': c, 'factory': f.get(c), 'source': s.get(c)}
                for c in sorted(set(f) | set(s)) if f.get(c) != s.get(c)]
        if rows:
            differing[stub] = rows
    # HIDL Java stubs (I$Stub with an I$Proxy) and Stubs without a generated Proxy are not AIDL
    # Proxy classes; their tables are still covered by the name/code comparison.
    return {'compared': compared, 'identical': compared - len(differing), 'differing': differing,
            'without_aidl_proxy': skipped}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--signatures', action='store_true',
                        help='also compare full signatures, directions and oneway of common tables')
    args = parser.parse_args()
    bt.pico.guard_volume()
    factory_paths, source_paths = jars(bt.FACTORY), jars(bt.SOURCE)
    factory, source = bt.aidl_tables(factory_paths), bt.aidl_tables(source_paths)
    differing, factory_only_interfaces = {}, []
    for stub in sorted(factory):
        f = factory[stub]
        if stub not in source:
            factory_only_interfaces.append(stub)
            continue
        s = source[stub]
        if f == s:
            continue
        fc, sc = {v: k for k, v in f.items()}, {v: k for k, v in s.items()}
        shifted = [c for c in sorted(set(fc) | set(sc)) if fc.get(c) != sc.get(c)]
        differing[stub] = {'factory_methods': len(f), 'source_methods': len(s),
                           'first_differing_code': shifted[0],
                           'appended_only': shifted[0] > len(s),
                           'factory_only': sorted(set(f) - set(s)),
                           'source_only': sorted(set(s) - set(f))}
    report = {'factory_interfaces': len(factory), 'source_interfaces': len(source),
              'identical': sum(1 for k in factory if source.get(k) == factory[k]),
              'differing': differing, 'factory_only_interfaces': factory_only_interfaces,
              'source_only_interfaces': sorted(set(source) - set(factory)),
              'system_partitions_modified': False}
    if args.signatures:
        same = [k for k in factory if source.get(k) == factory[k]]
        report['signatures'] = compare_signatures(factory_paths, source_paths, same)
    REPORT.write_text(json.dumps(report, indent=1) + '\n')
    summary = {'factory': len(factory), 'identical': report['identical'], 'differing': len(differing),
               'appended_only': sorted(k for k, v in differing.items() if v['appended_only']),
               'factory_only_interfaces': len(factory_only_interfaces)}
    if args.signatures:
        summary['signatures'] = {'compared': report['signatures']['compared'],
                                 'identical': report['signatures']['identical'],
                                 'differing': sorted(report['signatures']['differing'])}
    print(json.dumps(summary, indent=1))


if __name__ == '__main__':
    main()
