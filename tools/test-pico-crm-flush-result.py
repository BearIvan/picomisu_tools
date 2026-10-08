"""Actual flush caller/worker and queue ownership with modeled scheduling."""
from pathlib import Path
import hashlib,json,re,subprocess,importlib.util
spec=importlib.util.spec_from_file_location('ex',Path(__file__).with_name('test-pico-sensor-mono-hook.py'));ex=importlib.util.module_from_spec(spec);spec.loader.exec_module(ex)
BASE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro');SOURCE=BASE/'source/phoenix-kernel-recovery';D='techpack/camera/drivers/cam_req_mgr/'
NAMES=[D+n for n in ['cam_req_mgr_core.c','cam_req_mgr_workq.c','cam_req_mgr_workq.h','pico_crm_flush_result.inc','cam_req_mgr_interface.h']]+['techpack/camera/include/uapi/media/cam_req_mgr.h']
MODEL=r'''
#include <assert.h>
#include <stdint.h>
#include <stdlib.h>
#include <stdbool.h>
#include <stddef.h>
#include <string.h>
#include <stdio.h>
#include <errno.h>
#define CAM_ERR(...)
#define CAM_WARN(...)
#define CAM_DBG(...)
#define CAM_INFO(...)
#define trace_cam_flush_req(...)
#define CAM_REQ_MGR_FLUSH_TYPE_ALL 0
#define CAM_REQ_MGR_FLUSH_TYPE_CANCEL_REQ 1
#define CAM_REQ_MGR_FLUSH_TYPE_MAX 2
#define CRM_SLOT_STATUS_REQ_PENDING 1
#define CRM_SLOT_STATUS_REQ_APPLIED 2
#define CRM_WORKQ_TASK_FLUSH_REQ 1
#define CRM_TASK_PRIORITY_0 0
#define CRM_TASK_PRIORITY_MAX 2
#define CAM_REQ_MGR_SCHED_REQ_TIMEOUT 100
#define GFP_KERNEL 0
#define container_of(p,t,m) ((t *)((char *)(p)-offsetof(t,m)))
struct list_head {struct list_head *next,*prev;};
static void INIT_LIST_HEAD(struct list_head *p){p->next=p->prev=p;}
static void list_add_tail(struct list_head *p,struct list_head *h){p->prev=h->prev;p->next=h;h->prev->next=p;h->prev=p;}
static void list_del_init(struct list_head *p){p->prev->next=p->next;p->next->prev=p->prev;INIT_LIST_HEAD(p);}
static int list_empty(struct list_head *p){return p->next==p;}
#define list_first_entry(h,t,m) container_of((h)->next,t,m)
static void atomic_add(int n,int *v){*v+=n;}
static void atomic_sub(int n,int *v){*v-=n;}
static int atomic_read(int *v){return *v;}
static void mutex_lock(int *m){assert(!*m);*m=1;}
static void mutex_unlock(int *m){assert(*m);*m=0;}
#define WORKQ_ACQUIRE_LOCK(w,f) mutex_lock(&(w)->lock)
#define WORKQ_RELEASE_LOCK(w,f) mutex_unlock(&(w)->lock)
struct completion {int done;};
static void init_completion(struct completion *c){c->done=0;}
static void complete(struct completion *c){c->done++;}
struct kref {int refs;};
static void kref_init(struct kref *k){k->refs=1;}
static void kref_get(struct kref *k){assert(k->refs>0);k->refs++;}
static void kref_put(struct kref *k,void (*release)(struct kref *)){assert(k->refs>0);if(!--k->refs)release(k);}
static int live_results,fail_alloc,wait_timeout;
static void *allocate(size_t size){if(fail_alloc)return NULL;void *p=calloc(1,size);assert(p);live_results++;return p;}
static void release(void *p){if(p){assert(live_results>0);live_results--;free(p);}}
#define kzalloc(s,f) allocate(s)
#define kfree release
#define msecs_to_jiffies(n) (n)
struct crm_task_payload {int type;union {struct cam_req_mgr_flush_info flush;} u;};
struct crm_workq_task {struct list_head entry;void *parent,*priv,*payload;int cancel,priority;int (*process_cb)(void *,void *);};
struct cam_req_mgr_core_workq {int lock,in_irq;void *job,*job_using_kthread;bool is_using_kthread;int work,work_using_kthread;struct {struct list_head empty_head,process_head[2];int free_cnt,pending_cnt;} task;};
struct cam_req_mgr_slot {int status,additional_timeout;};
struct cam_req_mgr_req_queue {struct cam_req_mgr_slot slot[4];};
struct cam_req_mgr_connected_device {int32_t dev_hdl;struct {int (*flush_req)(struct cam_req_mgr_flush_request *);} *ops;};
struct cam_req_mgr_core_link {struct {int lock;struct cam_req_mgr_req_queue *in_q;} req;struct cam_req_mgr_connected_device *l_dev;int num_devs;int64_t last_flush_id;struct cam_req_mgr_core_workq *workq;struct completion workq_comp;};
struct cam_req_mgr_core_session {int num_links;};
static struct {int crm_lock;} core_device;
static __typeof__(core_device) *g_crm_core_dev=&core_device;
static struct cam_req_mgr_core_session session;
static struct cam_req_mgr_core_link link;
static void *cam_get_device_priv(int h){return h==1?(void *)&session:h==2?(void *)&link:NULL;}
static int slot_index=-1,flushed,skipped,callbacks,callback_rc[4];
static void __cam_req_mgr_flush_req_slot(struct cam_req_mgr_core_link *l){flushed++;}
static int __cam_req_mgr_find_slot_for_req(struct cam_req_mgr_req_queue *q,int64_t id){return slot_index;}
static void __cam_req_mgr_in_q_skip_idx(struct cam_req_mgr_req_queue *q,int idx){skipped++;}
static int device_flush(struct cam_req_mgr_flush_request *r){assert(r->link_hdl==2);callbacks++;return callback_rc[r->dev_hdl];}
static int queue_work(void *job,int *work){return 1;}
static int kthread_queue_work(void *job,int *work){return 1;}
static unsigned long wait_for_completion_timeout(struct completion *,unsigned long);
'''
MAIN=r'''
static struct cam_req_mgr_core_workq workq;
static struct crm_workq_task tasks[2];static struct crm_task_payload payloads[2];
static void run_task(struct crm_workq_task *task){list_del_init(&task->entry);workq.task.pending_cnt--;assert(!cam_req_mgr_process_task(task));}
static unsigned long wait_for_completion_timeout(struct completion *c,unsigned long ticks){
 if(wait_timeout)return 0;
 assert(!list_empty(&workq.task.process_head[0]));
 /* Execute newest task; an older timed-out request may still be queued. */
 struct crm_workq_task *t=container_of(workq.task.process_head[0].prev,struct crm_workq_task,entry);
 run_task(t);assert(c->done);return 25;
}
static void reset(void){
 assert(!live_results);memset(&workq,0,sizeof(workq));workq.job=(void *)1;workq.job_using_kthread=(void *)1;
 INIT_LIST_HEAD(&workq.task.empty_head);for(int i=0;i<2;i++){INIT_LIST_HEAD(&workq.task.process_head[i]);memset(&tasks[i],0,sizeof(tasks[i]));tasks[i].parent=&workq;tasks[i].payload=&payloads[i];INIT_LIST_HEAD(&tasks[i].entry);list_add_tail(&tasks[i].entry,&workq.task.empty_head);}workq.task.free_cnt=2;
 memset(callback_rc,0,sizeof(callback_rc));callbacks=flushed=skipped=fail_alloc=wait_timeout=0;slot_index=-1;session.num_links=1;core_device.crm_lock=link.req.lock=0;link.workq=&workq;
}
int main(void){
 static __typeof__(*(((struct cam_req_mgr_connected_device *)0)->ops)) ops={.flush_req=device_flush};
 static struct cam_req_mgr_connected_device devices[3];static struct cam_req_mgr_req_queue queue;
 link.num_devs=3;link.l_dev=devices;link.req.in_q=&queue;for(int i=0;i<3;i++){devices[i].dev_hdl=i;devices[i].ops=&ops;}
 struct cam_req_mgr_flush_info info={.session_hdl=1,.link_hdl=2,.flush_type=CAM_REQ_MGR_FLUSH_TYPE_ALL,.req_id=99};
 for(int kt=0;kt<2;kt++){
  reset();workq.is_using_kthread=kt;callback_rc[0]=-EIO;callback_rc[2]=0;assert(cam_req_mgr_flush_requests(&info)==-EIO&&callbacks==3&&!live_results&&workq.task.free_cnt==2);
  reset();callback_rc[0]=-EBUSY;callback_rc[1]=-EIO;assert(cam_req_mgr_flush_requests(&info)==-EBUSY&&callbacks==3&&!live_results);
  reset();assert(!cam_req_mgr_flush_requests(&info)&&callbacks==3&&!live_results);
  reset();fail_alloc=1;assert(cam_req_mgr_flush_requests(&info)==-ENOMEM&&!live_results&&workq.task.free_cnt==2);
  reset();workq.job=NULL;workq.job_using_kthread=NULL;assert(cam_req_mgr_flush_requests(&info)==-EINVAL&&!live_results&&workq.task.free_cnt==2);
  reset();tasks[0].cancel=1;assert(cam_req_mgr_flush_requests(&info)==-ECANCELED&&!live_results&&workq.task.free_cnt==2);
  reset();workq.task.free_cnt=0;INIT_LIST_HEAD(&workq.task.empty_head);assert(cam_req_mgr_flush_requests(&info)==-ENOMEM&&!live_results);
  reset();wait_timeout=1;assert(cam_req_mgr_flush_requests(&info)==-ETIMEDOUT&&live_results==1&&workq.task.pending_cnt==1);struct crm_workq_task *old=list_first_entry(&workq.task.process_head[0],struct crm_workq_task,entry);
  wait_timeout=0;callback_rc[1]=-ENODEV;assert(cam_req_mgr_flush_requests(&info)==-ENODEV&&live_results==1);run_task(old);assert(!live_results&&workq.task.free_cnt==2); /* late worker safely owns result */
  reset();info.flush_type=CAM_REQ_MGR_FLUSH_TYPE_CANCEL_REQ;slot_index=0;queue.slot[0].status=CRM_SLOT_STATUS_REQ_PENDING;assert(cam_req_mgr_flush_requests(&info)==-EINVAL&&!callbacks&&!live_results&&!link.req.lock); /* early native return still completes */
  reset();slot_index=0;queue.slot[0].status=0;queue.slot[0].additional_timeout=5;assert(!cam_req_mgr_flush_requests(&info)&&callbacks==3&&skipped==1&&!queue.slot[0].additional_timeout&&!live_results);info.flush_type=CAM_REQ_MGR_FLUSH_TYPE_ALL;
 }
 reset();struct crm_workq_task *t=cam_req_mgr_workq_get_task(&workq);t->cancel=1;assert(!cam_req_mgr_workq_enqueue_task(t,NULL,0)&&workq.task.free_cnt==2); /* legacy enqueue behavior preserved */
 reset();assert(cam_req_mgr_flush_requests(NULL)==-EFAULT);info.flush_type=CAM_REQ_MGR_FLUSH_TYPE_MAX;assert(cam_req_mgr_flush_requests(&info)==-EINVAL&&!live_results);info.flush_type=CAM_REQ_MGR_FLUSH_TYPE_ALL;info.session_hdl=7;assert(cam_req_mgr_flush_requests(&info)==-EINVAL&&!live_results);
 puts("PASS: actual flush caller/worker, result wrapper, native task get/put/process/enqueue; first error reaches caller, all callbacks visited, early return completes, timeout/late worker and overlapping request refs safe, allocation/pool/enqueue/cancel paths balanced, legacy cancellation retained");return 0;
}
'''
def function_top(s,signature):
    start=s.index(signature);return s[start:s.index('\n}\n',start)+3]
def main():
    texts={n:(SOURCE/n).read_text() for n in NAMES};core=texts[NAMES[0]];work=texts[NAMES[1]]
    types='\n'.join(re.search(r'struct '+name+r' \{.*?\n\};',texts[file],re.S).group(0) for name,file in [('cam_req_mgr_flush_info',NAMES[5]),('cam_req_mgr_flush_request',NAMES[4])])
    # Types must precede payload structs that embed them.
    model=MODEL.replace('struct crm_task_payload {',types+'\nstruct crm_task_payload {')
    flush=ex.function(core,'int cam_req_mgr_process_flush_req(');caller=ex.function(core,'int cam_req_mgr_flush_requests(');inc='\n'.join(l for l in texts[NAMES[3]].splitlines() if not l.startswith('#include'))
    queue='\n'.join(function_top(work,s) for s in ['struct crm_workq_task *cam_req_mgr_workq_get_task(','static void cam_req_mgr_workq_put_task(','static int cam_req_mgr_process_task(','static int pico_crm_enqueue_task(','int cam_req_mgr_workq_enqueue_task(','int pico_cam_req_mgr_workq_enqueue_owned('])
    code=model+queue+flush+inc+caller+MAIN;out=BASE/'out/phoenix-kernel-recovery/crm-flush-result-tests';out.mkdir(exist_ok=True);(out/'harness.c').write_text(code)
    runs={}
    for editor in [0,1]:
        binary=out/('test-'+str(editor));subprocess.run(['gcc','-std=gnu11','-g','-O1','-fsanitize=address,undefined','-fno-sanitize-recover=all']+(['-D__CAMERA_EDITOR__=1'] if editor else [])+[str(out/'harness.c'),'-o',str(binary)],check=True)
        r=subprocess.run([str(binary)],capture_output=True,text=True,timeout=30);runs[str(editor)]={'exit_code':r.returncode,'stdout':r.stdout,'stderr':r.stderr}
    report={'sources':{n:hashlib.sha256((SOURCE/n).read_bytes()).hexdigest() for n in NAMES},'harness_sha256':hashlib.sha256(code.encode()).hexdigest(),'exit_code':0 if all(r['exit_code']==0 for r in runs.values()) else 1,'runs':runs,'scope':'Actual native flush caller/worker and queue get/put/process/enqueue, private result wrapper; callback/slot/list/ref/completion/queue scheduling APIs modeled, sequential late-worker interleaving; native workqueue and kthread branches compile/run. No real concurrent kernel scheduling or link/remove lifetime proof','device_modified':False}
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));raise SystemExit(report['exit_code'])
if __name__=='__main__':main()
