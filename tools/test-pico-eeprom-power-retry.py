"""Actual EEPROM power helpers/release/shutdown/adapter and parser cleanup tails."""
from pathlib import Path
import hashlib,json,subprocess,importlib.util
BASE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro');SOURCE=BASE/'source/phoenix-kernel-recovery';D='techpack/camera/drivers/cam_sensor_module/cam_eeprom/'
NAMES=[D+n for n in ['cam_eeprom_core.c','cam_eeprom_dev.h','pico_memento_eeprom.inc','pico_eeprom_acquire_unwind.inc']]+['techpack/camera/include/uapi/media/'+n for n in ['cam_defs.h','cam_sensor.h']]
def load(name):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name(name+'.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
MOCKS=r'''
typedef int32_t s32;
#define CCI_MASTER 1
#define CAM_ERR(...) ((void)0)
#define CAM_DBG(...) ((void)0)
#define CAM_WARN(...) ((void)0)
#define u64_to_user_ptr(p) ((void *)(uintptr_t)(p))
struct cam_hw_soc_info {void *dev,*soc_private;int index;};
struct cam_sensor_power_ctrl_t {void *dev,*power_setting,*power_down_setting;unsigned power_setting_size,power_down_setting_size;};
struct cam_eeprom_soc_private {struct cam_sensor_power_ctrl_t power_info;};
struct camera_io_master {int master_type;};
struct cam_eeprom_ctrl_t {struct mutex eeprom_mutex;struct {int device_hdl,session_hdl,link_hdl,ops;}bridge_intf;enum cam_eeprom_state cam_eeprom_state;bool pico_acquire_cleanup_pending,pico_core_powered,pico_io_initialized,pico_transaction_cleanup_pending,userspace_probe,is_multimodule_mode;struct cam_hw_soc_info soc_info;struct camera_io_master io_master_info;struct {void *mapdata,*map;unsigned num_data,num_map;}cal_data;struct {int is_settings_valid;}wr_settings;};
struct pico_memento_eeprom {struct cam_eeprom_ctrl_t *eeprom;s32 session,device;bool complete;};
static int core_up_error,core_down_error,io_init_error,io_release_error,destroy_error,fill_error;
static unsigned ups,downs,inits,releases,destroys,frees,configs;
static int msm_camera_fill_vreg_params(struct cam_hw_soc_info *soc,void *p,unsigned n){return fill_error;}
static int cam_sensor_core_power_up(struct cam_sensor_power_ctrl_t *p,struct cam_hw_soc_info *soc){ups++;return core_up_error;}
static int cam_sensor_util_power_down(struct cam_sensor_power_ctrl_t *p,struct cam_hw_soc_info *soc){downs++;return core_down_error;}
static int camera_io_init(struct camera_io_master *io){inits++;return io_init_error;}
static int camera_io_release(struct camera_io_master *io){releases++;return io_release_error;}
static int cam_destroy_device_hdl(int handle){assert(held==1&&handle==1234);destroys++;return destroy_error;}
static int cam_eeprom_get_dev_handle(struct cam_eeprom_ctrl_t *c,void *arg){assert(0);return -EINVAL;}
static int cam_eeprom_pkt_parse(struct cam_eeprom_ctrl_t *c,void *arg){configs++;return 0;}
static int copy_to_user(void *dst,const void *src,size_t n){memcpy(dst,src,n);return 0;}
static void kfree(void *p){if(p){frees++;free(p);}}
static int32_t delete_eeprom_request(void *s){assert(0);return 0;}
#define vfree kfree
'''
MAIN=r'''
static void allocations(struct cam_eeprom_ctrl_t *c,struct cam_sensor_power_ctrl_t *p){p->power_setting=malloc(8);p->power_down_setting=malloc(8);c->cal_data.map=malloc(8);c->cal_data.mapdata=malloc(8);p->power_setting_size=p->power_down_setting_size=1;c->cal_data.num_data=c->cal_data.num_map=1;assert(p->power_setting&&p->power_down_setting&&c->cal_data.map&&c->cal_data.mapdata);}
int main(void){
 struct cam_eeprom_soc_private private={0};struct cam_eeprom_ctrl_t c={.eeprom_mutex={PTHREAD_MUTEX_INITIALIZER},.bridge_intf={1234,41,-1,0},.cam_eeprom_state=CAM_EEPROM_ACQUIRE,.soc_info={.soc_private=&private},.io_master_info={CCI_MASTER}};struct cam_sensor_power_ctrl_t *p=&private.power_info;
 fill_error=-ERANGE;assert(cam_eeprom_power_up(&c,p)==-ERANGE&&!ups&&!c.pico_core_powered);fill_error=0;
 core_up_error=-EIO;assert(cam_eeprom_power_up(&c,p)==-EIO&&ups==1&&!inits&&!c.pico_core_powered);core_up_error=0;
 io_init_error=-ENXIO;assert(cam_eeprom_power_up(&c,p)==-ENXIO&&downs==1&&!c.pico_core_powered&&!c.pico_io_initialized);
 core_down_error=-EBUSY;assert(cam_eeprom_power_up(&c,p)==-ENXIO&&downs==2&&c.pico_core_powered&&!c.pico_io_initialized);assert(cam_eeprom_power_up(&c,p)==-EBUSY&&ups==3);
 allocations(&c,p);assert(parser_cleanup(&c)==-EIO&&c.pico_transaction_cleanup_pending&&c.cam_eeprom_state==CAM_EEPROM_CONFIG&&!frees&&p->power_setting);
 struct cam_control cmd={.op_code=CAM_CONFIG_DEV,.handle_type=CAM_HANDLE_USER_POINTER};assert(cam_eeprom_driver_cmd(&c,&cmd)==-EBUSY&&!configs);
 cmd.op_code=CAM_RELEASE_DEV;assert(cam_eeprom_driver_cmd(&c,&cmd)==-EBUSY&&c.pico_core_powered&&!destroys&&!frees);
 core_down_error=0;destroy_error=-EINVAL;assert(cam_eeprom_driver_cmd(&c,&cmd)==-EINVAL&&!c.pico_core_powered&&c.pico_transaction_cleanup_pending&&c.cam_eeprom_state==CAM_EEPROM_ACQUIRE&&!frees);unsigned done_downs=downs;
 destroy_error=0;assert(!cam_eeprom_driver_cmd(&c,&cmd)&&downs==done_downs&&frees==4&&!c.pico_transaction_cleanup_pending&&c.bridge_intf.device_hdl==-1);
 io_init_error=0;c.bridge_intf.device_hdl=1234;c.bridge_intf.session_hdl=41;c.cam_eeprom_state=CAM_EEPROM_ACQUIRE;allocations(&c,p);assert(!cam_eeprom_power_up(&c,p)&&c.pico_core_powered&&c.pico_io_initialized);
 io_release_error=-EAGAIN;assert(cam_eeprom_power_down(&c)==-EAGAIN&&!c.pico_core_powered&&c.pico_io_initialized);done_downs=downs;unsigned done_releases=releases;
 assert(cam_eeprom_power_down(&c)==-EAGAIN&&downs==done_downs&&releases==done_releases+1);assert(parser_cleanup(&c)==-EIO&&c.pico_io_initialized&&c.pico_transaction_cleanup_pending&&frees==4);
 struct pico_memento_eeprom target;assert(!pico_memento_eeprom_init(&target,&c,41,1234));u32 packet[6]={41,1234},stop[2]={0};c.bridge_intf.link_hdl=7;
 assert(!pico_memento_eeprom_rollback(&target,0x1000c,CAM_STOP_DEV,stop,8));assert(pico_memento_eeprom_rollback(&target,0x1000c,CAM_RELEASE_DEV,packet,24)==-EAGAIN&&releases==done_releases+1);
 c.bridge_intf.link_hdl=-1;assert(pico_memento_eeprom_rollback(&target,0x1000c,CAM_RELEASE_DEV,packet,24)==-EAGAIN&&c.pico_io_initialized&&!target.complete);
 io_release_error=0;destroy_error=-EINVAL;assert(pico_memento_eeprom_rollback(&target,0x1000c,CAM_RELEASE_DEV,packet,24)==-EINVAL&&!c.pico_io_initialized&&!target.complete&&frees==4);done_releases=releases;
 destroy_error=0;assert(!pico_memento_eeprom_rollback(&target,0x1000c,CAM_RELEASE_DEV,packet,24)&&target.complete&&downs==done_downs&&releases==done_releases&&frees==8&&!c.pico_transaction_cleanup_pending);
 c.bridge_intf.device_hdl=1234;c.bridge_intf.session_hdl=41;c.cam_eeprom_state=CAM_EEPROM_ACQUIRE;c.io_master_info.master_type=0;allocations(&c,p);assert(!cam_eeprom_power_up(&c,p)&&c.pico_core_powered&&!c.pico_io_initialized);
 done_releases=releases;mutex_lock(&c.eeprom_mutex);cam_eeprom_shutdown(&c);mutex_unlock(&c.eeprom_mutex);assert(!c.pico_core_powered&&releases==done_releases&&frees==12&&c.cam_eeprom_state==CAM_EEPROM_INIT);
 assert(!held);assert(!pthread_mutex_destroy(&c.eeprom_mutex.value));puts("PASS: actual EEPROM core/I-O helpers, parser cleanup tail, native release/config gate, memento and shutdown; init unwind/error priority, retained allocations, core and I/O retry phases, linked/STOP guards, no duplicate completed provider stages, non-CCI path");
}
'''
def main():
    common=load('test-pico-camera-hub-registry');extract=load('test-pico-sensor-mono-hook');core=(SOURCE/NAMES[0]).read_text();header=(SOURCE/NAMES[1]).read_text();states=header[header.index('enum cam_eeprom_state {'):header.index('};',header.index('enum cam_eeprom_state {'))+2]
    parser=extract.function(core,'static int32_t cam_eeprom_pkt_parse_owned(');tail=parser[parser.index('memdata_free:\n'):]
    cleanup='static int parser_cleanup(struct cam_eeprom_ctrl_t *e_ctrl){int rc=-EIO;struct cam_eeprom_soc_private *private=e_ctrl->soc_info.soc_private;struct cam_sensor_power_ctrl_t *power_info=&private->power_info;goto memdata_free;\n'+tail
    prefix=common.HARNESS.split('/* OWNED_SUBDEVICE_MOCKS */')[0]
    code='#include <stdint.h>\n#include <stddef.h>\n#include <string.h>\n#include <cam_defs.h>\n#include <cam_sensor.h>\n'+prefix+states+MOCKS+extract.function(core,'static int cam_eeprom_power_up(')+extract.function(core,'static int cam_eeprom_power_down(')+extract.function(core,'static void pico_eeprom_free_transaction(')+(SOURCE/NAMES[3]).read_text()+extract.function(core,'int32_t cam_eeprom_driver_cmd(')+extract.function(core,'void cam_eeprom_shutdown(')+(SOURCE/NAMES[2]).read_text()+cleanup+MAIN
    out=BASE/'out/phoenix-kernel-recovery/eeprom-power-retry-tests';out.mkdir(exist_ok=True);(out/'harness.c').write_text(code)
    subprocess.run(['gcc','-std=gnu11','-g','-O1','-pthread','-fsanitize=address,undefined','-fno-omit-frame-pointer','-I'+str(SOURCE/'techpack/camera/include/uapi/media'),'-I'+str(SOURCE/'techpack/camera/include/uapi'),str(out/'harness.c'),'-o',str(out/'test')],check=True)
    r=subprocess.run([str(out/'test')],capture_output=True,text=True,timeout=30);report={'sources':{n:hashlib.sha256((SOURCE/n).read_bytes()).hexdigest() for n in NAMES},'harness_sha256':hashlib.sha256(code.encode()).hexdigest(),'exit_code':r.returncode,'stdout':r.stdout,'stderr':r.stderr,'sanitizers':['AddressSanitizer','UndefinedBehaviorSanitizer'],'scope':'Actual power helpers/free helper/native release/shutdown/memento and userspace parser cleanup tail, native state/UAPI; lower power/CCI/handle APIs and parser body modeled; DT/success/write parser error paths not exercised end-to-end, lower-provider partial side effects, removal/hardware pending','device_modified':False};(out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));raise SystemExit(r.returncode)
if __name__=='__main__':main()
