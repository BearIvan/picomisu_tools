"""Actual bounded copy and native slot retirement with concurrent threads."""
from pathlib import Path
import hashlib,json,subprocess,importlib.util
BASE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro');SOURCE=BASE/'source/phoenix-kernel-recovery';D='techpack/camera/drivers/cam_req_mgr/'
NAMES=[D+n for n in ['pico_mem_copy.inc','pico_mem_copy.h','cam_mem_mgr.c','cam_mem_mgr.h']]+['techpack/camera/include/uapi/media/cam_req_mgr.h']
NAMES += ['techpack/camera/include/uapi/media/cam_defs.h']
HARNESS=r'''
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <cam_req_mgr.h>
#include <cam_defs.h>
typedef int32_t s32;
struct mutex {pthread_mutex_t value;};static _Thread_local unsigned held;
static void mutex_lock(struct mutex *m){assert(!pthread_mutex_lock(&m->value));held++;}
static void mutex_unlock(struct mutex *m){assert(held);held--;assert(!pthread_mutex_unlock(&m->value));}
static void mutex_destroy(struct mutex *m){assert(held==1);assert(!pthread_mutex_destroy(&m->value));}
static atomic_int cam_mem_mgr_state=1;
#define atomic_read(p) atomic_load(p)
struct {struct mutex m_lock;struct {bool active;s32 buf_handle;unsigned flags;uintptr_t kmdvaddr;size_t len;struct mutex q_lock;}bufq[CAM_MEM_BUFQ_MAX];unsigned long bitmap[16];}tbl;
static void clear_bit(int index,unsigned long *bitmap){assert(held==1);bitmap[index/64]&=~(1UL<<(index%64));}
static pthread_mutex_t gate=PTHREAD_MUTEX_INITIALIZER;static pthread_cond_t changed=PTHREAD_COND_INITIALIZER;static bool block_copy,entered,proceed;static atomic_bool retired,retire_started;
static bool fail_vmalloc,mutate_header;static unsigned snapshots,packet_reads;
static void *vmalloc(size_t n){assert(held==2);if(fail_vmalloc)return NULL;void *p=malloc(n);if(p)snapshots++;return p;}
static void vfree(void *p){if(p){assert(snapshots);snapshots--;free(p);}}
static void checked_copy(void *dst,const void *src,size_t bytes){assert(held==2);pthread_mutex_lock(&gate);if(block_copy){entered=true;pthread_cond_broadcast(&changed);while(!proceed)pthread_cond_wait(&changed,&gate);}pthread_mutex_unlock(&gate);memcpy(dst,src,bytes);if(mutate_header&&++packet_reads==1)((struct cam_packet *)src)->header.size+=8;}
#define memcpy checked_copy
'''
MAIN=r'''
#undef memcpy
static void snapshot_cases(void){
 union {max_align_t align;unsigned char bytes[256];} memory;memset(memory.bytes,0,256);struct cam_packet *packet=(void *)memory.bytes;packet->header.size=128;packet->header.op_code=0x55;tbl.bufq[1].kmdvaddr=(uintptr_t)memory.bytes;tbl.bufq[1].len=256;void *owned;size_t bytes;
 assert(!pico_mem_dup_packet(0x20001,0,&owned,&bytes)&&bytes==128&&((struct cam_packet *)owned)->header.op_code==0x55&&snapshots==1);cam_mem_put_slot(1);memset(memory.bytes,0,256);assert(((struct cam_packet *)owned)->header.op_code==0x55);vfree(owned);assert(pico_mem_dup_packet(0x20001,0,&owned,&bytes)==-EINVAL&&!owned&&!bytes);
 assert(!pthread_mutex_init(&tbl.bufq[1].q_lock.value,NULL));tbl.bufq[1].active=true;packet->header.size=128;fail_vmalloc=true;assert(pico_mem_dup_packet(0x20001,0,&owned,&bytes)==-ENOMEM&&!owned&&!bytes&&!snapshots);fail_vmalloc=false;
 memcpy(memory.bytes+200,"data",4);assert(!pico_mem_dup_range(0x20001,200,4,&owned)&&!memcmp(owned,"data",4));memset(memory.bytes+200,0,4);assert(!memcmp(owned,"data",4));vfree(owned);assert(pico_mem_dup_range(0x20001,SIZE_MAX,4,&owned)==-EINVAL&&!owned);assert(pico_mem_dup_range(0x20001,0,SIZE_MAX,&owned)==-EINVAL&&!owned);fail_vmalloc=true;assert(pico_mem_dup_range(0x20001,0,4,&owned)==-ENOMEM&&!owned&&!snapshots);fail_vmalloc=false;
 assert(pico_mem_dup_packet(0x20001,SIZE_MAX,&owned,&bytes)==-EINVAL&&!owned&&!bytes);packet->header.size=257;assert(pico_mem_dup_packet(0x20001,0,&owned,&bytes)==-EINVAL&&!snapshots);packet->header.size=0;assert(pico_mem_dup_packet(0x20001,0,&owned,&bytes)==-EINVAL&&!snapshots);packet->header.size=offsetof(struct cam_packet,payload);assert(!pico_mem_dup_packet(0x20001,0,&owned,&bytes)&&bytes==offsetof(struct cam_packet,payload));vfree(owned);packet->header.size=128;mutate_header=true;assert(pico_mem_dup_packet(0x20001,0,&owned,&bytes)==-EINVAL&&!owned&&!bytes&&!snapshots);mutate_header=false;
}
static unsigned char output[8],source[4]={1,2,3,4};static int copy_result;
static void *copy_worker(void *arg){copy_result=pico_mem_copy_to(0x10001,2,source,4);return NULL;}
static void *retire_worker(void *arg){atomic_store(&retire_started,true);cam_mem_put_slot(1);atomic_store(&retired,true);return NULL;}
int main(void){
 assert(!pthread_mutex_init(&tbl.m_lock.value,NULL));assert(!pthread_mutex_init(&tbl.bufq[1].q_lock.value,NULL));tbl.bufq[1].active=true;tbl.bufq[1].buf_handle=0x10001;tbl.bufq[1].flags=CAM_MEM_FLAG_KMD_ACCESS;tbl.bufq[1].kmdvaddr=(uintptr_t)output;tbl.bufq[1].len=8;tbl.bitmap[0]=2;
 assert(!pico_mem_copy_to(0x10001,2,source,4)&&!memcmp(output+2,source,4));assert(pico_mem_copy_to(0x20001,2,source,4)==-EINVAL);assert(pico_mem_copy_to(0x10001,SIZE_MAX,source,4)==-EINVAL);assert(pico_mem_copy_to(0x10001,0,source,SIZE_MAX)==-EINVAL);assert(pico_mem_copy_to(0x10001,8,source,0)==-EINVAL);assert(pico_mem_copy_to(0x10001,0,NULL,1)==-EINVAL);tbl.bufq[1].flags=0;assert(pico_mem_copy_to(0x10001,0,source,4)==-EINVAL);tbl.bufq[1].flags=CAM_MEM_FLAG_KMD_ACCESS;
 block_copy=true;pthread_t writer,releaser;assert(!pthread_create(&writer,NULL,copy_worker,NULL));pthread_mutex_lock(&gate);while(!entered)pthread_cond_wait(&changed,&gate);pthread_mutex_unlock(&gate);assert(pthread_mutex_trylock(&tbl.m_lock.value)==EBUSY);assert(!pthread_create(&releaser,NULL,retire_worker,NULL));while(!atomic_load(&retire_started)){}assert(!atomic_load(&retired));pthread_mutex_lock(&gate);proceed=true;pthread_cond_broadcast(&changed);pthread_mutex_unlock(&gate);assert(!pthread_join(writer,NULL)&&!pthread_join(releaser,NULL));assert(!copy_result&&atomic_load(&retired)&&!tbl.bufq[1].active&&!tbl.bitmap[0]&&!memcmp(output+2,source,4));
 assert(pico_mem_copy_to(0x10001,0,source,4)==-EINVAL);assert(!pthread_mutex_init(&tbl.bufq[1].q_lock.value,NULL));tbl.bufq[1].active=true;tbl.bufq[1].buf_handle=0x20001;block_copy=false;memset(output,0,8);assert(pico_mem_copy_to(0x10001,0,source,4)==-EINVAL&&!output[0]);assert(!pico_mem_copy_to(0x20001,0,source,4)&&!memcmp(output,source,4));snapshot_cases();atomic_store(&cam_mem_mgr_state,0);assert(pico_mem_copy_to(0x20001,0,source,4)==-EINVAL);assert(!held);assert(!pthread_mutex_destroy(&tbl.bufq[1].q_lock.value));assert(!pthread_mutex_destroy(&tbl.m_lock.value));puts("PASS: actual output copy/packet snapshot/native slot retirement; lock exclusion, owned packet survives retired/overwritten source, allocation/header-change cleanup and size/offset guards, reuse rejects changed old handle");
}
'''
def main():
    spec=importlib.util.spec_from_file_location('extract',Path(__file__).with_name('test-pico-sensor-mono-hook.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    header=(SOURCE/NAMES[3]).read_text();define=next(line for line in header.splitlines() if line.startswith('#define CAM_MEM_BUFQ_MAX '));core=(SOURCE/NAMES[2]).read_text()
    code=define+'\n'+HARNESS+(SOURCE/NAMES[0]).read_text()+m.function(core,'static void cam_mem_put_slot(')+MAIN;out=BASE/'out/phoenix-kernel-recovery/mem-output-copy-tests';out.mkdir(exist_ok=True);(out/'harness.c').write_text(code)
    subprocess.run(['gcc','-std=gnu11','-g','-O1','-pthread','-fsanitize=address,undefined','-fno-omit-frame-pointer','-I'+str(SOURCE/'techpack/camera/include/uapi/media'),'-I'+str(SOURCE/'techpack/camera/include/uapi'),str(out/'harness.c'),'-o',str(out/'test')],check=True)
    r=subprocess.run([str(out/'test')],capture_output=True,text=True,timeout=10);report={'sources':{n:hashlib.sha256((SOURCE/n).read_bytes()).hexdigest() for n in NAMES},'harness_sha256':hashlib.sha256(code.encode()).hexdigest(),'exit_code':r.returncode,'stdout':r.stdout,'stderr':r.stderr,'sanitizers':['AddressSanitizer','UndefinedBehaviorSanitizer'],'scope':'Actual copy helper and native cam_mem_put_slot bodies, real handle/KMD UAPI and slot count; modeled table/lifecycle/bitmap API, host pthread locks and bounded memcpy gate; no full DMA unmap/deinit/provider/hardware proof','device_modified':False};(out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));raise SystemExit(r.returncode)
if __name__=='__main__':main()
