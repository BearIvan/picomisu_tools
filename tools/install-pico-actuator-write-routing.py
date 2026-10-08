"""Translate actuator sequential-write mode at the native master boundary."""
from pathlib import Path
import hashlib,json
SOURCE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro/source/phoenix-kernel-recovery')
NAME='techpack/camera/drivers/cam_sensor_module/cam_actuator/cam_actuator_core.c'
OLD='ee0b55ad93d24e205c9fc1221ed6cc5eb034335dc1f4ddf7cea547529f5d3411'
def main():
    root=Path(__file__).resolve().parent.parent; rp=root/'reports/kernel-source/recovery-20261003/actuator-write-routing-hooks.json'
    data=(SOURCE/NAME).read_bytes();actual=hashlib.sha256(data).hexdigest();prior=json.loads(rp.read_text()) if rp.exists() else {}
    if actual==OLD:
        t=data.decode();start=t.index('static int32_t cam_actuator_i2c_modes_util(');end=t.index('int32_t cam_actuator_slaveInfo_pkt_parser(',start);body=t[start:end]
        old='\t\t\t&(i2c_list->i2c_settings),\n\t\t\t0);'
        new='\t\t\t&(i2c_list->i2c_settings),\n\t\t\tio_master_info->master_type == I2C_MASTER ?\n\t\t\tCAM_SENSOR_I2C_WRITE_SEQ : 0);'
        if body.count(old)!=1:raise RuntimeError('Unexpected actuator sequential mode anchor')
        data=(t[:start]+body.replace(old,new)+t[end:]).encode()
    elif actual!=prior.get('sources',{}).get(NAME):raise RuntimeError('Preserve differing actuator core')
    # Keep the failing reproduction before passing tests replace its result.
    result=SOURCE.parent.parent/'out/phoenix-kernel-recovery/actuator-write-routing-tests/result.json'
    if result.exists() and json.loads(result.read_text())['exit_code']!=0:
        failed=result.with_name('pre-fix-result.json')
        if not failed.exists():failed.write_bytes(result.read_bytes())
    if (SOURCE/NAME).read_bytes()!=data:(SOURCE/NAME).write_bytes(data)
    report={'sources':{NAME:hashlib.sha256(data).hexdigest()},'preimages':{NAME:OLD},'scope':'Actuator sequential mode CCI/SPI 0 versus QUP native CAM_SENSOR_I2C_WRITE_SEQ; no shared API/driver layout change; native dispatch tested with modeled bus providers, hardware pending','device_modified':False}
    rp.write_text(json.dumps(report,indent=2)+'\n')
    for p in rp.parent.glob('*hooks.json'):
        if p==rp:continue
        obj=json.loads(p.read_text())
        if NAME in obj.get('sources',{}):
            obj['sources'][NAME]=report['sources'][NAME];obj['actuator_write_routing_hooks']=str(rp);p.write_text(json.dumps(obj,indent=2)+'\n')
    print(json.dumps(report,indent=2))
if __name__=='__main__':main()
