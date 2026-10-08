"""Apply factory 5.13.7 ISP buf-done handling: CAF last-consumed-address plus deferred buf-done acks."""
from pathlib import Path
import hashlib,json,subprocess
BASE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro');SOURCE=BASE/'source/phoenix-kernel-recovery';ROOT=Path(__file__).resolve().parents[1]
PATCH=ROOT/'kernel-recovery/patches/pico-isp-bufdone-consumed-addr.patch'
D='techpack/camera/drivers/'
PRE={D+'cam_core/cam_hw_mgr_intf.h':'e833e14cecb172390d8ab34d4787a3a0c55017b5118967747730b991f99f673c',
     D+'cam_isp/cam_isp_context.c':'1f12c25a9634618b4cfa7920659a13a76b0a82553870f54c89aafdb4b5173036',
     D+'cam_isp/cam_isp_context.h':'f2f14e64087b9a44349bfba2cdf7018c81f6e136da6a9e3d541e906431d75af2',
     D+'cam_isp/isp_hw_mgr/cam_ife_hw_mgr.c':'e699cf2a64f03adebd9e7e7651bd5bc1945c42be5df431af67067c9797092449',
     D+'cam_isp/isp_hw_mgr/cam_ife_hw_mgr.h':'7c9d0bc3ac912da8d4a44a0e522128374dc5ec7c5b4adcf58f41c934c21cada9',
     D+'cam_isp/isp_hw_mgr/include/cam_isp_hw_mgr_intf.h':'e0df6eb5cfa1b2f74f2cb5df72717e52c581e667a801e0fcecda0ca57cad31bf',
     D+'cam_isp/isp_hw_mgr/isp_hw/include/cam_isp_hw.h':'72b1d906d9049cbbcb9eab43481d65403d3cd9f56835f6a07cbd46c6917bdcf4',
     D+'cam_isp/isp_hw_mgr/isp_hw/vfe_hw/cam_vfe_core.c':'30069827c0ee947b8750d5da3d7cda752e8f3b9f372e6f55b449cc93bfc89155',
     D+'cam_isp/isp_hw_mgr/isp_hw/vfe_hw/vfe17x/cam_vfe480.h':'a4fa21bdca8994a69eacb0e9fd4107b5480e4898e93cbfd5eb71ca6a00bedda2',
     D+'cam_isp/isp_hw_mgr/isp_hw/vfe_hw/vfe_bus/cam_vfe_bus_ver3.c':'7df24914610ee12a32449191f3ba3ec2c857d7f006e003858629b75babb0ac0d',
     D+'cam_isp/isp_hw_mgr/isp_hw/vfe_hw/vfe_bus/cam_vfe_bus_ver3.h':'97db8965655bd261e3936d063d88ff4ab76b4d35f7266296fafe8379f822a636'}
SCOPE=('VFE bus ver3 reads WM addr_status_0 on buf done and IFE hw mgr reports it as last_consumed_addr (CAF LA.UM.8.12 camera-kernel, '
       'enabled for vfe480 as in factory). ISP context matches buffers by resource and consumed address, detects IRQ delay against the next '
       'active request, and defers buf dones for requests still in wait/pending lists until they complete or bubble (factory 5.13.7 '
       'decompile). RDI bubble SOF: deferred acks retire the request; public infinite loop over active requests replaced by the factory walk; '
       'RDI SOF substate handles late buf dones. Guards beyond factory: a fence is deferred at most once and dropped from the deferred list '
       'when signalled directly. th_reg_val kept instead of the CAF rename.')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    rp=ROOT/'reports/kernel-source/recovery-20261004/isp-bufdone-hooks.json'
    if rp.exists() and all(sha(SOURCE/n)==h for n,h in json.loads(rp.read_text())['sources'].items()):print('Already installed');return
    for n,h in PRE.items():
        if sha(SOURCE/n)!=h:raise RuntimeError('Unexpected preimage: '+n)
    subprocess.run(['patch','-p1','--dry-run','--no-backup-if-mismatch','-i',str(PATCH)],cwd=SOURCE,check=True,stdout=subprocess.DEVNULL)
    subprocess.run(['patch','-p1','--no-backup-if-mismatch','-i',str(PATCH)],cwd=SOURCE,check=True)
    rp.write_text(json.dumps({'patch':str(PATCH.relative_to(ROOT)),'patch_sha256':sha(PATCH),'preimages':PRE,
                              'sources':{n:sha(SOURCE/n) for n in PRE},'scope':SCOPE,'device_modified':False},indent=2)+'\n');print(rp)
if __name__=='__main__':main()
