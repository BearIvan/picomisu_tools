"""Execute the actual CDM kthread pool bodies with pthread-backed kthread workers under ASan/UBSan and TSan."""
from pathlib import Path
import hashlib,importlib.util,json,subprocess
BASE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro');SOURCE=BASE/'source/phoenix-kernel-recovery'
D='techpack/camera/drivers/cam_cdm/'
NAMES=[D+'cam_cdm_core_common.c',D+'cam_cdm.h']
FUNCS=['void cam_hw_cdm_kthread_func(','int cam_hw_cdm_queue_work(','int cam_hw_cdm_destory_kthread_workqueue(','int cam_hw_cdm_create_kthread_workqueue(']
MODEL=r'''
#define _GNU_SOURCE
#include <assert.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stddef.h>
#include <errno.h>
#include <unistd.h>
#define CAM_CDM 0
static atomic_int errs;
#define CAM_ERR(...) atomic_fetch_add(&errs,1)
#define GFP_KERNEL 0
#define MAX_ERRNO 4095
#define IS_ERR(p) ((unsigned long)(void *)(p)>=(unsigned long)-MAX_ERRNO)
#define ERR_PTR(e) ((void *)(long)(e))
struct list_head {struct list_head *next,*prev;};
#define LIST_HEAD(n) struct list_head n={&n,&n}
#define container_of(p,t,m) ((t *)((char *)(p)-offsetof(t,m)))
#define list_entry(p,t,m) container_of(p,t,m)
#define list_first_entry(h,t,m) list_entry((h)->next,t,m)
#define list_for_each_entry(p,h,m) for(p=list_first_entry(h,__typeof__(*p),m);&p->m!=(h);p=list_entry(p->m.next,__typeof__(*p),m))
#define list_for_each_entry_safe(p,n,h,m) for(p=list_first_entry(h,__typeof__(*p),m),n=list_entry(p->m.next,__typeof__(*p),m);&p->m!=(h);p=n,n=list_entry(n->m.next,__typeof__(*n),m))
static void INIT_LIST_HEAD(struct list_head *h){h->next=h->prev=h;}
static int list_empty(const struct list_head *h){return h->next==h;}
static void list_add_tail(struct list_head *n,struct list_head *h){n->next=h;n->prev=h->prev;h->prev->next=n;h->prev=n;}
static void list_del(struct list_head *e){e->prev->next=e->next;e->next->prev=e->prev;e->next=(void *)0x100;e->prev=(void *)0x200;}
static void list_splice_init(struct list_head *l,struct list_head *h){if(list_empty(l))return;struct list_head *f=l->next,*a=l->prev,*at=h->next;f->prev=h;h->next=f;a->next=at;at->prev=a;INIT_LIST_HEAD(l);}
typedef pthread_mutex_t spinlock_t;
#define spin_lock_init(l) pthread_mutex_init(l,NULL)
#define spin_lock_irqsave(l,f) do{(void)(f);pthread_mutex_lock(l);}while(0)
#define spin_unlock_irqrestore(l,f) pthread_mutex_unlock(l)
static atomic_int live_alloc,fail_alloc_at=-1,alloc_no;
static void *kzalloc(size_t s,int f){if(atomic_fetch_add(&alloc_no,1)==fail_alloc_at)return NULL;atomic_fetch_add(&live_alloc,1);return calloc(1,s);}
static void *kcalloc(size_t n,size_t s,int f){return kzalloc(n*s,f);}
static void kfree(const void *p){if(!p)return;atomic_fetch_sub(&live_alloc,1);free((void *)p);}
struct work_struct {long pad[4];};
struct cam_hw_info {int id;};
/* pthread-backed kthread_worker */
struct kthread_work;
typedef void (*kthread_work_func_t)(struct kthread_work *);
struct kthread_worker {pthread_t th;pthread_mutex_t m;pthread_cond_t c;struct kthread_work *q[64];int head,tail,stop,busy;void *task;};
struct kthread_work {struct list_head node;kthread_work_func_t func;struct kthread_worker *worker;int canceling;};
static atomic_int workers_live,fail_worker_at=-1,worker_no;
static void *worker_main(void *a){struct kthread_worker *w=a;pthread_mutex_lock(&w->m);for(;;){while(w->head==w->tail&&!w->stop)pthread_cond_wait(&w->c,&w->m);if(w->head==w->tail&&w->stop)break;struct kthread_work *k=w->q[w->head++%64];w->busy=1;pthread_mutex_unlock(&w->m);k->func(k);pthread_mutex_lock(&w->m);w->busy=0;pthread_cond_broadcast(&w->c);}pthread_mutex_unlock(&w->m);return NULL;}
static struct kthread_worker *kthread_create_worker(unsigned f,const char *name){if(atomic_fetch_add(&worker_no,1)==fail_worker_at)return ERR_PTR(-ENOMEM);struct kthread_worker *w=calloc(1,sizeof(*w));pthread_mutex_init(&w->m,NULL);pthread_cond_init(&w->c,NULL);w->task=w;pthread_create(&w->th,NULL,worker_main,w);atomic_fetch_add(&workers_live,1);assert(strlen(name)<64);return w;}
static void kthread_destroy_worker(struct kthread_worker *w){pthread_mutex_lock(&w->m);w->stop=1;pthread_cond_broadcast(&w->c);pthread_mutex_unlock(&w->m);pthread_join(w->th,NULL);assert(w->head==w->tail);free(w);atomic_fetch_sub(&workers_live,1);}
static bool kthread_queue_work(struct kthread_worker *w,struct kthread_work *k){pthread_mutex_lock(&w->m);assert(w->tail-w->head<64);k->worker=w;w->q[w->tail++%64]=k;pthread_cond_broadcast(&w->c);pthread_mutex_unlock(&w->m);return true;}
static void kthread_init_work(struct kthread_work *k,kthread_work_func_t f){memset(k,0,sizeof(*k));INIT_LIST_HEAD(&k->node);k->func=f;}
#define sched_setscheduler cdm_test_setscheduler
static atomic_int setsched;
static int sched_setscheduler(void *task,int policy,const struct sched_param *p){assert(policy==SCHED_FIFO&&p->sched_priority==49);atomic_fetch_add(&setsched,1);return 0;}
/* POOL_TYPES */
'''
MAIN=r'''
static atomic_int ran,running,max_running;static atomic_int gate;
static void work_fn(struct work_struct *w){struct cam_cdm_work_payload *p=container_of(w,struct cam_cdm_work_payload,work);int r=atomic_fetch_add(&running,1)+1;int m;while(r>(m=atomic_load(&max_running))&&!atomic_compare_exchange_weak(&max_running,&m,r));while(atomic_load(&gate))usleep(100);assert(p->irq_status==7);atomic_fetch_sub(&running,1);atomic_fetch_add(&ran,1);kfree(p);}
static struct cam_cdm_work_payload *payload(void){struct cam_cdm_work_payload *p=kzalloc(sizeof(*p),0);p->irq_status=7;return p;}
static struct cam_hw_cdm_kthread_pool pool;
static int free_count(void){int n=0;struct cam_hw_cdm_kthread_node *x;pthread_mutex_lock(&pool.lock);list_for_each_entry(x,&pool.free_list,free_entry)n++;pthread_mutex_unlock(&pool.lock);return n;}
static void *irq(void *a){int i,q=0;for(i=0;i<200;i++){struct cam_cdm_work_payload *p=payload();if(cam_hw_cdm_queue_work(&pool,p,work_fn))q++;else kfree(p);}return (void *)(long)q;}
int main(void){int i;long total=0;pthread_t t[4];
 /* 1. Five RT workers, all idle. */
 assert(!cam_hw_cdm_create_kthread_workqueue(&pool,5,"qcom,cam-cdm"));assert(workers_live==5&&setsched==5&&free_count()==5&&pool.num==5);
 /* 2. Exhaustion: with five works blocked the sixth is refused, the worker count bounds concurrency. */
 atomic_store(&gate,1);for(i=0;i<5;i++)assert(cam_hw_cdm_queue_work(&pool,payload(),work_fn)==1);
 {struct cam_cdm_work_payload *p=payload();assert(cam_hw_cdm_queue_work(&pool,p,work_fn)==0);kfree(p);}assert(errs==1);
 atomic_store(&gate,0);while(atomic_load(&ran)<5)usleep(100);while(free_count()<5)usleep(100);assert(max_running<=5);
 /* 3. Concurrent producers (IRQ-like) never lose a node and never run more than five at once. */
 for(i=0;i<4;i++)pthread_create(&t[i],NULL,irq,NULL);
 for(i=0;i<4;i++){void *r;pthread_join(t[i],&r);total+=(long)r;}
 while(atomic_load(&ran)<5+total)usleep(100);
 while(free_count()<5)usleep(100);
assert(max_running<=5&&total>0);
 /* 4. Teardown with queued work flushes it and frees every node. */
 atomic_store(&gate,1);for(i=0;i<3;i++)assert(cam_hw_cdm_queue_work(&pool,payload(),work_fn));{int before=ran;atomic_store(&gate,0);
 assert(!cam_hw_cdm_destory_kthread_workqueue(&pool));assert(ran==before+3);}assert(!workers_live&&list_empty(&pool.free_list)&&list_empty(&pool.all_list)&&!pool.workers);
 assert(!cam_hw_cdm_destory_kthread_workqueue(&pool));
 /* 5. Failed worker creation cleans up started workers (factory leaked them). */
 fail_worker_at=atomic_load(&worker_no)+2;assert(cam_hw_cdm_create_kthread_workqueue(&pool,5,"x")==-ENOMEM);assert(!workers_live&&list_empty(&pool.all_list));
 fail_worker_at=-1;assert(!cam_hw_cdm_destory_kthread_workqueue(&pool));
 /* 6. Node allocation failure also cleans up. */
 fail_alloc_at=atomic_load(&alloc_no)+3;assert(cam_hw_cdm_create_kthread_workqueue(&pool,5,"y")==-ENOMEM);fail_alloc_at=-1;assert(!workers_live);
 /* 7. Empty pool queueing is refused; NULL pool rejected. */
 assert(!cam_hw_cdm_create_kthread_workqueue(&pool,0,"z"));{struct cam_cdm_work_payload *p=payload();assert(!cam_hw_cdm_queue_work(&pool,p,work_fn));kfree(p);}
 assert(cam_hw_cdm_create_kthread_workqueue(NULL,5,"n")==-EINVAL);
 assert(!live_alloc);
 puts("PASS: five SCHED_FIFO(49) workers, refusal when exhausted, bounded concurrency with concurrent producers, flush+free on teardown, cleanup on partial creation");
 return 0;
}
'''
def main():
    spec=importlib.util.spec_from_file_location('ex',Path(__file__).with_name('test-pico-sensor-mono-hook.py'));ex=importlib.util.module_from_spec(spec);spec.loader.exec_module(ex)
    src=(SOURCE/NAMES[0]).read_text();hdr=(SOURCE/NAMES[1]).read_text()
    types=hdr[hdr.index('struct cam_cdm_work_payload {'):hdr.index('/* enum cam_cdm_bl_cb_type')]
    code=MODEL.replace('/* POOL_TYPES */',types)+'\n'.join(ex.function(src,f) for f in FUNCS)+MAIN
    out=BASE/'out/phoenix-kernel-recovery/cdm-kthread-pool-tests';out.mkdir(exist_ok=True);(out/'harness.c').write_text(code)
    runs={}
    for tag,flags in [('asan',['-fsanitize=address,undefined']),('tsan',['-fsanitize=thread'])]:
        exe=out/('test-'+tag)
        subprocess.run(['gcc','-std=gnu11','-g','-O1','-Wall','-Wno-unused-function',*flags,'-fno-sanitize-recover=all',str(out/'harness.c'),'-o',str(exe),'-lpthread'],check=True)
        # TSan cannot start under WSL's high mmap entropy; run it without ASLR.
        cmd=['setarch',subprocess.check_output(['uname','-m'],text=True).strip(),'-R',str(exe)] if tag=='tsan' else [str(exe)]
        r=subprocess.run(cmd,capture_output=True,text=True,timeout=120)
        runs[tag]={'exit_code':r.returncode,'stdout':r.stdout,'stderr':r.stderr[-4000:]}
    rc=max(v['exit_code'] for v in runs.values())
    report={'sources':{n:hashlib.sha256((SOURCE/n).read_bytes()).hexdigest() for n in NAMES},'harness_sha256':hashlib.sha256(code.encode()).hexdigest(),'exit_code':rc,'runs':runs,
            'scope':'Actual pool bodies and node/pool types from cam_cdm.h; kthread_worker emulated with pthreads (one thread, FIFO queue, flush on destroy), spinlock as mutex, scheduler call checked; real IRQ context, RT scheduling and CDM hardware not exercised.','device_modified':False}
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));raise SystemExit(rc)
if __name__=='__main__':main()
