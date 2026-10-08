"""Actual GPIO body: modeled retirement at unlock and pthread counter contention."""
from pathlib import Path
import hashlib,importlib.util,json,subprocess
BASE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro')
SOURCE=BASE/'source/phoenix-kernel-recovery'
NAME='techpack/camera/drivers/cam_sensor_module/cam_res_mgr/cam_res_mgr.c'
MODEL=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdlib.h>
#include <stdio.h>
#include <pthread.h>
#define CAM_DBG(...)
struct cam_gpio_res {unsigned gpio; int power_on_count; struct cam_gpio_res *next;};
struct head {struct cam_gpio_res *first;};
struct manager {bool shared_gpio_enabled; pthread_mutex_t gpio_res_lock; struct head gpio_res_list;};
static struct manager manager={.shared_gpio_enabled=true,.gpio_res_lock=PTHREAD_MUTEX_INITIALIZER};
static struct manager *cam_res=&manager;
static _Thread_local int locked;
static int retire_at_unlock,retired,final_count,high_writes,low_writes,direct_writes;
#define list_for_each_entry(pos,head,member) for(pos=(head)->first;pos;pos=pos->next)
static void mutex_lock(pthread_mutex_t *m) {assert(!locked);assert(!pthread_mutex_lock(m));locked=1;}
static void mutex_unlock(pthread_mutex_t *m) {
 assert(locked);locked=0;assert(!pthread_mutex_unlock(m));
 /* A concurrent remover may free the record as soon as this lock is dropped. */
 if(retire_at_unlock){struct cam_gpio_res *r=manager.gpio_res_list.first;final_count=r->power_on_count;manager.gpio_res_list.first=NULL;free(r);retired++;retire_at_unlock=0;}
}
static void gpio_set_value_cansleep(unsigned gpio,int value){
 if(cam_res && manager.shared_gpio_enabled && gpio==7 && manager.gpio_res_list.first){assert(locked);if(value)high_writes++;else low_writes++;}
 else {assert(!locked);direct_writes++;}
}
'''
MAIN=r'''
static void *worker(void *arg) {
 for(int i=0;i<200;i++)assert(!cam_res_mgr_gpio_set_value(7,(long)arg));
 assert(!locked);return NULL;
}
int main(int argc,char **argv){
 struct cam_gpio_res *r=calloc(1,sizeof(*r));assert(r);r->gpio=7;r->power_on_count=1;manager.gpio_res_list.first=r;
 retire_at_unlock=1;assert(!cam_res_mgr_gpio_set_value(7,0));assert(retired==1&&final_count==0&&!locked&&low_writes==1);
 r=calloc(1,sizeof(*r));assert(r);r->gpio=7;manager.gpio_res_list.first=r;low_writes=high_writes=0;
 pthread_t threads[8];
 for(int i=0;i<8;i++)assert(!pthread_create(&threads[i],NULL,worker,(void *)1));
 for(int i=0;i<8;i++)assert(!pthread_join(threads[i],NULL));
 assert(r->power_on_count==1600&&high_writes==1);
 for(int i=0;i<8;i++)assert(!pthread_create(&threads[i],NULL,worker,NULL));
 for(int i=0;i<8;i++)assert(!pthread_join(threads[i],NULL));
 assert(!r->power_on_count&&low_writes==1&&!locked);
 assert(!cam_res_mgr_gpio_set_value(8,1)&&direct_writes==1&&!locked);
 manager.shared_gpio_enabled=false;assert(!cam_res_mgr_gpio_set_value(7,1)&&direct_writes==2&&!locked);
 cam_res=NULL;manager.gpio_res_list.first=NULL;assert(!cam_res_mgr_gpio_set_value(7,0)&&direct_writes==3&&!locked);
 free(r);puts("PASS: record remains protected until final use; 8 pthreads preserve 1600 votes, single high/low hardware transitions; direct paths unlock");return 0;
}
'''
def main():
    spec=importlib.util.spec_from_file_location('ex',Path(__file__).with_name('test-pico-sensor-mono-hook.py'))
    ex=importlib.util.module_from_spec(spec);spec.loader.exec_module(ex)
    body=ex.function((SOURCE/NAME).read_text(),'int cam_res_mgr_gpio_set_value(')
    code=MODEL+body+MAIN;out=BASE/'out/phoenix-kernel-recovery/shared-gpio-lock-tests';out.mkdir(exist_ok=True)
    (out/'harness.c').write_text(code)
    subprocess.run(['gcc','-std=gnu11','-g','-O1','-pthread','-fsanitize=address,undefined','-fno-sanitize-recover=all',str(out/'harness.c'),'-o',str(out/'test')],check=True)
    r=subprocess.run([str(out/'test')],capture_output=True,text=True,timeout=30)
    report={'sources':{NAME:hashlib.sha256((SOURCE/NAME).read_bytes()).hexdigest()},'harness_sha256':hashlib.sha256(code.encode()).hexdigest(),'exit_code':r.returncode,'stdout':r.stdout,'stderr':r.stderr,'scope':'Actual shared GPIO setter body; pthread mutex and concurrent vote contention. Record retirement modeled deterministically at unlock; list/provider/manager layout modeled. No real kernel remover, manager lifetime or hardware validation.','device_modified':False}
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));raise SystemExit(r.returncode)
if __name__=='__main__':main()
