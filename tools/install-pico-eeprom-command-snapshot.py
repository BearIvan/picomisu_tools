"""Own exact EEPROM command descriptor windows through their parser lifetime."""
from pathlib import Path
import hashlib,json
SOURCE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro/source/phoenix-kernel-recovery');D='techpack/camera/drivers/cam_sensor_module/cam_eeprom/';M='techpack/camera/drivers/cam_req_mgr/'
OLD={D+'cam_eeprom_core.c':'a478c2e1944214fe2a2585eb073c5732bb222ef48817705e6fb7c64d9ae4b7b9',M+'pico_mem_copy.h':'1cbf66bc7a01e43a2a0933a9541f17d0c89ab4e3cab07edaaeb7e8ea0658843d',M+'pico_mem_copy.inc':'6f1e16e7a29b3a91836f4fa2c1d1c83f69318a75ce7d996ed4801961c549ac79'}
def replace(text,a,b):
    if text.count(a)!=1:raise RuntimeError('Unexpected command snapshot anchor: '+a)
    return text.replace(a,b)
def main():
    root=Path(__file__).resolve().parent.parent;rp=root/'reports/kernel-source/recovery-20261003/eeprom-command-snapshot-hooks.json';prior=json.loads(rp.read_text())['sources'] if rp.exists() else {};content={}
    for name,digest in OLD.items():
        data=(SOURCE/name).read_bytes();actual=hashlib.sha256(data).hexdigest()
        if actual not in [digest,prior.get(name)]:raise RuntimeError('Preserve differing snapshot source: '+name)
        if name.endswith(('.h','.inc')):data=(root/'kernel-recovery'/name).read_bytes().replace(b'\r\n',b'\n')
        elif actual==digest:
            text=data.decode()
            for signature in ['static int32_t cam_eeprom_parse_write_memory_packet(', 'static int32_t cam_eeprom_init_pkt_parser(']:
                start=text.index(signature);end=text.index('\n/**',start);body=text[start:end]
                body=replace(body,'\tuintptr_t                       generic_pkt_addr;','\tvoid *owned_cmd = NULL;') if 'parse_write' in signature else replace(body,'\tuintptr_t                        generic_pkt_addr;','\tvoid *owned_cmd = NULL;')
                body=replace(body,'\t\ttotal_cmd_buf_in_bytes = cmd_desc[i].length;','\t\tvfree(owned_cmd);\n\t\towned_cmd = NULL;\n\t\ttotal_cmd_buf_in_bytes = cmd_desc[i].length;')
                body=replace(body,'\t\trc = cam_mem_get_cpu_buf(cmd_desc[i].mem_handle,\n\t\t\t&generic_pkt_addr, &pkt_len);','\t\trc = pico_mem_dup_range(cmd_desc[i].mem_handle, cmd_desc[i].offset,\n\t\t\ttotal_cmd_buf_in_bytes, &owned_cmd);\n\t\tpkt_len = total_cmd_buf_in_bytes;')
                body=replace(body,'"Failed to get cpu buf");\n\t\t\treturn rc;','"Failed to get cpu buf");\n\t\t\tgoto end;')
                body=replace(body,'\t\tcmd_buf = (uint32_t *)generic_pkt_addr;','\t\tcmd_buf = owned_cmd;')
                begin=body.index('\t\tif ((pkt_len < sizeof(struct common_header)');finish=body.index('\t\tif (total_cmd_buf_in_bytes > remain_len)',begin)
                body=body[:begin]+'\t\tif (pkt_len < sizeof(struct common_header)) {rc = -EINVAL; goto end;}\n\t\tremain_len = pkt_len;\n\n'+body[finish:]
                body=replace(body,'end:\n\treturn rc;','end:\n\tvfree(owned_cmd);\n\treturn rc;');text=text[:start]+body+text[end:]
            data=text.encode()
        content[name]=data
    for name,data in content.items():
        if (SOURCE/name).read_bytes()!=data:(SOURCE/name).write_bytes(data)
    report={'sources':{n:hashlib.sha256(v).hexdigest() for n,v in content.items()},'preimages':OLD,'scope':'Nested read/write parser owns exact command windows duplicated under m_lock/q_lock; source offset applied once; current copy freed on next descriptor/all parser exits; lower power deep-copies fields into owned arrays; full lifecycle/provider/hardware pending','device_modified':False};rp.write_text(json.dumps(report,indent=2)+'\n')
    for file in rp.parent.glob('*hooks.json'):
        if file==rp:continue
        obj=json.loads(file.read_text());changed=False
        for n,h in report['sources'].items():
            if n in obj.get('sources',{}):obj['sources'][n]=h;changed=True
        if changed:obj['eeprom_command_snapshot_hooks']=str(rp);file.write_text(json.dumps(obj,indent=2)+'\n')
    print(json.dumps(report,indent=2))
if __name__=='__main__':main()
