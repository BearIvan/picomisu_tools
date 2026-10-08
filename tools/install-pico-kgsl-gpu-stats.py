"""Restore the factory 5.13.7 kgsl GPU statistics: /sys/class/kgsl/kgsl/composite, /proc/gpu_procs (total_stats, compositor, <pid>/status), the compositor frame flow (get_frame_flow), preemption-aware render times and the online TAP (gputap, kgsl_online_tap_data/clear)."""
from pathlib import Path
import hashlib,json,subprocess
BASE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro');SOURCE=BASE/'source/phoenix-kernel-recovery';ROOT=Path(__file__).resolve().parents[1]
PATCH=ROOT/'kernel-recovery/patches/pico-kgsl-gpu-stats.patch'
PRE={
     'drivers/gpu/msm/Makefile':'a27bdd8f7f8d1ac620ecc9738c968cd04743501347d8d5636e7bfcf5fdf54f99',
     'drivers/gpu/msm/adreno.c':'0b0dda5683ce528ecd5c1af9fc0226ccb9bd15bd28206875a6e0541fe991e81d',
     'drivers/gpu/msm/adreno_a6xx.c':'dea9b861959ff31d36bfa721b52fe3a1290a970ffd70d640b69e37647ca533b9',
     'drivers/gpu/msm/adreno_a6xx_preempt.c':'99d1986925fa03aa425321330fc44fc716efe472d7d9f8c80574b16d6fe9423c',
     'drivers/gpu/msm/adreno_dispatch.c':'af0c192d1ea4fdb9fa9278fd5a7ea382c46ef5fba1ecc6706222cad874bac3e9',
     'drivers/gpu/msm/adreno_dispatch.h':'27668eaa19c59e056dcccbe714e25df1b0a5d88d194fa1158f4e0708e41cfa36',
     'drivers/gpu/msm/adreno_drawctxt.c':'3cd9a393e404c0fd6b50e920e6f0220df23e3fe1880c4c3a87255f394f5256b5',
     'drivers/gpu/msm/adreno_drawctxt.h':'a915745e77ac938b2a7f601cc5d3a4636f6cda3dd55ad73f1fdfa960b0392440',
     'drivers/gpu/msm/adreno_ringbuffer.c':'2d241aa0c1fa649f11e0c673e60f8be42dd47bfb6f75cbedd6f65d29ab732be7',
     'drivers/gpu/msm/kgsl.c':'1c8fcadd84fe9b19273b6ea077b50daca7a6fa83d710e09a25f35407948d724d',
     'drivers/gpu/msm/kgsl_debugfs.c':'5616d475821cbe20aab8cbf112f813366c175042255ad6e8350f78c4a0424202',
     'drivers/gpu/msm/kgsl_debugfs.h':'c8debf8c22f98230f9acc5ed3e0766f9aa662ab6da912c928d57f3f717ca818d',
     'drivers/gpu/msm/kgsl_device.h':'0c7b634cc22107515750db674093fa6d2b17cee126447ace29d6c148469e2013',
     'drivers/gpu/msm/kgsl_drawobj.c':'3977f753c7919c466d8d2a15c31ab674ba6fca572aacd607b02bc7bae2a9c41d',
     'drivers/gpu/msm/kgsl_drawobj.h':'8607ecac48d096993c0099ea79e3d09882fb842f6dc656ea5d5ef190a8209938',
     'drivers/gpu/msm/kgsl_iommu.c':'43f731e1d61eec5fb3e53dee094deaf60a848c046087fe9b4b1b14686abb3f26',
     'drivers/gpu/msm/kgsl_mmu.c':'4d4c41368076858b53441fc506909eef191d3fe20f85cad0160893764506ddca',
     'drivers/gpu/msm/kgsl_pwrctrl.c':'4700cc74534e243ed4eeff26603d0949ceae60ff4fd735cd61e2f7e8e6dd827d',
     'drivers/gpu/msm/kgsl_pwrctrl.h':'a360e439777ca90797c2b1f05cbd30124236a77aa0d0d3403cae511e4efc2ea1',
     'drivers/gpu/msm/kgsl_pwrscale.c':'c7f213e9ef6ebefa8d6bf4d94fb809b344c2d2bf841e7e4e923a2b5854e2bc9a',
     'drivers/gpu/msm/kgsl_sharedmem.c':'6cee25fc8fff591b472a5b2f3befc8c8308e12ebc1754358b74ed9c6a1e8c01e',
     'drivers/gpu/msm/kgsl_tap.c':None,
     'drivers/gpu/msm/kgsl_tap.h':None,
     'include/linux/kgsl_pico.h':None,
}
SCOPE=('kgsl/adreno: write-only /sys/class/kgsl/kgsl/composite ("pid,pid", init smt.composite.attach) remembers the compositor pids '
       'and flags their process privates (bit0 of the new pico_flags, also set by kgsl_open for a restarted compositor); '
       '/proc/gpu_procs created at device probe with total_stats (busy_percent/load_percent from 10 ms devfreq windows, frequency weighted '
       'load, cur_freq, max_freq = freq_table[0], zeroed after a read while the GPU bus is off), compositor (binary 328 bytes: latest '
       'compositor timestamp + 8x5 u64 frame flow) and <pid>/status (us_on_gpu, gmem_used, per-context last render time raw and without '
       'preemption); compositor frame flow cache in adreno_drawctxt.c (update_frame_flow_cache from retire for runtime priority contexts, '
       'get_frame_flow(u64 *out, int n) global for sde_crtc: n must be 8, trylock, oldest first; SUBMIT_RETIRE_TICKS_SIZE 8); '
       'audit_preemption_ticks after every a6xx ringbuffer switch accounts the time the running command was preempted (new spinlock in '
       'the dispatcher drawqueue, references released through kgsl_drawobj_destroy_object_defer); online TAP (kgsl_tap.c: gputap sysfs '
       'node, kgsl_tap_get_device/kgsl_tap_result_show/kgsl_online_tap_init from a6xx_init, kgsl_online_tap_data/clear for the BSP trace '
       'driver, 7 latency histograms and 6 exception counters hooked into gpu_command, sendcmd, gpumem alloc/free, mmap, '
       'get_unmapped_area, page fault, mmu map/unmap, smmu fault, devfreq DDR pressure, a6xx reset/err/cp error, hang irq, preemption '
       'timeout); kgsl_get_dma_buf exported; is_runtime_context global. Fixes over factory: a context whose preemption init fails is '
       'never unlinked uninitialised, the audit cannot walk stale queue slots, queue entries are unpublished under the lock before they '
       'are freed, flow cache update is irq-safe, no divisions by zero, composite parsing works on a copy of the sysfs buffer, procfs '
       'nodes do not depend on debugfs. Not restored: GPU swap (kgsl_swap_*), freezer hooks, BSP trace point exports.')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    rp=ROOT/'reports/kernel-source/recovery-20261008/kgsl-gpu-stats-hooks.json'
    rp.parent.mkdir(parents=True,exist_ok=True)
    if rp.exists() and all((SOURCE/n).exists() and sha(SOURCE/n)==h for n,h in json.loads(rp.read_text())['sources'].items()):print('Already installed');return
    for n,h in PRE.items():
        if h is None:
            if (SOURCE/n).exists():raise RuntimeError('Unexpected existing file: '+n)
        elif sha(SOURCE/n)!=h:raise RuntimeError('Unexpected preimage: '+n)
    subprocess.run(['patch','-p1','--dry-run','--no-backup-if-mismatch','-i',str(PATCH)],cwd=SOURCE,check=True,stdout=subprocess.DEVNULL)
    subprocess.run(['patch','-p1','--no-backup-if-mismatch','-i',str(PATCH)],cwd=SOURCE,check=True)
    rp.write_text(json.dumps({'patch':str(PATCH.relative_to(ROOT)),'patch_sha256':sha(PATCH),'preimages':PRE,
                              'sources':{n:sha(SOURCE/n) for n in PRE},'scope':SCOPE,'device_modified':False},indent=2)+'\n');print(rp)
if __name__=='__main__':main()
