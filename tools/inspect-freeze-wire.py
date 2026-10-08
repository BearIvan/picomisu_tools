"""Check reconstructed PICO freeze Binder slots and transaction instructions.

No service lookup or executable library loading is performed. This does not
qualify FreezeManager registration lifetime, real IPC or buffer recovery.
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
TABLES = [
    '_ZTVN7android14IFreezeManagerE', '_ZTVN7android15BpFreezeManagerE',
    '_ZTVN7android17IUnFreezeCallbackE', '_ZTVN7android18BpUnFreezeCallbackE',
    '_ZTVN7android18BnUnFreezeCallbackE',
]
CHECKS = [
    (0x61848, 'b6e00094', 'register writes PID int32 first'),
    (0x61880, 'ace00094', 'register writes strong callback Binder second'),
    (0x618c4, 'e7e10094', 'register writes bool third'),
    (0x618cc, 'e1030032', 'register transaction 1'),
    (0x618dc, 'e4031f2a', 'register flags 0'),
    (0x6197c, '69e00094', 'unregister writes PID int32 first'),
    (0x619b4, '5fe00094', 'unregister writes callback Binder second'),
    (0x619f4, 'e1031f32', 'unregister transaction 2'),
    (0x61a04, 'e4031f2a', 'unregister flags 0'),
    (0x700dc, '91a60094', 'callback writes int32 PID'),
    (0x700e4, 'e1030032', 'callback transaction 1'),
    (0x700f4, 'e4030032', 'callback flags 1 (oneway)'),
    (0x6ff24, '3f040071', 'callback server recognizes transaction 1'),
    (0x6ff3c, '51a80094', 'callback checks interface token'),
    (0x6ff48, '42a70094', 'callback reads legacy int32 PID'),
    (0x6ff58, '081140f9', 'callback dispatches virtual slot 32'),
    (0x6ff60, 'e0031f2a', 'callback returns status 0 without writing reply'),
]


def read(relative):
    data = p.host_path(p.PROJECT / relative).read_bytes()
    return p.pointers.ElfPointers(data), hashlib.sha256(data).hexdigest()


def slot(elf, aliases, address):
    row = elf.pointer(address)
    return row, aliases.get(row['address'], set()) | ({row['symbol']} if row['symbol'] else set())


def main():
    rows = []
    for bits, directory in [(64, 'lib64'), (32, 'lib')]:
        factory, digest = read('analysis/stock-5.13.7-system/root/system/' + directory + '/libbinder.so')
        if bits == 64:
            if digest != FACTORY_SHA64:
                raise RuntimeError('Wrong pinned factory libbinder')
            for address, expected, _ in CHECKS:
                start = factory.file_offset(address, 4)
                if factory.data[start:start + 4].hex() != expected:
                    raise RuntimeError('Instruction changed at ' + hex(address))
            start = factory.file_offset(0x409db, 7)
            if factory.data[start:start + 7] != b'freeze\0':
                raise RuntimeError('Factory service lookup name changed')
        else:
            manifest = json.loads((ROOT / 'reports/vr-integration/factory-system.json').read_text())
            entry = next(e for e in manifest['entries'] if e['path'] == '/system/lib/libbinder.so')
            if digest != entry['sha256']:
                raise RuntimeError('Wrong authenticated ARM32 factory libbinder')
        source, source_digest = read('out/aosp-10/target/product/PICOA8110/system/' + directory + '/libbinder.so')
        fa, sa = p.aliases(factory), p.aliases(source)
        tables = {}
        for name in TABLES:
            f, s = factory.symbols[name], source.symbols[name]
            if f.st_size != s.st_size:
                raise RuntimeError('Freeze interface vtable size differs: ' + name)
            checks = []
            for offset in range(0, f.st_size, factory.width):
                fp, fn = slot(factory, fa, f.st_value + offset)
                sp, sn = slot(source, sa, s.st_value + offset)
                match = bool(fn & sn) if fn or sn else fp == sp
                if not match:
                    raise RuntimeError(f'Freeze slot differs: {name}+{offset}: {sorted(fn)} vs {sorted(sn)}')
                checks.append({'offset': offset, 'kind': 'function identity' if fn or sn else 'metadata'})
            tables[name] = {'bytes': f.st_size, 'slots_matched': len(checks)}
        rows.append({'abi': bits, 'factory_sha256': digest, 'source_sha256': source_digest,
                     'tables': tables, 'all_examined_slots_matched': True})
        print(f'ARM{bits}: all slots of five freeze Binder interface vtables match')
    result = {'interfaces': rows, 'service_name': 'freeze',
              'manager_descriptor': 'android.app.IFreezeManager',
              'callback_descriptor': 'android.app.IUnFreezeCallback',
              'register': {'code': 1, 'flags': 0, 'fields': ['int32 PID', 'strong callback Binder', 'bool']},
              'unregister': {'code': 2, 'flags': 0, 'fields': ['int32 PID', 'strong callback Binder']},
              'callback': {'code': 1, 'flags': 1, 'fields': ['int32 PID'], 'reply_payload_bytes': 0},
              'manager_methods_return_void_and_ignore_transport_status': True,
              'scope': 'interface identities/metadata and ARM64 instruction checkpoints; no real-service or complete FreezeManager behavior qualification',
              'instructions': [{'address': hex(a), 'bytes': b, 'observation': c} for a, b, c in CHECKS]}
    (ROOT / 'validation/freeze-wire-abi.json').write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    main()
