"""Install task/owner-bound observer and native sensor acquire packet hook."""
from pathlib import Path
import hashlib,json
SOURCE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro/source/phoenix-kernel-recovery')
NATIVE='techpack/camera/drivers/cam_sensor_module/cam_sensor/cam_sensor_core.c'
OLD='932904c5446395df981e497e9b43f853b438ed4c9bdcbfdfc130dd0ab2b107ab'
def main():
    root=Path(__file__).resolve().parent.parent;path=root/'reports/kernel-source/recovery-20261003/memento-capture-hooks.json';previous=json.loads(path.read_text())['sources'] if path.exists() else {};data=(SOURCE/NATIVE).read_bytes();actual=hashlib.sha256(data).hexdigest()
    if actual==OLD:
        text=data.decode();anchor='#include "pico_memento_sensor.h"';assert text.count(anchor)==1;text=text.replace(anchor,anchor+'\n#include "../../cam_core/pico_camera_memento_capture.h"')
        anchor='\t\tif (copy_to_user(u64_to_user_ptr(cmd->handle),\n\t\t\t&sensor_acq_dev,';assert text.count(anchor)==1
        hook='\t\tpico_memento_capture_native(s_ctrl, 0x10001, CAM_ACQUIRE_DEV,\n\t\t\t&sensor_acq_dev, sizeof(sensor_acq_dev),\n\t\t\t(s32)sensor_acq_dev.device_handle > 0 ? 0 : -EINVAL,\n\t\t\t(s32)sensor_acq_dev.device_handle > 0);\n'
        text=text.replace(anchor,hook+anchor);data=text.encode()
    elif actual!=previous.get(NATIVE):raise RuntimeError('Preserve differing sensor core')
    data=data.replace(b'sensor_acq_dev.device_handle > 0', b'(s32)sensor_acq_dev.device_handle > 0') if b'(s32)sensor_acq_dev.device_handle > 0' not in data else data
    content={NATIVE:data};d='techpack/camera/drivers/cam_core/'
    for suffix in ['c','h']:
        name=d+'pico_camera_memento_capture.'+suffix;data=(root/'kernel-recovery'/name).read_bytes().replace(b'\r\n',b'\n')
        if (SOURCE/name).exists() and (SOURCE/name).read_bytes()!=data and hashlib.sha256((SOURCE/name).read_bytes()).hexdigest()!=previous.get(name):raise RuntimeError('Preserve differing capture')
        content[name]=data
    for name,data in content.items():
        if not (SOURCE/name).exists() or (SOURCE/name).read_bytes()!=data:(SOURCE/name).write_bytes(data)
    makefile=SOURCE/d/'Makefile';text=makefile.read_text();line='obj-$(CONFIG_SPECTRA_CAMERA) += pico_camera_memento_capture.o\n'
    if line not in text:makefile.write_text(text+line)
    report={'sources':{n:hashlib.sha256(v).hexdigest() for n,v in content.items()},'preimage':OLD,'scope':'Observer wired at native sensor handle creation before copyout/powerup; caller dispatch, partial-acquire rollback and other native hooks pending','device_modified':False};path.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
