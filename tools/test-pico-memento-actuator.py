"""Actual ledger, actuator rollback and native delete_request with hardware models."""
from pathlib import Path
import hashlib,importlib.util,json,subprocess
BASE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro');SOURCE=BASE/'source/phoenix-kernel-recovery'
D='techpack/camera/drivers/cam_sensor_module/cam_actuator/'
NAMES=[D+n for n in ['pico_memento_actuator.inc','pico_memento_actuator.h','cam_actuator_core.c']]+['techpack/camera/drivers/cam_core/pico_camera_memento.'+ext for ext in ['c','h']]+['techpack/camera/drivers/cam_sensor_module/cam_sensor_utils/cam_sensor_util.c']
NAMES += [D+'pico_actuator_acquire_unwind.'+e for e in ['inc','h']]
MOCKS=r'''
#include <stdint.h>
typedef int s32;
#define CAM_ACTUATOR_INIT 0
#define CAM_ACTUATOR_ACQUIRE 1
#define CAM_ACTUATOR_CONFIG 2
#define CAM_ACTUATOR_START 3
#define MAX_PER_FRAME_ARRAY 4
#define CAM_ERR(...) ((void)0)
#define CAM_SENSOR 0
#define list_for_each_entry_safe(p,n,h,m) for(struct list_head *it=(h)->next,*next=it->next;it!=(h) && ((p)=container_of(it,__typeof__(*(p)),m),(n)=container_of(next,__typeof__(*(n)),m),1);it=next,next=it->next)
#define vfree kfree
struct i2c_settings_list {struct list_head list;struct {void *reg_setting;}i2c_settings;};
struct i2c_settings_array {struct list_head list_head;int is_settings_valid;int64_t request_id;};
struct cam_sensor_power_ctrl_t {void *power_setting,*power_down_setting;unsigned power_setting_size,power_down_setting_size;};
struct cam_actuator_soc_private {struct cam_sensor_power_ctrl_t power_info;};
struct cam_actuator_ctrl_t {struct mutex actuator_mutex;struct {int session_hdl,device_hdl,link_hdl;}bridge_intf;struct {struct i2c_settings_array per_frame[MAX_PER_FRAME_ARRAY];}i2c_data;struct {void *soc_private;}soc_info;int cam_act_state;unsigned last_flush_req;bool pico_acquire_cleanup_pending,pico_release_cleanup_pending,pico_release_power_done,pico_core_powered,pico_io_initialized;};
struct pico_memento_actuator {struct cam_actuator_ctrl_t *actuator;s32 session,device;bool powered_down,complete;};
static struct cam_actuator_ctrl_t *expected;static int power_error,destroy_error;static unsigned power_calls,destroy_calls;
static int cam_actuator_power_down(struct cam_actuator_ctrl_t *a){assert(held==1 && a==expected);power_calls++;return power_error;}
static int cam_destroy_device_hdl(int h){assert(held==1 && h==42 && expected->bridge_intf.device_hdl==42);destroy_calls++;return destroy_error;}
'''
MAIN=r'''
int main(void){
 struct cam_actuator_soc_private soc={0};soc.power_info.power_setting=kzalloc(8,0);soc.power_info.power_down_setting=kzalloc(8,0);soc.power_info.power_setting_size=soc.power_info.power_down_setting_size=1;
 struct cam_actuator_ctrl_t actuator={.actuator_mutex={PTHREAD_MUTEX_INITIALIZER},.bridge_intf={41,42,-1},.soc_info={&soc},.cam_act_state=3,.last_flush_req=55};expected=&actuator;
 for(unsigned i=0;i<MAX_PER_FRAME_ARRAY;i++){struct i2c_settings_array *r=&actuator.i2c_data.per_frame[i];INIT_LIST_HEAD(&r->list_head);if(i%2){struct i2c_settings_list *p=kzalloc(sizeof(*p),0);p->i2c_settings.reg_setting=kzalloc(8,0);list_add(&p->list,&r->list_head);r->is_settings_valid=1;}}
 assert(delete_request(NULL)==-EINVAL);
 struct pico_memento_actuator target;assert(pico_memento_actuator_init(NULL,&actuator,41,42)==-EINVAL);assert(!pico_memento_actuator_init(&target,&actuator,41,42));u32 acq[6]={41,42,1,0,0,0},zero[2]={0};
 assert(pico_memento_actuator_rollback(&target,0x10001,0x104,zero,8)==-EINVAL);assert(pico_memento_actuator_rollback(&target,0x10009,0x106,acq,8)==-EINVAL);acq[0]=99;assert(pico_memento_actuator_rollback(&target,0x10009,0x106,acq,24)==-EINVAL);acq[0]=41;
 struct pico_memento state;pico_memento_init(&state);struct pico_memento_record *ticket=NULL;
 assert(!pico_memento_prepare(0x10009,VIDIOC_CAM_CONTROL,0x102,&ticket));assert(!pico_memento_commit(&state,&ticket,0x10009,0x102,acq,24,0));assert(!pico_memento_prepare(0x10009,VIDIOC_CAM_CONTROL,0x103,&ticket));assert(!pico_memento_commit(&state,&ticket,0x10009,0x103,NULL,0,0));assert(live==8);
 actuator.bridge_intf.link_hdl=7;assert(pico_memento_cleanup(&state,pico_memento_actuator_rollback,&target)==-EAGAIN && actuator.cam_act_state==2 && !power_calls && list_empty(&state.starts) && live==3);for(unsigned i=0;i<4;i++)assert(list_empty(&actuator.i2c_data.per_frame[i].list_head) && !actuator.i2c_data.per_frame[i].is_settings_valid);
 actuator.bridge_intf.link_hdl=-1;power_error=-EIO;assert(pico_memento_cleanup(&state,pico_memento_actuator_rollback,&target)==-EIO && power_calls==1 && !target.powered_down && !destroy_calls && live==3);
 power_error=0;destroy_error=-EBUSY;assert(pico_memento_cleanup(&state,pico_memento_actuator_rollback,&target)==-EBUSY && power_calls==2 && target.powered_down && destroy_calls==1 && !target.complete && actuator.bridge_intf.device_hdl==42 && actuator.cam_act_state==2 && soc.power_info.power_setting && soc.power_info.power_down_setting && live==3);
 destroy_error=0;assert(!pico_memento_cleanup(&state,pico_memento_actuator_rollback,&target) && destroy_calls==2 && power_calls==2 && target.complete && actuator.cam_act_state==0 && actuator.bridge_intf.device_hdl==-1 && actuator.bridge_intf.session_hdl==-1 && !soc.power_info.power_setting && !soc.power_info.power_down_setting && !soc.power_info.power_setting_size && !soc.power_info.power_down_setting_size && !live);
 assert(!pico_memento_cleanup(&state,pico_memento_actuator_rollback,&target) && destroy_calls==2);
 actuator.bridge_intf.session_hdl=41;actuator.bridge_intf.device_hdl=42;actuator.cam_act_state=CAM_ACTUATOR_ACQUIRE;assert(!pico_memento_actuator_init(&target,&actuator,41,42));assert(!pico_memento_actuator_rollback(&target,0x10009,0x106,acq,24) && power_calls==2 && destroy_calls==3 && target.complete);assert(!held);
 actuator.bridge_intf.session_hdl=41;actuator.bridge_intf.device_hdl=42;actuator.cam_act_state=CAM_ACTUATOR_INIT;actuator.pico_acquire_cleanup_pending=true;assert(!pico_memento_actuator_init(&target,&actuator,41,42));destroy_error=-EIO;assert(pico_memento_actuator_rollback(&target,0x10009,0x106,acq,24)==-EIO&&!target.complete&&actuator.pico_acquire_cleanup_pending&&actuator.bridge_intf.device_hdl==42&&power_calls==2);destroy_error=0;assert(!pico_memento_actuator_rollback(&target,0x10009,0x106,acq,24)&&target.complete&&!actuator.pico_acquire_cleanup_pending&&actuator.bridge_intf.device_hdl==-1&&power_calls==2);
 actuator.bridge_intf.session_hdl=41;actuator.bridge_intf.device_hdl=42;actuator.cam_act_state=CAM_ACTUATOR_CONFIG;actuator.pico_release_cleanup_pending=true;actuator.pico_release_power_done=true;assert(!pico_memento_actuator_init(&target,&actuator,41,42));destroy_error=-EIO;assert(pico_memento_actuator_rollback(&target,0x10009,0x106,acq,24)==-EIO&&power_calls==2&&actuator.pico_release_power_done&&!target.complete);destroy_error=0;assert(!pico_memento_actuator_rollback(&target,0x10009,0x106,acq,24)&&power_calls==2&&target.complete&&!actuator.pico_release_cleanup_pending&&!actuator.pico_release_power_done);
 puts("PASS: actual actuator adapter/ledger/native delete_request; implicit stop and exact I2C frees; link/power/handle failure retention; retry skips completed power-down; final power-buffer/handle/state cleanup; unconfigured acquire skips power-down");
}
'''
def load(name):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name(name+'.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
def main():
    common=load('test-pico-camera-hub-registry');ledger=load('test-pico-camera-memento');body=(SOURCE/NAMES[3]).read_text();util=(SOURCE/NAMES[5]).read_text();start=util.index('int32_t delete_request(');end=util.index('int32_t cam_sensor_handle_delay(',start)
    allocation_mocks=ledger.MOCKS.replace('static void kfree(void *p) {assert(live);live--;free(p);}', 'static void kfree(void *p) {if(!p)return;assert(live);live--;free(p);}')
    code=common.HARNESS.split('/* OWNED_SUBDEVICE_MOCKS */')[0]+allocation_mocks+MOCKS+body[body.index('struct pico_memento_record {'):]+util[start:end]+(SOURCE/NAMES[6]).read_text()+'static void pico_actuator_clear_requests_locked(struct cam_actuator_ctrl_t *c){assert(held==1);}\n'+(SOURCE/NAMES[0]).read_text()+MAIN
    out=BASE/'out/phoenix-kernel-recovery/memento-actuator-tests';out.mkdir(exist_ok=True);(out/'harness.c').write_text(code)
    subprocess.run(['gcc','-std=gnu11','-g','-O1','-pthread','-fsanitize=address,undefined','-fno-omit-frame-pointer',str(out/'harness.c'),'-o',str(out/'test')],check=True)
    result=subprocess.run([str(out/'test')],capture_output=True,text=True,timeout=30)
    report={'sources':{n:hashlib.sha256((SOURCE/n).read_bytes()).hexdigest() for n in NAMES},'harness_sha256':hashlib.sha256(code.encode()).hexdigest(),'exit_code':result.returncode,'stdout':result.stdout,'stderr':result.stderr,'sanitizers':['AddressSanitizer','UndefinedBehaviorSanitizer'],'scope':'Actual ledger/actuator adapter/native delete_request with allocated I2C/power buffers and modeled power/handle APIs; no real actuator hardware or subdevice close integration','device_modified':False}
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));raise SystemExit(result.returncode)
if __name__=='__main__':main()
