"""Actual actuator power helpers and release/shutdown/memento phase integration."""
from pathlib import Path
import hashlib,json,subprocess,importlib.util
BASE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro');SOURCE=BASE/'source/phoenix-kernel-recovery';D='techpack/camera/drivers/cam_sensor_module/cam_actuator/'
LOWER=r'''
#define CAM_INFO(...) ((void)0)
static unsigned core_ups,core_downs,io_inits,io_releases,frees;
static int fill_error,core_up_error,core_down_error,io_init_error,io_release_error;
static void kfree(void *p){if(p){frees++;free(p);}}
static int cam_actuator_construct_default_power_setting(struct cam_sensor_power_ctrl_t *p){assert(0);return -EINVAL;}
static int msm_camera_fill_vreg_params(struct cam_hw_soc_info *soc,void *settings,unsigned n){return fill_error;}
static int cam_sensor_core_power_up(struct cam_sensor_power_ctrl_t *p,struct cam_hw_soc_info *soc){assert(held==1);core_ups++;return core_up_error;}
static int cam_sensor_util_power_down(struct cam_sensor_power_ctrl_t *p,struct cam_hw_soc_info *soc){assert(held==1);core_downs++;return core_down_error;}
static int camera_io_init(struct camera_io_master *io){assert(held==1);io_inits++;return io_init_error;}
static int camera_io_release(struct camera_io_master *io){assert(held==1);io_releases++;return io_release_error;}
'''
MAIN=r'''
static int power_up(struct cam_actuator_ctrl_t *ctrl){mutex_lock(&ctrl->actuator_mutex);int rc=cam_actuator_power_up(ctrl);mutex_unlock(&ctrl->actuator_mutex);return rc;}
static void settings(struct cam_sensor_power_ctrl_t *p){p->power_setting=malloc(8);p->power_down_setting=malloc(8);p->power_setting_size=p->power_down_setting_size=1;assert(p->power_setting&&p->power_down_setting);}
int main(void){
 struct cam_actuator_soc_private soc={0};settings(&soc.power_info);struct cam_actuator_ctrl_t ctrl={.actuator_mutex={PTHREAD_MUTEX_INITIALIZER},.bridge_intf={1234,41,-1,0},.soc_info={&soc,17},.cam_act_state=CAM_ACTUATOR_ACQUIRE};expected_owner=&ctrl;struct cam_control cmd={.op_code=CAM_RELEASE_DEV,.handle_type=CAM_HANDLE_USER_POINTER};
 fill_error=-ERANGE;assert(power_up(&ctrl)==-ERANGE&&!core_ups&&!ctrl.pico_core_powered);fill_error=0;core_up_error=-EIO;assert(power_up(&ctrl)==-EIO&&core_ups==1&&!io_inits&&!ctrl.pico_core_powered);core_up_error=0;
 io_init_error=-ENXIO;assert(power_up(&ctrl)==-ENXIO&&core_downs==1&&!ctrl.pico_core_powered&&!ctrl.pico_io_initialized&&!ctrl.pico_release_cleanup_pending);
 core_down_error=-EBUSY;assert(power_up(&ctrl)==-ENXIO&&core_downs==2&&ctrl.pico_core_powered&&!ctrl.pico_io_initialized&&ctrl.pico_release_cleanup_pending);unsigned before=core_ups;assert(power_up(&ctrl)==-EBUSY&&core_ups==before);cmd.op_code=CAM_CONFIG_DEV;assert(cam_actuator_driver_cmd(&ctrl,&cmd)==-EBUSY&&!configs);cmd.op_code=CAM_RELEASE_DEV;
 assert(cam_actuator_driver_cmd(&ctrl,&cmd)==-EBUSY&&core_downs==3&&!destroys&&ctrl.pico_core_powered&&soc.power_info.power_setting);core_down_error=0;destroy_error=-EIO;assert(cam_actuator_driver_cmd(&ctrl,&cmd)==-EIO&&core_downs==4&&!ctrl.pico_core_powered&&ctrl.pico_release_power_done&&ctrl.bridge_intf.device_hdl==1234&&!frees);assert(cam_actuator_driver_cmd(&ctrl,&cmd)==-EIO&&core_downs==4);destroy_error=0;assert(!cam_actuator_driver_cmd(&ctrl,&cmd)&&frees==2&&!ctrl.pico_release_cleanup_pending&&!ctrl.pico_release_power_done&&ctrl.cam_act_state==CAM_ACTUATOR_INIT);
 settings(&soc.power_info);ctrl.bridge_intf.device_hdl=1234;ctrl.bridge_intf.session_hdl=41;ctrl.cam_act_state=CAM_ACTUATOR_ACQUIRE;io_init_error=0;assert(!power_up(&ctrl)&&ctrl.pico_core_powered&&ctrl.pico_io_initialized);ctrl.cam_act_state=CAM_ACTUATOR_CONFIG;io_release_error=-EAGAIN;assert(cam_actuator_driver_cmd(&ctrl,&cmd)==-EAGAIN&&!ctrl.pico_core_powered&&ctrl.pico_io_initialized&&!ctrl.pico_release_power_done&&frees==2);before=core_downs;assert(cam_actuator_driver_cmd(&ctrl,&cmd)==-EAGAIN&&core_downs==before&&io_releases==2);
 struct pico_memento_actuator target;assert(!pico_memento_actuator_init(&target,&ctrl,41,1234));u32 packet[6]={41,1234};io_release_error=0;destroy_error=-EIO;assert(pico_memento_actuator_rollback(&target,0x10009,CAM_RELEASE_DEV,packet,24)==-EIO&&core_downs==before&&io_releases==3&&!ctrl.pico_io_initialized&&ctrl.pico_release_power_done&&!target.complete);destroy_error=0;mutex_lock(&ctrl.actuator_mutex);cam_actuator_shutdown(&ctrl);mutex_unlock(&ctrl.actuator_mutex);assert(core_downs==before&&io_releases==3&&frees==4&&ctrl.cam_act_state==CAM_ACTUATOR_INIT&&!ctrl.pico_release_cleanup_pending&&!ctrl.pico_release_power_done);
 assert(!held);assert(!pthread_mutex_destroy(&ctrl.actuator_mutex.value));puts("PASS: actual actuator power-up/down + native release/memento/shutdown; init primary error/unwind, failed core retained in ACQUIRE, config/power-up blocked, exact core/I-O phase retries, I-O release error preserved, completed providers skipped across entry points, allocated settings cleanup");
}
'''
def main():
    spec=importlib.util.spec_from_file_location('acquire',Path(__file__).with_name('test-pico-actuator-acquire-retry.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);extract=m.load('test-pico-sensor-mono-hook');core=(SOURCE/D/'cam_actuator_core.c').read_text();adapter=D+'pico_memento_actuator.inc'
    code=m.make_code(MAIN).replace('struct cam_sensor_power_ctrl_t {','struct cam_hw_soc_info {void *soc_private;int index;void *dev;};struct camera_io_master {int master_type;};\nstruct cam_sensor_power_ctrl_t {').replace('unsigned power_setting_size,power_down_setting_size;','unsigned power_setting_size,power_down_setting_size;void *dev;').replace('struct {void *soc_private;int index;}soc_info;','struct cam_hw_soc_info soc_info;struct camera_io_master io_master_info;')
    code=code.replace('struct cam_actuator_ctrl_t {','struct i2c_settings_array {int is_settings_valid;};\nstruct cam_actuator_ctrl_t {').replace('unsigned last_flush_req;','unsigned last_flush_req;struct {struct i2c_settings_array per_frame[4];}i2c_data;')
    stub='static void kfree(void *p){assert(!p);}\nstatic int cam_actuator_power_down(struct cam_actuator_ctrl_t *c){powers++;return power_error;}\n'
    code=code.replace(stub,LOWER+extract.function(core,'static int32_t cam_actuator_power_up(')+extract.function(core,'static int32_t cam_actuator_power_down('))
    extra='#define MAX_PER_FRAME_ARRAY 4\nstruct pico_memento_actuator {struct cam_actuator_ctrl_t *actuator;s32 session,device;bool powered_down,complete;};\nstatic int delete_request(struct i2c_settings_array *s){assert(0);return -EINVAL;}\n'+(SOURCE/adapter).read_text()+extract.function(core,'void cam_actuator_shutdown(')
    code=code.replace(MAIN,extra+MAIN);out=BASE/'out/phoenix-kernel-recovery/actuator-power-retry-tests';out.mkdir(exist_ok=True);(out/'harness.c').write_text(code)
    subprocess.run(['gcc','-std=gnu11','-g','-O1','-pthread','-fsanitize=address,undefined','-fno-omit-frame-pointer','-I'+str(SOURCE/'techpack/camera/include/uapi/media'),'-I'+str(SOURCE/'techpack/camera/include/uapi'),str(out/'harness.c'),'-o',str(out/'test')],check=True)
    r=subprocess.run([str(out/'test')],capture_output=True,text=True,timeout=10);report={'sources':{n:hashlib.sha256((SOURCE/n).read_bytes()).hexdigest() for n in [*m.NAMES,adapter]},'harness_sha256':hashlib.sha256(code.encode()).hexdigest(),'exit_code':r.returncode,'stdout':r.stdout,'stderr':r.stderr,'sanitizers':['AddressSanitizer','UndefinedBehaviorSanitizer'],'scope':'Actual power helpers/native release/memento/shutdown with allocated settings and real state/UAPI; default construction, vreg/core/I-O/destroy providers and controller types modeled; core provider partial side effects, packet activation/full per-frame/lifecycle/remove/hardware pending','device_modified':False};(out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));raise SystemExit(r.returncode)
if __name__=='__main__':main()
