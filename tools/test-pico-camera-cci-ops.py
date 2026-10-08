"""Actual factory-policy/update helpers and native CCI late assign body."""
from pathlib import Path
import hashlib
import json
import subprocess
import importlib.util


def load(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MOCKS = r'''
struct v4l2_file_operations {int marker;};
static const struct v4l2_file_operations before={1},after={2};
static struct v4l2_file_operations cci_v4l2_subdev_fops={3};
#define MAX_CCI 2
#define CAM_CCI 0
#define CAM_ERR(...) ((void)0)
static struct v4l2_subdev *g_cci_subdev[2];
static bool source_multi_enabled;
'''

MAIN = r'''
int main(void) {
 assert(pico_hub_entity_multi_client(0x10000));assert(pico_hub_entity_multi_client(0x10003));assert(pico_hub_entity_multi_client(0x10100));
 assert(!pico_hub_entity_multi_client(0x1000a));assert(!pico_hub_entity_multi_client(0x10001));assert(!pico_hub_entity_multi_client(0));
 struct video_device videos[4]={{0}};struct pico_hub_video parent={.original=&videos[0],.shadow=&videos[1]},other={.original=&videos[2],.shadow=&videos[3]};
 struct v4l2_subdev sd[4]={{0}};struct video_device nodes[2]={{.fops=&before},{.fops=&before}};
 sd[0].devnode=&nodes[0];sd[2].devnode=&nodes[1];
 struct pico_hub_subdevice multi={.original=&sd[0],.shadow=&sd[1],.multi_client=true,.original_fops=&before};
 struct pico_hub_subdevice cci={.original=&sd[2],.shadow=&sd[3],.multi_client=false,.original_fops=&before};
 assert(cam_device_hub_handle_v4l2_subdevice_ops_changed(NULL,&after)==-EINVAL);
 assert(cam_device_hub_handle_v4l2_subdevice_ops_changed(&sd[0],NULL)==-EINVAL);
 assert(cam_device_hub_handle_v4l2_subdevice_ops_changed(&sd[0],&after)==-ENOENT);
 pico_hub_registry_lock();assert(!pico_hub_add_video_locked(&parent));assert(!pico_hub_add_video_locked(&other));assert(!pico_hub_add_subdevice_locked(&parent,&multi));assert(!pico_hub_add_subdevice_locked(&other,&cci));pico_hub_registry_unlock();
 assert(!cam_device_hub_handle_v4l2_subdevice_ops_changed(&sd[0],&after));assert(multi.original_fops==&after && nodes[0].fops==&before);
 assert(!cam_device_hub_handle_v4l2_subdevice_ops_changed(&sd[1],&before));assert(multi.original_fops==&before);
 assert(cam_device_hub_handle_v4l2_subdevice_ops_changed(&sd[0],(const void *)&multi.fops)==-ELOOP);assert(multi.original_fops==&before);
 multi.shared_file=(void *)1;assert(cam_device_hub_handle_v4l2_subdevice_ops_changed(&sd[0],&after)==-EBUSY);
 pico_hub_registry_lock();assert(pico_hub_remove_subdevice_locked(&parent,&multi)==-EBUSY);pico_hub_registry_unlock();multi.shared_file=NULL;
 struct list_head live;list_add(&live,&multi.clients);assert(cam_device_hub_handle_v4l2_subdevice_ops_changed(&sd[0],&after)==-EBUSY);
 pico_hub_registry_lock();assert(pico_hub_remove_subdevice_locked(&parent,&multi)==-EBUSY);pico_hub_registry_unlock();list_del_init(&live);
 assert(!cam_device_hub_handle_v4l2_subdevice_ops_changed(&sd[2],&after));assert(cci.original_fops==&before); /* Factory non-multi no-op. */
 /* Actual CCI writer precedes the hook, whose result is ignored. */
 g_cci_subdev[0]=&sd[0];g_cci_subdev[1]=&sd[2];assert(!cam_cci_assign_fops());assert(nodes[0].fops==&cci_v4l2_subdev_fops && multi.original_fops==&cci_v4l2_subdev_fops);
 assert(nodes[1].fops==&cci_v4l2_subdev_fops && cci.original_fops==&before);
 sd[2].devnode=NULL;assert(cam_cci_assign_fops()==-EINVAL);sd[2].devnode=&nodes[1];g_cci_subdev[0]=NULL;nodes[1].fops=&before;assert(!cam_cci_assign_fops());assert(nodes[1].fops==&before);
 pico_hub_registry_lock();assert(!pico_hub_remove_subdevice_locked(&parent,&multi));assert(!pico_hub_remove_subdevice_locked(&other,&cci));pico_hub_registry_unlock();
 g_cci_subdev[0]=&sd[0];g_cci_subdev[1]=&sd[2];assert(!cam_cci_assign_fops()); /* Missing hub entry does not fail native late init. */
 pico_hub_registry_lock();assert(!pico_hub_remove_video_locked(&parent));assert(!pico_hub_remove_video_locked(&other));pico_hub_registry_unlock();
 puts("PASS: factory three-entity policy, original/shadow lookup, multi-only saved fops update, null/missing/self/busy guards and busy subdevice detach; actual CCI assignment-before-hook, two nodes, null/missing devnode and ignored hub miss");
}
'''


def main():
    common = load('test-pico-camera-hub-registry')
    prefix = common.HARNESS.split('/* SOURCE */')[0]
    prefix = prefix.replace('struct video_device {int marker;};', 'struct video_device {int marker;const struct v4l2_file_operations *fops;};')
    prefix = prefix.replace('struct v4l2_subdev {int marker;};', 'struct v4l2_subdev {int marker;struct video_device *devnode;};')
    base = Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro')
    source = base / 'source/phoenix-kernel-recovery'
    names = ['techpack/camera/drivers/cam_core/pico_camera_hub_registry.c', 'techpack/camera/drivers/cam_core/pico_camera_hub.h', 'techpack/camera/drivers/cam_sensor_module/cam_cci/cam_cci_dev.c']
    registry = (source / names[0]).read_text()
    cci = (source / names[2]).read_text()
    native = load('test-pico-camera-hub-dispatch').function(cci, 'static int cam_cci_assign_fops(')
    code = prefix + MOCKS + registry[registry.index('static DEFINE_MUTEX'):] + native + MAIN
    out = base / 'out/phoenix-kernel-recovery/camera-cci-ops-tests'
    out.mkdir(exist_ok=True)
    (out / 'harness.c').write_text(code)
    subprocess.run(['gcc', '-std=gnu11', '-g', '-O1', '-pthread', '-fsanitize=address,undefined', '-fno-omit-frame-pointer', str(out / 'harness.c'), '-o', str(out / 'test')], check=True)
    result = subprocess.run([str(out / 'test')], capture_output=True, text=True, timeout=30)
    report = {'sources': {n: hashlib.sha256((source / n).read_bytes()).hexdigest() for n in names}, 'harness_sha256': hashlib.sha256(code.encode()).hexdigest(), 'exit_code': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr, 'sanitizers': ['AddressSanitizer', 'UndefinedBehaviorSanitizer'], 'scope': 'Actual registry/policy/fops-change and native CCI late-assignment bodies with host lists/mutexes; no registered shadow subdevices or hardware CCI operations', 'device_modified': False}
    (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    raise SystemExit(result.returncode)


if __name__ == '__main__':
    main()
