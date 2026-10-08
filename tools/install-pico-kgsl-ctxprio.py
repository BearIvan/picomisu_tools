"""Restore the factory 5.13.7 GPU context priority shift ioctl (IOCTL_KGSL_CTXPRIO_SHIFT) used by system_server VR boost."""
from pathlib import Path
import hashlib,json,subprocess
BASE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro');SOURCE=BASE/'source/phoenix-kernel-recovery';ROOT=Path(__file__).resolve().parents[1]
PATCH=ROOT/'kernel-recovery/patches/pico-kgsl-ctxprio-shift.patch'
PRE={
     'drivers/gpu/msm/adreno_dispatch.c':'d906efcf2101626fd9b16b24610e8ca8280cd1a2d8fb0cd7e9f5246b6121a34f',
     'drivers/gpu/msm/adreno_drawctxt.c':'cf1d371e324e8f18bd61b10e80f63b039cfb7e0b368e5a47c7eafe2d1eef711e',
     'drivers/gpu/msm/adreno_drawctxt.h':'625efedecbcef419682f9489a1caf0c6c06728315a6964d822213896eb44f2bb',
     'drivers/gpu/msm/kgsl.c':'9f1852f203b8b998e57adfd3e17e9a8ec281796202153bf06e1c667eed7079e6',
     'drivers/gpu/msm/kgsl.h':'6a543898ffafe088c9900d26deeb5fca3d52ca27436ebcd894076c0163962fde',
     'drivers/gpu/msm/kgsl_device.h':'9715172e7148415b9cd5c3b56ff505da71911d3b8bf010ead86a295c6e942ad5',
     'drivers/gpu/msm/kgsl_drawobj.c':'04a580a2dd457d8f335c3b9643fcb152ea2937222e003826beaf59a31db7b907',
     'drivers/gpu/msm/kgsl_drawobj.h':'df53440302abe5b4fcc80040c5238a5eb506665a7079164cee4668fa9c48f482',
     'drivers/gpu/msm/kgsl_ioctl.c':'412b986f971bf45968a737eb1c25a8fb164c1b952153b70a3699716bc94c9958',
     'drivers/gpu/msm/kgsl_sync.c':'3c2f1cf22f3cd622a8671c4a2269103ce046dfac8e80875ca1cff8390458bc25',
     'drivers/gpu/msm/kgsl_sync.h':'c6cab5797acc02b57f826d29d547c26cded7de7f75112bf6d179819c06052134',
     'include/uapi/linux/msm_kgsl.h':'ba1b4275361f4c7185d5bff8eb0b419b7ff978c1ce38a777ff80e67326b0c7c0',
}
SCOPE=('IOCTL_KGSL_CTXPRIO_SHIFT 0xc0080956 {pid, prio 4..15}: for each non-runtime context of the process kgsl_set_prio queues a barrier '
       'sync object at the head of the context queue (waits on a kgsl_barriers fence and on the last submitted timestamp), switches '
       'priority bits, base priority, ringbuffer and dispatcher plist order, then releases the barrier; dprio stored in '
       'kgsl_process_private (write-only in factory). A runtime context (priority 0) refuses the shift with -EPERM. Factory helpers made '
       'visible: set_context_priority, drawobj_add_sync_fence/timestamp; kgsl_ctx_barrier/kgsl_ctx_barrier_release in kgsl_sync.c.')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    rp=ROOT/'reports/kernel-source/recovery-20261008/kgsl-ctxprio-hooks.json'
    rp.parent.mkdir(parents=True,exist_ok=True)
    if rp.exists() and all(sha(SOURCE/n)==h for n,h in json.loads(rp.read_text())['sources'].items()):print('Already installed');return
    for n,h in PRE.items():
        if sha(SOURCE/n)!=h:raise RuntimeError('Unexpected preimage: '+n)
    subprocess.run(['patch','-p1','--dry-run','--no-backup-if-mismatch','-i',str(PATCH)],cwd=SOURCE,check=True,stdout=subprocess.DEVNULL)
    subprocess.run(['patch','-p1','--no-backup-if-mismatch','-i',str(PATCH)],cwd=SOURCE,check=True)
    rp.write_text(json.dumps({'patch':str(PATCH.relative_to(ROOT)),'patch_sha256':sha(PATCH),'preimages':PRE,
                              'sources':{n:sha(SOURCE/n) for n in PRE},'scope':SCOPE,'device_modified':False},indent=2)+'\n');print(rp)
if __name__=='__main__':main()
