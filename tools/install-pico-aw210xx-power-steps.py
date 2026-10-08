"""Restore the factory 5.13.7 aw210xx LED power sequencing (aw210xx_power_up, aw210xx_power_down_2step_1/2) and hwen node."""
from pathlib import Path
import hashlib,json,subprocess
BASE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro');SOURCE=BASE/'source/phoenix-kernel-recovery';ROOT=Path(__file__).resolve().parents[1]
PATCH=ROOT/'kernel-recovery/patches/pico-aw210xx-power-steps.patch'
PRE={
     'drivers/i2c/aw210xx_driver/leds_aw210xx.c':'435dca36ebe031193ad77493ed00a1fcb1a864d2f4234b5b92da1fe77bdafc79',
     'drivers/i2c/aw210xx_driver/leds_aw210xx.h':'53de225209af739516de064cd4ddebac6f1fa93b90a26a755d9cd20c1a7eedfd',
}
SCOPE=('aw210xx_power_up drives enable-gpio ("gpio55") and enable-gpio-1V8 ("gpio58") high (+1 ms), power_down_2step_1 releases '
       'the 1V8 switch, power_down_2step_2 the chip enable; probe powers up around the class device registration and powers down '
       'again; hwen accepts a hex step (1 up, 2/3 down steps) and shows "gpio55=%d,gpio58=%d". Not instantiated by dtbo entry 0 '
       '(XR kona Standalone); only the MTP overlays 4/7/8/14 have awinic,aw210xx_led. Fixes over factory: no devm re-request per '
       'hwen write (devres growth, unconditional gpio_free of a possibly foreign request), requests tracked under a mutex, hwen '
       'parse errors return -EINVAL instead of -1, a failed class-device registration fails the probe (remove() would '
       'dereference cdev.dev).')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    rp=ROOT/'reports/kernel-source/recovery-20261008/aw210xx-power-steps-hooks.json'
    rp.parent.mkdir(parents=True,exist_ok=True)
    if rp.exists() and all(sha(SOURCE/n)==h for n,h in json.loads(rp.read_text())['sources'].items()):print('Already installed');return
    for n,h in PRE.items():
        if sha(SOURCE/n)!=h:raise RuntimeError('Unexpected preimage: '+n)
    subprocess.run(['patch','-p1','--dry-run','--no-backup-if-mismatch','-i',str(PATCH)],cwd=SOURCE,check=True,stdout=subprocess.DEVNULL)
    subprocess.run(['patch','-p1','--no-backup-if-mismatch','-i',str(PATCH)],cwd=SOURCE,check=True)
    rp.write_text(json.dumps({'patch':str(PATCH.relative_to(ROOT)),'patch_sha256':sha(PATCH),'preimages':PRE,
                              'sources':{n:sha(SOURCE/n) for n in PRE},'scope':SCOPE,'device_modified':False},indent=2)+'\n');print(rp)
if __name__=='__main__':main()
