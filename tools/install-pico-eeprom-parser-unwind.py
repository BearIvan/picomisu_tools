"""Keep EEPROM operation errno and unwind read/write transaction resources."""
from pathlib import Path
import hashlib,json,re
SOURCE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro/source/phoenix-kernel-recovery');D='techpack/camera/drivers/cam_sensor_module/cam_eeprom/'
OLD='964237b3784b89011d25abefc74860919474b4fbd55338f9781749a10e800f7d'
def replace(text,old,new):
    if text.count(old)!=1:raise RuntimeError('Unexpected parser anchor: '+old)
    return text.replace(old,new)
def main():
    root=Path(__file__).resolve().parent.parent;rp=root/'reports/kernel-source/recovery-20261003/eeprom-parser-unwind-hooks.json';name=D+'cam_eeprom_core.c';path=SOURCE/name;data=path.read_bytes();actual=hashlib.sha256(data).hexdigest();prior=json.loads(rp.read_text()) if rp.exists() else {}
    if actual==OLD:
        text=data.decode()
        text=replace(text,'#define MAX_READ_SIZE  0x7FFFF','#define MAX_READ_SIZE  0x7FFFF\n\nstatic int32_t delete_eeprom_request(struct i2c_settings_array *i2c_array);')
        text=replace(text,'\te_ctrl->pico_transaction_cleanup_pending = false;','\tif (e_ctrl->wr_settings.is_settings_valid)\n\t\tdelete_eeprom_request(&e_ctrl->wr_settings);\n\te_ctrl->pico_transaction_cleanup_pending = false;')
        start=text.index('static int32_t cam_eeprom_pkt_parse(');end=text.index('\nvoid cam_eeprom_shutdown(',start);body=text[start:end]
        body=replace(body,'\tint32_t                         rc = 0;','\tint32_t                         rc = 0;\n\tint cleanup_rc;')
        body=replace(body,'"Failed in parsing the pkt");\n\t\t\treturn rc;','"Failed in parsing the pkt");\n\t\t\tgoto memdata_free;')
        begin=body.index('\n\t\trc = cam_eeprom_get_cal_data(e_ctrl, csl_packet);')+1;finish=body.index('\n\t\tbreak;',begin)+1
        body=body[:begin]+'''\t\trc = cam_eeprom_get_cal_data(e_ctrl, csl_packet);
\t\tcleanup_rc = cam_eeprom_power_down(e_ctrl);
\t\tif (!rc)
\t\t\trc = cleanup_rc;
\t\tif (cleanup_rc)
\t\t\tgoto memdata_free;
\t\tpico_eeprom_free_transaction(e_ctrl);
\t\te_ctrl->cam_eeprom_state = CAM_EEPROM_ACQUIRE;
'''+body[finish:]
        start_write=body.index('\tcase CAM_EEPROM_WRITE:');end_write=body.index('\tdefault:',start_write);write=body[start_write:end_write]
        write=write.replace('\t\t\treturn rc;','\t\t\tgoto power_down;')
        # A write-parse failure has no powered device yet but may own list/settings.
        write=replace(write,'rc = cam_eeprom_parse_write_memory_packet(\n\t\t\tcsl_packet, e_ctrl);\n\t\tif (rc < 0) {\n\t\t\tCAM_ERR(CAM_EEPROM, "Failed: rc : %d", rc);\n\t\t\tgoto power_down;','rc = cam_eeprom_parse_write_memory_packet(\n\t\t\tcsl_packet, e_ctrl);\n\t\tif (rc < 0) {\n\t\t\tCAM_ERR(CAM_EEPROM, "Failed: rc : %d", rc);\n\t\t\tgoto memdata_free;')
        write=replace(write,'\t\tbreak;\n\t}', '\t\tpico_eeprom_free_transaction(e_ctrl);\n\t\te_ctrl->cam_eeprom_state = CAM_EEPROM_ACQUIRE;\n\t\tbreak;\n\t}')
        body=body[:start_write]+write+body[end_write:]
        tail=body.index('power_down:\n');body=body[:tail]+'''power_down:
\tcleanup_rc = cam_eeprom_power_down(e_ctrl);
\tif (!rc)
\t\trc = cleanup_rc;
memdata_free:
error:
\tif (e_ctrl->pico_core_powered || e_ctrl->pico_io_initialized) {
\t\te_ctrl->pico_transaction_cleanup_pending = true;
\t\te_ctrl->cam_eeprom_state = CAM_EEPROM_CONFIG;
\t\treturn rc;
\t}
\tpico_eeprom_free_transaction(e_ctrl);
\te_ctrl->cam_eeprom_state = CAM_EEPROM_ACQUIRE;
\treturn rc;
}
'''
        text=text[:start]+body+text[end:]
        # Normalize pointer-clearing indentation added alongside existing frees.
        text=re.sub(r'(?m)^(\t+)vfree\(e_ctrl->cal_data\.(mapdata|map)\);\n\te_ctrl->cal_data\.\2 = NULL;',lambda m:m.group(1)+'vfree(e_ctrl->cal_data.'+m.group(2)+');\n'+m.group(1)+'e_ctrl->cal_data.'+m.group(2)+' = NULL;',text)
        data=text.encode();path.write_bytes(data)
    elif actual!=prior.get('sources',{}).get(name):raise RuntimeError('Preserve differing EEPROM core')
    text=data.decode()
    bad='\t\t\trc = cam_eeprom_get_cal_data(e_ctrl, csl_packet);\n\t\tcleanup_rc = cam_eeprom_power_down(e_ctrl);\n\t\tif (!rc)\n\t\t\trc = cleanup_rc;\n\t\tif (cleanup_rc)\n\t\t\tgoto memdata_free;\n\t\tpico_eeprom_free_transaction(e_ctrl);\n\t\te_ctrl->cam_eeprom_state = CAM_EEPROM_ACQUIRE;\n\t\tbreak;'
    if bad in text:
        text=replace(text,bad,'\t\t\trc = cam_eeprom_get_cal_data(e_ctrl, csl_packet);\n\t\t\tvfree(e_ctrl->cal_data.mapdata);\n\t\t\te_ctrl->cal_data.mapdata = NULL;\n\t\t\tvfree(e_ctrl->cal_data.map);\n\t\t\te_ctrl->cal_data.map = NULL;\n\t\t\te_ctrl->cal_data.num_data = 0;\n\t\t\te_ctrl->cal_data.num_map = 0;\n\t\t\tCAM_DBG(CAM_EEPROM, "Returning the data using kernel probe");\n\t\t\tbreak;')
        begin=text.index('\n\t\trc = cam_eeprom_get_cal_data(e_ctrl, csl_packet);')+1;end=text.index('\n\t\tbreak;',begin)+1
        text=text[:begin]+'\t\trc = cam_eeprom_get_cal_data(e_ctrl, csl_packet);\n\t\tcleanup_rc = cam_eeprom_power_down(e_ctrl);\n\t\tif (!rc)\n\t\t\trc = cleanup_rc;\n\t\tif (cleanup_rc)\n\t\t\tgoto memdata_free;\n\t\tpico_eeprom_free_transaction(e_ctrl);\n\t\te_ctrl->cam_eeprom_state = CAM_EEPROM_ACQUIRE;\n'+text[end:]
    old='"failed: eeprom dt parse rc %d", rc);\n\t\treturn rc;';new='"failed: eeprom dt parse rc %d", rc);\n\t\tgoto data_mem_free;'
    if old in text:text=replace(text,old,new)
    start=text.index('static int32_t cam_eeprom_pkt_parse(');end=text.index('\nvoid cam_eeprom_shutdown(',start);body=text[start:end].replace('\tstruct cam_sensor_power_ctrl_t *power_info = &soc_private->power_info;\n','');text=text[:start]+body+text[end:];data=text.encode();path.write_bytes(data)
    report={'sources':{name:hashlib.sha256(data).hexdigest()},'preimage':OLD,'scope':'Userspace read/write transaction orchestrator preserves primary errno, powers down on erase/write errors, cleans settings/list after successful cleanup, retains allocations while phases pending; nested payload parsers/provider partial effects/remove/runtime pending','device_modified':False};rp.write_text(json.dumps(report,indent=2)+'\n')
    for filename in ['peer-acquire-capture-hooks.json','eeprom-acquire-retry-hooks.json','eeprom-shutdown-retry-hooks.json','eeprom-power-retry-hooks.json']:
        p=rp.parent/filename;obj=json.loads(p.read_text());obj['sources'][name]=report['sources'][name];obj['eeprom_parser_unwind_hooks']=str(rp);p.write_text(json.dumps(obj,indent=2)+'\n')
    print(json.dumps(report,indent=2))
if __name__=='__main__':main()
