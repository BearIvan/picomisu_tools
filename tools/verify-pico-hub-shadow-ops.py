"""Read the factory shadow subdevice core ops from relocated analysis data."""
from pathlib import Path
import json
import struct

BASE = Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro')
VA = 0xffffff8008080000


def main():
    elf = BASE / 'analysis/kernel-recovery/camera-relay/factory-5.13.7-symbolized.elf'
    data = elf.read_bytes()
    offset = struct.unpack_from('<Q', data, 40)[0]
    step, count, names_index = struct.unpack_from('<HHH', data, 58)
    sections = [struct.unpack_from('<IIQQQQIIQQ', data, offset + n * step) for n in range(count)]
    def contents(section):
        return data[section[4]:section[4] + section[5]]
    names = contents(sections[names_index])
    image = contents(next(section for section in sections if
                          names[section[0]:names.index(b'\0', section[0])] == b'.image'))
    symbols = [(int(addr, 16), kind, name) for addr, kind, name in
               (line.split() for line in (BASE / 'analysis/diff-5.13.7-vs-5.13.8/kernel/ks5.13.7.txt').read_text().splitlines())]
    labels = {addr + VA: name for addr, _, name in symbols}
    # Address comes from factory registration's v4l2_subdev_init x1.
    ops = 0x15d6e40
    core = struct.unpack_from('<Q', image, ops)[0]
    if not VA <= core < VA + len(image) - 112:
        raise RuntimeError('Invalid relocated shadow core ops pointer')
    pointers = struct.unpack_from('<' + 'Q' * 14, image, core - VA)
    table = [{'offset': n * 8, 'target': labels.get(pointer, hex(pointer)) if pointer else None}
             for n, pointer in enumerate(pointers)]
    report = {'factory_ops_offset': hex(ops), 'factory_core_offset': hex(core - VA), 'slots': table,
              'scope': 'all 14 core-ops pointers for this kernel, including ioctl/compat/event callbacks; no runtime proof'}
    expected = {48: 'v4l2_subdevice_ioctl', 56: 'v4l2_subdevice_compat_ioctl'}
    for slot in table:
        if slot['target'] != expected.get(slot['offset']):
            raise RuntimeError('Additional/unexpected factory core callback: ' + str(slot))
    root = Path(__file__).resolve().parent.parent
    (root / 'reports/kernel-source/recovery-20261003/camera-hub-shadow-ops.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
