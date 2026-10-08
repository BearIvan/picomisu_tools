"""Execute the actual binder remote-pid and async-space guard bodies under ASan/UBSan."""
from pathlib import Path
import hashlib,importlib.util,json,subprocess
BASE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro');SOURCE=BASE/'source/phoenix-kernel-recovery'
NAME='drivers/android/binder.c'
FUNCS=['static void binder_remote_pid_add(','static void binder_stat_get_remote_pids(','static int binder_handle_buffer_alloc(']
MODEL=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stddef.h>
typedef int32_t __s32;typedef uint32_t u32;
#define ARRAY_SIZE(a) (sizeof(a)/sizeof((a)[0]))
#define container_of(p,t,m) ((t *)((char *)(p)-offsetof(t,m)))
static int dbg,errs_once;
#define binder_debug(mask,...) (dbg++)
#define pr_err_once(...) (errs_once++)
#define BINDER_DEBUG_PICO 0
#define BINDER_WORK_TRANSACTION 1
#define BINDER_WORK_NODE 7
#define BINDER_REMOTE_PIDS_SCAN 16
#define BINDER_PICO_ASYNC_SPACE_LOW 0xC800
#define BINDER_PICO_ASYNC_SCAN_MAX 29
#define BINDER_PICO_ASYNC_SAME_CODE 26
struct list_head {struct list_head *next,*prev;};
#define list_entry(p,t,m) container_of(p,t,m)
#define list_for_each_entry(p,h,m) for(p=list_entry((h)->next,__typeof__(*p),m);&p->m!=(h);p=list_entry(p->m.next,__typeof__(*p),m))
static void INIT_LIST_HEAD(struct list_head *h){h->next=h->prev=h;}
static void list_add_tail(struct list_head *n,struct list_head *h){n->next=h;n->prev=h->prev;h->prev->next=n;h->prev=n;}
struct hlist_node {struct hlist_node *next;};struct hlist_head {struct hlist_node *first;};
#define hlist_for_each_entry(p,h,m) for(p=(h)->first?container_of((h)->first,__typeof__(*p),m):NULL;p;p=p->m.next?container_of(p->m.next,__typeof__(*p),m):NULL)
struct rb_node {struct rb_node *next;};struct rb_root {struct rb_node *first;};
#define rb_entry(p,t,m) container_of(p,t,m)
static struct rb_node *rb_first(struct rb_root *r){return r->first;}
static struct rb_node *rb_next(struct rb_node *n){return n->next;}
/* lock discipline: no lock taken twice, counts must balance */
static int procs_lock,inner,node_lock,node_inner,alloc_lock,tlocks;
struct mutex {int held;};
static void mutex_lock(void *m){int *h=m;assert(!*h);*h=1;}
static void mutex_unlock(void *m){int *h=m;assert(*h);*h=0;}
typedef struct {int held;} spinlock_t;
static void spin_lock(spinlock_t *l){assert(!l->held);l->held=1;tlocks++;}
static void spin_unlock(spinlock_t *l){assert(l->held);l->held=0;tlocks--;}
struct task_struct {char comm[16];};
struct binder_alloc {struct mutex mutex;size_t free_async_space;};
struct binder_proc {struct hlist_node proc_node;struct rb_root threads;int pid;struct task_struct *tsk;struct binder_alloc alloc;bool is_system_server;int inner_held;};
struct binder_thread {struct binder_proc *proc;struct rb_node rb_node;struct binder_transaction *transaction_stack;int pid;};
struct binder_work {struct list_head entry;int type;};
struct binder_transaction {int debug_id;struct binder_work work;struct binder_thread *from;struct binder_transaction *from_parent;struct binder_proc *to_proc;struct binder_thread *to_thread;struct binder_transaction *to_parent;unsigned code;spinlock_t lock;};
struct binder_node {int lock_held;struct binder_proc *proc;bool has_async_transaction;struct list_head async_todo;u32 pending_max_count_code;};
static struct mutex binder_procs_lock;static struct hlist_head binder_procs;
static void binder_inner_proc_lock(struct binder_proc *p){assert(!p->inner_held);p->inner_held=1;inner++;}
static void binder_inner_proc_unlock(struct binder_proc *p){assert(p->inner_held);p->inner_held=0;inner--;}
static void binder_node_lock(struct binder_node *n){assert(!n->lock_held);n->lock_held=1;node_lock++;}
static void binder_node_unlock(struct binder_node *n){assert(n->lock_held==1);n->lock_held=0;node_lock--;}
static void binder_node_inner_lock(struct binder_node *n){assert(!n->lock_held);n->lock_held=2;node_inner++;}
static void binder_node_inner_unlock(struct binder_node *n){assert(n->lock_held==2);n->lock_held=0;node_inner--;}
struct binder_remote_pids {__s32 pids[10];__s32 count;__s32 pid;};
'''
MAIN=r'''
static struct binder_proc procs[24];static struct binder_thread threads[24];static struct binder_transaction ts[64];static int nts;
static struct task_struct ss={"system_server"},app={"com.app"};
static void addproc(struct binder_proc *p,int pid){memset(p,0,sizeof(*p));p->pid=pid;p->proc_node.next=binder_procs.first;binder_procs.first=&p->proc_node;}
static struct binder_thread *addthread(struct binder_proc *p,struct binder_thread *t,int tid){memset(t,0,sizeof(*t));t->proc=p;t->pid=tid;t->rb_node.next=p->threads.first;p->threads.first=&t->rb_node;return t;}
/* a call from thread a (caller) to thread b (callee): pushed on both stacks */
static struct binder_transaction *call(struct binder_thread *a,struct binder_thread *b){struct binder_transaction *t=&ts[nts++];memset(t,0,sizeof(*t));t->from=a;t->to_proc=b->proc;t->to_thread=b;t->from_parent=a->transaction_stack;a->transaction_stack=t;t->to_parent=b->transaction_stack;b->transaction_stack=t;return t;}
static bool has(struct binder_remote_pids *r,int pid){for(int i=0;i<r->count;i++)if(r->pids[i]==pid)return true;return false;}
static void balanced(void){assert(!procs_lock&&!inner&&!node_lock&&!node_inner&&!tlocks&&!binder_procs_lock.held);}
static struct binder_node node;static struct binder_proc target;
static void queue_async(int n,unsigned code){for(int i=0;i<n;i++){struct binder_transaction *t=&ts[nts++];memset(t,0,sizeof(*t));t->work.type=BINDER_WORK_TRANSACTION;t->code=code;list_add_tail(&t->work.entry,&node.async_todo);}node.has_async_transaction=true;}
static void reset_node(size_t space,struct task_struct *tsk){nts=0;memset(&node,0,sizeof(node));INIT_LIST_HEAD(&node.async_todo);memset(&target,0,sizeof(target));target.tsk=tsk;target.alloc.free_async_space=space;node.proc=&target;}
int main(void){struct binder_remote_pids r;int i;
 /* server A(100) thread 101 calls B(200) thread 201 which calls C(300); D(400) also calls B. */
 addproc(&procs[0],100);addproc(&procs[1],200);addproc(&procs[2],300);addproc(&procs[3],400);addproc(&procs[4],200);
 struct binder_thread *a=addthread(&procs[0],&threads[0],101),*b=addthread(&procs[1],&threads[1],201),*c=addthread(&procs[2],&threads[2],301),*d=addthread(&procs[3],&threads[3],401),*b2=addthread(&procs[1],&threads[4],202);
 struct binder_thread *hw=addthread(&procs[4],&threads[5],203);(void)hw;
 call(a,b);call(b,c);call(d,b2);
 memset(&r,0,sizeof(r));r.pid=200;binder_stat_get_remote_pids(&r,true);balanced();assert(r.count==1&&has(&r,300));
 memset(&r,0,sizeof(r));r.pid=200;binder_stat_get_remote_pids(&r,false);balanced();assert(r.count==2&&has(&r,100)&&has(&r,400)&&r.pid==0);
 memset(&r,0,sizeof(r));r.pid=300;binder_stat_get_remote_pids(&r,false);assert(r.count==1&&has(&r,200));
 memset(&r,0,sizeof(r));r.pid=100;binder_stat_get_remote_pids(&r,true);assert(r.count==1&&has(&r,200));
 memset(&r,0,sizeof(r));r.pid=999;binder_stat_get_remote_pids(&r,true);assert(r.count==0);
 /* dead caller (from == NULL) is skipped; duplicates collapse; more than ten callers capped. */
 ts[1].from=NULL;memset(&r,0,sizeof(r));r.pid=300;binder_stat_get_remote_pids(&r,false);assert(r.count==0);ts[1].from=b;
 for(i=0;i<14;i++){addproc(&procs[5+i],1000+i);call(addthread(&procs[5+i],&threads[6+i],2000+i),c);}
 call(a,c);call(a,c);
 /* the same callee reached by several in-flight calls is reported once */
 memset(&r,0,sizeof(r));r.pid=100;binder_stat_get_remote_pids(&r,true);balanced();assert(r.count==2&&has(&r,200)&&has(&r,300));
 memset(&r,0,sizeof(r));r.pid=300;binder_stat_get_remote_pids(&r,false);balanced();assert(r.count==10&&errs_once==1);
 /* 1. enough async space: allowed and stale refusal cleared */
 reset_node(0x10000,&ss);node.pending_max_count_code=7;assert(!binder_handle_buffer_alloc(&target,true,&node,7));assert(!node.pending_max_count_code);balanced();
 /* 2. low space, not system_server: allowed */
 reset_node(0x100,&app);queue_async(28,7);assert(!binder_handle_buffer_alloc(&target,true,&node,7)&&!target.is_system_server);balanced();
 /* 3. low space, system_server, 26 same-code async queued: refused and remembered */
 reset_node(0x100,&ss);queue_async(26,7);assert(binder_handle_buffer_alloc(&target,true,&node,7)==-1&&node.pending_max_count_code==7&&target.is_system_server);balanced();
 assert(binder_handle_buffer_alloc(&target,true,&node,7)==-1);
 assert(!binder_handle_buffer_alloc(&target,true,&node,8));
 target.alloc.free_async_space=0x20000;assert(!binder_handle_buffer_alloc(&target,true,&node,7)&&!node.pending_max_count_code);balanced();
 /* 4. 25 same-code: allowed */
 reset_node(0x100,&ss);queue_async(25,7);assert(!binder_handle_buffer_alloc(&target,true,&node,7));
 /* 5. same code beyond the first 29 transactions is not counted */
 reset_node(0x100,&ss);queue_async(10,9);queue_async(26,7);assert(!binder_handle_buffer_alloc(&target,true,&node,7));
 /* 6. non-transaction work is skipped */
 reset_node(0x100,&ss);{struct binder_work w={.type=BINDER_WORK_NODE};list_add_tail(&w.entry,&node.async_todo);queue_async(26,7);assert(binder_handle_buffer_alloc(&target,true,&node,7)==-1);}
 /* 7. two-way, missing node or code 0: allowed */
 reset_node(0x100,&ss);queue_async(30,7);assert(!binder_handle_buffer_alloc(&target,false,&node,7)&&!binder_handle_buffer_alloc(&target,true,NULL,7)&&!binder_handle_buffer_alloc(&target,true,&node,0));balanced();
 puts("PASS: remote pids for callers/callees across binder domains, dead caller skipped, dedup and cap at ten; system_server async-space guard refuses a flooding code, clears on recovery, ignores other procs/codes and two-way calls; locks balanced");
 return 0;
}
'''
def main():
    spec=importlib.util.spec_from_file_location('ex',Path(__file__).with_name('test-pico-sensor-mono-hook.py'));ex=importlib.util.module_from_spec(spec);spec.loader.exec_module(ex)
    src=(SOURCE/NAME).read_text()
    code=MODEL+'\n'.join(ex.function(src,f) for f in FUNCS)+MAIN
    out=BASE/'out/phoenix-kernel-recovery/binder-extensions-tests';out.mkdir(exist_ok=True);(out/'harness.c').write_text(code)
    subprocess.run(['gcc','-std=gnu11','-g','-O1','-Wall','-Wno-unused-function','-fsanitize=address,undefined','-fno-sanitize-recover=all',str(out/'harness.c'),'-o',str(out/'test')],check=True)
    r=subprocess.run([str(out/'test')],capture_output=True,text=True,timeout=60)
    report={'sources':{NAME:hashlib.sha256((SOURCE/NAME).read_bytes()).hexdigest()},'harness_sha256':hashlib.sha256(code.encode()).hexdigest(),'exit_code':r.returncode,'stdout':r.stdout,'stderr':r.stderr[-3000:],
            'scope':'Actual binder_remote_pid_add, binder_stat_get_remote_pids and binder_handle_buffer_alloc; binder structs, rb tree, hlist, locks modeled with ordering asserts. ioctl plumbing verified by BUILD_BUG_ON on numbers and by compilation, not executed.','device_modified':False}
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));raise SystemExit(r.returncode)
if __name__=='__main__':main()
