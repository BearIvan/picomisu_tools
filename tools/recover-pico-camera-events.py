"""Restore the two proven V4L2 event bridge exports and their live CRM hooks.

This is the event subscription slice only, not the device-hub reconstruction.
"""
from pathlib import Path
import subprocess

SOURCE = Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro/source/phoenix-kernel-recovery')


def main():
    relative = 'techpack/camera/drivers/cam_req_mgr/cam_req_mgr_dev.c'
    path = SOURCE / relative
    if subprocess.check_output(['git', '-C', str(SOURCE), 'status', '--porcelain', '--', relative], text=True).strip():
        raise RuntimeError('Camera file has changes; preserve them')
    text = path.read_text()
    text = text.replace('static int cam_subscribe_event(', 'int bridge_cam_subscribe_event(')
    text = text.replace('static int cam_unsubscribe_event(', 'int bridge_cam_unsubscribe_event(')
    text = text.replace('.vidioc_subscribe_event = cam_subscribe_event,', '.vidioc_subscribe_event = bridge_cam_subscribe_event,')
    text = text.replace('.vidioc_unsubscribe_event = cam_unsubscribe_event,', '.vidioc_unsubscribe_event = bridge_cam_unsubscribe_event,')
    text = text.replace('return v4l2_event_subscribe(fh, sub, CAM_REQ_MGR_EVENT_MAX,',
                        '/* Factory bridge at Image+0xb99128 uses 240 events. */\n\treturn v4l2_event_subscribe(fh, sub, 240,')
    text = text.replace('static long cam_private_ioctl(', '''EXPORT_SYMBOL(bridge_cam_subscribe_event);
EXPORT_SYMBOL(bridge_cam_unsubscribe_event);

static long cam_private_ioctl(''')
    if text.count('EXPORT_SYMBOL(bridge_cam_') != 2:
        raise RuntimeError('Could not install camera bridge exports')
    path.write_text(text)
    header = SOURCE / 'techpack/camera/drivers/cam_req_mgr/cam_req_mgr_dev.h'
    text = header.read_text()
    insert = '''
/* Factory PICO event bridge; the device-hub layer is restored separately. */
struct v4l2_fh;
struct v4l2_event_subscription;
int bridge_cam_subscribe_event(struct v4l2_fh *fh,
	const struct v4l2_event_subscription *sub);
int bridge_cam_unsubscribe_event(struct v4l2_fh *fh,
	const struct v4l2_event_subscription *sub);

'''
    position = text.rfind('#endif')
    header.write_text(text[:position] + insert + text[position:])
    print('Restored camera event subscriptions, depth 240, live ioctl hooks, and exports')


if __name__ == '__main__':
    main()
