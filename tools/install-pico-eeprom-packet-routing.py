"""EEPROM packet offsets and per-entry output routing."""
from pathlib import Path
import hashlib,json
SOURCE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro/source/phoenix-kernel-recovery');D='techpack/camera/drivers/cam_sensor_module/cam_eeprom/';OLD='24bd23d82840a1a4e523abaeea803f3199f466b7804f47d5f3b0659ef075a094'
def replace(t,a,b):
    if t.count(a)!=1:raise RuntimeError('Unexpected packet anchor: '+a)
    return t.replace(a,b)
def main():
    root=Path(__file__).resolve().parent.parent;rp=root/'reports/kernel-source/recovery-20261003/eeprom-packet-routing-hooks.json';name=D+'cam_eeprom_core.c';p=SOURCE/name;data=p.read_bytes();actual=hashlib.sha256(data).hexdigest();prior=json.loads(rp.read_text()) if rp.exists() else {}
    if actual==OLD:
        t=data.decode();t=replace(t,'for (i = 0; i < csl_packet->num_io_configs; i++) {','for (i = 0; i < csl_packet->num_io_configs; i++, io_cfg++) {');t=replace(t,'((size_t)dev_config.offset >= pkt_len -','((size_t)dev_config.offset > pkt_len -');t=replace(t,'generic_pkt_addr + (uint32_t)dev_config.offset','generic_pkt_addr + dev_config.offset')
        t=replace(t,'\tswitch (csl_packet->header.op_code & 0xFFFFFF) {','\tif ((csl_packet->num_cmd_buf && (csl_packet->cmd_buf_offset & 3)) ||\n\t\t(csl_packet->num_io_configs && (csl_packet->io_configs_offset % __alignof__(struct cam_buf_io_cfg))))\n\t\treturn -EINVAL;\n\tswitch (csl_packet->header.op_code & 0xFFFFFF) {');data=t.encode();p.write_bytes(data)
    elif actual!=prior.get('sources',{}).get(name):raise RuntimeError('Preserve differing EEPROM core')
    report={'sources':{name:hashlib.sha256(data).hexdigest()},'preimage':OLD,'scope':'EEPROM advances each IO config, prevents descriptor offset truncation/unaligned typed config, uses full config offset and accepts exact packet fit; common range validator unchanged; mapping/provider/runtime pending','device_modified':False};rp.write_text(json.dumps(report,indent=2)+'\n')
    for file in rp.parent.glob('*.json'):
        if file==rp or file.name not in ['peer-acquire-capture-hooks.json','eeprom-acquire-retry-hooks.json','eeprom-shutdown-retry-hooks.json','eeprom-power-retry-hooks.json','eeprom-parser-unwind-hooks.json','eeprom-command-bounds-hooks.json','eeprom-write-payload-hooks.json']:continue
        obj=json.loads(file.read_text());obj['sources'][name]=report['sources'][name];obj['eeprom_packet_routing_hooks']=str(rp);file.write_text(json.dumps(obj,indent=2)+'\n')
    print(json.dumps(report,indent=2))
if __name__=='__main__':main()
