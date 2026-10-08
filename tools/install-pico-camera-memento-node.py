"""Wire kernel-payload memento rollback into the native cam_node translation unit."""
from pathlib import Path
import hashlib
import json
SOURCE = Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro/source/phoenix-kernel-recovery')
RELATIVE = 'techpack/camera/drivers/cam_core/cam_node.c'
OLD = 'f0d0eac482909ce433dd60cc85fca4a13e5a1434999db54d579e69521058229a'

def main():
    root = Path(__file__).resolve().parent.parent
    report_path = root / 'reports/kernel-source/recovery-20261003/camera-memento-node-hooks.json'
    previous = json.loads(report_path.read_text())['sources'] if report_path.exists() else {}
    data = (SOURCE / RELATIVE).read_bytes()
    actual = hashlib.sha256(data).hexdigest()
    if actual == OLD:
        text = data.decode()
        anchor = '#include "cam_debug_util.h"'
        assert text.count(anchor) == 1
        text = text.replace(anchor, anchor + '\n#include "pico_camera_memento.h"\n#include "pico_camera_memento_node.h"')
        anchor = 'static int __cam_node_handle_dump_dev('
        assert text.count(anchor) == 1
        text = text.replace(anchor, '#include "pico_camera_memento_node.inc"\n\n' + anchor)
        data = text.encode()
    elif actual != previous.get(RELATIVE):
        raise RuntimeError('Preserve differing cam_node source')
    content = {RELATIVE: data}
    for name in ['pico_camera_memento_node.h', 'pico_camera_memento_node.inc']:
        relative = 'techpack/camera/drivers/cam_core/' + name
        desired = (root / 'kernel-recovery' / relative).read_bytes().replace(b'\r\n', b'\n')
        target = SOURCE / relative
        if target.exists() and target.read_bytes() != desired:
            if hashlib.sha256(target.read_bytes()).hexdigest() != previous.get(relative):
                raise RuntimeError('Preserve differing adapter: ' + relative)
        content[relative] = desired
    for name, data in content.items():
        if not (SOURCE / name).exists() or (SOURCE / name).read_bytes() != data:
            (SOURCE / name).write_bytes(data)
    report = {'sources': {name: hashlib.sha256(data).hexdigest() for name, data in content.items()}, 'preimage': OLD, 'scope': 'Class1 kernel-payload native stop and phased release adapter compiled into cam_node; client close hooks not wired', 'device_modified': False}
    report_path.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))

if __name__ == '__main__':
    main()
