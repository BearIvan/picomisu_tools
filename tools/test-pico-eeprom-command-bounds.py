"""Actual nested EEPROM read/write loops and native memory-map decoder."""
from pathlib import Path
import hashlib,json,re,subprocess,importlib.util
BASE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro');SOURCE=BASE/'source/phoenix-kernel-recovery';D='techpack/camera/drivers/cam_sensor_module/cam_eeprom/'
NAMES=[D+n for n in ['cam_eeprom_core.c','cam_eeprom_dev.h']]+['techpack/camera/include/uapi/media/'+n for n in ['cam_defs.h','cam_sensor.h']]+['techpack/camera/drivers/cam_sensor_module/cam_sensor_utils/cam_sensor_cmn_header.h']
def load(name):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name(name+'.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
MOCKS=r'''
#define CAM_ERR(...) ((void)0)
#define CAM_DBG(...) ((void)0)
#define CCI_MASTER 1
#define I2C_MASTER 2
#define SPI_MASTER 3
#define U32_MAX UINT32_MAX
struct cam_sensor_cci_client {int cci_i2c_master,i2c_freq_mode,sid;};struct i2c_client {int addr;};
struct i2c_settings_array {int unused;};struct cam_sensor_power_ctrl_t {int unused;};struct cam_eeprom_soc_private {struct cam_sensor_power_ctrl_t power_info;};
struct cam_eeprom_ctrl_t {struct cam_eeprom_memory_block_t cal_data;struct {void *soc_private;}soc_info;struct {int master_type;struct cam_sensor_cci_client *cci_client;struct i2c_client *client;}io_master_info;int cci_i2c_master;struct i2c_settings_array wr_settings;};
static union {max_align_t align;unsigned char bytes[512];} mapped;
static size_t mapped_size=512;static int map_error,slave_error,helper_error;static unsigned helper_calls,power_calls,power_bytes,forced_progress=20;
static int cam_mem_get_cpu_buf(int h,uintptr_t *addr,size_t *n){assert(h==7);if(map_error)return map_error;*addr=(uintptr_t)mapped.bytes;*n=mapped_size;return 0;}
static void *vzalloc(size_t n){return calloc(1,n);}
static unsigned command_copies;static bool overwrite_source;
static int pico_mem_dup_range(int h,size_t offset,size_t bytes,void **window){uintptr_t p;size_t n;*window=NULL;int rc=cam_mem_get_cpu_buf(h,&p,&n);if(rc)return rc;if(!bytes||offset>n||bytes>n-offset)return -EINVAL;*window=malloc(bytes);if(!*window)return -ENOMEM;memcpy(*window,(void *)(p+offset),bytes);command_copies++;if(overwrite_source)memset((void *)(p+offset),0xff,bytes);return 0;}
static void vfree(void *window){if(window){assert(command_copies);command_copies--;free(window);}}
static int cam_eeprom_update_slaveInfo(struct cam_eeprom_ctrl_t *c,void *cmd){return slave_error;}
static bool append_calls[8];
static int pico_eeprom_update_power_settings(void *cmd,unsigned bytes,struct cam_sensor_power_ctrl_t *power,size_t remaining,bool append){assert(power_calls<8);append_calls[power_calls++]=append;power_bytes=bytes;assert(bytes==remaining);return 0;}
static int cam_eeprom_handle_continuous_write(struct cam_eeprom_ctrl_t *c,struct cam_cmd_i2c_continuous_wr *cmd,struct i2c_settings_array *settings,uint32_t *n,uint32_t *off,struct list_head **list){helper_calls++;*n=forced_progress;return helper_error;}
static int cam_eeprom_handle_delay(uint32_t **cmd,uint16_t op,struct i2c_settings_array *settings,uint32_t off,uint32_t *n,struct list_head *list,size_t remaining){helper_calls++;*n=forced_progress;return helper_error;}
'''
MAIN=r'''
static union {max_align_t align;unsigned char bytes[256];} packet_memory;
static struct cam_eeprom_ctrl_t c;static struct cam_eeprom_soc_private private;static struct cam_sensor_cci_client cci;static struct i2c_client client;
static struct cam_packet *packet;static struct cam_cmd_buf_desc *desc;
static void init(void){memset(&c,0,sizeof(c));memset(mapped.bytes,0,512);memset(packet_memory.bytes,0,256);c.soc_info.soc_private=&private;c.io_master_info.master_type=CCI_MASTER;c.io_master_info.cci_client=&cci;c.io_master_info.client=&client;c.cci_i2c_master=2;packet=(void *)packet_memory.bytes;packet->num_cmd_buf=1;desc=(void *)&packet->payload;desc->mem_handle=7;mapped_size=512;map_error=slave_error=helper_error=0;forced_progress=sizeof(struct cam_cmd_i2c_continuous_wr);helper_calls=power_calls=power_bytes=0;}
static int read_parse(void){int rc=cam_eeprom_init_pkt_parser(&c,packet);free(c.cal_data.map);c.cal_data.map=NULL;assert(!command_copies);return rc;}
int main(void){
 init();struct cam_cmd_i2c_info *info=(void *)mapped.bytes;info->cmd_type=CAMERA_SENSOR_CMD_TYPE_I2C_INFO;info->slave_addr=0x40;desc->length=sizeof(*info);assert(!cam_eeprom_parse_write_memory_packet(packet,&c)&&cci.sid==0x20&&cci.cci_i2c_master==2);
 desc->offset=1;assert(cam_eeprom_parse_write_memory_packet(packet,&c)==-EINVAL);desc->offset=0;desc->length=sizeof(*info)-1;assert(cam_eeprom_parse_write_memory_packet(packet,&c)==-EINVAL);
 init();struct common_header *head=(void *)mapped.bytes;head->cmd_type=255;desc->length=sizeof(*head);assert(cam_eeprom_parse_write_memory_packet(packet,&c)==-EINVAL);assert(read_parse()==-EINVAL);
 init();struct cam_cmd_i2c_continuous_wr *write=(void *)mapped.bytes;write->header.cmd_type=CAMERA_SENSOR_CMD_TYPE_I2C_CONT_WR;write->header.count=2;desc->length=sizeof(*write);assert(cam_eeprom_parse_write_memory_packet(packet,&c)==-EINVAL&&!helper_calls);
 write->header.count=1;assert(!cam_eeprom_parse_write_memory_packet(packet,&c)&&helper_calls==1);forced_progress=0;assert(cam_eeprom_parse_write_memory_packet(packet,&c)==-EINVAL);forced_progress=sizeof(*write)+4;assert(cam_eeprom_parse_write_memory_packet(packet,&c)==-EINVAL);forced_progress=sizeof(*write);helper_error=-ENOMEM;assert(cam_eeprom_parse_write_memory_packet(packet,&c)==-ENOMEM);
 init();struct cam_cmd_i2c_continuous_rd *rd=(void *)mapped.bytes;rd->header.cmd_type=CAMERA_SENSOR_CMD_TYPE_I2C_CONT_RD;rd->header.count=4;rd->reg_addr=0x100;desc->length=sizeof(struct common_header);assert(read_parse()==-EINVAL);desc->length=sizeof(*rd);assert(!read_parse()&&c.cal_data.num_data==4&&c.cal_data.num_map==1);
 init();info=(void *)mapped.bytes;info->cmd_type=CAMERA_SENSOR_CMD_TYPE_I2C_INFO;info->slave_addr=0x50;rd=(void *)(mapped.bytes+sizeof(*info));rd->header.cmd_type=CAMERA_SENSOR_CMD_TYPE_I2C_CONT_RD;rd->header.count=6;rd->reg_addr=0x300;desc->length=sizeof(*info)+sizeof(*rd);assert(!cam_eeprom_init_pkt_parser(&c,packet)&&c.cal_data.map[0].saddr==0x50&&c.cal_data.map[0].mem.addr==0x300&&c.cal_data.num_data==6);free(c.cal_data.map);c.cal_data.map=NULL;
 slave_error=-ENXIO;assert(read_parse()==-ENXIO);slave_error=0;struct cam_cmd_power *power=(void *)(mapped.bytes+sizeof(*info));power->cmd_type=CAMERA_SENSOR_CMD_TYPE_PWR_UP;power->count=1;desc->length=sizeof(*info)+sizeof(*power);assert(!read_parse()&&power_calls==1&&power_bytes==sizeof(*power));
 init();struct cam_cmd_conditional_wait *wait=(void *)mapped.bytes;wait->cmd_type=CAMERA_SENSOR_CMD_TYPE_WAIT;wait->op_code=CAMERA_SENSOR_WAIT_OP_COND;wait->reg_addr=0x123;wait->reg_data=7;wait->timeout=20;desc->length=sizeof(struct cam_cmd_unconditional_wait);assert(read_parse()==-EINVAL);desc->length=sizeof(*wait);assert(!cam_eeprom_init_pkt_parser(&c,packet)&&c.cal_data.map[0].poll.addr==0x123&&c.cal_data.map[0].poll.data==7);free(c.cal_data.map);c.cal_data.map=NULL;
 init();desc->length=sizeof(struct common_header);map_error=-ENOENT;assert(read_parse()==-ENOENT&&cam_eeprom_parse_write_memory_packet(packet,&c)==-ENOENT);
 struct cam_eeprom_memory_map_t map[1]={0};struct cam_eeprom_memory_block_t block={.map=map};int index=-1;uint32_t consumed=0;assert(cam_eeprom_parse_memory_map(&block,mapped.bytes,8,&consumed,&index,8)==-EINVAL);
 init();info=(void *)(mapped.bytes+4);info->cmd_type=CAMERA_SENSOR_CMD_TYPE_I2C_INFO;info->slave_addr=0x60;desc->offset=4;desc->length=sizeof(*info);overwrite_source=true;assert(!cam_eeprom_parse_write_memory_packet(packet,&c)&&cci.sid==0x30&&!command_copies);overwrite_source=false;
 init();head=(void *)mapped.bytes;head->cmd_type=255;desc->length=sizeof(*head);packet->num_cmd_buf=2;desc[1]=desc[0];desc[0].length=0;assert(cam_eeprom_parse_write_memory_packet(packet,&c)==-EINVAL&&!command_copies);
 init();info=(void *)mapped.bytes;info->cmd_type=CAMERA_SENSOR_CMD_TYPE_I2C_INFO;info->slave_addr=0x70;desc->length=sizeof(*info);packet->num_cmd_buf=2;desc[1]=desc[0];desc[1].offset=mapped_size;assert(cam_eeprom_parse_write_memory_packet(packet,&c)==-EINVAL&&!command_copies);assert(read_parse()==-EINVAL&&!command_copies);
 init();power=(void *)mapped.bytes;power->cmd_type=CAMERA_SENSOR_CMD_TYPE_PWR_UP;power->count=1;struct cam_cmd_power *down=(void *)(mapped.bytes+sizeof(*power));down->cmd_type=CAMERA_SENSOR_CMD_TYPE_PWR_DOWN;down->count=1;packet->num_cmd_buf=2;desc->length=sizeof(*power);desc[1]=desc[0];desc[1].offset=sizeof(*power);assert(!read_parse()&&power_calls==2&&!append_calls[0]&&append_calls[1]&&!command_copies);
 puts("PASS: actual nested read/write loops and memory-map decoder, real UAPI/enums/types; unknown WRITE terminates, alignment and descriptor-length windows, continuous count bound, callback zero/oversized progress/error, valid info/read/power/conditional-wait, truncated conditional wait, negative map index, mapping error");
}
'''
def main():
    common=load('test-pico-camera-hub-registry');extract=load('test-pico-sensor-mono-hook');core=(SOURCE/NAMES[0]).read_text();header=(SOURCE/NAMES[1]).read_text();cmn=(SOURCE/NAMES[4]).read_text()
    structs='\n'.join(re.search(r'struct '+n+r' \{.*?\n\};',header,re.S).group(0) for n in ['cam_eeprom_map_t','cam_eeprom_memory_map_t','cam_eeprom_memory_block_t'])+re.search(r'struct common_header \{.*?\n\};',cmn,re.S).group(0)
    enums='\n'.join(b for b in re.findall(r'enum \w+ \{.*?\n\};',cmn,re.S) if 'CAMERA_SENSOR_CMD_TYPE_I2C_INFO' in b or 'CAMERA_SENSOR_WAIT_OP_COND' in b)
    defines='\n'.join(line for line in header.splitlines() if line.startswith(('#define MSM_EEPROM_MEMORY_MAP_MAX_SIZE ', '#define MSM_EEPROM_MAX_MEM_MAP_CNT ')))
    bodies='\n'.join(extract.function(core,s) for s in ['static int32_t cam_eeprom_parse_memory_map(','static int32_t cam_eeprom_parse_write_memory_packet(','static int32_t cam_eeprom_init_pkt_parser('])
    code='#include <stdint.h>\n#include <stddef.h>\n#include <cam_defs.h>\n#include <cam_sensor.h>\n#include <string.h>\n'+common.HARNESS.split('/* OWNED_SUBDEVICE_MOCKS */')[0]+defines+'\n'+structs+enums+MOCKS+bodies+MAIN
    out=BASE/'out/phoenix-kernel-recovery/eeprom-command-bounds-tests';out.mkdir(exist_ok=True);(out/'harness.c').write_text(code)
    subprocess.run(['gcc','-std=gnu11','-g','-O1','-pthread','-fsanitize=address,undefined','-fno-omit-frame-pointer','-I'+str(SOURCE/'techpack/camera/include/uapi/media'),'-I'+str(SOURCE/'techpack/camera/include/uapi'),str(out/'harness.c'),'-o',str(out/'test')],check=True)
    r=subprocess.run([str(out/'test')],capture_output=True,text=True,timeout=5);report={'sources':{n:hashlib.sha256((SOURCE/n).read_bytes()).hexdigest() for n in NAMES},'harness_sha256':hashlib.sha256(code.encode()).hexdigest(),'exit_code':r.returncode,'stdout':r.stdout,'stderr':r.stderr,'sanitizers':['AddressSanitizer','UndefinedBehaviorSanitizer'],'scope':'Actual nested read/write parser and read memory-map decoder with native map/common-header/enums/macros and public command/descriptor UAPI; lower mapping/slave/power/continuous-write/delay helpers modeled; descriptor-table packet validation, continuous payload copy/list/delay, mapping ownership/providers/runtime pending','device_modified':False};(out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));raise SystemExit(r.returncode)
if __name__=='__main__':main()
