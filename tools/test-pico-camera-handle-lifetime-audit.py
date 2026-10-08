"""Reproduce native handle retirement without a pin; diagnostic, not a fix."""
from pathlib import Path
import hashlib,json,re,subprocess,importlib.util
BASE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro');SOURCE=BASE/'source/phoenix-kernel-recovery';D='techpack/camera/drivers/cam_req_mgr/'
NAMES=[D+'cam_req_mgr_util.c',D+'cam_req_mgr_util.h',D+'cam_req_mgr_util_priv.h',D+'cam_req_mgr_core.c','techpack/camera/drivers/cam_sensor_module/cam_actuator/cam_actuator_dev.c','techpack/camera/drivers/cam_sensor_module/cam_actuator/cam_actuator_core.c']
MOCKS=r'''
#include <assert.h>
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <stdbool.h>
#include <pthread.h>
#include <errno.h>
#define CAM_ERR(...) ((void)0)
#define CAM_ERR_RATE_LIMIT(...) ((void)0)
#define CAM_REQ_MGR_MAX_HANDLES_V2 256
#define CAM_REQ_MGR_HDL_IDX_POS 8
#define CAM_REQ_MGR_HDL_IDX_MASK 255
static pthread_mutex_t hdl_tbl_lock=PTHREAD_MUTEX_INITIALIZER;
#define spin_lock_bh(p) assert(!pthread_mutex_lock(p))
#define spin_unlock_bh(p) assert(!pthread_mutex_unlock(p))
static unsigned cleared;
static void clear_bit(int idx,void *map){assert(idx==3);cleared++;}
'''
MAIN=r'''
static pthread_mutex_t gate=PTHREAD_MUTEX_INITIALIZER;static pthread_cond_t changed=PTHREAD_COND_INITIALIZER;static bool returned,resume;static int handle_value;static int *borrowed;
static void *callback(void *unused){int *ptr=cam_get_device_priv(handle_value);assert(ptr);pthread_mutex_lock(&gate);borrowed=ptr;returned=true;pthread_cond_broadcast(&changed);while(!resume)pthread_cond_wait(&changed,&gate);pthread_mutex_unlock(&gate);/* Native lookup has returned an unpinned pointer. */volatile int value=*ptr;assert(value==73);return NULL;}
int main(int argc,char **argv){struct cam_req_mgr_util_hdl_tbl table={0};hdl_tbl=&table;handle_value=GET_DEV_HANDLE(11,HDL_TYPE_DEV,3);int *owner=malloc(sizeof(*owner));assert(owner);*owner=73;table.hdl[3].hdl_value=handle_value;table.hdl[3].state=HDL_ACTIVE;table.hdl[3].type=HDL_TYPE_DEV;table.hdl[3].priv=owner;table.hdl[3].ops=(void *)1;
assert(!cam_get_device_priv(handle_value^(1<<16)));assert(cam_destroy_device_hdl(handle_value^(1<<16))==-EINVAL);assert(cam_get_device_priv(handle_value)==owner);
pthread_t worker;assert(!pthread_create(&worker,NULL,callback,NULL));pthread_mutex_lock(&gate);while(!returned)pthread_cond_wait(&changed,&gate);pthread_mutex_unlock(&gate);
assert(!cam_destroy_device_hdl(handle_value));assert(!cam_get_device_priv(handle_value)&&table.hdl[3].state==HDL_FREE&&!table.hdl[3].ops&&!table.hdl[3].priv&&cleared==1&&borrowed==owner);
/* A successful native destroy is not a callback-drain barrier. */
if(argc>1)free(owner);
pthread_mutex_lock(&gate);resume=true;pthread_cond_broadcast(&changed);pthread_mutex_unlock(&gate);assert(!pthread_join(worker,NULL));if(argc==1)free(owner);puts("OBSERVED: native destroy returned while an earlier lookup still held the raw private pointer; new lookup rejected");}
'''
def main():
    spec=importlib.util.spec_from_file_location('extract',Path(__file__).with_name('test-pico-sensor-mono-hook.py'));ex=importlib.util.module_from_spec(spec);spec.loader.exec_module(ex)
    util=(SOURCE/NAMES[0]).read_text();header=(SOURCE/NAMES[1]).read_text();priv=(SOURCE/NAMES[2]).read_text()
    types='\n'.join(re.search(r'(?:enum|struct) '+name+r' \{.*?\n\};',header,re.S).group(0) for name in ['hdl_state','hdl_type','handle','cam_req_mgr_util_hdl_tbl'])
    # Use the native bit/type macros, including the reserved/random fields.
    macros=priv[priv.index('#define CAM_REQ_MGR_HDL_SIZE'):priv.rindex('#endif')]
    bodies='\n'.join(ex.function(util,s) for s in ['void *cam_get_device_priv(','static int cam_destroy_hdl(','int cam_destroy_device_hdl('])
    code=MOCKS+macros+types+'\nstatic struct cam_req_mgr_util_hdl_tbl *hdl_tbl;\n'+bodies+MAIN
    out=BASE/'out/phoenix-kernel-recovery/camera-handle-lifetime-audit';out.mkdir(exist_ok=True);(out/'harness.c').write_text(code)
    subprocess.run(['gcc','-std=gnu11','-g','-O1','-pthread','-fsanitize=address,undefined','-fno-omit-frame-pointer',str(out/'harness.c'),'-o',str(out/'test')],check=True)
    safe=subprocess.run([str(out/'test')],capture_output=True,text=True,timeout=10)
    failure=subprocess.run([str(out/'test'),'free-before-callback'],capture_output=True,text=True,timeout=10)
    reproduced=safe.returncode==0 and failure.returncode!=0 and 'heap-use-after-free' in failure.stderr
    (out/'uaf.stderr.log').write_text(failure.stderr)
    root=Path(__file__).resolve().parent.parent;target=root/'reports/kernel-source/recovery-20261003/camera-handle-lifetime-audit';target.mkdir(exist_ok=True)
    evidence={
        NAMES[0]:['void *cam_get_device_priv(','static int cam_destroy_hdl('],
        NAMES[3]:['static int __cam_req_mgr_disconnect_link(','static int __cam_req_mgr_unlink(','static int __cam_req_mgr_setup_link_info(','int cam_req_mgr_process_flush_req('],
        NAMES[4]:['static int32_t cam_actuator_platform_remove(','static int32_t cam_actuator_driver_i2c_remove(','static int cam_actuator_subdev_close('],
        NAMES[5]:['int32_t cam_actuator_apply_request(','int32_t cam_actuator_flush_request(','int32_t cam_actuator_establish_link(','void cam_actuator_shutdown(']}
    for name,signatures in evidence.items():
        text=(SOURCE/name).read_text();(target/(Path(name).stem+'-evidence.c')).write_text('\n\n'.join(ex.function(text,s) for s in signatures)+'\n')
    report={'sources':{n:hashlib.sha256((SOURCE/n).read_bytes()).hexdigest() for n in NAMES},'harness_sha256':hashlib.sha256(code.encode()).hexdigest(),'audit_exit_code':0 if reproduced else 1,'safe_borrow_exit_code':safe.returncode,'retire_then_free_exit_code':failure.returncode,'use_after_free_reproduced':reproduced,'stdout':safe.stdout,'scope':'Actual native cam_get_device_priv/cam_destroy_hdl/device wrapper, native handle types/bit macros with pthread synchronization and modeled spinlock/bitmap/owner allocation; synthetic owner free reproduces the native actuator remove lifetime requirement; no hardware test, no fix, existing raw lookup API remains unsafe without an external owner pin','required_followup':['Introduce a stable owner pin acquired before raw lookup can race physical removal, including queued/cached CRM callbacks','Unpublish new entry points before teardown, wait for in-flight callbacks outside actuator_mutex','Keep callback storage/ops/controller alive until all users release their pins; include ioctl/open/close/remove paths','Handle physical remove power/handle cleanup failure without freeing owned resources','Propagate CRM link_setup errors and unwind partially connected devices; current manager ignores link_setup rc'],'device_modified':False,'kernel_changed':False}
    for p in [out/'result.json',target/'result.json']:p.write_text(json.dumps(report,indent=2)+'\n')
    (target/'uaf.stderr.log').write_text(failure.stderr)
    print(json.dumps(report,indent=2));raise SystemExit(report['audit_exit_code'])
if __name__=='__main__':main()
