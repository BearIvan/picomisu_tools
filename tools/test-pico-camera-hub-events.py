"""Exercise real registry + event functions with mocked FH event queues.

This verifies process-context unicast selection/owned route keys. No V4L2
nodes, subscription calls or IRQ delivery are simulated as working hardware.
"""
from pathlib import Path
import hashlib
import importlib.util
import json
import subprocess

BASE = Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro')
DIRECTORY = 'techpack/camera/drivers/cam_core/'

EXTRA = r'''
#include <stdint.h>
#include <string.h>
typedef uint32_t u32;
#define GFP_KERNEL 0
#define spin_lock_init(p) (*(p)=0)
#define pico_hub_check_client_layouts() ((void)0)
#define list_for_each_entry_safe(p,n,h,m) \
 for(struct list_head *cursor=(h)->next,*following;cursor!=(h) && \
 ((following=cursor->next),(p)=container_of(cursor,__typeof__(*(p)),m), \
 (n)=following!=(h)?container_of(following,__typeof__(*(n)),m):NULL,1);cursor=following)
static void list_del(struct list_head *node) {node->next->prev=node->prev;node->prev->next=node->next;}
struct v4l2_fh {struct video_device *vdev;struct list_head subscribed;struct mutex subscribe_lock;};
struct v4l2_event {u32 type,pad;union {unsigned char data[64];} u;u32 id;};
struct pico_hub_client {
 struct pico_hub_video *parent;
 struct list_head sync_handles,session_handles,reserved_handles_40,reserved_handles_56;
 int tgid,lock;u32 reserved_80;struct v4l2_fh fh;struct list_head registry;u32 cleanup_active;
};
struct pico_hub_event_handle {u32 key,reserved;struct list_head list;};
static unsigned allocated,freed,delivered;
static int fail_alloc;
static struct v4l2_fh *last_fh;
static struct v4l2_event last_event;
static void *kzalloc(size_t n,int flags) {assert(held);if(fail_alloc)return NULL;void *p=calloc(1,n);assert(p);allocated++;return p;}
static void kfree(void *p) {assert(held);if(p){freed++;free(p);}}
static void v4l2_event_queue_fh(struct v4l2_fh *fh,const struct v4l2_event *event) {
 assert(held && fh && fh->vdev);last_fh=fh;last_event=*event;delivered++;
}
/* IRQ_MOCKS: real index/producer paths have a separate concurrency harness. */
static unsigned long pico_hub_irq_lock(void) {assert(held);return 0;}
static void pico_hub_irq_unlock(unsigned long f) {assert(held);}
static int pico_hub_irq_attach_client_locked(struct pico_hub_client *c) {assert(held);return 0;}
static void pico_hub_irq_detach_client_locked(struct pico_hub_client *c) {assert(held);}
static void pico_hub_mark_client_closed_locked(struct pico_hub_client *c) {assert(held);c->reserved_80=1;}
/* BODIES */
static void set_key(struct v4l2_event *event,u32 key) {memcpy(event->u.data,&key,sizeof(key));}
int main(void) {
 struct video_device video[6]={{0}};
 video[0].entity.function=0x10000;video[2].entity.function=0x10100;
 struct pico_hub_video crm={.original=&video[0],.shadow=&video[1],.multi_client=true};
 struct pico_hub_video sync={.original=&video[2],.shadow=&video[3],.multi_client=true};
 struct pico_hub_client one={.fh={.vdev=&video[1]}},two={.fh={.vdev=&video[0]}},three={.fh={.vdev=&video[3]}};
 struct pico_hub_client invalid={.fh={.vdev=&video[4]}};
 struct v4l2_event event={.type=0x8000000};set_key(&event,0xdeadbeefU);
 INIT_LIST_HEAD(&one.fh.subscribed);INIT_LIST_HEAD(&two.fh.subscribed);INIT_LIST_HEAD(&three.fh.subscribed);
 pico_hub_registry_lock();
 assert(!pico_hub_route_event_locked(&video[4],&event));assert(!delivered);
 assert(!pico_hub_add_video_locked(&crm));assert(!pico_hub_add_video_locked(&sync));
 assert(pico_hub_add_event_handle_locked(0,false,1)==-ENOENT);
 assert(pico_hub_attach_client_locked(&crm,&invalid)==-EINVAL);
 assert(!pico_hub_attach_client_locked(&crm,&one));assert(!pico_hub_attach_client_locked(&crm,&two));
 assert(!pico_hub_attach_client_locked(&sync,&three));
 assert(pico_hub_attach_client_locked(&crm,&one)==-EEXIST);
 assert(pico_hub_remove_video_locked(&crm)==-EBUSY);
 assert(pico_hub_route_event_locked(&video[0],&event)==-1);
 assert(!pico_hub_route_event_locked(&video[1],&event)); /* shadow is not a source key */
 assert(!pico_hub_add_event_handle_locked(&one,true,0xdeadbeefU));
 assert(pico_hub_route_event_locked(&video[0],&event)==-1); /* wrong resource class */
 assert(!pico_hub_add_event_handle_locked(&one,false,0xdeadbeefU));
 assert(!pico_hub_route_event_locked(&video[0],&event));assert(last_fh==&one.fh && delivered==1);
 assert(!memcmp(&event,&last_event,sizeof(event)));
 assert(pico_hub_add_event_handle_locked(&one,false,0xdeadbeefU)==-EEXIST);
 assert(!pico_hub_add_event_handle_locked(&two,false,0xdeadbeefU));
 assert(!pico_hub_route_event_locked(&video[0],&event));assert(last_fh==&two.fh && delivered==2);
 assert(!pico_hub_add_event_handle_locked(&three,false,0xdeadbeefU));
 assert(pico_hub_route_event_locked(&video[2],&event)==-1);
 assert(!pico_hub_add_event_handle_locked(&three,true,0xdeadbeefU));
 assert(!pico_hub_route_event_locked(&video[2],&event));assert(last_fh==&three.fh && delivered==3);
 assert(pico_hub_route_event_locked(&video[0],NULL)==-EINVAL);
 crm.multi_client=false;assert(!pico_hub_route_event_locked(&video[0],&event));assert(delivered==3);crm.multi_client=true;
 video[0].entity.function=0x10003;assert(!pico_hub_route_event_locked(&video[0],&event));assert(delivered==3);video[0].entity.function=0x10000;
 fail_alloc=1;assert(pico_hub_add_event_handle_locked(&one,false,123)==-ENOMEM);fail_alloc=0;
 assert(pico_hub_remove_event_handle_locked(&one,false,123)==-ENOENT);
 assert(!pico_hub_remove_event_handle_locked(&two,false,0xdeadbeefU));
 assert(!pico_hub_route_event_locked(&video[0],&event));assert(last_fh==&one.fh && delivered==4);
 struct list_head unknown;list_add(&unknown,&one.reserved_handles_40);
 assert(pico_hub_detach_client_locked(&one)==-EBUSY);list_del(&unknown);
 assert(pico_hub_detach_client_locked(&one)==-EBUSY);
 assert(!pico_hub_remove_event_handle_locked(&one,false,0xdeadbeefU));
 assert(!pico_hub_remove_event_handle_locked(&one,true,0xdeadbeefU));
 assert(!pico_hub_remove_event_handle_locked(&three,false,0xdeadbeefU));
 assert(!pico_hub_remove_event_handle_locked(&three,true,0xdeadbeefU));
 assert(!pico_hub_detach_client_locked(&one));assert(!one.parent);
 assert(pico_hub_route_event_locked(&video[0],&event)==-1);
 assert(pico_hub_detach_client_locked(&one)==-ENOENT);
 assert(!pico_hub_detach_client_locked(&two));assert(!pico_hub_detach_client_locked(&three));
 assert(allocated==freed);assert(!pico_hub_remove_video_locked(&crm));assert(!pico_hub_remove_video_locked(&sync));
 assert(!pico_hub_route_event_locked(&video[2],&event));assert(delivered==4);
 pico_hub_registry_unlock();
 puts("PASS: CRM/session vs sync/sync-handle unicast, high-bit keys, first matching client, no-match/no-op rules, allocation faults and detach cleanup");
}
'''


def main():
    spec = importlib.util.spec_from_file_location('registry_test', Path(__file__).with_name('test-pico-camera-hub-registry.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    prefix = module.HARNESS.split('/* SOURCE */')[0]
    prefix = prefix.replace('struct video_device {int marker;};', 'struct video_device {int marker;struct {unsigned function;} entity;};')
    prefix = prefix.replace('struct video_device *original,*shadow;struct list_head registry,subdevices,clients,events;int event_lock;',
                            'struct video_device *original,*shadow;struct list_head registry,subdevices,clients,events;int event_lock;bool multi_client;')
    root = BASE / 'source/phoenix-kernel-recovery'
    registry = (root / DIRECTORY / 'pico_camera_hub_registry.c').read_text()
    events = (root / DIRECTORY / 'pico_camera_hub_events.c').read_text()
    bodies = registry[registry.index('static DEFINE_MUTEX'):] + events[events.index('static bool pico_hub_client_attached_locked'):]
    code = prefix + EXTRA.replace('/* BODIES */', bodies)
    out = BASE / 'out/phoenix-kernel-recovery/camera-hub-events-tests'
    out.mkdir(exist_ok=True)
    (out / 'harness.c').write_text(code)
    subprocess.run(['gcc', '-std=gnu11', '-g', '-O1', '-pthread', '-fsanitize=address,undefined',
                    '-fno-omit-frame-pointer', str(out / 'harness.c'), '-o', str(out / 'test')], check=True)
    result = subprocess.run([str(out / 'test')], capture_output=True, text=True, timeout=30)
    sources = {DIRECTORY + name: hashlib.sha256((root / DIRECTORY / name).read_bytes()).hexdigest()
               for name in ['pico_camera_hub_registry.c', 'pico_camera_hub_events.c', 'pico_camera_hub.h']}
    report = {'sources': sources, 'harness_sha256': hashlib.sha256(code.encode()).hexdigest(),
              'scope': 'Actual registry/event function bodies with mock lists/mutex/FH queue; process context only, no IRQ/subscription/V4L2 nodes',
              'exit_code': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr,
              'sanitizers': ['AddressSanitizer', 'UndefinedBehaviorSanitizer'], 'device_modified': False}
    (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    if result.returncode:
        raise SystemExit(result.returncode)


if __name__ == '__main__':
    main()
