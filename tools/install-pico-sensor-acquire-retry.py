"""Persist native sensor power/I-O/IRQ/handle phases across failed-acquire cleanup."""
from pathlib import Path
import hashlib,json
SOURCE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro/source/phoenix-kernel-recovery');D='techpack/camera/drivers/cam_sensor_module/cam_sensor/'
OLD={D+'cam_sensor_core.c':'ebfd7b2e2573bb89db5726a1cc1afee8be0d4bf20d568a1a4826426cf058e3ed',D+'cam_sensor_dev.h':'d76e76a0fd2eeb6f80c47a96fdb3c39852d9e6e01c54efd88db1cc74f0b6323e'}
def replace(text,old,new):
    if text.count(old)!=1:raise RuntimeError('Unexpected phase anchor: '+old)
    return text.replace(old,new)
POWER_DOWN='''int cam_sensor_power_down(struct cam_sensor_ctrl_t *s_ctrl)
{
	struct cam_sensor_power_ctrl_t *power_info;
	struct cam_hw_soc_info *soc_info;
	int rc;

	if (!s_ctrl || !s_ctrl->sensordata)
		return -EINVAL;
	power_info = &s_ctrl->sensordata->power_info;
	soc_info = &s_ctrl->soc_info;
	if (s_ctrl->pico_core_powered) {
		rc = cam_sensor_util_power_down(power_info, soc_info);
		if (rc)
			return rc;
		s_ctrl->pico_core_powered = false;
	}
	if (s_ctrl->pico_bob_pending) {
		rc = cam_sensor_bob_pwm_mode_switch(soc_info, s_ctrl->bob_reg_index, false);
		if (rc)
			return rc;
		s_ctrl->pico_bob_pending = false;
	}
	if (s_ctrl->pico_io_initialized) {
		rc = camera_io_release(&s_ctrl->io_master_info);
		if (rc)
			return rc;
		s_ctrl->pico_io_initialized = false;
	}
	return 0;
}

'''
def main():
    root=Path(__file__).resolve().parent.parent;path=root/'reports/kernel-source/recovery-20261003/sensor-acquire-retry-hooks.json';previous=json.loads(path.read_text())['sources'] if path.exists() else {};content={}
    for name,digest in OLD.items():
        data=(SOURCE/name).read_bytes();actual=hashlib.sha256(data).hexdigest()
        if actual==digest:
            text=data.decode()
            if name.endswith('.h'):
                text=replace(text,'\tbool pico_fsin_irq_owned;','\tbool pico_fsin_irq_owned;\n\tbool pico_core_powered, pico_io_initialized, pico_bob_pending;\n\tbool pico_acquire_cleanup_pending;')
            else:
                text=replace(text,'#include "pico_memento_sensor.h"','#include "pico_memento_sensor.h"\n#include "pico_sensor_acquire_unwind.h"')
                start=text.index('int cam_sensor_power_up(');end=text.index('int cam_sensor_power_down(',start);power=text[start:end]
                power=replace(power,'if (!s_ctrl) {','if (!s_ctrl || !s_ctrl->sensordata) {')
                power=replace(power,'\tsoc_info = &s_ctrl->soc_info;','\tsoc_info = &s_ctrl->soc_info;\n\tif (s_ctrl->pico_core_powered || s_ctrl->pico_io_initialized || s_ctrl->pico_bob_pending)\n\t\treturn -EBUSY;')
                power=replace(power,'\tif (s_ctrl->bob_pwm_switch) {','\tif (s_ctrl->bob_pwm_switch) {\n\t\ts_ctrl->pico_bob_pending = true;')
                power=replace(power,'\trc = camera_io_init(&(s_ctrl->io_master_info));','\ts_ctrl->pico_core_powered = true;\n\trc = camera_io_init(&(s_ctrl->io_master_info));')
                power=replace(power,'\t\tpico_memento_capture_power_cleanup(s_ctrl, cleanup_rc);','\t\tif (!cleanup_rc)\n\t\t\ts_ctrl->pico_core_powered = false;\n\t\tpico_memento_capture_power_cleanup(s_ctrl, cleanup_rc);')
                old='\t\tif (s_ctrl->bob_pwm_switch && !cleanup_rc)\n\t\t\tcam_sensor_bob_pwm_mode_switch(soc_info, s_ctrl->bob_reg_index, false);'
                new='\t\tif (s_ctrl->pico_bob_pending && !cleanup_rc &&\n\t\t\t!cam_sensor_bob_pwm_mode_switch(soc_info, s_ctrl->bob_reg_index, false))\n\t\t\ts_ctrl->pico_bob_pending = false;'
                power=replace(power,old,new);power=replace(power,'\n    /*added by webber.wang for Bug 55091 - [neo2.5]four 6dof camera sensors debug--start*/','\n\ts_ctrl->pico_io_initialized = true;\n    /*added by webber.wang for Bug 55091 - [neo2.5]four 6dof camera sensors debug--start*/')
                down_end=text.index('int cam_sensor_apply_settings(',end);text=text[:start]+power+POWER_DOWN+text[down_end:]
                start=text.index('\tcase CAM_ACQUIRE_DEV: {',text.index('int32_t cam_sensor_driver_cmd('));end=text.index('\tcase CAM_RELEASE_DEV:',start);acquire=text[start:end]
                acquire=replace(acquire,'\t\ts_ctrl->bridge_intf.device_hdl = sensor_acq_dev.device_handle;','\t\ts_ctrl->pico_acquire_cleanup_pending = true;\n\t\ts_ctrl->bridge_intf.device_hdl = sensor_acq_dev.device_handle;')
                start_u=acquire.index('\t\t\tunwind_rc = cam_destroy_device_hdl(');end_u=acquire.index('\t\t\trc = -EFAULT;',start_u);acquire=acquire[:start_u]+acquire[end_u:]
                acquire=replace(acquire,'\t\t\trc = -EFAULT;\n\t\t\tgoto release_mutex;','\t\t\trc = -EFAULT;\n\t\t\tgoto acquire_unwind;')
                start_u=acquire.index('\t\tif (rc) {\n\t\t\tunwind_rc = cam_destroy_device_hdl(');end_u=acquire.index('\t\t#endif',start_u);acquire=acquire[:start_u]+'\t\tif (rc)\n\t\t\tgoto acquire_unwind;\n'+acquire[end_u:]
                acquire=replace(acquire,'"Sensor Power up failed");\n\t\t\tgoto release_mutex;','"Sensor Power up failed");\n\t\t\tgoto acquire_unwind;')
                acquire=replace(acquire,'\t\ts_ctrl->sensor_state = CAM_SENSOR_ACQUIRE;','\t\ts_ctrl->pico_acquire_cleanup_pending = false;\n\t\ts_ctrl->sensor_state = CAM_SENSOR_ACQUIRE;')
                marker='\t}\n\t\tbreak;\n';assert acquire.endswith(marker)
                acquire=acquire[:-len(marker)]+'\t\tgoto acquire_done;\nacquire_unwind:\n\t\tunwind_rc = pico_sensor_acquire_unwind_locked(s_ctrl);\n\t\tpico_memento_capture_unwind(s_ctrl, 0x10001, CAM_ACQUIRE_DEV, unwind_rc);\nacquire_done:\n\t\t;\n'+marker
                text=text[:start]+acquire+text[end:]
                text=replace(text,'\tcase CAM_RELEASE_DEV: {\n\t\t//CAM_INFO(CAM_SENSOR,','\tcase CAM_RELEASE_DEV: {\n\t\tif (s_ctrl->pico_acquire_cleanup_pending) {\n\t\t\trc = pico_sensor_acquire_unwind_locked(s_ctrl);\n\t\t\tgoto release_mutex;\n\t\t}\n\t\t//CAM_INFO(CAM_SENSOR,')
                text+='\n#include "pico_sensor_acquire_unwind.inc"\n'
            data=text.encode()
        elif actual!=previous.get(name):raise RuntimeError('Preserve differing acquire phase source: '+name)
        if name.endswith('.c'):
            text=data.decode()
            gate='\tif (s_ctrl->pico_acquire_cleanup_pending &&\n\t\tcmd->op_code != CAM_RELEASE_DEV && cmd->op_code != CAM_ACQUIRE_DEV) {\n\t\trc = -EBUSY;\n\t\tgoto release_mutex;\n\t}\n'
            if gate not in text:
                text=replace(text,'\tmutex_lock(&(s_ctrl->cam_sensor_mutex));\n\tswitch (cmd->op_code) {','\tmutex_lock(&(s_ctrl->cam_sensor_mutex));\n'+gate+'\tswitch (cmd->op_code) {')
                data=text.encode()
        content[name]=data
    for suffix in ['h','inc']:
        name=D+'pico_sensor_acquire_unwind.'+suffix;data=(root/'kernel-recovery'/name).read_bytes().replace(b'\r\n',b'\n')
        if (SOURCE/name).exists() and (SOURCE/name).read_bytes()!=data and hashlib.sha256((SOURCE/name).read_bytes()).hexdigest()!=previous.get(name):raise RuntimeError('Preserve differing unwind')
        content[name]=data
    for name,data in content.items():
        if not (SOURCE/name).exists() or (SOURCE/name).read_bytes()!=data:(SOURCE/name).write_bytes(data)
    report={'sources':{n:hashlib.sha256(v).hexdigest() for n,v in content.items()},'preimages':OLD,'scope':'Driver-owned core/BoB/I-O phases and failed acquire cleanup; native release retries pending cleanup; lower helper/hardware error fidelity and hot-remove remain unverified','device_modified':False};path.write_text(json.dumps(report,indent=2)+'\n')
    capture_path=root/'reports/kernel-source/recovery-20261003/memento-capture-hooks.json';capture=json.loads(capture_path.read_text());capture['sources'][D+'cam_sensor_core.c']=report['sources'][D+'cam_sensor_core.c'];capture['sensor_acquire_retry_hooks']=str(path);capture_path.write_text(json.dumps(capture,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
