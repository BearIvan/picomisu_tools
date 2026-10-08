"""Actual flash-off, ledger and phased Flash rollback with provider API models."""
from pathlib import Path
import hashlib,importlib.util,json,subprocess
BASE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro');SOURCE=BASE/'source/phoenix-kernel-recovery';D='techpack/camera/drivers/cam_sensor_module/cam_flash/'
NAMES=[D+n for n in ['pico_memento_flash.inc','pico_memento_flash.h','cam_flash_dev.c','cam_flash_core.c','cam_flash_dev.h']]+['techpack/camera/drivers/cam_core/pico_camera_memento.'+e for e in ['c','h']]
MOCKS=r'''
#include <stdint.h>
typedef int s32;
#define CAM_FLASH_STATE_INIT 0
#define CAM_FLASH_STATE_ACQUIRE 1
#define CAM_FLASH_STATE_CONFIG 2
#define CAM_FLASH_STATE_START 3
#define CAM_ERR(...) ((void)0)
#define CAM_DBG(...) ((void)0)
#define CAM_FLASH 0
#define FLUSH_ALL 0
enum led_brightness {LED_SWITCH_OFF=0};
struct cam_flash_ctrl {struct mutex flash_mutex;struct {int session_hdl,device_hdl,link_hdl;}bridge_intf;int flash_state;unsigned last_flush_req;void *switch_trigger;struct {void *gpio_data;}soc_info;struct {int (*flush_req)(struct cam_flash_ctrl *,int,uint64_t);int (*power_ops)(struct cam_flash_ctrl *,bool);}func_tbl;};
struct pico_memento_flash {struct cam_flash_ctrl *flash;s32 session,device;bool off_done,flushed,powered_down,complete;};
static struct cam_flash_ctrl *expected;static int flush_error,power_error,destroy_error;static unsigned led_calls,gpio_calls,gpios_calls,flush_calls,power_calls,destroy_calls;
static void cam_res_mgr_led_trigger_event(void *trigger,enum led_brightness b){assert(held==1 && trigger==expected->switch_trigger && b==0);led_calls++;}
static void cam_flash_set_gpio(struct cam_flash_ctrl *f,bool on){assert(held==1 && f==expected && !on);gpio_calls++;}
static void cam_flash_set_gpios(struct cam_flash_ctrl *f,bool on){assert(held==1 && f==expected && !on);gpios_calls++;}
static int flush(struct cam_flash_ctrl *f,int type,uint64_t req){assert(held==1 && f==expected && type==FLUSH_ALL && !req);flush_calls++;return flush_error;}
static int power(struct cam_flash_ctrl *f,bool on){assert(held==1 && f==expected && !on);power_calls++;return power_error;}
static int cam_destroy_device_hdl(int h){assert(held==1 && h==42 && expected->bridge_intf.device_hdl==42);destroy_calls++;return destroy_error;}
'''
MAIN=r'''
int main(void){
 struct cam_flash_ctrl flash={.flash_mutex={PTHREAD_MUTEX_INITIALIZER},.bridge_intf={41,42,-1},.flash_state=3,.last_flush_req=55,.switch_trigger=(void *)1,.soc_info={(void *)2},.func_tbl={flush,power}};expected=&flash;struct pico_memento_flash target;
 assert(pico_memento_flash_init(NULL,&flash,41,42)==-EINVAL);assert(!pico_memento_flash_init(&target,&flash,41,42));u32 acq[6]={41,42,1,0,0,0},zero[2]={0};assert(pico_memento_flash_rollback(&target,0x1000c,0x106,acq,24)==-EINVAL);assert(pico_memento_flash_rollback(&target,0x1000b,0x106,acq,8)==-EINVAL);
 struct pico_memento state;pico_memento_init(&state);struct pico_memento_record *ticket=NULL;assert(!pico_memento_prepare(0x1000b,VIDIOC_CAM_CONTROL,0x102,&ticket));assert(!pico_memento_commit(&state,&ticket,0x1000b,0x102,acq,24,0));assert(!pico_memento_prepare(0x1000b,VIDIOC_CAM_CONTROL,0x103,&ticket));assert(!pico_memento_commit(&state,&ticket,0x1000b,0x103,NULL,0,0));
 flash.func_tbl.flush_req=NULL;assert(pico_memento_cleanup(&state,pico_memento_flash_rollback,&target)==-EOPNOTSUPP && target.off_done && led_calls==1 && gpio_calls==1 && gpios_calls==1 && flash.flash_state==3 && live==2);flash.func_tbl.flush_req=flush;
 flush_error=-EIO;assert(pico_memento_cleanup(&state,pico_memento_flash_rollback,&target)==-EIO && flush_calls==1 && led_calls==1 && !target.flushed && live==2);
 flush_error=0;flash.bridge_intf.link_hdl=7;assert(pico_memento_cleanup(&state,pico_memento_flash_rollback,&target)==-EAGAIN && target.flushed && flush_calls==2 && flash.flash_state==1 && !flash.last_flush_req && list_empty(&state.starts) && live==1);
 flash.bridge_intf.link_hdl=-1;flash.func_tbl.power_ops=NULL;assert(pico_memento_cleanup(&state,pico_memento_flash_rollback,&target)==-EOPNOTSUPP && !power_calls);flash.func_tbl.power_ops=power;
 power_error=-EIO;assert(pico_memento_cleanup(&state,pico_memento_flash_rollback,&target)==-EIO && power_calls==1 && !target.powered_down && !destroy_calls);
 power_error=0;destroy_error=-EBUSY;assert(pico_memento_cleanup(&state,pico_memento_flash_rollback,&target)==-EBUSY && power_calls==2 && target.powered_down && destroy_calls==1 && flash.bridge_intf.device_hdl==42 && !target.complete && live==1);
 destroy_error=0;assert(!pico_memento_cleanup(&state,pico_memento_flash_rollback,&target) && power_calls==2 && destroy_calls==2 && target.complete && flash.flash_state==0 && flash.bridge_intf.device_hdl==-1 && !live && led_calls==1 && flush_calls==2);
 flash.bridge_intf.session_hdl=41;flash.bridge_intf.device_hdl=42;flash.flash_state=3;assert(!pico_memento_flash_init(&target,&flash,41,42));assert(!pico_memento_flash_rollback(&target,0x1000b,0x106,acq,24) && led_calls==2 && flush_calls==3 && power_calls==3 && destroy_calls==3 && target.complete && flash.flash_state==0);assert(!held);
 puts("PASS: actual Flash adapter/ledger/native flash_off; LED/GPIO off once across flush retry; missing providers/link/flush/power/handle errors retained; phased retry skips completed stages; release handles config-induced START without journal start; final cleanup");
}
'''
def load(name):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name(name+'.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
def main():
    common=load('test-pico-camera-hub-registry');ledger=load('test-pico-camera-memento');body=(SOURCE/NAMES[5]).read_text();core=(SOURCE/NAMES[3]).read_text();off=core[core.index('int cam_flash_off('):core.index('static int cam_flash_low(')]
    code=common.HARNESS.split('/* OWNED_SUBDEVICE_MOCKS */')[0]+ledger.MOCKS+MOCKS+body[body.index('struct pico_memento_record {'):]+off+(SOURCE/NAMES[0]).read_text()+MAIN
    out=BASE/'out/phoenix-kernel-recovery/memento-flash-tests';out.mkdir(exist_ok=True);(out/'harness.c').write_text(code)
    subprocess.run(['gcc','-std=gnu11','-g','-O1','-pthread','-fsanitize=address,undefined','-fno-omit-frame-pointer',str(out/'harness.c'),'-o',str(out/'test')],check=True)
    result=subprocess.run([str(out/'test')],capture_output=True,text=True,timeout=30)
    report={'sources':{n:hashlib.sha256((SOURCE/n).read_bytes()).hexdigest() for n in NAMES},'harness_sha256':hashlib.sha256(code.encode()).hexdigest(),'exit_code':result.returncode,'stdout':result.stdout,'stderr':result.stderr,'sanitizers':['AddressSanitizer','UndefinedBehaviorSanitizer'],'scope':'Actual ledger/Flash adapter/native flash_off; modeled LED/GPIO/flush/power/handle providers; no live hardware or subdevice close integration','device_modified':False}
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));raise SystemExit(result.returncode)
if __name__=='__main__':main()
