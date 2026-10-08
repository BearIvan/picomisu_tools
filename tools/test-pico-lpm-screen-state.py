"""Execute the actual screen-state LPM restriction (DT parse, panel notifier, lpm_disallowed) under ASan/UBSan."""
from pathlib import Path
import hashlib,importlib.util,json,re,subprocess
BASE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro');SOURCE=BASE/'source/phoenix-kernel-recovery'
LPM='drivers/cpuidle/lpm-levels.c';OF='drivers/cpuidle/lpm-levels-of.c';HDR='drivers/cpuidle/lpm-levels.h'
MODEL=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef int64_t s64;typedef uint64_t u64;
#define READ_ONCE(x) (x)
#define WRITE_ONCE(x,v) ((x)=(v))
#define KBUILD_MODNAME "lpm_levels"
#define IS_ERR(p) ((unsigned long)(p)>=(unsigned long)-4095)
#define ERR_PTR(e) ((void *)(long)(e))
#define EPROBE_DEFER 517
static int infos;
#define pr_info(...) (infos++)
struct cpumask {unsigned long bits[1];};
#define nr_cpumask_bits 8
#define cpumask_bits(m) ((m)->bits)
static void cpumask_clear(struct cpumask *m){m->bits[0]=0;}
static int cpumask_test_cpu(int c,const struct cpumask *m){return (m->bits[0]>>c)&1;}
static void cpumask_and(struct cpumask *d,const struct cpumask *a,const struct cpumask *b){d->bits[0]=a->bits[0]&b->bits[0];}
static int bitmap_parse(const char *s,unsigned len,unsigned long *b,int nbits){char t[32];if(len>=sizeof t)return -22;memcpy(t,s,len);t[len]=0;char *e;unsigned long v=strtoul(t,&e,16);
  if(!len||*e)return -22;*b=v&((1UL<<nbits)-1);/* the kernel parser may leave partial bits on error */if(v>>nbits)return -75;return 0;}
struct device_node {const char *mask;int npanels;int found_at;};
struct drm_panel {int id;};
static struct drm_panel panels[4];static int put_nodes,parsed;
static int of_count_phandle_with_args(struct device_node *np,const char *n,const char *c){assert(!strcmp(n,"panel")&&!c);return np->npanels;}
static struct device_node phandle_nodes[4];
static struct device_node *of_parse_phandle(struct device_node *np,const char *n,int i){assert(!strcmp(n,"panel")&&i<np->npanels);parsed++;phandle_nodes[i].found_at=(i==np->found_at);return &phandle_nodes[i];}
static struct drm_panel *of_drm_find_panel(struct device_node *n){return n->found_at?&panels[n-phandle_nodes]:ERR_PTR(-EPROBE_DEFER);}
static void of_node_put(struct device_node *n){(void)n;put_nodes++;}
static const void *of_get_property(struct device_node *np,const char *n,int *l){(void)l;assert(!strcmp(n,"qcom,lpm-disallowed-cpumask"));return np->mask;}
struct lpm_cpu {struct cpumask related_cpus;struct cpumask lpm_disallowed_cpus;u64 bias;};
static int sleep_disabled,isolated_mask;static u64 bias_val;
static int cpu_isolated(int c){return (isolated_mask>>c)&1;}
static u64 sched_lpm_disallowed_time(int c){(void)c;return bias_val;}
#define DRM_PANEL_EVENT_BLANK 0x01
enum {DRM_PANEL_BLANK_UNBLANK,DRM_PANEL_BLANK_LP,DRM_PANEL_BLANK_POWERDOWN};
struct drm_panel_notifier {int refresh_rate;void *data;unsigned id;};
struct notifier_block {int x;};
static bool screen_on_now = true;
'''
MAIN=r'''
int main(void){struct device_node np={"ff",3,1};struct lpm_cpu c;
 /* DT: first registered panel wins; mask parsed up to newline */
 lpm_of_parse_screen_config(&np);assert(lpm_active_panel==&panels[1]&&parsed==2&&put_nodes==2&&lpm_disallowed_mask.bits[0]==0xff);
 lpm_active_panel=NULL;np=(struct device_node){"f0\nxx",2,-1};parsed=put_nodes=0;lpm_of_parse_screen_config(&np);assert(!lpm_active_panel&&parsed==2&&put_nodes==2&&lpm_disallowed_mask.bits[0]==0xf0);
 np=(struct device_node){"zz",0,-1};lpm_of_parse_screen_config(&np);assert(lpm_disallowed_mask.bits[0]==0);
 np=(struct device_node){"1ff",0,-1};lpm_of_parse_screen_config(&np);assert(lpm_disallowed_mask.bits[0]==0);
 np=(struct device_node){NULL,0,-1};lpm_disallowed_mask.bits[0]=0x3;lpm_of_parse_screen_config(&np);assert(lpm_disallowed_mask.bits[0]==0);
 /* per-cpu mask = related & DT mask (as parse_cpu_levels does) */
 c.related_cpus.bits[0]=0xf0;struct cpumask m={{0x30}};cpumask_and(&c.lpm_disallowed_cpus,&c.related_cpus,&m);assert(c.lpm_disallowed_cpus.bits[0]==0x30);
 /* lpm_disallowed */
 c.bias=0;screen_on_now=true;assert(lpm_disallowed(1000,4,&c)&&!lpm_disallowed(1000,6,&c));
 screen_on_now=false;assert(!lpm_disallowed(1000,4,&c));
 screen_on_now=true;isolated_mask=1<<4;assert(!lpm_disallowed(1000,4,&c));isolated_mask=0;
 sleep_disabled=1;assert(lpm_disallowed(1000,6,&c));sleep_disabled=0;
 bias_val=77;assert(lpm_disallowed(1000,6,&c)&&c.bias==77);bias_val=0;
 assert(lpm_disallowed(-1,6,&c));
 /* panel notifier */
 {int blank;struct drm_panel_notifier ev={60,&blank,0};
  screen_on_now=true;blank=DRM_PANEL_BLANK_POWERDOWN;assert(!screen_state_chg_callback(NULL,DRM_PANEL_EVENT_BLANK,&ev)&&!screen_on_now);
  blank=DRM_PANEL_BLANK_UNBLANK;screen_state_chg_callback(NULL,DRM_PANEL_EVENT_BLANK,&ev);assert(screen_on_now);
  blank=DRM_PANEL_BLANK_LP;screen_state_chg_callback(NULL,DRM_PANEL_EVENT_BLANK,&ev);assert(screen_on_now);
  blank=DRM_PANEL_BLANK_POWERDOWN;screen_state_chg_callback(NULL,2,&ev);assert(screen_on_now);
  screen_state_chg_callback(NULL,DRM_PANEL_EVENT_BLANK,NULL);ev.data=NULL;screen_state_chg_callback(NULL,DRM_PANEL_EVENT_BLANK,&ev);assert(screen_on_now);}
 puts("PASS: panel lookup takes the first registered panel and puts every node; cpumask parse incl. newline, garbage, overflow, absence; screen-on restriction per CPU, isolation/sleep_disabled/bias/negative sleep; blank notifier on/off/LP/other events/NULL data");
 return 0;}
'''
def main():
    spec=importlib.util.spec_from_file_location('ex',Path(__file__).with_name('test-pico-sensor-mono-hook.py'));ex=importlib.util.module_from_spec(spec);spec.loader.exec_module(ex)
    lpm=(SOURCE/LPM).read_text();of=(SOURCE/OF).read_text()
    assert 'cpumask_and(&cpu->lpm_disallowed_cpus, &cpu->related_cpus,\n\t\t    &lpm_disallowed_mask);' in ex.function(of,'static int parse_cpu_levels('),'per-cpu mask'
    assert re.search(r'lpm_of_parse_screen_config\(pdev->dev\.of_node\);\s*\n\s*top = of_find_node_by_name',of),'parse order'
    assert 'drm_panel_notifier_register(lpm_active_panel, &screen_noti_block)' in ex.function(lpm,'static int lpm_probe('),'probe'
    glob='struct drm_panel *lpm_active_panel;\nstatic struct cpumask lpm_disallowed_mask;\n'
    assert glob in of
    code=(MODEL+glob+ex.function(of,'static void lpm_of_parse_screen_config(')+'\n'+ex.function(lpm,'static inline bool lpm_disallowed(')+'\n'
          +ex.function(lpm,'static int screen_state_chg_callback(')+MAIN)
    out=BASE/'out/phoenix-kernel-recovery/lpm-screen-state-tests';out.mkdir(exist_ok=True);(out/'harness.c').write_text(code)
    subprocess.run(['gcc','-std=gnu11','-g','-O1','-Wall','-Wno-unused-function','-fsanitize=address,undefined','-fno-sanitize-recover=all',str(out/'harness.c'),'-o',str(out/'test')],check=True)
    r=subprocess.run([str(out/'test')],capture_output=True,text=True,timeout=60)
    report={'sources':{n:hashlib.sha256((SOURCE/n).read_bytes()).hexdigest() for n in (LPM,OF,HDR)},'harness_sha256':hashlib.sha256(code.encode()).hexdigest(),
            'exit_code':r.returncode,'stdout':r.stdout,'stderr':r.stderr[-2000:],
            'scope':'Actual lpm_of_parse_screen_config, lpm_disallowed and screen_state_chg_callback; per-cpu mask, parse order and probe registration checked on the source. OF/DRM/cpumask modeled.','device_modified':False}
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));raise SystemExit(r.returncode)
if __name__=='__main__':main()
