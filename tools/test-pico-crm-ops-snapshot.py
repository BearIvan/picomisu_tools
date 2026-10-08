"""Native snapshot/allocation and setup selection; legacy pointer UAF audit."""
from pathlib import Path
import hashlib,json,re,subprocess,importlib.util,os
def load(n):
    s=importlib.util.spec_from_file_location(n,Path(__file__).with_name(n+'.py'));m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
audit=load('test-pico-camera-handle-lifetime-audit');ex=load('test-pico-sensor-mono-hook');BASE=audit.BASE;SOURCE=audit.SOURCE;D=audit.D
NAMES=[D+n for n in ['cam_req_mgr_util.c','cam_req_mgr_util.h','cam_req_mgr_util_priv.h','cam_req_mgr_core.c','cam_req_mgr_core.h','cam_req_mgr_interface.h']]
MODEL=r'''
#include <string.h>
#include <stddef.h>
#define GFP_KERNEL 0
static int fail_alloc;
#define kcalloc(n,s,f) (fail_alloc?NULL:calloc(n,s))
#define kfree free
#define VERSION_1 1
#define VERSION_2 2
struct cam_req_mgr_device_info {int dev_hdl;};
struct cam_req_mgr_core_link;
struct cam_req_mgr_ver_info {int version;union {struct {int32_t dev_hdls[4];} link_info_v1;struct {int32_t dev_hdls[4];} link_info_v2;} u;};
static int calls;
static int get_info(struct cam_req_mgr_device_info *d){calls++;return 19;}
static int link_setup(struct cam_req_mgr_core_dev_link_setup *d){return 21;}
'''
MAIN=r'''
int main(int argc,char **argv){
 struct cam_req_mgr_util_hdl_tbl table={0};hdl_tbl=&table;int h=GET_DEV_HANDLE(11,HDL_TYPE_DEV,3);
 struct cam_req_mgr_kmd_ops *owner=calloc(1,sizeof(*owner));assert(owner);owner->get_dev_info=get_info;owner->link_setup=link_setup;
 table.hdl[3].hdl_value=h;table.hdl[3].state=HDL_ACTIVE;table.hdl[3].priv=owner;table.hdl[3].ops=owner;
 if(argc>1){struct cam_req_mgr_kmd_ops *legacy=cam_get_device_ops(h);assert(legacy==owner);assert(!cam_destroy_device_hdl(h));free(owner);return legacy->get_dev_info(NULL);} /* expected ASan UAF */
 struct cam_req_mgr_kmd_ops snapshot,zero={0};assert(pico_cam_get_device_ops_snapshot(h,NULL)==-EINVAL);
 hdl_tbl=NULL;memset(&snapshot,0xff,sizeof(snapshot));assert(pico_cam_get_device_ops_snapshot(h,&snapshot)==-ENODEV&&!memcmp(&snapshot,&zero,sizeof(zero)));hdl_tbl=&table;
 assert(pico_cam_get_device_ops_snapshot(h^(1<<16),&snapshot)==-ENODEV);
 assert(pico_cam_get_device_ops_snapshot(GET_DEV_HANDLE(11,HDL_TYPE_SESSION,3),&snapshot)==-ENODEV);
 table.hdl[3].state=HDL_FREE;assert(pico_cam_get_device_ops_snapshot(h,&snapshot)==-ENODEV);table.hdl[3].state=HDL_ACTIVE;
 table.hdl[3].priv=NULL;assert(pico_cam_get_device_ops_snapshot(h,&snapshot)==-ENODEV);table.hdl[3].priv=owner;
 table.hdl[3].ops=NULL;assert(pico_cam_get_device_ops_snapshot(h,&snapshot)==-ENODEV);table.hdl[3].ops=owner;
 struct cam_req_mgr_connected_device *devices=NULL;
 assert(__cam_req_mgr_create_subdevs(&devices,-1)==-EINVAL);
 assert(__cam_req_mgr_create_subdevs(&devices,CAM_REQ_MGR_MAX_HANDLES_V2+1)==-EINVAL);
 fail_alloc=1;assert(__cam_req_mgr_create_subdevs(&devices,2)==-ENOMEM);fail_alloc=0;
 assert(!__cam_req_mgr_create_subdevs(&devices,2));struct cam_req_mgr_core_link link={.l_dev=devices};struct cam_req_mgr_ver_info info={.version=VERSION_1};info.u.link_info_v1.dev_hdls[0]=info.u.link_info_v1.dev_hdls[1]=h;
 assert(!exercise_selection(&link,&info,2));assert(devices[0].ops!=owner&&devices[1].ops!=owner&&devices[0].ops!=devices[1].ops);
 assert((void *)devices[0].ops==(void *)(devices+2));assert((uintptr_t)devices[0].ops%_Alignof(struct cam_req_mgr_kmd_ops)==0);
 info.version=VERSION_2;assert(!exercise_selection(&link,&info,2));
 owner->link_setup=NULL;assert(exercise_selection(&link,&info,2)==-ENXIO);owner->link_setup=link_setup;assert(!exercise_selection(&link,&info,2));
 owner->get_dev_info=NULL; /* driver table mutation does not mutate saved bytes */
 assert(!cam_destroy_device_hdl(h));free(owner);assert(devices[0].ops->get_dev_info(NULL)==19&&devices[1].ops->get_dev_info(NULL)==19&&calls==2);
 assert(pico_cam_get_device_ops_snapshot(h,&snapshot)==-ENODEV&&!memcmp(&snapshot,&zero,sizeof(zero)));
 assert(exercise_selection(&link,&info,2)==-ENODEV&&!devices[0].ops);__cam_req_mgr_destroy_subdev(devices);
 assert(!__cam_req_mgr_create_subdevs(&devices,CAM_REQ_MGR_MAX_HANDLES_V2));__cam_req_mgr_destroy_subdev(devices);
 puts("PASS: native snapshot/allocation/setup selection V1/V2; table bytes remain usable after actual handle destroy and owner free, per-device owned tail, invalid/retired/missing ops reject, allocation bounds/failure, required callback guard");return 0;
}
'''
def main():
    util=(SOURCE/NAMES[0]).read_text();header=(SOURCE/NAMES[1]).read_text();priv=(SOURCE/NAMES[2]).read_text();core=(SOURCE/NAMES[3]).read_text();coreh=(SOURCE/NAMES[4]).read_text();interface=(SOURCE/NAMES[5]).read_text()
    types='\n'.join(re.search(r'(?:enum|struct) '+n+r' \{.*?\n\};',header,re.S).group(0) for n in ['hdl_state','hdl_type','handle','cam_req_mgr_util_hdl_tbl'])
    forward='\n'.join(l for l in interface.splitlines()[:27] if l.startswith('struct ') and l.endswith(';'))
    typedefs='\n'.join(re.search(r'typedef int \(\*'+n+r'\).*?;',interface,re.S).group(0) for n in ['cam_req_mgr_get_dev_info','cam_req_mgr_link_setup','cam_req_mgr_apply_req','cam_req_mgr_flush_req','cam_req_mgr_process_evt','cam_req_mgr_dump_req'])
    ops=re.search(r'struct cam_req_mgr_kmd_ops \{.*?\n\};',interface,re.S).group(0)
    connected=re.search(r'struct cam_req_mgr_connected_device \{.*?\n\};',coreh,re.S).group(0)
    macros=priv[priv.index('#define CAM_REQ_MGR_HDL_SIZE'):priv.rindex('#endif')]
    functions='\n'.join(ex.function(util,s) for s in ['void *cam_get_device_ops(','int pico_cam_get_device_ops_snapshot(','static int cam_destroy_hdl(','int cam_destroy_device_hdl('])
    alloc='\n'+ex.function(core,'static int __cam_req_mgr_create_subdevs(')+'\n'+ex.function(core,'static void __cam_req_mgr_destroy_subdev(')
    setup=ex.function(core,'static int __cam_req_mgr_setup_link_info(');start=setup.index('\t\t/* Cache link-owned table bytes');end=setup.index('\t\tdev->parent = (void *)link;',start)
    selection='\nstatic int exercise_selection(struct cam_req_mgr_core_link *link,struct cam_req_mgr_ver_info *link_info,int num_devices){int rc=0;struct cam_req_mgr_connected_device *dev;for(int i=0;i<num_devices;i++){dev=&link->l_dev[i];\n'+setup[start:end]+'}\nreturn 0;error:return rc;}\n'
    code=audit.MOCKS+forward+typedefs+ops+MODEL+macros+types+'\nstatic struct cam_req_mgr_util_hdl_tbl *hdl_tbl;\n'+connected+'\nstruct cam_req_mgr_core_link {struct cam_req_mgr_connected_device *l_dev;};\n'+functions+alloc+selection+MAIN
    out=BASE/'out/phoenix-kernel-recovery/crm-ops-snapshot-tests';out.mkdir(exist_ok=True);(out/'harness.c').write_text(code)
    subprocess.run(['gcc','-std=gnu11','-g','-O1','-pthread','-fsanitize=address,undefined','-fno-sanitize-recover=all',str(out/'harness.c'),'-o',str(out/'test')],check=True)
    env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0');runs={}
    for mode,args in [('snapshot',[]),('legacy',['legacy'])]:
        r=subprocess.run([str(out/'test')]+args,capture_output=True,text=True,timeout=30,env=env);runs[mode]={'exit_code':r.returncode,'stdout':r.stdout,'stderr':r.stderr};(out/(mode+'.stderr.log')).write_text(r.stderr)
    ok=runs['snapshot']['exit_code']==0 and 'heap-use-after-free' in runs['legacy']['stderr']
    report={'sources':{n:hashlib.sha256((SOURCE/n).read_bytes()).hexdigest() for n in NAMES},'harness_sha256':hashlib.sha256(code.encode()).hexdigest(),'exit_code':0 if ok else 1,'runs':runs,'scope':'Actual util snapshot/get/destroy, native create/destroy allocation and setup selection block, native ops/connected declarations; metadata/control flow outside selection, callbacks, allocator/spin/bitmap modeled. Legacy UAF expected; full link setup/unlink/workqueue/module-code lifetime and physical remove not covered','device_modified':False}
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'exit_code':report['exit_code'],'runs':{m:r['exit_code'] for m,r in runs.items()}}));raise SystemExit(report['exit_code'])
if __name__=='__main__':main()
