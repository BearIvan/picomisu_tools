"""Native borrow/quiesce bodies with a modeled sleepable grace-period domain."""
from pathlib import Path
import hashlib,json,re,subprocess,importlib.util
def load(name):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name(name+'.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
audit=load('test-pico-camera-handle-lifetime-audit');BASE=audit.BASE;SOURCE=audit.SOURCE;NAMES=audit.NAMES[:3]
MODEL=r'''
struct srcu_struct {pthread_rwlock_t lock;};
#define DEFINE_SRCU(name) struct srcu_struct name={PTHREAD_RWLOCK_INITIALIZER}
static _Thread_local int reads;static pthread_mutex_t gate=PTHREAD_MUTEX_INITIALIZER;static pthread_cond_t changed=PTHREAD_COND_INITIALIZER;static bool waiting,drained;
static int srcu_read_lock(struct srcu_struct *s){assert(!pthread_rwlock_rdlock(&s->lock));reads++;return 0;}
static void srcu_read_unlock(struct srcu_struct *s,int cookie){assert(cookie==0&&reads>0);reads--;assert(!pthread_rwlock_unlock(&s->lock));}
static void synchronize_srcu(struct srcu_struct *s){pthread_mutex_lock(&gate);waiting=true;pthread_cond_broadcast(&changed);pthread_mutex_unlock(&gate);assert(!pthread_rwlock_wrlock(&s->lock));assert(!pthread_rwlock_unlock(&s->lock));pthread_mutex_lock(&gate);drained=true;pthread_cond_broadcast(&changed);pthread_mutex_unlock(&gate);}
'''
MAIN=r'''
static int *owner;
static void *retire(void *unused){pico_cam_device_priv_quiesce(owner);return NULL;}
int main(void){struct cam_req_mgr_util_hdl_tbl table={0};hdl_tbl=&table;int h=GET_DEV_HANDLE(11,HDL_TYPE_DEV,3);owner=malloc(sizeof(*owner));assert(owner);*owner=73;table.hdl[3].hdl_value=h;table.hdl[3].state=HDL_ACTIVE;table.hdl[3].priv=owner;
assert(!pico_cam_device_priv_get(h,NULL));int cookie=99;assert(!pico_cam_device_priv_get(h^(1<<16),&cookie)&&cookie==-1&&!reads);pico_cam_device_priv_put(cookie);
int *borrowed=pico_cam_device_priv_get(h,&cookie);assert(borrowed==owner&&cookie==0&&reads==1);pthread_t worker;assert(!pthread_create(&worker,NULL,retire,NULL));pthread_mutex_lock(&gate);while(!waiting)pthread_cond_wait(&changed,&gate);assert(!drained);pthread_mutex_unlock(&gate);
int absent_cookie;assert(!pico_cam_device_priv_get(h,&absent_cookie)&&absent_cookie==-1&&reads==1);assert(table.hdl[3].state==HDL_ACTIVE&&table.hdl[3].hdl_value==h);assert(*borrowed==73);pico_cam_device_priv_put(cookie);assert(!reads);assert(!pthread_join(worker,NULL)&&drained);assert(!cam_destroy_device_hdl(h));free(owner);pico_cam_device_priv_quiesce(NULL);
puts("PASS: native borrow/quiesce/get/destroy; read protection precedes lookup, failed lookup balanced, quiesce denies new priv lookup and waits for old reader, handle remains destroyable, owner freed only after drain");}
'''
def main():
    ex=load('test-pico-sensor-mono-hook');util=(SOURCE/NAMES[0]).read_text();header=(SOURCE/NAMES[1]).read_text();priv=(SOURCE/NAMES[2]).read_text()
    types='\n'.join(re.search(r'(?:enum|struct) '+n+r' \{.*?\n\};',header,re.S).group(0) for n in ['hdl_state','hdl_type','handle','cam_req_mgr_util_hdl_tbl'])
    macros=priv[priv.index('#define CAM_REQ_MGR_HDL_SIZE'):priv.rindex('#endif')]
    bodies='\n'.join(ex.function(util,s) for s in ['void *cam_get_device_priv(','static int cam_destroy_hdl(','int cam_destroy_device_hdl('])
    api=util[util.index('static DEFINE_SRCU(pico_camera_callback_srcu);'):]
    code=audit.MOCKS+macros+types+'\nstatic struct cam_req_mgr_util_hdl_tbl *hdl_tbl;\n'+MODEL+bodies+api+MAIN
    out=BASE/'out/phoenix-kernel-recovery/camera-callback-borrow-tests';out.mkdir(exist_ok=True);(out/'harness.c').write_text(code)
    subprocess.run(['gcc','-std=gnu11','-g','-O1','-pthread','-fsanitize=address,undefined','-fno-omit-frame-pointer',str(out/'harness.c'),'-o',str(out/'test')],check=True)
    r=subprocess.run([str(out/'test')],capture_output=True,text=True,timeout=10);report={'sources':{n:hashlib.sha256((SOURCE/n).read_bytes()).hexdigest() for n in NAMES},'harness_sha256':hashlib.sha256(code.encode()).hexdigest(),'exit_code':r.returncode,'stdout':r.stdout,'stderr':r.stderr,'scope':'Actual native borrow/quiesce/lookup/destroy, native handle types/macros; SRCU modeled by pthread rwlock, spinlock/bitmap modeled; real kernel SRCU scheduling and physical remove/V4L2 integration still pending','device_modified':False};(out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));raise SystemExit(r.returncode)
if __name__=='__main__':main()
