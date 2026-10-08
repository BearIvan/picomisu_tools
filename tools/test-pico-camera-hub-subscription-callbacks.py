"""Exercise real V4L2-facing subscribe/unsubscribe/close helper bodies.

V4L2 queues and original driver callbacks are mocked. Covers shared counts,
metadata propagation, duplicates, rollback and close under original errors.
"""
from pathlib import Path
import hashlib
import importlib.util
import json
import subprocess

BASE = Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro')
DIRECTORY = 'techpack/camera/drivers/cam_core/'

MOCK = r'''
#include <limits.h>
#define V4L2_EVENT_ALL 0
#define ENOIOCTLCMD 515
typedef atomic_int atomic_t;
#define atomic_set(p,n) atomic_store(p,n)
#define atomic_read(p) atomic_load(p)
#define pico_hub_check_subscription_layouts() ((void)0)
struct v4l2_event_subscription {u32 type,id,flags,reserved[5];};
struct v4l2_subscribed_event_ops {int marker;};
struct v4l2_subscribed_event {
 struct list_head list;u32 type,id,flags;unsigned elems;
 const struct v4l2_subscribed_event_ops *ops;
};
struct file {void *private_data;};
struct v4l2_ioctl_ops {
 int (*vidioc_subscribe_event)(struct v4l2_fh *,const struct v4l2_event_subscription *);
 int (*vidioc_unsubscribe_event)(struct v4l2_fh *,const struct v4l2_event_subscription *);
};
static const struct v4l2_subscribed_event_ops queue_ops={.marker=88};
static struct v4l2_fh *shared_fh;
static unsigned subscribe_calls,unsubscribe_calls;
static int original_error,original_partial_error,original_empty,original_unsub_error,local_error;
static int mock_subscribe(struct v4l2_fh *fh,const struct v4l2_event_subscription *sub,
 unsigned elems,const struct v4l2_subscribed_event_ops *ops) {
 struct v4l2_subscribed_event *entry;
 assert(held==1);
 if(fh!=shared_fh && local_error)return local_error;
 list_for_each_entry(entry,&fh->subscribed,list)
  if(entry->type==sub->type && entry->id==sub->id)return 0;
 entry=kzalloc(sizeof(*entry),GFP_KERNEL);if(!entry)return -ENOMEM;
 entry->type=sub->type;entry->id=sub->id;entry->flags=sub->flags;entry->elems=elems;entry->ops=ops;
 list_add(&entry->list,&fh->subscribed);return 0;
}
static int v4l2_event_subscribe(struct v4l2_fh *fh,const struct v4l2_event_subscription *sub,
 unsigned elems,const struct v4l2_subscribed_event_ops *ops) {return mock_subscribe(fh,sub,elems,ops);}
static int v4l2_event_unsubscribe(struct v4l2_fh *fh,const struct v4l2_event_subscription *sub) {
 struct v4l2_subscribed_event *entry,*next;
 assert(held==1);
 list_for_each_entry_safe(entry,next,&fh->subscribed,list)
  if(sub->type==V4L2_EVENT_ALL || (entry->type==sub->type && entry->id==sub->id)) {
   list_del(&entry->list);kfree(entry);
  }
 return 0;
}
static void v4l2_event_unsubscribe_all(struct v4l2_fh *fh) {
 struct v4l2_event_subscription all={.type=V4L2_EVENT_ALL};v4l2_event_unsubscribe(fh,&all);
}
static int original_subscribe(struct v4l2_fh *fh,const struct v4l2_event_subscription *sub) {
 assert(fh==shared_fh);subscribe_calls++;
 if(original_error)return original_error;
 if(original_empty)return 0;
 int rc=mock_subscribe(fh,sub,240,&queue_ops);
 return original_partial_error?original_partial_error:rc;
}
static int original_unsubscribe(struct v4l2_fh *fh,const struct v4l2_event_subscription *sub) {
 assert(fh==shared_fh);unsubscribe_calls++;
 if(original_unsub_error)return original_unsub_error;
 return v4l2_event_unsubscribe(fh,sub);
}
static void fh_init(struct v4l2_fh *fh,struct video_device *vdev) {
 fh->vdev=vdev;INIT_LIST_HEAD(&fh->subscribed);assert(!pthread_mutex_init(&fh->subscribe_lock.value,0));
}
/* TYPES */
/* BODIES */
int main(void) {
 struct video_device v[2]={{0}};
 struct v4l2_fh original={0};fh_init(&original,&v[0]);shared_fh=&original;
 struct file file={.private_data=&original};
 struct v4l2_ioctl_ops ops={.vidioc_subscribe_event=original_subscribe,.vidioc_unsubscribe_event=original_unsubscribe};
 struct pico_hub_video parent={.original=&v[0],.shadow=&v[1],.multi_client=true,.shared_file=&file,.original_ioctl_ops=&ops};
 struct pico_hub_client a={0},b={0};fh_init(&a.fh,&v[1]);fh_init(&b.fh,&v[1]);
 struct v4l2_event_subscription sub={.type=0x8000000,.id=7,.flags=1},other=sub;other.id=8;
 pico_hub_registry_lock();assert(!pico_hub_add_video_locked(&parent));
 assert(!pico_hub_attach_client_locked(&parent,&a));assert(!pico_hub_attach_client_locked(&parent,&b));
 assert(pico_hub_subscribe_client_locked(&a,NULL)==-EINVAL);
 struct v4l2_event_subscription all={.type=V4L2_EVENT_ALL};
 assert(pico_hub_subscribe_client_locked(&a,&all)==-EINVAL);
 parent.shared_file=NULL;assert(pico_hub_subscribe_client_locked(&a,&sub)==-ENODEV);parent.shared_file=&file;
 parent.original_ioctl_ops=NULL;assert(pico_hub_subscribe_client_locked(&a,&sub)==-ENOIOCTLCMD);parent.original_ioctl_ops=&ops;
 fail_alloc=1;assert(pico_hub_subscribe_client_locked(&a,&sub)==-ENOMEM);fail_alloc=0;assert(!subscribe_calls);
 original_error=-EIO;assert(pico_hub_subscribe_client_locked(&a,&sub)==-EIO);original_error=0;
 assert(list_empty(&parent.events) && list_empty(&original.subscribed) && list_empty(&a.fh.subscribed));
 original_partial_error=-EINVAL;assert(pico_hub_subscribe_client_locked(&a,&sub)==-EINVAL);original_partial_error=0;
 assert(list_empty(&parent.events) && list_empty(&original.subscribed));
 original_empty=1;assert(pico_hub_subscribe_client_locked(&a,&sub)==-EINVAL);original_empty=0;
 local_error=-ENOMEM;assert(pico_hub_subscribe_client_locked(&a,&sub)==-ENOMEM);local_error=0;
 assert(list_empty(&parent.events) && list_empty(&original.subscribed) && list_empty(&a.fh.subscribed));
 assert(!pico_hub_subscribe_client_locked(&a,&sub));assert(pico_hub_event_ref_locked(&parent,&sub,0)==1);
 struct v4l2_subscribed_event *entry=container_of(a.fh.subscribed.next,struct v4l2_subscribed_event,list);
 assert(entry->elems==240 && entry->ops==&queue_ops && entry->flags==sub.flags);assert(list_empty(&original.subscribed));
 unsigned calls=subscribe_calls;assert(!pico_hub_subscribe_client_locked(&a,&sub));assert(subscribe_calls==calls);
 assert(!pico_hub_subscribe_client_locked(&b,&sub));assert(pico_hub_event_ref_locked(&parent,&sub,0)==2);
 assert(pico_hub_detach_client_locked(&a)==-EBUSY);
 calls=unsubscribe_calls;assert(!pico_hub_unsubscribe_client_locked(&a,&sub));assert(unsubscribe_calls==calls);
 assert(pico_hub_event_ref_locked(&parent,&sub,0)==1);
 original_unsub_error=-EIO;assert(pico_hub_unsubscribe_client_locked(&b,&sub)==-EIO);
 assert(!list_empty(&b.fh.subscribed) && pico_hub_event_ref_locked(&parent,&sub,0)==1);
 original_unsub_error=0;assert(!pico_hub_unsubscribe_client_locked(&b,&sub));assert(list_empty(&parent.events));
 assert(!pico_hub_unsubscribe_client_locked(&b,&sub));
 assert(!pico_hub_subscribe_client_locked(&a,&sub));assert(!pico_hub_subscribe_client_locked(&a,&other));
 original_unsub_error=-EIO;assert(pico_hub_close_subscriptions_locked(&a)==-EIO);original_unsub_error=0;
 assert(list_empty(&a.fh.subscribed) && list_empty(&parent.events));
 assert(!pico_hub_subscribe_client_locked(&a,&sub));assert(!pico_hub_subscribe_client_locked(&b,&sub));
 assert(!pico_hub_unsubscribe_client_locked(&a,&all));assert(pico_hub_event_ref_locked(&parent,&sub,0)==1);
 assert(!pico_hub_close_subscriptions_locked(&b));assert(list_empty(&parent.events));
 assert(!pico_hub_detach_client_locked(&a));assert(!pico_hub_detach_client_locked(&b));assert(!pico_hub_remove_video_locked(&parent));
 assert(allocated==freed);pico_hub_registry_unlock();
 assert(!pthread_mutex_destroy(&original.subscribe_lock.value));assert(!pthread_mutex_destroy(&a.fh.subscribe_lock.value));
 assert(!pthread_mutex_destroy(&b.fh.subscribe_lock.value));
 puts("PASS: original callback -> client V4L2 queue metadata, shared counts, duplicates, reservation/original/local rollback, last-user unsubscribe, retry and forced close cleanup");
}
'''


def load(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    r = load('test-pico-camera-hub-registry')
    e = load('test-pico-camera-hub-events')
    prefix = r.HARNESS.split('/* SOURCE */')[0]
    prefix = prefix.replace('struct video_device {int marker;};', 'struct video_device {int marker;struct {unsigned function;} entity;};')
    prefix = prefix.replace('assert(!held);assert(!pthread_mutex_lock', 'assert(!pthread_mutex_lock')
    prefix = prefix.replace('assert(held==1);held--;', 'assert(held>=1);held--;')
    old = 'struct video_device *original,*shadow;struct list_head registry,subdevices,clients,events;int event_lock;'
    prefix = prefix.replace(old, old + 'bool multi_client;struct file *shared_file;const struct v4l2_ioctl_ops *original_ioctl_ops;')
    prefix += e.EXTRA.split('/* BODIES */')[0]
    root = BASE / 'source/phoenix-kernel-recovery' / DIRECTORY
    registry = (root / 'pico_camera_hub_registry.c').read_text()
    events = (root / 'pico_camera_hub_events.c').read_text()
    counts = (root / 'pico_camera_hub_subscriptions.c').read_text()
    callbacks = (root / 'pico_camera_hub_subscription_callbacks.c').read_text()
    header = (root / 'pico_camera_hub_subscriptions.h').read_text()
    types = header[header.index('struct pico_hub_subscription {'):header.index('/* Process context')]
    bodies = registry[registry.index('static DEFINE_MUTEX'):] + events[events.index('static bool pico_hub_client_attached_locked'):] + counts[counts.index('int pico_hub_event_ref_locked'):] + callbacks[callbacks.index('static struct pico_hub_video *pico_hub_subscription_parent_locked'):]
    code = prefix + MOCK.replace('/* TYPES */', types).replace('/* BODIES */', bodies)
    out = BASE / 'out/phoenix-kernel-recovery/camera-hub-subscription-callbacks-tests'
    out.mkdir(exist_ok=True)
    (out / 'harness.c').write_text(code)
    subprocess.run(['gcc', '-std=gnu11', '-g', '-O1', '-pthread', '-fsanitize=address,undefined',
                    '-fno-omit-frame-pointer', str(out / 'harness.c'), '-o', str(out / 'test')], check=True)
    result = subprocess.run([str(out / 'test')], capture_output=True, text=True, timeout=30)
    names = ['pico_camera_hub_subscription_callbacks.c', 'pico_camera_hub_subscription_callbacks.h',
             'pico_camera_hub_subscriptions.c', 'pico_camera_hub_subscriptions.h', 'pico_camera_hub_events.c',
             'pico_camera_hub_registry.c', 'pico_camera_hub.h']
    report = {'sources': {DIRECTORY + name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in names},
              'scope': 'Actual registry/event/count/callback bodies with mock V4L2 queues and original callbacks; no actual nodes or device runtime',
              'harness_sha256': hashlib.sha256(code.encode()).hexdigest(), 'exit_code': result.returncode,
              'stdout': result.stdout, 'stderr': result.stderr, 'sanitizers': ['AddressSanitizer', 'UndefinedBehaviorSanitizer'],
              'device_modified': False}
    (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    if result.returncode:
        raise SystemExit(result.returncode)


if __name__ == '__main__':
    main()
