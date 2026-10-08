"""Verify the existing AOSP consumer-listener interface against PICO.

No port is needed for onDisconnect: it exists in the pinned upstream. Checks
callback slots in both ABIs and the factory ARM64 Binder command dispatch.
"""
import importlib.util
import argparse
import json
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('p', ROOT / 'tools/inspect-producer-fence.py')
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)

TABLES = ['_ZTVN7android16ConsumerListenerE', '_ZTVN7android17IConsumerListenerE',
          '_ZTVN7android18BnConsumerListenerE', '_ZTVN7android18BpConsumerListenerE',
          '_ZTVN7android11BufferQueue21ProxyConsumerListenerE', '_ZTVN7android12ConsumerBaseE']
METHODS = ['onDisconnect', 'onFrameAvailable', 'onFrameReplaced', 'onBuffersReleased',
           'onSidebandStreamChanged', 'addAndGetFrameTimestamps']


def check_table(elf, symbol):
    rows, aliases = elf.vtable(symbol), p.aliases(elf)
    checked = []
    for index, method in enumerate(METHODS):
        row = rows[5 + index]
        names = {row['symbol']} if row['symbol'] else aliases.get(row['address'], set())
        valid = '__cxa_pure_virtual' in names or any(method + 'E' in n for n in names)
        if not valid:
            raise RuntimeError('Cannot verify consumer callback slot: ' + symbol + ' ' + method)
        checked.append({'expected_method': method,
                        'method_name_verified': '__cxa_pure_virtual' not in names,
                        'pure_virtual': '__cxa_pure_virtual' in names})
    return {'vtable_bytes': elf.symbols[symbol].st_size,
            'primary_prefix': [r['address'] for r in rows[:3]], 'callback_order': checked}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--require-layout-match', action='store_true',
                        help='Return failure when any inspected vtable layout differs')
    args = parser.parse_args()
    manifest = json.loads((ROOT / 'reports/vr-integration/factory-system.json').read_text())
    results = []
    for directory in ('lib64', 'lib'):
        virtual = '/system/' + directory + '/libgui.so'
        entry = next(e for e in manifest['entries'] if e['path'] == virtual)
        factory, a = p.inspect(p.host_path(PurePosixPath(manifest['tree']) / virtual.lstrip('/')))
        built, b = p.inspect(p.host_path(p.PROJECT / 'out/aosp-10/target/product/PICOA8110/system' / directory / 'libgui.so'))
        if factory['sha256'] != entry['sha256']:
            raise RuntimeError('Factory input changed')
        tables = {}
        for symbol in TABLES:
            x, y = check_table(a, symbol), check_table(b, symbol)
            tables[symbol] = {'factory': x, 'source': y,
                              'vtable_size_matches': x['vtable_bytes'] == y['vtable_bytes'],
                              'primary_prefix_matches': x['primary_prefix'] == y['primary_prefix'],
                              'callback_order_matches': x['callback_order'] == y['callback_order']}
            if symbol.endswith('12ConsumerBaseE'):
                getter = 'getLatchAcquireSlotLocked'
                for label, elf in [('factory', a), ('source', b)]:
                    names = p.aliases(elf)
                    slots = []
                    for index, row in enumerate(elf.vtable(symbol)):
                        candidates = {row['symbol']} if row['symbol'] else names.get(row['address'], set())
                        if any(getter + 'E' in n for n in candidates):
                            slots.append(index * elf.width)
                    tables[symbol][label]['latch_getter_offsets_from_vtable_start'] = slots
                tables[symbol]['latch_getter_slots_match'] = (
                    tables[symbol]['factory']['latch_getter_offsets_from_vtable_start'] ==
                    tables[symbol]['source']['latch_getter_offsets_from_vtable_start'])
        result = {'abi': factory['abi'], 'factory_sha256': factory['sha256'],
                  'source_sha256': built['sha256'], 'tables': tables,
                  'on_disconnect_already_present_in_pinned_aosp': True,
                  'full_libgui_abi_proven': False}
        if a.width == 8:
            offset = a.file_offset(0x557d8, 5)
            targets = [0x7f898 + byte * 4 for byte in a.data[offset:offset + 5]]
            if targets != [0x7f898, 0x7f914, 0x7f8b4, 0x7f8bc, 0x7f8d8]:
                raise RuntimeError('Factory consumer Binder commands differ')
            result['factory_binder_commands'] = dict(zip(METHODS[:5], range(1, 6)))
        results.append(result)
        differences = [name for name, table in tables.items()
                       if not table['vtable_size_matches'] or not table['primary_prefix_matches']
                       or not table['callback_order_matches']
                       or not table.get('latch_getter_slots_match', True)]
        result['layout_differences'] = differences
        print(str(factory['abi']) + ': consumer callback slots inspected; layout differences: '
              + ', '.join(differences))
    (ROOT / 'validation/consumer-listener.json').write_text(json.dumps(results, indent=2) + '\n')
    if args.require_layout_match and any(r['layout_differences'] for r in results):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
