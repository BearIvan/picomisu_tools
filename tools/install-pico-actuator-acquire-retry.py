"""Native actuator acquire handle guards and partial cleanup retry."""
from pathlib import Path
import hashlib,json
SOURCE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro/source/phoenix-kernel-recovery');D='techpack/camera/drivers/cam_sensor_module/cam_actuator/';OLD='1cd3a60b158a8c2c1437b578dd6278b41272001c57165a6523b2b4565f37ffb1'
def replace(t,a,b):
    if t.count(a)!=1:raise RuntimeError('Unexpected actuator anchor: '+a)
    return t.replace(a,b)
def main():
    root=Path(__file__).resolve().parent.parent;rp=root/'reports/kernel-source/recovery-20261003/actuator-acquire-retry-hooks.json';prior=json.loads(rp.read_text())['sources'] if rp.exists() else {};content={};preimages={}
    for n in ['cam_actuator_core.c','cam_actuator_dev.h']:
        name=D+n;data=(SOURCE/name).read_bytes();actual=hashlib.sha256(data).hexdigest();preimages[name]=json.loads(rp.read_text()).get('preimages',{}).get(name,actual) if rp.exists() else actual
        baseline=OLD if n.endswith('.c') else actual if not prior else prior.get(name)
        if actual==baseline and actual!=prior.get(name):
            t=data.decode()
            if n.endswith('.h'):t=replace(t,'\tuint32_t open_cnt;','\tuint32_t open_cnt;\n\tbool pico_acquire_cleanup_pending;')
            else:
                t=replace(t,'#include "cam_actuator_core.h"','#include "cam_actuator_core.h"\n#include "pico_actuator_acquire_unwind.h"')
                start=t.index('\tcase CAM_ACQUIRE_DEV: {');end=t.index('\tcase CAM_RELEASE_DEV:',start);body=t[start:end]
                body=replace(body,'\t\tif (a_ctrl->bridge_intf.device_hdl != -1) {','\t\tif (a_ctrl->cam_act_state != CAM_ACTUATOR_INIT) {rc = -EINVAL; goto release_mutex;}\n\t\tif (a_ctrl->bridge_intf.device_hdl != -1) {')
                body=replace(body,'\t\tif (rc < 0) {\n\t\t\tCAM_ERR(CAM_ACTUATOR, "Failed Copying from user\\n");','\t\tif (rc) {\n\t\t\trc = -EFAULT;\n\t\t\tCAM_ERR(CAM_ACTUATOR, "Failed Copying from user\\n");')
                hook='\t\tpico_memento_capture_native(a_ctrl, 0x10009, CAM_ACQUIRE_DEV,\n\t\t\t&actuator_acq_dev, sizeof(actuator_acq_dev),\n\t\t\t(s32)actuator_acq_dev.device_handle > 0 ? 0 : -EINVAL,\n\t\t\t(s32)actuator_acq_dev.device_handle > 0);\n';body=replace(body,hook,'');hook=hook.replace('> 0 ? 0 : -EINVAL,','> 0 ? 0 : ((s32)actuator_acq_dev.device_handle ?: -EINVAL),')
                body=replace(body,'\t\ta_ctrl->bridge_intf.device_hdl = actuator_acq_dev.device_handle;',hook+'\t\tif ((s32)actuator_acq_dev.device_handle <= 0) {\n\t\t\trc = (s32)actuator_acq_dev.device_handle ?: -EINVAL;\n\t\t\tgoto release_mutex;\n\t\t}\n\t\ta_ctrl->pico_acquire_cleanup_pending = true;\n\t\ta_ctrl->bridge_intf.device_hdl = actuator_acq_dev.device_handle;')
                body=replace(body,'CAM_ERR(CAM_ACTUATOR, "Failed Copy to User");\n\t\t\trc = -EFAULT;','CAM_ERR(CAM_ACTUATOR, "Failed Copy to User");\n\t\t\trc = pico_actuator_acquire_unwind_locked(a_ctrl);\n\t\t\tpico_memento_capture_unwind(a_ctrl, 0x10009, CAM_ACQUIRE_DEV, rc);\n\t\t\trc = -EFAULT;')
                body=replace(body,'\t\ta_ctrl->cam_act_state = CAM_ACTUATOR_ACQUIRE;','\t\ta_ctrl->pico_acquire_cleanup_pending = false;\n\t\ta_ctrl->cam_act_state = CAM_ACTUATOR_ACQUIRE;');t=t[:start]+body+t[end:]
                t=replace(t,'\tcase CAM_RELEASE_DEV: {','\tcase CAM_RELEASE_DEV: {\n\t\tif (a_ctrl->pico_acquire_cleanup_pending) {\n\t\t\trc = pico_actuator_acquire_unwind_locked(a_ctrl);\n\t\t\tgoto release_mutex;\n\t\t}')
                t=replace(t,'\tmutex_lock(&(a_ctrl->actuator_mutex));\n\tswitch (cmd->op_code)', '\tmutex_lock(&(a_ctrl->actuator_mutex));\n\tif (a_ctrl->pico_acquire_cleanup_pending && cmd->op_code != CAM_ACQUIRE_DEV && cmd->op_code != CAM_RELEASE_DEV && cmd->op_code != CAM_QUERY_CAP) {rc = -EBUSY; goto release_mutex;}\n\tswitch (cmd->op_code)')
                t+='\n#include "pico_actuator_acquire_unwind.inc"\n'
            data=t.encode()
        elif actual!=prior.get(name):raise RuntimeError('Preserve differing actuator source: '+name)
        content[name]=data
    for suffix in ['h','inc']:
        name=D+'pico_actuator_acquire_unwind.'+suffix;data=(root/'kernel-recovery'/name).read_bytes().replace(b'\r\n',b'\n')
        if (SOURCE/name).exists() and hashlib.sha256((SOURCE/name).read_bytes()).hexdigest() not in [prior.get(name),hashlib.sha256(data).hexdigest()]:raise RuntimeError('Preserve differing actuator unwind')
        content[name]=data
    name=D+'pico_memento_actuator.inc';data=(root/'kernel-recovery'/name).read_bytes().replace(b'\r\n',b'\n');actual=hashlib.sha256((SOURCE/name).read_bytes()).hexdigest()
    if actual not in ['dfc915204857a684ed3c2fa515aad4af221c6a3e2c7b514f3860178f5f0eac17',prior.get(name),hashlib.sha256(data).hexdigest()]:raise RuntimeError('Preserve differing actuator adapter')
    content[name]=data
    for name,data in content.items():
        if not (SOURCE/name).exists() or (SOURCE/name).read_bytes()!=data:(SOURCE/name).write_bytes(data)
    report={'sources':{n:hashlib.sha256(v).hexdigest() for n,v in content.items()},'preimages':preimages,'scope':'Native actuator INIT acquire, positive copyin remainder/negative or zero handle reject, copyout handle unwind with pending retry/release/config gate and memento INIT cleanup; normal-release/shutdown/power phases/removal/runtime pending','device_modified':False};rp.write_text(json.dumps(report,indent=2)+'\n')
    p=rp.parent/'peer-acquire-capture-hooks.json';obj=json.loads(p.read_text());obj['sources'][D+'cam_actuator_core.c']=report['sources'][D+'cam_actuator_core.c'];obj['actuator_acquire_retry_hooks']=str(rp);p.write_text(json.dumps(obj,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
