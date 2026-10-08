"""Bound EEPROM nested descriptor windows and parser progress."""
from pathlib import Path
import hashlib,json,re
SOURCE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro/source/phoenix-kernel-recovery');D='techpack/camera/drivers/cam_sensor_module/cam_eeprom/'
OLD='f8185264ace5706b3727138940a00db0348bce2a47cc1dcef841a3a111e6ba97'
def replace(text,old,new):
    if text.count(old)!=1:raise RuntimeError('Unexpected command bounds anchor: '+old)
    return text.replace(old,new)
def main():
    root=Path(__file__).resolve().parent.parent;rp=root/'reports/kernel-source/recovery-20261003/eeprom-command-bounds-hooks.json';name=D+'cam_eeprom_core.c';path=SOURCE/name;data=path.read_bytes();actual=hashlib.sha256(data).hexdigest();previous=json.loads(rp.read_text()) if rp.exists() else {}
    if actual==OLD:
        text=data.decode()
        start=text.index('static int32_t cam_eeprom_parse_memory_map(');end=text.index('\nstatic struct i2c_settings_list',start);body=text[start:end]
        body=replace(body,'else if (cmm_hdr->cmd_type == CAMERA_SENSOR_CMD_TYPE_WAIT)\n\t\tvalidate_size = sizeof(struct cam_cmd_unconditional_wait);','else if (cmm_hdr->cmd_type == CAMERA_SENSOR_CMD_TYPE_WAIT)\n\t\tvalidate_size = generic_op_code == CAMERA_SENSOR_WAIT_OP_COND ?\n\t\t\tsizeof(struct cam_cmd_conditional_wait) : sizeof(struct cam_cmd_unconditional_wait);')
        body=replace(body,'if (remain_buf_len < validate_size ||','if (*num_map < 0 || remain_buf_len < validate_size ||');text=text[:start]+body+text[end:]
        for signature in ['static int32_t cam_eeprom_parse_write_memory_packet(', 'static int32_t cam_eeprom_init_pkt_parser(']:
            start=text.index(signature);end=text.index('\n/**',start);body=text[start:end]
            body=replace(body,'\t\tif (!total_cmd_buf_in_bytes)\n\t\t\tcontinue;','\t\tif (!total_cmd_buf_in_bytes)\n\t\t\tcontinue;\n\t\tif ((cmd_desc[i].offset & 3) || (total_cmd_buf_in_bytes & 3)) {\n\t\t\trc = -EINVAL;\n\t\t\tgoto end;\n\t\t}')
            # Window is descriptor length, not unused trailing mapped bytes.
            begin=body.index('\t\tif (total_cmd_buf_in_bytes > remain_len)');finish=body.index('\n\t\t}',begin)+len('\n\t\t}')
            body=body[:finish]+'\n\t\tremain_len = total_cmd_buf_in_bytes;'+body[finish:]
            body=replace(body,'\t\twhile (processed_cmd_buf_in_bytes < total_cmd_buf_in_bytes) {','\t\twhile (processed_cmd_buf_in_bytes < total_cmd_buf_in_bytes) {\n\t\t\tcmd_length_in_bytes = 0;')
            pattern=r'(?m)^(\t+)processed_cmd_buf_in_bytes \+=\n\1\tcmd_length_in_bytes;'
            def guard(m):
                tabs=m.group(1)
                return tabs+'if (rc || !cmd_length_in_bytes || (cmd_length_in_bytes & 3) ||\n'+tabs+'\tcmd_length_in_bytes > total_cmd_buf_in_bytes - processed_cmd_buf_in_bytes) {\n'+tabs+'\tif (!rc) rc = -EINVAL;\n'+tabs+'\tgoto end;\n'+tabs+'}\n'+m.group(0)
            body,n=re.subn(pattern,guard,body)
            if n!=3:raise RuntimeError('Unexpected progress sites: '+signature+' '+str(n))
            if 'parse_write' in signature:
                body=replace(body,'cmm_hdr->cmd_type);\n\t\t\t\trc = -EINVAL;\n\t\t\t\tbreak;','cmm_hdr->cmd_type);\n\t\t\t\trc = -EINVAL;\n\t\t\t\tgoto end;')
                anchor='\n\t\t\t\tCAM_DBG(CAM_EEPROM,\n\t\t\t\t\t"CAMERA_SENSOR_CMD_TYPE_I2C_CONT_WR");'
                bounds='''
\t\t\t\tif (!cam_cmd_i2c_continuous_wr->header.count ||
\t\t\t\t\tcam_cmd_i2c_continuous_wr->header.count >
\t\t\t\t\t((remain_len - processed_cmd_buf_in_bytes -
\t\t\t\t\t  sizeof(struct i2c_rdwr_header) - sizeof(uint32_t)) /
\t\t\t\t\t sizeof(struct cam_cmd_read))) {
\t\t\t\t\trc = -EINVAL;
\t\t\t\t\tgoto end;
\t\t\t\t}
'''
                body=replace(body,anchor,bounds+anchor)
            else:
                body=replace(body,'\t\t\t\tmap[num_map + 1].saddr = i2c_info->slave_addr;','\t\t\t\tif (num_map + 1 >= MSM_EEPROM_MAX_MEM_MAP_CNT * MSM_EEPROM_MEMORY_MAP_MAX_SIZE) {rc = -EINVAL; goto end;}\n\t\t\t\tmap[num_map + 1].saddr = i2c_info->slave_addr;')
                body=replace(body,'cmd_length_in_bytes = total_cmd_buf_in_bytes;','cmd_length_in_bytes = total_cmd_buf_in_bytes - processed_cmd_buf_in_bytes;')
            text=text[:start]+body+text[end:]
        data=text.encode();path.write_bytes(data)
    elif actual!=previous.get('sources',{}).get(name):raise RuntimeError('Preserve differing EEPROM core')
    report={'sources':{name:hashlib.sha256(data).hexdigest()},'preimage':OLD,'scope':'Actual nested read/write parsers use aligned descriptor windows and checked progress; unknown write opcode terminates; continuous count bound, conditional wait/map index bounds; continuous payload copy/list/error and mapping ownership still pending','device_modified':False};rp.write_text(json.dumps(report,indent=2)+'\n')
    for filename in ['peer-acquire-capture-hooks.json','eeprom-acquire-retry-hooks.json','eeprom-shutdown-retry-hooks.json','eeprom-power-retry-hooks.json','eeprom-parser-unwind-hooks.json']:
        p=rp.parent/filename;obj=json.loads(p.read_text());obj['sources'][name]=report['sources'][name];obj['eeprom_command_bounds_hooks']=str(rp);p.write_text(json.dumps(obj,indent=2)+'\n')
    print(json.dumps(report,indent=2))
if __name__=='__main__':main()
