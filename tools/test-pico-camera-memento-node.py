"""Actual ledger, native stop helper and phased rollback adapter with driver mocks."""
from pathlib import Path
import hashlib
import importlib.util
import json
import subprocess
BASE = Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro')
SOURCE = BASE / 'source/phoenix-kernel-recovery'
D = 'techpack/camera/drivers/cam_core/'
NAMES = [D + n for n in ['pico_camera_memento.c', 'pico_camera_memento.h', 'pico_camera_memento_node.inc', 'pico_camera_memento_node.h', 'cam_node.c']]
MOCKS = r'''
typedef int s32;
#define CAM_CTX_UNINIT 0
#define CAM_CTX_STATE_MAX 5
#define CAM_CORE 0
#define CAM_ERR(...) ((void)0)
struct cam_node {char name[32];};
struct cam_context {struct cam_node *node;char dev_name[32];int state,session_hdl,dev_hdl;unsigned refs;};
struct cam_start_stop_dev_cmd {s32 session_handle,dev_handle;};
struct cam_release_dev_cmd {s32 session_handle,dev_handle;};
struct pico_memento_node {struct cam_node *node;u32 entity;struct cam_context *released_context;s32 pending_session,pending_device;};
static struct cam_context *lookup;static int stop_error,release_error,destroy_error;
static unsigned stops,releases,destroys,ref_puts;
static void *cam_get_device_priv(int h) {return lookup && lookup->dev_hdl==h?lookup:NULL;}
static int cam_context_handle_stop_dev(struct cam_context *ctx,struct cam_start_stop_dev_cmd *cmd) {assert(ctx==lookup && cmd->dev_handle==ctx->dev_hdl);stops++;return stop_error;}
static int cam_context_handle_release_dev(struct cam_context *ctx,struct cam_release_dev_cmd *cmd) {assert(ctx==lookup && ctx->refs==1);releases++;if(release_error)return release_error;ctx->state=CAM_CTX_UNINIT;ctx->dev_hdl=-1;ctx->session_hdl=-1;return 0;}
static int cam_destroy_device_hdl(int h) {assert(lookup && h==42 && lookup->refs==1 && lookup->state==CAM_CTX_UNINIT);destroys++;if(destroy_error)return destroy_error;lookup=NULL;return 0;}
static void cam_context_putref(struct cam_context *ctx) {assert(!lookup && ctx->refs==1 && ctx->dev_hdl==-1);ctx->refs--;ref_puts++;}
'''
MAIN = r'''
int main(void) {
 struct cam_node node;snprintf(node.name,sizeof(node.name),"cam-isp");struct cam_context ctx={.node=&node,.state=2,.session_hdl=41,.dev_hdl=42,.refs=1};snprintf(ctx.dev_name,sizeof(ctx.dev_name),"cam-isp");lookup=&ctx;
 struct pico_memento_node target;assert(pico_memento_node_init(NULL,&node,0x10003)==-EINVAL);assert(pico_memento_node_init(&target,&node,0x10001)==-EINVAL);assert(!pico_memento_node_init(&target,&node,0x10003));
 u32 packet[6]={41,42,1,0,0,0};assert(pico_memento_node_rollback(&target,0x10002,0x104,packet,8)==-EINVAL);assert(pico_memento_node_rollback(&target,0x10003,0x104,packet,24)==-EINVAL);assert(pico_memento_node_rollback(&target,0x10003,0x106,packet,8)==-EINVAL);
 struct pico_memento state;pico_memento_init(&state);struct pico_memento_record *ticket=NULL;
 assert(!pico_memento_prepare(0x10003,VIDIOC_CAM_CONTROL,0x102,&ticket));assert(!pico_memento_commit(&state,&ticket,0x10003,0x102,packet,24,0));assert(!pico_memento_prepare(0x10003,VIDIOC_CAM_CONTROL,0x103,&ticket));assert(!pico_memento_commit(&state,&ticket,0x10003,0x103,packet,8,0));
 stop_error=-EIO;assert(pico_memento_cleanup(&state,pico_memento_node_rollback,&target)==-EIO && stops==1 && !releases && !ref_puts && !list_empty(&state.starts));
 stop_error=0;release_error=-EAGAIN;assert(pico_memento_cleanup(&state,pico_memento_node_rollback,&target)==-EAGAIN && stops==2 && releases==1 && !destroys && !ref_puts && !target.released_context && list_empty(&state.starts) && !list_empty(&state.acquisitions));
 release_error=0;destroy_error=-EBUSY;assert(pico_memento_cleanup(&state,pico_memento_node_rollback,&target)==-EBUSY && releases==2 && destroys==1 && !ref_puts && target.released_context==&ctx && ctx.refs==1);
 assert(pico_memento_node_rollback(&target,0x10003,0x104,packet,8)==-EBUSY);packet[1]=43;assert(pico_memento_node_rollback(&target,0x10003,0x106,packet,24)==-EBUSY);packet[1]=42;
 destroy_error=0;assert(!pico_memento_cleanup(&state,pico_memento_node_rollback,&target) && releases==2 && destroys==2 && ref_puts==1 && !ctx.refs && !target.released_context && !live);
 assert(!pico_memento_cleanup(&state,pico_memento_node_rollback,&target) && destroys==2 && ref_puts==1);
 ctx.refs=1;ctx.dev_hdl=42;ctx.session_hdl=41;ctx.state=2;lookup=&ctx;packet[0]=999;assert(pico_memento_node_rollback(&target,0x10003,0x106,packet,24)==-EINVAL);packet[0]=41;ctx.state=0;assert(pico_memento_node_rollback(&target,0x10003,0x106,packet,24)==-EPROTO);ctx.state=2;struct cam_node alien;ctx.node=&alien;assert(pico_memento_node_rollback(&target,0x10003,0x106,packet,24)==-EINVAL);ctx.node=&node;
 puts("PASS: actual native node stop + ledger/adapter, entity/size/session/node guards, stop and release errors retained, release success followed by destroy failure preserves context reference/phase, retry skips repeated release, exact final handle/ref cleanup");
}
'''

def main():
    spec = importlib.util.spec_from_file_location('ledger', Path(__file__).with_name('test-pico-camera-memento.py'))
    ledger = importlib.util.module_from_spec(spec);spec.loader.exec_module(ledger)
    spec = importlib.util.spec_from_file_location('registry', Path(__file__).with_name('test-pico-camera-hub-registry.py'))
    common = importlib.util.module_from_spec(spec);spec.loader.exec_module(common)
    native = (SOURCE / (D + 'cam_node.c')).read_text()
    start = native.index('static int __cam_node_handle_stop_dev(')
    end = native.index('static int __cam_node_handle_config_dev(', start)
    body = (SOURCE / NAMES[0]).read_text()
    code = common.HARNESS.split('/* OWNED_SUBDEVICE_MOCKS */')[0] + ledger.MOCKS + MOCKS + body[body.index('struct pico_memento_record {'):] + native[start:end] + (SOURCE / NAMES[2]).read_text() + MAIN
    out = BASE / 'out/phoenix-kernel-recovery/camera-memento-node-tests';out.mkdir(exist_ok=True)
    (out / 'harness.c').write_text(code)
    subprocess.run(['gcc', '-std=gnu11', '-g', '-O1', '-pthread', '-fsanitize=address,undefined', '-fno-omit-frame-pointer', str(out / 'harness.c'), '-o', str(out / 'test')], check=True)
    result = subprocess.run([str(out / 'test')], capture_output=True, text=True, timeout=30)
    report = {'sources': {n: hashlib.sha256((SOURCE / n).read_bytes()).hexdigest() for n in NAMES}, 'harness_sha256': hashlib.sha256(code.encode()).hexdigest(), 'exit_code': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr, 'sanitizers': ['AddressSanitizer', 'UndefinedBehaviorSanitizer'], 'scope': 'Actual ledger/native node stop/new phased class1 adapter; hardware context release, handle table and context refs modeled; no live-driver or subdevice-file integration', 'device_modified': False}
    (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n');print(json.dumps(report, indent=2));raise SystemExit(result.returncode)

if __name__ == '__main__':
    main()
