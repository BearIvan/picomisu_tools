"""Independently reread every file and its Android metadata from the final image.

WSL root is used only for the read-only loop mount of this local output image.
No headset operations and no mounts or writes to the input factory image.
"""
import importlib.util
import json
import os
from pathlib import Path
import subprocess

spec = importlib.util.spec_from_file_location('pico_extractor', Path(__file__).with_name('extract-vr-system.py'))
extractor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(extractor)
spec = importlib.util.spec_from_file_location('pico_assembler', Path(__file__).with_name('assemble-vr-system.py'))
pico = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pico)


def main():
    pico.guard_volume()
    if os.geteuid() != 0:
        raise RuntimeError('Read-only loop mount requires WSL root')
    report_file = pico.REPORTS / 'image.json'
    image = json.loads(report_file.read_text())
    stage = json.loads((pico.REPORTS / 'staging.json').read_text())
    raw = Path(image['files']['system.img']['path'])
    if pico.digest(raw) != image['files']['system.img']['sha256']:
        raise RuntimeError('Output system changed after AVB verification')
    mount = pico.STAGE / 'verify-image-readonly'
    mount.mkdir(exist_ok=True)
    if os.path.ismount(mount) or list(mount.iterdir()):
        raise RuntimeError('Verification mount point is already in use')
    expected = {entry['path']: entry for entry in stage['entries']}
    subprocess.run(['mount', '-t', 'ext4', '-o', 'loop,ro,noload', str(raw), str(mount)], check=True)
    verified = 0
    try:
        options = subprocess.check_output(['findmnt', '-n', '-o', 'OPTIONS', '--mountpoint', str(mount)], text=True)
        if 'ro' not in options.strip().split(','):
            raise RuntimeError('Verification mount must be read only')
        paths = {'/'}
        for folder, directories, files in os.walk(mount, followlinks=False):
            paths.update('/' + str((Path(folder) / name).relative_to(mount)) for name in directories + files)
        if paths != set(expected):
            raise RuntimeError('Image entries differ: extra=' + str(sorted(paths - set(expected)))
                               + '; missing=' + str(sorted(set(expected) - paths)))
        for relative, entry in sorted(expected.items()):
            file = mount / relative.lstrip('/')
            actual = extractor.metadata(file, relative)
            for key in ['kind', 'uid', 'gid', 'mode', 'selinux', 'capabilities', 'xattrs']:
                if actual[key] != entry[key]:
                    raise RuntimeError('Image metadata differs: ' + relative + ': ' + key
                                       + ': ' + str(actual[key]) + ' != ' + str(entry[key]))
            if entry['kind'] == 'file':
                if actual['bytes'] != entry['bytes'] or pico.digest(file) != entry['sha256']:
                    raise RuntimeError('Image content differs: ' + relative)
            elif entry['kind'] == 'symlink' and actual['target'] != entry['target']:
                raise RuntimeError('Image symlink differs: ' + relative)
            verified += 1
            if verified % 1000 == 0:
                print(json.dumps({'verified_image_entries': verified}), flush=True)
    finally:
        subprocess.run(['umount', str(mount)], check=True)
    roundtrip = raw.parent / '.verification-roundtrip-system.img'
    if roundtrip.exists():
        raise RuntimeError('Preserve existing roundtrip verification file')
    subprocess.run([str(pico.HOST / 'simg2img'), image['files']['system.sparse.img']['path'], str(roundtrip)], check=True)
    if pico.digest(roundtrip) != image['files']['system.img']['sha256']:
        raise RuntimeError('Sparse system does not roundtrip to the verified raw image')
    roundtrip.unlink()
    image.update(filesystem_contents_independently_verified=True, independently_verified_entries=verified,
                 owners_modes_selinux_capabilities_verified=True, sparse_roundtrip_sha256_verified=True,
                 factory_layer_byte_preservation_verified=True)
    report_file.write_text(json.dumps(image, indent=2) + '\n')
    print(json.dumps({'image_verified': True, 'entries': verified, 'sparse_roundtrip_verified': True,
                      'on_device_vr_tested': False}))


if __name__ == '__main__':
    main()
