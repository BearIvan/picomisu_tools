"""Execute the actual aw210xx power sequencing, hwen node, probe and remove bodies under ASan/UBSan."""
from pathlib import Path
import hashlib,importlib.util,json,subprocess
BASE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro');SOURCE=BASE/'source/phoenix-kernel-recovery'
DRV='drivers/i2c/aw210xx_driver/leds_aw210xx.c';HDR='drivers/i2c/aw210xx_driver/leds_aw210xx.h'
STRUCTS=[(HDR,'typedef enum {\n\tCLK_FRQ_16M'),(HDR,'typedef enum {\n\tBR_RESOLUTION_8BIT'),(HDR,'struct aw210xx {')]
FUNCS=[(DRV,'static int aw210xx_power_gpio_get('),(DRV,'static void aw210xx_power_gpio_put('),(DRV,'static void aw210xx_power_up_locked('),
       (DRV,'static void aw210xx_power_up('),(DRV,'static void aw210xx_power_down_2step_1('),(DRV,'static void aw210xx_power_down_2step_2('),
       (DRV,'static ssize_t aw210xx_hwen_store('),(DRV,'static ssize_t aw210xx_hwen_show('),
       (DRV,'static int aw210xx_parse_led_cdev('),(DRV,'static int aw210xx_parse_dt('),
       (DRV,'static int aw210xx_i2c_probe('),(DRV,'static int aw210xx_i2c_remove(')]
MODEL=r'''
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/types.h>
typedef uint8_t u8;typedef uint32_t u32;
#define PAGE_SIZE 4096
#define EINVAL 22
#define EIO 5
#define ENOMEM 12
#define EBUSY 16
#define GFP_KERNEL 0
#define GPIOF_OUT_INIT_LOW 0
#define I2C_FUNC_I2C 1
#define container_of(p,t,m) ((t *)((char *)(p)-offsetof(t,m)))
static int logs;
#define AW_LOG(...) ((void)0)
#define AW_ERR(...) (logs++)
#define dev_err(...) (logs++)
/* mutex model */
struct mutex {int held,inited;};
static void mutex_init(struct mutex *m){m->held=0;m->inited=1;}
static void mutex_lock(struct mutex *m){assert(m->inited&&!m->held);m->held=1;}
static void mutex_unlock(struct mutex *m){assert(m->held);m->held=0;}
static struct mutex *gpio_lock;
/* gpio model: owner 0 free, 1 driver, 2 foreign */
#define NGPIO 128
static int owner[NGPIO],level[NGPIO],requests,frees;static char label[NGPIO][32];
struct gpio_desc {int n;};static struct gpio_desc descs[NGPIO];
static bool gpio_is_valid(int n){return n>=0&&n<1280;}
static int gpio_request_one(unsigned g,unsigned long f,const char *l){assert(g<NGPIO&&f==GPIOF_OUT_INIT_LOW);if(gpio_lock)assert(gpio_lock->held);
  if(owner[g])return -EBUSY;owner[g]=1;level[g]=0;snprintf(label[g],32,"%s",l);requests++;return 0;}
static void gpio_free(unsigned g){assert(g<NGPIO&&owner[g]==1);if(gpio_lock)assert(gpio_lock->held);owner[g]=0;frees++;}
static void gpio_set_value_cansleep(unsigned g,int v){assert(g<NGPIO&&owner[g]==1);level[g]=v;}
static struct gpio_desc *gpio_to_desc(int n){return (n>=0&&n<NGPIO)?&descs[n]:NULL;}
static int gpiod_get_raw_value(const struct gpio_desc *d){return d?level[d->n]:0;}
static int slept;static void msleep(unsigned ms){slept+=ms;}
/* devices */
struct device_node {const char *name;struct device_node *child;int en,en18,osc,br,glo;int has_name;};
struct kobject {int x;};
struct device {void *drvdata;struct device_node *of_node;struct kobject kobj;};
struct i2c_adapter {int funcs;};
struct i2c_client {struct i2c_adapter *adapter;struct device dev;};
struct i2c_device_id {int x;};
struct work_struct {void (*func)(struct work_struct *);};
#define INIT_WORK(w,f) ((w)->func=(f))
enum led_brightness {LED_OFF=0};
struct led_classdev {const char *name;enum led_brightness brightness;enum led_brightness max_brightness;
  void (*brightness_set)(struct led_classdev *,enum led_brightness);struct device *dev;};
'''
MODEL2=r'''
static int i2c_check_functionality(struct i2c_adapter *a,int f){return (a->funcs&f)!=0;}
static void i2c_set_clientdata(struct i2c_client *c,void *d){c->dev.drvdata=d;}
static void *i2c_get_clientdata(struct i2c_client *c){return c->dev.drvdata;}
static void dev_set_drvdata(struct device *d,void *p){d->drvdata=p;}
static void *dev_get_drvdata(struct device *d){return d->drvdata;}
static int nalloc;
static void *devm_kzalloc(struct device *d,size_t n,int g){(void)d;(void)g;nalloc++;return calloc(1,n);}
static void devm_kfree(struct device *d,void *p){(void)d;nalloc--;free(p);}
static int of_get_named_gpio(struct device_node *np,const char *p,int i){(void)i;return !strcmp(p,"enable-gpio")?np->en:!strcmp(p,"enable-gpio-1V8")?np->en18:-EINVAL;}
static int of_property_read_u32(struct device_node *np,const char *p,void *out){u32 v;
  if(!strcmp(p,"osc_clk"))v=np->osc;else if(!strcmp(p,"br_res"))v=np->br;else if(!strcmp(p,"global_current"))v=np->glo;
  else if(!strcmp(p,"aw210xx,imax"))v=12;else if(!strcmp(p,"aw210xx,brightness"))v=0;else if(!strcmp(p,"aw210xx,max_brightness"))v=255;else return -EINVAL;
  if((int)v<0)return -EINVAL;memcpy(out,&v,4);return 0;}
static int of_property_read_string(struct device_node *np,const char *p,const char **out){(void)p;if(!np->has_name)return -EINVAL;*out=np->name;return 0;}
#define for_each_child_of_node(P_,C_) for(C_=(P_)->child;C_;C_=NULL)
static int reg_rc,reg_calls,unreg_calls,group_calls,group_rm_calls,powered_at_register;static struct device ledd;
static int led_classdev_register(struct device *p,struct led_classdev *c){(void)p;reg_calls++;
  powered_at_register=level[55]&&level[58];if(reg_rc)return reg_rc;c->dev=&ledd;ledd.drvdata=c;return 0;}
static void led_classdev_unregister(struct led_classdev *c){assert(c->dev);unreg_calls++;c->dev=NULL;}
struct attribute_group {int x;};static struct attribute_group aw210xx_attribute_group;
static int sysfs_create_group(struct kobject *k,const struct attribute_group *g){(void)k;(void)g;group_calls++;return 0;}
static void sysfs_remove_group(struct kobject *k,const struct attribute_group *g){(void)k;(void)g;group_rm_calls++;}
static void aw210xx_brightness_work(struct work_struct *w){(void)w;}
static void aw210xx_set_brightness(struct led_classdev *c,enum led_brightness b){(void)c;(void)b;}
'''
MAIN=r'''
struct device_attribute {int x;};
static struct device_node child={"aw210xx_led",NULL,0,0,0,0,0,1};
static struct device_node node={"aw",&child,55,58,0,0,0x66,1};
static struct i2c_adapter adap={I2C_FUNC_I2C};
static struct i2c_client cl;
static ssize_t hwen(struct device *d,const char *s){return aw210xx_hwen_store(d,NULL,s,strlen(s));}
static const char *show(struct device *d){static char b[PAGE_SIZE];aw210xx_hwen_show(d,NULL,b);return b;}
static void reset(void){memset(owner,0,sizeof(owner));memset(level,0,sizeof(level));requests=frees=0;slept=0;reg_rc=0;reg_calls=unreg_calls=0;
  group_calls=group_rm_calls=0;memset(&cl,0,sizeof(cl));cl.adapter=&adap;cl.dev.of_node=&node;gpio_lock=NULL;}
int main(void){
 for(int i=0;i<NGPIO;i++)descs[i].n=i;
 /* --- probe: chip powered while the class device registers, released afterwards --- */
 reset();assert(!aw210xx_i2c_probe(&cl,NULL));struct aw210xx *aw=i2c_get_clientdata(&cl);
 assert(aw&&powered_at_register&&reg_calls==1&&group_calls==1&&slept==1);
 assert(requests==2&&frees==2&&!owner[55]&&!owner[58]&&!level[55]&&!level[58]&&!aw->en_requested&&!aw->i2c_1v8_requested);
 assert(!strcmp(label[55],"aw210xx_en")&&!strcmp(label[58],"aw210xx_I2C_1V8")&&aw->glo_current==0x66);
 gpio_lock=&aw->power_lock;
 struct device *ld=&ledd;assert(ledd.drvdata==&aw->cdev&&aw->cdev.dev==&ledd);
 assert(!strcmp(show(ld),"gpio55=0,gpio58=0\n"));
 /* --- hwen steps --- */
 assert(hwen(ld,"1\n")==2&&owner[55]==1&&owner[58]==1&&level[55]==1&&level[58]==1&&slept==2);
 assert(!strcmp(show(ld),"gpio55=1,gpio58=1\n"));
 int rq=requests,lg=logs;assert(hwen(ld,"1")==1&&requests==rq&&level[55]&&level[58]&&logs==lg); /* idempotent: no re-request, no glitch */
 assert(hwen(ld,"2")==1&&!owner[58]&&!level[58]&&owner[55]==1&&level[55]==1);assert(!strcmp(show(ld),"gpio55=1,gpio58=0\n"));
 int fr=frees;assert(hwen(ld,"2")==1&&frees==fr); /* no double free */
 assert(hwen(ld,"3")==1&&!owner[55]&&!level[55]&&frees==fr+1);assert(hwen(ld,"3")==1&&frees==fr+1);
 assert(!strcmp(show(ld),"gpio55=0,gpio58=0\n"));
 /* hex parsing like the factory sscanf("%x"), other values ignored, garbage rejected */
 assert(hwen(ld,"0x1")==3&&owner[55]&&owner[58]);assert(hwen(ld,"3")==1&&hwen(ld,"2")==1&&!owner[55]&&!owner[58]);
 rq=requests;fr=frees;assert(hwen(ld,"a")==1&&hwen(ld,"0")==1&&hwen(ld,"4")==1&&hwen(ld,"10")==2&&requests==rq&&frees==fr);
 assert(hwen(ld,"zz")==-EINVAL&&hwen(ld,"")==-EINVAL&&requests==rq);
 /* --- a foreign owner of the 1V8 line is never freed --- */
 owner[58]=2;assert(hwen(ld,"1")==1&&owner[55]==1&&!level[55]&&owner[58]==2&&logs);
 assert(hwen(ld,"2")==1&&owner[58]==2);assert(hwen(ld,"3")==1&&!owner[55]&&owner[58]==2);owner[58]=0;
 /* foreign owner of the enable: nothing else is touched */
 owner[55]=2;assert(hwen(ld,"1")==1&&owner[55]==2&&!owner[58]&&!level[58]);assert(hwen(ld,"3")==1&&hwen(ld,"2")==1&&owner[55]==2);owner[55]=0;
 /* --- remove releases what hwen left requested --- */
 assert(hwen(ld,"1")==1&&owner[55]&&owner[58]);
 assert(!aw210xx_i2c_remove(&cl)&&!owner[55]&&!owner[58]&&unreg_calls==1&&group_rm_calls==1&&nalloc==0);gpio_lock=NULL;
 /* --- probe failures --- */
 reset();reg_rc=-ENOMEM;assert(aw210xx_i2c_probe(&cl,NULL)==-ENOMEM&&!owner[55]&&!owner[58]&&nalloc==0&&requests==2&&frees==2);
 reset();node.en=-2;assert(aw210xx_i2c_probe(&cl,NULL)==-EINVAL&&requests==0&&nalloc==0);node.en=55;
 reset();child.has_name=0;assert(aw210xx_i2c_probe(&cl,NULL)<0&&reg_calls==0&&!owner[55]&&!owner[58]&&nalloc==0);child.has_name=1;
 reset();adap.funcs=0;assert(aw210xx_i2c_probe(&cl,NULL)==-EIO&&nalloc==0);adap.funcs=I2C_FUNC_I2C;
 /* invalid 1V8 line: only the enable is driven */
 reset();node.en18=-2;assert(!aw210xx_i2c_probe(&cl,NULL));aw=i2c_get_clientdata(&cl);gpio_lock=&aw->power_lock;
 assert(hwen(ld,"1")==1&&owner[55]&&level[55]&&!owner[58]);assert(!strcmp(show(ld),"gpio55=1,gpio58=0\n"));
 assert(hwen(ld,"2")==1&&owner[55]);assert(hwen(ld,"3")==1&&!owner[55]);assert(!aw210xx_i2c_remove(&cl)&&nalloc==0);gpio_lock=NULL;node.en18=58;
 puts("PASS: probe powers the chip around class device registration and releases both lines; hwen 1/2/3 steps, idempotent, "
      "no double free, hex parsing, garbage -EINVAL; foreign gpio owner untouched; remove releases leftovers; probe failures "
      "(led registration, DT, missing child props, i2c) leave nothing requested or allocated; invalid 1V8 line; show format");
 return 0;
}
'''
def main():
    spec=importlib.util.spec_from_file_location('ex',Path(__file__).with_name('test-pico-sensor-mono-hook.py'));ex=importlib.util.module_from_spec(spec);spec.loader.exec_module(ex)
    srcs={n:(SOURCE/n).read_text() for n in (DRV,HDR)}
    structs=[]
    for f,s in STRUCTS:
        body=ex.function(srcs[f],s);end=srcs[f].index(body)+len(body);tail=srcs[f][end:srcs[f].index(';',end)+1]
        structs.append(body+tail)
    code=MODEL+'\n'.join(structs)+'\n'+MODEL2+'\n'.join(ex.function(srcs[f],s) for f,s in FUNCS)+'\n'+MAIN
    out=BASE/'out/phoenix-kernel-recovery/aw210xx-power-steps-tests';out.mkdir(exist_ok=True);(out/'harness.c').write_text(code)
    subprocess.run(['gcc','-std=gnu11','-g','-O1','-Wall','-Wno-unused-function','-Wno-unused-variable','-fsanitize=address,undefined','-fno-sanitize-recover=all',str(out/'harness.c'),'-o',str(out/'test')],check=True)
    r=subprocess.run([str(out/'test')],capture_output=True,text=True,timeout=60)
    report={'sources':{n:hashlib.sha256((SOURCE/n).read_bytes()).hexdigest() for n in sorted(srcs)},'harness_sha256':hashlib.sha256(code.encode()).hexdigest(),
            'exit_code':r.returncode,'stdout':r.stdout,'stderr':r.stderr[-3000:],
            'scope':'Actual aw210xx power helpers, power_up/power_down_2step_1/2, hwen store/show, parse_dt, parse_led_cdev, i2c probe and '
                    'remove with the real struct aw210xx. GPIO model rejects double requests/frees, frees of foreign owners and gpio calls '
                    'outside power_lock; DT, LED class, sysfs and devm modeled with allocation accounting.','device_modified':False}
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));raise SystemExit(r.returncode)
if __name__=='__main__':main()
