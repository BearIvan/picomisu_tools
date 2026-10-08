"""Exercise actual registration/unregister code with V4L2 refcount mocks."""
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
#include <stdint.h>
#include <string.h>
typedef uint32_t u32;
#define GFP_KERNEL 0
#define VFL_TYPE_GRABBER 0
struct media_device {char model[32],bus_info[32];bool registered;struct device *dev;};
struct v4l2_device {struct media_device *mdev;void (*release)(struct v4l2_device *);unsigned refs;char name[64];bool registered;};
struct v4l2_file_operations {int marker;};struct v4l2_ioctl_ops {int marker;};
static const struct v4l2_file_operations native_fops={1},pico_hub_video_fops={2};
static const struct v4l2_ioctl_ops native_ioctl={1},pico_hub_video_ioctl_ops={2};
static int fail_stage,media_live,root_live,video_live,owned_live;
static unsigned allocated,freed;
static bool runtime_busy;
static void *kzalloc(size_t size,int flags) {if(fail_stage==1)return NULL;void *p=calloc(1,size);assert(p);allocated++;return p;}
static void kfree(void *p) {if(p){freed++;free(p);}}
static size_t strlcpy(char *dst,const char *src,size_t n) {size_t len=strlen(src);snprintf(dst,n,"%s",src);return len;}
static void media_device_init(struct media_device *m) {memset(m,0,sizeof(*m));}
static int media_device_register(struct media_device *m) {bool hub=!strcmp(m->model,"pico_device_hub");if(fail_stage==(hub?3:12))return -EIO;assert(!m->registered);m->registered=true;media_live++;return 0;}
static void media_device_unregister(struct media_device *m) {assert(m->registered);m->registered=false;media_live--;}
static void media_device_cleanup(struct media_device *m) {assert(!m->registered);}
static int v4l2_device_register(struct device *d,struct v4l2_device *v) {if(!d)assert(v->name[0]);if(fail_stage==(d?10:4))return -EIO;v->refs=1;v->registered=true;return 0;}
static int v4l2_device_set_name(struct v4l2_device *v,const char *s,int *instance) {int index=(*instance)++;snprintf(v->name,sizeof(v->name),"%s%d",s,index);return index;}
static void v4l2_device_unregister(struct v4l2_device *v) {assert(v->registered);v->registered=false;}
static void v4l2_device_put(struct v4l2_device *v) {assert(v->refs);if(!--v->refs && v->release)v->release(v);}
static void video_device_release(struct video_device *v) {assert(!v->dev.refs);video_live--;kfree(v);}
static struct video_device *video_device_alloc(void) {if(fail_stage==2)return NULL;struct video_device *v=kzalloc(sizeof(*v),0);if(!v)return NULL;video_live++;v->dev.owner=v;v->release=video_device_release;return v;}
static bool video_is_registered(struct video_device *v) {return v->registered;}
static void get_device(struct device *d) {assert(d->refs);d->refs++;}
static void put_device(struct device *d) {assert(d->refs);if(!--d->refs){struct video_device *v=d->owner;struct v4l2_device *root=v->v4l2_dev;v->release(v);if(root->release)v4l2_device_put(root);}}
static bool defer_native;static struct video_device *native_original;static struct device *deferred_shadow,*deferred_original;
static int video_register_device(struct video_device *v,int type,int nr) {assert(type==0 && nr==-1 && v->v4l2_dev && v->release && v->fops==&pico_hub_video_fops && v->ioctl_ops==&pico_hub_video_ioctl_ops && v->lock);bool shadow=!strncmp(v->name,"hub_",4);if(fail_stage==(shadow?8:7))return -EIO;v->registered=true;v->entity.function=0x10001;v->dev.refs=1;v->v4l2_dev->refs++;if(!strcmp(v->name,"cam_sync"))native_original=v;if(defer_native && shadow){deferred_shadow=&v->dev;deferred_original=&native_original->dev;get_device(deferred_shadow);get_device(deferred_original);}return 0;}
static void video_unregister_device(struct video_device *v) {assert(v->registered);v->registered=false;put_device(&v->dev);}
static const char *video_device_node_name(struct video_device *v) {return v->name;}
struct mock_runtime {bool ready;};
static int pico_hub_video_runtime_init(struct pico_hub_video *p) {if(fail_stage==6)return -ENOMEM;struct mock_runtime *r=kzalloc(sizeof(*r),0);assert(r);p->reserved_224=r;return 0;}
static int pico_hub_video_runtime_activate(struct pico_hub_video *p) {if(!p||!p->reserved_224)return -ENOENT;((struct mock_runtime *)p->reserved_224)->ready=true;return 0;}
static int pico_hub_video_runtime_stop(struct pico_hub_video *p) {if(runtime_busy)return -EBUSY;assert(p->reserved_224);kfree(p->reserved_224);p->reserved_224=NULL;return 0;}
static void cond_resched(void) {runtime_busy=false;}
'''

NATIVE_SUPPORT = r'''
#define CAM_SYNC_MAX_OBJS 4
#define CAM_SYNC_NAME "cam_sync"
#define CAM_SYNC_DEVICE_NAME "cam_sync"
#define CAM_SYNC_DEVICE_TYPE 0x10100
#define CAM_SYNC_WORKQUEUE_NAME "cam-sync"
#define WQ_HIGHPRI 1
#define WQ_UNBOUND 2
#define CAM_SYNC 0
#define CAM_ERR(...) ((void)0)
struct platform_device {struct device dev;};
struct workqueue_struct {int marker;};
struct sync_device {struct mutex table_lock;int cam_sync_eventq_lock,row_spinlocks[4];struct video_device *vdev;struct v4l2_device v4l2_dev;int sync_table[16];uint64_t bitmap[1];struct workqueue_struct *work_queue;void *dentry;};
static struct sync_device *sync_dev;static bool trigger_cb_without_switch;
static void mutex_init(struct mutex *m) {assert(!pthread_mutex_init(&m->value,NULL));}
static void mutex_destroy(struct mutex *m) {assert(!pthread_mutex_destroy(&m->value));}
static void bitmap_zero(uint64_t *p,int n) {*p=0;}
static void set_bit(int n,uint64_t *p) {*p|=1ULL<<n;}
static int media_entity_pads_init(void *e,int n,void *p) {assert(e && n==0 && !p);return fail_stage==13?-EIO:0;}
static void media_entity_cleanup(void *e) {assert(e);}
static void video_set_drvdata(struct video_device *v,void *p) {assert(v && p);}
static struct workqueue_struct *alloc_workqueue(const char *s,int flags,int n) {if(fail_stage==11)return NULL;return kzalloc(sizeof(struct workqueue_struct),0);}
static void destroy_workqueue(struct workqueue_struct *q) {assert(q);kfree(q);}
static int cam_sync_create_debugfs(void) {return 0;}
static void debugfs_remove_recursive(void *p) {(void)p;}
#define cam_sync_v4l2_fops native_fops
#define g_cam_sync_ioctl_ops native_ioctl
'''

CRM_SUPPORT = r'''
#define CAM_VNODE_DEVICE_TYPE 0x10000
#define CAM_REQ_MGR_VNODE_NAME "cam-req-mgr"
#define CAM_CRM 0
#define CAM_DBG(...) ((void)0)
#define SLAB_CONSISTENCY_CHECKS 1
#define SLAB_RED_ZONE 2
#define SLAB_POISON 4
#define SLAB_STORE_USER 8
struct cam_req_mgr_timer {int marker;};struct kmem_cache {int marker;};
static struct kmem_cache timer_cache,*g_cam_req_mgr_timer_cachep;
static struct kmem_cache *kmem_cache_create(const char *s,size_t n,int a,int flags,void *ctor) {return &timer_cache;}
struct crm_device {struct video_device *video;struct v4l2_device *v4l2_dev;int open_cnt,cam_eventq_lock;bool subdev_nodes_created,state;struct mutex cam_lock,dev_lock;};
static struct crm_device g_dev;static bool util_started,core_started;
static int cam_req_mgr_util_init(void) {if(fail_stage==15)return -EIO;util_started=true;return 0;}
static void cam_req_mgr_util_deinit(void) {assert(util_started);util_started=false;}
static int cam_req_mgr_core_device_init(void) {if(fail_stage==14)return -EIO;core_started=true;return 0;}
static void cam_req_mgr_core_device_deinit(void) {assert(core_started);core_started=false;}
#define g_cam_fops native_fops
#define g_cam_ioctl_ops native_ioctl
'''

MAIN = r'''
static void root_release(struct v4l2_device *v) {root_live--;kfree(v);}
static struct video_device *new_original(u32 entity,struct v4l2_device **root) {
 fail_stage=0;*root=kzalloc(sizeof(**root),0);(*root)->refs=1;(*root)->release=root_release;root_live++;
 struct video_device *v=video_device_alloc();assert(v);v->v4l2_dev=*root;v->fops=&native_fops;v->ioctl_ops=&native_ioctl;
 snprintf(v->name,sizeof(v->name),"%s",entity==0x10000?"cam-req-mgr":"cam_sync");return v;
}
static struct pico_hub_video *find(struct video_device *v) {pico_hub_registry_lock();struct pico_hub_video *p=pico_hub_find_video_locked(v,false);pico_hub_registry_unlock();return p;}
int main(void) {
 assert(pico_hub_register_video_device(NULL,0x10000)==-EINVAL);
 for(int stage=1;stage<=8;stage++) {
  struct v4l2_device *root;struct video_device *v=new_original(0x10000,&root);fail_stage=stage;
  assert(pico_hub_register_video_device(v,0x10000)<0);fail_stage=0;v4l2_device_put(root);
  assert(!video_live && !root_live && !media_live && !pico_hub_media_users);assert(list_empty(&pico_hub_videos));assert(allocated==freed);
 }
 struct v4l2_device *root;struct video_device *v=new_original(0x10000,&root);
 assert(!pico_hub_register_video_device(v,0x10000));struct pico_hub_video *p=find(v);assert(p && p->shadow && p->v4l2_dev);
 assert(p->original_fops==&native_fops && p->original_ioctl_ops==&native_ioctl);assert(!strcmp(p->shadow->name,"hub_cam-req-mgr"));
 assert(!strcmp(p->v4l2_dev->name,"hub_cam-req-mgr0"));
 assert(v->entity.function==0x10000 && p->shadow->entity.function==0x10000);assert(!((struct mock_runtime *)p->reserved_224)->ready);
 assert(!pico_hub_activate_video_device(v));assert(((struct mock_runtime *)p->reserved_224)->ready);
 assert(pico_hub_register_video_device(v,0x10000)==-EINVAL);assert(find(v)==p);
 runtime_busy=true;assert(pico_hub_unregister_video_device(v)==-EBUSY);assert(v->registered && p->shadow->registered && find(v)==p);runtime_busy=false;
 /* In-flight generic failed opens retain device refs after unregister. */
 struct device *shadow_ref=&p->shadow->dev,*original_ref=&v->dev;get_device(shadow_ref);get_device(original_ref);
 assert(!pico_hub_unregister_video_device(v));assert(!list_empty(&pico_hub_videos)==false);assert(media_live==1 && pico_hub_media_users==1 && root_live==1 && video_live==2);
 v4l2_device_put(root);assert(root_live==1);put_device(shadow_ref);assert(!media_live && !pico_hub_media_users && video_live==1 && root_live==1);
 put_device(original_ref);assert(!root_live && !video_live && allocated==freed);
 /* Shared media lifetime is independent of either original driver. */
 struct v4l2_device *roots[2];struct video_device *nodes[2];
 nodes[0]=new_original(0x10000,&roots[0]);assert(!pico_hub_register_video_device(nodes[0],0x10000));
 nodes[1]=new_original(0x10100,&roots[1]);assert(!pico_hub_register_video_device(nodes[1],0x10100));assert(media_live==1 && pico_hub_media_users==2);
 assert(!strcmp(find(nodes[1])->shadow->name,"hub_cam_sync"));assert(!pico_hub_unregister_video_device(nodes[0]));v4l2_device_put(roots[0]);assert(media_live==1 && pico_hub_media_users==1);
 assert(!pico_hub_unregister_video_device(nodes[1]));v4l2_device_put(roots[1]);assert(!media_live && !root_live && !video_live && !pico_hub_media_users);assert(allocated==freed);
 /* Actual native sync probe/remove with modeled underlying kernel APIs. */
 struct platform_device platform={0};
 for(int stage=1;stage<=13;stage++) {
  if(stage==9)continue;fail_stage=stage;assert(cam_sync_probe(&platform)<0);fail_stage=0;
  assert(!sync_dev && !media_live && !video_live && !pico_hub_media_users);assert(allocated==freed);
 }
 assert(!cam_sync_probe(&platform));assert(sync_dev && media_live==2);assert(!cam_sync_remove(&platform));assert(!sync_dev && !media_live && !video_live && allocated==freed);
 fail_stage=11;defer_native=true;assert(cam_sync_probe(&platform)==-ENOMEM);fail_stage=0;defer_native=false;
 assert(!sync_dev && allocated>freed && video_live==2 && media_live==1);
 put_device(deferred_shadow);assert(video_live==1 && !media_live && allocated>freed);
 put_device(deferred_original);assert(!video_live && allocated==freed);
 for(int stage=1;stage<=15;stage++) {
  if(stage==9||stage==11)continue;memset(&g_dev,0,sizeof(g_dev));fail_stage=stage;
  assert(cam_req_mgr_probe(&platform)<0);fail_stage=0;
  assert(!g_dev.video && !g_dev.v4l2_dev && !media_live && !video_live && !pico_hub_media_users && !core_started && !util_started);assert(allocated==freed);
 }
 memset(&g_dev,0,sizeof(g_dev));assert(!cam_req_mgr_probe(&platform));assert(g_dev.state && core_started && util_started && media_live==2);
 assert(!cam_req_mgr_remove(&platform));assert(!g_dev.state && !g_dev.video && !g_dev.v4l2_dev && !core_started && !util_started && !media_live && !video_live && allocated==freed);
 puts("PASS: actual registration with eight failure stages, gate/ops identity, busy/deferred unregister and shared media lifetime; actual native sync/CRM media/probe/remove through allocation, registration, workqueue/core/util failures and deferred failed-open refs; no owned allocation leaks");
}
'''


def main():
    common = load('test-pico-camera-hub-registry')
    prefix = common.HARNESS.split('/* SOURCE */')[0]
    prefix = prefix.replace('struct video_device {int marker;};', 'struct video_device;struct device {unsigned refs;struct video_device *owner;};struct video_device {bool registered;int minor,vfl_type;char name[32];struct device dev;struct {unsigned function;const char *name;} entity;const struct v4l2_file_operations *fops;const struct v4l2_ioctl_ops *ioctl_ops;struct mutex *lock;struct v4l2_device *v4l2_dev;void (*release)(struct video_device *);};')
    prefix = prefix.replace('int event_lock;', 'int event_lock;int instance;bool multi_client;struct mutex ioctl_lock;struct v4l2_device *v4l2_dev;const struct v4l2_file_operations *original_fops;const struct v4l2_ioctl_ops *original_ioctl_ops;')
    prefix = prefix.replace('static void mutex_lock(struct mutex *m) {assert(!held);assert(!pthread_mutex_lock(&m->value));held++;}', 'static struct mutex pico_hub_registry_mutex;static void mutex_lock(struct mutex *m) {if(m==&pico_hub_registry_mutex)assert(!held);assert(!pthread_mutex_lock(&m->value));if(m==&pico_hub_registry_mutex)held++;}')
    prefix = prefix.replace('static void mutex_unlock(struct mutex *m) {assert(held==1);held--;assert(!pthread_mutex_unlock(&m->value));}', 'static void mutex_unlock(struct mutex *m) {if(m==&pico_hub_registry_mutex){assert(held==1);held--;}assert(!pthread_mutex_unlock(&m->value));}')
    base = Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro')
    source = base / 'source/phoenix-kernel-recovery'
    directory = 'techpack/camera/drivers/cam_core/'
    names = [directory + n for n in ['pico_camera_hub_registry.c', 'pico_camera_hub_registration.c', 'pico_camera_hub_registration.h', 'pico_camera_hub_fops.h', 'pico_camera_hub.h']]
    registry, registration = [(source / n).read_text() for n in names[:2]]
    registry = registry[registry.index('static DEFINE_MUTEX'):].replace('int pico_hub_add_video_locked(', 'int real_pico_hub_add_video_locked(')
    wrapper = 'int pico_hub_add_video_locked(struct pico_hub_video *p) {return fail_stage==5?-EIO:real_pico_hub_add_video_locked(p);}\n'
    sync_name = 'techpack/camera/drivers/cam_sync/cam_sync.c'
    names.append(sync_name)
    sync = (source / sync_name).read_text()
    parse = load('test-pico-camera-hub-dispatch').function
    native = ''.join(parse(sync, signature) for signature in ['static int cam_sync_media_controller_init(', 'static void cam_sync_media_controller_cleanup(', 'static void cam_sync_init_entity(', 'static void cam_sync_v4l2_release(', 'static int cam_sync_probe(', 'static int cam_sync_remove('])
    crm_name = 'techpack/camera/drivers/cam_req_mgr/cam_req_mgr_dev.c'
    names.append(crm_name)
    crm = (source / crm_name).read_text()
    native_crm = ''.join(parse(crm, signature) for signature in ['static int cam_media_device_setup(', 'static void cam_media_device_cleanup(', 'static void cam_v4l2_device_release(', 'static int cam_v4l2_device_setup(', 'static void cam_v4l2_device_cleanup(', 'static int cam_video_device_setup(', 'void cam_video_device_cleanup(', 'static int cam_req_mgr_remove(', 'static int cam_req_mgr_probe('])
    code = prefix + MOCKS + registry + wrapper + registration[registration.index('struct pico_hub_registration {'):] + NATIVE_SUPPORT + native + CRM_SUPPORT + native_crm + MAIN
    out = base / 'out/phoenix-kernel-recovery/camera-hub-registration-tests'
    out.mkdir(exist_ok=True)
    (out / 'harness.c').write_text(code)
    subprocess.run(['gcc', '-std=gnu11', '-g', '-O1', '-pthread', '-fsanitize=address,undefined', '-fno-omit-frame-pointer', str(out / 'harness.c'), '-o', str(out / 'test')], check=True)
    result = subprocess.run([str(out / 'test')], capture_output=True, text=True, timeout=30)
    report = {'sources': {n: hashlib.sha256((source / n).read_bytes()).hexdigest() for n in names}, 'harness_sha256': hashlib.sha256(code.encode()).hexdigest(), 'exit_code': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr, 'sanitizers': ['AddressSanitizer', 'UndefinedBehaviorSanitizer'], 'scope': 'Actual registration/registry and native sync/CRM media/probe/remove/release functions; modeled kernel V4L2/media/device refs, workqueue, runtime/core/util APIs; no physical driver probe execution', 'device_modified': False}
    (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    raise SystemExit(result.returncode)


if __name__ == '__main__':
    main()
