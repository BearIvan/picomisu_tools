"""Add a sleepable callback borrow domain and wire actuator CRM readers."""
from pathlib import Path
import hashlib,json,re
SOURCE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro/source/phoenix-kernel-recovery');D='techpack/camera/drivers/cam_req_mgr/';A='techpack/camera/drivers/cam_sensor_module/cam_actuator/cam_actuator_core.c'
OLD={D+'cam_req_mgr_util.c':'977d1aa545d3fe90920bee947e147c8a5409ec6a9af36c55510a983dc0875919',D+'cam_req_mgr_util.h':'e2189551746238e2af6418737e375ca4a0aead2a24a91e3947bd2439683017df',A:'ff81f3577e1dea93fe02bfc0b0c9c220fec0db6190b03e34e12c07381ba941fb'}
API='''
/* SRCU borrow begins before lookup and may span a controller mutex wait.
 * Removal must deny owner re-publication, quiesce outside its mutex, and
 * protect non-CRM users separately before freeing the owner.
 */
static DEFINE_SRCU(pico_camera_callback_srcu);

void *pico_cam_device_priv_get(int32_t handle, int *cookie)
{
	void *priv;
	if (!cookie)
		return NULL;
	*cookie = srcu_read_lock(&pico_camera_callback_srcu);
	priv = cam_get_device_priv(handle);
	if (!priv) {
		srcu_read_unlock(&pico_camera_callback_srcu, *cookie);
		*cookie = -1;
	}
	return priv;
}

void pico_cam_device_priv_put(int cookie)
{
	if (cookie >= 0)
		srcu_read_unlock(&pico_camera_callback_srcu, cookie);
}

void pico_cam_device_priv_quiesce(void *priv)
{
	int i;
	if (!priv)
		return;
	spin_lock_bh(&hdl_tbl_lock);
	if (hdl_tbl) {
		for (i = 0; i < CAM_REQ_MGR_MAX_HANDLES_V2; i++)
			if (hdl_tbl->hdl[i].priv == priv)
				hdl_tbl->hdl[i].priv = NULL;
	}
	spin_unlock_bh(&hdl_tbl_lock);
	/* Never call while holding a mutex needed by a borrowed callback. */
	synchronize_srcu(&pico_camera_callback_srcu);
}
'''
def main():
    root=Path(__file__).resolve().parent.parent;rp=root/'reports/kernel-source/recovery-20261003/camera-callback-borrow-hooks.json';prior=json.loads(rp.read_text()) if rp.exists() else {};contents={}
    for name,digest in OLD.items():
        data=(SOURCE/name).read_bytes();actual=hashlib.sha256(data).hexdigest()
        if actual==digest:
            t=data.decode()
            if name.endswith('util.c'):t=t.replace('#include <linux/spinlock.h>','#include <linux/spinlock.h>\n#include <linux/srcu.h>')+API
            elif name.endswith('util.h'):
                at=t.rindex('#endif');t=t[:at]+'/* Paired in the same task; quiesce requires removal to block new owners. */\nvoid *pico_cam_device_priv_get(int32_t handle, int *cookie);\nvoid pico_cam_device_priv_put(int cookie);\nvoid pico_cam_device_priv_quiesce(void *priv);\n\n'+t[at:]
            else:
                for sig,end_sig,arg in [('int32_t cam_actuator_apply_request(','int32_t cam_actuator_establish_link(','apply'),('int32_t cam_actuator_establish_link(','static void cam_actuator_update_req_mgr(','link'),('int32_t cam_actuator_flush_request(','#include "pico_memento_actuator.inc"','flush_req')]:
                    start=t.index(sig);end=t.index(end_sig,start);body=t[start:end];anchor='\tstruct cam_actuator_ctrl_t *a_ctrl = NULL;'
                    if body.count(anchor)!=1:raise RuntimeError('Borrow controller anchor')
                    body=body.replace(anchor,anchor+'\n\tint pico_borrow_cookie = -1;');old='cam_get_device_priv('+arg+'->dev_hdl)'
                    if body.count(old)!=1:raise RuntimeError('Borrow lookup anchor')
                    body=body.replace(old,'pico_cam_device_priv_get('+arg+'->dev_hdl, &pico_borrow_cookie)')
                    # All exits release the cookie; pre-lookup exits use -1.
                    body=re.sub(r'(?m)^(\t+)return ([^;]+);',r'\1pico_cam_device_priv_put(pico_borrow_cookie);\n\1return \2;',body)
                    # Preserve the one unbraced early flush input guard.
                    if arg=='flush_req':body=body.replace('if (!flush_req)\n\t\tpico_cam_device_priv_put(pico_borrow_cookie);\n\t\treturn -EINVAL;','if (!flush_req) {\n\t\tpico_cam_device_priv_put(pico_borrow_cookie);\n\t\treturn -EINVAL;\n\t}')
                    t=t[:start]+body+t[end:]
            data=t.encode()
        elif actual!=prior.get('sources',{}).get(name):raise RuntimeError('Preserve differing borrow source '+name)
        contents[name]=data
    for n,d in contents.items():
        if (SOURCE/n).read_bytes()!=d:(SOURCE/n).write_bytes(d)
    report={'sources':{n:hashlib.sha256(d).hexdigest() for n,d in contents.items()},'preimages':OLD,'scope':'SRCU callback borrow before lookup through all actuator apply/flush/link exits; quiesce primitive invalidates private lookups and waits outside owner mutex; physical remove/V4L2 integration not wired yet, removal remains unsafe','device_modified':False};rp.write_text(json.dumps(report,indent=2)+'\n')
    for p in rp.parent.glob('*hooks.json'):
        if p==rp:continue
        obj=json.loads(p.read_text());changed=False
        for n,h in report['sources'].items():
            if n in obj.get('sources',{}):obj['sources'][n]=h;changed=True
        if changed:obj['camera_callback_borrow_hooks']=str(rp);p.write_text(json.dumps(obj,indent=2)+'\n')
    print(json.dumps(report,indent=2))
if __name__=='__main__':main()
