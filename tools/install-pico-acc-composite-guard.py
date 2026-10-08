"""Restore the factory 5.13.7 acc_ctrlrequest_composite wLength guard on the android_setup accessory path."""
from pathlib import Path
import hashlib,json,subprocess
BASE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro');SOURCE=BASE/'source/phoenix-kernel-recovery';ROOT=Path(__file__).resolve().parents[1]
PATCH=ROOT/'kernel-recovery/patches/pico-acc-composite-guard.patch'
PRE={
     'drivers/usb/gadget/function/f_accessory.c':'63bae9876ab21a0289293830e12dcf33db79ed13d1adfff3b4ad7e99ec09b50d',
     'drivers/usb/gadget/configfs.c':'cf1b6ebec9528b93296cef24d1be03575b0ddb75458c5dd42edc53fdda0030db',
}
SCOPE=('acc_ctrlrequest_composite(): host control requests with wLength > USB_COMP_EP0_BUFSIZ (4096) are clamped for IN and '
       'refused (-EINVAL) for OUT before acc_ctrlrequest() sets up the ep0 data stage; android_setup (configfs.c) calls it like '
       'the factory. Fix over factory: acc_ctrlrequest_configfs (per-function setup path, same ep0 buffer) is routed through the '
       'same guard; the factory still called acc_ctrlrequest unguarded there.')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    rp=ROOT/'reports/kernel-source/recovery-20261008/acc-composite-guard-hooks.json'
    rp.parent.mkdir(parents=True,exist_ok=True)
    if rp.exists() and all(sha(SOURCE/n)==h for n,h in json.loads(rp.read_text())['sources'].items()):print('Already installed');return
    for n,h in PRE.items():
        if sha(SOURCE/n)!=h:raise RuntimeError('Unexpected preimage: '+n)
    subprocess.run(['patch','-p1','--dry-run','--no-backup-if-mismatch','-i',str(PATCH)],cwd=SOURCE,check=True,stdout=subprocess.DEVNULL)
    subprocess.run(['patch','-p1','--no-backup-if-mismatch','-i',str(PATCH)],cwd=SOURCE,check=True)
    rp.write_text(json.dumps({'patch':str(PATCH.relative_to(ROOT)),'patch_sha256':sha(PATCH),'preimages':PRE,
                              'sources':{n:sha(SOURCE/n) for n in PRE},'scope':SCOPE,'device_modified':False},indent=2)+'\n');print(rp)
if __name__=='__main__':main()
