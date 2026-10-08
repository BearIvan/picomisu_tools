"""Replace native partial power-up unwind with validated acquisition and a retained unwind ledger."""
from pathlib import Path
import hashlib,importlib.util,json
BASE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro');SOURCE=BASE/'source/phoenix-kernel-recovery';ROOT=Path(__file__).resolve().parents[1]
D='techpack/camera/drivers/cam_sensor_module/cam_sensor_utils/'
NAME=D+'cam_sensor_util.c';DOWN=D+'pico_camera_power_down.inc';UP=D+'pico_camera_power_up.inc'
PRE={NAME:'be1e89a6f04a77e7c9c1909cd3e0650e934b06ba014fe0a6e2bf817e38798e95',DOWN:'97ad005309412b9bbbe39f40ba24c1de745b0991cc5d910adf389852823a6a8d'}
SCOPE=('Power-up validates sizes, clock/regulator indices, GPIO info and duplicate regulator acquisition before any change; '
       'former false-success paths return errors. A partial acquisition becomes an unwind ledger that replays completed steps in reverse '
       '(partial MCLK clocks, got-but-disabled regulators) through the common phased shutdown and is retried by the next power-up/down. '
       'Common shutdown now logs and skips unmatched regulator/unknown steps like factory power-down; GPIO table release result ignored '
       '(fails only without a table). cam_config_mclk_reg removed (wrong power_down_setting index). Public structs unchanged. '
       'Manager lifetime, physical remove/devres, real providers and hardware still pending.')
def main():
    rp=ROOT/'reports/kernel-source/recovery-20261004/camera-power-up-unwind-hooks.json'
    if rp.exists() and all(hashlib.sha256((SOURCE/n).read_bytes()).hexdigest()==h for n,h in json.loads(rp.read_text())['sources'].items()):print('Already installed');return
    for n,h in PRE.items():
        if hashlib.sha256((SOURCE/n).read_bytes()).hexdigest()!=h:raise RuntimeError('Unexpected preimage: '+n)
    spec=importlib.util.spec_from_file_location('ex',Path(__file__).with_name('test-pico-sensor-mono-hook.py'));ex=importlib.util.module_from_spec(spec);spec.loader.exec_module(ex)
    source=(SOURCE/NAME).read_text()
    mclk='static int '+ex.function(source,'cam_config_mclk_reg(struct')
    if source.count(mclk)!=1:raise RuntimeError('Unexpected MCLK unwind helper')
    source=source.replace(mclk+'\n\n','',1)
    up=ex.function(source,'int cam_sensor_core_power_up(')
    if source.count(up)!=1 or '#include "pico_camera_power_down.inc"\n\n'+up not in source:raise RuntimeError('Unexpected power-up layout')
    source=source.replace(up,'#include "pico_camera_power_up.inc"',1)
    for n in [DOWN,UP]:(SOURCE/n).write_bytes((ROOT/'kernel-recovery'/n).read_bytes())
    (SOURCE/NAME).write_text(source.rstrip()+'\n')
    rp.write_text(json.dumps({'preimages':PRE,'sources':{n:hashlib.sha256((SOURCE/n).read_bytes()).hexdigest() for n in [NAME,DOWN,UP]},'scope':SCOPE,'device_modified':False},indent=2)+'\n');print(rp)
if __name__=='__main__':main()
