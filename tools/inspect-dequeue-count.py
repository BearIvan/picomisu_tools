"""Check PICO's single-layer dequeue quota instructions against pinned factory ELF."""
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('producer_inspector', ROOT / 'tools/inspect-producer-fence.py')
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)

CHECKS = {
    'arm64': {
        'directory': 'lib64',
        'sha256': '7b52e5bc29cf5d68c1b24ce6701535dcae64131e3c83b685713ea4a0b4b6dcc5',
        'sf_field_offset': 68, 'mode_field_offset': 313, 'private_consumer_field_offset': 5785,
        'instructions': [
            (0x73bd8, '9f0a0031', 'test request -2'),
            (0x73be0, '68124139', 'load consumer-is-SurfaceFlinger flag'),
            (0x73bf0, '68e60439', 'arm single-layer allowance'),
            (0x73c54, '68e64439', 'load single-layer allowance'),
            (0x73c58, '2ad38252', 'private consumer flag offset'),
            (0x73c5c, '2a696a38', 'load private consumer marker'),
            (0x73c60, '0801140b', 'add single-layer allowance to request'),
            (0x73c64, '0b090011', 'add private consumer allowance of two'),
            (0x73c68, '7f050071', 'compare extended count with one'),
            (0x73c6c, '6bc59f1a', 'clamp private consumer count to at least one'),
            (0x73c7c, '14018b1a', 'select ordinary or private consumer count'),
        ],
    },
    'arm': {
        'directory': 'lib',
        'sha256': '09e91a368003bf8112abaf4adc98f1a78df9ac88ada3f9c81f1eb12f51e68db0',
        'sf_field_offset': 36, 'mode_field_offset': 125, 'private_consumer_field_offset': 3929,
        'instructions': [
            (0x50d74, 'a81c', 'test request -2'),
            (0x50d78, '99f82400', 'load consumer-is-SurfaceFlinger flag'),
            (0x50d80, '89f87d00', 'arm single-layer allowance'),
            (0x50d9a, '99f87d60', 'load single-layer allowance'),
            (0x50d9e, '90f8597f', 'load private consumer marker'),
            (0x50db4, '7119', 'add single-layer allowance to request'),
            (0x50dba, '01f10208', 'add private consumer allowance of two'),
            (0x50dbe, 'b8f1010f', 'compare extended count with one'),
            (0x50dc4, '4ff00108', 'clamp private consumer count to at least one'),
            (0x50dce, '8846', 'select ordinary count when no private marker is present'),
        ],
    },
}


def main():
    result = {'factory_code_executed': False, 'full_private_object_abi_proven': False,
              'special_command': -2, 'single_layer_extra_slots': 1,
              'private_consumer_extra_slots': 2, 'private_consumer_minimum_count': 1,
              'special_command_precedes_abandoned_queue_check': True, 'inputs': {}}
    for abi, entry in CHECKS.items():
        source = p.host_path(p.PROJECT / 'analysis/stock-5.13.7-system/root/system' /
                             entry['directory'] / 'libgui.so')
        data = source.read_bytes()
        if hashlib.sha256(data).hexdigest() != entry['sha256']:
            raise RuntimeError('Factory ELF differs: ' + abi)
        elf = p.pointers.ElfPointers(data)
        rows = []
        for address, expected, observation in entry['instructions']:
            offset = elf.file_offset(address, len(expected) // 2)
            if data[offset:offset + len(expected) // 2].hex() != expected:
                raise RuntimeError('Factory instruction differs: ' + abi + ' ' + hex(address))
            rows.append({'address': hex(address), 'bytes': expected, 'observation': observation})
        result['inputs'][abi] = {k: entry[k] for k in ('sha256', 'sf_field_offset',
                                'mode_field_offset', 'private_consumer_field_offset')}
        result['inputs'][abi]['instruction_checkpoints'] = rows
    factory = p.host_path(p.PROJECT / 'analysis/stock-5.13.7-system/root/system/lib64/libsurfaceflinger.so')
    data = factory.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != 'd23904265c575d67c8818fa5eca24936d78ae137833e1c5383a7a4b09f3bdb51':
        raise RuntimeError('Factory compositor differs')
    elf = p.pointers.ElfPointers(data)
    offset = elf.file_offset(0x4c156, 1)
    property_name = data[offset:data.index(b'\0', offset)].decode()
    if property_name != 'persist.sys.skip_single_layer':
        raise RuntimeError('Factory composition property differs')
    result['factory_composition_gate'] = {
        'sha256': digest, 'property': property_name, 'property_string_address': '0x4c156',
        'global_boolean_address': '0x1981d8', 'property_default': True,
        'property_get_bool_call': '0x109be0', 'global_store': '0x109bf8',
        'composition_global_read': '0xe9984', 'display_flag_bit': 20,
        'buffer_queue_layer_command_call': '0x86c5c',
        'source_composition_caller_qualified': False,
    }
    (ROOT / 'validation/dequeue-count-abi.json').write_text(json.dumps(result, indent=2) + '\n')
    print('Verified 21 pinned ARM64/ARM32 quota checkpoints and factory composition property')


if __name__ == '__main__':
    main()
