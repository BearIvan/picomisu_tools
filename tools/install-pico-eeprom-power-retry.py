"""EEPROM core/I-O ownership phases and transaction cleanup retention."""
from pathlib import Path
import hashlib,json
SOURCE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro/source/phoenix-kernel-recovery');D='techpack/camera/drivers/cam_sensor_module/cam_eeprom/'
OLD={D+'cam_eeprom_core.c':'6173e88d5ebf9e616ad713eff2b19f2d4214ecab7329efbff2468854713b51cb',D+'cam_eeprom_dev.h':'450f9abae81b4b79cb4d30d4f2972d5c4d2461fa4509c81b60dbb933e5124cd4'}
def replace(text,old,new):
    if text.count(old)!=1:raise RuntimeError('Unexpected power anchor: '+old)
    return text.replace(old,new)
DOWN='''static int cam_eeprom_power_down(struct cam_eeprom_ctrl_t *e_ctrl)
{
	struct cam_eeprom_soc_private *soc_private;
	int rc;
	if (!e_ctrl || !e_ctrl->soc_info.soc_private)
		return -EINVAL;
	soc_private = e_ctrl->soc_info.soc_private;
	if (e_ctrl->pico_core_powered) {
		rc = cam_sensor_util_power_down(&soc_private->power_info, &e_ctrl->soc_info);
		if (rc)
			return rc;
		e_ctrl->pico_core_powered = false;
	}
	if (e_ctrl->pico_io_initialized) {
		rc = camera_io_release(&e_ctrl->io_master_info);
		if (rc)
			return rc;
		e_ctrl->pico_io_initialized = false;
	}
	return 0;
}

static void pico_eeprom_free_transaction(struct cam_eeprom_ctrl_t *e_ctrl)
{
	struct cam_eeprom_soc_private *private = e_ctrl->soc_info.soc_private;
	struct cam_sensor_power_ctrl_t *power = &private->power_info;
	vfree(e_ctrl->cal_data.mapdata);
	vfree(e_ctrl->cal_data.map);
	e_ctrl->cal_data.mapdata = NULL;
	e_ctrl->cal_data.map = NULL;
	e_ctrl->cal_data.num_data = 0;
	e_ctrl->cal_data.num_map = 0;
	kfree(power->power_setting);
	kfree(power->power_down_setting);
	power->power_setting = NULL;
	power->power_down_setting = NULL;
	power->power_setting_size = 0;
	power->power_down_setting_size = 0;
	e_ctrl->pico_transaction_cleanup_pending = false;
}

'''
GUARD='''	if (e_ctrl->pico_core_powered || e_ctrl->pico_io_initialized) {
		e_ctrl->pico_transaction_cleanup_pending = true;
		e_ctrl->cam_eeprom_state = CAM_EEPROM_CONFIG;
		return rc;
	}
'''
def main():
    root=Path(__file__).resolve().parent.parent;rp=root/'reports/kernel-source/recovery-20261003/eeprom-power-retry-hooks.json';prior=json.loads(rp.read_text())['sources'] if rp.exists() else {};content={}
    for name,digest in OLD.items():
        data=(SOURCE/name).read_bytes();actual=hashlib.sha256(data).hexdigest()
        if actual==digest:
            text=data.decode()
            if name.endswith('.h'):
                text=replace(text,'\tbool pico_acquire_cleanup_pending;','\tbool pico_acquire_cleanup_pending;\n\tbool pico_core_powered, pico_io_initialized;\n\tbool pico_transaction_cleanup_pending;')
            else:
                start=text.index('static int cam_eeprom_power_up(');end=text.index('\n/**',start);up=text[start:end]
                up=replace(up,'\tint32_t                 rc = 0;','\tint32_t                 rc = 0;\n\tint cleanup_rc;')
                up=replace(up,'\t/* Parse and fill vreg params for power up settings */','\tif (e_ctrl->pico_core_powered || e_ctrl->pico_io_initialized ||\n\t\te_ctrl->pico_transaction_cleanup_pending)\n\t\treturn -EBUSY;\n\n\t/* Parse and fill vreg params for power up settings */')
                up=replace(up,'\tif (e_ctrl->io_master_info.master_type == CCI_MASTER) {','\te_ctrl->pico_core_powered = true;\n\tif (e_ctrl->io_master_info.master_type == CCI_MASTER) {')
                up=replace(up,'\t\t\treturn -EINVAL;','\t\t\tcleanup_rc = cam_sensor_util_power_down(power_info, soc_info);\n\t\t\tif (!cleanup_rc)\n\t\t\t\te_ctrl->pico_core_powered = false;\n\t\t\telse\n\t\t\t\tCAM_ERR(CAM_EEPROM, "CCI init power unwind failed: %d", cleanup_rc);\n\t\t\treturn rc;')
                up=replace(up,'\t\t}\n\t}\n\treturn rc;','\t\t}\n\t\te_ctrl->pico_io_initialized = true;\n\t}\n\treturn rc;');text=text[:start]+up+text[end:]
                start=text.index('static int cam_eeprom_power_down(');end=text.index('\n/**',start);text=text[:start]+DOWN+text[end:]
                # All existing map free paths must clear the pointer for later shutdown.
                for field in ['mapdata','map']:
                    old='vfree(e_ctrl->cal_data.'+field+');';text=text.replace(old,old+'\n\te_ctrl->cal_data.'+field+' = NULL;')
                # Guard labels before any transaction allocation is freed.
                text=text.replace('data_mem_free:\n','data_mem_free:\n'+GUARD).replace('memdata_free:\n','memdata_free:\n'+GUARD).replace('error:\n\tkfree(power_info->power_setting);','error:\n'+GUARD+'\tkfree(power_info->power_setting);')
                text=replace(text,'\tif (rc)\n\t\tCAM_ERR(CAM_EEPROM, "failed: eeprom power down rc %d", rc);','\tif (rc) {\n\t\te_ctrl->pico_transaction_cleanup_pending = true;\n\t\treturn rc;\n\t}')
                text=replace(text,'\t\trc = cam_eeprom_power_down(e_ctrl);\n\t\te_ctrl->cam_eeprom_state = CAM_EEPROM_ACQUIRE;','\t\trc = cam_eeprom_power_down(e_ctrl);\n\t\tif (rc)\n\t\t\tgoto memdata_free;\n\t\te_ctrl->cam_eeprom_state = CAM_EEPROM_ACQUIRE;')
                # Shutdown must also see WRITE/acquire states with driver-owned power.
                text=replace(text,'\tif (e_ctrl->cam_eeprom_state == CAM_EEPROM_CONFIG) {\n\t\trc = cam_eeprom_power_down(e_ctrl);','\tif (e_ctrl->cam_eeprom_state == CAM_EEPROM_CONFIG ||\n\t\te_ctrl->pico_core_powered || e_ctrl->pico_io_initialized) {\n\t\trc = cam_eeprom_power_down(e_ctrl);')
                text=replace(text,'\tif (e_ctrl->cam_eeprom_state == CAM_EEPROM_INIT)\n\t\treturn;','\tif (e_ctrl->cam_eeprom_state == CAM_EEPROM_INIT &&\n\t\t!e_ctrl->pico_core_powered && !e_ctrl->pico_io_initialized)\n\t\treturn;')
                # Shutdown currently frees power settings after handle destroy.
                start=text.index('void cam_eeprom_shutdown(');end=text.index('\n/**',start);body=text[start:end];begin=body.index('\t\tkfree(power_info->power_setting);');finish=body.index('\n\t}',begin);body=body[:begin]+'\t\tpico_eeprom_free_transaction(e_ctrl);'+body[finish:]
                body=body.replace('\tstruct cam_eeprom_soc_private *soc_private;\n\tstruct cam_sensor_power_ctrl_t *power_info;\n','').replace('\tsoc_private = e_ctrl->soc_info.soc_private;\n\tpower_info = &soc_private->power_info;\n','');text=text[:start]+body+text[end:]
                text=replace(text,'\tcase CAM_CONFIG_DEV:\n\t\trc = cam_eeprom_pkt_parse(e_ctrl, arg);','\tcase CAM_CONFIG_DEV:\n\t\tif (e_ctrl->pico_core_powered || e_ctrl->pico_io_initialized || e_ctrl->pico_transaction_cleanup_pending) {rc = -EBUSY; goto release_mutex;}\n\t\trc = cam_eeprom_pkt_parse(e_ctrl, arg);')
                # Native release powers down before deleting ownership, then frees retained allocations.
                start=text.index('\tcase CAM_RELEASE_DEV:',text.index('int32_t cam_eeprom_driver_cmd('));end=text.index('\tcase CAM_CONFIG_DEV:',start);release=text[start:end]
                release=replace(release,'\t\tif (e_ctrl->cam_eeprom_state != CAM_EEPROM_ACQUIRE) {','\t\tif (e_ctrl->cam_eeprom_state == CAM_EEPROM_CONFIG || e_ctrl->pico_core_powered || e_ctrl->pico_io_initialized) {\n\t\t\trc = cam_eeprom_power_down(e_ctrl);\n\t\t\tif (rc)\n\t\t\t\tgoto release_mutex;\n\t\t\te_ctrl->cam_eeprom_state = CAM_EEPROM_ACQUIRE;\n\t\t}\n\t\tif (e_ctrl->cam_eeprom_state != CAM_EEPROM_ACQUIRE) {')
                release=replace(release,'\t\te_ctrl->bridge_intf.device_hdl = -1;','\t\tif (e_ctrl->pico_transaction_cleanup_pending)\n\t\t\tpico_eeprom_free_transaction(e_ctrl);\n\t\te_ctrl->bridge_intf.device_hdl = -1;');text=text[:start]+release+text[end:]
            data=text.encode()
        elif actual!=prior.get(name):raise RuntimeError('Preserve differing EEPROM source: '+name)
        if name.endswith('.c'):
            text=data.decode();anchor='if (e_ctrl->cam_eeprom_state == CAM_EEPROM_CONFIG || e_ctrl->pico_core_powered || e_ctrl->pico_io_initialized) {\n\t\t\trc = cam_eeprom_power_down(e_ctrl);';new=anchor.replace('\n\t\t\trc', '\n\t\t\te_ctrl->pico_transaction_cleanup_pending = true;\n\t\t\trc')
            if new not in text:text=replace(text,anchor,new)
            data=text.encode()
        content[name]=data
    name=D+'pico_memento_eeprom.inc';data=(root/'kernel-recovery'/name).read_bytes().replace(b'\r\n',b'\n');actual=hashlib.sha256((SOURCE/name).read_bytes()).hexdigest()
    if actual not in ['078b7b51e4bdb8f75d731586aab92a7e60a44240f8633188c4e85260eab4c19f',prior.get(name),hashlib.sha256(data).hexdigest()]:raise RuntimeError('Preserve differing EEPROM adapter')
    content[name]=data
    for name,data in content.items():(SOURCE/name).write_bytes(data)
    report={'sources':{n:hashlib.sha256(v).hexdigest() for n,v in content.items()},'preimages':OLD,'scope':'EEPROM core/I-O phases, CCI-init core unwind, parser retained cleanup settings, native release/shutdown; memento hardware cleanup/remove lifetime and provider partial effects still pending','device_modified':False};rp.write_text(json.dumps(report,indent=2)+'\n')
    for filename in ['peer-acquire-capture-hooks.json','eeprom-acquire-retry-hooks.json','eeprom-shutdown-retry-hooks.json']:
        p=rp.parent/filename;obj=json.loads(p.read_text());obj['sources'].update(report['sources'] if filename=='eeprom-acquire-retry-hooks.json' else {D+'cam_eeprom_core.c':report['sources'][D+'cam_eeprom_core.c']});obj['eeprom_power_retry_hooks']=str(rp);p.write_text(json.dumps(obj,indent=2)+'\n')
    print(json.dumps(report,indent=2))
if __name__=='__main__':main()
