"""Execute private common shutdown and native actuator wrapper under sanitizers.

Power-up entry/unwind checks moved to test-pico-camera-power-up-unwind.py.
"""
from pathlib import Path
import hashlib,importlib.util,json,subprocess
BASE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro');SOURCE=BASE/'source/phoenix-kernel-recovery';D='techpack/camera/drivers/cam_sensor_module/'
NAMES=[D+'cam_sensor_utils/cam_sensor_util.c',D+'cam_sensor_utils/pico_camera_power_down.inc',D+'cam_actuator/cam_actuator_core.c']
def module(name,file):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name(file));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
EXTRA=r'''
#include <string.h>
#include <stddef.h>
#define CAM_SOC_MAX_CLK 32
typedef unsigned char u8;
#define GFP_KERNEL 0
struct list_head {struct list_head *next,*prev;};
#define LIST_HEAD(name) struct list_head name={&name,&name}
#define DEFINE_MUTEX(name) int name
#define container_of(p,t,m) ((t *)((char *)(p)-offsetof(t,m)))
#define list_for_each_entry(p,h,m) for(p=container_of((h)->next,__typeof__(*p),m);&p->m!=(h);p=container_of(p->m.next,__typeof__(*p),m))
static void list_add_tail(struct list_head *n,struct list_head *h){n->next=h;n->prev=h->prev;h->prev->next=n;h->prev=n;}
static void list_del(struct list_head *n){n->prev->next=n->next;n->next->prev=n->prev;}
static void mutex_lock(int *m){assert(!*m);*m=1;}
static void mutex_unlock(int *m){assert(*m);*m=0;}
static int fail_alloc,live_alloc,fail_load,fail_voltage,fail_shared,fail_release;
static int load_calls,voltage_calls,gpio_calls,shared_votes,shared_put;
static void *kzalloc(size_t s,int flags){if(fail_alloc)return NULL;void *p=calloc(1,s);assert(p);live_alloc++;return p;}
static void kfree(void *p){assert(p);live_alloc--;free(p);}
static int regulator_disable(struct regulator *r){assert(r);reg_disable++;if(fail_reg)return -EIO;assert(r->enabled);r->enabled=0;return 0;}
static int regulator_count_voltages(struct regulator *r){return 1;}
static int regulator_set_load(struct regulator *r,int v){assert(!r->enabled);load_calls++;return fail_load?-EIO:0;}
static int regulator_set_voltage(struct regulator *r,int min,int max){assert(!r->enabled);voltage_calls++;return fail_voltage?-EBUSY:0;}
'''
MAIN=r'''
static struct msm_camera_gpio_num_info gpio;
static struct cam_sensor_power_setting up[3],down[3];
static struct cam_actuator_soc_private private;
static struct cam_actuator_ctrl_t ctrl;
static int expected_gpio_calls,expected_clk_calls,fail_clk;
static void fixture(void){
 assert(!live_alloc);assert(pico_camera_shutdowns.next==&pico_camera_shutdowns);
 expected_gpio_calls=2;expected_clk_calls=1;fail_clk=0;fail_alloc=fail_reg=fail_pin=fail_load=fail_voltage=fail_gpio=fail_shared=fail_release=0;
 reg_disable=reg_put=load_calls=voltage_calls=gpio_calls=clk_disable=pin_put=gpio_release=io_release=shared_votes=shared_put=0;
 up[0]=(struct cam_sensor_power_setting){.seq_type=SENSOR_MCLK};up[1]=(struct cam_sensor_power_setting){.seq_type=SENSOR_VAF,.seq_val=0};up[2]=(struct cam_sensor_power_setting){.seq_type=SENSOR_VIO,.seq_val=1};memcpy(down,up,sizeof(up));
 private=(struct cam_actuator_soc_private){.power_info={.power_setting=up,.power_down_setting=down,.power_setting_size=3,.power_down_setting_size=3,.gpio_num_info=&gpio,.cam_pinctrl_status=1,.pinctrl_info={(void *)1,(void *)2}}};
 ctrl=(struct cam_actuator_ctrl_t){.soc_info={.soc_private=&private,.num_rgltr=2,.num_clk=1,.use_shared_clk=1,.clk={(void *)3},.clk_name={"mclk"},.rgltr={&first,&second},.rgltr_name={"vaf","vio"}},.pico_core_powered=true,.pico_io_initialized=true};first.enabled=second.enabled=1;
}
static void finish(void){assert(!cam_actuator_power_down(&ctrl));assert(!live_alloc&&!ctrl.pico_core_powered&&!ctrl.pico_io_initialized&&io_release==1);assert(!pico_camera_shutdown_find(&private.power_info));assert(!first.enabled&&!second.enabled&&reg_put==2&&clk_disable==expected_clk_calls&&gpio_calls==expected_gpio_calls&&pin_put==1&&shared_votes==1&&shared_put==1);}
int main(void){
 fixture();finish();
 fixture();fail_reg=1;assert(cam_actuator_power_down(&ctrl)==-EIO);assert(ctrl.soc_info.rgltr[0]==&first&&first.enabled&&ctrl.pico_core_powered&&ctrl.pico_io_initialized&&!io_release&&!reg_put&&clk_disable==1&&gpio_calls==1);assert(pico_camera_shutdown_find(&private.power_info));fail_reg=0;finish();
 fixture();fail_load=1;assert(cam_actuator_power_down(&ctrl)==-EIO&&!first.enabled&&ctrl.soc_info.rgltr[0]==&first&&reg_disable==1&&!voltage_calls&&!reg_put);fail_load=0;finish();assert(reg_disable==2&&load_calls==3&&voltage_calls==2);
 fixture();fail_voltage=1;assert(cam_actuator_power_down(&ctrl)==-EBUSY&&reg_disable==1&&load_calls==1&&voltage_calls==1&&!reg_put);fail_voltage=0;finish();assert(reg_disable==2&&load_calls==2&&voltage_calls==3);
 fixture();fail_pin=1;assert(cam_actuator_power_down(&ctrl)==-EIO&&reg_put==2&&!pin_put&&private.power_info.cam_pinctrl_status&&ctrl.pico_core_powered&&!shared_votes);fail_pin=0;finish();assert(reg_disable==2);
 fixture();fail_shared=1;assert(cam_actuator_power_down(&ctrl)==-EIO&&reg_put==2&&pin_put==1&&shared_votes==1&&!shared_put);fail_shared=0;finish();
 /* GPIO table release only fails without a table, so its result no longer blocks completion. */
 fixture();fail_release=1;assert(!cam_actuator_power_down(&ctrl)&&!live_alloc&&!ctrl.pico_core_powered&&gpio_release==1&&shared_put==1&&reg_put==2);fail_release=0;
 fixture();fail_gpio=1;assert(cam_actuator_power_down(&ctrl)==-EIO&&!reg_disable&&!reg_put&&clk_disable==1);fail_gpio=0;expected_gpio_calls=3;finish();assert(gpio_calls==3);
 fixture();fail_reg=1;assert(cam_actuator_power_down(&ctrl)==-EIO);down[1].delay=2;assert(cam_actuator_power_down(&ctrl)==-ESTALE&&reg_disable==1);down[1].delay=0;fail_reg=0;finish();
 fixture();fail_alloc=1;assert(cam_actuator_power_down(&ctrl)==-ENOMEM&&!live_alloc&&!reg_disable&&!gpio_calls&&!clk_disable&&ctrl.pico_core_powered);fail_alloc=0;finish();
 fixture();private.power_info.power_down_setting_size=MAX_POWER_CONFIG+1;assert(cam_actuator_power_down(&ctrl)==-EINVAL&&!live_alloc&&!reg_disable);private.power_info.power_down_setting_size=3;finish();
 fixture();fail_clk=1;assert(cam_actuator_power_down(&ctrl)==-EIO&&!reg_disable&&!gpio_calls);fail_clk=0;expected_clk_calls=2;finish();
 fixture();ctrl.soc_info.rgltr_name[0]="cam_clk";fail_reg=1;assert(cam_actuator_power_down(&ctrl)==-EIO&&clk_disable==1&&!gpio_calls);fail_reg=0;finish();
 fixture();fail_load=1;assert(cam_actuator_power_down(&ctrl)==-EIO);ctrl.soc_info.rgltr[0]=&second;assert(cam_actuator_power_down(&ctrl)==-ESTALE);ctrl.soc_info.rgltr[0]=&first;fail_load=0;finish();
 /* Unknown steps are logged and skipped like factory power-down; the omitted regulator stays as configured. */
 fixture();down[2].seq_type=999;assert(!cam_actuator_power_down(&ctrl)&&!live_alloc&&second.enabled&&reg_put==1&&!ctrl.pico_core_powered);down[2]=up[2];
 puts("PASS: actual common shutdown retains pointers and retries only incomplete regulator/clock/GPIO/pinctrl/shared stages; native actuator preserves power/IO on failure; allocation/size guards, unknown-step skip and ledger cleanup");return 0;
}
'''
def main():
    audit=module('audit','test-pico-camera-power-down-audit.py');ex=module('ex','test-pico-sensor-mono-hook.py')
    model=audit.MODEL.replace('return fail_gpio?-EIO:0;','gpio_calls++;return fail_gpio?-EIO:0;')
    # Declarations must precede provider functions in the inherited mock API.
    model=model.replace('static struct regulator first,second;','static int gpio_calls,shared_votes,shared_put,fail_shared,fail_release;\nstatic struct regulator first,second;')
    model=model.replace('static int cam_soc_util_clk_disable(void *clk,const char *name){clk_disable++;return 0;}','static int fail_clk;\nstatic int cam_soc_util_clk_disable(void *clk,const char *name){clk_disable++;return fail_clk?-EIO:0;}')
    model=model.replace('static int cam_res_mgr_shared_clk_config(bool enabled){return 0;}','static int cam_res_mgr_shared_clk_config(bool enabled){assert(!enabled);shared_votes++;return 0;}')
    model=model.replace('static int cam_res_mgr_shared_pinctrl_select_state(bool enabled){return 0;}','static int cam_res_mgr_shared_pinctrl_select_state(bool enabled){return fail_shared?-EIO:0;}')
    model=model.replace('static void cam_res_mgr_shared_pinctrl_put(void){}','static void cam_res_mgr_shared_pinctrl_put(void){shared_put++;}')
    model=model.replace('if(!enabled)gpio_release++;return 0;','if(!enabled)gpio_release++;return fail_release?-EIO:0;')
    inc=(SOURCE/NAMES[1]).read_text();core=(SOURCE/NAMES[2]).read_text()
    code=model+EXTRA+inc+ex.function(core,'static int32_t cam_actuator_power_down(')+MAIN
    out=BASE/'out/phoenix-kernel-recovery/camera-power-down-phases-tests';out.mkdir(exist_ok=True);(out/'harness.c').write_text(code)
    subprocess.run(['gcc','-std=gnu11','-g','-O1','-fsanitize=address,undefined','-fno-sanitize-recover=all',str(out/'harness.c'),'-o',str(out/'test')],check=True)
    r=subprocess.run([str(out/'test')],capture_output=True,text=True,timeout=30)
    report={'sources':{n:hashlib.sha256((SOURCE/n).read_bytes()).hexdigest() for n in NAMES},'harness_sha256':hashlib.sha256(code.encode()).hexdigest(),'exit_code':r.returncode,'stdout':r.stdout,'stderr':r.stderr,'scope':'Actual new common power-down, private ledger helpers and native actuator wrapper. Regulator/clock/GPIO/pinctrl/IO APIs, layouts, list and mutex modeled. Fully acquired fixture only; partial power-up unwind covered by camera-power-up-unwind tests; other owners, physical remove/concurrency/hardware not validated.','device_modified':False}
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));raise SystemExit(r.returncode)
if __name__=='__main__':main()

