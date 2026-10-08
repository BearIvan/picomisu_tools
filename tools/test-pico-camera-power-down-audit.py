"""Execute actual shared and actuator power-down bodies; audit expected defects."""
from pathlib import Path
import hashlib,json,subprocess,importlib.util
spec=importlib.util.spec_from_file_location('ex',Path(__file__).with_name('test-pico-sensor-mono-hook.py'));ex=importlib.util.module_from_spec(spec);spec.loader.exec_module(ex)
BASE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro');SOURCE=BASE/'source/phoenix-kernel-recovery'
NAMES=['techpack/camera/drivers/cam_sensor_module/cam_sensor_utils/cam_sensor_util.c','techpack/camera/drivers/cam_sensor_module/cam_actuator/cam_actuator_core.c','drivers/base/dd.c']
MODEL=r'''
#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
#include <stdlib.h>
#include <stdio.h>
#include <errno.h>
#define CAM_INFO(...)
#define CAM_ERR(...)
#define CAM_DBG(...)
#define CAM_SOC_MAX_REGULATOR 8
#define MAX_POWER_CONFIG 12
#define INVALID_VREG 65535
#define GPIOF_OUT_INIT_LOW 0
enum msm_camera_power_seq_type {SENSOR_MCLK,SENSOR_RESET,SENSOR_STANDBY,SENSOR_CUSTOM_GPIO1,SENSOR_CUSTOM_GPIO2,SENSOR_CUSTOM_GPIO3,SENSOR_VANA,SENSOR_VDIG,SENSOR_VIO,SENSOR_VAF,SENSOR_VAF_PWDM,SENSOR_CUSTOM_REG1,SENSOR_CUSTOM_REG2};
struct cam_sensor_power_setting {enum msm_camera_power_seq_type seq_type;uint16_t seq_val;unsigned config_val,delay;void *data[2];};
struct msm_camera_gpio_num_info {int valid[16],gpio_num[16];};
struct regulator {int enabled;};
struct cam_sensor_power_ctrl_t {struct cam_sensor_power_setting *power_setting,*power_down_setting;int power_setting_size,power_down_setting_size;struct msm_camera_gpio_num_info *gpio_num_info;int cam_pinctrl_status;struct {void *pinctrl,*gpio_state_suspend;} pinctrl_info;};
struct cam_hw_soc_info {void *soc_private;int num_rgltr,index,num_clk,use_shared_clk;void *clk[8];const char *clk_name[8];struct regulator *rgltr[8];const char *rgltr_name[8];int rgltr_min_volt[8],rgltr_max_volt[8],rgltr_op_mode[8],rgltr_delay[8];};
struct cam_actuator_soc_private {struct cam_sensor_power_ctrl_t power_info;};
struct cam_actuator_ctrl_t {struct cam_hw_soc_info soc_info;bool pico_core_powered,pico_io_initialized;int io_master_info;};
static struct regulator first,second;
static int fail_reg,fail_pin,fail_gpio,reg_disable,reg_put,pin_put,gpio_release,io_release,clk_disable;
static int cam_soc_util_clk_disable(void *clk,const char *name){clk_disable++;return 0;}
static int cam_config_mclk_reg(struct cam_sensor_power_ctrl_t *c,struct cam_hw_soc_info *s,int idx){return 0;}
static void cam_res_mgr_gpio_set_value(int n,int v){}
static int msm_cam_sensor_handle_reg_gpio(enum msm_camera_power_seq_type t,struct msm_camera_gpio_num_info *g,int v){return fail_gpio?-EIO:0;}
static void msleep(unsigned ms){}
static void usleep_range(unsigned a,unsigned b){}
static int cam_soc_util_regulator_disable(struct regulator *r,const char *name,int a,int b,int c,int d){assert(r);reg_disable++;if(fail_reg&&r==&first)return -EIO;r->enabled=0;return 0;}
static void regulator_put(struct regulator *r){assert(r);reg_put++;}
static int pinctrl_select_state(void *p,void *s){assert(p);return fail_pin?-EIO:0;}
static void devm_pinctrl_put(void *p){assert(p);pin_put++;}
static int cam_res_mgr_shared_clk_config(bool enabled){return 0;}
static int cam_res_mgr_shared_pinctrl_select_state(bool enabled){return 0;}
static void cam_res_mgr_shared_pinctrl_put(void){}
static int cam_sensor_util_request_gpio_table(struct cam_hw_soc_info *s,int enabled){if(!enabled)gpio_release++;return 0;}
static int camera_io_release(int *io){io_release++;return 0;}
'''
MAIN=r'''
int main(void){
 struct msm_camera_gpio_num_info gpio={0};struct cam_sensor_power_setting up[2]={{.seq_type=SENSOR_VAF,.seq_val=0},{.seq_type=SENSOR_VIO,.seq_val=1}},down[2]={{.seq_type=SENSOR_VAF,.seq_val=0},{.seq_type=SENSOR_VIO,.seq_val=1}};
 struct cam_actuator_soc_private soc={.power_info={.power_setting=up,.power_down_setting=down,.power_setting_size=2,.power_down_setting_size=2,.gpio_num_info=&gpio}};
 struct cam_actuator_ctrl_t ctrl={.soc_info={.soc_private=&soc,.num_rgltr=2},.pico_core_powered=true,.pico_io_initialized=true};
 first.enabled=second.enabled=1;ctrl.soc_info.rgltr[0]=&first;ctrl.soc_info.rgltr[1]=&second;
 assert(!cam_actuator_power_down(&ctrl)&&!first.enabled&&!second.enabled&&reg_put==2&&!ctrl.pico_core_powered&&!ctrl.pico_io_initialized);
 reg_disable=reg_put=gpio_release=io_release=0;ctrl.pico_core_powered=ctrl.pico_io_initialized=true;first.enabled=second.enabled=1;ctrl.soc_info.rgltr[0]=&first;ctrl.soc_info.rgltr[1]=&second;fail_reg=1;
 assert(!cam_actuator_power_down(&ctrl));assert(first.enabled&&!second.enabled);assert(!ctrl.soc_info.rgltr[0]&&reg_put==1&&reg_disable==2&&gpio_release==1&&io_release==1&&!ctrl.pico_core_powered&&!ctrl.pico_io_initialized);
 puts("CONFIRMED: failed regulator remains enabled but pointer lost; actual shared power-down returns0, actuator clears core flag and releases IO, GPIO ownership released");
 fail_reg=0;ctrl.pico_core_powered=ctrl.pico_io_initialized=true;soc.power_info.power_down_setting_size=0;soc.power_info.cam_pinctrl_status=1;soc.power_info.pinctrl_info.pinctrl=(void *)1;fail_pin=1;
 assert(!cam_actuator_power_down(&ctrl)&&pin_put==1&&!soc.power_info.cam_pinctrl_status&&!ctrl.pico_core_powered);
 puts("CONFIRMED: failed suspend still drops managed pinctrl and clears status, returns0 and actuator marks core off");
 fail_pin=0;fail_gpio=1;soc.power_info.power_down_setting_size=1;ctrl.pico_core_powered=ctrl.pico_io_initialized=true;first.enabled=1;ctrl.soc_info.rgltr[0]=&first;
 assert(!cam_actuator_power_down(&ctrl)&&!ctrl.pico_core_powered);puts("CONFIRMED: regulator GPIO error hidden by later provider success");
 ctrl.pico_core_powered=true;ctrl.pico_io_initialized=true;soc.power_info.power_down_setting_size=MAX_POWER_CONFIG+1;
 assert(cam_actuator_power_down(&ctrl)==-EINVAL&&ctrl.pico_core_powered&&ctrl.pico_io_initialized);
 return 0;
}
'''
def main():
    shared=(SOURCE/NAMES[0]).read_text();core=(SOURCE/NAMES[1]).read_text();dd=(SOURCE/NAMES[2]).read_text()
    bodies=ex.function(shared,'msm_camera_get_power_settings(struct')+'\n'+ex.function(shared,'int cam_sensor_util_power_down(')+'\n'+ex.function(core,'static int32_t cam_actuator_power_down(')
    code=MODEL+'static struct cam_sensor_power_setting*\n'+bodies+MAIN
    out=BASE/'out/phoenix-kernel-recovery/camera-power-down-audit';out.mkdir(exist_ok=True);(out/'harness.c').write_text(code)
    subprocess.run(['gcc','-std=gnu11','-g','-O1','-fsanitize=address,undefined','-fno-sanitize-recover=all',str(out/'harness.c'),'-o',str(out/'test')],check=True)
    r=subprocess.run([str(out/'test')],capture_output=True,text=True,timeout=30)
    # Native driver core ignores bus/driver remove return before releasing devres.
    start=dd.index('\t\tif (dev->bus && dev->bus->remove)',dd.index('static void __device_release_driver'))
    detach=dd[start:dd.index('\t\tdma_deconfigure(dev);',start)]
    (out/'native-detach-devres.txt').write_text(detach)
    (out/'shared-power-down.c').write_text(ex.function(shared,'int cam_sensor_util_power_down('))
    report={'sources':{n:hashlib.sha256((SOURCE/n).read_bytes()).hexdigest() for n in NAMES},'harness_sha256':hashlib.sha256(code.encode()).hexdigest(),'audit_exit_code':r.returncode,'stdout':r.stdout,'stderr':r.stderr,'scope':'Actual shared power-down/setting lookup and actuator wrapper bodies; lower regulator/pinctrl/GPIO/clock/IO APIs and controller layout modeled. Exit0 confirms current defects, not successful cleanup. Driver-core remove/devres ordering retained as source excerpt, not executed in this harness.','device_modified':False}
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));raise SystemExit(r.returncode)
if __name__=='__main__':main()
