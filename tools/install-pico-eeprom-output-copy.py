"""Use serialized memory-manager copies for EEPROM outputs, without ABI edits."""
from pathlib import Path
import hashlib,json
SOURCE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro/source/phoenix-kernel-recovery');D='techpack/camera/drivers/cam_sensor_module/cam_eeprom/';M='techpack/camera/drivers/cam_req_mgr/'
def main():
    root=Path(__file__).resolve().parent.parent;rp=root/'reports/kernel-source/recovery-20261003/eeprom-output-copy-hooks.json';previous=json.loads(rp.read_text())['sources'] if rp.exists() else {};content={}
    for name in [D+'cam_eeprom_core.c',M+'cam_mem_mgr.c']:
        data=(SOURCE/name).read_bytes();actual=hashlib.sha256(data).hexdigest()
        baseline='9faab7aa75ae9eee377b8d2d18a50786b815aa9c2457a661ee4c8826c9fe0057' if name.startswith(D) else previous.get(name)
        # Memory-manager preimage is recorded on first use, with original code untouched except includes.
        if name.startswith(M) and not previous:baseline=actual
        if actual!=previous.get(name):
            if actual!=baseline:raise RuntimeError('Preserve differing native source: '+name)
            text=data.decode()
            if name.startswith(D):
                text=text.replace('#include "cam_eeprom_core.h"','#include "cam_eeprom_core.h"\n#include "../../cam_req_mgr/pico_mem_copy.h"',1)
                start=text.index('static int32_t cam_eeprom_get_cal_data(');end=text.index('\nstatic int32_t delete_eeprom_request(',start)
                text=text[:start]+'''static int32_t cam_eeprom_get_cal_data(struct cam_eeprom_ctrl_t *e_ctrl,
\tstruct cam_packet *packet)
{
\tstruct cam_buf_io_cfg *config = (struct cam_buf_io_cfg *)
\t\t((uint8_t *)&packet->payload + packet->io_configs_offset);
\tuint32_t index;
\tint rc;
\tfor (index = 0; index < packet->num_io_configs; index++, config++) {
\t\tif (config->direction != CAM_BUF_OUTPUT)
\t\t\treturn -EINVAL;
\t\trc = pico_mem_copy_to(config->mem_handle[0], config->offsets[0],
\t\t\te_ctrl->cal_data.mapdata, e_ctrl->cal_data.num_data);
\t\tif (rc)
\t\t\treturn rc;
\t}
\treturn 0;
}
'''+text[end:]
            else:
                text=text.replace('#include "cam_mem_mgr.h"','#include "cam_mem_mgr.h"\n#include "pico_mem_copy.h"',1)+'\n#include "pico_mem_copy.inc"\n'
            data=text.encode()
        content[name]=data
    for suffix in ['h','inc']:
        name=M+'pico_mem_copy.'+suffix;data=(root/'kernel-recovery'/name).read_bytes().replace(b'\r\n',b'\n')
        if (SOURCE/name).exists() and (SOURCE/name).read_bytes()!=data and hashlib.sha256((SOURCE/name).read_bytes()).hexdigest()!=previous.get(name):raise RuntimeError('Preserve differing copy helper')
        content[name]=data
    for name,data in content.items():
        if not (SOURCE/name).exists() or (SOURCE/name).read_bytes()!=data:(SOURCE/name).write_bytes(data)
    report={'sources':{n:hashlib.sha256(v).hexdigest() for n,v in content.items()},'scope':'Output memcpy under native m_lock/q_lock with identity/range revalidation; no table layout or original exported API change; caller retains manager lifecycle; input borrowed buffers and deinit/erase/providers/runtime pending','device_modified':False};rp.write_text(json.dumps(report,indent=2)+'\n')
    for file in rp.parent.glob('*hooks.json'):
        if file==rp:continue
        obj=json.loads(file.read_text())
        if D+'cam_eeprom_core.c' in obj.get('sources',{}):obj['sources'][D+'cam_eeprom_core.c']=report['sources'][D+'cam_eeprom_core.c'];obj['eeprom_output_copy_hooks']=str(rp);file.write_text(json.dumps(obj,indent=2)+'\n')
    print(json.dumps(report,indent=2))
if __name__=='__main__':main()
