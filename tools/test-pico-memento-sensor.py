"""Actual ledger and phased native sensor rollback with hardware API models."""
from pathlib import Path
import hashlib,importlib.util,json,subprocess
BASE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro')
SOURCE=BASE/'source/phoenix-kernel-recovery';D='techpack/camera/drivers/cam_sensor_module/cam_sensor/'
NAMES=[D+n for n in ['pico_memento_sensor.inc','pico_memento_sensor.h','cam_sensor_core.c']]+['techpack/camera/drivers/cam_core/pico_camera_memento.'+ext for ext in ['c','h']]
MOCKS=r'''
typedef int s32;
#define CAM_SENSOR_INIT 0
#define CAM_SENSOR_ACQUIRE 1
#define CAM_SENSOR_START 2
#define CAM_SENSOR_PACKET_OPCODE_SENSOR_STREAMOFF 99
#define NEO25_FOUR_6DOF_CAMERAS_SUPPORT 1
struct cam_sensor_ctrl_t {struct mutex cam_sensor_mutex;struct {int session_hdl,device_hdl,link_hdl;}bridge_intf;struct {struct {bool is_settings_valid;int request_id;}streamoff_settings;}i2c_data;int sensor_state;unsigned last_flush_req,streamon_count,streamoff_count;bool pico_release_cleanup_pending,pico_release_resources_done;};
struct pico_memento_sensor {struct cam_sensor_ctrl_t *sensor;s32 session,device;bool powered_down,resources_released,complete;};
static struct cam_sensor_ctrl_t *expected;static int apply_error,power_error,destroy_error;
static unsigned apply_calls,power_calls,frame_calls,stream_calls,irq_calls,destroy_calls;
static int cam_sensor_apply_settings(struct cam_sensor_ctrl_t *s,int request,unsigned op){assert(held==1 && s==expected && !request && op==99);apply_calls++;return apply_error;}
static int cam_sensor_power_down(struct cam_sensor_ctrl_t *s){assert(held==1 && s==expected);power_calls++;return power_error;}
static void cam_sensor_release_per_frame_resource(struct cam_sensor_ctrl_t *s){assert(held==1 && s==expected);frame_calls++;}
static void cam_sensor_release_stream_rsc(struct cam_sensor_ctrl_t *s){assert(held==1 && s==expected);stream_calls++;}
static void cam_sensor_unregister_irq(struct cam_sensor_ctrl_t *s){assert(held==1 && s==expected);irq_calls++;}
static int cam_destroy_device_hdl(int h){assert(held==1 && h==42 && expected->bridge_intf.device_hdl==42);destroy_calls++;return destroy_error;}
'''
MAIN=r'''
int main(void){
 struct cam_sensor_ctrl_t sensor={.cam_sensor_mutex={PTHREAD_MUTEX_INITIALIZER},.bridge_intf={41,42,-1},.i2c_data={.streamoff_settings={true,0}},.sensor_state=2,.last_flush_req=55,.streamon_count=1,.streamoff_count=1};expected=&sensor;struct pico_memento_sensor target;
 assert(pico_memento_sensor_init(NULL,&sensor,41,42)==-EINVAL);assert(pico_memento_sensor_init(&target,&sensor,0,42)==-EINVAL);assert(!pico_memento_sensor_init(&target,&sensor,41,42));
 u32 acquire[6]={41,42,1,0,0,0},zero[2]={0};assert(pico_memento_sensor_rollback(&target,0x10009,0x104,zero,8)==-EINVAL);assert(pico_memento_sensor_rollback(&target,0x10001,0x106,acquire,8)==-EINVAL);acquire[0]=99;assert(pico_memento_sensor_rollback(&target,0x10001,0x106,acquire,24)==-EINVAL);acquire[0]=41;
 struct pico_memento state;pico_memento_init(&state);struct pico_memento_record *ticket=NULL;
 assert(!pico_memento_prepare(0x10001,VIDIOC_CAM_CONTROL,0x102,&ticket));assert(!pico_memento_commit(&state,&ticket,0x10001,0x102,acquire,24,0));assert(!pico_memento_prepare(0x10001,VIDIOC_CAM_CONTROL,0x103,&ticket));assert(!pico_memento_commit(&state,&ticket,0x10001,0x103,NULL,0,0));
 apply_error=-EIO;assert(pico_memento_cleanup(&state,pico_memento_sensor_rollback,&target)==-EIO && sensor.sensor_state==2 && apply_calls==1 && !frame_calls && !power_calls && !list_empty(&state.starts));
 apply_error=0;sensor.bridge_intf.link_hdl=7;assert(pico_memento_cleanup(&state,pico_memento_sensor_rollback,&target)==-EAGAIN && sensor.sensor_state==1 && apply_calls==2 && frame_calls==1 && !power_calls && list_empty(&state.starts) && !list_empty(&state.acquisitions));
 sensor.bridge_intf.link_hdl=-1;power_error=-EIO;assert(pico_memento_cleanup(&state,pico_memento_sensor_rollback,&target)==-EIO && power_calls==1 && !target.powered_down && !stream_calls && !destroy_calls);
 power_error=0;destroy_error=-EBUSY;assert(pico_memento_cleanup(&state,pico_memento_sensor_rollback,&target)==-EBUSY && power_calls==2 && target.powered_down && target.resources_released && frame_calls==2 && stream_calls==1 && irq_calls==1 && destroy_calls==1 && sensor.bridge_intf.device_hdl==42 && sensor.sensor_state==1 && !target.complete);
 assert(sensor.pico_release_cleanup_pending && sensor.pico_release_resources_done);
 destroy_error=0;assert(!pico_memento_cleanup(&state,pico_memento_sensor_rollback,&target) && destroy_calls==2 && power_calls==2 && frame_calls==2 && stream_calls==1 && irq_calls==1 && sensor.sensor_state==0 && sensor.bridge_intf.device_hdl==-1 && sensor.bridge_intf.session_hdl==-1 && !sensor.last_flush_req && !sensor.streamon_count && !sensor.streamoff_count && target.complete && !sensor.pico_release_cleanup_pending && !sensor.pico_release_resources_done && !live);
 assert(!pico_memento_cleanup(&state,pico_memento_sensor_rollback,&target) && destroy_calls==2);
 assert(pico_memento_sensor_rollback(&target,0x10001,0x106,acquire,24)==-EINVAL);
 assert(!pico_memento_sensor_init(&target,&sensor,41,42));assert(pico_memento_sensor_rollback(&target,0x10001,0x104,zero,8)==-EINVAL);
 sensor.bridge_intf.session_hdl=41;sensor.bridge_intf.device_hdl=42;sensor.sensor_state=1;sensor.pico_release_cleanup_pending=true;sensor.pico_release_resources_done=true;
 assert(!pico_memento_sensor_rollback(&target,0x10001,0x106,acquire,24) && frame_calls==2 && stream_calls==1 && irq_calls==1 && !sensor.pico_release_cleanup_pending && !sensor.pico_release_resources_done);assert(!held);
 puts("PASS: actual ledger/native sensor adapter, implicit stop keys and identity guards, streamoff/link/power failures retained, handle failure preserves phase and handles, retry skips repeated power/resource/IRQ cleanup, final state and exact ledger frees");
}
'''
def load(name):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name(name+'.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
def main():
    common=load('test-pico-camera-hub-registry');ledger=load('test-pico-camera-memento');body=(SOURCE/NAMES[3]).read_text()
    code=common.HARNESS.split('/* OWNED_SUBDEVICE_MOCKS */')[0]+ledger.MOCKS+MOCKS+body[body.index('struct pico_memento_record {'):]+(SOURCE/NAMES[0]).read_text()+MAIN
    out=BASE/'out/phoenix-kernel-recovery/memento-sensor-tests';out.mkdir(exist_ok=True);(out/'harness.c').write_text(code)
    subprocess.run(['gcc','-std=gnu11','-g','-O1','-pthread','-fsanitize=address,undefined','-fno-omit-frame-pointer',str(out/'harness.c'),'-o',str(out/'test')],check=True)
    result=subprocess.run([str(out/'test')],capture_output=True,text=True,timeout=30)
    report={'sources':{n:hashlib.sha256((SOURCE/n).read_bytes()).hexdigest() for n in NAMES},'harness_sha256':hashlib.sha256(code.encode()).hexdigest(),'exit_code':result.returncode,'stdout':result.stdout,'stderr':result.stderr,'sanitizers':['AddressSanitizer','UndefinedBehaviorSanitizer'],'scope':'Actual ledger and native phased sensor adapter; modeled I2C/power/IRQ/resource/handle APIs; no real driver hardware or subdevice close integration','device_modified':False}
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));raise SystemExit(result.returncode)
if __name__=='__main__':main()
