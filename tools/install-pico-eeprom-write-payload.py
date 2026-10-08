"""Restore EEPROM continuous register tables and exactly-once delay advance."""
from pathlib import Path
import hashlib,json
SOURCE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro/source/phoenix-kernel-recovery');D='techpack/camera/drivers/cam_sensor_module/cam_eeprom/'
OLD='ad036b9fed986de244aed6fca8a0302077b26e922c0879e08f54a38db4b3fb59'
GET='''static struct i2c_settings_list *cam_eeprom_get_i2c_ptr(
	struct i2c_settings_array *settings, uint32_t size)
{
	struct i2c_settings_list *node;
	if (!settings || !size)
		return NULL;
	node = kzalloc(sizeof(*node), GFP_KERNEL);
	if (!node)
		return NULL;
	node->i2c_settings.reg_setting = kcalloc(size,
		sizeof(*node->i2c_settings.reg_setting), GFP_KERNEL);
	if (!node->i2c_settings.reg_setting) {
		kfree(node);
		return NULL;
	}
	node->i2c_settings.size = size;
	list_add_tail(&node->list, &settings->list_head);
	return node;
}

'''
HANDLE='''static int32_t cam_eeprom_handle_continuous_write(
	struct cam_eeprom_ctrl_t *e_ctrl,
	struct cam_cmd_i2c_continuous_wr *cmd,
	struct i2c_settings_array *settings,
	uint32_t *bytes, int32_t *offset, struct list_head **list)
{
	struct i2c_settings_list *node;
	uint32_t index, count;
	enum cam_sensor_i2c_cmd_type opcode;
	if (!e_ctrl || !cmd || !settings || !bytes || !offset || !list)
		return -EINVAL;
	count = cmd->header.count;
	if (!count || cmd->header.addr_type <= CAMERA_SENSOR_I2C_TYPE_INVALID ||
		cmd->header.addr_type >= CAMERA_SENSOR_I2C_TYPE_MAX ||
		cmd->header.data_type <= CAMERA_SENSOR_I2C_TYPE_INVALID ||
		cmd->header.data_type >= CAMERA_SENSOR_I2C_TYPE_MAX)
		return -EINVAL;
	if (cmd->header.op_code == CAMERA_SENSOR_I2C_OP_CONT_WR_BRST)
		opcode = CAM_SENSOR_I2C_WRITE_BURST;
	else if (cmd->header.op_code == CAMERA_SENSOR_I2C_OP_CONT_WR_SEQN)
		opcode = CAM_SENSOR_I2C_WRITE_SEQ;
	else
		return -EINVAL;
	/* Caller checked the complete counted UAPI payload before entering. */
	node = cam_eeprom_get_i2c_ptr(settings, count);
	if (!node)
		return -ENOMEM;
	node->op_code = opcode;
	node->i2c_settings.addr_type = cmd->header.addr_type;
	node->i2c_settings.data_type = cmd->header.data_type;
	for (index = 0; index < count; index++) {
		node->i2c_settings.reg_setting[index].reg_addr = cmd->reg_addr;
		node->i2c_settings.reg_setting[index].reg_data = cmd->data_read[index].reg_data;
	}
	if (opcode == CAM_SENSOR_I2C_WRITE_SEQ) {
		e_ctrl->eebin_info.start_address = cmd->reg_addr;
		e_ctrl->eebin_info.size = count;
		e_ctrl->eebin_info.is_valid = 1;
	}
	*bytes = sizeof(struct i2c_rdwr_header) + sizeof(cmd->reg_addr) +
		count * sizeof(struct cam_cmd_read);
	*offset = count;
	*list = &node->list;
	return 0;
}

'''
DELAY='''static int32_t cam_eeprom_handle_delay(uint32_t **cmd_buf,
	uint16_t opcode, struct i2c_settings_array *settings, uint32_t offset,
	uint32_t *bytes, struct list_head *list, size_t remaining)
{
	struct cam_cmd_unconditional_wait *cmd;
	struct i2c_settings_list *node;
	if (!cmd_buf || !*cmd_buf || !settings || !bytes || !list ||
		remaining < sizeof(*cmd) || !offset)
		return -EINVAL;
	if (opcode != CAMERA_SENSOR_WAIT_OP_HW_UCND &&
		opcode != CAMERA_SENSOR_WAIT_OP_SW_UCND)
		return -EINVAL;
	cmd = (struct cam_cmd_unconditional_wait *)*cmd_buf;
	node = list_entry(list, struct i2c_settings_list, list);
	if (!node->i2c_settings.reg_setting || offset > node->i2c_settings.size)
		return -EINVAL;
	if (opcode == CAMERA_SENSOR_WAIT_OP_HW_UCND)
		node->i2c_settings.reg_setting[offset - 1].delay = cmd->delay;
	else
		node->i2c_settings.delay = cmd->delay;
	/* The nested parser advances the pointer/count exactly once. */
	*bytes = sizeof(*cmd);
	return 0;
}

'''
def replace(text,old,new):
    if text.count(old)!=1:raise RuntimeError('Unexpected write payload anchor: '+old)
    return text.replace(old,new)
def main():
    root=Path(__file__).resolve().parent.parent;rp=root/'reports/kernel-source/recovery-20261003/eeprom-write-payload-hooks.json';name=D+'cam_eeprom_core.c';path=SOURCE/name;data=path.read_bytes();actual=hashlib.sha256(data).hexdigest();prior=json.loads(rp.read_text()) if rp.exists() else {}
    if actual==OLD:
        text=data.decode();start=text.index('static struct i2c_settings_list*');end=text.index('\n/**',text.index('static int32_t cam_eeprom_handle_delay(',start));text=text[:start]+GET+HANDLE+DELAY+text[end:]
        text=replace(text,'\t\tkfree(i2c_list->seq_settings.reg_data);','\t\tkfree(i2c_list->i2c_settings.reg_setting);\n\t\tkfree(i2c_list->seq_settings.reg_data);')
        text=replace(text,'\t\t\t\t&i2c_list->i2c_settings, 1);','\t\t\t\t&i2c_list->i2c_settings,\n\t\t\t\te_ctrl->io_master_info.master_type == I2C_MASTER ?\n\t\t\t\t\ti2c_list->op_code :\n\t\t\t\t\t(i2c_list->op_code == CAM_SENSOR_I2C_WRITE_BURST ? 1 : 0));')
        data=text.encode();path.write_bytes(data)
    elif actual!=prior.get('sources',{}).get(name):raise RuntimeError('Preserve differing EEPROM core')
    refs=['techpack/camera/drivers/cam_sensor_module/cam_sensor_utils/cam_sensor_util.c','techpack/camera/drivers/cam_sensor_module/cam_sensor_utils/cam_sensor_cmn_header.h','techpack/camera/drivers/cam_sensor_module/cam_sensor_io/cam_sensor_io.c','techpack/camera/drivers/cam_sensor_module/cam_sensor_io/cam_sensor_cci_i2c.c','techpack/camera/drivers/cam_sensor_module/cam_sensor_io/cam_sensor_qup_i2c.c']
    ks=SOURCE.parent.parent/'analysis/diff-5.13.7-vs-5.13.8/kernel/ks5.13.7.txt';names={line.split()[-1] for line in ks.read_text().splitlines() if line.split()};factory={'path':str(ks),'sha256':hashlib.sha256(ks.read_bytes()).hexdigest(),'symbols':{n:n in names for n in ['cam_eeprom_handle_continuous_write','cam_eeprom_write','cam_eeprom_handle_delay']}}
    report={'sources':{name:hashlib.sha256(data).hexdigest()},'preimage':OLD,'reference_sources':{n:hashlib.sha256((SOURCE/n).read_bytes()).hexdigest() for n in refs},'factory_symbol_search':factory,'scope':'Continuous payload uses native register table API patterned on sensor parser; mode flags follow actual CCI/QUP adapters; delay caller advances once; invalid command/allocation failures publish no node; no factory EEPROM symbol match or hardware write proof, erase/eebin policy and provider behavior pending','device_modified':False};rp.write_text(json.dumps(report,indent=2)+'\n')
    for filename in ['peer-acquire-capture-hooks.json','eeprom-acquire-retry-hooks.json','eeprom-shutdown-retry-hooks.json','eeprom-power-retry-hooks.json','eeprom-parser-unwind-hooks.json','eeprom-command-bounds-hooks.json']:
        p=rp.parent/filename;obj=json.loads(p.read_text());obj['sources'][name]=report['sources'][name];obj['eeprom_write_payload_hooks']=str(rp);p.write_text(json.dumps(obj,indent=2)+'\n')
    print(json.dumps(report,indent=2))
if __name__=='__main__':main()
