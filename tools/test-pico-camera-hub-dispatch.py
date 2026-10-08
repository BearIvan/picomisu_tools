"""Real dispatch plus actual native tracked CRM cases and sync helper bodies."""
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


SUPPORT = r'''
struct task_struct {int marker;};static struct task_struct task;static struct task_struct *current=&task;
struct file {void *private_data;struct video_device *vdev;};
struct v4l2_event_subscription {u32 type,id;};
struct v4l2_ioctl_ops {long (*vidioc_default)(struct file *,void *,bool,unsigned,void *);int (*vidioc_subscribe_event)(struct v4l2_fh *,const struct v4l2_event_subscription *);int (*vidioc_unsubscribe_event)(struct v4l2_fh *,const struct v4l2_event_subscription *);};
static struct video_device *video_devdata(struct file *f) {return f->vdev;}
#define LIST_HEAD(n) struct list_head n={&(n),&(n)}
#define pr_warn_ratelimited(...) ((void)0)
static bool ioctl_locked;
#undef lockdep_assert_held
#define lockdep_assert_held(p) assert((p)==&pico_hub_registry_mutex?held==1:ioctl_locked)
#define u64_to_user_ptr(n) ((void *)(uintptr_t)(n))
#define CAM_PRIVATE_IOCTL_CMD VIDIOC_CAM_CONTROL
#define SYNC_DEBUG_NAME_LEN 63
#define CAM_SYNC_REGISTER_PAYLOAD 2
#define CAM_SYNC_DEREGISTER_PAYLOAD 3
#define CAM_SYNC_SIGNAL 4
#define CAM_SYNC_MERGE 5
#define CAM_SYNC_WAIT 6
#define ENOIOCTLCMD 515
#define CAM_SYNC 0
#define CAM_ERR(...) ((void)0)
struct sync_device {int marker;};static struct sync_device sync_device;
static struct sync_device *video_drvdata(struct file *f) {return &sync_device;}
static int fail_output,mutate_output,fail_copy,driver_error,rollback_error;
static unsigned copies,outputs,callbacks,creates,releases;
static struct file *expected_file;static void *expected_fh;
static unsigned long copy_from_user(void *to,const void *from,size_t n) {assert(!held);copies++;if(fail_copy||!from)return n;memcpy(to,from,n);return 0;}
static unsigned long copy_to_user(void *to,const void *from,size_t n) {assert(!held);outputs++;if(fail_output)return n;memcpy(to,from,n);if(mutate_output && n==104)((struct cam_mem_mgr_alloc_cmd *)to)->out.buf_handle=9999;return 0;}
static int cam_req_mgr_create_session(struct cam_req_mgr_session_info *p) {assert(!held);creates++;p->session_hdl=1701;return driver_error;}
static int cam_req_mgr_destroy_session(struct cam_req_mgr_session_info *p,bool shut) {assert(!held && !shut);releases++;return rollback_error?rollback_error:driver_error;}
static int cam_req_mgr_link(struct cam_req_mgr_ver_info *p) {assert(!held && p->version==1);creates++;p->u.link_info_v1.link_hdl=3701;return driver_error;}
static int cam_req_mgr_link_v2(struct cam_req_mgr_ver_info *p) {assert(!held && p->version==2);creates++;p->u.link_info_v2.link_hdl=4701;return driver_error;}
static int cam_req_mgr_unlink(struct cam_req_mgr_unlink_info *p) {assert(!held);releases++;return rollback_error?rollback_error:driver_error;}
static int cam_mem_mgr_alloc_and_map(struct cam_mem_mgr_alloc_cmd *p) {assert(!held);creates++;p->out.buf_handle=1001;p->out.fd=17;return driver_error;}
static int cam_mem_mgr_map(struct cam_mem_mgr_map_cmd *p) {assert(!held);creates++;p->out.buf_handle=1002;return driver_error;}
static int cam_mem_mgr_release(struct cam_mem_mgr_release_cmd *p) {assert(!held);releases++;return rollback_error?rollback_error:driver_error;}
static int cam_sync_create(int32_t *key,const char *name) {assert(!held && name[63]==0);creates++;*key=2701;return driver_error;}
static int cam_sync_destroy(int32_t key) {assert(!held);releases++;return rollback_error?rollback_error:driver_error;}
static int pico_hub_subscribe_client_locked(struct pico_hub_client *c,const struct v4l2_event_subscription *s) {assert(held);return 0;}
static int pico_hub_unsubscribe_client_locked(struct pico_hub_client *c,const struct v4l2_event_subscription *s) {assert(held);return 0;}
static int cam_sync_handle_register_user_payload(struct cam_private_ioctl_arg *p) {return 17;}
static int cam_sync_handle_deregister_user_payload(struct cam_private_ioctl_arg *p) {return 18;}
static int cam_sync_handle_signal(struct cam_private_ioctl_arg *p) {return 19;}
static int cam_sync_handle_merge(struct cam_private_ioctl_arg *p) {return 20;}
static int cam_sync_handle_wait(struct cam_private_ioctl_arg *p) {p->result=42;return 0;}
#define VERSION_1 1
#define VERSION_2 2
'''

MAIN = r'''
static long native_crm(struct file *f,void *fh,bool prio,unsigned cmd,void *arg) {assert(!held && ioctl_locked && f==expected_file && fh==expected_fh && prio);callbacks++;return cam_private_ioctl(f,fh,prio,cmd,arg);}
static long native_sync(struct file *f,void *fh,bool prio,unsigned cmd,void *arg) {assert(!held && ioctl_locked && f==expected_file && fh==expected_fh && prio);callbacks++;return cam_sync_dev_ioctl(f,fh,prio,cmd,arg);}
static long dispatch(struct file *f,unsigned cmd,void *arg) {ioctl_locked=true;expected_fh=f->private_data;long rc=pico_hub_vidioc_default(f,f->private_data,true,cmd,arg);ioctl_locked=false;return rc;}
static int count(struct list_head *h) {int n=0;for(struct list_head *p=h->next;p!=h;p=p->next)n++;return n;}
int main(void) {
 struct video_device v[4]={{0}};v[0].entity.function=0x10000;v[2].entity.function=0x10100;
 const struct v4l2_ioctl_ops crm_ops={.vidioc_default=native_crm},sync_ops={.vidioc_default=native_sync};
 struct file original={.vdev=&v[0]},sync_original={.vdev=&v[2]};
 struct pico_hub_video crm={.original=&v[0],.shadow=&v[1],.multi_client=true,.original_ioctl_ops=&crm_ops,.shared_file=&original};
 struct pico_hub_video sync={.original=&v[2],.shadow=&v[3],.multi_client=true,.original_ioctl_ops=&sync_ops,.shared_file=&sync_original};
 struct pico_hub_client c={.fh={.vdev=&v[1]}},foreign={.fh={.vdev=&v[1]}},s={.fh={.vdev=&v[3]}};
 INIT_LIST_HEAD(&c.fh.subscribed);INIT_LIST_HEAD(&foreign.fh.subscribed);INIT_LIST_HEAD(&s.fh.subscribed);
 pico_hub_registry_lock();assert(!pico_hub_add_video_locked(&crm));assert(!pico_hub_add_video_locked(&sync));assert(!pico_hub_attach_client_locked(&crm,&c));assert(!pico_hub_attach_client_locked(&crm,&foreign));assert(!pico_hub_attach_client_locked(&sync,&s));pico_hub_registry_unlock();
 struct file f={.private_data=&c.fh,.vdev=&v[1]},other={.private_data=&foreign.fh,.vdev=&v[1]},sf={.private_data=&s.fh,.vdev=&v[3]};expected_file=&original;
 struct cam_mem_mgr_alloc_cmd alloc={.len=4096};struct cam_control ctrl={.op_code=CAM_REQ_MGR_ALLOC_BUF,.size=104,.handle=(uintptr_t)&alloc};
 fail_alloc=1;unsigned before=callbacks;assert(dispatch(&f,VIDIOC_CAM_CONTROL,&ctrl)==-ENOMEM);assert(callbacks==before);fail_alloc=0;
 fail_copy=1;assert(dispatch(&f,VIDIOC_CAM_CONTROL,&ctrl)==-EFAULT);fail_copy=0;assert(!count(&c.reserved_handles_40));
 driver_error=-EIO;assert(dispatch(&f,VIDIOC_CAM_CONTROL,&ctrl)==-EIO);driver_error=0;assert(!count(&c.reserved_handles_40));
 unsigned before_copies=copies;mutate_output=1;assert(!dispatch(&f,VIDIOC_CAM_CONTROL,&ctrl));mutate_output=0;assert(copies==before_copies+1 && alloc.out.buf_handle==9999);
 struct pico_hub_buffer_record *b=list_first_entry(&c.reserved_handles_40,struct pico_hub_buffer_record,list);assert(b->info.out.buf_handle==1001 && b->info.out.fd==17);
 struct cam_mem_mgr_release_cmd release={.buf_handle=1001};ctrl.op_code=CAM_REQ_MGR_RELEASE_BUF;ctrl.size=8;ctrl.handle=(uintptr_t)&release;
 before=releases;assert(dispatch(&other,VIDIOC_CAM_CONTROL,&ctrl)==-ENOENT);assert(releases==before && count(&c.reserved_handles_40)==1);
 driver_error=-EIO;assert(dispatch(&f,VIDIOC_CAM_CONTROL,&ctrl)==-EIO);assert(count(&c.reserved_handles_40)==1);driver_error=0;assert(!dispatch(&f,VIDIOC_CAM_CONTROL,&ctrl));
 /* Output failure immediately rolls back; failed rollback remains owned. */
 ctrl.op_code=CAM_REQ_MGR_ALLOC_BUF;ctrl.size=104;ctrl.handle=(uintptr_t)&alloc;fail_output=1;
 before=releases;assert(dispatch(&f,VIDIOC_CAM_CONTROL,&ctrl)==-EFAULT);assert(releases==before+1 && !count(&c.reserved_handles_40));
 rollback_error=-EBUSY;assert(dispatch(&f,VIDIOC_CAM_CONTROL,&ctrl)==-EFAULT);assert(count(&c.reserved_handles_40)==1);rollback_error=0;fail_output=0;
 ctrl.op_code=CAM_REQ_MGR_RELEASE_BUF;ctrl.size=8;ctrl.handle=(uintptr_t)&release;assert(!dispatch(&f,VIDIOC_CAM_CONTROL,&ctrl));
 struct cam_mem_mgr_map_cmd map={.fd=77,.out={.vaddr=888}};ctrl.op_code=CAM_REQ_MGR_MAP_BUF;ctrl.size=96;ctrl.handle=(uintptr_t)&map;assert(!dispatch(&f,VIDIOC_CAM_CONTROL,&ctrl));
 b=list_first_entry(&c.reserved_handles_40,struct pico_hub_buffer_record,list);assert(b->info.out.buf_handle==1002 && !b->info.out.fd && !b->info.out.vaddr);
 release.buf_handle=1002;ctrl.op_code=CAM_REQ_MGR_RELEASE_BUF;ctrl.size=8;ctrl.handle=(uintptr_t)&release;assert(!dispatch(&f,VIDIOC_CAM_CONTROL,&ctrl));
 struct cam_req_mgr_session_info session={0};ctrl.op_code=CAM_REQ_MGR_CREATE_SESSION;ctrl.size=8;ctrl.handle=(uintptr_t)&session;assert(!dispatch(&f,VIDIOC_CAM_CONTROL,&ctrl));assert(count(&c.session_handles)==1 && session.session_hdl==1701);
 for(int version=1;version<=2;version++) {
  struct cam_req_mgr_ver_info link={.version=version};link.u.link_info_v1.session_hdl=1701;
  ctrl.op_code=version==1?CAM_REQ_MGR_LINK:CAM_REQ_MGR_LINK_V2;ctrl.size=version==1?268:524;ctrl.handle=(uintptr_t)&link.u;
  assert(!dispatch(&f,VIDIOC_CAM_CONTROL,&ctrl));assert(count(&c.reserved_handles_56)==1);
  struct cam_req_mgr_unlink_info unlink={.session_hdl=1701,.link_hdl=version==1?3701:4701};ctrl.op_code=CAM_REQ_MGR_UNLINK;ctrl.size=8;ctrl.handle=(uintptr_t)&unlink;
  before=releases;unlink.session_hdl=99;assert(dispatch(&f,VIDIOC_CAM_CONTROL,&ctrl)==-ENOENT);assert(releases==before);unlink.session_hdl=1701;assert(!dispatch(&f,VIDIOC_CAM_CONTROL,&ctrl));
 }
 ctrl.op_code=CAM_REQ_MGR_DESTROY_SESSION;ctrl.size=8;ctrl.handle=(uintptr_t)&session;assert(!dispatch(&f,VIDIOC_CAM_CONTROL,&ctrl));
 /* Session destruction implicitly removes links in the real CRM core. */
 ctrl.op_code=CAM_REQ_MGR_CREATE_SESSION;assert(!dispatch(&f,VIDIOC_CAM_CONTROL,&ctrl));
 struct cam_req_mgr_link_info_v2 implicit={.session_hdl=1701};ctrl.op_code=CAM_REQ_MGR_LINK_V2;ctrl.size=524;ctrl.handle=(uintptr_t)&implicit;
 assert(!dispatch(&other,VIDIOC_CAM_CONTROL,&ctrl));assert(count(&foreign.reserved_handles_56)==1);
 ctrl.op_code=CAM_REQ_MGR_DESTROY_SESSION;ctrl.size=8;ctrl.handle=(uintptr_t)&session;assert(!dispatch(&f,VIDIOC_CAM_CONTROL,&ctrl));assert(!count(&foreign.reserved_handles_56));
 fail_output=1;ctrl.op_code=CAM_REQ_MGR_CREATE_SESSION;assert(dispatch(&f,VIDIOC_CAM_CONTROL,&ctrl)==-EFAULT);assert(!count(&c.session_handles));
 rollback_error=-EBUSY;assert(dispatch(&f,VIDIOC_CAM_CONTROL,&ctrl)==-EFAULT);assert(count(&c.session_handles)==1);rollback_error=0;fail_output=0;
 for(int version=1;version<=2;version++) {
  struct cam_req_mgr_ver_info link={.version=version};link.u.link_info_v1.session_hdl=1701;
  ctrl.op_code=version==1?CAM_REQ_MGR_LINK:CAM_REQ_MGR_LINK_V2;ctrl.size=version==1?268:524;ctrl.handle=(uintptr_t)&link.u;
  fail_output=1;assert(dispatch(&f,VIDIOC_CAM_CONTROL,&ctrl)==-EFAULT);assert(!count(&c.reserved_handles_56));
  rollback_error=-EBUSY;assert(dispatch(&f,VIDIOC_CAM_CONTROL,&ctrl)==-EFAULT);assert(count(&c.reserved_handles_56)==1);rollback_error=0;fail_output=0;
  struct cam_req_mgr_unlink_info unlink={.session_hdl=1701,.link_hdl=version==1?3701:4701};ctrl.op_code=CAM_REQ_MGR_UNLINK;ctrl.size=8;ctrl.handle=(uintptr_t)&unlink;assert(!dispatch(&f,VIDIOC_CAM_CONTROL,&ctrl));
 }
 ctrl.op_code=CAM_REQ_MGR_DESTROY_SESSION;ctrl.size=8;ctrl.handle=(uintptr_t)&session;assert(!dispatch(&f,VIDIOC_CAM_CONTROL,&ctrl));
 expected_file=&sync_original;struct cam_sync_info info={0};memset(info.name,'a',64);struct cam_private_ioctl_arg sc={.id=CAM_SYNC_CREATE,.size=68,.ioctl_ptr=(uintptr_t)&info};
 assert(!dispatch(&sf,VIDIOC_CAM_CONTROL,&sc));assert(count(&s.sync_handles)==1 && info.sync_obj==2701 && !info.name[63]);sc.id=CAM_SYNC_DESTROY;assert(!dispatch(&sf,VIDIOC_CAM_CONTROL,&sc));assert(!count(&s.sync_handles));
 sc.id=CAM_SYNC_CREATE;fail_output=1;assert(dispatch(&sf,VIDIOC_CAM_CONTROL,&sc)==-EFAULT);assert(!count(&s.sync_handles));fail_output=0;
 sc.id=CAM_SYNC_CREATE;fail_output=1;rollback_error=-EBUSY;assert(dispatch(&sf,VIDIOC_CAM_CONTROL,&sc)==-EFAULT);assert(count(&s.sync_handles)==1);
 rollback_error=0;fail_output=0;sc.id=CAM_SYNC_DESTROY;assert(!dispatch(&sf,VIDIOC_CAM_CONTROL,&sc));assert(!count(&s.sync_handles));
 sc.id=CAM_SYNC_WAIT;sc.result=0;assert(!dispatch(&sf,VIDIOC_CAM_CONTROL,&sc));assert(sc.result==42);
 /* Instrumented original driver without active hub dispatch stays native. */
 ctrl.op_code=CAM_REQ_MGR_ALLOC_BUF;ctrl.size=104;ctrl.handle=(uintptr_t)&alloc;
 assert(!cam_private_ioctl(&original,&foreign.fh,true,VIDIOC_CAM_CONTROL,&ctrl));assert(!count(&foreign.reserved_handles_40));
 release.buf_handle=1001;ctrl.op_code=CAM_REQ_MGR_RELEASE_BUF;ctrl.size=8;ctrl.handle=(uintptr_t)&release;
 assert(!cam_private_ioctl(&original,&foreign.fh,true,VIDIOC_CAM_CONTROL,&ctrl));assert(list_empty(&pico_hub_dispatches));
 assert(!pico_hub_complete_native_ioctl(&original,&c.fh,0x10000,CAM_REQ_MGR_ALLOC_BUF,NULL,0));
 struct v4l2_event_subscription sub={0};assert(!pico_hub_video_ioctl_ops.vidioc_subscribe_event(&c.fh,&sub));assert(!pico_hub_video_ioctl_ops.vidioc_unsubscribe_event(&c.fh,&sub));
 pico_hub_registry_lock();assert(!pico_hub_detach_client_locked(&c));assert(!pico_hub_detach_client_locked(&foreign));assert(!pico_hub_detach_client_locked(&s));assert(!pico_hub_remove_video_locked(&crm));assert(!pico_hub_remove_video_locked(&sync));pico_hub_registry_unlock();
 assert(allocated==freed);assert(list_empty(&pico_hub_dispatches));
 puts("PASS: actual tracked CRM cases/sync helpers through shared-file/client-FH dispatch, single user read and immutable result, preallocated ownership, foreign release rejection, native failure preservation, output-error rollback/retention, LINK1/2, MAP normalization and untracked sync result forwarding; no record leaks");
}
'''


def function(source, signature):
    start = source.index(signature)
    brace = source.index('{', start)
    depth = 1
    pos = brace + 1
    while depth:
        depth += (source[pos] == '{') - (source[pos] == '}')
        pos += 1
    return source[start:pos] + '\n'


def main():
    registry_test = load('test-pico-camera-hub-registry')
    event_test = load('test-pico-camera-hub-events')
    ioctl_test = load('test-pico-camera-hub-ioctl')
    prefix = registry_test.HARNESS.split('/* SOURCE */')[0]
    prefix = prefix.replace('struct video_device {int marker;};', 'struct video_device {int marker;struct {unsigned function;} entity;};')
    prefix = prefix.replace('int event_lock;', 'int event_lock;bool multi_client;struct mutex ioctl_lock;const struct v4l2_ioctl_ops *original_ioctl_ops;struct file *shared_file;')
    extra = event_test.EXTRA.split('/* BODIES */')[0].replace('assert(held);if(fail_alloc)', 'if(fail_alloc)').replace('assert(held);if(p)', 'if(p)')
    prefix += extra
    types = ioctl_test.MOCKS.split('static int fail_copy;')[0]
    source = event_test.BASE / 'source/phoenix-kernel-recovery'
    directory = event_test.DIRECTORY
    names = [directory + n for n in ['pico_camera_hub_registry.c', 'pico_camera_hub_events.c', 'pico_camera_hub_dispatch.c', 'pico_camera_hub_dispatch.h', 'pico_camera_hub.h', 'pico_camera_hub_ioctl.h', 'pico_camera_hub_resources.h']]
    crm_path = 'techpack/camera/drivers/cam_req_mgr/cam_req_mgr_dev.c'
    sync_path = 'techpack/camera/drivers/cam_sync/cam_sync.c'
    names += [crm_path, sync_path]
    registry, events, dispatch = [(source / n).read_text() for n in names[:3]]
    header = (source / (directory + 'pico_camera_hub_ioctl.h')).read_text()
    definitions = header[header.index('enum pico_hub_handle_action'):header.index('/* control is')]
    bodies = registry[registry.index('static DEFINE_MUTEX'):] + events[events.index('static bool pico_hub_client_attached_locked'):] + dispatch[dispatch.index('union pico_hub_owned_record {'):]
    crm = function((source / crm_path).read_text(), 'static long cam_private_ioctl(')
    selected = []
    for op in ['CREATE_SESSION', 'DESTROY_SESSION', 'LINK', 'LINK_V2', 'UNLINK', 'ALLOC_BUF', 'MAP_BUF', 'RELEASE_BUF']:
        start = crm.index('case CAM_REQ_MGR_' + op + ':')
        end = crm.find('\n\tcase ', start + 1)
        selected.append(crm[start:end])
    native_crm = crm[:crm.index('switch (k_ioctl->op_code)')] + 'switch(k_ioctl->op_code) {\n' + '\n'.join(selected) + '\ndefault:return -ENOIOCTLCMD;\n}\nreturn rc;\n}\n'
    sync = (source / sync_path).read_text()
    native_sync = ''.join(function(sync, signature) for signature in ['static int cam_sync_handle_create(', 'static int cam_sync_handle_destroy(', 'static long cam_sync_dev_ioctl('])
    code = prefix + types + SUPPORT + definitions + bodies + native_crm + native_sync + MAIN
    out = event_test.BASE / 'out/phoenix-kernel-recovery/camera-hub-dispatch-tests'
    out.mkdir(exist_ok=True)
    (out / 'harness.c').write_text(code)
    subprocess.run(['gcc', '-std=gnu11', '-g', '-O1', '-pthread', '-fsanitize=address,undefined', '-fno-omit-frame-pointer', str(out / 'harness.c'), '-o', str(out / 'test')], check=True)
    result = subprocess.run([str(out / 'test')], capture_output=True, text=True, timeout=30)
    report = {'sources': {n: hashlib.sha256((source / n).read_bytes()).hexdigest() for n in names}, 'harness_sha256': hashlib.sha256(code.encode()).hexdigest(), 'exit_code': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr, 'sanitizers': ['AddressSanitizer', 'UndefinedBehaviorSanitizer'], 'scope': 'Actual dispatch, registry/event, selected verbatim CRM ioctl cases and sync create/destroy/dev-ioctl bodies; underlying hardware/V4L2 and remaining sync handlers mocked', 'device_modified': False}
    (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    raise SystemExit(result.returncode)


if __name__ == '__main__':
    main()
