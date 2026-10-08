"""Preserve native actuator normal-release resources/identity on failures."""
from pathlib import Path
import hashlib,json
SOURCE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro/source/phoenix-kernel-recovery');D='techpack/camera/drivers/cam_sensor_module/cam_actuator/'
OLD={D+'cam_actuator_core.c':'6ebee256ba8a4f28f62fe65fa2ea304a28cde3838b30e388087ef9424656fbfd',D+'cam_actuator_dev.h':'3c9dbe4ba1d444135a96e4b169283c854c15aea8c14f5d24b91229e2a3299ee9'}
def replace(t,a,b):
    if t.count(a)!=1:raise RuntimeError('Unexpected release retry anchor: '+a)
    return t.replace(a,b)
def main():
    root=Path(__file__).resolve().parent.parent;rp=root/'reports/kernel-source/recovery-20261003/actuator-release-retry-hooks.json';prior=json.loads(rp.read_text())['sources'] if rp.exists() else {};content={}
    for name,digest in OLD.items():
        data=(SOURCE/name).read_bytes();actual=hashlib.sha256(data).hexdigest()
        if actual==digest:
            t=data.decode()
            if name.endswith('.h'):t=replace(t,'\tbool pico_acquire_cleanup_pending;','\tbool pico_acquire_cleanup_pending;\n\tbool pico_release_cleanup_pending, pico_release_power_done;')
            else:
                t=replace(t,'if (a_ctrl->pico_acquire_cleanup_pending && cmd->op_code != CAM_ACQUIRE_DEV','if ((a_ctrl->pico_acquire_cleanup_pending || a_ctrl->pico_release_cleanup_pending) && cmd->op_code != CAM_ACQUIRE_DEV')
                start=t.index('\tcase CAM_RELEASE_DEV: {');end=t.index('\tcase CAM_QUERY_CAP:',start);body=t[start:end]
                pstart=body.index('\t\tif (a_ctrl->cam_act_state == CAM_ACTUATOR_CONFIG) {');pend=body.index('\t\tif (a_ctrl->bridge_intf.device_hdl == -1)',pstart);body=body[:pstart]+body[pend:]
                body=replace(body,'\t\tif (a_ctrl->bridge_intf.device_hdl == -1) {','\t\tif ((a_ctrl->cam_act_state != CAM_ACTUATOR_CONFIG && a_ctrl->cam_act_state != CAM_ACTUATOR_ACQUIRE) || a_ctrl->bridge_intf.device_hdl <= 0) {')
                body=replace(body,'\t\trc = cam_destroy_device_hdl(a_ctrl->bridge_intf.device_hdl);','\t\ta_ctrl->pico_release_cleanup_pending = true;\n\t\tif (a_ctrl->cam_act_state == CAM_ACTUATOR_CONFIG && !a_ctrl->pico_release_power_done) {\n\t\t\trc = cam_actuator_power_down(a_ctrl);\n\t\t\tif (rc)\n\t\t\t\tgoto release_mutex;\n\t\t\ta_ctrl->pico_release_power_done = true;\n\t\t}\n\t\trc = cam_destroy_device_hdl(a_ctrl->bridge_intf.device_hdl);')
                body=replace(body,'\t\tif (rc < 0)\n\t\t\tCAM_ERR(CAM_ACTUATOR, "destroying the device hdl");','\t\tif (rc) {\n\t\t\tCAM_ERR(CAM_ACTUATOR, "destroying the device hdl: %d", rc);\n\t\t\tgoto release_mutex;\n\t\t}\n\t\ta_ctrl->pico_release_cleanup_pending = false;\n\t\ta_ctrl->pico_release_power_done = false;');t=t[:start]+body+t[end:]
            data=t.encode()
        elif actual!=prior.get(name):raise RuntimeError('Preserve differing actuator source: '+name)
        content[name]=data
    name=D+'pico_memento_actuator.inc';data=(root/'kernel-recovery'/name).read_bytes().replace(b'\r\n',b'\n');actual=hashlib.sha256((SOURCE/name).read_bytes()).hexdigest()
    if actual not in ['3eed0311beeceb17094acae6ade57c54dec7d9c84db4aa628448be53869a5dec',prior.get(name),hashlib.sha256(data).hexdigest()]:raise RuntimeError('Preserve differing actuator adapter')
    content[name]=data
    for name,data in content.items():
        if (SOURCE/name).read_bytes()!=data:(SOURCE/name).write_bytes(data)
    report={'sources':{n:hashlib.sha256(v).hexdigest() for n,v in content.items()},'preimages':OLD,'scope':'Normal actuator release link/state/identity guards before power effects; reported-successful power stage shared between native and memento; failed destroy retains handles/state/power allocations; config/start/stop pending gate; lower core/I-O phases/shutdown/removal/runtime pending','device_modified':False};rp.write_text(json.dumps(report,indent=2)+'\n')
    for p in rp.parent.glob('*hooks.json'):
        if p==rp:continue
        obj=json.loads(p.read_text());changed=False
        for n,h in report['sources'].items():
            if n in obj.get('sources',{}):obj['sources'][n]=h;changed=True
        if changed:obj['actuator_release_retry_hooks']=str(rp);p.write_text(json.dumps(obj,indent=2)+'\n')
    print(json.dumps(report,indent=2))
if __name__=='__main__':main()
