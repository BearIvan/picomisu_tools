"""Preserve EEPROM shutdown stages and unwind pending INIT acquisition."""
from pathlib import Path
import hashlib,json
SOURCE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro/source/phoenix-kernel-recovery')
D='techpack/camera/drivers/cam_sensor_module/cam_eeprom/'
OLD='7219301a5bda4b4c2677b7c8111d76dd223289edc809a58b1cdd5fb1a919901e'
def replace(text,old,new):
    if text.count(old)!=1:raise RuntimeError('Unexpected shutdown anchor: '+old)
    return text.replace(old,new)
def main():
    root=Path(__file__).resolve().parent.parent;report_path=root/'reports/kernel-source/recovery-20261003/eeprom-shutdown-retry-hooks.json';name=D+'cam_eeprom_core.c';path=SOURCE/name;data=path.read_bytes();actual=hashlib.sha256(data).hexdigest()
    previous=json.loads(report_path.read_text()) if report_path.exists() else {}
    if actual==OLD:
        text=data.decode();start=text.index('void cam_eeprom_shutdown(');end=text.index('\n/**',start);body=text[start:end]
        body=replace(body,'\tstruct cam_eeprom_soc_private  *soc_private =\n\t\t(struct cam_eeprom_soc_private *)e_ctrl->soc_info.soc_private;\n\tstruct cam_sensor_power_ctrl_t *power_info = &soc_private->power_info;', '\tstruct cam_eeprom_soc_private *soc_private;\n\tstruct cam_sensor_power_ctrl_t *power_info;\n\n\tlockdep_assert_held(&e_ctrl->eeprom_mutex);\n\tif (e_ctrl->pico_acquire_cleanup_pending) {\n\t\trc = pico_eeprom_acquire_unwind_locked(e_ctrl);\n\t\tif (rc)\n\t\t\tCAM_ERR(CAM_EEPROM, "pending acquire shutdown failed: %d", rc);\n\t\treturn;\n\t}')
        body=replace(body,'\tif (e_ctrl->cam_eeprom_state == CAM_EEPROM_INIT)\n\t\treturn;','\tif (e_ctrl->cam_eeprom_state == CAM_EEPROM_INIT)\n\t\treturn;\n\tsoc_private = e_ctrl->soc_info.soc_private;\n\tpower_info = &soc_private->power_info;')
        body=replace(body,'\t\tif (rc < 0)\n\t\t\tCAM_ERR(CAM_EEPROM, "EEPROM Power down failed");','\t\tif (rc) {\n\t\t\tCAM_ERR(CAM_EEPROM, "EEPROM Power down failed: %d", rc);\n\t\t\treturn;\n\t\t}')
        body=replace(body,'\t\tif (rc < 0)\n\t\t\tCAM_ERR(CAM_EEPROM, "destroying the device hdl");','\t\tif (rc) {\n\t\t\tCAM_ERR(CAM_EEPROM, "destroying the device hdl: %d", rc);\n\t\t\treturn;\n\t\t}')
        data=(text[:start]+body+text[end:]).encode();path.write_bytes(data)
    elif actual!=previous.get('sources',{}).get(name):raise RuntimeError('Preserve differing EEPROM core')
    report={'sources':{name:hashlib.sha256(data).hexdigest()},'preimage':OLD,'scope':'Void native shutdown retries pending INIT acquisition; retains CONFIG on power failure and ACQUIRE/handles/allocations on destroy failure; last-close caller remains void; remove quiescence/lifetime unresolved','device_modified':False}
    report_path.write_text(json.dumps(report,indent=2)+'\n')
    for filename in ['peer-acquire-capture-hooks.json','eeprom-acquire-retry-hooks.json']:
        p=report_path.parent/filename;obj=json.loads(p.read_text());obj['sources'][name]=report['sources'][name];obj['eeprom_shutdown_retry_hooks']=str(report_path);p.write_text(json.dumps(obj,indent=2)+'\n')
    print(json.dumps(report,indent=2))
if __name__=='__main__':main()
