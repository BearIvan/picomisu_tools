"""Execute the actual sixdof_Fsin_boottime store under ASan/UBSan and check the acquire/release FSIN irq wiring."""
from pathlib import Path
import hashlib,importlib.util,json,re,subprocess
BASE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro');SOURCE=BASE/'source/phoenix-kernel-recovery'
NAME='techpack/camera/drivers/cam_sensor_module/cam_sensor/cam_sensor_core.c'
MODEL=r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/types.h>
#define EINVAL 22
#define WRITE_ONCE(x,v) ((x)=(v))
static int infos;
#define CAM_INFO(...) (infos++)
struct device;struct device_attribute;
uint8_t Remove_Fsin = 0;
'''
MAIN=r'''
int main(void){
 assert(sixdof_Fsin_boottime_store(NULL,NULL,"1\n",2)==2&&Remove_Fsin==1&&infos==1);
 assert(sixdof_Fsin_boottime_store(NULL,NULL,"0",1)==1&&Remove_Fsin==0);
 assert(sixdof_Fsin_boottime_store(NULL,NULL,"ff",2)==2&&Remove_Fsin==0xff);
 assert(sixdof_Fsin_boottime_store(NULL,NULL,"1ff",3)==3&&Remove_Fsin==0xff);
 assert(sixdof_Fsin_boottime_store(NULL,NULL,"0x10",4)==4&&Remove_Fsin==0x10);
 Remove_Fsin=7;assert(sixdof_Fsin_boottime_store(NULL,NULL,"zz",2)==-EINVAL&&Remove_Fsin==7&&infos==5);
 assert(sixdof_Fsin_boottime_store(NULL,NULL,"",0)==-EINVAL&&Remove_Fsin==7);
 puts("PASS: hex parse, u8 truncation, 0x prefix, invalid input keeps the flag");
 return 0;
}
'''
def main():
    spec=importlib.util.spec_from_file_location('ex',Path(__file__).with_name('test-pico-sensor-mono-hook.py'));ex=importlib.util.module_from_spec(spec);spec.loader.exec_module(ex)
    src=(SOURCE/NAME).read_text()
    store=ex.function(src,'static ssize_t sixdof_Fsin_boottime_store(')
    # wiring: the attribute has the store, acquire guards registration, release always unregisters
    assert re.search(r'DEVICE_ATTR\(\s*sixdof_Fsin_boottime,\s*0664,\s*sixdof_Fsin_boottime_show,\s*sixdof_Fsin_boottime_store\)',src),'attr'
    acq=src[src.index('case CAM_ACQUIRE_DEV'):src.index('case CAM_RELEASE_DEV')]
    rel=src[src.index('case CAM_RELEASE_DEV'):src.index('case CAM_QUERY_CAP')]
    assert re.search(r'if \(!READ_ONCE\(Remove_Fsin\)\) \{\s*rc = cam_sensor_register_irq\(s_ctrl\);\s*if \(rc\)\s*goto acquire_unwind;\s*\}',acq),'acquire guard'
    assert acq.count('cam_sensor_register_irq(')==1,'acquire count'
    assert re.search(r'\n\t\tcam_sensor_unregister_irq\(s_ctrl\);',rel) and 'Remove_Fsin' not in rel,'release unconditional'
    code=MODEL+store+MAIN
    out=BASE/'out/phoenix-kernel-recovery/sixdof-remove-fsin-tests';out.mkdir(exist_ok=True);(out/'harness.c').write_text(code)
    subprocess.run(['gcc','-std=gnu11','-g','-O1','-Wall','-fsanitize=address,undefined','-fno-sanitize-recover=all',str(out/'harness.c'),'-o',str(out/'test')],check=True)
    r=subprocess.run([str(out/'test')],capture_output=True,text=True,timeout=60)
    report={'sources':{NAME:hashlib.sha256((SOURCE/NAME).read_bytes()).hexdigest()},'harness_sha256':hashlib.sha256(code.encode()).hexdigest(),
            'exit_code':r.returncode,'stdout':r.stdout,'stderr':r.stderr[-3000:],
            'scope':'Actual sixdof_Fsin_boottime_store executed; attribute, acquire guard and unconditional release unregister checked on the source text. FSIN irq ownership logic itself is pre-existing (pico_sensor_fsin_irq.inc).',
            'device_modified':False}
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));raise SystemExit(r.returncode)
if __name__=='__main__':main()
