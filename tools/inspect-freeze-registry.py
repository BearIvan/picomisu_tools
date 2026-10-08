"""Revalidate recovered FreezeManager self/PID facade and source prefix layout.

Private map node ownership differs deliberately. Remote/frozen-PID paths and
the complete private type ABI are not qualified by this inspector.
"""
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('producer_inspector', ROOT / 'tools/inspect-producer-fence.py')
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)
FACTORY_SHA = '9e5bdf585d73baddf17bbc646b4daea0e2b15d4fb6d8dc244d08412dd1be86a9'
CHECKS = [
    (0x56518, '00128052', 'singleton allocation is 144 bytes'),
    (0x56174, '9f8e00f8', 'callback strong pointer at offset 8'),
    (0x56178, 'e20c0194', 'service mutex starts at offset 16'),
    (0x56244, '604200b9', 'process PID at offset 64'),
    (0x56584, '08e28452', 'public PID register UID threshold is 10000'),
    (0x5658c, '6c020054', 'UID threshold uses signed greater-than'),
    (0x56634, '8b0c0194', 'inner PID register reaches service without UID guard'),
    (0x566e0, '081540f9', 'explicit PID unregister invokes service slot 40'),
    (0x56d98, 'a84640f9', 'self registry size read at 136'),
    (0x56e28, 'b94240b9', 'first self registration uses process PID'),
    (0x56e50, '081140f9', 'first self registration invokes service slot 32'),
    (0x56eb8, 'a0e20191', 'self registry starts at 120'),
    (0x56ec8, '820a0194', 'self registration emplaces a unique key'),
    (0x56fb4, '80e20191', 'self unregister accesses registry at 120'),
    (0x56fbc, '490a0194', 'self unregister erases local key without remote unregister'),
    (0x57a04, '094140b9', 'self callback reads process PID at 64'),
    (0x57a0c, 'a1080054', 'self callback filters PID equality'),
    (0x57a10, '173d40f9', 'self callback iterates registry begin at 120'),
    (0x57a80, '081b40f9', 'self callback passes saved argument at record offset 48'),
    (0x57b84, '93060194', 'registry lock remains held until callbacks finish'),
    (0x57040, '2c0a0194', 'remote registration depends on getLastFrozenPid'),
]
FIELDS = {'mCallback': 8, 'mServiceMutex': 16, 'mService': 56, 'mPid': 64,
          'mOnceRegistry': 72, 'mPersistentRegistry': 96, 'mSelfRegistry': 120}


def shape(elf):
    for cu in elf.elf.get_dwarf_info().iter_CUs():
        name = cu.get_top_DIE().attributes.get('DW_AT_name')
        if not name or not name.value.endswith(b'libs/binder/FreezeManager.cpp'):
            continue
        for die in cu.iter_DIEs():
            name = die.attributes.get('DW_AT_name')
            if not name or name.value != b'FreezeManager' or 'DW_AT_byte_size' not in die.attributes:
                continue
            return {'bytes': die.attributes['DW_AT_byte_size'].value,
                    'fields': {child.attributes['DW_AT_name'].value.decode():
                               child.attributes['DW_AT_data_member_location'].value
                               for child in die.iter_children()
                               if child.tag == 'DW_TAG_member' and 'DW_AT_data_member_location' in child.attributes}}
    raise RuntimeError('Missing FreezeManager source DWARF')


def main():
    data = p.host_path(p.PROJECT / 'analysis/stock-5.13.7-system/root/system/lib64/libbinder.so').read_bytes()
    if hashlib.sha256(data).hexdigest() != FACTORY_SHA:
        raise RuntimeError('Wrong pinned factory Binder')
    factory = p.pointers.ElfPointers(data)
    for address, expected, _ in CHECKS:
        start = factory.file_offset(address, 4)
        if data[start:start + 4].hex() != expected:
            raise RuntimeError('Instruction changed at ' + hex(address))
    source_data = p.host_path(p.PROJECT / 'out/aosp-10/target/product/PICOA8110/symbols/system/lib64/libbinder.so').read_bytes()
    source = p.pointers.ElfPointers(source_data)
    layout = shape(source)
    if layout['bytes'] != 144 or any(layout['fields'].get(n) != v for n, v in FIELDS.items()):
        raise RuntimeError('Recovered manager prefix differs')
    fa, sa = p.aliases(factory), p.aliases(source)
    tables = {}
    for name in ['_ZTVN7android13FreezeManagerE', '_ZTVN7android13FreezeManager8CallbackE']:
        fs, ss = factory.symbols[name], source.symbols[name]
        if fs.st_size != ss.st_size:
            raise RuntimeError('Manager/callback vtable extent differs')
        for offset in range(0, fs.st_size, 8):
            fp, sp = factory.pointer(fs.st_value + offset), source.pointer(ss.st_value + offset)
            fn = fa.get(fp['address'], set()) | ({fp['symbol']} if fp['symbol'] else set())
            sn = sa.get(sp['address'], set()) | ({sp['symbol']} if sp['symbol'] else set())
            if not (bool(fn & sn) if fn or sn else fp == sp):
                raise RuntimeError('Manager/callback slot differs: ' + name + '+' + str(offset))
        tables[name] = {'bytes': fs.st_size, 'slots_matched': fs.st_size // 8}
    arm_data = p.host_path(p.PROJECT / 'out/aosp-10/target/product/PICOA8110/symbols/system/lib/libbinder.so').read_bytes()
    result = {'factory_sha256': FACTORY_SHA, 'source_sha256': hashlib.sha256(source_data).hexdigest(),
              'source_arm64_shape': layout, 'source_arm32_shape': shape(p.pointers.ElfPointers(arm_data)),
              'arm64_vtables': tables, 'recovered_arm64_prefix_matches': True,
              'full_private_type_abi_proven': False,
              'source_differences': ['shared ownership releases callback records on removal',
                                     'recursive registry lock and snapshot support reentrant removal'],
              'remote_registry_behavior_ported': False,
              'instructions': [{'address': hex(a), 'bytes': b, 'observation': c} for a, b, c in CHECKS]}
    (ROOT / 'validation/freeze-registry-abi.json').write_text(json.dumps(result, indent=2) + '\n')
    print(f'ARM64 manager prefix/vtables match; verified {len(CHECKS)} registry instruction checkpoints')


if __name__ == '__main__':
    main()
