"""Snapshot EEPROM packet under native memory-manager locks before parsing."""
from pathlib import Path
import hashlib,json
SOURCE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro/source/phoenix-kernel-recovery');D='techpack/camera/drivers/cam_sensor_module/cam_eeprom/';M='techpack/camera/drivers/cam_req_mgr/'
OLD={D+'cam_eeprom_core.c':'1e1d2505b0ebb1d376e3ee80ce7735f8d2d98262239737e54a805bc7dadd11bf',M+'cam_mem_mgr.c':'0d2b21798fed76463fa4914512c8709354a43c0288842ea30ae51df3942b5496',M+'pico_mem_copy.h':'7d47bf5dda3c2f7341cd7c8be5119e85c3357c47109a93ff97714bab30194b3a',M+'pico_mem_copy.inc':'e39e0f8ccb4cfe0171279f7e23eec656f17612b2a543f11689465ec0208f3249'}
def main():
    root=Path(__file__).resolve().parent.parent;rp=root/'reports/kernel-source/recovery-20261003/eeprom-packet-snapshot-hooks.json';prior=json.loads(rp.read_text())['sources'] if rp.exists() else {};content={}
    for name,digest in OLD.items():
        data=(SOURCE/name).read_bytes();actual=hashlib.sha256(data).hexdigest()
        if actual not in [digest,prior.get(name)]:raise RuntimeError('Preserve differing snapshot source: '+name)
        if name.endswith(('.h','.inc')):data=(root/'kernel-recovery'/name).read_bytes().replace(b'\r\n',b'\n')
        elif actual==digest:
            text=data.decode()
            if name.startswith(M):text=text.replace('#include <linux/module.h>','#include <linux/module.h>\n#include <linux/vmalloc.h>',1)
            else:
                start=text.index('static int32_t cam_eeprom_pkt_parse(');end=text.index('\nvoid cam_eeprom_shutdown(',start);body=text[start:end];switch=body.index('\tif (cam_packet_util_validate_packet(')
                body='''static int32_t cam_eeprom_pkt_parse_owned(struct cam_eeprom_ctrl_t *e_ctrl,
\tstruct cam_packet *csl_packet, size_t remain_len)
{
\tint rc = 0, cleanup_rc;
\tstruct cam_eeprom_soc_private *soc_private = e_ctrl->soc_info.soc_private;
'''+body[switch:]
                body+='''
static int32_t cam_eeprom_pkt_parse(struct cam_eeprom_ctrl_t *e_ctrl, void *arg)
{
\tstruct cam_control *cmd = arg;
\tstruct cam_config_dev_cmd config;
\tvoid *packet;
\tsize_t bytes;
\tint rc;
\tif (copy_from_user(&config, u64_to_user_ptr(cmd->handle), sizeof(config)))
\t\treturn -EFAULT;
\trc = pico_mem_dup_packet(config.packet_handle, config.offset, &packet, &bytes);
\tif (rc)
\t\treturn rc;
\trc = cam_eeprom_pkt_parse_owned(e_ctrl, packet, bytes);
\tvfree(packet);
\treturn rc;
}
''';text=text[:start]+body+text[end:]
            data=text.encode()
        content[name]=data
    for name,data in content.items():
        if (SOURCE/name).read_bytes()!=data:(SOURCE/name).write_bytes(data)
    report={'sources':{n:hashlib.sha256(v).hexdigest() for n,v in content.items()},'preimages':OLD,'scope':'Outer packet snapshotted under m_lock/q_lock and owned/vfree through every parser return; copied header size checked and common range validator runs on snapshot; nested commands still borrowed, manager lifecycle/user mutations/DMA/deinit/runtime pending','device_modified':False};rp.write_text(json.dumps(report,indent=2)+'\n')
    for file in rp.parent.glob('*hooks.json'):
        if file==rp:continue
        obj=json.loads(file.read_text());changed=False
        for n,h in report['sources'].items():
            if n in obj.get('sources',{}):obj['sources'][n]=h;changed=True
        if changed:obj['eeprom_packet_snapshot_hooks']=str(rp);file.write_text(json.dumps(obj,indent=2)+'\n')
    print(json.dumps(report,indent=2))
if __name__=='__main__':main()
