"""Revalidate PICO cached-buffer and unfreeze observations without executing ELF.

Instruction checkpoints support specific recovered decisions, not whole-class
layout compatibility or complete FreezeManager reconstruction.
"""
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('producer_inspector', ROOT / 'tools/inspect-producer-fence.py')
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)

GUI_SHA = '7b52e5bc29cf5d68c1b24ce6701535dcae64131e3c83b685713ea4a0b4b6dcc5'
BINDER_SHA = '9e5bdf585d73baddf17bbc646b4daea0e2b15d4fb6d8dc244d08412dd1be86a9'
CHECKS = [
    (0x76b98, '942100b4', 'reject null outSlot'),
    (0x76b9c, '360100b5', 'nonzero ID permits absent buffer'),
    (0x76ba4, 'e80000b5', 'buffer permits zero ID'),
    (0x76c20, '085440b9', 'require connected producer'),
    (0x76c2c, '08686838', 'reject shared mode'),
    (0x76c78, '160300b4', 'zero ID bypasses cached-ID lookup'),
    (0x76c80, 'c80200b5', 'provided buffer bypasses cached-ID lookup'),
    (0x76cc8, 'f77b1f32', 'missing cached ID returns -2'),
    (0x76ce4, 'e1030032', 'use Attach free-slot caller'),
    (0x76d48, '880200b9', 'write selected slot'),
    (0x76d90, 'f60500b4', 'zero ID bypasses buffer replacement'),
    (0x76da4, '9f870194', 'provided buffer cached by helper'),
    (0x76e48, '7a870194', 'absent buffer fetched by helper'),
    (0x76e64, '29050011', 'attach increments producer dequeue state'),
    (0x76eb0, '09810039', 'request-buffer flag set true'),
    (0x76ec4, '1f010139', 'acquire flag cleared'),
    (0x76ed8, '1f050139', 'reallocation flag cleared'),
    (0x77160, '0a1900f9', 'fetch refreshes access timestamp'),
    (0x77168, '141540f9', 'fetch retains cached GraphicBuffer'),
    (0x771cc, '186d40f9', 'cache key is actual GraphicBuffer ID'),
    (0x771d0, '3f1500f1', 'evict when existing cache size is at least five'),
    (0x77244, 'bf0109eb', 'LRU compares access timestamps'),
    (0x7729c, '69860194', 'evict before map lookup/update'),
    (0x77464, 'b61a00f9', 'cache refreshes access timestamp'),
    (0x799b8, '3e7c0194', 'successful disconnect destroys cache nodes'),
    (0x799c0, '7ffe12a9', 'disconnect clears cache root and size'),
    (0x799c4, '749200f9', 'disconnect restores empty-tree begin pointer'),
    (0x7aa48, '12780194', 'listenFreezeSelf obtains FreezeManager'),
    (0x7aa78, 'b6780194', 'register self-unfreeze listener'),
    (0x7b034, '686e40f9', 'unfreeze callback reads producer flag pointer at 216'),
    (0x7b03c, '09010039', 'unfreeze callback sets pointed boolean true'),
    (0x736dc, 'f1940194', 'producer destructor unregisters self-unfreeze listener'),
]


def main():
    data = p.host_path(p.PROJECT / 'analysis/stock-5.13.7-system/root/system/lib64/libgui.so').read_bytes()
    if hashlib.sha256(data).hexdigest() != GUI_SHA:
        raise RuntimeError('Wrong pinned factory libgui')
    elf = p.pointers.ElfPointers(data)
    for address, expected, _ in CHECKS:
        start = elf.file_offset(address, 4)
        if data[start:start + 4].hex() != expected:
            raise RuntimeError('Instruction changed at ' + hex(address))
    binder_data = p.host_path(p.PROJECT / 'analysis/stock-5.13.7-system/root/system/lib64/libbinder.so').read_bytes()
    if hashlib.sha256(binder_data).hexdigest() != BINDER_SHA:
        raise RuntimeError('Wrong pinned factory libbinder')
    binder = p.pointers.ElfPointers(binder_data)
    provider = {}
    for fragment in ['11getInstanceE', '28registerSelfUnFreezeListenerE',
                     '30unRegisterSelfUnFreezeListenerE']:
        found = [(name, entry) for name, entry in binder.symbols.items()
                 if 'FreezeManager' in name and fragment in name]
        if len(found) != 1:
            raise RuntimeError('Unfreeze provider identity differs')
        name, entry = found[0]
        provider[name] = {'address': hex(entry.st_value), 'bytes': entry.st_size}
    result = {
        'factory_gui_sha256': GUI_SHA, 'factory_binder_sha256': BINDER_SHA,
        'abi': 64, 'cache_capacity': 5, 'eviction': 'least access counter before insertion/update',
        'lookup_missing_status': -2, 'lookup_present_status': -17,
        'register_key': 'actual GraphicBuffer ID; supplied nonzero ID only enables cache path',
        'zero_id': 'retains selected slot buffer even if a different buffer argument is provided',
        'generation_check_in_cached_attach_observed': False,
        'producer_cache_offset': 288,
        'successful_disconnect_clears_cache': True,
        'factory_code_executed_by_inspector': False,
        'freeze_provider': 'libbinder.so', 'freeze_provider_methods': provider,
        'freeze_behavior_ported': False,
        'pending': ['FreezeManager Binder contract and callback lifetime port',
                    'producer fields for unfreeze refresh and complete class layout',
                    'concurrent cache eviction during slot wait qualification',
                    'full ARM32 instruction comparison'],
        'instructions': [{'address': hex(a), 'bytes': b, 'observation': c} for a, b, c in CHECKS],
    }
    (ROOT / 'validation/cached-buffer-research.json').write_text(json.dumps(result, indent=2) + '\n')
    print(f'Verified {len(CHECKS)} PICO cached-buffer/unfreeze instruction checkpoints and Binder provider identities')


if __name__ == '__main__':
    main()
