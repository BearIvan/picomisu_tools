"""Actual shutdown/memento/list deletion with allocated native request nodes."""
from pathlib import Path
import hashlib,json,re,subprocess,importlib.util
def load(name):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name(name+'.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
p=load('test-pico-eeprom-write-payload');BASE=p.BASE;SOURCE=p.SOURCE;D='techpack/camera/drivers/cam_sensor_module/cam_actuator/'
NAMES=[D+'cam_actuator_core.c',D+'cam_actuator_dev.h',D+'pico_memento_actuator.inc','techpack/camera/drivers/cam_sensor_module/cam_sensor_utils/cam_sensor_util.c',p.NAMES[4],p.NAMES[5],p.NAMES[6]]
def main():
    ex=load('test-pico-sensor-mono-hook');common=load('test-pico-camera-hub-registry');cmn=(SOURCE/NAMES[4]).read_text();hdr=(SOURCE/NAMES[1]).read_text();core=(SOURCE/NAMES[0]).read_text()
    enums='\n'.join(re.search(r'enum '+n+r' \{.*?\n\};',cmn,re.S).group(0) for n in ['camera_sensor_i2c_type','cam_sensor_i2c_cmd_type'])+re.search(r'enum cam_actuator_state \{.*?\n\};',hdr,re.S).group(0)
    structs='\n'.join(re.search(r'struct '+n+r' \{.*?\n\};',cmn,re.S).group(0) for n in ['cam_sensor_i2c_reg_array','cam_sensor_i2c_reg_setting','cam_sensor_i2c_seq_reg','i2c_settings_list','i2c_settings_array'])
    mocks=r'''
#define CAM_ERR(...) ((void)0)
#define CAM_WARN(...) ((void)0)
#define MAX_PER_FRAME_ARRAY 4
#define GFP_KERNEL 0
#define list_for_each_entry_safe(p,t,h,m) for(struct list_head *cur=(h)->next,*next;cur!=(h)&&((next=cur->next),(p)=container_of(cur,__typeof__(*(p)),m),1);cur=next)
#define list_del(p) list_del_init(p)
static unsigned live,powers,destroys;static int power_error,destroy_error;
static void *kzalloc(size_t n,int flags){void *p=calloc(1,n);assert(p);live++;return p;}
static void kfree(void *p){if(p){assert(live);live--;free(p);}}
static void vfree(void *p){kfree(p);}
struct cam_sensor_power_ctrl_t {void *power_setting,*power_down_setting;unsigned power_setting_size,power_down_setting_size;};
struct cam_actuator_soc_private {struct cam_sensor_power_ctrl_t power_info;};
struct cam_actuator_ctrl_t {struct mutex actuator_mutex;struct {int device_hdl,session_hdl,link_hdl;}bridge_intf;struct {void *soc_private;}soc_info;enum cam_actuator_state cam_act_state;bool pico_acquire_cleanup_pending,pico_release_cleanup_pending,pico_release_power_done,pico_core_powered,pico_io_initialized;unsigned last_flush_req;struct {struct i2c_settings_array init_settings;struct i2c_settings_array *per_frame;}i2c_data;};
struct pico_memento_actuator {struct cam_actuator_ctrl_t *actuator;s32 session,device;bool powered_down,complete;};
static int cam_actuator_power_down(struct cam_actuator_ctrl_t *c){assert(held==1);powers++;return power_error;}
static int cam_destroy_device_hdl(int h){assert(held==1&&h==1234);destroys++;return destroy_error;}
static int pico_actuator_acquire_unwind_locked(struct cam_actuator_ctrl_t *c){assert(0);return -EINVAL;}
'''
    body=ex.function((SOURCE/NAMES[3]).read_text(),'int32_t delete_request(')
    if 'static void pico_actuator_clear_requests_locked(' in core:body+=ex.function(core,'static void pico_actuator_clear_requests_locked(')
    body+=ex.function(core,'void cam_actuator_shutdown(')+(SOURCE/NAMES[2]).read_text()
    release_start=core.index('\tcase CAM_RELEASE_DEV:',core.index('int32_t cam_actuator_driver_cmd('));release_end=core.index('\tcase CAM_QUERY_CAP:',release_start)
    body+='static int native_release(struct cam_actuator_ctrl_t *a_ctrl){int rc=0;struct cam_actuator_soc_private *soc=a_ctrl->soc_info.soc_private;struct cam_sensor_power_ctrl_t *power_info=&soc->power_info;mutex_lock(&a_ctrl->actuator_mutex);switch(CAM_RELEASE_DEV){'+core[release_start:release_end]+'}release_mutex:mutex_unlock(&a_ctrl->actuator_mutex);return rc;}\n'
    cases=r'''
static void add(struct i2c_settings_array *a,int valid){struct i2c_settings_list *n=kzalloc(sizeof(*n),0);n->i2c_settings.reg_setting=kzalloc(2*sizeof(struct cam_sensor_i2c_reg_array),0);list_add(&n->list,&a->list_head);a->is_settings_valid=valid;a->request_id=31;}
static void setup(struct cam_actuator_ctrl_t *c,struct cam_actuator_soc_private *soc,struct i2c_settings_array *frames){c->soc_info.soc_private=soc;c->bridge_intf.device_hdl=1234;c->bridge_intf.session_hdl=41;c->bridge_intf.link_hdl=-1;c->cam_act_state=CAM_ACTUATOR_CONFIG;c->i2c_data.per_frame=frames;INIT_LIST_HEAD(&c->i2c_data.init_settings.list_head);for(unsigned i=0;i<4;i++)INIT_LIST_HEAD(&frames[i].list_head);add(&c->i2c_data.init_settings,0);add(&frames[0],1);add(&frames[3],0);soc->power_info.power_setting=kzalloc(8,0);soc->power_info.power_down_setting=kzalloc(8,0);}
static void shutdown(struct cam_actuator_ctrl_t *c){mutex_lock(&c->actuator_mutex);cam_actuator_shutdown(c);mutex_unlock(&c->actuator_mutex);}
static void empty(struct cam_actuator_ctrl_t *c){assert(!live&&list_empty(&c->i2c_data.init_settings.list_head)&&!c->i2c_data.init_settings.request_id);for(unsigned i=0;i<4;i++)assert(list_empty(&c->i2c_data.per_frame[i].list_head)&&!c->i2c_data.per_frame[i].is_settings_valid&&!c->i2c_data.per_frame[i].request_id);}
int main(void){struct cam_actuator_ctrl_t c={.actuator_mutex={PTHREAD_MUTEX_INITIALIZER}};struct cam_actuator_soc_private soc={0};struct i2c_settings_array frames[4]={0};setup(&c,&soc,frames);assert(live==8);power_error=-EIO;shutdown(&c);assert(live==8&&!destroys);power_error=0;destroy_error=-EAGAIN;shutdown(&c);assert(live==8&&c.pico_release_power_done);destroy_error=0;shutdown(&c);empty(&c);unsigned before=powers;shutdown(&c);assert(powers==before);
setup(&c,&soc,frames);struct pico_memento_actuator target;u32 packet[6]={41,1234};assert(!pico_memento_actuator_init(&target,&c,41,1234));destroy_error=-EIO;assert(pico_memento_actuator_rollback(&target,0x10009,CAM_RELEASE_DEV,packet,24)==-EIO&&live==8);destroy_error=0;assert(!pico_memento_actuator_rollback(&target,0x10009,CAM_RELEASE_DEV,packet,24)&&target.complete);empty(&c);assert(!held);assert(!pthread_mutex_destroy(&c.actuator_mutex.value));puts("PASS: actual shutdown/memento/common drain/native delete_request with allocated init/per-frame nodes; failed power/handle retains settings; valid and partial invalid lists drained once, initialized heads retained, repeated shutdown safe");}
'''
    cases=cases.replace('assert(!held);assert(!pthread_mutex_destroy', 'setup(&c,&soc,frames);destroy_error=-EIO;assert(native_release(&c)==-EIO&&live==8);destroy_error=0;assert(!native_release(&c));empty(&c);assert(!held);assert(!pthread_mutex_destroy')
    code='#include <stdint.h>\n#include <stddef.h>\n#include <string.h>\n#include <cam_defs.h>\n#include <cam_sensor.h>\ntypedef int32_t s32;\n'+common.HARNESS.split('/* OWNED_SUBDEVICE_MOCKS */')[0]+enums+structs+mocks+body+cases
    out=BASE/'out/phoenix-kernel-recovery/actuator-request-cleanup-tests';out.mkdir(exist_ok=True);(out/'harness.c').write_text(code)
    subprocess.run(['gcc','-std=gnu11','-g','-O1','-pthread','-fsanitize=address,undefined','-fno-omit-frame-pointer','-I'+str(SOURCE/'techpack/camera/include/uapi/media'),'-I'+str(SOURCE/'techpack/camera/include/uapi'),str(out/'harness.c'),'-o',str(out/'test')],check=True)
    r=subprocess.run([str(out/'test')],capture_output=True,text=True,timeout=10);report={'sources':{n:hashlib.sha256((SOURCE/n).read_bytes()).hexdigest() for n in NAMES},'harness_sha256':hashlib.sha256(code.encode()).hexdigest(),'exit_code':r.returncode,'stdout':r.stdout,'stderr':r.stderr,'sanitizers':['AddressSanitizer','UndefinedBehaviorSanitizer'],'scope':'Actual native release case/shutdown/memento/common drain/native delete_request with native settings/list types and allocated nodes; array capacity4/power/handle APIs/controller modeled, physical remove/CRM callback lifetime/factory runtime pending','device_modified':False};(out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));raise SystemExit(r.returncode)
if __name__=='__main__':main()
