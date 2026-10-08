"""Restore the factory 5.13.7 sixdof_Fsin_boottime store (Remove_Fsin): lets the 6DoF stack keep camera acquire from claiming the FSIN interrupt."""
from pathlib import Path
import hashlib,json,subprocess
BASE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro');SOURCE=BASE/'source/phoenix-kernel-recovery';ROOT=Path(__file__).resolve().parents[1]
PATCH=ROOT/'kernel-recovery/patches/pico-sixdof-remove-fsin.patch'
PRE={'techpack/camera/drivers/cam_sensor_module/cam_sensor/cam_sensor_core.c':'a1a469348f6acc70ad9cab6980205c75b4616a1d944141c1230253af5ca2cace'}
SCOPE=('sixdof_Fsin_boottime (mode 0664) gets its factory store: sscanf %x into the u8 Remove_Fsin. While set, CAM_ACQUIRE_DEV skips '
       'cam_sensor_register_irq for the 6DoF sensors. Deviation: CAM_RELEASE_DEV keeps calling cam_sensor_unregister_irq unconditionally '
       '(ownership-guarded no-op) instead of the factory "if (!Remove_Fsin)", so toggling the flag between acquire and release can no '
       'longer leak or double-free the FSIN irq; invalid input returns -EINVAL instead of -1.')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    rp=ROOT/'reports/kernel-source/recovery-20261008/sixdof-remove-fsin-hooks.json'
    rp.parent.mkdir(parents=True,exist_ok=True)
    if rp.exists() and all(sha(SOURCE/n)==h for n,h in json.loads(rp.read_text())['sources'].items()):print('Already installed');return
    for n,h in PRE.items():
        if sha(SOURCE/n)!=h:raise RuntimeError('Unexpected preimage: '+n)
    subprocess.run(['patch','-p1','--dry-run','--no-backup-if-mismatch','-i',str(PATCH)],cwd=SOURCE,check=True,stdout=subprocess.DEVNULL)
    subprocess.run(['patch','-p1','--no-backup-if-mismatch','-i',str(PATCH)],cwd=SOURCE,check=True)
    rp.write_text(json.dumps({'patch':str(PATCH.relative_to(ROOT)),'patch_sha256':sha(PATCH),'preimages':PRE,
                              'sources':{n:sha(SOURCE/n) for n in PRE},'scope':SCOPE,'device_modified':False},indent=2)+'\n');print(rp)
if __name__=='__main__':main()
