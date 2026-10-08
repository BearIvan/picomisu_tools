"""Execute the actual check_thread_timers RLIMIT_RTTIME watchdog and the ktop worker dump under ASan/UBSan."""
from pathlib import Path
import hashlib,importlib.util,json,subprocess
BASE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro');SOURCE=BASE/'source/phoenix-kernel-recovery'
POSIX='kernel/time/posix-cpu-timers.c';KTOP='fs/proc/ktop.c'
MODEL=r'''
#include <assert.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef uint64_t u64;
#define HZ 100
#define USEC_PER_SEC 1000000UL
#define RLIM_INFINITY (~0UL)
#define RLIMIT_RTTIME 15
#define DIV_ROUND_UP(n,d) (((n)+(d)-1)/(d))
#define SIGKILL 9
#define SIGXCPU 24
#define CONFIG_PROC_KTOP 1
struct list_head {struct list_head *next,*prev;};
struct task_cputime {u64 prof_exp,virt_exp,sched_exp;};
struct rlimit {unsigned long rlim_cur,rlim_max;};
struct signal_struct {struct rlimit rlim[16];};
struct sched_rt_entity {unsigned long timeout;};
struct sched_entity {u64 sum_exec_runtime;};
struct task_struct {struct list_head cpu_timers[3];struct task_cputime cputime_expires;struct signal_struct *signal;struct sched_rt_entity rt;struct sched_entity se;int prio,pid,tgid;char comm[16];};
struct siginfo {int si_signo,si_errno,si_code;int pad[29];};
static void clear_siginfo(struct siginfo *i){memset(i,0x5a,sizeof(*i));memset(i,0,sizeof(*i));}
static int sigs,last_sig,last_code,kills,ktop_dumps,logs;static char lastlog[256];
static int __group_send_sig_info(int sig,struct siginfo *info,struct task_struct *t){(void)t;sigs++;last_sig=sig;
  last_code=(info&&(unsigned long)info>16)?info->si_code:-1;if(sig==SIGKILL)kills++;if(info&&(unsigned long)info>16)assert(info->si_signo==sig);return 0;}
#define SEND_SIG_PRIV ((struct siginfo *)1)
static int pr_info(const char *f,...){va_list a;va_start(a,f);vsnprintf(lastlog,sizeof(lastlog),f,a);va_end(a);logs++;return 0;}
static int print_fatal_signals;
static int dl_task(struct task_struct *t){(void)t;return 0;}
static void check_dl_overrun(struct task_struct *t){(void)t;}
static int task_cputime_zero(const struct task_cputime *c){return !c->prof_exp&&!c->virt_exp&&!c->sched_exp;}
static u64 check_timers_list(struct list_head *l,struct list_head *f,u64 now){(void)l;(void)f;(void)now;return 5;}
static u64 prof_ticks(struct task_struct *t){(void)t;return 0;}
static u64 virt_ticks(struct task_struct *t){(void)t;return 0;}
static unsigned long task_rlimit(struct task_struct *t,int r){return t->signal->rlim[r].rlim_cur;}
static unsigned long task_rlimit_max(struct task_struct *t,int r){return t->signal->rlim[r].rlim_max;}
static int task_pid_nr(struct task_struct *t){return t->pid;}
static int task_tgid_nr(struct task_struct *t){return t->tgid;}
static void ktop_show_by_workqueue(void){ktop_dumps++;}
#define TICK_DEP_BIT_POSIX_TIMER 1
static int tick_clears;static void tick_dep_clear_task(struct task_struct *t,int b){(void)t;(void)b;tick_clears++;}
'''
MAIN=r'''
static struct signal_struct sig;static struct task_struct t={.signal=&sig,.prio=89,.pid=321,.tgid=300,.comm="RenderThread"};
static void reset(unsigned long soft,unsigned long hard,unsigned long timeout){memset(&sig,0,sizeof(sig));sig.rlim[RLIMIT_RTTIME].rlim_cur=soft;sig.rlim[RLIMIT_RTTIME].rlim_max=hard;
  t.rt.timeout=timeout;t.cputime_expires.sched_exp=1;sigs=kills=ktop_dumps=logs=0;last_sig=0;}
int main(void){struct list_head firing;
 /* below soft: nothing */
 reset(200000,500000,20);check_thread_timers(&t,&firing);assert(!sigs&&!logs&&sig.rlim[RLIMIT_RTTIME].rlim_cur==200000);
 /* soft exceeded (20 ticks = 200 ms): log only, soft += 100 ms, no SIGXCPU */
 reset(200000,500000,21);check_thread_timers(&t,&firing);
 assert(!sigs&&logs==1&&sig.rlim[RLIMIT_RTTIME].rlim_cur==300000&&sig.rlim[RLIMIT_RTTIME].rlim_max==500000);
 assert(!strcmp(lastlog,"RT Watchdog Timeout (soft): RenderThread[321], tgid=300 timeout=21 tickets prio=89\n"));
 /* soft below hard by less than the step: raised by 100 ms anyway (factory), still no signal */
 reset(400000,450000,41);check_thread_timers(&t,&firing);assert(!sigs&&logs==1&&sig.rlim[RLIMIT_RTTIME].rlim_cur==500000);
 /* soft == hard: never raised */
 reset(450000,450000,45);check_thread_timers(&t,&firing);assert(!sigs&&!logs&&sig.rlim[RLIMIT_RTTIME].rlim_cur==450000);
 /* hard exceeded: no SIGKILL, signal 35 with si_code 129, rlim_max doubled, ktop dump */
 reset(200000,500000,51);check_thread_timers(&t,&firing);
 assert(sigs==1&&!kills&&last_sig==35&&last_code==129&&sig.rlim[RLIMIT_RTTIME].rlim_max==1000000&&ktop_dumps==1);
 assert(!strcmp(lastlog,"CPU Watchdog Timeout (hard): RenderThread[321], tgid=300 timeout=51 tickets prio=89\n"));
 /* after doubling, the same timeout is only a soft event */
 sigs=ktop_dumps=logs=0;check_thread_timers(&t,&firing);assert(!sigs&&!ktop_dumps&&logs==1);
 /* exactly at the hard limit is still soft */
 reset(200000,500000,50);check_thread_timers(&t,&firing);assert(!sigs&&logs==1);
 /* infinite hard: soft path only, soft keeps growing */
 reset(200000,RLIM_INFINITY,1000);check_thread_timers(&t,&firing);assert(!sigs&&sig.rlim[RLIMIT_RTTIME].rlim_cur==300000);
 /* RTTIME unlimited: untouched */
 reset(RLIM_INFINITY,RLIM_INFINITY,100000);check_thread_timers(&t,&firing);assert(!sigs&&!logs);
 puts("PASS: soft limit logs and raises soft by 100 ms without SIGXCPU; hard limit sends signal 35/si_code 129 instead of SIGKILL, doubles rlim_max and dumps ktop; boundaries and infinite limits");
 return 0;}
'''
def main():
    spec=importlib.util.spec_from_file_location('ex',Path(__file__).with_name('test-pico-sensor-mono-hook.py'));ex=importlib.util.module_from_spec(spec);spec.loader.exec_module(ex)
    src=(SOURCE/POSIX).read_text();ktop=(SOURCE/KTOP).read_text()
    defs='\n'.join(l for l in src.splitlines() if l.startswith('#define PICO_RT_WATCHDOG_'))
    body=ex.function(src,'static void check_thread_timers(')
    # the worker dump must use the shared show routine with a NULL seq_file
    wf=ex.function(ktop,'static void ktop_show_work_func(');assert 'ktop_show(NULL, NULL);' in wf,'work func'
    bw=ex.function(ktop,'void ktop_show_by_workqueue(');assert 'queue_work(system_unbound_wq, &ktop_show_work);' in bw,'queue'
    assert 'static DECLARE_WORK(ktop_show_work, ktop_show_work_func);' in ktop and ktop.count('seq_printf(m,')==1,'ktop_out'
    code=MODEL+defs+'\n'+body+MAIN
    out=BASE/'out/phoenix-kernel-recovery/ktop-rt-watchdog-tests';out.mkdir(exist_ok=True);(out/'harness.c').write_text(code)
    subprocess.run(['gcc','-std=gnu11','-g','-O1','-Wall','-Wno-unused-function','-fsanitize=address,undefined','-fno-sanitize-recover=all',str(out/'harness.c'),'-o',str(out/'test')],check=True)
    r=subprocess.run([str(out/'test')],capture_output=True,text=True,timeout=60)
    report={'sources':{n:hashlib.sha256((SOURCE/n).read_bytes()).hexdigest() for n in (POSIX,KTOP,'include/linux/ktop.h')},'harness_sha256':hashlib.sha256(code.encode()).hexdigest(),
            'exit_code':r.returncode,'stdout':r.stdout,'stderr':r.stderr[-2000:],
            'scope':'Actual check_thread_timers executed with modeled rlimits/signals; ktop worker and NULL-seq_file dump checked on the source (ktop_show itself is pre-existing public code).','device_modified':False}
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));raise SystemExit(r.returncode)
if __name__=='__main__':main()
