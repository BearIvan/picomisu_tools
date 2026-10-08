#!/usr/bin/env python3
"""Symbol/ABI parity of Source native libraries with the factory PICO OS 5.13.7.

Run inside WSL (taskset -c 0-7). Read-only: compares the extracted factory
system/vendor/product/odm trees with the Source product output.

For every checked library and install variant (lib64, lib, vndk-29, vndk-sp-29)
the dynamic exports are compared. Each factory-only export is classified by
its factory consumers (UND references of all factory ELF files that list the
library in DT_NEEDED): a consumer whose path is rebuilt by Source is replaced,
otherwise the symbol is needed. Symbols without consumers are classified as
compiler/template artefacts or unconsumed API; explanations for known entries
come from EXPLANATIONS. The symbol-resolution check then resolves every UND
symbol of the preserved factory consumers against the Source build of their
DT_NEEDED libraries (factory libraries where Source builds none).
"""
import concurrent.futures
import json
import os
import re
import subprocess
import sys
from pathlib import Path

PROJECT = Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro')
REPO = Path(__file__).resolve().parents[1]
BIN = PROJECT / 'source/aosp-10/prebuilts/clang/host/linux-x86/clang-r353983c/bin'
FACTORY = {
    'system': PROJECT / 'analysis/stock-5.13.7-system/root',
    'vendor': PROJECT / 'analysis/stock-5.13.7-partitions/vendor',
    'product': PROJECT / 'analysis/stock-5.13.7-partitions/product',
    'odm': PROJECT / 'analysis/stock-5.13.7-partitions/odm',
}
PRODUCT = PROJECT / 'out/aosp-10/target/product/PICOA8110'
CACHE = PROJECT / 'logs/native-parity-factory-elf.json'
# Libraries whose factory-only exports are ported and classified in stage 3 chunk 6.
LIBRARIES = ['libbinder.so', 'libbinder_call_stat.so', 'libhwui.so', 'libmedia_jni.so',
             'libspatialaudio.so', 'libandroid_runtime.so']
# Media libraries touched by chunk 6 (VR type, spatializer client); their other factory
# (mostly CodeLinaro AV extension) exports are recorded but belong to later work.
INFORMATIVE = ['libaudioclient.so', 'libmedia.so', 'libmediaplayerservice.so', 'libstagefright.so']
VARIANTS = ['lib64', 'lib', 'lib64/vndk-29', 'lib/vndk-29', 'lib64/vndk-sp-29', 'lib/vndk-sp-29']
COMPILER = re.compile(r'^(std::|void std::|unsigned long std::|int std::|bool std::|'
                      r'construction vtable|VTT for|typeinfo|vtable for android::SortedVector|'
                      r'vtable for android::Vector|android::SortedVector<|android::Vector<|'
                      r'android::KeyedVector<|int android::Parcel::readAligned<|'
                      r'android::TextOutput& android::operator<<|virtual thunk|non-virtual thunk|'
                      r'__(add|sub|mul|div)tf3$|__float(di|si|un)[a-z]*$|__fe_|__aeabi_|__floatundisf$|'
                      r'android::Singleton<.*>::(getInstance|hasInstance|Singleton|~Singleton)|'
                      r'int android::Parcel::unsafeReadTypedVector<|'
                      r'android::sp<.*>::~sp\(\))')


def run(*args):
    return subprocess.run(args, capture_output=True, text=True).stdout


def demangle(names):
    out = subprocess.run(['c++filt'], input='\n'.join(names) + '\n', capture_output=True,
                         text=True).stdout.split('\n')
    return dict(zip(names, out))


def exports(path):
    result = {}
    for line in run(str(BIN / 'llvm-nm'), '-D', '--defined-only', str(path)).splitlines():
        parts = line.split()
        if len(parts) >= 3:
            result[parts[2]] = parts[1]
    return result


def scan(item):
    part, root, path = item
    header = run('readelf', '-W', '-d', '-h', path)
    needed = re.findall(r'\(NEEDED\).*\[(.+?)\]', header)
    undefined = []
    for line in run(str(BIN / 'llvm-nm'), '-D', '--undefined-only', path).splitlines():
        parts = line.split()
        if parts:
            undefined.append([parts[0], parts[-1]])
    rel = path[len(str(root)):]
    return {'path': rel if part == 'system' else '/' + part + rel,
            'class': 64 if 'ELF64' in header else 32, 'needed': needed, 'und': undefined}


def factory_elves():
    if CACHE.exists():
        return json.loads(CACHE.read_text())
    items = []
    for part, root in FACTORY.items():
        for directory, _, files in os.walk(root):
            for name in files:
                path = os.path.join(directory, name)
                if os.path.islink(path) or not os.path.isfile(path):
                    continue
                with open(path, 'rb') as handle:
                    if handle.read(4) != b'\x7fELF':
                        continue
                items.append((part, str(root), path))
    with concurrent.futures.ThreadPoolExecutor(8) as pool:
        result = list(pool.map(scan, items))
    CACHE.write_text(json.dumps(result))
    return result


def source_path(factory_path):
    return PRODUCT / factory_path.lstrip('/')


def classify(symbol, demangled, consumers, explanations):
    preserved = [c for c in consumers if not source_path(c).exists()]
    replaced = [c for c in consumers if source_path(c).exists()]
    if preserved:
        kind = 'needed_by_preserved_factory_consumer'
    elif replaced:
        kind = 'consumer_replaced_by_source'
    elif COMPILER.search(demangled):
        kind = 'compiler_or_template_instantiation'
    else:
        kind = 'no_factory_consumer'
    entry = {'symbol': symbol, 'demangled': demangled, 'classification': kind}
    if preserved:
        entry['preserved_consumers'] = preserved
    if replaced:
        entry['replaced_consumers'] = replaced
    for pattern, text in explanations.items():
        if re.search(pattern, demangled):
            entry['explanation'] = text
            break
    return entry


EXPLANATIONS = json.loads((REPO / 'config/native-parity-explanations.json').read_text())


def main():
    elves = factory_elves()
    report = {'factory_elf_files': len(elves), 'libraries': {}, 'resolution': {}}
    factory_root = FACTORY['system'] / 'system'
    for lib in LIBRARIES + INFORMATIVE:
        for variant in VARIANTS:
            f = factory_root / variant / lib
            s = PRODUCT / 'system' / variant / lib
            if not f.exists() and not s.exists():
                continue
            key = variant + '/' + lib
            if not f.exists() or not s.exists():
                report['libraries'][key] = {'factory_present': f.exists(), 'source_present': s.exists()}
                continue
            fe, se = exports(f), exports(s)
            fo = sorted(set(fe) - set(se))
            so = sorted(set(se) - set(fe))
            names = demangle(fo + so)
            consumers = {}
            vendor_side = 'vndk' in variant
            bits = 64 if variant.startswith('lib64') else 32
            for elf in elves:
                if lib not in elf['needed'] or elf['class'] != bits:
                    continue
                if vendor_side != elf['path'].startswith(('/vendor', '/odm')):
                    continue
                for _, sym in elf['und']:
                    if sym in fe and sym not in se:
                        consumers.setdefault(sym, []).append(elf['path'])
            entries = [classify(sym, names[sym], sorted(consumers.get(sym, [])),
                                EXPLANATIONS.get(lib, {})) for sym in fo]
            summary = {}
            for entry in entries:
                summary[entry['classification']] = summary.get(entry['classification'], 0) + 1
            if lib in INFORMATIVE:
                # Only the entries with factory consumers are listed for libraries outside chunk 6.
                entries = [e for e in entries if e['classification'] in (
                    'needed_by_preserved_factory_consumer', 'consumer_replaced_by_source')]
                so = [sym for sym in so if not COMPILER.search(names[sym])]
            report['libraries'][key] = {
                'scope': 'chunk6' if lib in LIBRARIES else 'informative',
                'factory_exports': len(fe), 'source_exports': len(se),
                'factory_only': len(fo), 'source_only': len(so),
                'factory_only_by_class': summary,
                'factory_only_symbols': entries,
                'source_only_symbols': [{'symbol': sym, 'demangled': names[sym],
                                         'classification': 'compiler_or_template_instantiation'
                                         if COMPILER.search(names[sym]) else 'source_only_api'}
                                        for sym in so],
            }
    # Resolution of preserved factory consumers of the checked libraries.
    export_cache = {}

    needed_cache = {}

    def locate(bits, vendor_side, name):
        """Library the loader would use: Source build first, factory when Source has none."""
        base = 'lib64' if bits == 64 else 'lib'
        candidates = []
        if vendor_side:
            # Factory VNDK extensions on /vendor take precedence over the core VNDK copy.
            candidates += [FACTORY['vendor'] / base / 'vndk' / name, FACTORY['vendor'] / base / 'vndk-sp' / name,
                           PRODUCT / 'system' / base / 'vndk-29' / name,
                           PRODUCT / 'system' / base / 'vndk-sp-29' / name,
                           FACTORY['vendor'] / base / name, FACTORY['odm'] / base / name,
                           FACTORY['vendor'] / base / 'egl' / name, FACTORY['vendor'] / base / 'hw' / name]
        candidates += [PRODUCT / 'system' / base / name, factory_root / base / name,
                       FACTORY['product'] / base / name,
                       PRODUCT / 'system' / 'apex' / 'com.android.runtime.debug' / base / name,
                       factory_root / base / 'bootstrap' / name]
        for c in candidates:
            if c.exists():
                return c
        return None

    def lib_exports(path):
        if path not in export_cache:
            export_cache[path] = set(exports(path))
        return export_cache[path]

    def lib_needed(path):
        if path not in needed_cache:
            needed_cache[path] = re.findall(r'\(NEEDED\).*\[(.+?)\]', run('readelf', '-W', '-d', str(path)))
        return needed_cache[path]

    checked = 0
    unresolved = {}
    missing_libraries = {}
    for elf in elves:
        if not any(lib in elf['needed'] for lib in LIBRARIES):
            continue
        if source_path(elf['path']).exists():
            continue  # rebuilt by Source
        vendor_side = elf['path'].startswith(('/vendor', '/odm'))
        available = set()
        queue, seen = list(elf['needed']), set()
        while queue:
            name = queue.pop()
            if name in seen:
                continue
            seen.add(name)
            path = locate(elf['class'], vendor_side, name)
            if path is None:
                missing_libraries.setdefault(elf['path'], []).append(name)
                continue
            available |= lib_exports(path)
            queue.extend(lib_needed(path))
        missing = [sym for bind, sym in elf['und'] if bind == 'U' and sym not in available]
        checked += 1
        if missing:
            unresolved[elf['path']] = missing

    def factory_provider(elf_path, bits, vendor_side, needed, symbol):
        base = 'lib64' if bits == 64 else 'lib'
        queue, seen = list(needed), set()
        while queue:
            name = queue.pop()
            if name in seen:
                continue
            seen.add(name)
            for root in ([FACTORY['vendor'] / base / 'vndk', FACTORY['vendor'] / base, factory_root / base / 'vndk-29',
                          factory_root / base / 'vndk-sp-29'] if vendor_side else []) + \
                        [factory_root / base, FACTORY['product'] / base, factory_root / base / 'bootstrap']:
                path = root / name
                if path.exists():
                    if symbol in lib_exports(path):
                        return str(path).split('/root', 1)[-1].replace(str(PROJECT) + '/analysis/stock-5.13.7-partitions', '')
                    queue.extend(lib_needed(path))
                    break
        return None

    grouped = {}
    for path, symbols in unresolved.items():
        elf = next(e for e in elves if e['path'] == path)
        vendor_side = path.startswith(('/vendor', '/odm'))
        names = demangle(symbols)
        for symbol in symbols:
            provider = factory_provider(path, elf['class'], vendor_side, elf['needed'], symbol)
            grouped.setdefault(provider or 'not-found-offline', {}).setdefault(path, []).append(names[symbol])
    chunk_regressions = {p: v for p, v in grouped.items()
                         if p and os.path.basename(p) in LIBRARIES}
    report['resolution'] = {'preserved_factory_consumers_checked': checked,
                            'consumers_with_unresolved_symbols': len(unresolved),
                            'unresolved_from_chunk_libraries': chunk_regressions,
                            'unresolved_by_factory_provider': grouped,
                            'libraries_not_found_offline': missing_libraries}
    out = REPO / 'validation/native-parity.json'
    out.write_text(json.dumps(report, indent=1, ensure_ascii=False) + '\n')
    for key, value in report['libraries'].items():
        print(key, {k: v for k, v in value.items() if not k.endswith('symbols')})
    resolution = report['resolution']
    print('resolution checked=%d with-unresolved=%d chunk-regressions=%d' % (
        resolution['preserved_factory_consumers_checked'], resolution['consumers_with_unresolved_symbols'],
        len(resolution['unresolved_from_chunk_libraries'])))
    for provider, consumers in resolution['unresolved_by_factory_provider'].items():
        print('  provider', provider, {k: len(v) for k, v in consumers.items()})


if __name__ == '__main__':
    sys.exit(main())
