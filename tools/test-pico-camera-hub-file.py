"""Test actual hub worker/helper bodies with host threads and mocked VFS.

The test does not open device nodes. It checks ownership, worker drain on
timeout, both factory operation groups, and unchanged VFS error results.
"""
from pathlib import Path
import hashlib
import json
import subprocess

BASE = Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro')
DIRECTORY = 'techpack/camera/drivers/cam_core/'

HARNESS = r'''
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <pthread.h>
#include <stdatomic.h>
#include <unistd.h>
#include <time.h>
#include <fcntl.h>
typedef uint32_t u32;
#define GFP_KERNEL 0
#define container_of(p,t,m) ((t *)((char *)(p)-offsetof(t,m)))
#define ERR_PTR(n) ((void *)(intptr_t)(n))
#define PTR_ERR(p) ((long)(intptr_t)(p))
#define IS_ERR(p) ((uintptr_t)(p)>=(uintptr_t)-4095)
#define IS_ERR_OR_NULL(p) (!(p)||IS_ERR(p))
#define pico_hub_check_work_layouts() ((void)0)
struct file {int token;};
struct completion {atomic_bool done;};
struct work_struct {
 void (*fn)(struct work_struct *);pthread_t thread;
 atomic_bool started;bool pending,has_thread;
};
struct workqueue_struct {int dummy;};
/* HEADER */
static _Thread_local bool in_worker;
static atomic_uint opens,closes,deferred_closes,files_allocated,files_freed;
static unsigned jobs_allocated,jobs_freed,queue_calls;
static int fail_alloc,fail_queue_at,defer_next,open_error;
static unsigned open_delay_ms,close_delay_ms;
static const char *expected_path;
static void *kzalloc(size_t n,int flags) {
 if(fail_alloc)return 0;void *p=calloc(1,n);assert(p);jobs_allocated++;return p;
}
static void kfree(void *p) {if(p){jobs_freed++;free(p);}}
static unsigned long strlcpy(char *to,const char *from,size_t n) {
 size_t len=strlen(from);if(n){size_t take=len<n-1?len:n-1;memcpy(to,from,take);to[take]=0;}return len;
}
static void init_completion(struct completion *c) {atomic_init(&c->done,false);}
static void complete(struct completion *c) {atomic_store(&c->done,true);}
static unsigned long now_ms(void) {
 struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return t.tv_sec*1000UL+t.tv_nsec/1000000UL;
}
static unsigned long wait_for_completion_timeout(struct completion *c,unsigned long timeout) {
 unsigned long start=now_ms();
 while(!atomic_load(&c->done)) {if(now_ms()-start>=timeout)return 0;usleep(100);}
 return 1;
}
static void mock_init_work(struct work_struct *w,void (*fn)(struct work_struct *)) {
 w->fn=fn;w->pending=false;w->has_thread=false;atomic_init(&w->started,false);
}
#define INIT_WORK(w,fn) mock_init_work(w,fn)
static void *threadfn(void *p) {
 struct work_struct *w=p;in_worker=true;atomic_store(&w->started,true);w->fn(w);in_worker=false;return 0;
}
static bool queue_work(struct workqueue_struct *q,struct work_struct *w) {
 assert(q);queue_calls++;if(queue_calls==fail_queue_at)return false;
 assert(!w->pending && !w->has_thread);w->pending=true;
 if(defer_next){defer_next=0;return true;}
 w->has_thread=true;assert(!pthread_create(&w->thread,0,threadfn,w));return true;
}
static bool cancel_work_sync(struct work_struct *w) {
 if(w->has_thread){assert(!pthread_join(w->thread,0));w->has_thread=false;w->pending=false;return false;}
 bool pending=w->pending;w->pending=false;return pending;
}
static bool flush_work(struct work_struct *w) {
 bool pending=w->pending;
 if(w->has_thread){assert(!pthread_join(w->thread,0));w->has_thread=false;}
 else if(w->pending){bool saved=in_worker;in_worker=true;w->fn(w);in_worker=saved;}
 w->pending=false;return pending;
}
static struct file *filp_open(const char *path,int flags,int mode) {
 assert(in_worker && flags==O_RDWR && !mode);assert(!strcmp(path,expected_path));
 atomic_fetch_add(&opens,1);usleep(open_delay_ms*1000);
 if(open_error)return ERR_PTR(open_error);
 struct file *f=malloc(sizeof(*f));assert(f);f->token=99;atomic_fetch_add(&files_allocated,1);return f;
}
static void drop(struct file *f) {
 assert(!IS_ERR_OR_NULL(f) && f->token==99);f->token=0;free(f);atomic_fetch_add(&files_freed,1);
}
static void __fput_sync(struct file *f) {
 assert(in_worker);usleep(close_delay_ms*1000);atomic_fetch_add(&closes,1);drop(f);
}
static void fput(struct file *f) {atomic_fetch_add(&deferred_closes,1);drop(f);}
/* SOURCE */
static void reset(void) {
 assert(jobs_allocated==jobs_freed && atomic_load(&files_allocated)==atomic_load(&files_freed));
 fail_alloc=fail_queue_at=defer_next=open_error=0;open_delay_ms=close_delay_ms=0;queue_calls=0;
 expected_path="/dev/video0";
}
int main(void) {
 struct workqueue_struct q={0};struct file *file;
 reset();assert(PTR_ERR(pico_hub_file_open(0,PICO_HUB_VIDEO_OPEN,"x",100))==-ENODEV);
 assert(PTR_ERR(pico_hub_file_open(&q,PICO_HUB_VIDEO_CLOSE,"x",100))==-EINVAL);
 assert(PTR_ERR(pico_hub_file_open(&q,PICO_HUB_VIDEO_OPEN,0,100))==-EINVAL);
 char too_long[65];memset(too_long,'x',64);too_long[64]=0;
 assert(PTR_ERR(pico_hub_file_open(&q,PICO_HUB_VIDEO_OPEN,too_long,100))==-ENAMETOOLONG);
 fail_alloc=1;assert(PTR_ERR(pico_hub_file_open(&q,PICO_HUB_VIDEO_OPEN,expected_path,100))==-ENOMEM);
 reset();fail_queue_at=1;assert(PTR_ERR(pico_hub_file_open(&q,PICO_HUB_VIDEO_OPEN,expected_path,100))==-EBUSY);
 reset();open_error=-ENOENT;assert(PTR_ERR(pico_hub_file_open(&q,PICO_HUB_VIDEO_OPEN,expected_path,1000))==-ENOENT);
 for(unsigned kind=0;kind<2;kind++) {
  reset();enum pico_hub_file_operation op=kind?PICO_HUB_SUBDEVICE_OPEN:PICO_HUB_VIDEO_OPEN;
  file=pico_hub_file_open(&q,op,expected_path,1000);assert(!IS_ERR_OR_NULL(file));
  assert(!pico_hub_file_close(&q,kind?PICO_HUB_SUBDEVICE_CLOSE:PICO_HUB_VIDEO_CLOSE,file,1000));
 }
 reset();defer_next=1;unsigned before=atomic_load(&opens);
 assert(PTR_ERR(pico_hub_file_open(&q,PICO_HUB_VIDEO_OPEN,expected_path,0))==-ETIMEDOUT);
 assert(atomic_load(&opens)==before); /* canceled before worker start */
 reset();open_delay_ms=30;before=atomic_load(&closes);
 assert(PTR_ERR(pico_hub_file_open(&q,PICO_HUB_SUBDEVICE_OPEN,expected_path,1))==-ETIMEDOUT);
 assert(atomic_load(&closes)==before+1); /* running open drained, late file closed */
 reset();open_delay_ms=30;open_error=-EIO;before=atomic_load(&closes);
 assert(PTR_ERR(pico_hub_file_open(&q,PICO_HUB_VIDEO_OPEN,expected_path,1))==-ETIMEDOUT);
 assert(atomic_load(&closes)==before); /* ERR_PTR has no reference */
 reset();open_delay_ms=30;fail_queue_at=2;before=atomic_load(&deferred_closes);
 assert(PTR_ERR(pico_hub_file_open(&q,PICO_HUB_VIDEO_OPEN,expected_path,1))==-ETIMEDOUT);
 assert(atomic_load(&deferred_closes)==before+1);
 reset();file=pico_hub_file_open(&q,PICO_HUB_VIDEO_OPEN,expected_path,1000);
 assert(pico_hub_file_close(0,PICO_HUB_VIDEO_CLOSE,file,100)==-ENODEV);
 assert(pico_hub_file_close(&q,PICO_HUB_VIDEO_OPEN,file,100)==-EINVAL);
 assert(pico_hub_file_close(&q,PICO_HUB_VIDEO_CLOSE,ERR_PTR(-ENOENT),100)==-EINVAL);
 fail_alloc=1;assert(pico_hub_file_close(&q,PICO_HUB_VIDEO_CLOSE,file,100)==-ENOMEM);
 fail_alloc=0;fail_queue_at=queue_calls+1;
 assert(pico_hub_file_close(&q,PICO_HUB_VIDEO_CLOSE,file,100)==-EBUSY);
 fail_queue_at=0;close_delay_ms=30;before=atomic_load(&closes);
 assert(pico_hub_file_close(&q,PICO_HUB_VIDEO_CLOSE,file,1)==-ETIMEDOUT);
 assert(atomic_load(&closes)==before+1);
 reset();file=pico_hub_file_open(&q,PICO_HUB_VIDEO_OPEN,expected_path,1000);
 defer_next=1;before=atomic_load(&closes);
 assert(pico_hub_file_close(&q,PICO_HUB_VIDEO_CLOSE,file,0)==-ETIMEDOUT);
 assert(atomic_load(&closes)==before+1); /* pending close is flushed, not canceled */
 reset();puts("PASS: both open/close modes, VFS errors, queue/allocation failures, pending/running timeout cleanup and exact reference ownership");
}
'''


def main():
    root = BASE / 'source/phoenix-kernel-recovery' / DIRECTORY
    source = (root / 'pico_camera_hub_file.c').read_text()
    header = (root / 'pico_camera_hub_file.h').read_text()
    types = header[header.index('enum pico_hub_file_operation'):header.index('void _video_device_workfn')]
    job = source[source.index('struct pico_hub_file_job {'):source.index('static void pico_hub_check_work_layouts')]
    body = source[source.index('void _video_device_workfn'):]
    code = HARNESS.replace('/* HEADER */', types).replace('/* SOURCE */', job + body)
    out = BASE / 'out/phoenix-kernel-recovery/camera-hub-file-tests'
    out.mkdir(exist_ok=True)
    (out / 'harness.c').write_text(code)
    subprocess.run(['gcc', '-std=gnu11', '-g', '-O1', '-pthread', '-fsanitize=address,undefined',
                    '-fno-omit-frame-pointer', str(out / 'harness.c'), '-o', str(out / 'test')], check=True)
    result = subprocess.run([str(out / 'test')], capture_output=True, text=True, timeout=30)
    report = {'source_sha256': hashlib.sha256(source.encode()).hexdigest(),
              'header_sha256': hashlib.sha256(header.encode()).hexdigest(),
              'scope': 'Actual worker/helper bodies and header structs; host queue/VFS mocks; no device nodes opened',
              'exit_code': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr,
              'sanitizers': ['AddressSanitizer', 'UndefinedBehaviorSanitizer'], 'device_modified': False}
    (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    if result.returncode:
        raise SystemExit(result.returncode)


if __name__ == '__main__':
    main()
