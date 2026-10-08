"""Execute native probes with immediate publication inspection/fault injection."""
from pathlib import Path
import hashlib,json,subprocess,importlib.util
spec=importlib.util.spec_from_file_location('ex',Path(__file__).with_name('test-pico-sensor-mono-hook.py'));ex=importlib.util.module_from_spec(spec);spec.loader.exec_module(ex)
BASE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro');SOURCE=BASE/'source/phoenix-kernel-recovery';N='techpack/camera/drivers/cam_sensor_module/cam_actuator/cam_actuator_dev.c'
MODEL=r'''
#include <assert.h>
#include <stdint.h>
#include <stddef.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
#define GFP_KERNEL 0
#define MAX_PER_FRAME_ARRAY 32
#define I2C_FUNC_I2C 1
#define I2C_MASTER 1
#define CCI_MASTER 0
#define CAM_ACTUATOR_INIT 0
#define CAM_ACTUATOR 0
#define CAM_ERR(...)
struct list_head {struct list_head *next,*prev;};
static void INIT_LIST_HEAD(struct list_head *p){p->next=p->prev=p;}
struct device {const char *name;};
struct platform_device {struct device dev;const char *name;int id;void *data;};
struct i2c_client {struct device dev;const char *name;void *adapter;int addr;void *data;};
struct i2c_device_id {int unused;};
struct cam_sensor_cci_client {int unused;};
struct cam_sensor_power_ctrl_t {struct device *dev;};
struct cam_actuator_soc_private {struct {int slave_addr;} i2c_info;struct cam_sensor_power_ctrl_t power_info;};
struct cam_hw_soc_info {void *soc_private;struct device *dev;const char *dev_name;struct platform_device *pdev;int index;};
struct i2c_settings_array {struct list_head list_head;};
struct cam_actuator_ctrl_t {struct cam_hw_soc_info soc_info;struct {struct i2c_client *client;struct cam_sensor_cci_client *cci_client;int master_type;} io_master_info;struct {struct i2c_settings_array *per_frame;struct i2c_settings_array init_settings;} i2c_data;struct {struct platform_device *pdev;} v4l2_dev_str;struct {int device_hdl,link_hdl;struct {void *get_dev_info,*link_setup,*apply_req,*flush_req;} ops;} bridge_intf;unsigned last_flush_req,open_cnt;int cam_act_state,mutex_ready;};
static int alloc_step,fail_step,live,fail_dt,fail_publish,publishes,unregisters;
static struct cam_actuator_ctrl_t *published;
static void *allocation(size_t size){alloc_step++;if(alloc_step==fail_step)return NULL;void *p=calloc(1,size);assert(p);live++;return p;}
static void deallocation(void *p){if(p){live--;free(p);}}
#define kzalloc(s,f) allocation(s)
#define kfree deallocation
#define devm_kzalloc(d,s,f) allocation(s)
#define devm_kfree(d,p) deallocation(p)
static void i2c_set_clientdata(struct i2c_client *c,void *p){c->data=p;}
static void platform_set_drvdata(struct platform_device *p,void *d){p->data=d;}
static int i2c_check_functionality(void *a,int f){return 1;}
static int cam_actuator_parse_dt(struct cam_actuator_ctrl_t *a,struct device *dev){a->mutex_ready=1;a->soc_info.index=7;return fail_dt?-EINVAL:0;}
static int cam_actuator_publish_dev_info,cam_actuator_establish_link,cam_actuator_apply_request,cam_actuator_flush_request;
static int cam_actuator_init_subdev(struct cam_actuator_ctrl_t *a){
 assert(a->mutex_ready&&a->i2c_data.per_frame);
 assert(a->bridge_intf.device_hdl==-1&&a->bridge_intf.link_hdl==-1);
 assert(a->bridge_intf.ops.get_dev_info&&a->bridge_intf.ops.link_setup&&a->bridge_intf.ops.apply_req);
 assert(!a->open_cnt&&!a->last_flush_req&&a->cam_act_state==CAM_ACTUATOR_INIT);
 assert(a->i2c_data.init_settings.list_head.next==&a->i2c_data.init_settings.list_head);
 for(int i=0;i<MAX_PER_FRAME_ARRAY;i++)assert(a->i2c_data.per_frame[i].list_head.next==&a->i2c_data.per_frame[i].list_head);
 if(fail_publish)return -ENODEV;publishes++;published=a;return 0;
}
static int cam_unregister_subdev(void *sd){unregisters++;return 0;}
'''
MAIN=r'''
static void reset(void){assert(!live);alloc_step=0;fail_step=0;fail_dt=fail_publish=publishes=unregisters=0;published=NULL;}
static void cleanup(struct cam_actuator_ctrl_t *a){kfree(a->i2c_data.per_frame);kfree(a->soc_info.soc_private);kfree(a->io_master_info.cci_client);kfree(a);}
int main(void){
 struct i2c_client client={.dev={.name="i2c"},.name="i2c"};struct i2c_device_id id={0};struct platform_device platform={.dev={.name="platform"},.name="platform"};
 reset();assert(!cam_actuator_driver_i2c_probe(&client,&id)&&publishes==1&&client.data==published);cleanup(published);client.data=NULL;
 reset();assert(!cam_actuator_driver_platform_probe(&platform)&&publishes==1&&platform.data==published);cleanup(published);platform.data=NULL;
 for(int type=0;type<2;type++){
  for(int step=1;step<=(type?4:3);step++){reset();fail_step=step;int rc=type?cam_actuator_driver_platform_probe(&platform):cam_actuator_driver_i2c_probe(&client,&id);assert(rc==-ENOMEM&&!live&&!publishes&&!unregisters&&!client.data&&!platform.data);}
  reset();fail_dt=1;assert((type?cam_actuator_driver_platform_probe(&platform):cam_actuator_driver_i2c_probe(&client,&id))==-EINVAL&&!live&&!publishes&&!unregisters&&!client.data&&!platform.data);
  reset();fail_publish=1;assert((type?cam_actuator_driver_platform_probe(&platform):cam_actuator_driver_i2c_probe(&client,&id))==-ENODEV&&!live&&!publishes&&!unregisters&&!client.data&&!platform.data);
 }
 puts("PASS: actual I2C/platform probes initialize mutex, request lists/frames, handles/state/callbacks before publication; allocation/DT/register failure drains owned allocations without publishing or stale driverdata");return 0;
}
'''
def main():
    dev=(SOURCE/N).read_text()
    # The harness models callbacks as stable addresses, not callback execution.
    bodies='\n'.join('static int32_t '+ex.function(dev,n) for n in ['cam_actuator_driver_i2c_probe','cam_actuator_driver_platform_probe'])
    for n in ['cam_actuator_publish_dev_info','cam_actuator_establish_link','cam_actuator_apply_request','cam_actuator_flush_request']:
        bodies=bodies.replace('=\n\t\t'+n+';','=\n\t\t&'+n+';')
    code=MODEL+bodies+MAIN;out=BASE/'out/phoenix-kernel-recovery/actuator-probe-publication-tests';out.mkdir(exist_ok=True);(out/'harness.c').write_text(code)
    subprocess.run(['gcc','-std=gnu11','-g','-O1','-fsanitize=address,undefined','-fno-sanitize-recover=all',str(out/'harness.c'),'-o',str(out/'test')],check=True)
    r=subprocess.run([str(out/'test')],capture_output=True,text=True,timeout=30)
    report={'sources':{N:hashlib.sha256((SOURCE/N).read_bytes()).hexdigest()},'harness_sha256':hashlib.sha256(code.encode()).hexdigest(),'exit_code':r.returncode,'stdout':r.stdout,'stderr':r.stderr,'scope':'Actual probe bodies; allocation/device/DT/V4L2 publication and callback addresses modeled, immediate publication inspection and fault injection; no DT internal resource cleanup or runtime/remove integration','device_modified':False}
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));raise SystemExit(r.returncode)
if __name__=='__main__':main()
