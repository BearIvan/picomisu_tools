"""Restore the factory 5.13.7 temperature dependent backlight PWM of the DSI panel and the sde-crtc bl_pwm_timing/vsync_timing nodes."""
from pathlib import Path
import hashlib,json,subprocess
BASE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro');SOURCE=BASE/'source/phoenix-kernel-recovery';ROOT=Path(__file__).resolve().parents[1]
PATCH=ROOT/'kernel-recovery/patches/pico-display-temp-pwm.patch'
PRE={
     'drivers/gpu/drm/drm_mipi_dsi.c':'21f20aa640d146d0748cfae79f4b68ae44a55398f0e8cdbe23bfce77884310f4',
     'include/drm/drm_mipi_dsi.h':'52599ffdcdc274d50aa42568e5023542d9bd96cfe760c403364024d8e5d416e4',
     'techpack/display/msm/dsi/dsi_display.c':'20d32338180436a6afa06ea7a6c91cfb0d5f5455591e8c124456e2c58db6a2a2',
     'techpack/display/msm/dsi/dsi_display.h':'69ca81834092dc6d2127f82d05fef0ffdad915df8c370b27881ffe3c858d4d95',
     'techpack/display/msm/dsi/dsi_panel.c':'f416b08c669bb0621ecd6f98e4ab543aa37a0f2264bf2f2d045c4f4994659a22',
     'techpack/display/msm/dsi/dsi_panel.h':'852a51b0b3a067978dd9fdaf8d139b7e30f21832d55308f90bbd53d78d104b7e',
     'techpack/display/msm/sde/sde_crtc.c':'03dc39d5e28a07b1eda254664e00f78b77955c12a0a129ca7a4171e09547fb1d',
     'techpack/display/msm/sde/sde_crtc.h':'de0f141ad2dc324a400d6c58f874c5adec8e11254aa6284b3ba892794fa1089c',
     'techpack/display/msm/sde/sde_encoder.c':'c942e40ade38db7ae236d96da5188d6caf53df667d145de839809a9c23bbc7a5',
}
SCOPE=('qcom,temperature-dependent-pwm + qcom,response-temp-curve (bl_ctrl_gpio panels): a board thermistor read through the panel '
       'io-channels is offset to panel temperature, interpolated on the curve into a settling time and, after 240 s of display-on, '
       'turned into the backlight pulse position written by DCS (sharp ls026b3sa: B9 hi lo; innolux nt57900: FF 23, DA hi, DB lo) '
       'through the new mipi_dsi_dcs_write_group(); re-run every 100 jiffies and after every backlight update. dsi_backlight_config '
       'keeps the factory 248-byte layout. sde_encoder_vblank_callback mirrors the PWM window and vertical timing into sde_crtc for the '
       'read-only bl_pwm_timing and vsync_timing nodes of sde-crtc-N. Fixes over factory: the work is cancelled outside panel_lock '
       '(factory cancel_delayed_work_sync under panel_lock can deadlock with the work), a stop flag prevents rearming between pre_disable '
       'and disable, the work is queued instead of run in the backlight caller, iio channel and curve are released in dsi_panel_put, '
       'unsupported panels do not publish a window. BSP trace hooks (get_display_interval, dsi_panel_mtp_trace_point_update) not restored.')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    rp=ROOT/'reports/kernel-source/recovery-20261008/display-temp-pwm-hooks.json'
    rp.parent.mkdir(parents=True,exist_ok=True)
    if rp.exists() and all(sha(SOURCE/n)==h for n,h in json.loads(rp.read_text())['sources'].items()):print('Already installed');return
    for n,h in PRE.items():
        if sha(SOURCE/n)!=h:raise RuntimeError('Unexpected preimage: '+n)
    subprocess.run(['patch','-p1','--dry-run','--no-backup-if-mismatch','-i',str(PATCH)],cwd=SOURCE,check=True,stdout=subprocess.DEVNULL)
    subprocess.run(['patch','-p1','--no-backup-if-mismatch','-i',str(PATCH)],cwd=SOURCE,check=True)
    rp.write_text(json.dumps({'patch':str(PATCH.relative_to(ROOT)),'patch_sha256':sha(PATCH),'preimages':PRE,
                              'sources':{n:sha(SOURCE/n) for n in PRE},'scope':SCOPE,'device_modified':False},indent=2)+'\n');print(rp)
if __name__=='__main__':main()
