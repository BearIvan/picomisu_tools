"""Actual native acquire/release/power/observer/unwind pipeline with provider models."""
from pathlib import Path
import hashlib,importlib.util,json,subprocess
BASE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro');SOURCE=BASE/'source/phoenix-kernel-recovery';D='techpack/camera/drivers/cam_sensor_module/cam_sensor/'
NAMES=[D+n for n in ['cam_sensor_core.c','cam_sensor_dev.h','pico_sensor_acquire_unwind.inc','pico_sensor_acquire_unwind.h']]+['techpack/camera/drivers/cam_core/pico_camera_memento_capture.'+e for e in ['c','h']]
MOCKS=r'''
#include <stdint.h>
#include <string.h>
typedef unsigned char u8;typedef int32_t s32;
#define CAM_ACQUIRE_DEV 0x102
#define CAM_START_DEV 0x103
#define CAM_STOP_DEV 0x104
#define CAM_RELEASE_DEV 0x106
#define CAM_SENSOR_INIT 0
#define CAM_SENSOR_ACQUIRE 1
#define CAM_SENSOR_START 2
#define CAM_ERR(...) ((void)0)
#define CAM_WARN(...) ((void)0)
#define CAM_DBG(...) ((void)0)
#define CAM_INFO(...) ((void)0)
#define NEO25_FOUR_6DOF_CAMERAS_SUPPORT 1
#define u64_to_user_ptr(p) ((void *)(uintptr_t)(p))
struct task_struct {int id;};static struct task_struct task={1};static struct task_struct *current=&task;
struct pico_memento_capture {struct list_head list;struct task_struct *task;const void *owner;u32 entity,opcode;u8 packet[24];size_t bytes;int native_result,error,unwind_result;bool captured,side_effect,unwound,power_cleanup_attempted;int power_cleanup_result;};
struct cam_sensor_acquire_dev {u32 session_handle,device_handle,handle_type,reserved;uint64_t info_handle;};struct cam_control {u32 op_code,size,handle_type,reserved;uint64_t handle;};
struct cam_create_dev_hdl {u32 session_hdl;void *ops;int v4l2_sub_dev_flag,media_entity_flag;void *priv;};
struct cam_sensor_power_ctrl_t {int marker;};struct cam_camera_slave_info {int sensor_id;};struct cam_hw_soc_info {int marker;};struct camera_io_master {int marker;};
struct cam_sensor_ctrl_t {struct mutex cam_sensor_mutex;struct {struct cam_sensor_power_ctrl_t power_info;struct cam_camera_slave_info slave_info;} *sensordata;struct cam_hw_soc_info soc_info;struct camera_io_master io_master_info;bool bob_pwm_switch;int bob_reg_index;int is_probe_succeed,sensor_state;struct {int device_hdl,session_hdl,link_hdl,ops;}bridge_intf;unsigned last_flush_req,streamon_count,streamoff_count;bool pico_fsin_irq_owned,pico_core_powered,pico_io_initialized,pico_bob_pending,pico_acquire_cleanup_pending,pico_release_cleanup_pending,pico_release_resources_done;};
static struct cam_sensor_ctrl_t *expected;static int copy_error,handle_result=1234,irq_error,core_error,io_error,down_error,release_error,destroy_error,bob_off_error;static unsigned irq_gets,irq_puts,cores,downs,io_inits,io_releases,destroys,bob_on,bob_off,frame_frees,stream_frees;
static int copy_from_user(void *d,const void *s,size_t n){memcpy(d,s,n);return 0;}
static int copy_to_user(void *d,const void *s,size_t n){if(copy_error)return 1;memcpy(d,s,n);return 0;}
static int cam_create_device_hdl(struct cam_create_dev_hdl *p){assert(held==1 && p->session_hdl==41);return handle_result;}
/* Remove_Fsin (sixdof_Fsin_boottime store) stays 0: acquire registers the FSIN irq */
static unsigned char Remove_Fsin;
#ifndef READ_ONCE
#define READ_ONCE(x) (x)
#endif
static int cam_sensor_register_irq(struct cam_sensor_ctrl_t *s){assert(held==1 && !s->pico_fsin_irq_owned);irq_gets++;if(irq_error)return irq_error;s->pico_fsin_irq_owned=true;return 0;}
static int cam_sensor_unregister_irq(struct cam_sensor_ctrl_t *s){assert(held==1);if(!s->pico_fsin_irq_owned)return 0;irq_puts++;s->pico_fsin_irq_owned=false;return 0;}
static int cam_sensor_core_power_up(struct cam_sensor_power_ctrl_t *p,struct cam_hw_soc_info *s){assert(held==1);cores++;return core_error;}
static int cam_sensor_util_power_down(struct cam_sensor_power_ctrl_t *p,struct cam_hw_soc_info *s){assert(held==1 && expected->pico_core_powered);downs++;return down_error;}
static int camera_io_init(struct camera_io_master *i){assert(held==1);io_inits++;return io_error;}
static int camera_io_release(struct camera_io_master *i){assert(held==1 && expected->pico_io_initialized && !expected->pico_core_powered);io_releases++;return release_error;}
static int cam_sensor_bob_pwm_mode_switch(struct cam_hw_soc_info *s,int idx,bool on){assert(held==1);if(on){bob_on++;return 0;}bob_off++;return bob_off_error;}
static void cam_change_sensor_private_slave_address(struct cam_sensor_ctrl_t *s){assert(held==1);}
static int cam_destroy_device_hdl(int handle){assert(held==1 && handle==1234 && !expected->pico_core_powered && !expected->pico_io_initialized && !expected->pico_bob_pending && !expected->pico_fsin_irq_owned);destroys++;return destroy_error;}
static void cam_sensor_release_per_frame_resource(struct cam_sensor_ctrl_t *s){assert(held==1);frame_frees++;}
static void cam_sensor_release_stream_rsc(struct cam_sensor_ctrl_t *s){assert(held==1);stream_frees++;}
'''
MAIN=r'''
static void begin(struct pico_memento_capture *s,struct cam_sensor_ctrl_t *sensor){assert(!pico_memento_capture_begin(s,sensor,0x10001,CAM_ACQUIRE_DEV));}
static void clean(struct cam_sensor_ctrl_t *s){assert(s->bridge_intf.device_hdl==-1 && s->sensor_state==0 && !s->pico_acquire_cleanup_pending && !s->pico_release_cleanup_pending && !s->pico_release_resources_done && !s->pico_fsin_irq_owned && !s->pico_core_powered && !s->pico_io_initialized && !s->pico_bob_pending);}
int main(void){
 struct cam_sensor_ctrl_t sensor={.cam_sensor_mutex={PTHREAD_MUTEX_INITIALIZER},.is_probe_succeed=1,.bridge_intf={-1,-1,-1,0}};__typeof__(*sensor.sensordata) data={0};sensor.sensordata=&data;expected=&sensor;struct cam_sensor_acquire_dev user={.session_handle=41};struct cam_control acq={.op_code=CAM_ACQUIRE_DEV,.handle=(uintptr_t)&user},rel={.op_code=CAM_RELEASE_DEV};struct pico_memento_capture scope;
 begin(&scope,&sensor);copy_error=1;assert(native_command(&sensor,&acq)==-EFAULT);assert(!pico_memento_capture_end(&scope) && scope.unwound);clean(&sensor);copy_error=0;
 begin(&scope,&sensor);irq_error=-EIO;assert(native_command(&sensor,&acq)==-EIO);assert(!pico_memento_capture_end(&scope) && scope.unwound);clean(&sensor);assert(!cores && !irq_puts);irq_error=0;
 begin(&scope,&sensor);core_error=-EIO;assert(native_command(&sensor,&acq)==-EIO);assert(!pico_memento_capture_end(&scope) && scope.unwound);clean(&sensor);assert(irq_puts==1 && !downs);core_error=0;
 begin(&scope,&sensor);io_error=-ENODEV;assert(native_command(&sensor,&acq)==-ENODEV);assert(!pico_memento_capture_end(&scope) && scope.unwound && scope.power_cleanup_attempted && !scope.power_cleanup_result);clean(&sensor);assert(downs==1 && !io_releases);
 begin(&scope,&sensor);down_error=-EBUSY;assert(native_command(&sensor,&acq)==-ENODEV);assert(!pico_memento_capture_end(&scope) && !scope.unwound && scope.unwind_result==-EBUSY && sensor.pico_core_powered && sensor.pico_fsin_irq_owned && sensor.pico_acquire_cleanup_pending && sensor.bridge_intf.device_hdl==1234);assert(native_command(&sensor,&acq)==-EINVAL);
 struct cam_control config={.op_code=0x105};assert(native_command(&sensor,&config)==-EBUSY);
 unsigned before=downs;down_error=0;assert(!native_command(&sensor,&rel) && downs==before+1);clean(&sensor);io_error=0;
 begin(&scope,&sensor);copy_error=1;destroy_error=-EBUSY;assert(native_command(&sensor,&acq)==-EFAULT);assert(!pico_memento_capture_end(&scope) && !scope.unwound && sensor.pico_acquire_cleanup_pending);before=downs;assert(native_command(&sensor,&rel)==-EBUSY && downs==before);destroy_error=0;assert(!native_command(&sensor,&rel) && downs==before);clean(&sensor);copy_error=0;
 begin(&scope,&sensor);assert(!native_command(&sensor,&acq));assert(!pico_memento_capture_end(&scope) && !scope.unwound && !sensor.pico_acquire_cleanup_pending && sensor.pico_core_powered && sensor.pico_io_initialized && sensor.pico_fsin_irq_owned && sensor.sensor_state==1);
 release_error=-EIO;before=downs;assert(native_command(&sensor,&rel)==-EIO && downs==before+1 && !sensor.pico_core_powered && sensor.pico_io_initialized && sensor.pico_fsin_irq_owned);release_error=0;assert(!native_command(&sensor,&rel) && downs==before+1);clean(&sensor);
 sensor.bob_pwm_switch=true;sensor.bob_reg_index=7;assert(!native_command(&sensor,&acq));bob_off_error=-EIO;before=downs;assert(native_command(&sensor,&rel)==-EIO && downs==before+1 && !sensor.pico_core_powered && sensor.pico_bob_pending && sensor.pico_io_initialized);bob_off_error=0;assert(!native_command(&sensor,&rel) && downs==before+1 && bob_on==1 && bob_off==2);clean(&sensor);
 assert(!native_command(&sensor,&acq));unsigned frames=frame_frees,streams=stream_frees,puts_before=irq_puts;before=downs;destroy_error=-EBUSY;
 assert(native_command(&sensor,&rel)==-EBUSY && sensor.pico_release_cleanup_pending && sensor.pico_release_resources_done && sensor.sensor_state==1 && sensor.bridge_intf.device_hdl==1234 && downs==before+1 && frame_frees==frames+1 && stream_frees==streams+1 && irq_puts==puts_before+1);
 assert(native_command(&sensor,&config)==-EBUSY);assert(native_command(&sensor,&acq)==-EINVAL);
 assert(native_command(&sensor,&rel)==-EBUSY && downs==before+1 && frame_frees==frames+1 && stream_frees==streams+1 && irq_puts==puts_before+1);
 destroy_error=0;assert(!native_command(&sensor,&rel) && downs==before+1 && frame_frees==frames+1 && stream_frees==streams+1 && irq_puts==puts_before+1);clean(&sensor);
 assert(list_empty(&pico_memento_captures) && !held);puts("PASS: actual native acquire/release/power/down/observer/unwind pipeline; failed-acquire retries; normal release handle error preserves handles/state, gates config and skips completed power/I-O/IRQ/resource stages on retry; exact final cleanup");
}
'''
def main():
    spec=importlib.util.spec_from_file_location('registry',Path(__file__).with_name('test-pico-camera-hub-registry.py'));common=importlib.util.module_from_spec(spec);spec.loader.exec_module(common)
    prefix=common.HARNESS.split('/* OWNED_SUBDEVICE_MOCKS */')[0].replace('assert(!held);assert(!pthread_mutex_lock','assert(!pthread_mutex_lock').replace('assert(held==1);held--;','assert(held>0);held--;')
    native=(SOURCE/NAMES[0]).read_text();power=native[native.index('int cam_sensor_power_up('):native.index('int cam_sensor_apply_settings(')]
    start=native.index('\tcase CAM_ACQUIRE_DEV: {',native.index('int32_t cam_sensor_driver_cmd('));end=native.index('\tcase CAM_QUERY_CAP:',start)
    gate_start=native.index('\tmutex_lock(&(s_ctrl->cam_sensor_mutex));',native.index('int32_t cam_sensor_driver_cmd('));gate_end=native.index('\tswitch (cmd->op_code) {',gate_start)
    wrapper='static int native_command(struct cam_sensor_ctrl_t *s_ctrl,struct cam_control *cmd){int rc=0;'+native[gate_start:gate_end]+'switch(cmd->op_code){'+native[start:end]+'}release_mutex:mutex_unlock(&s_ctrl->cam_sensor_mutex);return rc;}\n'
    capture=(SOURCE/NAMES[4]).read_text();code=prefix+MOCKS+capture[capture.index('static DEFINE_MUTEX'):]+power+(SOURCE/NAMES[2]).read_text()+wrapper+MAIN
    out=BASE/'out/phoenix-kernel-recovery/sensor-acquire-retry-tests';out.mkdir(exist_ok=True);(out/'harness.c').write_text(code)
    subprocess.run(['gcc','-std=gnu11','-g','-O1','-pthread','-fsanitize=address,undefined','-fno-omit-frame-pointer',str(out/'harness.c'),'-o',str(out/'test')],check=True)
    result=subprocess.run([str(out/'test')],capture_output=True,text=True,timeout=30)
    report={'sources':{n:hashlib.sha256((SOURCE/n).read_bytes()).hexdigest() for n in NAMES},'harness_sha256':hashlib.sha256(code.encode()).hexdigest(),'sensor_release_retry_tested':True,'exit_code':result.returncode,'stdout':result.stdout,'stderr':result.stderr,'sanitizers':['AddressSanitizer','UndefinedBehaviorSanitizer'],'scope':'Actual native acquire/release/power_up/power_down/unwind/observer bodies; lower core/BoB/I-O/IRQ/resource/handle APIs modeled; complete phase path in host model, no live hardware/subdevice file or hot-remove verification','device_modified':False}
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));raise SystemExit(result.returncode)
if __name__=='__main__':main()
