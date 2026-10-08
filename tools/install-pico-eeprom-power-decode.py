"""EEPROM transactional power decoder adapter; original generic decoder unchanged."""
from pathlib import Path
import hashlib,json
SOURCE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro/source/phoenix-kernel-recovery');D='techpack/camera/drivers/cam_sensor_module/cam_eeprom/';OLD='5dd2394fb2f497ba0aeb630a97b40b23bf17a14a59cca45c3c753ebce9a0b623'
def replace(t,a,b):
    if t.count(a)!=1:raise RuntimeError('Unexpected power adapter anchor: '+a)
    return t.replace(a,b)
def main():
    root=Path(__file__).resolve().parent.parent;rp=root/'reports/kernel-source/recovery-20261003/eeprom-power-decode-hooks.json';prior=json.loads(rp.read_text())['sources'] if rp.exists() else {};name=D+'cam_eeprom_core.c';data=(SOURCE/name).read_bytes();actual=hashlib.sha256(data).hexdigest()
    if actual==OLD:
        t=data.decode();start=t.index('static int32_t cam_eeprom_init_pkt_parser(');end=t.index('\n/**',start);body=t[start:end];body=replace(body,'\tint                             num_map = -1;','\tint                             num_map = -1;\n\tbool power_seen = false;');body=replace(body,'rc = cam_sensor_update_power_settings(cmd_buf,','rc = pico_eeprom_update_power_settings(cmd_buf,');body=replace(body,'cmd_length_in_bytes, power_info,\n\t\t\t\t\t(remain_len -\n\t\t\t\t\tprocessed_cmd_buf_in_bytes));','cmd_length_in_bytes, power_info,\n\t\t\t\t\t(remain_len -\n\t\t\t\t\tprocessed_cmd_buf_in_bytes), power_seen);\n\t\t\t\tif (!rc) power_seen = true;');t=t[:start]+'#include "pico_eeprom_power_decode.inc"\n\n'+body+t[end:];data=t.encode()
    elif actual!=prior.get(name):raise RuntimeError('Preserve differing EEPROM core')
    helper=D+'pico_eeprom_power_decode.inc';new=(root/'kernel-recovery'/helper).read_bytes().replace(b'\r\n',b'\n')
    if (SOURCE/helper).exists() and hashlib.sha256((SOURCE/helper).read_bytes()).hexdigest() not in [prior.get(helper),hashlib.sha256(new).hexdigest()]:raise RuntimeError('Preserve differing power decoder adapter')
    for n,v in [(name,data),(helper,new)]:
        if not (SOURCE/n).exists() or (SOURCE/n).read_bytes()!=v:(SOURCE/n).write_bytes(v)
    report={'sources':{name:hashlib.sha256(data).hexdigest(),helper:hashlib.sha256(new).hexdigest()},'preimage':OLD,'scope':'EEPROM power counted window validated before generic decoder, decoded into temporary arrays and committed after bounded merge; first descriptor replaces settings, subsequent descriptors append; generic decoder unchanged; physical power/providers pending','device_modified':False};rp.write_text(json.dumps(report,indent=2)+'\n')
    for p in rp.parent.glob('*hooks.json'):
        if p==rp:continue
        obj=json.loads(p.read_text())
        if name in obj.get('sources',{}):obj['sources'][name]=report['sources'][name];obj['eeprom_power_decode_hooks']=str(rp);p.write_text(json.dumps(obj,indent=2)+'\n')
    print(json.dumps(report,indent=2))
if __name__=='__main__':main()
