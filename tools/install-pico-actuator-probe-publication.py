"""Initialize driver callback state before V4L2 subdevice publication."""
from pathlib import Path
import hashlib,json,importlib.util
BASE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro');SOURCE=BASE/'source/phoenix-kernel-recovery';ROOT=Path(__file__).resolve().parents[1]
N='techpack/camera/drivers/cam_sensor_module/cam_actuator/cam_actuator_dev.c';PRE='98365fb25c4428cd8c508e4ca1c09bfd5b93c98fcc2ad2dab251fc76d93755c6'
def replace(s,a,b):
    if s.count(a)!=1:raise RuntimeError('Unexpected count '+a[:80])
    return s.replace(a,b)
def main():
    report_path=ROOT/'reports/kernel-source/recovery-20261003/actuator-probe-publication-hooks.json'
    if report_path.exists():
        report=json.loads(report_path.read_text())
        if all(hashlib.sha256((SOURCE/n).read_bytes()).hexdigest()==h for n,h in report['sources'].items()):print('Already installed');return
    p=SOURCE/N
    if hashlib.sha256(p.read_bytes()).hexdigest()!=PRE:raise RuntimeError('Preimage mismatch')
    spec=importlib.util.spec_from_file_location('ex',Path(__file__).with_name('test-pico-sensor-mono-hook.py'));ex=importlib.util.module_from_spec(spec);spec.loader.exec_module(ex)
    s=p.read_text()
    old=ex.function(s,'cam_actuator_driver_i2c_probe');new=old
    new=replace(new,'\ti2c_set_clientdata(client, a_ctrl);\n\n','')
    new=replace(new,'\trc = cam_actuator_init_subdev(a_ctrl);\n\tif (rc)\n\t\tgoto free_soc;\n\n','')
    new=replace(new,'\t\tgoto unreg_subdev;','\t\tgoto free_soc;')
    new=replace(new,'\treturn rc;\n\nunreg_subdev:\n\tcam_unregister_subdev(&(a_ctrl->v4l2_dev_str));','\t/* Publish only once all callback-visible state is initialized. */\n\trc = cam_actuator_init_subdev(a_ctrl);\n\tif (rc)\n\t\tgoto free_frames;\n\ti2c_set_clientdata(client, a_ctrl);\n\treturn rc;\n\nfree_frames:\n\tkfree(a_ctrl->i2c_data.per_frame);')
    s=replace(s,old,new)
    old=ex.function(s,'cam_actuator_driver_platform_probe');new=old
    new=replace(new,'\trc = cam_actuator_init_subdev(a_ctrl);\n\tif (rc)\n\t\tgoto free_mem;\n\n','')
    new=replace(new,'\tplatform_set_drvdata(pdev, a_ctrl);\n','')
    new=replace(new,'\ta_ctrl->open_cnt = 0;\n\n\treturn rc;','\ta_ctrl->open_cnt = 0;\n\n\t/* Publish only once all callback-visible state is initialized. */\n\trc = cam_actuator_init_subdev(a_ctrl);\n\tif (rc)\n\t\tgoto free_mem;\n\tplatform_set_drvdata(pdev, a_ctrl);\n\treturn rc;')
    s=replace(s,old,new);p.write_text(s)
    report={'preimages':{N:PRE},'sources':{N:hashlib.sha256(p.read_bytes()).hexdigest()},'scope':'I2C/platform probe initializes request storage/list heads/bridge callbacks/handles/state before V4L2 registration; I2C driverdata assigned only after successful publication; lifetime bind/remove integration remains pending','device_modified':False}
    report_path.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
