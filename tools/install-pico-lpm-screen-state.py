"""Restore the factory 5.13.7 screen-state LPM restriction (qcom,lpm-disallowed-cpumask + panel blank notifier)."""
from pathlib import Path
import hashlib,json,subprocess
BASE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro');SOURCE=BASE/'source/phoenix-kernel-recovery';ROOT=Path(__file__).resolve().parents[1]
PATCH=ROOT/'kernel-recovery/patches/pico-lpm-screen-state.patch'
PRE={'drivers/cpuidle/lpm-levels.c':'7ed71bef5f25e3aecac9c3824fcb5a9a34bd54d6b0dc9f0c1b9902ec0c1234ab',
     'drivers/cpuidle/lpm-levels.h':'132539c90e4fa4bcb8d576b057a2271da9814f78c69a1ad6567ee69cec8e92df',
     'drivers/cpuidle/lpm-levels-of.c':'4e9e79da78b2072d5ef92eb8af8317f3b0f0cd190bae4045f2942a5be5b074d8'}
SCOPE=('lpm-levels: "qcom,lpm-disallowed-cpumask" (boot dtb: "ff") is ANDed into each lpm_cpu (factory field at offset 24 after '
       'related_cpus); while module param lpm_levels.screen_on_now (default 1, 0664) is set, those CPUs get no low power mode (lpm_disallowed '
       'returns true -> WFI). The first already-registered panel among the dtbo "panel" phandles gets a drm panel notifier '
       '(screen_state_chg_callback: BLANK_UNBLANK -> on, BLANK_POWERDOWN -> off). As in the factory there is no probe deferral: if no panel '
       'is registered when lpm probes, screen_on_now stays 1 and all CPUs stay out of LPM. Runtime value must be checked on hardware.')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    rp=ROOT/'reports/kernel-source/recovery-20261008/lpm-screen-state-hooks.json'
    rp.parent.mkdir(parents=True,exist_ok=True)
    if rp.exists() and all(sha(SOURCE/n)==h for n,h in json.loads(rp.read_text())['sources'].items()):print('Already installed');return
    for n,h in PRE.items():
        if sha(SOURCE/n)!=h:raise RuntimeError('Unexpected preimage: '+n)
    subprocess.run(['patch','-p1','--dry-run','--no-backup-if-mismatch','-i',str(PATCH)],cwd=SOURCE,check=True,stdout=subprocess.DEVNULL)
    subprocess.run(['patch','-p1','--no-backup-if-mismatch','-i',str(PATCH)],cwd=SOURCE,check=True)
    rp.write_text(json.dumps({'patch':str(PATCH.relative_to(ROOT)),'patch_sha256':sha(PATCH),'preimages':PRE,
                              'sources':{n:sha(SOURCE/n) for n in PRE},'scope':SCOPE,'device_modified':False},indent=2)+'\n');print(rp)
if __name__=='__main__':main()
