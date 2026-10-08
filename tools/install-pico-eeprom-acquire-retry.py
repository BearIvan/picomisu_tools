"""Native EEPROM acquire guards/unwind/retry and handle release error retention."""
from pathlib import Path
import hashlib,json
SOURCE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro/source/phoenix-kernel-recovery');D='techpack/camera/drivers/cam_sensor_module/cam_eeprom/'
OLD={D+'cam_eeprom_core.c':'da8632e5dae41ef1f16ba27688e65bc1387549ac3e2df16a655fb9dde99a0219',D+'cam_eeprom_dev.h':'29345955a81d08d5de93e2978ad4725bd69584a52c96a1ca2c537918a7178c53'}
def replace(text,old,new):
    if text.count(old)!=1:raise RuntimeError('Unexpected EEPROM anchor: '+old)
    return text.replace(old,new)
def main():
    root=Path(__file__).resolve().parent.parent;path=root/'reports/kernel-source/recovery-20261003/eeprom-acquire-retry-hooks.json';previous=json.loads(path.read_text())['sources'] if path.exists() else {};content={}
    for name,digest in OLD.items():
        data=(SOURCE/name).read_bytes();actual=hashlib.sha256(data).hexdigest()
        if actual==digest:
            text=data.decode()
            if name.endswith('.h'):
                text=replace(text,'\tuint32_t open_cnt;','\tuint32_t open_cnt;\n\tbool pico_acquire_cleanup_pending;')
            else:
                text=replace(text,'#include "cam_eeprom_core.h"','#include "cam_eeprom_core.h"\n#include "pico_eeprom_acquire_unwind.h"')
                start=text.index('static int32_t cam_eeprom_get_dev_handle(');end=text.index('\n/**',start);body=text[start:end]
                body=replace(body,'\tstruct cam_control              *cmd = (struct cam_control *)arg;','\tstruct cam_control              *cmd = (struct cam_control *)arg;\n\tint rc;\n\tif (e_ctrl->cam_eeprom_state != CAM_EEPROM_INIT)\n\t\treturn -EINVAL;')
                hook='\tpico_memento_capture_native(e_ctrl, 0x1000c, CAM_ACQUIRE_DEV,\n\t\t&eeprom_acq_dev, sizeof(eeprom_acq_dev),\n\t\t(s32)eeprom_acq_dev.device_handle > 0 ? 0 : -EINVAL,\n\t\t(s32)eeprom_acq_dev.device_handle > 0);\n';body=replace(body,hook,'')
                create='\t\tcam_create_device_hdl(&bridge_params);\n';guard='\tif ((s32)eeprom_acq_dev.device_handle <= 0)\n\t\treturn (s32)eeprom_acq_dev.device_handle ?: -EINVAL;\n\te_ctrl->pico_acquire_cleanup_pending = true;\n';body=replace(body,create,create+hook+guard)
                body=replace(body,'"EEPROM:ACQUIRE_DEV: copy to user failed");\n\t\treturn -EFAULT;','"EEPROM:ACQUIRE_DEV: copy to user failed");\n\t\trc = pico_eeprom_acquire_unwind_locked(e_ctrl);\n\t\tpico_memento_capture_unwind(e_ctrl, 0x1000c, CAM_ACQUIRE_DEV, rc);\n\t\treturn -EFAULT;')
                body=replace(body,'\treturn 0;\n}','\te_ctrl->pico_acquire_cleanup_pending = false;\n\treturn 0;\n}');text=text[:start]+body+text[end:]
                text=replace(text,'\tmutex_lock(&(e_ctrl->eeprom_mutex));\n\tswitch (cmd->op_code)', '\tmutex_lock(&(e_ctrl->eeprom_mutex));\n\tif (e_ctrl->pico_acquire_cleanup_pending && cmd->op_code != CAM_RELEASE_DEV && cmd->op_code != CAM_ACQUIRE_DEV) {\n\t\trc = -EBUSY;\n\t\tgoto release_mutex;\n\t}\n\tswitch (cmd->op_code)')
                text=replace(text,'\tcase CAM_RELEASE_DEV:\n','\tcase CAM_RELEASE_DEV:\n\t\tif (e_ctrl->pico_acquire_cleanup_pending) {\n\t\t\trc = pico_eeprom_acquire_unwind_locked(e_ctrl);\n\t\t\tgoto release_mutex;\n\t\t}\n')
                text=replace(text,'\t\tif (rc < 0)\n\t\t\tCAM_ERR(CAM_EEPROM,\n\t\t\t\t"failed in destroying the device hdl");','\t\tif (rc) {\n\t\t\tCAM_ERR(CAM_EEPROM, "failed in destroying the device hdl: %d", rc);\n\t\t\tgoto release_mutex;\n\t\t}')
                text+='\n#include "pico_eeprom_acquire_unwind.inc"\n'
            data=text.encode()
        elif actual!=previous.get(name):raise RuntimeError('Preserve differing EEPROM source: '+name)
        content[name]=data
    for suffix in ['h','inc']:
        name=D+'pico_eeprom_acquire_unwind.'+suffix;data=(root/'kernel-recovery'/name).read_bytes().replace(b'\r\n',b'\n')
        if (SOURCE/name).exists() and (SOURCE/name).read_bytes()!=data and hashlib.sha256((SOURCE/name).read_bytes()).hexdigest()!=previous.get(name):raise RuntimeError('Preserve differing EEPROM unwind')
        content[name]=data
    name=D+'pico_memento_eeprom.inc';data=(root/'kernel-recovery'/name).read_bytes().replace(b'\r\n',b'\n');actual=hashlib.sha256((SOURCE/name).read_bytes()).hexdigest()
    if actual not in ['8532298f27f0e0f3565bf079e32626cf3e22c9cfd472762036fbc423056e1b9c',previous.get(name),hashlib.sha256(data).hexdigest()]:raise RuntimeError('Preserve differing EEPROM adapter')
    content[name]=data
    for name,data in content.items():
        if not (SOURCE/name).exists() or (SOURCE/name).read_bytes()!=data:(SOURCE/name).write_bytes(data)
    report={'sources':{n:hashlib.sha256(v).hexdigest() for n,v in content.items()},'preimages':OLD,'scope':'Native EEPROM failed acquire handle cleanup/release retry; normal release preserves handle on failure; physical hardware/dispatch/hot-remove pending','device_modified':False};path.write_text(json.dumps(report,indent=2)+'\n')
    peer_path=root/'reports/kernel-source/recovery-20261003/peer-acquire-capture-hooks.json';peer=json.loads(peer_path.read_text());peer['sources'][D+'cam_eeprom_core.c']=report['sources'][D+'cam_eeprom_core.c'];peer['eeprom_acquire_retry_hooks']=str(path);peer_path.write_text(json.dumps(peer,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
