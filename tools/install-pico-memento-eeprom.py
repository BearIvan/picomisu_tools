"""Install native phased eeprom rollback, preserving normal ioctl and existing edits."""
from pathlib import Path
import hashlib,json
SOURCE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro/source/phoenix-kernel-recovery')
D='techpack/camera/drivers/cam_sensor_module/cam_eeprom/'
OLD='d36c7aa51bc0a9731a46783954beae02a24948f617737fe540aecfe24683b6c0'
def main():
    root=Path(__file__).resolve().parent.parent;path=root/'reports/kernel-source/recovery-20261003/memento-eeprom-hooks.json'
    previous=json.loads(path.read_text())['sources'] if path.exists() else {}
    name=D+'cam_eeprom_core.c';data=(SOURCE/name).read_bytes();digest=hashlib.sha256(data).hexdigest()
    if digest==OLD:
        text=data.decode();anchor='#include "cam_eeprom_core.h"';assert text.count(anchor)==1
        text=text.replace(anchor,anchor+'\n#include "pico_memento_eeprom.h"');text+='\n#include "pico_memento_eeprom.inc"\n';data=text.encode()
    elif digest!=previous.get(name):raise RuntimeError('Preserve differing native eeprom core')
    content={name:data}
    for suffix in ['h','inc']:
        name=D+'pico_memento_eeprom.'+suffix;data=(root/'kernel-recovery'/name).read_bytes().replace(b'\r\n',b'\n')
        if (SOURCE/name).exists() and (SOURCE/name).read_bytes()!=data and hashlib.sha256((SOURCE/name).read_bytes()).hexdigest()!=previous.get(name):raise RuntimeError('Preserve differing adapter')
        content[name]=data
    for name,data in content.items():
        if not (SOURCE/name).exists() or (SOURCE/name).read_bytes()!=data:(SOURCE/name).write_bytes(data)
    report={'sources':{name:hashlib.sha256(data).hexdigest() for name,data in content.items()},'preimage':OLD,'scope':'Native eeprom controller kernel-payload stop/release adapter with error/phase retention; subdevice close hooks pending','device_modified':False}
    path.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
