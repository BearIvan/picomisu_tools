"""Return actual flush errors using a refcounted per-request completion."""
from pathlib import Path
import hashlib,json,importlib.util
BASE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro');SOURCE=BASE/'source/phoenix-kernel-recovery';ROOT=Path(__file__).resolve().parents[1];D='techpack/camera/drivers/cam_req_mgr/'
PRE={D+'cam_req_mgr_core.c':'e6e22f651dab4392abdc3fe0d23fe8f17672100fda4b7aaf29441661bbd15b1e',D+'cam_req_mgr_workq.c':'6b8bc5ce7e166c38a57e0e0c59f586ba309bcf6c03851b23db625f36d8845cdd',D+'cam_req_mgr_workq.h':'b73a78514a95401ae46e8bffd725e89aa56f13e86705978541df62e77b9460b3'}
NEW=D+'pico_crm_flush_result.inc'
def replace(s,a,b):
    if s.count(a)!=1:raise RuntimeError('Unexpected count '+a[:80])
    return s.replace(a,b)
def main():
    rp=ROOT/'reports/kernel-source/recovery-20261003/crm-flush-result-hooks.json'
    if rp.exists():
        r=json.loads(rp.read_text())
        if all(hashlib.sha256((SOURCE/n).read_bytes()).hexdigest()==h for n,h in r['sources'].items()):print('Already installed');return
    texts={n:(SOURCE/n).read_text() for n in PRE}
    for n,h in PRE.items():
        if hashlib.sha256((SOURCE/n).read_bytes()).hexdigest()!=h:raise RuntimeError('Preimage mismatch '+n)
    spec=importlib.util.spec_from_file_location('ex',Path(__file__).with_name('test-pico-sensor-mono-hook.py'));ex=importlib.util.module_from_spec(spec);spec.loader.exec_module(ex)
    n=D+'cam_req_mgr_core.c';s=texts[n];old=ex.function(s,'int cam_req_mgr_process_flush_req(');new=old
    new=replace(new,'\t\t/* @TODO: error return handling from drivers */\n\t\tif (device->ops && device->ops->flush_req)\n\t\t\trc = device->ops->flush_req(&flush_req);','\t\tif (device->ops && device->ops->flush_req) {\n\t\t\tint dev_rc = device->ops->flush_req(&flush_req);\n\n\t\t\tif (dev_rc && !rc)\n\t\t\t\trc = dev_rc;\n\t\t}')
    new=replace(new,'\tcomplete(&link->workq_comp);\n','');s=replace(s,old,new)
    s=replace(s,'int cam_req_mgr_flush_requests(', '#include "pico_crm_flush_result.inc"\n\nint cam_req_mgr_flush_requests(')
    old=ex.function(s,'int cam_req_mgr_flush_requests(');new=old
    new=replace(new,'\tint                               rc = 0;','\tint                               rc = 0;\n\tstruct pico_crm_flush_result     *result = NULL;')
    new=replace(new,'\ttask = cam_req_mgr_workq_get_task(link->workq);','\tresult = kzalloc(sizeof(*result), GFP_KERNEL);\n\tif (!result) {\n\t\trc = -ENOMEM;\n\t\tgoto end;\n\t}\n\tkref_init(&result->ref);\n\tinit_completion(&result->done);\n\tresult->link = link;\n\ttask = cam_req_mgr_workq_get_task(link->workq);')
    a='''	task->process_cb = &cam_req_mgr_process_flush_req;
	init_completion(&link->workq_comp);
	rc = cam_req_mgr_workq_enqueue_task(task, link, CRM_TASK_PRIORITY_0);

	/* Blocking call */
	rc = wait_for_completion_timeout(
		&link->workq_comp,
		msecs_to_jiffies(CAM_REQ_MGR_SCHED_REQ_TIMEOUT));'''
    b='''	task->process_cb = &pico_crm_process_flush;
	kref_get(&result->ref);
	rc = pico_cam_req_mgr_workq_enqueue_owned(task, result,
		CRM_TASK_PRIORITY_0);
	if (rc) {
		/* Owned enqueue returns failed/canceled tasks to their pool. */
		kref_put(&result->ref, pico_crm_flush_result_release);
		goto end;
	}
	/* Completion belongs to this request, including early worker errors. */
	if (!wait_for_completion_timeout(&result->done,
		msecs_to_jiffies(CAM_REQ_MGR_SCHED_REQ_TIMEOUT)))
		rc = -ETIMEDOUT;
	else
		rc = result->rc;'''
    new=replace(new,a,b)
    new=replace(new,'end:\n\tmutex_unlock(&g_crm_core_dev->crm_lock);','end:\n\tif (result)\n\t\tkref_put(&result->ref, pico_crm_flush_result_release);\n\tmutex_unlock(&g_crm_core_dev->crm_lock);')
    s=replace(s,old,new);texts[n]=s
    n=D+'cam_req_mgr_workq.c';s=texts[n]
    start=s.index('int cam_req_mgr_workq_enqueue_task(')
    old=s[start:s.index('\n}\n',start)+3];new=old
    new=replace(new,'int cam_req_mgr_workq_enqueue_task(struct crm_workq_task *task,\n\tvoid *priv, int32_t prio)','static int pico_crm_enqueue_task(struct crm_workq_task *task,\n\tvoid *priv, int32_t prio, bool report_cancel)')
    new=replace(new,'\t\trc = 0;\n\t\tgoto end;','\t\trc = report_cancel ? -ECANCELED : 0;\n\t\tgoto end;')
    new+='''

int cam_req_mgr_workq_enqueue_task(struct crm_workq_task *task,
	void *priv, int32_t prio)
{
	return pico_crm_enqueue_task(task, priv, prio, false);
}

int pico_cam_req_mgr_workq_enqueue_owned(struct crm_workq_task *task,
	void *priv, int32_t prio)
{
	int rc = pico_crm_enqueue_task(task, priv, prio, true);

	if (rc && rc != -ECANCELED && task && task->parent)
		cam_req_mgr_workq_put_task(task);
	return rc;
}
'''
    texts[n]=replace(s,old,new)
    n=D+'cam_req_mgr_workq.h';texts[n]=replace(texts[n],'int cam_req_mgr_workq_enqueue_task(struct crm_workq_task *task,','/* Valid owned task is pooled on failure/cancel; success queues its callback. */\nint pico_cam_req_mgr_workq_enqueue_owned(struct crm_workq_task *task,\n\tvoid *priv, int32_t prio);\n\nint cam_req_mgr_workq_enqueue_task(struct crm_workq_task *task,')
    texts[NEW]=(ROOT/'kernel-recovery'/NEW).read_text()
    for n,s in texts.items():(SOURCE/n).write_text(s)
    r={'preimages':PRE,'sources':{n:hashlib.sha256((SOURCE/n).read_bytes()).hexdigest() for n in texts},'scope':'Preserve first flush callback error, per-request result/completion with caller/worker refs, completion on early worker return, timeout errno, enqueue cancellation ownership; legacy enqueue cancellation ABI unchanged; link/workqueue physical lifecycle still pending','device_modified':False};rp.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))
if __name__=='__main__':main()
