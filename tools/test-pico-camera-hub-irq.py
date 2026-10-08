"""Actual IRQ route + client/handle mutations and native event producer bodies."""
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


SPIN = r'''
#include <stdatomic.h>
#define LIST_HEAD(n) struct list_head n={&(n),&(n)}
#define DEFINE_SPINLOCK(n) pthread_mutex_t n=PTHREAD_MUTEX_INITIALIZER
#define spin_lock_irqsave(p,f) do {(f)=0;assert(!irq_held);assert(!pthread_mutex_lock(p));irq_held=1;}while(0)
#define spin_unlock_irqrestore(p,f) do {assert(irq_held);irq_held=0;assert(!pthread_mutex_unlock(p));}while(0)
static unsigned long pico_hub_irq_lock(void);
static void pico_hub_irq_unlock(unsigned long);
static int pico_hub_irq_attach_client_locked(struct pico_hub_client *);
static void pico_hub_irq_detach_client_locked(struct pico_hub_client *);
static void pico_hub_mark_client_closed_locked(struct pico_hub_client *);
'''

QUEUE = r'''
static pthread_mutex_t gate=PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t changed=PTHREAD_COND_INITIALIZER;
static bool pause_queue,queue_entered,allow_queue,close_started,close_done;
static void v4l2_event_queue_fh(struct v4l2_fh *fh,const struct v4l2_event *event) {
 assert(!held && irq_held && fh && fh->vdev);
 pthread_mutex_lock(&gate);queue_entered=true;pthread_cond_broadcast(&changed);
 while(pause_queue && !allow_queue)pthread_cond_wait(&changed,&gate);
 pthread_mutex_unlock(&gate);
 last_fh=fh;last_event=*event;delivered++;
}
'''

NATIVE = r'''
typedef uint64_t __u64;
struct cam_req_mgr_message {u32 session_hdl;unsigned char payload[60];};
struct cam_sync_ev_header {u32 sync_obj;int status;};
#define CAM_REQ_MGR_GET_PAYLOAD_PTR(e,t) ((t *)(e).u.data)
#define CAM_SYNC_GET_HEADER_PTR(e) ((struct cam_sync_ev_header *)(e).u.data)
#define CAM_SYNC_GET_PAYLOAD_PTR(e,t) ((t *)((e).u.data+sizeof(struct cam_sync_ev_header)))
#define CAM_SYNC_V4L_EVENT 0x8000000U
#define CAM_SYNC 0
#define CAM_DBG(...) ((void)0)
'''

MAIN = r'''
static struct pico_hub_client *closing_client;
static struct v4l2_event threaded_event;
static _Atomic bool stop_stream;
static _Atomic unsigned stream_calls;
static void *deliver_one(void *unused) {irq_context=1;assert(!pico_hub_route_irq_event(0x10000,&threaded_event));irq_context=0;return NULL;}
static void *close_one(void *unused) {
 pthread_mutex_lock(&gate);close_started=true;pthread_cond_broadcast(&changed);pthread_mutex_unlock(&gate);
 pico_hub_registry_lock();pico_hub_mark_client_closed_locked(closing_client);
 assert(!pico_hub_remove_event_handle_locked(closing_client,false,777));assert(!pico_hub_detach_client_locked(closing_client));kfree(closing_client);pico_hub_registry_unlock();
 pthread_mutex_lock(&gate);close_done=true;pthread_cond_broadcast(&changed);pthread_mutex_unlock(&gate);return NULL;
}
static void *stream(void *unused) {irq_context=1;while(!atomic_load(&stop_stream)) {int rc=pico_hub_route_irq_event(0x10000,&threaded_event);assert(!rc || rc==-ENOENT);atomic_fetch_add(&stream_calls,1);}irq_context=0;return NULL;}
static void init_client(struct pico_hub_client *c,struct video_device *v) {memset(c,0,sizeof(*c));c->fh.vdev=v;INIT_LIST_HEAD(&c->fh.subscribed);}
static void key(struct v4l2_event *e,u32 value) {memcpy(e->u.data,&value,4);}
int main(void) {
 struct video_device v[4]={{0}};v[0].entity.function=0x10000;v[2].entity.function=0x10100;
 struct pico_hub_video crm={.original=&v[0],.shadow=&v[1],.multi_client=true},sync={.original=&v[2],.shadow=&v[3],.multi_client=true};
 struct pico_hub_client first,second,fence,failed;init_client(&first,&v[1]);init_client(&second,&v[0]);init_client(&fence,&v[3]);init_client(&failed,&v[1]);
 pico_hub_registry_lock();assert(!pico_hub_add_video_locked(&crm));assert(!pico_hub_add_video_locked(&sync));
 fail_alloc=1;assert(pico_hub_attach_client_locked(&crm,&failed)==-ENOMEM);assert(!failed.parent && list_empty(&pico_hub_irq_clients));fail_alloc=0;
 assert(!pico_hub_attach_client_locked(&crm,&first));assert(!pico_hub_attach_client_locked(&crm,&second));assert(!pico_hub_attach_client_locked(&sync,&fence));
 assert(!pico_hub_add_event_handle_locked(&second,false,0xdeadbeefU));assert(!pico_hub_add_event_handle_locked(&first,false,0xdeadbeefU));assert(!pico_hub_add_event_handle_locked(&fence,true,0xdeadbeefU));pico_hub_registry_unlock();
 struct v4l2_event e={.type=17,.id=9};key(&e,0xdeadbeefU);irq_context=1;
 assert(!pico_hub_route_irq_event(0x10000,&e));assert(last_fh==&second.fh);assert(!memcmp(&e,&last_event,sizeof(e)));
 assert(!pico_hub_route_irq_event(0x10100,&e));assert(last_fh==&fence.fh);assert(!pico_hub_route_irq_event(0x10003,&e));assert(pico_hub_route_irq_event(0x10000,NULL)==-EINVAL);irq_context=0;
 pico_hub_registry_lock();pico_hub_mark_client_closed_locked(&second);pico_hub_registry_unlock();irq_context=1;
 assert(!pico_hub_route_irq_event(0x10000,&e));assert(last_fh==&first.fh);irq_context=0;
 /* Real native producer bodies preserve type/id/payload and zero tail. */
 struct cam_req_mgr_message msg={.session_hdl=0xdeadbeefU};memset(msg.payload,0xa5,sizeof(msg.payload));irq_context=1;
 assert(!cam_req_mgr_notify_message(&msg,33,44));assert(last_fh==&first.fh && last_event.id==33 && last_event.type==44 && !memcmp(last_event.u.data,&msg,sizeof(msg)));
 assert(cam_req_mgr_notify_message(NULL,0,0)==-EINVAL);
 __u64 payload[2]={0x1122334455667788ULL,0xaabbccddULL};cam_sync_util_send_v4l2_event(66,0xdeadbeefU,-7,payload,16);
 assert(last_fh==&fence.fh && last_event.id==66 && last_event.type==CAM_SYNC_V4L_EVENT);struct cam_sync_ev_header *header=(void *)last_event.u.data;assert(header->sync_obj==0xdeadbeefU && header->status==-7);assert(!memcmp(last_event.u.data+8,payload,16));
 for(int i=24;i<64;i++)assert(!last_event.u.data[i]);unsigned before=delivered;
 cam_sync_util_send_v4l2_event(1,0xdeadbeefU,0,payload,-1);cam_sync_util_send_v4l2_event(1,0xdeadbeefU,0,payload,57);cam_sync_util_send_v4l2_event(1,0xdeadbeefU,0,NULL,1);assert(delivered==before);
 cam_sync_util_send_v4l2_event(1,0xdeadbeefU,0,NULL,0);assert(delivered==before+1);irq_context=0;
 pico_hub_registry_lock();assert(!pico_hub_remove_event_handle_locked(&first,false,0xdeadbeefU));assert(!pico_hub_remove_event_handle_locked(&second,false,0xdeadbeefU));assert(!pico_hub_remove_event_handle_locked(&fence,true,0xdeadbeefU));assert(!pico_hub_detach_client_locked(&first));assert(!pico_hub_detach_client_locked(&second));assert(!pico_hub_detach_client_locked(&fence));pico_hub_registry_unlock();
 /* Pause simulated IRQ in the queue callback; close cannot free the FH. */
 pico_hub_registry_lock();closing_client=kzalloc(sizeof(*closing_client),0);init_client(closing_client,&v[1]);assert(!pico_hub_attach_client_locked(&crm,closing_client));assert(!pico_hub_add_event_handle_locked(closing_client,false,777));pico_hub_registry_unlock();
 threaded_event=(struct v4l2_event){.type=1};key(&threaded_event,777);pause_queue=true;allow_queue=false;queue_entered=false;close_started=false;close_done=false;
 pthread_t producer,closer;assert(!pthread_create(&producer,NULL,deliver_one,NULL));pthread_mutex_lock(&gate);while(!queue_entered)pthread_cond_wait(&changed,&gate);pthread_mutex_unlock(&gate);
 assert(!pthread_create(&closer,NULL,close_one,NULL));pthread_mutex_lock(&gate);while(!close_started)pthread_cond_wait(&changed,&gate);assert(!close_done);allow_queue=true;pthread_cond_broadcast(&changed);pthread_mutex_unlock(&gate);
 assert(!pthread_join(producer,NULL));assert(!pthread_join(closer,NULL));assert(close_done);pause_queue=false;
 irq_context=1;assert(pico_hub_route_irq_event(0x10000,&threaded_event)==-ENOENT);irq_context=0;
 /* Concurrent lookup while keys and entire clients are recycled. */
 atomic_store(&stop_stream,false);assert(!pthread_create(&producer,NULL,stream,NULL));
 while(!atomic_load(&stream_calls))sched_yield();
 for(int i=0;i<1000;i++) {pico_hub_registry_lock();struct pico_hub_client *c=kzalloc(sizeof(*c),0);init_client(c,&v[1]);assert(!pico_hub_attach_client_locked(&crm,c));assert(!pico_hub_add_event_handle_locked(c,false,777));assert(!pico_hub_remove_event_handle_locked(c,false,777));assert(!pico_hub_detach_client_locked(c));kfree(c);pico_hub_registry_unlock();}
 atomic_store(&stop_stream,true);assert(!pthread_join(producer,NULL));assert(list_empty(&pico_hub_irq_clients));
 pico_hub_registry_lock();assert(!pico_hub_remove_video_locked(&crm));assert(!pico_hub_remove_video_locked(&sync));pico_hub_registry_unlock();assert(allocated==freed);
 puts("PASS: actual IRQ/client/handle functions and native producers; no registry mutex/allocation in IRQ; newest matching client, entity separation, closed exclusion, packet bounds/zero tail, blocked delivery vs close and 1000 concurrent client/key free cycles; no allocation leaks");
}
'''


def main():
    common = load('test-pico-camera-hub-registry')
    event_test = load('test-pico-camera-hub-events')
    prefix = 'static _Thread_local int irq_context,irq_held;\n' + common.HARNESS.split('/* SOURCE */')[0]
    prefix = prefix.replace('struct video_device {int marker;};', 'struct video_device {int marker;struct {unsigned function;} entity;};')
    prefix = prefix.replace('int event_lock;', 'int event_lock;bool multi_client;')
    prefix = prefix.replace('static void mutex_lock(struct mutex *m) {assert(!held);', 'static void mutex_lock(struct mutex *m) {assert(!irq_context);assert(!held);')
    extra = event_test.EXTRA.split('/* IRQ_MOCKS')[0]
    extra = extra.replace('assert(held);if(fail_alloc)', 'assert(!irq_context && held);if(fail_alloc)').replace('assert(held);if(p)', 'assert(!irq_context && held);if(p)')
    start = extra.index('static void v4l2_event_queue_fh(')
    extra = extra[:start] + QUEUE
    prefix += extra + SPIN
    source = event_test.BASE / 'source/phoenix-kernel-recovery'
    d = event_test.DIRECTORY
    names = [d + n for n in ['pico_camera_hub_registry.c', 'pico_camera_hub_events.c', 'pico_camera_hub_irq.c', 'pico_camera_hub_irq.h', 'pico_camera_hub.h', 'pico_camera_hub_dispatch.c', 'pico_camera_hub_cleanup.c', 'pico_camera_hub_fops.c']]
    crm_name = 'techpack/camera/drivers/cam_req_mgr/cam_req_mgr_dev.c'
    sync_name = 'techpack/camera/drivers/cam_sync/cam_sync_util.c'
    names += [crm_name, sync_name]
    registry, events, irq = [(source / n).read_text() for n in names[:3]]
    # Public functions are extern in the kernel; forward-declare identically.
    prefix = prefix.replace('static unsigned long pico_hub_irq_lock', 'unsigned long pico_hub_irq_lock').replace('static void pico_hub_irq_', 'void pico_hub_irq_').replace('static int pico_hub_irq_', 'int pico_hub_irq_').replace('static void pico_hub_mark_', 'void pico_hub_mark_')
    bodies = registry[registry.index('static DEFINE_MUTEX'):] + irq[irq.index('struct pico_hub_irq_client {'):] + events[events.index('static bool pico_hub_client_attached_locked'):]
    parse = load('test-pico-camera-hub-dispatch').function
    native = parse((source / crm_name).read_text(), 'int cam_req_mgr_notify_message(') + parse((source / sync_name).read_text(), 'void cam_sync_util_send_v4l2_event(')
    code = prefix + bodies + NATIVE + native + MAIN
    out = event_test.BASE / 'out/phoenix-kernel-recovery/camera-hub-irq-tests'
    out.mkdir(exist_ok=True)
    (out / 'harness.c').write_text(code)
    subprocess.run(['gcc', '-std=gnu11', '-g', '-O1', '-pthread', '-fsanitize=address,undefined', '-fno-omit-frame-pointer', str(out / 'harness.c'), '-o', str(out / 'test')], check=True)
    result = subprocess.run([str(out / 'test')], capture_output=True, text=True, timeout=30)
    report = {'sources': {n: hashlib.sha256((source / n).read_bytes()).hexdigest() for n in names}, 'harness_sha256': hashlib.sha256(code.encode()).hexdigest(), 'exit_code': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr, 'sanitizers': ['AddressSanitizer', 'UndefinedBehaviorSanitizer'], 'scope': 'Actual IRQ index/route/client/handle and native producers; pthread spin model, deliberately paused mock FH callback, kernel-style mutex/allocator forbidden in simulated IRQ; no hardware IRQ or real V4L2 queue runtime', 'device_modified': False}
    (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    raise SystemExit(result.returncode)


if __name__ == '__main__':
    main()
