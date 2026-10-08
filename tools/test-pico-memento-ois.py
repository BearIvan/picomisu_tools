"""Actual OIS rollback/ledger/native request deletion with hardware API models."""
from pathlib import Path
import hashlib,importlib.util,json,subprocess
BASE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro');SOURCE=BASE/'source/phoenix-kernel-recovery'
D='techpack/camera/drivers/cam_sensor_module/cam_ois/'
NAMES=[D+n for n in ['pico_memento_ois.inc','pico_memento_ois.h','cam_ois_core.c']]+['techpack/camera/drivers/cam_core/pico_camera_memento.'+e for e in ['c','h']]+['techpack/camera/drivers/cam_sensor_module/cam_sensor_utils/cam_sensor_util.c']
MAIN=r'''
int main(void){
 struct cam_ois_soc_private soc={0};soc.power_info.power_setting=kzalloc(8,0);soc.power_info.power_down_setting=kzalloc(8,0);soc.power_info.power_setting_size=soc.power_info.power_down_setting_size=1;
 struct cam_ois_ctrl_t ois={.ois_mutex={PTHREAD_MUTEX_INITIALIZER},.bridge_intf={41,42,-1},.soc_info={&soc},.cam_ois_state=3};expected=&ois;
 struct i2c_settings_array *requests[3]={&ois.i2c_mode_data,&ois.i2c_calib_data,&ois.i2c_init_data};for(unsigned i=0;i<3;i++){struct i2c_settings_array *r=requests[i];INIT_LIST_HEAD(&r->list_head);struct i2c_settings_list *p=kzalloc(sizeof(*p),0);p->i2c_settings.reg_setting=kzalloc(8,0);list_add(&p->list,&r->list_head);r->is_settings_valid=1;}
 struct pico_memento_ois target;assert(pico_memento_ois_init(NULL,&ois,41,42)==-EINVAL);assert(!pico_memento_ois_init(&target,&ois,41,42));u32 acq[6]={41,42,1,0,0,0},zero[2]={0};
 assert(pico_memento_ois_rollback(&target,0x10009,0x104,zero,8)==-EINVAL);assert(pico_memento_ois_rollback(&target,0x1000d,0x106,acq,8)==-EINVAL);acq[0]=99;assert(pico_memento_ois_rollback(&target,0x1000d,0x106,acq,24)==-EINVAL);acq[0]=41;
 ois.cam_ois_state=CAM_OIS_ACQUIRE;assert(pico_memento_ois_rollback(&target,0x1000d,0x104,zero,8)==-EINVAL && ois.cam_ois_state==CAM_OIS_ACQUIRE);ois.cam_ois_state=CAM_OIS_START;
 struct pico_memento state;pico_memento_init(&state);struct pico_memento_record *ticket=NULL;
 assert(!pico_memento_prepare(0x1000d,VIDIOC_CAM_CONTROL,0x102,&ticket));assert(!pico_memento_commit(&state,&ticket,0x1000d,0x102,acq,24,0));assert(!pico_memento_prepare(0x1000d,VIDIOC_CAM_CONTROL,0x103,&ticket));assert(!pico_memento_commit(&state,&ticket,0x1000d,0x103,NULL,0,0));assert(live==10);
 ois.bridge_intf.link_hdl=7;assert(pico_memento_cleanup(&state,pico_memento_ois_rollback,&target)==-EAGAIN && ois.cam_ois_state==CAM_OIS_CONFIG && !power_calls && list_empty(&state.starts) && live==9);for(unsigned i=0;i<3;i++)assert(requests[i]->is_settings_valid);
 ois.bridge_intf.link_hdl=-1;power_error=-EIO;assert(pico_memento_cleanup(&state,pico_memento_ois_rollback,&target)==-EIO && power_calls==1 && !target.powered_down && !destroy_calls && live==9);
 power_error=0;destroy_error=-EBUSY;assert(pico_memento_cleanup(&state,pico_memento_ois_rollback,&target)==-EBUSY && power_calls==2 && target.powered_down && destroy_calls==1 && !target.complete && ois.bridge_intf.device_hdl==42 && ois.cam_ois_state==CAM_OIS_CONFIG && soc.power_info.power_setting && soc.power_info.power_down_setting && live==3);for(unsigned i=0;i<3;i++)assert(list_empty(&requests[i]->list_head) && !requests[i]->is_settings_valid);
 destroy_error=0;assert(!pico_memento_cleanup(&state,pico_memento_ois_rollback,&target) && destroy_calls==2 && power_calls==2 && target.complete && ois.cam_ois_state==CAM_OIS_INIT && ois.bridge_intf.device_hdl==-1 && ois.bridge_intf.session_hdl==-1 && !soc.power_info.power_setting && !soc.power_info.power_down_setting && !soc.power_info.power_setting_size && !soc.power_info.power_down_setting_size && !live);
 assert(!pico_memento_cleanup(&state,pico_memento_ois_rollback,&target) && destroy_calls==2);
 ois.bridge_intf.session_hdl=41;ois.bridge_intf.device_hdl=42;ois.cam_ois_state=CAM_OIS_ACQUIRE;assert(!pico_memento_ois_init(&target,&ois,41,42));assert(!pico_memento_ois_rollback(&target,0x1000d,0x106,acq,24) && power_calls==2 && destroy_calls==3 && target.complete);assert(!held);
 puts("PASS: actual OIS adapter/ledger/native delete_request, invalid stop preserves state, implicit keys and identity guards, link/power/handle failures, exact mode/calib/init I2C frees, retry skips power-down and cleared lists, final buffers/handles/state cleanup, unconfigured acquire");
}
'''
def load(name):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name(name+'.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
def main():
    common=load('test-pico-camera-hub-registry');ledger=load('test-pico-camera-memento');act=load('test-pico-memento-actuator')
    mocks=act.MOCKS.replace('ACTUATOR','OIS').replace('actuator','ois').replace('cam_act_state','cam_ois_state')
    mocks=mocks.replace('struct {struct i2c_settings_array per_frame[MAX_PER_FRAME_ARRAY];}i2c_data;', 'struct i2c_settings_array i2c_mode_data,i2c_calib_data,i2c_init_data;')
    body=(SOURCE/NAMES[3]).read_text();util=(SOURCE/NAMES[5]).read_text();start=util.index('int32_t delete_request(');end=util.index('int32_t cam_sensor_handle_delay(',start)
    alloc=ledger.MOCKS.replace('static void kfree(void *p) {assert(live);live--;free(p);}','static void kfree(void *p) {if(!p)return;assert(live);live--;free(p);}')
    code=common.HARNESS.split('/* OWNED_SUBDEVICE_MOCKS */')[0]+alloc+mocks+body[body.index('struct pico_memento_record {'):]+util[start:end]+(SOURCE/NAMES[0]).read_text()+MAIN
    out=BASE/'out/phoenix-kernel-recovery/memento-ois-tests';out.mkdir(exist_ok=True);(out/'harness.c').write_text(code)
    subprocess.run(['gcc','-std=gnu11','-g','-O1','-pthread','-fsanitize=address,undefined','-fno-omit-frame-pointer',str(out/'harness.c'),'-o',str(out/'test')],check=True)
    result=subprocess.run([str(out/'test')],capture_output=True,text=True,timeout=30)
    report={'sources':{n:hashlib.sha256((SOURCE/n).read_bytes()).hexdigest() for n in NAMES},'harness_sha256':hashlib.sha256(code.encode()).hexdigest(),'exit_code':result.returncode,'stdout':result.stdout,'stderr':result.stderr,'sanitizers':['AddressSanitizer','UndefinedBehaviorSanitizer'],'scope':'Actual ledger/OIS adapter/native delete_request with allocated I2C and power buffers; power and handle APIs modeled; no real OIS hardware or subdevice close integration','device_modified':False}
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));raise SystemExit(result.returncode)
if __name__=='__main__':main()
