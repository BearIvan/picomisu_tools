"""Execute the actual temperature dependent backlight PWM, DCS group write and sde-crtc mirror bodies under ASan/UBSan."""
from pathlib import Path
import hashlib,importlib.util,json,re,subprocess,sys
BASE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro');SOURCE=BASE/'source/phoenix-kernel-recovery'
MIPI='drivers/gpu/drm/drm_mipi_dsi.c';PANEL='techpack/display/msm/dsi/dsi_panel.c';PANEL_H='techpack/display/msm/dsi/dsi_panel.h'
DISP='techpack/display/msm/dsi/dsi_display.c';CRTC='techpack/display/msm/sde/sde_crtc.c';CRTC_H='techpack/display/msm/sde/sde_crtc.h'
ENC='techpack/display/msm/sde/sde_encoder.c'
FUNCS=[(MIPI,'ssize_t mipi_dsi_dcs_write_group('),
       (PANEL,'int dsi_panel_handle_backlight_pwm('),(PANEL,'static u32 dsi_panel_temp_settling_us('),
       (PANEL,'static void dsi_panel_temp_dependent_bl_task('),(PANEL,'void dsi_panel_temp_pwm_kick('),
       (PANEL,'static void dsi_panel_temp_pwm_stop('),(PANEL,'static void dsi_panel_parse_temp_pwm('),
       (PANEL,'int dsi_panel_enable('),(PANEL,'int dsi_panel_pre_disable('),(PANEL,'void dsi_panel_put('),
       (DISP,'int dsi_display_set_backlight('),(DISP,'int dsi_display_get_bl_pwm_timing('),
       (CRTC,'static ssize_t vsync_timing_show('),(CRTC,'static ssize_t bl_pwm_timing_show('),
       (ENC,'static void sde_encoder_mirror_panel_timing(')]
STRUCTS=[(PANEL_H,'struct dsi_bl_pwm_timing {'),(PANEL_H,'struct dsi_backlight_config {'),
         (CRTC_H,'struct sde_crtc_bl_pwm_timing {'),(CRTC_H,'struct sde_crtc_vsync_timing {')]
MODEL=r'''
#include <assert.h>
#include <limits.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/types.h>
typedef uint8_t u8;typedef uint16_t u16;typedef uint32_t u32;typedef int32_t s32;typedef int64_t s64;typedef uint64_t u64;
typedef s64 ktime_t;
#define BIT(n) (1UL<<(n))
#define container_of(p,t,m) ((t *)((char *)(p)-offsetof(t,m)))
#define NSEC_PER_SEC 1000000000L
#define USEC_PER_SEC 1000000L
#define PAGE_SIZE 4096
#define EINVAL 22
#define ENOSYS 38
#define EOPNOTSUPP 95
#define ENODEV 19
#define EAGAIN 11
#define GFP_KERNEL 0
#define MAX_BL_SCALE_LEVEL 1024
#define MAX_SV_BL_SCALE_LEVEL 65535
static int errs,infos;
#define DSI_ERR(...) (errs++)
#define DSI_INFO(...) (infos++)
#define DSI_DEBUG(...) ((void)0)
#define SDE_ERROR(...) (errs++)
#define pr_err(...) ((void)0)
#define scnprintf snprintf
#define IS_ERR_OR_NULL(p) (!(p)||(unsigned long)(p)>=(unsigned long)-4095)
#define PTR_ERR(p) ((long)(p))
#define ERR_PTR(e) ((void *)(long)(e))
static s64 now_ns;
static ktime_t ktime_get(void){return now_ns;}
static ktime_t ktime_sub(ktime_t a,ktime_t b){return a-b;}
static s64 ktime_to_ns(ktime_t k){return k;}
static void msleep(unsigned ms){(void)ms;}
static int allocs;
static void *kzalloc(size_t n,int f){(void)f;allocs++;return calloc(1,n);}
static void *kcalloc(size_t c,size_t n,int f){(void)f;allocs++;return calloc(c,n);}
static void kfree(const void *p){if(p)allocs--;free((void *)p);}
/* locks: double lock / unlock without lock abort */
struct mutex {int held;};
static void mutex_lock(struct mutex *m){assert(!m->held);m->held=1;}
static void mutex_unlock(struct mutex *m){assert(m->held);m->held=0;}
/* workqueue model: 88-byte delayed_work like arm64 4.19 */
struct work_struct;typedef void (*work_func_t)(struct work_struct *);
struct work_struct {long data;void *entry[2];work_func_t func;};
struct timer_list {void *entry[2];unsigned long expires;void *function;u32 flags;};
struct workqueue_struct {int x;};
struct delayed_work {struct work_struct work;struct timer_list timer;struct workqueue_struct *wq;int cpu;};
static struct workqueue_struct system_wq_s;static struct workqueue_struct *system_wq=&system_wq_s;
#define to_delayed_work(w) container_of(w,struct delayed_work,work)
#define INIT_DELAYED_WORK(dw,f) do{memset(dw,0,sizeof(*(dw)));(dw)->work.func=(f);}while(0)
/* pending == timer.flags bit0, delay in timer.expires */
static struct mutex *lock_forbidden_in_cancel;
static int cancels;
static bool queue_delayed_work(struct workqueue_struct *wq,struct delayed_work *dw,unsigned long d){assert(wq==system_wq);if(dw->timer.flags&1)return false;dw->timer.flags|=1;dw->timer.expires=d;return true;}
static bool mod_delayed_work(struct workqueue_struct *wq,struct delayed_work *dw,unsigned long d){bool was=dw->timer.flags&1;assert(wq==system_wq);dw->timer.flags|=1;dw->timer.expires=d;return was;}
static bool cancel_delayed_work_sync(struct delayed_work *dw){bool was=dw->timer.flags&1;
  /* the work itself takes panel_lock: waiting for it with the lock held deadlocks */
  if(lock_forbidden_in_cancel)assert(!lock_forbidden_in_cancel->held);
  dw->timer.flags&=~1u;cancels++;return was;}
static bool pending(struct delayed_work *dw){return dw->timer.flags&1;}
static void run_work(struct delayed_work *dw){assert(pending(dw));dw->timer.flags&=~1u;dw->work.func(&dw->work);}
/* MIPI DSI */
#define MIPI_DSI_DCS_SHORT_WRITE 0x05
#define MIPI_DSI_DCS_SHORT_WRITE_PARAM 0x15
#define MIPI_DSI_DCS_LONG_WRITE 0x39
#define MIPI_DSI_MSG_USE_LPM BIT(1)
#define MIPI_DSI_MSG_LASTCOMMAND BIT(3)
#define MIPI_DSI_MODE_LPM BIT(11)
struct mipi_dsi_msg {u8 channel;u8 type;u16 flags;u32 ctrl;u32 wait_ms;u8 tx_flag;u8 tx_buf2[8];size_t tx_len;const void *tx_buf;size_t rx_len;void *rx_buf;};
struct mipi_dsi_host;
struct mipi_dsi_host_ops {int (*attach)(void);int (*detach)(void);ssize_t (*transfer)(struct mipi_dsi_host *,const struct mipi_dsi_msg *);};
struct mipi_dsi_host {const struct mipi_dsi_host_ops *ops;};
struct mipi_dsi_device {struct mipi_dsi_host *host;unsigned int channel;unsigned long mode_flags;};
struct sent {u8 type;u16 flags;u32 ctrl;u8 ch;size_t len;u8 b[4];};
static struct sent sent[16];static int nsent;static int dsi_fail;static struct mutex *expect_locked;
static ssize_t fake_transfer(struct mipi_dsi_host *h,const struct mipi_dsi_msg *m){(void)h;assert(nsent<16);
  if(expect_locked)assert(expect_locked->held);
  sent[nsent].type=m->type;sent[nsent].flags=m->flags;sent[nsent].ctrl=m->ctrl;sent[nsent].ch=m->channel;sent[nsent].len=m->tx_len;
  memcpy(sent[nsent].b,m->tx_buf,m->tx_len<4?m->tx_len:4);nsent++;return dsi_fail?-5:(ssize_t)m->tx_len;}
static const struct mipi_dsi_host_ops host_ops={.transfer=fake_transfer};
static const struct mipi_dsi_host_ops no_ops={0};
static struct mipi_dsi_host host={&host_ops};
/* panel side */
struct pwm_device;struct led_trigger;struct backlight_device;struct iio_channel {int id;};
enum dsi_backlight_type {DSI_BACKLIGHT_PWM};enum bl_update_flag {BL_UPDATE_NONE};
'''
MODEL2=r'''
struct device_node {int id;};struct device_attribute;struct dsi_panel;
struct device {void *driver_data;struct device_node *of_node;char pad[600];};
static void *dev_get_drvdata(struct device *d){return d->driver_data;}
struct dsi_parser_utils {void *data;struct device_node *node;
  bool (*read_bool)(const struct device_node *,const char *);
  int (*read_u32_array)(const struct device_node *,const char *,u32 *,size_t);
  int (*count_u32_elems)(const struct device_node *,const char *);};
struct dsi_mode_info {u32 h_active,h_back_porch,h_sync_width,h_front_porch,h_skew;bool h_sync_polarity;u32 v_active,v_back_porch,v_sync_width,v_front_porch;bool v_sync_polarity;u32 refresh_rate;};
struct dsi_display_mode {struct dsi_mode_info timing;};
struct drm_panel {int x;};struct dsi_panel_esd_config {int x;};
struct dsi_panel {const char *name;struct mipi_dsi_device mipi_device;struct mutex panel_lock;u32 dts_panel_type;
  struct drm_panel drm_panel;struct dsi_display_mode *cur_mode;struct dsi_backlight_config bl_config;struct dsi_parser_utils utils;
  struct dsi_panel_esd_config esd_config;bool panel_initialized;};
static bool dsi_panel_initialized(struct dsi_panel *p){return p->panel_initialized;}
/* iio */
static struct iio_channel chan_obj;static int iio_rc,iio_val,iio_get_mode,iio_released;static struct device_node *iio_expect_node;
static struct dsi_panel *kick_during_read;void dsi_panel_temp_pwm_kick(struct dsi_panel *panel);
static int iio_read_channel_processed(struct iio_channel *c,int *v){assert(c==&chan_obj);if(kick_during_read){mutex_lock(&kick_during_read->panel_lock);dsi_panel_temp_pwm_kick(kick_during_read);mutex_unlock(&kick_during_read->panel_lock);kick_during_read=NULL;}if(iio_rc<0)return iio_rc;*v=iio_val;return 0;}
static struct iio_channel *iio_channel_get(struct device *d,const char *name){assert(d&&!name&&d->of_node==iio_expect_node);
  return iio_get_mode==0?&chan_obj:iio_get_mode==1?NULL:ERR_PTR(-ENODEV);}
static void iio_channel_release(struct iio_channel *c){assert(c==&chan_obj);iio_released++;}
/* DT */
static bool dt_bool;static u32 dt_curve[16];static int dt_len,dt_read_rc;
static bool read_bool(const struct device_node *n,const char *p){(void)n;assert(!strcmp(p,"qcom,temperature-dependent-pwm"));return dt_bool;}
static int count_u32(const struct device_node *n,const char *p){(void)n;assert(!strcmp(p,"qcom,response-temp-curve"));return dt_len;}
static int read_u32_array(const struct device_node *n,const char *p,u32 *o,size_t sz){(void)n;assert(!strcmp(p,"qcom,response-temp-curve"));
  assert((int)sz==dt_len);if(dt_read_rc)return dt_read_rc;memcpy(o,dt_curve,sz*4);return 0;}
/* panel commands */
enum {DSI_CMD_SET_ON,DSI_CMD_SET_ON_P1,DSI_CMD_SET_PRE_OFF};
static int hw_version_display=1,tx_cmds,tx_rc;
static int dsi_panel_tx_cmd_set(struct dsi_panel *p,int t){assert(p->panel_lock.held);(void)t;tx_cmds++;return tx_rc;}
static int panel_removed,esd_deinit;
static void drm_panel_remove(struct drm_panel *p){(void)p;panel_removed++;}
static void dsi_panel_esd_config_deinit(struct dsi_panel_esd_config *e){(void)e;esd_deinit++;}
/* display side */
enum {DSI_CORE_CLK=1};enum {DSI_CLK_OFF,DSI_CLK_ON};
struct drm_connector {int id;};
struct dsi_display {const char *name;struct dsi_panel *panel;void *dsi_clk_handle;};
static int clk_on_rc,clk_off_rc,bl_set;static u32 vxr7200_brightness;
static int dsi_display_clk_ctrl(void *h,int c,int s){(void)h;(void)c;return s==DSI_CLK_ON?clk_on_rc:clk_off_rc;}
static int dsi_panel_set_backlight(struct dsi_panel *p,u32 l){assert(p->panel_lock.held);bl_set=l;return 0;}
/* sde side */
#define DRM_MODE_CONNECTOR_DSI 16
struct drm_display_mode {int vdisplay,vsync_start,vsync_end,vtotal,vrefresh;};
struct sde_connector {struct drm_connector base;void *display;};
#define to_sde_connector(c) container_of(c,struct sde_connector,base)
struct sde_encoder_phys {struct drm_connector *connector;struct drm_display_mode cached_mode;};
struct msm_display_info {int intf_type;};
struct sde_encoder_virt {struct sde_encoder_phys *cur_master;void *crtc_vblank_cb_data;struct msm_display_info disp_info;};
struct drm_crtc {int id;};
struct sde_crtc {struct drm_crtc base;struct sde_crtc_bl_pwm_timing bl_pwm_timing;struct sde_crtc_vsync_timing vsync_timing;};
#define to_sde_crtc(c) container_of(c,struct sde_crtc,base)
int dsi_panel_handle_backlight_pwm(struct dsi_panel *panel);
void dsi_panel_temp_pwm_kick(struct dsi_panel *panel);
'''
MAIN=r'''
/* factory dsi_backlight_config layout (dsi_panel_handle_backlight_pwm / dsi_panel_get offsets) */
_Static_assert(offsetof(struct dsi_backlight_config,pwm_timing)==88,"pwm_timing");
_Static_assert(offsetof(struct dsi_backlight_config,pwm_timing.end_line)==92,"end");
_Static_assert(offsetof(struct dsi_backlight_config,pwm_timing.start_line)==96,"start");
_Static_assert(offsetof(struct dsi_backlight_config,pwm_timing.valid)==100,"valid");
_Static_assert(offsetof(struct dsi_backlight_config,temp_pwm_enabled)==104,"enabled");
_Static_assert(offsetof(struct dsi_backlight_config,temp_chan)==112,"chan");
_Static_assert(offsetof(struct dsi_backlight_config,temp_pwm_work)==120,"work");
_Static_assert(offsetof(struct dsi_backlight_config,response_temp_curve)==208,"curve");
_Static_assert(offsetof(struct dsi_backlight_config,response_temp_curve_len)==216,"len");
_Static_assert(offsetof(struct dsi_backlight_config,settling_time_target_us)==220,"target");
_Static_assert(offsetof(struct dsi_backlight_config,startup_board_temp)==224,"startup");
_Static_assert(offsetof(struct dsi_backlight_config,display_on_time)==240,"on_time");
_Static_assert(sizeof(struct dsi_backlight_config)==248,"size");
static struct device_node panel_node;
static struct dsi_display_mode mode;
static struct dsi_panel *new_panel(u32 type){struct dsi_panel *p=kzalloc(sizeof(*p),GFP_KERNEL);p->name="test";p->mipi_device.host=&host;p->mipi_device.channel=0;
  p->dts_panel_type=type;p->cur_mode=&mode;p->utils.data=&panel_node;p->utils.node=&panel_node;p->utils.read_bool=read_bool;
  p->utils.count_u32_elems=count_u32;p->utils.read_u32_array=read_u32_array;lock_forbidden_in_cancel=&p->panel_lock;expect_locked=&p->panel_lock;return p;}
static void set_mode(u32 va,u32 vbp,u32 vsw,u32 vfp,u32 fps){memset(&mode,0,sizeof(mode));mode.timing.v_active=va;mode.timing.v_back_porch=vbp;
  mode.timing.v_sync_width=vsw;mode.timing.v_front_porch=vfp;mode.timing.refresh_rate=fps;mode.timing.h_active=2160;}
static void enable_dt(void){dt_bool=true;dt_len=6;u32 c[6]={20000,3000,40000,5000,60000,9000};memcpy(dt_curve,c,sizeof(c));dt_read_rc=0;iio_get_mode=0;iio_expect_node=&panel_node;}
static void check(u32 code,u32 type,u32 period,u32 end,u32 start,struct dsi_panel *p){
  if(type==2){assert(nsent==1&&sent[0].type==MIPI_DSI_DCS_LONG_WRITE&&sent[0].len==3&&sent[0].b[0]==0xB9&&sent[0].b[1]==((code>>8)&0xff)&&sent[0].b[2]==(code&0xff));
    assert((sent[0].flags&MIPI_DSI_MSG_LASTCOMMAND)&&sent[0].ctrl==0);}
  else{assert(nsent==3);assert(sent[0].type==MIPI_DSI_DCS_SHORT_WRITE_PARAM&&sent[0].b[0]==0xFF&&sent[0].b[1]==0x23&&!(sent[0].flags&MIPI_DSI_MSG_LASTCOMMAND));
    assert(sent[1].type==MIPI_DSI_DCS_SHORT_WRITE_PARAM&&sent[1].b[0]==0xDA&&sent[1].b[1]==((code>>8)&0xff)&&!(sent[1].flags&MIPI_DSI_MSG_LASTCOMMAND));
    assert(sent[2].type==MIPI_DSI_DCS_SHORT_WRITE_PARAM&&sent[2].b[0]==0xDB&&sent[2].b[1]==(code&0xff)&&(sent[2].flags&MIPI_DSI_MSG_LASTCOMMAND));}
  struct dsi_bl_pwm_timing *t=&p->bl_config.pwm_timing;
  if(t->period_lines!=period||t->end_line!=end||t->start_line!=start||t->valid!=1){fprintf(stderr,"timing %u %u %u %u want %u %u %u\n",t->period_lines,t->end_line,t->start_line,t->valid,period,end,start);abort();}}
int main(void){struct dsi_panel *p;struct dsi_backlight_config *bl;char buf[PAGE_SIZE];
 /* --- DCS group write --- */
 {struct mipi_dsi_device d={&host,2,MIPI_DSI_MODE_LPM};u8 one=0x29,two[2]={1,2},three[3]={1,2,3};nsent=0;expect_locked=NULL;
  assert(mipi_dsi_dcs_write_group(&d,&one,0,0,0)==-EINVAL&&nsent==0);
  assert(mipi_dsi_dcs_write_group(&d,&one,1,0,7)==1&&sent[0].type==MIPI_DSI_DCS_SHORT_WRITE&&sent[0].flags==MIPI_DSI_MSG_USE_LPM&&sent[0].ctrl==7&&sent[0].ch==2);
  assert(mipi_dsi_dcs_write_group(&d,two,2,MIPI_DSI_MSG_LASTCOMMAND,0)==2&&sent[1].type==MIPI_DSI_DCS_SHORT_WRITE_PARAM&&sent[1].flags==(MIPI_DSI_MSG_USE_LPM|MIPI_DSI_MSG_LASTCOMMAND));
  d.mode_flags=0;assert(mipi_dsi_dcs_write_group(&d,three,3,0,0)==3&&sent[2].type==MIPI_DSI_DCS_LONG_WRITE&&sent[2].flags==0);
  assert(mipi_dsi_dcs_write_group(NULL,three,3,0,0)==-EINVAL);d.host=NULL;assert(mipi_dsi_dcs_write_group(&d,three,3,0,0)==-EINVAL);
  struct mipi_dsi_host h2={&no_ops};d.host=&h2;assert(mipi_dsi_dcs_write_group(&d,three,3,0,0)==-ENOSYS&&nsent==3);}
 /* --- DT parse --- */
 p=new_panel(2);dt_bool=false;dsi_panel_parse_temp_pwm(p);assert(!p->bl_config.temp_pwm_enabled&&allocs==1);
 enable_dt();dt_len=5;dsi_panel_parse_temp_pwm(p);assert(!p->bl_config.temp_pwm_enabled&&allocs==1);
 enable_dt();dt_len=0;dsi_panel_parse_temp_pwm(p);assert(!p->bl_config.temp_pwm_enabled&&allocs==1);
 enable_dt();dt_read_rc=-22;dsi_panel_parse_temp_pwm(p);assert(!p->bl_config.temp_pwm_enabled&&allocs==1);
 enable_dt();iio_get_mode=1;dsi_panel_parse_temp_pwm(p);assert(!p->bl_config.temp_pwm_enabled&&allocs==1);
 enable_dt();iio_get_mode=2;dsi_panel_parse_temp_pwm(p);assert(!p->bl_config.temp_pwm_enabled&&allocs==1);
 /* kick/stop on a disabled feature never touch the uninitialised work */
 memset(&p->bl_config.temp_pwm_work,0xa5,sizeof(p->bl_config.temp_pwm_work));dsi_panel_temp_pwm_kick(p);dsi_panel_temp_pwm_stop(p);assert(cancels==0);
 enable_dt();dsi_panel_parse_temp_pwm(p);bl=&p->bl_config;
 assert(bl->temp_pwm_enabled&&bl->temp_chan==&chan_obj&&bl->response_temp_curve_len==3&&bl->settling_time_target_us==3000&&allocs==2&&!pending(&bl->temp_pwm_work));
 /* --- interpolation --- */
 {const s32 *c=(const s32 *)bl->response_temp_curve;
  assert(dsi_panel_temp_settling_us(c,3,-40000)==3000&&dsi_panel_temp_settling_us(c,3,20000)==3000&&dsi_panel_temp_settling_us(c,3,30000)==4000);
  assert(dsi_panel_temp_settling_us(c,3,40000)==5000&&dsi_panel_temp_settling_us(c,3,50000)==7000&&dsi_panel_temp_settling_us(c,3,60000)==9000);
  assert(dsi_panel_temp_settling_us(c,3,99000)==9000&&dsi_panel_temp_settling_us(c,3,INT_MIN)==3000);}
 /* --- panel enable arms, backlight kicks under the panel lock --- */
 {struct dsi_display disp={"d",p,NULL};struct drm_connector conn;
  tx_rc=-5;assert(dsi_panel_enable(p)==-5&&!p->panel_initialized);tx_rc=0;
  bl->temp_pwm_stopped=true;assert(!dsi_panel_enable(p)&&p->panel_initialized&&!bl->temp_pwm_stopped);
  clk_on_rc=-1;assert(dsi_display_set_backlight(&conn,&disp,100)==-1&&!pending(&bl->temp_pwm_work));clk_on_rc=0;
  clk_off_rc=-1;assert(dsi_display_set_backlight(&conn,&disp,100)==-1&&!pending(&bl->temp_pwm_work));clk_off_rc=0;
  bl->bl_scale=MAX_BL_SCALE_LEVEL;bl->bl_scale_sv=MAX_SV_BL_SCALE_LEVEL;
  assert(!dsi_display_set_backlight(&conn,&disp,100)&&bl_set==100&&pending(&bl->temp_pwm_work)&&bl->temp_pwm_work.timer.expires==0);
  p->panel_initialized=false;bl->temp_pwm_work.timer.flags=0;assert(dsi_display_set_backlight(&conn,&disp,100)==-EINVAL&&!pending(&bl->temp_pwm_work));
  p->panel_initialized=true;assert(!dsi_display_set_backlight(&conn,&disp,100)&&pending(&bl->temp_pwm_work));
  struct dsi_bl_pwm_timing t;assert(dsi_display_get_bl_pwm_timing(NULL,&t)==-EINVAL);disp.panel=NULL;assert(dsi_display_get_bl_pwm_timing(&disp,&t)==-EINVAL);}
 /* --- work: 90 Hz sharp panel, warm (past the 240 s hold-off) --- */
 set_mode(EXP_VA,EXP_VBP,EXP_VSW,EXP_VFP,90);bl->display_on_time=0;now_ns=300LL*NSEC_PER_SEC;iio_rc=0;iio_val=45000;nsent=0;
 run_work(&bl->temp_pwm_work);
 assert(infos==1&&bl->startup_board_temp==45000&&bl->settling_time_target_us==EXP_TARGET&&bl->last_board_temp==39000);
 check(EXP_A_CODE,2,EXP_PERIOD,EXP_A_END,EXP_A_START,p);
 assert(pending(&bl->temp_pwm_work)&&bl->temp_pwm_work.timer.expires==100&&!p->panel_lock.held);
 /* a kick while queued keeps the work due now; the running work must not push it back */
 dsi_panel_temp_pwm_kick(p);assert(bl->temp_pwm_work.timer.expires==0);
 /* a backlight update while the work runs must not be delayed by the requeue */
 kick_during_read=p;nsent=0;run_work(&bl->temp_pwm_work);assert(pending(&bl->temp_pwm_work)&&bl->temp_pwm_work.timer.expires==0);
 /* --- cold start: within the hold-off the maximum window is used --- */
 bl->display_on_time=now_ns-10LL*NSEC_PER_SEC;nsent=0;run_work(&bl->temp_pwm_work);check(EXP_B_CODE,2,EXP_PERIOD,EXP_B_END,EXP_B_START,p);assert(infos==1);
 /* --- innolux nt57900 at 72 Hz, cold sensor below the curve --- */
 p->dts_panel_type=1;set_mode(EXP_VA,EXP_VBP,EXP_VSW,EXP_VFP,72);bl->display_on_time=0;iio_val=10000;nsent=0;run_work(&bl->temp_pwm_work);
 assert(bl->settling_time_target_us==3000);check(EXP_C_CODE,1,EXP_PERIOD,EXP_C_END,EXP_C_START,p);
 /* --- target above the window: the window wins --- */
 iio_val=80000;nsent=0;run_work(&bl->temp_pwm_work);assert(bl->settling_time_target_us==9000);check(EXP_D_CODE,1,EXP_PERIOD,EXP_D_END,EXP_D_START,p);
 /* --- sensor failure falls back to the first curve point --- */
 iio_rc=-5;nsent=0;run_work(&bl->temp_pwm_work);assert(bl->settling_time_target_us==3000&&bl->last_board_temp==INT_MIN);iio_rc=0;
 /* --- DCS failure still publishes the window, errors logged --- */
 dsi_fail=1;nsent=0;errs=0;run_work(&bl->temp_pwm_work);assert(nsent==1&&errs==1&&bl->pwm_timing.valid);dsi_fail=0;
 /* --- unsupported panel / no mode / zero fps / panel off: no DCS, window untouched --- */
 memset(&bl->pwm_timing,0,sizeof(bl->pwm_timing));
 p->dts_panel_type=0;nsent=0;assert(dsi_panel_handle_backlight_pwm(p)==-EOPNOTSUPP&&nsent==0&&!bl->pwm_timing.valid);p->dts_panel_type=2;
 mode.timing.refresh_rate=0;assert(dsi_panel_handle_backlight_pwm(p)==-EINVAL&&nsent==0);
 set_mode(0,0,0,0,90);assert(dsi_panel_handle_backlight_pwm(p)==-EINVAL&&nsent==0);
 set_mode(EXP_VA,EXP_VBP,EXP_VSW,EXP_VFP,90);p->cur_mode=NULL;assert(dsi_panel_handle_backlight_pwm(p)==-EINVAL);p->cur_mode=&mode;
 p->panel_initialized=false;assert(dsi_panel_handle_backlight_pwm(p)==-EINVAL&&nsent==0);p->panel_initialized=true;
 /* pathological mode: window underflows to zero instead of wrapping */
 set_mode(9000,10,10,10,120);bl->display_on_time=0;assert(!dsi_panel_handle_backlight_pwm(p)&&nsent==1&&sent[0].b[1]==0x23&&sent[0].b[2]==0x28);nsent=0;set_mode(EXP_VA,EXP_VBP,EXP_VSW,EXP_VFP,90);
 /* --- disable: stop outside panel_lock, no rearm afterwards --- */
 assert(pending(&bl->temp_pwm_work));tx_cmds=0;assert(!dsi_panel_pre_disable(p)&&tx_cmds==1&&bl->temp_pwm_stopped&&!pending(&bl->temp_pwm_work)&&cancels==1);
 dsi_panel_temp_pwm_kick(p);assert(!pending(&bl->temp_pwm_work));
 {struct dsi_display disp={"d",p,NULL};struct drm_connector conn;assert(!dsi_display_set_backlight(&conn,&disp,50)&&!pending(&bl->temp_pwm_work));}
 /* a work instance that was already running when stop happened finishes without requeueing */
 bl->temp_pwm_work.timer.flags=1;nsent=0;run_work(&bl->temp_pwm_work);assert(!pending(&bl->temp_pwm_work));
 /* re-enable rearms */
 assert(!dsi_panel_enable(p)&&!bl->temp_pwm_stopped);dsi_panel_temp_pwm_kick(p);assert(pending(&bl->temp_pwm_work));
 /* --- sde mirror and sysfs --- */
 {struct dsi_display disp={"d",p,NULL};struct sde_connector sc={{1},&disp};struct sde_encoder_phys phys={&sc.base,{2160,2196,2200,2220,90}};
  struct sde_crtc crtc;memset(&crtc,0,sizeof(crtc));struct sde_encoder_virt enc={&phys,&crtc.base,{DRM_MODE_CONNECTOR_DSI}};
  bl->pwm_timing=(struct dsi_bl_pwm_timing){222,3364,3252,1};
  enc.disp_info.intf_type=11;sde_encoder_mirror_panel_timing(&enc);assert(!crtc.bl_pwm_timing.valid&&!crtc.vsync_timing.vtotal);enc.disp_info.intf_type=DRM_MODE_CONNECTOR_DSI;
  enc.cur_master=NULL;sde_encoder_mirror_panel_timing(&enc);assert(!crtc.bl_pwm_timing.valid);enc.cur_master=&phys;
  enc.crtc_vblank_cb_data=NULL;sde_encoder_mirror_panel_timing(&enc);assert(!crtc.bl_pwm_timing.valid);enc.crtc_vblank_cb_data=&crtc.base;
  disp.panel=NULL;sde_encoder_mirror_panel_timing(&enc);assert(!crtc.bl_pwm_timing.valid&&!crtc.vsync_timing.vtotal);disp.panel=p;
  sde_encoder_mirror_panel_timing(&enc);
  struct device dev={.driver_data=&crtc.base};
  assert(bl_pwm_timing_show(&dev,NULL,buf)>0&&!strcmp(buf,"1,222,3364,3252\n"));
  assert(vsync_timing_show(&dev,NULL,buf)>0&&!strcmp(buf,"24,2160,36@90\n"));
  assert(bl_pwm_timing_show(NULL,NULL,buf)==-11&&vsync_timing_show(&dev,NULL,NULL)==-11);}
 /* --- teardown releases everything --- */
 assert(!dsi_panel_pre_disable(p));dsi_panel_put(p);assert(iio_released==1&&panel_removed==1&&esd_deinit==1&&allocs==0);
 puts("PASS: DCS group write (types, LPM, batching, errors); DT parse incl. all failure paths without leaks; curve interpolation; "
      "sharp B9 / innolux FF23 DA DB sequences and PWM window at 90/72 Hz, warm and cold; hold-off and window clamp; sensor and DCS "
      "failures; unsupported panel/mode guards; kick only on successful backlight under panel_lock; stop cancels outside panel_lock "
      "and nothing rearms until enable; sde mirror guards and sysfs formats; teardown releases iio and curve; factory 248-byte layout");
 return 0;
}
'''
def expected():
    # independent model of factory dsi_panel_handle_backlight_pwm arithmetic (32-bit unsigned like the factory)
    va,vbp,vsw,vfp=2160,20,4,36
    vt=va+vbp+vsw+vfp
    def run(fps,target,warm,typ):
        line=(1000*(1000000//fps)//vt)&0xffffffff
        if fps==90:mx=10680-1800*va//1000
        else:mx=1000000//fps-1800*va//1000-(1000000//fps)//10
        mx=max(mx,0)
        s=target if (warm and mx>=target) else mx
        pulse=(1800*va+1000*s)&0xffffffff
        so,eo=(1496,1608) if typ==2 else (1540,1900)
        return pulse//1800,(pulse+line*eo)//line,(pulse+line*so)//line
    tgt=3000+(5000-3000)*(45000-6000-20000)//(40000-20000)
    a=run(90,tgt,True,2);b=run(90,tgt,False,2);c=run(72,3000,True,1);d=run(72,9000,True,1)
    defs=dict(EXP_VA=va,EXP_VBP=vbp,EXP_VSW=vsw,EXP_VFP=vfp,EXP_TARGET=tgt,EXP_PERIOD=vt//10)
    for k,v in zip('ABCD',(a,b,c,d)):defs.update({f'EXP_{k}_CODE':v[0],f'EXP_{k}_END':v[1],f'EXP_{k}_START':v[2]})
    return ''.join(f'#define {k} {v}u\n' for k,v in defs.items()),defs
def main():
    spec=importlib.util.spec_from_file_location('ex',Path(__file__).with_name('test-pico-sensor-mono-hook.py'));ex=importlib.util.module_from_spec(spec);spec.loader.exec_module(ex)
    srcs={n:(SOURCE/n).read_text() for n in {f for f,_ in FUNCS+STRUCTS}}
    defines='\n'.join(l for l in srcs[PANEL].splitlines() if re.match(r'#define DSI_PANEL_(TEMP_PWM|DTS_TYPE)_',l))
    head,defs=expected()
    code=(MODEL+'\n'.join(ex.function(srcs[f],s)+';' for f,s in STRUCTS[:2])+MODEL2.replace('struct sde_crtc {','\n'+'\n'.join(ex.function(srcs[f],s)+';' for f,s in STRUCTS[2:])+'\nstruct sde_crtc {',1)
          +defines+'\n'+'\n'.join(ex.function(srcs[f],s) for f,s in FUNCS)+'\n'+head+MAIN)
    out=BASE/'out/phoenix-kernel-recovery/display-temp-pwm-tests';out.mkdir(exist_ok=True);(out/'harness.c').write_text(code)
    subprocess.run(['gcc','-std=gnu11','-g','-O1','-Wall','-Wno-unused-function','-fsanitize=address,undefined','-fno-sanitize-recover=all',str(out/'harness.c'),'-o',str(out/'test')],check=True)
    r=subprocess.run([str(out/'test')],capture_output=True,text=True,timeout=60)
    report={'sources':{n:hashlib.sha256((SOURCE/n).read_bytes()).hexdigest() for n in sorted(srcs)},'harness_sha256':hashlib.sha256(code.encode()).hexdigest(),
            'expected':defs,'exit_code':r.returncode,'stdout':r.stdout,'stderr':r.stderr[-3000:],
            'scope':'Actual mipi_dsi_dcs_write_group, dsi_panel temp-PWM parse/work/kick/stop, dsi_panel_enable/pre_disable/put, dsi_display_set_backlight/'
                    'get_bl_pwm_timing, sde_encoder_mirror_panel_timing and the two sde-crtc show bodies plus the real dsi_backlight_config and '
                    'timing structs (factory offsets asserted). DSI host, IIO, DT utils, workqueue and locks modeled; cancel asserts panel_lock is '
                    'not held. Expected PWM numbers come from an independent Python model of the factory arithmetic.','device_modified':False}
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));raise SystemExit(r.returncode)
if __name__=='__main__':main()
