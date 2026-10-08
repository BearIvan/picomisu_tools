"""Restore the factory 5.13.7 PICO BSP trace telemetry driver (/sys/tracepoint, /sys/kmemind, /sys/kioind)."""
from pathlib import Path
import hashlib,json,subprocess
BASE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro');SOURCE=BASE/'source/phoenix-kernel-recovery';ROOT=Path(__file__).resolve().parents[1]
PATCH=ROOT/'kernel-recovery/patches/pico-bsp-trace.patch'
PRE={
     'drivers/misc/Makefile':'e09c16ffb28e2221f0a569584858726e1a34611aba67178270375fcbf16fc037',
}
SCOPE=('New drivers/misc/pico_bsp_trace.c + include/linux/pico_bsp_trace.h (factory drivers/bytedance trace_point.c, kmemind.c, '
       'kioind.c): 12 exported *_trace_point_set() producers append {u64 realtime ns, u8 type, u8 subtype, 10 reserved, u32 len} '
       '+ payload to an 8 KiB overwrite ring buffer; rb_consumer moves records to a 4 KiB staging buffer and sysfs_notify()s '
       '/sys/tracepoint/trace (read drains it, every trace point node shows the same buffer, writing a node injects a record of '
       'its type); trace_on/kmemind_interval/kioind_interval/sched_interval/display_interval/kgsl_interval/rb_size/trigger knobs '
       '(factory defaults 1/2/12/2/10/2); ts_timer_getdata_thread samples every 5 s the 864 byte kmemind record (psi, '
       'reclaim/compaction/PG_locked latency histograms, allocation failures, 64 vmstat counters, 30 meminfo values), the 2024 '
       'byte kioind record (diskstats of sda/sde/sdf/sda7/sda16/zram0, bio latency buckets, top 10 uid io deltas), the sched '
       'metrics record (weak sched_metrics_info_upload(), NULL until restored) and the GPU TAP record (weak '
       'kgsl_online_tap_data/clear(), GPU agent provides the strong ones). Fixes over factory: unknown attribute no longer calls '
       'past the trace point table, reserved events are always committed and with the event pointer (factory passed the '
       'payload), uninitialised header bytes zeroed, producers before init ignored, notify age computed in 64 bit, thread '
       'start/stop/trigger serialised, init unwinds completely, kioind dev line prints devt instead of a kernel pointer, bio '
       'bucket [67,134) ms uses slot 26 (factory slot 27 shifted every later bucket). Dead factory helpers '
       'read_rb_to_user/should_read_ringbuffer/read_rb_stat_reset not restored.')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    rp=ROOT/'reports/kernel-source/recovery-20261008/bsp-trace-hooks.json'
    rp.parent.mkdir(parents=True,exist_ok=True)
    if rp.exists() and all(sha(SOURCE/n)==h for n,h in json.loads(rp.read_text())['sources'].items()):print('Already installed');return
    for n,h in PRE.items():
        if sha(SOURCE/n)!=h:raise RuntimeError('Unexpected preimage: '+n)
    subprocess.run(['patch','-p1','--dry-run','--no-backup-if-mismatch','-i',str(PATCH)],cwd=SOURCE,check=True,stdout=subprocess.DEVNULL)
    subprocess.run(['patch','-p1','--no-backup-if-mismatch','-i',str(PATCH)],cwd=SOURCE,check=True)
    rp.write_text(json.dumps({'patch':str(PATCH.relative_to(ROOT)),'patch_sha256':sha(PATCH),'preimages':PRE,
                              'sources':{n:sha(SOURCE/n) for n in PRE},'scope':SCOPE,'device_modified':False},indent=2)+'\n');print(rp)
if __name__=='__main__':main()
