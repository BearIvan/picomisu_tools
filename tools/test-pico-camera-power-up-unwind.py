"""Execute actual camera power-up, retained unwind ledger and common shutdown under sanitizers."""
from pathlib import Path
import hashlib,importlib.util,json,re,subprocess
BASE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro');SOURCE=BASE/'source/phoenix-kernel-recovery'
D='techpack/camera/drivers/cam_sensor_module/cam_sensor_utils/'
NAMES=[D+'cam_sensor_util.c',D+'pico_camera_power_down.inc',D+'pico_camera_power_up.inc',D+'cam_sensor_cmn_header.h',D+'cam_sensor_util.h']
MODEL=r'''
#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <stddef.h>
#include <errno.h>
#define CAM_SENSOR 0
#define CAM_INFO(...)
#define CAM_ERR(...)
#define CAM_DBG(...)
#define CAM_SOC_MAX_REGULATOR 5
#define CAM_SOC_MAX_CLK 32
#define CAM_MAX_VOTE 2
#define GPIOF_OUT_INIT_LOW 0
#define GFP_KERNEL 0
#define EPROBE_DEFER 517
typedef unsigned char u8;
/* HEADER */
struct device {int id;};
struct regulator {const char *name;int refs,enabled,load,volt;};
struct pinctrl {int held;};
struct pinctrl_state {int id;};
struct msm_pinctrl_info {struct pinctrl *pinctrl;struct pinctrl_state *gpio_state_active,*gpio_state_suspend;bool use_pinctrl;};
struct cam_sensor_power_ctrl_t {struct device *dev;struct cam_sensor_power_setting *power_setting;uint16_t power_setting_size;struct cam_sensor_power_setting *power_down_setting;uint16_t power_down_setting_size;struct msm_camera_gpio_num_info *gpio_num_info;struct msm_pinctrl_info pinctrl_info;uint8_t cam_pinctrl_status;};
struct cam_hw_soc_info {struct device *dev;int num_rgltr;struct regulator *rgltr[CAM_SOC_MAX_REGULATOR];const char *rgltr_name[CAM_SOC_MAX_REGULATOR];uint32_t rgltr_min_volt[CAM_SOC_MAX_REGULATOR],rgltr_max_volt[CAM_SOC_MAX_REGULATOR],rgltr_op_mode[CAM_SOC_MAX_REGULATOR],rgltr_delay[CAM_SOC_MAX_REGULATOR];uint32_t num_clk;void *clk[CAM_SOC_MAX_CLK];const char *clk_name[CAM_SOC_MAX_CLK];int32_t clk_rate[CAM_MAX_VOTE][CAM_SOC_MAX_CLK];int use_shared_clk;};
struct list_head {struct list_head *next,*prev;};
#define LIST_HEAD(name) struct list_head name={&name,&name}
#define DEFINE_MUTEX(name) int name
#define container_of(p,t,m) ((t *)((char *)(p)-offsetof(t,m)))
#define list_for_each_entry(p,h,m) for(p=container_of((h)->next,__typeof__(*p),m);&p->m!=(h);p=container_of(p->m.next,__typeof__(*p),m))
static void list_add_tail(struct list_head *n,struct list_head *h){n->next=h;n->prev=h->prev;h->prev->next=n;h->prev=n;}
static void list_del(struct list_head *n){n->prev->next=n->next;n->next->prev=n->prev;}
static void mutex_lock(int *m){assert(!*m);*m=1;}
static void mutex_unlock(int *m){assert(*m);*m=0;}
#define MAX_ERRNO 4095
#define IS_ERR_OR_NULL(p) (!(p)||(unsigned long)(void *)(p)>=(unsigned long)-MAX_ERRNO)
#define PTR_ERR(p) ((long)(p))
#define ERR_PTR(e) ((void *)(long)(e))
static void msleep(unsigned ms){}
static void usleep_range(unsigned a,unsigned b){}
/* Fault injection and accounting. */
static int live_alloc,fail_alloc,fail_get_idx=-1,get_null,fail_enable_idx=-1,fail_disable_idx=-1,fail_load,fail_clk_on=-1,fail_clk_off=-1;
static int fail_pin_suspend,fail_shared_init,fail_gpio_table,fail_shared_suspend,pinctrl_absent;
static int shared_votes,shared_pin_held,shared_pin_puts,gpio_table,post_init,events,pin_suspends;
static int gpio_level[64],gpio_order[64],disable_order[CAM_SOC_MAX_REGULATOR];
static int clk_on[CAM_SOC_MAX_CLK],clk_on_calls,clk_off_calls;
static struct regulator regs[CAM_SOC_MAX_REGULATOR];
static struct pinctrl pin;static struct pinctrl_state active,suspend;
static void *kzalloc(size_t s,int f){if(fail_alloc)return NULL;void *p=calloc(1,s);assert(p);live_alloc++;return p;}
static void kfree(void *p){assert(p);live_alloc--;free(p);}
static struct regulator *regulator_get(struct device *d,const char *name){int i;for(i=0;i<CAM_SOC_MAX_REGULATOR;i++)if(regs[i].name&&!strcmp(regs[i].name,name)){if(i==fail_get_idx)return get_null?NULL:ERR_PTR(-EPROBE_DEFER);regs[i].refs++;return &regs[i];}return ERR_PTR(-ENODEV);}
static void regulator_put(struct regulator *r){assert(r&&r->refs>0&&!r->enabled);r->refs--;}
static int regulator_disable(struct regulator *r){assert(r->refs>0&&r->enabled);if(r==&regs[fail_disable_idx<0?0:fail_disable_idx]&&fail_disable_idx>=0)return -EIO;r->enabled=0;disable_order[r-regs]=++events;return 0;}
static int regulator_count_voltages(struct regulator *r){return 1;}
static int regulator_set_load(struct regulator *r,int l){assert(!r->enabled);if(fail_load)return -EIO;r->load=l;return 0;}
static int regulator_set_voltage(struct regulator *r,int a,int b){assert(!r->enabled);r->volt=a;return 0;}
static int cam_soc_util_regulator_enable(struct regulator *r,const char *n,uint32_t a,uint32_t b,uint32_t c,uint32_t d){assert(r&&r->refs>0&&!r->enabled);r->volt=a;r->load=c;if(r==&regs[fail_enable_idx<0?0:fail_enable_idx]&&fail_enable_idx>=0)return -EIO;r->enabled=1;return 0;}
static int cam_soc_util_clk_enable(void *c,const char *n,int32_t rate){int i=(int)(long)c;assert(!clk_on[i]);clk_on_calls++;if(i==fail_clk_on)return -ETIMEDOUT;clk_on[i]=1;return 0;}
static int cam_soc_util_clk_disable(void *c,const char *n){int i=(int)(long)c;clk_off_calls++;assert(clk_on[i]);if(i==fail_clk_off)return -EIO;clk_on[i]=0;return 0;}
static void cam_res_mgr_gpio_set_value(unsigned int gpio,int val){gpio_level[gpio]=val;gpio_order[gpio]=++events;}
static int msm_camera_pinctrl_init(struct msm_pinctrl_info *p,struct device *d){if(pinctrl_absent)return -EINVAL;assert(!pin.held);pin.held=1;p->pinctrl=&pin;p->gpio_state_active=&active;p->gpio_state_suspend=&suspend;return 0;}
static int pinctrl_select_state(struct pinctrl *p,struct pinctrl_state *s){assert(p==&pin&&pin.held);if(s==&suspend){pin_suspends++;if(fail_pin_suspend)return -EIO;}return 0;}
static void devm_pinctrl_put(struct pinctrl *p){assert(p==&pin&&pin.held);pin.held=0;}
static int cam_res_mgr_shared_clk_config(bool on){shared_votes+=on?1:-1;assert(shared_votes>=0);return 0;}
static int cam_res_mgr_shared_pinctrl_init(void){if(fail_shared_init)return -EINVAL;shared_pin_held=1;return 0;}
static int cam_res_mgr_shared_pinctrl_select_state(bool on){if(!on&&fail_shared_suspend)return -EIO;return 0;}
static void cam_res_mgr_shared_pinctrl_put(void){shared_pin_held=0;shared_pin_puts++;}
static int cam_res_mgr_shared_pinctrl_post_init(void){post_init++;return 0;}
static int cam_sensor_util_request_gpio_table(struct cam_hw_soc_info *s,int en){if(en){gpio_table++;return fail_gpio_table?-EINVAL:0;}gpio_table--;return 0;}
'''
MAIN=r'''
enum {G_VANA=1,G_RESET=2,G_VIO=3};
static struct device dev;
static struct msm_camera_gpio_num_info gpio;
static struct cam_sensor_power_setting up[MAX_POWER_CONFIG],down[MAX_POWER_CONFIG];
static struct cam_sensor_power_ctrl_t ctrl;
static struct cam_hw_soc_info soc;
static void set(struct cam_sensor_power_setting *p,int t,int v,long c){memset(p,0,sizeof(*p));p->seq_type=t;p->seq_val=v;p->config_val=c;}
/* regs: 0 cam_vana, 1 cam_vio, 2 cam_clk; clocks 0..1. up: MCLK, VANA, VIO, RESET. */
static void fixture(void){
 assert(!live_alloc&&pico_camera_shutdowns.next==&pico_camera_shutdowns);
 fail_alloc=get_null=fail_load=fail_pin_suspend=fail_shared_init=fail_gpio_table=fail_shared_suspend=pinctrl_absent=0;
 fail_get_idx=fail_enable_idx=fail_disable_idx=fail_clk_on=fail_clk_off=-1;
 shared_votes=shared_pin_held=shared_pin_puts=gpio_table=post_init=events=pin_suspends=clk_on_calls=clk_off_calls=0;
 memset(gpio_level,0,sizeof(gpio_level));memset(gpio_order,0,sizeof(gpio_order));memset(disable_order,0,sizeof(disable_order));memset(clk_on,0,sizeof(clk_on));memset(&pin,0,sizeof(pin));
 memset(regs,0,sizeof(regs));regs[0].name="cam_vana";regs[1].name="cam_vio";regs[2].name="cam_clk";
 memset(&gpio,0,sizeof(gpio));gpio.valid[SENSOR_VANA]=gpio.valid[SENSOR_RESET]=gpio.valid[SENSOR_VIO]=1;gpio.gpio_num[SENSOR_VANA]=G_VANA;gpio.gpio_num[SENSOR_RESET]=G_RESET;gpio.gpio_num[SENSOR_VIO]=G_VIO;
 set(&up[0],SENSOR_MCLK,0,24000000);set(&up[1],SENSOR_VANA,0,0);set(&up[2],SENSOR_VIO,1,0);set(&up[3],SENSOR_RESET,0,1);
 set(&down[0],SENSOR_RESET,0,GPIOF_OUT_INIT_LOW);set(&down[1],SENSOR_VIO,1,0);set(&down[2],SENSOR_VANA,0,0);set(&down[3],SENSOR_MCLK,0,0);
 memset(&ctrl,0,sizeof(ctrl));ctrl.dev=&dev;ctrl.power_setting=up;ctrl.power_setting_size=4;ctrl.power_down_setting=down;ctrl.power_down_setting_size=4;ctrl.gpio_num_info=&gpio;
 memset(&soc,0,sizeof(soc));soc.dev=&dev;soc.num_rgltr=3;soc.rgltr_name[0]="cam_vana";soc.rgltr_name[1]="cam_vio";soc.rgltr_name[2]="cam_clk";soc.num_clk=2;soc.clk[0]=(void *)0;soc.clk[1]=(void *)1;soc.use_shared_clk=1;
}
static bool pending(void){return pico_camera_shutdown_find(&ctrl)!=NULL;}
static void clean(void){int i;
 assert(!pending()&&!live_alloc);
 for(i=0;i<3;i++)assert(!regs[i].refs&&!regs[i].enabled&&!soc.rgltr[i]);
 assert(!clk_on[0]&&!clk_on[1]);
 assert(!gpio_level[G_VANA]&&!gpio_level[G_RESET]&&!gpio_level[G_VIO]);
 assert(!pin.held&&!ctrl.cam_pinctrl_status&&!shared_votes&&!shared_pin_held&&gpio_table==0);
 for(i=0;i<MAX_POWER_CONFIG;i++)assert(!up[i].data[0]);
}
static void powered(void){assert(regs[0].enabled&&regs[1].enabled&&regs[2].enabled&&clk_on[0]&&clk_on[1]&&gpio_level[G_RESET]&&gpio_level[G_VANA]&&gpio_level[G_VIO]&&pin.held&&shared_votes==1&&shared_pin_held&&gpio_table==1&&post_init==1);}
static void no_mutation(void){int i;assert(!pending()&&!live_alloc&&!shared_votes&&!pin.held&&!shared_pin_held&&!gpio_table&&!clk_on_calls);for(i=0;i<3;i++)assert(!regs[i].refs);}
int main(void){
 /* 1. Full success and phased shutdown. */
 fixture();assert(!cam_sensor_core_power_up(&ctrl,&soc));powered();assert(up[0].data[0]==&regs[2]&&up[1].data[0]==&regs[0]);
 assert(!cam_sensor_util_power_down(&ctrl,&soc));clean();
 /* 2. Regulator get failure at VIO: MCLK+VANA unwound, error not success. */
 fixture();fail_get_idx=1;assert(cam_sensor_core_power_up(&ctrl,&soc)==-EPROBE_DEFER);clean();assert(clk_off_calls==2);
 fixture();fail_get_idx=1;get_null=1;assert(cam_sensor_core_power_up(&ctrl,&soc)==-EINVAL);clean();
 /* 3. Enable failure: got-but-disabled VIO gets load/voltage reset and put, no disable. */
 fixture();fail_enable_idx=1;regs[1].load=-1;assert(cam_sensor_core_power_up(&ctrl,&soc)==-EIO);clean();assert(regs[1].load==0&&!gpio_order[G_VIO]);
 /* 4. Second clock fails: only clock0 disabled; cam_clk released. */
 fixture();fail_clk_on=1;assert(cam_sensor_core_power_up(&ctrl,&soc)==-ETIMEDOUT);clean();assert(clk_on_calls==2&&clk_off_calls==1);
 /* 5. GPIO table request failure reaches GPIO step: real error, prior steps unwound, RESET untouched. */
 fixture();fail_gpio_table=1;assert(cam_sensor_core_power_up(&ctrl,&soc)==-EINVAL);clean();assert(!gpio_order[G_RESET]);
 /* 6. Validation before any change. */
 fixture();up[0].seq_val=2;assert(cam_sensor_core_power_up(&ctrl,&soc)==-EINVAL);no_mutation();
 fixture();up[1].seq_val=CAM_VREG_MAX;assert(cam_sensor_core_power_up(&ctrl,&soc)==-EINVAL);no_mutation();
 fixture();up[2].seq_val=0;assert(cam_sensor_core_power_up(&ctrl,&soc)==-EINVAL);no_mutation();
 fixture();up[2].seq_val=2;assert(cam_sensor_core_power_up(&ctrl,&soc)==-EINVAL);no_mutation();
 fixture();ctrl.gpio_num_info=NULL;assert(cam_sensor_core_power_up(&ctrl,&soc)==-EINVAL);no_mutation();
 fixture();ctrl.power_setting_size=MAX_POWER_CONFIG+1;assert(cam_sensor_core_power_up(&ctrl,&soc)==-EINVAL);no_mutation();
 fixture();soc.num_rgltr=0;assert(cam_sensor_core_power_up(&ctrl,&soc)==-EINVAL);no_mutation();
 fixture();fail_alloc=1;assert(cam_sensor_core_power_up(&ctrl,&soc)==-ENOMEM);no_mutation();
 /* 7. Shared pinctrl init failure drops shared clock vote and private pinctrl only. */
 fixture();fail_shared_init=1;assert(cam_sensor_core_power_up(&ctrl,&soc)==-EINVAL);clean();assert(!shared_pin_puts&&pin_suspends==1);
 fixture();fail_shared_init=1;pinctrl_absent=1;soc.use_shared_clk=0;assert(cam_sensor_core_power_up(&ctrl,&soc)==-EINVAL);clean();
 /* 8. Unwind that cannot finish is retained and retried by the next power-up. */
 fixture();fail_enable_idx=1;fail_disable_idx=0;assert(cam_sensor_core_power_up(&ctrl,&soc)==-EIO);
 assert(pending()&&regs[0].enabled&&soc.rgltr[0]==&regs[0]&&!regs[1].refs&&clk_on[0]&&regs[2].enabled&&pin.held&&shared_votes==1&&gpio_table==1&&!gpio_level[G_VANA]);
 fail_enable_idx=-1;assert(cam_sensor_core_power_up(&ctrl,&soc)==-EIO&&pending()&&regs[0].enabled);
 fail_disable_idx=-1;post_init=0;assert(!cam_sensor_core_power_up(&ctrl,&soc));assert(!live_alloc);powered();assert(!cam_sensor_util_power_down(&ctrl,&soc));clean();
 /* 8b. Power-down also completes a pending unwind. */
 fixture();fail_clk_on=1;fail_clk_off=0;assert(cam_sensor_core_power_up(&ctrl,&soc)==-ETIMEDOUT);assert(pending()&&clk_on[0]&&regs[2].enabled);
 fail_clk_off=-1;fail_clk_on=-1;assert(!cam_sensor_util_power_down(&ctrl,&soc));clean();assert(clk_off_calls==2);
 /* 8c. Pinctrl suspend failure keeps pinctrl; retry does not repeat completed steps. */
 fixture();fail_get_idx=1;fail_pin_suspend=1;assert(cam_sensor_core_power_up(&ctrl,&soc)==-EPROBE_DEFER);assert(pending()&&pin.held&&!regs[0].refs&&!regs[2].refs&&shared_votes==1);
 fail_pin_suspend=0;fail_get_idx=-1;clk_off_calls=0;post_init=0;assert(!cam_sensor_core_power_up(&ctrl,&soc));assert(!clk_off_calls);powered();assert(!cam_sensor_util_power_down(&ctrl,&soc));clean();
 /* 8d. Shared pinctrl suspend failure retained, then completed. */
 fixture();fail_get_idx=1;fail_shared_suspend=1;assert(cam_sensor_core_power_up(&ctrl,&soc)==-EPROBE_DEFER&&pending()&&shared_pin_held&&!shared_votes);
 fail_shared_suspend=0;assert(!cam_sensor_util_power_down(&ctrl,&soc));clean();assert(shared_pin_puts==1);
 /* 9. Pending unwind survives replaced settings (callers may free them) but not a changed soc. */
 fixture();fail_enable_idx=1;fail_disable_idx=0;assert(cam_sensor_core_power_up(&ctrl,&soc)==-EIO&&pending());
 {static struct cam_sensor_power_setting other[MAX_POWER_CONFIG];memcpy(other,up,sizeof(other));ctrl.power_setting=other;
  soc.num_clk=1;assert(cam_sensor_core_power_up(&ctrl,&soc)==-ESTALE&&pending());soc.num_clk=2;
  fail_disable_idx=-1;fail_enable_idx=-1;post_init=0;assert(!cam_sensor_core_power_up(&ctrl,&soc));assert(other[0].data[0]==&regs[2]);
  assert(!cam_sensor_util_power_down(&ctrl,&soc));assert(!other[0].data[0]&&!other[1].data[0]);ctrl.power_setting=up;clean();}
 /* 10. Out-of-range regulator index and unknown types are tolerated like factory. */
 fixture();soc.num_rgltr=2;soc.rgltr_name[2]=NULL;set(&up[0],SENSOR_VAF,2,0);set(&down[3],SENSOR_VAF,2,0);set(&up[4],SENSOR_SEQ_TYPE_MAX+3,0,0);ctrl.power_setting_size=5;
 set(&down[4],SENSOR_SEQ_TYPE_MAX+3,0,0);ctrl.power_down_setting_size=5;gpio.valid[SENSOR_VAF]=1;gpio.gpio_num[SENSOR_VAF]=7;
 assert(!cam_sensor_core_power_up(&ctrl,&soc));assert(gpio_level[7]&&!clk_on_calls);assert(!cam_sensor_util_power_down(&ctrl,&soc));clean();assert(!gpio_level[7]);
 /* 11. Pending power-down blocks power-up; regulator GPIO goes low before its regulator is disabled. */
 fixture();assert(!cam_sensor_core_power_up(&ctrl,&soc));fail_disable_idx=1;events=0;
 assert(cam_sensor_util_power_down(&ctrl,&soc)==-EIO&&pending());assert(cam_sensor_core_power_up(&ctrl,&soc)==-EBUSY);
 fail_disable_idx=-1;assert(!cam_sensor_util_power_down(&ctrl,&soc));clean();
 fixture();assert(!cam_sensor_core_power_up(&ctrl,&soc));fail_get_idx=-1;
 events=0;assert(!cam_sensor_util_power_down(&ctrl,&soc));assert(gpio_order[G_VIO]&&gpio_order[G_VIO]<disable_order[1]&&gpio_order[G_VANA]<disable_order[0]);clean();
 /* 12. Unwind order: reverse of acquisition, regulator GPIO low before regulator disable. */
 fixture();set(&up[4],SENSOR_CUSTOM_GPIO1,0,1);ctrl.power_setting_size=5;fail_gpio_table=1;gpio.valid[SENSOR_CUSTOM_GPIO1]=1;gpio.gpio_num[SENSOR_CUSTOM_GPIO1]=9;
 up[3].seq_type=SENSOR_VAF;up[3].seq_val=INVALID_VREG;events=0;
 assert(cam_sensor_core_power_up(&ctrl,&soc)==-EINVAL);clean();assert(gpio_order[G_VIO]<disable_order[1]&&disable_order[1]<gpio_order[G_VANA]&&gpio_order[G_VANA]<disable_order[0]&&disable_order[0]<disable_order[2]&&!gpio_order[9]);
 puts("PASS: actual power-up validates before change, returns real errors, unwinds partial MCLK/regulator steps via retained ledger retried by power-up/down; shutdown tolerates unmatched/unknown steps like factory");
 return 0;
}
'''
def main():
    spec=importlib.util.spec_from_file_location('ex',Path(__file__).with_name('test-pico-sensor-mono-hook.py'));ex=importlib.util.module_from_spec(spec);spec.loader.exec_module(ex)
    util=(SOURCE/NAMES[0]).read_text();down=(SOURCE/NAMES[1]).read_text();up=(SOURCE/NAMES[2]).read_text();hdr=(SOURCE/NAMES[3]).read_text();uh=(SOURCE/NAMES[4]).read_text()
    if 'cam_config_mclk_reg' in util or '#include "pico_camera_power_up.inc"' not in util:raise RuntimeError('Power-up unwind not installed')
    pick=lambda pat:re.search(pat,hdr,re.S).group(0)
    header='#define MAX_POWER_CONFIG '+re.search(r'#define MAX_POWER_CONFIG (\d+)',hdr).group(1)+'\n#define INVALID_VREG '+re.search(r'#define INVALID_VREG (\d+)',uh).group(1)+'\n'
    header+=pick(r'enum msm_camera_power_seq_type \{.*?\};')+'\n'+pick(r'enum [a-z_]+ \{[^}]*CAM_VREG_MAX,?\s*\};')+'\n'
    header+=pick(r'struct msm_camera_gpio_num_info \{.*?\};')+'\n'+pick(r'struct cam_sensor_power_setting \{.*?\};')+'\n'
    code=MODEL.replace('/* HEADER */',header)+ex.function(util,'int msm_cam_sensor_handle_reg_gpio(')+'\n'+down+up+MAIN
    out=BASE/'out/phoenix-kernel-recovery/camera-power-up-unwind-tests';out.mkdir(exist_ok=True);(out/'harness.c').write_text(code)
    subprocess.run(['gcc','-std=gnu11','-g','-O1','-Wall','-Wno-unused-function','-fsanitize=address,undefined','-fno-sanitize-recover=all',str(out/'harness.c'),'-o',str(out/'test')],check=True)
    r=subprocess.run([str(out/'test')],capture_output=True,text=True,timeout=30)
    report={'sources':{n:hashlib.sha256((SOURCE/n).read_bytes()).hexdigest() for n in NAMES},'harness_sha256':hashlib.sha256(code.encode()).hexdigest(),'exit_code':r.returncode,'stdout':r.stdout,'stderr':r.stderr,
            'scope':'Actual new power-up, unwind ledger, common shutdown and native GPIO helper; enums/structs from real headers. Regulator/clock/pinctrl/shared-manager/GPIO-table providers, list and mutex modeled; single-threaded host fixture, no hardware.','device_modified':False}
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));raise SystemExit(r.returncode)
if __name__=='__main__':main()
