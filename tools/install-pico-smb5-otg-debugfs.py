"""Restore the factory 5.13.7 qpnp-smbcharger OTG debugfs controls (otg_current_limit, otg_disable) and the 1100 mA psensor charge step."""
from pathlib import Path
import hashlib,json,subprocess
BASE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro');SOURCE=BASE/'source/phoenix-kernel-recovery';ROOT=Path(__file__).resolve().parents[1]
PATCH=ROOT/'kernel-recovery/patches/pico-smb5-otg-debugfs.patch'
PRE={
     'drivers/power/supply/qcom/qpnp-smb5.c':'a928e84a686bb996d707bed21d55d714f4f3c3f1b332abbd3b1699a48a8ac333',
}
SCOPE=('debugfs qpnp-smbcharger/otg_current_limit (0666, "0x%02llx"): reads chg->otg_cl_ua, accepts only 500000/1000000/1500000 '
       'uA and programs param.otg_cl through smblib_set_charge_param when the value changes; qpnp-smbcharger/otg_disable (0666): '
       'reads DCDC_CMD_OTG_REG OTG_EN_BIT, writing 0 clears OTG_EN_BIT, anything else is -EINVAL. disable_chg value 3 votes FCC '
       '1100 mA like the factory (public tree: 800 mA). Fix over factory: otg_cl_ua is restored when the PMIC write fails so the '
       'readback matches the hardware.')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    rp=ROOT/'reports/kernel-source/recovery-20261008/smb5-otg-debugfs-hooks.json'
    rp.parent.mkdir(parents=True,exist_ok=True)
    if rp.exists() and all(sha(SOURCE/n)==h for n,h in json.loads(rp.read_text())['sources'].items()):print('Already installed');return
    for n,h in PRE.items():
        if sha(SOURCE/n)!=h:raise RuntimeError('Unexpected preimage: '+n)
    subprocess.run(['patch','-p1','--dry-run','--no-backup-if-mismatch','-i',str(PATCH)],cwd=SOURCE,check=True,stdout=subprocess.DEVNULL)
    subprocess.run(['patch','-p1','--no-backup-if-mismatch','-i',str(PATCH)],cwd=SOURCE,check=True)
    rp.write_text(json.dumps({'patch':str(PATCH.relative_to(ROOT)),'patch_sha256':sha(PATCH),'preimages':PRE,
                              'sources':{n:sha(SOURCE/n) for n in PRE},'scope':SCOPE,'device_modified':False},indent=2)+'\n');print(rp)
if __name__=='__main__':main()
