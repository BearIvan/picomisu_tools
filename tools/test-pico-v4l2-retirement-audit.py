"""Audit native V4L2 close after modeled unregister/free; expected failures."""
from pathlib import Path
import hashlib, json, os, subprocess, importlib.util

spec = importlib.util.spec_from_file_location('extract', Path(__file__).with_name('test-pico-sensor-mono-hook.py'))
extract = importlib.util.module_from_spec(spec)
spec.loader.exec_module(extract)
BASE = Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro')
SOURCE = BASE / 'source/phoenix-kernel-recovery'
NAMES = ['drivers/media/v4l2-core/' + name for name in ['v4l2-subdev.c', 'v4l2-device.c', 'v4l2-dev.c']]
MODEL = r'''
#include <assert.h>
#include <stdlib.h>
#include <stdio.h>
#define CONFIG_MEDIA_CONTROLLER 1
struct media_entity {int unused;};
struct v4l2_device {void *mdev;};
struct v4l2_subdev_fh;
struct v4l2_subdev;
struct internal_ops {int (*close)(struct v4l2_subdev *,struct v4l2_subdev_fh *);};
struct v4l2_subdev {struct internal_ops *internal_ops;struct v4l2_device *v4l2_dev;struct media_entity entity;};
struct video_device {struct v4l2_subdev *sd;};
struct v4l2_fh {int unused;};
struct v4l2_subdev_fh {struct v4l2_fh vfh;};
struct file {struct video_device *vdev;void *private_data;};
static struct video_device *video_devdata(struct file *f){return f->vdev;}
static struct v4l2_subdev *vdev_to_v4l2_subdev(struct video_device *v){return v->sd;}
static struct v4l2_subdev_fh *to_v4l2_subdev_fh(struct v4l2_fh *fh){return (void *)fh;}
static void media_entity_put(struct media_entity *e){(void)e;}
static void v4l2_fh_del(struct v4l2_fh *f){(void)f;}
static void v4l2_fh_exit(struct v4l2_fh *f){(void)f;}
static void subdev_fh_free(struct v4l2_subdev_fh *f){(void)f;}
#define kfree free
'''
MAIN = r'''
int main(int argc,char **argv){
 struct v4l2_device parent={.mdev=(void *)1};
 struct v4l2_subdev *sd=calloc(1,sizeof(*sd));assert(sd);sd->v4l2_dev=&parent;
 struct video_device vdev={.sd=sd};struct file file={.vdev=&vdev,.private_data=calloc(1,sizeof(struct v4l2_subdev_fh))};assert(file.private_data);
 if(argc>1 && argv[1][0]=='u')sd->v4l2_dev=NULL; /* native unregister mutation; scheduler/devnode refs modeled */
 if(argc>1 && argv[1][0]=='f')free(sd); /* actuator remove frees embedded sd; video fd remains */
 assert(!subdev_close(&file));if(argc==1)free(sd);puts("PASS: live owner close");return 0;
}
'''

def main():
    texts = {name:(SOURCE/name).read_text() for name in NAMES}
    body = extract.function(texts[NAMES[0]], 'subdev_close')
    out = BASE / 'out/phoenix-kernel-recovery/v4l2-retirement-audit'
    out.mkdir(exist_ok=True)
    code = MODEL + 'static int ' + body + MAIN
    (out/'harness.c').write_text(code)
    subprocess.run(['gcc','-std=gnu11','-g','-O1','-fsanitize=address,undefined','-fno-sanitize-recover=all',str(out/'harness.c'),'-o',str(out/'test')],check=True)
    runs = {}
    env = dict(os.environ, ASAN_OPTIONS='detect_leaks=0')
    for mode, args in [('live',[]),('unregistered',['unregistered']),('freed',['freed'])]:
        result = subprocess.run([str(out/'test')]+args,capture_output=True,text=True,timeout=20,env=env)
        (out/(mode+'.stderr.log')).write_text(result.stderr)
        runs[mode] = {'exit_code':result.returncode,'stdout':result.stdout,'stderr':result.stderr}
    confirmed = runs['live']['exit_code']==0 and 'null pointer' in runs['unregistered']['stderr'] and 'heap-use-after-free' in runs['freed']['stderr']
    report = {'sources':{n:hashlib.sha256((SOURCE/n).read_bytes()).hexdigest() for n in NAMES},'harness_sha256':hashlib.sha256(code.encode()).hexdigest(),'runs':runs,'audit_exit_code':0 if confirmed else 1,'scope':'Actual native subdev_close; unregister NULL assignment and owner free modeled from source. V4L2 scheduler, device/file references and entity API modeled; expected sanitizer failures confirm unfinished retirement, not a passing recovery.','device_modified':False}
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'audit_exit_code':report['audit_exit_code'],'modes':{m:r['exit_code'] for m,r in runs.items()}}))
    raise SystemExit(report['audit_exit_code'])

if __name__=='__main__':main()
