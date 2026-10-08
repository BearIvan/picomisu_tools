"""Execute the actual kgsl priority-shift bodies (dispatcher + drawctxt + rb selection) under ASan/UBSan."""
from pathlib import Path
import hashlib,importlib.util,json,subprocess
BASE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro');SOURCE=BASE/'source/phoenix-kernel-recovery'
M='drivers/gpu/msm/'
NAMES=[M+'adreno_dispatch.c',M+'adreno_drawctxt.c',M+'adreno.h']
MODEL=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stddef.h>
#include <errno.h>
#define container_of(p,t,m) ((t *)((char *)(p)-offsetof(t,m)))
#define IS_ERR(p) ((unsigned long)(void *)(p)>=(unsigned long)-4095)
#define PTR_ERR(p) ((long)(p))
#define ERR_PTR(e) ((void *)(long)(e))
#define GFP_KERNEL 0
#define KGSL_CONTEXT_PRIORITY_MASK 0x0000F000
#define KGSL_CONTEXT_PRIORITY_SHIFT 12
#define KGSL_CONTEXT_PRIORITY_UNDEF 0
#define KGSL_CONTEXT_PRIORITY_HIGH 0x4
#define KGSL_CONTEXT_PRIORITY_MED 0x8
#define ADRENO_CONTEXT_DRAWQUEUE_SIZE 128
#define ADRENO_PRIORITY_MAX_RB_LEVELS 4
static int logs;
#define pr_err_ratelimited(...) (logs++)
#define pr_info_ratelimited(...) (logs++)
/* locks: counted, nesting checked */
static int rt_held,ctx_held,plist_held,ctxlock_held,dprio_held;
struct rt_mutex {int x;};struct mutex {int x;};typedef struct {int x;} spinlock_t;typedef struct {int x;} rwlock_t;
static void rt_mutex_lock(struct rt_mutex *m){assert(!rt_held++);}
static void rt_mutex_unlock(struct rt_mutex *m){assert(rt_held--==1);}
static void mutex_lock(struct mutex *m){assert(!dprio_held++);}
static void mutex_unlock(struct mutex *m){assert(dprio_held--==1);}
static int *which(spinlock_t *l);
static void spin_lock(spinlock_t *l){int *h=which(l);assert(!*h);*h=1;}
static void spin_unlock(spinlock_t *l){int *h=which(l);assert(*h);*h=0;}
static void read_lock(rwlock_t *l){assert(!ctxlock_held++);}
static void read_unlock(rwlock_t *l){assert(ctxlock_held--==1);}
struct plist_node {int prio;struct plist_node *next;bool on;};struct plist_head {struct plist_node *first;};
static bool plist_node_empty(struct plist_node *n){return !n->on;}
static void plist_del(struct plist_node *n,struct plist_head *h){struct plist_node **p=&h->first;while(*p!=n)p=&(*p)->next;*p=n->next;n->on=false;}
static void plist_add(struct plist_node *n,struct plist_head *h){struct plist_node **p=&h->first;while(*p&&(*p)->prio<=n->prio)p=&(*p)->next;n->next=*p;*p=n;n->on=true;}
struct kref {int refcount;};
static void kref_get(struct kref *k){assert(k->refcount>0);k->refcount++;}
/* kgsl model */
struct kgsl_device;struct kgsl_process_private;
struct kgsl_context {unsigned int id;unsigned int priority;unsigned int flags;unsigned long priv;struct kgsl_device *device;struct kgsl_process_private *proc_priv;struct kref refcount;};
struct kgsl_drawobj {struct kgsl_context *context;struct kref refcount;};
struct kgsl_drawobj_sync_event {int type;};
struct kgsl_drawobj_sync {struct kgsl_drawobj base;struct kgsl_drawobj_sync_event *synclist;unsigned int numsyncs;int fence_fd;unsigned int ts_ctx,ts;bool has_ts;};
#define DRAWOBJ(o) (&(o)->base)
struct adreno_ringbuffer {int id;};
struct adreno_context {struct kgsl_context base;spinlock_t lock;struct kgsl_drawobj *drawqueue[ADRENO_CONTEXT_DRAWQUEUE_SIZE];unsigned int drawqueue_head,drawqueue_tail;unsigned int queued;struct plist_node pending;struct adreno_ringbuffer *rb;unsigned int submitted_timestamp;int wq;};
#define ADRENO_CONTEXT(c) container_of(c,struct adreno_context,base)
struct adreno_dispatcher {struct rt_mutex rt_mutex;struct plist_head pending;spinlock_t plist_lock;};
struct kgsl_device {rwlock_t context_lock;int context_idr;struct kgsl_context *ctx_by_id[16];};
struct adreno_device {struct kgsl_device dev;struct adreno_dispatcher dispatcher;struct adreno_ringbuffer ringbuffers[4];unsigned int num_ringbuffers;bool preempt;};
#define ADRENO_DEVICE(d) container_of(d,struct adreno_device,dev)
#define KGSL_DEVICE(a) (&(a)->dev)
struct kgsl_process_private {int pid;char comm[16];struct mutex dprio_lock;int dprio;int refs;};
struct kgsl_device_private {struct kgsl_device *device;};
struct kgsl_ctxprio_shift {unsigned int pid;unsigned int prio;};
struct kgsl_cmd_syncpoint_timestamp {unsigned int context_id;unsigned int timestamp;};
struct kgsl_cmd_syncpoint_fence {int fd;};
static struct adreno_device adev;static struct adreno_context ctxs[6];
static int *which(spinlock_t *l){if(l==&adev.dispatcher.plist_lock)return &plist_held;return &ctx_held;}
static int live_sync,barriers_open,barriers_released,fail_sync_create,fail_fence,fail_ts,fail_barrier,wait_calls,wait_result=1,context_state_err,max_ctx;
static bool runtime_flag;
static int state_calls,fail_state_from;
static long _check_context_state(struct kgsl_context *c){state_calls++;return (fail_state_from&&state_calls>=fail_state_from)?-ENOENT:0;}
static int _check_context_queue(struct adreno_context *d){return d->queued<50;}
static unsigned int _context_queue_wait=10000;
static unsigned long msecs_to_jiffies(unsigned int ms){return ms;}
/* wait: emulate the dispatcher retiring queued work while we sleep */
#define wait_event_interruptible_timeout(wq,cond,t) (wait_calls++,(wait_result>0?(drain_for_wait(),(long)wait_result):(long)wait_result))
static struct adreno_context *waiting_on;static void drain_for_wait(void){waiting_on->queued=10;}
static struct kgsl_drawobj_sync *kgsl_drawobj_sync_create(struct kgsl_device *d,struct kgsl_context *c){if(fail_sync_create)return ERR_PTR(-ENOMEM);struct kgsl_drawobj_sync *s=calloc(1,sizeof(*s));s->base.context=c;s->base.refcount.refcount=1;live_sync++;return s;}
static void *kcalloc(size_t n,size_t s,int f){return calloc(n,s);}
static void kgsl_drawobj_put(struct kgsl_drawobj *o){if(!o||IS_ERR(o))return;assert(o->refcount.refcount>0);if(--o->refcount.refcount==0){struct kgsl_drawobj_sync *s=container_of(o,struct kgsl_drawobj_sync,base);free(s->synclist);free(s);live_sync--;}}
static int kgsl_ctx_barrier(struct kgsl_device *d){if(fail_barrier)return -EBADF;barriers_open++;return 100+barriers_open;}
static struct kgsl_drawobj_sync *fence_waiter[64];
static void kgsl_drawobj_put(struct kgsl_drawobj *o);
/* signalling the barrier runs the sync event callback, which drops the event's reference */
static void kgsl_ctx_barrier_release(int fd){assert(fd>100);barriers_released++;struct kgsl_drawobj_sync *w=fence_waiter[fd-100];fence_waiter[fd-100]=NULL;if(w)kgsl_drawobj_put(&w->base);}
static int drawobj_add_sync_fence(struct kgsl_device *d,struct kgsl_drawobj_sync *s,void *priv){struct kgsl_cmd_syncpoint_fence *f=priv;if(fail_fence)return -EINVAL;s->fence_fd=f->fd;s->numsyncs++;s->base.refcount.refcount++;fence_waiter[f->fd-100]=s;return 0;}
static int drawobj_add_sync_timestamp(struct kgsl_device *d,struct kgsl_drawobj_sync *s,void *priv){struct kgsl_cmd_syncpoint_timestamp *t=priv;if(fail_ts)return -EINVAL;s->ts_ctx=t->context_id;s->ts=t->timestamp;s->has_ts=true;s->numsyncs++;s->base.refcount.refcount++;return 0;}
static bool task_kgsl_ctx_priority_max(void *t){return runtime_flag;}
static void *current;
static bool adreno_is_preemption_enabled(struct adreno_device *a){return a->preempt;}
static struct kgsl_process_private procs[3];
static struct kgsl_process_private *kgsl_process_private_find(int pid){for(int i=0;i<3;i++)if(procs[i].pid==pid){procs[i].refs++;return &procs[i];}return NULL;}
static void kgsl_process_private_put(struct kgsl_process_private *p){assert(p->refs>0);p->refs--;}
static void *idr_get_next(void *idr,int *id){for(;*id<16;(*id)++)if(adev.dev.ctx_by_id[*id])return adev.dev.ctx_by_id[*id];return NULL;}
static int _kgsl_context_get(struct kgsl_context *c){if(c->refcount.refcount<=0)return 0;c->refcount.refcount++;return 1;}
static void kgsl_context_put(struct kgsl_context *c){assert(c->refcount.refcount>1);c->refcount.refcount--;}
static int pid_nr(int p){return p;}
'''
MAIN=r'''
/* the dispatcher would retire queued barrier objects; release them between scenarios */
static void drain(void){for(int i=0;i<6;i++)for(int k=0;k<ADRENO_CONTEXT_DRAWQUEUE_SIZE;k++)if(ctxs[i].drawqueue[k]){struct kgsl_drawobj_sync *o=container_of(ctxs[i].drawqueue[k],struct kgsl_drawobj_sync,base);free(o->synclist);free(o);live_sync--;ctxs[i].drawqueue[k]=NULL;}}
static void fixture(void){drain();memset(&adev,0,sizeof(adev));adev.num_ringbuffers=4;for(int i=0;i<4;i++)adev.ringbuffers[i].id=i;adev.preempt=true;
 memset(ctxs,0,sizeof(ctxs));memset(procs,0,sizeof(procs));procs[0].pid=500;procs[1].pid=600;strcpy(procs[0].comm,"vrapp");
 memset(fence_waiter,0,sizeof(fence_waiter));live_sync=barriers_open=barriers_released=fail_sync_create=fail_fence=fail_ts=fail_barrier=wait_calls=context_state_err=state_calls=fail_state_from=0;wait_result=1;runtime_flag=false;
 for(int i=0;i<6;i++){struct adreno_context *d=&ctxs[i];d->base.id=i+1;d->base.device=&adev.dev;d->base.refcount.refcount=1;d->base.flags=KGSL_CONTEXT_PRIORITY_MED<<12;
  set_context_priority(d);d->rb=adreno_ctx_get_rb(&adev,d);d->pending.prio=d->base.priority;d->submitted_timestamp=40+i;d->base.proc_priv=&procs[i<3?0:1];adev.dev.ctx_by_id[i+1]=&d->base;}}
static long shift(int pid,int prio){struct kgsl_ctxprio_shift p={pid,prio};struct kgsl_device_private dp={&adev.dev};return kgsl_ioctl_ctxprio_shift(&dp,0,&p);}
static void quiet(void){assert(!rt_held&&!ctx_held&&!plist_held&&!ctxlock_held&&!dprio_held);for(int i=0;i<3;i++)assert(!procs[i].refs);for(int i=0;i<6;i++)assert(ctxs[i].base.refcount.refcount==1);}
static struct kgsl_drawobj_sync *head(struct adreno_context *d){return container_of(d->drawqueue[d->drawqueue_head],struct kgsl_drawobj_sync,base);}
int main(void){
 /* 1. shift a process's contexts to HIGH: only its contexts move, barrier at queue head waits for submitted ts */
 fixture();assert(ctxs[0].rb->id==2);
 assert(shift(500,4)==0);quiet();
 for(int i=0;i<3;i++){struct adreno_context *d=&ctxs[i];assert(d->base.priority==4&&((d->base.flags>>12)&0xF)==4&&d->rb->id==1&&d->queued==1&&d->drawqueue_head==127);
  struct kgsl_drawobj_sync *s=head(d);assert(s->has_ts&&s->ts==d->submitted_timestamp&&s->ts_ctx==d->base.id&&s->numsyncs==2&&s->base.refcount.refcount==2);}
 for(int i=3;i<6;i++)assert(ctxs[i].base.priority==8&&!ctxs[i].queued);
 assert(barriers_open==3&&barriers_released==3&&procs[0].dprio==4);
 /* 2. back to MED: second barrier also goes in front, plist reordered for a pending context */
 ctxs[0].pending.on=false;plist_add(&ctxs[0].pending,&adev.dispatcher.pending);plist_add(&ctxs[3].pending,&adev.dispatcher.pending);assert(adev.dispatcher.pending.first==&ctxs[0].pending);
 assert(shift(500,8)==0);quiet();assert(ctxs[0].queued==2&&ctxs[0].drawqueue_head==126&&ctxs[0].base.priority==8&&ctxs[0].rb->id==2&&ctxs[0].pending.prio==8);
 assert(adev.dispatcher.pending.first==&ctxs[3].pending||adev.dispatcher.pending.first->prio==8);
 /* 2b. a boosted context overtakes an earlier pending context in the dispatcher order */
 fixture();plist_add(&ctxs[3].pending,&adev.dispatcher.pending);plist_add(&ctxs[0].pending,&adev.dispatcher.pending);assert(adev.dispatcher.pending.first==&ctxs[3].pending);
 assert(shift(500,4)==0);quiet();assert(adev.dispatcher.pending.first==&ctxs[0].pending&&ctxs[0].pending.prio==4&&ctxs[0].pending.next==&ctxs[3].pending);
 /* 3. illegal prio / pid */
 fixture();assert(shift(500,3)==-EINVAL&&shift(500,16)==-EINVAL&&shift(999,4)==-ESRCH);quiet();assert(!barriers_open);
 /* 4. runtime context refuses (priority 0) and dprio is not stored */
 fixture();ctxs[1].base.priority=0;assert(shift(500,4)==-EPERM);quiet();assert(procs[0].dprio==0);
 /* 5. HIGH from a task with the max flag becomes runtime priority 0 (factory set_context_priority) */
 fixture();runtime_flag=true;assert(shift(500,4)==0);assert(ctxs[0].base.priority==0&&ctxs[0].rb->id==0);quiet();
 /* 6a. context already invalid: nothing is created or changed */
 fixture();fail_state_from=1;assert(shift(500,4)==0);quiet();assert(!ctxs[0].queued&&ctxs[0].base.priority==8&&!barriers_open&&!live_sync);
 /* 6b. context becomes invalid before queueing: factory still changes its priority, no barrier queued, barrier released */
 fixture();fail_state_from=2;assert(shift(500,4)==0);quiet();
 assert(ctxs[0].base.priority==4&&!ctxs[0].queued&&barriers_open==1&&barriers_released==1&&!live_sync);
 assert(ctxs[1].base.priority==8&&ctxs[2].base.priority==8);
 /* 7. full queue waits for the dispatcher, then queues */
 fixture();ctxs[0].queued=127;ctxs[0].drawqueue_head=5;waiting_on=&ctxs[0];assert(shift(500,4)==0);quiet();assert(wait_calls==1&&ctxs[0].queued==11&&ctxs[0].drawqueue_head==4);
 /* 8. wait timeout: no priority change for that context, barrier released, refs balanced */
 fixture();ctxs[0].queued=127;waiting_on=&ctxs[0];wait_result=0;assert(shift(500,4)==0);quiet();assert(ctxs[0].base.priority==8&&ctxs[1].base.priority==4&&barriers_released==barriers_open);
 /* 9. timestamp syncpoint failure after queueing: no priority change, queued barrier still owned by the queue */
 fixture();fail_ts=1;assert(shift(500,4)==0);quiet();assert(ctxs[0].base.priority==8&&ctxs[0].queued==1&&head(&ctxs[0])->base.refcount.refcount==1);
 /* 10. fence / barrier / sync object failures leave everything untouched */
 fixture();fail_fence=1;assert(shift(500,4)==0);quiet();assert(!ctxs[0].queued&&ctxs[0].base.priority==8&&!live_sync);
 fixture();fail_barrier=1;assert(shift(500,4)==0);quiet();assert(!live_sync&&!barriers_released);
 fixture();fail_sync_create=1;assert(shift(500,4)==0);quiet();
 /* 11. without preemption every context stays on rb 0 */
 fixture();adev.preempt=false;assert(shift(500,4)==0);assert(ctxs[0].rb->id==0);quiet();
 drain();assert(!live_sync);
 puts("PASS: priority shift moves only the target's contexts, barrier at queue head on the last submitted timestamp, rb/plist updated, runtime refusal, full-queue wait/timeout, invalid context, failure paths release barriers and balance refs");
 return 0;
}
'''
def main():
    spec=importlib.util.spec_from_file_location('ex',Path(__file__).with_name('test-pico-sensor-mono-hook.py'));ex=importlib.util.module_from_spec(spec);spec.loader.exec_module(ex)
    disp=(SOURCE/NAMES[0]).read_text();ctx=(SOURCE/NAMES[1]).read_text();adr=(SOURCE/NAMES[2]).read_text()
    bodies='\n'.join([ex.function(adr,'static inline struct adreno_ringbuffer *adreno_ctx_get_rb('),
                      ex.function(ctx,'void set_context_priority(struct adreno_context *drawctxt)'),
                      ex.function(disp,'static bool is_runtime_context('),ex.function(disp,'static int kgsl_set_prio('),
                      ex.function(disp,'long kgsl_ioctl_ctxprio_shift(')])
    code=MODEL+bodies+MAIN
    out=BASE/'out/phoenix-kernel-recovery/kgsl-ctxprio-tests';out.mkdir(exist_ok=True);(out/'harness.c').write_text(code)
    subprocess.run(['gcc','-std=gnu11','-g','-O1','-Wall','-Wno-unused-function','-Wno-unused-variable','-fsanitize=address,undefined','-fno-sanitize-recover=all',str(out/'harness.c'),'-o',str(out/'test')],check=True)
    r=subprocess.run([str(out/'test')],capture_output=True,text=True,timeout=60)
    report={'sources':{n:hashlib.sha256((SOURCE/n).read_bytes()).hexdigest() for n in NAMES},'harness_sha256':hashlib.sha256(code.encode()).hexdigest(),'exit_code':r.returncode,'stdout':r.stdout,'stderr':r.stderr[-3000:],
            'scope':'Actual kgsl_set_prio, kgsl_ioctl_ctxprio_shift, is_runtime_context, set_context_priority and adreno_ctx_get_rb; sync objects, barrier fences, waits, locks, idr and plist modeled. kgsl_ctx_barrier/release and drawobj sync plumbing verified by compilation, not executed; no GPU.','device_modified':False}
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));raise SystemExit(r.returncode)
if __name__=='__main__':main()
