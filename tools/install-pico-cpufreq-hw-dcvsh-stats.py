"""Restore the factory 5.13.7 cpufreq-hw DCVSH statistics nodes and cpuinfo_cur_freq_real."""
from pathlib import Path
import hashlib,json,subprocess
BASE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro');SOURCE=BASE/'source/phoenix-kernel-recovery';ROOT=Path(__file__).resolve().parents[1]
PATCH=ROOT/'kernel-recovery/patches/pico-cpufreq-hw-dcvsh-stats.patch'
PRE={
     'drivers/cpufreq/qcom-cpufreq-hw.c':'e54e0989adfb7e8fac9f52d6042dc693c88ad2c8c04efbf8cde232131342e3a5',
     'drivers/cpufreq/cpufreq.c':'ed988a90e15c2259fec788dcfd660729efbac3a34393639af4d45bf98e243fae',
     'include/linux/cpufreq.h':'39daac78d8947fd86d02f736bfd9d59edc7a537b6e414e740b020cd7ace44d3f',
}
SCOPE=('struct cpufreq_driver gains get_real after get (factory layout: bios_limit 120, exit 128, attr 168); cpufreq core '
       'exports cpuinfo_cur_freq_real (0444) when the driver has get_real. qcom-cpufreq-hw: qcom_cpufreq_hw_get_real = min(LUT '
       'frequency of the current perf index, dcvsh_freq_limit); cpuN/dcvsh_freq_limit_time counts 10 ms limit polls where the '
       'DCVSH limit is below the hardware frequency; cpuN/total_time prints CLOCK_BOOTTIME ms since the domain was initialised. '
       'struct cpufreq_qcom follows the factory layout (424 bytes). Deviation: show_cpuinfo_cur_freq_real checks get_real '
       'instead of get (factory copy of __cpufreq_get checked ->get).')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    rp=ROOT/'reports/kernel-source/recovery-20261008/cpufreq-hw-dcvsh-stats-hooks.json'
    rp.parent.mkdir(parents=True,exist_ok=True)
    if rp.exists() and all(sha(SOURCE/n)==h for n,h in json.loads(rp.read_text())['sources'].items()):print('Already installed');return
    for n,h in PRE.items():
        if sha(SOURCE/n)!=h:raise RuntimeError('Unexpected preimage: '+n)
    subprocess.run(['patch','-p1','--dry-run','--no-backup-if-mismatch','-i',str(PATCH)],cwd=SOURCE,check=True,stdout=subprocess.DEVNULL)
    subprocess.run(['patch','-p1','--no-backup-if-mismatch','-i',str(PATCH)],cwd=SOURCE,check=True)
    rp.write_text(json.dumps({'patch':str(PATCH.relative_to(ROOT)),'patch_sha256':sha(PATCH),'preimages':PRE,
                              'sources':{n:sha(SOURCE/n) for n in PRE},'scope':SCOPE,'device_modified':False},indent=2)+'\n');print(rp)
if __name__=='__main__':main()
