"""Drain initialized actuator settings lists after successful handle teardown."""
from pathlib import Path
import hashlib,json
SOURCE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro/source/phoenix-kernel-recovery');D='techpack/camera/drivers/cam_sensor_module/cam_actuator/'
OLD={D+'cam_actuator_core.c':'dd86f9287492fd0c7cdc1f4d613ea77dd725b1accd7cd69146353320f735d6ea',D+'pico_memento_actuator.inc':'1bdd041626e38a784ae9b30a2b17058ee504b8437b53f25d8121ef63d1092ae1'}
HELPER='''static void pico_actuator_clear_requests_locked(struct cam_actuator_ctrl_t *a_ctrl)
{
	int i;
	lockdep_assert_held(&a_ctrl->actuator_mutex);
	/* Probe initializes these list heads before a handle can be acquired.
	 * delete_request accepts an initialized empty list and cannot fail here.
	 */
	delete_request(&a_ctrl->i2c_data.init_settings);
	a_ctrl->i2c_data.init_settings.request_id = 0;
	if (a_ctrl->i2c_data.per_frame) {
		for (i = 0; i < MAX_PER_FRAME_ARRAY; i++) {
			delete_request(&a_ctrl->i2c_data.per_frame[i]);
			a_ctrl->i2c_data.per_frame[i].request_id = 0;
		}
	}
}

'''
def main():
    root=Path(__file__).resolve().parent.parent;rp=root/'reports/kernel-source/recovery-20261003/actuator-request-cleanup-hooks.json';prior=json.loads(rp.read_text()) if rp.exists() else {};content={}
    for name,digest in OLD.items():
        data=(SOURCE/name).read_bytes();actual=hashlib.sha256(data).hexdigest()
        if actual==digest:
            t=data.decode()
            if name.endswith('.c'):
                anchor='void cam_actuator_shutdown('
                if t.count(anchor)!=1:raise RuntimeError('Shutdown anchor')
                t=t.replace(anchor,HELPER+anchor)
                anchor='\tkfree(power_info->power_setting);'
                start=t.index('void cam_actuator_shutdown(');end=t.index('int32_t cam_actuator_driver_cmd(',start)
                body=t[start:end]
                if body.count(anchor)!=1:raise RuntimeError('Shutdown final cleanup anchor')
                t=t[:start]+body.replace(anchor,'\tpico_actuator_clear_requests_locked(a_ctrl);\n'+anchor)+t[end:]
                anchor='\t\ta_ctrl->pico_release_cleanup_pending = false;'
                if t.count(anchor)!=1:raise RuntimeError('Native release anchor')
                t=t.replace(anchor,'\t\tpico_actuator_clear_requests_locked(a_ctrl);\n'+anchor)
            else:
                anchor='\tactuator->pico_release_cleanup_pending = false;'
                if t.count(anchor)!=1:raise RuntimeError('Memento release anchor')
                t=t.replace(anchor,'\tpico_actuator_clear_requests_locked(actuator);\n'+anchor)
            data=t.encode()
        elif actual!=prior.get('sources',{}).get(name):raise RuntimeError('Preserve differing source: '+name)
        content[name]=data
    for name,data in content.items():
        if (SOURCE/name).read_bytes()!=data:(SOURCE/name).write_bytes(data)
        if name.endswith('.inc'):(root/'kernel-recovery'/name).write_bytes(data)
    report={'sources':{n:hashlib.sha256(d).hexdigest() for n,d in content.items()},'preimages':OLD,'scope':'Drain initialized init/per-frame lists only after successful power/handle cleanup in shutdown/native release/memento; retain settings on earlier failure; CRM callback quiescence/physical remove remain pending','device_modified':False};rp.write_text(json.dumps(report,indent=2)+'\n')
    for p in rp.parent.glob('*hooks.json'):
        if p==rp:continue
        obj=json.loads(p.read_text());changed=False
        for n,h in report['sources'].items():
            if n in obj.get('sources',{}):obj['sources'][n]=h;changed=True
        if changed:obj['actuator_request_cleanup_hooks']=str(rp);p.write_text(json.dumps(obj,indent=2)+'\n')
    print(json.dumps(report,indent=2))
if __name__=='__main__':main()
