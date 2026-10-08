"""Restore the factory 5.13.7 display BSP trace producers (dsi panel info, temp PWM window, tear/error)."""
from pathlib import Path
import hashlib,json,subprocess
BASE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro');SOURCE=BASE/'source/phoenix-kernel-recovery';ROOT=Path(__file__).resolve().parents[1]
PATCH=ROOT/'kernel-recovery/patches/pico-bsp-trace-display.patch'
PRE={
     'techpack/display/msm/dsi/dsi_panel.c':'f73a6bd11505d3d3f7086d55792039cbdc2bdc39a9625c8d543daf191e89821d',
     'techpack/display/msm/dsi/dsi_drm.c':'633a1838339a7843f3c9d87e1613d3fd3b1f0053bc1aa03bc7c3bd31ce1e3c96',
}
SCOPE=('dsi_panel.c: display_tear/error_trace_point_update() (exported, subtypes 1/3, send tear_data_point/lcd_error_point when '
       'their count is non zero; the sde producers that fill them are not restored), dsi_panel_info_trace_point_update() '
       '(subtype 0: panel type, h_active, v_active/back porch/sync width/front porch, fps) called from dsi_bridge_enable() when '
       'display_interval != 0, dsi_panel_mtp_trace_point_update() (subtype 2: board temp, panel offsets, PWM start/end/period, '
       'mid points, fps) every max(display_interval, 10) runs of the temp PWM work. Fix over factory: offsets are 0 instead of '
       'uninitialised stack for other panel types.')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    rp=ROOT/'reports/kernel-source/recovery-20261008/bsp-trace-display-hooks.json'
    rp.parent.mkdir(parents=True,exist_ok=True)
    if rp.exists() and all(sha(SOURCE/n)==h for n,h in json.loads(rp.read_text())['sources'].items()):print('Already installed');return
    for n,h in PRE.items():
        if sha(SOURCE/n)!=h:raise RuntimeError('Unexpected preimage: '+n)
    subprocess.run(['patch','-p1','--dry-run','--no-backup-if-mismatch','-i',str(PATCH)],cwd=SOURCE,check=True,stdout=subprocess.DEVNULL)
    subprocess.run(['patch','-p1','--no-backup-if-mismatch','-i',str(PATCH)],cwd=SOURCE,check=True)
    rp.write_text(json.dumps({'patch':str(PATCH.relative_to(ROOT)),'patch_sha256':sha(PATCH),'preimages':PRE,
                              'sources':{n:sha(SOURCE/n) for n in PRE},'scope':SCOPE,'device_modified':False},indent=2)+'\n');print(rp)
if __name__=='__main__':main()
