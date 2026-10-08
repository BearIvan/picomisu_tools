"""Restore the factory 5.13.7 dwc3 IRQ bottom half on a dedicated SCHED_FIFO kthread worker (dwc3_bh_kwork)."""
from pathlib import Path
import hashlib,json,subprocess
BASE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro');SOURCE=BASE/'source/phoenix-kernel-recovery';ROOT=Path(__file__).resolve().parents[1]
PATCH=ROOT/'kernel-recovery/patches/pico-dwc3-bh-kthread.patch'
PRE={
     'drivers/usb/dwc3/core.h':'888db9c3689dde90d6200e9f7c800c5937849b3b984fa97d21ffbe5c366395bc',
     'drivers/usb/dwc3/core.c':'e758d0c07800b42d92c90a565438c5d0df5a7280db472471750239b1c1987960',
     'drivers/usb/dwc3/gadget.c':'140a0545ab0905f26d967fb2db5eea5266fab48cc79e4d35bf3af3d5a741b456',
     'drivers/usb/dwc3/gadget.h':'803dc6f5c6b9f479e4a2a10a73102ad39d3c12a95f947347ae49eaf934e87446',
}
SCOPE=('struct dwc3 gains the factory tail (kthread_worker @2440, task @2496, kthread_work @2504, 2544 bytes on arm64). '
       'dwc3_probe starts "dwc_<dev>" running kthread_worker_fn at SCHED_FIFO prio 1, dwc3_interrupt queues dwc3_bh_kwork on it '
       'instead of bh_work on dwc_wq, pullup/vbus_session/gadget_stop flush the worker. Fixes over factory: kthread creation '
       'failure fails the probe instead of leaving a worker without thread (every flush would hang), the worker is stopped on '
       'all probe error paths (including the clk -EPROBE_DEFER return that also leaked dwc_wq) and in dwc3_remove.')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    rp=ROOT/'reports/kernel-source/recovery-20261008/dwc3-bh-kthread-hooks.json'
    rp.parent.mkdir(parents=True,exist_ok=True)
    if rp.exists() and all(sha(SOURCE/n)==h for n,h in json.loads(rp.read_text())['sources'].items()):print('Already installed');return
    for n,h in PRE.items():
        if sha(SOURCE/n)!=h:raise RuntimeError('Unexpected preimage: '+n)
    subprocess.run(['patch','-p1','--dry-run','--no-backup-if-mismatch','-i',str(PATCH)],cwd=SOURCE,check=True,stdout=subprocess.DEVNULL)
    subprocess.run(['patch','-p1','--no-backup-if-mismatch','-i',str(PATCH)],cwd=SOURCE,check=True)
    rp.write_text(json.dumps({'patch':str(PATCH.relative_to(ROOT)),'patch_sha256':sha(PATCH),'preimages':PRE,
                              'sources':{n:sha(SOURCE/n) for n in PRE},'scope':SCOPE,'device_modified':False},indent=2)+'\n');print(rp)
if __name__=='__main__':main()
