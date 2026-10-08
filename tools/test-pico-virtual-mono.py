"""Exercise recovered function bodies with mocked VB2/usercopy boundaries.

These tests check dispatch, private payloads, mapping and error propagation.
They do not establish real VB2 or hardware operation. The arm64 build checks
real kernel layouts separately; this harness runs actual source bodies.
"""
from pathlib import Path
import hashlib
import json
import subprocess

BASE = Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro')
SOURCE = BASE / 'source/phoenix-kernel-recovery/techpack/camera/drivers/cam_core'

HARNESS = r'''
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <pthread.h>
#include <unistd.h>
#include <stdatomic.h>
#include "pico_virtual_mono.h"
typedef uint32_t u32;
typedef atomic_int atomic_t;
#define __user
#define ENOIOCTLCMD 515
#include "cam_defs.h"


#define GFP_KERNEL 0
#define VB2_USERPTR 2
#define VB2_BUF_STATE_ACTIVE 5
#define VB2_BUF_STATE_DONE 6
#define atomic_set(p,n) atomic_store(p,n)
#define atomic_inc(p) atomic_fetch_add(p,1)
#define atomic_dec(p) atomic_fetch_sub(p,1)
#define atomic_read(p) atomic_load(p)
#define u64_to_user_ptr(p) ((void *)(uintptr_t)(p))
struct mutex { pthread_mutex_t value; };
static void mutex_init(struct mutex *m) { assert(!pthread_mutex_init(&m->value,0)); }
static void mutex_lock(struct mutex *m) { assert(!pthread_mutex_lock(&m->value)); }
static void mutex_unlock(struct mutex *m) { assert(!pthread_mutex_unlock(&m->value)); }
typedef int wait_queue_head_t;
#define wait_event(w,c) do { while (!(c)) usleep(1000); } while(0)
#define wake_up_all(w) ((void)0)
struct list { struct list *next, *prev; };
#define INIT_LIST_HEAD(l) ((l)->next=(l)->prev=(l))
struct device { int dummy; };
struct platform_device { struct device dev; };
struct cam_subdev { int dummy; };

struct v4l2_subdev { void *dev_priv; };
#define v4l2_get_subdevdata(sd) ((sd)->dev_priv)
enum dma_data_direction { DMA_NONE };
struct vb2_queue;
struct vb2_buffer { struct list queued_entry; int state; struct vb2_queue *queue; };
struct vb2_mem_ops {
 void *(*get_userptr)(struct device *, unsigned long, unsigned long, enum dma_data_direction);
 void (*put_userptr)(void *);
};
struct vb2_ops {
 int (*queue_setup)(struct vb2_queue *,unsigned *,unsigned *,unsigned *,struct device **);
 void (*wait_prepare)(struct vb2_queue *), (*wait_finish)(struct vb2_queue *);
 int (*buf_init)(struct vb2_buffer *);
 int (*start_streaming)(struct vb2_queue *,unsigned);
 void (*stop_streaming)(struct vb2_queue *), (*buf_queue)(struct vb2_buffer *);
};
struct vb2_queue {
 unsigned type, io_modes, timestamp_flags;
 const struct vb2_ops *ops; const struct vb2_mem_ops *mem_ops;
 void *drv_priv; struct mutex *lock;
 struct vb2_buffer *bufs[8]; bool live, streaming; unsigned count, done;
 pthread_cond_t ready;
};
static unsigned allocations, frees, warnings, init_calls, release_calls;
static int fail_alloc, fail_copy, fail_init_at, vb2_error;
static struct vb2_queue *last_queue;
static void *kmalloc(size_t n,int flags) {
 if(fail_alloc) return 0;
 void *p=malloc(n); assert(p); allocations++; return p;
}
static void kfree(void *p) { if(p) { frees++; free(p); } }
#define dev_warn(...) (warnings++)
struct radix_tree_root { void *values[8]; unsigned long keys[8]; };
struct radix_tree_iter { unsigned long index; };
static void *radix_tree_lookup(struct radix_tree_root *r,unsigned long key) {
 for(unsigned i=0;i<8;i++) if(r->values[i] && r->keys[i]==key) return r->values[i];
 return 0;
}
static int radix_tree_insert(struct radix_tree_root *r,unsigned long key,void *p) {
 if(radix_tree_lookup(r,key)) return -EEXIST;
 for(unsigned i=0;i<8;i++) if(!r->values[i]) { r->values[i]=p;r->keys[i]=key;return 0; }
 return -ENOSPC;
}
/* Iterator uses the real key for deletion, separately from array position. */
#undef radix_tree_for_each_slot
#define radix_tree_for_each_slot(slot,r,it,start) \
 for(unsigned si=0;si<8;si++) \
  if(((slot)=&(r)->values[si]), ((it)->index=(r)->keys[si]), *(slot))
static void *radix_tree_delete(struct radix_tree_root *r,unsigned long key) {
 for(unsigned i=0;i<8;i++) if(r->values[i] && r->keys[i]==key) {
  void *p=r->values[i];r->values[i]=0;return p;
 } return 0;
}
static unsigned long copy_from_user(void *to,const void *from,size_t n) {
 if(fail_copy || !from) return n; memcpy(to,from,n);return 0;
}
static unsigned long copy_to_user(void *to,const void *from,size_t n) {
 if(fail_copy || !to) return n;memcpy(to,from,n);return 0;
}
static void vb2_ops_wait_prepare(struct vb2_queue *q) { mutex_unlock(q->lock); }
static void vb2_ops_wait_finish(struct vb2_queue *q) { mutex_lock(q->lock); }
static int vb2_queue_init(struct vb2_queue *q) {
 init_calls++;if(init_calls==fail_init_at) return -ENOMEM;
 q->live=true;assert(!pthread_cond_init(&q->ready,0));return 0;
}
static void vb2_queue_release(struct vb2_queue *q) {
 assert(q->live);for(unsigned i=0;i<8;i++) {free(q->bufs[i]);q->bufs[i]=0;}
 assert(!pthread_cond_destroy(&q->ready));q->live=false;release_calls++;
}
static int vb2_reqbufs(struct vb2_queue *q,struct v4l2_requestbuffers *r) {
 last_queue=q;if(vb2_error) return vb2_error;
 assert(q->live);if(r->count>8) r->count=8;
 q->count=r->count;for(unsigned i=0;i<r->count;i++) {
 if(!q->bufs[i]) {q->bufs[i]=calloc(1,sizeof(*q->bufs[i]));q->bufs[i]->queue=q;}
 } return 0;
}
static int vb2_qbuf(struct vb2_queue *q,struct v4l2_buffer *b) {
 last_queue=q;if(vb2_error) return vb2_error;
 if(b->index>=q->count) return -EINVAL;
 q->bufs[b->index]->state=q->streaming?VB2_BUF_STATE_ACTIVE:3;return 0;
}
static void vb2_buffer_done(struct vb2_buffer *vb,int state) {
 vb->state=state;vb->queue->done++;pthread_cond_broadcast(&vb->queue->ready);
}
static int vb2_dqbuf(struct vb2_queue *q,struct v4l2_buffer *b,bool nonblock) {
 last_queue=q;if(vb2_error) return vb2_error;
 assert(!nonblock);
 while(q->streaming && !q->done) pthread_cond_wait(&q->ready,&q->lock->value);
 if(!q->streaming) return -EINVAL;
 q->done--;b->sequence=123;return 0;
}
static int vb2_streamon(struct vb2_queue *q,unsigned type) {
 last_queue=q;if(vb2_error) return vb2_error;
 if(type!=q->type) return -EINVAL;
 q->streaming=true;return 0;
}
static int vb2_streamoff(struct vb2_queue *q,unsigned type) {
 last_queue=q;if(vb2_error) return vb2_error;
 if(type!=q->type) return -EINVAL;
 q->streaming=false;pthread_cond_broadcast(&q->ready);return 0;
}
/* SOURCE_BODIES */
static long call(struct v4l2_subdev *sd,u32 op,void *p,u32 n) {
 struct cam_control c={.op_code=op,.size=n,.handle=(uintptr_t)p};
 return virtual_mono_subdev_ioctl(sd,VIDIOC_CAM_CONTROL,&c);
}
struct dequeue { struct v4l2_subdev *sd; long result; };
static void *dequeue_thread(void *arg) {
 struct dequeue *d=arg;struct pico_mono_buffer b={0};
 d->result=call(d->sd,PICO_MONO_DQBUF,&b,sizeof(b));return 0;
}
int main(void) {
 struct pico_mono mono={0};struct platform_device dev={0};
 struct v4l2_subdev sd={.dev_priv=&mono};mono.pdev=&dev;
 mutex_init(&mono.mutex);mutex_init(&mono.hal.mutex);mutex_init(&mono.camx.mutex);
 struct cam_control c={.op_code=PICO_MONO_QBUF,.size=96,.handle=1};
 assert(virtual_mono_subdev_ioctl(&sd,1,&c)==-EINVAL);
 assert(virtual_mono_subdev_ioctl(&sd,VIDIOC_CAM_CONTROL,0)==-EINVAL);
 c.handle=0;assert(virtual_mono_subdev_ioctl(&sd,VIDIOC_CAM_CONTROL,&c)==-EINVAL);
 assert(call(&sd,999,&c,0)==-ENOIOCTLCMD);
 struct pico_mono_buffer b={0};b.buffer.m.userptr=0x123456789abcUL;
 assert(call(&sd,PICO_MONO_QBUF,&b,88)==-EINVAL);
 assert(call(&sd,PICO_MONO_QBUF,&b,96)==-EINVAL);
 fail_init_at=2;
 assert(call(&sd,CAM_ACQUIRE_DEV,&c,0)==-ENOMEM);
 assert(!mono.initialized && release_calls==1 && !mono.hal.queue.live);
 fail_init_at=0;
 assert(!call(&sd,CAM_ACQUIRE_DEV,&c,0));
 assert(call(&sd,CAM_ACQUIRE_DEV,&c,0)==-EBUSY);
 assert(mono.hal.queue.drv_priv==&mono && mono.camx.queue.drv_priv==&mono);
 assert(mono.hal.queue.io_modes==VB2_USERPTR);
 struct pico_mono_requestbuffers r={.request={.count=4,.type=2,.memory=V4L2_MEMORY_USERPTR}};
 assert(!call(&sd,PICO_MONO_REQBUFS,&r,24));assert(last_queue==&mono.hal.queue);
 r.is_camx=1;assert(!call(&sd,PICO_MONO_REQBUFS,&r,24));assert(last_queue==&mono.camx.queue);
 struct pico_mono_stream s={.type=2};
 assert(!call(&sd,PICO_MONO_STREAMON,&s,8));assert(mono.streaming_hal);
 s.is_camx=1;assert(!call(&sd,PICO_MONO_STREAMON,&s,8));assert(mono.streaming_camx);
 b.buffer.index=2;assert(!call(&sd,PICO_MONO_QBUF,&b,96));
 assert(last_queue==&mono.hal.queue && mono.hal.queue.bufs[2]->state==VB2_BUF_STATE_DONE);
 b.buffer.index=0;assert(!call(&sd,PICO_MONO_QBUF,&b,96));assert(b.buffer.index==2);
 b.is_camx=1;b.buffer.index=1;assert(!call(&sd,PICO_MONO_QBUF,&b,96));
 assert(last_queue==&mono.camx.queue && b.buffer.index==1);
 assert(!call(&sd,PICO_MONO_DQBUF,&b,96));assert(b.buffer.sequence==123);
 vb2_error=-EIO;assert(call(&sd,PICO_MONO_QBUF,&b,96)==-EIO);
 assert(call(&sd,PICO_MONO_REQBUFS,&r,24)==-EIO);vb2_error=0;
 fail_copy=1;assert(call(&sd,PICO_MONO_QBUF,&b,96)==-EFAULT);fail_copy=0;
 fail_alloc=1;b.buffer.m.userptr=0x76543210;b.buffer.index=3;
 assert(!call(&sd,PICO_MONO_QBUF,&b,96));assert(warnings==1);fail_alloc=0;
 /* Drain HAL, then release while a real host thread blocks in mock VB2. */
 mono.hal.queue.done=0;
 pthread_t thread;struct dequeue d={.sd=&sd};
 assert(!pthread_create(&thread,0,dequeue_thread,&d));
 unsigned polls=0;while(!atomic_read(&mono.operation_hal)) {usleep(1000);assert(++polls<5000);}
 u32 acquisition[6]={41,42,1,0,0,0};
 assert(pico_memento_mono_rollback(&sd,0x10010,CAM_STOP_DEV,acquisition,24)==-EINVAL);
 assert(pico_memento_mono_rollback(&sd,0x10001,CAM_RELEASE_DEV,acquisition,24)==-EINVAL);
 assert(pico_memento_mono_rollback(&sd,0x10010,CAM_RELEASE_DEV,acquisition,8)==-EINVAL);
 assert(!pico_memento_mono_rollback(&sd,0x10010,CAM_RELEASE_DEV,acquisition,24));
 assert(!pthread_join(thread,0));assert(d.result==-EINVAL);
 assert(!mono.initialized && allocations==frees);
 assert(!call(&sd,CAM_RELEASE_DEV,0,0));
 assert(call(&sd,PICO_MONO_QBUF,&b,96)==-EINVAL);
 assert(CAM_RELEASE_DEV==0x106 && CAM_CONFIG_DEV==0x105);
 assert(call(&sd,CAM_CONFIG_DEV,&c,0)==-ENOIOCTLCMD);
 assert(!call(&sd,CAM_ACQUIRE_DEV,&c,0));assert(!call(&sd,CAM_RELEASE_DEV,0,0));
 assert(!pthread_mutex_destroy(&mono.mutex.value));
 assert(!pthread_mutex_destroy(&mono.hal.mutex.value));
 assert(!pthread_mutex_destroy(&mono.camx.mutex.value));
 puts("PASS: dispatch, dual queues, mapping, faults, rollback, blocked dequeue release");
}
'''


def main():
    source = (SOURCE / 'pico_virtual_mono.c').read_text()
    bodies = source[source.index('struct pico_mono_queue {'):source.index('#ifdef CONFIG_COMPAT')]
    out = BASE / 'out/phoenix-kernel-recovery/virtual-mono-tests'
    out.mkdir(exist_ok=True)
    harness = out / 'harness.c'
    harness.write_text(HARNESS.replace('/* SOURCE_BODIES */', bodies))
    compiler = ['gcc', '-std=gnu11', '-g', '-O1', '-pthread', '-fsanitize=address,undefined',
                '-fno-omit-frame-pointer', '-I' + str(SOURCE), '-I' + str(SOURCE.parents[1] / 'include/uapi/media'), str(harness), '-o', str(out / 'test')]
    subprocess.run(compiler, check=True)
    result = subprocess.run([str(out / 'test')], capture_output=True, text=True, timeout=30)
    uapi = SOURCE.parents[1] / 'include/uapi/media/cam_defs.h'
    report = {'source_sha256': hashlib.sha256(source.encode()).hexdigest(),
              'uapi_source': 'techpack/camera/include/uapi/media/cam_defs.h',
              'uapi_source_sha256': hashlib.sha256(uapi.read_bytes()).hexdigest(),
              'mono_release_opcode': 0x106,
              'memento_mono_rollback_tested': True,
              'scope': 'Actual recovered function bodies with mocked VB2, radix tree and usercopy; not a real kernel runtime',
              'sanitizers': ['AddressSanitizer', 'UndefinedBehaviorSanitizer'],
              'exit_code': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr,
              'device_modified': False}
    (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    if result.returncode:
        raise SystemExit(result.returncode)


if __name__ == '__main__':
    main()
