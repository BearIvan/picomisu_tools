"""Restore the factory sensor-probe -> virtual-mono creation call.

The arm64 factory call at Image+0xc1e224 uses soc_info.index, before CRM's
late subdevice-node creation. Preserve its registration guard unchanged.
"""
from pathlib import Path
import hashlib
import json
import subprocess

BASE = Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro')
SOURCE = BASE / 'source/phoenix-kernel-recovery'
RELATIVE = 'techpack/camera/drivers/cam_sensor_module/cam_sensor/cam_sensor_dev.c'
HOOK = '''
	/* Factory 5.13.7 Image+0xc1e224 creates a virtual peer per sensor slot.
	 * This runs before CRM's late_initcall creates the subdevice nodes.
	 */
	rc = cam_quick_register_virtual_device(soc_info->index);
	if (rc) {
		kfree(s_ctrl->i2c_data.per_frame);
		s_ctrl->i2c_data.per_frame = NULL;
		goto unreg_subdev;
	}

'''


def main():
    path = SOURCE / RELATIVE
    original = subprocess.check_output(['git', '-C', str(SOURCE), 'show', 'HEAD:' + RELATIVE], text=True)
    text = path.read_text()
    expected = original.replace('#include "cam_sensor_core.h"',
                                '#include "cam_sensor_core.h"\n#include "pico_virtual_mono.h"', 1)
    marker = '\tINIT_LIST_HEAD(&(s_ctrl->i2c_data.init_settings.list_head));'
    # This marker appears in multiple probes; select only the platform path.
    start = expected.index('static int32_t cam_sensor_driver_platform_probe(')
    offset = expected.index(marker, start)
    expected = expected[:offset] + HOOK + expected[offset:]
    if text not in (original, expected):
        raise RuntimeError('Preserve existing sensor edits: ' + RELATIVE)
    path.write_text(expected)
    report = {'source': RELATIVE, 'source_sha256': hashlib.sha256(expected.encode()).hexdigest(),
              'factory_call_offset': '0xc1e224', 'factory_caller': 'cam_sensor_driver_platform_probe',
              'argument': 'soc_info.index',
              'difference': 'Free per_frame allocation if platform-device creation fails; factory leaks it in this branch',
              'crm_registration_guard_changed': False, 'device_modified': False, 'runtime_verified': False}
    root = Path(__file__).resolve().parent.parent
    (root / 'reports/kernel-source/recovery-20261003/sensor-mono-hook.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
