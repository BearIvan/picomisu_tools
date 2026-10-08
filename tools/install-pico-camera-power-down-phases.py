"""Replace false-success common power-down with retained private retry phases."""
from pathlib import Path
import hashlib,importlib.util,json
BASE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro');SOURCE=BASE/'source/phoenix-kernel-recovery';ROOT=Path(__file__).resolve().parents[1]
D='techpack/camera/drivers/cam_sensor_module/cam_sensor_utils/'
NAME=D+'cam_sensor_util.c';NEW=D+'pico_camera_power_down.inc'
PRE='2b33706eea22f1b2ac02e0272c607e0765b76e859ae35076afb88478438c2c6f'
def main():
    rp=ROOT/'reports/kernel-source/recovery-20261004/camera-power-down-phases-hooks.json'
    if rp.exists() and all(hashlib.sha256((SOURCE/n).read_bytes()).hexdigest()==h for n,h in json.loads(rp.read_text())['sources'].items()):print('Already installed');return
    if hashlib.sha256((SOURCE/NAME).read_bytes()).hexdigest()!=PRE:raise RuntimeError('Unexpected common power source preimage')
    spec=importlib.util.spec_from_file_location('ex',Path(__file__).with_name('test-pico-sensor-mono-hook.py'));ex=importlib.util.module_from_spec(spec);spec.loader.exec_module(ex)
    source=(SOURCE/NAME).read_text();old=ex.function(source,'int cam_sensor_util_power_down(');source=source.replace(old,'')
    unused='static struct cam_sensor_power_setting*\n'+ex.function(source,'msm_camera_get_power_settings(struct')
    if source.count(unused)!=1:raise RuntimeError('Unexpected former lookup helper')
    source=source.replace(unused,'')
    source=source.replace('int cam_sensor_core_power_up(', '#include <linux/mutex.h>\n#include <linux/list.h>\n#include "pico_camera_power_down.inc"\n\nint cam_sensor_core_power_up(',1)
    old=ex.function(source,'int cam_sensor_core_power_up(');new=old.replace('if (!ctrl) {','if (!ctrl || !soc_info) {',1)
    marker='\tgpio_num_info = ctrl->gpio_num_info;'
    new=new.replace(marker,'\tif (pico_camera_power_down_pending(ctrl))\n\t\treturn -EBUSY;\n\n'+marker,1)
    source=source.replace(old,new)
    (SOURCE/NEW).write_bytes((ROOT/'kernel-recovery'/NEW).read_bytes());(SOURCE/NAME).write_text(source.rstrip()+'\n')
    rp.write_text(json.dumps({'preimages':{NAME:PRE},'sources':{n:hashlib.sha256((SOURCE/n).read_bytes()).hexdigest() for n in [NAME,NEW]},'scope':'Common successful-power-up shutdown retains private regulator/clock/GPIO/pinctrl phases on error; pending shutdown blocks new native power-up. Original partial power-up unwind, physical removal/devres, provider and hardware validation still pending. Public structs unchanged.','device_modified':False},indent=2)+'\n');print(rp)
if __name__=='__main__':main()
