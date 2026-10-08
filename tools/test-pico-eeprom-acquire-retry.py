"""Actual EEPROM ioctl/acquire/unwind bodies; lower handle/usercopy API modeled."""
from pathlib import Path
import hashlib,json,subprocess
import importlib.util
BASE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro');SOURCE=BASE/'source/phoenix-kernel-recovery'
D='techpack/camera/drivers/cam_sensor_module/cam_eeprom/'
NAMES=[D+n for n in ['cam_eeprom_core.c','cam_eeprom_dev.h','pico_eeprom_acquire_unwind.inc','pico_eeprom_acquire_unwind.h']]+['techpack/camera/drivers/cam_core/pico_camera_memento_capture.'+e for e in ['c','h']]+['techpack/camera/include/uapi/media/'+n for n in ['cam_defs.h','cam_sensor.h']]
def load(name):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name(name+'.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
MAIN=r'''
int main(void){
 struct cam_eeprom_ctrl_t ctrl={.eeprom_mutex={PTHREAD_MUTEX_INITIALIZER},.bridge_intf={-1,-1,-1,0}};
 struct cam_sensor_acquire_dev user={.session_handle=41};struct cam_control cmd={.op_code=CAM_ACQUIRE_DEV,.handle_type=CAM_HANDLE_USER_POINTER,.handle=(uintptr_t)&user};
 struct pico_memento_capture scope;expected_owner=&ctrl;
 input_error=1;assert(cam_eeprom_driver_cmd(&ctrl,&cmd)==-EFAULT && !creates && ctrl.bridge_intf.device_hdl==-1);input_error=0;
 next_handle=-ENOMEM;watch=&scope;assert(!pico_memento_capture_begin(&scope,&ctrl,0x1000c,CAM_ACQUIRE_DEV));assert(cam_eeprom_driver_cmd(&ctrl,&cmd)==-ENOMEM);assert(!pico_memento_capture_end(&scope) && scope.captured && !scope.side_effect && !copies && !destroys && ctrl.cam_eeprom_state==0 && !ctrl.pico_acquire_cleanup_pending);
 next_handle=0;watch=NULL;assert(cam_eeprom_driver_cmd(&ctrl,&cmd)==-EINVAL && !copies && ctrl.bridge_intf.device_hdl==-1);
 next_handle=1234;copy_error=1;watch=&scope;assert(!pico_memento_capture_begin(&scope,&ctrl,0x1000c,CAM_ACQUIRE_DEV));assert(cam_eeprom_driver_cmd(&ctrl,&cmd)==-EFAULT);assert(!pico_memento_capture_end(&scope) && scope.unwound && scope.side_effect && !scope.unwind_result && destroys==1 && !ctrl.pico_acquire_cleanup_pending && ctrl.bridge_intf.device_hdl==-1 && ctrl.cam_eeprom_state==0);
 destroy_error=-EIO;assert(!pico_memento_capture_begin(&scope,&ctrl,0x1000c,CAM_ACQUIRE_DEV));assert(cam_eeprom_driver_cmd(&ctrl,&cmd)==-EFAULT);assert(!pico_memento_capture_end(&scope) && !scope.unwound && scope.unwind_result==-EIO && ctrl.pico_acquire_cleanup_pending && ctrl.bridge_intf.device_hdl==1234 && ctrl.cam_eeprom_state==0);watch=NULL;
 unsigned before=creates;assert(cam_eeprom_driver_cmd(&ctrl,&cmd)==-EFAULT && creates==before);
 cmd.op_code=CAM_CONFIG_DEV;assert(cam_eeprom_driver_cmd(&ctrl,&cmd)==-EBUSY && !configs);
 cmd.op_code=CAM_RELEASE_DEV;assert(cam_eeprom_driver_cmd(&ctrl,&cmd)==-EIO && ctrl.pico_acquire_cleanup_pending && ctrl.bridge_intf.device_hdl==1234);
 destroy_error=0;assert(!cam_eeprom_driver_cmd(&ctrl,&cmd) && !ctrl.pico_acquire_cleanup_pending && ctrl.bridge_intf.device_hdl==-1 && ctrl.bridge_intf.session_hdl==-1 && ctrl.cam_eeprom_state==0);
 cmd.op_code=CAM_ACQUIRE_DEV;copy_error=0;assert(!cam_eeprom_driver_cmd(&ctrl,&cmd) && ctrl.cam_eeprom_state==1 && user.device_handle==1234);
 cmd.op_code=CAM_RELEASE_DEV;destroy_error=-EAGAIN;assert(cam_eeprom_driver_cmd(&ctrl,&cmd)==-EAGAIN && ctrl.cam_eeprom_state==1 && ctrl.bridge_intf.device_hdl==1234 && ctrl.bridge_intf.session_hdl==41);
 destroy_error=0;assert(!cam_eeprom_driver_cmd(&ctrl,&cmd) && ctrl.cam_eeprom_state==0 && ctrl.bridge_intf.device_hdl==-1 && ctrl.bridge_intf.session_hdl==-1);
 assert(cam_eeprom_driver_cmd(&ctrl,&cmd)==-EINVAL && !held && list_empty(&pico_memento_captures));assert(!pthread_mutex_destroy(&ctrl.eeprom_mutex.value));
 puts("PASS: actual native EEPROM ioctl/acquire/unwind; copyin failure, zero/negative create, copyout rollback, failed cleanup retained in INIT, blocked config/reacquire, repeated release cleanup, ordinary release failed destroy preserves acquisition");
}
'''
def main():
    peer=load('test-pico-peer-acquire-capture');common=load('test-pico-camera-hub-registry');extract=load('test-pico-sensor-mono-hook')
    prefix=common.HARNESS.split('/* OWNED_SUBDEVICE_MOCKS */')[0].replace('assert(!held);assert(!pthread_mutex_lock','assert(!pthread_mutex_lock').replace('assert(held==1);held--;','assert(held>0);held--;')
    mocks=peer.MOCKS.replace('static int copy_from_user(void *dst,const void *src,size_t n){memcpy(dst,src,n);return 0;}','static int input_error,destroy_error;static unsigned destroys,configs;\nstatic int copy_from_user(void *dst,const void *src,size_t n){if(input_error)return 1;memcpy(dst,src,n);return 0;}').replace('static int cam_destroy_device_hdl(int handle){assert(held==1 && handle==1234);return 0;}','static int cam_destroy_device_hdl(int handle){assert(held==1 && handle==1234);destroys++;return destroy_error;}')
    types='struct cam_eeprom_ctrl_t {struct mutex eeprom_mutex;struct {int device_hdl,session_hdl,link_hdl,ops;}bridge_intf;int cam_eeprom_state;bool pico_acquire_cleanup_pending,userspace_probe,is_multimodule_mode,pico_core_powered,pico_io_initialized,pico_transaction_cleanup_pending;struct {int index;}soc_info;};\n'
    core=(SOURCE/NAMES[0]).read_text();capture=(SOURCE/NAMES[4]).read_text()
    bodies=(SOURCE/NAMES[2]).read_text()+extract.function(core,'static int32_t cam_eeprom_get_dev_handle(')+'\nstatic int cam_eeprom_pkt_parse(struct cam_eeprom_ctrl_t *c,void *arg){configs++;return 0;}\nstatic int cam_eeprom_power_down(struct cam_eeprom_ctrl_t *c){assert(!c->pico_core_powered&&!c->pico_io_initialized);return 0;}\nstatic void pico_eeprom_free_transaction(struct cam_eeprom_ctrl_t *c){c->pico_transaction_cleanup_pending=false;}\n'+extract.function(core,'int32_t cam_eeprom_driver_cmd(')
    code='#include <stdint.h>\n#include <stddef.h>\n#include <string.h>\n#include <cam_defs.h>\n#include <cam_sensor.h>\n#define CAM_EEPROM_ACQUIRE 1\n#define CAM_EEPROM_CONFIG 2\n'+prefix+types+mocks+capture[capture.index('static DEFINE_MUTEX'):]+bodies+MAIN
    out=BASE/'out/phoenix-kernel-recovery/eeprom-acquire-retry-tests';out.mkdir(exist_ok=True);(out/'harness.c').write_text(code)
    subprocess.run(['gcc','-std=gnu11','-g','-O1','-pthread','-fsanitize=address,undefined','-fno-omit-frame-pointer','-I'+str(SOURCE/'techpack/camera/include/uapi/media'),'-I'+str(SOURCE/'techpack/camera/include/uapi'),str(out/'harness.c'),'-o',str(out/'test')],check=True)
    result=subprocess.run([str(out/'test')],capture_output=True,text=True,timeout=30)
    report={'sources':{n:hashlib.sha256((SOURCE/n).read_bytes()).hexdigest() for n in NAMES},'harness_sha256':hashlib.sha256(code.encode()).hexdigest(),'exit_code':result.returncode,'stdout':result.stdout,'stderr':result.stderr,'sanitizers':['AddressSanitizer','UndefinedBehaviorSanitizer'],'scope':'Actual EEPROM ioctl/acquire/unwind/capture bodies and UAPI; modeled lower create/destroy/usercopy/config parser/controller APIs; no hardware, shutdown or subdevice dispatch proof','device_modified':False}
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));raise SystemExit(result.returncode)
if __name__=='__main__':main()
