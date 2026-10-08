"""Verify the recorded factory ProducerListener dispatch table in pinned libgui.

Addresses come from the previously authenticated ARM64 disassembly. This checks
the exact binary identity and table targets, not a generic opcode recognizer.
"""
import hashlib
import json
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = '7b52e5bc29cf5d68c1b24ce6701535dcae64131e3c83b685713ea4a0b4b6dcc5'


def main():
    manifest = json.loads((ROOT / 'reports/vr-integration/factory-system.json').read_text())
    path = Path(manifest['tree']) / 'system/lib64/libgui.so'
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != EXPECTED:
        raise RuntimeError('Unexpected factory libgui')
    phoff = struct.unpack_from('<Q', data, 32)[0]
    entry_size, count = struct.unpack_from('<HH', data, 54)
    table = None
    for index in range(count):
        kind, _, offset, address, _, file_bytes, _, _ = struct.unpack_from('<IIQQQQQQ', data, phoff + index * entry_size)
        if kind == 1 and address <= 0x55828 and 0x5582c <= address + file_bytes:
            table = data[offset + 0x55828 - address:offset + 0x5582c - address]
    if table is None:
        raise RuntimeError('Factory dispatch table not mapped')
    targets = {index + 1: 0x89ae4 + value * 4 for index, value in enumerate(table)}
    expected_targets = {1: 0x89ae4, 2: 0x89c40, 3: 0x89b08, 4: 0x89b58}
    if targets != expected_targets:
        raise RuntimeError('Factory dispatch targets differ: ' + str(targets))
    report = {'factory_libgui_sha256': EXPECTED, 'abi': 64,
              'on_buffer_released_transaction': 1, 'needs_release_notify_transaction': 2,
              'on_buffers_discarded_transaction': 3, 'release_with_fence_transaction': 4,
              'discard_payload_from_verified_disassembly': 'Parcel::readInt32Vector',
              'discard_virtual_call_offset_bytes': 32,
              'factory_dispatch_table_checked': True}
    (ROOT / 'validation/producer-discard-protocol.json').write_text(json.dumps(report, indent=2) + '\n')
    print('Factory discarded-buffer transaction 3 verified')


if __name__ == '__main__':
    main()
