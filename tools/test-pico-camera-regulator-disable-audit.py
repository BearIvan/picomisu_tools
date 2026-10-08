"""Audit actual camera regulator disable helper; provider APIs modeled."""
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
NAME = 'techpack/camera/drivers/cam_utils/cam_soc_util.c'
MODEL = r'''
#include <assert.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#define CAM_ERR(...)
struct regulator { int enabled, load, voltage; };
static int disable_error, load_error, voltage_error;
static int disable_calls, load_calls, voltage_calls, delay_calls;
static int regulator_disable(struct regulator *r) {
 disable_calls++;
 if (disable_error) return disable_error;
 assert(r->enabled == 1); r->enabled = 0; return 0;
}
static int regulator_count_voltages(struct regulator *r) { return 1; }
static int regulator_set_load(struct regulator *r, int load) {
 load_calls++; if (load_error) return load_error; r->load = load; return 0;
}
static int regulator_set_voltage(struct regulator *r, int min, int max) {
 voltage_calls++; if (voltage_error) return voltage_error; r->voltage = min; return 0;
}
static void msleep(unsigned n) { delay_calls++; }
static void usleep_range(unsigned a, unsigned b) { delay_calls++; }
'''
MAIN = r'''
static void reset(void) {
 disable_error = load_error = voltage_error = 0;
 disable_calls = load_calls = voltage_calls = delay_calls = 0;
}
int main(void) {
 struct regulator r;
 reset(); r = (struct regulator){1,100,1800000};
 assert(!cam_soc_util_regulator_disable(&r,"cam",1800000,1800000,100,10));
 assert(!r.enabled && !r.load && !r.voltage && delay_calls == 1);
 reset(); r = (struct regulator){1,100,1800000}; disable_error = -EIO;
 assert(cam_soc_util_regulator_disable(&r,"cam",1800000,1800000,100,10) == -EIO);
 assert(r.enabled && r.load == 100 && r.voltage == 1800000);
 assert(!load_calls && !voltage_calls && !delay_calls);
 reset(); r = (struct regulator){1,100,1800000}; load_error = -EIO;
 assert(!cam_soc_util_regulator_disable(&r,"cam",1800000,1800000,100,10));
 assert(!r.enabled && r.load == 100 && !r.voltage && load_calls == 1 && voltage_calls == 1);
 puts("CONFIRMED: load reset failure discarded after disable; voltage reset still runs, helper returns0");
 reset(); r = (struct regulator){1,100,1800000}; voltage_error = -EBUSY;
 assert(!cam_soc_util_regulator_disable(&r,"cam",1800000,1800000,100,10));
 assert(!r.enabled && !r.load && r.voltage == 1800000);
 puts("CONFIRMED: voltage reset failure discarded after disable, helper returns0");
 reset(); r = (struct regulator){1,100,1800000}; load_error = -EIO; voltage_error = -EBUSY;
 assert(!cam_soc_util_regulator_disable(&r,"cam",1800000,1800000,100,10));
 assert(!r.enabled && r.load == 100 && r.voltage == 1800000);
 assert(cam_soc_util_regulator_disable(NULL,"cam",0,0,0,0) == -EINVAL);
 return 0;
}
'''

def main():
    source = (SOURCE / NAME).read_text()
    body = extract.function(source, 'int cam_soc_util_regulator_disable(')
    code = MODEL + body + MAIN
    out = BASE / 'out/phoenix-kernel-recovery/camera-regulator-disable-audit'
    out.mkdir(exist_ok=True)
    (out / 'harness.c').write_text(code)
    (out / 'actual-regulator-disable.c').write_text(body)
    subprocess.run(['gcc','-std=gnu11','-g','-O1','-fsanitize=address,undefined','-fno-sanitize-recover=all',str(out / 'harness.c'),'-o',str(out / 'test')],check=True)
    run = subprocess.run([str(out / 'test')],capture_output=True,text=True,timeout=30)
    report = {'sources':{NAME:hashlib.sha256((SOURCE / NAME).read_bytes()).hexdigest()},'harness_sha256':hashlib.sha256(code.encode()).hexdigest(),'audit_exit_code':run.returncode,'stdout':run.stdout,'stderr':run.stderr,'scope':'Actual cam_soc_util_regulator_disable body; regulator provider APIs and layout modeled. Exit0 confirms discarded load/voltage errors, not complete power-down. No real kernel or hardware execution.','device_modified':False}
    (out / 'result.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
    raise SystemExit(run.returncode)

if __name__ == '__main__':
    main()
