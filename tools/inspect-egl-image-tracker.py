"""Verify tracker interface and instruction evidence against pinned PICO ELF.

This checks the tracker group on both ABIs. It does not prove the full libgui
object ABI, real EGL image lifetime, or hardware graphics compatibility.
"""
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('producer_inspector', ROOT / 'tools/inspect-producer-fence.py')
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)

FACTORY = {
    'lib64': {
        'sha256': '7b52e5bc29cf5d68c1b24ce6701535dcae64131e3c83b685713ea4a0b4b6dcc5',
        'implementation_allocation_bytes': 144,
        'no_op_allocation_bytes': 8,
        'checkpoints': [
            (0xa44a8, '7ad60094', 'read the tracker debug property'),
            (0xa44b4, '00030034', 'atoi zero selects the no-op implementation'),
            (0xa44b8, '00128052', 'enabled implementation allocation is 144 bytes'),
            (0xa4514, 'e0031d32', 'no-op implementation allocation is 8 bytes'),
            (0xa450c, '1f7c08a9', 'initialize the two total counters to zero'),
            (0xa4638, '081440f9', 'read the create count for an origin'),
            (0xa4640, '081400f9', 'write the incremented create count'),
            (0xa4654, '684240f9', 'read total created at offset 128'),
            (0xa4660, '684200f9', 'write total created at offset 128'),
            (0xa4770, '081440f9', 'read the destroy count for an origin'),
            (0xa4778, '081400f9', 'write the incremented destroy count'),
            (0xa478c, '684640f9', 'read total destroyed at offset 136'),
            (0xa4798, '684600f9', 'write total destroyed at offset 136'),
            (0xa4800, 'a82648a9', 'dump reads the two total counters'),
        ],
    },
    'lib': {
        'sha256': '09e91a368003bf8112abaf4adc98f1a78df9ac88ada3f9c81f1eb12f51e68db0',
        'implementation_allocation_bytes': 64,
        'no_op_allocation_bytes': 4,
        'checkpoints': [
            (0x731d4, 'd8b1', 'atoi zero selects the no-op implementation'),
            (0x731d6, '4020', 'enabled implementation allocation is 64 bytes'),
            (0x7320e, '0420', 'no-op implementation allocation is 4 bytes'),
        ],
    },
}

DONOR_FILES = {
    'libs/gui/DebugEGLImageTracker.cpp': '59ef09b182e23b5f484f9ac4caabbf278abdedaf123147aca4c2782af4ea3aa1',
    'libs/gui/include/gui/DebugEGLImageTracker.h': '6ebb51047bd63b553b8908c3f952a645da7a2c460ccec7b517faaa214319020d',
}


def tracker_tables(elf):
    aliases = p.aliases(elf)
    result = {}
    for kind in ('Impl', 'NoOp'):
        class_name = 'DebugEGLImageTracker' + kind
        table_name = '_ZTV24' + class_name
        table = elf.vtable(table_name)
        if len(table) != 7 or elf.symbols[table_name].st_size != 7 * elf.width:
            raise RuntimeError('Unexpected tracker vtable size: ' + kind)
        expected = ['6createEPKc', '7destroyEPKc',
                    '4dumpERNSt3__112basic_stringIcNS0_11char_traitsIcEENS0_9allocatorIcEEEE',
                    'D2Ev', 'D0Ev']
        methods = []
        for index, suffix in enumerate(expected):
            row = table[index + 2]
            names = set(aliases.get(row['address'], set()))
            if row['symbol']:
                names.add(row['symbol'])
            symbol = '_ZN24' + class_name + suffix
            accepted = {symbol}
            # PICO folds the empty NoOp destructor into the empty base destructor.
            if kind == 'NoOp' and suffix == 'D2Ev':
                accepted.add('_ZN20DebugEGLImageTrackerD2Ev')
            if not accepted & names:
                raise RuntimeError('Tracker method order differs: ' + symbol)
            methods.append({'offset_from_address_point': index * elf.width, 'symbol': symbol})
        result[kind] = {'vtable_bytes': 7 * elf.width, 'methods': methods}
    return result


def main():
    result = {'donor_project': 'platform/frameworks/native',
              'donor_revision': '71e1890b755f126274e8225875050c7b785006e4',
              'source_files_match_pinned_donor': True, 'donor_file_sha256': DONOR_FILES,
              'scope': 'Tracker public interface and authenticated factory instruction evidence',
              'full_libgui_abi_proven': False, 'real_egl_lifecycle_qualified': False, 'abis': {}}
    for relative, expected in DONOR_FILES.items():
        path = p.host_path(p.PROJECT / 'source/aosp-10/frameworks/native' / relative)
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise RuntimeError('Source tracker differs from pinned donor: ' + relative)
    for directory, entry in FACTORY.items():
        factory_path = p.host_path(p.PROJECT / 'analysis/stock-5.13.7-system/root/system' / directory / 'libgui.so')
        data = factory_path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        if digest != entry['sha256']:
            raise RuntimeError('Pinned factory library changed: ' + directory)
        factory = p.pointers.ElfPointers(data)
        if b'debug.sf.enable_egl_image_tracker\0' not in data:
            raise RuntimeError('Tracker property is absent')
        checks = []
        for address, expected, observation in entry['checkpoints']:
            offset = factory.file_offset(address, len(bytes.fromhex(expected)))
            if data[offset:offset + len(bytes.fromhex(expected))].hex() != expected:
                raise RuntimeError('Tracker instruction differs: ' + hex(address))
            checks.append({'address': hex(address), 'bytes': expected, 'observation': observation})
        built_path = p.host_path(p.PROJECT / 'out/aosp-10/target/product/PICOA8110/system' / directory / 'libgui.so')
        built_data = built_path.read_bytes()
        built = p.pointers.ElfPointers(built_data)
        factory_tables = tracker_tables(factory)
        source_tables = tracker_tables(built)
        if factory_tables != source_tables:
            raise RuntimeError('Tracker interface differs on ' + directory)
        if '_ZN20DebugEGLImageTracker11getInstanceEv' not in built.symbols:
            raise RuntimeError('Tracker singleton is not exported')
        result['abis']['arm64' if directory == 'lib64' else 'arm'] = {
                'factory_sha256': digest, 'source_sha256': hashlib.sha256(built_data).hexdigest(),
                'factory_implementation_allocation_bytes': entry['implementation_allocation_bytes'],
                'factory_no_op_allocation_bytes': entry['no_op_allocation_bytes'],
                'instruction_checkpoints': checks, 'matching_virtual_interfaces': factory_tables,
                'singleton_export_present': True}
    (ROOT / 'validation/egl-image-tracker-abi.json').write_text(json.dumps(result, indent=2) + '\n')
    print('EGL tracker singleton and virtual methods match on ARM64/ARM32; 17 factory instruction checkpoints verified')


if __name__ == '__main__':
    main()
