"""Exercise the actual memento ledger; native rollback adapters remain separate."""
from pathlib import Path
import hashlib
import importlib.util
import json
import subprocess

BASE = Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro')
SOURCE = BASE / 'source/phoenix-kernel-recovery'
NAMES = ['techpack/camera/drivers/cam_core/pico_camera_memento.' + ext for ext in ['c', 'h']]

MOCKS = r'''
#include <string.h>
typedef unsigned char u8;
#define GFP_KERNEL 0
#define VIDIOC_CAM_CONTROL 0xc01856c0U
#define CAM_ACQUIRE_DEV 0x102
#define CAM_START_DEV 0x103
#define CAM_STOP_DEV 0x104
#define CAM_RELEASE_DEV 0x106
#define list_del list_del_init
#define list_first_entry(h,t,m) container_of((h)->next,t,m)
static unsigned live;static bool fail_alloc;
static void *kzalloc(size_t n,int flags) {if(fail_alloc)return NULL;void *p=calloc(1,n);assert(p);live++;return p;}
static void kfree(void *p) {assert(live);live--;free(p);}
struct pico_memento {struct list_head acquisitions,starts;};
typedef int (*pico_memento_rollback)(void *,u32,u32,const void *,size_t);
'''
MAIN = r'''
static unsigned count(struct list_head *h) {unsigned n=0;for(struct list_head *p=h->next;p!=h;p=p->next)n++;return n;}
static unsigned attempt,successes;static unsigned fail_at;static u32 entities[10],operations[10];static u8 packets[10][24];
static int rollback(void *opaque,u32 entity,u32 opcode,const void *payload,size_t bytes) {
 assert(opaque==(void *)123 && bytes==(opcode==CAM_RELEASE_DEV?24:8));attempt++;
 if(attempt==fail_at)return -EIO;
 assert(successes<10);entities[successes]=entity;operations[successes]=opcode;memcpy(packets[successes],payload,bytes);successes++;return 0;
}
static void remember(struct pico_memento *s,u32 entity,u32 op,const void *p,size_t n) {
 struct pico_memento_record *ticket=NULL;assert(!pico_memento_prepare(entity,VIDIOC_CAM_CONTROL,op,&ticket));assert(ticket);assert(!pico_memento_commit(s,&ticket,entity,op,p,n,0) && !ticket);
}
int main(void) {
 const int policy[16]={0,1,1,1,1,1,2,0,0,-EOPNOTSUPP,0,0,0,1,-EOPNOTSUPP,0};
 for(unsigned i=0;i<16;i++)assert(pico_memento_entity_class(0x10001+i)==policy[i]);
 assert(pico_memento_entity_class(0)==-EOPNOTSUPP && pico_memento_entity_class(0x10011)==-EOPNOTSUPP);
 struct pico_memento s;pico_memento_init(&s);struct pico_memento_record *ticket=NULL;
 assert(pico_memento_prepare(0x10003,0,0x102,&ticket)==-EINVAL && !ticket);
 assert(!pico_memento_prepare(0x10007,0,0x102,&ticket) && !ticket);
 assert(!pico_memento_commit(&s,&ticket,0x10007,0x102,NULL,0,0));
 assert(!pico_memento_prepare(0x10003,VIDIOC_CAM_CONTROL,0x105,&ticket) && !ticket);
 assert(!pico_memento_commit(&s,&ticket,0x10003,0x105,NULL,0,0));
 fail_alloc=true;assert(pico_memento_prepare(0x10003,VIDIOC_CAM_CONTROL,0x102,&ticket)==-ENOMEM && !ticket);fail_alloc=false;
 u32 acquire[6]={41,42,1,0,0x55667788,0x11223344};
 assert(!pico_memento_prepare(0x10003,VIDIOC_CAM_CONTROL,0x102,&ticket));assert(!pico_memento_commit(&s,&ticket,0x10003,0x102,NULL,0,-EIO) && !ticket && !live);
 assert(!pico_memento_prepare(0x10003,VIDIOC_CAM_CONTROL,0x102,&ticket));assert(pico_memento_commit(&s,&ticket,0x10003,0x103,acquire,8,0)==-EINVAL && ticket);
 assert(pico_memento_commit(&s,&ticket,0x10003,0x102,acquire,8,0)==-EINVAL && ticket && list_empty(&s.acquisitions));
 assert(!pico_memento_commit(&s,&ticket,0x10003,0x102,acquire,24,0) && !ticket && count(&s.acquisitions)==1);
 u32 wrong[2]={999,42};assert(pico_memento_commit(&s,&ticket,0x10003,0x106,wrong,8,0)==-ENOENT && count(&s.acquisitions)==1);
 assert(!pico_memento_commit(&s,&ticket,0x10003,0x106,acquire,8,-EIO) && count(&s.acquisitions)==1);
 assert(!pico_memento_commit(&s,&ticket,0x10003,0x106,acquire,8,0) && !live);
 remember(&s,0x10003,0x102,acquire,24);acquire[1]=43;remember(&s,0x10003,0x102,acquire,24);
 remember(&s,0x10003,0x103,acquire,8);remember(&s,0x10001,0x103,NULL,0);remember(&s,0x10008,0x103,acquire,8);
 assert(count(&s.starts)==3 && count(&s.acquisitions)==2);
 assert(!pico_memento_commit(&s,&ticket,0x10001,0x104,wrong,8,0) && count(&s.starts)==2);
 assert(pico_memento_commit(&s,&ticket,0x10008,0x104,NULL,0,0)==-EINVAL);
 fail_at=2;assert(pico_memento_cleanup(&s,rollback,(void *)123)==-EIO);assert(successes==1 && operations[0]==0x104 && entities[0]==0x10008 && !memcmp(packets[0],acquire,8));assert(count(&s.starts)==1 && count(&s.acquisitions)==2);
 fail_at=4;assert(pico_memento_cleanup(&s,rollback,(void *)123)==-EIO);assert(successes==2 && operations[1]==0x104 && list_empty(&s.starts) && count(&s.acquisitions)==2);
 fail_at=0;assert(!pico_memento_cleanup(&s,rollback,(void *)123));assert(successes==4 && operations[2]==0x106 && operations[3]==0x106 && ((u32 *)packets[2])[1]==43 && ((u32 *)packets[3])[1]==42);
 assert(!pico_memento_cleanup(&s,rollback,(void *)123) && successes==4 && !live);
 puts("PASS: exact 16-type factory policy, private command/opcode gates, preallocation/failure cancellation, validated kernel capture and ticket retention, acquire/start/remove keys and CSIPHY exception, stop-before-release cleanup and retry without repeating successful operations");
}
'''

def main():
    path = Path(__file__).with_name('test-pico-camera-hub-registry.py')
    spec = importlib.util.spec_from_file_location('registry', path)
    common = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(common)
    prefix = common.HARNESS.split('/* OWNED_SUBDEVICE_MOCKS */')[0]
    body = (SOURCE / NAMES[0]).read_text()
    code = prefix + MOCKS + body[body.index('struct pico_memento_record {'):] + MAIN
    out = BASE / 'out/phoenix-kernel-recovery/camera-memento-tests'
    out.mkdir(exist_ok=True)
    (out / 'harness.c').write_text(code)
    subprocess.run(['gcc', '-std=gnu11', '-g', '-O1', '-pthread', '-fsanitize=address,undefined', '-fno-omit-frame-pointer', str(out / 'harness.c'), '-o', str(out / 'test')], check=True)
    result = subprocess.run([str(out / 'test')], capture_output=True, text=True, timeout=30)
    report = {'sources': {n: hashlib.sha256((SOURCE / n).read_bytes()).hexdigest() for n in NAMES}, 'harness_sha256': hashlib.sha256(code.encode()).hexdigest(), 'exit_code': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr, 'sanitizers': ['AddressSanitizer', 'UndefinedBehaviorSanitizer'], 'scope': 'Actual memento ledger and cleanup bodies; modeled allocations/lists and rollback callback; kernel packet capture and native rollback/file adapters not connected; no hardware', 'device_modified': False}
    (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    raise SystemExit(result.returncode)

if __name__ == '__main__':
    main()
