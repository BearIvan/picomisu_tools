"""Execute the actual dwc3 probe/remove, IRQ top half, kthread bottom half and the flush sites (pullup, vbus_session, gadget_stop) under ASan/UBSan."""
from pathlib import Path
import hashlib,importlib.util,json,re,subprocess
BASE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro');SOURCE=BASE/'source/phoenix-kernel-recovery'
CORE='drivers/usb/dwc3/core.c';CORE_H='drivers/usb/dwc3/core.h';GAD='drivers/usb/dwc3/gadget.c'
OBJ=BASE/'out/phoenix-kernel-recovery/obj'
STRUCTS=[(CORE_H,'struct dwc3_event_buffer {')]
FUNCS=[(CORE_H,'static inline bool dwc3_is_otg_or_drd('),
       (GAD,'void dwc3_bh_kwork('),(GAD,'static irqreturn_t dwc3_check_event_buf('),(GAD,'irqreturn_t dwc3_interrupt('),
       (GAD,'static int dwc3_gadget_pullup('),(GAD,'static int dwc3_gadget_vbus_session('),(GAD,'static int dwc3_gadget_stop('),
       (CORE,'static int dwc3_probe('),(CORE,'static int dwc3_remove(')]
MODEL=r'''
#include <assert.h>
#include <stdarg.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef uint8_t u8;typedef uint16_t u16;typedef uint32_t u32;typedef uint64_t u64;typedef int64_t s64;typedef s64 ktime_t;typedef u64 dma_addr_t;
typedef u64 resource_size_t;
#define __iomem
#define BIT(n) (1UL<<(n))
#define container_of(p,t,m) ((t *)((char *)(p)-offsetof(t,m)))
#define ARRAY_SIZE(a) (sizeof(a)/sizeof((a)[0]))
#define min(a,b) ((a)<(b)?(a):(b))
#define EINVAL 22
#define ENOMEM 12
#define ENODEV 19
#define EPERM 1
#define EAGAIN 11
#define ETIMEDOUT 110
#define EPROBE_DEFER 517
#define GFP_KERNEL 0
#define IS_ERR(p) ((unsigned long)(p)>=(unsigned long)-4095)
#define PTR_ERR(p) ((long)(p))
#define ERR_PTR(e) ((void *)(long)(e))
static int logs;
#define dev_err(...) (logs++)
#define dev_dbg(...) ((void)0)
#define pr_err(...) (logs++)
#define dbg_event(...) ((void)0)
#define dbg_log_string(...) ((void)0)
typedef int irqreturn_t;
#define IRQ_NONE 0
#define IRQ_HANDLED 1
#define IRQ_WAKE_THREAD 2
#define IRQF_SHARED 0x80
#define MAX_INTR_STATS 10
#define DWC3_GEVNTSIZ(n) (0xc408 + ((n) * 0x10))
#define DWC3_GEVNTCOUNT(n) (0xc40c + ((n) * 0x10))
#define DWC3_DEV_IMOD(n) (0xca00 + ((n) * 0x4))
#define DWC3_GEVNTCOUNT_MASK 0xfffc
#define DWC3_GEVNTCOUNT_EHB BIT(31)
#define DWC3_GEVNTSIZ_INTMASK BIT(31)
#define DWC3_XHCI_REGS_END 0x7fff
#define DWC3_GLOBALS_REGS_START 0xc100
#define DWC_CTRL_COUNT 10
#define NUM_LOG_PAGES 12
#define DWC3_EVENT_BUFFERS_SIZE 4096
#define DWC3_DEFAULT_AUTOSUSPEND_DELAY 500
#define DWC3_PULL_UP_TIMEOUT 500
#define MIN_RUN_STOP_DELAY_MS 50
#define EP0_SETUP_PHASE 1
#define DWC3_EP0_COMPLETE 1
#define DWC3_CONTROLLER_NOTIFY_OTG_EVENT 6
#define DWC3_CONTROLLER_ERROR_EVENT 0
#define DWC3_CONTROLLER_NOTIFY_CLEAR_DB 15
#define IORESOURCE_MEM 0x200
#define WQ_HIGHPRI 0x10
#define SCHED_FIFO 1
enum usb_dr_mode {USB_DR_MODE_UNKNOWN,USB_DR_MODE_HOST,USB_DR_MODE_PERIPHERAL,USB_DR_MODE_OTG,USB_DR_MODE_DRD};
/* locks and irqs */
typedef struct {int held;} spinlock_t;
static void spin_lock_irqsave_(spinlock_t *l){assert(!l->held);l->held=1;}
static void spin_unlock_irqrestore_(spinlock_t *l){assert(l->held);l->held=0;}
#define spin_lock_irqsave(l,f) do{(f)=0;spin_lock_irqsave_(l);}while(0)
#define spin_unlock_irqrestore(l,f) do{(void)(f);spin_unlock_irqrestore_(l);}while(0)
static void spin_lock_init(spinlock_t *l){l->held=0;}
static int irq_depth;
static void disable_irq(int irq){(void)irq;irq_depth++;}
static void enable_irq(int irq){(void)irq;assert(irq_depth>0);irq_depth--;}
/* kthread worker model */
struct task_struct {char comm[32];int policy,prio,alive;struct kthread_worker *worker;};
struct kthread_work;typedef void (*kthread_work_func_t)(struct kthread_work *);
struct kthread_work {kthread_work_func_t func;struct kthread_worker *worker;int queued;};
struct kthread_worker {int inited;struct task_struct *task;struct kthread_work *pending[8];int npending;};
static int kthread_fail,tasks_live,flushes,queues;static spinlock_t *flush_forbidden_lock;static int flush_needs_irq_off;
static int kthread_worker_fn(void *w){(void)w;return 0;}
static void kthread_init_worker(struct kthread_worker *w){memset(w,0,sizeof(*w));w->inited=1;}
static void kthread_init_work(struct kthread_work *k,kthread_work_func_t f){memset(k,0,sizeof(*k));k->func=f;}
static struct task_struct *kthread_run(int (*fn)(void *),void *data,const char *fmt,...){assert(fn==kthread_worker_fn);
  if(kthread_fail)return ERR_PTR(-EAGAIN);struct task_struct *t=calloc(1,sizeof(*t));va_list ap;va_start(ap,fmt);vsnprintf(t->comm,sizeof(t->comm),fmt,ap);va_end(ap);
  t->alive=1;t->worker=data;((struct kthread_worker *)data)->task=t;tasks_live++;return t;}
static int kthread_stop(struct task_struct *t){assert(t&&t->alive);t->alive=0;t->worker->task=NULL;tasks_live--;free(t);return 0;}
static bool kthread_queue_work(struct kthread_worker *w,struct kthread_work *k){assert(w->inited&&k->func);queues++;
  if(k->queued)return false;assert(w->npending<8);w->pending[w->npending++]=k;k->queued=1;k->worker=w;return true;}
static void kthread_flush_worker(struct kthread_worker *w){assert(w->inited);assert(w->task&&w->task->alive); /* no thread: flush never returns */
  if(flush_forbidden_lock)assert(!flush_forbidden_lock->held);if(flush_needs_irq_off)assert(irq_depth>0);flushes++;
  while(w->npending){struct kthread_work *k=w->pending[0];memmove(w->pending,w->pending+1,--w->npending*sizeof(k));k->queued=0;k->func(k);}}
struct sched_param {int sched_priority;};
static int sched_calls,sched_policy,sched_prio;static struct task_struct *sched_task;
static int sched_setscheduler(struct task_struct *t,int pol,const struct sched_param *p){sched_calls++;sched_task=t;sched_policy=pol;sched_prio=p->sched_priority;t->policy=pol;t->prio=p->sched_priority;return 0;}
/* workqueue (still allocated for bh_work) */
struct workqueue_struct {int x;};struct work_struct {void (*func)(struct work_struct *);};
static int wq_live,wq_fail;
static struct workqueue_struct *alloc_ordered_workqueue(const char *n,int f){(void)n;assert(f==WQ_HIGHPRI);if(wq_fail)return NULL;wq_live++;return calloc(1,sizeof(struct workqueue_struct));}
static void destroy_workqueue(struct workqueue_struct *w){assert(w);wq_live--;free(w);}
#define INIT_WORK(w,f) ((w)->func=(f))
/* pm runtime */
struct dev_pm_info {int usage_count;};
struct device {const char *name;struct dev_pm_info power;void *drvdata;void *of_node;};
static const char *dev_name(const struct device *d){return d->name;}
static int pm_get,pm_put;
static int pm_runtime_get_sync(struct device *d){(void)d;pm_get++;return 0;}
static int pm_runtime_put(struct device *d){(void)d;pm_put++;return 0;}
static int pm_runtime_put_autosuspend(struct device *d){(void)d;pm_put++;return 0;}
static void pm_runtime_mark_last_busy(struct device *d){(void)d;}
static void pm_runtime_no_callbacks(struct device *d){(void)d;}
static void pm_runtime_set_active(struct device *d){(void)d;}
static void pm_runtime_set_autosuspend_delay(struct device *d,int x){(void)d;(void)x;}
static void pm_runtime_use_autosuspend(struct device *d){(void)d;}
static void pm_runtime_enable(struct device *d){(void)d;}
static void pm_runtime_disable(struct device *d){(void)d;}
static void pm_runtime_forbid(struct device *d){(void)d;}
static void pm_runtime_allow(struct device *d){(void)d;}
/* misc */
struct completion {int done;};
static void reinit_completion(struct completion *c){c->done=0;}
static unsigned long wait_for_completion_timeout(struct completion *c,unsigned long t){(void)c;return t;}
static unsigned long msecs_to_jiffies(unsigned m){return m/10;}
static s64 now_ns=1000000000;
static ktime_t ktime_get(void){return now_ns+=1000000000;}
static ktime_t ktime_sub(ktime_t a,ktime_t b){return a-b;}
static s64 ktime_to_ms(ktime_t k){return k/1000000;}
static s64 ktime_us_delta(ktime_t a,ktime_t b){return (a-b)/1000;}
static void msleep(unsigned m){(void)m;}
typedef struct {int c;} wait_queue_head_t;
static void init_waitqueue_head(wait_queue_head_t *w){w->c=0;}
struct resource {resource_size_t start,end;const char *name;unsigned long flags;};
static resource_size_t resource_size(const struct resource *r){return r->end-r->start+1;}
struct clk_bulk_data {const char *id;void *clk;};
struct reset_control {int x;};
struct usb_gadget {int x;};struct usb_gadget_driver {int x;};
'''
MODEL2=r'''
struct dwc3 {
  spinlock_t lock;struct device *dev;struct clk_bulk_data *clks;int num_clks;struct reset_control *reset;
  u64 reg_phys;struct resource xhci_resources[1];void __iomem *regs;size_t regs_size;int irq;
  struct workqueue_struct *dwc_wq;struct work_struct bh_work;wait_queue_head_t wait_linkstate;bool enable_bus_suspend;
  enum usb_dr_mode dr_mode;void *dwc_ipc_log_ctxt,*dwc_dma_ipc_log_ctxt;unsigned int index;
  struct dwc3_event_buffer *ev_buf;struct usb_gadget gadget;struct usb_gadget_driver *gadget_driver;
  bool err_evt_seen,pullups_connected,vbus_active,softconnect,b_suspend;u16 imod_interval;unsigned long irq_cnt;
  int irq_dbg_index;ktime_t irq_start_time[MAX_INTR_STATS];unsigned irq_completion_time[MAX_INTR_STATS];unsigned irq_event_count[MAX_INTR_STATS];
  int ep0state,ep0_next_event;struct completion ep0_in_setup;ktime_t last_run_stop;
  struct kthread_worker bh_worker;struct task_struct *bh_worker_task;struct kthread_work bh_kwork;
};
#define gadget_to_dwc(g) (container_of(g, struct dwc3, gadget))
/* register file */
static u32 regfile[0x10000/4];
static u32 dwc3_readl(void __iomem *base,u32 off){assert(base==(void *)regfile);return regfile[off/4];}
static void dwc3_writel(void __iomem *base,u32 off,u32 v){assert(base==(void *)regfile);regfile[off/4]=v;}
/* bottom half body (static in gadget.c) */
static int thread_calls;static struct dwc3 *cur_dwc;
static irqreturn_t dwc3_thread_interrupt(int irq,void *evt){thread_calls++;assert(cur_dwc&&irq==cur_dwc->irq&&evt==cur_dwc->ev_buf);
  assert(pm_get>pm_put);assert(!cur_dwc->lock.held);struct dwc3_event_buffer *e=evt;e->flags&=~1u;return IRQ_HANDLED;}
static void dwc3_bh_work(struct work_struct *w){(void)w;assert(!"bh_work must not run");}
static int run_stop_calls,run_stop_rc,soft_resets,notify_calls,disconnects;
static int dwc3_gadget_run_stop(struct dwc3 *d,int on,bool s){(void)s;assert(d->lock.held);run_stop_calls++;return run_stop_rc;}
static void dwc3_device_core_soft_reset(struct dwc3 *d){(void)d;soft_resets++;}
static void dwc3_notify_event(struct dwc3 *d,int e,int v){(void)d;(void)e;(void)v;notify_calls++;}
static void dwc3_gadget_disconnect_interrupt(struct dwc3 *d){(void)d;disconnects++;}
/* probe environment */
static int count;static struct dwc3 *dwc3_instance[DWC_CTRL_COUNT];
static const struct clk_bulk_data dwc3_core_clks[]={{"ref"},{"bus_early"},{"suspend"}};
struct platform_device {struct device dev;};
#define to_platform_device(d) container_of(d,struct platform_device,dev)
static void *allocs[64];static int nallocs;
static void *devm_kzalloc(struct device *d,size_t n,int g){(void)d;(void)g;void *p=calloc(1,n);allocs[nallocs++]=p;return p;}
static void *devm_kmemdup(struct device *d,const void *s,size_t n,int g){void *p=devm_kzalloc(d,n,g);memcpy(p,s,n);return p;}
static void devres_release_all(void){while(nallocs)free(allocs[--nallocs]);}
static struct resource memres={0xa600000,0xa6fffff,"dwc3",IORESOURCE_MEM};
static struct resource *platform_get_resource(struct platform_device *p,int t,int i){(void)p;assert(t==IORESOURCE_MEM&&i==0);return &memres;}
static int platform_get_irq(struct platform_device *p,int i){(void)p;(void)i;return 165;}
static irqreturn_t (*irq_handler)(int,void *);static void *irq_data;
static int devm_request_irq(struct device *d,int irq,irqreturn_t (*h)(int,void *),unsigned long f,const char *n,void *data){(void)d;(void)irq;(void)f;(void)n;irq_handler=h;irq_data=data;return 0;}
static void __iomem *devm_ioremap_resource(struct device *d,struct resource *r){(void)d;assert(r->start==0xa600000+DWC3_GLOBALS_REGS_START);return regfile;}
static void dwc3_get_properties(struct dwc3 *d){d->dr_mode=USB_DR_MODE_OTG;}
static struct reset_control rc_obj;static int deassert_rc,clk_get_rc,prepare_rc,enable_rc,evbuf_rc,clk_put_calls,clk_disable_calls,reset_assert_calls;
static struct reset_control *devm_reset_control_get_optional_shared(struct device *d,const char *n){(void)d;(void)n;return &rc_obj;}
static int clk_bulk_get(struct device *d,int n,struct clk_bulk_data *c){(void)d;(void)n;(void)c;return clk_get_rc;}
static void clk_bulk_put(int n,struct clk_bulk_data *c){(void)n;(void)c;clk_put_calls++;}
static int reset_control_deassert(struct reset_control *r){(void)r;return deassert_rc;}
static int reset_control_assert(struct reset_control *r){(void)r;reset_assert_calls++;return 0;}
static int clk_bulk_prepare(int n,struct clk_bulk_data *c){(void)n;(void)c;return prepare_rc;}
static void clk_bulk_unprepare(int n,struct clk_bulk_data *c){(void)n;(void)c;}
static int clk_bulk_enable(int n,struct clk_bulk_data *c){(void)n;(void)c;return enable_rc;}
static void clk_bulk_disable(int n,struct clk_bulk_data *c){(void)n;(void)c;clk_disable_calls++;}
static void platform_set_drvdata(struct platform_device *p,void *d){p->dev.drvdata=d;}
static void *platform_get_drvdata(struct platform_device *p){return p->dev.drvdata;}
static struct dwc3_event_buffer evbuf_obj;static u32 evmem[1024],evcache[1024];
static int dwc3_alloc_event_buffers(struct dwc3 *d,unsigned len){if(evbuf_rc)return evbuf_rc;evbuf_obj=(struct dwc3_event_buffer){evmem,evcache,len,0,0,0,0,d};d->ev_buf=&evbuf_obj;return 0;}
static int dwc3_alloc_scratch_buffers(struct dwc3 *d){(void)d;return 0;}
static void dwc3_free_event_buffers(struct dwc3 *d){d->ev_buf=NULL;}
static void dwc3_free_scratch_buffers(struct dwc3 *d){(void)d;}
static int dwc3_gadget_init(struct dwc3 *d){(void)d;return 0;}
static void dwc3_gadget_exit(struct dwc3 *d){(void)d;}
static void dwc3_debugfs_init(struct dwc3 *d){(void)d;}
static void dwc3_debugfs_exit(struct dwc3 *d){(void)d;}
static void *ipc_log_context_create(int p,const char *n,int f){(void)p;(void)n;(void)f;return (void *)1;}
static void ipc_log_context_destroy(void *c){(void)c;}
void dwc3_bh_kwork(struct kthread_work *w);
irqreturn_t dwc3_interrupt(int irq, void *_dwc);
'''
MAIN=r'''
static struct platform_device pdev;
static void reset_env(void){kthread_fail=wq_fail=0;deassert_rc=clk_get_rc=prepare_rc=enable_rc=evbuf_rc=0;clk_put_calls=clk_disable_calls=reset_assert_calls=0;
  sched_calls=0;sched_task=NULL;flushes=queues=0;thread_calls=0;pm_get=pm_put=0;memset(&pdev,0,sizeof(pdev));pdev.dev.name="a600000.dwc3";pdev.dev.of_node=(void *)&pdev;
  memset(regfile,0,sizeof(regfile));irq_depth=0;}
static void after_failure(int ret,int expect){if(ret!=expect)fprintf(stderr,"ret %d expected %d\n",ret,expect);assert(ret==expect);assert(tasks_live==0&&wq_live==0&&count==0);devres_release_all();}
int main(void){
 /* --- probe error paths: no leaked thread or workqueue --- */
 reset_env();kthread_fail=1;after_failure(dwc3_probe(&pdev),-EAGAIN);assert(sched_calls==0);
 reset_env();clk_get_rc=-EPROBE_DEFER;after_failure(dwc3_probe(&pdev),-EPROBE_DEFER);assert(clk_put_calls==0);
 reset_env();deassert_rc=-EIO_;after_failure(dwc3_probe(&pdev),-EIO_);assert(clk_put_calls==1);
 reset_env();evbuf_rc=-ENOMEM;after_failure(dwc3_probe(&pdev),-ENOMEM);assert(clk_put_calls==1&&clk_disable_calls==1&&reset_assert_calls==1);
 reset_env();wq_fail=1;dwc3_probe(&pdev);assert(tasks_live==0&&wq_live==0);devres_release_all();
 /* --- probe success --- */
 reset_env();assert(!dwc3_probe(&pdev));struct dwc3 *dwc=pdev.dev.drvdata;cur_dwc=dwc;
 assert(dwc&&count==1&&dwc3_instance[0]==dwc&&tasks_live==1&&wq_live==1);
 assert(irq_depth==1);enable_irq(dwc->irq); /* probe leaves the irq disabled until dwc3_msm_resume */
 assert(dwc->bh_worker.inited&&dwc->bh_worker_task&&dwc->bh_worker.task==dwc->bh_worker_task&&!strcmp(dwc->bh_worker_task->comm,"dwc_a600000.dwc3"));
 assert(sched_calls==1&&sched_task==dwc->bh_worker_task&&sched_policy==SCHED_FIFO&&sched_prio==1);
 assert(dwc->bh_kwork.func==dwc3_bh_kwork&&dwc->bh_work.func==dwc3_bh_work&&irq_handler==dwc3_interrupt&&irq_data==dwc);
 /* --- top half queues the kthread work, once per pending event batch --- */
 dwc->pullups_connected=true;regfile[DWC3_GEVNTCOUNT(0)/4]=8;
 assert(irq_handler(dwc->irq,dwc)==IRQ_HANDLED&&queues==1&&dwc->bh_worker.npending==1&&dwc->bh_worker.pending[0]==&dwc->bh_kwork);
 assert(dwc->ev_buf->flags&1&&(regfile[DWC3_GEVNTSIZ(0)/4]&DWC3_GEVNTSIZ_INTMASK));
 assert(irq_handler(dwc->irq,dwc)==IRQ_HANDLED&&queues==1); /* still pending: not requeued */
 /* no events: nothing queued */
 dwc->ev_buf->flags=0;regfile[DWC3_GEVNTCOUNT(0)/4]=0;
 /* --- the worker runs the real bottom half --- */
 flush_forbidden_lock=&dwc->lock;
 kthread_flush_worker(&dwc->bh_worker);assert(thread_calls==1&&pm_get==1&&pm_put==1&&!dwc->bh_worker.npending);
 assert(irq_handler(dwc->irq,dwc)==IRQ_HANDLED&&queues==1);
 /* --- flush sites: irq disabled, dwc->lock not held --- */
 flush_needs_irq_off=1;
 regfile[DWC3_GEVNTCOUNT(0)/4]=4;assert(irq_handler(dwc->irq,dwc)==IRQ_HANDLED&&queues==2);
 dwc->vbus_active=true;dwc->softconnect=true;struct usb_gadget_driver gd;dwc->gadget_driver=&gd;dwc->ep0state=EP0_SETUP_PHASE;dwc->ep0_next_event=DWC3_EP0_COMPLETE;
 int f0=flushes;assert(!dwc3_gadget_pullup(&dwc->gadget,1)&&flushes==f0+1&&thread_calls==2&&irq_depth==0&&soft_resets==1&&run_stop_calls==1);
 f0=flushes;assert(!dwc3_gadget_pullup(&dwc->gadget,0)&&flushes==f0+1&&irq_depth==0&&!dwc->pullups_connected);
 dwc->pullups_connected=true;regfile[DWC3_GEVNTCOUNT(0)/4]=4;assert(irq_handler(dwc->irq,dwc)==IRQ_HANDLED&&queues==3);
 f0=flushes;assert(!dwc3_gadget_vbus_session(&dwc->gadget,0)&&flushes==f0+1&&thread_calls==3&&irq_depth==0&&disconnects==1);
 dwc->dr_mode=USB_DR_MODE_PERIPHERAL;f0=flushes;assert(dwc3_gadget_vbus_session(&dwc->gadget,1)==-EPERM&&flushes==f0);dwc->dr_mode=USB_DR_MODE_OTG;
 flush_needs_irq_off=0;
 regfile[DWC3_GEVNTCOUNT(0)/4]=4;assert(irq_handler(dwc->irq,dwc)==IRQ_HANDLED&&queues==4);
 f0=flushes;assert(!dwc3_gadget_stop(&dwc->gadget)&&flushes==f0+1&&thread_calls==4&&!dwc->gadget_driver&&!dwc->lock.held);
 /* --- remove: flush + stop exactly once; a late irq only queues --- */
 regfile[DWC3_GEVNTCOUNT(0)/4]=4;dwc->pullups_connected=true;assert(irq_handler(dwc->irq,dwc)==IRQ_HANDLED&&queues==5);
 assert(!dwc3_remove(&pdev)&&tasks_live==0&&thread_calls==5&&count==0&&!dwc->bh_worker.task);
 regfile[DWC3_GEVNTCOUNT(0)/4]=4;dwc->ev_buf=&evbuf_obj;evbuf_obj.flags=0;assert(irq_handler(dwc->irq,dwc)==IRQ_HANDLED&&queues==6&&thread_calls==5);
 destroy_workqueue(dwc->dwc_wq); /* the public remove never destroyed dwc_wq (unchanged) */
 devres_release_all();assert(irq_depth==0&&wq_live==0);
 puts("PASS: probe starts dwc_<dev> at SCHED_FIFO 1 and binds dwc3_bh_kwork; every probe failure (kthread, EPROBE_DEFER, reset, "
      "event buffers) leaves no thread/workqueue; dwc3_interrupt queues the kthread work (not bh_work) once per batch; the worker "
      "runs the real bottom half with runtime PM; pullup/vbus_session flush with the irq disabled and dwc->lock free; gadget_stop "
      "flushes the worker; remove flushes and stops it once and later IRQs only queue");
 return 0;
}
'''
def dwarf_layout(obj,name):
    lines=subprocess.run(['readelf','--debug-dump=info',str(obj)],capture_output=True,text=True).stdout.split('\n')
    for i,l in enumerate(lines):
        if 'DW_TAG_structure_type' not in l:continue
        depth=int(re.search(r'<(\d+)>',l).group(1));j=i+1;nm=size=None
        while j<len(lines) and 'Abbrev Number' not in lines[j]:
            m=re.search(r'DW_AT_name\s*:\s*(?:\(.*?\):\s*)?(\S+)',lines[j])
            if m:nm=m.group(1)
            if 'DW_AT_byte_size' in lines[j]:size=int(lines[j].split(':')[-1])
            j+=1
        if nm!=name or size is None:continue
        got={'size':size};k=j
        while k<len(lines):
            m=re.search(r'<(\d+)><',lines[k])
            if m and int(m.group(1))<=depth:break
            if 'DW_TAG_member' in lines[k] and m and int(m.group(1))==depth+1:
                q=k+1;mn=loc=None
                while q<len(lines) and 'Abbrev Number' not in lines[q]:
                    mm=re.search(r'DW_AT_name\s*:\s*(?:\(.*?\):\s*)?(\S+)',lines[q])
                    if mm:mn=mm.group(1)
                    if 'DW_AT_data_member_location' in lines[q]:loc=int(lines[q].split(':')[-1])
                    q+=1
                got[mn]=loc
            k+=1
        return got
    return {}
def main():
    spec=importlib.util.spec_from_file_location('ex',Path(__file__).with_name('test-pico-sensor-mono-hook.py'));ex=importlib.util.module_from_spec(spec);spec.loader.exec_module(ex)
    srcs={n:(SOURCE/n).read_text() for n in (CORE,CORE_H,GAD)}
    code=(MODEL+'#define EIO_ 5\n'+'\n'.join(ex.function(srcs[f],s)+';' for f,s in STRUCTS)+MODEL2
          +'\n'.join(ex.function(srcs[f],s) for f,s in FUNCS)+'\n'+MAIN)
    out=BASE/'out/phoenix-kernel-recovery/dwc3-bh-kthread-tests';out.mkdir(exist_ok=True);(out/'harness.c').write_text(code)
    subprocess.run(['gcc','-std=gnu11','-g','-O1','-Wall','-Wno-unused-function','-Wno-unused-variable','-Wno-unused-but-set-variable','-fsanitize=address,undefined','-fno-sanitize-recover=all',str(out/'harness.c'),'-o',str(out/'test')],check=True)
    r=subprocess.run([str(out/'test')],capture_output=True,text=True,timeout=60)
    want={'size':2544,'last_run_stop':2432,'bh_worker':2440,'bh_worker_task':2496,'bh_kwork':2504,'bh_work':1984,'dwc_wq':1976,'ev_buf':456,'irq':2140}
    got=dwarf_layout(OBJ/'drivers/usb/dwc3/core.o','dwc3')
    dwarf={k:(got.get(k),v) for k,v in want.items()};dwarf_ok=all(a==b for a,b in dwarf.values())
    rc=r.returncode if r.returncode else (0 if dwarf_ok else 3)
    report={'sources':{n:hashlib.sha256((SOURCE/n).read_bytes()).hexdigest() for n in sorted(srcs)},'harness_sha256':hashlib.sha256(code.encode()).hexdigest(),
            'dwarf_layout':dwarf,'dwarf_ok':dwarf_ok,'exit_code':rc,'stdout':r.stdout,'stderr':r.stderr[-3000:],
            'scope':'Actual dwc3_probe, dwc3_remove, dwc3_interrupt, dwc3_check_event_buf, dwc3_bh_kwork, dwc3_gadget_pullup, '
                    'dwc3_gadget_vbus_session, dwc3_gadget_stop and dwc3_is_otg_or_drd with the real dwc3_event_buffer. kthread worker modeled '
                    '(flush asserts a live thread, the dwc lock free and, at the pullup/vbus sites, the irq disabled); LeakSanitizer catches a '
                    'thread not stopped on an error path. The factory struct dwc3 tail offsets are checked in the DWARF of the built core.o.',
            'device_modified':False}
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));raise SystemExit(rc)
if __name__=='__main__':main()
