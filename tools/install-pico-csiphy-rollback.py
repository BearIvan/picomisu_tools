"""Install factory kernel-payload CSIPHY rollback without changing normal ioctl."""
from pathlib import Path
import hashlib
import json
SOURCE = Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro/source/phoenix-kernel-recovery')
D = 'techpack/camera/drivers/cam_sensor_module/cam_csiphy/'
OLD = {D+'cam_csiphy_core.c': '5f8c440f30d224604730a81fe34f1db35c31d8c17bb96a80c30c0620b8dae842', D+'cam_csiphy_core.h': '4f4baa5c3fade679f9543926b13ea2ba53fa11043d4535be675bde2fda55aebc'}
def main():
    root = Path(__file__).resolve().parent.parent
    path = root / 'reports/kernel-source/recovery-20261003/csiphy-rollback-hooks.json'
    previous = json.loads(path.read_text())['sources'] if path.exists() else {}
    content = {}
    for name, digest in OLD.items():
        data = (SOURCE/name).read_bytes();actual=hashlib.sha256(data).hexdigest()
        if actual == digest:
            text=data.decode()
            if name.endswith('.c'):
                text+='\n#include "pico_csiphy_rollback.inc"\n'
            else:
                anchor='int cam_csiphy_core_cfg(void *csiphy_dev, void *arg);'
                assert text.count(anchor)==1
                text=text.replace(anchor,anchor+'\n/* Trusted kernel cam_control payload only; not a userspace ioctl. */\nint32_t rollback_cam_csiphy_core_cfg(void *csiphy_dev, void *arg);')
            data=text.encode()
        elif actual != previous.get(name):
            raise RuntimeError('Preserve differing source: '+name)
        content[name]=data
    name=D+'pico_csiphy_rollback.inc';data=(root/'kernel-recovery'/name).read_bytes().replace(b'\r\n',b'\n')
    if (SOURCE/name).exists() and (SOURCE/name).read_bytes()!=data:
        if hashlib.sha256((SOURCE/name).read_bytes()).hexdigest()!=previous.get(name):
            raise RuntimeError('Preserve differing rollback')
    content[name]=data
    for name,data in content.items():
        if not (SOURCE/name).exists() or (SOURCE/name).read_bytes()!=data:
            (SOURCE/name).write_bytes(data)
    report={'sources':{name:hashlib.sha256(data).hexdigest() for name,data in content.items()},'preimages':OLD,'scope':'Kernel-payload factory CSIPHY stop/release; invalid input guards normalized; native failures can advance factory counters, not connected to retry ledger','device_modified':False}
    path.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
