"""Test real decode/apply -> registry -> event routing with mocked usercopy.

Driver execution is an explicit input result; it is not simulated as a working
physical driver. Tests cover success-only tracking and packet/header ABI logic.
"""
from pathlib import Path
import hashlib
import importlib.util
import json
import subprocess

BASE = Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro')
DIRECTORY = 'techpack/camera/drivers/cam_core/'

MOCKS = r'''
#define VIDIOC_CAM_CONTROL 0xc01856c0U
#define CAM_REQ_MGR_CREATE_SESSION 0x10b
#define CAM_REQ_MGR_DESTROY_SESSION 0x10c
#define CAM_REQ_MGR_LINK 0x10d
#define CAM_REQ_MGR_UNLINK 0x10e
#define CAM_REQ_MGR_ALLOC_BUF 0x112
#define CAM_REQ_MGR_MAP_BUF 0x113
#define CAM_REQ_MGR_RELEASE_BUF 0x114
#define CAM_REQ_MGR_LINK_V2 0x117
#define __user
#define list_first_entry(head,type,member) ((type *)((char *)(head)->next - offsetof(type,member)))
#define pico_hub_check_resource_layouts() ((void)0)
#define CAM_SYNC_CREATE 0
#define CAM_SYNC_DESTROY 1
#define pico_hub_check_ioctl_layouts() ((void)0)
#define u64_to_user_ptr(n) ((void *)(uintptr_t)(n))
struct cam_control {u32 op_code,size,handle_type,reserved;uint64_t handle;};
struct cam_private_ioctl_arg {u32 id,size,result,reserved;uint64_t ioctl_ptr;};
struct cam_req_mgr_session_info {int32_t session_hdl,reserved;};
struct cam_sync_info {char name[64];int32_t sync_obj;};
struct cam_mem_alloc_out_params {u32 buf_handle;int32_t fd;uint64_t vaddr;};
struct cam_mem_map_out_params {u32 buf_handle,reserved;uint64_t vaddr;};
struct cam_mem_mgr_alloc_cmd {uint64_t len,align;int32_t mmu_hdls[16];u32 num_hdl,flags;struct cam_mem_alloc_out_params out;};
struct cam_mem_mgr_map_cmd {int32_t mmu_hdls[16];u32 num_hdl,flags;int32_t fd;u32 reserved;struct cam_mem_map_out_params out;};
struct cam_mem_mgr_release_cmd {int32_t buf_handle;u32 reserved;};
struct cam_req_mgr_link_info {int32_t session_hdl;u32 num_devices;int32_t dev_hdls[64];int32_t link_hdl;};
struct cam_req_mgr_link_info_v2 {int32_t session_hdl;u32 num_devices;int32_t dev_hdls[128];int32_t link_hdl;};
struct cam_req_mgr_ver_info {u32 version;union {struct cam_req_mgr_link_info link_info_v1;struct cam_req_mgr_link_info_v2 link_info_v2;} u;};
struct cam_req_mgr_unlink_info {int32_t session_hdl,link_hdl;};
struct pico_hub_buffer_record {struct cam_mem_mgr_alloc_cmd info;struct list_head list;};
struct pico_hub_link_record {struct cam_req_mgr_ver_info info;struct list_head list;};
static int fail_copy;
static unsigned copies;
static unsigned long copy_from_user(void *to,const void *from,size_t n) {
 assert(!held);copies++;if(fail_copy || !from)return n;memcpy(to,from,n);return 0;
}
/* IOCTL_HEADER */
/* BODIES */
static int apply(struct pico_hub_client *client,struct pico_hub_ioctl_transition *t) {
 pico_hub_registry_lock();int rc=pico_hub_apply_ioctl_transition_locked(client,t);pico_hub_registry_unlock();return rc;
}
static int route(struct video_device *video,u32 key) {
 struct v4l2_event e={0};memcpy(e.u.data,&key,4);
 pico_hub_registry_lock();int rc=pico_hub_route_event_locked(video,&e);pico_hub_registry_unlock();return rc;
}
int main(void) {
 struct video_device v[4]={{0}};v[0].entity.function=0x10000;v[2].entity.function=0x10100;
 struct pico_hub_video crm={.original=&v[0],.shadow=&v[1],.multi_client=true};
 struct pico_hub_video sync={.original=&v[2],.shadow=&v[3],.multi_client=true};
 struct pico_hub_client c={.fh={.vdev=&v[1]}},s={.fh={.vdev=&v[3]}};
 INIT_LIST_HEAD(&c.fh.subscribed);INIT_LIST_HEAD(&s.fh.subscribed);
 pico_hub_registry_lock();assert(!pico_hub_add_video_locked(&crm));assert(!pico_hub_add_video_locked(&sync));
 assert(!pico_hub_attach_client_locked(&crm,&c));assert(!pico_hub_attach_client_locked(&sync,&s));pico_hub_registry_unlock();
 struct cam_req_mgr_session_info session={.session_hdl=(int32_t)0xdeadbeefU};
 struct cam_control ctrl={.op_code=CAM_REQ_MGR_CREATE_SESSION,.size=8,.handle=(uintptr_t)&session};
 struct pico_hub_ioctl_transition t;
 assert(!pico_hub_decode_ioctl_result(0x10000,VIDIOC_CAM_CONTROL,&ctrl,0,&t));
 assert(t.action==PICO_HUB_ADD_SESSION && t.key==0xdeadbeefU);
 assert(!apply(&c,&t));assert(!route(&v[0],t.key));assert(last_fh==&c.fh);
 assert(apply(&c,&t)==-EEXIST);assert(apply(&s,&t)==-EINVAL);
 ctrl.op_code=CAM_REQ_MGR_DESTROY_SESSION;unsigned before=copies;
 assert(pico_hub_decode_ioctl_result(0x10000,VIDIOC_CAM_CONTROL,&ctrl,-EIO,&t)==-EIO);
 assert(t.action==PICO_HUB_HANDLE_NONE && copies==before);
 assert(!apply(&c,&t));assert(!route(&v[0],0xdeadbeefU)); /* failure did not remove */
 assert(pico_hub_decode_ioctl_result(0x10000,VIDIOC_CAM_CONTROL,&ctrl,0x100000005L,&t)==0x100000005L);
 assert(copies==before && t.action==PICO_HUB_HANDLE_NONE);
 assert(!pico_hub_decode_ioctl_result(0x10000,VIDIOC_CAM_CONTROL,&ctrl,0,&t));
 assert(t.action==PICO_HUB_REMOVE_SESSION);assert(!apply(&c,&t));assert(route(&v[0],t.key)==-1);
 assert(apply(&c,&t)==-ENOENT);
 struct cam_sync_info info={.name="test",.sync_obj=42};
 struct cam_private_ioctl_arg sync_ctrl={.id=CAM_SYNC_CREATE,.size=68,.result=123,.ioctl_ptr=(uintptr_t)&info};
 assert(!pico_hub_decode_ioctl_result(0x10100,VIDIOC_CAM_CONTROL,&sync_ctrl,0,&t));
 assert(t.action==PICO_HUB_ADD_SYNC && t.key==42 && sync_ctrl.result==123);
 assert(!apply(&s,&t));assert(!route(&v[2],42));assert(last_fh==&s.fh);
 assert(route(&v[0],42)==-1);
 sync_ctrl.id=CAM_SYNC_DESTROY;
 assert(!pico_hub_decode_ioctl_result(0x10100,VIDIOC_CAM_CONTROL,&sync_ctrl,0,&t));
 assert(!apply(&s,&t));assert(route(&v[2],42)==-1);
 sync_ctrl.size=4;assert(pico_hub_decode_ioctl_result(0x10100,VIDIOC_CAM_CONTROL,&sync_ctrl,0,&t)==-EINVAL);
 assert(t.action==PICO_HUB_HANDLE_NONE);sync_ctrl.size=68;
 sync_ctrl.ioctl_ptr=0;assert(pico_hub_decode_ioctl_result(0x10100,VIDIOC_CAM_CONTROL,&sync_ctrl,0,&t)==-EINVAL);
 sync_ctrl.ioctl_ptr=(uintptr_t)&info;fail_copy=1;
 assert(pico_hub_decode_ioctl_result(0x10100,VIDIOC_CAM_CONTROL,&sync_ctrl,0,&t)==-EFAULT);assert(!t.action);fail_copy=0;
 ctrl.size=7;assert(pico_hub_decode_ioctl_result(0x10000,VIDIOC_CAM_CONTROL,&ctrl,0,&t)==-EINVAL);ctrl.size=8;
 assert(pico_hub_decode_ioctl_result(0x10000,VIDIOC_CAM_CONTROL,NULL,0,&t)==-EINVAL);
 before=copies;ctrl.op_code=0x115;
 assert(!pico_hub_decode_ioctl_result(0x10000,VIDIOC_CAM_CONTROL,&ctrl,0,&t));assert(!t.action && copies==before);
 assert(!pico_hub_decode_ioctl_result(0x10000,123,&ctrl,0,&t));assert(!t.action && copies==before);
 assert(!pico_hub_decode_ioctl_result(0x10003,VIDIOC_CAM_CONTROL,&ctrl,0,&t));assert(!t.action && copies==before);
 ctrl.op_code=CAM_REQ_MGR_CREATE_SESSION;
 assert(!pico_hub_decode_ioctl_result(0x10000,VIDIOC_CAM_CONTROL,&ctrl,0,&t));
 fail_alloc=1;assert(apply(&c,&t)==-ENOMEM);fail_alloc=0;assert(route(&v[0],t.key)==-1);
 t.action=999;assert(apply(&c,&t)==-EINVAL);
 struct cam_mem_mgr_alloc_cmd alloc={.len=4096,.align=64,.num_hdl=1,.flags=7,.out={.buf_handle=99,.fd=17,.vaddr=0x12345678}};
 ctrl=(struct cam_control){.op_code=CAM_REQ_MGR_ALLOC_BUF,.size=104,.handle=(uintptr_t)&alloc};
 assert(!pico_hub_decode_ioctl_result(0x10000,VIDIOC_CAM_CONTROL,&ctrl,0,&t));
 assert(t.action==PICO_HUB_ADD_BUFFER && t.key==99);assert(!apply(&c,&t));
 struct pico_hub_buffer_record *b=list_first_entry(&c.reserved_handles_40,struct pico_hub_buffer_record,list);
 assert(!memcmp(&b->info,&alloc,sizeof(alloc)));assert(apply(&c,&t)==-EEXIST);assert(apply(&s,&t)==-EINVAL);
 pico_hub_registry_lock();assert(pico_hub_detach_client_locked(&c)==-EBUSY);pico_hub_registry_unlock();
 struct cam_mem_mgr_release_cmd release={.buf_handle=99};ctrl.op_code=CAM_REQ_MGR_RELEASE_BUF;ctrl.size=8;ctrl.handle=(uintptr_t)&release;
 assert(pico_hub_decode_ioctl_result(0x10000,VIDIOC_CAM_CONTROL,&ctrl,-EIO,&t)==-EIO);assert(!apply(&c,&t));
 assert(!list_empty(&c.reserved_handles_40));
 assert(!pico_hub_decode_ioctl_result(0x10000,VIDIOC_CAM_CONTROL,&ctrl,0,&t));assert(!apply(&c,&t));assert(apply(&c,&t)==-ENOENT);
 struct cam_mem_mgr_map_cmd map={.fd=123,.flags=8,.out={.buf_handle=77,.vaddr=999}};
 ctrl.op_code=CAM_REQ_MGR_MAP_BUF;ctrl.size=96;ctrl.handle=(uintptr_t)&map;
 assert(!pico_hub_decode_ioctl_result(0x10000,VIDIOC_CAM_CONTROL,&ctrl,0,&t));
 struct cam_mem_mgr_alloc_cmd expected={.out={.buf_handle=77}};assert(!memcmp(&t.data.buffer,&expected,sizeof(expected)));
 fail_alloc=1;assert(apply(&c,&t)==-ENOMEM);fail_alloc=0;assert(list_empty(&c.reserved_handles_40));assert(!apply(&c,&t));
 release.buf_handle=77;ctrl.op_code=CAM_REQ_MGR_RELEASE_BUF;ctrl.size=8;ctrl.handle=(uintptr_t)&release;
 assert(!pico_hub_decode_ioctl_result(0x10000,VIDIOC_CAM_CONTROL,&ctrl,0,&t));assert(!apply(&c,&t));
 struct cam_req_mgr_link_info_v2 link={.session_hdl=51,.num_devices=128,.link_hdl=701};
 for(int i=0;i<128;i++)link.dev_hdls[i]=i+1000;
 ctrl.op_code=CAM_REQ_MGR_LINK_V2;ctrl.size=524;ctrl.handle=(uintptr_t)&link;
 assert(!pico_hub_decode_ioctl_result(0x10000,VIDIOC_CAM_CONTROL,&ctrl,0,&t));assert(t.data.link.version==2 && t.key==701);
 assert(!memcmp(&t.data.link.u.link_info_v2,&link,sizeof(link)));assert(!apply(&c,&t));assert(apply(&c,&t)==-EEXIST);
 struct pico_hub_link_record *l=list_first_entry(&c.reserved_handles_56,struct pico_hub_link_record,list);
 assert(l->info.version==2 && !memcmp(&l->info.u.link_info_v2,&link,sizeof(link)));
 pico_hub_registry_lock();assert(pico_hub_detach_client_locked(&c)==-EBUSY);pico_hub_registry_unlock();
 struct cam_req_mgr_unlink_info unlink={.session_hdl=51,.link_hdl=701};ctrl.op_code=CAM_REQ_MGR_UNLINK;ctrl.size=8;ctrl.handle=(uintptr_t)&unlink;
 assert(pico_hub_decode_ioctl_result(0x10000,VIDIOC_CAM_CONTROL,&ctrl,-EIO,&t)==-EIO);assert(!apply(&c,&t));assert(!list_empty(&c.reserved_handles_56));
 assert(!pico_hub_decode_ioctl_result(0x10000,VIDIOC_CAM_CONTROL,&ctrl,0,&t));assert(t.key==701);assert(!apply(&c,&t));assert(apply(&c,&t)==-ENOENT);
 struct cam_req_mgr_link_info legacy={.session_hdl=52,.num_devices=1,.dev_hdls={61},.link_hdl=702};
 ctrl.op_code=CAM_REQ_MGR_LINK;ctrl.size=268;ctrl.handle=(uintptr_t)&legacy;
 assert(!pico_hub_decode_ioctl_result(0x10000,VIDIOC_CAM_CONTROL,&ctrl,0,&t));assert(t.data.link.version==1 && t.key==702);
 assert(!apply(&c,&t));pico_hub_registry_lock();assert(!pico_hub_remove_link_locked(&c,702));pico_hub_registry_unlock();
 ctrl.size--;assert(pico_hub_decode_ioctl_result(0x10000,VIDIOC_CAM_CONTROL,&ctrl,0,&t)==-EINVAL);assert(!t.action);ctrl.size++;
 fail_copy=1;assert(pico_hub_decode_ioctl_result(0x10000,VIDIOC_CAM_CONTROL,&ctrl,0,&t)==-EFAULT);assert(!t.action);fail_copy=0;
 pico_hub_registry_lock();assert(!pico_hub_detach_client_locked(&c));assert(!pico_hub_detach_client_locked(&s));
 assert(!pico_hub_remove_video_locked(&crm));assert(!pico_hub_remove_video_locked(&sync));pico_hub_registry_unlock();
 assert(allocated==freed);
 puts("PASS: session/sync routing, ALLOC/MAP/RELEASE and LINK v1/v2/UNLINK tracking; original failure preserves ownership, strict ABI, bookkeeping ENOMEM, detach guards and no record leaks");
}
'''


def load(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    registry_test = load('test-pico-camera-hub-registry')
    event_test = load('test-pico-camera-hub-events')
    prefix = registry_test.HARNESS.split('/* SOURCE */')[0]
    prefix = prefix.replace('struct video_device {int marker;};', 'struct video_device {int marker;struct {unsigned function;} entity;};')
    prefix = prefix.replace('struct video_device *original,*shadow;struct list_head registry,subdevices,clients,events;int event_lock;',
                            'struct video_device *original,*shadow;struct list_head registry,subdevices,clients,events;int event_lock;bool multi_client;')
    prefix += event_test.EXTRA.split('/* BODIES */')[0]
    root = BASE / 'source/phoenix-kernel-recovery' / DIRECTORY
    registry = (root / 'pico_camera_hub_registry.c').read_text()
    events = (root / 'pico_camera_hub_events.c').read_text()
    ioctl = (root / 'pico_camera_hub_ioctl.c').read_text()
    header = (root / 'pico_camera_hub_ioctl.h').read_text()
    resources = (root / 'pico_camera_hub_resources.c').read_text()
    definitions = header[header.index('enum pico_hub_handle_action'):header.index('/* control is')]
    bodies = registry[registry.index('static DEFINE_MUTEX'):] + events[events.index('static bool pico_hub_client_attached_locked'):] + resources[resources.index('static bool pico_hub_resource_client_locked'):] + ioctl[ioctl.index('static long pico_hub_decode_resources'):]
    code = prefix + MOCKS.replace('/* IOCTL_HEADER */', definitions).replace('/* BODIES */', bodies)
    out = BASE / 'out/phoenix-kernel-recovery/camera-hub-ioctl-tests'
    out.mkdir(exist_ok=True)
    (out / 'harness.c').write_text(code)
    subprocess.run(['gcc', '-std=gnu11', '-g', '-O1', '-pthread', '-fsanitize=address,undefined',
                    '-fno-omit-frame-pointer', str(out / 'harness.c'), '-o', str(out / 'test')], check=True)
    result = subprocess.run([str(out / 'test')], capture_output=True, text=True, timeout=30)
    names = ['pico_camera_hub_ioctl.c', 'pico_camera_hub_ioctl.h', 'pico_camera_hub_registry.c', 'pico_camera_hub_events.c', 'pico_camera_hub.h', 'pico_camera_hub_resources.c', 'pico_camera_hub_resources.h']
    report = {'sources': {DIRECTORY + name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in names},
              'harness_sha256': hashlib.sha256(code.encode()).hexdigest(),
              'scope': 'Actual decode/apply/registry/route bodies with mock usercopy/FH; explicit driver result, no real original ioctl/V4L2/IRQ',
              'exit_code': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr,
              'sanitizers': ['AddressSanitizer', 'UndefinedBehaviorSanitizer'], 'device_modified': False}
    (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    if result.returncode:
        raise SystemExit(result.returncode)


if __name__ == '__main__':
    main()
