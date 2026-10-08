"""Audit necessary symbol compatibility with authenticated factory consumers.

Symbol names are compared without version suffixes. This does not prove C++
object layout, virtual method order or behavioral compatibility.
"""
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PROJECT = Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro')


def symbols(path):
    output = subprocess.check_output(['readelf', '--dyn-syms', '--wide', str(path)], text=True)
    exports, imports = {}, set()
    for line in output.splitlines():
        fields = line.split()
        if len(fields) < 8 or not fields[0].endswith(':') or not fields[0][:-1].isdigit():
            continue
        name = fields[7].split('@')[0]
        if fields[6] == 'UND':
            if fields[4] == 'GLOBAL':
                imports.add(name)
        elif fields[4] in ('GLOBAL', 'WEAK') and fields[5] in ('DEFAULT', 'PROTECTED'):
            exports[name] = {'type': fields[3],
                             'bytes': int(fields[2], 16 if fields[2].startswith('0x') else 10)}
    return exports, imports


def verified(path, sha):
    if hashlib.sha256(path.read_bytes()).hexdigest() != sha:
        raise RuntimeError('Authenticated factory input changed: ' + str(path))


def main():
    factory = json.loads((ROOT / 'reports/vr-integration/factory-system.json').read_text())
    graph = json.loads((ROOT / 'reports/vr-dependencies/factory-graph.json').read_text())
    results = []
    for directory, elf_class in [('lib64', 64), ('lib', 32)]:
        entry = next(row for row in factory['entries'] if row['path'] == '/system/' + directory + '/libgui.so')
        stock = Path(factory['tree']) / entry['path'].lstrip('/')
        verified(stock, entry['sha256'])
        built = PROJECT / 'out/aosp-10/target/product/PICOA8110/system' / directory / 'libgui.so'
        stock_exports, _ = symbols(stock)
        built_exports, _ = symbols(built)
        absent = set(stock_exports) - set(built_exports)
        consumers = {}
        inspected = 0
        for virtual, row in graph['elf_files'].items():
            if row['elf_class'] != elf_class:
                continue
            path = Path(row['analysis_copy'])
            verified(path, row['sha256'])
            _, imported = symbols(path)
            inspected += 1
            required = imported & set(stock_exports)
            if required:
                missing = sorted(required & absent)
                consumers[virtual] = {'factory_gui_import_count': len(required),
                                      'missing_in_aosp_libgui': missing}
        changed_vtables = {name: {'factory_bytes': stock_exports[name]['bytes'],
                                  'aosp_bytes': built_exports[name]['bytes']}
                           for name in set(stock_exports) & set(built_exports)
                           if name.startswith('_ZTV') and stock_exports[name]['bytes'] != built_exports[name]['bytes']}
        results.append({'abi': elf_class, 'factory_sha256': entry['sha256'],
                        'aosp_sha256': hashlib.sha256(built.read_bytes()).hexdigest(),
                        'factory_export_count': len(stock_exports),
                        'aosp_export_count': len(built_exports),
                        'factory_exports_absent_in_aosp': sorted(absent),
                        'inspected_factory_elf_count': inspected,
                        'factory_consumers': consumers, 'changed_vtable_sizes': changed_vtables,
                        'full_abi_compatibility_proven': False})
    destination = ROOT / 'reports/framework-bridge/libgui-symbol-compatibility.json'
    destination.write_text(json.dumps(results, indent=2) + '\n')
    for result in results:
        impacted = {name: entry['missing_in_aosp_libgui'] for name, entry in result['factory_consumers'].items()
                    if entry['missing_in_aosp_libgui']}
        print(json.dumps({'abi': result['abi'],
                          'inspected_factory_elf_count': result['inspected_factory_elf_count'],
                          'absent_factory_export_count': len(result['factory_exports_absent_in_aosp']),
                          'consumers_with_missing_symbols': impacted,
                          'changed_vtable_sizes': result['changed_vtable_sizes']}, indent=2))


if __name__ == '__main__':
    main()
