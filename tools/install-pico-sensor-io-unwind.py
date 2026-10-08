"""Unwind core sensor power if camera I/O init fails; retain both results."""
from pathlib import Path
import hashlib,json
SOURCE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro/source/phoenix-kernel-recovery')
NATIVE='techpack/camera/drivers/cam_sensor_module/cam_sensor/cam_sensor_core.c'
OLD='b281eeff15f95daa73d44c5578555ff5bd7c46626aadd1fd0e73f91ab353557f'
def main():
    root=Path(__file__).resolve().parent.parent;path=root/'reports/kernel-source/recovery-20261003/sensor-io-unwind-hooks.json';previous=json.loads(path.read_text())['sources'] if path.exists() else {};data=(SOURCE/NATIVE).read_bytes();actual=hashlib.sha256(data).hexdigest()
    if actual==OLD:
        text=data.decode();start=text.index('int cam_sensor_power_up(');end=text.index('int cam_sensor_power_down(',start);body=text[start:end]
        anchor='\tint rc;';assert body.count(anchor)==1;body=body.replace(anchor,'\tint rc, cleanup_rc;')
        anchor='\tif (rc < 0)\n\t\tCAM_ERR(CAM_SENSOR, "cci_init failed: rc: %d", rc);';assert body.count(anchor)==1
        new='\tif (rc < 0) {\n\t\tCAM_ERR(CAM_SENSOR, "cci_init failed: rc: %d", rc);\n\t\tcleanup_rc = cam_sensor_util_power_down(power_info, soc_info);\n\t\tpico_memento_capture_power_cleanup(s_ctrl, cleanup_rc);\n\t\tif (cleanup_rc < 0)\n\t\t\tCAM_ERR(CAM_SENSOR, "core power unwind failed: %d", cleanup_rc);\n\t\tif (s_ctrl->bob_pwm_switch && !cleanup_rc)\n\t\t\tcam_sensor_bob_pwm_mode_switch(soc_info, s_ctrl->bob_reg_index, false);\n\t\treturn rc;\n\t}'
        body=body.replace(anchor,new);data=(text[:start]+body+text[end:]).encode()
    elif actual!=previous.get(NATIVE):raise RuntimeError('Preserve differing sensor power-up')
    if (SOURCE/NATIVE).read_bytes()!=data:(SOURCE/NATIVE).write_bytes(data)
    report={'sources':{NATIVE:hashlib.sha256(data).hexdigest()},'preimage':OLD,'scope':'Native I/O-init failure unwinds successful core power-up, retains original init errno and separate core cleanup status; IRQ/handle cleanup still pending','device_modified':False};path.write_text(json.dumps(report,indent=2)+'\n')
    capture_path=root/'reports/kernel-source/recovery-20261003/memento-capture-hooks.json';capture=json.loads(capture_path.read_text());capture['sources'].update(report['sources']);capture['sensor_io_unwind_hooks']=str(path);capture_path.write_text(json.dumps(capture,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
