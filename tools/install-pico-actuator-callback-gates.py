"""Revalidate the live actuator handle under its mutex in CRM callbacks."""
from pathlib import Path
import hashlib,json
SOURCE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro/source/phoenix-kernel-recovery');NAME='techpack/camera/drivers/cam_sensor_module/cam_actuator/cam_actuator_core.c';OLD='792d866afd6dbc9ed035ed4a3ae63d73d4856bce82ba7b3f8f9fda67a4b061dd'
def main():
    root=Path(__file__).resolve().parent.parent;rp=root/'reports/kernel-source/recovery-20261003/actuator-callback-gates-hooks.json';prior=json.loads(rp.read_text()) if rp.exists() else {};data=(SOURCE/NAME).read_bytes();actual=hashlib.sha256(data).hexdigest()
    if actual==OLD:
        t=data.decode()
        for signature,end_sig,arg in [('int32_t cam_actuator_apply_request(','int32_t cam_actuator_establish_link(','apply'),('int32_t cam_actuator_establish_link(','static void cam_actuator_update_req_mgr(','link'),('int32_t cam_actuator_flush_request(','#include "pico_memento_actuator.inc"','flush_req')]:
            start=t.index(signature);end=t.index(end_sig,start);body=t[start:end];anchor='\tmutex_lock(&(a_ctrl->actuator_mutex));'
            if body.count(anchor)!=1:raise RuntimeError('Callback lock anchor '+arg)
            gate='\n\tif (a_ctrl->bridge_intf.device_hdl != '+arg+'->dev_hdl) {\n\t\tmutex_unlock(&a_ctrl->actuator_mutex);\n\t\treturn -ENODEV;\n\t}\n'
            if arg in ['apply','link']:
                cond='a_ctrl->pico_acquire_cleanup_pending || a_ctrl->pico_release_cleanup_pending'
                if arg=='link':cond='link->link_enable && ('+cond+')'
                gate+='\tif ('+cond+') {\n\t\tmutex_unlock(&a_ctrl->actuator_mutex);\n\t\treturn -EBUSY;\n\t}\n'
            if arg=='apply':gate+='\tif (!a_ctrl->i2c_data.per_frame) {\n\t\tmutex_unlock(&a_ctrl->actuator_mutex);\n\t\treturn -EINVAL;\n\t}\n'
            if arg=='flush_req':
                old='\tif (a_ctrl->i2c_data.per_frame == NULL) {\n\t\tCAM_ERR(CAM_ACTUATOR, "i2c frame data is NULL");\n\t\treturn -EINVAL;\n\t}\n\n'
                if body.count(old)!=1:raise RuntimeError('Flush frame guard')
                body=body.replace(old,'');gate+='\tif (!a_ctrl->i2c_data.per_frame) {\n\t\tmutex_unlock(&a_ctrl->actuator_mutex);\n\t\treturn -EINVAL;\n\t}\n'
            t=t[:start]+body.replace(anchor,anchor+gate)+t[end:]
        data=t.encode()
    elif actual!=prior.get('sources',{}).get(NAME):raise RuntimeError('Preserve differing actuator source')
    result=SOURCE.parent.parent/'out/phoenix-kernel-recovery/actuator-callback-gates-tests/result.json'
    if result.exists() and json.loads(result.read_text())['exit_code']!=0:
        failed=result.with_name('pre-fix-result.json')
        if not failed.exists():failed.write_bytes(result.read_bytes())
    if (SOURCE/NAME).read_bytes()!=data:(SOURCE/NAME).write_bytes(data)
    report={'sources':{NAME:hashlib.sha256(data).hexdigest()},'preimages':{NAME:OLD},'scope':'Revalidate handle under controller mutex in apply/flush/link; pending apply/link-enable blocked while unlink remains available; per-frame access guard under lock; raw-pointer physical remove lifetime pending','device_modified':False};rp.write_text(json.dumps(report,indent=2)+'\n')
    for p in rp.parent.glob('*hooks.json'):
        if p==rp:continue
        obj=json.loads(p.read_text())
        if NAME in obj.get('sources',{}):obj['sources'][NAME]=report['sources'][NAME];obj['actuator_callback_gates_hooks']=str(rp);p.write_text(json.dumps(obj,indent=2)+'\n')
    print(json.dumps(report,indent=2))
if __name__=='__main__':main()
