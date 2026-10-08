"""Exercise real common-subscription counts and registry lifetime gates.

V4L2 subscribe/unsubscribe callbacks are not implemented by this test. It
checks the bookkeeping needed before those callbacks can be wired correctly.
"""
from pathlib import Path
import hashlib
import importlib.util
import json
import subprocess

BASE = Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro')
DIRECTORY = 'techpack/camera/drivers/cam_core/'

TEST = r'''
#include <limits.h>
typedef atomic_int atomic_t;
#define atomic_set(p,n) atomic_store(p,n)
#define atomic_read(p) atomic_load(p)
#define pico_hub_check_subscription_layouts() ((void)0)
struct v4l2_event_subscription {u32 type,id,flags,reserved[5];};
/* TYPES */
/* BODIES */
int main(void) {
 struct video_device v[4]={{0}};
 struct pico_hub_video one={.original=&v[0],.shadow=&v[1]};
 struct pico_hub_video two={.original=&v[2],.shadow=&v[3]};
 struct v4l2_event_subscription a={.type=0x8000000,.id=7,.flags=1,.reserved={4,3,2,1,0}};
 struct v4l2_event_subscription b=a;b.id=8;
 struct v4l2_event_subscription c=a;c.type++;
 pico_hub_registry_lock();
 assert(pico_hub_event_ref_locked(&one,&a,0)==-ENOENT);
 assert(!pico_hub_add_video_locked(&one));assert(!pico_hub_add_video_locked(&two));
 assert(pico_hub_event_ref_locked(&one,NULL,1)==-EINVAL);
 assert(pico_hub_event_ref_locked(&one,&a,2)==-EINVAL);
 assert(pico_hub_event_ref_locked(&one,&a,-2)==-EINVAL);
 assert(!pico_hub_event_ref_locked(&one,&a,0));
 assert(pico_hub_event_ref_locked(&one,&a,-1)==-ENOENT);assert(list_empty(&one.events));
 fail_alloc=1;assert(pico_hub_event_ref_locked(&one,&a,1)==-ENOMEM);fail_alloc=0;
 assert(list_empty(&one.events));
 assert(pico_hub_event_ref_locked(&one,&a,1)==1);
 struct pico_hub_subscription *entry=container_of(one.events.next,struct pico_hub_subscription,list);
 assert(!memcmp(&entry->subscription,&a,sizeof(a)));
 assert(pico_hub_event_ref_locked(&one,&a,1)==2);
 struct v4l2_event_subscription changed=a;changed.flags=0x1234;
 assert(pico_hub_event_ref_locked(&one,&changed,0)==2); /* key excludes flags */
 assert(!memcmp(&entry->subscription,&a,sizeof(a))); /* first full subscription retained */
 assert(pico_hub_event_ref_locked(&one,&b,1)==1);
 assert(pico_hub_event_ref_locked(&one,&c,1)==1);
 assert(pico_hub_event_ref_locked(&two,&a,1)==1);
 assert(pico_hub_event_ref_locked(&two,&a,0)==1);
 assert(pico_hub_event_ref_locked(&one,&a,0)==2);
 assert(pico_hub_remove_video_locked(&one)==-EBUSY);
 atomic_set(&entry->users,INT_MAX);assert(pico_hub_event_ref_locked(&one,&a,1)==-EOVERFLOW);
 assert(pico_hub_event_ref_locked(&one,&a,0)==INT_MAX);
 atomic_set(&entry->users,0);assert(pico_hub_event_ref_locked(&one,&a,-1)==-EINVAL);
 atomic_set(&entry->users,2);
 assert(pico_hub_event_ref_locked(&one,&a,-1)==1);
 assert(pico_hub_event_ref_locked(&one,&a,-1)==0);
 assert(pico_hub_event_ref_locked(&one,&a,-1)==-ENOENT);
 assert(pico_hub_event_ref_locked(&one,&b,-1)==0);
 assert(pico_hub_event_ref_locked(&one,&c,-1)==0);
 assert(list_empty(&one.events));assert(!pico_hub_remove_video_locked(&one));
 assert(pico_hub_event_ref_locked(&two,&a,-1)==0);assert(!pico_hub_remove_video_locked(&two));
 assert(allocated==freed);pico_hub_registry_unlock();
 puts("PASS: shared type/id counts, independent owners, full subscription retention, last-user free, missing decrement, overflow/corruption guards, ENOMEM and owner lifetime");
}
'''


def load(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    registry_test = load('test-pico-camera-hub-registry')
    event_test = load('test-pico-camera-hub-events')
    prefix = registry_test.HARNESS.split('/* SOURCE */')[0]
    prefix += event_test.EXTRA.split('/* BODIES */')[0]
    root = BASE / 'source/phoenix-kernel-recovery' / DIRECTORY
    registry = (root / 'pico_camera_hub_registry.c').read_text()
    source = (root / 'pico_camera_hub_subscriptions.c').read_text()
    header = (root / 'pico_camera_hub_subscriptions.h').read_text()
    types = header[header.index('struct pico_hub_subscription {'):header.index('/* Process context')]
    bodies = registry[registry.index('static DEFINE_MUTEX'):] + source[source.index('int pico_hub_event_ref_locked'):]
    code = prefix + TEST.replace('/* TYPES */', types).replace('/* BODIES */', bodies)
    out = BASE / 'out/phoenix-kernel-recovery/camera-hub-subscriptions-tests'
    out.mkdir(exist_ok=True)
    (out / 'harness.c').write_text(code)
    subprocess.run(['gcc', '-std=gnu11', '-g', '-O1', '-pthread', '-fsanitize=address,undefined',
                    '-fno-omit-frame-pointer', str(out / 'harness.c'), '-o', str(out / 'test')], check=True)
    result = subprocess.run([str(out / 'test')], capture_output=True, text=True, timeout=30)
    names = ['pico_camera_hub_subscriptions.c', 'pico_camera_hub_subscriptions.h', 'pico_camera_hub_registry.c', 'pico_camera_hub.h']
    report = {'sources': {DIRECTORY + name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in names},
              'harness_sha256': hashlib.sha256(code.encode()).hexdigest(),
              'scope': 'Actual common-count/registry functions with host lists/mutexes; no V4L2 subscription callbacks or real users',
              'exit_code': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr,
              'sanitizers': ['AddressSanitizer', 'UndefinedBehaviorSanitizer'], 'device_modified': False}
    (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    if result.returncode:
        raise SystemExit(result.returncode)


if __name__ == '__main__':
    main()
