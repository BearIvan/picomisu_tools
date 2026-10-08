"""Install native phased actuator rollback, preserving normal ioctl and existing edits."""
from pathlib import Path
import hashlib,json
SOURCE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro/source/phoenix-kernel-recovery')
D='techpack/camera/drivers/cam_sensor_module/cam_actuator/'
OLD='4b52add1db6278fb856d465b4ee72474e6b7e9b3046db2b0f2c8cb35a2429bd5'
def main():
    root=Path(__file__).resolve().parent.parent;path=root/'reports/kernel-source/recovery-20261003/memento-actuator-hooks.json'
    previous=json.loads(path.read_text())['sources'] if path.exists() else {}
    name=D+'cam_actuator_core.c';data=(SOURCE/name).read_bytes();digest=hashlib.sha256(data).hexdigest()
    if digest==OLD:
        text=data.decode();anchor='#include "cam_actuator_core.h"';assert text.count(anchor)==1
        text=text.replace(anchor,anchor+'\n#include "pico_memento_actuator.h"');text+='\n#include "pico_memento_actuator.inc"\n';data=text.encode()
    elif digest!=previous.get(name):raise RuntimeError('Preserve differing native actuator core')
    content={name:data}
    for suffix in ['h','inc']:
        name=D+'pico_memento_actuator.'+suffix;data=(root/'kernel-recovery'/name).read_bytes().replace(b'\r\n',b'\n')
        if (SOURCE/name).exists() and (SOURCE/name).read_bytes()!=data and hashlib.sha256((SOURCE/name).read_bytes()).hexdigest()!=previous.get(name):raise RuntimeError('Preserve differing adapter')
        content[name]=data
    for name,data in content.items():
        if not (SOURCE/name).exists() or (SOURCE/name).read_bytes()!=data:(SOURCE/name).write_bytes(data)
    report={'sources':{name:hashlib.sha256(data).hexdigest() for name,data in content.items()},'preimage':OLD,'scope':'Native actuator controller kernel-payload stop/release adapter with error/phase retention; subdevice close hooks pending','device_modified':False}
    path.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
