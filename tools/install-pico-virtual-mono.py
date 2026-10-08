"""Install the reviewed virtual-mono sources into the isolated recovery tree.

Refuse to overwrite differing sources: manual Linux edits take precedence.
This does not create a device, flash an image, or bypass CRM registration.
"""
from pathlib import Path
import hashlib
import json
import subprocess

SOURCE = Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro/source/phoenix-kernel-recovery')


def main():
    expected = 'ceafd3afc0208c03e0eb7a1a60939d147f92d72a'
    if subprocess.check_output(['git', '-C', str(SOURCE), 'rev-parse', 'HEAD'], text=True).strip() != expected:
        raise RuntimeError('Unexpected recovery base')
    root = Path(__file__).resolve().parent.parent
    directory = 'techpack/camera/drivers/cam_core/'
    paths = [directory + name for name in ('pico_virtual_mono.c', 'pico_virtual_mono.h')]
    inputs = {name: (root / 'kernel-recovery' / name).read_bytes().replace(b'\r\n', b'\n') for name in paths}
    for name, content in inputs.items():
        target = SOURCE / name
        if target.exists() and target.read_bytes() != content:
            managed_previous = {'techpack/camera/drivers/cam_core/pico_virtual_mono.c': ('cf5e00596edfe01d1106dce2622546b9781ab20c761d42366f260b759a83c16b', '681e6ef709c01315f5ef8b0ca24759aed12efb13259a06bfc4b2cbf569d97c8c'), 'techpack/camera/drivers/cam_core/pico_virtual_mono.h': ('9d40286b0e181f2ae03192087b1a9d6e03bf71eef8c402d449bfa7cb4e58826e',)}
            if hashlib.sha256(target.read_bytes()).hexdigest() not in managed_previous.get(name, ()):
                raise RuntimeError('Preserve differing source: ' + name)
    makefile = SOURCE / directory / 'Makefile'
    text = makefile.read_text()
    line = 'obj-$(CONFIG_SPECTRA_CAMERA) += pico_virtual_mono.o\n'
    for name, content in inputs.items():
        if not (SOURCE / name).exists() or (SOURCE / name).read_bytes() != content:
            (SOURCE / name).write_bytes(content)
    if line not in text:
        makefile.write_text(text + '\n# PICO virtual transport, recovered from factory 5.13.7\n' + line)
    report = {'base': expected, 'sources': {name: hashlib.sha256(content).hexdigest() for name, content in inputs.items()},
              'device_modified': False, 'runtime_verified': False,
              'pending': ['camera hub wrappers and client routing', 'open-file lifetime on remove', 'real queue/runtime validation']}
    out = root / 'reports/kernel-source/recovery-20261003/virtual-mono-source.json'
    out.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
