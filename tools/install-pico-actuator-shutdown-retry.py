"""Native actuator shutdown retains failed cleanup and shares release phase."""
from pathlib import Path
import hashlib,json
SOURCE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro/source/phoenix-kernel-recovery');D='techpack/camera/drivers/cam_sensor_module/cam_actuator/';OLD='49e5b1a6c8312b09347855256a7b3eb64b9001bd70a2639e9ad4b34f8a63c1d0'
BODY='''void cam_actuator_shutdown(struct cam_actuator_ctrl_t *a_ctrl)
{
	struct cam_actuator_soc_private *soc_private;
	struct cam_sensor_power_ctrl_t *power_info;
	int rc;
	lockdep_assert_held(&a_ctrl->actuator_mutex);
	if (a_ctrl->pico_acquire_cleanup_pending) {
		rc = pico_actuator_acquire_unwind_locked(a_ctrl);
		if (rc)
			CAM_ERR(CAM_ACTUATOR, "pending acquire shutdown failed: %d", rc);
		return;
	}
	if (a_ctrl->cam_act_state == CAM_ACTUATOR_INIT)
		return;
	soc_private = a_ctrl->soc_info.soc_private;
	if (!soc_private)
		return;
	power_info = &soc_private->power_info;
	a_ctrl->pico_release_cleanup_pending = true;
	/* Preserve native forced-close behavior for CONFIG/START and linked
	 * devices; CRM unlink/quiescence is a separate lifecycle requirement.
	 */
	if (a_ctrl->cam_act_state >= CAM_ACTUATOR_CONFIG) {
		if (!a_ctrl->pico_release_power_done) {
			rc = cam_actuator_power_down(a_ctrl);
			if (rc) {
				CAM_ERR(CAM_ACTUATOR, "Actuator Power down failed: %d", rc);
				return;
			}
			a_ctrl->pico_release_power_done = true;
		}
		a_ctrl->cam_act_state = CAM_ACTUATOR_ACQUIRE;
	}
	if (a_ctrl->cam_act_state >= CAM_ACTUATOR_ACQUIRE) {
		rc = cam_destroy_device_hdl(a_ctrl->bridge_intf.device_hdl);
		if (rc) {
			CAM_ERR(CAM_ACTUATOR, "destroying dhdl failed: %d", rc);
			return;
		}
		a_ctrl->bridge_intf.device_hdl = -1;
		a_ctrl->bridge_intf.link_hdl = -1;
		a_ctrl->bridge_intf.session_hdl = -1;
	}
	kfree(power_info->power_setting);
	kfree(power_info->power_down_setting);
	power_info->power_setting = NULL;
	power_info->power_down_setting = NULL;
	power_info->power_setting_size = 0;
	power_info->power_down_setting_size = 0;
	a_ctrl->last_flush_req = 0;
	a_ctrl->pico_release_cleanup_pending = false;
	a_ctrl->pico_release_power_done = false;
	a_ctrl->cam_act_state = CAM_ACTUATOR_INIT;
}

'''
def main():
    root=Path(__file__).resolve().parent.parent;rp=root/'reports/kernel-source/recovery-20261003/actuator-shutdown-retry-hooks.json';name=D+'cam_actuator_core.c';p=SOURCE/name;data=p.read_bytes();actual=hashlib.sha256(data).hexdigest();prior=json.loads(rp.read_text()) if rp.exists() else {}
    if actual==OLD:
        t=data.decode();start=t.index('void cam_actuator_shutdown(');end=t.index('int32_t cam_actuator_driver_cmd(',start);data=(t[:start]+BODY+t[end:]).encode();p.write_bytes(data)
    elif actual!=prior.get('sources',{}).get(name):raise RuntimeError('Preserve differing actuator source')
    report={'sources':{name:hashlib.sha256(data).hexdigest()},'preimage':OLD,'scope':'Void shutdown handles pending INIT acquire, retains state/resources after failed power/handle cleanup, shares reported release power stage; forced CONFIG/START/linked-close behavior retained; caller holds mutex, remove quiescence/lifecycle and lower phases pending','device_modified':False};rp.write_text(json.dumps(report,indent=2)+'\n')
    for f in rp.parent.glob('*hooks.json'):
        if f==rp:continue
        obj=json.loads(f.read_text())
        if name in obj.get('sources',{}):obj['sources'][name]=report['sources'][name];obj['actuator_shutdown_retry_hooks']=str(rp);f.write_text(json.dumps(obj,indent=2)+'\n')
    print(json.dumps(report,indent=2))
if __name__=='__main__':main()
