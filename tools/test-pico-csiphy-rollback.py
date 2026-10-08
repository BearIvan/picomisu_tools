"""Exercise recovered kernel-payload CSIPHY rollback and factory failure mutations."""
from pathlib import Path
import hashlib
import json
import subprocess
BASE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro')
SOURCE=BASE/'source/phoenix-kernel-recovery'
D='techpack/camera/drivers/cam_sensor_module/cam_csiphy/'
NAMES=[D+n for n in ['pico_csiphy_rollback.inc','cam_csiphy_core.c','cam_csiphy_core.h']]
MOCKS=r'''
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#define CAM_HANDLE_USER_POINTER 1
#define CAM_STOP_DEV 0x104
#define CAM_RELEASE_DEV 0x106
#define CAM_CSIPHY_INIT 0
#define CAM_CSIPHY_ACQUIRE 1
#define CAM_CSIPHY_START 2
#define CAM_SECURE_MODE_NON_SECURE 0
struct mutex {bool held;};
static void mutex_lock(struct mutex *m){assert(!m->held);m->held=true;}
static void mutex_unlock(struct mutex *m){assert(m->held);m->held=false;}
struct cam_control {uint32_t op_code,size,handle_type,reserved;uint64_t handle;};
struct cam_start_stop_dev_cmd {int32_t session_handle,dev_handle;};
struct info {unsigned secure_mode;uint64_t csiphy_cpas_cp_reg_mask;struct {int device_hdl,session_hdl;}hdl_data;int lane_cnt,lane_assign,csiphy_3phase;};
struct csiphy_device {struct mutex mutex;unsigned csiphy_state,acquire_count,start_dev_count,config_count,session_max_device_support;struct info csiphy_info[2];uint64_t csiphy_cpas_cp_reg_mask[2];unsigned combo_mode;int cpas_handle;};
static struct csiphy_device *expected;static int offset_error=-999,secure_error,disable_error,cpas_error,destroy_error,lane_error;
static unsigned secure_calls,disable_calls,cpas_calls,destroy_calls,lane_calls;static char order[32];static unsigned order_n;
static void note(char op){assert(expected->mutex.held && order_n<sizeof(order));order[order_n++]=op;}
static int cam_csiphy_get_instance_offset(struct csiphy_device *d,int handle){assert(d==expected && d->mutex.held);if(offset_error!=-999)return offset_error;for(int i=0;i<2;i++)if(d->csiphy_info[i].hdl_data.device_hdl==handle)return i;return -EINVAL;}
static int cam_csiphy_notify_secure_mode(struct csiphy_device *d,int mode,int slot){assert(d==expected && mode==0 && slot>=0 && slot<2);note('s');secure_calls++;return secure_error;}
static int cam_csiphy_update_lane(struct csiphy_device *d,int slot,bool on){assert(d==expected && !on && slot>=0 && slot<2);note('l');lane_calls++;return lane_error;}
static int cam_csiphy_disable_hw(struct csiphy_device *d){assert(d==expected);note('h');disable_calls++;return disable_error;}
static int cam_cpas_stop(int h){assert(h==expected->cpas_handle);note('p');cpas_calls++;return cpas_error;}
static int cam_destroy_device_hdl(int h){assert(h==42);note('d');destroy_calls++;return destroy_error;}
static void reset(struct csiphy_device *d){memset(d,0,sizeof(*d));d->csiphy_state=2;d->acquire_count=2;d->start_dev_count=2;d->config_count=2;d->session_max_device_support=2;d->combo_mode=1;d->cpas_handle=9;for(int i=0;i<2;i++){d->csiphy_info[i].hdl_data.device_hdl=42+i;d->csiphy_info[i].hdl_data.session_hdl=41;d->csiphy_info[i].secure_mode=1;d->csiphy_info[i].csiphy_cpas_cp_reg_mask=99;d->csiphy_info[i].lane_cnt=4;d->csiphy_info[i].lane_assign=5;d->csiphy_info[i].csiphy_3phase=1;d->csiphy_cpas_cp_reg_mask[i]=99;}expected=d;offset_error=-999;secure_error=disable_error=cpas_error=destroy_error=lane_error=0;secure_calls=disable_calls=cpas_calls=destroy_calls=lane_calls=order_n=0;memset(order,0,sizeof(order));}
'''
MAIN=r'''
int main(void){
 struct csiphy_device d;reset(&d);struct cam_start_stop_dev_cmd key={41,42};struct cam_control cmd={.op_code=CAM_STOP_DEV,.handle_type=1,.handle=(uintptr_t)&key};
 assert(rollback_cam_csiphy_core_cfg(NULL,&cmd)==-EINVAL);assert(rollback_cam_csiphy_core_cfg(&d,NULL)==-EINVAL);cmd.handle_type=2;assert(rollback_cam_csiphy_core_cfg(&d,&cmd)==-EINVAL);cmd.handle_type=1;cmd.handle=0;assert(rollback_cam_csiphy_core_cfg(&d,&cmd)==-EINVAL);cmd.op_code=0x105;assert(!rollback_cam_csiphy_core_cfg(&d,&cmd));cmd.op_code=CAM_STOP_DEV;cmd.handle=(uintptr_t)&key;
 d.csiphy_state=1;assert(rollback_cam_csiphy_core_cfg(&d,&cmd)==-EINVAL && !d.mutex.held);d.csiphy_state=2;offset_error=2;assert(rollback_cam_csiphy_core_cfg(&d,&cmd)==-EINVAL && d.start_dev_count==2);offset_error=-999;
 secure_error=-EIO;lane_error=-EAGAIN;assert(!rollback_cam_csiphy_core_cfg(&d,&cmd) && d.start_dev_count==1 && d.csiphy_state==2 && secure_calls==1 && lane_calls==1 && !disable_calls && !strcmp(order,"sl"));assert(!d.csiphy_info[0].secure_mode && !d.csiphy_info[0].csiphy_cpas_cp_reg_mask && d.csiphy_info[1].secure_mode==1);
 reset(&d);d.start_dev_count=1;disable_error=-EIO;assert(!rollback_cam_csiphy_core_cfg(&d,&cmd) && !d.start_dev_count && d.csiphy_state==1 && disable_calls==1 && cpas_calls==1 && !strcmp(order,"shp"));
 reset(&d);d.start_dev_count=1;cpas_error=-EAGAIN;assert(rollback_cam_csiphy_core_cfg(&d,&cmd)==-EAGAIN && !d.start_dev_count && d.csiphy_state==1 && cpas_calls==1);
 reset(&d);cmd.op_code=CAM_RELEASE_DEV;d.acquire_count=0;assert(rollback_cam_csiphy_core_cfg(&d,&cmd)==-EINVAL && !destroy_calls);reset(&d);offset_error=-1;assert(rollback_cam_csiphy_core_cfg(&d,&cmd)==-EINVAL && d.acquire_count==2 && !destroy_calls);
 reset(&d);assert(!rollback_cam_csiphy_core_cfg(&d,&cmd) && d.acquire_count==1 && d.config_count==1 && d.csiphy_state==2 && d.combo_mode==1 && d.csiphy_info[0].hdl_data.device_hdl==-1 && d.csiphy_info[0].hdl_data.session_hdl==-1 && !d.csiphy_cpas_cp_reg_mask[0] && d.csiphy_info[0].csiphy_cpas_cp_reg_mask==99 && !strcmp(order,"sd"));
 reset(&d);d.acquire_count=1;d.config_count=1;d.start_dev_count=0;destroy_error=-EIO;assert(rollback_cam_csiphy_core_cfg(&d,&cmd)==-EIO && !d.acquire_count && !d.config_count && d.csiphy_state==0 && !d.combo_mode && !d.csiphy_info[0].lane_cnt && !d.csiphy_info[0].lane_assign && d.csiphy_info[0].csiphy_3phase==-1 && destroy_calls==1);
 assert(!d.mutex.held);puts("PASS: actual kernel-payload CSIPHY rollback, input/state/slot guards, combo stop lane vs final hardware/CPAS, distinct secure masks, release handles/counters/reset, factory ignored secure/lane/disable errors and state advance after CPAS/handle errors");
}
'''
def main():
    body=(SOURCE/NAMES[0]).read_text();code=MOCKS+body+MAIN
    out=BASE/'out/phoenix-kernel-recovery/csiphy-rollback-tests';out.mkdir(exist_ok=True);(out/'harness.c').write_text(code)
    subprocess.run(['gcc','-std=gnu11','-g','-O1','-fsanitize=address,undefined','-fno-omit-frame-pointer',str(out/'harness.c'),'-o',str(out/'test')],check=True)
    result=subprocess.run([str(out/'test')],capture_output=True,text=True,timeout=30)
    report={'sources':{n:hashlib.sha256((SOURCE/n).read_bytes()).hexdigest() for n in NAMES},'harness_sha256':hashlib.sha256(code.encode()).hexdigest(),'exit_code':result.returncode,'stdout':result.stdout,'stderr':result.stderr,'sanitizers':['AddressSanitizer','UndefinedBehaviorSanitizer'],'scope':'Actual recovered kernel rollback body with modeled CSIPHY state/mutex and hardware/secure/lane/CPAS/handle callbacks; failure mutations verified, not safe retry integration or hardware runtime','device_modified':False}
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));raise SystemExit(result.returncode)
if __name__=='__main__':main()
