"""Test real hub open/release/retry/stop code with host V4L2/workqueue mocks."""
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
#include <stdatomic.h>
struct task_struct {int tgid;};
static struct task_struct user_task={123},worker_task={0};
static _Thread_local struct task_struct *current=&user_task;
static int task_tgid_nr(struct task_struct *t) {return t->tgid;}
#define READ_ONCE(x) (x)
#define WRITE_ONCE(x,v) ((x)=(v))
#define msecs_to_jiffies(x) (x)
#define WQ_MEM_RECLAIM 1
#define THIS_MODULE NULL
#define CONFIG_COMPAT 1
#define O_RDWR 2
#define EPOLLERR 8
#define EPOLLPRI 2
typedef unsigned __poll_t;
struct poll_table_struct {int marker;};
struct file {void *private_data;struct video_device *vdev;struct v4l2_fh original_fh;};
static struct video_device *video_devdata(struct file *f) {return f->vdev;}
static const char *dev_name(struct device *d) {return d->name;}
struct v4l2_file_operations {void *owner;int (*open)(struct file *);int (*release)(struct file *);__poll_t (*poll)(struct file *,struct poll_table_struct *);long (*unlocked_ioctl)(struct file *,unsigned,u_long);long (*compat_ioctl32)(struct file *,unsigned,u_long);};
struct kref {unsigned count;};
static void kref_init(struct kref *r) {r->count=1;}
static void kref_get(struct kref *r) {assert(r->count);r->count++;}
static unsigned kref_read(struct kref *r) {return r->count;}
static int kref_put(struct kref *r,void (*fn)(struct kref *)) {assert(r->count);if(!--r->count){fn(r);return 1;}return 0;}
struct work_struct {void (*fn)(struct work_struct *);pthread_t thread;};
struct delayed_work {struct work_struct work;};
struct workqueue_struct {int marker;};
static struct workqueue_struct global_queue;
static struct workqueue_struct *system_unbound_wq=&global_queue;
static struct delayed_work *pending;
static int fail_queue,fail_queue_alloc,queues;
#define INIT_WORK(w,f) ((w)->fn=(f))
#define INIT_WORK_ONSTACK(w,f) INIT_WORK(w,f)
static void destroy_work_on_stack(struct work_struct *w) {(void)w;}
#define INIT_DELAYED_WORK(w,f) INIT_WORK(&(w)->work,f)
#define to_delayed_work(w) container_of(w,struct delayed_work,work)
static struct workqueue_struct *alloc_workqueue(const char *name,int flags,int threads) {assert(threads==1);if(fail_queue_alloc)return NULL;queues++;return calloc(1,sizeof(struct workqueue_struct));}
static void destroy_workqueue(struct workqueue_struct *q) {assert(!pending);queues--;free(q);}
static void *run_work(void *arg) {struct work_struct *w=arg;current=&worker_task;w->fn(w);return NULL;}
static bool queue_work(struct workqueue_struct *q,struct work_struct *w) {if(fail_queue)return false;assert(!pthread_create(&w->thread,NULL,run_work,w));return true;}
static void flush_work(struct work_struct *w) {assert(!pthread_join(w->thread,NULL));}
static bool queue_delayed_work(struct workqueue_struct *q,struct delayed_work *w,unsigned delay) {assert(q!=system_unbound_wq && delay==1000 && !pending);pending=w;return true;}
static void run_pending(void) {assert(pending);struct delayed_work *w=pending;pending=NULL;struct task_struct *save=current;current=&worker_task;w->work.fn(&w->work);current=save;}
#define pr_warn_ratelimited(...) ((void)0)
#define IS_ERR(p) ((uintptr_t)(p)>=(uintptr_t)-4095)
#define IS_ERR_OR_NULL(p) (!(p)||IS_ERR(p))
#define ERR_PTR(x) ((void *)(intptr_t)(x))
#define PTR_ERR(p) ((int)(intptr_t)(p))
static struct file *filp_open(const char *path,int flags,int mode);
enum pico_hub_file_operation {PICO_HUB_VIDEO_CLOSE=1};
static int pico_hub_file_close(struct workqueue_struct *,enum pico_hub_file_operation,struct file *,unsigned);
static int pico_hub_cleanup_client_resources(struct pico_hub_client *);
static int pico_hub_close_subscriptions_locked(struct pico_hub_client *);
static _Atomic unsigned added,deleted,exited,opened,closed,cleanup_calls;
static int open_error,close_error,cleanup_error,subscription_error;
static struct video_device *physical;
static void v4l2_fh_init(struct v4l2_fh *f,struct video_device *v) {f->vdev=v;INIT_LIST_HEAD(&f->subscribed);}
static void v4l2_fh_add(struct v4l2_fh *f) {added++;}
static void v4l2_fh_del(struct v4l2_fh *f) {deleted++;}
static void v4l2_fh_exit(struct v4l2_fh *f) {assert(list_empty(&f->subscribed));exited++;}
static void poll_wait(struct file *f,int *wait,struct poll_table_struct *p) {(void)f;(void)wait;(void)p;}
static int v4l2_event_pending(struct v4l2_fh *f) {return f->wait;}
static long video_ioctl2(struct file *f,unsigned c,u_long a) {return -ENOTTY;}
static long v4l2_compat_ioctl32(struct file *f,unsigned c,u_long a) {return -ENOTTY;}
static int list_is_singular(struct list_head *h) {return !list_empty(h)&&h->next==h->prev;}
'''

MAIN = r'''
static pthread_mutex_t open_gate=PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t open_signal=PTHREAD_COND_INITIALIZER;
static bool block_open,open_entered;
static int native_open(struct file *f) {
 assert(!held && current==&worker_task);opened++;
 pthread_mutex_lock(&open_gate);open_entered=true;pthread_cond_broadcast(&open_signal);
 while(block_open)pthread_cond_wait(&open_signal,&open_gate);pthread_mutex_unlock(&open_gate);
 if(open_error)return open_error;f->private_data=&f->original_fh;v4l2_fh_init(&f->original_fh,f->vdev);return 0;
}
static int native_release(struct file *f) {assert(!held && f->private_data==&f->original_fh);closed++;return 0;}
static struct file *filp_open(const char *path,int flags,int mode) {
 assert(!strcmp(path,"/dev/video0") && flags==O_RDWR && !mode);
 struct file *f=kzalloc(sizeof(*f),GFP_KERNEL);assert(f);f->vdev=physical;
 int rc=pico_hub_video_open(f);if(rc){kfree(f);return ERR_PTR(rc);}return f;
}
static int pico_hub_file_close(struct workqueue_struct *q,enum pico_hub_file_operation op,struct file *f,unsigned timeout) {
 assert(!held && q==system_unbound_wq && op==PICO_HUB_VIDEO_CLOSE && timeout==500);
 if(close_error && close_error!=-ETIMEDOUT)return close_error;
 assert(!pico_hub_video_release(f));kfree(f);return close_error;
}
static int pico_hub_close_subscriptions_locked(struct pico_hub_client *c) {assert(held==1);return subscription_error;}
static int pico_hub_cleanup_client_resources(struct pico_hub_client *c) {
 assert(!held && c->reserved_80);cleanup_calls++;if(cleanup_error)return cleanup_error;
 pico_hub_registry_lock();
 while(!list_empty(&c->session_handles)) {struct pico_hub_event_handle *e=container_of(c->session_handles.next,struct pico_hub_event_handle,list);assert(!pico_hub_remove_event_handle_locked(c,false,e->key));}
 pico_hub_registry_unlock();return 0;
}
static void setup(struct pico_hub_video *p,struct video_device v[2]) {
 static const struct v4l2_file_operations ops={.open=native_open,.release=native_release};
 memset(p,0,sizeof(*p));memset(v,0,2*sizeof(*v));v[0].entity.function=0x10000;v[0].dev.name="video0";physical=&v[0];
 p->original=&v[0];p->shadow=&v[1];p->multi_client=true;p->original_fops=&ops;
 pico_hub_registry_lock();assert(!pico_hub_add_video_locked(p));pico_hub_registry_unlock();
 assert(!pico_hub_video_runtime_init(p));assert(pico_hub_video_runtime_init(p)==-EBUSY);
 struct file early={.vdev=&v[1]};assert(pico_hub_video_open(&early)==-ENODEV);
 assert(!pico_hub_video_runtime_activate(p));
 pico_hub_registry_lock();assert(pico_hub_remove_video_locked(p)==-EBUSY);pico_hub_registry_unlock();
}
static void teardown(struct pico_hub_video *p) {
 assert(!pico_hub_video_runtime_stop(p));assert(!p->reserved_224 && !p->shared_file);
 pico_hub_registry_lock();assert(!pico_hub_remove_video_locked(p));pico_hub_registry_unlock();
 assert(!queues && !pending);
}
struct race_call {struct file *file;struct pico_hub_video *parent;int result;};
static void *race_open(void *arg) {struct race_call *c=arg;c->result=pico_hub_video_open(c->file);return NULL;}
static void *race_stop(void *arg) {struct race_call *c=arg;c->result=pico_hub_video_runtime_stop(c->parent);return NULL;}
int main(void) {
 assert(pico_hub_video_runtime_init(NULL)==-EINVAL);
 struct pico_hub_video p;struct video_device v[2];setup(&p,v);
 struct file one={.vdev=&v[1]},two={.vdev=&v[0]};
 assert(!pico_hub_video_open(&one));assert(!pico_hub_video_open(&two));assert(opened==1 && !closed && added==2);
 struct pico_hub_client *c=container_of(one.private_data,struct pico_hub_client,fh);
 assert(c->tgid==123 && c->fh.vdev==&v[1]);
 struct poll_table_struct wait={0};assert(!pico_hub_video_poll(&one,&wait));c->fh.wait=1;assert(pico_hub_video_poll(&one,&wait)==EPOLLPRI);
 assert(pico_hub_video_runtime_stop(&p)==-EBUSY);struct file refused={.vdev=&v[1]};assert(pico_hub_video_open(&refused)==-ENODEV);
 assert(!pico_hub_video_release(&one));assert(!one.private_data && !closed && deleted==1);
 assert(!pico_hub_video_release(&two));assert(closed==1 && deleted==2 && cleanup_calls==2);teardown(&p);
 /* Failed resource destruction retains FH/runtime/shared file for retries. */
 setup(&p,v);one=(struct file){.vdev=&v[1]};assert(!pico_hub_video_open(&one));
 c=container_of(one.private_data,struct pico_hub_client,fh);pico_hub_registry_lock();assert(!pico_hub_add_event_handle_locked(c,false,777));pico_hub_registry_unlock();
 cleanup_error=-EIO;assert(pico_hub_video_release(&one)==-EIO);assert(pending && !one.private_data && c->reserved_80 && p.shared_file);
 struct v4l2_event e={0};u32 key=777;memcpy(e.u.data,&key,4);pico_hub_registry_lock();assert(pico_hub_route_event_locked(&v[0],&e)==-1);pico_hub_registry_unlock();
 assert(pico_hub_video_runtime_stop(&p)==-EBUSY);run_pending();assert(pending && p.shared_file);cleanup_error=0;run_pending();assert(!pending && !p.shared_file);teardown(&p);
 /* Close worker allocation/queue failure still owns the original file. */
 setup(&p,v);one=(struct file){.vdev=&v[1]};assert(!pico_hub_video_open(&one));close_error=-ENOMEM;
 assert(pico_hub_video_release(&one)==-ENOMEM);assert(pending && p.shared_file);close_error=-ETIMEDOUT;run_pending();assert(!pending && !p.shared_file);close_error=0;teardown(&p);
 /* Driver-open and queue failure unwind the managed client and lookup ref. */
 setup(&p,v);one=(struct file){.vdev=&v[1]};open_error=-EIO;assert(pico_hub_video_open(&one)==-EIO);assert(!one.private_data && !p.shared_file);open_error=0;
 fail_queue=1;assert(pico_hub_video_open(&one)==-EBUSY);fail_queue=0;
 fail_alloc=1;assert(pico_hub_video_open(&one)==-ENOMEM);fail_alloc=0;teardown(&p);
 /* Runtime lookup acquired before stop is drained before parent removal. */
 setup(&p,v);one=(struct file){.vdev=&v[1]};struct pico_hub_video_runtime *r=pico_hub_get_runtime(&one,false);
 assert(r);assert(pico_hub_video_runtime_stop(&p)==-EBUSY);assert(!pico_hub_get_runtime(&one,false));kref_put(&r->refs,pico_hub_runtime_free);teardown(&p);
 /* Stop while a real pthread worker is inside original open. Its flag
  * rejects new lookups while the existing open keeps parent lifetime. */
 setup(&p,v);one=(struct file){.vdev=&v[1]};pthread_t opener,stopper;
 struct race_call opening={.file=&one},stopping={.parent=&p};
 pthread_mutex_lock(&open_gate);block_open=true;open_entered=false;pthread_mutex_unlock(&open_gate);
 assert(!pthread_create(&opener,NULL,race_open,&opening));
 pthread_mutex_lock(&open_gate);while(!open_entered)pthread_cond_wait(&open_signal,&open_gate);pthread_mutex_unlock(&open_gate);
 assert(!pthread_create(&stopper,NULL,race_stop,&stopping));
 bool seen=false;for(int i=0;i<1000000;i++) {pico_hub_registry_lock();seen=((struct pico_hub_video_runtime *)p.reserved_224)->stopping;pico_hub_registry_unlock();if(seen)break;sched_yield();}assert(seen);
 refused=(struct file){.vdev=&v[1]};assert(pico_hub_video_open(&refused)==-ENODEV);
 pthread_mutex_lock(&open_gate);block_open=false;pthread_cond_broadcast(&open_signal);pthread_mutex_unlock(&open_gate);
 assert(!pthread_join(opener,NULL));assert(!pthread_join(stopper,NULL));assert(!opening.result && stopping.result==-EBUSY);
 assert(!pico_hub_video_release(&one));teardown(&p);
 assert(allocated==freed);assert(added==deleted);
 assert(pico_hub_video_fops.open && pico_hub_video_fops.release && pico_hub_video_fops.unlocked_ioctl==video_ioctl2 && pico_hub_video_fops.compat_ioctl32==v4l2_compat_ioctl32);
 puts("PASS: shared original open with pthread worker bypass, per-client FH and poll, final close, retained cleanup retries, closed-event exclusion, close timeout ownership, unwind faults, stop/ref guards and stop during blocked worker open; no owned allocation leaks");
}
'''


def main():
    registry_test = load('test-pico-camera-hub-registry')
    event_test = load('test-pico-camera-hub-events')
    prefix = registry_test.HARNESS.split('/* SOURCE */')[0]
    prefix = prefix.replace('struct video_device {int marker;};', 'struct device {const char *name;};struct video_device {int marker;struct {unsigned function;} entity;struct device dev;};')
    prefix = prefix.replace('int event_lock;', 'int event_lock;bool multi_client;struct mutex open_lock,ioctl_lock;const struct v4l2_file_operations *original_fops;struct file *shared_file;')
    prefix = prefix.replace('static void mutex_lock(struct mutex *m) {assert(!held);assert(!pthread_mutex_lock(&m->value));held++;}', 'static struct mutex pico_hub_registry_mutex;static void mutex_init(struct mutex *m) {assert(!pthread_mutex_init(&m->value,NULL));}static void mutex_lock(struct mutex *m) {if(m==&pico_hub_registry_mutex)assert(!held);assert(!pthread_mutex_lock(&m->value));if(m==&pico_hub_registry_mutex)held++;}')
    prefix = prefix.replace('static void mutex_unlock(struct mutex *m) {assert(held==1);held--;assert(!pthread_mutex_unlock(&m->value));}', 'static void mutex_unlock(struct mutex *m) {if(m==&pico_hub_registry_mutex){assert(held==1);held--;}assert(!pthread_mutex_unlock(&m->value));}')
    extra = event_test.EXTRA.split('/* BODIES */')[0]
    extra = extra.replace('struct mutex subscribe_lock;', 'struct mutex subscribe_lock;int wait;')
    extra = extra.replace('assert(held);if(fail_alloc)', 'if(fail_alloc)').replace('assert(held);if(p)', 'if(p)')
    prefix += extra
    root = event_test.BASE / 'source/phoenix-kernel-recovery' / event_test.DIRECTORY
    names = ['pico_camera_hub_registry.c', 'pico_camera_hub_events.c', 'pico_camera_hub_fops.c', 'pico_camera_hub_fops.h', 'pico_camera_hub.h']
    registry, events, fops = [(root / n).read_text() for n in names[:3]]
    bodies = registry[registry.index('static DEFINE_MUTEX'):] + events[events.index('static bool pico_hub_client_attached_locked'):] + fops[fops.index('struct pico_hub_video_runtime {'):]
    code = prefix + MOCKS + bodies + MAIN
    out = event_test.BASE / 'out/phoenix-kernel-recovery/camera-hub-fops-tests'
    out.mkdir(exist_ok=True)
    (out / 'harness.c').write_text(code)
    subprocess.run(['gcc', '-std=gnu11', '-g', '-O1', '-pthread', '-fsanitize=address,undefined', '-fno-omit-frame-pointer', str(out / 'harness.c'), '-o', str(out / 'test')], check=True)
    result = subprocess.run([str(out / 'test')], capture_output=True, text=True, timeout=30)
    report = {'sources': {event_test.DIRECTORY + n: hashlib.sha256((root / n).read_bytes()).hexdigest() for n in names}, 'harness_sha256': hashlib.sha256(code.encode()).hexdigest(), 'exit_code': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr, 'sanitizers': ['AddressSanitizer', 'UndefinedBehaviorSanitizer'], 'scope': 'Actual open/release/retry/stop/registry/event bodies with pthread open workers and V4L2/file/cleanup mocks; delayed retry manually dispatched; no real nodes or physical drivers', 'device_modified': False}
    (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    raise SystemExit(result.returncode)


if __name__ == '__main__':
    main()
