"""Verify authenticated PICO frame-history and caller-query instruction evidence.

The runtime probe separately checks actual constructor/frame bytes and query
payloads. Neither check proves full libgui/Binder ABI or remote Binder behavior.
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
        'libgui.so': ('7b52e5bc29cf5d68c1b24ce6701535dcae64131e3c83b685713ea4a0b4b6dcc5', [
            (0xd8058, '08de8952', 'constructor prepares mutex offset 20208'),
            (0xd8064, '00b0933d', 'constructor stores index/count at 20160/20168'),
            (0xd8070, '08e38952', 'constructor prepares caller-ID offset 20248'),
            (0xd8074, '7f6a28b8', 'constructor clears caller ID'),
            (0xd80c4, 'e0030032', 'sample the monotonic clock, ID 1'),
            (0xd80cc, '9f0e0071', 'four valid stage indices, 0 through 3'),
            (0xd80f0, '606a27f9', 'stage zero stored at 20176'),
            (0xd80f8, '606e27f9', 'stage one stored at 20184'),
            (0xd8100, '607227f9', 'stage two stored at 20192'),
            (0xd8108, '607627f9', 'stage three stored at 20200'),
            (0xd8160, 'eb0f1d32', 'ring capacity 120'),
            (0xd8180, '09158052', 'frame stride 168 bytes'),
            (0xd81a0, 'e21b0032', 'copy at most 127 name bytes'),
            (0xd81b0, '08541029', 'caller ID/frame number at 128/132'),
            (0xd81fc, '1f210071', 'compare count with eight for lookup'),
            (0xd8200, 'ed031d32', 'lookup searches at most eight frames'),
        ]),
        'libbinder.so': ('9e5bdf585d73baddf17bbc646b4daea0e2b15d4fb6d8dc244d08412dd1be86a9', [
            (0x6a864, 'e1438c52', 'caller query low request bits 0x621f'),
            (0x6a868, '8100b072', 'caller query high request bits 0x8004'),
            (0x6a874, 'ff0700b9', 'initialize int32 reply to zero'),
            (0x6a884, '6000f837', 'negative ioctl result enters error branch'),
            (0x6a890, '00008012', 'ioctl error returns minus one'),
        ]),
    },
    'lib': {
        'libgui.so': ('09e91a368003bf8112abaf4adc98f1a78df9ac88ada3f9c81f1eb12f51e68db0', [
            (0x97566, '0120', 'sample the monotonic clock, ID 1'),
            (0x9756c, '032d', 'four valid stage indices, 0 through 3'),
            (0x975cc, '7822', 'ring capacity 120'),
            (0x975f4, 'a820', 'frame stride 168 bytes'),
            (0x975fa, '7f22', 'copy at most 127 name bytes'),
            (0x976a8, '082e', 'compare count with eight for lookup'),
            (0x976ae, '0825', 'lookup searches at most eight frames'),
        ]),
        'libbinder.so': ('0d0459e40cde072ade682b87ff45da9333a30f2efdf908b92255ecd8924e6823', [
            (0x47b48, '0021', 'initialize int32 reply to zero'),
            (0x47b5c, '0028', 'test ioctl result for failure'),
        ]),
    },
}

EXPORTS = {
    'libgui.so': ['_ZN7android13SurfaceClientC1Ev', '_ZN7android13SurfaceClientD1Ev',
                  '_ZN7android13SurfaceClient12setFrameItemEi',
                  '_ZN7android13SurfaceClient8addFrameENS_7String8Ei',
                  '_ZN7android13SurfaceClient16findCurrentFrameEi'],
    'libbinder.so': ['_ZN7android14IPCThreadState13getCallingTidEv'],
}


def main():
    result = {'scope': 'SurfaceClient frame history and getCallingTid ioctl',
              'frame_bytes': 168, 'history_capacity': 120, 'lookup_window': 8,
              'name_copy_limit': 127, 'frame_offsets': {'name': 0, 'calling_tid': 128,
                                                       'number': 132, 'timestamps': 136},
              'caller_query': {'request': '0x8004621f', 'payload': 'int32',
                               'initial_value': 0, 'error_value': -1},
              'full_graphics_or_binder_abi_proven': False,
              'real_remote_caller_query_qualified': False, 'abis': {}}
    for directory, libraries in FACTORY.items():
        abi = 'arm64' if directory == 'lib64' else 'arm'
        entry = {'observed_class_bytes': 20256 if abi == 'arm64' else 20216,
                 'observed_class_offsets': {'frames': 0, 'index': 20160, 'count': 20168,
                     'timestamps': 20176, 'mutex': 20208, 'calling_tid': 20248 if abi == 'arm64' else 20212},
                 'libraries': {}}
        for library, (expected_hash, checkpoints) in libraries.items():
            path = p.host_path(p.PROJECT / 'analysis/stock-5.13.7-system/root/system' / directory / library)
            data = path.read_bytes()
            if hashlib.sha256(data).hexdigest() != expected_hash:
                raise RuntimeError('Pinned factory library changed: ' + library + '/' + directory)
            elf = p.pointers.ElfPointers(data)
            checked = []
            for address, expected, observation in checkpoints:
                size = len(bytes.fromhex(expected))
                offset = elf.file_offset(address, size)
                if data[offset:offset + size].hex() != expected:
                    raise RuntimeError('SurfaceClient instruction differs: ' + hex(address))
                checked.append({'address': hex(address), 'bytes': expected, 'observation': observation})
            built_data = p.host_path(p.PROJECT / 'out/aosp-10/target/product/PICOA8110/system' / directory / library).read_bytes()
            built = p.pointers.ElfPointers(built_data)
            for symbol in EXPORTS[library]:
                if symbol not in elf.symbols or symbol not in built.symbols:
                    raise RuntimeError('Required export absent: ' + symbol)
            entry['libraries'][library] = {'factory_sha256': expected_hash,
                    'source_sha256': hashlib.sha256(built_data).hexdigest(),
                    'matching_exports': EXPORTS[library], 'instruction_checkpoints': checked}
        result['abis'][abi] = entry
    (ROOT / 'validation/surface-client-abi.json').write_text(json.dumps(result, indent=2) + '\n')
    print('SurfaceClient and caller-ID exports present on both ABIs; 30 factory instruction checkpoints verified')


if __name__ == '__main__':
    main()
