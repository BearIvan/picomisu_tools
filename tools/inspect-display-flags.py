"""Revalidate ARM64 PICO display-flags research against pinned factory ELF.

Instruction checkpoints support the recorded data-flow observations, not a
complete reconstruction of the compositor or proof of runtime compatibility.
No factory code is executed. Run with Windows Python and pyelftools.
"""
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('producer_inspector', ROOT / 'tools/inspect-producer-fence.py')
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)

INPUTS = {
    'libgui.so': {
        'sha256': '7b52e5bc29cf5d68c1b24ce6701535dcae64131e3c83b685713ea4a0b4b6dcc5',
        'instructions': [
            (0xbbc28, '1f4800b9', 'DisplayState constructor initializes flags to zero'),
            (0xcea0c, '134800b9', 'setter stores uint32 at DisplayState+72'),
            (0xcea10, '08011c32', 'setter ORs what with 0x10'),
            (0xbbd44, '814a40b9', 'write loads trailing flags after width and height'),
            (0xbbed0, '604a00b9', 'read stores trailing flags at DisplayState+72'),
            (0xbbf34, 'c8002036', 'merge tests what bit 4'),
            (0xbbf44, '684a40b9', 'merge reads source flags'),
            (0xbbf48, '884a00b9', 'merge stores destination flags'),
        ],
    },
    'libsurfaceflinger.so': {
        'sha256': 'd23904265c575d67c8818fa5eca24936d78ae137833e1c5383a7a4b09f3bdb51',
        'instructions': [
            (0xef7d4, 'f7002036', 'transaction handling tests what bit 4'),
            (0xef7dc, '694a40b9', 'transaction reads DisplayState+72'),
            (0xef7e8, '08011e32', 'changed flags request display transaction bit 0x4'),
            (0xef7ec, '897e00b9', 'transaction stores DisplayDeviceState+124'),
            (0xed270, '28511453', 'display update extracts flag bit 20'),
            (0xed274, '68c60239', 'display update stores boolean at device+177'),
            (0xed27c, '693a16b9', 'display update stores full flags at device+5688'),
            (0xee228, '697e40b9', 'display creation reads state+124'),
            (0xee22c, '093916b9', 'display creation stores full flags at device+5688'),
            (0xee234, '09c50239', 'display creation stores bit 20 at device+177'),
            (0xe99a8, '08c54239', 'composition reads device+177 under an additional global gate'),
            (0xeabf8, 'e82f40b9', 'composition reloads saved boolean from stack'),
            (0xeac38, 'ea035eb2', 'gated branch prepares usage value 0x400000000'),
            (0xeac3c, 'ec035db2', 'gated branch prepares usage value 0x800000000'),
            (0xeac40, '6b0d6092', 'gated branch masks usage with 0xf00000000'),
            (0xeac1c, '5f8104f1', 'gated branch requires one 288-byte layer-settings entry'),
            (0xeac64, 'aded5c92', 'gated branch clears the usage nibble'),
            (0xeac68, '8d3d00f9', 'gated branch writes cleared usage back to GraphicBuffer'),
            (0xeaee8, '085d40f9', 'composition calls RenderSurface vslot 184: getMultiLayerFlag'),
            (0xeaf2c, '085140f9', 'composition calls RenderSurface vslot 160: attachBuffer'),
            (0xeaf78, '085940f9', 'composition calls RenderSurface vslot 176: setMultiLayerFlag'),
            (0x12c404, '29ed5c92', 'RenderSurface attach clears old usage nibble'),
            (0x12c408, '290160b2', 'RenderSurface attach sets usage nibble 1 before Surface attach'),
            (0x12c440, '29015fb2', 'RenderSurface attach sets usage nibble 2 after Surface attach'),
            (0x12c56c, '032540f9', 'setSingleLayer forwards to DisplaySurface vslot 72'),
            (0x12c580, '022940f9', 'setMultiLayerFlag forwards to DisplaySurface vslot 80'),
            (0x12c590, '012d40f9', 'getMultiLayerFlag forwards to DisplaySurface vslot 88'),
            (0x12bd30, '800e40f9', 'constructor loads explicit Surface from creation args+24'),
            (0x12bd38, '200c02f8', 'constructor stores explicit Surface at RenderSurface+32'),
            (0x12bd44, '7ffe02a9', 'constructor clears previous/current buffers at +40/+48'),
            (0x12bd78, '7f920079', 'constructor clears protected and flip flags at +72/+73'),
            (0x12ca84, '08240139', 'flipClientTarget only writes boolean at RenderSurface+73'),
            (0x12c5f8, '68264139', 'queueBuffer tests flip flag before ordinary composition checks'),
            (0x12c71c, '02008012', 'queueBuffer uses fence FD -1 when flip flag is set'),
            (0x12c7bc, '02008012', 'cancelBuffer error path also uses FD -1 for flip flag'),
            (0x12c4d0, '10000014', 'failed attach branches to last-attempt buffer assignment'),
            (0x12c548, '750200f9', 'last-attempt buffer is assigned after success or failure'),
            (0x81b3c, 'e0030032', 'base getMultiLayerFlag returns true'),
        ],
    },
}


def main():
    result = {'abi': 64, 'display_state_flags_offset': 72,
              'display_state_flags_default': 0,
              'display_state_changed_mask': 16, 'display_device_state_flags_offset': 124,
              'display_flags_composition_gate_bit': 20,
              'factory_code_executed': False, 'source_port_complete': False,
              'full_abi_proven': False, 'inputs': {},
              'pending': ['ARM32 object and wire layout', 'DisplayDeviceState constructor defaults',
                          'complete gated composition branch and concrete DisplaySurface implementations',
                          'additional global gate meaning', 'source/factory runtime fixtures']}
    for name, entry in INPUTS.items():
        path = p.host_path(p.PROJECT / 'analysis/stock-5.13.7-system/root/system/lib64' / name)
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != entry['sha256']:
            raise RuntimeError('Factory file changed: ' + name)
        elf = p.pointers.ElfPointers(data)
        checks = []
        for address, expected, observation in entry['instructions']:
            offset = elf.file_offset(address, 4)
            actual = data[offset:offset + 4].hex()
            if actual != expected:
                raise RuntimeError('Instruction differs: ' + name + ' ' + hex(address))
            checks.append({'address': hex(address), 'bytes': actual, 'observation': observation})
        result['inputs'][name] = {'sha256': entry['sha256'], 'instruction_checkpoints': checks}
        if name == 'libsurfaceflinger.so':
            aliases = p.aliases(elf)
            table = elf.vtable('_ZTVN7android17compositionengine4impl13RenderSurfaceE')
            result['render_surface_extensions'] = []
            for offset, method in [(152, 'flipClientTarget'), (160, 'attachBuffer'), (168, 'setSingleLayer'),
                                   (176, 'setMultiLayerFlag'), (184, 'getMultiLayerFlag')]:
                row = table[(offset + 16) // 8]
                names = {row['symbol']} if row['symbol'] else aliases.get(row['address'], set())
                matches = sorted(n for n in names if 'RenderSurface' in n and method + 'E' in n)
                if not matches:
                    raise RuntimeError('Cannot identify RenderSurface extension at ' + str(offset))
                result['render_surface_extensions'].append(
                    {'offset_from_address_point': offset, 'method': method, 'symbols': matches})
            flip_symbol = '_ZN7android17compositionengine4impl13RenderSurface16flipClientTargetEb'
            if elf.symbols[flip_symbol].st_size != 12:
                raise RuntimeError('flipClientTarget function boundary changed')
            result['render_surface_layout_observations'] = {
                'creation_args_surface_pointer_offset': 24,
                'explicit_surface_pointer_offset': 32,
                'last_attached_buffer_offset': 40, 'current_buffer_offset': 48,
                'display_surface_offset': 56, 'protected_flag_offset': 72,
                'flip_client_target_flag_offset': 73, 'page_flip_count_offset': 76,
                'flip_client_target_function_bytes': 12,
                'flip_uses_no_fence_fd_for_queue_and_cancel': True,
                'release_fence_lifecycle_fully_reconstructed': False}
            built_path = p.host_path(p.PROJECT / 'out/aosp-10/target/product/PICOA8110/system/lib64' / name)
            built_data = built_path.read_bytes()
            built = p.pointers.ElfPointers(built_data)
            built_aliases = p.aliases(built)
            built_table = built.vtable('_ZTVN7android17compositionengine4impl13RenderSurfaceE')
            for extension in result['render_surface_extensions']:
                index = (extension['offset_from_address_point'] + 16) // 8
                extension['source_slot_matches'] = False
                if index < len(built_table):
                    row = built_table[index]
                    names = {row['symbol']} if row['symbol'] else built_aliases.get(row['address'], set())
                    extension['source_slot_matches'] = bool(set(extension['symbols']) & names)
            tables = ['_ZTVN7android17compositionengine4impl13RenderSurfaceE',
                      '_ZTVN7android17compositionengine13RenderSurfaceE',
                      '_ZTVN7android17compositionengine14DisplaySurfaceE']
            result['source_compositor_comparison'] = {
                'sha256': hashlib.sha256(built_data).hexdigest(),
                'tables': {symbol: {'factory_bytes': elf.symbols[symbol].st_size,
                                    'source_bytes': built.symbols[symbol].st_size}
                           for symbol in tables},
                'full_method_order_or_object_layout_verified': False}
    (ROOT / 'validation/display-flags-research.json').write_text(json.dumps(result, indent=2) + '\n')
    count = sum(len(entry['instructions']) for entry in INPUTS.values())
    print(f'Verified {count} pinned ARM64 instruction checkpoints; compositor port remains incomplete')


if __name__ == '__main__':
    main()
