"""Actual native callbacks, paused after handle lookup before controller lock."""
from pathlib import Path
import hashlib,json,subprocess,importlib.util
BASE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro');SOURCE=BASE/'source/phoenix-kernel-recovery';NAME='techpack/camera/drivers/cam_sensor_module/cam_actuator/cam_actuator_core.c'
MOCKS=r'''
#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <pthread.h>
#include <errno.h>
#define CAM_ERR(...) ((void)0)
#define CAM_DBG(...) ((void)0)
#define CAM_ERR_RATE_LIMIT(...) ((void)0)
#define trace_cam_apply_req(...) ((void)0)
#define MAX_PER_FRAME_ARRAY 32
#define MAX_SYSTEM_PIPELINE_DELAY 2
#define CAM_REQ_MGR_FLUSH_TYPE_ALL 0
#define CAM_REQ_MGR_FLUSH_TYPE_CANCEL_REQ 1
struct mutex {pthread_mutex_t value;};static _Thread_local int held;
static void mutex_lock(struct mutex *m){assert(!pthread_mutex_lock(&m->value));held++;}
static void mutex_unlock(struct mutex *m){assert(held==1);held--;assert(!pthread_mutex_unlock(&m->value));}
struct i2c_settings_array {uint64_t request_id;int is_settings_valid;};
struct cam_actuator_ctrl_t {struct mutex actuator_mutex;struct {int device_hdl,link_hdl;void *crm_cb;}bridge_intf;bool pico_acquire_cleanup_pending,pico_release_cleanup_pending;struct {struct i2c_settings_array *per_frame;}i2c_data;uint64_t last_flush_req;};
struct cam_req_mgr_apply_request {int dev_hdl;uint64_t request_id;};
struct cam_req_mgr_flush_request {int dev_hdl;unsigned type;uint64_t req_id;};
struct cam_req_mgr_core_dev_link_setup {int dev_hdl,link_enable,link_hdl;void *crm_cb;};
static struct cam_actuator_ctrl_t ctrl={.actuator_mutex={PTHREAD_MUTEX_INITIALIZER}};
static pthread_mutex_t gate=PTHREAD_MUTEX_INITIALIZER;static pthread_cond_t changed=PTHREAD_COND_INITIALIZER;static bool pause_lookup,looked_up,resume_lookup;
static void *cam_get_device_priv(int h){assert(h==1234);assert(!pthread_mutex_lock(&gate));if(pause_lookup){looked_up=true;pthread_cond_broadcast(&changed);while(!resume_lookup)pthread_cond_wait(&changed,&gate);}pthread_mutex_unlock(&gate);return &ctrl;}
static _Thread_local unsigned borrowed;
static void *pico_cam_device_priv_get(int h,int *cookie){*cookie=0;borrowed++;return cam_get_device_priv(h);}
static void pico_cam_device_priv_put(int cookie){if(cookie>=0){assert(borrowed);borrowed--;}}
static unsigned writes,deletes;
static int cam_actuator_apply_settings(struct cam_actuator_ctrl_t *c,struct i2c_settings_array *s){assert(held==1);writes++;return 0;}
static int delete_request(struct i2c_settings_array *s){assert(held==1);deletes++;s->is_settings_valid=0;return 0;}
'''
CASES=r'''
static struct cam_req_mgr_apply_request apply={1234,5};static struct cam_req_mgr_flush_request flush={1234,CAM_REQ_MGR_FLUSH_TYPE_ALL,5};static struct cam_req_mgr_core_dev_link_setup link={1234,1,77,(void *)1};static int result,kind;
static void *callback(void *unused){result=kind==0?cam_actuator_apply_request(&apply):kind==1?cam_actuator_flush_request(&flush):cam_actuator_establish_link(&link);assert(!borrowed);return NULL;}
int main(void){struct i2c_settings_array frames[32]={0};ctrl.i2c_data.per_frame=frames;ctrl.bridge_intf.device_hdl=1234;frames[5].request_id=5;frames[5].is_settings_valid=1;
for(kind=0;kind<3;kind++){
 frames[5].is_settings_valid=1;ctrl.bridge_intf.device_hdl=1234;ctrl.bridge_intf.link_hdl=-1;ctrl.bridge_intf.crm_cb=NULL;ctrl.last_flush_req=0;writes=deletes=0;pause_lookup=true;looked_up=resume_lookup=false;
 pthread_t worker;assert(!pthread_create(&worker,NULL,callback,NULL));pthread_mutex_lock(&gate);while(!looked_up)pthread_cond_wait(&changed,&gate);pthread_mutex_unlock(&gate);
 /* The callback already owns a raw pointer, while release/reacquire changes
  * the handle on the same still-live controller before its mutex is taken. */
 mutex_lock(&ctrl.actuator_mutex);ctrl.bridge_intf.device_hdl=4321;mutex_unlock(&ctrl.actuator_mutex);
 pthread_mutex_lock(&gate);resume_lookup=true;pthread_cond_broadcast(&changed);pthread_mutex_unlock(&gate);assert(!pthread_join(worker,NULL));
 assert(result==-ENODEV&&!writes&&!deletes&&ctrl.bridge_intf.link_hdl==-1&&!ctrl.bridge_intf.crm_cb&&!ctrl.last_flush_req&&frames[5].is_settings_valid);
}
pause_lookup=false;ctrl.bridge_intf.device_hdl=1234;ctrl.pico_release_cleanup_pending=true;assert(cam_actuator_apply_request(&apply)==-EBUSY&&!writes);assert(cam_actuator_establish_link(&link)==-EBUSY&&!ctrl.bridge_intf.crm_cb);
link.link_enable=0;assert(!cam_actuator_establish_link(&link));ctrl.pico_release_cleanup_pending=false;
ctrl.i2c_data.per_frame=NULL;assert(cam_actuator_apply_request(&apply)==-EINVAL);assert(cam_actuator_flush_request(&flush)==-EINVAL);ctrl.i2c_data.per_frame=frames;
assert(!cam_actuator_apply_request(&apply)&&writes==1);assert(!cam_actuator_flush_request(&flush)&&ctrl.last_flush_req==5&&!frames[5].is_settings_valid);link.link_enable=1;assert(!cam_actuator_establish_link(&link)&&ctrl.bridge_intf.link_hdl==77&&ctrl.bridge_intf.crm_cb==(void *)1);
assert(!held&&!borrowed);puts("PASS: actual apply/flush/link callbacks; threaded lookup-to-lock handle replacement rejected without side effects, pending apply/link enable blocked, unlink retained, NULL frame guard and normal callbacks");}
'''
def main():
    spec=importlib.util.spec_from_file_location('extract',Path(__file__).with_name('test-pico-sensor-mono-hook.py'));ex=importlib.util.module_from_spec(spec);spec.loader.exec_module(ex);core=(SOURCE/NAME).read_text()
    code=MOCKS+'\n'.join(ex.function(core,s) for s in ['int32_t cam_actuator_apply_request(','int32_t cam_actuator_flush_request(','int32_t cam_actuator_establish_link('])+CASES
    out=BASE/'out/phoenix-kernel-recovery/actuator-callback-gates-tests';out.mkdir(exist_ok=True);(out/'harness.c').write_text(code)
    subprocess.run(['gcc','-std=gnu11','-g','-O1','-pthread','-fsanitize=address,undefined','-fno-omit-frame-pointer',str(out/'harness.c'),'-o',str(out/'test')],check=True)
    r=subprocess.run([str(out/'test')],capture_output=True,text=True,timeout=10);report={'sources':{NAME:hashlib.sha256((SOURCE/NAME).read_bytes()).hexdigest()},'harness_sha256':hashlib.sha256(code.encode()).hexdigest(),'exit_code':r.returncode,'stdout':r.stdout,'stderr':r.stderr,'scope':'Actual apply/flush/link callback bodies with pthread lookup-to-lock interleaving on a still-live controller; controller/request/list/handle lookup/bus providers modeled; raw-pointer physical remove lifetime/CRM global quiescence not solved','device_modified':False};(out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));raise SystemExit(r.returncode)
if __name__=='__main__':main()
