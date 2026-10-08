"""Execute the actual drivers/misc/pico_bsp_trace.c (whole file) under ASan/UBSan against a modeled kernel."""
from pathlib import Path
import hashlib,json,re,subprocess
BASE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro');SOURCE=BASE/'source/phoenix-kernel-recovery'
DRV='drivers/misc/pico_bsp_trace.c';HDR='include/linux/pico_bsp_trace.h';VMEV='include/linux/vm_event_item.h'
MODEL=r'''
#include <assert.h>
#include <stdarg.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/types.h>
typedef uint8_t u8;typedef uint16_t u16;typedef uint32_t u32;typedef uint64_t u64;typedef int32_t s32;typedef int64_t s64;
typedef unsigned int uid_t_;
#define uid_t uid_t_
typedef unsigned short umode_t;
#define __init
#define __weak __attribute__((weak))
#define EXPORT_SYMBOL(x) extern int __export_dummy_##x
#define late_initcall(f) int (*__lc_##f)(void) = f
#define late_initcall_sync(f) int (*__lcs_##f)(void) = f
#define READ_ONCE(x) (*(volatile __typeof__(x) *)&(x))
#define WRITE_ONCE(x,v) (*(volatile __typeof__(x) *)&(x) = (v))
#define ARRAY_SIZE(a) (sizeof(a)/sizeof((a)[0]))
#define min_t(t,a,b) ((t)(a)<(t)(b)?(t)(a):(t)(b))
#define max(a,b) ((a)>(b)?(a):(b))
#define NSEC_PER_SEC 1000000000LL
#define NSEC_PER_MSEC 1000000LL
#define NSEC_PER_USEC 1000LL
#define PAGE_SIZE 4096
#define PAGE_SHIFT 12
#define EINVAL 22
#define ENOMEM 12
#define EAGAIN 11
#define GFP_KERNEL 0
#define IS_ERR(p) ((unsigned long)(p)>=(unsigned long)-4095)
#define PTR_ERR(p) ((long)(p))
#define ERR_PTR(e) ((void *)(long)(e))
#define CONFIG_SWAP 1
#define CONFIG_COMPACTION 1
#define CONFIG_MIGRATION 1
#define CONFIG_SPECULATIVE_PAGE_FAULT 1
static int infos,errs;
#define pr_info(...) (infos++)
#define pr_err(...) (errs++)
static s64 div_s64(s64 a,s64 b){return a/b;}
static u64 div_u64(u64 a,u64 b){return a/b;}
static int fls64(u64 x){return x?64-__builtin_clzll(x):0;}
static u64 clock_ns;static u64 sched_clock(void){return clock_ns;}
static int scnprintf(char *b,size_t n,const char *f,...){va_list ap;int r;if(!n)return 0;va_start(ap,f);r=vsnprintf(b,n,f,ap);va_end(ap);if(r<0)return 0;return (size_t)r>=n?(int)n-1:r;}
/* allocation accounting with failure injection */
static int live_allocs,fail_alloc_at,alloc_seq;
static void *kzalloc(size_t n,int f){(void)f;if(fail_alloc_at&&++alloc_seq==fail_alloc_at)return NULL;live_allocs++;return calloc(1,n);}
static void *kmalloc_array(size_t c,size_t n,int f){return kzalloc(c*n,f);}
static void kfree(const void *p){if(p)live_allocs--;free((void *)p);}
/* locks */
struct mutex {int held;};
#define DEFINE_MUTEX(m) struct mutex m={0}
static void mutex_lock(struct mutex *m){assert(!m->held);m->held=1;}
static void mutex_unlock(struct mutex *m){assert(m->held);m->held=0;}
typedef struct {int held;} spinlock_t;
#define DEFINE_SPINLOCK(s) spinlock_t s={0}
#define spin_lock_irqsave(l,f) do{(f)=0;assert(!(l)->held);(l)->held=1;}while(0)
#define spin_unlock_irqrestore(l,f) do{(void)(f);assert((l)->held);(l)->held=0;}while(0)
/* current */
struct task_struct {char comm[16];int running;int (*fn)(void *);char name[32];};
static struct task_struct current_task={"stressapp-12345"};
#define current (&current_task)
/* completion */
struct completion {int done;};
static void init_completion(struct completion *c){c->done=0;}
static void reinit_completion(struct completion *c){c->done=0;}
static void complete(struct completion *c){c->done++;}
static struct mutex *no_lock_while_waiting;
static int waits;
static void wait_for_completion(struct completion *c){assert(c->done>0);c->done--;}
static void (*reader_hook)(void);static int reader_reads_on_wait;
static unsigned long wait_for_completion_timeout(struct completion *c,unsigned long t){assert(t==500);waits++;
  if(no_lock_while_waiting)assert(!no_lock_while_waiting->held);
  if(reader_reads_on_wait&&reader_hook)reader_hook();
  if(c->done>0){c->done--;return 1;}return 0;}
/* jiffies / kthreads */
static u64 jiffies64=1000000;
static u64 get_jiffies_64(void){return jiffies64;}
#define time_before64(a,b) ((s64)((a)-(b))<0)
static int stop_after=-1,stop_checks;
static int kthread_should_stop(void){stop_checks++;if(stop_after<0)return 0;return stop_checks>stop_after;}
static long schedule_timeout_interruptible(long t){assert(t>0);jiffies64+=t;return 0;}
static int kthread_fail_name;static char kthread_names[8][32];static int nthreads,threads_live,stops,wakes;
static struct task_struct *kthread_run(int (*fn)(void *),void *d,const char *name){(void)d;
  if(kthread_fail_name&&!strcmp(name,kthread_fail_name==1?"rb_consumer":"ts_timer_getdata_thread"))return ERR_PTR(-EAGAIN);
  struct task_struct *t=calloc(1,sizeof(*t));t->fn=fn;t->running=1;snprintf(t->name,32,"%s",name);snprintf(kthread_names[nthreads++%8],32,"%s",name);threads_live++;return t;}
static struct mutex *stop_lock_check;
static int kthread_stop(struct task_struct *t){assert(t&&t->running);t->running=0;threads_live--;stops++;free(t);return 0;}
static int wake_up_process(struct task_struct *t){assert(t&&t->running);wakes++;return 1;}
/* sysfs */
struct attribute {const char *name;umode_t mode;};
struct kobject {char name[32];};
struct kobj_attribute {struct attribute attr;ssize_t (*show)(struct kobject *,struct kobj_attribute *,char *);ssize_t (*store)(struct kobject *,struct kobj_attribute *,const char *,size_t);};
struct attribute_group {struct attribute **attrs;};
#define __ATTR(_n,_m,_s,_st) {.attr={.name=#_n,.mode=(_m)},.show=(_s),.store=(_st)}
static struct kobject *init_kobjs[4];static int ninit_kobjs;
static int fail_kobj,fail_group,kobjs_live,groups_live,notifies;static const struct attribute_group *groups[4];static char kobj_names[4][32];static int nkobj;
static struct kobject *kobject_create_and_add(const char *n,struct kobject *p){assert(!p);if(fail_kobj)return NULL;struct kobject *k=calloc(1,sizeof(*k));snprintf(k->name,32,"%s",n);snprintf(kobj_names[nkobj++%4],32,"%s",n);kobjs_live++;if(strcmp(n,"tracepoint"))init_kobjs[ninit_kobjs++]=k;return k;}
static void kobject_put(struct kobject *k){assert(k);kobjs_live--;free(k);}
static int sysfs_create_group(struct kobject *k,const struct attribute_group *g){assert(k);if(fail_group)return -ENOMEM;groups[groups_live++%4]=g;return 0;}
static void sysfs_remove_group(struct kobject *k,const struct attribute_group *g){(void)k;(void)g;groups_live--;}
static struct mutex *notify_lock_check;
static void sysfs_notify(struct kobject *k,const char *d,const char *a){assert(k&&!d&&!strcmp(a,"trace"));if(notify_lock_check)assert(!notify_lock_check->held);notifies++;}
/* ring buffer */
#define NCPU 2
#define RB_FL_OVERWRITE 1
#define RING_BUFFER_ALL_CPUS -1
struct ring_buffer_event {unsigned magic;struct ring_buffer_event *next;unsigned len;unsigned char data[];};
struct ring_buffer {struct ring_buffer_event *head[NCPU],*tail[NCPU],*last[NCPU];int open;unsigned long size;long resized;int resized_cpu;};
static int rb_fail_alloc,rb_reserve_fail,cur_cpu,rb_live,resize_rc;
static struct ring_buffer *ring_buffer_alloc(unsigned long size,int flags){assert(size==0x2000&&flags==RB_FL_OVERWRITE);if(rb_fail_alloc)return NULL;struct ring_buffer *b=calloc(1,sizeof(*b));b->size=size;rb_live++;return b;}
static void ring_buffer_free(struct ring_buffer *b){assert(b&&!b->open);for(int c=0;c<NCPU;c++){while(b->head[c]){struct ring_buffer_event *e=b->head[c];b->head[c]=e->next;free(e);}free(b->last[c]);}free(b);rb_live--;}
static struct ring_buffer_event *ring_buffer_lock_reserve(struct ring_buffer *b,unsigned long len){assert(b);if(rb_reserve_fail||len>4080)return NULL;
  struct ring_buffer_event *e=malloc(sizeof(*e)+len);e->magic=0xfeed;e->next=NULL;e->len=len;memset(e->data,0xAA,len);b->open++;return e;}
static void *ring_buffer_event_data(struct ring_buffer_event *e){assert(e->magic==0xfeed);return e->data;}
static int ring_buffer_unlock_commit(struct ring_buffer *b,struct ring_buffer_event *e){assert(b->open>0&&e->magic==0xfeed);b->open--;
  if(b->tail[cur_cpu])b->tail[cur_cpu]->next=e;else b->head[cur_cpu]=e;b->tail[cur_cpu]=e;return 0;}
static unsigned long ring_buffer_entries_cpu(struct ring_buffer *b,int c){unsigned long n=0;for(struct ring_buffer_event *e=b->head[c];e;e=e->next)n++;return n;}
static struct ring_buffer_event *ring_buffer_consume(struct ring_buffer *b,int c,u64 *ts,unsigned long *lost){(void)ts;(void)lost;
  free(b->last[c]);b->last[c]=NULL;struct ring_buffer_event *e=b->head[c];if(!e)return NULL;b->head[c]=e->next;if(!e->next)b->tail[c]=NULL;b->last[c]=e;return e;}
static unsigned long ring_buffer_size(struct ring_buffer *b,int c){(void)c;return b->size;}
static int ring_buffer_resize(struct ring_buffer *b,unsigned long size,int cpu){b->resized=size;b->resized_cpu=cpu;if(!resize_rc)b->size=size;return resize_rc;}
#define for_each_online_cpu(c) for((c)=0;(c)<NCPU;(c)++)
struct timespec64 {s64 tv_sec;long tv_nsec;};
static s64 rt_sec=1700000000;static long rt_nsec=123456789;
static void ktime_get_real_ts64(struct timespec64 *t){t->tv_sec=rt_sec;t->tv_nsec=rt_nsec;}
/* memory statistics */
'''
MODEL2=r'''
enum node_stat_item {NR_INACTIVE_ANON,NR_ACTIVE_ANON,NR_INACTIVE_FILE,NR_ACTIVE_FILE,NR_UNEVICTABLE,NR_SLAB_RECLAIMABLE,NR_SLAB_UNRECLAIMABLE,
  NR_ISOLATED_ANON,NR_ISOLATED_FILE,WORKINGSET_REFAULT,WORKINGSET_ACTIVATE,WORKINGSET_RESTORE,WORKINGSET_NODERECLAIM,NR_ANON_MAPPED,NR_FILE_MAPPED,
  NR_FILE_PAGES,NR_FILE_DIRTY,NR_WRITEBACK,NR_NODE_ITEMS};
enum zone_stat_item {NR_FREE_PAGES,NR_MLOCK=7,NR_PAGETABLE,NR_KERNEL_STACK_KB,NR_FREE_CMA_PAGES=12};
static unsigned long node_val(int i){return 1000+17*i;}
static unsigned long zone_val(int i){return 5000+31*i;}
static unsigned long global_node_page_state(enum node_stat_item i){return node_val(i);}
static unsigned long global_zone_page_state(enum zone_stat_item i){return zone_val(i);}
static void all_vm_events(unsigned long *ev){for(int i=0;i<NR_VM_EVENT_ITEMS;i++)ev[i]=100000+i*3;}
struct sysinfo {unsigned long totalram,freeram,sharedram,bufferram;};
static unsigned long si_total=2000000;
static void si_meminfo(struct sysinfo *s){s->totalram=si_total;s->freeram=11;s->sharedram=13;s->bufferram=17;}
static void si_swapinfo(struct sysinfo *s){(void)s;}
static unsigned long total_swapcache_pages(void){return 19;}
static unsigned long vmalloc_nr_pages(void){return 23;}
static unsigned long pcpu_nr_pages(void){return 29;}
unsigned long totalcma_pages=31;
unsigned long zram_meminfo(void){return 37;}
struct ion_meminfo_data {unsigned long system_alloc,total_alloc,cached;};
void ion_meminfo(struct ion_meminfo_data *d){d->system_alloc=41*1024+3;d->total_alloc=1;d->cached=43*1024+1023;}
static size_t dma_buf_total_size(void){return 47*1024+5;}
typedef struct {long counter;} atomic_long_t;
static long atomic_long_read(atomic_long_t *a){return a->counter;}
struct kgsl_driver {struct {atomic_long_t page_alloc;} stats;} kgsl_driver={{{53*4096+7}}};
static int kgsl_pool_size_total(void){return 59;}
struct hd_struct;
'''
STRONG=r'''
#include <stddef.h>
#include <stdlib.h>
#include <string.h>
int strong_sched_calls,strong_tap_calls,strong_tap_clears,strong_tear,strong_err,strong_psi,strong_disk,strong_uid,strong_uidinit;
int sched_rec_on,tap_rec_on;static char sched_rec[268],tap_rec[380];
void *sched_metrics_info_upload(void){strong_sched_calls++;memset(sched_rec,0x5c,sizeof(sched_rec));return sched_rec_on?sched_rec:NULL;}
void *kgsl_online_tap_data(void){strong_tap_calls++;memset(tap_rec,0x6b,sizeof(tap_rec));return tap_rec_on?tap_rec:NULL;}
void kgsl_online_tap_clear(void){strong_tap_clears++;}
int display_tear_trace_point_update(void){strong_tear++;return 0;}
int display_error_trace_point_update(void){strong_err++;return 0;}
void kmemind_psi(void){strong_psi++;}
int kio_diskstats(void){strong_disk++;return 0;}
int kio_uid_io(void){strong_uid++;return 0;}
void kio_uid_io_init(void){strong_uidinit++;}
'''
MAIN=r'''
extern int strong_sched_calls,strong_tap_calls,strong_tap_clears,strong_tear,strong_err,strong_psi,strong_disk,strong_uid,strong_uidinit,sched_rec_on,tap_rec_on;
/* drain and parse the staging buffer through the real show */
struct rec {u8 type,subtype;u32 len;u64 ts;unsigned char payload[2100];};
static struct rec recs[64];static int nrecs;
static char page[PAGE_SIZE];
static int read_trace(void){ssize_t n=trace_pointtrace_attr.show(NULL,&trace_pointtrace_attr,page);assert(n>=0&&n<PAGE_SIZE);int off=0;
  while(off<n){struct bsp_trace_header h;assert(off+24<=n);memcpy(&h,page+off,24);
    for(int i=0;i<10;i++)assert(h.reserved[i]==0);assert(off+24+(int)h.len<=n);
    recs[nrecs].type=h.type;recs[nrecs].subtype=h.subtype;recs[nrecs].len=h.len;recs[nrecs].ts=h.time_ns;memcpy(recs[nrecs].payload,page+off+24,h.len);nrecs++;off+=24+h.len;}
  return (int)n;}
static void reader(void){read_trace();}
static struct kobj_attribute *find_attr(const char *n){for(int i=0;trace_point_attrs[i];i++)if(!strcmp(trace_point_attrs[i]->name,n))return (struct kobj_attribute *)trace_point_attrs[i];return NULL;}
static ssize_t store(const char *attr,const char *v){struct kobj_attribute *a=find_attr(attr);assert(a&&a->store);return a->store(NULL,a,v,strlen(v));}
static const char *show(const char *attr){static char b[PAGE_SIZE];struct kobj_attribute *a=find_attr(attr);assert(a&&a->show);ssize_t n=a->show(NULL,a,b);assert(n>=0&&n<PAGE_SIZE);b[n]=0;return b;}
/* the rb_consumer thread: one pass (at most one event per cpu) per completion */
static void consume_all(void){while(data_ready.done>0){wait_for_completion(&data_ready);read_ringbuffer_to_tempbuf();}assert(!ring_buffer_entries_cpu(buffer,0)&&!ring_buffer_entries_cpu(buffer,1));}
int main(void){
 /* --- factory record layouts --- */
 assert(sizeof(struct bsp_trace_header)==24&&offsetof(struct bsp_trace_header,type)==8&&offsetof(struct bsp_trace_header,subtype)==9&&offsetof(struct bsp_trace_header,len)==20);
 assert(sizeof(struct kmemind)==864&&offsetof(struct kmemind,psi)==8&&offsetof(struct kmemind,lat)==88&&offsetof(struct kmemind,alloc_fail_cnt)==200);
 assert(offsetof(struct kmemind,alloc_fail_comm)==212&&offsetof(struct kmemind,vmstat)==232&&offsetof(struct kmemind,meminfo)==744);
 assert(sizeof(struct kioind)==2024&&offsetof(struct kioind,disk)==8&&sizeof(struct kio_disk)==176&&offsetof(struct kio_disk,bio)==88);
 assert(offsetof(struct kioind,uid)==1064&&sizeof(struct kio_uid)==96&&offsetof(struct kio_uid,delta_sum)==72&&sizeof(b_q2c)==1440);
 assert(sizeof(struct display_tear_trace)==152&&offsetof(struct display_tear_trace,count)==144&&sizeof(struct lcd_error_trace)==68&&offsetof(struct lcd_error_trace,count)==64);
 assert(trace_on==1&&display_interval==10&&kmemind_interval==2&&kioind_interval==12&&sched_interval==2&&kgsl_interval==2&&kmemind_on==1&&kioind_on==1);
 assert(!strcmp(kioind_dev[0].name,"sda")&&!strcmp(kioind_dev[1].name,"sde")&&!strcmp(kioind_dev[2].name,"sdf")&&!strcmp(kioind_dev[3].name,"sda7")&&!strcmp(kioind_dev[4].name,"sda16")&&!strcmp(kioind_dev[5].name,"zram0"));
 /* --- producers before init are ignored --- */
 assert(fs_trace_point_set("x",1,0)==0&&!buffer);
 /* --- init failure unwinds --- */
 int base=live_allocs;
 fail_kobj=1;assert(trace_point_init()==-ENOMEM&&!kobjs_live);fail_kobj=0;
 fail_group=1;assert(trace_point_init()<0&&!kobjs_live&&groups_live==0);fail_group=0;
 fail_alloc_at=1;alloc_seq=0;assert(trace_point_init()<0&&!kobjs_live&&!groups_live&&live_allocs==base);fail_alloc_at=0;
 rb_fail_alloc=1;assert(trace_point_init()<0&&!kobjs_live&&live_allocs==base&&!rb_live);rb_fail_alloc=0;
 kthread_fail_name=1;assert(trace_point_init()==-EAGAIN&&!kobjs_live&&live_allocs==base&&!rb_live&&!threads_live);
 kthread_fail_name=2;assert(trace_point_init()==-EAGAIN&&!kobjs_live&&live_allocs==base&&!rb_live&&!threads_live&&!consumer);kthread_fail_name=0;
 assert(!buffer&&!tp_buffer_sum&&!k_trace_point);
 /* --- successful init --- */
 int psi0=strong_psi,sched0=strong_sched_calls;
 assert(trace_point_init()==0&&buffer&&tp_buffer_sum&&consumer&&common_thread&&threads_live==2&&groups_live==1);
 assert(!strcmp(k_trace_point->name,"tracepoint")&&!strcmp(consumer->name,"rb_consumer")&&!strcmp(common_thread->name,"ts_timer_getdata_thread"));
 assert(next_jiffies==jiffies64+500&&strong_psi==psi0+1&&strong_sched_calls==sched0+1&&strong_disk&&strong_uid);
 {const char *names[]={"trace","usb","display","kmem","sched","kio","dp","wifi","gpu","traintime","fs","test","trace_on","kmemind_interval","kioind_interval","sched_interval","display_interval","kgsl_interval","rb_size","trigger"};
  for(int i=0;i<20;i++){assert(trace_point_attrs[i]&&!strcmp(trace_point_attrs[i]->name,names[i]));assert(trace_point_attrs[i]->mode==(i<12?0644:0664));}
  assert(!trace_point_attrs[20]);}
 assert(!trigger_attribute.show&&kmemind_init()==0&&kioind_init()==0&&strong_uidinit==1);
 assert(mem_attributes[0]&&!strcmp(mem_attributes[0]->name,"show")&&mem_attributes[0]->mode==0644&&!mem_attributes[1]);
 assert(!strcmp(io_attributes[0]->name,"show1_diskstats")&&!strcmp(io_attributes[1]->name,"show2_uid_io")&&!strcmp(io_attributes[2]->name,"show3_bio_time")&&!io_attributes[3]);
 /* --- every producer: type, subtype, len, header --- */
 int (*setters[12])(const void *,int,int)={trace_trace_point_set,usb_trace_point_set,display_trace_point_set,kmem_trace_point_set,sched_trace_point_set,kio_trace_point_set,dp_trace_point_set,wifi_trace_point_set,gpu_trace_point_set,traintime_trace_point_set,fs_trace_point_set,test_trace_point_set};
 notify_lock_check=&buffer_lock;no_lock_while_waiting=&buffer_lock;
 for(int i=0;i<12;i++){char p[8]={(char)i,1,2,3,4,5,6,7};cur_cpu=i&1;assert(setters[i](p,8,i+100)==0);}
 assert(buffer->open==0&&data_ready.done==12);
 consume_all();nrecs=0;read_trace();assert(nrecs==12);
 {int seen[12]={0};for(int i=0;i<12;i++){assert(recs[i].len==8&&recs[i].payload[0]==recs[i].type&&recs[i].subtype==(u8)(recs[i].type+100));assert(recs[i].ts==(u64)rt_sec*NSEC_PER_SEC+rt_nsec);seen[recs[i].type]++;}
  for(int i=0;i<12;i++)assert(seen[i]==1);}
 assert(tmp_data_done.done>=1);reinit_completion(&tmp_data_done);
 assert(get_display_interval()==10);
 /* trace off: nothing recorded; zero length payload with NULL data is fine */
 trace_on=0;assert(kmem_trace_point_set("x",1,0)==0&&!ring_buffer_entries_cpu(buffer,0)&&!ring_buffer_entries_cpu(buffer,1));trace_on=1;
 traintime_trace_point_set(NULL,0,0);consume_all();nrecs=0;read_trace();assert(nrecs==1&&recs[0].type==BSP_TRACE_TRAINTIME&&recs[0].len==0);
 rb_reserve_fail=1;errs=0;assert(usb_trace_point_set("a",1,0)==0&&errs==1&&buffer->open==0);rb_reserve_fail=0;
 /* --- writing a node injects a record of that type; limits --- */
 assert(store("fs","hello")==5);assert(store("wifi","w")==1);consume_all();nrecs=0;read_trace();
 assert(nrecs==2&&recs[0].type==BSP_TRACE_FS&&recs[0].len==5&&!memcmp(recs[0].payload,"hello",5)&&recs[0].subtype==0&&recs[1].type==BSP_TRACE_WIFI);
 {char big[600];memset(big,'a',sizeof(big));big[488]=0;assert(store("fs",big)==-EINVAL);big[487]=0;assert(store("test",big)==487);consume_all();nrecs=0;read_trace();assert(nrecs==1&&recs[0].len==487);}
 {struct kobj_attribute bogus=__ATTR(bogus,0644,trace_point_show,trace_point_store);assert(trace_point_store(NULL,&bogus,"x",1)==-EINVAL);consume_all();nrecs=0;assert(read_trace()==0);}
 /* --- staging: full buffer waits for the reader, timeout drops --- */
 {char p[1000];memset(p,7,sizeof(p));for(int i=0;i<4;i++)kio_trace_point_set(p,1000,i);
  reader_hook=reader;reader_reads_on_wait=1;nrecs=0;notifies=0;consume_all();
  /* 3 records fit (3072 < 4096 but > 3840 after the third -> notify), the reader drains, the fourth lands next */
  assert(notifies>=1&&nrecs==3);read_trace();assert(nrecs==4);
  for(int i=0;i<4;i++)assert(recs[i].subtype==i);
  /* reader gone: the record that does not fit is dropped after the timeout */
  reader_reads_on_wait=0;for(int i=0;i<5;i++)kio_trace_point_set(p,1000,i);infos=0;consume_all();
  nrecs=0;read_trace();assert(nrecs==3&&recs[2].subtype==2);consume_all();}
 /* --- age based notify (>15 s since the last notify) --- */
 notifies=0;tempbuf_last_data_time=(s64)rt_sec*NSEC_PER_SEC;rt_sec+=16;dp_trace_point_set("d",1,0);consume_all();assert(notifies==1);
 notifies=0;dp_trace_point_set("d",1,0);consume_all();assert(notifies==0);nrecs=0;read_trace();
 /* --- trace_on knob and thread lifetime --- */
 assert(!strcmp(show("trace_on"),"1\n"));
 assert(store("trace_on","2")==-EINVAL&&store("trace_on","-1")==-EINVAL&&store("trace_on","x")==-EINVAL);
 int st=stops;assert(store("trace_on","0")==1&&stops==st+1&&!common_thread&&threads_live==1&&trace_on==0);
 assert(store("trace_on","0")==1&&stops==st+1);
 assert(store("trace_on","1")==1&&common_thread&&threads_live==2&&!strcmp(common_thread->name,"ts_timer_getdata_thread"));
 kthread_fail_name=2;assert(store("trace_on","0")==1&&store("trace_on","1")==-EINVAL&&!common_thread);kthread_fail_name=0;
 assert(store("trace_on","0")==1&&store("trace_on","1")==1&&common_thread);
 /* --- interval knobs --- */
 const char *iv[]={"kmemind_interval","kioind_interval","sched_interval","display_interval","kgsl_interval"};
 for(int i=0;i<5;i++){assert(store(iv[i],"10000")>0);assert(store(iv[i],"10001")==-EINVAL&&store(iv[i],"-1")==-EINVAL&&store(iv[i],"z")==-EINVAL);
   char b[16];assert(!strcmp(show(iv[i]),"10000\n"));snprintf(b,16,"%d",3+i);assert(store(iv[i],b)>0);}
 assert(kmemind_interval==3&&kioind_interval==4&&sched_interval==5&&display_interval==6&&kgsl_interval==7);
 kmemind_interval=2;kioind_interval=12;sched_interval=2;display_interval=10;kgsl_interval=2;
 /* --- rb_size --- */
 assert(!strcmp(show("rb_size"),"8192\n"));
 assert(store("rb_size","4095")==-EINVAL&&store("rb_size","1048577")==-EINVAL&&store("rb_size","q")==-EINVAL);
 assert(store("rb_size","4096")==4&&buffer->resized==4096&&buffer->resized_cpu==RING_BUFFER_ALL_CPUS&&!strcmp(show("rb_size"),"4096\n"));
 assert(store("rb_size","1048576")>0&&buffer->resized==1048576);resize_rc=-ENOMEM;errs=0;assert(store("rb_size","8192")>0&&errs==1);resize_rc=0;
 /* --- sampler: kmem every 2, kio every 12, sched every 2, gpu every 2, display every 10 s --- */
 consume_all();nrecs=0;read_trace();
 sched_rec_on=1;tap_rec_on=1;int tear0=strong_tear,clr0=strong_tap_clears;
 kmem_cnt=kio_cnt=sched_cnt=kgsl_cnt=disp_cnt=0;
 for(int i=0;i<12;i++){tp_sample_once();consume_all();read_trace();}
 {int c[12]={0};for(int i=0;i<nrecs;i++)c[recs[i].type]++;
  assert(c[BSP_TRACE_KMEM]==6&&c[BSP_TRACE_KIO]==1&&c[BSP_TRACE_SCHED]==6&&c[BSP_TRACE_GPU]==6);
  for(int i=0;i<nrecs;i++){if(recs[i].type==BSP_TRACE_KMEM)assert(recs[i].len==864);if(recs[i].type==BSP_TRACE_KIO)assert(recs[i].len==2024);
   if(recs[i].type==BSP_TRACE_SCHED)assert(recs[i].len==268&&recs[i].payload[0]==0x5c);if(recs[i].type==BSP_TRACE_GPU)assert(recs[i].len==380&&recs[i].payload[0]==0x6b);}}
 assert(strong_tear==tear0+6&&strong_tap_clears==clr0+6);
 /* records are cleared after sending */
 {static const struct kmemind zero;assert(!memcmp(&kmemind,&zero,sizeof(zero)));}
 /* interval 0 disables */
 kmemind_interval=0;nrecs=0;for(int i=0;i<4;i++){tp_sample_once();consume_all();read_trace();}
 {for(int i=0;i<nrecs;i++)assert(recs[i].type!=BSP_TRACE_KMEM);}kmemind_interval=2;
 /* NULL producers send nothing and are not cleared */
 sched_rec_on=0;tap_rec_on=0;clr0=strong_tap_clears;nrecs=0;sched_cnt=kgsl_cnt=1;tp_sample_once();consume_all();read_trace();
 {for(int i=0;i<nrecs;i++)assert(recs[i].type!=BSP_TRACE_SCHED&&recs[i].type!=BSP_TRACE_GPU);}assert(strong_tap_clears==clr0);
 /* --- getdata thread timing --- */
 {int samples0=strong_tear;disp_cnt=0;display_interval=5; /* one display update per sample */
  next_jiffies=jiffies64+300;u64 j0=jiffies64;stop_checks=0;stop_after=4;common_getdata_thread(NULL);stop_after=-1;
  assert(strong_tear==samples0+1&&jiffies64==j0+300&&next_jiffies==j0+800);
  /* late: skip a round */
  next_jiffies=jiffies64-1;stop_checks=0;stop_after=1;common_getdata_thread(NULL);stop_after=-1;assert(strong_tear==samples0+1&&next_jiffies==jiffies64-1+1000);
  /* trigger: next moves to now+1000, the unsigned lateness check restarts the period */
  next_jiffies=jiffies64+200;int w=wakes;assert(store("trigger","1")==1&&wakes==w+1&&next_jiffies==jiffies64+1000);
  nrecs=0;consume_all();read_trace();assert(nrecs==1&&recs[0].type==BSP_TRACE_TRAINTIME);
  display_interval=10;}
 /* trigger without the thread: no wake-up, and with trace_on 0 the traintime record is dropped too */
 assert(store("trace_on","0")==1);int w2=wakes;assert(store("trigger","")==0&&wakes==w2);nrecs=0;consume_all();read_trace();assert(nrecs==0);
 assert(store("trace_on","1")==1);
 /* --- kmemind --- */
 /* latency buckets */
 for(int t=0;t<KMEMIND_LAT_NR;t++)for(int s=0;s<KMEMIND_LAT_SLOTS;s++)kmemind_lat_slots[t][s]=(t+1)*1000+s;
 memset(&kmemind,0,sizeof(kmemind));kmemind_fold_latency();
 {static const int bucket_of[40]={EXP_KMEM_BUCKETS};for(int t=0;t<KMEMIND_LAT_NR;t++){int sum[11]={0};for(int s=0;s<40;s++)sum[bucket_of[s]]+=(t+1)*1000+s;
   for(int b=0;b<11;b++)assert(kmemind.lat[t][b]==(u16)sum[b]);for(int s=0;s<40;s++)assert(kmemind_lat_slots[t][s]==0);}}
 /* folding accumulates */
 kmemind_lat_slots[KMEMIND_PG_LOCKED][27]=5;u16 before=kmemind.lat[KMEMIND_PG_LOCKED][10];kmemind_fold_latency();assert(kmemind.lat[KMEMIND_PG_LOCKED][10]==(u16)(before+5));
 /* header inline helpers */
 clock_ns=1000;u64 s0=kmemind_lat_start();assert(s0==1000);clock_ns=1000+70000000;kmemind_lat_end(KMEMIND_ASYNC_RECLAIM,s0);assert(kmemind_lat_slots[0][26]==1);
 clock_ns=2000;kmemind_lat_end(KMEMIND_ASYNC_RECLAIM,2000);clock_ns=2000+(1ULL<<45);kmemind_lat_end(KMEMIND_ASYNC_RECLAIM,2000);
 assert(kmemind_lat_slots[0][39]==0);kmemind_on=0;assert(kmemind_lat_start()==0);clock_ns+=100;kmemind_lat_end(KMEMIND_ASYNC_RECLAIM,0);kmemind_on=1;
 memset(kmemind_lat_slots,0,sizeof(kmemind_lat_slots));
 /* allocation failures */
 memset(&kmemind,0,sizeof(kmemind));kmemind_alloc_fail(0x6000c0,3);kmemind_alloc_fail(0x400,0);
 assert(kmemind.alloc_fail_cnt==2&&kmemind.alloc_fail_order_bitmap==0x9&&kmemind.alloc_fail_gfp==0x400&&!memcmp(kmemind.alloc_fail_comm,"stressapp-12345",16));
 kmemind_alloc_fail(0,40);assert(kmemind.alloc_fail_order_bitmap==0x9);kmemind_on=0;kmemind_alloc_fail(1,1);assert(kmemind.alloc_fail_cnt==3);kmemind_on=1;
 /* vmstat order follows the factory record */
 memset(&kmemind,0,sizeof(kmemind));fail_alloc_at=0;assert(get_all_kmemind()==&kmemind);
 {static const int ev[]={EXP_VMSTAT_EVENTS};assert(sizeof(ev)/sizeof(ev[0])==57);
  assert(kmemind.vmstat[0]==node_val(NR_ISOLATED_ANON)&&kmemind.vmstat[1]==node_val(NR_ISOLATED_FILE)&&kmemind.vmstat[2]==node_val(WORKINGSET_REFAULT));
  assert(kmemind.vmstat[3]==node_val(WORKINGSET_ACTIVATE)&&kmemind.vmstat[4]==node_val(WORKINGSET_RESTORE)&&kmemind.vmstat[5]==node_val(WORKINGSET_NODERECLAIM));
  for(int i=0;i<57;i++){unsigned long v=100000+ev[i]*3;if(i<2)v/=2;assert(kmemind.vmstat[6+i]==v);}
  assert(kmemind.vmstat[63]==0);}
 /* meminfo */
 {const u32 *m=kmemind.meminfo;
  assert(m[0]==si_total*4&&m[1]==44&&m[2]==68&&m[3]==76&&m[4]==4*node_val(NR_ACTIVE_ANON)&&m[5]==4*node_val(NR_INACTIVE_ANON));
  assert(m[6]==4*node_val(NR_ACTIVE_FILE)&&m[7]==4*node_val(NR_INACTIVE_FILE)&&m[8]==4*node_val(NR_UNEVICTABLE)&&m[9]==4*zone_val(NR_MLOCK));
  assert(m[10]==4*node_val(NR_FILE_DIRTY)&&m[11]==4*node_val(NR_WRITEBACK)&&m[12]==4*node_val(NR_ANON_MAPPED)&&m[13]==4*node_val(NR_FILE_MAPPED));
  assert(m[14]==52&&m[15]==4*node_val(NR_SLAB_RECLAIMABLE)&&m[16]==4*node_val(NR_SLAB_UNRECLAIMABLE)&&m[17]==zone_val(NR_KERNEL_STACK_KB));
  assert(m[18]==4*zone_val(NR_PAGETABLE)&&m[19]==92&&m[20]==116&&m[21]==124&&m[22]==4*zone_val(NR_FREE_CMA_PAGES)&&m[23]==148);
  assert(m[24]==40&&m[25]==40&&m[26]==44&&m[27]==212&&m[28]==236);
  u32 used=236+212+44+68+m[4]+m[6]+m[5]+m[7]+m[15]+m[16]+52+m[18]+44+40+148+92;assert(m[29]==m[0]-used);
  }
 {u32 keep=kmemind.meminfo[29];si_total=10;memset(&kmemind,0,sizeof(kmemind));kmemind.meminfo[29]=777;get_all_kmemind();assert(kmemind.meminfo[29]==777);si_total=2000000;(void)keep;}
 kmemind_on=0;assert(!get_all_kmemind());kmemind_on=1;
 /* vmstat buffer allocation failure leaves the events untouched */
 memset(&kmemind,0,sizeof(kmemind));fail_alloc_at=1;alloc_seq=0;get_all_kmemind();assert(kmemind.vmstat[6]==0&&kmemind.vmstat[0]!=0);fail_alloc_at=0;
 /* show */
 {char *b=malloc(PAGE_SIZE);memset(&kmemind,0,sizeof(kmemind));kmemind_lat_slots[KMEMIND_DIRECT_RECLAIM][20]=3;kmemind_alloc_fail(0x14,2);
  ssize_t n=kmemind_show(NULL,&kmemind_show_attr,b);assert(n>0&&n<PAGE_SIZE&&b[n]==0);
  assert(strstr(b,"sizeof(struct kmemind)=864(Bytes)")&&strstr(b,"sizeof(c_arr0)=80")&&strstr(b,"psi: cpu    some avg10="));
  assert(strstr(b,"direct_reclaim: 0           0           0           0           0           3           0"));
  assert(strstr(b,"page allocation failure: cnt=1, order_bitmap=0x4, gfp=0x14, comm=stressapp-12345"));
  assert(strstr(b,"graphic_swap_out=0\n\n")&&strstr(b,"/proc/meminfo(KB):   total=8000000 free=44")&&strstr(b,"LostMem="));
  char exp[64];snprintf(exp,64,"pgpgin=%lu pgpgout=%lu ",(100000UL+PGPGIN*3)/2,(100000UL+PGPGOUT*3)/2);assert(strstr(b,exp));
  snprintf(exp,64,"oom_kill=%lu ",100000UL+OOM_KILL*3);assert(strstr(b,exp));
  free(b);}
 /* --- kioind --- */
 for(int d=0;d<3;d++)for(int t=0;t<3;t++)for(int s=0;s<40;s++)b_q2c[d][t][s]=d*10000+t*1000+s;
 memset(&kioind,0,sizeof(kioind));int disk0=strong_disk,uid0=strong_uid;assert(get_all_kioind()==&kioind&&strong_disk==disk0+1&&strong_uid==uid0+1);
 {static const int bucket_of[40]={EXP_BIO_BUCKETS};for(int d=0;d<3;d++)for(int t=0;t<3;t++){u32 sum[7]={0};for(int s=0;s<40;s++)sum[bucket_of[s]]+=d*10000+t*1000+s;
   for(int b=0;b<7;b++)assert(kioind.disk[d].bio[t][b]==sum[b]);}
  for(int d=3;d<6;d++)for(int t=0;t<3;t++)for(int b=0;b<7;b++)assert(kioind.disk[d].bio[t][b]==0);
  for(int d=0;d<3;d++)for(int t=0;t<3;t++)for(int s=0;s<40;s++)assert(b_q2c[d][t][s]==0);}
 kioind_on=0;assert(!get_all_kioind());kioind_on=1;
 {char *b=malloc(PAGE_SIZE);
  kioind_dev[0].major=8;kioind_dev[0].minor=0;kioind_dev[0].devt=0x800000;kioind_dev[0].part=(struct hd_struct *)0xffffff8012345678UL;
  for(int i=0;i<11;i++)kioind.disk[0].stats[i]=i+1;
  ssize_t n=show1_diskstats(NULL,&show1_diskstats_attr,b);assert(n>0&&n<PAGE_SIZE);
  assert(strstr(b,"sizeof(struct kioind)=2024(Bytes)")&&strstr(b,"sizeof(b_q2c)=1440")&&strstr(b,"dev(major, minor): sda(8,0,800000)|sde(0,0,0)|"));
  assert(strstr(b,"zram0(0,0,0) \n\n/proc/diskstats: rd_ios")&&!strstr(b,"12345678"));
  assert(strstr(b,"            sda: 1            2            3            4            5            6            7            8            9            10           11           \n"));
  kioind.uid[0].uid=10123;kioind.uid[0].delta_sum=99;kioind.uid[0].delta[0]=1;kioind.uid[0].total[3]=77;
  n=show2_uid_io(NULL,&show2_uid_io_attr,b);assert(n>0&&n<PAGE_SIZE);
  assert(strstr(b,"\n/proc/uid_io/stats: uid     delta")&&strstr(b,"             Top 1: 10123   99              1               ")&&strstr(b,"             Top10: "));
  memset(kioind.disk,0,sizeof(kioind.disk));kioind.disk[1].bio[0][0]=5;kioind.disk[1].bio[2][6]=9;n=show3_bio_time(NULL,&show3_bio_time_attr,b);assert(n>0&&n<PAGE_SIZE);
  assert(strstr(b,"\nbio Q2C: [0,1)ms")&&strstr(b,"    sde: 5       |0       |0        ")&&strstr(b,"|9       \n"));
  free(b);}
 /* --- teardown releases everything --- */
 assert(store("trace_on","0")==1);complete(&data_ready);kthread_stop(consumer);ring_buffer_free(buffer);buffer=NULL;kfree(tp_buffer_sum);sysfs_remove_group(k_trace_point,&trace_point_group);kobject_put(k_trace_point);
 assert(threads_live==0&&rb_live==0);
 /* kmemind/kioind kobjects live forever in the kernel (initcalls): release them for LeakSanitizer */
 assert(ninit_kobjs==2&&!strcmp(init_kobjs[0]->name,"kmemind")&&!strcmp(init_kobjs[1]->name,"kioind"));for(int i=0;i<ninit_kobjs;i++)kobject_put(init_kobjs[i]);assert(kobjs_live==0&&live_allocs==base);
 puts("PASS: factory record layouts and defaults; producers before init; init failure unwinds; 12 producers with type/subtype/len/"
      "realtime header and zeroed reserved bytes; trace_on off; node writes inject typed records, 488 byte limit, unknown node "
      "-EINVAL; staging full/notify/timeout drop; 15 s age notify; trace_on thread lifecycle; interval/rb_size knobs and bounds; "
      "sampler cadence per interval incl. disable and NULL producers; thread timing, late round, trigger; kmemind buckets, "
      "helpers, allocation failures, factory vmstat order, meminfo/LostMem, show; kioind bio buckets (slot 26 fix), shows");
 return 0;
}
'''
def expected():
    # kmemind buckets from the factory header edges (ns)
    edges=[64,512,1000,524000,1000000,8000000,16000000,33000000,67000000,134000000]
    kb=[sum(1 for e in edges if (1<<s)>=e) for s in range(40)]
    bio_edges=[1e6,16e6,67e6,134e6,268e6,536e6]
    bb=[sum(1 for e in bio_edges if (1<<s)>=e) for s in range(40)]
    order=['PGPGIN','PGPGOUT','PGPGOUTCLEAN','PSWPIN','PSWPOUT','PGALLOC_NORMAL','PGALLOC_MOVABLE','ALLOCSTALL_NORMAL','ALLOCSTALL_MOVABLE',
           'PGSCAN_SKIP_NORMAL','PGSCAN_SKIP_MOVABLE','PGFREE','PGACTIVATE','PGDEACTIVATE','PGLAZYFREE','PGFAULT','PGMAJFAULT','PGLAZYFREED',
           'PGREFILL','PGSCAN_KSWAPD','PGSTEAL_KSWAPD','PGSCAN_DIRECT','PGSTEAL_DIRECT','PGSCAN_DIRECT_THROTTLE','SLABS_SCANNED','PGINODESTEAL',
           'KSWAPD_INODESTEAL','KSWAPD_LOW_WMARK_HIT_QUICKLY','KSWAPD_HIGH_WMARK_HIT_QUICKLY','PAGEOUTRUN','PGROTATED','DROP_PAGECACHE',
           'DROP_SLAB','OOM_KILL','PGMIGRATE_SUCCESS','PGMIGRATE_FAIL','COMPACTMIGRATE_SCANNED','COMPACTFREE_SCANNED','COMPACTISOLATED',
           'COMPACTSTALL','COMPACTFAIL','COMPACTSUCCESS','KCOMPACTD_WAKE','KCOMPACTD_MIGRATE_SCANNED','KCOMPACTD_FREE_SCANNED',
           'UNEVICTABLE_PGCULLED','UNEVICTABLE_PGSCANNED','UNEVICTABLE_PGRESCUED','UNEVICTABLE_PGMLOCKED','UNEVICTABLE_PGMUNLOCKED',
           'UNEVICTABLE_PGCLEARED','UNEVICTABLE_PGSTRANDED','SWAP_RA','SWAP_RA_HIT','SPECULATIVE_PGFAULT_ANON','SPECULATIVE_PGFAULT_FILE',
           'STORAGE_SWAP_OUT']
    return {'EXP_KMEM_BUCKETS':','.join(map(str,kb)),'EXP_BIO_BUCKETS':','.join(map(str,bb)),'EXP_VMSTAT_EVENTS':','.join(order)}
def strip_includes(t):
    return '\n'.join(l for l in t.splitlines() if not l.startswith('#include'))
def main():
    srcs={n:(SOURCE/n).read_text() for n in (DRV,HDR,VMEV)}
    exp=expected()
    head=''.join(f'#define {k} {v}\n' for k,v in exp.items())
    code=(MODEL+srcs[VMEV]+MODEL2+strip_includes(srcs[HDR])+'\n'+strip_includes(srcs[DRV])+'\n'+head+MAIN)
    out=BASE/'out/phoenix-kernel-recovery/bsp-trace-tests';out.mkdir(exist_ok=True);(out/'harness.c').write_text(code);(out/'strong.c').write_text(STRONG)
    subprocess.run(['gcc','-std=gnu11','-g','-O1','-Wall','-Wno-unused-function','-Wno-unused-variable','-Wno-unused-but-set-variable','-Wno-format-truncation',
                    '-fsanitize=address,undefined','-fno-sanitize-recover=all',str(out/'harness.c'),str(out/'strong.c'),'-o',str(out/'test')],check=True)
    r=subprocess.run([str(out/'test')],capture_output=True,text=True,timeout=120)
    report={'sources':{n:hashlib.sha256((SOURCE/n).read_bytes()).hexdigest() for n in sorted(srcs)},'harness_sha256':hashlib.sha256(code.encode()).hexdigest(),
            'expected':exp,'exit_code':r.returncode,'stdout':r.stdout,'stderr':r.stderr[-3000:],
            'scope':'The whole drivers/misc/pico_bsp_trace.c and include/linux/pico_bsp_trace.h (includes stripped) with the real '
                    'vm_event_item enum, against a modeled kernel: ring buffer (reserve/commit discipline, garbage-filled reservations), '
                    'completions with a simulated userspace reader, kthreads, jiffies, sysfs, allocations with failure injection; '
                    'strong producer overrides linked from a second object exercise the weak hooks. Bucket edges and the vmstat record '
                    'order come from the factory format strings, not from the code under test.','device_modified':False}
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));raise SystemExit(r.returncode)
if __name__=='__main__':main()
