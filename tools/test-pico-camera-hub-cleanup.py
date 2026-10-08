"""Exercise actual cleanup bodies against failing, reentrant driver mocks."""
from pathlib import Path
import hashlib
import json
import subprocess
import importlib.util


def load(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SUPPORT = r'''
#define LIST_HEAD(n) struct list_head n={&(n),&(n)}
static void list_splice_init(struct list_head *src,struct list_head *dst) {
 if(list_empty(src))return;
 struct list_head *first=src->next,*last=src->prev,*next=dst->next;
 dst->next=first;first->prev=dst;last->next=next;next->prev=last;INIT_LIST_HEAD(src);
}
static int cam_req_mgr_unlink(struct cam_req_mgr_unlink_info *p);
static int cam_req_mgr_destroy_session(struct cam_req_mgr_session_info *p,bool shutdown);
static int cam_sync_destroy(int32_t key);
static int cam_mem_mgr_release(struct cam_mem_mgr_release_cmd *p);
'''

MAIN = r'''
static struct pico_hub_client *active;
static int calls,fail_at,kinds[16],keys[16];
static int driver(int kind,int key) {
 assert(!held && active->cleanup_active);kinds[calls]=kind;keys[calls++]=key;
 /* Reentrant event/registry use must not deadlock or detach the client. */
 pico_hub_registry_lock();assert(pico_hub_detach_client_locked(active)==-EBUSY);
 assert(pico_hub_add_event_handle_locked(active,false,999)==-EBUSY);
 if(active->parent->original->entity.function==0x10000) {
  struct cam_mem_mgr_alloc_cmd a={.out={.buf_handle=999}};
  assert(pico_hub_add_buffer_locked(active,&a)==-EBUSY);
  assert(pico_hub_remove_buffer_locked(active,999)==-EBUSY);
 }
 pico_hub_registry_unlock();
 assert(pico_hub_cleanup_client_resources(active)==-EBUSY);
 return calls==fail_at?-EIO:0;
}
static int cam_req_mgr_unlink(struct cam_req_mgr_unlink_info *p) {assert(p->session_hdl==777);return driver(1,p->link_hdl);}
static int cam_req_mgr_destroy_session(struct cam_req_mgr_session_info *p,bool shutdown) {assert(!shutdown && !p->reserved);return driver(2,p->session_hdl);}
static int cam_sync_destroy(int32_t key) {return driver(3,key);}
static int cam_mem_mgr_release(struct cam_mem_mgr_release_cmd *p) {assert(!p->reserved);return driver(4,p->buf_handle);}
static int count(struct list_head *h) {int n=0;for(struct list_head *p=h->next;p!=h;p=p->next)n++;return n;}
int main(void) {
 assert(pico_hub_cleanup_client_resources(NULL)==-ENOENT);
 for(int failure=0;failure<=4;failure++) {
  struct video_device v[2]={{0}};v[0].entity.function=0x10000;
  struct pico_hub_video parent={.original=&v[0],.shadow=&v[1],.multi_client=true};
  struct pico_hub_client c={.fh={.vdev=&v[1]}};INIT_LIST_HEAD(&c.fh.subscribed);
  pico_hub_registry_lock();assert(!pico_hub_add_video_locked(&parent));assert(!pico_hub_attach_client_locked(&parent,&c));
  struct cam_req_mgr_ver_info a={.version=1,.u.link_info_v1={.session_hdl=777,.link_hdl=101}};
  struct cam_req_mgr_ver_info b={.version=2,.u.link_info_v2={.session_hdl=777,.link_hdl=102}};
  struct cam_mem_mgr_alloc_cmd buf={.out={.buf_handle=888}};
  assert(!pico_hub_add_link_locked(&c,&a));assert(!pico_hub_add_link_locked(&c,&b));
  assert(!pico_hub_add_event_handle_locked(&c,false,777));assert(!pico_hub_add_buffer_locked(&c,&buf));
  assert(pico_hub_detach_client_locked(&c)==-EBUSY);pico_hub_registry_unlock();
  active=&c;calls=0;fail_at=failure;
  assert(pico_hub_cleanup_client_resources(&c)==(failure?-EIO:0));assert(!c.cleanup_active);
  int expected_kinds[]={1,1,2,4},expected_keys[]={102,101,777,888};
  assert(calls==(failure?failure:4));for(int i=0;i<calls;i++){assert(kinds[i]==expected_kinds[i]);assert(keys[i]==expected_keys[i]);}
  if(failure) {
   assert(count(&c.reserved_handles_56)==(failure<=2?3-failure:0));
   assert(count(&c.session_handles)==(failure<=3?1:0));assert(count(&c.reserved_handles_40)==1);
   calls=0;fail_at=0;assert(!pico_hub_cleanup_client_resources(&c));assert(calls==5-failure);
   for(int i=0;i<calls;i++){assert(kinds[i]==expected_kinds[i+failure-1]);assert(keys[i]==expected_keys[i+failure-1]);}
  }
  assert(!pico_hub_cleanup_client_resources(&c));
  pico_hub_registry_lock();assert(!pico_hub_detach_client_locked(&c));assert(!pico_hub_remove_video_locked(&parent));pico_hub_registry_unlock();
 }
 struct video_device v[2]={{0}};v[0].entity.function=0x10100;
 struct pico_hub_video parent={.original=&v[0],.shadow=&v[1],.multi_client=true};
 struct pico_hub_client c={.fh={.vdev=&v[1]}};INIT_LIST_HEAD(&c.fh.subscribed);
 pico_hub_registry_lock();assert(!pico_hub_add_video_locked(&parent));assert(!pico_hub_attach_client_locked(&parent,&c));
 assert(!pico_hub_add_event_handle_locked(&c,true,555));pico_hub_registry_unlock();active=&c;calls=0;fail_at=1;
 assert(pico_hub_cleanup_client_resources(&c)==-EIO);assert(count(&c.sync_handles)==1);fail_at=0;calls=0;
 assert(!pico_hub_cleanup_client_resources(&c));assert(calls==1 && kinds[0]==3 && keys[0]==555);
 pico_hub_registry_lock();assert(!pico_hub_detach_client_locked(&c));assert(!pico_hub_remove_video_locked(&parent));pico_hub_registry_unlock();
 assert(allocated==freed);puts("PASS: real cleanup order and payloads, failure at every step, preserved unprocessed records, exact retry, sync destroy, reentrant registry use and detach/operation guards; no record leaks");
}
'''


def main():
    ioctl_test = load('test-pico-camera-hub-ioctl')
    registry_test = load('test-pico-camera-hub-registry')
    event_test = load('test-pico-camera-hub-events')
    prefix = registry_test.HARNESS.split('/* SOURCE */')[0]
    prefix = prefix.replace('struct video_device {int marker;};', 'struct video_device {int marker;struct {unsigned function;} entity;};')
    prefix = prefix.replace('int event_lock;', 'int event_lock;bool multi_client;')
    prefix += event_test.EXTRA.split('/* BODIES */')[0]
    root = ioctl_test.BASE / 'source/phoenix-kernel-recovery' / ioctl_test.DIRECTORY
    names = ['pico_camera_hub_registry.c', 'pico_camera_hub_events.c', 'pico_camera_hub_resources.c', 'pico_camera_hub_cleanup.c', 'pico_camera_hub.h', 'pico_camera_hub_cleanup.h', 'pico_camera_hub_resources.h']
    registry, events, resources, cleanup = [(root / n).read_text() for n in names[:4]]
    bodies = registry[registry.index('static DEFINE_MUTEX'):] + events[events.index('static bool pico_hub_client_attached_locked'):] + resources[resources.index('static bool pico_hub_resource_client_locked'):] + cleanup[cleanup.index('static void pico_hub_cleanup_free'):]
    mocks = ioctl_test.MOCKS.split('/* IOCTL_HEADER */')[0]
    code = prefix + mocks + SUPPORT + bodies + MAIN
    out = ioctl_test.BASE / 'out/phoenix-kernel-recovery/camera-hub-cleanup-tests'
    out.mkdir(exist_ok=True)
    (out / 'harness.c').write_text(code)
    subprocess.run(['gcc', '-std=gnu11', '-g', '-O1', '-pthread', '-fsanitize=address,undefined', '-fno-omit-frame-pointer', str(out / 'harness.c'), '-o', str(out / 'test')], check=True)
    result = subprocess.run([str(out / 'test')], capture_output=True, text=True, timeout=30)
    report = {'sources': {ioctl_test.DIRECTORY + n: hashlib.sha256((root / n).read_bytes()).hexdigest() for n in names}, 'harness_sha256': hashlib.sha256(code.encode()).hexdigest(), 'exit_code': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr, 'sanitizers': ['AddressSanitizer', 'UndefinedBehaviorSanitizer'], 'scope': 'Actual cleanup/resource/event/registry functions with failing driver mocks; no physical driver execution', 'device_modified': False}
    (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    raise SystemExit(result.returncode)


if __name__ == '__main__':
    main()
