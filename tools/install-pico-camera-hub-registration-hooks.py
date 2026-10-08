"""Install owned CRM/sync node publication and defer native V4L2 frees."""
from pathlib import Path
import hashlib
import json

BASE = Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro')
SOURCE = BASE / 'source/phoenix-kernel-recovery'
CRM = 'techpack/camera/drivers/cam_req_mgr/cam_req_mgr_dev.c'
SYNC = 'techpack/camera/drivers/cam_sync/cam_sync.c'


def replace(text, old, new):
    if text.count(old) != 1:
        raise RuntimeError('Unexpected source anchor: ' + old)
    return text.replace(old, new)


def body(text, signature, replacement):
    start = text.index(signature)
    pos = text.index('{', start) + 1
    depth = 1
    while depth:
        depth += (text[pos] == '{') - (text[pos] == '}')
        pos += 1
    return text[:start] + replacement + text[pos:]


def main():
    root = Path(__file__).resolve().parent.parent
    report_path = root / 'reports/kernel-source/recovery-20261003/camera-hub-registration-hooks.json'
    old = {CRM: '66d9a16ca67680f364b726d776cabbc152c333400ecdd0178ddbc925c8e8edbd', SYNC: '349019461b0cf5edd0b1f6250bf3e8c175fdbcc373079d9044b08d50cd718cad'}
    previous = json.loads(report_path.read_text())['sources'] if report_path.exists() else {}
    content = {}
    for name, digest in old.items():
        data = (SOURCE / name).read_bytes()
        actual = hashlib.sha256(data).hexdigest()
        if actual == previous.get(name):
            if name == SYNC:
                text = data.decode()
                anchor = 'v4l2_device_unregister(sync_dev->vdev->v4l2_dev);'
                if anchor in text:
                    text = replace(text, anchor, 'v4l2_device_unregister(&sync_dev->v4l2_dev);')
                    data = text.encode()
                anchor = 'register_fail:\n\tmedia_device_cleanup(sync_dev->v4l2_dev.mdev);\n\treturn rc;'
                if anchor in text:
                    text = replace(text, anchor, 'register_fail:\n\tmedia_device_cleanup(sync_dev->v4l2_dev.mdev);\n\tkfree(sync_dev->v4l2_dev.mdev);\n\tsync_dev->v4l2_dev.mdev = NULL;\n\treturn rc;')
                    data = text.encode()
            content[name] = data
            continue
        if actual != digest:
            raise RuntimeError('Preserve differing source: ' + name)
        text = replace(data.decode(), '#include "../cam_core/pico_camera_hub_dispatch.h"', '#include "../cam_core/pico_camera_hub_dispatch.h"\n#include "../cam_core/pico_camera_hub_registration.h"')
        if name == CRM:
            text = replace(text, '\tmedia_entity_cleanup(&g_dev.video->entity);', '\tif (g_dev.video)\n\t\tmedia_entity_cleanup(&g_dev.video->entity);')
            text = replace(text, 'static int cam_v4l2_device_setup(', 'static void cam_v4l2_device_release(struct v4l2_device *v4l2)\n{\n\tkfree(v4l2);\n}\n\nstatic int cam_v4l2_device_setup(')
            text = replace(text, '\trc = v4l2_device_register(dev, g_dev.v4l2_dev);', '\tg_dev.v4l2_dev->release = cam_v4l2_device_release;\n\trc = v4l2_device_register(dev, g_dev.v4l2_dev);')
            text = replace(text, '\tv4l2_device_unregister(g_dev.v4l2_dev);\n\tkfree(g_dev.v4l2_dev);', '\tv4l2_device_unregister(g_dev.v4l2_dev);\n\tv4l2_device_put(g_dev.v4l2_dev);')
            text = replace(text, '\trc = video_register_device(g_dev.video, VFL_TYPE_GRABBER, -1);\n\tif (rc)\n\t\tgoto v4l2_fail;', '\trc = pico_hub_register_video_device(g_dev.video, CAM_VNODE_DEVICE_TYPE);\n\tif (rc) {\n\t\tg_dev.video = NULL;\n\t\tgoto video_fail;\n\t}')
            text = replace(text, 'entity_fail:\n\tvideo_unregister_device(g_dev.video);\nv4l2_fail:\n\tvideo_device_release(g_dev.video);', 'entity_fail:\n\twhile (pico_hub_unregister_video_device(g_dev.video) == -EBUSY)\n\t\tcond_resched();')
            text = body(text, 'void cam_video_device_cleanup(void)', 'void cam_video_device_cleanup(void)\n{\n\tif (!g_dev.video)\n\t\treturn;\n\twhile (pico_hub_unregister_video_device(g_dev.video) == -EBUSY)\n\t\tcond_resched();\n\tg_dev.video = NULL;\n}')
            text = replace(text, 'static int cam_req_mgr_remove(struct platform_device *pdev)\n{', 'static int cam_req_mgr_remove(struct platform_device *pdev)\n{\n\tint rc = pico_hub_unregister_video_device(g_dev.video);\n\tif (rc)\n\t\treturn rc;\n\tg_dev.video = NULL;')
            start = text.index('static int cam_req_mgr_probe(')
            end = text.index('static const struct of_device_id', start)
            probe = text[start:end]
            probe = replace(probe, '\treturn rc;\n\nreq_mgr_core_fail:', '\trc = pico_hub_activate_video_device(g_dev.video);\n\tif (!rc)\n\t\treturn 0;\n\tcam_req_mgr_core_device_deinit();\n\tg_dev.state = false;\n\nreq_mgr_core_fail:')
            text = text[:start] + probe + text[end:]
        else:
            # Native sync state contains its V4L2 device; defer freeing state
            # until the last original node reference is gone.
            text = replace(text, 'static int cam_sync_probe(', 'static void cam_sync_v4l2_release(struct v4l2_device *v4l2)\n{\n\tkfree(container_of(v4l2, struct sync_device, v4l2_dev));\n}\n\nstatic int cam_sync_probe(')
            text = replace(text, '\tmedia_entity_cleanup(&sync_dev->vdev->entity);', '\tif (sync_dev->vdev)\n\t\tmedia_entity_cleanup(&sync_dev->vdev->entity);')
            text = replace(text, '\tkfree(sync_dev->v4l2_dev.mdev);', '\tkfree(sync_dev->v4l2_dev.mdev);\n\tsync_dev->v4l2_dev.mdev = NULL;')
            text = replace(text, 'register_fail:\n\tmedia_device_cleanup(sync_dev->v4l2_dev.mdev);\n\treturn rc;', 'register_fail:\n\tmedia_device_cleanup(sync_dev->v4l2_dev.mdev);\n\tkfree(sync_dev->v4l2_dev.mdev);\n\tsync_dev->v4l2_dev.mdev = NULL;\n\treturn rc;')
            start = text.index('static int cam_sync_probe(')
            end = text.index('static int cam_sync_remove(', start)
            probe = text[start:end]
            probe = replace(probe, '\tint idx;', '\tint idx;\n\tbool v4l2_registered = false, hub_registered = false;')
            probe = replace(probe, 'v4l2_device_unregister(sync_dev->vdev->v4l2_dev);', 'v4l2_device_unregister(&sync_dev->v4l2_dev);')
            probe = replace(probe, '\trc = v4l2_device_register(&(pdev->dev),', '\tsync_dev->v4l2_dev.release = cam_sync_v4l2_release;\n\trc = v4l2_device_register(&(pdev->dev),')
            probe = replace(probe, '\t\tgoto register_fail;', '\t\tgoto register_fail;\n\tv4l2_registered = true;')
            probe = replace(probe, '\trc = video_register_device(sync_dev->vdev,\n\t\tVFL_TYPE_GRABBER, -1);\n\tif (rc < 0)\n\t\tgoto v4l2_fail;', '\trc = pico_hub_register_video_device(sync_dev->vdev, CAM_SYNC_DEVICE_TYPE);\n\tif (rc < 0) {\n\t\tsync_dev->vdev = NULL;\n\t\tgoto v4l2_fail;\n\t}\n\thub_registered = true;')
            probe = replace(probe, '\treturn rc;\n\nv4l2_fail:', '\trc = pico_hub_activate_video_device(sync_dev->vdev);\n\tif (!rc)\n\t\treturn 0;\n\nv4l2_fail:\n\tif (hub_registered) {\n\t\twhile (pico_hub_unregister_video_device(sync_dev->vdev) == -EBUSY)\n\t\t\tcond_resched();\n\t\tsync_dev->vdev = NULL;\n\t}\n\tif (sync_dev->work_queue)\n\t\tdestroy_workqueue(sync_dev->work_queue);')
            probe = replace(probe, '\tvideo_device_release(sync_dev->vdev);', '\tif (sync_dev->vdev)\n\t\tvideo_device_release(sync_dev->vdev);')
            probe = replace(probe, '\tkfree(sync_dev);\n\treturn rc;', '\tif (v4l2_registered) {\n\t\tstruct sync_device *old = sync_dev;\n\t\tsync_dev = NULL;\n\t\tv4l2_device_put(&old->v4l2_dev);\n\t} else {\n\t\tkfree(sync_dev);\n\t\tsync_dev = NULL;\n\t}\n\treturn rc;')
            text = text[:start] + probe + text[end:]
            text = body(text, 'static int cam_sync_remove(struct platform_device *pdev)', 'static int cam_sync_remove(struct platform_device *pdev)\n{\n\tstruct sync_device *old = sync_dev;\n\tint rc = pico_hub_unregister_video_device(old->vdev);\n\tif (rc)\n\t\treturn rc;\n\told->vdev = NULL;\n\tdestroy_workqueue(old->work_queue);\n\tdebugfs_remove_recursive(old->dentry);\n\told->dentry = NULL;\n\tcam_sync_media_controller_cleanup(old);\n\tv4l2_device_unregister(&old->v4l2_dev);\n\tmutex_destroy(&old->table_lock);\n\tsync_dev = NULL;\n\tv4l2_device_put(&old->v4l2_dev);\n\treturn 0;\n}')
        content[name] = text.encode()
    for name, data in content.items():
        if (SOURCE / name).read_bytes() != data:
            (SOURCE / name).write_bytes(data)
    report = {'sources': {name: hashlib.sha256(data).hexdigest() for name, data in content.items()}, 'preimages': old,
              'scope': 'Owned original/hub registration, gate until native ready, deferred native V4L2 state freeing; physical detach still requires successful quiescence',
              'device_modified': False}
    report_path.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
