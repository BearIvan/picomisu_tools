"""Compare PICO VirtualDisplaySurface ARM64 slots and recovered object layout.

Reads ELF/DWARF without executing either library. The ARM32 source shape is
reported separately; it is not a comparison against the ARM32 factory class.
"""
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('producer_inspector', ROOT / 'tools/inspect-producer-fence.py')
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)

FACTORY_SHA = 'd23904265c575d67c8818fa5eca24936d78ae137833e1c5383a7a4b09f3bdb51'
GUI_SHA = '7b52e5bc29cf5d68c1b24ce6701535dcae64131e3c83b685713ea4a0b4b6dcc5'
FACTORY_BASE = 0x184fa8
TABLE_BYTES = 1040
FIELDS = {
    'mOutputUsage': 1800, 'mForceHwcCopy': 3488, 'mSecure': 3489, 'mSinkUsage': 3492,
    'mSingleLayerFrames': 3496, 'mSingleLayerMutex': 3520,
    'mMultiLayer': 3560, 'mReleaseListener': 3568, 'mUseTwoSinkBuffers': 3576,
}
# These private factory functions were identified by the instruction research.
PRIVATE_METHODS = {
    96: (0xb07f8, '14setSingleLayerE'),
    104: (0xb0c6c, '17setMultiLayerFlagE'),
    112: (0xb0c78, '17getMultiLayerFlagE'),
    120: (0xb0528, '25onBufferReleasedWithFenceE'),
    128: (0xb01c0, '24notifySingleLayerBuffersE'),
    320: (0xb01a0, '14setOutputUsageE'),
}
CHECKS = [
    (0xedc2c, '00c28152', 'allocation size 3600'),
    (0xade48, '9b863639', 'secure flag at 3489'),
    (0xade4c, '9fa60db9', 'sink usage at 3492'),
    (0xade6c, '98e23739', 'two-buffer option at 3576'),
    (0xadf94, 'e81740b9', 'read legacy sink query int32'),
    (0xadfa4, '08011532', 'include HW_COMPOSER usage'),
    (0xadfa8, '88a60db9', 'save sink usage'),
    (0xae068, 'e1031f32', 'two sink buffers: count 2'),
    (0xae070, '081940f9', 'setMaxDequeuedBufferCount producer slot 48'),
    (0xb01a0, '08a48db9', 'sign extend legacy sink usage'),
    (0xb01a4, '09847639', 'read secure flag'),
    (0xb01b0, '68008036', 'test HW_VIDEO_ENCODER bit 16'),
    (0xb01b4, '080172b2', 'add PROTECTED bit 14'),
]


def load(relative):
    data = p.host_path(p.PROJECT / relative).read_bytes()
    return p.pointers.ElfPointers(data), hashlib.sha256(data).hexdigest()


def source_shape(elf):
    table = next(s for s in elf.elf.get_section_by_name('.symtab').iter_symbols()
                 if s.name == '_ZTVN7android21VirtualDisplaySurfaceE')
    shape = {'vtable_bytes': table.entry.st_size}
    dwarf = elf.elf.get_dwarf_info()
    for cu in dwarf.iter_CUs():
        name = cu.get_top_DIE().attributes.get('DW_AT_name')
        if not name or not name.value.endswith(b'DisplayHardware/VirtualDisplaySurface.cpp'):
            continue
        for die in cu.iter_DIEs():
            name = die.attributes.get('DW_AT_name')
            if not name or name.value not in (b'VirtualDisplaySurface', b'SingleLayerFrame'):
                continue
            if 'DW_AT_byte_size' not in die.attributes:
                continue
            members = {child.attributes['DW_AT_name'].value.decode():
                       child.attributes['DW_AT_data_member_location'].value
                       for child in die.iter_children() if child.tag == 'DW_TAG_member'}
            label = 'display' if name.value == b'VirtualDisplaySurface' else 'record'
            shape[label] = {'bytes': die.attributes['DW_AT_byte_size'].value,
                            'fields': members}
        break
    if 'display' not in shape or 'record' not in shape:
        raise RuntimeError('Missing source layout DWARF')
    return table.entry.st_value, shape


def names(elf, aliases, address):
    row = elf.pointer(address)
    return row, aliases.get(row['address'], set()) | ({row['symbol']} if row['symbol'] else set())


def main():
    factory, digest = load('analysis/stock-5.13.7-system/root/system/lib64/libsurfaceflinger.so')
    if digest != FACTORY_SHA:
        raise RuntimeError('Wrong pinned factory SurfaceFlinger')
    for address, expected, _ in CHECKS:
        start = factory.file_offset(address, 4)
        if factory.data[start:start + 4].hex() != expected:
            raise RuntimeError('Instruction changed at ' + hex(address))
    gui, gui_digest = load('analysis/stock-5.13.7-system/root/system/lib64/libgui.so')
    if gui_digest != GUI_SHA:
        raise RuntimeError('Wrong pinned factory libgui')
    for address, expected in [(0x70154, 'e0031f2ac0035fd6'), (0x6c328, 'c0035fd6')]:
        start = gui.file_offset(address, len(expected) // 2)
        if gui.data[start:start + len(expected) // 2].hex() != expected:
            raise RuntimeError('Factory producer base default changed')
    source, source_digest = load('out/aosp-10/target/product/PICOA8110/symbols/system/lib64/libsurfaceflinger.so')
    base, shape = source_shape(source)
    if shape['vtable_bytes'] != TABLE_BYTES or shape['display']['bytes'] != 3600:
        raise RuntimeError('VirtualDisplaySurface extent differs')
    for name, offset in FIELDS.items():
        if shape['display']['fields'][name] != offset:
            raise RuntimeError('Source field differs: ' + name)
    if shape['record'] != {'bytes': 32, 'fields': {'slot': 4, 'buffer': 8, 'layer': 16,
                                                'outstanding': 24}}:
        raise RuntimeError('Source registry record differs')
    factory_aliases, source_aliases = p.aliases(factory), p.aliases(source)
    rows, unmatched = [], []
    for offset in range(0, TABLE_BYTES, 8):
        f, fn = names(factory, factory_aliases, FACTORY_BASE + offset)
        s, sn = names(source, source_aliases, base + offset)
        if offset in PRIVATE_METHODS:
            target, fragment = PRIVATE_METHODS[offset]
            matched = f['address'] == target and any('VirtualDisplaySurface' in n and fragment in n for n in sn)
            kind = 'private function identity from instruction research'
        elif fn or sn:
            matched = bool(fn & sn)
            kind = 'function symbol intersection'
        else:
            matched = f == s
            kind = 'vtable metadata'
        rows.append({'offset': offset, 'kind': kind, 'matched': matched})
        if not matched:
            unmatched.append({'offset': offset, 'factory': sorted(fn), 'source': sorted(sn),
                              'factory_address': f['address'], 'source_address': s['address']})
    arm, arm_digest = load('out/aosp-10/target/product/PICOA8110/symbols/system/lib/libsurfaceflinger.so')
    _, arm_shape = source_shape(arm)
    result = {
        'factory_sha256': digest, 'factory_gui_sha256': gui_digest,
        'source_sha256': source_digest, 'arm32_source_sha256': arm_digest,
        'arm64_source_shape': shape, 'arm32_source_shape': arm_shape,
        'arm64_slots_examined': len(rows), 'arm64_all_slots_matched': not unmatched,
        'unmatched_slots': unmatched, 'slot_checks': rows,
        'recovered_fields_match': True, 'source_record_matches_factory_observations': True,
        'arm32_factory_comparison_complete': False,
        'scope': 'vtable identities/metadata and recovered member offsets; function behavior, all member types and full graphics compatibility are separate checks',
        'concrete_bufferqueue_extensions_ported': False,
        'instructions': [{'address': hex(a), 'bytes': b, 'observation': c} for a, b, c in CHECKS],
    }
    (ROOT / 'validation/virtual-display-abi.json').write_text(json.dumps(result, indent=2) + '\n')
    print(f'ARM64: {len(rows) - len(unmatched)}/{len(rows)} vtable entries match; recovered member offsets match')
    if unmatched:
        raise RuntimeError('Unmatched VirtualDisplaySurface entries: ' + str(unmatched))


if __name__ == '__main__':
    main()
