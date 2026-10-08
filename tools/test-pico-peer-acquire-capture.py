"""Real four-peer acquire bodies and capture, using current public UAPI packets."""
from pathlib import Path
import hashlib,importlib.util,json,subprocess
BASE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro');SOURCE=BASE/'source/phoenix-kernel-recovery'
PEERS=[('cam_actuator/cam_actuator_core.c','cam_actuator_ctrl_t','a_ctrl',0x10009,'actuator',None),('cam_ois/cam_ois_core.c','cam_ois_ctrl_t','o_ctrl',0x1000d,'ois','static int cam_ois_get_dev_handle('),('cam_eeprom/cam_eeprom_core.c','cam_eeprom_ctrl_t','e_ctrl',0x1000c,'eeprom','static int32_t cam_eeprom_get_dev_handle('),('cam_flash/cam_flash_dev.c','cam_flash_ctrl','fctrl',0x1000b,'flash',None)]
NAMES=['techpack/camera/drivers/cam_sensor_module/'+p[0] for p in PEERS]+['techpack/camera/drivers/cam_core/pico_camera_memento_capture.'+e for e in ['c','h']]+['techpack/camera/include/uapi/media/'+n for n in ['cam_defs.h','cam_sensor.h']]
NAMES += ['techpack/camera/drivers/cam_sensor_module/cam_eeprom/pico_eeprom_acquire_unwind.'+e for e in ['inc','h']]
NAMES += ['techpack/camera/drivers/cam_sensor_module/cam_actuator/pico_actuator_acquire_unwind.'+e for e in ['inc','h']]
MOCKS=r'''
typedef unsigned char u8;typedef int32_t s32;
#define CAM_ACTUATOR_ACQUIRE 1
#define CAM_ACTUATOR_INIT 0
#define CAM_EEPROM_INIT 0
#define CAM_FLASH_STATE_INIT 0
#define CAM_FLASH_STATE_ACQUIRE 1
#define CAM_ERR(...) ((void)0)
#define CAM_DBG(...) ((void)0)
#define CAM_WARN(...) ((void)0)
#define u64_to_user_ptr(p) ((void *)(uintptr_t)(p))
struct task_struct {int id;};static struct task_struct task={1};static struct task_struct *current=&task;
struct pico_memento_capture {struct list_head list;struct task_struct *task;const void *owner;u32 entity,opcode;u8 packet[24];size_t bytes;int native_result,error,unwind_result;bool captured,side_effect,unwound,power_cleanup_attempted;int power_cleanup_result;};
struct cam_create_dev_hdl {u32 session_hdl;void *ops;int v4l2_sub_dev_flag,media_entity_flag;void *priv;};
static struct pico_memento_capture *watch;static void *expected_owner;static int next_handle=1234,copy_error;static unsigned copies,creates;
static int copy_from_user(void *dst,const void *src,size_t n){memcpy(dst,src,n);return 0;}
static int copy_to_user(void *dst,const void *src,size_t n){assert(held==1 && n==24);if(watch)assert(watch->captured && watch->owner==expected_owner && watch->bytes==24 && !memcmp(watch->packet,src,24));copies++;if(copy_error)return 1;memcpy(dst,src,n);return 0;}
static int cam_create_device_hdl(struct cam_create_dev_hdl *p){assert(held==1 && p->priv==expected_owner && p->session_hdl==41);creates++;return next_handle;}
static int cam_destroy_device_hdl(int handle){assert(held==1 && handle==1234);return 0;}
'''
def load(name):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name(name+'.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
def main():
    common=load('test-pico-camera-hub-registry');extract=load('test-pico-sensor-mono-hook')
    prefix=common.HARNESS.split('/* OWNED_SUBDEVICE_MOCKS */')[0].replace('assert(!held);assert(!pthread_mutex_lock','assert(!pthread_mutex_lock').replace('assert(held==1);held--;','assert(held>0);held--;')
    types='';bodies='';tests='int main(void){assert(sizeof(struct cam_sensor_acquire_dev)==24 && CAM_ACQUIRE_DEV==0x102);\n'
    for rel,kind,owner,entity,label,signature in PEERS:
        types+=f'struct {kind} {{struct mutex mutex,eeprom_mutex,actuator_mutex;struct {{int device_hdl,session_hdl,link_hdl,ops;}}bridge_intf;int cam_act_state,flash_state,cam_eeprom_state;unsigned last_flush_req;bool pico_acquire_cleanup_pending;}};\n'
        text=(SOURCE/('techpack/camera/drivers/cam_sensor_module/'+rel)).read_text()
        if signature:
            if label=='eeprom':bodies+=(SOURCE/NAMES[8]).read_text()+'\n'
            body=extract.function(text,signature);bodies+=body+'\n';callee='cam_'+label+'_get_dev_handle'
        else:
            if label=='actuator':bodies+=(SOURCE/NAMES[10]).read_text()+'\n'
            start=text.index('\tcase CAM_ACQUIRE_DEV: {');end=text.index('\tcase CAM_RELEASE_DEV:',start)
            bodies+=f'static int native_{label}(struct {kind} *{owner},void *arg){{int rc=0;struct cam_control *cmd=arg;switch(cmd->op_code){{'+text[start:end]+'}release_mutex:return rc;}\n';callee='native_'+label
        bodies+=f'static int call_{label}(struct {kind} *ctrl,struct cam_control *cmd){{mutex_lock(&ctrl->mutex);int rc={callee}(ctrl,cmd);mutex_unlock(&ctrl->mutex);return rc;}}\n'
        tests+='{' +f'struct {kind} ctrl={{.mutex={{PTHREAD_MUTEX_INITIALIZER}},.bridge_intf={{-1,-1,-1,0}}}};struct cam_sensor_acquire_dev user={{.session_handle=41}};struct cam_control cmd={{.op_code=CAM_ACQUIRE_DEV,.handle=(uintptr_t)&user}};struct pico_memento_capture scope;expected_owner=&ctrl;watch=&scope;next_handle=1234;copy_error=0;\n'
        tests+=f'assert(!pico_memento_capture_begin(&scope,&ctrl,0x{entity:x},CAM_ACQUIRE_DEV));assert(!call_{label}(&ctrl,&cmd));assert(!pico_memento_capture_end(&scope) && scope.side_effect && !scope.native_result && !scope.unwound && user.device_handle==1234);\n'
        tests+=f'ctrl.bridge_intf.device_hdl=-1;ctrl.flash_state=0;user.device_handle=0;copy_error=1;assert(!pico_memento_capture_begin(&scope,&ctrl,0x{entity:x},CAM_ACQUIRE_DEV));assert(call_{label}(&ctrl,&cmd)==-EFAULT);assert(!pico_memento_capture_end(&scope) && scope.side_effect && !scope.unwound && user.device_handle==0 && ((const struct cam_sensor_acquire_dev *)scope.packet)->device_handle==1234);\n'
        tests+=f'ctrl.bridge_intf.device_hdl=-1;ctrl.flash_state=0;copy_error=0;next_handle=-ENOMEM;assert(!pico_memento_capture_begin(&scope,&ctrl,0x{entity:x},CAM_ACQUIRE_DEV));assert(!call_{label}(&ctrl,&cmd));assert(!pico_memento_capture_end(&scope) && !scope.side_effect && scope.native_result==-EINVAL && (s32)((const struct cam_sensor_acquire_dev *)scope.packet)->device_handle==-ENOMEM);\n'
        tests+=f'watch=NULL;ctrl.bridge_intf.device_hdl=-1;ctrl.flash_state=0;next_handle=1234;assert(!call_{label}(&ctrl,&cmd));assert(!pthread_mutex_destroy(&ctrl.mutex.value));'+'}\n'
        if label=='actuator':
            bodies=bodies.replace('mutex_lock(&ctrl->mutex);int rc=native_actuator(ctrl,cmd);mutex_unlock(&ctrl->mutex);','mutex_lock(&ctrl->actuator_mutex);int rc=native_actuator(ctrl,cmd);mutex_unlock(&ctrl->actuator_mutex);')
            start=tests.rindex('{struct cam_actuator_ctrl_t');section=tests[start:]
            section=section.replace('.mutex={PTHREAD_MUTEX_INITIALIZER}', '.actuator_mutex={PTHREAD_MUTEX_INITIALIZER}').replace('ctrl.flash_state=0;', 'ctrl.flash_state=0;ctrl.cam_act_state=0;')
            section=section.replace('scope.side_effect && !scope.unwound && user.device_handle==0','scope.side_effect && scope.unwound && ctrl.bridge_intf.device_hdl==-1 && user.device_handle==0')
            section=section.replace('assert(!call_actuator(&ctrl,&cmd));assert(!pico_memento_capture_end(&scope) && !scope.side_effect','assert(call_actuator(&ctrl,&cmd)==-ENOMEM);assert(!pico_memento_capture_end(&scope) && !scope.side_effect').replace('scope.native_result==-EINVAL','scope.native_result==-ENOMEM')
            section=section.replace('ctrl.mutex.value','ctrl.actuator_mutex.value');tests=tests[:start]+section
        if label=='eeprom':
            bodies=bodies.replace('mutex_lock(&ctrl->mutex);int rc=cam_eeprom_get_dev_handle(ctrl,cmd);mutex_unlock(&ctrl->mutex);','mutex_lock(&ctrl->eeprom_mutex);int rc=cam_eeprom_get_dev_handle(ctrl,cmd);mutex_unlock(&ctrl->eeprom_mutex);')
            start=tests.rindex('{struct cam_eeprom_ctrl_t');section=tests[start:]
            section=section.replace('.mutex={PTHREAD_MUTEX_INITIALIZER}', '.eeprom_mutex={PTHREAD_MUTEX_INITIALIZER}')
            section=section.replace('scope.side_effect && !scope.unwound && user.device_handle==0','scope.side_effect && scope.unwound && ctrl.bridge_intf.device_hdl==-1 && user.device_handle==0')
            section=section.replace('assert(!call_eeprom(&ctrl,&cmd));assert(!pico_memento_capture_end(&scope) && !scope.side_effect','assert(call_eeprom(&ctrl,&cmd)==-ENOMEM);assert(!pico_memento_capture_end(&scope) && !scope.side_effect')
            section=section.replace('ctrl.mutex.value','ctrl.eeprom_mutex.value');tests=tests[:start]+section
    tests+='assert(creates==16 && copies==14 && list_empty(&pico_memento_captures) && !held);puts("PASS: four actual native acquire bodies/observer with real UAPI; EEPROM/actuator copyout unwind and negative create rejection; OIS/Flash retain original partial-acquire behavior; ordinary no-scope path");}\n'
    capture=(SOURCE/NAMES[4]).read_text();code='#include <stdint.h>\n#include <stddef.h>\n#include <string.h>\n#include <cam_defs.h>\n#include <cam_sensor.h>\n'+prefix+types+MOCKS+capture[capture.index('static DEFINE_MUTEX'):]+bodies+tests
    out=BASE/'out/phoenix-kernel-recovery/peer-acquire-capture-tests';out.mkdir(exist_ok=True);(out/'harness.c').write_text(code)
    subprocess.run(['gcc','-std=gnu11','-g','-O1','-pthread','-fsanitize=address,undefined','-fno-omit-frame-pointer','-I'+str(SOURCE/'techpack/camera/include/uapi/media'),'-I'+str(SOURCE/'techpack/camera/include/uapi'),str(out/'harness.c'),'-o',str(out/'test')],check=True)
    result=subprocess.run([str(out/'test')],capture_output=True,text=True,timeout=30)
    report={'sources':{n:hashlib.sha256((SOURCE/n).read_bytes()).hexdigest() for n in NAMES},'harness_sha256':hashlib.sha256(code.encode()).hexdigest(),'exit_code':result.returncode,'stdout':result.stdout,'stderr':result.stderr,'sanitizers':['AddressSanitizer','UndefinedBehaviorSanitizer'],'scope':'Actual four-peer acquire/helper bodies and observer using current UAPI; modeled create/usercopy and controller mutex; captures side effects, peer failed-acquire cleanup/hardware/dispatch integration not verified','device_modified':False}
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));raise SystemExit(result.returncode)
if __name__=='__main__':main()
