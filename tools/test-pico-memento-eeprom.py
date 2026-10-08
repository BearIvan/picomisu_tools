"""Actual EEPROM ledger/adapter and CRM handle-table destruction bodies."""
from pathlib import Path
import hashlib,importlib.util,json,subprocess
BASE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro');SOURCE=BASE/'source/phoenix-kernel-recovery'
D='techpack/camera/drivers/cam_sensor_module/cam_eeprom/'
NAMES=[D+n for n in ['pico_memento_eeprom.inc','pico_memento_eeprom.h','cam_eeprom_core.c']]+['techpack/camera/drivers/cam_core/pico_camera_memento.'+e for e in ['c','h']]+['techpack/camera/drivers/cam_req_mgr/'+n for n in ['cam_req_mgr_util.c','cam_req_mgr_util.h','cam_req_mgr_util_priv.h']]+['techpack/camera/include/uapi/media/cam_req_mgr.h']
NAMES += [D+'pico_eeprom_acquire_unwind.'+e for e in ['inc','h']]
MOCKS=r'''
typedef int s32;
#define CAM_EEPROM_INIT 0
#define CAM_EEPROM_ACQUIRE 1
#define CAM_EEPROM_CONFIG 2
#define CAM_CRM 0
#define CAM_ERR(...) ((void)0)
struct cam_eeprom_ctrl_t {struct mutex eeprom_mutex;struct {int session_hdl,device_hdl,link_hdl;}bridge_intf;int cam_eeprom_state;bool pico_acquire_cleanup_pending,pico_core_powered,pico_io_initialized,pico_transaction_cleanup_pending;};
static int cam_eeprom_power_down(struct cam_eeprom_ctrl_t *c){assert(!c->pico_core_powered&&!c->pico_io_initialized);return 0;}
static void pico_eeprom_free_transaction(struct cam_eeprom_ctrl_t *c){c->pico_transaction_cleanup_pending=false;}
struct pico_memento_eeprom {struct cam_eeprom_ctrl_t *eeprom;s32 session,device;bool complete;};
static struct cam_req_mgr_util_hdl_tbl *hdl_tbl;
static int hdl_tbl_lock;static bool spin_held;
static void spin_lock_bh(int *lock){assert(held==1&&!spin_held);spin_held=true;}
static void spin_unlock_bh(int *lock){assert(held==1&&spin_held);spin_held=false;}
static void clear_bit(unsigned idx,void *bitmap){assert(spin_held);((unsigned long *)bitmap)[idx/(8*sizeof(unsigned long))]&=~(1UL<<(idx%(8*sizeof(unsigned long))));}
'''
MAIN=r'''
int main(void){
 const unsigned idx=3;const int handle=GET_DEV_HANDLE(0x12,HDL_TYPE_DEV,idx);assert(handle>0 && CAM_REQ_MGR_GET_HDL_TYPE(handle)==HDL_TYPE_DEV && CAM_REQ_MGR_GET_HDL_IDX(handle)==idx);
 unsigned long bitmap[(CAM_REQ_MGR_MAX_HANDLES_V2+63)/64]={1UL<<idx};struct cam_req_mgr_util_hdl_tbl table={.bitmap=bitmap};table.hdl[idx].hdl_value=handle;table.hdl[idx].state=HDL_ACTIVE;table.hdl[idx].priv=(void *)123;table.hdl[idx].ops=(void *)456;
 struct cam_eeprom_ctrl_t eeprom={.eeprom_mutex={PTHREAD_MUTEX_INITIALIZER},.bridge_intf={41,handle,-1},.cam_eeprom_state=1};struct pico_memento_eeprom target;
 assert(pico_memento_eeprom_init(NULL,&eeprom,41,handle)==-EINVAL);assert(!pico_memento_eeprom_init(&target,&eeprom,41,handle));u32 acq[6]={41,handle,1,0,0,0},zero[2]={0};assert(pico_memento_eeprom_rollback(&target,0x1000d,0x106,acq,24)==-EINVAL);assert(pico_memento_eeprom_rollback(&target,0x1000c,0x106,acq,8)==-EINVAL);
 struct pico_memento state;pico_memento_init(&state);struct pico_memento_record *ticket=NULL;assert(!pico_memento_prepare(0x1000c,VIDIOC_CAM_CONTROL,0x102,&ticket));assert(!pico_memento_commit(&state,&ticket,0x1000c,0x102,acq,24,0));assert(!pico_memento_prepare(0x1000c,VIDIOC_CAM_CONTROL,0x103,&ticket));assert(!pico_memento_commit(&state,&ticket,0x1000c,0x103,NULL,0,0));
 eeprom.bridge_intf.link_hdl=7;assert(pico_memento_cleanup(&state,pico_memento_eeprom_rollback,&target)==-EAGAIN && list_empty(&state.starts) && live==1 && !target.complete);
 eeprom.bridge_intf.link_hdl=-1;hdl_tbl=NULL;assert(pico_memento_cleanup(&state,pico_memento_eeprom_rollback,&target)==-EINVAL && eeprom.bridge_intf.device_hdl==handle && eeprom.cam_eeprom_state==1 && live==1);
 hdl_tbl=&table;table.hdl[idx].state=HDL_FREE;assert(pico_memento_cleanup(&state,pico_memento_eeprom_rollback,&target)==-EINVAL && live==1);table.hdl[idx].state=HDL_ACTIVE;table.hdl[idx].hdl_value=handle+0x10000;assert(pico_memento_cleanup(&state,pico_memento_eeprom_rollback,&target)==-EINVAL && live==1 && bitmap[0]&(1UL<<idx));
 table.hdl[idx].hdl_value=handle;assert(!pico_memento_cleanup(&state,pico_memento_eeprom_rollback,&target) && table.hdl[idx].state==HDL_FREE && !table.hdl[idx].priv && !table.hdl[idx].ops && !(bitmap[0]&(1UL<<idx)) && eeprom.bridge_intf.device_hdl==-1 && eeprom.bridge_intf.session_hdl==-1 && eeprom.cam_eeprom_state==0 && target.complete && !live);
 assert(!pico_memento_cleanup(&state,pico_memento_eeprom_rollback,&target));assert(!held && !spin_held);
 eeprom.bridge_intf.session_hdl=41;eeprom.bridge_intf.device_hdl=handle;eeprom.pico_acquire_cleanup_pending=true;
 assert(!pico_memento_eeprom_init(&target,&eeprom,41,handle));
 assert(pico_memento_eeprom_rollback(&target,0x1000c,CAM_RELEASE_DEV,acq,24)==-EINVAL && !target.complete && eeprom.pico_acquire_cleanup_pending && eeprom.bridge_intf.device_hdl==handle);
 table.hdl[idx].state=HDL_ACTIVE;bitmap[0]|=1UL<<idx;
 assert(!pico_memento_eeprom_rollback(&target,0x1000c,CAM_RELEASE_DEV,acq,24) && target.complete && !eeprom.pico_acquire_cleanup_pending && eeprom.bridge_intf.device_hdl==-1 && !(bitmap[0]&(1UL<<idx)));
 puts("PASS: actual EEPROM adapter/ledger/native cam_destroy_hdl, real handle macros/table fields, implicit stop no-op, identity/link guards, missing table/inactive/stale handle failure retains acquisition, retry clears table/bitmap/controller exactly once");
}
'''
def load(name):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name(name+'.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
def main():
    common=load('test-pico-camera-hub-registry');ledger=load('test-pico-camera-memento');body=(SOURCE/NAMES[3]).read_text();util=(SOURCE/NAMES[5]).read_text();header=(SOURCE/NAMES[6]).read_text()
    types=header[header.index('enum hdl_state {'):header.index('/**\n * cam_req_mgr_util APIs')]
    handles=util[util.index('static int cam_destroy_hdl('):util.index('int cam_destroy_session_hdl(')]
    mocks='\n'.join(line for line in ledger.MOCKS.splitlines() if not line.startswith(('#define VIDIOC_CAM_CONTROL ', '#define CAM_ACQUIRE_DEV ', '#define CAM_START_DEV ', '#define CAM_STOP_DEV ', '#define CAM_RELEASE_DEV ')))+'\n'
    code='#include <stdint.h>\n#include <stddef.h>\n#include <cam_req_mgr.h>\n#include "cam_req_mgr_util_priv.h"\n'+common.HARNESS.split('/* OWNED_SUBDEVICE_MOCKS */')[0]+mocks+types+MOCKS+body[body.index('struct pico_memento_record {'):]+handles+(SOURCE/NAMES[0]).read_text()+MAIN
    code=code.replace((SOURCE/NAMES[0]).read_text(),(SOURCE/NAMES[9]).read_text()+(SOURCE/NAMES[0]).read_text())
    out=BASE/'out/phoenix-kernel-recovery/memento-eeprom-tests';out.mkdir(exist_ok=True);(out/'harness.c').write_text(code)
    subprocess.run(['gcc','-std=gnu11','-g','-O1','-pthread','-fsanitize=address,undefined','-fno-omit-frame-pointer','-I'+str(SOURCE/'techpack/camera/include/uapi/media'),'-I'+str(SOURCE/'techpack/camera/include/uapi'),'-I'+str(SOURCE/'techpack/camera/drivers/cam_req_mgr'),str(out/'harness.c'),'-o',str(out/'test')],check=True)
    result=subprocess.run([str(out/'test')],capture_output=True,text=True,timeout=30)
    report={'sources':{n:hashlib.sha256((SOURCE/n).read_bytes()).hexdigest() for n in NAMES},'harness_sha256':hashlib.sha256(code.encode()).hexdigest(),'exit_code':result.returncode,'stdout':result.stdout,'stderr':result.stderr,'sanitizers':['AddressSanitizer','UndefinedBehaviorSanitizer'],'scope':'Actual ledger/EEPROM adapter/native CRM handle-destroy bodies and current UAPI/macros/types; controller mutex/spin/bitmap API modeled, real table-state mutations; no hardware/subdevice close integration','device_modified':False}
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));raise SystemExit(result.returncode)
if __name__=='__main__':main()
