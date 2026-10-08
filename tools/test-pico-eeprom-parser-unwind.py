"""Complete native EEPROM packet orchestrator/DT path/get-cal/write/cleanup."""
from pathlib import Path
import hashlib,json,subprocess,importlib.util
BASE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro');SOURCE=BASE/'source/phoenix-kernel-recovery';D='techpack/camera/drivers/cam_sensor_module/cam_eeprom/'
NAMES=[D+n for n in ['cam_eeprom_core.c','cam_eeprom_dev.h','pico_eeprom_acquire_unwind.inc']]+['techpack/camera/include/uapi/media/'+n for n in ['cam_defs.h','cam_sensor.h']]+['techpack/camera/drivers/cam_sensor_module/cam_sensor_utils/cam_sensor_cmn_header.h']
NAMES += ['techpack/camera/drivers/cam_utils/cam_packet_util.c']
def load(name):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name(name+'.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
EXTRA=r'''
#define MSM_CAMERA_SPI_DEVICE 3
#define I2C_MASTER 2
struct device_node {int unused;};struct device {struct device_node *of_node;};
struct cam_eeprom_memory_block_t {void *map,*mapdata;unsigned num_data,num_map;};
struct i2c_settings_list {struct list_head list;struct {void *reg_data;}seq_settings;struct {void *reg_setting;int unused;}i2c_settings;int op_code;};
struct i2c_settings_array {struct list_head list_head;int is_settings_valid;};
#define list_del(n) list_del_init(n)
#define list_for_each_entry_safe(p,t,h,m) for(struct list_head *cur=(h)->next,*next;cur!=(h)&&((next=cur->next),(p)=container_of(cur,__typeof__(*(p)),m),1);cur=next)
static union {max_align_t align;unsigned char bytes[1024];} packet_store;
static unsigned char output[8];static size_t packet_size=1024,output_size=8;static int input_error,mapping_error,output_mapping_error,validate_error,nested_parse_error,dt_error,read_error,erase_error,write_error;
static unsigned reads,erases,writes;
static int copy_from_user(void *dst,const void *src,size_t n){if(input_error)return 1;memcpy(dst,src,n);return 0;}
static int cam_mem_get_cpu_buf(int handle,uintptr_t *addr,size_t *size){if(handle==1){if(mapping_error)return mapping_error;*addr=(uintptr_t)packet_store.bytes;*size=packet_size;}else{assert(handle==2);if(output_mapping_error)return output_mapping_error;*addr=(uintptr_t)output;*size=output_size;}return 0;}
static int pico_mem_copy_to(int handle,size_t offset,const void *source,size_t n){uintptr_t address;size_t bytes;int rc=cam_mem_get_cpu_buf(handle,&address,&bytes);if(rc)return rc;if(offset>=bytes||n>bytes-offset)return -EINVAL;memcpy((void *)(address+offset),source,n);return 0;}
static int pico_mem_dup_packet(int handle,size_t offset,void **packet,size_t *bytes){uintptr_t address;size_t len;*packet=NULL;*bytes=0;int rc=cam_mem_get_cpu_buf(handle,&address,&len);if(rc)return rc;if(offset>len||len-offset<sizeof(struct cam_packet))return -EINVAL;struct cam_packet *src=(void *)(address+offset);if(src->header.size<sizeof(*src)||src->header.size>len-offset)return -EINVAL;*packet=malloc(src->header.size);if(!*packet)return -ENOMEM;*bytes=src->header.size;memcpy(*packet,src,*bytes);return 0;}
static int cam_packet_util_validate_packet(struct cam_packet *packet,size_t n){return validate_error;}
static void *vzalloc(size_t n){return calloc(1,n);}
static void usleep_range(unsigned min,unsigned max){}
static void settings(struct cam_eeprom_ctrl_t *c){struct cam_eeprom_soc_private *p=c->soc_info.soc_private;if(!p->power_info.power_setting){p->power_info.power_setting=malloc(8);p->power_info.power_down_setting=malloc(8);p->power_info.power_setting_size=p->power_info.power_down_setting_size=1;}}
static int cam_eeprom_init_pkt_parser(struct cam_eeprom_ctrl_t *c,struct cam_packet *p){settings(c);c->cal_data.map=malloc(8);c->cal_data.num_map=1;c->cal_data.num_data=4;return nested_parse_error;}
static int cam_eeprom_parse_dt_memory_map(struct device_node *node,struct cam_eeprom_memory_block_t *block){block->map=malloc(8);block->mapdata=malloc(4);block->num_map=1;block->num_data=4;return dt_error;}
static int cam_eeprom_match_id(struct cam_eeprom_ctrl_t *c){return 0;}
static int cam_eeprom_read_memory(struct cam_eeprom_ctrl_t *c,struct cam_eeprom_memory_block_t *block){reads++;if(read_error)return read_error;memset(block->mapdata,0x5a,block->num_data);return 0;}
static int cam_eeprom_parse_write_memory_packet(struct cam_packet *p,struct cam_eeprom_ctrl_t *c){settings(c);struct i2c_settings_list *node=calloc(1,sizeof(*node));node->seq_settings.reg_data=malloc(8);list_add(&node->list,&c->wr_settings.list_head);return nested_parse_error;}
static int camera_io_dev_erase(struct camera_io_master *io,unsigned start,unsigned size){erases++;return erase_error;}
static int camera_io_dev_write_continuous(struct camera_io_master *io,void *settings,int mode){writes++;return write_error;}
'''
MAIN=r'''
static struct cam_eeprom_ctrl_t c;static struct cam_eeprom_soc_private private;static struct device device;static struct cam_config_dev_cmd config;static struct cam_control cmd;
static void init(bool userspace,unsigned opcode){
 memset(&c,0,sizeof(c));memset(&private,0,sizeof(private));assert(!pthread_mutex_init(&c.eeprom_mutex.value,NULL));c.bridge_intf.device_hdl=1234;c.bridge_intf.session_hdl=41;c.bridge_intf.link_hdl=-1;c.cam_eeprom_state=CAM_EEPROM_ACQUIRE;c.userspace_probe=userspace;c.soc_info.soc_private=&private;c.soc_info.dev=&device;c.io_master_info.master_type=CCI_MASTER;INIT_LIST_HEAD(&c.wr_settings.list_head);
 memset(packet_store.bytes,0,1024);memset(output,0,8);struct cam_packet *packet=(void *)packet_store.bytes;packet->header.op_code=opcode;packet->header.size=1024;packet->num_io_configs=1;struct cam_buf_io_cfg *io=(void *)&packet->payload;io->direction=CAM_BUF_OUTPUT;io->mem_handle[0]=2;
 config=(struct cam_config_dev_cmd){.packet_handle=1};cmd=(struct cam_control){.op_code=CAM_CONFIG_DEV,.handle_type=CAM_HANDLE_USER_POINTER,.handle=(uintptr_t)&config};
 core_up_error=core_down_error=io_init_error=io_release_error=destroy_error=fill_error=input_error=mapping_error=output_mapping_error=validate_error=nested_parse_error=dt_error=read_error=erase_error=write_error=0;packet_size=1024;output_size=8;ups=downs=inits=releases=destroys=frees=configs=reads=erases=writes=0;
 if(!userspace)settings(&c);
}
static void finish(void){assert(!c.pico_core_powered&&!c.pico_io_initialized&&!c.pico_transaction_cleanup_pending);assert(!c.cal_data.map&&!c.cal_data.mapdata);assert(list_empty(&c.wr_settings.list_head)&&!c.wr_settings.is_settings_valid);assert(!private.power_info.power_setting&&!private.power_info.power_down_setting);assert(!held);assert(!pthread_mutex_destroy(&c.eeprom_mutex.value));}
static void shutdown(void){mutex_lock(&c.eeprom_mutex);cam_eeprom_shutdown(&c);mutex_unlock(&c.eeprom_mutex);}
int main(void){
 init(true,CAM_EEPROM_PACKET_OPCODE_INIT);assert(!cam_eeprom_driver_cmd(&c,&cmd)&&ups==1&&downs==1&&inits==1&&releases==1&&reads==1&&!memcmp(output,"ZZZZ",4)&&c.cam_eeprom_state==CAM_EEPROM_ACQUIRE);finish();
 init(true,CAM_EEPROM_PACKET_OPCODE_INIT);input_error=1;assert(cam_eeprom_driver_cmd(&c,&cmd)==-EFAULT&&!ups);input_error=0;mapping_error=-ENOENT;assert(cam_eeprom_driver_cmd(&c,&cmd)==-ENOENT&&!ups);mapping_error=0;packet_size=sizeof(struct cam_packet);assert(cam_eeprom_driver_cmd(&c,&cmd)==-EINVAL&&!ups);packet_size=1024;((struct cam_packet *)packet_store.bytes)->header.size=0;assert(cam_eeprom_driver_cmd(&c,&cmd)==-EINVAL&&!ups);finish();
 init(true,CAM_EEPROM_PACKET_OPCODE_INIT);nested_parse_error=-EINVAL;assert(cam_eeprom_driver_cmd(&c,&cmd)==-EINVAL&&!ups);finish();
 init(true,CAM_EEPROM_PACKET_OPCODE_INIT);output_size=2;assert(cam_eeprom_driver_cmd(&c,&cmd)==-EINVAL&&downs==1&&releases==1);finish();
 init(true,CAM_EEPROM_PACKET_OPCODE_INIT);output_mapping_error=-ENXIO;io_release_error=-EAGAIN;assert(cam_eeprom_driver_cmd(&c,&cmd)==-ENXIO&&!c.pico_core_powered&&c.pico_io_initialized&&c.pico_transaction_cleanup_pending&&private.power_info.power_setting&&c.cal_data.mapdata&&c.cam_eeprom_state==CAM_EEPROM_CONFIG);
 unsigned completed_downs=downs;assert(cam_eeprom_driver_cmd(&c,&cmd)==-EBUSY);io_release_error=0;cmd.op_code=CAM_RELEASE_DEV;assert(!cam_eeprom_driver_cmd(&c,&cmd)&&downs==completed_downs&&releases==2);finish();
 init(true,CAM_EEPROM_PACKET_OPCODE_INIT);read_error=-EREMOTEIO;core_down_error=-EBUSY;assert(cam_eeprom_driver_cmd(&c,&cmd)==-EREMOTEIO&&c.pico_core_powered&&c.cal_data.mapdata);core_down_error=0;shutdown();finish();
 init(true,CAM_EEPROM_PACKET_OPCODE_INIT);io_init_error=-ENXIO;core_down_error=-EBUSY;assert(cam_eeprom_driver_cmd(&c,&cmd)==-ENXIO&&c.pico_core_powered&&!c.pico_io_initialized&&c.pico_transaction_cleanup_pending);core_down_error=0;shutdown();finish();
 init(true,CAM_EEPROM_WRITE);nested_parse_error=-EINVAL;assert(cam_eeprom_driver_cmd(&c,&cmd)==-EINVAL&&!ups&&!erases&&!writes);finish();
 init(true,CAM_EEPROM_WRITE);erase_error=-EIO;assert(cam_eeprom_driver_cmd(&c,&cmd)==-EIO&&erases==1&&!writes&&downs==1&&releases==1);finish();
 init(true,CAM_EEPROM_WRITE);write_error=-EREMOTEIO;assert(cam_eeprom_driver_cmd(&c,&cmd)==-EREMOTEIO&&writes==1&&downs==1&&releases==1);finish();
 init(true,CAM_EEPROM_WRITE);assert(!cam_eeprom_driver_cmd(&c,&cmd)&&erases==1&&writes==1&&downs==1&&releases==1&&c.cam_eeprom_state==CAM_EEPROM_ACQUIRE);finish();
 init(true,CAM_EEPROM_WRITE);erase_error=-EIO;io_release_error=-EAGAIN;assert(cam_eeprom_driver_cmd(&c,&cmd)==-EIO&&c.pico_io_initialized&&private.power_info.power_setting&&!list_empty(&c.wr_settings.list_head));completed_downs=downs;io_release_error=0;shutdown();assert(downs==completed_downs&&releases==2);finish();
 init(false,CAM_EEPROM_PACKET_OPCODE_INIT);void *dt_settings=private.power_info.power_setting;assert(!cam_eeprom_driver_cmd(&c,&cmd)&&private.power_info.power_setting==dt_settings&&!c.cal_data.map&&!memcmp(output,"ZZZZ",4));assert(!cam_eeprom_driver_cmd(&c,&cmd)&&private.power_info.power_setting==dt_settings&&ups==2&&downs==2);shutdown();finish();
 init(false,CAM_EEPROM_PACKET_OPCODE_INIT);read_error=-EREMOTEIO;io_release_error=-EAGAIN;assert(cam_eeprom_driver_cmd(&c,&cmd)==-EREMOTEIO&&c.pico_io_initialized&&c.cal_data.mapdata&&c.cam_eeprom_state==CAM_EEPROM_CONFIG);io_release_error=0;shutdown();finish();
 init(false,CAM_EEPROM_PACKET_OPCODE_INIT);dt_error=-EINVAL;assert(cam_eeprom_driver_cmd(&c,&cmd)==-EINVAL&&!ups&&!c.cal_data.map&&!c.cal_data.mapdata&&private.power_info.power_setting);shutdown();finish();
 init(true,CAM_EEPROM_WRITE);io_release_error=-EAGAIN;assert(cam_eeprom_driver_cmd(&c,&cmd)==-EAGAIN&&writes==1&&c.pico_io_initialized&&c.pico_transaction_cleanup_pending&&list_empty(&c.wr_settings.list_head));completed_downs=downs;io_release_error=0;shutdown();assert(downs==completed_downs);finish();
 init(true,CAM_EEPROM_PACKET_OPCODE_INIT);struct cam_packet *pkt=(void *)packet_store.bytes;struct cam_buf_io_cfg *cfg=(void *)&pkt->payload;pkt->num_io_configs=2;cfg[1]=cfg[0];cfg[1].offsets[0]=4;assert(!cam_eeprom_driver_cmd(&c,&cmd)&&!memcmp(output,"ZZZZZZZZ",8));finish();
 init(true,CAM_EEPROM_PACKET_OPCODE_INIT);pkt=(void *)packet_store.bytes;cfg=(void *)&pkt->payload;pkt->num_io_configs=2;cfg[1]=cfg[0];cfg[1].direction=CAM_BUF_INPUT;assert(cam_eeprom_driver_cmd(&c,&cmd)==-EINVAL);finish();
 init(true,CAM_EEPROM_PACKET_OPCODE_INIT);pkt=(void *)packet_store.bytes;pkt->num_cmd_buf=1;pkt->cmd_buf_offset=1;assert(cam_eeprom_driver_cmd(&c,&cmd)==-EINVAL&&!ups);pkt->num_cmd_buf=UINT32_MAX;pkt->cmd_buf_offset=0;assert(cam_eeprom_driver_cmd(&c,&cmd)==-EINVAL&&!ups);finish();
 init(true,CAM_EEPROM_PACKET_OPCODE_INIT);pkt=(void *)packet_store.bytes;pkt->io_configs_offset=1;assert(cam_eeprom_driver_cmd(&c,&cmd)==-EINVAL&&!ups);pkt->io_configs_offset=1024;assert(cam_eeprom_driver_cmd(&c,&cmd)==-EINVAL&&!ups);finish();
 puts("PASS: complete actual EEPROM packet orchestrator, DT read path, UAPI get-cal, write/list destruction, power/release/shutdown; validation and nested-parse errors, read result precedence, CCI unwind retention/retry, erase/write rollback, successful write cleanup, repeated DT reads preserve settings");
}
'''
def main():
    power=load('test-pico-eeprom-power-retry');common=load('test-pico-camera-hub-registry');extract=load('test-pico-sensor-mono-hook');core=(SOURCE/NAMES[0]).read_text();header=(SOURCE/NAMES[1]).read_text();cmn=(SOURCE/NAMES[5]).read_text()
    states=header[header.index('enum cam_eeprom_state {'):header.index('};',header.index('enum cam_eeprom_state {'))+2];opcodes=cmn[cmn.index('enum cam_eeprom_packet_opcodes {'):cmn.index('};',cmn.index('enum cam_eeprom_packet_opcodes {'))+2]+cmn[cmn.index('enum cam_sensor_i2c_cmd_type {'):cmn.index('};',cmn.index('enum cam_sensor_i2c_cmd_type {'))+2]
    mocks=power.MOCKS.replace('static int cam_eeprom_pkt_parse(struct cam_eeprom_ctrl_t *c,void *arg){configs++;return 0;}','').replace('static int32_t delete_eeprom_request(void *s){assert(0);return 0;}','').replace('void *dev,*soc_private;','struct device *dev;void *soc_private;').replace('struct {void *mapdata,*map;unsigned num_data,num_map;}cal_data;struct {int is_settings_valid;}wr_settings;','struct cam_eeprom_memory_block_t cal_data;struct i2c_settings_array wr_settings;int eeprom_device_type;struct {unsigned start_address,size;}eebin_info;')
    # Type declarations precede controllers; API definitions follow controllers.
    split=EXTRA.index('static union');types=EXTRA[:split];extra=EXTRA[split:]
    signatures=['static int32_t delete_eeprom_request(','static int cam_eeprom_power_up(','static int cam_eeprom_power_down(','static void pico_eeprom_free_transaction(','int32_t cam_eeprom_parse_read_memory_map(','static int32_t cam_eeprom_get_cal_data(','static int32_t cam_eeprom_write(','static int32_t cam_eeprom_pkt_parse_owned(','static int32_t cam_eeprom_pkt_parse(']
    bodies='\n'.join(extract.function(core[core.rindex(s):] if s.startswith('static int32_t delete_eeprom_request(') else core,s) for s in signatures)+(SOURCE/NAMES[2]).read_text()+extract.function(core,'int32_t cam_eeprom_driver_cmd(')+extract.function(core,'void cam_eeprom_shutdown(')
    extra=extra.replace('static int cam_packet_util_validate_packet(struct cam_packet *packet,size_t n){return validate_error;}',extract.function((SOURCE/NAMES[6]).read_text(),'int cam_packet_util_validate_packet('))
    code='#include <stdint.h>\n#include <stddef.h>\n#include <string.h>\n#include <cam_defs.h>\n#include <cam_sensor.h>\n'+common.HARNESS.split('/* OWNED_SUBDEVICE_MOCKS */')[0]+states+opcodes+types+mocks+extra+bodies+MAIN
    out=BASE/'out/phoenix-kernel-recovery/eeprom-parser-unwind-tests';out.mkdir(exist_ok=True);(out/'harness.c').write_text(code)
    subprocess.run(['gcc','-std=gnu11','-g','-O1','-pthread','-fsanitize=address,undefined','-fno-omit-frame-pointer','-I'+str(SOURCE/'techpack/camera/include/uapi/media'),'-I'+str(SOURCE/'techpack/camera/include/uapi'),str(out/'harness.c'),'-o',str(out/'test')],check=True)
    r=subprocess.run([str(out/'test')],capture_output=True,text=True,timeout=30);report={'sources':{n:hashlib.sha256((SOURCE/n).read_bytes()).hexdigest() for n in NAMES},'harness_sha256':hashlib.sha256(code.encode()).hexdigest(),'exit_code':r.returncode,'stdout':r.stdout,'stderr':r.stderr,'sanitizers':['AddressSanitizer','UndefinedBehaviorSanitizer'],'scope':'Complete actual packet orchestrator/DT read/get-cal/write/delete-request/power/free/release/shutdown bodies with native state/opcode enums and real public packet/io-config UAPI; lower mapping/DT/nested payload parsers/hardware providers modeled; no actual EEPROM writes or hardware/remove lifetime proof','device_modified':False};(out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));raise SystemExit(r.returncode)
if __name__=='__main__':main()
