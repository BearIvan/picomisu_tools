"""Restore the factory 5.13.7 PICO RTT minidump context-switch recorder (arm,pico_rtt) and its __switch_to / GIC hook registration."""
from pathlib import Path
import hashlib,json,subprocess
BASE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro');SOURCE=BASE/'source/phoenix-kernel-recovery';ROOT=Path(__file__).resolve().parents[1]
PATCH=ROOT/'kernel-recovery/patches/pico-rtt.patch'
PRE={
     'arch/arm64/kernel/process.c':'cd3cddd69216494569ac031b5fe012cc842e37e5602e94bdc9db234694caf1da',
     'drivers/irqchip/irq-gic-v3.c':'6b7730fa8cd03d79987fc93bccb8fe93188e2c81e98bde84c83dba20b39270b4',
     'kernel/trace/Makefile':'4f2e0a9eac7afb5c78b02f61789e9e730121e8c390709eccc9e2d0b9e04b4e66',
}
NEW=['kernel/trace/pico_rtt.c','include/linux/pico_rtt.h']
SCOPE=('pico_rtt platform driver (boot dtb node /soc/pico,rtt, compatible arm,pico_rtt): per possible CPU a 64 KiB dma_alloc_coherent ring of '
       '4096 {u64 sched_clock, u32 next pid | real_parent pid<<16} entries, registered in minidump as rtt_<cpu>; filled from a hook in __switch_to '
       '(thread_register_notifier, called after dsb(ish) before cpu_switch_to, as in the factory); panic notifier unhooks and flushes the rings. '
       'irq_register_notifier stores rtt_irq_switch_hook in the GIC driver but, as in the factory, nothing calls it. Deviations: '
       'hook pointers use READ_ONCE/WRITE_ONCE; allocation failure frees through dma_free_coherent; probe is not re-entered (suppress_bind_attrs).')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    rp=ROOT/'reports/kernel-source/recovery-20261008/rtt-hooks.json'
    rp.parent.mkdir(parents=True,exist_ok=True)
    names=list(PRE)+NEW
    if rp.exists() and all((SOURCE/n).exists() and sha(SOURCE/n)==h for n,h in json.loads(rp.read_text())['sources'].items()):print('Already installed');return
    for n,h in PRE.items():
        if sha(SOURCE/n)!=h:raise RuntimeError('Unexpected preimage: '+n)
    for n in NEW:
        if (SOURCE/n).exists():raise RuntimeError('Unexpected existing file: '+n)
    subprocess.run(['patch','-p1','--dry-run','--no-backup-if-mismatch','-i',str(PATCH)],cwd=SOURCE,check=True,stdout=subprocess.DEVNULL)
    subprocess.run(['patch','-p1','--no-backup-if-mismatch','-i',str(PATCH)],cwd=SOURCE,check=True)
    rp.write_text(json.dumps({'patch':str(PATCH.relative_to(ROOT)),'patch_sha256':sha(PATCH),'preimages':PRE,'new_files':NEW,
                              'sources':{n:sha(SOURCE/n) for n in names},'scope':SCOPE,'device_modified':False},indent=2)+'\n');print(rp)
if __name__=='__main__':main()
