"""Wire the native CSR/sync producers to the IRQ-safe client route index."""
from pathlib import Path
import hashlib
import json

BASE = Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro')
SOURCE = BASE / 'source/phoenix-kernel-recovery'
CRM = 'techpack/camera/drivers/cam_req_mgr/cam_req_mgr_dev.c'
SYNC = 'techpack/camera/drivers/cam_sync/cam_sync_util.c'


def replace(text, old, new):
    if text.count(old) != 1:
        raise RuntimeError('Unexpected anchor: ' + old)
    return text.replace(old, new)


def main():
    root = Path(__file__).resolve().parent.parent
    path = root / 'reports/kernel-source/recovery-20261003/camera-hub-irq-hooks.json'
    preimages = {CRM: '52bb21c75b59011b35ee6cc37ca650a8e7618328f8cfe6f0c87d3e66a1e9c25b', SYNC: '41b8dce05621331f3a640ff524c6fe845734ba656fd972df39b69bb66da16a40'}
    previous = json.loads(path.read_text())['sources'] if path.exists() else {}
    content = {}
    for name, digest in preimages.items():
        data = (SOURCE / name).read_bytes()
        actual = hashlib.sha256(data).hexdigest()
        if actual == previous.get(name):
            if name == SYNC:
                include = '#include "../cam_core/pico_camera_hub_irq.h"\n'
                text = data.decode()
                if text.startswith(include):
                    text = text[len(include):]
                    position = text.index('#include ')
                    text = text[:position] + include + text[position:]
                    data = text.encode()
            content[name] = data
            continue
        if actual != digest:
            raise RuntimeError('Preserve differing native source: ' + name)
        text = data.decode()
        if name == CRM:
            text = replace(text, '#include "../cam_core/pico_camera_hub_registration.h"', '#include "../cam_core/pico_camera_hub_registration.h"\n#include "../cam_core/pico_camera_hub_irq.h"')
            text = replace(text, '\tv4l2_event_queue(g_dev.video, &event);', '\tpico_hub_route_irq_event(0x10000, &event);')
            text = replace(text, '\tstruct v4l2_event event;', '\tstruct v4l2_event event = {0};')
        else:
            # Add include before the first native function, without guessing
            # platform-global device lifetime from IRQ context.
            position = text.index('#include ')
            text = text[:position] + '#include "../cam_core/pico_camera_hub_irq.h"\n' + text[position:]
            text = replace(text, '\tstruct v4l2_event event;', '\tstruct v4l2_event event = {0};')
            text = replace(text, '\tmemcpy(payload_data, payload, len);', '\tif (len < 0 || len > sizeof(event.u.data) - sizeof(*ev_header) ||\n\t\t(len && !payload))\n\t\treturn;\n\tif (len)\n\t\tmemcpy(payload_data, payload, len);')
            text = replace(text, '\tv4l2_event_queue(sync_dev->vdev, &event);', '\tpico_hub_route_irq_event(0x10100, &event);')
        content[name] = text.encode()
    for name, data in content.items():
        if (SOURCE / name).read_bytes() != data:
            (SOURCE / name).write_bytes(data)
    report = {'sources': {name: hashlib.sha256(data).hexdigest() for name, data in content.items()},
              'preimages': preimages, 'scope': 'Single native CRM/sync entity providers; IRQ-safe direct FH delivery; zeroed event packets and bounded sync payload', 'device_modified': False}
    path.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
