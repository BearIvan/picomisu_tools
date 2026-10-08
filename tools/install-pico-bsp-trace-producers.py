"""Restore the in-tree factory 5.13.7 kmemind/kioind producers (mm, psi, genhd, uid_sys_stats)."""
from pathlib import Path
import hashlib,json,subprocess
BASE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro');SOURCE=BASE/'source/phoenix-kernel-recovery';ROOT=Path(__file__).resolve().parents[1]
PATCH=ROOT/'kernel-recovery/patches/pico-bsp-trace-producers.patch'
PRE={
     'mm/vmscan.c':'0643ec984a6630ae88bb50a85785ba9318da28883711ef3541b2dec8c26c2272',
     'mm/compaction.c':'2d093099e447167065c9907ba5e425fec82a6e1f9aed238dc6bcfffed9d82271',
     'mm/page_alloc.c':'d4cf1b603dde56df9da40421ca0fd7db9fc7bbdd1094fc016d5a6c97c73e4b88',
     'mm/filemap.c':'ab8d270545574874fb0b4a299d02fc4aa3c8e2161e291714b8f1caee6280b63c',
     'kernel/sched/psi.c':'c584b65cca8db66b3a02e7c35517fd4cb3c5f34b68bdad6b6a3a2ede18131e71',
     'block/genhd.c':'fcf3b76882613454b4f8a78e158c2d09c95648502274cbafbcf0f67264473efe',
     'drivers/misc/uid_sys_stats.c':'15dc4f26b12fbae62716b3735930c67f07ff1241da222ee836b81a02e215b50b',
}
SCOPE=('kmemind latency (ilog2 ns slots, factory placement inside the psi_memstall sections): kswapd balance_pgdat '
       '(async_reclaim), kcompactd_do_work (async_compact), __perform_reclaim (direct_reclaim), __alloc_pages_direct_compact '
       '(direct_compact), wait_on_page_bit_common thrashing waits (PG_locked); allocation failures (count, order bitmap, gfp, '
       'comm) at the __alloc_pages_slowpath fail label; kmemind_psi() in psi.c (psi_show() update, skipped when psi is disabled: '
       'the factory locked an uninitialised mutex then). kioind: register_disk() records major/minor/devt/hd_struct of the '
       'watched names, kio_diskstats() in genhd.c, kio_uid_io() top 10 fg/bg read/write byte deltas in uid_sys_stats.c. Fixes '
       'over factory: del_gendisk() drops cached hd_struct pointers of a removed disk, kio_uid_io_init() no longer wipes '
       'hash_table (late initcall after uid entries existed) and hash_table_prev (already filled by trace_point_init), exact '
       'top-10 minimum tracking, unused uid slots cleared. Not restored (needs struct bio +8 bytes at offset 128, full rebuild): '
       'bio_endio/generic_make_request_checks Q2C latency (b_q2c stays 0).')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    rp=ROOT/'reports/kernel-source/recovery-20261008/bsp-trace-producers-hooks.json'
    rp.parent.mkdir(parents=True,exist_ok=True)
    if rp.exists() and all(sha(SOURCE/n)==h for n,h in json.loads(rp.read_text())['sources'].items()):print('Already installed');return
    for n,h in PRE.items():
        if sha(SOURCE/n)!=h:raise RuntimeError('Unexpected preimage: '+n)
    subprocess.run(['patch','-p1','--dry-run','--no-backup-if-mismatch','-i',str(PATCH)],cwd=SOURCE,check=True,stdout=subprocess.DEVNULL)
    subprocess.run(['patch','-p1','--no-backup-if-mismatch','-i',str(PATCH)],cwd=SOURCE,check=True)
    rp.write_text(json.dumps({'patch':str(PATCH.relative_to(ROOT)),'patch_sha256':sha(PATCH),'preimages':PRE,
                              'sources':{n:sha(SOURCE/n) for n in PRE},'scope':SCOPE,'device_modified':False},indent=2)+'\n');print(rp)
if __name__=='__main__':main()
