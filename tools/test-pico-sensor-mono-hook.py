"""Test the actual recovered sensor probe and virtual-device helper bodies.

Mocks cover allocation/registration boundaries and unwind order, not device
binding, DT parsing, physical cameras, or camera-hub runtime.
"""
from pathlib import Path
import hashlib
import json
import subprocess

BASE = Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro')
SOURCE = BASE / 'source/phoenix-kernel-recovery'
SENSOR = 'techpack/camera/drivers/cam_sensor_module/cam_sensor/cam_sensor_dev.c'
MONO = 'techpack/camera/drivers/cam_core/pico_virtual_mono.c'

HARNESS = r'''
#include <assert.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
struct list { struct list *next, *prev; };
#define INIT_LIST_HEAD(l) ((l)->next=(l)->prev=(l))
#define GFP_KERNEL 0
#define MAX_PER_FRAME_ARRAY 32
#define CCI_MASTER 1
#define CAM_SENSOR_INIT 0
#define CAM_SENSOR 0
#define CAM_ERR(...) ((void)0)
struct device {void *of_node;};
struct platform_device {struct device dev;const char *name;int id;void *data;};
struct cam_hw_soc_info {struct platform_device *pdev;struct device *dev;const char *dev_name;unsigned index;};
struct i2c_settings_array {struct list list_head;};
struct settings {
 struct i2c_settings_array *per_frame;
 struct i2c_settings_array init_settings,config_settings,streamon_settings,streamoff_settings;
 struct i2c_settings_array poweron_reg_settings,poweroff_reg_settings,read_settings;
};
static void cam_sensor_publish_dev_info(void) {}
static void cam_sensor_establish_link(void) {}
static void cam_sensor_apply_request(void) {}
static void cam_sensor_flush_request(void) {}
struct cam_sensor_ctrl_t {
 struct cam_hw_soc_info soc_info;void *of_node;
 int is_probe_succeed,open_cnt,last_flush_req;
 struct platform_device *pdev;struct {int master_type;} io_master_info;
 struct settings i2c_data;int v4l2_dev_str;
 struct {int device_hdl,link_hdl;struct {void (*get_dev_info)(void),(*link_setup)(void),(*apply_req)(void),(*flush_req)(void);} ops;} bridge_intf;
 struct {struct {struct device *dev;} power_info;} *sensordata;
 int sensor_state;
};
static struct cam_sensor_ctrl_t *latest;
static struct platform_device *virtual_device;
static unsigned allocated,freed,unregister_calls,add_calls,put_calls;
static int fail_ctrl,fail_settings,fail_platform,parse_error,subdev_error,add_error;
static void *devm_kzalloc(struct device *dev,size_t n,int flags) {
 if(fail_ctrl) return 0;latest=calloc(1,n);assert(latest);allocated++;return latest;
}
static void devm_kfree(struct device *dev,void *p) {assert(p);free(p);latest=0;freed++;}
static void *kzalloc(size_t n,int flags) {
 if(fail_settings) return 0;void *p=calloc(1,n);assert(p);allocated++;return p;
}
static void kfree(void *p) {if(p){free(p);freed++;}}
static int cam_sensor_parse_dt(struct cam_sensor_ctrl_t *ctrl) {
 assert(ctrl==latest && ctrl->soc_info.dev==&ctrl->pdev->dev);
 ctrl->soc_info.index=5;static typeof(*ctrl->sensordata) data;
 ctrl->sensordata=&data;return parse_error;
}
static int cam_sensor_init_subdev_params(struct cam_sensor_ctrl_t *ctrl) {return subdev_error;}
static int cam_unregister_subdev(void *p) {assert(p==&latest->v4l2_dev_str);unregister_calls++;return 0;}
static void platform_set_drvdata(struct platform_device *dev,void *p) {dev->data=p;}
static struct platform_device *platform_device_alloc(const char *name,int id) {
 if(fail_platform) return 0;
 virtual_device=calloc(1,sizeof(*virtual_device));assert(virtual_device);allocated++;
 virtual_device->name=name;virtual_device->id=id;return virtual_device;
}
static int platform_device_add(struct platform_device *dev) {
 assert(!strcmp(dev->name,"cam_virtual_mono") && dev->id==5);
 assert(latest->i2c_data.per_frame && !latest->i2c_data.init_settings.list_head.next);
 add_calls++;return add_error;
}
static void platform_device_put(struct platform_device *dev) {assert(dev==virtual_device);put_calls++;free(dev);virtual_device=0;freed++;}
/* HELPER */
/* PROBE */
static void reset(void) {
 assert(allocated==freed);fail_ctrl=fail_settings=fail_platform=0;
 parse_error=subdev_error=add_error=0;unregister_calls=add_calls=put_calls=0;
}
int main(void) {
 struct platform_device dev={.name="qcom,camera",.id=-1};
 reset();fail_ctrl=1;assert(cam_sensor_driver_platform_probe(&dev)==-ENOMEM);
 reset();parse_error=-EINVAL;assert(cam_sensor_driver_platform_probe(&dev)==-EINVAL);
 assert(!unregister_calls && !add_calls);
 reset();subdev_error=-ENODEV;assert(cam_sensor_driver_platform_probe(&dev)==-ENODEV);
 assert(!unregister_calls && !add_calls);
 reset();fail_settings=1;assert(cam_sensor_driver_platform_probe(&dev)==-ENOMEM);
 assert(unregister_calls==1 && !add_calls);
 reset();fail_platform=1;assert(cam_sensor_driver_platform_probe(&dev)==-ENOMEM);
 assert(unregister_calls==1 && !add_calls);
 reset();add_error=-EEXIST;assert(cam_sensor_driver_platform_probe(&dev)==-EEXIST);
 assert(unregister_calls==1 && add_calls==1 && put_calls==1);
 reset();assert(!cam_sensor_driver_platform_probe(&dev));
 assert(dev.data==latest && dev.id==5 && add_calls==1 && !put_calls && !unregister_calls);
 assert(latest->sensor_state==CAM_SENSOR_INIT && latest->bridge_intf.device_hdl==-1);
 assert(latest->i2c_data.init_settings.list_head.next==&latest->i2c_data.init_settings.list_head);
 for(unsigned i=0;i<MAX_PER_FRAME_ARRAY;i++)
 assert(latest->i2c_data.per_frame[i].list_head.next==&latest->i2c_data.per_frame[i].list_head);
 assert(latest->sensordata->power_info.dev==&dev.dev);
 kfree(latest->i2c_data.per_frame);devm_kfree(&dev.dev,latest);platform_device_put(virtual_device);
 assert(allocated==freed);
 puts("PASS: sensor slot, early virtual peer creation, all failure unwinds, success initialization");
}
'''


def function(text, signature):
    start = text.index(signature)
    body = text.index('{', start)
    depth = 0
    for end in range(body, len(text)):
        if text[end] == '{':
            depth += 1
        elif text[end] == '}':
            depth -= 1
            if not depth:
                return text[start:end + 1]
    raise RuntimeError('Incomplete function')


def main():
    sensor = (SOURCE / SENSOR).read_text()
    mono = (SOURCE / MONO).read_text()
    code = HARNESS.replace('/* PROBE */', function(sensor, 'static int32_t cam_sensor_driver_platform_probe('))
    code = code.replace('/* HELPER */', function(mono, 'int cam_quick_register_virtual_device('))
    out = BASE / 'out/phoenix-kernel-recovery/sensor-mono-hook-tests'
    out.mkdir(exist_ok=True)
    (out / 'harness.c').write_text(code)
    subprocess.run(['gcc', '-std=gnu11', '-g', '-O1', '-fsanitize=address,undefined',
                    '-fno-omit-frame-pointer', str(out / 'harness.c'), '-o', str(out / 'test')], check=True)
    result = subprocess.run([str(out / 'test')], capture_output=True, text=True, timeout=30)
    report = {'sources': {SENSOR: hashlib.sha256(sensor.encode()).hexdigest(),
                          MONO: hashlib.sha256(mono.encode()).hexdigest()},
              'scope': 'Actual probe/helper bodies; mocked registration and allocation; no real device binding',
              'exit_code': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr,
              'sanitizers': ['AddressSanitizer', 'UndefinedBehaviorSanitizer'], 'device_modified': False}
    (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    if result.returncode:
        raise SystemExit(result.returncode)


if __name__ == '__main__':
    main()
