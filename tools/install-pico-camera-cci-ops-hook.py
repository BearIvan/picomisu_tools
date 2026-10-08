"""Restore the factory CCI late fops assignment + hub notification order."""
from pathlib import Path
import hashlib
import json
import struct

BASE = Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro')
NAME = 'techpack/camera/drivers/cam_sensor_module/cam_cci/cam_cci_dev.c'


def main():
    root = Path(__file__).resolve().parent.parent
    path = root / 'reports/kernel-source/recovery-20261003/camera-cci-ops-hook.json'
    target = BASE / 'source/phoenix-kernel-recovery' / NAME
    data = target.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    old = '2fb9441d0833be3453e6244655dee64f2396868e7589ed2d1278a9376165491f'
    prior = json.loads(path.read_text()) if path.exists() else None
    if not prior or digest != prior['sources'][NAME]:
        if digest != old:
            raise RuntimeError('Preserve differing CCI source')
        text = data.decode()
        first_include = text.index('#include ')
        text = text[:first_include] + '#include "../../cam_core/pico_camera_hub.h"\n' + text[first_include:]
        anchor = '\t\tsd->devnode->fops = &cci_v4l2_subdev_fops;'
        if text.count(anchor) != 1:
            raise RuntimeError('Unexpected CCI fops assignment')
        text = text.replace(anchor, anchor + '\n\t\t/* Factory late init ignores missing/non-multi hub notification. */\n\t\tcam_device_hub_handle_v4l2_subdevice_ops_changed(sd,\n\t\t\t&cci_v4l2_subdev_fops);')
        data = text.encode()
        target.write_bytes(data)
    image = (BASE / 'stock/5.13.7-SEKO/boot-unpacked/kernel').read_bytes()
    table = struct.unpack_from('<6I', image, 0x20d3d48)
    if table != (0x10000, 1, 0x10003, 1, 0x10100, 1):
        raise RuntimeError('Unexpected factory multi-client table')
    report = {'sources': {NAME: hashlib.sha256(data).hexdigest()}, 'preimage': old,
              'factory_image_sha256': hashlib.sha256(image).hexdigest(), 'factory_table_offset': '0x20d3d48',
              'factory_multi_client_entries': [hex(table[i]) for i in (0, 2, 4)],
              'scope': 'Native fops write before notification, multi-only saved fops update; CCI flags/entity remain as original; subdevice registration still pending', 'device_modified': False}
    path.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
