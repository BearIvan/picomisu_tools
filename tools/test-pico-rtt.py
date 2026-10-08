"""Execute the actual PICO RTT recorder, probe, panic notifier and the __switch_to hook under ASan/UBSan."""
from pathlib import Path
import hashlib,importlib.util,json,subprocess
BASE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro');SOURCE=BASE/'source/phoenix-kernel-recovery'
RTT='kernel/trace/pico_rtt.c';PROC='arch/arm64/kernel/process.c';GIC='drivers/irqchip/irq-gic-v3.c';HDR='include/linux/pico_rtt.h'
RTT_FUNCS=['static notrace void rtt_record(','notrace void rtt_irq_switch_hook(','notrace void rtt_task_switch_callback(',
           'static int rtt_panic_notifier(','static void rtt_free(','static int rtt_probe(']
MODEL=r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef uint8_t u8;typedef uint16_t u16;typedef uint32_t u32;typedef uint64_t u64;typedef u64 dma_addr_t;
#define NR_CPUS 8
#define notrace
#define EXPORT_SYMBOL_GPL(x)
#define READ_ONCE(x) (x)
#define WRITE_ONCE(x,v) ((x)=(v))
#define ENOMEM 12
#define GFP_KERNEL 0
#define NOTIFY_DONE 0
static int ncpus=4,cur_cpu;
#define for_each_possible_cpu(c) for((c)=0;(c)<(unsigned)ncpus;(c)++)
static int raw_smp_processor_id(void){return cur_cpu;}
static u64 clk=1000;static u64 sched_clock(void){return clk++;}
struct device {int x;};struct platform_device {struct device dev;};
static int errs;
#define dev_err(d,...) (errs++)
static int allocs,alloc_fail_at=-1,nalloc;
static void *dma_alloc_coherent(struct device *d,size_t sz,dma_addr_t *h,int g){(void)d;(void)g;if(nalloc++==alloc_fail_at)return NULL;allocs++;void *p=calloc(1,sz);*h=0x80000000u+(u64)nalloc*0x10000;return p;}
static void dma_free_coherent(struct device *d,size_t sz,void *p,dma_addr_t h){(void)d;(void)sz;(void)h;allocs--;free(p);}
#define MAX_NAME_LENGTH 12
struct md_region {char name[MAX_NAME_LENGTH];u32 id;u64 virt_addr;u64 phys_addr;u64 size;};
static struct md_region regions[16];static int nreg,md_fail;
static int msm_minidump_add_region(const struct md_region *r){regions[nreg++]=*r;return md_fail;}
static int flushed[NR_CPUS];static void *flush_ptr[NR_CPUS];
static void *rtt_bufs_for_flush[NR_CPUS];
static void __dma_flush_area(const void *p,size_t sz){assert(sz==65536);for(int c=0;c<ncpus;c++)if(rtt_bufs_for_flush[c]==p)flushed[c]++;}
struct notifier_block {int (*notifier_call)(struct notifier_block *,unsigned long,void *);};
static struct notifier_block *panic_registered;static int panic_notifier_list;
static int atomic_notifier_chain_register(int *l,struct notifier_block *n){(void)l;panic_registered=n;return 0;}
struct task_struct {int pid;struct task_struct *real_parent;};
'''
MAIN=r'''
static struct task_struct init_task_s={1,NULL},parent={1234,&init_task_s},child={0x12345,&parent};
static int order[64],nord;
static void fpsimd_thread_switch(struct task_struct *n){(void)n;order[nord++]=1;}
static void dsb_ish(void){order[nord++]=2;}
static struct task_struct *cpu_switch_to(struct task_struct *p,struct task_struct *n){(void)n;order[nord++]=4;return p;}
static int hook_calls;static struct task_struct *hp,*hn;
static void test_hook(struct task_struct *p,struct task_struct *n){order[nord++]=3;hook_calls++;hp=p;hn=n;}
int main(void){struct platform_device pdev;unsigned c;
 init_task_s.real_parent=&init_task_s;
 /* --- hook registry --- */
 assert(!thread_hook&&!int_hook);thread_register_notifier(test_hook);assert(thread_hook==test_hook);
 irq_register_notifier(rtt_irq_switch_hook);assert(int_hook==rtt_irq_switch_hook);
 nord=0;assert(switch_to_model(&parent,&child)==&parent&&hook_calls==1&&hp==&parent&&hn==&child);
 assert(nord==4&&order[0]==1&&order[1]==2&&order[2]==3&&order[3]==4);
 thread_unregister_notifier();irq_unregister_notifier();assert(!thread_hook&&!int_hook);
 nord=0;switch_to_model(&parent,&child);assert(hook_calls==1&&nord==3);
 /* --- probe: allocation failure part-way frees everything and installs nothing --- */
 alloc_fail_at=2;nalloc=0;assert(rtt_probe(&pdev)==-ENOMEM&&allocs==0&&!thread_hook&&!int_hook&&!panic_registered);
 for(c=0;c<NR_CPUS;c++)assert(!g_rtt_ctrl[c].buf&&!g_rtt_ctrl[c].enabled);
 /* --- probe success --- */
 alloc_fail_at=-1;nalloc=0;nreg=0;md_fail=1;errs=0;assert(rtt_probe(&pdev)==0&&allocs==ncpus&&nreg==ncpus&&errs==ncpus+1);
 assert(thread_hook==rtt_task_switch_callback&&int_hook==rtt_irq_switch_hook&&panic_registered==&rtt_notifier);
 for(c=0;c<(unsigned)ncpus;c++){char n[12];snprintf(n,12,"rtt_%d",c);assert(!strcmp(regions[c].name,n)&&regions[c].id==0xffffffffu&&regions[c].size==65536);
  assert(regions[c].virt_addr==(u64)(uintptr_t)g_rtt_ctrl[c].buf&&regions[c].phys_addr==g_rtt_ctrl[c].phys);
  assert(g_rtt_ctrl[c].cpu==c&&g_rtt_ctrl[c].entries==4096&&g_rtt_ctrl[c].idx==0&&g_rtt_ctrl[c].enabled==1);rtt_bufs_for_flush[c]=g_rtt_ctrl[c].buf;}
 /* --- recording: per-CPU, encoding, wrap at 4096 --- */
 cur_cpu=2;clk=500;switch_to_model(&parent,&child);
 assert(g_rtt_ctrl[2].idx==1&&g_rtt_ctrl[2].buf[0].ts==500&&g_rtt_ctrl[2].buf[0].data==((0x2345u)|(1234u<<16))&&g_rtt_ctrl[1].idx==0);
 rtt_irq_switch_hook(33,1);assert(g_rtt_ctrl[2].buf[1].data==(1u|(33u<<16))&&g_rtt_ctrl[2].idx==2);
 for(int i=0;i<4094;i++)rtt_task_switch_callback(&parent,&parent);assert(g_rtt_ctrl[2].idx==0);
 assert(g_rtt_ctrl[2].buf[4095].data==(1234u|(1u<<16)));
 rtt_task_switch_callback(&parent,&child);assert(g_rtt_ctrl[2].idx==1&&g_rtt_ctrl[2].buf[0].data==((0x2345u)|(1234u<<16)));
 cur_cpu=3;rtt_task_switch_callback(&parent,&child);assert(g_rtt_ctrl[3].idx==1);
 /* --- panic: unhook, flush each ring once --- */
 assert(rtt_panic_notifier(&rtt_notifier,0,NULL)==NOTIFY_DONE&&!thread_hook&&!int_hook);
 for(c=0;c<(unsigned)ncpus;c++)assert(flushed[c]==1);
 {unsigned i2=g_rtt_ctrl[3].idx;switch_to_model(&parent,&child);assert(g_rtt_ctrl[3].idx==i2);}
 rtt_free(&pdev.dev);assert(allocs==0);
 puts("PASS: hook registry and __switch_to ordering (after dsb, before cpu_switch_to, skipped when unhooked); probe failure "
      "unwinds without hooks; minidump regions rtt_<cpu> with buffer addresses; per-CPU recording, pid/parent encoding, "
      "irq word, 4096-entry wrap; panic unhooks and flushes every ring");
 return 0;
}
'''
def main():
    spec=importlib.util.spec_from_file_location('ex',Path(__file__).with_name('test-pico-sensor-mono-hook.py'));ex=importlib.util.module_from_spec(spec);spec.loader.exec_module(ex)
    rtt=(SOURCE/RTT).read_text();proc=(SOURCE/PROC).read_text();gic=(SOURCE/GIC).read_text();hdr=(SOURCE/HDR).read_text()
    hdr_body=hdr[hdr.index('typedef void (*thread_switch_hook_t)'):hdr.index('void thread_register_notifier')]
    rtt_top=rtt[rtt.index('#define RTT_ENTRIES'):rtt.index('static notrace void rtt_record(')]
    notifier=rtt[rtt.index('static struct notifier_block rtt_notifier'):rtt.index('static void rtt_free(')]
    proc_hook=proc[proc.index('static thread_switch_hook_t thread_hook;'):proc.index('EXPORT_SYMBOL_GPL(thread_unregister_notifier);')]
    gic_hook=gic[gic.index('static irq_switch_hook_t int_hook;'):gic.index('EXPORT_SYMBOL_GPL(irq_unregister_notifier);')]
    sw=ex.function(proc,'__notrace_funcgraph struct task_struct *__switch_to(')
    # model the arch helpers around the real hook placement
    sw=sw.replace('__notrace_funcgraph struct task_struct *__switch_to(','static struct task_struct *switch_to_model(')
    for f in ('tls_thread_switch(next);','hw_breakpoint_thread_switch(next);','contextidr_thread_switch(next);','entry_task_switch(next);',
              'uao_thread_switch(next);','ssbs_thread_switch(next);','scs_overflow_check(next);'):
        assert f in sw,f;sw=sw.replace(f,';')
    sw=sw.replace('dsb(ish);','dsb_ish();')
    fwd='static void fpsimd_thread_switch(struct task_struct *);static void dsb_ish(void);static struct task_struct *cpu_switch_to(struct task_struct *,struct task_struct *);\n'
    code=(MODEL+hdr_body+proc_hook+'\n'+gic_hook+'\n'+rtt_top+'\n'.join(ex.function(rtt,f) for f in RTT_FUNCS[:4])+'\n'+notifier
          +'\n'.join(ex.function(rtt,f) for f in RTT_FUNCS[4:])+'\n'+fwd+sw+MAIN)
    out=BASE/'out/phoenix-kernel-recovery/rtt-tests';out.mkdir(exist_ok=True);(out/'harness.c').write_text(code)
    subprocess.run(['gcc','-std=gnu11','-g','-O1','-Wall','-Wno-unused-function','-Wno-unused-variable','-fsanitize=address,undefined','-fno-sanitize-recover=all',str(out/'harness.c'),'-o',str(out/'test')],check=True)
    r=subprocess.run([str(out/'test')],capture_output=True,text=True,timeout=60)
    names=[RTT,PROC,GIC,HDR]
    report={'sources':{n:hashlib.sha256((SOURCE/n).read_bytes()).hexdigest() for n in names},'harness_sha256':hashlib.sha256(code.encode()).hexdigest(),
            'exit_code':r.returncode,'stdout':r.stdout,'stderr':r.stderr[-3000:],
            'scope':'Actual rtt_record/hooks/panic notifier/probe/free, thread and irq hook registries and the patched __switch_to body (arch helpers stubbed, hook ordering checked). DMA, minidump, sched_clock modeled.',
            'device_modified':False}
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));raise SystemExit(r.returncode)
if __name__=='__main__':main()
