"""Guarded native CRM/sync packet hooks, preserving non-hub ioctl behavior."""
from pathlib import Path
import hashlib
import json
import subprocess

BASE = Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro')
SOURCE = BASE / 'source/phoenix-kernel-recovery'
CRM = 'techpack/camera/drivers/cam_req_mgr/cam_req_mgr_dev.c'
SYNC = 'techpack/camera/drivers/cam_sync/cam_sync.c'


def replace(text, old, new):
    if text.count(old) != 1:
        raise RuntimeError('Unexpected anchor count: ' + old)
    return text.replace(old, new)


def main():
    if subprocess.check_output(['git', '-C', str(SOURCE), 'rev-parse', 'HEAD'], text=True).strip() != 'ceafd3afc0208c03e0eb7a1a60939d147f92d72a':
        raise RuntimeError('Unexpected source base')
    root = Path(__file__).resolve().parent.parent
    report_path = root / 'reports/kernel-source/recovery-20261003/camera-hub-dispatch-hooks.json'
    old = {CRM: '6dcec584a8d418600379c5697eef8cb8b822cc57895220bf5a6f137332147c8d', SYNC: 'ee1a08473d221eade682e0643060c3de50194cde7410ae506e5ccd5764da4324'}
    previous = json.loads(report_path.read_text())['sources'] if report_path.exists() else {}
    content = {}
    for name, digest in old.items():
        data = (SOURCE / name).read_bytes()
        actual = hashlib.sha256(data).hexdigest()
        if actual == previous.get(name):
            content[name] = data
            continue
        if actual != digest:
            raise RuntimeError('Preserve differing source: ' + name)
        text = data.decode()
        text = replace(text, '#include "cam_common_util.h"', '#include "cam_common_util.h"\n#include "../cam_core/pico_camera_hub_dispatch.h"')
        if name == CRM:
            operations = [
                ('CAM_REQ_MGR_CREATE_SESSION', 'cam_req_mgr_create_session(&ses_info)', 'ses_info', False),
                ('CAM_REQ_MGR_DESTROY_SESSION', 'cam_req_mgr_destroy_session(&ses_info, false)', 'ses_info', True),
                ('CAM_REQ_MGR_LINK', 'cam_req_mgr_link(&ver_info)', 'ver_info', False),
                ('CAM_REQ_MGR_LINK_V2', 'cam_req_mgr_link_v2(&ver_info)', 'ver_info', False),
                ('CAM_REQ_MGR_UNLINK', 'cam_req_mgr_unlink(&unlink_info)', 'unlink_info', True),
                ('CAM_REQ_MGR_ALLOC_BUF', 'cam_mem_mgr_alloc_and_map(&cmd)', 'cmd', False),
                ('CAM_REQ_MGR_MAP_BUF', 'cam_mem_mgr_map(&cmd)', 'cmd', False),
                ('CAM_REQ_MGR_RELEASE_BUF', 'cam_mem_mgr_release(&cmd)', 'cmd', True)]
            for op, call, packet, destructive in operations:
                original = '\t\trc = ' + call + ';'
                guard = ('\t\trc = pico_hub_validate_native_release(file, fh, 0x10000,\n'
                         '\t\t\t' + op + ', &' + packet + ');\n\t\tif (rc)\n\t\t\tbreak;\n') if destructive else ''
                hook = '\n\t\trc = pico_hub_complete_native_ioctl(file, fh, 0x10000,\n\t\t\t' + op + ', &' + packet + ', rc);'
                text = replace(text, original, guard + original + hook)
        else:
            for kind in ['create', 'destroy']:
                text = replace(text, 'static int cam_sync_handle_' + kind + '(struct cam_private_ioctl_arg *k_ioctl)',
                               'static int cam_sync_handle_' + kind + '(struct file *file, void *fh,\n\tstruct cam_private_ioctl_arg *k_ioctl)')
                text = replace(text, 'rc = cam_sync_handle_' + kind + '(&k_ioctl);', 'rc = cam_sync_handle_' + kind + '(filep, fh, &k_ioctl);')
            text = replace(text, 'result = cam_sync_create(&sync_create.sync_obj,\n\t\tsync_create.name);',
                           'result = cam_sync_create(&sync_create.sync_obj,\n\t\tsync_create.name);\n\tresult = pico_hub_complete_native_ioctl(file, fh, 0x10100,\n\t\tCAM_SYNC_CREATE, &sync_create, result);')
            text = replace(text, '\treturn cam_sync_destroy(sync_create.sync_obj);',
                           '\t{\n\t\tint rc = pico_hub_validate_native_release(file, fh, 0x10100,\n\t\t\tCAM_SYNC_DESTROY, &sync_create);\n\t\tif (rc)\n\t\t\treturn rc;\n\t\trc = cam_sync_destroy(sync_create.sync_obj);\n\t\treturn pico_hub_complete_native_ioctl(file, fh, 0x10100,\n\t\t\tCAM_SYNC_DESTROY, &sync_create, rc);\n\t}')
        content[name] = text.encode()
    for name, data in content.items():
        if (SOURCE / name).read_bytes() != data:
            (SOURCE / name).write_bytes(data)
    report = {'sources': {name: hashlib.sha256(data).hexdigest() for name, data in content.items()},
              'original_sources': old, 'scope': 'Native kernel packet validation/capture before usercopy; original callback preserved',
              'hub_nodes_registered': False, 'device_modified': False}
    report_path.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
