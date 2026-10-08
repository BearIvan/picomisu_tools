"""Execute the actual acc_ctrlrequest_composite, acc_ctrlrequest_configfs, acc_ctrlrequest and android_setup bodies under ASan/UBSan."""
from pathlib import Path
import hashlib,importlib.util,json,subprocess
BASE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro');SOURCE=BASE/'source/phoenix-kernel-recovery'
ACC='drivers/usb/gadget/function/f_accessory.c';CFS='drivers/usb/gadget/configfs.c'
FUNCS=[(ACC,'static void acc_complete_setup_noop('),(ACC,'static void acc_complete_set_string('),
       (ACC,'int acc_ctrlrequest('),(ACC,'int acc_ctrlrequest_composite('),(ACC,'int acc_ctrlrequest_configfs('),
       (CFS,'static int android_setup(')]
MODEL=r'''
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef uint8_t u8;typedef uint16_t u16;typedef uint32_t u32;typedef uint16_t __le16;
#define le16_to_cpu(x) ((u16)(x))
#define cpu_to_le16(x) ((__le16)(x))
#define container_of(p,t,m) ((t *)((char *)(p)-offsetof(t,m)))
#define EOPNOTSUPP 95
#define EINVAL 22
#define ENODEV 19
#define GFP_ATOMIC 0
#define USB_DIR_OUT 0
#define USB_DIR_IN 0x80
#define USB_TYPE_VENDOR (0x02 << 5)
#define USB_REQ_SET_CONFIGURATION 0x09
#define USB_COMP_EP0_BUFSIZ 4096
#define ACC_STRING_SIZE 256
#define ACCESSORY_STRING_MANUFACTURER 0
#define ACCESSORY_STRING_MODEL 1
#define ACCESSORY_STRING_DESCRIPTION 2
#define ACCESSORY_STRING_VERSION 3
#define ACCESSORY_STRING_URI 4
#define ACCESSORY_STRING_SERIAL 5
#define ACCESSORY_GET_PROTOCOL 51
#define ACCESSORY_SEND_STRING 52
#define ACCESSORY_START 53
#define ACCESSORY_REGISTER_HID 54
#define ACCESSORY_UNREGISTER_HID 55
#define ACCESSORY_SET_HID_REPORT_DESC 56
#define ACCESSORY_SEND_HID_EVENT 57
#define ACCESSORY_SET_AUDIO_MODE 58
#define PROTOCOL_VERSION 2
#define CONFIG_USB_F_NCM 1
#define CONFIG_USB_CONFIGFS_F_ACC 1
static int errors;
#define pr_err(...) (errors++)
#define ERROR(c,...) (errors++)
#define VDBG(...) ((void)0)
#define msecs_to_jiffies(x) (x)
struct usb_ctrlrequest {u8 bRequestType;u8 bRequest;__le16 wValue;__le16 wIndex;__le16 wLength;} __attribute__((packed));
/* spinlocks: no recursion, balanced */
typedef struct {int held;} spinlock_t;
static void spin_lock_irqsave_(spinlock_t *l){assert(!l->held);l->held=1;}
static void spin_unlock_irqrestore_(spinlock_t *l){assert(l->held);l->held=0;}
#define spin_lock_irqsave(l,f) do{(f)=0;spin_lock_irqsave_(l);}while(0)
#define spin_unlock_irqrestore(l,f) do{(void)(f);spin_unlock_irqrestore_(l);}while(0)
struct list_head {struct list_head *next,*prev;};
#define list_for_each_entry(pos,head,member) for(pos=container_of((head)->next,__typeof__(*pos),member);&pos->member!=(head);pos=container_of(pos->member.next,__typeof__(*pos),member))
struct work_struct {int queued;};
struct delayed_work {struct work_struct work;};
static int scheduled_delayed,scheduled_work;
static void schedule_delayed_work(struct delayed_work *w,unsigned long d){(void)d;w->work.queued=1;scheduled_delayed++;}
static void schedule_work(struct work_struct *w){w->queued=1;scheduled_work++;}
/* ep0 model: 4096 byte request buffer; an OUT data stage writes w_length host bytes into req->buf */
struct usb_ep;struct usb_request;
struct usb_request {void *buf;unsigned length;unsigned actual;int status;unsigned zero;void *context;void (*complete)(struct usb_ep *,struct usb_request *);};
struct usb_ep {void *driver_data;};
struct usb_gadget {struct usb_ep *ep0;void *data;};
struct usb_composite_dev {struct usb_gadget *gadget;struct usb_request *req;void *config;spinlock_t lock;};
static int queued,queue_rc,out_stage;static unsigned last_len;
static int usb_ep_queue(struct usb_ep *ep,struct usb_request *req,int gfp){(void)gfp;queued++;last_len=req->length;
  if(queue_rc)return queue_rc;
  if(out_stage){memset(req->buf,'H',req->length);req->actual=req->length;req->status=0;req->complete(ep,req);} /* host data stage */
  return 0;}
struct acc_hid_dev {int id;int report_desc_len;int report_desc_offset;};
struct acc_dev {spinlock_t lock;char manufacturer[ACC_STRING_SIZE];char model[ACC_STRING_SIZE];char description[ACC_STRING_SIZE];
  char version[ACC_STRING_SIZE];char uri[ACC_STRING_SIZE];char serial[ACC_STRING_SIZE];int string_index;int start_requested;int audio_mode;
  struct delayed_work start_work;struct list_head hid_list,new_hid_list;};
static struct acc_dev *_acc_dev;
static int acc_register_hid(struct acc_dev *d,int id,int len){(void)d;(void)id;(void)len;return 0;}
static int acc_unregister_hid(struct acc_dev *d,int id){(void)d;(void)id;return 0;}
static struct acc_hid_dev *acc_hid_get(struct list_head *l,int id){(void)l;(void)id;return NULL;}
static void acc_complete_set_hid_report_desc(struct usb_ep *e,struct usb_request *r){(void)e;(void)r;}
static void acc_complete_send_hid_event(struct usb_ep *e,struct usb_request *r){(void)e;(void)r;}
/* configfs side */
struct usb_configuration {struct usb_composite_dev *cdev;};
struct usb_function {struct usb_configuration *config;int (*setup)(struct usb_function *,const struct usb_ctrlrequest *);};
struct usb_function_instance {struct usb_function *f;struct list_head cfs_list;};
struct gadget_info {int pad;struct list_head available_func;struct usb_composite_dev cdev;bool connected;struct work_struct work;};
static void *get_gadget_data(struct usb_gadget *g){return g->data;}
static int ncm_calls,ncm_rc=-EOPNOTSUPP,comp_calls,comp_rc=-EOPNOTSUPP;
static int ncm_ctrlrequest(struct usb_composite_dev *c,const struct usb_ctrlrequest *r){(void)c;(void)r;ncm_calls++;return ncm_rc;}
static int composite_setup(struct usb_gadget *g,const struct usb_ctrlrequest *r){(void)g;(void)r;comp_calls++;return comp_rc;}
'''
MAIN=r'''
static struct usb_ep ep0;static struct usb_request req;static struct usb_gadget gadget={&ep0,NULL};
static struct gadget_info gi;static struct acc_dev dev;
static void reset(void){queued=queue_rc=out_stage=0;last_len=0;ncm_calls=comp_calls=0;errors=0;scheduled_delayed=scheduled_work=0;
  free(req.buf);memset(&req,0,sizeof(req));req.buf=malloc(USB_COMP_EP0_BUFSIZ);ep0.driver_data=NULL;
  memset(&dev,0,sizeof(dev));_acc_dev=&dev;}
static struct usb_ctrlrequest R(u8 type,u8 rq,u16 val,u16 idx,u16 len){struct usb_ctrlrequest c={type,rq,val,idx,len};return c;}
int main(void){
 gi.cdev.gadget=&gadget;gi.cdev.req=&req;gadget.data=&gi.cdev;gi.available_func.next=gi.available_func.prev=&gi.available_func;
 struct usb_composite_dev *cdev=&gi.cdev;struct usb_ctrlrequest c;
 /* --- composite guard: boundary --- */
 reset();out_stage=1;dev.string_index=ACCESSORY_STRING_SERIAL;c=R(USB_DIR_OUT|USB_TYPE_VENDOR,ACCESSORY_SEND_STRING,0,ACCESSORY_STRING_SERIAL,USB_COMP_EP0_BUFSIZ);
 assert(acc_ctrlrequest_composite(cdev,&c)==0&&queued==1&&last_len==4096&&c.wLength==4096);
 assert(strlen(dev.serial)==ACC_STRING_SIZE-1&&dev.serial[0]=='H');
 /* OUT above the ep0 buffer: refused before acc_ctrlrequest, wLength untouched */
 reset();out_stage=1;c=R(USB_DIR_OUT|USB_TYPE_VENDOR,ACCESSORY_SEND_STRING,0,0,4097);
 assert(acc_ctrlrequest_composite(cdev,&c)==-EINVAL&&queued==0&&c.wLength==4097&&dev.manufacturer[0]==0);
 c=R(USB_DIR_OUT|USB_TYPE_VENDOR,ACCESSORY_SEND_STRING,0,0,0xffff);assert(acc_ctrlrequest_composite(cdev,&c)==-EINVAL&&!queued);
 /* IN above the buffer: clamped in place, then handled */
 reset();c=R(USB_DIR_IN|USB_TYPE_VENDOR,ACCESSORY_GET_PROTOCOL,0,0,0xffff);
 assert(acc_ctrlrequest_composite(cdev,&c)==0&&c.wLength==4096&&queued==1&&last_len==2&&*(u16 *)req.buf==PROTOCOL_VERSION);
 reset();c=R(USB_DIR_IN|USB_TYPE_VENDOR,ACCESSORY_GET_PROTOCOL,0,0,4097);assert(acc_ctrlrequest_composite(cdev,&c)==0&&c.wLength==4096);
 /* small requests untouched */
 reset();c=R(USB_DIR_IN|USB_TYPE_VENDOR,ACCESSORY_GET_PROTOCOL,0,0,2);assert(acc_ctrlrequest_composite(cdev,&c)==0&&c.wLength==2);
 reset();c=R(USB_DIR_OUT|USB_TYPE_VENDOR,ACCESSORY_START,0,0,0);assert(acc_ctrlrequest_composite(cdev,&c)==0&&scheduled_delayed==1&&dev.start_requested==1);
 /* error code of acc_ctrlrequest is passed through */
 reset();_acc_dev=NULL;c=R(USB_DIR_OUT|USB_TYPE_VENDOR,ACCESSORY_START,0,0,0);assert(acc_ctrlrequest_composite(cdev,&c)==-ENODEV);
 reset();c=R(USB_DIR_IN|USB_TYPE_VENDOR,0x77,0,0,8);assert(acc_ctrlrequest_composite(cdev,&c)==-EOPNOTSUPP&&!queued);
 /* --- configfs per-function setup path uses the same guard --- */
 {struct usb_configuration cfg={cdev};struct usb_function f={&cfg,acc_ctrlrequest_configfs};
  reset();out_stage=1;c=R(USB_DIR_OUT|USB_TYPE_VENDOR,ACCESSORY_SEND_STRING,0,0,8000);assert(acc_ctrlrequest_configfs(&f,&c)==-EINVAL&&!queued);
  reset();out_stage=1;c=R(USB_DIR_OUT|USB_TYPE_VENDOR,ACCESSORY_SEND_STRING,0,ACCESSORY_STRING_URI,10);dev.string_index=ACCESSORY_STRING_URI;
  assert(acc_ctrlrequest_configfs(&f,&c)==10-10&&queued==1&&strlen(dev.uri)==10);
  struct usb_configuration nocdev={NULL};f.config=&nocdev;assert(acc_ctrlrequest_configfs(&f,&c)==-1);f.config=NULL;assert(acc_ctrlrequest_configfs(&f,&c)==-1);
  /* --- android_setup: the accessory request with an oversized OUT stage never reaches the ep0 buffer --- */
  reset();out_stage=1;gi.connected=0;c=R(USB_DIR_OUT|USB_TYPE_VENDOR,ACCESSORY_SEND_STRING,0,0,8000);
  assert(android_setup(&gadget,&c)==-EOPNOTSUPP&&!queued&&ncm_calls==1&&comp_calls==1&&gi.connected&&scheduled_work==1);
  assert(!gi.cdev.lock.held);
  /* a regular accessory request is answered by acc and not by composite_setup */
  reset();out_stage=1;dev.string_index=ACCESSORY_STRING_MODEL;c=R(USB_DIR_OUT|USB_TYPE_VENDOR,ACCESSORY_SEND_STRING,0,ACCESSORY_STRING_MODEL,5);
  assert(android_setup(&gadget,&c)==0&&queued==1&&comp_calls==0&&!strcmp(dev.model,"HHHHH"));
  /* IN oversize via android_setup: clamped */
  reset();c=R(USB_DIR_IN|USB_TYPE_VENDOR,ACCESSORY_GET_PROTOCOL,0,0,0x8000);assert(android_setup(&gadget,&c)==0&&c.wLength==4096&&!comp_calls);
  /* a bound function's setup (acc_ctrlrequest_configfs) in available_func is guarded too */
  struct usb_configuration cfg2={cdev};struct usb_function f2={&cfg2,acc_ctrlrequest_configfs};struct usb_function_instance fi={&f2};
  gi.available_func.next=gi.available_func.prev=&fi.cfs_list;fi.cfs_list.next=fi.cfs_list.prev=&gi.available_func;
  reset();out_stage=1;c=R(USB_DIR_OUT|USB_TYPE_VENDOR,ACCESSORY_SEND_STRING,0,0,0x9000);
  assert(android_setup(&gadget,&c)==-EOPNOTSUPP&&!queued&&comp_calls==1);
  reset();out_stage=1;dev.string_index=ACCESSORY_STRING_VERSION;c=R(USB_DIR_OUT|USB_TYPE_VENDOR,ACCESSORY_SEND_STRING,0,ACCESSORY_STRING_VERSION,3);
  assert(android_setup(&gadget,&c)==0&&queued==1&&ncm_calls==0&&comp_calls==0&&!strcmp(dev.version,"HHH"));
  /* SET_CONFIGURATION with a config schedules the uevent work */
  gi.available_func.next=gi.available_func.prev=&gi.available_func;
  reset();comp_rc=0;gi.cdev.config=&cfg;c=R(0,USB_REQ_SET_CONFIGURATION,1,0,0);assert(android_setup(&gadget,&c)==0&&scheduled_work==1);comp_rc=-EOPNOTSUPP;
 }
 free(req.buf);
 puts("PASS: wLength boundary 4096 passes, OUT >4096 refused before the ep0 data stage, IN >4096 clamped in place, error passthrough; "
      "configfs per-function path and android_setup use the guard (no heap overflow of the 4096-byte ep0 buffer under ASan), "
      "fallthrough to composite_setup, uevent scheduling kept");
 return 0;
}
'''
def main():
    spec=importlib.util.spec_from_file_location('ex',Path(__file__).with_name('test-pico-sensor-mono-hook.py'));ex=importlib.util.module_from_spec(spec);spec.loader.exec_module(ex)
    srcs={n:(SOURCE/n).read_text() for n in {f for f,_ in FUNCS}}
    code=MODEL+'\n'.join(ex.function(srcs[f],s) for f,s in FUNCS)+'\n'+MAIN
    out=BASE/'out/phoenix-kernel-recovery/acc-composite-guard-tests';out.mkdir(exist_ok=True);(out/'harness.c').write_text(code)
    subprocess.run(['gcc','-std=gnu11','-g','-O1','-Wall','-Wno-unused-function','-Wno-unused-variable','-Wno-address-of-packed-member','-fsanitize=address,undefined','-fno-sanitize-recover=all',str(out/'harness.c'),'-o',str(out/'test')],check=True)
    r=subprocess.run([str(out/'test')],capture_output=True,text=True,timeout=60)
    report={'sources':{n:hashlib.sha256((SOURCE/n).read_bytes()).hexdigest() for n in sorted(srcs)},'harness_sha256':hashlib.sha256(code.encode()).hexdigest(),
            'exit_code':r.returncode,'stdout':r.stdout,'stderr':r.stderr[-3000:],
            'scope':'Actual acc_ctrlrequest_composite, acc_ctrlrequest_configfs, acc_ctrlrequest, acc_complete_set_string and android_setup. '
                    'The ep0 request buffer is a 4096-byte heap block and the modeled UDC performs the OUT data stage (w_length host bytes) '
                    'into it, so a missing guard is an ASan heap overflow. Locks must be balanced; NCM/composite_setup/acc HID helpers modeled.',
            'device_modified':False}
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));raise SystemExit(r.returncode)
if __name__=='__main__':main()
