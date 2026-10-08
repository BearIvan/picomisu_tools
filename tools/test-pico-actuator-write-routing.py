"""Exercise actual actuator caller and native CCI/QUP dispatch bodies."""
from pathlib import Path
import hashlib,json,subprocess
import importlib.util
def load(name):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name(name+'.py')); m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
payload=load('test-pico-eeprom-write-payload')
BASE=payload.BASE;SOURCE=payload.SOURCE
NAMES=['techpack/camera/drivers/cam_sensor_module/cam_actuator/cam_actuator_core.c']+payload.NAMES[1:]
def main():
    extract=load('test-pico-sensor-mono-hook');common=load('test-pico-camera-hub-registry')
    # Reuse only the native UAPI/type extraction, not EEPROM functions or cases.
    import re
    cmn=(SOURCE/NAMES[4]).read_text()
    enums='\n'.join(re.search(r'enum '+n+r' \{.*?\n\};',cmn,re.S).group(0) for n in ['camera_sensor_cmd_type','camera_sensor_i2c_op_code','camera_sensor_wait_op_code','camera_sensor_i2c_type','cam_sensor_i2c_cmd_type'])
    structs='\n'.join(re.search(r'struct '+n+r' \{.*?\n\};',cmn,re.S).group(0) for n in ['common_header','cam_sensor_i2c_reg_array','cam_sensor_i2c_reg_setting','cam_sensor_i2c_seq_reg','i2c_settings_list','i2c_settings_array'])
    mocks=payload.MOCKS.split('static union {max_align_t')[0]+r'''
static int camera_io_dev_write(struct camera_io_master *io,struct cam_sensor_i2c_reg_setting *s){return provider(s,400);}
static unsigned polls;
static int camera_io_dev_poll(struct camera_io_master *io,uint32_t addr,uint16_t data,uint16_t mask,enum camera_sensor_i2c_type at,enum camera_sensor_i2c_type dt,uint32_t delay){polls++;return provider_error;}
'''
    dispatch=extract.function((SOURCE/NAMES[2]).read_text(),'int32_t cam_cci_i2c_write_continuous_table(')+extract.function((SOURCE/NAMES[3]).read_text(),'int32_t cam_qup_i2c_write_continuous_table(')+extract.function((SOURCE/NAMES[1]).read_text(),'int32_t camera_io_dev_write_continuous(')
    caller=extract.function((SOURCE/NAMES[0]).read_text(),'static int32_t cam_actuator_i2c_modes_util(')
    cases=r'''
int main(void){
struct cam_sensor_i2c_reg_array regs[2]={{0}};struct i2c_settings_list node={0};struct camera_io_master io={0};
expected_addr=0x200;expected_count=2;expected_data[0]=0xa5;expected_data[1]=0x5a;
for(unsigned i=0;i<2;i++){regs[i].reg_addr=expected_addr;regs[i].reg_data=expected_data[i];}
node.i2c_settings.reg_setting=regs;node.i2c_settings.size=2;node.i2c_settings.addr_type=CAMERA_SENSOR_I2C_TYPE_WORD;node.i2c_settings.data_type=CAMERA_SENSOR_I2C_TYPE_BYTE;
for(unsigned master=CCI_MASTER;master<=SPI_MASTER;master++){
 io.master_type=master;
 for(unsigned burst=0;burst<2;burst++){
  node.op_code=burst?CAM_SENSOR_I2C_WRITE_BURST:CAM_SENSOR_I2C_WRITE_SEQ;
  expected_mode=master==CCI_MASTER?(burst?MSM_CCI_I2C_WRITE_BURST:MSM_CCI_I2C_WRITE_SEQ):master==I2C_MASTER?(burst?201:200):300;
  provider_error=0;provider_calls=0;assert(!cam_actuator_i2c_modes_util(&io,&node));assert(provider_calls==1);
  provider_error=-EIO;provider_calls=0;assert(cam_actuator_i2c_modes_util(&io,&node)==-EIO&&provider_calls==1);
 }
 node.op_code=CAM_SENSOR_I2C_WRITE_RANDOM;expected_mode=400;provider_error=0;provider_calls=0;assert(!cam_actuator_i2c_modes_util(&io,&node)&&provider_calls==1);
 provider_error=-EREMOTEIO;assert(cam_actuator_i2c_modes_util(&io,&node)==-EREMOTEIO);
 node.op_code=CAM_SENSOR_I2C_POLL;polls=0;provider_error=0;assert(!cam_actuator_i2c_modes_util(&io,&node)&&polls==2);
 polls=0;provider_error=-ETIMEDOUT;assert(cam_actuator_i2c_modes_util(&io,&node)==-ETIMEDOUT&&polls==1);
}
puts("PASS: actual actuator mode caller and CCI/QUP/SPI continuous dispatch; sequential/burst calls exactly once, unchanged payload, provider errors, random/poll regression");
}
'''
    code='#include <stdint.h>\n#include <stddef.h>\n#include <string.h>\n#include <cam_defs.h>\n#include <cam_sensor.h>\n'+common.HARNESS.split('/* OWNED_SUBDEVICE_MOCKS */')[0]+enums+structs+mocks+dispatch+caller+cases
    out=BASE/'out/phoenix-kernel-recovery/actuator-write-routing-tests';out.mkdir(exist_ok=True);(out/'harness.c').write_text(code)
    subprocess.run(['gcc','-std=gnu11','-g','-O1','-pthread','-fsanitize=address,undefined','-fno-omit-frame-pointer','-I'+str(SOURCE/'techpack/camera/include/uapi/media'),'-I'+str(SOURCE/'techpack/camera/include/uapi'),str(out/'harness.c'),'-o',str(out/'test')],check=True)
    r=subprocess.run([str(out/'test')],capture_output=True,text=True,timeout=5)
    report={'sources':{n:hashlib.sha256((SOURCE/n).read_bytes()).hexdigest() for n in NAMES},'harness_sha256':hashlib.sha256(code.encode()).hexdigest(),'exit_code':r.returncode,'stdout':r.stdout,'stderr':r.stderr,'scope':'Actual actuator mode caller and native I/O/CCI/QUP dispatch; real UAPI/settings/op enums; bus providers and CCI command enum values modeled; physical bus/packet/per-frame lifecycle/factory behavior pending','device_modified':False}
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));raise SystemExit(r.returncode)
if __name__=='__main__':main()
