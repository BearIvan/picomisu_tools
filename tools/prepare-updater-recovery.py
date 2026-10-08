"""Build the Source updater recovery from the offline recovery of preview 01.

The offline recovery (tools/prepare-offline-recovery.py: factory 5.13.7 kernel/DTB/ramdisk,
root ADB, recovery UI disabled, /data and /metadata out of the fstab, dmctl added) gets the
recovery side of the Source updater:
  system/bin/source-updater.sh  device/pico/PICOA8110/source-updater.sh
  init.rc                       service source_updater, started on boot
  prop.default                  ro.source.updater=<UPDATER_VERSION>
  system/etc/recovery.fstab     the factory recovery fstab (v2): /data and /metadata are listed
                                again, so the factory recovery binary can wipe userdata
                                (`recovery --wipe_data`, run on request by tools/source-ota.py);
                                recovery init still mounts nothing by itself
Without a staged package the updater exits at once, so the image still is the offline recovery
(same marker property) for tools/source-trial-install.py. The image gets an AVB hash footer
with the AOSP test key like tools/sign-offline-recovery.py (factory rollback index and salt).
No headset partition is written here. Run with python3 in WSL.

v3 and later are built from the previous updater payload (outputs/source-updater/updater-v2;
the preview-01 offline recovery was cleaned up): only source-updater.sh and the
ro.source.updater marker change.
"""
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess

UPDATER_VERSION = '3'
BASE_UPDATER = '2'
ROOT = Path(__file__).resolve().parents[1]
PROJECT = Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid')
AVB = PROJECT / 'source/external/avb/avbtool.py'
KEY = PROJECT / 'pico4-pro/source/caf-10/external/avb/test/data/testkey_rsa4096.pem'
PREVIEW = ROOT / 'outputs/vr-preview-01-installation'
FACTORY = ROOT / 'outputs/rollback-5.13.7-for-vr-preview-01/recovery.img'
SCRIPT = ROOT / 'device/pico/PICOA8110/source-updater.sh'
OUTPUT = ROOT / 'outputs/source-updater'
PARTITION_BYTES = 104857600

SERVICE = '''
# Source updater (tools/prepare-updater-recovery.py): applies a package staged by
# tools/source-ota.py in /cache/source-ota, otherwise exits at once.
service source_updater /system/bin/sh /system/bin/source-updater.sh
    user root
    group root
    seclabel u:r:recovery:s0
    oneshot
    disabled

on boot
    start source_updater
'''


def load_offline_tool():
    spec = importlib.util.spec_from_file_location('prepare_offline_recovery', ROOT / 'tools/prepare-offline-recovery.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def avb(*arguments):
    p = subprocess.run(['python3', str(AVB), *map(str, arguments)], capture_output=True, text=True, timeout=90)
    if p.returncode:
        raise RuntimeError(p.stderr.strip())
    return p.stdout + p.stderr


def main():
    tool = load_offline_tool()
    base_dir = OUTPUT / ('updater-v' + BASE_UPDATER)
    base_info = json.loads((base_dir / 'recovery.json').read_text())
    source = (base_dir / 'recovery.unsigned.img').read_bytes()
    if hashlib.sha256(source).hexdigest() != base_info['payload_sha256']:
        raise RuntimeError('Base updater payload changed')
    header = bytearray(source[:4096])
    word = lambda offset: struct.unpack_from('<I', header, offset)[0]
    ks, rs, page = word(8), word(16), word(36)
    align = lambda value: (value + page - 1) // page * page
    kernel = source[page:page + ks]
    disk = source[page + align(ks):page + align(ks) + rs]
    dtbo_start = struct.unpack_from('<Q', header, 1636)[0]
    dtbo = source[dtbo_start:dtbo_start + word(1632)]
    dtb_start = dtbo_start + align(len(dtbo))
    dtb = source[dtb_start:dtb_start + word(1648)]
    if dtbo_start != page + align(ks) + align(rs) or len(dtb) != word(1648):
        raise RuntimeError('Unexpected updater recovery layout')

    rows = tool.parse_cpio(gzip.decompress(disk))
    by_name = {row['name']: row for row in rows}
    before = {row['name']: hashlib.sha256(row['content']).hexdigest() for row in rows}
    props = by_name['prop.default']['content'].decode()
    marker = 'ro.source.updater=' + BASE_UPDATER + '\n'
    if marker not in props or 'ro.pico.recovery.offline_trial=' + tool.MARKER not in props:
        raise RuntimeError('Base updater markers missing')
    by_name['prop.default']['content'] = props.replace(marker, 'ro.source.updater=' + UPDATER_VERSION + '\n').encode()
    for tool_name in ['sh', 'dd', 'sha256sum', 'zcat', 'mount', 'umount', 'blockdev', 'setprop', 'dmctl', 'log', 'cut',
                      'grep', 'stat', 'printf', 'wc', 'sleep', 'dmesg', 'date', 'sync', 'toybox']:
        if 'system/bin/' + tool_name not in by_name:
            raise RuntimeError('Recovery lacks ' + tool_name)
    script = SCRIPT.read_bytes().replace(b'\r\n', b'\n')
    by_name['system/bin/source-updater.sh']['content'] = script
    by_name['system/bin/source-updater.sh']['fields'][6] = len(script)
    changes = sorted(r['name'] for r in rows if hashlib.sha256(r['content']).hexdigest() != before[r['name']])
    if changes != ['prop.default', 'system/bin/source-updater.sh']:
        raise RuntimeError('Unexpected ramdisk changes: %s' % changes)

    new_disk = gzip.compress(tool.serialize_cpio(rows), compresslevel=9, mtime=0)
    struct.pack_into('<I', header, 16, len(new_disk))
    struct.pack_into('<Q', header, 1636, page + align(ks) + align(len(new_disk)))
    identifier = hashlib.sha1()
    for content in (kernel, new_disk, b'', dtbo, dtb):
        identifier.update(content)
        identifier.update(struct.pack('<I', len(content)))
    header[576:608] = identifier.digest() + bytes(12)
    image = bytes(header) + kernel + bytes(align(len(kernel)) - len(kernel))
    image += new_disk + bytes(align(len(new_disk)) - len(new_disk))
    image += dtbo + bytes(align(len(dtbo)) - len(dtbo))
    image += dtb + bytes(align(len(dtb)) - len(dtb))
    check = tool.parse_cpio(gzip.decompress(image[page + align(ks):page + align(ks) + len(new_disk)]))
    if {r['name']: r['content'] for r in check} != {r['name']: r['content'] for r in rows}:
        raise RuntimeError('Ramdisk roundtrip differs')

    # avbtool verify_image looks the partition up as <dir>/recovery.img.
    out = OUTPUT / ('updater-v' + UPDATER_VERSION)
    out.mkdir(parents=True, exist_ok=True)
    unsigned = out / 'recovery.unsigned.img'
    signed = out / 'recovery.img'
    unsigned.write_bytes(image)
    info = avb('info_image', '--image', FACTORY)
    rollback = int(re.search(r'Rollback Index:\s*(\d+)', info).group(1))
    salt = re.search(r'Salt:\s*([a-f0-9]+)', info).group(1)
    shutil.copyfile(unsigned, signed)
    avb('add_hash_footer', '--image', signed, '--partition_name', 'recovery', '--partition_size', PARTITION_BYTES,
        '--algorithm', 'SHA256_RSA4096', '--key', KEY, '--rollback_index', rollback, '--hash_algorithm', 'sha256', '--salt', salt)
    avb('verify_image', '--image', signed, '--key', KEY)
    data = signed.read_bytes()
    if len(data) != PARTITION_BYTES:
        raise RuntimeError('Signed image is not the recovery partition size')
    result = {'updater_version': UPDATER_VERSION, 'path': 'C:/Users/RedPanda/Documents/ChatGPT/Android/pico4-pro/outputs/source-updater/%s/recovery.img' % out.name,
              'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
              'payload_sha256': hashlib.sha256(image).hexdigest(), 'payload_bytes': len(image),
              'based_on_updater': 'updater-v' + BASE_UPDATER, 'based_on_payload_sha256': base_info['payload_sha256'],
              'factory_recovery_sha256': hashlib.sha256(FACTORY.read_bytes()).hexdigest(),
              'script_sha256': hashlib.sha256(script).hexdigest(), 'avb_key': 'AOSP testkey_rsa4096', 'rollback_index': rollback,
              'marker': tool.MARKER}
    (out / 'recovery.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
