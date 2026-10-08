"""Keep the media module reference in private file storage across unregister."""
from pathlib import Path
import hashlib,json
BASE=Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro')
SOURCE=BASE/'source/phoenix-kernel-recovery'
D='drivers/media/v4l2-core/'
PRE={D+'v4l2-subdev.c':'0af1964a3347a3feced9ba5fd063b50ac5d4a3ecb4f12af7d379a08eeae76bac',D+'v4l2-device.c':'92fc67b38e8c86b89f5afcf7e4afdf849d9932fbc321831d49d04c2a20ec4965'}
HEADER='''/* Private to videodev; no public structure or exported-symbol changes. */
#ifndef PICO_V4L2_MEDIA_PIN_H
#define PICO_V4L2_MEDIA_PIN_H
struct module;
struct v4l2_subdev;
int pico_v4l2_subdev_media_pin(struct v4l2_subdev *sd, struct module **owner);
#endif
'''
HELPER='''
/* Serialize the registered-parent snapshot with unregister's detach. */
static DEFINE_MUTEX(pico_subdev_parent_lock);

int pico_v4l2_subdev_media_pin(struct v4l2_subdev *sd, struct module **owner)
{
	int ret = 0;

	*owner = NULL;
	mutex_lock(&pico_subdev_parent_lock);
	if (!sd->v4l2_dev) {
		ret = -ENODEV;
		goto out;
	}
#if defined(CONFIG_MEDIA_CONTROLLER)
	if (sd->v4l2_dev->mdev && sd->v4l2_dev->mdev->dev) {
		struct device *dev = sd->v4l2_dev->mdev->dev;

		if (!dev->driver) {
			ret = -ENODEV;
			goto out;
		}
		if (!try_module_get(dev->driver->owner)) {
			ret = -EBUSY;
			goto out;
		}
		*owner = dev->driver->owner;
	}
#endif
out:
	mutex_unlock(&pico_subdev_parent_lock);
	return ret;
}
'''
def replace(text,old,new):
    if text.count(old)!=1:raise RuntimeError('Unexpected replacement count: '+old[:80])
    return text.replace(old,new)
def main():
    texts={n:(SOURCE/n).read_text() for n in PRE}
    report_path=Path(__file__).resolve().parents[1]/'reports/kernel-source/recovery-20261003/v4l2-media-pin-hooks.json'
    if report_path.exists():
        saved=json.loads(report_path.read_text())
        if all(hashlib.sha256((SOURCE/n).read_bytes()).hexdigest()==h for n,h in saved['sources'].items()):
            print('Already installed');return
    for n,h in PRE.items():
        if hashlib.sha256((SOURCE/n).read_bytes()).hexdigest()!=h:raise RuntimeError('Preimage mismatch '+n)
    n=D+'v4l2-subdev.c';s=texts[n]
    s=replace(s,'static int subdev_fh_init(','''#include <linux/module.h>
#include "pico-v4l2-media-pin.h"

struct pico_subdev_file {
	struct v4l2_subdev_fh fh;
	struct module *media_owner;
};

static int subdev_fh_init(''')
    s=replace(s,'#if defined(CONFIG_MEDIA_CONTROLLER)\n\tstruct media_entity *entity = NULL;\n#endif','\tstruct pico_subdev_file *private;')
    s=replace(s,'\tsubdev_fh = kzalloc(sizeof(*subdev_fh), GFP_KERNEL);','\tprivate = kzalloc(sizeof(*private), GFP_KERNEL);\n\tsubdev_fh = private ? &private->fh : NULL;')
    start=s.index('#if defined(CONFIG_MEDIA_CONTROLLER)\n\tif (sd->v4l2_dev->mdev) {',s.index('static int subdev_open'))
    end=s.index('\n#endif',start)+len('\n#endif')
    s=s[:start]+'''\tret = pico_v4l2_subdev_media_pin(sd, &private->media_owner);
	if (ret)
		goto err;'''+s[end:]
    s=replace(s,'#if defined(CONFIG_MEDIA_CONTROLLER)\n\tmedia_entity_put(entity);\n#endif','\tmodule_put(private->media_owner);')
    start=s.index('static int subdev_close(')
    s=s[:start]+replace(s[start:s.index('\n#if defined(CONFIG_VIDEO_V4L2_SUBDEV_API)',start)],'\tstruct v4l2_subdev_fh *subdev_fh = to_v4l2_subdev_fh(vfh);','\tstruct v4l2_subdev_fh *subdev_fh = to_v4l2_subdev_fh(vfh);\n\tstruct pico_subdev_file *private =\n\t\tcontainer_of(subdev_fh, struct pico_subdev_file, fh);')+s[s.index('\n#if defined(CONFIG_VIDEO_V4L2_SUBDEV_API)',start):]
    s=replace(s,'#if defined(CONFIG_MEDIA_CONTROLLER)\n\tif (sd->v4l2_dev->mdev)\n\t\tmedia_entity_put(&sd->entity);\n#endif','\tmodule_put(private->media_owner);')
    texts[n]=s
    n=D+'v4l2-device.c';s=texts[n]
    s=replace(s,'void v4l2_device_unregister_subdev(struct v4l2_subdev *sd)', '#include "pico-v4l2-media-pin.h"\n'+HELPER+'\nvoid v4l2_device_unregister_subdev(struct v4l2_subdev *sd)')
    s=replace(s,'\tif (sd == NULL || sd->v4l2_dev == NULL)\n\t\treturn;','\tmutex_lock(&pico_subdev_parent_lock);\n\tif (sd == NULL || sd->v4l2_dev == NULL) {\n\t\tmutex_unlock(&pico_subdev_parent_lock);\n\t\treturn;\n\t}')
    # Release the snapshot lock before arbitrary driver callbacks.
    s=replace(s,'\tif (sd->internal_ops && sd->internal_ops->unregistered)\n\t\tsd->internal_ops->unregistered(sd);\n\tsd->v4l2_dev = NULL;','\tmutex_unlock(&pico_subdev_parent_lock);\n\tif (sd->internal_ops && sd->internal_ops->unregistered)\n\t\tsd->internal_ops->unregistered(sd);\n\tmutex_lock(&pico_subdev_parent_lock);\n\tsd->v4l2_dev = NULL;\n\tmutex_unlock(&pico_subdev_parent_lock);')
    texts[n]=s
    texts[D+'pico-v4l2-media-pin.h']=HEADER
    for n,s in texts.items():(SOURCE/n).write_text(s)
    report={'preimages':PRE,'sources':{n:hashlib.sha256((SOURCE/n).read_bytes()).hexdigest() for n in texts},'scope':'Private file media-module pin and serialized parent detach; owner/controller lifetime and registration/open race outside pin helper remain pending. Original unregistered callback parent visibility preserved.','device_modified':False}
    report_path.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
