"""Copy only verified development images into the Windows task output directory."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PROJECT = Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro')
DEST = ROOT / 'outputs/vr-preview-01'


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


def main():
    image = json.loads((ROOT / 'reports/vr-integration/image.json').read_text())
    if not (image['filesystem_contents_independently_verified']
            and image['sparse_roundtrip_sha256_verified'] and image['avb_chain_verification_exit_code'] == 0):
        raise RuntimeError('Only a fully verified image may be copied for review')
    state = json.loads(subprocess.check_output(
        ['findmnt', '--json', '-o', 'FSTYPE,UUID', '--target', '/mnt/wsl/PHYSICALDRIVE5p3'], text=True))['filesystems']
    if state != [{'fstype': 'ext4', 'uuid': 'a00da05f-1eb2-44b6-99f0-9109391f67dc'}]:
        raise RuntimeError('Expected ext4 volume is not mounted')
    if shutil.disk_usage(ROOT).free < image['files']['system.sparse.img']['bytes'] + 1024**3:
        raise RuntimeError('Insufficient Windows output space')
    DEST.mkdir(parents=True, exist_ok=True)
    copied = {}
    for source_name, output_name in [('system.sparse.img', 'system.img'),
                                     ('vbmeta.img', 'vbmeta.img'), ('vbmeta_system.img', 'vbmeta_system.img')]:
        record = image['files'][source_name]
        source, output = Path(record['path']), DEST / output_name
        if output.exists() and digest(output) != record['sha256']:
            raise RuntimeError('Preserve a different existing Windows output: ' + output_name)
        if not output.exists():
            shutil.copyfile(source, output)
        if digest(output) != record['sha256']:
            raise RuntimeError('Windows copy checksum mismatch')
        copied[output_name] = {'path': str(output), 'sha256': record['sha256'], 'bytes': output.stat().st_size}
    (DEST / 'SHA256SUMS.txt').write_text(''.join(
        item['sha256'] + '  ' + name + '\n' for name, item in copied.items()))
    (DEST / 'verification.json').write_text(json.dumps(image, indent=2) + '\n')
    (ROOT / 'reports/vr-integration/windows-output.json').write_text(json.dumps(
        {'complete': True, 'copied': copied, 'system_img_format': 'Android sparse',
         'system_expanded_bytes': image['partition_size'], 'on_device_vr_tested': False,
         'boot_flash_required': False, 'bound_current_boot_sha256': image['current_boot_sha256']}, indent=2) + '\n')
    print(json.dumps({'verified_windows_output': str(DEST), 'files': list(copied)}))


if __name__ == '__main__':
    main()
