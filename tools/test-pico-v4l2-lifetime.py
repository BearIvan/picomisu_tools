"""Actual owner registry plus native node creation/release; ref/file APIs modeled."""
from pathlib import Path
import hashlib,json,re,subprocess,importlib.util
def load(n):
    s=importlib.util.spec_from_file_location(n,Path(__file__).with_name(n+'.py'));m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
ex=load('test-pico-sensor-mono-hook')
BASE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro');SOURCE=BASE/'source/phoenix-kernel-recovery'
NAMES=['drivers/media/v4l2-core/v4l2-device.c','drivers/media/v4l2-core/pico-v4l2-lifetime.inc','include/media/pico-v4l2-lifetime.h']
MODEL=r'''
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
#define container_of(p,t,m) ((t *)((char *)(p)-offsetof(t,m)))
struct list_head {struct list_head *next,*prev;};
#define LIST_HEAD(n) struct list_head n={&n,&n}
static void INIT_LIST_HEAD(struct list_head *p){p->next=p->prev=p;}
static void list_add_tail(struct list_head *p,struct list_head *h){p->prev=h->prev;p->next=h;h->prev->next=p;h->prev=p;}
static void list_del(struct list_head *p){p->prev->next=p->next;p->next->prev=p->prev;}
#define list_for_each_entry(p,h,m) for(p=container_of((h)->next,__typeof__(*p),m); &(p)->m!=(h);p=container_of((p)->m.next,__typeof__(*p),m))
#define DEFINE_MUTEX(n) int n
static void mutex_lock(int *m){assert(!*m);*m=1;}
static void mutex_unlock(int *m){assert(*m);*m=0;}
struct kref {int refs;};
static void kref_init(struct kref *k){k->refs=1;}
static void kref_get(struct kref *k){assert(k->refs>0);k->refs++;}
static void kref_put(struct kref *k,void (*release)(struct kref *)){assert(k->refs>0);if(!--k->refs)release(k);}
struct module {int refs;};
static int denied,fail_alloc,fail_register,fail_link,published,releases;
static int try_module_get(struct module *m){if(denied)return 0;if(m)m->refs++;return 1;}
static void module_put(struct module *m){if(m){assert(m->refs>0);m->refs--;}}
#define GFP_KERNEL 0
#define kzalloc(s,f) (fail_alloc?NULL:calloc(1,s))
#define kfree free
#define EXPORT_SYMBOL_GPL(x)
#define V4L2_SUBDEV_FL_HAS_DEVNODE 1
#define VFL_TYPE_SUBDEV 1
#define VIDEO_MAJOR 81
#define MEDIA_LNK_FL_ENABLED 1
#define MEDIA_LNK_FL_IMMUTABLE 2
struct media_link {int unused;};
struct media_entity {struct {struct {int major,minor;} dev;} info;};
struct media_intf {int unused;};
struct media_devnode {struct media_intf intf;};
static struct media_devnode intf;
static struct media_link link;
static struct media_link *media_create_intf_link(struct media_entity *e,struct media_intf *i,int flags){return fail_link?NULL:&link;}
struct v4l2_device {struct list_head subdevs;void *mdev;};
struct v4l2_subdev;
struct video_device {struct v4l2_subdev *sd;char name[32];struct v4l2_device *v4l2_dev;void *fops;void (*release)(struct video_device *);void *ctrl_handler;int refs,minor,registered;struct media_devnode *intf_devnode;};
struct v4l2_subdev {struct list_head list;struct v4l2_device *v4l2_dev;struct video_device *devnode;unsigned flags;char name[32];struct module *owner;void *ctrl_handler;struct media_entity entity;};
static int v4l2_subdev_fops;
static void video_set_drvdata(struct video_device *v,struct v4l2_subdev *sd){v->sd=sd;}
static struct v4l2_subdev *video_get_drvdata(struct video_device *v){return v->sd;}
static size_t strlcpy(char *d,const char *s,size_t n){snprintf(d,n,"%s",s);return strlen(s);}
static int __video_register_device(struct video_device *v,int t,int nr,int warn,struct module *owner);
static void video_put(struct video_device *v){assert(v->refs>0);if(!--v->refs)v->release(v);}
static void video_unregister_device(struct video_device *v){if(v&&v->registered){v->registered=0;video_put(v);}}
'''
MAIN=r'''
static int __video_register_device(struct video_device *v,int t,int nr,int warn,struct module *owner){
 struct pico_subdev_node *node=container_of(v,struct pico_subdev_node,vdev);
 if(node->owner)assert(node->owner->ref.refs==2); /* pin already held before publication */
 if(fail_register)return -EIO;v->refs=1;v->registered=1;v->intf_devnode=&intf;published++;return 0;
}
static void release_owner(void *p){assert(!pico_subdev_owners_lock);releases++;free(p);}
static struct v4l2_subdev *make_owner(void){struct v4l2_subdev *s=calloc(1,sizeof(*s));assert(s);s->flags=1;strcpy(s->name,"fixture");return s;}
static void attach(struct v4l2_subdev *sd,struct v4l2_device *parent){sd->v4l2_dev=parent;list_add_tail(&sd->list,&parent->subdevs);}
static void detach(struct v4l2_subdev *sd){list_del(&sd->list);sd->v4l2_dev=NULL;}
int main(void){
 struct module code={0};struct v4l2_device parent={.mdev=(void *)1};INIT_LIST_HEAD(&parent.subdevs);
 struct v4l2_subdev *sd=make_owner();assert(pico_v4l2_subdev_owner_bind(NULL,sd,release_owner,&code)==-EINVAL);
 fail_alloc=1;assert(pico_v4l2_subdev_owner_bind(sd,sd,release_owner,&code)==-ENOMEM);fail_alloc=0;
 denied=1;assert(pico_v4l2_subdev_owner_bind(sd,sd,release_owner,&code)==-ENODEV);denied=0;
 assert(!pico_v4l2_subdev_owner_bind(sd,sd,release_owner,&code)&&code.refs==1);
 assert(pico_v4l2_subdev_owner_bind(sd,sd,release_owner,&code)==-EEXIST&&code.refs==1);
 attach(sd,&parent);assert(pico_v4l2_subdev_owner_retire(sd)==-EBUSY);
 fail_alloc=1;assert(v4l2_device_register_subdev_nodes(&parent)==-ENOMEM);fail_alloc=0;
 fail_register=1;assert(v4l2_device_register_subdev_nodes(&parent)==-EIO&&!sd->devnode&&!releases);fail_register=0;
#ifdef CONFIG_MEDIA_CONTROLLER
 fail_link=1;assert(v4l2_device_register_subdev_nodes(&parent)==-ENOMEM&&!sd->devnode&&!releases);fail_link=0;
#endif
 assert(!v4l2_device_register_subdev_nodes(&parent)&&sd->devnode);
 struct video_device *node=sd->devnode;node->refs++; /* open file */
 detach(sd);video_unregister_device(node);assert(!releases&&sd->devnode==node);
 assert(!pico_v4l2_subdev_owner_retire(sd)&&!releases&&code.refs==1);
 assert(pico_v4l2_subdev_owner_retire(sd)==-EALREADY);
 struct pico_subdev_owner *borrow;assert(pico_subdev_node_pin(sd,&borrow)==-ENODEV&&!borrow);
 video_put(node);assert(releases==1&&!code.refs); /* native release touches sd before owner free */
 sd=make_owner();assert(!pico_v4l2_subdev_owner_bind(sd,sd,release_owner,NULL));assert(!pico_v4l2_subdev_owner_retire(sd)&&releases==2); /* probe fail, no published node */
 sd=make_owner();assert(!pico_v4l2_subdev_owner_bind(sd,sd,release_owner,&code));attach(sd,&parent);assert(!v4l2_device_register_subdev_nodes(&parent));node=sd->devnode;detach(sd);video_unregister_device(node);assert(releases==2&&!sd->devnode);assert(!pico_v4l2_subdev_owner_retire(sd)&&releases==3&&!code.refs); /* node first, driver last */
 sd=make_owner();attach(sd,&parent);assert(pico_v4l2_subdev_owner_bind(sd,sd,release_owner,&code)==-EBUSY&&!code.refs);assert(!v4l2_device_register_subdev_nodes(&parent));node=sd->devnode;detach(sd);video_unregister_device(node);assert(!sd->devnode);assert(pico_v4l2_subdev_owner_retire(sd)==-ENOENT);free(sd); /* legacy path unchanged */
 assert(pico_subdev_owners.next==&pico_subdev_owners);puts("PASS: actual registry/native node creation/release, pin before publication, delayed owner free after final file, retirement guards, allocation/register errors, both release orders, legacy node");return 0;
}
'''
def main():
    dev=(SOURCE/NAMES[0]).read_text();inc=(SOURCE/NAMES[1]).read_text()
    inc='\n'.join(l for l in inc.splitlines() if not l.startswith('#include'))
    code=MODEL+inc+'\nstatic void '+ex.function(dev,'v4l2_device_release_subdev_node')+'\nint '+ex.function(dev,'v4l2_device_register_subdev_nodes')+MAIN
    out=BASE/'out/phoenix-kernel-recovery/v4l2-lifetime-tests';out.mkdir(exist_ok=True);(out/'harness.c').write_text(code)
    runs={}
    for config in [0,1]:
        binary=out/('test-'+str(config));subprocess.run(['gcc','-std=gnu11','-g','-O1','-fsanitize=address,undefined','-fno-sanitize-recover=all']+(['-DCONFIG_MEDIA_CONTROLLER=1'] if config else [])+[str(out/'harness.c'),'-o',str(binary)],check=True)
        r=subprocess.run([str(binary)],capture_output=True,text=True,timeout=30);runs[str(config)]={'exit_code':r.returncode,'stdout':r.stdout,'stderr':r.stderr}
    report={'sources':{n:hashlib.sha256((SOURCE/n).read_bytes()).hexdigest() for n in NAMES},'harness_sha256':hashlib.sha256(code.encode()).hexdigest(),'exit_code':0 if all(r['exit_code']==0 for r in runs.values()) else 1,'runs':runs,'scope':'Actual registry and native node creation/final release with media config on/off; module/kref/list/mutex/video file/device/link APIs modeled. No concurrent scheduling, actuator bind/retire or physical removal integration.','device_modified':False}
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));raise SystemExit(report['exit_code'])
if __name__=='__main__':main()
