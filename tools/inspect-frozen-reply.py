"""Revalidate PICO 10 Binder frozen reply and the source PID field.

ARM64 instruction checks and source DWARF complement the intercepted-ioctl
factory comparisons. This does not qualify real kernel IPC, remote freeze
registration, the full IPCThreadState ABI, or stalled-buffer recovery.
"""
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('producer_inspector', ROOT / 'tools/inspect-producer-fence.py')
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)
FACTORY_SHA64 = '9e5bdf585d73baddf17bbc646b4daea0e2b15d4fb6d8dc244d08412dd1be86a9'
GETTER = '_ZNK7android14IPCThreadState16getLastFrozenPidEv'
CHECKS = [
    (0x6a338, '7fce01b9', 'constructor initializes PID field at 460 to zero'),
    (0x6a7d0, '00cc41b9', 'getter reads signed int32 field at 460'),
    (0x6a7d4, 'c0035fd6', 'getter returns'),
    (0x69b78, 'a9000010', 'dispatch base is 0x69b8c'),
    (0x69b7c, '8a6b6838', 'dispatch loads a byte from the command table'),
    (0x69b80, '29090a8b', 'dispatch scales table byte by four'),
    (0x69ea8, '6abf0094', 'frozen reply reads legacy Parcel int32 PID'),
    (0x69eac, '48008052', 'error construction starts with 2'),
    (0x69eb0, '0800b072', 'error construction adds high bits 0x80000000'),
    (0x69eb4, '60ce01b9', 'frozen reply saves PID at 460'),
    (0x69eb8, '181d0011', 'error construction adds 7: status 0x80000009'),
]
FIELDS64 = {'mIn': 168, 'mOut': 288, 'mCallRestriction': 456, 'mLastFrozenPid': 460}


def read(relative):
    data = p.host_path(p.PROJECT / relative).read_bytes()
    return p.pointers.ElfPointers(data), hashlib.sha256(data).hexdigest()


def shape(elf):
    for cu in elf.elf.get_dwarf_info().iter_CUs():
        name = cu.get_top_DIE().attributes.get('DW_AT_name')
        if not name or not name.value.endswith(b'libs/binder/IPCThreadState.cpp'):
            continue
        for die in cu.iter_DIEs():
            name = die.attributes.get('DW_AT_name')
            if not name or name.value != b'IPCThreadState' or 'DW_AT_byte_size' not in die.attributes:
                continue
            return {'bytes': die.attributes['DW_AT_byte_size'].value,
                    'fields': {child.attributes['DW_AT_name'].value.decode():
                               child.attributes['DW_AT_data_member_location'].value
                               for child in die.iter_children()
                               if child.tag == 'DW_TAG_member' and 'DW_AT_data_member_location' in child.attributes}}
    raise RuntimeError('Missing IPCThreadState source DWARF')


def main():
    factory, digest = read('analysis/stock-5.13.7-system/root/system/lib64/libbinder.so')
    if digest != FACTORY_SHA64:
        raise RuntimeError('Wrong pinned factory libbinder')
    for address, expected, _ in CHECKS:
        start = factory.file_offset(address, 4)
        if factory.data[start:start + 4].hex() != expected:
            raise RuntimeError('Instruction changed at ' + hex(address))
    table_start = factory.file_offset(0x41960, 14)
    table = factory.data[table_start:table_start + 14]
    if table.hex() != '13000a0a0a0a0a0a0a0a0a0acec6':
        raise RuntimeError('Frozen reply dispatch table changed')
    target = 0x69b8c + table[0x7212 - 0x7205] * 4
    if target != 0x69ea4:
        raise RuntimeError('Frozen reply dispatch target changed')

    source_rows = []
    for bits, directory in [(64, 'lib64'), (32, 'lib')]:
        source, source_digest = read('out/aosp-10/target/product/PICOA8110/symbols/system/' + directory + '/libbinder.so')
        layout = shape(source)
        if GETTER not in source.symbols or 'mLastFrozenPid' not in layout['fields']:
            raise RuntimeError('Missing source frozen PID getter or field')
        getter = source.symbols[GETTER]
        address = getter.st_value & ~1 if bits == 32 else getter.st_value
        start = source.file_offset(address, getter.st_size)
        body = source.data[start:start + getter.st_size]
        if bits == 64:
            if layout['bytes'] != 464 or any(layout['fields'].get(n) != v for n, v in FIELDS64.items()):
                raise RuntimeError('Recovered ARM64 source PID layout differs')
            if body.hex() != '00cc41b9c0035fd6':
                raise RuntimeError('ARM64 source getter differs from factory body')
        source_rows.append({'abi': bits, 'source_symbols_sha256': source_digest,
                            'shape': layout, 'getter_bytes': body.hex(),
                            'factory_layout_instruction_match_proven': bits == 64})
    result = {'factory_arm64_sha256': digest, 'source': source_rows,
              'command': '0x7212', 'payload': 'legacy int32 PID despite zero ioctl size bits',
              'status': '0x80000009', 'status_signed': -2147483639,
              'dispatch_table': {'address': '0x41960', 'bytes': table.hex(),
                                 'command_base': '0x7205', 'dispatch_base': '0x69b8c',
                                 'frozen_reply_target': hex(target)},
              'instructions': [{'address': hex(a), 'bytes': b, 'observation': c} for a, b, c in CHECKS],
              'full_private_type_abi_proven': False,
              'real_kernel_ipc_qualified': False,
              'runtime_evidence': 'validation/native-runtime-current.json',
              'scope': 'ARM64 factory instructions/getter and selected source fields; ARM32 source shape recorded, factory behavior compared separately'}
    (ROOT / 'validation/frozen-reply-abi.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(f'ARM64 frozen reply/getter checkpoints match; verified {len(CHECKS)} instructions; ARM32 source shape recorded')


if __name__ == '__main__':
    main()
