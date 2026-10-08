"""Track actuator core/I-O power ownership through activation/cleanup failures."""
from pathlib import Path
import hashlib,json
SOURCE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro/source/phoenix-kernel-recovery');D='techpack/camera/drivers/cam_sensor_module/cam_actuator/'
OLD={D+'cam_actuator_core.c':'e222bce51437ec079e16385c5f3f42f4bebe9ca5a4ea882a3f65548d398984bb',D+'cam_actuator_dev.h':'3865e00bcd2ec4c728e5d6f8aec93cf6b4ad7f8f5432f1b4c84b1baac4436f63'}
DOWN='''static int32_t cam_actuator_power_down(struct cam_actuator_ctrl_t *a_ctrl)
{
	struct cam_actuator_soc_private *soc;
	int rc;
	if (!a_ctrl || !a_ctrl->soc_info.soc_private)
		return -EINVAL;
	soc = a_ctrl->soc_info.soc_private;
	if (a_ctrl->pico_core_powered) {
		rc = cam_sensor_util_power_down(&soc->power_info, &a_ctrl->soc_info);
		if (rc)
			return rc;
		a_ctrl->pico_core_powered = false;
	}
	if (a_ctrl->pico_io_initialized) {
		rc = camera_io_release(&a_ctrl->io_master_info);
		if (rc)
			return rc;
		a_ctrl->pico_io_initialized = false;
	}
	return 0;
}

'''
def replace(t,a,b):
    if t.count(a)!=1:raise RuntimeError('Unexpected actuator power anchor: '+a)
    return t.replace(a,b)
def main():
    root=Path(__file__).resolve().parent.parent;rp=root/'reports/kernel-source/recovery-20261003/actuator-power-retry-hooks.json';prior=json.loads(rp.read_text())['sources'] if rp.exists() else {};content={}
    for name,digest in OLD.items():
        data=(SOURCE/name).read_bytes();actual=hashlib.sha256(data).hexdigest()
        if actual==digest:
            t=data.decode()
            if name.endswith('.h'):t=replace(t,'\tbool pico_release_cleanup_pending, pico_release_power_done;','\tbool pico_release_cleanup_pending, pico_release_power_done;\n\tbool pico_core_powered, pico_io_initialized;')
            else:
                start=t.index('static int32_t cam_actuator_power_up(');end=t.index('static int32_t cam_actuator_power_down(',start);body=t[start:end]
                body=replace(body,'\tint rc = 0;','\tint rc = 0, cleanup_rc;')
                body=replace(body,'\tstruct cam_hw_soc_info  *soc_info =\n\t\t&a_ctrl->soc_info;','\tstruct cam_hw_soc_info *soc_info;')
                body=replace(body,'\tsoc_private =\n','\tif (!a_ctrl || !a_ctrl->soc_info.soc_private)\n\t\treturn -EINVAL;\n\tif (a_ctrl->pico_core_powered || a_ctrl->pico_io_initialized || a_ctrl->pico_release_cleanup_pending)\n\t\treturn -EBUSY;\n\tsoc_info = &a_ctrl->soc_info;\n\tsoc_private =\n')
                body=replace(body,'\trc = camera_io_init(&a_ctrl->io_master_info);\n\tif (rc < 0)\n\t\tCAM_ERR(CAM_ACTUATOR, "cci init failed: rc: %d", rc);','\ta_ctrl->pico_core_powered = true;\n\trc = camera_io_init(&a_ctrl->io_master_info);\n\tif (rc) {\n\t\tCAM_ERR(CAM_ACTUATOR, "cci init failed: rc: %d", rc);\n\t\tcleanup_rc = cam_sensor_util_power_down(power_info, soc_info);\n\t\tif (!cleanup_rc)\n\t\t\ta_ctrl->pico_core_powered = false;\n\t\telse {\n\t\t\ta_ctrl->pico_release_cleanup_pending = true;\n\t\t\tCAM_ERR(CAM_ACTUATOR, "core unwind failed: %d", cleanup_rc);\n\t\t}\n\t\treturn rc;\n\t}\n\ta_ctrl->pico_io_initialized = true;')
                downend=t.index('static int32_t cam_actuator_i2c_modes_util(',end);t=t[:start]+body+DOWN+t[downend:]
                t=replace(t,'if (a_ctrl->cam_act_state == CAM_ACTUATOR_CONFIG && !a_ctrl->pico_release_power_done) {','if ((a_ctrl->cam_act_state == CAM_ACTUATOR_CONFIG && !a_ctrl->pico_release_power_done) || a_ctrl->pico_core_powered || a_ctrl->pico_io_initialized) {')
                start=t.index('void cam_actuator_shutdown(');end=t.index('int32_t cam_actuator_driver_cmd(',start);body=t[start:end]
                body=replace(body,'if (a_ctrl->cam_act_state == CAM_ACTUATOR_INIT)\n','if (a_ctrl->cam_act_state == CAM_ACTUATOR_INIT && !a_ctrl->pico_core_powered && !a_ctrl->pico_io_initialized)\n')
                body=replace(body,'if (a_ctrl->cam_act_state >= CAM_ACTUATOR_CONFIG) {','if (a_ctrl->cam_act_state >= CAM_ACTUATOR_CONFIG || a_ctrl->pico_core_powered || a_ctrl->pico_io_initialized) {')
                body=replace(body,'if (!a_ctrl->pico_release_power_done) {','if (!a_ctrl->pico_release_power_done || a_ctrl->pico_core_powered || a_ctrl->pico_io_initialized) {');t=t[:start]+body+t[end:]
            data=t.encode()
        elif actual!=prior.get(name):raise RuntimeError('Preserve differing actuator power source: '+name)
        content[name]=data
    name=D+'pico_memento_actuator.inc';data=(root/'kernel-recovery'/name).read_bytes().replace(b'\r\n',b'\n');actual=hashlib.sha256((SOURCE/name).read_bytes()).hexdigest()
    if actual not in ['acfa5fe21bd0215a8eb848cdeb1419831c9d8f79e43777e3985dee28d2874b8b',prior.get(name),hashlib.sha256(data).hexdigest()]:raise RuntimeError('Preserve differing actuator memento')
    content[name]=data
    for name,data in content.items():
        if (SOURCE/name).read_bytes()!=data:(SOURCE/name).write_bytes(data)
    report={'sources':{n:hashlib.sha256(v).hexdigest() for n,v in content.items()},'preimages':OLD,'scope':'Actuator driver-owned core/I-O phases; failed init core unwind preserves primary errno and retains failed core cleanup; release/shutdown/memento check phases even in ACQUIRE; I/O release errors propagate and completed core step skipped; lower partial effects/provider/lifecycle pending','device_modified':False};rp.write_text(json.dumps(report,indent=2)+'\n')
    for p in rp.parent.glob('*hooks.json'):
        if p==rp:continue
        obj=json.loads(p.read_text());changed=False
        for n,h in report['sources'].items():
            if n in obj.get('sources',{}):obj['sources'][n]=h;changed=True
        if changed:obj['actuator_power_retry_hooks']=str(rp);p.write_text(json.dumps(obj,indent=2)+'\n')
    print(json.dumps(report,indent=2))
if __name__=='__main__':main()
