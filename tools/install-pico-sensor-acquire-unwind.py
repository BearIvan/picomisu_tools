"""Fix native sensor pre-power acquire failures and observe handle unwind."""
from pathlib import Path
import hashlib,json
SOURCE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro/source/phoenix-kernel-recovery')
NATIVE='techpack/camera/drivers/cam_sensor_module/cam_sensor/cam_sensor_core.c'
OLD='54ef159ff0bb519a94ae2f48ab3acd23b038c96dd469286c1cc35e44a36fd379'
def replace(text,old,new):
    if text.count(old)!=1:raise RuntimeError('Unexpected native anchor: '+old)
    return text.replace(old,new)
def main():
    root=Path(__file__).resolve().parent.parent;path=root/'reports/kernel-source/recovery-20261003/sensor-acquire-unwind-hooks.json';previous=json.loads(path.read_text())['sources'] if path.exists() else {};data=(SOURCE/NATIVE).read_bytes();actual=hashlib.sha256(data).hexdigest()
    if actual==OLD:
        text=data.decode();start=text.index('\tcase CAM_ACQUIRE_DEV: {',text.index('int32_t cam_sensor_driver_cmd('));end=text.index('\tcase CAM_RELEASE_DEV:',start);body=text[start:end]
        body=replace(body,'\t\tstruct cam_create_dev_hdl bridge_params;','\t\tstruct cam_create_dev_hdl bridge_params;\n\t\tint unwind_rc;')
        body=replace(body,'\t\tif (rc < 0) {\n\t\t\tCAM_ERR(CAM_SENSOR, "Failed Copying from user");','\t\tif (rc) {\n\t\t\trc = -EFAULT;\n\t\t\tCAM_ERR(CAM_SENSOR, "Failed Copying from user");')
        hook='\t\tpico_memento_capture_native(s_ctrl, 0x10001, CAM_ACQUIRE_DEV,\n\t\t\t&sensor_acq_dev, sizeof(sensor_acq_dev),\n\t\t\t(s32)sensor_acq_dev.device_handle > 0 ? 0 : -EINVAL,\n\t\t\t(s32)sensor_acq_dev.device_handle > 0);\n'
        body=replace(body,hook,'')
        anchor='\t\t\tcam_create_device_hdl(&bridge_params);\n'
        guard='\t\tif ((s32)sensor_acq_dev.device_handle <= 0) {\n\t\t\trc = (s32)sensor_acq_dev.device_handle;\n\t\t\tif (!rc)\n\t\t\t\trc = -EINVAL;\n\t\t\tgoto release_mutex;\n\t\t}\n'
        body=replace(body,anchor,anchor+hook+guard)
        anchor='\t\t\trc = -EFAULT;\n\t\t\tgoto release_mutex;\n'
        unwind='\t\t\tunwind_rc = cam_destroy_device_hdl((s32)sensor_acq_dev.device_handle);\n\t\t\tpico_memento_capture_unwind(s_ctrl, 0x10001, CAM_ACQUIRE_DEV, unwind_rc);\n\t\t\tif (!unwind_rc) {\n\t\t\t\ts_ctrl->bridge_intf.device_hdl = -1;\n\t\t\t\ts_ctrl->bridge_intf.session_hdl = -1;\n\t\t\t\ts_ctrl->bridge_intf.link_hdl = -1;\n\t\t\t}\n'
        body=replace(body,anchor,unwind+anchor);data=(text[:start]+body+text[end:]).encode()
    elif actual!=previous.get(NATIVE):raise RuntimeError('Preserve differing sensor acquire')
    if (SOURCE/NATIVE).read_bytes()!=data:(SOURCE/NATIVE).write_bytes(data)
    report={'sources':{NATIVE:hashlib.sha256(data).hexdigest()},'preimage':OLD,'scope':'Native pre-power sensor acquire usercopy/negative handle guards and handle unwind on copyout error; power-up partial failure cleanup pending','device_modified':False};path.write_text(json.dumps(report,indent=2)+'\n')
    capture_path=root/'reports/kernel-source/recovery-20261003/memento-capture-hooks.json';capture=json.loads(capture_path.read_text());capture['sources'].update(report['sources']);capture['sensor_acquire_unwind_hooks']=str(path);capture_path.write_text(json.dumps(capture,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
