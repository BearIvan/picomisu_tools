"""Test actual hub relay function bodies with a mock original subdevice.

Real kernel prefix sizes/offsets are checked in the arm64 build. This harness
checks forwarding, missing callbacks, native/compat choice and signed results.
"""
from pathlib import Path
import hashlib
import json
import subprocess

BASE = Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro')
RELATIVE = 'techpack/camera/drivers/cam_core/pico_camera_hub.c'

HARNESS = r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <errno.h>
struct v4l2_subdev;
struct v4l2_subdev_core_ops {
 long (*ioctl)(struct v4l2_subdev *,unsigned,void *);
 long (*compat_ioctl32)(struct v4l2_subdev *,unsigned,unsigned long);
};
struct v4l2_subdev_ops {const struct v4l2_subdev_core_ops *core;};
struct v4l2_subdev {const struct v4l2_subdev_ops *ops;void *dev_priv;};
struct pico_hub_subdevice {struct v4l2_subdev *original;};
#define v4l2_get_subdevdata(sd) ((sd)->dev_priv)
#define pico_hub_check_factory_layouts() ((void)0)
#define CONFIG_COMPAT 1
static int pico_hub_acquire_subdevice_relay(struct v4l2_subdev *sd,struct pico_hub_subdevice **e,void **c) {*e=0;*c=0;return 1;}
static void pico_hub_release_subdevice_relay(void *c) {assert(!c);}
static struct v4l2_subdev *expected_sd;
static unsigned expected_cmd,native_calls,compat_calls;
static void *expected_arg;
static long result;
static long native(struct v4l2_subdev *sd,unsigned cmd,void *arg) {
 assert(sd==expected_sd);assert(cmd==expected_cmd);assert(arg==expected_arg);
 native_calls++;return result;
}
static long compat(struct v4l2_subdev *sd,unsigned cmd,unsigned long arg) {
 compat_calls++;return -ENOSYS;
}
/* SOURCE */
int main(void) {
 struct v4l2_subdev original={0},shadow={0};
 struct pico_hub_subdevice entry={.original=&original};
 struct v4l2_subdev_core_ops core={.ioctl=native,.compat_ioctl32=compat};
 struct v4l2_subdev_ops ops={.core=&core};
 expected_sd=&original;expected_cmd=0xc01856c0U;int packet=42;expected_arg=&packet;
 assert(v4l2_subdevice_ioctl(0,expected_cmd,&packet)==-1);
 assert(v4l2_subdevice_ioctl(&shadow,expected_cmd,&packet)==-1);
 shadow.dev_priv=&entry;
 assert(v4l2_subdevice_ioctl(&shadow,expected_cmd,&packet)==-1);
 original.ops=&ops;ops.core=0;
 assert(v4l2_subdevice_ioctl(&shadow,expected_cmd,&packet)==-1);
 ops.core=&core;core.ioctl=0;
 assert(v4l2_subdevice_ioctl(&shadow,expected_cmd,&packet)==-1);
 core.ioctl=native;entry.original=0;
 assert(v4l2_subdevice_ioctl(&shadow,expected_cmd,&packet)==-1);
 entry.original=&original;assert(!native_calls && !compat_calls);
 const long results[]={0,-EINVAL,-EIO,17,0x100000005L,0xffffffff80000001L};
 for(unsigned i=0;i<sizeof(results)/sizeof(results[0]);i++) {
  result=results[i];
  assert(v4l2_subdevice_ioctl(&shadow,expected_cmd,&packet)==(int)result);
  assert(v4l2_subdevice_compat_ioctl(&shadow,expected_cmd,(unsigned long)&packet)==(int)result);
 }
 assert(native_calls==12 && !compat_calls && packet==42);
 expected_cmd=0xffffffffU;expected_arg=0;result=-515;
 assert(v4l2_subdevice_ioctl(&shadow,expected_cmd,0)==-515);
 expected_cmd=0;expected_arg=(void *)(uintptr_t)0x12345678U;
 assert(v4l2_subdevice_compat_ioctl(&shadow,0,0x12345678U)==-515);
 assert(!compat_calls && native_calls==14);
 puts("PASS: original subdevice/command/argument forwarding, null guards, native compat route, signed 32-bit results");
}
'''


def main():
    source = (BASE / 'source/phoenix-kernel-recovery' / RELATIVE).read_text()
    bodies = source[source.index('long v4l2_subdevice_ioctl('):source.index('static const struct v4l2_subdev_core_ops')]
    out = BASE / 'out/phoenix-kernel-recovery/camera-hub-relay-tests'
    out.mkdir(exist_ok=True)
    (out / 'harness.c').write_text(HARNESS.replace('/* SOURCE */', bodies))
    subprocess.run(['gcc', '-std=gnu11', '-g', '-O1', '-fsanitize=address,undefined',
                    '-fno-omit-frame-pointer', str(out / 'harness.c'), '-o', str(out / 'test')], check=True)
    result = subprocess.run([str(out / 'test')], capture_output=True, text=True, timeout=30)
    report = {'source_sha256': hashlib.sha256(source.encode()).hexdigest(),
              'scope': 'Actual relay bodies with mock original subdevice; no registered nodes or real V4L2 runtime',
              'exit_code': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr,
              'sanitizers': ['AddressSanitizer', 'UndefinedBehaviorSanitizer'], 'device_modified': False}
    (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    if result.returncode:
        raise SystemExit(result.returncode)


if __name__ == '__main__':
    main()
