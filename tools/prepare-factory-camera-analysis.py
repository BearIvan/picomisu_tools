"""Prepare a full camera decompilation with BSS symbols and known kernel APIs.

The generated IDC only assigns analysis types. It never executes kernel code.
"""
from pathlib import Path
import json
import shutil

BASE = Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro')
PROJECT = Path(__file__).resolve().parents[1]
VA = 0xffffff8008080000
PROTOTYPES = {
    'printk': 'int printk(const char *format, ...);',
    'snprintf': 'int snprintf(char *buf, unsigned long size, const char *format, ...);',
    'strlcpy': 'unsigned long strlcpy(char *dst, const char *src, unsigned long len);',
    'memcpy': 'void *memcpy(void *dst, const void *src, unsigned long len);',
    'memset': 'void *memset(void *dst, int value, unsigned long len);',
    'kmem_cache_alloc_trace': 'void *kmem_cache_alloc_trace(void *cache, unsigned int flags, unsigned long size);',
    'kfree': 'void kfree(const void *ptr);',
    '__mutex_init': 'void __mutex_init(void *lock, const char *name, void *key);',
    'mutex_lock': 'void mutex_lock(void *lock);',
    'mutex_unlock': 'void mutex_unlock(void *lock);',
    'platform_device_alloc': 'void *platform_device_alloc(const char *name, int id);',
    'platform_device_add': 'int platform_device_add(void *device);',
    'platform_device_put': 'void platform_device_put(void *device);',
    'platform_device_unregister': 'void platform_device_unregister(void *device);',
    '__platform_driver_register': 'int __platform_driver_register(void *driver, void *module);',
    'platform_driver_unregister': 'void platform_driver_unregister(void *driver);',
    'v4l2_device_register': 'int v4l2_device_register(void *device, void *v4l2_device);',
    'v4l2_device_set_name': 'int v4l2_device_set_name(void *device, const char *base, void *instance);',
    'v4l2_device_unregister': 'void v4l2_device_unregister(void *device);',
    'v4l2_device_register_subdev': 'int v4l2_device_register_subdev(void *device, void *subdevice);',
    'v4l2_device_unregister_subdev': 'void v4l2_device_unregister_subdev(void *subdevice);',
    'v4l2_device_register_subdev_nodes': 'int v4l2_device_register_subdev_nodes(void *device);',
    'video_device_alloc': 'void *video_device_alloc(void);',
    'video_device_release': 'void video_device_release(void *device);',
    '__video_register_device': 'int __video_register_device(void *device, int type, int nr, int warn, void *module);',
    'video_unregister_device': 'void video_unregister_device(void *device);',
    'media_entity_pads_init': 'int media_entity_pads_init(void *entity, unsigned short count, void *pads);',
    'v4l2_subdev_init': 'void v4l2_subdev_init(void *subdevice, const void *ops);',
    'v4l2_fh_init': 'void v4l2_fh_init(void *fh, void *device);',
    'v4l2_fh_add': 'void v4l2_fh_add(void *fh);',
    'v4l2_fh_del': 'void v4l2_fh_del(void *fh);',
    'v4l2_fh_exit': 'void v4l2_fh_exit(void *fh);',
    'v4l2_event_queue_fh': 'void v4l2_event_queue_fh(void *fh, const void *event);',
    'v4l2_event_subscribe': 'int v4l2_event_subscribe(void *fh, const void *subscription, unsigned int elements, const void *ops);',
    'v4l2_event_unsubscribe': 'int v4l2_event_unsubscribe(void *fh, const void *subscription);',
    'video_ioctl2': 'long video_ioctl2(void *file, unsigned int command, unsigned long argument);',
    'vb2_queue_init': 'int vb2_queue_init(void *queue);',
    'vb2_queue_release': 'void vb2_queue_release(void *queue);',
    'vb2_reqbufs': 'int vb2_reqbufs(void *queue, void *request);',
    'vb2_qbuf': 'int vb2_qbuf(void *queue, void *buffer);',
    'vb2_dqbuf': 'int vb2_dqbuf(void *queue, void *buffer, int nonblocking);',
    'vb2_streamon': 'int vb2_streamon(void *queue, unsigned int type);',
    'vb2_streamoff': 'int vb2_streamoff(void *queue, unsigned int type);',
    'vb2_buffer_done': 'void vb2_buffer_done(void *buffer, int state);',
    'cam_register_subdev': 'int cam_register_subdev(void *subdevice);',
    'cam_unregister_subdev': 'int cam_unregister_subdev(void *subdevice);',
    'cam_mem_get_cpu_buf': 'int cam_mem_get_cpu_buf(int handle, unsigned long *address, unsigned long *length);',
    'cam_mem_put_cpu_buf': 'int cam_mem_put_cpu_buf(int handle);',
    'cam_get_module_name': 'const char *cam_get_module_name(unsigned int module);',
}


def main():
    symbols = [(int(a, 16), t, n) for a, t, n in
               (line.split() for line in (BASE / 'analysis/diff-5.13.7-vs-5.13.8/kernel/ks5.13.7.txt').read_text().splitlines())]
    selected = [(a, n) for a, t, n in symbols if t in 'tTwW' and
                (0xb8aff4 <= a <= 0xb926c8 or n in
                 ('cam_device_hub_init', 'cam_device_hub_exit', 'memento_init',
                  'cam_virtual_mono_init_module', 'cam_virtual_mono_exit_module',
                  'cam_quick_register_virtual_device', 'bridge_cam_subscribe_event', 'bridge_cam_unsubscribe_event'))]
    output = PROJECT / 'reports/kernel-source/recovery-20261003/ida-full'
    output.mkdir(parents=True, exist_ok=True)
    shutil.copy2(BASE / 'analysis/kernel-recovery/camera-full/factory-5.13.7-symbolized.elf', output / 'factory-kernel.elf')
    statements, applied = [], []
    for name, prototype in PROTOTYPES.items():
        found = [(a, t) for a, t, n in symbols if n == name and t in 'tTwW']
        if len(found) != 1:
            continue
        address = VA + found[0][0]
        statements.append(f'  if (!apply_type(0x{address:x}, {json.dumps(prototype)})) msg("type failed: {name}\\n");')
        applied.append({'name': name, 'ea': hex(address), 'prototype': prototype})
    idc = '#include <idc.idc>\nstatic main() {\n' + '\n'.join(statements) + '\n  msg("Kernel API types applied.\\n");\n}\n'
    (output / 'kernel-api-types.idc').write_text(idc)
    (output / 'analysis-inputs.json').write_text(json.dumps({'functions': selected,
                                                           'api_types': applied,
                                                           'bss_present': True,
                                                           'decompiler_output_is_not_compilable_source': True}, indent=2) + '\n')
    # Addresses avoid ambiguity from duplicate static symbol names.
    option = '-Ohexrays:camera-full.c:' + ':'.join(hex(VA + a) for a, _ in selected)
    (output / 'hexrays-option.txt').write_text(option)
    print('Selected', len(selected), 'functions;', len(applied), 'API prototypes')


if __name__ == '__main__':
    main()
