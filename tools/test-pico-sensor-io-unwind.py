"""Actual power-up/I-O-init/capture functions with lower hardware APIs modeled."""
from pathlib import Path
import hashlib,importlib.util,json,subprocess
BASE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro');SOURCE=BASE/'source/phoenix-kernel-recovery'
NAMES=['techpack/camera/drivers/cam_sensor_module/cam_sensor/cam_sensor_core.c','techpack/camera/drivers/cam_sensor_module/cam_sensor_io/cam_sensor_io.c']+['techpack/camera/drivers/cam_core/pico_camera_memento_capture.'+e for e in ['c','h']]
MOCKS=r'''
#include <stdint.h>
#include <string.h>
typedef unsigned char u8;
#define CAM_ACQUIRE_DEV 0x102
#define CAM_START_DEV 0x103
#define CAM_STOP_DEV 0x104
#define CAM_RELEASE_DEV 0x106
#define CAM_ERR(...) ((void)0)
#define CAM_WARN(...) ((void)0)
#define CAM_SENSOR 0
#define NEO25_FOUR_6DOF_CAMERAS_SUPPORT 1
#define CCI_MASTER 1
#define I2C_MASTER 2
#define SPI_MASTER 3
#define MSM_CCI_INIT 99
struct task_struct {int id;};static struct task_struct task={1};static struct task_struct *current=&task;
struct pico_memento_capture {struct list_head list;struct task_struct *task;const void *owner;u32 entity,opcode;u8 packet[24];size_t bytes;int native_result,error,unwind_result;bool captured,side_effect,unwound,power_cleanup_attempted;int power_cleanup_result;};
struct cam_sensor_power_ctrl_t {int marker;};struct cam_camera_slave_info {int sensor_id;};struct cam_hw_soc_info {int marker;};
struct cci_client {void *cci_subdev;int cci_device;};struct camera_io_master {int master_type;struct cci_client *cci_client;};
struct cam_sensor_ctrl_t {struct mutex mutex;struct {struct cam_sensor_power_ctrl_t power_info;struct cam_camera_slave_info slave_info;} *sensordata;struct cam_hw_soc_info soc_info;struct camera_io_master io_master_info;bool bob_pwm_switch;int bob_reg_index;bool pico_core_powered,pico_io_initialized,pico_bob_pending;};
static struct cam_sensor_ctrl_t *expected;static int core_result,io_result,cleanup_result,bob_result;static unsigned core_calls,cci_calls,cleanup_calls,private_calls,bob_on,bob_off;
static int cam_sensor_core_power_up(struct cam_sensor_power_ctrl_t *p,struct cam_hw_soc_info *s){assert(held==1 && p==&expected->sensordata->power_info && s==&expected->soc_info);core_calls++;return core_result;}
static int cam_sensor_util_power_down(struct cam_sensor_power_ctrl_t *p,struct cam_hw_soc_info *s){assert(held==1 && p==&expected->sensordata->power_info && s==&expected->soc_info);cleanup_calls++;return cleanup_result;}
static int cam_sensor_bob_pwm_mode_switch(struct cam_hw_soc_info *s,int idx,bool on){assert(held==1 && s==&expected->soc_info && idx==7);if(on)bob_on++;else bob_off++;return bob_result;}
static void *cam_cci_get_subdev(int dev){assert(held==1 && dev==4);return (void *)123;}
static int cam_sensor_cci_i2c_util(struct cci_client *c,int op){assert(held==1 && c==expected->io_master_info.cci_client && c->cci_subdev==(void *)123 && op==99);cci_calls++;return io_result;}
static void cam_change_sensor_private_slave_address(struct cam_sensor_ctrl_t *s){assert(held==1 && s==expected);private_calls++;}
'''
MAIN=r'''
static void begin(struct pico_memento_capture *s,struct cam_sensor_ctrl_t *sensor){sensor->pico_core_powered=sensor->pico_io_initialized=sensor->pico_bob_pending=false;u32 packet[6]={41,1234,1,0,0,0};assert(!pico_memento_capture_begin(s,sensor,0x10001,CAM_ACQUIRE_DEV));pico_memento_capture_native(sensor,0x10001,CAM_ACQUIRE_DEV,packet,24,0,true);}
static int powerup(struct cam_sensor_ctrl_t *s){mutex_lock(&s->mutex);int rc=cam_sensor_power_up(s);mutex_unlock(&s->mutex);return rc;}
int main(void){
 struct cam_sensor_ctrl_t sensor={.mutex={PTHREAD_MUTEX_INITIALIZER}};__typeof__(*sensor.sensordata) data={.slave_info={0x6710}};struct cci_client client={.cci_device=4};sensor.sensordata=&data;sensor.io_master_info.master_type=CCI_MASTER;sensor.io_master_info.cci_client=&client;expected=&sensor;struct pico_memento_capture scope;
 assert(!powerup(&sensor) && core_calls==1 && cci_calls==1 && private_calls==1 && !cleanup_calls);
 begin(&scope,&sensor);core_result=-EIO;assert(powerup(&sensor)==-EIO && core_calls==2 && cci_calls==1 && !cleanup_calls);assert(!pico_memento_capture_end(&scope) && !scope.power_cleanup_attempted && !scope.unwound);core_result=0;
 begin(&scope,&sensor);io_result=-ENODEV;assert(powerup(&sensor)==-ENODEV && cleanup_calls==1 && private_calls==1);assert(!pico_memento_capture_end(&scope) && scope.power_cleanup_attempted && !scope.power_cleanup_result && scope.side_effect && !scope.unwound);
 begin(&scope,&sensor);cleanup_result=-EBUSY;assert(powerup(&sensor)==-ENODEV && cleanup_calls==2 && private_calls==1);assert(!pico_memento_capture_end(&scope) && scope.power_cleanup_attempted && scope.power_cleanup_result==-EBUSY && !scope.unwound);
 cleanup_result=0;sensor.bob_pwm_switch=true;sensor.bob_reg_index=7;begin(&scope,&sensor);assert(powerup(&sensor)==-ENODEV && cleanup_calls==3 && bob_on==1 && bob_off==1);assert(!pico_memento_capture_end(&scope));
 cleanup_result=-EBUSY;begin(&scope,&sensor);assert(powerup(&sensor)==-ENODEV && cleanup_calls==4 && bob_on==2 && bob_off==1);assert(!pico_memento_capture_end(&scope));
 sensor.pico_core_powered=sensor.pico_io_initialized=sensor.pico_bob_pending=false;sensor.bob_pwm_switch=false;sensor.io_master_info.master_type=I2C_MASTER;io_result=0;assert(!powerup(&sensor) && cleanup_calls==4 && private_calls==2);
 sensor.pico_core_powered=sensor.pico_io_initialized=sensor.pico_bob_pending=false;sensor.io_master_info.master_type=0;cleanup_result=0;assert(powerup(&sensor)==-EINVAL && cleanup_calls==5 && private_calls==2);assert(list_empty(&pico_memento_captures) && !held);
 puts("PASS: actual sensor power_up/camera_io_init/capture, core failure vs CCI failure, core cleanup success/failure preserves original init errno, no private-address call on failed init, separate power-only status without full-unwind claim, BoB restore gating and I2C/invalid-master paths");
}
'''
def main():
    spec=importlib.util.spec_from_file_location('registry',Path(__file__).with_name('test-pico-camera-hub-registry.py'));common=importlib.util.module_from_spec(spec);spec.loader.exec_module(common)
    prefix=common.HARNESS.split('/* OWNED_SUBDEVICE_MOCKS */')[0].replace('assert(!held);assert(!pthread_mutex_lock','assert(!pthread_mutex_lock').replace('assert(held==1);held--;','assert(held>0);held--;')
    native=(SOURCE/NAMES[0]).read_text();power=native[native.index('int cam_sensor_power_up('):native.index('int cam_sensor_power_down(')]
    io=(SOURCE/NAMES[1]).read_text();init=io[io.index('int32_t camera_io_init('):io.index('int32_t camera_io_release(')]
    capture=(SOURCE/NAMES[2]).read_text();code=prefix+MOCKS+capture[capture.index('static DEFINE_MUTEX'):]+init+power+MAIN
    out=BASE/'out/phoenix-kernel-recovery/sensor-io-unwind-tests';out.mkdir(exist_ok=True);(out/'harness.c').write_text(code)
    subprocess.run(['gcc','-std=gnu11','-g','-O1','-pthread','-fsanitize=address,undefined','-fno-omit-frame-pointer',str(out/'harness.c'),'-o',str(out/'test')],check=True)
    result=subprocess.run([str(out/'test')],capture_output=True,text=True,timeout=30)
    report={'sources':{n:hashlib.sha256((SOURCE/n).read_bytes()).hexdigest() for n in NAMES},'harness_sha256':hashlib.sha256(code.encode()).hexdigest(),'exit_code':result.returncode,'stdout':result.stdout,'stderr':result.stderr,'sanitizers':['AddressSanitizer','UndefinedBehaviorSanitizer'],'scope':'Actual power_up/camera_io_init/capture bodies; core power/CCI/BoB/private-address APIs modeled; core cleanup status only, remaining IRQ/handle/full acquire cleanup and hardware validation pending','device_modified':False}
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));raise SystemExit(result.returncode)
if __name__=='__main__':main()
