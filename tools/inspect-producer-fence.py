"""Check producer-listener primary vtables against authenticated PICO ELF.

Run with Windows Python (pyelftools is already available there). Data is read
from WSL through UNC paths. No code is loaded or executed by this inspector.
This checks this interface group, not the complete libgui C++ ABI.
"""
import argparse
import hashlib
import importlib.util
import io
import json
import lzma
import os
from pathlib import Path, PurePosixPath
import re

from elftools.elf.elffile import ELFFile
from elftools.elf.sections import SymbolTableSection

ROOT = Path(__file__).resolve().parents[1]
PROJECT = PurePosixPath('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro')
spec = importlib.util.spec_from_file_location('elf_pointers', ROOT / 'tools/elf-pointers.py')
pointers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pointers)

TABLES = {
    'BnProducerListener': '_ZTVN7android18BnProducerListenerE',
    'BpProducerListener': '_ZTVN7android18BpProducerListenerE',
    'HpProducerListener': '_ZTVN7android18HpProducerListenerE',
    'DummyProducerListener': '_ZTVN7android21DummyProducerListenerE',
    'SurfaceProducerListenerProxy': '_ZTVN7android7Surface21ProducerListenerProxyE',
    'VirtualDisplayProducerListener': '_ZTVN7android30VirtualDisplayProducerListenerE',
}
CALLBACKS = ['onBufferReleased', 'needsReleaseNotify', 'onBuffersDiscarded',
             'onBufferReleasedWithFence']


def host_path(path):
    path = str(path)
    if os.name == 'nt' and path.startswith('/'):
        return Path('\\\\wsl.localhost\\Ubuntu-24.04' + path.replace('/', '\\'))
    return Path(path)


def aliases(elf):
    result = {}
    sources = [elf.elf]
    debug = elf.elf.get_section_by_name('.gnu_debugdata')
    if debug is not None:
        sources.append(ELFFile(io.BytesIO(lzma.decompress(debug.data()))))
    for source in sources:
        for section in source.iter_sections():
            if isinstance(section, SymbolTableSection):
                for s in section.iter_symbols():
                    if s.name and s.entry.st_shndx != 'SHN_UNDEF' and s.entry.st_info.type == 'STT_FUNC':
                        result.setdefault(s.entry.st_value, set()).add(s.name)
    return result


def inspect(path):
    data = path.read_bytes()
    elf = pointers.ElfPointers(data)
    names = aliases(elf)
    tables = {}
    for label, symbol in TABLES.items():
        rows = elf.vtable(symbol)
        callbacks = []
        for index, callback in enumerate(CALLBACKS):
            row = rows[5 + index]
            methods = {row['symbol']} if row['symbol'] else names.get(row['address'], set())
            # A pure virtual slot cannot independently reveal its method's name.
            pure = methods == {'__cxa_pure_virtual'}
            matching = sorted(n for n in methods if re.search(r'\d+' + callback + r'E', n))
            callbacks.append({'offset_from_primary_address_point': (index + 2) * elf.width,
                              'expected_callback': callback, 'pure_virtual': pure,
                              'method_name_verified': bool(matching),
                              'methods': matching or sorted(methods),
                              'address': hex(row['address']) if row['address'] is not None else None})
        tables[label] = {'vtable_bytes': elf.symbols[symbol].st_size,
                         'primary_prefix': [r['address'] for r in rows[:3]],
                         'callbacks': callbacks}
    return {'sha256': hashlib.sha256(data).hexdigest(), 'abi': elf.elf.elfclass,
            'relocation_formats': sorted(elf.formats), 'tables': tables}, elf


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compare-built', action='store_true')
    args = parser.parse_args()
    manifest = json.loads((ROOT / 'reports/vr-integration/factory-system.json').read_text())
    results = []
    for directory in ('lib64', 'lib'):
        virtual = '/system/' + directory + '/libgui.so'
        entry = next(e for e in manifest['entries'] if e['path'] == virtual)
        path = host_path(PurePosixPath(manifest['tree']) / virtual.lstrip('/'))
        factory, elf = inspect(path)
        if factory['sha256'] != entry['sha256']:
            raise RuntimeError('Factory input changed')
        if directory == 'lib64' and factory['sha256'] != '7b52e5bc29cf5d68c1b24ce6701535dcae64131e3c83b685713ea4a0b4b6dcc5':
            raise RuntimeError('Wrong pinned ARM64 libgui')
        suffix = 'm' if elf.width == 8 else 'y'
        method = '_ZN7android18BnProducerListener25onBufferReleasedWithFenceERKNS_2spINS_5FenceEEE' + suffix + 'b'
        address = elf.symbols[method].st_value
        offset = elf.file_offset(address & ~1, 4 if elf.width == 8 else 2)
        expected_return = b'\xc0\x03\x5f\xd6' if elf.width == 8 else b'\x70\x47'
        if elf.data[offset:offset + len(expected_return)] != expected_return:
            raise RuntimeError('Default fence callback no longer matches verified empty void body')
        for table in factory['tables'].values():
            if not all(c['method_name_verified'] or c['pure_virtual'] for c in table['callbacks']):
                raise RuntimeError('Factory callback order could not be verified')
        result = {'factory': factory, 'default_callback_empty_return_checked': True,
                  'full_libgui_abi_proven': False}
        if args.compare_built:
            built, _ = inspect(host_path(PROJECT / 'out/aosp-10/target/product/PICOA8110/system' / directory / 'libgui.so'))
            comparison = {}
            for label in TABLES:
                a, b = factory['tables'][label], built['tables'][label]
                comparison[label] = {
                    'vtable_size_matches': a['vtable_bytes'] == b['vtable_bytes'],
                    'primary_prefix_matches': a['primary_prefix'] == b['primary_prefix'],
                    'primary_callback_order_matches': all(
                        (x['pure_virtual'] and y['pure_virtual']) or
                        (x['method_name_verified'] and y['method_name_verified'])
                        for x, y in zip(a['callbacks'], b['callbacks']))}
            result.update(built=built, comparison=comparison)
            if not all(all(v.values()) for v in comparison.values()):
                raise RuntimeError('Producer-listener vtable group differs: ' + json.dumps(comparison))
        results.append(result)
    destination = ROOT / 'reports/framework-bridge/producer-fence-abi.json'
    destination.write_text(json.dumps(results, indent=2) + '\n')
    for result in results:
        print(json.dumps({'abi': result['factory']['abi'], 'factory_sha256': result['factory']['sha256'],
                          'callback_order_verified': True,
                          'built_vtable_group_matches': bool(result.get('comparison'))}))


if __name__ == '__main__':
    main()
