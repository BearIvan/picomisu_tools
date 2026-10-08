"""Actual EEPROM write payload/allocator/delay/list and I/O mode dispatch."""
from pathlib import Path
import hashlib,json,re,subprocess,importlib.util
BASE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro');SOURCE=BASE/'source/phoenix-kernel-recovery';D='techpack/camera/drivers/cam_sensor_module/cam_eeprom/';IO='techpack/camera/drivers/cam_sensor_module/cam_sensor_io/'
NAMES=[D+'cam_eeprom_core.c',IO+'cam_sensor_io.c',IO+'cam_sensor_cci_i2c.c',IO+'cam_sensor_qup_i2c.c','techpack/camera/drivers/cam_sensor_module/cam_sensor_utils/cam_sensor_cmn_header.h','techpack/camera/include/uapi/media/cam_defs.h','techpack/camera/include/uapi/media/cam_sensor.h']
def load(name):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name(name+'.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
MOCKS=r'''
#define CAM_ERR(...) ((void)0)
#define CAM_DBG(...) ((void)0)
#define CCI_MASTER 1
#define I2C_MASTER 2
#define SPI_MASTER 3
#define GFP_KERNEL 0
#define list_entry(p,t,m) container_of(p,t,m)
#define list_del(p) list_del_init(p)
#define list_for_each_entry_safe(p,t,h,m) for(struct list_head *cur=(h)->next,*next;cur!=(h)&&((next=cur->next),(p)=container_of(cur,__typeof__(*(p)),m),1);cur=next)
static void list_add_tail(struct list_head *n,struct list_head *h){n->prev=h->prev;n->next=h;h->prev->next=n;h->prev=n;}
static int fail_alloc;static unsigned live;
static void *kcalloc(size_t count,size_t bytes,int flags){if(fail_alloc&&!--fail_alloc)return NULL;void *p=calloc(count,bytes);if(p)live++;return p;}
static void *kzalloc(size_t bytes,int flags){return kcalloc(1,bytes,flags);}
static void kfree(void *p){if(p){assert(live);live--;free(p);}}
struct cam_sensor_cci_client {int cci_i2c_master,i2c_freq_mode,sid;};struct i2c_client {int addr;};
struct camera_io_master {int master_type;struct cam_sensor_cci_client *cci_client;struct i2c_client *client;};
struct cam_eeprom_ctrl_t {struct camera_io_master io_master_info;int cci_i2c_master;struct i2c_settings_array wr_settings;struct {unsigned start_address,size,is_valid;}eebin_info;};
enum cam_cci_cmd_type {MSM_CCI_I2C_WRITE_BURST=100,MSM_CCI_I2C_WRITE_SEQ=101};
static unsigned provider_calls;static int provider_error,expected_mode,seen_mode;static unsigned expected_addr,expected_count;static uint32_t expected_data[4],expected_hw_delay,expected_sw_delay;
static int provider(struct cam_sensor_i2c_reg_setting *s,int mode){assert(s&&s->reg_setting&&s->size==expected_count&&s->addr_type==CAMERA_SENSOR_I2C_TYPE_WORD&&s->data_type==CAMERA_SENSOR_I2C_TYPE_BYTE);for(unsigned i=0;i<s->size;i++)assert(s->reg_setting[i].reg_addr==expected_addr&&s->reg_setting[i].reg_data==expected_data[i]&&!s->reg_setting[i].data_mask);assert(s->reg_setting[s->size-1].delay==expected_hw_delay&&s->delay==expected_sw_delay);provider_calls++;seen_mode=mode;assert(mode==expected_mode);return provider_error;}
static int cam_cci_i2c_write_table_cmd(struct camera_io_master *c,struct cam_sensor_i2c_reg_setting *s,enum cam_cci_cmd_type cmd){return provider(s,cmd);}
static int cam_qup_i2c_write_seq(struct camera_io_master *c,struct cam_sensor_i2c_reg_setting *s){return provider(s,200);}
static int cam_qup_i2c_write_burst(struct camera_io_master *c,struct cam_sensor_i2c_reg_setting *s){return provider(s,201);}
static int cam_spi_write_table(struct camera_io_master *c,struct cam_sensor_i2c_reg_setting *s){return provider(s,300);}
static union {max_align_t align;unsigned char bytes[512];} mapped;
static size_t mapped_size=512;
static int cam_mem_get_cpu_buf(int handle,uintptr_t *p,size_t *n){assert(handle==7);*p=(uintptr_t)mapped.bytes;*n=mapped_size;return 0;}
static unsigned command_copies;
static int pico_mem_dup_range(int h,size_t offset,size_t bytes,void **window){uintptr_t p;size_t n;*window=NULL;int rc=cam_mem_get_cpu_buf(h,&p,&n);if(rc)return rc;if(!bytes||offset>n||bytes>n-offset)return -EINVAL;*window=malloc(bytes);if(!*window)return -ENOMEM;memcpy(*window,(void *)(p+offset),bytes);command_copies++;return 0;}
static void vfree(void *window){if(window){assert(command_copies);command_copies--;free(window);}}
'''
MAIN=r'''
static union {max_align_t align;unsigned char bytes[256];} packet_store;static struct cam_packet *packet;static struct cam_cmd_buf_desc *desc;static struct cam_eeprom_ctrl_t c;static struct cam_sensor_cci_client cci;static struct i2c_client client;
static void init(void){assert(!live);memset(&c,0,sizeof(c));memset(mapped.bytes,0,512);memset(packet_store.bytes,0,256);INIT_LIST_HEAD(&c.wr_settings.list_head);c.wr_settings.is_settings_valid=1;c.io_master_info.master_type=CCI_MASTER;c.io_master_info.cci_client=&cci;c.io_master_info.client=&client;packet=(void *)packet_store.bytes;packet->num_cmd_buf=1;desc=(void *)&packet->payload;desc->mem_handle=7;provider_calls=0;provider_error=0;fail_alloc=0;expected_addr=0x200;expected_count=2;expected_data[0]=0xa5;expected_data[1]=0x5a;expected_hw_delay=expected_sw_delay=0;}
static unsigned command(unsigned at,unsigned opcode,unsigned count,unsigned addr){struct cam_cmd_i2c_continuous_wr *wr=(void *)(mapped.bytes+at);wr->header.cmd_type=CAMERA_SENSOR_CMD_TYPE_I2C_CONT_WR;wr->header.op_code=opcode;wr->header.addr_type=CAMERA_SENSOR_I2C_TYPE_WORD;wr->header.data_type=CAMERA_SENSOR_I2C_TYPE_BYTE;wr->header.count=count;wr->reg_addr=addr;for(unsigned i=0;i<count;i++)wr->data_read[i].reg_data=expected_data[i];return sizeof(struct i2c_rdwr_header)+4+count*sizeof(struct cam_cmd_read);}
static unsigned wait_cmd(unsigned at,unsigned op,unsigned delay){struct cam_cmd_unconditional_wait *wait=(void *)(mapped.bytes+at);wait->cmd_type=CAMERA_SENSOR_CMD_TYPE_WAIT;wait->op_code=op;wait->delay=delay;return sizeof(*wait);}
static void clean(void){assert(!delete_eeprom_request(&c.wr_settings)&&!live&&list_empty(&c.wr_settings.list_head)&&!c.wr_settings.is_settings_valid);}
int main(void){
 init();unsigned bytes=command(0,CAMERA_SENSOR_I2C_OP_CONT_WR_SEQN,2,0x200);desc->length=bytes;assert(!cam_eeprom_parse_write_memory_packet(packet,&c)&&live==2&&c.eebin_info.start_address==0x200&&c.eebin_info.size==2);struct i2c_settings_list *node=list_entry(c.wr_settings.list_head.next,struct i2c_settings_list,list);assert(node->i2c_settings.reg_setting[1].reg_data==0x5a&&!node->seq_settings.reg_data);
 expected_mode=MSM_CCI_I2C_WRITE_SEQ;assert(!cam_eeprom_write(&c)&&provider_calls==1&&seen_mode==expected_mode&&!live&&list_empty(&c.wr_settings.list_head));
 init();bytes=command(0,CAMERA_SENSOR_I2C_OP_CONT_WR_BRST,2,0x200);bytes+=wait_cmd(bytes,CAMERA_SENSOR_WAIT_OP_HW_UCND,9);bytes+=wait_cmd(bytes,CAMERA_SENSOR_WAIT_OP_SW_UCND,5);desc->length=bytes;expected_hw_delay=9;expected_sw_delay=5;assert(!cam_eeprom_parse_write_memory_packet(packet,&c)&&live==2);expected_mode=MSM_CCI_I2C_WRITE_BURST;assert(!cam_eeprom_write(&c)&&provider_calls==1&&!live);
 for(unsigned mode=I2C_MASTER;mode<=SPI_MASTER;mode++){for(unsigned op=0;op<2;op++){init();c.io_master_info.master_type=mode;desc->length=command(0,op?CAMERA_SENSOR_I2C_OP_CONT_WR_BRST:CAMERA_SENSOR_I2C_OP_CONT_WR_SEQN,2,0x200);assert(!cam_eeprom_parse_write_memory_packet(packet,&c));expected_mode=mode==SPI_MASTER?300:(op?201:200);assert(!cam_eeprom_write(&c)&&provider_calls==1&&!live);}}
 for(unsigned allocation=1;allocation<=2;allocation++){init();desc->length=command(0,CAMERA_SENSOR_I2C_OP_CONT_WR_SEQN,2,0x200);fail_alloc=allocation;assert(cam_eeprom_parse_write_memory_packet(packet,&c)==-ENOMEM&&!live&&list_empty(&c.wr_settings.list_head));clean();}
 init();desc->length=command(0,255,2,0x200);assert(cam_eeprom_parse_write_memory_packet(packet,&c)==-EINVAL&&!live&&list_empty(&c.wr_settings.list_head));clean();
 init();desc->length=command(0,CAMERA_SENSOR_I2C_OP_CONT_WR_SEQN,2,0x200);((struct cam_cmd_i2c_continuous_wr *)mapped.bytes)->header.data_type=CAMERA_SENSOR_I2C_TYPE_INVALID;assert(cam_eeprom_parse_write_memory_packet(packet,&c)==-EINVAL&&!live);clean();
 init();bytes=command(0,CAMERA_SENSOR_I2C_OP_CONT_WR_SEQN,2,0x200);bytes+=wait_cmd(bytes,CAMERA_SENSOR_WAIT_OP_HW_UCND,3);bytes+=command(bytes,CAMERA_SENSOR_I2C_OP_CONT_WR_BRST,1,0x300);desc->length=bytes;assert(!cam_eeprom_parse_write_memory_packet(packet,&c)&&live==4);node=list_entry(c.wr_settings.list_head.next,struct i2c_settings_list,list);assert(node->i2c_settings.reg_setting[1].delay==3);node=list_entry(node->list.next,struct i2c_settings_list,list);assert(node->i2c_settings.size==1&&node->i2c_settings.reg_setting[0].reg_addr==0x300);clean();
 init();desc->length=wait_cmd(0,CAMERA_SENSOR_WAIT_OP_HW_UCND,1);assert(cam_eeprom_parse_write_memory_packet(packet,&c)==-EINVAL&&!live);clean();
 init();desc->length=command(0,CAMERA_SENSOR_I2C_OP_CONT_WR_SEQN,2,0x200);assert(!cam_eeprom_parse_write_memory_packet(packet,&c));provider_error=-EIO;expected_mode=MSM_CCI_I2C_WRITE_SEQ;assert(cam_eeprom_write(&c)==-EIO&&provider_calls==1&&!live);clean();
 assert(!command_copies);puts("PASS: actual continuous payload/allocator/delay/parser/delete/write/I-O wrapper/CCI-QUP dispatch; UAPI reg table data/types, burst/seq modes, HW/SW delays and subsequent command exactly once, node/table allocation failures, invalid command/types publish nothing, provider error destroys requests, SPI routing");
}
'''
def main():
    common=load('test-pico-camera-hub-registry');extract=load('test-pico-sensor-mono-hook');core=(SOURCE/NAMES[0]).read_text();cmn=(SOURCE/NAMES[4]).read_text()
    enum_names=['camera_sensor_cmd_type','camera_sensor_i2c_op_code','camera_sensor_wait_op_code','camera_sensor_i2c_type','cam_sensor_i2c_cmd_type']
    enums='\n'.join(re.search(r'enum '+n+r' \{.*?\n\};',cmn,re.S).group(0) for n in enum_names)
    structs='\n'.join(re.search(r'struct '+n+r' \{.*?\n\};',cmn,re.S).group(0) for n in ['common_header','cam_sensor_i2c_reg_array','cam_sensor_i2c_reg_setting','cam_sensor_i2c_seq_reg','i2c_settings_list','i2c_settings_array'])
    signatures=['static struct i2c_settings_list *cam_eeprom_get_i2c_ptr(','static int32_t cam_eeprom_handle_continuous_write(','static int32_t cam_eeprom_handle_delay(','static int32_t cam_eeprom_parse_write_memory_packet(','static int32_t delete_eeprom_request(','static int32_t cam_eeprom_write(']
    bodies='\n'.join(extract.function(core[core.rindex(s):] if s.startswith('static int32_t delete_eeprom_request(') else core,s) for s in signatures)
    dispatch=extract.function((SOURCE/NAMES[2]).read_text(),'int32_t cam_cci_i2c_write_continuous_table(')+extract.function((SOURCE/NAMES[3]).read_text(),'int32_t cam_qup_i2c_write_continuous_table(')+extract.function((SOURCE/NAMES[1]).read_text(),'int32_t camera_io_dev_write_continuous(')
    code='#include <stdint.h>\n#include <stddef.h>\n#include <string.h>\n#include <cam_defs.h>\n#include <cam_sensor.h>\n'+common.HARNESS.split('/* OWNED_SUBDEVICE_MOCKS */')[0]+enums+structs+MOCKS+dispatch+bodies+MAIN
    out=BASE/'out/phoenix-kernel-recovery/eeprom-write-payload-tests';out.mkdir(exist_ok=True);(out/'harness.c').write_text(code)
    subprocess.run(['gcc','-std=gnu11','-g','-O1','-pthread','-fsanitize=address,undefined','-fno-omit-frame-pointer','-I'+str(SOURCE/'techpack/camera/include/uapi/media'),'-I'+str(SOURCE/'techpack/camera/include/uapi'),str(out/'harness.c'),'-o',str(out/'test')],check=True)
    r=subprocess.run([str(out/'test')],capture_output=True,text=True,timeout=5);report={'sources':{n:hashlib.sha256((SOURCE/n).read_bytes()).hexdigest() for n in NAMES},'harness_sha256':hashlib.sha256(code.encode()).hexdigest(),'exit_code':r.returncode,'stdout':r.stdout,'stderr':r.stderr,'sanitizers':['AddressSanitizer','UndefinedBehaviorSanitizer'],'scope':'Actual allocator/payload/delay/nested parser/delete/write and I/O/CCI/QUP dispatch bodies with real UAPI/native register/list/types/enums; allocation/mapping/list APIs and lower providers/CCI enum values modeled, no bus/erase/eebin policy or factory EEPROM behavior/hardware proof','device_modified':False};(out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));raise SystemExit(r.returncode)
if __name__=='__main__':main()
