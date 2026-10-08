"""Restore factory 5.13.7 binder extensions: remote pid / calling tid ioctls and the system_server async-space guard."""
from pathlib import Path
import hashlib,json,subprocess
BASE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro');SOURCE=BASE/'source/phoenix-kernel-recovery';ROOT=Path(__file__).resolve().parents[1]
PATCH=ROOT/'kernel-recovery/patches/pico-binder-remote-pids-async-guard.patch'
NAME='drivers/android/binder.c'
PRE={NAME:'5ae6428e5d4fa96cf39459379e181824ecd98336dc778e99db67855349e9f9ce'}
SCOPE=('ioctls used by the Source libbinder: b,14/b,15 (48-byte binder_remote_pids: callee/caller pids of the target in-flight transactions, '
       'factory binder_stat_get_remote_pids), b,30 (existing get_target_proc_tid wired up), b,31 (calling tid of the top transaction, -EINVAL '
       'without one). binder_handle_buffer_alloc: with system_server free async space <= 0xC800, a oneway code with >=26 of the first 29 '
       'queued async transactions on a node is refused with BR_FAILED_REPLY/-ENOSPC until space recovers. Differences: factory sent signal '
       '58 to every 100th refused sender for a backtrace; Source has no handler (default action kills), so only a log is kept. Locks added '
       'around the calling-tid read; remote pid collection without allocations.')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    rp=ROOT/'reports/kernel-source/recovery-20261004/binder-extensions-hooks.json'
    if rp.exists() and all(sha(SOURCE/n)==h for n,h in json.loads(rp.read_text())['sources'].items()):print('Already installed');return
    for n,h in PRE.items():
        if sha(SOURCE/n)!=h:raise RuntimeError('Unexpected preimage: '+n)
    subprocess.run(['patch','-p1','--dry-run','--no-backup-if-mismatch','-i',str(PATCH)],cwd=SOURCE,check=True,stdout=subprocess.DEVNULL)
    subprocess.run(['patch','-p1','--no-backup-if-mismatch','-i',str(PATCH)],cwd=SOURCE,check=True)
    rp.write_text(json.dumps({'patch':str(PATCH.relative_to(ROOT)),'patch_sha256':sha(PATCH),'preimages':PRE,
                              'sources':{n:sha(SOURCE/n) for n in PRE},'scope':SCOPE,'device_modified':False},indent=2)+'\n');print(rp)
if __name__=='__main__':main()
