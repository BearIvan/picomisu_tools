"""Keep native normal-release ownership until handle destroy succeeds."""
from pathlib import Path
import hashlib,json
SOURCE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro/source/phoenix-kernel-recovery');D='techpack/camera/drivers/cam_sensor_module/cam_sensor/'
OLD={D+'cam_sensor_core.c':'2ecd0500114372509cb25414a3e0585933401571b48125adcece09848c8dd79b',D+'cam_sensor_dev.h':'2a41097d51067be1070347754f5cabbc1887361a674fb4f20765cf013f9ea8c2'}
def replace(text,old,new):
    if text.count(old)!=1:raise RuntimeError('Unexpected release anchor: '+old)
    return text.replace(old,new)
def main():
    root=Path(__file__).resolve().parent.parent;path=root/'reports/kernel-source/recovery-20261003/sensor-release-retry-hooks.json';previous=json.loads(path.read_text())['sources'] if path.exists() else {};content={}
    for name,digest in OLD.items():
        data=(SOURCE/name).read_bytes();actual=hashlib.sha256(data).hexdigest()
        if actual==digest:
            text=data.decode()
            if name.endswith('.h'):
                text=replace(text,'\tbool pico_acquire_cleanup_pending;','\tbool pico_acquire_cleanup_pending;\n\tbool pico_release_cleanup_pending, pico_release_resources_done;')
            else:
                text=replace(text,'\tif (s_ctrl->pico_acquire_cleanup_pending &&','\tif ((s_ctrl->pico_acquire_cleanup_pending || s_ctrl->pico_release_cleanup_pending) &&')
                start=text.index('\tcase CAM_ACQUIRE_DEV: {',text.index('int32_t cam_sensor_driver_cmd('));end=text.index('\tcase CAM_RELEASE_DEV:',start);body=text[start:end]
                body=replace(body,'\t\ts_ctrl->pico_acquire_cleanup_pending = true;','\t\ts_ctrl->pico_release_cleanup_pending = false;\n\t\ts_ctrl->pico_release_resources_done = false;\n\t\ts_ctrl->pico_acquire_cleanup_pending = true;');text=text[:start]+body+text[end:]
                start=text.index('\tcase CAM_RELEASE_DEV: {',text.index('int32_t cam_sensor_driver_cmd('));end=text.index('\tcase CAM_QUERY_CAP:',start);body=text[start:end]
                body=replace(body,'\t\trc = cam_sensor_power_down(s_ctrl);','\t\tif (s_ctrl->bridge_intf.device_hdl <= 0) {\n\t\t\trc = -EINVAL;\n\t\t\tgoto release_mutex;\n\t\t}\n\t\ts_ctrl->pico_release_cleanup_pending = true;\n\t\trc = cam_sensor_power_down(s_ctrl);')
                body=replace(body,'\t\tcam_sensor_release_per_frame_resource(s_ctrl);\n\t\tcam_sensor_release_stream_rsc(s_ctrl);','\t\tif (!s_ctrl->pico_release_resources_done) {\n\t\t\tcam_sensor_release_per_frame_resource(s_ctrl);\n\t\t\tcam_sensor_release_stream_rsc(s_ctrl);\n\t\t\ts_ctrl->pico_release_resources_done = true;\n\t\t}')
                body=replace(body,'\t\tif (rc < 0)\n\t\t\tCAM_ERR(CAM_SENSOR,\n\t\t\t\t"failed in destroying the device hdl");','\t\tif (rc) {\n\t\t\tCAM_ERR(CAM_SENSOR, "failed in destroying the device hdl: %d", rc);\n\t\t\tgoto release_mutex;\n\t\t}')
                body=replace(body,'\t\ts_ctrl->sensor_state = CAM_SENSOR_INIT;','\t\ts_ctrl->pico_release_cleanup_pending = false;\n\t\ts_ctrl->pico_release_resources_done = false;\n\t\ts_ctrl->sensor_state = CAM_SENSOR_INIT;');text=text[:start]+body+text[end:]
            data=text.encode()
        elif actual!=previous.get(name):raise RuntimeError('Preserve differing sensor release source: '+name)
        content[name]=data
    name=D+'pico_memento_sensor.inc';data=(root/'kernel-recovery'/name).read_bytes().replace(b'\r\n',b'\n');old=(SOURCE/name).read_bytes();old_digest=hashlib.sha256(old).hexdigest()
    if old!=data and old_digest not in ('e0c242b3f10480649682488248a9f137c7a6e3bc4a3081d3f86905d7f37a7c1f',previous.get(name)):
        raise RuntimeError('Preserve differing memento sensor adapter')
    content[name]=data
    for name,data in content.items():
        if (SOURCE/name).read_bytes()!=data:(SOURCE/name).write_bytes(data)
    report={'sources':{n:hashlib.sha256(v).hexdigest() for n,v in content.items()},'preimages':OLD,'scope':'Native normal release phase retention, handle error propagation and config gate; physical hardware/subdevice-file/hot-remove validation pending','device_modified':False};path.write_text(json.dumps(report,indent=2)+'\n')
    capture_path=root/'reports/kernel-source/recovery-20261003/memento-capture-hooks.json';capture=json.loads(capture_path.read_text());capture['sources'][D+'cam_sensor_core.c']=report['sources'][D+'cam_sensor_core.c'];capture['sensor_release_retry_hooks']=str(path);capture_path.write_text(json.dumps(capture,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
