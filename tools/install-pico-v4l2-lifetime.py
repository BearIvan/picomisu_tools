"""Attach optional owner refs to native video-node publication/final release."""
from pathlib import Path
import hashlib,json
BASE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro')
SOURCE=BASE/'source/phoenix-kernel-recovery'
ROOT=Path(__file__).resolve().parents[1]
N='drivers/media/v4l2-core/v4l2-device.c'
PRE='001f1f8186c3cb7e9f6dd65435e22864925dbe287ee26d7c8098ec6f65a92416'
NEW=['drivers/media/v4l2-core/pico-v4l2-lifetime.inc','include/media/pico-v4l2-lifetime.h']
def replace(s,a,b):
    if s.count(a)!=1:raise RuntimeError('Unexpected count '+a[:80])
    return s.replace(a,b)
def main():
    report_path=ROOT/'reports/kernel-source/recovery-20261003/v4l2-lifetime-hooks.json'
    if report_path.exists():
        report=json.loads(report_path.read_text())
        if all(hashlib.sha256((SOURCE/n).read_bytes()).hexdigest()==h for n,h in report['sources'].items()):print('Already installed');return
    p=SOURCE/N
    if hashlib.sha256(p.read_bytes()).hexdigest()!=PRE:raise RuntimeError('Preimage mismatch')
    s=p.read_text()
    s=replace(s,'static void v4l2_device_release_subdev_node(', '#include "pico-v4l2-lifetime.inc"\n\nstatic void v4l2_device_release_subdev_node(')
    s=replace(s,'\tstruct v4l2_subdev *sd = video_get_drvdata(vdev);\n\tsd->devnode = NULL;\n\tkfree(vdev);','\tstruct v4l2_subdev *sd = video_get_drvdata(vdev);\n\tstruct pico_subdev_node *node =\n\t\tcontainer_of(vdev, struct pico_subdev_node, vdev);\n\tstruct pico_subdev_owner *owner = node->owner;\n\n\tsd->devnode = NULL;\n\tkfree(vdev);\n\tif (owner)\n\t\tkref_put(&owner->ref, pico_subdev_owner_release);')
    s=replace(s,'\tstruct video_device *vdev;\n\tstruct v4l2_subdev *sd;\n\tint err;','\tstruct video_device *vdev;\n\tstruct pico_subdev_node *node;\n\tstruct v4l2_subdev *sd;\n\tint err;')
    s=replace(s,'\t\tvdev = kzalloc(sizeof(*vdev), GFP_KERNEL);\n\t\tif (!vdev) {','\t\tnode = kzalloc(sizeof(*node), GFP_KERNEL);\n\t\tvdev = node ? &node->vdev : NULL;\n\t\tif (!vdev) {')
    s=replace(s,'\t\tvideo_set_drvdata(vdev, sd);','\t\terr = pico_subdev_node_pin(sd, &node->owner);\n\t\tif (err) {\n\t\t\tkfree(vdev);\n\t\t\tgoto clean_up;\n\t\t}\n\t\tvideo_set_drvdata(vdev, sd);')
    s=replace(s,'\t\tif (err < 0) {\n\t\t\tkfree(vdev);\n\t\t\tgoto clean_up;\n\t\t}','\t\tif (err < 0) {\n\t\t\tif (node->owner)\n\t\t\t\tkref_put(&node->owner->ref, pico_subdev_owner_release);\n\t\t\tkfree(vdev);\n\t\t\tgoto clean_up;\n\t\t}')
    for n in NEW:
        target=SOURCE/n;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes((ROOT/'kernel-recovery'/n).read_bytes())
    p.write_text(s)
    report={'preimages':{N:PRE},'sources':{n:hashlib.sha256((SOURCE/n).read_bytes()).hexdigest() for n in [N]+NEW},'scope':'Optional bind-before-registration owner registry, node ref before publication, release ref after native final-node callback; no actuator bind/retire callers yet, owner removal remains unsafe','device_modified':False}
    report_path.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
