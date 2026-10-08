"""Restore the factory 5.13.7 CDM RT kthread worker pool in place of the CDM workqueue."""
from pathlib import Path
import hashlib,json,subprocess
BASE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro');SOURCE=BASE/'source/phoenix-kernel-recovery';ROOT=Path(__file__).resolve().parents[1]
PATCH=ROOT/'kernel-recovery/patches/pico-cdm-kthread-pool.patch'
D='techpack/camera/drivers/cam_cdm/'
PRE={D+'cam_cdm.h':'230ef53586039cea901e6a99c818ede53dc2212e1368196474b3f9fd7fca1d18',
     D+'cam_cdm_core_common.c':'435acae545601c68043cc0002f62988f0ec63e0f9fb709b8d30e216c68c2a144',
     D+'cam_cdm_core_common.h':'8d826277f5d57be807c4e18aa98b30f14c7fcc6898eca5258e7b770fd63a1d3a',
     D+'cam_cdm_hw_core.c':'09825380c63dd38ec8eab541bbe460c984653100262bc0002a08e3fff65dde81',
     D+'cam_cdm_virtual_core.c':'6a706d061870dc6988f29313842105974b684abb914311a24e04ae48865f356a'}
SCOPE=('cam_hw_cdm_create/destory_kthread_workqueue, cam_hw_cdm_queue_work and cam_hw_cdm_kthread_func reconstructed from the factory '
       'decompile: 5 SCHED_FIFO(49) kthread workers per CDM, 104-byte node, pool replaces work_queue at the same struct offset; HW and '
       'virtual CDM IRQ/submit work queued to an idle worker and dropped with an error when none is idle, as in factory. Fixes beyond '
       'factory: teardown no longer reads a node after kfree, failed creation destroys started workers, virtual submit frees an '
       'unqueued payload, virtual probe returns an error when the pool cannot be created.')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    rp=ROOT/'reports/kernel-source/recovery-20261004/cdm-kthread-pool-hooks.json'
    if rp.exists() and all(sha(SOURCE/n)==h for n,h in json.loads(rp.read_text())['sources'].items()):print('Already installed');return
    for n,h in PRE.items():
        if sha(SOURCE/n)!=h:raise RuntimeError('Unexpected preimage: '+n)
    subprocess.run(['patch','-p1','--dry-run','--no-backup-if-mismatch','-i',str(PATCH)],cwd=SOURCE,check=True,stdout=subprocess.DEVNULL)
    subprocess.run(['patch','-p1','--no-backup-if-mismatch','-i',str(PATCH)],cwd=SOURCE,check=True)
    rp.write_text(json.dumps({'patch':str(PATCH.relative_to(ROOT)),'patch_sha256':sha(PATCH),'preimages':PRE,
                              'sources':{n:sha(SOURCE/n) for n in PRE},'scope':SCOPE,'device_modified':False},indent=2)+'\n');print(rp)
if __name__=='__main__':main()
