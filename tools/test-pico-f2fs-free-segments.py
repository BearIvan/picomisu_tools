"""Execute the actual f2fs free_segments_show under ASan/UBSan and check its sysfs registration."""
from pathlib import Path
import hashlib,importlib.util,json,re,subprocess
BASE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro');SOURCE=BASE/'source/phoenix-kernel-recovery'
NAME='fs/f2fs/sysfs.c'
MODEL=r'''
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <sys/types.h>
#define PAGE_SIZE 4096
struct free_segmap_info {unsigned start_segno;unsigned free_segments;};
struct f2fs_sm_info {void *sit;struct free_segmap_info *free_info;};
struct f2fs_sb_info {struct f2fs_sm_info *sm_info;};
#define FREE_I(s) ((s)->sm_info->free_info)
static unsigned free_segments(struct f2fs_sb_info *s){return FREE_I(s)->free_segments;}
struct f2fs_attr {int x;};
'''
MAIN=r'''
int main(void){char buf[PAGE_SIZE];struct free_segmap_info fi={0,4242};struct f2fs_sm_info sm={0,&fi};struct f2fs_sb_info sbi={&sm};
 assert(free_segments_show(NULL,&sbi,buf)==5&&!strcmp(buf,"4242\n"));
 fi.free_segments=0xffffffffu;assert(free_segments_show(NULL,&sbi,buf)==11&&!strcmp(buf,"4294967295\n"));
 puts("PASS: free_segments_show prints FREE_I(sbi)->free_segments");return 0;}
'''
def main():
    spec=importlib.util.spec_from_file_location('ex',Path(__file__).with_name('test-pico-sensor-mono-hook.py'));ex=importlib.util.module_from_spec(spec);spec.loader.exec_module(ex)
    src=(SOURCE/NAME).read_text()
    assert re.search(r'^F2FS_GENERAL_RO_ATTR\(free_segments\);$',src,re.M),'attr'
    attrs=src[src.index('static struct attribute *f2fs_attrs[]'):]
    attrs=attrs[:attrs.index('};')]
    assert 'ATTR_LIST(free_segments),' in attrs,'list'
    code=MODEL+ex.function(src,'static ssize_t free_segments_show(')+MAIN
    out=BASE/'out/phoenix-kernel-recovery/f2fs-free-segments-tests';out.mkdir(exist_ok=True);(out/'harness.c').write_text(code)
    subprocess.run(['gcc','-std=gnu11','-g','-O1','-Wall','-fsanitize=address,undefined','-fno-sanitize-recover=all',str(out/'harness.c'),'-o',str(out/'test')],check=True)
    r=subprocess.run([str(out/'test')],capture_output=True,text=True,timeout=60)
    report={'sources':{NAME:hashlib.sha256((SOURCE/NAME).read_bytes()).hexdigest()},'harness_sha256':hashlib.sha256(code.encode()).hexdigest(),
            'exit_code':r.returncode,'stdout':r.stdout,'stderr':r.stderr[-2000:],'scope':'Actual free_segments_show; attribute definition and f2fs_attrs registration checked on the source.','device_modified':False}
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));raise SystemExit(r.returncode)
if __name__=='__main__':main()
