"""Actual EEPROM shutdown/open/last-close bodies; resource APIs modeled."""
from pathlib import Path
import hashlib,json,subprocess,importlib.util
BASE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro');SOURCE=BASE/'source/phoenix-kernel-recovery';D='techpack/camera/drivers/cam_sensor_module/cam_eeprom/'
NAMES=[D+n for n in ['cam_eeprom_core.c','cam_eeprom_dev.c','cam_eeprom_dev.h','pico_eeprom_acquire_unwind.inc','pico_eeprom_acquire_unwind.h']]
def load(name):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name(name+'.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
MOCKS=r'''
#define CAM_ERR(...) ((void)0)
#define CAM_DBG(...) ((void)0)
struct cam_sensor_power_ctrl_t {void *power_setting,*power_down_setting;unsigned power_setting_size,power_down_setting_size;};
struct cam_eeprom_soc_private {struct cam_sensor_power_ctrl_t power_info;};
struct cam_eeprom_ctrl_t {struct mutex eeprom_mutex;struct {int device_hdl,session_hdl,link_hdl;}bridge_intf;enum cam_eeprom_state cam_eeprom_state;bool pico_acquire_cleanup_pending,pico_core_powered,pico_io_initialized,pico_transaction_cleanup_pending;unsigned open_cnt;struct {void *soc_private;}soc_info;struct {void *mapdata,*map;unsigned num_data,num_map;}cal_data;struct {int is_settings_valid;}wr_settings;};
struct v4l2_subdev {struct cam_eeprom_ctrl_t *ctrl;};struct v4l2_subdev_fh {int unused;};
static void *v4l2_get_subdevdata(struct v4l2_subdev *sd){return sd->ctrl;}
static int destroy_error,power_error;static unsigned destroys,power_downs,frees;
static int cam_destroy_device_hdl(int handle){assert(held==1&&handle==1234);destroys++;return destroy_error;}
static int cam_eeprom_power_down(struct cam_eeprom_ctrl_t *ctrl){assert(held==1&&ctrl->cam_eeprom_state==CAM_EEPROM_CONFIG);power_downs++;return power_error;}
static void kfree(void *ptr){assert(held==1);if(ptr){frees++;free(ptr);}}
static int delete_eeprom_request(void *s){assert(0);return 0;}
#define vfree kfree
static void run_shutdown(struct cam_eeprom_ctrl_t *ctrl);
'''
MAIN=r'''
static void run_shutdown(struct cam_eeprom_ctrl_t *ctrl){mutex_lock(&ctrl->eeprom_mutex);cam_eeprom_shutdown(ctrl);mutex_unlock(&ctrl->eeprom_mutex);}
int main(void){
 struct cam_eeprom_ctrl_t ctrl={.eeprom_mutex={PTHREAD_MUTEX_INITIALIZER},.bridge_intf={-1,-1,-1}};struct v4l2_subdev sd={&ctrl};
 run_shutdown(&ctrl);assert(!destroys&&!power_downs&&!frees);
 ctrl.pico_acquire_cleanup_pending=true;ctrl.bridge_intf.device_hdl=1234;ctrl.bridge_intf.session_hdl=41;
 destroy_error=-EINVAL;assert(!cam_eeprom_subdev_open(&sd,NULL));assert(!cam_eeprom_subdev_open(&sd,NULL));assert(!cam_eeprom_subdev_close(&sd,NULL)&&!destroys&&ctrl.open_cnt==1);
 assert(!cam_eeprom_subdev_close(&sd,NULL)&&destroys==1&&ctrl.open_cnt==0&&ctrl.pico_acquire_cleanup_pending&&ctrl.bridge_intf.device_hdl==1234&&ctrl.cam_eeprom_state==CAM_EEPROM_INIT);
 assert(cam_eeprom_subdev_close(&sd,NULL)==-EINVAL&&destroys==1);
 destroy_error=0;assert(!cam_eeprom_subdev_open(&sd,NULL));assert(!cam_eeprom_subdev_close(&sd,NULL)&&destroys==2&&!ctrl.pico_acquire_cleanup_pending&&ctrl.bridge_intf.device_hdl==-1&&!power_downs&&!frees);
 struct cam_eeprom_soc_private private={.power_info={malloc(8),malloc(16),1,2}};assert(private.power_info.power_setting&&private.power_info.power_down_setting);ctrl.soc_info.soc_private=&private;
 ctrl.cam_eeprom_state=CAM_EEPROM_CONFIG;ctrl.bridge_intf.device_hdl=1234;ctrl.bridge_intf.session_hdl=41;power_error=-EIO;
 run_shutdown(&ctrl);assert(ctrl.cam_eeprom_state==CAM_EEPROM_CONFIG&&ctrl.bridge_intf.device_hdl==1234&&power_downs==1&&destroys==2&&!frees&&private.power_info.power_setting);
 power_error=0;destroy_error=-EINVAL;run_shutdown(&ctrl);assert(ctrl.cam_eeprom_state==CAM_EEPROM_ACQUIRE&&ctrl.bridge_intf.device_hdl==1234&&power_downs==2&&destroys==3&&!frees&&private.power_info.power_setting);
 run_shutdown(&ctrl);assert(ctrl.cam_eeprom_state==CAM_EEPROM_ACQUIRE&&power_downs==2&&destroys==4&&!frees);
 destroy_error=0;run_shutdown(&ctrl);assert(ctrl.cam_eeprom_state==CAM_EEPROM_INIT&&ctrl.bridge_intf.device_hdl==-1&&ctrl.bridge_intf.session_hdl==-1&&ctrl.bridge_intf.link_hdl==-1&&power_downs==2&&destroys==5&&frees==2&&!private.power_info.power_setting&&!private.power_info.power_down_setting&&!private.power_info.power_setting_size&&!private.power_info.power_down_setting_size);
 run_shutdown(&ctrl);assert(power_downs==2&&destroys==5&&frees==2&&!held);assert(!pthread_mutex_destroy(&ctrl.eeprom_mutex.value));
 puts("PASS: actual EEPROM shutdown/open/last-close bodies; partial INIT without soc-private dereference, close-count gate, failed destroy retention/reopen-close retry, CONFIG power failure retention, successful power stage skipped on handle retry, allocation freeing exactly once");
}
'''
def main():
    common=load('test-pico-camera-hub-registry');extract=load('test-pico-sensor-mono-hook');core=(SOURCE/NAMES[0]).read_text();dev=(SOURCE/NAMES[1]).read_text();header=(SOURCE/NAMES[2]).read_text()
    states=header[header.index('enum cam_eeprom_state {'):header.index('};',header.index('enum cam_eeprom_state {'))+2]
    prefix=common.HARNESS.split('/* OWNED_SUBDEVICE_MOCKS */')[0].replace('struct v4l2_subdev {int marker;};','')
    code='#include <stdbool.h>\n'+prefix+states+MOCKS+(SOURCE/NAMES[3]).read_text()+extract.function(core,'static void pico_eeprom_free_transaction(')+extract.function(core,'void cam_eeprom_shutdown(')+extract.function(dev,'static int cam_eeprom_subdev_open(')+extract.function(dev,'static int cam_eeprom_subdev_close(')+MAIN
    out=BASE/'out/phoenix-kernel-recovery/eeprom-shutdown-retry-tests';out.mkdir(exist_ok=True);(out/'harness.c').write_text(code)
    subprocess.run(['gcc','-std=gnu11','-g','-O1','-pthread','-fsanitize=address,undefined','-fno-omit-frame-pointer',str(out/'harness.c'),'-o',str(out/'test')],check=True)
    result=subprocess.run([str(out/'test')],capture_output=True,text=True,timeout=30)
    report={'sources':{n:hashlib.sha256((SOURCE/n).read_bytes()).hexdigest() for n in NAMES},'harness_sha256':hashlib.sha256(code.encode()).hexdigest(),'exit_code':result.returncode,'stdout':result.stdout,'stderr':result.stderr,'sanitizers':['AddressSanitizer','UndefinedBehaviorSanitizer'],'scope':'Actual EEPROM shutdown/open/close/unwind and native state enum; lower power-down/handle/user/controller/subdev APIs modeled; no physical hardware/remove-lifetime or individual power-down provider retry proof','device_modified':False}
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));raise SystemExit(result.returncode)
if __name__=='__main__':main()
