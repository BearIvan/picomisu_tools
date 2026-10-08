"""Execute the actual qcom-cpufreq-hw DCVSH statistics / get_real bodies and the cpufreq core cpuinfo_cur_freq_real glue under ASan/UBSan."""
from pathlib import Path
import hashlib,importlib.util,json,re,subprocess
BASE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro');SOURCE=BASE/'source/phoenix-kernel-recovery'
HW='drivers/cpufreq/qcom-cpufreq-hw.c';CORE='drivers/cpufreq/cpufreq.c';HDR='include/linux/cpufreq.h'
OBJ=BASE/'out/phoenix-kernel-recovery/obj'
STRUCTS=[(HDR,'struct cpufreq_driver {'),(HW,'struct skipped_freq {'),(HW,'struct cpufreq_qcom {')]
FUNCS=[(HW,'static ssize_t dcvsh_freq_limit_show('),(HW,'static ssize_t dcvsh_freq_limit_time_show('),(HW,'static ssize_t total_time_show('),
       (HW,'static unsigned long limits_mitigation_notify('),(HW,'static void limits_dcvsh_poll('),
       (HW,'static unsigned int qcom_cpufreq_hw_get(unsigned int cpu)\n{'),(HW,'static unsigned int qcom_cpufreq_hw_get_real('),
       (HW,'static int qcom_cpufreq_hw_cpu_init('),(HW,'static int qcom_cpu_resources_init('),
       (CORE,'static inline bool policy_is_inactive('),(CORE,'static ssize_t show_cpuinfo_cur_freq_real('),
       (CORE,'static int cpufreq_add_dev_interface(')]
DRIVER=(HW,'static struct cpufreq_driver cpufreq_qcom_hw_driver = {')
MODEL=r'''
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/types.h>
typedef uint8_t u8;typedef uint16_t u16;typedef uint32_t u32;typedef uint64_t u64;typedef int64_t s64;typedef s64 ktime_t;
#define __iomem
#define PAGE_SIZE 4096
#define U32_MAX 0xffffffffU
#define BIT(n) (1UL<<(n))
#define GENMASK(h,l) (((~0UL)<<(l))&(~0UL>>(63-(h))))
#define DIV_ROUND_CLOSEST_ULL(x,d) (((unsigned long long)(x)+(d)/2)/(d))
#define container_of(p,t,m) ((t *)((char *)(p)-offsetof(t,m)))
#define min(a,b) ((a)<(b)?(a):(b))
#define READ_ONCE(x) (x)
#define ENODEV 19
#define ENOMEM 12
#define EINVAL 22
#define ENOENT 2
#define CPUFREQ_NAME_LEN 16
#define CPUFREQ_STICKY 1
#define CPUFREQ_NEED_INITIAL_FREQ_CHECK 2
#define CPUFREQ_HAVE_GOVERNOR_PER_POLICY 4
#define IRQF_TRIGGER_HIGH 4
#define IRQF_ONESHOT 0x2000
#define IRQF_NO_SUSPEND 0x4000
#define NR_CPUS 8
#define MAX_FN_SIZE 20
#define LIMITS_POLLING_DELAY_MS 10
#define GT_IRQ_STATUS BIT(2)
#define IS_ERR(p) ((unsigned long)(p)>=(unsigned long)-4095)
#define PTR_ERR(p) ((long)(p))
static int logs;
#define pr_err(...) (logs++)
#define dev_err(...) (logs++)
#define pr_debug(...) ((void)0)
/* arm64 sizes so that offsetof() reproduces the factory layout */
typedef struct {unsigned long bits[1];} cpumask_t;
typedef struct {u32 raw;} spinlock_t;
struct mutex {long owner;int held;int pad;long wait_list[2];};               /* 32 bytes */
struct work_struct {long data;void *entry[2];void (*func)(struct work_struct *);}; /* 32 */
struct timer_list {void *entry[2];unsigned long expires;void *function;u32 flags;}; /* 40 */
struct delayed_work {struct work_struct work;struct timer_list timer;void *wq;int cpu;}; /* 88 */
struct attribute {const char *name;u16 mode;};
struct device;struct device_attribute {struct attribute attr;ssize_t (*show)(struct device *,struct device_attribute *,char *);
  ssize_t (*store)(struct device *,struct device_attribute *,const char *,size_t);}; /* 32 */
_Static_assert(sizeof(struct mutex)==32&&sizeof(struct delayed_work)==88&&sizeof(struct device_attribute)==32,"model sizes");
struct cpufreq_frequency_table {unsigned int flags;unsigned int driver_data;unsigned int frequency;};
struct cpufreq_cpuinfo {unsigned int max_freq,min_freq,transition_latency;};
struct kobject {int x;};
struct cpufreq_policy {cpumask_t cpus[1];cpumask_t related_cpus[1];unsigned int cpu;struct cpufreq_cpuinfo cpuinfo;
  struct cpufreq_frequency_table *freq_table;void *driver_data;bool fast_switch_possible;bool dvfs_possible_from_any_cpu;struct kobject kobj;};
struct freq_attr {struct attribute attr;ssize_t (*show)(struct cpufreq_policy *,char *);ssize_t (*store)(struct cpufreq_policy *,const char *,size_t);};
static int cpumask_empty(const cpumask_t *m){return !(m->bits[0]&0xff);}
static unsigned cpumask_first(const cpumask_t *m){for(unsigned i=0;i<NR_CPUS;i++)if(m->bits[0]&(1UL<<i))return i;return NR_CPUS;}
static void cpumask_copy(cpumask_t *d,const cpumask_t *s){*d=*s;}
#define for_each_cpu(c,m) for((c)=0;(c)<NR_CPUS;(c)++) if((m)->bits[0]&(1UL<<(c)))
static u32 readl_relaxed(const volatile void *a){return *(const volatile u32 *)a;}
static void writel_relaxed(u32 v,volatile void *a){*(volatile u32 *)a=v;}
static void mutex_lock(struct mutex *m){assert(!m->held);m->held=1;}
static void mutex_unlock(struct mutex *m){assert(m->held);m->held=0;}
static void mutex_init(struct mutex *m){memset(m,0,sizeof(*m));}
#define INIT_DEFERRABLE_WORK(dw,f) do{memset(dw,0,sizeof(*(dw)));(dw)->work.func=(void (*)(struct work_struct *))(f);}while(0)
static void *system_highpri_wq=(void *)1;static int rearmed;static unsigned long rearm_delay;
static bool mod_delayed_work(void *wq,struct delayed_work *dw,unsigned long d){assert(wq==system_highpri_wq);(void)dw;rearmed++;rearm_delay=d;return true;}
static unsigned long msecs_to_jiffies(unsigned ms){return ms/10;} /* HZ=100 */
static int irq_enabled_calls;static void enable_irq(int irq){(void)irq;irq_enabled_calls++;}
static unsigned long sched_max;static void sched_update_cpu_freq_min_max(const cpumask_t *m,u32 lo,u32 hi){(void)m;(void)lo;sched_max=hi;}
static void trace_dcvsh_freq(unsigned cpu,unsigned long f){(void)cpu;(void)f;}
static s64 boot_ns;static ktime_t ktime_get_boottime(void){return boot_ns;}
static s64 ktime_to_ms(ktime_t k){return k/1000000;}
static struct cpufreq_policy *policies[NR_CPUS];
static struct cpufreq_policy *cpufreq_cpu_get_raw(unsigned cpu){return cpu<NR_CPUS?policies[cpu]:NULL;}
enum {REG_ENABLE,REG_FREQ_LUT_TABLE,REG_VOLT_LUT_TABLE,REG_PERF_STATE,REG_CYCLE_CNTR,REG_DOMAIN_STATE,REG_INTR_EN,REG_INTR_CLR,REG_INTR_STATUS,REG_ARRAY_SIZE};
'''
MODEL2=r'''
static struct cpufreq_qcom *qcom_freq_domain_map[NR_CPUS];
static bool accumulative_counter;
static unsigned int qcom_cpufreq_hw_get(unsigned int cpu);
/* cpu_init / resources_init environment */
struct device_node {int x;};struct device {const char *name;struct device_node *of_node;};
struct platform_device {struct device dev;};
static struct device cpu_devs[NR_CPUS];static int no_cpu_dev;
static struct device *get_cpu_device(unsigned cpu){return no_cpu_dev?NULL:&cpu_devs[cpu];}
static int dev_pm_opp_get_opp_count(struct device *d){(void)d;return 5;}
struct em_data_callback {int (*active_power)(void);};
#define EM_DATA_CB(cb) {.active_power=(cb)}
static int of_dev_pm_opp_get_cpu_power(void){return 0;}
static int em_register_perf_domain(cpumask_t *s,int n,struct em_data_callback *cb){(void)s;(void)n;(void)cb;return 0;}
typedef int irqreturn_t;
static irqreturn_t dcvsh_handle_isr(int irq,void *data){(void)irq;(void)data;return 0;}
static int irq_rc,irq_reqs;
static int devm_request_threaded_irq(struct device *d,int irq,void *h,irqreturn_t (*t)(int,void *),unsigned long f,const char *n,void *data){
  (void)d;(void)irq;(void)h;assert(t==dcvsh_handle_isr&&f==(IRQF_TRIGGER_HIGH|IRQF_ONESHOT|IRQF_NO_SUSPEND));(void)n;(void)data;irq_reqs++;return irq_rc;}
static struct device_attribute *files[16];static int nfiles;
static int device_create_file(struct device *d,struct device_attribute *a){(void)d;assert(nfiles<16);files[nfiles++]=a;return 0;}
static int snprintf_(char *b,size_t n,const char *f,int v){return snprintf(b,n,f,v);}
/* resources init */
static void *devm_kzalloc(struct device *d,size_t n,int g){(void)d;(void)g;return calloc(1,n);}
#define GFP_KERNEL 0
static const u16 *match_offsets;
static const void *of_device_get_match_data(struct device *d){(void)d;return match_offsets;}
#define IORESOURCE_MEM 0x200
struct resource {int idx;};static struct resource res0;
static struct resource *platform_get_resource(struct platform_device *p,int t,int i){(void)p;(void)t;(void)i;return &res0;}
static u32 regspace[0x1000];
static void __iomem *devm_ioremap_resource(struct device *d,struct resource *r){(void)d;(void)r;return regspace;}
static bool of_property_read_bool(struct device_node *n,const char *p){(void)n;(void)p;return true;}
static int qcom_get_related_cpus(int index,cpumask_t *m){m->bits[0]=index?0xf0:0x0f;return 0;}
static int qcom_cpufreq_hw_read_lut(struct platform_device *p,struct cpufreq_qcom *c){(void)p;c->lut_max_entries=3;return 0;}
static int has_irq_prop=1,of_irq;
static void *of_find_property(struct device_node *n,const char *p,int *l){(void)n;(void)l;return (has_irq_prop&&!strcmp(p,"interrupts"))?(void *)1:NULL;}
static int of_irq_get(struct device_node *n,int i){(void)n;(void)i;return of_irq;}
'''
MAIN=r'''
static ssize_t show_cpuinfo_cur_freq_real(struct cpufreq_policy *policy,char *buf);
static struct freq_attr cpuinfo_cur_freq={{"cpuinfo_cur_freq",0400}},scaling_cur_freq={{"scaling_cur_freq",0444}},bios_limit={{"bios_limit",0444}};
static struct freq_attr cpuinfo_cur_freq_real={{"cpuinfo_cur_freq_real",0444},show_cpuinfo_cur_freq_real,NULL};
static const struct cpufreq_driver *cpufreq_driver;
static struct attribute *created[16];static int ncreated;
static int sysfs_create_file(struct kobject *k,const struct attribute *a){(void)k;created[ncreated++]=(struct attribute *)a;return 0;}
'''
MAIN2=r'''
static unsigned get_stub(unsigned cpu){(void)cpu;return 1;}
int main(void){
 /* --- factory layouts (arm64) --- */
 assert(offsetof(struct cpufreq_driver,get)==104&&offsetof(struct cpufreq_driver,get_real)==112&&offsetof(struct cpufreq_driver,bios_limit)==120);
 assert(offsetof(struct cpufreq_driver,exit)==128&&offsetof(struct cpufreq_driver,ready)==160&&offsetof(struct cpufreq_driver,attr)==168&&sizeof(struct cpufreq_driver)==192);
 assert(offsetof(struct cpufreq_qcom,lut_max_entries)==92&&offsetof(struct cpufreq_qcom,dcvsh_freq_limit_time)==96&&offsetof(struct cpufreq_qcom,xo_rate)==104);
 assert(offsetof(struct cpufreq_qcom,dcvsh_freq_limit)==120&&offsetof(struct cpufreq_qcom,init_time_ms)==128&&offsetof(struct cpufreq_qcom,freq_poll_work)==136);
 assert(offsetof(struct cpufreq_qcom,dcvsh_lock)==224&&offsetof(struct cpufreq_qcom,freq_limit_attr)==256&&offsetof(struct cpufreq_qcom,freq_limit_time_attr)==288);
 assert(offsetof(struct cpufreq_qcom,total_time_attr)==320&&offsetof(struct cpufreq_qcom,skip_data)==352&&offsetof(struct cpufreq_qcom,dcvsh_irq)==392);
 assert(offsetof(struct cpufreq_qcom,is_irq_enabled)==416&&sizeof(struct cpufreq_qcom)==424);
 assert(cpufreq_qcom_hw_driver.get_real==qcom_cpufreq_hw_get_real&&cpufreq_qcom_hw_driver.get==qcom_cpufreq_hw_get);
 /* --- resources init: domain 0 with irq, boot time reference --- */
 static const u16 offs[REG_ARRAY_SIZE]={0,0x100,0x200,0x320,0x3c4,0x020,0x304,0x308,0x30C};match_offsets=offs;regspace[0]=1;
 struct platform_device pdev={{"cpufreq"}};boot_ns=EXP_BOOT_NS;of_irq=30;
 assert(!qcom_cpu_resources_init(&pdev,0,0,4,EXP_XO,300000));struct cpufreq_qcom *c=qcom_freq_domain_map[0];
 assert(c&&qcom_freq_domain_map[3]==c&&!qcom_freq_domain_map[4]&&c->init_time_ms==EXP_INIT_MS&&c->dcvsh_irq==30&&c->xo_rate==EXP_XO);
 assert(c->freq_poll_work.work.func==(void (*)(struct work_struct *))limits_dcvsh_poll);
 /* domain without irq still gets the time reference */
 has_irq_prop=0;boot_ns=EXP_BOOT_NS2;assert(!qcom_cpu_resources_init(&pdev,4,1,4,EXP_XO,300000));has_irq_prop=1;
 struct cpufreq_qcom *c1=qcom_freq_domain_map[4];assert(c1!=c&&c1->init_time_ms==EXP_INIT_MS2&&c1->dcvsh_irq==0);
 /* --- cpu_init: three nodes, factory names/modes --- */
 struct cpufreq_frequency_table tbl[4]={{0,0,300000},{0,0,1000000},{0,0,2400000},{0,0,~0u}};c->table=tbl;
 struct cpufreq_policy pol;memset(&pol,0,sizeof(pol));pol.cpu=0;pol.cpuinfo.max_freq=2400000;policies[0]=policies[1]=&pol;
 c->dcvsh_freq_limit_time=1234;
 assert(!qcom_cpufreq_hw_cpu_init(&pol)&&pol.driver_data==c&&pol.cpus[0].bits[0]==0x0f&&irq_reqs==1&&nfiles==3);
 assert(!strcmp(files[0]->attr.name,"dcvsh_freq_limit")&&!strcmp(files[1]->attr.name,"dcvsh_freq_limit_time")&&!strcmp(files[2]->attr.name,"total_time"));
 for(int i=0;i<3;i++)assert(files[i]->attr.mode==0444&&files[i]->show&&!files[i]->store);
 assert(c->dcvsh_freq_limit==U32_MAX&&c->dcvsh_freq_limit_time==0&&c->is_irq_enabled&&c->is_irq_requested);
 /* second policy init of the same domain does not re-create the nodes */
 assert(!qcom_cpufreq_hw_cpu_init(&pol)&&irq_reqs==1&&nfiles==3);
 /* irq failure: no nodes */
 {struct cpufreq_qcom *c2=calloc(1,sizeof(*c2));c2->dcvsh_irq=31;c2->table=tbl;qcom_freq_domain_map[5]=c2;struct cpufreq_policy p2;memset(&p2,0,sizeof(p2));p2.cpu=5;
  irq_rc=-EINVAL;nfiles=0;assert(qcom_cpufreq_hw_cpu_init(&p2)==-EINVAL&&nfiles==0&&!c2->is_irq_requested);irq_rc=0;
  no_cpu_dev=1;assert(qcom_cpufreq_hw_cpu_init(&p2)==-ENODEV);no_cpu_dev=0;qcom_freq_domain_map[5]=NULL;free(c2);}
 nfiles=3;
 char buf[PAGE_SIZE];
 /* --- show formats --- */
 assert(files[0]->show(NULL,files[0],buf)>0&&!strcmp(buf,"4294967295\n"));
 assert(files[1]->show(NULL,files[1],buf)==2&&!strcmp(buf,"0\n"));
 boot_ns=EXP_BOOT_NS+EXP_ELAPSED_NS;assert(files[2]->show(NULL,files[2],buf)>0&&!strcmp(buf,EXP_TOTAL_STR));
 /* --- get_real: hw LUT frequency capped by the dcvsh limit --- */
 regspace[0x320/4]=2;assert(qcom_cpufreq_hw_get(0)==2400000&&qcom_cpufreq_hw_get_real(0)==2400000);
 regspace[0x320/4]=9;assert(qcom_cpufreq_hw_get_real(0)==2400000); /* index clamped to lut_max_entries-1 */
 c->dcvsh_freq_limit=1497600;assert(qcom_cpufreq_hw_get_real(0)==1497600);regspace[0x320/4]=1;assert(qcom_cpufreq_hw_get_real(0)==1000000);
 c->dcvsh_freq_limit=0x1000003e8UL;regspace[0x320/4]=2;assert(qcom_cpufreq_hw_get_real(0)==1000); /* factory: u32 compare */
 assert(qcom_cpufreq_hw_get_real(6)==0);
 /* --- poll: count only while the limit is below the hw frequency --- */
 regspace[0x020/4]=EXP_LUT_CODE;regspace[0x320/4]=2;c->dcvsh_freq_limit_time=0;rearmed=0;irq_enabled_calls=0;
 limits_dcvsh_poll(&c->freq_poll_work.work);assert(rearmed==1&&rearm_delay==1&&c->dcvsh_freq_limit_time==1&&c->dcvsh_freq_limit==EXP_LIMIT&&!c->dcvsh_lock.held);
 limits_dcvsh_poll(&c->freq_poll_work.work);assert(rearmed==2&&c->dcvsh_freq_limit_time==2);
 assert(files[1]->show(NULL,files[1],buf)==2&&!strcmp(buf,"2\n"));
 /* hw frequency already below the limit (limit above current): rearm without counting */
 regspace[0x320/4]=0;limits_dcvsh_poll(&c->freq_poll_work.work);assert(rearmed==3&&c->dcvsh_freq_limit_time==2&&irq_enabled_calls==0);
 /* limit reached the hw frequency: unthrottle, re-enable irq, no count */
 regspace[0x020/4]=EXP_LUT_CODE_EQ;regspace[0x320/4]=1;regspace[0x308/4]=0;c->is_irq_enabled=false;
 limits_dcvsh_poll(&c->freq_poll_work.work);assert(rearmed==3&&c->dcvsh_freq_limit_time==2&&irq_enabled_calls==1&&c->is_irq_enabled&&(regspace[0x308/4]&GT_IRQ_STATUS));
 assert(c->dcvsh_freq_limit==2400000&&sched_max==2400000);
 /* --- cpufreq core: cpuinfo_cur_freq_real --- */
 struct cpufreq_driver drv;memset(&drv,0,sizeof(drv));drv.get=get_stub;drv.get_real=qcom_cpufreq_hw_get_real;cpufreq_driver=&drv;
 c->dcvsh_freq_limit=1000000;regspace[0x320/4]=2;
 assert(show_cpuinfo_cur_freq_real(&pol,buf)==8&&!strcmp(buf,"1000000\n"));
 c->dcvsh_freq_limit=0;assert(!strcmp((show_cpuinfo_cur_freq_real(&pol,buf),buf),"<unknown>\n"));c->dcvsh_freq_limit=1000000;
 cpumask_t saved=pol.cpus[0];pol.cpus[0].bits[0]=0;assert(show_cpuinfo_cur_freq_real(&pol,buf)==10&&!strcmp(buf,"<unknown>\n"));pol.cpus[0]=saved;
 drv.get_real=NULL;assert(!strcmp((show_cpuinfo_cur_freq_real(&pol,buf),buf),"<unknown>\n"));
 /* node created only for drivers with get_real, after cpuinfo_cur_freq and before scaling_cur_freq */
 ncreated=0;drv.get_real=qcom_cpufreq_hw_get_real;assert(!cpufreq_add_dev_interface(&pol));
 assert(ncreated==3&&created[0]==&cpuinfo_cur_freq.attr&&created[1]==&cpuinfo_cur_freq_real.attr&&created[2]==&scaling_cur_freq.attr);
 assert(cpuinfo_cur_freq_real.attr.mode==0444&&cpuinfo_cur_freq_real.show==show_cpuinfo_cur_freq_real&&!cpuinfo_cur_freq_real.store);
 ncreated=0;drv.get_real=NULL;assert(!cpufreq_add_dev_interface(&pol)&&ncreated==2&&created[1]==&scaling_cur_freq.attr);
 free(c);free(c1);
 puts("PASS: factory layouts (cpufreq_driver.get_real @112, cpufreq_qcom 424 bytes with time fields @96/@128 and attrs @288/@320); "
      "boot-time reference per domain; three 0444 nodes once per domain, none on irq failure; show formats; get_real = min(LUT freq, "
      "u32 limit); poll counts only while the limit caps the hw frequency, unthrottle path unchanged, dcvsh_lock balanced; "
      "cpuinfo_cur_freq_real output, inactive policy, creation order and gating on get_real");
 return 0;
}
'''
def expected():
    # independent model of the factory arithmetic: limit = round(code * xo / 1000) kHz, total_time = boot_ms(now) - boot_ms(init)
    boot=123456789012;boot2=223456789999;el=7777000001
    xo=19200000;code=78
    return {'EXP_BOOT_NS':boot,'EXP_INIT_MS':boot//1000000,'EXP_BOOT_NS2':boot2,'EXP_INIT_MS2':boot2//1000000,'EXP_ELAPSED_NS':el,
            'EXP_TOTAL_STR':'"%d\\n"'%(((boot+el)//1000000)-(boot//1000000)),'EXP_XO':xo,'EXP_LUT_CODE':code,'EXP_LIMIT':(code*xo+500)//1000,
            # unthrottle case: 20 MHz xo, code 50 -> exactly the 1000000 kHz LUT entry
            'EXP_XO_EQ':20000000,'EXP_LUT_CODE_EQ':50}
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
    srcs={n:(SOURCE/n).read_text() for n in (HW,CORE,HDR)}
    defs=expected()
    head=''.join(f'#define {k} {v}\n' for k,v in defs.items())
    main2=MAIN2.replace('regspace[0x020/4]=EXP_LUT_CODE_EQ;','c->xo_rate=EXP_XO_EQ;regspace[0x020/4]=EXP_LUT_CODE_EQ;')
    code=(MODEL+'\n'.join(ex.function(srcs[f],s)+';' for f,s in STRUCTS)+MODEL2+MAIN
          +'\n'.join(ex.function(srcs[f],s) for f,s in FUNCS)+'\n'+ex.function(srcs[DRIVER[0]],DRIVER[1])+';\n'+head+main2)
    code=code.replace('static struct cpufreq_driver cpufreq_qcom_hw_driver = {','static unsigned int qcom_cpufreq_hw_target_index_(void){return 0;}\n'
                      'static struct cpufreq_driver cpufreq_qcom_hw_driver = {',1)
    stubs=('static int cpufreq_generic_frequency_table_verify(struct cpufreq_policy *p){(void)p;return 0;}\n'
           'static int qcom_cpufreq_hw_target_index(struct cpufreq_policy *p,unsigned int i){(void)p;(void)i;return 0;}\n'
           'static unsigned int qcom_cpufreq_hw_fast_switch(struct cpufreq_policy *p,unsigned int f){(void)p;return f;}\n'
           'static struct freq_attr *qcom_cpufreq_hw_attr[]={NULL};\nstatic void qcom_cpufreq_ready(struct cpufreq_policy *p){(void)p;}\n')
    code=code.replace('static unsigned int qcom_cpufreq_hw_target_index_(void){return 0;}\n',stubs,1)
    out=BASE/'out/phoenix-kernel-recovery/cpufreq-hw-dcvsh-stats-tests';out.mkdir(exist_ok=True);(out/'harness.c').write_text(code)
    subprocess.run(['gcc','-std=gnu11','-g','-O1','-Wall','-Wno-unused-function','-Wno-unused-variable','-fsanitize=address,undefined','-fno-sanitize-recover=all',str(out/'harness.c'),'-o',str(out/'test')],check=True)
    r=subprocess.run([str(out/'test')],capture_output=True,text=True,timeout=60)
    # DWARF of the built objects (real arm64 layout)
    dwarf={}
    for obj,st,want in (('drivers/cpufreq/qcom-cpufreq-hw.o','cpufreq_qcom',{'size':424,'dcvsh_freq_limit_time':96,'xo_rate':104,'dcvsh_freq_limit':120,
                                                                          'init_time_ms':128,'freq_poll_work':136,'freq_limit_time_attr':288,'total_time_attr':320,'skip_data':352}),
                        ('drivers/cpufreq/cpufreq.o','cpufreq_driver',{'size':192,'get':104,'get_real':112,'bios_limit':120,'exit':128,'attr':168})):
        got=dwarf_layout(OBJ/obj,st)
        dwarf[st]={k:(got.get(k),v) for k,v in want.items()}
    dwarf_ok=all(a==b for d in dwarf.values() for a,b in d.values())
    rc=r.returncode if r.returncode else (0 if dwarf_ok else 3)
    report={'sources':{n:hashlib.sha256((SOURCE/n).read_bytes()).hexdigest() for n in sorted(srcs)},'harness_sha256':hashlib.sha256(code.encode()).hexdigest(),
            'expected':defs,'dwarf_layout':dwarf,'dwarf_ok':dwarf_ok,'exit_code':rc,'stdout':r.stdout,'stderr':r.stderr[-3000:],
            'scope':'Actual struct cpufreq_driver/cpufreq_qcom/skipped_freq definitions (offsets asserted against the factory with arm64-sized '
                    'kernel types, plus DWARF of the built objects), the dcvsh show bodies, limits_mitigation_notify, limits_dcvsh_poll, '
                    'qcom_cpufreq_hw_get/get_real, qcom_cpufreq_hw_cpu_init, qcom_cpu_resources_init, the cpufreq_qcom_hw_driver initializer and '
                    'cpufreq core policy_is_inactive/show_cpuinfo_cur_freq_real/cpufreq_add_dev_interface. MMIO, irq, sysfs, mutex modeled.',
            'device_modified':False}
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));raise SystemExit(rc)
if __name__=='__main__':main()
