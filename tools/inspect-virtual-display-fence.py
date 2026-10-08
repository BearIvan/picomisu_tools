"""Revalidate the recovered ARM64 VirtualDisplaySurface fence path.

The private table is located through constructor instructions, not an exported
class symbol. This verifies specific observations, not the complete implementation.
"""
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('producer_inspector', ROOT / 'tools/inspect-producer-fence.py')
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)

CHECKS = [
    (0xadd30, 'a80600f0', 'constructor loads private vtable page'),
    (0xadd34, '08a13e91', 'constructor adds vtable base offset'),
    (0xadd3c, '0a610091', 'primary address point is table+24'),
    (0xade70, '88a23739', 'constructor initializes multi-layer flag true at +3560'),
    (0xb0820, '13003791', 'setSingleLayer uses mutex at +3520'),
    (0xb08f4, '080b41b9', 'record captures composition-layer state int at +264'),
    (0xb0900, '1f200029', 'record initializes refcount and captured slot'),
    (0xb0904, '398c00f8', 'record stores GraphicBuffer at +8'),
    (0xb091c, '280c01f8', 'record stores Layer at +16'),
    (0xb0934, 'bc1a00b9', 'record stores outstanding count at +24'),
    (0xb0a04, '1c050011', 'repeated ID increments previous outstanding count'),
    (0xb0544, '5f0400b1', 'release callback rejects buffer ID UINT64_MAX'),
    (0xb06ec, '2d030054', 'release count reaching zero selects final release'),
    (0xb06f0, 'a51a00b9', 'nonfinal release stores decremented count'),
    (0xb0778, '081941f9', 'final release invokes Layer virtual slot 560'),
    (0xb0780, '36010036', 'replacement flag controls pending-buffer release'),
    (0xb079c, '081541f9', 'replacement invokes Layer virtual slot 552'),
    (0xb0c70, '08a03739', 'concrete multi-layer setter stores boolean'),
    (0xb0c78, '00a07739', 'concrete multi-layer getter reads boolean'),
    (0x837e8, 'eedb0394', 'consumer optionally adds release fence for matching pending buffer'),
    (0x83820, '086140f9', 'consumer forwards to IGraphicBufferConsumer virtual slot 192'),
    (0xafba4, 'f4eb06a9', 'connect captures raw VDS pointer in bound callback storage'),
    (0xafcb8, '170300f9', 'connect stores newly constructed producer listener'),
    (0xb0f3c, '0005898b', 'bound callback adjusts this by member-pointer delta shifted right'),
    (0xb0f40, '69000036', 'member-pointer low bit selects virtual dispatch'),
    (0xb0f48, '046964f8', 'bound callback loads member from vtable by offset'),
    (0xafe18, 'ff1300f9', 'disconnect constructs empty callback'),
    (0xafe20, '482d0394', 'disconnect clears producer callback first'),
    (0xafe3c, 'e1000094', 'disconnect invokes registry notification helper'),
    (0xb0424, '43280394', 'notification helper unlocks registry before Layer callbacks'),
    (0xb0458, '291941f9', 'notification helper calls Layer notifyFenceReady'),
    (0xafe50, '084540f9', 'disconnect subsequently forwards to sink disconnect'),
]


def main():
    data = p.host_path(p.PROJECT / 'analysis/stock-5.13.7-system/root/system/lib64/libsurfaceflinger.so').read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != 'd23904265c575d67c8818fa5eca24936d78ae137833e1c5383a7a4b09f3bdb51':
        raise RuntimeError('Wrong pinned SurfaceFlinger')
    elf = p.pointers.ElfPointers(data)
    for address, expected, _ in CHECKS:
        offset = elf.file_offset(address, 4)
        if data[offset:offset + 4].hex() != expected:
            raise RuntimeError('Instruction changed at ' + hex(address))
    address_point = (0xadd30 & ~4095) + 880640 + 4008 + 24
    methods = {72: 0xb07f8, 80: 0xb0c6c, 88: 0xb0c78, 96: 0xb0528, 104: 0xb01c0}
    for offset, expected in methods.items():
        if elf.pointer(address_point + offset)['address'] != expected:
            raise RuntimeError('Private VirtualDisplaySurface table differs')
    aliases = p.aliases(elf)
    if elf.word(0x43240) != 96 or elf.word(0x43248) != 1:
        raise RuntimeError('Bound callback member-pointer representation changed')
    if elf.pointer(0x185ef0 + 48)['address'] != 0xb0f34:
        raise RuntimeError('Bound callback invoker changed')
    if elf.pointer(0x195298)['symbol'] != '_ZN7android5Fence8NO_FENCEE':
        raise RuntimeError('Disconnect helper fence changed')
    layer_methods = {}
    for offset, expected in [(552, 'releasePendingBuffer'), (560, 'notifyFenceReady')]:
        row = elf.pointer(0x1805b8 + offset)
        names = aliases.get(row['address'], set()) | ({row['symbol']} if row['symbol'] else set())
        verified = sorted(n for n in names if 'BufferQueueLayer' in n and expected + 'E' in n)
        if not verified:
            raise RuntimeError('Cannot identify BufferQueueLayer callback')
        layer_methods[str(offset)] = verified
    result = {
        'factory_sha256': digest, 'abi': 64, 'primary_address_point': hex(address_point),
        'private_methods': {str(k): hex(v) for k, v in methods.items()},
        'layer_callbacks': layer_methods,
        'record_observations': {'allocation_bytes': 32, 'slot_offset': 4, 'buffer_offset': 8,
                                'layer_offset': 16, 'outstanding_count_offset': 24},
        'registry_observations': {'tree_root_offset': 3504, 'size_offset': 3512,
                                 'mutex_offset': 3520, 'multilayer_offset': 3560},
        'final_callback_after_registry_mutex_unlock': True,
        'registration': {'bound_virtual_slot': 96, 'this_adjustment': 0,
                         'captures_raw_this': True, 'creates_own_producer_listener': True},
        'disconnect_observations': ['clear producer callback',
                                    'snapshot strong record references under registry mutex',
                                    'notify captured layers with NO_FENCE after unlocking',
                                    'disconnect sink'],
        'notification_helper_explicit_registry_erase_observed': False,
        'factory_code_executed': False, 'full_path_ported': False,
        'pending': ['destructor lifetime and concurrent callback qualification',
                    'complete ARM32 comparison', 'source implementation and runtime comparison'],
        'instructions': [{'address': hex(a), 'bytes': b, 'observation': c} for a, b, c in CHECKS],
    }
    (ROOT / 'validation/virtual-display-fence-research.json').write_text(json.dumps(result, indent=2) + '\n')
    print(f'Verified private VDS table, Layer callback identities and {len(CHECKS)} instruction checkpoints')


if __name__ == '__main__':
    main()
