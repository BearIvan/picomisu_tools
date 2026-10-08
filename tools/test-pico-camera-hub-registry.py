"""Test the real registry function bodies with native host mutex/list mocks.

Checks selection, parent ownership, duplicate protection, detach and lock
contracts. No V4L2 registration, device node, or camera runtime is mocked as
successful by this registry test.
"""
from pathlib import Path
import hashlib
import json
import subprocess

BASE = Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro')
RELATIVE = 'techpack/camera/drivers/cam_core/pico_camera_hub_registry.c'

HARNESS = r'''
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <pthread.h>
#include <stdatomic.h>
#include <unistd.h>
struct list_head {struct list_head *next,*prev;};
#define LIST_HEAD(n) struct list_head n={&(n),&(n)}
#define INIT_LIST_HEAD(n) ((n)->next=(n)->prev=(n))
#define container_of(p,t,m) ((t *)((char *)(p)-offsetof(t,m)))
#define list_for_each_entry(p,h,m) \
 for(struct list_head *cursor=(h)->next;cursor!=(h) && ((p)=container_of(cursor,__typeof__(*(p)),m),1);cursor=cursor->next)
static void list_add(struct list_head *node,struct list_head *head) {
 node->next=head->next;node->prev=head;head->next->prev=node;head->next=node;
}
static void list_del_init(struct list_head *node) {
 node->next->prev=node->prev;node->prev->next=node->next;INIT_LIST_HEAD(node);
}
static bool list_empty(struct list_head *head) {return head->next==head;}
struct mutex {pthread_mutex_t value;};
#define DEFINE_MUTEX(n) struct mutex n={PTHREAD_MUTEX_INITIALIZER}
static _Thread_local unsigned held;
static void mutex_lock(struct mutex *m) {assert(!held);assert(!pthread_mutex_lock(&m->value));held++;}
static void mutex_unlock(struct mutex *m) {assert(held==1);held--;assert(!pthread_mutex_unlock(&m->value));}
#define lockdep_assert_held(m) assert(held==1)
#define spin_lock_init(p) (*(p)=0)
struct video_device {int marker;};
struct v4l2_subdev {int marker;};
struct pico_hub_video {
	void *reserved_224;
 struct video_device *original,*shadow;struct list_head registry,subdevices,clients,events;int event_lock;
};
struct pico_hub_subdevice {
 struct v4l2_subdev *original,*shadow;struct list_head registry,clients;bool multi_client;const struct v4l2_file_operations *original_fops;struct {int marker;} fops;struct file *shared_file;
};
#define WRITE_ONCE(x,v) ((x)=(v))
typedef unsigned int u32;
/* OWNED_SUBDEVICE_MOCKS */
static bool pico_hub_subdevice_relay_busy_locked(struct pico_hub_subdevice *e) {return false;}
static bool pico_hub_subdevice_detach_ready_locked(struct pico_hub_subdevice *e) {return true;}
/* SOURCE */
static struct v4l2_subdev original_sd={77},shadow_sd={88};
static atomic_bool stop;
static atomic_uint visits;
static atomic_uint matches;
static void *reader(void *arg) {
 while(!atomic_load(&stop)) {
  struct pico_hub_video *parent;struct pico_hub_subdevice *entry;
  pico_hub_registry_lock();
  pico_hub_find_subdevice_owner_locked(&shadow_sd,&parent,&entry);
  if(entry) {assert(parent && entry->original->marker==77);assert(entry->shadow->marker==88);atomic_fetch_add(&matches,1);}
  else assert(!parent);
  pico_hub_registry_unlock();atomic_fetch_add(&visits,1);
 }return 0;
}
int main(void) {
 struct video_device video[6]={{1},{2},{3},{4},{5},{6}};
 struct pico_hub_video first={.original=&video[0],.shadow=&video[1]};
 struct pico_hub_video second={.original=&video[2],.shadow=&video[3]};
 struct pico_hub_video absent={.original=&video[4],.shadow=&video[5]};
 struct pico_hub_subdevice child={.original=&original_sd,.shadow=&shadow_sd};
 struct pico_hub_video *owner=(void *)1;struct pico_hub_subdevice *found=(void *)1;
 pico_hub_registry_lock();
 assert(!pico_hub_find_video_locked(0,true));
 pico_hub_find_subdevice_owner_locked(&original_sd,&owner,&found);assert(!owner && !found);
 assert(pico_hub_remove_video_locked(&first)==-ENOENT);
 assert(pico_hub_add_video_locked(0)==-EINVAL);
 struct pico_hub_video invalid={0};assert(pico_hub_add_video_locked(&invalid)==-EINVAL);
 assert(!pico_hub_add_video_locked(&first));assert(!pico_hub_add_video_locked(&second));
 assert(pico_hub_add_video_locked(&first)==-EEXIST);
 struct pico_hub_video duplicate={.original=&video[1],.shadow=&video[5]};
 assert(pico_hub_add_video_locked(&duplicate)==-EEXIST);
 assert(pico_hub_find_video_locked(&video[0],false)==&first);
 assert(!pico_hub_find_video_locked(&video[1],false));
 assert(pico_hub_find_video_locked(&video[1],true)==&first);
 assert(pico_hub_find_video_locked(&video[2],true)==&second);
 assert(!pico_hub_find_video_locked(&video[4],true));
 assert(pico_hub_add_subdevice_locked(&absent,&child)==-ENOENT);
 assert(pico_hub_add_subdevice_locked(&first,0)==-EINVAL);
 assert(!pico_hub_add_subdevice_locked(&first,&child));
 assert(pico_hub_add_subdevice_locked(&second,&child)==-EEXIST);
 struct pico_hub_subdevice duplicate_child={.original=&shadow_sd,.shadow=&original_sd};
 assert(pico_hub_add_subdevice_locked(&second,&duplicate_child)==-EEXIST);
 assert(pico_hub_find_subdevice_locked(&first,&original_sd,false)==&child);
 assert(!pico_hub_find_subdevice_locked(&first,&shadow_sd,false));
 assert(pico_hub_find_subdevice_locked(&first,&shadow_sd,true)==&child);
 assert(!pico_hub_find_subdevice_locked(&second,&original_sd,true));
 pico_hub_find_subdevice_owner_locked(&shadow_sd,&owner,&found);assert(owner==&first && found==&child);
 pico_hub_find_subdevice_owner_locked(&original_sd,0,0);
 assert(pico_hub_remove_video_locked(&first)==-EBUSY);
 assert(pico_hub_remove_subdevice_locked(&second,&child)==-ENOENT);
 assert(!pico_hub_remove_subdevice_locked(&first,&child));
 assert(pico_hub_remove_subdevice_locked(&first,&child)==-ENOENT);
 pico_hub_find_subdevice_owner_locked(&shadow_sd,&owner,&found);assert(!owner && !found);
 pico_hub_registry_unlock();
 /* Concurrent lookup/borrow/use versus detach/free, honoring the API lock. */
 pthread_t thread;assert(!pthread_create(&thread,0,reader,0));
 for(unsigned n=0;n<1000;n++) {
  struct pico_hub_subdevice *entry=calloc(1,sizeof(*entry));assert(entry);
  entry->original=&original_sd;entry->shadow=&shadow_sd;
  pico_hub_registry_lock();assert(!pico_hub_add_subdevice_locked(&first,entry));pico_hub_registry_unlock();
  if(!n) {
   unsigned polls=0;
   while(!atomic_load(&matches)) {usleep(1000);assert(++polls<5000);}
  }
  pico_hub_registry_lock();assert(!pico_hub_remove_subdevice_locked(&first,entry));free(entry);pico_hub_registry_unlock();
 }
 atomic_store(&stop,true);assert(!pthread_join(thread,0));
 assert(atomic_load(&visits)>0 && atomic_load(&matches)>0);
 pico_hub_registry_lock();assert(!pico_hub_remove_video_locked(&first));assert(!pico_hub_remove_video_locked(&second));
 assert(!pico_hub_find_video_locked(&video[1],true));
 assert(list_empty(&pico_hub_videos));pico_hub_registry_unlock();
 puts("PASS: original/shadow selectors, parent ownership, duplicate rejection, detach, 1000 concurrent attach/detach/free cycles");
}
'''


def main():
    source = (BASE / 'source/phoenix-kernel-recovery' / RELATIVE).read_text()
    body = source[source.index('static DEFINE_MUTEX'):]
    out = BASE / 'out/phoenix-kernel-recovery/camera-hub-registry-tests'
    out.mkdir(exist_ok=True)
    (out / 'harness.c').write_text(HARNESS.replace('/* SOURCE */', body))
    subprocess.run(['gcc', '-std=gnu11', '-g', '-O1', '-pthread', '-fsanitize=address,undefined',
                    '-fno-omit-frame-pointer', str(out / 'harness.c'), '-o', str(out / 'test')], check=True)
    result = subprocess.run([str(out / 'test')], capture_output=True, text=True, timeout=30)
    report = {'source_sha256': hashlib.sha256(source.encode()).hexdigest(),
              'scope': 'Actual registry bodies with host lists/mutexes; caller holds lock while using borrowed pointers; no V4L2 runtime',
              'exit_code': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr,
              'sanitizers': ['AddressSanitizer', 'UndefinedBehaviorSanitizer'], 'device_modified': False}
    (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    if result.returncode:
        raise SystemExit(result.returncode)


if __name__ == '__main__':
    main()
