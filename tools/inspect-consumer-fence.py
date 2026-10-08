"""Verify the local-only consumer vtable tail and latch getter field offset.

Uses the same authenticated inputs and ARM relocation decoder as the producer
inspector. It does not establish complete BufferQueue or ConsumerBase layout.
"""
import importlib.util
import json
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('producer_inspector', ROOT / 'tools/inspect-producer-fence.py')
producer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(producer)

TABLES = ['_ZTVN7android22IGraphicBufferConsumerE',
          '_ZTVN7android23BnGraphicBufferConsumerE',
          '_ZTVN7android23BpGraphicBufferConsumerE',
          '_ZTVN7android19BufferQueueConsumerE']
GETTER = '_ZN7android12ConsumerBase25getLatchAcquireSlotLockedEv'


def main():
    manifest = json.loads((ROOT / 'reports/vr-integration/factory-system.json').read_text())
    results = []
    for directory in ('lib64', 'lib'):
        virtual = '/system/' + directory + '/libgui.so'
        entry = next(e for e in manifest['entries'] if e['path'] == virtual)
        factory, a = producer.inspect(producer.host_path(PurePosixPath(manifest['tree']) / virtual.lstrip('/')))
        built, b = producer.inspect(producer.host_path(producer.PROJECT / 'out/aosp-10/target/product/PICOA8110/system' / directory / 'libgui.so'))
        if factory['sha256'] != entry['sha256']:
            raise RuntimeError('Factory libgui changed')
        tables = {}
        for symbol in TABLES:
            x, y = a.vtable(symbol), b.vtable(symbol)
            # Three prefix words, two destructors, two interface functions,
            # twenty standard consumer methods, then local notifyFenceReady.
            index = 27
            p, q = x[index], y[index]
            if symbol != TABLES[-1]:
                expected = b'\xe0\x03\x1f\x2a\xc0\x03\x5f\xd6' if a.width == 8 else b'\x00\x20\x70\x47'
                for elf, row in [(a, p), (b, q)]:
                    offset = elf.file_offset(row['address'] & ~1, len(expected))
                    if elf.data[offset:offset + len(expected)] != expected:
                        raise RuntimeError('Local default is not the verified return-zero stub')
            else:
                if 'notifyFenceReady' not in (p['symbol'] or '') or 'notifyFenceReady' not in (q['symbol'] or ''):
                    raise RuntimeError('Local override not found at the factory vtable position')
            tables[symbol] = {'vtable_size_matches': a.symbols[symbol].st_size == b.symbols[symbol].st_size,
                              'primary_prefix_matches': [r['address'] for r in x[:3]] == [r['address'] for r in y[:3]],
                              'local_notify_slot_verified': True}
            if not all(tables[symbol].values()):
                raise RuntimeError('Consumer interface group differs: ' + symbol)
        body = []
        for elf in (a, b):
            symbol = elf.symbols[GETTER]
            offset = elf.file_offset(symbol.st_value & ~1, symbol.st_size)
            body.append(elf.data[offset:offset + symbol.st_size].hex())
        if body[0] != body[1]:
            raise RuntimeError('Latch slot getter field offset differs')
        results.append({'abi': factory['abi'], 'factory_libgui_sha256': factory['sha256'],
                        'source_libgui_sha256': built['sha256'], 'consumer_vtables': tables,
                        'latch_getter_body_matches': True, 'getter_body_hex': body[0],
                        'new_binder_transaction_defined': False, 'full_libgui_abi_proven': False})
        print(str(factory['abi']) + ': local consumer tail and latch getter match factory')
    (ROOT / 'validation/consumer-fence-abi.json').write_text(json.dumps(results, indent=2) + '\n')


if __name__ == '__main__':
    main()
