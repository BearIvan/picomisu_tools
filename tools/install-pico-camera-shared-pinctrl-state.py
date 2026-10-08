"""Preserve shared pinctrl software state when the provider rejects a transition."""
from pathlib import Path
import hashlib
import json

BASE = Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro')
SOURCE = BASE / 'source/phoenix-kernel-recovery'
ROOT = Path(__file__).resolve().parents[1]
NAME = 'techpack/camera/drivers/cam_sensor_module/cam_res_mgr/cam_res_mgr.c'
PRE = '691e4bd2eefb618169de428cfe553f64e5ddf334aae114aed176ca01a6f95483'

def main():
    path = SOURCE / NAME
    report = ROOT / 'reports/kernel-source/recovery-20261004/shared-pinctrl-state-hooks.json'
    current = hashlib.sha256(path.read_bytes()).hexdigest()
    if report.exists() and json.loads(report.read_text())['sources'][NAME] == current:
        print('Already installed')
        return
    if current != PRE:
        raise RuntimeError('Unexpected shared resource manager preimage')
    source = path.read_text()
    for state in ('ACTIVE', 'SUSPEND'):
        old = '\t\tcam_res->pstatus = PINCTRL_STATUS_' + state + ';'
        if source.count(old) != 1:
            raise RuntimeError('Unexpected state assignment count: ' + state)
        source = source.replace(old, '\t\tif (!rc)\n\t' + old)
    path.write_text(source)
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps({'preimages':{NAME:PRE},'sources':{NAME:hashlib.sha256(path.read_bytes()).hexdigest()},'scope':'Only commit shared ACTIVE/SUSPEND software state after successful pinctrl_select_state. No public layout or ABI change. Shared put, counter ownership and common power-down retry remain unresolved.','device_modified':False},indent=2)+'\n')
    print(report)

if __name__ == '__main__':
    main()
