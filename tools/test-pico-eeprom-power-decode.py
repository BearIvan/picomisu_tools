"""Actual generic power decoder/validator and EEPROM staged merge adapter."""
from pathlib import Path
import hashlib,json,re,subprocess,importlib.util
BASE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro');SOURCE=BASE/'source/phoenix-kernel-recovery';D='techpack/camera/drivers/cam_sensor_module/'
NAMES=[D+'cam_eeprom/pico_eeprom_power_decode.inc',D+'cam_eeprom/cam_eeprom_core.c',D+'cam_sensor_utils/cam_sensor_util.c',D+'cam_sensor_utils/cam_sensor_cmn_header.h','techpack/camera/include/uapi/media/cam_sensor.h']
NAMES += ['techpack/camera/include/uapi/media/cam_defs.h']
MOCKS=r'''
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include <string.h>
#include <stdio.h>
#include <stdlib.h>
#include <assert.h>
#include <errno.h>
#include <cam_sensor.h>
#define CAM_ERR(...) ((void)0)
#define CAM_DBG(...) ((void)0)
#define CAM_WARN(...) ((void)0)
#define GFP_KERNEL 0
#define U16_MAX UINT16_MAX
static unsigned live,allocations;static int fail_alloc;
static void *kcalloc(size_t n,size_t bytes,int flags){allocations++;if(fail_alloc&&!--fail_alloc)return NULL;void *p=calloc(n,bytes);if(p)live++;return p;}
static void *kzalloc(size_t bytes,int flags){return kcalloc(1,bytes,flags);}
static void kfree(void *p){if(p){assert(live);live--;free(p);}}
'''
MAIN=r'''
static union {max_align_t align;unsigned char bytes[256];} window;
static unsigned command(unsigned at,unsigned type,unsigned count,unsigned value){struct cam_cmd_power *p=(void *)(window.bytes+at);p->cmd_type=type;p->count=count;for(unsigned i=0;i<count;i++){p->power_settings[i].power_seq_type=SENSOR_VANA;p->power_settings[i].config_val_low=value+i;}return sizeof(*p)+(count?count-1:0)*sizeof(struct cam_power_settings);}
int main(void){
 struct cam_sensor_power_ctrl_t power={0};unsigned bytes=command(0,CAMERA_SENSOR_CMD_TYPE_PWR_UP,1,11);power.power_setting=kcalloc(1,sizeof(*power.power_setting),0);power.power_setting_size=1;power.power_setting[0].config_val=777;
 assert(!pico_eeprom_update_power_settings(window.bytes,bytes,&power,bytes,false)&&power.power_setting_size==1&&power.power_setting[0].config_val==11&&!power.power_down_setting_size&&live==1);
 bytes=command(0,CAMERA_SENSOR_CMD_TYPE_PWR_DOWN,1,22);assert(!pico_eeprom_update_power_settings(window.bytes,bytes,&power,bytes,true)&&power.power_setting_size==1&&power.power_setting[0].config_val==11&&power.power_down_setting_size==1&&power.power_down_setting[0].config_val==22&&live==2);
 bytes=command(0,CAMERA_SENSOR_CMD_TYPE_PWR_UP,1,33);assert(!pico_eeprom_update_power_settings(window.bytes,bytes,&power,bytes,true)&&power.power_setting_size==2&&power.power_setting[1].config_val==33&&power.power_down_setting[0].config_val==22&&live==2);
 bytes=command(0,CAMERA_SENSOR_CMD_TYPE_PWR_UP,1,50);struct cam_cmd_unconditional_wait *wait=(void *)(window.bytes+bytes);wait->cmd_type=CAMERA_SENSOR_CMD_TYPE_WAIT;wait->op_code=CAMERA_SENSOR_WAIT_OP_SW_UCND;wait->delay=9;bytes+=sizeof(*wait);bytes+=command(bytes,CAMERA_SENSOR_CMD_TYPE_PWR_DOWN,1,60);
 assert(!pico_eeprom_update_power_settings(window.bytes,bytes,&power,bytes,false)&&power.power_setting_size==1&&power.power_setting[0].config_val==50&&power.power_setting[0].delay==9&&power.power_down_setting_size==1&&power.power_down_setting[0].config_val==60&&live==2);
 struct cam_sensor_power_setting *old_up=power.power_setting,*old_down=power.power_down_setting;
 bytes=command(0,CAMERA_SENSOR_CMD_TYPE_PWR_DOWN,1,70);for(unsigned fail=1;fail<=4;fail++){fail_alloc=fail;assert(pico_eeprom_update_power_settings(window.bytes,bytes,&power,bytes,true)==-ENOMEM&&power.power_setting==old_up&&power.power_down_setting==old_down&&power.power_down_setting[0].config_val==60&&live==2);}fail_alloc=0;
 unsigned before=allocations;bytes=command(0,CAMERA_SENSOR_CMD_TYPE_PWR_UP,2,80);assert(pico_eeprom_update_power_settings(window.bytes,sizeof(struct cam_cmd_power),&power,sizeof(struct cam_cmd_power),true)==-EINVAL&&allocations==before&&power.power_setting==old_up);
 bytes=command(0,CAMERA_SENSOR_CMD_TYPE_PWR_UP,MAX_POWER_CONFIG,90);assert(pico_eeprom_update_power_settings(window.bytes,bytes,&power,bytes,true)==-EINVAL&&power.power_setting==old_up&&live==2);
 bytes=command(0,255,1,0);assert(pico_eeprom_update_power_settings(window.bytes,bytes,&power,bytes,true)==-EINVAL&&live==2);
 assert(pico_eeprom_update_power_settings(window.bytes,bytes,NULL,bytes,true)==-EINVAL&&live==2);kfree(power.power_setting);kfree(power.power_down_setting);assert(!live);
 puts("PASS: actual generic power validator/decoder + EEPROM adapter; first block replaces, split UP/DOWN and repeated descriptors merge in order, delays preserved, truncated counted payload rejected before decoder, staged/merged allocation failures retain old arrays, aggregate cap rollback, zero leaks");
}
'''
def main():
    spec=importlib.util.spec_from_file_location('extract',Path(__file__).with_name('test-pico-sensor-mono-hook.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);util=(SOURCE/NAMES[2]).read_text();cmn=(SOURCE/NAMES[3]).read_text()
    enums='\n'.join(re.search(r'enum '+n+r' \{.*?\n\};',cmn,re.S).group(0) for n in ['camera_sensor_cmd_type','camera_sensor_wait_op_code','msm_camera_power_seq_type'])
    settings=re.search(r'struct cam_sensor_power_setting \{.*?\n\};',cmn,re.S).group(0);common=re.search(r'struct common_header \{.*?\n\};',cmn,re.S).group(0);limit=next(line for line in cmn.splitlines() if line.startswith('#define MAX_POWER_CONFIG '))
    ctrl='struct cam_sensor_power_ctrl_t {struct cam_sensor_power_setting *power_setting;uint16_t power_setting_size;struct cam_sensor_power_setting *power_down_setting;uint16_t power_down_setting_size;};\n'
    code=MOCKS+limit+'\n'+enums+settings+common+ctrl+m.function(util,'static int32_t cam_sensor_validate(')+m.function(util,'int32_t cam_sensor_update_power_settings(')+(SOURCE/NAMES[0]).read_text()+MAIN
    out=BASE/'out/phoenix-kernel-recovery/eeprom-power-decode-tests';out.mkdir(exist_ok=True);(out/'harness.c').write_text(code)
    subprocess.run(['gcc','-std=gnu11','-g','-O1','-fsanitize=address,undefined','-fno-omit-frame-pointer','-I'+str(SOURCE/'techpack/camera/include/uapi/media'),'-I'+str(SOURCE/'techpack/camera/include/uapi'),str(out/'harness.c'),'-o',str(out/'test')],check=True)
    r=subprocess.run([str(out/'test')],capture_output=True,text=True,timeout=10);report={'sources':{n:hashlib.sha256((SOURCE/n).read_bytes()).hexdigest() for n in NAMES},'harness_sha256':hashlib.sha256(code.encode()).hexdigest(),'exit_code':r.returncode,'stdout':r.stdout,'stderr':r.stderr,'sanitizers':['AddressSanitizer','UndefinedBehaviorSanitizer'],'scope':'Actual generic validator/decoder and EEPROM staged adapter, native settings/common-header/enums/limit, real power UAPI; allocator and power-control shape modeled; parser integration tested separately, no GPIO/regulator/power-provider/hardware proof','device_modified':False};(out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));raise SystemExit(r.returncode)
if __name__=='__main__':main()
