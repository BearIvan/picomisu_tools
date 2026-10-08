"""Execute the actual ISP buf-done, deferred-ack and RDI bubble SOF bodies under sanitizers."""
from pathlib import Path
import hashlib,importlib.util,json,subprocess
BASE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro');SOURCE=BASE/'source/phoenix-kernel-recovery'
NAME='techpack/camera/drivers/cam_isp/cam_isp_context.c'
FUNCS=['static int __cam_isp_ctx_handle_buf_done_for_req_list(','static int __cam_isp_ctx_handle_buf_done_for_request(',
       'static void __cam_isp_ctx_drop_deferred_ack(','static bool __cam_isp_ctx_ack_deferred(','static void __cam_isp_handle_deferred_buf_done(',
       'static int __cam_isp_ctx_handle_buf_done_for_request_verify_addr(','static int __cam_isp_ctx_handle_buf_done(',
       'static void __cam_isp_ctx_buf_done_match_req(','static int __cam_isp_ctx_handle_buf_done_verify_addr(',
       'static int __cam_isp_ctx_handle_buf_done_in_activated_state(','static int __cam_isp_ctx_buf_done_in_sof(',
       'static int __cam_isp_ctx_rdi_only_sof_in_bubble_state(']
MODEL=r'''
#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <stddef.h>
#include <errno.h>
#define CAM_ISP 0
#define CAM_REQ 1
static int warns,errs,warn_on;
#define CAM_DBG(...) do {} while (0)
#define CAM_INFO(...) do {} while (0)
#define CAM_WARN(...) (warns++)
#define CAM_ERR(...) (errs++)
#define WARN_ON(x) (warn_on += !!(x))
#define trace_cam_buf_done(...) do {} while (0)
#define trace_cam_log_event(...) do {} while (0)
#define CAM_ISP_CTX_RES_MAX 24
#define CAM_NUM_OUT_PER_COMP_IRQ_MAX 12
#define CAM_SYNC_STATE_SIGNALED_SUCCESS 2
#define CAM_SYNC_STATE_SIGNALED_ERROR 3
#define CAM_REQ_MGR_SOF_EVENT_SUCCESS 0
#define CAM_ISP_STATE_CHANGE_TRIGGER_DONE 5
#define CAM_ISP_CTX_EVENT_BUFDONE 4
#define CAM_HW_MGR_CMD_INTERNAL 1
#define CAM_ISP_HW_MGR_GET_LAST_CDM_DONE 6
#define CAM_TRIGGER_POINT_SOF 1
#define CAM_ISP_CTX_ACTIVATED_SOF 0
struct list_head {struct list_head *next,*prev;};
#define container_of(p,t,m) ((t *)((char *)(p)-offsetof(t,m)))
#define list_entry(p,t,m) container_of(p,t,m)
#define list_first_entry(h,t,m) list_entry((h)->next,t,m)
#define list_last_entry(h,t,m) list_entry((h)->prev,t,m)
#define list_for_each_entry(p,h,m) for(p=list_first_entry(h,__typeof__(*p),m);&p->m!=(h);p=list_entry(p->m.next,__typeof__(*p),m))
static void INIT_LIST_HEAD(struct list_head *h){h->next=h->prev=h;}
static int list_empty(const struct list_head *h){return h->next==h;}
static void __list_add(struct list_head *n,struct list_head *p,struct list_head *x){x->prev=n;n->next=x;n->prev=p;p->next=n;}
static void list_add(struct list_head *n,struct list_head *h){__list_add(n,h,h->next);}
static void list_add_tail(struct list_head *n,struct list_head *h){__list_add(n,h->prev,h);}
static void list_del_init(struct list_head *e){e->prev->next=e->next;e->next->prev=e->prev;INIT_LIST_HEAD(e);}
typedef struct {int counter;} atomic_t;
#define atomic_set(a,v) ((a)->counter=(v))
#define atomic_read(a) ((a)->counter)
struct cam_hw_fence_map_entry {uint32_t resource_handle;int32_t sync_id;int32_t image_buf_addr[3];};
struct cam_isp_prepare_hw_update_data {uint32_t frame_header_res_id;uint64_t frame_header_cpu_addr;};
struct cam_isp_ctx_req {void *base;struct cam_hw_fence_map_entry fence_map_out[CAM_ISP_CTX_RES_MAX];uint32_t num_fence_map_out;uint32_t num_acked;uint32_t num_deferred_acks;uint32_t deferred_fence_map_index[CAM_ISP_CTX_RES_MAX];int32_t bubble_report;struct cam_isp_prepare_hw_update_data hw_update_data;bool bubble_detected,reapply,cdm_reset_before_apply;};
struct cam_ctx_request {struct list_head list;uint64_t request_id;void *req_priv;};
struct cam_req_mgr_trigger_notify {int32_t link_hdl,dev_hdl;int64_t frame_id;uint32_t trigger;uint64_t req_id;uint64_t sof_timestamp_val;};
struct cam_req_mgr_crm_cb {int (*notify_trigger)(struct cam_req_mgr_trigger_notify *);};
struct cam_hw_cmd_args {void *ctxt_to_hw_map;uint32_t cmd_type;union {void *internal_args;} u;};
struct cam_isp_hw_cmd_args {uint32_t cmd_type;union {uint64_t last_cdm_done;} u;};
struct cam_hw_mgr_intf {void *hw_mgr_priv;int (*hw_cmd)(void *,void *);};
struct cam_context {struct list_head active_req_list,pending_req_list,wait_req_list,free_req_list;uint32_t ctx_id;int64_t last_flush_req;struct cam_req_mgr_crm_cb *ctx_crm_intf;struct cam_hw_mgr_intf *hw_mgr_intf;int32_t link_hdl,dev_hdl;};
struct cam_isp_context {struct cam_context *base;int64_t frame_id;uint32_t substate_activated;atomic_t process_bubble;uint32_t bubble_frame_cnt;void *hw_ctx;uint64_t sof_timestamp_val,boot_timestamp,last_sof_timestamp;int32_t active_req_cnt;int64_t reported_req_id;struct {int64_t last_bufdone_req_id;} req_info;bool use_frame_header_ts,support_consumed_addr;};
struct cam_isp_hw_done_event_data {uint32_t num_handles;uint32_t resource_handle[CAM_NUM_OUT_PER_COMP_IRQ_MAX];uint32_t last_consumed_addr[CAM_NUM_OUT_PER_COMP_IRQ_MAX];uint64_t timestamp;};
struct cam_isp_hw_sof_event_data {uint64_t timestamp,boot_time;};
/* Fences: each sync id may be signalled once. */
static int fence_state[256],signal_calls,double_signals,fail_signal_id=-1;
static int cam_sync_signal(int32_t id,uint32_t status){assert(id>=0&&id<256);signal_calls++;if(id==fail_signal_id)return -EINVAL;if(fence_state[id]){double_signals++;return -EALREADY;}fence_state[id]=status;return 0;}
static int sof_ts_sent,frame_header_sent,crm_notified;static uint64_t last_cdm_done;
static void __cam_isp_ctx_send_sof_timestamp(struct cam_isp_context *c,uint64_t id,uint32_t s){sof_ts_sent++;}
static void __cam_isp_ctx_send_sof_timestamp_frame_header(struct cam_isp_context *c,uint64_t addr,uint64_t id,uint32_t s){frame_header_sent++;}
static void __cam_isp_ctx_update_state_monitor_array(struct cam_isp_context *c,int t,uint64_t id){}
static void __cam_isp_ctx_update_event_record(struct cam_isp_context *c,int e,struct cam_ctx_request *r){}
static const char *__cam_isp_resource_handle_id_to_type(uint32_t id){return "res";}
static const char *__cam_isp_ctx_substate_val_to_type(uint32_t s){return "SOF";}
static int notify_trigger(struct cam_req_mgr_trigger_notify *n){crm_notified++;return 0;}
static int hw_cmd(void *p,void *a){struct cam_hw_cmd_args *h=a;struct cam_isp_hw_cmd_args *i=h->u.internal_args;assert(i->cmd_type==CAM_ISP_HW_MGR_GET_LAST_CDM_DONE);i->u.last_cdm_done=last_cdm_done;return 0;}
'''
MAIN=r'''
static struct cam_context ctx;static struct cam_isp_context isp;
static struct cam_req_mgr_crm_cb crm={notify_trigger};static struct cam_hw_mgr_intf hwm={0,hw_cmd};
static struct cam_ctx_request reqs[4];static struct cam_isp_ctx_req rp[4];
/* Request n uses fences 10n+k for resources 0x100+k with buffer addresses 0x1000*n+k. */
static void fixture(void){int n,k;memset(fence_state,0,sizeof(fence_state));signal_calls=double_signals=warns=errs=warn_on=sof_ts_sent=frame_header_sent=crm_notified=0;fail_signal_id=-1;
 memset(&ctx,0,sizeof(ctx));INIT_LIST_HEAD(&ctx.active_req_list);INIT_LIST_HEAD(&ctx.pending_req_list);INIT_LIST_HEAD(&ctx.wait_req_list);INIT_LIST_HEAD(&ctx.free_req_list);ctx.ctx_crm_intf=&crm;ctx.hw_mgr_intf=&hwm;ctx.last_flush_req=0;
 memset(&isp,0,sizeof(isp));isp.base=&ctx;isp.support_consumed_addr=true;
 for(n=0;n<4;n++){memset(&rp[n],0,sizeof(rp[n]));rp[n].num_fence_map_out=3;for(k=0;k<3;k++){rp[n].fence_map_out[k].resource_handle=0x100+k;rp[n].fence_map_out[k].sync_id=10*n+k;rp[n].fence_map_out[k].image_buf_addr[0]=0x1000*n+k;}
  memset(&reqs[n],0,sizeof(reqs[n]));reqs[n].request_id=n+1;reqs[n].req_priv=&rp[n];INIT_LIST_HEAD(&reqs[n].list);}}
static void activate(int n){list_add_tail(&reqs[n].list,&ctx.active_req_list);isp.active_req_cnt++;}
static struct cam_isp_hw_done_event_data done1(int k,uint32_t addr){struct cam_isp_hw_done_event_data d;memset(&d,0,sizeof(d));d.num_handles=1;d.resource_handle[0]=0x100+k;d.last_consumed_addr[0]=addr;return d;}
static int bufdone(int k,uint32_t addr,int bubble){struct cam_isp_hw_done_event_data d=done1(k,addr);return __cam_isp_ctx_handle_buf_done_in_activated_state(&isp,&d,bubble);}
static bool on(struct list_head *h,int n){struct cam_ctx_request *r;list_for_each_entry(r,h,list)if(r==&reqs[n])return true;return false;}
static void sof_bubble(void){struct cam_isp_hw_sof_event_data e={isp.last_sof_timestamp+1,0};assert(!__cam_isp_ctx_rdi_only_sof_in_bubble_state(&isp,&e));}
int main(void){int k;
 /* 1. Consumed-address path: complete request moves to free list, each fence signalled once. */
 fixture();activate(0);for(k=0;k<3;k++)assert(!bufdone(k,k,0));assert(on(&ctx.free_req_list,0)&&!isp.active_req_cnt&&isp.req_info.last_bufdone_req_id==1);
 for(k=0;k<3;k++)assert(fence_state[k]==CAM_SYNC_STATE_SIGNALED_SUCCESS);assert(!double_signals&&!warn_on);
 /* 2. Wrong consumed address is not matched to the request. */
 fixture();activate(0);assert(!bufdone(0,0x9999,0));assert(!fence_state[0]&&rp[0].num_acked==0);
 /* 3. IRQ delay: the consumed address already belongs to the next request, so the delayed
  *    current buffer is acked without address check and the next one with it. */
 fixture();activate(0);activate(1);assert(!bufdone(1,0x1001,0));assert(fence_state[11]==CAM_SYNC_STATE_SIGNALED_SUCCESS&&fence_state[1]==CAM_SYNC_STATE_SIGNALED_SUCCESS);
 assert(!bufdone(1,1,0));assert(!double_signals&&rp[0].num_acked==1&&rp[1].num_acked==1);
 /* 3b. Without a match in the next request the current one requires the exact address. */
 fixture();activate(0);activate(1);assert(!bufdone(1,0x5555,0));assert(!signal_calls);
 /* 4. Deferred: buf done for a request in wait list only records it; duplicates are not recorded twice. */
 fixture();list_add_tail(&reqs[0].list,&ctx.wait_req_list);assert(!bufdone(2,2,0));assert(rp[0].num_deferred_acks==1&&rp[0].deferred_fence_map_index[0]==2&&!signal_calls);
 assert(!bufdone(2,2,0));assert(rp[0].num_deferred_acks==1);
 /* ... once active, the next direct ack also signals the deferred fence. */
 list_del_init(&reqs[0].list);activate(0);assert(!bufdone(0,0,0));assert(fence_state[0]&&fence_state[2]&&rp[0].num_acked==2&&!rp[0].num_deferred_acks);
 assert(!bufdone(1,1,0));assert(on(&ctx.free_req_list,0)&&!double_signals&&!warn_on);
 /* 5. Deferred fence later reported directly is dropped from the deferred list (no double signal). */
 fixture();list_add_tail(&reqs[0].list,&ctx.pending_req_list);assert(!bufdone(0,0,0)&&rp[0].num_deferred_acks==1);
 list_del_init(&reqs[0].list);activate(0);assert(!bufdone(0,0,0));assert(fence_state[0]&&rp[0].num_acked==1&&!rp[0].num_deferred_acks);
 assert(!bufdone(1,1,0)&&!bufdone(2,2,0));assert(on(&ctx.free_req_list,0)&&!double_signals&&!warn_on);
 /* 6. Bubble with recovery: acks counted (deferred too), request returns to pending list, no fence signalled. */
 fixture();list_add_tail(&reqs[0].list,&ctx.wait_req_list);assert(!bufdone(2,2,1));list_del_init(&reqs[0].list);activate(0);rp[0].bubble_detected=true;rp[0].bubble_report=1;
 assert(!bufdone(0,0,1));assert(rp[0].num_acked==2&&!rp[0].num_deferred_acks);assert(!bufdone(1,1,1));
 assert(on(&ctx.pending_req_list,0)&&!rp[0].bubble_detected&&!rp[0].num_acked&&!signal_calls&&!isp.active_req_cnt);
 /* 7. Bubble without recovery: error signalled for direct and deferred fences. */
 fixture();list_add_tail(&reqs[0].list,&ctx.wait_req_list);assert(!bufdone(1,1,1));list_del_init(&reqs[0].list);activate(0);rp[0].bubble_detected=true;
 assert(!bufdone(0,0,1));assert(fence_state[0]==CAM_SYNC_STATE_SIGNALED_ERROR&&fence_state[1]==CAM_SYNC_STATE_SIGNALED_ERROR);
 /* 8. Legacy path without consumed address still hands unmatched handles to the next request. */
 fixture();isp.support_consumed_addr=false;activate(0);activate(1);rp[0].fence_map_out[2].resource_handle=0x200;
 assert(!bufdone(2,0,0));assert(fence_state[12]==CAM_SYNC_STATE_SIGNALED_SUCCESS);
 /* 9. RDI SOF substate handles late buf dones. */
 fixture();activate(0);{struct cam_isp_hw_done_event_data d=done1(0,0);assert(!__cam_isp_ctx_buf_done_in_sof(&isp,&d));}assert(fence_state[0]);
 /* 10. RDI bubble SOF walks past non-bubbled requests (public code looped forever here). */
 fixture();activate(0);activate(1);rp[1].bubble_detected=true;sof_bubble();assert(on(&ctx.active_req_list,0)&&on(&ctx.pending_req_list,1)&&isp.active_req_cnt==1&&crm_notified==1);
 fixture();activate(0);sof_bubble();assert(on(&ctx.active_req_list,0)&&crm_notified==1);
 /* 11. Bubble with CDM done and all buffers deferred: request retired through req_list. */
 fixture();activate(0);atomic_set(&isp.process_bubble,1);rp[0].bubble_detected=true;rp[0].bubble_report=1;rp[0].num_deferred_acks=3;for(k=0;k<3;k++)rp[0].deferred_fence_map_index[k]=k;
 last_cdm_done=5;sof_bubble();assert(on(&ctx.pending_req_list,0)&&!isp.active_req_cnt&&!rp[0].num_deferred_acks&&!signal_calls&&!atomic_read(&isp.process_bubble));
 /* 12. CDM not done: request re-applied with CDM reset. */
 fixture();activate(0);atomic_set(&isp.process_bubble,1);rp[0].bubble_detected=true;last_cdm_done=0;sof_bubble();assert(on(&ctx.pending_req_list,0)&&rp[0].cdm_reset_before_apply);
 /* 13. Flushed bubbled request goes to free list with error fences. */
 fixture();activate(0);rp[0].bubble_detected=true;rp[0].bubble_report=1;ctx.last_flush_req=1;for(k=0;k<3;k++)assert(!bufdone(k,k,1));
 assert(on(&ctx.free_req_list,0));for(k=0;k<3;k++)assert(fence_state[k]==CAM_SYNC_STATE_SIGNALED_ERROR);
 /* 14. Deferral capacity: never more deferred entries than fences. */
 fixture();rp[0].num_fence_map_out=CAM_ISP_CTX_RES_MAX;for(k=0;k<CAM_ISP_CTX_RES_MAX;k++){rp[0].fence_map_out[k].resource_handle=0x100;rp[0].fence_map_out[k].image_buf_addr[0]=7;rp[0].fence_map_out[k].sync_id=100+k;}
 list_add_tail(&reqs[0].list,&ctx.wait_req_list);for(k=0;k<3*CAM_ISP_CTX_RES_MAX;k++)bufdone(0,7,0);assert(rp[0].num_deferred_acks==1);
 puts("PASS: consumed-address matching, IRQ-delay routing, deferred acks (no double signal, bounded), bubble recovery/flush, RDI SOF late buf done and RDI bubble walk");
 return 0;
}
'''
def main():
    spec=importlib.util.spec_from_file_location('ex',Path(__file__).with_name('test-pico-sensor-mono-hook.py'));ex=importlib.util.module_from_spec(spec);spec.loader.exec_module(ex)
    src=(SOURCE/NAME).read_text()
    bodies='\n'.join(ex.function(src,f) for f in FUNCS)
    code=MODEL+bodies+MAIN
    out=BASE/'out/phoenix-kernel-recovery/isp-bufdone-tests';out.mkdir(exist_ok=True);(out/'harness.c').write_text(code)
    subprocess.run(['gcc','-std=gnu11','-g','-O1','-Wall','-Wno-unused-function','-fsanitize=address,undefined','-fno-sanitize-recover=all',str(out/'harness.c'),'-o',str(out/'test')],check=True)
    r=subprocess.run([str(out/'test')],capture_output=True,text=True,timeout=30)
    report={'sources':{NAME:hashlib.sha256((SOURCE/NAME).read_bytes()).hexdigest()},'harness_sha256':hashlib.sha256(code.encode()).hexdigest(),'exit_code':r.returncode,'stdout':r.stdout,'stderr':r.stderr,
            'scope':'Actual buf-done/deferred/consumed-address/RDI bubble SOF bodies from the patched ISP context; lists, fences, CRM/hw-mgr callbacks and context layout modeled; no VFE hardware or real IRQ timing.','device_modified':False}
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));raise SystemExit(r.returncode)
if __name__=='__main__':main()
