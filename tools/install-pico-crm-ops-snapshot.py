"""Give each CRM link owned callback tables without changing native layouts."""
from pathlib import Path
import hashlib,json
BASE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro');SOURCE=BASE/'source/phoenix-kernel-recovery';ROOT=Path(__file__).resolve().parents[1]
D='techpack/camera/drivers/cam_req_mgr/'
PRE={D+'cam_req_mgr_util.c':'7eae383ec9d44e6e802019da7d816ab3d29b6801b421b2f65a959c607c5a892d',D+'cam_req_mgr_util.h':'3ce455d54e81a6d80bc6be75e1482a8b09a7e3ee9fbe78ce2ca52be5c9890383',D+'cam_req_mgr_core.c':'d2dd1906217b777a0372436081d5ed8543dafd873e420feef00fc3af3a620def'}
API='''int pico_cam_get_device_ops_snapshot(int32_t dev_hdl,
	struct cam_req_mgr_kmd_ops *snapshot)
{
	struct handle *entry;
	int idx, ret = -ENODEV;

	if (!snapshot)
		return -EINVAL;
	memset(snapshot, 0, sizeof(*snapshot));
	spin_lock_bh(&hdl_tbl_lock);
	if (!hdl_tbl || CAM_REQ_MGR_GET_HDL_TYPE(dev_hdl) != HDL_TYPE_DEV)
		goto out;
	idx = CAM_REQ_MGR_GET_HDL_IDX(dev_hdl);
	if (idx >= CAM_REQ_MGR_MAX_HANDLES_V2)
		goto out;
	entry = &hdl_tbl->hdl[idx];
	if (entry->state != HDL_ACTIVE || entry->hdl_value != dev_hdl ||
		!entry->priv || !entry->ops)
		goto out;
	/* Owner retirement must invalidate priv/destroy handle under this lock
	 * before freeing ops storage. Never cache the driver's table pointer.
	 */
	*snapshot = *(struct cam_req_mgr_kmd_ops *)entry->ops;
	ret = 0;
out:
	spin_unlock_bh(&hdl_tbl_lock);
	return ret;
}

'''
def replace(s,a,b):
    if s.count(a)!=1:raise RuntimeError('Unexpected count '+a[:80])
    return s.replace(a,b)
def main():
    report_path=ROOT/'reports/kernel-source/recovery-20261003/crm-ops-snapshot-hooks.json'
    if report_path.exists():
        report=json.loads(report_path.read_text())
        if all(hashlib.sha256((SOURCE/n).read_bytes()).hexdigest()==h for n,h in report['sources'].items()):print('Already installed');return
    texts={n:(SOURCE/n).read_text() for n in PRE}
    for n,h in PRE.items():
        if hashlib.sha256((SOURCE/n).read_bytes()).hexdigest()!=h:raise RuntimeError('Preimage mismatch '+n)
    n=D+'cam_req_mgr_util.c';s=texts[n]
    s=replace(s,'#include "cam_req_mgr_util.h"','#include "cam_req_mgr_util.h"\n#include "cam_req_mgr_interface.h"')
    s=replace(s,'static int cam_destroy_hdl(',API+'static int cam_destroy_hdl(');texts[n]=s
    n=D+'cam_req_mgr_util.h';texts[n]=replace(texts[n],'/* Paired in the same task; quiesce requires removal to block new owners. */','struct cam_req_mgr_kmd_ops;\n/* Snapshot table bytes under native handle lock; no callback code/module pin. */\nint pico_cam_get_device_ops_snapshot(int32_t dev_hdl,\n\tstruct cam_req_mgr_kmd_ops *snapshot);\n\n/* Paired in the same task; quiesce requires removal to block new owners. */')
    n=D+'cam_req_mgr_core.c';s=texts[n]
    s=replace(s,'\t*l_dev = kzalloc(sizeof(struct cam_req_mgr_connected_device) *\n\t\tnum_dev, GFP_KERNEL);','\tif (num_dev < 0 || num_dev > CAM_REQ_MGR_MAX_HANDLES_V2)\n\t\treturn -EINVAL;\n\t/* Keep the native device array stride; owned ops occupy its tail. */\n\t*l_dev = kcalloc(num_dev, sizeof(struct cam_req_mgr_connected_device) +\n\t\tsizeof(struct cam_req_mgr_kmd_ops), GFP_KERNEL);')
    old='''		/* Using dev hdl, get ops ptr to communicate with device */
		if (link_info->version == VERSION_1)
			dev->ops = (struct cam_req_mgr_kmd_ops *)
					cam_get_device_ops(
					link_info->u.link_info_v1.dev_hdls[i]);
		else if (link_info->version == VERSION_2)
			dev->ops = (struct cam_req_mgr_kmd_ops *)
					cam_get_device_ops(
					link_info->u.link_info_v2.dev_hdls[i]);'''
    new='''		/* Cache link-owned table bytes, not a pointer into driver state. */
		if (link_info->version == VERSION_1)
			dev->dev_hdl = link_info->u.link_info_v1.dev_hdls[i];
		else if (link_info->version == VERSION_2)
			dev->dev_hdl = link_info->u.link_info_v2.dev_hdls[i];
		dev->ops = (struct cam_req_mgr_kmd_ops *)
			(link->l_dev + num_devices) + i;
		rc = pico_cam_get_device_ops_snapshot(dev->dev_hdl, dev->ops);
		if (rc) {
			dev->ops = NULL;
			goto error;
		}'''
    s=replace(s,old,new)
    # The handle is now selected before snapshot, so remove the second assignment.
    old='''		if (link_info->version == VERSION_1)
			dev->dev_hdl = link_info->u.link_info_v1.dev_hdls[i];
		else if (link_info->version == VERSION_2)
			dev->dev_hdl = link_info->u.link_info_v2.dev_hdls[i];
		dev->parent = (void *)link;'''
    s=replace(s,old,'\t\tdev->parent = (void *)link;');texts[n]=s
    for n,s in texts.items():(SOURCE/n).write_text(s)
    report={'preimages':PRE,'sources':{n:hashlib.sha256((SOURCE/n).read_bytes()).hexdigest() for n in texts},'scope':'Native CRM link owns callback-table copies in allocation tail; device array/handle/public ABI layouts unchanged; atomic copy under handle lock rejects retired priv. Callback code pin, linked-driver lifetime and full physical remove integration remain pending','device_modified':False}
    report_path.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
