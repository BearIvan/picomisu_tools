"""Resolve factory callback tables from the relocated analysis ELF.

This independently checks whether the no-DMA callbacks belong to virtual
mono's real VB2 operations, instead of inferring them from function names.
"""
from pathlib import Path
import json
import struct

BASE = Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro')
VA = 0xffffff8008080000


def main():
    elf = BASE / 'analysis/kernel-recovery/camera-full/factory-5.13.7-symbolized.elf'
    blob = elf.read_bytes()
    offset = struct.unpack_from('<Q', blob, 40)[0]
    step, count, names_index = struct.unpack_from('<HHH', blob, 58)
    sections = [struct.unpack_from('<IIQQQQIIQQ', blob, offset + n * step) for n in range(count)]
    def contents(section):
        return blob[section[4]:section[4] + section[5]]
    def string(data, index):
        return data[index:data.index(b'\0', index)].decode()
    names = contents(sections[names_index])
    image = next(section for section in sections if string(names, section[0]) == '.image')
    data = contents(image)
    kallsyms = BASE / 'analysis/diff-5.13.7-vs-5.13.8/kernel/ks5.13.7.txt'
    symbols = [(int(addr, 16), kind, name) for addr, kind, name in
               (line.split() for line in kallsyms.read_text().splitlines())]
    addresses = {name: addr for addr, _, name in symbols}
    labels = {addr + VA: name for addr, _, name in symbols}
    tables = {'mono_subdev_vb2_q_ops': 10, 'mono_subdev_vb2_mem_ops': 15,
              'virtual_mono_subdev_intern_ops': 4}
    report = {}
    for name, count in tables.items():
        pointers = struct.unpack_from('<' + 'Q' * count, data, addresses[name])
        report[name] = [{'offset': n * 8, 'target': labels.get(pointer, hex(pointer)) if pointer else None}
                        for n, pointer in enumerate(pointers)]
    qops = report['mono_subdev_vb2_q_ops']
    expected = {0: 'mono_subdev_queue_setup', 8: 'vb2_ops_wait_prepare',
                16: 'vb2_ops_wait_finish', 24: 'mono_subdev_buf_init',
                56: 'mono_subdev_start_streaming', 64: 'mono_subdev_stop_streaming',
                72: 'mono_subdev_buf_queue'}
    for slot in qops:
        if slot['target'] != expected.get(slot['offset']):
            raise RuntimeError('Factory queue ops differ: ' + str(slot))
    expected_mem = {24: 'mono_subdev_vb2_dc_get_userptr', 32: 'mono_subdev_vb2_put_userptr'}
    expected_internal = {16: 'virtual_mono_subdev_open', 24: 'virtual_mono_subdev_close'}
    for name, expected_slots in [('mono_subdev_vb2_mem_ops', expected_mem),
                                 ('virtual_mono_subdev_intern_ops', expected_internal)]:
        for slot in report[name]:
            if slot['target'] != expected_slots.get(slot['offset']):
                raise RuntimeError('Factory callback differs: ' + str(slot))
    root = Path(__file__).resolve().parent.parent
    (root / 'reports/kernel-source/recovery-20261003/virtual-mono-factory-tables.json').write_text(
        json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
