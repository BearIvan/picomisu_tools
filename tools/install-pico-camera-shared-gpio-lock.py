"""Keep a shared GPIO record protected through its count and hardware update."""
from pathlib import Path
import hashlib
import importlib.util
import json
BASE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro')
SOURCE=BASE/'source/phoenix-kernel-recovery'
ROOT=Path(__file__).resolve().parents[1]
NAME='techpack/camera/drivers/cam_sensor_module/cam_res_mgr/cam_res_mgr.c'
PRE='08b0e70407db2fc6f8c26dceefb36e201f0f8f7cd3c0e0f8de8c8364425412d1'
def main():
    path=SOURCE/NAME;rp=ROOT/'reports/kernel-source/recovery-20261004/shared-gpio-lock-hooks.json'
    current=hashlib.sha256(path.read_bytes()).hexdigest()
    if rp.exists() and json.loads(rp.read_text())['sources'][NAME]==current:
        print('Already installed');return
    if current!=PRE:raise RuntimeError('Unexpected resource manager preimage')
    spec=importlib.util.spec_from_file_location('ex',Path(__file__).with_name('test-pico-sensor-mono-hook.py'))
    ex=importlib.util.module_from_spec(spec);spec.loader.exec_module(ex)
    source=path.read_text();old=ex.function(source,'int cam_res_mgr_gpio_set_value(')
    new=old.replace('\t\tmutex_unlock(&cam_res->gpio_res_lock);','\t\t/* A found record remains owned until its update completes. */\n\t\tif (!found)\n\t\t\tmutex_unlock(&cam_res->gpio_res_lock);')
    ending='\t\t}\n\t}\n\n\treturn rc;'
    if new.count(ending)!=1:raise RuntimeError('Unexpected function ending')
    new=new.replace(ending,'\t\t}\n\t\tmutex_unlock(&cam_res->gpio_res_lock);\n\t}\n\n\treturn rc;')
    path.write_text(source.replace(old,new))
    rp.write_text(json.dumps({'preimages':{NAME:PRE},'sources':{NAME:hashlib.sha256(path.read_bytes()).hexdigest()},'scope':'Shared GPIO record lookup, counter update and GPIO provider call serialized against record removal. Existing high/low vote semantics and public layout unchanged; manager lifetime and retry vote ownership remain pending.','device_modified':False},indent=2)+'\n')
    print(rp)
if __name__=='__main__':main()
