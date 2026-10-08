"""Observe native actuator/OIS/EEPROM/Flash acquire packets before usercopy."""
from pathlib import Path
import hashlib,json,re
SOURCE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro/source/phoenix-kernel-recovery');D='techpack/camera/drivers/cam_sensor_module/'
PEERS=[('cam_actuator/cam_actuator_core.c','9c3d9d8a5567c6b69324f8f5c6518d0770852a133209ddac304bf0dc1a65ba2e','a_ctrl','actuator_acq_dev',0x10009,'cam_actuator_core.h'),('cam_ois/cam_ois_core.c','0e8f5c5dce4fbaaa3e3c94067fd2b18ca78bf6cc43607d73c51ffbfbb47c7a59','o_ctrl','ois_acq_dev',0x1000d,'cam_ois_core.h'),('cam_eeprom/cam_eeprom_core.c','782d86d3efed01b3bf486bd6484050d336a77e5abb3ffd937d96e63320bd4669','e_ctrl','eeprom_acq_dev',0x1000c,'cam_eeprom_core.h'),('cam_flash/cam_flash_dev.c','8d206c1fde3180cd03b6c3bfc7b69e595a13a710e0466651725a7a6efc578698','fctrl','flash_acq_dev',0x1000b,'cam_flash_core.h')]
def main():
    root=Path(__file__).resolve().parent.parent;path=root/'reports/kernel-source/recovery-20261003/peer-acquire-capture-hooks.json';previous=json.loads(path.read_text())['sources'] if path.exists() else {};content={}
    for rel,digest,owner,packet,entity,header in PEERS:
        name=D+rel;data=(SOURCE/name).read_bytes();actual=hashlib.sha256(data).hexdigest()
        if actual==digest:
            text=data.decode();anchor='#include "'+header+'"';assert text.count(anchor)==1;text=text.replace(anchor,anchor+'\n#include "../../cam_core/pico_camera_memento_capture.h"')
            lines=text.splitlines(keepends=True);positions=[];offset=0
            for i,line in enumerate(lines):
                if line.lstrip().startswith(('if (copy_to_user','rc = copy_to_user')) and packet in ''.join(lines[i:i+4]):
                    positions.append((offset,line[:len(line)-len(line.lstrip())]))
                offset+=len(line)
            if len(positions)!=1:raise RuntimeError('Unexpected copyout anchors: '+name)
            position,indent=positions[0];hook=indent+f'pico_memento_capture_native({owner}, 0x{entity:x}, CAM_ACQUIRE_DEV,\n'+indent+f'\t&{packet}, sizeof({packet}),\n'+indent+f'\t(s32){packet}.device_handle > 0 ? 0 : -EINVAL,\n'+indent+f'\t(s32){packet}.device_handle > 0);\n';text=text[:position]+hook+text[position:];data=text.encode()
        elif actual!=previous.get(name):raise RuntimeError('Preserve differing native peer: '+name)
        content[name]=data
    for name,data in content.items():
        if (SOURCE/name).read_bytes()!=data:(SOURCE/name).write_bytes(data)
    report={'sources':{n:hashlib.sha256(v).hexdigest() for n,v in content.items()},'preimages':{D+row[0]:row[1] for row in PEERS},'entities':{row[2]:hex(row[4]) for row in PEERS},'scope':'Native acquire packet observers wired before copyout; original results preserved; peer partial-acquire cleanup and dispatch integration pending','device_modified':False};path.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
