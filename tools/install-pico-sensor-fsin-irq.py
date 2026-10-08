"""Transactional shared FSIN IRQ ownership and native acquire error propagation."""
from pathlib import Path
import hashlib,json
SOURCE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro/source/phoenix-kernel-recovery')
D='techpack/camera/drivers/cam_sensor_module/cam_sensor/'
OLD={D+'cam_sensor_core.c':'095560a5d0fd0157d26408e38966f2af502ddfae70982db9a2fbe86c76685057',D+'cam_sensor_dev.h':'c218c56aaa6a92ccfb73c7ba9ff81ea81be18833233532714d1618c60876e68f'}
def main():
    root=Path(__file__).resolve().parent.parent;path=root/'reports/kernel-source/recovery-20261003/sensor-fsin-irq-hooks.json';previous=json.loads(path.read_text())['sources'] if path.exists() else {};content={}
    for name,digest in OLD.items():
        data=(SOURCE/name).read_bytes();actual=hashlib.sha256(data).hexdigest()
        if actual==digest:
            text=data.decode()
            if name.endswith('.c'):
                start=text.index('int cam_sensor_register_irq(');end=text.index('#endif\nint32_t cam_sensor_driver_cmd(',start);text=text[:start]+'#include "pico_sensor_fsin_irq.inc"\n'+text[end:]
                reset='\t\tFsin_irq_register = 0;//when do recovey Fsin_irq_register should be clear';assert text.count(reset)==1;text=text.replace(reset,'\t\t/* Live FSIN ownership is maintained by register/unregister only. */')
                start=text.index('\tcase CAM_ACQUIRE_DEV: {',text.index('int32_t cam_sensor_driver_cmd('));end=text.index('\tcase CAM_RELEASE_DEV:',start);body=text[start:end]
                anchor='\t\tcam_sensor_register_irq(s_ctrl);';assert body.count(anchor)==1
                replacement='\t\trc = cam_sensor_register_irq(s_ctrl);\n\t\tif (rc) {\n\t\t\tunwind_rc = cam_destroy_device_hdl((s32)sensor_acq_dev.device_handle);\n\t\t\tpico_memento_capture_unwind(s_ctrl, 0x10001, CAM_ACQUIRE_DEV, unwind_rc);\n\t\t\tif (!unwind_rc) {\n\t\t\t\ts_ctrl->bridge_intf.device_hdl = -1;\n\t\t\t\ts_ctrl->bridge_intf.session_hdl = -1;\n\t\t\t\ts_ctrl->bridge_intf.link_hdl = -1;\n\t\t\t}\n\t\t\tgoto release_mutex;\n\t\t}'
                body=body.replace(anchor,replacement);text=text[:start]+body+text[end:]
            else:
                anchor='\tint32_t open_cnt;';assert text.count(anchor)==1;text=text.replace(anchor,anchor+'\n\t/* Recovery-owned shared FSIN reference, following the native prefix. */\n\tbool pico_fsin_irq_owned;')
            data=text.encode()
        elif actual!=previous.get(name):raise RuntimeError('Preserve differing FSIN source: '+name)
        content[name]=data
    name=D+'pico_sensor_fsin_irq.inc';data=(root/'kernel-recovery'/name).read_bytes().replace(b'\r\n',b'\n')
    if (SOURCE/name).exists() and (SOURCE/name).read_bytes()!=data and hashlib.sha256((SOURCE/name).read_bytes()).hexdigest()!=previous.get(name):raise RuntimeError('Preserve differing FSIN implementation')
    content[name]=data
    for name,data in content.items():
        if not (SOURCE/name).exists() or (SOURCE/name).read_bytes()!=data:(SOURCE/name).write_bytes(data)
    report={'sources':{n:hashlib.sha256(v).hexdigest() for n,v in content.items()},'preimages':OLD,'scope':'Shared FSIN transaction/per-controller ownership and stable IRQ cookie; native acquire rejects IRQ failure and attempts handle unwind; failed power-up IRQ cleanup remains pending','device_modified':False};path.write_text(json.dumps(report,indent=2)+'\n')
    capture_path=root/'reports/kernel-source/recovery-20261003/memento-capture-hooks.json';capture=json.loads(capture_path.read_text());capture['sources'][D+'cam_sensor_core.c']=report['sources'][D+'cam_sensor_core.c'];capture['sensor_fsin_irq_hooks']=str(path);capture_path.write_text(json.dumps(capture,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
