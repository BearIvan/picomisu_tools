"""Execute the actual reconstructed kgsl GPU statistics bodies (composite, /proc/gpu_procs, frame flow, preemption audit, online TAP)
under ASan/UBSan, plus a static check of every TAP hook against the factory call-site table."""
from pathlib import Path
import hashlib,importlib.util,json,re,subprocess
BASE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro');SOURCE=BASE/'source/phoenix-kernel-recovery'
G='drivers/gpu/msm/'
KP='include/linux/kgsl_pico.h';TAPH=G+'kgsl_tap.h';TAPC=G+'kgsl_tap.c';PWRH=G+'kgsl_pwrctrl.h';PWRC=G+'kgsl_pwrctrl.c';PSC=G+'kgsl_pwrscale.c'
DOH=G+'kgsl_drawobj.h';DOC=G+'kgsl_drawobj.c';DCH=G+'adreno_drawctxt.h';DCC=G+'adreno_drawctxt.c';DSH=G+'adreno_dispatch.h';DSC=G+'adreno_dispatch.c'
PRE=G+'adreno_a6xx_preempt.c';SHM=G+'kgsl_sharedmem.c';KG=G+'kgsl.c';DBG=G+'kgsl_debugfs.c';MMU=G+'kgsl_mmu.c';IOMMU=G+'kgsl_iommu.c'
A6=G+'adreno_a6xx.c';AD=G+'adreno.c'
STRUCTS=[(KP,'struct kgsl_online_tap {'),(PWRH,'struct kgsl_clk_stats {'),(DOH,'enum kgsl_drawobj_cmd_priv {'),(DOH,'struct kgsl_drawobj {'),
         (DOH,'struct kgsl_drawobj_cmd {'),(DSH,'struct adreno_dispatcher_drawqueue {')]
ADRENO_CTX=(DCH,'struct adreno_context {')
FUNCS=[(TAPH,'static inline bool kgsl_tap_enabled('),(TAPH,'static inline unsigned int kgsl_tap_bucket('),
       (TAPH,'static inline void caculate_and_inc_counter('),(TAPH,'static inline u64 kgsl_tap_begin('),
       (TAPC,'struct kgsl_device *kgsl_tap_get_device('),(TAPC,'static int tap_row('),(TAPC,'static int tap_event('),
       (TAPC,'int kgsl_tap_result_show('),(TAPC,'struct kgsl_online_tap *kgsl_online_tap_data('),(TAPC,'void kgsl_online_tap_clear('),
       (TAPC,'int kgsl_online_tap_init('),
       (PWRC,'void kgsl_pwrctrl_busy_time('),(PWRC,'static ssize_t gputap_show('),
       (DOC,'static void _deferred_destroy('),(DOC,'void kgsl_drawobj_destroy_object_defer('),
       (DCC,'int get_frame_flow('),(DCC,'static inline u64 flow_ticks_us('),(DCC,'void update_frame_flow_cache('),
       (DSH,'static inline bool adreno_drawqueue_is_empty('),
       (DSC,'bool is_runtime_context('),(DSC,'static void _queue_drawobj('),(DSC,'static int _queue_cmdobj('),(DSC,'static int sendcmd('),
       (DSC,'static void cmdobj_profile_ticks('),(DSC,'static void retire_cmdobj('),(DSC,'static int adreno_dispatch_retire_drawqueue('),
       (PRE,'static inline bool drawqueue_slot_live('),(PRE,'void audit_preemption_ticks('),
       (SHM,'static ssize_t composite_store('),(KG,'struct dma_buf *kgsl_get_dma_buf('),
       (DBG,'static inline u64 kgsl_ticks_to_us('),(DBG,'static int proc_status_show('),(DBG,'static int total_status_show('),
       (DBG,'static int compositor_show('),(DBG,'void kgsl_procfs_init('),(DBG,'void kgsl_procfs_close(')]
DEFINES=[(KP,r'#define KGSL_(TAP_BUCKETS|FRAME_FLOW_\w+)\b'),(DCH,r'#define (SUBMIT_RETIRE_TICKS_SIZE|ADRENO_CONTEXT_DRAWQUEUE_SIZE)\b'),
         (DSH,r'#define (ADRENO_DISPATCH_DRAWQUEUE_SIZE|DRAWQUEUE_NEXT)\b'),(PWRC,r'#define UPDATE_BUSY_VAL\b'),
         (DBG,r'#define GPU_PROCS_PWRFLAGS_AXI_ON\b')]
GLOBALS=[(TAPC,r'^(struct static_key kgsl_tap_key|static struct kgsl_device \*kgsl_tap_device);'),
         (DCC,r'^(static DEFINE_SPINLOCK\(flow_lock\)|static int latest_idx|static u64 frame_flow\[.*\]|unsigned int latest_compositor_ts);'),
         (SHM,r'^int composite\[2\];'),(DBG,r'^static struct proc_dir_entry \*procfs;')]
MACROS=[(TAPH,'#define kgsl_tap_period('),(TAPH,'#define kgsl_tap_event(')]
# snippets of larger functions: (file, start marker, end marker (exclusive))
SNIPPETS={'open_composite':(KG,'\t/* PICO: a compositor that restarted keeps its flag */','\tspin_lock(&kgsl_driver.proclist_lock);'),
          'ddr_pressure':(PSC,'\t/* PICO: DDR pressure','\tmemset(&pwrscale->accum_stats'),
          'ctx_list_add':(DCC,'\t/* PICO: visible in /proc/gpu_procs/<pid>/status */','\treturn &drawctxt->base;'),
          'ctx_list_del':(DCC,'\twrite_lock(&context->proc_priv->ctxt_list_lock);','\tspin_lock(&drawctxt->lock);'),
          'proc_dir':(DBG,'\t/* PICO: /proc/gpu_procs/<pid>/status (independent of debugfs) */','\tprivate->debug_root = debugfs_create_dir(name, proc_d_debugfs);'),
          'replay_reset':(DSC,'\t\t/* PICO: the replay starts its preemption accounting afresh */','\t\tret = sendcmd(adreno_dev, replay[i]);')}
# factory TAP call sites (function -> counter), from the 5.13.7 decompile (offsets into the 380 byte block)
TAP_SITES=[(KG,'long kgsl_ioctl_gpu_command(',['sched_p_flush_composite','sched_p_flush']),(DSC,'static int sendcmd(',['sched_p_submit_composite','sched_p_submit']),
           (KG,'long gpumem_free_entry(',['gmem_p_free']),(KG,'struct kgsl_mem_entry *gpumem_alloc_entry(',['gmem_p_alloc']),
           (KG,'static int kgsl_mmap(',['gmem_p_cmap']),(KG,'kgsl_get_unmapped_area(struct file *file',['gmem_p_get_area']),
           (SHM,'static int kgsl_page_alloc_vmfault(',['gmem_p_cfault']),(MMU,'kgsl_mmu_map(struct kgsl_pagetable *pagetable',['gmem_p_gmap']),
           (MMU,'kgsl_mmu_unmap(struct kgsl_pagetable *pagetable',['gmem_p_gumap']),(IOMMU,'static int kgsl_iommu_fault_handler(',['gmem_e_smmu_fault']),
           (PSC,'int kgsl_devfreq_get_dev_status(',['bus_e_ddr_pressure']),(A6,'static int a6xx_reset(',['stat_e_hw_reset']),
           (A6,'static void a6xx_err_callback(',['stat_e_hw_error']),(A6,'static void a6xx_cp_hw_err_callback(',['stat_e_cp_error']),
           (AD,'void adreno_hang_int_callback(',['stat_e_hw_hang']),(PRE,'static void _a6xx_preemption_worker(',['sched_e_preempt_timeout'])]
FACTORY_TAP_OFFSETS={'sched_p_flush':0,'sched_p_flush_composite':32,'sched_p_submit':64,'sched_p_submit_composite':96,'sched_e_preempt_timeout':128,
    'gmem_p_alloc':132,'gmem_p_free':164,'gmem_p_gmap':196,'gmem_p_gumap':228,'gmem_p_get_area':260,'gmem_p_cmap':292,'gmem_p_cfault':324,
    'gmem_e_smmu_fault':356,'bus_e_ddr_pressure':360,'stat_e_cp_error':364,'stat_e_hw_error':368,'stat_e_hw_hang':372,'stat_e_hw_reset':376}
PRELUDE=r'''
#include <assert.h>
#include <errno.h>
#include <stdarg.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef uint8_t u8;typedef uint16_t u16;typedef uint32_t u32;typedef uint64_t u64;typedef int64_t s64;typedef unsigned long ulong;
typedef long ssize_t_k;
#define BIT(n) (1UL<<(n))
#define ARRAY_SIZE(a) (sizeof(a)/sizeof((a)[0]))
#define BUILD_BUG_ON(c) _Static_assert(!(c),#c)
#define container_of(p,t,m) ((t *)((char *)(p)-offsetof(t,m)))
#define min(a,b) ((a)<(b)?(a):(b))
#define max(a,b) ((a)>(b)?(a):(b))
#define READ_ONCE(x) (x)
#define WRITE_ONCE(x,v) ((x)=(v))
#define PAGE_SIZE 4096
#define EXPORT_SYMBOL(x)
#define rmb() ((void)0)
#define smp_wmb() ((void)0)
#define __must_check
static u64 div_u64(u64 a,u32 b){return a/b;}
static u64 div64_u64(u64 a,u64 b){assert(b);return a/b;}
static int fls64(u64 x){return x?64-__builtin_clzll(x):0;}
static int test_bit(int nr,const unsigned long *a){return (*a>>nr)&1;}
static void set_bit(int nr,unsigned long *a){*a|=1UL<<nr;}
static void clear_bit(int nr,unsigned long *a){*a&=~(1UL<<nr);}
static int test_and_set_bit(int nr,unsigned long *a){int o=test_bit(nr,a);set_bit(nr,a);return o;}
static size_t strlcpy(char *d,const char *s,size_t n){size_t l=strlen(s);if(n){size_t c=l>=n?n-1:l;memcpy(d,s,c);d[c]=0;}return l;}
static int kstrtoint(const char *s,unsigned int base,int *res){char *e;long v;(void)base;if(!*s)return -EINVAL;v=strtol(s,&e,10);
  if(e==s)return -EINVAL;if(*e=='\n')e++;if(*e)return -EINVAL;*res=(int)v;return 0;}
/* ---- fake clocks ---- */
static u64 now_ns;
static u64 ktime_get_ns(void){return now_ns;}
static u64 alwayson;
/* ---- locks: double lock / unlock without lock abort, irq depth tracked ---- */
typedef struct {int held;} spinlock_t;
#define DEFINE_SPINLOCK(x) spinlock_t x={0}
static int irq_off;
#define spin_lock_irqsave(l,f) do{assert(!(l)->held);(l)->held=1;irq_off++;(f)=0x5a;}while(0)
#define spin_unlock_irqrestore(l,f) do{assert((l)->held);assert((f)==0x5a);(l)->held=0;irq_off--;}while(0)
static int trylock_fail;
#define spin_trylock_irqsave(l,f) ((trylock_fail||(l)->held)?0:((l)->held=1,irq_off++,(f)=0x5a,1))
typedef struct {int readers,writer;} rwlock_t;
static void read_lock(rwlock_t *l){assert(!l->writer);l->readers++;}
static void read_unlock(rwlock_t *l){assert(l->readers>0);l->readers--;}
static void write_lock(rwlock_t *l){assert(!l->writer&&!l->readers);l->writer=1;}
static void write_unlock(rwlock_t *l){assert(l->writer);l->writer=0;}
struct mutex {int held;};
static void mutex_lock(struct mutex *m){assert(!m->held);m->held=1;}
static void mutex_unlock(struct mutex *m){assert(m->held);m->held=0;}
/* ---- lists ---- */
struct list_head {struct list_head *next,*prev;};
static void INIT_LIST_HEAD(struct list_head *l){l->next=l->prev=l;}
static void list_add_tail(struct list_head *n,struct list_head *h){n->prev=h->prev;n->next=h;h->prev->next=n;h->prev=n;}
static void list_del_init(struct list_head *n){n->prev->next=n->next;n->next->prev=n->prev;INIT_LIST_HEAD(n);}
#define list_entry(p,t,m) container_of(p,t,m)
#define list_for_each_entry(pos,head,member) for(pos=list_entry((head)->next,__typeof__(*pos),member);&pos->member!=(head);pos=list_entry(pos->member.next,__typeof__(*pos),member))
/* ---- kref / work ---- */
struct kref {int refcount;};
static int kref_get_unless_zero(struct kref *k){if(!k->refcount)return 0;k->refcount++;return 1;}
static int kref_put(struct kref *k,void (*rel)(struct kref *)){assert(k->refcount>0);if(--k->refcount==0){rel(k);return 1;}return 0;}
struct work_struct;typedef void (*work_func_t)(struct work_struct *);
struct work_struct {work_func_t func;int pending;};
#define INIT_WORK(w,f) do{(w)->func=(f);(w)->pending=0;}while(0)
struct workqueue_struct {int x;};
static struct workqueue_struct mem_wq;
static struct work_struct *workq[64];static int nwork;
static bool queue_work(struct workqueue_struct *wq,struct work_struct *w){assert(wq==&mem_wq);assert(!w->pending);w->pending=1;assert(nwork<64);workq[nwork++]=w;return true;}
static void run_work(void){while(nwork){struct work_struct *w=workq[--nwork];assert(irq_off==0);w->pending=0;w->func(w);}}
static struct {struct workqueue_struct *mem_workqueue;} kgsl_driver={&mem_wq};
/* ---- static key ---- */
struct static_key {int enabled;};
#define STATIC_KEY_INIT_FALSE {0}
#define static_key_enabled(k) ((k)->enabled>0)
static void static_key_enable(struct static_key *k){k->enabled=1;}
static int vz_fail,allocs;
static void *vzalloc(size_t n){if(vz_fail)return NULL;allocs++;return calloc(1,n);}
static int scnprintf(char *buf,size_t size,const char *fmt,...) __attribute__((format(printf,3,4)));
static int scnprintf(char *buf,size_t size,const char *fmt,...){va_list ap;int n;if(!size)return 0;va_start(ap,fmt);n=vsnprintf(buf,size,fmt,ap);va_end(ap);if(n<0)return 0;return (size_t)n>=size?(int)size-1:n;}
/* ---- seq_file ---- */
struct seq_file {char buf[8192];size_t count;void *private;};
static void seq_printf(struct seq_file *s,const char *fmt,...) __attribute__((format(printf,2,3)));
static void seq_printf(struct seq_file *s,const char *fmt,...){va_list ap;va_start(ap,fmt);s->count+=vsnprintf(s->buf+s->count,sizeof(s->buf)-s->count,fmt,ap);va_end(ap);}
static void seq_puts(struct seq_file *s,const char *str){seq_printf(s,"%s",str);}
static void seq_write(struct seq_file *s,const void *d,size_t n){memcpy(s->buf+s->count,d,n);s->count+=n;}
/* ---- procfs ---- */
struct proc_dir_entry {char name[32];struct proc_dir_entry *parent;int (*show)(struct seq_file *,void *);void *data;int removed;umode_t_dummy;};
'''
PRELUDE=PRELUDE.replace('umode_t_dummy;','int mode;')
PRELUDE2=r'''
static struct proc_dir_entry pde[32];static int npde;
static struct proc_dir_entry *proc_mkdir(const char *n,struct proc_dir_entry *p){struct proc_dir_entry *e=&pde[npde++];strcpy(e->name,n);e->parent=p;return e;}
static struct proc_dir_entry *proc_create_single_data(const char *n,int mode,struct proc_dir_entry *p,int (*show)(struct seq_file *,void *),void *data){
  struct proc_dir_entry *e=proc_mkdir(n,p);e->mode=mode;e->show=show;e->data=data;return e;}
static void proc_remove(struct proc_dir_entry *e){if(e)e->removed=1;}
static struct proc_dir_entry *pde_find(struct proc_dir_entry *parent,const char *n){for(int i=0;i<npde;i++)if(pde[i].parent==parent&&!strcmp(pde[i].name,n)&&!pde[i].removed)return &pde[i];return NULL;}
static struct seq_file seq;
static int pde_read(struct proc_dir_entry *e){memset(&seq,0,sizeof(seq));seq.private=e->data;return e->show(&seq,NULL);}
/* ---- kgsl model ---- */
typedef struct {long counter;} atomic_long_t;
#define atomic_long_read(a) ((a)->counter)
enum {KGSL_MEM_ENTRY_KERNEL=0,KGSL_MEM_ENTRY_USER,KGSL_MEM_ENTRY_ION,KGSL_MEM_ENTRY_MAX};
#define KGSL_PROC_COMPOSITOR 0
struct pid {int nr;};
static int pid_nr(struct pid *p){return p?p->nr:0;}
struct kgsl_process_private {struct pid *pid;struct kref refcount;struct {atomic_long_t cur;u64 max;} stats[KGSL_MEM_ENTRY_MAX];
  rwlock_t ctxt_list_lock;struct list_head ctxt_list;struct proc_dir_entry *proc_dir;u64 gpu_busy_ticks;unsigned long pico_flags;int in_list;};
struct kgsl_device;
struct kgsl_context {unsigned int id;int priority;unsigned long flags;unsigned long priv;struct kgsl_process_private *proc_priv;struct kgsl_device *device;};
struct kgsl_pwrctrl;struct kgsl_mem_entry;
'''
MODEL=r'''
struct kgsl_pwrctrl {unsigned long power_flags;struct kgsl_clk_stats clk_stats;};
struct kgsl_pwrscale {unsigned long freq_table[16];struct {u64 busy_time,ram_time,ram_wait;} accum_stats;};
struct kgsl_memdesc_m {u8 data[40*820];};
struct kgsl_device {struct kgsl_pwrctrl pwrctrl;struct kgsl_pwrscale pwrscale;struct kgsl_online_tap *tap;struct kgsl_memdesc_m memstore;
  struct kgsl_context *ctx_by_id[64];struct mutex mutex;};
#define kgsl_context_idr ctx_by_id
/* memstore: 40 bytes per id like struct kgsl_devmemstore */
struct devmemstore_m {u32 soptimestamp,sbz,eoptimestamp,sbz2,preempted,sbz3,ref_wait_ts,sbz4,current_context,sbz5;};
#define KGSL_MEMSTORE_MAX 814
#define KGSL_MEMSTORE_OFFSET(id,field) ((id)*sizeof(struct devmemstore_m)+offsetof(struct devmemstore_m,field))
#define MEMSTORE_RB_OFFSET(rb,field) KGSL_MEMSTORE_OFFSET(((rb)->id+KGSL_MEMSTORE_MAX),field)
static void kgsl_sharedmem_readl(struct kgsl_memdesc_m *m,unsigned int *v,u64 off){assert(off+4<=sizeof(m->data));memcpy(v,m->data+off,4);}
static void memstore_set(struct kgsl_device *d,u64 off,u32 v){memcpy(d->memstore.data+off,&v,4);}
struct idr_m {int x;};
static void *idr_find(void *idr,unsigned int id){struct kgsl_context **t=idr;return id<64?t[id]:NULL;}
'''
MODEL2=r'''
struct adreno_ringbuffer {unsigned int id;struct adreno_dispatcher_drawqueue dispatch_q;};
struct adreno_dispatcher {unsigned int inflight;unsigned long priv;struct {int x;} timer;};
struct adreno_drawobj_profile_entry {u64 started;u64 retired;};
struct adreno_gpudev {void (*preemption_schedule)(void *);};
struct adreno_device {struct kgsl_device dev;struct adreno_ringbuffer rb[2];struct adreno_ringbuffer *cur_rb,*prev_rb,*next_rb;
  struct adreno_dispatcher dispatcher;unsigned long priv;unsigned long ft_policy;unsigned int profile_index;struct {void *hostptr;} profile_buffer;
  struct adreno_gpudev *gpudev;};
#define KGSL_DEVICE(a) (&(a)->dev)
#define ADRENO_GPU_DEVICE(a) ((a)->gpudev)
#define ADRENO_CONTEXT(c) container_of(c,struct adreno_context,base)
#define DRAWOBJ(obj) (&(obj)->base)
#define CMDOBJ(obj) container_of(obj,struct kgsl_drawobj_cmd,base)
#define ADRENO_DRAWOBJ_DISPATCH_DRAWQUEUE(d) (&(ADRENO_CONTEXT((d)->context)->rb->dispatch_q))
#define ADRENO_DRAWOBJ_RB(d) (ADRENO_CONTEXT((d)->context)->rb)
#define ADRENO_REG_RBBM_ALWAYSON_COUNTER_LO 75
#define ADRENO_REG_RBBM_ALWAYSON_COUNTER_HI 76
#define MARKEROBJ_TYPE 2
#define CMDOBJ_TYPE 1
#define ADRENO_DEVICE_DRAWOBJ_PROFILE 31
#define ADRENO_DRAWOBJ_PROFILE_COUNT 64
#define ADRENO_DISPATCHER_POWER 0
#define ADRENO_DISPATCHER_ACTIVE 1
#define ADRENO_CONTEXT_FAULT 3
#define ADRENO_PREEMPT_NONE 0
#define ENOENT_K ENOENT
struct adreno_submit_time {u64 ticks;u64 ktime;};
static struct adreno_device adev;
static struct kgsl_process_private *find_list[8];static int nfind;
'''
STUBS=r'''
/* readreg64 of the always-on counter only */
static void (*readreg_hook)(void);
static void adreno_readreg64(struct adreno_device *a,int lo,int hi,u64 *v){(void)a;assert(lo==ADRENO_REG_RBBM_ALWAYSON_COUNTER_LO&&hi==ADRENO_REG_RBBM_ALWAYSON_COUNTER_HI);*v=alwayson;if(readreg_hook){void (*h)(void)=readreg_hook;readreg_hook=NULL;h();}}
/* drawobj lifetime model: release asserts nobody can still find the object in a live queue slot */
static int destroyed;
static void assert_unpublished(struct kgsl_drawobj *d){for(int r=0;r<2;r++){struct adreno_dispatcher_drawqueue *q=&adev.rb[r].dispatch_q;
  for(unsigned int i=q->head;i!=q->tail;i=(i+1)%ADRENO_DISPATCH_DRAWQUEUE_SIZE)assert(DRAWOBJ(q->cmd_q[i])!=d);}}
static void kgsl_drawobj_destroy_object(struct kref *kref){struct kgsl_drawobj *d=container_of(kref,struct kgsl_drawobj,refcount);
  assert(irq_off==0);assert_unpublished(d);destroyed++;free(CMDOBJ(d));}
static void kgsl_drawobj_destroy(struct kgsl_drawobj *d){kref_put(&d->refcount,kgsl_drawobj_destroy_object);}
static void kgsl_drawobj_destroy_object_defer(struct kref *kref);
static struct kgsl_drawobj_cmd *new_cmd(struct kgsl_context *c,u32 ts){struct kgsl_drawobj_cmd *o=calloc(1,sizeof(*o));o->base.context=c;o->base.timestamp=ts;
  o->base.type=CMDOBJ_TYPE;o->base.refcount.refcount=1;return o;}
static void q_push(struct adreno_ringbuffer *rb,struct kgsl_drawobj_cmd *o){struct adreno_dispatcher_drawqueue *q=&rb->dispatch_q;q->cmd_q[q->tail]=o;q->tail=(q->tail+1)%ADRENO_DISPATCH_DRAWQUEUE_SIZE;q->inflight++;}
/* retire */
static u32 retired_ts[64];
static int kgsl_check_timestamp(struct kgsl_device *d,struct kgsl_context *c,u32 ts){(void)d;return ts<=retired_ts[c->id];}
#define trace_adreno_cmdbatch_retired(...) ((void)0)
#define trace_adreno_cmdbatch_queued(...) ((void)0)
#define trace_adreno_cmdbatch_submitted(...) ((void)0)
#define trace_kgsl_gpubusy(...) ((void)0)
static int adreno_is_a3xx(struct adreno_device *a){(void)a;return 0;}
static unsigned int adreno_get_rptr(struct adreno_ringbuffer *rb){(void)rb;return 0;}
static void _print_recovery(struct kgsl_device *d,struct kgsl_drawobj_cmd *c){(void)d;(void)c;}
/* queue */
static int get_timestamp(struct adreno_context *drawctxt,struct kgsl_drawobj *drawobj,unsigned int *timestamp,unsigned int user_ts){(void)user_ts;
  drawctxt->timestamp++;*timestamp=drawctxt->timestamp;drawobj->timestamp=*timestamp;return 0;}
static void _set_ft_policy(struct adreno_device *a,struct adreno_context *c,struct kgsl_drawobj_cmd *o){(void)a;(void)c;(void)o;}
static void _cmdobj_set_flags(struct adreno_context *c,struct kgsl_drawobj_cmd *o){(void)c;(void)o;}
/* sendcmd */
static int submit_rc;static u64 submit_cost_ns,submit_ticks_v,submit_ktime_v;static int preempt_sched_calls;
static int adreno_gpu_halt(struct adreno_device *a){(void)a;return 0;}
static int kgsl_active_count_get(struct kgsl_device *d){(void)d;return 0;}
static void kgsl_active_count_put(struct kgsl_device *d){(void)d;}
static int adreno_ringbuffer_submitcmd(struct adreno_device *a,struct kgsl_drawobj_cmd *o,struct adreno_submit_time *t){(void)a;(void)o;
  assert(a->dev.mutex.held);now_ns+=submit_cost_ns;t->ticks=submit_ticks_v;t->ktime=submit_ktime_v;return submit_rc;}
static void del_timer_sync(void *t){(void)t;}
static void fault_detect_read(struct adreno_device *a){(void)a;}
static void start_fault_timer(struct adreno_device *a){(void)a;}
struct completion {int x;};
static void reinit_completion(void *c){(void)c;}
static void kgsl_pwrscale_midframe_timer_restart(struct kgsl_device *d){(void)d;}
#define dev_err(...) ((void)0)
static unsigned long jiffies;static unsigned int adreno_drawobj_timeout=2000;
static unsigned long msecs_to_jiffies(unsigned int m){return m/10;}
#define do_div(n,base) ({u32 __r=(n)%(base);(n)/=(base);__r;})
static int adreno_in_preempt_state(struct adreno_device *a,int s){(void)a;(void)s;return 0;}
static int drawqueue_is_current(struct adreno_dispatcher_drawqueue *q){(void)q;return 0;}
static void mod_timer(void *t,unsigned long e){(void)t;(void)e;}
static void preempt_schedule_cb(void *a){(void)a;preempt_sched_calls++;}
/* processes */
static struct kgsl_process_private *kgsl_process_private_find(int pid){for(int i=0;i<nfind;i++)if(find_list[i]->pid->nr==pid&&find_list[i]->in_list){
  find_list[i]->refcount.refcount++;return find_list[i];}return NULL;}
static void priv_rel(struct kref *k){(void)k;}
static void kgsl_process_private_put(struct kgsl_process_private *p){if(p)kref_put(&p->refcount,priv_rel);}
struct device {void *driver_data;};
struct device_attribute {int x;};
static void *dev_get_drvdata(struct device *d){return d->driver_data;}
/* dma-buf */
struct dma_buf {int x;};
struct kgsl_dma_buf_meta {void *entry;void *attach;struct dma_buf *dmabuf;};
struct kgsl_memdesc {int usermem;};
struct kgsl_mem_entry {struct kgsl_memdesc memdesc;void *priv_data;};
static int kgsl_memdesc_usermem_type(struct kgsl_memdesc *m){return m->usermem;}
'''
MAIN=r'''
/* ---- snippet wrappers ---- */
static int composite_hits;
static void open_composite(struct kgsl_process_private *private,struct pid *cur_pid){int i;
/* SNIP open_composite */
}
static void ddr_pressure(struct kgsl_pwrscale *pwrscale){
/* SNIP ddr_pressure */
}
struct kgsl_device_private {struct kgsl_process_private *process_priv;};
static struct adreno_context *ctx_list_add(struct kgsl_device_private *dev_priv,struct adreno_context *drawctxt){
/* SNIP ctx_list_add */
	return drawctxt;}
static void ctx_list_del(struct kgsl_context *context,struct adreno_context *drawctxt){
/* SNIP ctx_list_del */
}
static void proc_dir(struct kgsl_process_private *private,const char *name){
/* SNIP proc_dir */
}
static void replay_reset(struct kgsl_drawobj_cmd **replay,int i){
/* SNIP replay_reset */
}
static void quiescent(void){assert(irq_off==0);for(int r=0;r<2;r++)assert(!adev.rb[r].dispatch_q.lock.held);}
static struct pid pids[8];static struct kgsl_process_private privs[8];
static struct kgsl_process_private *mkpriv(int i,int pid){struct kgsl_process_private *p=&privs[i];memset(p,0,sizeof(*p));pids[i].nr=pid;p->pid=&pids[i];
  p->refcount.refcount=1;p->in_list=1;rwlock_init_m(&p->ctxt_list_lock);INIT_LIST_HEAD(&p->ctxt_list);find_list[i]=p;if(nfind<=i)nfind=i+1;return p;}
static struct adreno_context *mkctx(unsigned int id,int prio,struct kgsl_process_private *p,int rb){struct adreno_context *c=calloc(1,sizeof(*c));
  c->base.id=id;c->base.priority=prio;c->base.proc_priv=p;c->base.device=&adev.dev;c->rb=&adev.rb[rb];INIT_LIST_HEAD(&c->priv_node);adev.dev.ctx_by_id[id]=&c->base;return c;}
static void check_flow(const u64 *got,const u64 *want){for(int i=0;i<5;i++)if(got[i]!=want[i]){fprintf(stderr,"flow[%d] %llu want %llu\n",i,(unsigned long long)got[i],(unsigned long long)want[i]);abort();}}
int main(void){char buf[PAGE_SIZE];int n;
 /* factory layouts */
 _Static_assert(sizeof(struct kgsl_online_tap)==EXP_TAP_SIZE,"tap size");
 /* EXP_TAP_OFFSETS */
 assert(MEMSTORE_RB_OFFSET(&adev.rb[0],current_context)==EXP_RB0_CURCTX);
 _Static_assert(SUBMIT_RETIRE_TICKS_SIZE==KGSL_FRAME_FLOW_ENTRIES,"ring = flow");
 adev.rb[0].id=0;adev.rb[1].id=1;adev.cur_rb=&adev.rb[0];
 /* ===== TAP ===== */
 assert(kgsl_online_tap_data()==NULL);kgsl_online_tap_clear();
 assert(kgsl_tap_result_show(&adev.dev,buf)==(int)strlen("GPUTAP Not Enabled\n")&&!strcmp(buf,"GPUTAP Not Enabled\n"));
 assert(kgsl_tap_begin()==0);
 vz_fail=1;assert(kgsl_online_tap_init(&adev.dev)==-ENOMEM&&!kgsl_tap_enabled()&&!adev.dev.tap);vz_fail=0;
 assert(kgsl_online_tap_init(&adev.dev)==0&&kgsl_tap_enabled()&&adev.dev.tap&&kgsl_tap_get_device()==&adev.dev&&allocs==1);
 {struct kgsl_device other;memset(&other,0,sizeof(other));assert(kgsl_online_tap_init(&other)==0&&!other.tap&&allocs==1&&kgsl_tap_get_device()==&adev.dev);}
 assert(kgsl_online_tap_data()==adev.dev.tap);
 /* buckets vs the factory 62-clz switch */
 {static const u64 d[]={BUCKET_INPUTS};static const unsigned int w[]={BUCKET_WANT};
  for(unsigned int i=0;i<ARRAY_SIZE(d);i++){if(kgsl_tap_bucket(d[i])!=w[i]){fprintf(stderr,"bucket(%llu)=%u want %u\n",(unsigned long long)d[i],kgsl_tap_bucket(d[i]),w[i]);abort();}}}
 now_ns=1000000;{u64 t=kgsl_tap_begin();assert(t==1000000);now_ns+=3000000;kgsl_tap_period(gmem_p_gmap,t);assert(adev.dev.tap->gmem_p_gmap[4]==1);
  kgsl_tap_period(gmem_p_gmap,0);assert(adev.dev.tap->gmem_p_gmap[4]==1);}
 kgsl_tap_event(stat_e_hw_hang);kgsl_tap_event(stat_e_hw_hang);assert(adev.dev.tap->stat_e_hw_hang==2);
 for(unsigned int i=0;i<sizeof(*adev.dev.tap)/4;i++)((u32 *)adev.dev.tap)[i]=0x100+i;
 n=kgsl_tap_result_show(&adev.dev,buf);assert(n==(int)strlen(buf));
 if(strcmp(buf,TAP_TEXT)){fprintf(stderr,"tap text:\n%s\nwant:\n%s\n",buf,TAP_TEXT);abort();}
 {struct device dv={&adev.dev};char b2[PAGE_SIZE];assert(gputap_show(&dv,NULL,b2)==n&&!strcmp(b2,buf));}
 kgsl_online_tap_clear();for(unsigned int i=0;i<sizeof(*adev.dev.tap)/4;i++)assert(((u32 *)adev.dev.tap)[i]==0);
 /* DDR pressure */
 {struct kgsl_pwrscale ps;memset(&ps,0,sizeof(ps));ddr_pressure(&ps);assert(adev.dev.tap->bus_e_ddr_pressure==0);
  ps.accum_stats.ram_time=1000;ps.accum_stats.ram_wait=899;ddr_pressure(&ps);assert(adev.dev.tap->bus_e_ddr_pressure==0);
  ps.accum_stats.ram_wait=900;ddr_pressure(&ps);assert(adev.dev.tap->bus_e_ddr_pressure==1);}
 /* ===== busy / load windows (factory kgsl_pwrctrl_busy_time) ===== */
 {struct kgsl_clk_stats *s=&adev.dev.pwrctrl.clk_stats;static const u64 smp[][3]={BUSY_SAMPLES};static const u64 exp[][4]={BUSY_WANT};
  adev.dev.pwrscale.freq_table[0]=587000000;
  for(unsigned int i=0;i<ARRAY_SIZE(smp);i++){kgsl_pwrctrl_busy_time(&adev.dev,smp[i][0],smp[i][1],smp[i][2]);
   if(s->busy_percent!=exp[i][0]||s->load_percent!=exp[i][1]||s->cur_freq!=exp[i][2]||s->total_old!=exp[i][3]){
    fprintf(stderr,"busy sample %u: %llu %llu %llu %u\n",i,(unsigned long long)s->busy_percent,(unsigned long long)s->load_percent,(unsigned long long)s->cur_freq,s->total_old);abort();}}
  adev.dev.pwrscale.freq_table[0]=0;kgsl_pwrctrl_busy_time(&adev.dev,100,50,1);adev.dev.pwrscale.freq_table[0]=587000000;
  /* total_stats: printed, then zeroed while the GPU bus is off */
  kgsl_procfs_init(&adev.dev);
  struct proc_dir_entry *root=pde_find(NULL,"gpu_procs"),*ts=pde_find(root,"total_stats"),*cs=pde_find(root,"compositor");
  assert(root&&ts&&cs&&ts->mode==0444&&cs->mode==0444&&ts->data==&adev.dev);
  s->busy_percent=37;s->load_percent=21;s->cur_freq=441600000;adev.dev.pwrctrl.power_flags=BIT(GPU_PROCS_PWRFLAGS_AXI_ON);
  assert(pde_read(ts)==0&&!strcmp(seq.buf,"busy_percent: 37\nload_percent: 21\ncur_freq: 441600000\nmax_freq: 587000000\n")&&s->busy_percent==37);
  adev.dev.pwrctrl.power_flags=0;assert(pde_read(ts)==0&&s->busy_percent==0&&s->load_percent==0&&s->cur_freq==0);
  assert(pde_read(ts)==0&&!strcmp(seq.buf,"busy_percent: 0\nload_percent: 0\ncur_freq: 0\nmax_freq: 587000000\n"));}
 /* ===== composite ===== */
 {struct kgsl_process_private *a=mkpriv(0,100),*b=mkpriv(1,200),*c=mkpriv(2,300),*d=mkpriv(3,400);struct device dv={NULL};
  const char *in="100,200\n";assert(composite_store(&dv,NULL,in,strlen(in))==(ssize_t)strlen(in));
  assert(test_bit(KGSL_PROC_COMPOSITOR,&a->pico_flags)&&test_bit(KGSL_PROC_COMPOSITOR,&b->pico_flags)&&composite[0]==100&&composite[1]==200);
  assert(a->refcount.refcount==1&&b->refcount.refcount==1&&!strcmp(in,"100,200\n"));
  in="300";composite_store(&dv,NULL,in,3);assert(test_bit(KGSL_PROC_COMPOSITOR,&c->pico_flags)&&composite[0]==100&&composite[1]==200);
  in="0,400";composite_store(&dv,NULL,in,5);assert(!d->pico_flags&&composite[0]==100);
  in="abc,400";composite_store(&dv,NULL,in,7);assert(!d->pico_flags&&composite[0]==100);
  in="400,xyz";composite_store(&dv,NULL,in,7);assert(test_bit(KGSL_PROC_COMPOSITOR,&d->pico_flags)&&composite[0]==400&&composite[1]==400);
  in="555,666";composite_store(&dv,NULL,in,7);assert(composite[0]==555&&composite[1]==666);
  {char big[200];memset(big,'1',sizeof(big)-1);big[199]=0;assert(composite_store(&dv,NULL,big,199)==199);}
  /* kgsl_open: a restarted compositor gets its flag back */
  struct kgsl_process_private *e=mkpriv(4,666),*f=mkpriv(5,777);struct pid pe={666},pf={777};
  open_composite(e,&pe);open_composite(f,&pf);assert(test_bit(KGSL_PROC_COMPOSITOR,&e->pico_flags)&&!f->pico_flags);}
 /* ===== dma-buf accessor ===== */
 {struct dma_buf db;struct kgsl_dma_buf_meta meta={NULL,NULL,&db};struct kgsl_mem_entry ent={{KGSL_MEM_ENTRY_ION},&meta};
  assert(kgsl_get_dma_buf(&ent)==&db);ent.priv_data=NULL;assert(kgsl_get_dma_buf(&ent)==NULL);ent.priv_data=&meta;
  ent.memdesc.usermem=KGSL_MEM_ENTRY_KERNEL;assert(kgsl_get_dma_buf(&ent)==NULL);assert(kgsl_get_dma_buf(NULL)==NULL);}
 /* ===== per-process proc entries and context list ===== */
 struct kgsl_process_private *P=mkpriv(6,4242);
 proc_dir(P,"4242");{struct proc_dir_entry *root=pde_find(NULL,"gpu_procs"),*pd=pde_find(root,"4242"),*st=pde_find(pd,"status");
  assert(pd==P->proc_dir&&st&&st->mode==0444&&(long)st->data==4242);}
 struct kgsl_device_private dp={P};
 struct adreno_context *C1=mkctx(7,8,P,0),*C2=mkctx(9,0,P,1),*C3=mkctx(11,8,P,0);
 assert(ctx_list_add(&dp,C1)==C1&&ctx_list_add(&dp,C2)==C2&&ctx_list_add(&dp,C3)==C3&&!P->ctxt_list_lock.writer);
 /* ===== queue: queue time, latest compositor ts ===== */
 {struct kgsl_drawobj_cmd *o=new_cmd(&C2->base,0);unsigned int ts;now_ns=5000000000ULL;C2->timestamp=40;
  assert(_queue_cmdobj(&adev,C2,o,&ts,0)==0&&ts==41&&o->queue_ktime==5000000000ULL&&latest_compositor_ts==41&&C2->queued==1);
  struct kgsl_drawobj_cmd *o2=new_cmd(&C1->base,0);C1->timestamp=7;assert(_queue_cmdobj(&adev,C1,o2,&ts,0)==0&&latest_compositor_ts==41);
  free(o);free(o2);C2->drawqueue_tail=C2->drawqueue_head=C1->drawqueue_tail=C1->drawqueue_head=0;C2->queued=C1->queued=0;}
 /* ===== sendcmd: submit time, ringbuffer queue, TAP submit rows ===== */
 {struct adreno_gpudev gd={preempt_schedule_cb};adev.gpudev=&gd;kgsl_online_tap_clear();
  struct kgsl_drawobj_cmd *o=new_cmd(&C2->base,41);submit_cost_ns=SUBMIT_COST_A;submit_ticks_v=1000000;submit_ktime_v=5000100000ULL;
  assert(sendcmd(&adev,o)==0);quiescent();assert(o->submit_ticks==1000000&&o->submit_ktime==5000100000ULL&&adev.rb[1].dispatch_q.cmd_q[0]==o&&adev.rb[1].dispatch_q.tail==1);
  assert(adev.dev.tap->sched_p_submit_composite[SUBMIT_BUCKET_A]==1&&adev.dev.tap->sched_p_submit[SUBMIT_BUCKET_A]==0&&preempt_sched_calls==1);
  struct kgsl_drawobj_cmd *p=new_cmd(&C1->base,8);submit_cost_ns=SUBMIT_COST_B;assert(sendcmd(&adev,p)==0);
  assert(adev.dev.tap->sched_p_submit[SUBMIT_BUCKET_B]==1&&adev.rb[0].dispatch_q.cmd_q[0]==p);
  struct kgsl_drawobj_cmd *f=new_cmd(&C1->base,9);submit_rc=-ENOSPC;assert(sendcmd(&adev,f)==-ENOSPC&&adev.rb[0].dispatch_q.tail==1);
  for(int i=0;i<8;i++)assert(adev.dev.tap->sched_p_submit[i]==(i==SUBMIT_BUCKET_B));submit_rc=0;free(f);
  adev.dispatcher.inflight=0;
  /* ===== preemption audit ===== */
  /* rb0 runs C1 ts 8 (started, not ended); switch rb0 -> rb1 */
  memstore_set(&adev.dev,MEMSTORE_RB_OFFSET(&adev.rb[0],current_context),7);memstore_set(&adev.dev,KGSL_MEMSTORE_OFFSET(7,soptimestamp),8);
  memstore_set(&adev.dev,KGSL_MEMSTORE_OFFSET(7,eoptimestamp),7);
  memstore_set(&adev.dev,MEMSTORE_RB_OFFSET(&adev.rb[1],current_context),9);memstore_set(&adev.dev,KGSL_MEMSTORE_OFFSET(9,soptimestamp),40);
  memstore_set(&adev.dev,KGSL_MEMSTORE_OFFSET(9,eoptimestamp),40);
  adev.prev_rb=&adev.rb[0];adev.cur_rb=&adev.rb[1];alwayson=AUD_T0;
  audit_preemption_ticks(&adev,adev.cur_rb);audit_preemption_ticks(&adev,adev.prev_rb);quiescent();
  assert(p->preempted&&p->preempt_start==AUD_T0&&!o->preempted&&p->base.refcount.refcount==1&&o->base.refcount.refcount==1&&destroyed==0);
  /* back to rb0 */
  adev.prev_rb=&adev.rb[1];adev.cur_rb=&adev.rb[0];alwayson=AUD_T1;
  audit_preemption_ticks(&adev,adev.cur_rb);audit_preemption_ticks(&adev,adev.prev_rb);quiescent();
  assert(!p->preempted&&p->preempted_ticks==AUD_T1-AUD_T0&&!o->preempted);
  /* a command that already ended is not marked when its ringbuffer leaves */
  memstore_set(&adev.dev,KGSL_MEMSTORE_OFFSET(7,eoptimestamp),8);adev.prev_rb=&adev.rb[0];adev.cur_rb=&adev.rb[1];
  audit_preemption_ticks(&adev,adev.prev_rb);assert(!p->preempted);memstore_set(&adev.dev,KGSL_MEMSTORE_OFFSET(7,eoptimestamp),7);
  audit_preemption_ticks(&adev,NULL);adev.dev.ctx_by_id[7]=NULL;audit_preemption_ticks(&adev,&adev.rb[0]);assert(!p->preempted);adev.dev.ctx_by_id[7]=&C1->base;
  /* ===== retire: render times, process GPU time, frame flow ===== */
  struct adreno_drawobj_profile_entry prof[64];memset(prof,0,sizeof(prof));adev.profile_buffer.hostptr=prof;
  set_bit(CMDOBJ_PROFILE,&p->priv);p->profile_index=3;prof[3].started=RET_START;prof[3].retired=RET_END;
  retired_ts[7]=8;C1->ticks_index=7;
  assert(adreno_dispatch_retire_drawqueue(&adev,&adev.rb[0].dispatch_q)==1);quiescent();
  assert(destroyed==1&&adev.rb[0].dispatch_q.head==1&&adev.rb[0].dispatch_q.cmd_q[0]==NULL);
  assert(C1->raw_render_ticks==RET_END-RET_START&&C1->render_ticks==EXP_RENDER&&C1->render_valid&&P->gpu_busy_ticks==EXP_RENDER);
  assert(C1->ticks_index==0&&C1->submit_retire_ticks[7]==RET_END-1000000);
  {u64 fl[40];assert(get_frame_flow(fl,8)==0);for(int i=0;i<40;i++)assert(fl[i]==0);}  /* not a runtime context */
  /* compositor command on rb1 */
  set_bit(CMDOBJ_PROFILE,&o->priv);o->profile_index=5;prof[5].started=FLOW_START;prof[5].retired=FLOW_END;retired_ts[9]=41;C2->ticks_index=2;
  o->preempted_ticks=FLOW_PRE;
  assert(adreno_dispatch_retire_drawqueue(&adev,&adev.rb[1].dispatch_q)==1&&destroyed==2);
  assert(C2->render_ticks==EXP_FLOW_RENDER&&P->gpu_busy_ticks==EXP_RENDER+EXP_FLOW_RENDER);
  {u64 fl[40];static const u64 want[5]={FLOW_WANT};assert(get_frame_flow(fl,8)==0);check_flow(&fl[35],want);for(int i=0;i<35;i++)assert(fl[i]==0);
   assert(get_frame_flow(fl,7)==-EINVAL&&get_frame_flow(fl,9)==-EINVAL);trylock_fail=1;assert(get_frame_flow(fl,8)==-EBUSY);trylock_fail=0;quiescent();}
  /* wraparound: oldest first */
  {static const u64 base[5]={FLOW_WANT};for(int k=0;k<10;k++){struct kgsl_drawobj_cmd *w=new_cmd(&C2->base,100+k);w->queue_ktime=1000*k;w->submit_ktime=2000000;
     w->submit_ticks=0;update_frame_flow_cache(w,(2+1+k)%8,192,384);free(w);}
   u64 fl[40];assert(get_frame_flow(fl,8)==0);for(int i=0;i<8;i++){assert(fl[i*5]==102+i&&fl[i*5+1]==(u64)(2+i)&&fl[i*5+2]==2000&&fl[i*5+3]==2010&&fl[i*5+4]==2020);}
   update_frame_flow_cache(NULL,1,0,0);update_frame_flow_cache((struct kgsl_drawobj_cmd *)base,8,0,0);update_frame_flow_cache((struct kgsl_drawobj_cmd *)base,-1,0,0);
   u64 fl2[40];get_frame_flow(fl2,8);assert(!memcmp(fl,fl2,sizeof(fl)));}
  /* compositor procfs node: binary 328 bytes */
  {struct proc_dir_entry *cs=pde_find(pde_find(NULL,"gpu_procs"),"compositor");latest_compositor_ts=41;
   assert(pde_read(cs)==0&&seq.count==328);u64 v[41];memcpy(v,seq.buf,328);assert(v[0]==41);u64 fl[40];get_frame_flow(fl,8);assert(!memcmp(&v[1],fl,320));
   trylock_fail=1;assert(pde_read(cs)==-EINVAL);trylock_fail=0;}
  /* per-process status */
  {struct proc_dir_entry *st=pde_find(pde_find(pde_find(NULL,"gpu_procs"),"4242"),"status");P->stats[KGSL_MEM_ENTRY_KERNEL].cur.counter=123456;
   assert(pde_read(st)==0);if(strcmp(seq.buf,STATUS_TEXT)){fprintf(stderr,"status:\n%s\nwant:\n%s\n",seq.buf,STATUS_TEXT);abort();}
   assert(!P->ctxt_list_lock.readers&&P->refcount.refcount==1);
   P->in_list=0;assert(pde_read(st)==-ENODEV);P->in_list=1;}
  /* detach unlinks the context */
  ctx_list_del(&C3->base,C3);ctx_list_del(&C3->base,C3);{struct adreno_context *it;int k=0;list_for_each_entry(it,&P->ctxt_list,priv_node)k++;assert(k==2);}
  {struct adreno_context *never=mkctx(13,8,P,0);ctx_list_del(&never->base,never);free(never);}
  /* replay resets the accounting */
  {struct kgsl_drawobj_cmd *r=new_cmd(&C1->base,50);r->preempted=true;r->preempted_ticks=99;replay_reset(&r,0);assert(!r->preempted&&!r->preempted_ticks);free(r);}
  /* ===== audit vs concurrent retire / reset ===== */
  {struct kgsl_drawobj_cmd *a1=new_cmd(&C1->base,60),*a2=new_cmd(&C1->base,61);struct adreno_dispatcher_drawqueue *q=&adev.rb[0].dispatch_q;
   hq=q;q->head=q->tail=0;q_push(&adev.rb[0],a1);q_push(&adev.rb[0],a2);
   memstore_set(&adev.dev,KGSL_MEMSTORE_OFFSET(7,soptimestamp),60);memstore_set(&adev.dev,KGSL_MEMSTORE_OFFSET(7,eoptimestamp),59);
   adev.prev_rb=&adev.rb[0];adev.cur_rb=&adev.rb[1];
   /* the dispatcher retires a1 while the IRQ holds a reference: the IRQ does the last put, the release is deferred */
   victim=a1;readreg_hook=retire_victim;int before=destroyed;irq_off++;audit_preemption_ticks(&adev,&adev.rb[0]);irq_off--;quiescent();
   assert(destroyed==before&&nwork==1);run_work();assert(destroyed==before+1);
   /* a2 still queued and not the running command */
   assert(!a2->preempted&&a2->base.refcount.refcount==1);
   kgsl_drawobj_destroy_q(q,a2);
   /* a queue reset during the unlocked window: the audit must not walk on into stale slots */
   struct kgsl_drawobj_cmd *b1=new_cmd(&C3->base,70),*b2=new_cmd(&C3->base,71);q->head=q->tail=10;q_push(&adev.rb[0],b1);q_push(&adev.rb[0],b2);
   memstore_set(&adev.dev,KGSL_MEMSTORE_OFFSET(7,soptimestamp),999);
   stale=b2;kref_put_hook=reset_queue;audit_preemption_ticks(&adev,&adev.rb[0]);quiescent();assert(!kref_put_hook&&b1->base.refcount.refcount==1);
   kgsl_drawobj_destroy(DRAWOBJ(b1));q->head=q->tail=0;}
  free(C1);free(C2);free(C3);}
 /* deferred destroy runs from the workqueue */
 {struct kgsl_drawobj_cmd *z=new_cmd(NULL,1);int before=destroyed;kgsl_drawobj_destroy_object_defer(&z->base.refcount);assert(nwork==1&&destroyed==before);run_work();assert(destroyed==before+1);}
 kgsl_procfs_close();assert(pde_find(NULL,"gpu_procs")==NULL);
 free(adev.dev.tap);
 puts("PASS: TAP init/enable/clear/data, factory buckets, report text, gputap; DDR pressure; busy/load windows and total_stats; composite store "
      "parsing quirks and kgsl_open flag; dma-buf accessor; per-process proc dir and context list; queue time and latest compositor ts; "
      "sendcmd submit time, queue insert, TAP submit rows; preemption audit (switch out/in, ended command, guards); retire render times, "
      "process GPU time, frame flow only for runtime contexts, ring index; frame flow order/wrap/guards/-EINVAL/-EBUSY; compositor node; "
      "status text; detach unlink; replay reset; audit with concurrent retire (deferred release) and queue reset");
 return 0;}
'''
def factory_model():
    """Independent model of the factory arithmetic: caculate_and_inc_counter (switch on 62-clz), kgsl_pwrctrl_busy_time
    (10000 us windows, load = sum(busy*freq/max_freq)), retire render ticks (max(dur,pre)-pre), update_frame_flow_cache
    (10*(t-submit_ticks)/0xC0 + submit_ktime/1000), proc_status (10*x/0xC0) and the gputap text (factory format strings)."""
    def bucket(ns):
        if ns==0: return 0  # factory: clz(0)=64 -> default bucket 7; reconstruction puts 0 ns into the first bucket
        k=(ns.bit_length()-1)-1
        if k<=8: return 0
        if k<=17: return 1
        return {18:2,19:3,20:4,21:5,22:6}.get(k,7)
    ins=[1,1023,1024,1025,524287,524288,1048575,1048576,2097151,2097152,4194303,4194304,8388607,8388608,16777215,16777216,10**10,2**63]
    want=[bucket(x) for x in ins]
    M=2**64
    # busy windows
    samples=[(3000,1500,587000000),(3000,3000,300000000),(5000,1000,441600000),(9000,9000,587000000),(10000,0,100000000),(2000,1000,587000000)]
    tot=busy=load=0;bp=lp=0;told=0;exp=[]
    for t,b,f in samples:
        tot+=t;busy+=b;load+=(b*f)//587000000
        if tot>=10000:
            told=tot;lp=100*load//tot;bp=100*busy//tot;load=0;tot=0;busy=0
        exp.append((bp,lp,f,told))
    # sendcmd costs
    ca,cb=3_000_000,700
    # audit / retire
    T0,T1=50_000,80_000;rs,re_=100_000,140_000;pre=T1-T0
    render=max(re_-rs,pre)-pre
    fs,fe,fpre=1_000_000+19_200,1_000_000+192_000,4_000
    frender=max(fe-fs,fpre)-fpre
    sub_us=5000100000//1000
    flow=[41,5000000000//1000,sub_us,(10*((fs-1000000)%M))//192+sub_us,(10*((fe-1000000)%M))//192+sub_us]
    us=lambda x:(10*x)//192
    status=('us_on_gpu: %d\ngmem_used: %d\nus_render:\n  context-%u:\n  * %u\n    %u\n  context-%u:\n  * %u\n    %u\n'%(
        us(render+frender),123456,7,us(re_-rs),us(render),9,us(fe-fs),us(frender)))
    # tap text
    rows=[(' sched.p_flush',0),(' sched.p_flush_composite',8),(' sched.p_submit',16),(' sched.p_submit_composite',24),(' gmem.p_alloc',33),
          (' gmem.p_free',41),(' gmem.p_gmap',49),(' gmem.p_gumap',57),(' gmem.p_get_area',65),(' gmem.p_cmap',73),(' gmem.p_cfault',81)]
    ev=[(' sched.e_preempt_timeout',32),(' gmem.e_smmu_fault',89),(' bus.e_ddr_pressure',90),(' stat.e_cp_error',91),(' stat.e_hw_error',92),
        (' stat.e_hw_hang',93),(' stat.e_hw_reset',94)]
    t='Period Events:\n'+'%29s %-10s %-10s %-10s %-10s %-10s %-10s %-10s %-10s\n'%('','1ns-1us','1us-512us','512us-1ms','1ms-2ms','2ms-4ms','4ms-8ms','8ms-16ms','>16ms')
    for name,i in rows: t+='%-29s '%name+' '.join('0x%-8x'%(0x100+i+j) for j in range(8))+'\n'
    t+='\nException Events:\n'
    for name,i in ev: t+='%-29s : 0x%x\n'%(name,0x100+i)
    c=lambda s:'"'+s.replace('\\','\\\\').replace('\n','\\n').replace('"','\\"')+'"'
    defs={'EXP_TAP_SIZE':'380','EXP_RB0_CURCTX':'32592','BUCKET_INPUTS':','.join('%dULL'%x for x in ins),'BUCKET_WANT':','.join(map(str,want)),
          'BUSY_SAMPLES':','.join('{%d,%d,%d}'%s for s in samples),'BUSY_WANT':','.join('{%d,%d,%d,%d}'%e for e in exp),
          'SUBMIT_COST_A':str(ca),'SUBMIT_BUCKET_A':str(bucket(ca)),'SUBMIT_COST_B':str(cb),'SUBMIT_BUCKET_B':str(bucket(cb)),
          'AUD_T0':str(T0),'AUD_T1':str(T1),'RET_START':str(rs),'RET_END':str(re_),'EXP_RENDER':str(render),
          'FLOW_START':str(fs),'FLOW_END':str(fe),'FLOW_PRE':str(fpre),'EXP_FLOW_RENDER':str(frender),'FLOW_WANT':','.join('%dULL'%x for x in flow),
          'STATUS_TEXT':c(status),'TAP_TEXT':c(t)}
    offs=''.join('_Static_assert(offsetof(struct kgsl_online_tap,%s)==%d,"%s");\n '%(k,v,k) for k,v in FACTORY_TAP_OFFSETS.items())
    return defs,offs
def macro(text,start):
    i=text.index(start);j=i
    while True:
        e=text.index('\n',j)
        if not text[j:e].rstrip().endswith('\\'):return text[i:e+1]
        j=e+1
def snippet(text,a,b):
    i=text.index(a);return text[i:text.index(b,i)]
def tap_static(srcs,ex):
    res={};ok=True
    for f,sig,rows in TAP_SITES:
        body=ex.function(srcs[f],sig);got=re.findall(r'kgsl_tap_(?:period|event)\((\w+)',body)
        res[sig]={'want':rows,'got':got};ok&=sorted(got)==sorted(rows)
    return ok,res
def main():
    spec=importlib.util.spec_from_file_location('ex',Path(__file__).with_name('test-pico-sensor-mono-hook.py'));ex=importlib.util.module_from_spec(spec);spec.loader.exec_module(ex)
    files={f for f,_ in STRUCTS+FUNCS+DEFINES+GLOBALS+MACROS}|{ADRENO_CTX[0]}|{v[0] for v in SNIPPETS.values()}|{f for f,_,_ in TAP_SITES}
    srcs={n:(SOURCE/n).read_text() for n in files}
    defines='\n'.join(l for f,pat in DEFINES for l in srcs[f].splitlines() if re.match(pat,l))
    globs='\n'.join(l for f,pat in GLOBALS for l in srcs[f].splitlines() if re.match(pat,l))
    defs,offs=factory_model()
    head=''.join('#define %s %s\n'%(k,v) for k,v in defs.items())
    ctx=ex.function(srcs[ADRENO_CTX[0]],ADRENO_CTX[1])+';'
    stubs_ctx='struct plist_node {int x;};typedef struct {int x;} wait_queue_head_t;struct dentry;\n'
    main=MAIN.replace('/* EXP_TAP_OFFSETS */',offs)
    for k,(f,a,b) in SNIPPETS.items():main=main.replace('/* SNIP %s */'%k,snippet(srcs[f],a,b))
    code=(PRELUDE+PRELUDE2+defines+'\n'+'\n'.join(ex.function(srcs[f],s)+';' for f,s in STRUCTS)+'\n'+MODEL+stubs_ctx+ctx+'\n'+MODEL2+
          '#define rwlock_init_m(l) memset(l,0,sizeof(*(l)))\n'+STUBS+head+globs+'\n'+'\n'.join(macro(srcs[f],s) for f,s in MACROS)+'\n'+
          'struct kgsl_device *kgsl_tap_get_device(void);\nbool is_runtime_context(struct kgsl_context *context);\n'
          'void update_frame_flow_cache(struct kgsl_drawobj_cmd *cmdobj, int idx, u64 start, u64 end);\n'
          'typedef long ssize_t;\n'+
          '\n'.join(ex.function(srcs[f],s) for f,s in FUNCS)+'\n'+main)
    code=code.replace('typedef long ssize_t;\n','') if 'ssize_t' in PRELUDE else code
    out=BASE/'out/phoenix-kernel-recovery/kgsl-gpu-stats-tests';out.mkdir(exist_ok=True);(out/'harness.c').write_text(code)
    subprocess.run(['gcc','-std=gnu11','-g','-O1','-Wall','-Wno-unused-function','-Wno-unused-variable','-Werror=implicit-function-declaration','-Werror=format',
                    '-fsanitize=address,undefined','-fno-sanitize-recover=all','-fno-omit-frame-pointer',str(out/'harness.c'),'-o',str(out/'test')],check=True)
    r=subprocess.run([str(out/'test')],capture_output=True,text=True,timeout=120)
    sok,sres=tap_static(srcs,ex)
    rc=r.returncode if r.returncode else (0 if sok else 3)
    report={'sources':{n:hashlib.sha256((SOURCE/n).read_bytes()).hexdigest() for n in sorted(srcs)},'harness_sha256':hashlib.sha256(code.encode()).hexdigest(),
            'factory_model':defs,'tap_sites_ok':sok,'tap_sites':sres,'exit_code':rc,'harness_exit_code':r.returncode,'stdout':r.stdout,'stderr':r.stderr[-3000:],
            'scope':'Actual kgsl_tap.h/.c, kgsl_pwrctrl_busy_time, gputap_show, deferred drawobj release, frame flow cache, is_runtime_context, '
                    '_queue_drawobj/_queue_cmdobj, sendcmd, cmdobj_profile_ticks, retire_cmdobj, adreno_dispatch_retire_drawqueue, drawqueue_slot_live, '
                    'audit_preemption_ticks, composite_store, kgsl_get_dma_buf, proc_status/total_status/compositor show, kgsl_procfs_init/close and the '
                    'PICO snippets of kgsl_process_private_new, kgsl_devfreq_get_dev_status, adreno_drawctxt_create/detach, kgsl_process_init_debugfs and '
                    'recover_dispatch_q, with the real kgsl_online_tap/kgsl_clk_stats/kgsl_drawobj/kgsl_drawobj_cmd/adreno_context/drawqueue structs; '
                    'locks, lists, refcounts, workqueue, procfs/seq_file, memstore, clocks and registers modeled. Expected numbers from an independent '
                    'Python model of the factory arithmetic; every TAP hook checked statically against the factory call-site table.','device_modified':False}
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k not in ('tap_sites','factory_model')},indent=2))
    raise SystemExit(rc)
if __name__=='__main__':main()
