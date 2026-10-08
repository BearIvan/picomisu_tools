"""Execute native shared pinctrl selection with modeled mutex/provider/hold query."""
from pathlib import Path
import hashlib
import importlib.util
import json
import subprocess

spec = importlib.util.spec_from_file_location('extract', Path(__file__).with_name('test-pico-sensor-mono-hook.py'))
extract = importlib.util.module_from_spec(spec)
spec.loader.exec_module(extract)
BASE = Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro')
SOURCE = BASE / 'source/phoenix-kernel-recovery'
NAME = 'techpack/camera/drivers/cam_sensor_module/cam_res_mgr/cam_res_mgr.c'
MODEL = r'''
#include <assert.h>
#include <stdbool.h>
#include <errno.h>
#include <stdio.h>
#define CAM_DBG(...)
enum { PINCTRL_STATUS_PUT, PINCTRL_STATUS_ACTIVE, PINCTRL_STATUS_SUSPEND };
struct cam_soc_pinctrl_info { void *pinctrl, *gpio_state_active, *gpio_state_suspend; };
struct res { bool shared_gpio_enabled; int gpio_res_lock, pstatus; struct {struct cam_soc_pinctrl_info pinctrl_info;} dt; };
static struct res *cam_res;
static int provider_error, provider_calls, held, physical_state;
static void mutex_lock(int *lock) { assert(!*lock); *lock = 1; }
static void mutex_unlock(int *lock) { assert(*lock); *lock = 0; }
static bool cam_res_mgr_shared_pinctrl_check_hold(void) {
 assert(cam_res->gpio_res_lock); return held;
}
static int pinctrl_select_state(void *p, void *state) {
 assert(p == (void *)1 && cam_res->gpio_res_lock);
 provider_calls++;
 if (provider_error) return provider_error;
 physical_state = state == (void *)2 ? PINCTRL_STATUS_ACTIVE : PINCTRL_STATUS_SUSPEND;
 return 0;
}
'''
MAIN = r'''
int main(void) {
 struct res res = {.shared_gpio_enabled=true, .pstatus=PINCTRL_STATUS_SUSPEND,
 .dt.pinctrl_info={(void *)1,(void *)2,(void *)3}};
 assert(!cam_res_mgr_shared_pinctrl_select_state(true) && !provider_calls);
 cam_res=&res; res.shared_gpio_enabled=false;
 assert(!cam_res_mgr_shared_pinctrl_select_state(false) && !provider_calls);
 res.shared_gpio_enabled=true; res.pstatus=PINCTRL_STATUS_PUT;
 assert(!cam_res_mgr_shared_pinctrl_select_state(true) && !provider_calls);
 res.pstatus=physical_state=PINCTRL_STATUS_SUSPEND; provider_error=-EIO;
 assert(cam_res_mgr_shared_pinctrl_select_state(true)==-EIO);
 assert(res.pstatus==PINCTRL_STATUS_SUSPEND && physical_state==PINCTRL_STATUS_SUSPEND && !res.gpio_res_lock);
 provider_error=0;
 assert(!cam_res_mgr_shared_pinctrl_select_state(true) && res.pstatus==PINCTRL_STATUS_ACTIVE && provider_calls==2);
 assert(!cam_res_mgr_shared_pinctrl_select_state(true) && provider_calls==2);
 held=1; assert(!cam_res_mgr_shared_pinctrl_select_state(false) && res.pstatus==PINCTRL_STATUS_ACTIVE && provider_calls==2);
 held=0; provider_error=-EBUSY;
 assert(cam_res_mgr_shared_pinctrl_select_state(false)==-EBUSY);
 assert(res.pstatus==PINCTRL_STATUS_ACTIVE && physical_state==PINCTRL_STATUS_ACTIVE && !res.gpio_res_lock);
 provider_error=0;
 assert(!cam_res_mgr_shared_pinctrl_select_state(false) && res.pstatus==PINCTRL_STATUS_SUSPEND && physical_state==PINCTRL_STATUS_SUSPEND && provider_calls==4);
 assert(!res.gpio_res_lock);
 puts("PASS: failed ACTIVE and SUSPEND preserve prior software state; retries reach provider; hold and no-provider paths preserved");
 return 0;
}
'''

def main():
    body = extract.function((SOURCE / NAME).read_text(), 'int cam_res_mgr_shared_pinctrl_select_state(')
    code = MODEL + body + MAIN
    out = BASE / 'out/phoenix-kernel-recovery/shared-pinctrl-state-tests'
    out.mkdir(exist_ok=True)
    (out / 'harness.c').write_text(code)
    subprocess.run(['gcc','-std=gnu11','-g','-O1','-fsanitize=address,undefined','-fno-sanitize-recover=all',str(out / 'harness.c'),'-o',str(out / 'test')],check=True)
    run = subprocess.run([str(out / 'test')],capture_output=True,text=True,timeout=30)
    report = {'sources':{NAME:hashlib.sha256((SOURCE / NAME).read_bytes()).hexdigest()},'harness_sha256':hashlib.sha256(code.encode()).hexdigest(),'exit_code':run.returncode,'stdout':run.stdout,'stderr':run.stderr,'scope':'Actual native shared pinctrl selection body. Mutex, provider, hold query and layouts modeled. No hardware, concurrency or shared put/common power-down validation.','device_modified':False}
    (out / 'result.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
    raise SystemExit(run.returncode)

if __name__ == '__main__':
    main()
