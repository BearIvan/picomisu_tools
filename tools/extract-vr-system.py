"""Extract authenticated factory system files and exact Android filesystem metadata.

Run as WSL root only for a read-only loop mount. Never mounts a headset partition.
The extracted working files belong to redpanda; Android owners/labels/caps are
recorded independently for e2fsdroid and for subsequent image verification.
"""
import base64
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import pwd
import shutil
import stat
import struct
import subprocess

ROOT = Path(__file__).resolve().parents[1]
VOLUME = Path('/mnt/wsl/PHYSICALDRIVE5p3')
PROJECT = VOLUME / 'home/red_panda/RedPandaAndroid/pico4-pro'
DEST = PROJECT / 'analysis/stock-5.13.7-system'
IMAGE = PROJECT / 'stock/5.13.7-SEKO/system.img'
REPORT = ROOT / 'reports/vr-integration/factory-system.json'


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


def metadata(path, relative):
    info = path.lstat()
    kind = ('directory' if stat.S_ISDIR(info.st_mode) else 'symlink'
            if stat.S_ISLNK(info.st_mode) else 'file' if stat.S_ISREG(info.st_mode) else None)
    if kind is None:
        raise RuntimeError('Unexpected factory inode type: ' + relative)
    attrs = {name: os.getxattr(path, name, follow_symlinks=False)
             for name in os.listxattr(path, follow_symlinks=False)}
    context = attrs.get('security.selinux', b'').rstrip(b'\0').decode('ascii')
    if not context:
        raise RuntimeError('Missing factory SELinux context: ' + relative)
    caps = attrs.get('security.capability', b'')
    mask = 0
    if caps:
        if len(caps) not in (20, 24):
            raise RuntimeError('Unsupported capability structure: ' + relative)
        magic, low, inheritable_low, high, inheritable_high = struct.unpack('<5I', caps[:20])
        if (magic & 0xfffffffe) not in (0x02000000, 0x03000000) or inheritable_low or inheritable_high:
            raise RuntimeError('Capability structure needs explicit handling: ' + relative)
        mask = low | high << 32
    result = {'path': relative, 'kind': kind, 'uid': info.st_uid, 'gid': info.st_gid,
              'mode': format(stat.S_IMODE(info.st_mode), '04o'), 'bytes': info.st_size,
              'selinux': context, 'capabilities': mask,
              'xattrs': {name: base64.b64encode(value).decode('ascii') for name, value in attrs.items()}}
    if kind == 'symlink':
        result['target'] = os.readlink(path)
    return result


def main():
    if os.geteuid() != 0:
        raise RuntimeError('Read-only loop mount requires WSL root')
    mounted = json.loads(subprocess.check_output(
        ['findmnt', '--json', '-o', 'FSTYPE,UUID', '--target', str(VOLUME)], text=True))['filesystems']
    if mounted != [{'fstype': 'ext4', 'uuid': 'a00da05f-1eb2-44b6-99f0-9109391f67dc'}]:
        raise RuntimeError('Expected physical ext4 volume is not mounted')
    trusted = json.loads((ROOT / 'reports/verification.json').read_text())['downloaded_factory_ota']
    if not (trusted['whole_package_signature_verified'] and
            trusted['signer_matches_installed_ota_trust_store'] and
            trusted['avb_verification_exit_code'] == 0 and 'system' in trusted['avb_images_checked']):
        raise RuntimeError('Factory authentication has not passed')
    expected = json.loads((ROOT / 'reports/baseline-5.13.7/verification.json').read_text())['images']['system']
    if IMAGE.stat().st_size != expected['bytes'] or digest(IMAGE) != expected['sha256']:
        raise RuntimeError('Factory system changed after authentication')
    if REPORT.exists():
        previous = json.loads(REPORT.read_text())
        if previous['complete'] and previous['image_sha256'] == expected['sha256'] and (DEST / 'root').is_dir():
            print(json.dumps({'already_extracted': True, 'report': str(REPORT)}))
            return
        raise RuntimeError('Preserve existing extraction report')
    DEST.mkdir(parents=True, exist_ok=True)
    tree = DEST / 'root'
    mount = DEST / 'mount-readonly'
    if tree.exists():
        raise RuntimeError('Preserve an existing extraction without a completed manifest')
    mount.mkdir(exist_ok=True)
    if os.path.ismount(mount) or list(mount.iterdir()):
        raise RuntimeError('Read-only mount point is already in use')
    user = pwd.getpwnam('redpanda')
    entries = []
    subprocess.run(['mount', '-t', 'ext4', '-o', 'loop,ro,noload', str(IMAGE), str(mount)], check=True)
    try:
        options = subprocess.check_output(['findmnt', '-n', '-o', 'OPTIONS', '--mountpoint', str(mount)], text=True)
        if 'ro' not in options.strip().split(','):
            raise RuntimeError('Factory mount must be read only')
        tree.mkdir()
        entries.append(metadata(mount, '/'))
        for folder, directories, files in os.walk(mount, followlinks=False):
            for name in sorted(directories + files):
                source = Path(folder) / name
                relative = '/' + str(source.relative_to(mount))
                entry = metadata(source, relative)
                destination = tree / relative.lstrip('/')
                if entry['kind'] == 'directory':
                    destination.mkdir(exist_ok=True)
                    destination.chmod(0o755)
                elif entry['kind'] == 'symlink':
                    destination.symlink_to(entry['target'])
                else:
                    shutil.copyfile(source, destination)
                    entry['sha256'] = digest(destination)
                    destination.chmod(0o755 if int(entry['mode'], 8) & 0o111 else 0o644)
                os.chown(destination, user.pw_uid, user.pw_gid, follow_symlinks=False)
                entries.append(entry)
                if len(entries) % 1000 == 0:
                    print(json.dumps({'extracted_entries': len(entries)}), flush=True)
        os.chown(tree, user.pw_uid, user.pw_gid)
    finally:
        subprocess.run(['umount', str(mount)], check=True)
    report = {'created_at': datetime.now(timezone.utc).isoformat(), 'complete': True,
              'pico_build': '5.13.7 SEKO b9665', 'image': str(IMAGE),
              'image_sha256': expected['sha256'], 'tree': str(tree),
              'factory_mount_read_only': True, 'headset_modified': False,
              'entries': sorted(entries, key=lambda entry: entry['path'])}
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'complete': True, 'entries': len(entries), 'report': str(REPORT)}))


if __name__ == '__main__':
    main()
