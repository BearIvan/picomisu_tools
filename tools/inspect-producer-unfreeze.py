"""Check the PICO self-unfreeze slot contract and both-ABI listener slot.

Only selected ARM64 factory instructions and source shapes are checked.
Source captures a shared atomic flag instead of factory raw this/heap bool.
Full producer/core layout, real freeze events and GPU fences are not proven.
"""
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('producer_inspector', ROOT / 'tools/inspect-producer-fence.py')
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)
FACTORY_SHA64 = '7b52e5bc29cf5d68c1b24ce6701535dcae64131e3c83b685713ea4a0b4b6dcc5'
TABLE = '_ZTVN7android19BufferQueueProducerE'
LISTEN = '_ZN7android19BufferQueueProducer16listenFreezeSelfEv'
CHECKS = [
    (0x7aa48, '12780194', 'listener obtains FreezeManager singleton'),
    (0x7aa64, 'e10313aa', 'self registration key is producer this'),
    (0x7aa68, 'e3031faa', 'self registration argument is null'),
    (0x7aa6c, 'e4031f2a', 'self registration flag is false'),
    (0x7aa78, 'b6780194', 'register self callback'),
    (0x7b034, '686e40f9', 'callback loads producer flag pointer at 216'),
    (0x7b03c, '09010039', 'callback sets flag byte'),
    (0x7458c, 'ea100034', 'no queued frame bypasses max-count recovery branch'),
    (0x74590, '057d55b9', 'read maximum dequeued count'),
    (0x74594, '3f01056b', 'compare dequeued count with maximum'),
    (0x74598, '8b100054', 'below maximum bypasses recovery branch'),
    (0x745c4, 'c86e40f9', 'at limit read pending flag pointer'),
    (0x745cc, '692a0034', 'no pending event returns INVALID_OPERATION'),
    (0x74600, '8e1140b9', 'candidate uses slot dequeue count at 16'),
    (0x7460c, '7b038d1a', 'last nonzero dequeue-count slot is retained'),
    (0x7467c, '29050051', 'cancel one dequeue ownership count'),
    (0x74680, '090100b9', 'save decremented ownership count'),
    (0x74778, '28670af9', 'increment free-buffer list size'),
    (0x74790, 'b88f0194', 'assign NO_FENCE to recovered slot'),
    (0x747a4, '1f010039', 'consume pending flag'),
    (0x787a8, '1f010039', 'successful queue also clears pending flag'),
]


def read(relative):
    data = p.host_path(p.PROJECT / relative).read_bytes()
    return p.pointers.ElfPointers(data), hashlib.sha256(data).hexdigest()


def shape(elf):
    for cu in elf.elf.get_dwarf_info().iter_CUs():
        name = cu.get_top_DIE().attributes.get('DW_AT_name')
        if not name or not name.value.endswith(b'libs/gui/BufferQueueProducer.cpp'):
            continue
        for die in cu.iter_DIEs():
            name = die.attributes.get('DW_AT_name')
            if not name or name.value != b'BufferQueueProducer' or 'DW_AT_byte_size' not in die.attributes:
                continue
            return {'bytes': die.attributes['DW_AT_byte_size'].value,
                    'fields': {child.attributes['DW_AT_name'].value.decode():
                               child.attributes['DW_AT_data_member_location'].value
                               for child in die.iter_children()
                               if child.tag == 'DW_TAG_member' and 'DW_AT_data_member_location' in child.attributes}}
    raise RuntimeError('Missing producer source DWARF')


def main():
    rows = []
    for bits, directory in [(64, 'lib64'), (32, 'lib')]:
        factory, digest = read('analysis/stock-5.13.7-system/root/system/' + directory + '/libgui.so')
        if bits == 64:
            if digest != FACTORY_SHA64:
                raise RuntimeError('Wrong pinned factory GUI')
            for address, expected, _ in CHECKS:
                start = factory.file_offset(address, 4)
                if factory.data[start:start + 4].hex() != expected:
                    raise RuntimeError('Instruction changed at ' + hex(address))
        else:
            manifest = json.loads((ROOT / 'reports/vr-integration/factory-system.json').read_text(encoding='utf-8'))
            expected = next(e['sha256'] for e in manifest['entries'] if e['path'] == '/system/lib/libgui.so')
            if digest != expected:
                raise RuntimeError('Wrong authenticated ARM32 factory GUI')
        source, source_digest = read('out/aosp-10/target/product/PICOA8110/symbols/system/' + directory + '/libgui.so')
        offset = 272 if bits == 64 else 136
        for owner in [factory, source]:
            table = owner.symbols[TABLE]
            if owner.pointer(table.st_value + offset)['address'] != owner.symbols[LISTEN].st_value:
                raise RuntimeError('Producer self-listener virtual slot differs')
        layout = shape(source)
        if 'mPicoUnfreezePending' not in layout['fields']:
            raise RuntimeError('Missing source pending flag ownership')
        rows.append({'abi': bits, 'factory_sha256': digest, 'source_symbols_sha256': source_digest,
                     'listener_vtable_offset': offset, 'listener_slot_identity_matches': True,
                     'source_shape': layout})
    result = {'producers': rows,
              'instructions': [{'address': hex(a), 'bytes': b, 'observation': c} for a, b, c in CHECKS],
              'trigger': 'queued frame exists, producer dequeue count reaches maximum, pending self-unfreeze event',
              'slot_rule': 'last active slot with nonzero dequeue count; cancel one, move to free buffers, clear fence',
              'source_differences': ['shared atomic flag capture avoids raw producer callback access and data race'],
              'full_private_type_abi_proven': False, 'real_freeze_events_qualified': False,
              'gpu_fences_qualified': False,
              'runtime_evidence': 'validation/native-runtime-current.json'}
    (ROOT / 'validation/producer-unfreeze-abi.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(f'Self-listener slot matches both ABIs; verified {len(CHECKS)} ARM64 unfreeze checkpoints')


if __name__ == '__main__':
    main()
