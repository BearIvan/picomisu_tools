"""Restore the factory 5.13.7 RLIMIT_RTTIME watchdog (debuggerd signal instead of SIGKILL) and the ktop log dump it triggers."""
from pathlib import Path
import hashlib,json,subprocess
BASE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro');SOURCE=BASE/'source/phoenix-kernel-recovery';ROOT=Path(__file__).resolve().parents[1]
PATCH=ROOT/'kernel-recovery/patches/pico-ktop-rt-watchdog.patch'
PRE={'fs/proc/ktop.c':'e20370191ee51ca97c1ffb1974fdce4bf411a034b987b1b1bffee66780322b1f',
     'include/linux/ktop.h':'b5a695ee2ae57550f571d5aee88f23a5ca6c231fda0b283ea851575a779f6bc1',
     'kernel/time/posix-cpu-timers.c':'b6c7ed84935591b922bf51c0a5bee66455987aff1b180ef964e99d954df95758'}
SCOPE=('check_thread_timers RLIMIT_RTTIME, factory behaviour: past the hard limit the RT thread is not SIGKILLed; the kernel logs '
       '"CPU Watchdog Timeout (hard): comm[pid], tgid timeout prio", doubles rlim_max, sends signal 35 (bionic BIONIC_SIGNAL_DEBUGGER, '
       'si_code 129) and dumps the ktop top list to the kernel log through a worker (ktop_show_by_workqueue / ktop_show_work_func, '
       'ktop_show with a NULL seq_file prints with pr_info). Past the soft limit only a log line and soft += 100 ms (no SIGXCPU). '
       'The factory prio<0 && flag 0x10 SIGXCPU path is not restored (unknown flag, unreachable with normal priorities).')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    rp=ROOT/'reports/kernel-source/recovery-20261008/ktop-rt-watchdog-hooks.json'
    rp.parent.mkdir(parents=True,exist_ok=True)
    if rp.exists() and all(sha(SOURCE/n)==h for n,h in json.loads(rp.read_text())['sources'].items()):print('Already installed');return
    for n,h in PRE.items():
        if sha(SOURCE/n)!=h:raise RuntimeError('Unexpected preimage: '+n)
    subprocess.run(['patch','-p1','--dry-run','--no-backup-if-mismatch','-i',str(PATCH)],cwd=SOURCE,check=True,stdout=subprocess.DEVNULL)
    subprocess.run(['patch','-p1','--no-backup-if-mismatch','-i',str(PATCH)],cwd=SOURCE,check=True)
    rp.write_text(json.dumps({'patch':str(PATCH.relative_to(ROOT)),'patch_sha256':sha(PATCH),'preimages':PRE,
                              'sources':{n:sha(SOURCE/n) for n in PRE},'scope':SCOPE,'device_modified':False},indent=2)+'\n');print(rp)
if __name__=='__main__':main()
