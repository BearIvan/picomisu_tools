"""Actual native open/pin/close with module/file APIs modeled."""
from pathlib import Path
import hashlib,json,re,subprocess,importlib.util
def load(n):
    s=importlib.util.spec_from_file_location(n,Path(__file__).with_name(n+'.py'));m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
audit=load('test-pico-v4l2-retirement-audit');SOURCE=audit.SOURCE;BASE=audit.BASE
MODEL=audit.MODEL.replace('#define CONFIG_MEDIA_CONTROLLER 1','').replace('struct v4l2_device {void *mdev;};','struct module {int refs;};\nstruct device_driver {struct module *owner;};\nstruct device {struct device_driver *driver;};\nstruct media_device {struct device *dev;};\nstruct v4l2_device {struct media_device *mdev;};').replace('struct internal_ops {int (*close)', 'struct internal_ops {int (*open)(struct v4l2_subdev *,struct v4l2_subdev_fh *);int (*close)')
MODEL+=r'''
#include <stddef.h>
#include <errno.h>
#define GFP_KERNEL 0
#define container_of(p,t,m) ((t *)((char *)(p)-offsetof(t,m)))
#define DEFINE_MUTEX(x) int x
static void mutex_lock(int *x){assert(!*x);*x=1;}
static void mutex_unlock(int *x){assert(*x);*x=0;}
static int denied,fail_alloc,fail_init,fail_open,detach_open;
static int try_module_get(struct module *m){if(denied)return 0;if(m)m->refs++;return 1;}
static void module_put(struct module *m){if(m){assert(m->refs>0);m->refs--;}}
static void *kzalloc(size_t size,int flags){return fail_alloc?NULL:calloc(1,size);}
static int subdev_fh_init(struct v4l2_subdev_fh *f,struct v4l2_subdev *s){return fail_init?-ENOMEM:0;}
static void v4l2_fh_init(struct v4l2_fh *f,struct video_device *v){}
static void v4l2_fh_add(struct v4l2_fh *f){}
static int driver_open(struct v4l2_subdev *s,struct v4l2_subdev_fh *f){if(detach_open)s->v4l2_dev=NULL;return fail_open?-EIO:0;}
'''
MAIN=r'''
int main(void){
 struct module module={0};struct device_driver driver={.owner=&module};struct device dev={.driver=&driver};struct media_device media={.dev=&dev};struct v4l2_device parent={.mdev=&media};struct internal_ops ops={.open=driver_open};struct v4l2_subdev sd={.v4l2_dev=&parent,.internal_ops=&ops};struct video_device vdev={.sd=&sd};struct file file={.vdev=&vdev};
 fail_alloc=1;assert(subdev_open(&file)==-ENOMEM&&!module.refs);fail_alloc=0;
 fail_init=1;assert(subdev_open(&file)==-ENOMEM&&!module.refs);fail_init=0;
 fail_open=1;assert(subdev_open(&file)==-EIO&&!module.refs);fail_open=0;
 detach_open=1;fail_open=1;assert(subdev_open(&file)==-EIO&&!module.refs);fail_open=0;detach_open=0;sd.v4l2_dev=&parent;
#ifdef CONFIG_MEDIA_CONTROLLER
 denied=1;assert(subdev_open(&file)==-EBUSY&&!module.refs);denied=0;
 dev.driver=NULL;assert(subdev_open(&file)==-ENODEV&&!module.refs);dev.driver=&driver;
#endif
 assert(!subdev_open(&file));
#ifdef CONFIG_MEDIA_CONTROLLER
 assert(module.refs==1);
#else
 assert(!module.refs);
#endif
 sd.v4l2_dev=NULL;parent.mdev=NULL;dev.driver=NULL; /* unregister/device state is no longer usable */
 assert(!subdev_close(&file)&&!module.refs&&!file.private_data);
 assert(subdev_open(&file)==-ENODEV&&!module.refs);
 sd.v4l2_dev=&parent;assert(!subdev_open(&file));assert(!subdev_close(&file)&&!module.refs);
 puts("PASS: native open/pin/close, balanced module ref after detached parent, no-media case, allocation/init/driver/pin failure cleanup");return 0;
}
'''
def main():
    names=audit.NAMES[:2]+['drivers/media/v4l2-core/pico-v4l2-media-pin.h']
    sub=(SOURCE/names[0]).read_text();dev=(SOURCE/names[1]).read_text()
    wrapper=re.search(r'struct pico_subdev_file \{.*?\n\};',sub,re.S).group(0)
    code=MODEL+wrapper+'\nstatic DEFINE_MUTEX(pico_subdev_parent_lock);\nint '+audit.extract.function(dev,'pico_v4l2_subdev_media_pin')+'\nstatic int '+audit.extract.function(sub,'subdev_open')+'\nstatic int '+audit.extract.function(sub,'subdev_close')+MAIN
    out=BASE/'out/phoenix-kernel-recovery/v4l2-media-pin-tests';out.mkdir(exist_ok=True);(out/'harness.c').write_text(code)
    runs={}
    for config in [0,1]:
        binary=out/('test-'+str(config));subprocess.run(['gcc','-std=gnu11','-g','-O1','-fsanitize=address,undefined','-fno-sanitize-recover=all']+(['-DCONFIG_MEDIA_CONTROLLER=1'] if config else [])+[str(out/'harness.c'),'-o',str(binary)],check=True)
        result=subprocess.run([str(binary)],capture_output=True,text=True,timeout=20);runs[str(config)]={'exit_code':result.returncode,'stdout':result.stdout,'stderr':result.stderr}
    report={'sources':{n:hashlib.sha256((SOURCE/n).read_bytes()).hexdigest() for n in names},'harness_sha256':hashlib.sha256(code.encode()).hexdigest(),'runs':runs,'exit_code':0 if all(r['exit_code']==0 for r in runs.values()) else 1,'scope':'Actual open/pin/close; module, mutex, file API and detach modeled, owner remains alive; no concurrent scheduling proof or owner/free retirement coverage.','device_modified':False}
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));raise SystemExit(report['exit_code'])
if __name__=='__main__':main()
