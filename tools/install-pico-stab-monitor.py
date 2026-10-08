"""Restore the factory 5.13.7 stab_monitor (/dev/stabd) and the f2fs core_files_reserved_blocks reserve for critical files."""
from pathlib import Path
import hashlib,json,subprocess
BASE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro');SOURCE=BASE/'source/phoenix-kernel-recovery';ROOT=Path(__file__).resolve().parents[1]
PATCH=ROOT/'kernel-recovery/patches/pico-stab-monitor.patch'
PRE={
     'drivers/misc/Makefile':'5f12b2c2283762e0baf7bd2f0225c65e71fa290e32d4eab748198184c624097c',
     'fs/f2fs/f2fs.h':'aca6197e1b80839d81a480b68d287bcd642138656ae901f98f3acda4652c2bbd',
     'fs/f2fs/namei.c':'b3404aded15690875bc333c45aaa80ce87bc0e2cd2c13f7822e53b2afba51c74',
     'fs/f2fs/super.c':'6eb7d6c99317011148257654cb8f3fdbd841b649b29fbc68d6d5a7a3e54e978d',
     'fs/f2fs/sysfs.c':'c2a58173fe76260fb59fb55be10fa107b6b2654ee668681117e8dfb245ea743c',
}
NEW=['drivers/misc/stab_monitor.c','include/linux/stab_monitor.h']
SCOPE=('stab_monitor misc device /dev/stabd (factory module stab_monitor, param debug_stabd): 8-byte block-logo stage records (stage<16, max 50 queued) '
       'written by system services and consumed only by the process named stabd (blocking read, poll); ioctls 0x40cc6401 mark a file '
       '(filp_open + inode i_opflags IOP_PICO_CORE_FILE 0x20), 0x403c6402 register a core file name, 0x40046403 seal the list; '
       'is_core_file_name() exported. f2fs: sbi->core_files_reserved_blocks (sysfs core_files_reserved_blocks <= 0x40000, init writes 25600 '
       'for userdata) is kept free for files whose name ends in .db/xml/txt/bak/shm/wal and is registered (flag cached on the inode) in '
       'inc_valid_block_count, inc_valid_node_count and f2fs_create; statfs f_bavail and the reserved_blocks bound exclude it. '
       'Fixes over factory: NULL inode dereference in inc_valid_node_count (recovery path), dentry name read after dropping i_lock, '
       'is_core_file_name comparing with the list lock dropped, read copying kernel list pointers to userspace, a non-blocking writer '
       'not waking blocked readers, poll always reporting readable, copy faults returning 1, unbounded name list.')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    rp=ROOT/'reports/kernel-source/recovery-20261008/stab-monitor-hooks.json'
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
