"""Actual observer and native sensor acquire case, including partial failure."""
from pathlib import Path
import hashlib,importlib.util,json,subprocess
BASE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro');SOURCE=BASE/'source/phoenix-kernel-recovery';D='techpack/camera/drivers/cam_core/'
NAMES=[D+'pico_camera_memento_capture.'+s for s in ['c','h']]+['techpack/camera/drivers/cam_sensor_module/cam_sensor/cam_sensor_core.c']
NAMES += ['techpack/camera/drivers/cam_sensor_module/cam_sensor/pico_sensor_acquire_unwind.'+s for s in ['inc','h']]
MOCKS=r'''
#include <stdint.h>
#include <string.h>
typedef unsigned char u8;
typedef int32_t s32;
#define CAM_ACQUIRE_DEV 0x102
#define CAM_START_DEV 0x103
#define CAM_STOP_DEV 0x104
#define CAM_RELEASE_DEV 0x106
#define CAM_SENSOR_INIT 0
#define CAM_SENSOR_ACQUIRE 1
#define CAM_DBG(...) ((void)0)
#define CAM_WARN(...) ((void)0)
#define CAM_ERR(...) ((void)0)
#define CAM_INFO(...) ((void)0)
#define NEO25_FOUR_6DOF_CAMERAS_SUPPORT 1
#define u64_to_user_ptr(p) ((void *)(uintptr_t)(p))
struct task_struct {int id;};static struct task_struct root={1},other={2};static _Thread_local struct task_struct *current;
struct pico_memento_capture {struct list_head list;struct task_struct *task;const void *owner;u32 entity,opcode;u8 packet[24];size_t bytes;int native_result,error,unwind_result;bool captured,side_effect,unwound,power_cleanup_attempted;int power_cleanup_result;};
struct cam_sensor_acquire_dev {u32 session_handle,device_handle,handle_type,reserved;uint64_t info_handle;};
struct cam_control {u32 op_code,size,handle_type,reserved;uint64_t handle;};
struct cam_create_dev_hdl {u32 session_hdl;void *ops;int v4l2_sub_dev_flag,media_entity_flag;void *priv;};
struct cam_sensor_ctrl_t {struct mutex cam_sensor_mutex;int is_probe_succeed,sensor_state;struct {int device_hdl,session_hdl,ops,link_hdl;}bridge_intf;unsigned last_flush_req;bool pico_acquire_cleanup_pending,pico_fsin_irq_owned,pico_core_powered,pico_io_initialized,pico_bob_pending,pico_release_cleanup_pending,pico_release_resources_done;};
static struct pico_memento_capture *watch;static int copyin_error,copy_error,power_error,destroy_error,irq_error;static unsigned destroys;static unsigned copyouts,powerups,irqs;static int next_handle=1234;
static int copy_from_user(void *dst,const void *src,size_t n){if(copyin_error)return 1;memcpy(dst,src,n);return 0;}
static int copy_to_user(void *dst,const void *src,size_t n){assert(held==1);if(watch)assert(watch->captured && watch->bytes==24 && !memcmp(watch->packet,src,24));copyouts++;if(copy_error)return 1;memcpy(dst,src,n);return 0;}
static int cam_create_device_hdl(struct cam_create_dev_hdl *p){assert(held==1 && p->session_hdl==41);return next_handle;}
static int cam_destroy_device_hdl(int handle){assert(held==1 && handle==1234);destroys++;return destroy_error;}
static int cam_sensor_power_down(struct cam_sensor_ctrl_t *s){assert(held==1);s->pico_core_powered=s->pico_io_initialized=s->pico_bob_pending=false;return 0;}
static int cam_sensor_unregister_irq(struct cam_sensor_ctrl_t *s){assert(held==1 && s->pico_fsin_irq_owned);s->pico_fsin_irq_owned=false;return 0;}
static int cam_sensor_power_up(struct cam_sensor_ctrl_t *s){assert(held==1);powerups++;return power_error;}
/* Remove_Fsin (sixdof_Fsin_boottime store) stays 0: acquire registers the FSIN irq */
static unsigned char Remove_Fsin;
#ifndef READ_ONCE
#define READ_ONCE(x) (x)
#endif
static int cam_sensor_register_irq(struct cam_sensor_ctrl_t *s){assert(held==1);irqs++;if(!irq_error)s->pico_fsin_irq_owned=true;return irq_error;}
'''
MAIN=r'''
static struct pico_memento_capture foreign;
static int owner;
static void *other_thread(void *arg){current=&other;u32 packet[6]={41,77,1,0,0,0};assert(pico_memento_capture_end(&foreign)==-EPERM);pico_memento_capture_native(&owner,0x10001,CAM_ACQUIRE_DEV,packet,24,0,true);struct pico_memento_capture local;assert(!pico_memento_capture_begin(&local,&owner,0x10001,CAM_ACQUIRE_DEV));pico_memento_capture_native(&owner,0x10001,CAM_ACQUIRE_DEV,packet,24,0,true);assert(!pico_memento_capture_end(&local) && local.packet[4]==77);return NULL;}
int main(void){current=&root;struct pico_memento_capture scope,duplicate;u32 packet[6]={41,42,1,0,0,0};
 assert(pico_memento_capture_begin(NULL,&owner,0x10001,CAM_ACQUIRE_DEV)==-EINVAL);assert(!pico_memento_capture_begin(&scope,&owner,0x10001,CAM_ACQUIRE_DEV));assert(pico_memento_capture_begin(&scope,&owner,0x10001,CAM_ACQUIRE_DEV)==-EBUSY);assert(pico_memento_capture_begin(&duplicate,&owner,0x10001,CAM_START_DEV)==-EBUSY);
 pico_memento_capture_native(&duplicate,0x10001,CAM_ACQUIRE_DEV,packet,24,0,true);pico_memento_capture_native(&owner,0x10009,CAM_ACQUIRE_DEV,packet,24,0,true);pico_memento_capture_native(&owner,0x10001,CAM_START_DEV,packet,8,0,true);assert(!scope.captured);assert(pico_memento_capture_end(&scope)==-ENODATA);
 assert(!pico_memento_capture_begin(&scope,&owner,0x10001,CAM_ACQUIRE_DEV));pico_memento_capture_native(&owner,0x10001,CAM_ACQUIRE_DEV,packet,8,0,true);assert(pico_memento_capture_end(&scope)==-EINVAL && scope.side_effect && !scope.captured);
 assert(!pico_memento_capture_begin(&scope,&owner,0x10001,CAM_ACQUIRE_DEV));pico_memento_capture_native(&owner,0x10001,CAM_ACQUIRE_DEV,packet,24,0,true);packet[1]=999;pico_memento_capture_native(&owner,0x10001,CAM_ACQUIRE_DEV,packet,24,0,true);assert(pico_memento_capture_end(&scope)==-EALREADY && ((u32 *)scope.packet)[1]==42);assert(pico_memento_capture_end(&scope)==-ENOENT);
 assert(!pico_memento_capture_begin(&foreign,&owner,0x10001,CAM_ACQUIRE_DEV));pthread_t t;assert(!pthread_create(&t,NULL,other_thread,NULL));assert(!pthread_join(t,NULL));assert(!foreign.captured && pico_memento_capture_end(&foreign)==-ENODATA);
 struct cam_sensor_ctrl_t sensor={.cam_sensor_mutex={PTHREAD_MUTEX_INITIALIZER},.is_probe_succeed=1,.sensor_state=0,.bridge_intf={-1,-1,0,-1}};struct cam_sensor_acquire_dev user={.session_handle=41};struct cam_control cmd={.op_code=CAM_ACQUIRE_DEV,.handle=(uintptr_t)&user};
 assert(!pico_memento_capture_begin(&scope,&sensor,0x10001,CAM_ACQUIRE_DEV));copyin_error=1;assert(native_acquire(&sensor,&cmd)==-EFAULT && !copyouts && !powerups && sensor.bridge_intf.device_hdl==-1);assert(pico_memento_capture_end(&scope)==-ENODATA && !scope.side_effect);copyin_error=0;
 assert(!pico_memento_capture_begin(&scope,&sensor,0x10001,CAM_ACQUIRE_DEV));watch=&scope;copy_error=1;assert(native_acquire(&sensor,&cmd)==-EFAULT && !powerups && !irqs && copyouts==1);assert(!pico_memento_capture_end(&scope) && scope.side_effect && scope.unwound && scope.unwind_result==0 && destroys==1 && sensor.bridge_intf.device_hdl==-1 && scope.native_result==0 && ((u32 *)scope.packet)[1]==1234 && sensor.sensor_state==0);
 destroy_error=-EBUSY;assert(!pico_memento_capture_begin(&scope,&sensor,0x10001,CAM_ACQUIRE_DEV));assert(native_acquire(&sensor,&cmd)==-EFAULT);assert(!pico_memento_capture_end(&scope) && !scope.unwound && scope.unwind_result==-EBUSY && sensor.bridge_intf.device_hdl==1234 && scope.side_effect);assert(native_acquire(&sensor,&cmd)==-EINVAL);destroy_error=0;
 sensor.bridge_intf.device_hdl=-1;copy_error=0;irq_error=-EIO;assert(!pico_memento_capture_begin(&scope,&sensor,0x10001,CAM_ACQUIRE_DEV));assert(native_acquire(&sensor,&cmd)==-EIO && !powerups && irqs==1);assert(!pico_memento_capture_end(&scope) && scope.unwound && sensor.bridge_intf.device_hdl==-1);irq_error=0;
 sensor.bridge_intf.device_hdl=-1;copy_error=0;power_error=-EIO;assert(!pico_memento_capture_begin(&scope,&sensor,0x10001,CAM_ACQUIRE_DEV));assert(native_acquire(&sensor,&cmd)==-EIO && powerups==1 && irqs==2);assert(!pico_memento_capture_end(&scope) && scope.side_effect && sensor.sensor_state==0);
 sensor.bridge_intf.device_hdl=-1;power_error=0;assert(!pico_memento_capture_begin(&scope,&sensor,0x10001,CAM_ACQUIRE_DEV));assert(!native_acquire(&sensor,&cmd) && sensor.sensor_state==1);assert(!pico_memento_capture_end(&scope) && ((u32 *)scope.packet)[1]==1234);
 sensor.bridge_intf.device_hdl=-1;sensor.sensor_state=0;next_handle=-ENOMEM;assert(!pico_memento_capture_begin(&scope,&sensor,0x10001,CAM_ACQUIRE_DEV));assert(native_acquire(&sensor,&cmd)==-ENOMEM);assert(!pico_memento_capture_end(&scope) && sensor.bridge_intf.device_hdl==-1 && !scope.side_effect && scope.native_result==-EINVAL && (s32)((u32 *)scope.packet)[1]==-ENOMEM);
 next_handle=1234;watch=NULL;sensor.bridge_intf.device_hdl=-1;sensor.sensor_state=0;assert(!native_acquire(&sensor,&cmd));assert(list_empty(&pico_memento_captures) && !held);
 puts("PASS: actual observer/native sensor acquire case; task/owner/entity/op routing, nested/duplicate/malformed capture, cross-thread isolation/end guard, packet observed before usercopy, copyout and powerup errors retain created-handle evidence, pre-power copyin/create guards and copyout handle unwind; normal success with no scope");
}
'''
def main():
    spec=importlib.util.spec_from_file_location('registry',Path(__file__).with_name('test-pico-camera-hub-registry.py'));common=importlib.util.module_from_spec(spec);spec.loader.exec_module(common)
    prefix=common.HARNESS.split('/* OWNED_SUBDEVICE_MOCKS */')[0].replace('assert(!held);assert(!pthread_mutex_lock', 'assert(!pthread_mutex_lock').replace('assert(held==1);held--;','assert(held>0);held--;')
    capture=(SOURCE/NAMES[0]).read_text();native=(SOURCE/NAMES[2]).read_text();start=native.index('\tcase CAM_ACQUIRE_DEV: {',native.index('int32_t cam_sensor_driver_cmd('));end=native.index('\tcase CAM_RELEASE_DEV:',start)
    wrapper='static int native_acquire(struct cam_sensor_ctrl_t *s_ctrl,struct cam_control *cmd){int rc=0;mutex_lock(&s_ctrl->cam_sensor_mutex);switch(cmd->op_code){\n'+native[start:end]+'}\nrelease_mutex:mutex_unlock(&s_ctrl->cam_sensor_mutex);return rc;}\n'
    code=prefix+MOCKS+capture[capture.index('static DEFINE_MUTEX'):]+(SOURCE/NAMES[3]).read_text()+wrapper+MAIN
    out=BASE/'out/phoenix-kernel-recovery/memento-capture-tests';out.mkdir(exist_ok=True);(out/'harness.c').write_text(code)
    subprocess.run(['gcc','-std=gnu11','-g','-O1','-pthread','-fsanitize=address,undefined','-fno-omit-frame-pointer',str(out/'harness.c'),'-o',str(out/'test')],check=True)
    result=subprocess.run([str(out/'test')],capture_output=True,text=True,timeout=30)
    report={'sources':{n:hashlib.sha256((SOURCE/n).read_bytes()).hexdigest() for n in NAMES},'harness_sha256':hashlib.sha256(code.encode()).hexdigest(),'sensor_pre_power_unwind_tested':True,'exit_code':result.returncode,'stdout':result.stdout,'stderr':result.stderr,'sanitizers':['AddressSanitizer','UndefinedBehaviorSanitizer'],'scope':'Actual capture bodies/native sensor acquire case; pthread task identities, modeled copyout/create/power/IRQ APIs; pre-power input/create guards and copyout handle unwind observed; power-up failure rollback and live hardware/subdevice dispatch pending','device_modified':False}
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));raise SystemExit(result.returncode)
if __name__=='__main__':main()
