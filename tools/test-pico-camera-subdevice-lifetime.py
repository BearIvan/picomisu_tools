"""Test owned mirrors, media attachment, relay pins and concurrent destruction."""
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
#define GFP_KERNEL 0
#define CONFIG_COMPAT 1
#define THIS_MODULE NULL
#define V4L2_SUBDEV_FL_HAS_DEVNODE 4
#define pico_hub_check_factory_layouts() ((void)0)
static unsigned allocated,freed;static int fail_alloc;
static void *kzalloc(size_t n,int flags) {if(fail_alloc)return NULL;void *p=calloc(1,n);assert(p);allocated++;return p;}
static void kfree(void *p) {if(p){freed++;free(p);}}
struct module {_Atomic unsigned refs;bool live;};
static bool try_module_get(struct module *m) {if(!m)return true;if(!m->live)return false;atomic_fetch_add(&m->refs,1);return true;}
static void module_put(struct module *m) {if(m)assert(atomic_fetch_sub(&m->refs,1)>0);}
struct kref {_Atomic unsigned count;};
static void kref_init(struct kref *r) {atomic_store(&r->count,1);}
static void kref_get(struct kref *r) {assert(atomic_fetch_add(&r->count,1)>0);}
static unsigned kref_read(const struct kref *r) {return atomic_load(&r->count);}
static int kref_put(struct kref *r,void (*fn)(struct kref *)) {unsigned old=atomic_fetch_sub(&r->count,1);assert(old);if(old==1){fn(r);return 1;}return 0;}
static void v4l2_subdev_init(struct v4l2_subdev *sd,const struct v4l2_subdev_ops *ops) {memset(sd,0,sizeof(*sd));sd->ops=ops;}
static void v4l2_set_subdevdata(struct v4l2_subdev *sd,void *p) {sd->dev_priv=p;}
static void *v4l2_get_subdevdata(struct v4l2_subdev *sd) {return sd->dev_priv;}
static size_t strlcpy(char *d,const char *s,size_t n) {size_t len=strlen(s);snprintf(d,n,"%s",s);return len;}
struct v4l2_device {_Atomic unsigned refs;};
static unsigned pads_live,registered_live;static int fail_pads,fail_register;
static pthread_mutex_t reg_gate=PTHREAD_MUTEX_INITIALIZER;static pthread_cond_t reg_signal=PTHREAD_COND_INITIALIZER;
static bool reg_block,reg_entered,reg_allow;
static int media_entity_pads_init(struct media_entity *e,unsigned n,void *pads) {assert(!n&&!pads);if(fail_pads)return -ENOMEM;assert(!e->initialized);e->initialized=true;pads_live++;return 0;}
static void media_entity_cleanup(struct media_entity *e) {assert(e->initialized && pads_live);e->initialized=false;pads_live--;}
static void v4l2_device_get(struct v4l2_device *v) {assert(atomic_fetch_add(&v->refs,1));}
static void v4l2_device_put(struct v4l2_device *v) {assert(atomic_fetch_sub(&v->refs,1)>1);}
static int v4l2_device_register_subdev(struct v4l2_device *v,struct v4l2_subdev *sd) {
 assert(!held && !sd->v4l2_dev && sd->entity.initialized);
 pthread_mutex_lock(&reg_gate);reg_entered=true;pthread_cond_broadcast(&reg_signal);while(reg_block&&!reg_allow)pthread_cond_wait(&reg_signal,&reg_gate);pthread_mutex_unlock(&reg_gate);
 if(fail_register)return -EIO;sd->v4l2_dev=v;registered_live++;return 0;
}
static void v4l2_device_unregister_subdev(struct v4l2_subdev *sd) {assert(!held && sd->v4l2_dev && !sd->devnode && registered_live);sd->v4l2_dev=NULL;registered_live--;}
extern const struct v4l2_subdev_ops pico_hub_shadow_subdev_ops;
static bool pico_hub_subdevice_relay_busy_locked(struct pico_hub_subdevice *e);
static bool pico_hub_subdevice_detach_ready_locked(struct pico_hub_subdevice *e);
'''

MAIN = r'''
static pthread_mutex_t gate=PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t signal=PTHREAD_COND_INITIALIZER;
static bool block,entered,allow;static unsigned calls;
static struct v4l2_subdev *expected,*invoke_shadow;static struct module owner={.live=true};
static int packet=42;static long native_result=0x100000007L;
static long native(struct v4l2_subdev *sd,unsigned cmd,void *arg) {assert(!held && sd==expected && cmd==0x1234 && arg==&packet);assert(atomic_load(&owner.refs)==1);calls++;pthread_mutex_lock(&gate);entered=true;pthread_cond_broadcast(&signal);while(block&&!allow)pthread_cond_wait(&signal,&gate);pthread_mutex_unlock(&gate);return native_result;}
static void *invoke(void *unused) {assert(v4l2_subdevice_ioctl(invoke_shadow,0x1234,&packet)==7);return NULL;}
static void *attach(void *unused) {assert(!pico_hub_register_prepared_subdevice(invoke_shadow));return NULL;}
int main(void) {
 struct video_device nodes[2]={{0}};struct pico_hub_video parent={.original=&nodes[0],.shadow=&nodes[1]};
 struct v4l2_subdev_core_ops core={.ioctl=native};struct v4l2_subdev_ops ops={.core=&core};
 struct v4l2_subdev original={.ops=&ops,.owner=&owner,.flags=12,.entity={.function=0x10003}};snprintf(original.name,sizeof(original.name),"cam-isp");expected=&original;
 struct v4l2_subdev *shadow=(void *)1;
 assert(pico_hub_prepare_subdevice(NULL,&original,&shadow)==-EINVAL);assert(pico_hub_destroy_prepared_subdevice(NULL)==-ENOENT);
 pico_hub_registry_lock();assert(!pico_hub_add_video_locked(&parent));pico_hub_registry_unlock();
 fail_alloc=1;assert(pico_hub_prepare_subdevice(&parent,&original,&shadow)==-ENOMEM && !shadow);fail_alloc=0;
 fail_pads=1;assert(pico_hub_prepare_subdevice(&parent,&original,&shadow)==-ENOMEM && !shadow);fail_pads=0;
 assert(!pico_hub_prepare_subdevice(&parent,&original,&shadow));assert(shadow && shadow!=&original && shadow->ops==&pico_hub_shadow_subdev_ops && !strcmp(shadow->name,"cam-isp") && shadow->flags==12 && shadow->entity.function==0x10003);
 struct v4l2_subdev *duplicate=NULL;assert(pico_hub_prepare_subdevice(&parent,&original,&duplicate)==-EEXIST && !duplicate);
 struct pico_hub_subdevice *entry=shadow->dev_priv;pico_hub_registry_lock();assert(pico_hub_remove_subdevice_locked(&parent,entry)==-EBUSY);assert(pico_hub_remove_video_locked(&parent)==-EBUSY);pico_hub_registry_unlock();
 assert(v4l2_subdevice_ioctl(shadow,0x1234,&packet)==7);assert(v4l2_subdevice_compat_ioctl(shadow,0x1234,(unsigned long)&packet)==7);assert(!atomic_load(&owner.refs));
 owner.live=false;unsigned before=calls;assert(v4l2_subdevice_ioctl(shadow,0x1234,&packet)==-ENODEV && calls==before);owner.live=true;
 core.ioctl=NULL;assert(v4l2_subdevice_ioctl(shadow,0x1234,&packet)==-1 && !atomic_load(&owner.refs));core.ioctl=native;
 block=true;allow=false;entered=false;invoke_shadow=shadow;pthread_t caller;assert(!pthread_create(&caller,NULL,invoke,NULL));pthread_mutex_lock(&gate);while(!entered)pthread_cond_wait(&signal,&gate);pthread_mutex_unlock(&gate);
 assert(pico_hub_destroy_prepared_subdevice(shadow)==-EBUSY);assert(atomic_load(&owner.refs)==1);assert(v4l2_subdevice_ioctl(shadow,0x1234,&packet)==-ENODEV);
 pico_hub_registry_lock();assert(pico_hub_remove_subdevice_locked(&parent,entry)==-EBUSY);pico_hub_registry_unlock();
 pthread_mutex_lock(&gate);allow=true;pthread_cond_broadcast(&signal);pthread_mutex_unlock(&gate);assert(!pthread_join(caller,NULL));assert(!atomic_load(&owner.refs));assert(!pico_hub_destroy_prepared_subdevice(shadow));block=false;
 original.entity.function=0x10001;assert(!pico_hub_prepare_subdevice(&parent,&original,&shadow));assert(shadow->flags==8 && shadow->entity.function==0x10001);
 shadow->devnode=&nodes[0];assert(pico_hub_destroy_prepared_subdevice(shadow)==-EBUSY);shadow->devnode=NULL;assert(!pico_hub_destroy_prepared_subdevice(shadow));
 original.entity.function=0x10003;assert(!pico_hub_prepare_subdevice(&parent,&original,&shadow));shadow->v4l2_dev=(void *)1;assert(pico_hub_destroy_prepared_subdevice(shadow)==-EBUSY);shadow->v4l2_dev=NULL;assert(!pico_hub_destroy_prepared_subdevice(shadow));
 struct v4l2_device target={.refs=1};
 assert(pico_hub_register_prepared_subdevice(NULL)==-ENOENT);
 assert(!pico_hub_prepare_subdevice(&parent,&original,&shadow));assert(pico_hub_register_prepared_subdevice(shadow)==-EINVAL);parent.v4l2_dev=&target;
 fail_register=1;assert(pico_hub_register_prepared_subdevice(shadow)==-EIO && !shadow->v4l2_dev && atomic_load(&target.refs)==1);fail_register=0;
 assert(!pico_hub_register_prepared_subdevice(shadow));assert(shadow->v4l2_dev==&target && !shadow->devnode && shadow->flags==12 && atomic_load(&target.refs)==2);assert(pico_hub_register_prepared_subdevice(shadow)==-EBUSY);assert(!pico_hub_destroy_prepared_subdevice(shadow));assert(atomic_load(&target.refs)==1 && !registered_live);
 assert(!pico_hub_prepare_subdevice(&parent,&original,&shadow));invoke_shadow=shadow;reg_block=true;reg_entered=false;reg_allow=false;assert(!pthread_create(&caller,NULL,attach,NULL));pthread_mutex_lock(&reg_gate);while(!reg_entered)pthread_cond_wait(&reg_signal,&reg_gate);pthread_mutex_unlock(&reg_gate);
 assert(pico_hub_register_prepared_subdevice(shadow)==-EBUSY);assert(pico_hub_destroy_prepared_subdevice(shadow)==-EBUSY);assert(pico_hub_register_prepared_subdevice(shadow)==-ENODEV);
 pthread_mutex_lock(&reg_gate);reg_allow=true;pthread_cond_broadcast(&reg_signal);pthread_mutex_unlock(&reg_gate);assert(!pthread_join(caller,NULL));assert(!pico_hub_destroy_prepared_subdevice(shadow));assert(atomic_load(&target.refs)==1 && !registered_live && !pads_live);
 pico_hub_registry_lock();assert(!pico_hub_remove_video_locked(&parent));pico_hub_registry_unlock();assert(list_empty(&pico_hub_owned_subdevices) && allocated==freed);
 puts("PASS: owned subdevice prepare/duplicate/ENOMEM/pads failure, factory flags/name/entity, relay/module pins, closing gate and blocked callback vs destroy, managed V4L2 registration/error/retry/duplicate, parent refs, blocked registration vs destroy, devnode refusal and exact media/context frees");
}
'''


def main():
    common = load('test-pico-camera-hub-registry')
    prefix = common.HARNESS.split('/* OWNED_SUBDEVICE_MOCKS */')[0]
    prefix = prefix.replace('struct video_device {int marker;};', 'struct video_device {int marker;const struct v4l2_file_operations *fops;};')
    prefix = prefix.replace('void *reserved_224;', 'void *reserved_224;struct v4l2_device *v4l2_dev;')
    types = 'struct v4l2_subdev;struct module;struct v4l2_subdev_core_ops {long (*ioctl)(struct v4l2_subdev *,unsigned,void *);long (*compat_ioctl32)(struct v4l2_subdev *,unsigned,unsigned long);};struct v4l2_subdev_ops {const struct v4l2_subdev_core_ops *core;};struct v4l2_subdev {int marker;const struct v4l2_subdev_ops *ops;struct module *owner;unsigned flags;char name[32];struct {unsigned function;} entity;void *dev_priv,*v4l2_dev;struct video_device *devnode;};'
    prefix = prefix.replace('struct v4l2_subdev {int marker;};', types)
    prefix = prefix.replace('struct {unsigned function;} entity;', 'struct media_entity {unsigned function;bool initialized;} entity;')
    base = Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro')
    source = base / 'source/phoenix-kernel-recovery'
    d = 'techpack/camera/drivers/cam_core/'
    names = [d + n for n in ['pico_camera_hub_registry.c', 'pico_camera_hub_subdevice.c', 'pico_camera_hub.c', 'pico_camera_hub_subdevice.h', 'pico_camera_hub.h']]
    registry, owned, relay = [(source / n).read_text() for n in names[:3]]
    # Native kernel declarations are extern; same here for the registry hooks.
    mocks = MOCKS.replace('static bool pico_hub_subdevice_', 'bool pico_hub_subdevice_')
    bodies = registry[registry.index('static DEFINE_MUTEX'):] + owned[owned.index('struct pico_hub_owned_subdevice {'):] + relay[relay.index('long v4l2_subdevice_ioctl('):]
    code = '#include <string.h>\n' + prefix + '\n#define list_del list_del_init\n' + mocks + bodies + MAIN
    out = base / 'out/phoenix-kernel-recovery/camera-subdevice-lifetime-tests'
    out.mkdir(exist_ok=True)
    (out / 'harness.c').write_text(code)
    subprocess.run(['gcc', '-std=gnu11', '-g', '-O1', '-pthread', '-fsanitize=address,undefined', '-fno-omit-frame-pointer', str(out / 'harness.c'), '-o', str(out / 'test')], check=True)
    result = subprocess.run([str(out / 'test')], capture_output=True, text=True, timeout=30)
    report = {'sources': {n: hashlib.sha256((source / n).read_bytes()).hexdigest() for n in names}, 'harness_sha256': hashlib.sha256(code.encode()).hexdigest(), 'exit_code': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr, 'sanitizers': ['AddressSanitizer', 'UndefinedBehaviorSanitizer'], 'scope': 'Actual owned prepare/register/destroy/relay/ref/closing/registry functions; pthread blocked native callback and registration; modeled media pads and V4L2 registration APIs with fault injection, module/kref mocks; no real devnodes or hardware', 'device_modified': False}
    (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    raise SystemExit(result.returncode)


if __name__ == '__main__':
    main()
