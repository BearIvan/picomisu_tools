"""Actual normal actuator release fragment with driver-owned retry phase."""
from pathlib import Path
import hashlib,json,subprocess,importlib.util
BASE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro');SOURCE=BASE/'source/phoenix-kernel-recovery'
MAIN=r'''
int main(void){
 struct cam_actuator_soc_private soc={0};soc.power_info.power_setting=malloc(8);soc.power_info.power_down_setting=malloc(8);soc.power_info.power_setting_size=soc.power_info.power_down_setting_size=1;struct cam_actuator_ctrl_t ctrl={.actuator_mutex={PTHREAD_MUTEX_INITIALIZER},.bridge_intf={1234,41,7,0},.soc_info={&soc,17},.cam_act_state=CAM_ACTUATOR_CONFIG};expected_owner=&ctrl;struct cam_control cmd={.op_code=CAM_RELEASE_DEV,.handle_type=CAM_HANDLE_USER_POINTER};
 assert(cam_actuator_driver_cmd(&ctrl,&cmd)==-EAGAIN&&!powers&&!destroys&&!ctrl.pico_release_cleanup_pending&&soc.power_info.power_setting);
 ctrl.bridge_intf.link_hdl=-1;ctrl.cam_act_state=CAM_ACTUATOR_START;assert(cam_actuator_driver_cmd(&ctrl,&cmd)==-EINVAL&&!powers&&!destroys);ctrl.cam_act_state=CAM_ACTUATOR_CONFIG;
 power_error=-EIO;assert(cam_actuator_driver_cmd(&ctrl,&cmd)==-EIO&&powers==1&&!destroys&&ctrl.pico_release_cleanup_pending&&!ctrl.pico_release_power_done&&ctrl.cam_act_state==CAM_ACTUATOR_CONFIG&&ctrl.bridge_intf.device_hdl==1234&&soc.power_info.power_setting);
 cmd.op_code=CAM_CONFIG_DEV;assert(cam_actuator_driver_cmd(&ctrl,&cmd)==-EBUSY&&!configs);cmd.op_code=CAM_ACQUIRE_DEV;assert(cam_actuator_driver_cmd(&ctrl,&cmd)==-EINVAL&&!creates);cmd.op_code=CAM_RELEASE_DEV;
 power_error=0;destroy_error=-EBUSY;assert(cam_actuator_driver_cmd(&ctrl,&cmd)==-EBUSY&&powers==2&&destroys==1&&ctrl.pico_release_power_done&&ctrl.cam_act_state==CAM_ACTUATOR_CONFIG&&ctrl.bridge_intf.device_hdl==1234&&!frees);
 assert(cam_actuator_driver_cmd(&ctrl,&cmd)==-EBUSY&&powers==2&&destroys==2&&soc.power_info.power_down_setting);
 destroy_error=0;assert(!cam_actuator_driver_cmd(&ctrl,&cmd)&&powers==2&&destroys==3&&frees==2&&!ctrl.pico_release_cleanup_pending&&!ctrl.pico_release_power_done&&ctrl.cam_act_state==CAM_ACTUATOR_INIT&&ctrl.bridge_intf.device_hdl==-1&&ctrl.bridge_intf.session_hdl==-1&&!soc.power_info.power_setting&&!soc.power_info.power_down_setting&&!soc.power_info.power_setting_size&&!soc.power_info.power_down_setting_size);
 ctrl.bridge_intf.device_hdl=1234;ctrl.bridge_intf.session_hdl=41;ctrl.cam_act_state=CAM_ACTUATOR_CONFIG;destroy_error=-EIO;assert(cam_actuator_driver_cmd(&ctrl,&cmd)==-EIO&&powers==3&&ctrl.pico_release_power_done);struct pico_memento_actuator target;assert(!pico_memento_actuator_init(&target,&ctrl,41,1234));u32 packet[6]={41,1234};destroy_error=0;assert(!pico_memento_actuator_rollback(&target,0x10009,CAM_RELEASE_DEV,packet,24)&&target.complete&&powers==3&&!ctrl.pico_release_cleanup_pending&&!ctrl.pico_release_power_done);
 ctrl.bridge_intf.device_hdl=1234;ctrl.bridge_intf.session_hdl=41;ctrl.cam_act_state=CAM_ACTUATOR_ACQUIRE;destroy_error=-EIO;assert(cam_actuator_driver_cmd(&ctrl,&cmd)==-EIO&&powers==3&&ctrl.cam_act_state==CAM_ACTUATOR_ACQUIRE&&ctrl.bridge_intf.device_hdl==1234);destroy_error=0;assert(!cam_actuator_driver_cmd(&ctrl,&cmd)&&powers==3&&!ctrl.pico_release_cleanup_pending);
 assert(!held);assert(!pthread_mutex_destroy(&ctrl.actuator_mutex.value));puts("PASS: actual native actuator normal release; link/START guards precede power, power failure retains identity/resources, config/acquire gates, failed destroy preserves state/buffers and completed power stage, repeat skips power, final cleanup once, ACQUIRE release skips power");
}
'''
def main():
    spec=importlib.util.spec_from_file_location('acquire',Path(__file__).with_name('test-pico-actuator-acquire-retry.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    adapter='techpack/camera/drivers/cam_sensor_module/cam_actuator/pico_memento_actuator.inc'
    code=m.make_code(MAIN).replace('static void kfree(void *p){assert(!p);}','static unsigned frees;static void kfree(void *p){if(p){frees++;free(p);}}')
    code=code.replace('struct cam_actuator_ctrl_t {','struct i2c_settings_array {int is_settings_valid;};\nstruct cam_actuator_ctrl_t {').replace('unsigned last_flush_req;','unsigned last_flush_req;struct {struct i2c_settings_array per_frame[4];}i2c_data;')
    extra='#define MAX_PER_FRAME_ARRAY 4\nstruct pico_memento_actuator {struct cam_actuator_ctrl_t *actuator;s32 session,device;bool powered_down,complete;};\nstatic int delete_request(struct i2c_settings_array *s){assert(0);return -EINVAL;}\n'+(SOURCE/adapter).read_text()
    code=code.replace(MAIN,extra+MAIN)
    out=BASE/'out/phoenix-kernel-recovery/actuator-release-retry-tests';out.mkdir(exist_ok=True);(out/'harness.c').write_text(code)
    subprocess.run(['gcc','-std=gnu11','-g','-O1','-pthread','-fsanitize=address,undefined','-fno-omit-frame-pointer','-I'+str(SOURCE/'techpack/camera/include/uapi/media'),'-I'+str(SOURCE/'techpack/camera/include/uapi'),str(out/'harness.c'),'-o',str(out/'test')],check=True)
    r=subprocess.run([str(out/'test')],capture_output=True,text=True,timeout=10);report={'sources':{n:hashlib.sha256((SOURCE/n).read_bytes()).hexdigest() for n in [*m.NAMES,adapter]},'harness_sha256':hashlib.sha256(code.encode()).hexdigest(),'exit_code':r.returncode,'stdout':r.stdout,'stderr':r.stderr,'sanitizers':['AddressSanitizer','UndefinedBehaviorSanitizer'],'scope':'Actual native prefix/release/gate and state/UAPI plus memento release on the same controller; allocated power buffers, lower power/destroy APIs modeled, reported-successful stage retained; no individual core/I-O/BOB retry, shutdown/remove/provider/hardware proof','device_modified':False};(out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));raise SystemExit(r.returncode)
if __name__=='__main__':main()
