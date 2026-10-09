#!/usr/bin/env python3
"""Install Picomisu on a PICO 4 Pro from a repo checkout (picomisu/install.sh).

  install.sh [--wipe] [--yes]     install the release built by picomisu/build.sh
                                  (out/picomisu/outputs/source-<version>, version from release.json)
  install.sh factory [--yes]      return to the factory PICO OS 5.13.7 (system, vbmeta, recovery; wipes)
  install.sh status               headset, release, recovery
  install.sh recovery [--yes]     only build and write the updater recovery

Runs on Linux or Windows (python picomisu/tools/picomisu-install.py), with adb from PATH
(or PICOMISU_ADB). The headset must be connected over USB: the updater recovery has no Wi-Fi.

The PICO 4 Pro has no A/B slots, so system is written from recovery. The updater recovery is the
factory 5.13.7 recovery with root ADB, its UI disabled, the factory dmctl and
device/pico/PICOA8110/source-updater.sh added (built here from the pinned factory OTA). In it,
system is mapped inside super with dmctl (the LP metadata is read from the headset, checked and
never written), and system, vbmeta_system and vbmeta are streamed in verified chunks; every
partition is read back and compared by SHA-256. Writing recovery needs root on the running
system: adbd root on Picomisu userdebug, or su (Magisk) on the factory system.
"""
import argparse
import gzip
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import struct
import subprocess
import sys
import time


def _load(name, file):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(file))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


env = _load('picomisu_env', 'picomisu_env.py')
offline = _load('prepare_offline_recovery', 'prepare-offline-recovery.py')
osi = _load('offline_system_install', 'offline-system-install.py')

ADB = os.environ.get('PICOMISU_ADB') or shutil.which('adb') or 'adb'
STOCK = env.STOCK
WORK = env.WORK / 'install'
JOURNAL = WORK / 'journal.jsonl'
UPDATER = WORK / 'updater-recovery.img'
DEVICE = env.DEVICE
PART = '/dev/block/bootdevice/by-name/'
MARKER = 'pico-vr-offline-trial-01'
UPDATER_VERSION = 'picomisu-1'
MAPPER = 'pico-vr-system'
SYSTEM_BYTES = env.LOCK['images']['system']['bytes']
SYSTEM_START_SECTOR, SYSTEM_SECTORS = 2457536, 11142056
SUPER_BYTES = 8589934592
RECOVERY_BYTES = 104857600
FACTORY_DMCTL_SHA256 = '917639b88d258c4493c22f323cb221dc8559d83afe7d3d932c16131b0016dba9'
PARTITIONS = ['system', 'vbmeta_system', 'vbmeta']
# The legacy updaters of the author's workspace carry the same marker and tools.
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

osi.ADB = ADB
osi.REPORT = WORK
osi.STATE = WORK / 'transfer-state.json'


def say(text):
    print(text, flush=True)


def journal(event):
    WORK.mkdir(parents=True, exist_ok=True)
    event = dict(event, at=time.strftime('%Y-%m-%dT%H:%M:%S%z'))
    with JOURNAL.open('a', encoding='utf-8') as out:
        out.write(json.dumps(event, ensure_ascii=False) + '\n')


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def confirm(args, question, word):
    if args.yes:
        return
    answer = input('%s\nType %s to continue: ' % (question, word)).strip()
    if answer != word:
        raise SystemExit('Cancelled')


# --------------------------------------------------------------------------- adb

def adb(serial, *arguments, timeout=60, check=True, binary=False):
    command = [ADB] + (['-s', serial] if serial else []) + [str(a) for a in arguments]
    try:
        result = subprocess.run(command, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise SystemExit('adb timed out: ' + ' '.join(map(str, arguments[:2])))
    if check and result.returncode:
        raise SystemExit('adb %s failed: %s' % (arguments[0], result.stderr.decode(errors='replace').strip()))
    return result.stdout if binary else result.stdout.decode(errors='replace').strip()


def devices():
    rows = [line.split() for line in adb(None, 'devices', timeout=15).splitlines()[1:]]
    return {row[0]: row[1] for row in rows if len(row) >= 2}


def headset(serial):
    """The one connected PICO 4 Pro (or the given serial / ip:port)."""
    if serial and ':' in serial and devices().get(serial) != 'device':
        adb(None, 'connect', serial, timeout=20, check=False)
    found = [s for s, state in devices().items() if state in ('device', 'recovery') and (not serial or s == serial)]
    found = [s for s in found if adb(s, 'shell', 'getprop ro.product.device', timeout=15, check=False) == 'PICOA8110']
    if len(found) != 1:
        raise SystemExit('Expected exactly one connected PICO 4 Pro (PICOA8110), found %s; use -s SERIAL' % found)
    return found[0]


class Root:
    """Root shell on the running Android: adbd root (userdebug) or su (Magisk)."""

    def __init__(self, serial):
        self.serial, self.su = serial, False
        if adb(serial, 'shell', 'id -u', check=False) == '0':
            return
        if adb(serial, 'shell', 'getprop ro.debuggable', check=False) == '1':
            adb(serial, 'root', timeout=30, check=False)
            for _ in range(30):
                time.sleep(2)
                if ':' in serial:
                    adb(None, 'connect', serial, timeout=20, check=False)
                if devices().get(serial) == 'device' and adb(serial, 'shell', 'id -u', check=False) == '0':
                    return
        if adb(serial, 'shell', "su -c 'id -u'", timeout=60, check=False) == '0':
            self.su = True
            return
        raise SystemExit('No root on the headset: needs adbd root (Picomisu userdebug) or su (Magisk); '
                         'allow the shell in Magisk if it asks')

    def __call__(self, command, timeout=120):
        command = 'su -c ' + shlex.quote(command) if self.su else command
        return adb(self.serial, 'shell', command, timeout=timeout)


def read_bytes(run, path, offset, length):
    """Bytes of a block device read through a root shell (base64, binary-safe on every host)."""
    out = run('dd if=%s bs=4096 skip=%d count=%d 2>/dev/null | toybox base64' % (path, offset // 4096, -(-length // 4096)),
              timeout=300)
    import base64
    return base64.b64decode(''.join(out.split()))[:length]


# --------------------------------------------------------------------------- images

def release_set():
    version = json.loads((DEVICE / 'release.json').read_text())['version']
    folder = env.WORK / 'outputs' / ('source-' + version)
    sums = folder / 'SHA256SUMS.txt'
    if not sums.exists():
        raise SystemExit('No build of release %s in %s: run picomisu/build.sh first' % (version, folder))
    expected = dict(reversed(line.split()) for line in sums.read_text().splitlines() if line.strip())
    images = {}
    for part in PARTITIONS:
        path = folder / (part + '.img')
        images[part] = {'path': path, 'bytes': path.stat().st_size, 'sha256': expected[part + '.img']}
    return version, images


def factory_set():
    images = {}
    for part, key in [('system', 'system'), ('vbmeta_system', 'firmware-update/vbmeta_system.img'),
                      ('vbmeta', 'firmware-update/vbmeta.img')]:
        path = STOCK / (part + '.img')
        images[part] = {'path': path, 'bytes': path.stat().st_size, 'sha256': env.LOCK['images'][key]['sha256']}
    return images


def verify_local(images):
    for part, row in images.items():
        say('checking %s' % row['path'])
        if sha256(row['path']) != row['sha256']:
            raise SystemExit('Local image changed: ' + str(row['path']))


def boot_parts(image):
    header = bytearray(image[:4096])
    word = lambda offset: struct.unpack_from('<I', header, offset)[0]
    ks, rs, ss, page, version = [word(offset) for offset in (8, 16, 24, 36, 40)]
    if page != 4096 or version != 2 or ss != 0:
        raise SystemExit('Unsupported recovery image layout')
    align = lambda value: (value + page - 1) // page * page
    kernel = image[page:page + ks]
    disk = image[page + align(ks):page + align(ks) + rs]
    dtbo_start = struct.unpack_from('<Q', header, 1636)[0]
    dtbo = image[dtbo_start:dtbo_start + word(1632)]
    dtb_start = dtbo_start + align(len(dtbo))
    dtb = image[dtb_start:dtb_start + word(1648)]
    return header, page, align, kernel, disk, dtbo, dtb


def ramdisk_props(run):
    """prop.default of the recovery partition's ramdisk (None if it is not a parsable recovery)."""
    head = read_bytes(run, PART + 'recovery', 0, 4096)
    word = lambda offset: struct.unpack_from('<I', head, offset)[0]
    ks, rs, page = word(8), word(16), word(36)
    if head[:8] != b'ANDROID!' or page != 4096:
        return None
    start = page + (ks + page - 1) // page * page
    data = read_bytes(run, PART + 'recovery', start, rs)
    try:
        rows = offline.parse_cpio(gzip.decompress(data))
    except (OSError, RuntimeError, EOFError):
        return None
    prop = next((r['content'].decode(errors='replace') for r in rows if r['name'] == 'prop.default'), '')
    return dict(line.split('=', 1) for line in prop.splitlines() if '=' in line and not line.startswith('#'))


def build_updater():
    """The updater recovery from the factory recovery of the pinned OTA (cached in out/picomisu/install)."""
    factory = (STOCK / 'recovery.img').read_bytes()
    if hashlib.sha256(factory).hexdigest() != env.LOCK['images']['recovery.img']['sha256']:
        raise SystemExit('Factory recovery differs from the lock: run picomisu/build.sh')
    dmctl_path = env.WORK / 'analysis/stock-5.13.7-system/root/system/bin/dmctl'
    dmctl = dmctl_path.read_bytes()
    if hashlib.sha256(dmctl).hexdigest() != FACTORY_DMCTL_SHA256:
        raise SystemExit('Factory dmctl missing or changed: run picomisu/build.sh')
    script = (DEVICE / 'source-updater.sh').read_bytes().replace(b'\r\n', b'\n')
    header, page, align, kernel, disk, dtbo, dtb = boot_parts(factory)
    rows = offline.parse_cpio(gzip.decompress(disk))
    by_name = {row['name']: row for row in rows}
    init = by_name['init.rc']['content'].decode()
    if init.count('service recovery /system/bin/recovery\n') != 1:
        raise SystemExit('Unexpected factory recovery init.rc')
    init = init.replace('service recovery /system/bin/recovery\n', 'service recovery /system/bin/recovery\n    disabled\n')
    by_name['init.rc']['content'] = (init + SERVICE).encode()
    props = by_name['prop.default']['content'].decode()
    for key, value in {'ro.secure': '0', 'ro.adb.secure': '0', 'ro.debuggable': '1', 'persist.sys.usb.config': 'adb'}.items():
        props, count = re.subn(r'^' + re.escape(key) + r'=.*$', key + '=' + value, props, flags=re.MULTILINE)
        if not count:
            raise SystemExit('Factory recovery lacks ' + key)
    props += '\nro.pico.recovery.offline_trial=' + MARKER + '\nro.source.updater=' + UPDATER_VERSION + '\n'
    by_name['prop.default']['content'] = props.encode()
    # Inode numbers as in the updaters installed so far (dmctl after the factory entries, the script at 200000).
    for name, content, inode in [('system/bin/dmctl', dmctl, 100000 + len(rows)),
                                 ('system/bin/source-updater.sh', script, 200000)]:
        rows.append({'name': name, 'content': content,
                     'fields': [inode, 0o100755, 0, 2000, 1, 0, len(content), 0, 0, 0, 0, len(name) + 1, 0]})
    for tool in ['sh', 'dd', 'sha256sum', 'toybox', 'blockdev', 'mount']:
        if 'system/bin/' + tool not in {r['name'] for r in rows}:
            raise SystemExit('Factory recovery lacks ' + tool)
    new_disk = gzip.compress(offline.serialize_cpio(rows), compresslevel=9, mtime=0)
    struct.pack_into('<I', header, 16, len(new_disk))
    struct.pack_into('<Q', header, 1636, page + align(len(kernel)) + align(len(new_disk)))
    identifier = hashlib.sha1()
    for content in (kernel, new_disk, b'', dtbo, dtb):
        identifier.update(content)
        identifier.update(struct.pack('<I', len(content)))
    header[576:608] = identifier.digest() + bytes(12)
    image = bytes(header) + kernel + bytes(align(len(kernel)) - len(kernel))
    image += new_disk + bytes(align(len(new_disk)) - len(new_disk))
    image += dtbo + bytes(align(len(dtbo)) - len(dtbo)) + dtb + bytes(align(len(dtb)) - len(dtb))
    check = offline.parse_cpio(gzip.decompress(boot_parts(image)[4]))
    if {r['name']: r['content'] for r in check} != {r['name']: r['content'] for r in rows}:
        raise SystemExit('Updater ramdisk roundtrip differs')
    WORK.mkdir(parents=True, exist_ok=True)
    (WORK / 'updater-recovery.unsigned.img').write_bytes(image)
    UPDATER.write_bytes(image)
    # AVB hash footer like the factory recovery's (rollback index and salt), AOSP test key.
    avbtool = [sys.executable, str(env.AVBTOOL)]
    info = subprocess.run(avbtool + ['info_image', '--image', str(STOCK / 'recovery.img')],
                          capture_output=True, text=True, check=True).stdout
    rollback = re.search(r'Rollback Index:\s*(\d+)', info).group(1)
    salt = re.search(r'Salt:\s*([a-f0-9]+)', info).group(1)
    key = env.TOP / 'external/avb/test/data/testkey_rsa4096.pem'
    subprocess.run(avbtool + ['add_hash_footer', '--image', str(UPDATER), '--partition_name', 'recovery',
                              '--partition_size', str(RECOVERY_BYTES), '--algorithm', 'SHA256_RSA4096',
                              '--key', str(key), '--rollback_index', rollback, '--hash_algorithm', 'sha256',
                              '--salt', salt], check=True, capture_output=True)
    if UPDATER.stat().st_size != RECOVERY_BYTES:
        raise SystemExit('Updater recovery is not the partition size')
    say('updater recovery %s  %s' % (UPDATER, sha256(UPDATER)))
    return UPDATER


# --------------------------------------------------------------------------- recovery side

def write_recovery_from_android(serial, image, args, why):
    confirm(args, 'Write %s to the recovery partition (%s)?' % (image.name, why), 'RECOVERY')
    run = Root(serial)
    if int(run('blockdev --getsize64 ' + PART + 'recovery')) != RECOVERY_BYTES:
        raise SystemExit('Unexpected recovery partition size')
    local = sha256(image)
    temp = '/data/local/tmp/picomisu-recovery.img'
    adb(serial, 'push', image, temp, timeout=300)
    if run('sha256sum ' + temp).split()[0] != local:
        raise SystemExit('Pushed recovery image differs; nothing written')
    journal({'step': 'recovery-write', 'image_sha256': local})
    run('dd if=%s of=%srecovery bs=1048576 && sync' % (temp, PART), timeout=180)
    after = run('sha256sum %srecovery' % PART, timeout=180).split()[0]
    run('rm -f ' + temp)
    if after != local:
        raise SystemExit('Recovery readback mismatch: ' + after)
    journal({'step': 'recovery-verified', 'sha256': after})
    say('recovery written and verified')


def ensure_updater(serial, args):
    run = Root(serial)
    props = ramdisk_props(run) or {}
    if props.get('ro.pico.recovery.offline_trial') == MARKER:
        say('recovery: updater (%s)' % props.get('ro.source.updater', '?'))
        return
    write_recovery_from_android(serial, build_updater(), args, 'the current recovery is not a Picomisu updater')


def wait_recovery(minutes=10):
    say('waiting for the updater recovery on USB')
    deadline = time.time() + minutes * 60
    while time.time() < deadline:
        time.sleep(5)
        for serial, state in devices().items():
            if state not in ('recovery', 'device') or ':' in serial:
                continue
            get = lambda prop: adb(serial, 'shell', 'getprop ' + prop, timeout=15, check=False)
            if get('ro.pico.recovery.offline_trial') != MARKER or get('ro.product.device') != 'PICOA8110':
                continue
            if get('init.svc.source_updater') == 'running':
                continue
            if adb(serial, 'shell', 'id -u', check=False) != '0':
                raise SystemExit('Updater recovery without root ADB')
            return serial
    raise SystemExit('The updater recovery did not appear on USB (the recovery has no Wi-Fi: connect USB)')


def lp_check(serial):
    """Read the super LP metadata from the headset and check the system extent (nothing is written)."""
    shell = lambda c, timeout=60: adb(serial, 'shell', c, timeout=timeout)
    if int(shell('blockdev --getsize64 ' + PART + 'super')) != SUPER_BYTES:
        raise SystemExit('Unexpected super size')
    data = read_bytes(shell, PART + 'super', 0, 1 << 20)
    geometry = data[4096:4148]
    magic, size, _, max_size, slots, _ = struct.unpack('<II32sIII', geometry)
    lp = _load('parse_lp', 'parse-lp-metadata.py')
    if magic != 0x616c4467 or size != 52 or not lp.valid_checksum(geometry, 8) or data[8192:8244] != geometry:
        raise SystemExit('Invalid LP geometry')
    offset = 12288  # primary metadata, slot 0
    magic, major, minor, hsize = struct.unpack_from('<IHHI', data, offset)
    header = data[offset:offset + hsize]
    tables_size = struct.unpack_from('<I', header, 44)[0]
    tables = data[offset + hsize:offset + hsize + tables_size]
    if (magic, major, minor, hsize) != (0x414c5030, 10, 0, 128) or not lp.valid_checksum(header, 12) \
            or hashlib.sha256(tables).digest() != header[48:80]:
        raise SystemExit('Invalid LP metadata')
    descriptors = [struct.unpack_from('<III', header, 80 + j * 12) for j in range(4)]
    parts = [struct.unpack('<36sIIII', tables[descriptors[0][0] + n * 52:descriptors[0][0] + (n + 1) * 52])
             for n in range(descriptors[0][1])]
    extents = [struct.unpack('<QIQI', tables[descriptors[1][0] + n * 24:descriptors[1][0] + (n + 1) * 24])
               for n in range(descriptors[1][1])]
    system = [p for p in parts if p[0].split(b'\0')[0] == b'system']
    if len(system) != 1:
        raise SystemExit('No single system partition in the LP metadata')
    first, count = system[0][2], system[0][3]
    if extents[first:first + count] != [(SYSTEM_SECTORS, 0, SYSTEM_START_SECTOR, 0)]:
        raise SystemExit('Unexpected system extent layout: %s' % (extents[first:first + count],))
    return hashlib.sha256(data).hexdigest()


def write_partitions(serial, images):
    mounts = adb(serial, 'shell', 'cat /proc/mounts')
    if any(l.split()[0].startswith('/dev/block') and l.split()[2] not in ('tmpfs', 'devtmpfs') for l in mounts.splitlines()):
        raise SystemExit('A storage filesystem is mounted in recovery; nothing written')
    lp = lp_check(serial)
    adb(serial, 'shell', 'dmctl delete %s > /dev/null 2>&1; true' % MAPPER)
    adb(serial, 'shell', 'dmctl create %s linear 0 %d %ssuper %d' % (MAPPER, SYSTEM_SECTORS, PART, SYSTEM_START_SECTOR))
    target = adb(serial, 'shell', 'dmctl getpath ' + MAPPER)
    if not re.fullmatch(r'/dev/block/dm-[0-9]+', target):
        raise SystemExit('Unexpected mapped device ' + target)
    for _ in range(20):
        if adb(serial, 'shell', 'blockdev --getsize64 ' + target, check=False) == str(SYSTEM_BYTES):
            break
        time.sleep(0.25)
    else:
        raise SystemExit('Mapped system has an unexpected size')
    journal({'step': 'mapped', 'target': target, 'super_lp_sha256': lp})
    osi.fixture(serial, {})
    try:
        for part in PARTITIONS:
            row = images[part]
            block = target if part == 'system' else PART + part
            if int(adb(serial, 'shell', 'blockdev --getsize64 ' + block)) != row['bytes']:
                raise SystemExit('Size mismatch: ' + part)
            if osi.remote_hash(serial, block) == row['sha256']:
                say(part + ': already the target')
                continue
            journal({'step': 'write', 'partition': part, 'sha256': row['sha256']})

            def progress(count, part=part, size=row['bytes']):
                say('%s: %d/%d MiB' % (part, count >> 20, size >> 20))
            with open(row['path'], 'rb') as reader:
                sent, _ = osi.stream_to_device(serial, reader, block, row['bytes'], progress, verify_existing=True)
            readback = osi.remote_hash(serial, block)
            if sent != row['sha256'] or readback != row['sha256']:
                journal({'step': 'failed', 'partition': part, 'readback': readback})
                raise SystemExit('Readback mismatch: ' + part)
            journal({'step': 'verified', 'partition': part})
            say(part + ': written and verified')
    finally:
        adb(serial, 'shell', 'sync; dmctl delete ' + MAPPER, check=False)


def wait_android(serial, minutes=8):
    deadline = time.time() + minutes * 60
    while time.time() < deadline:
        time.sleep(5)
        if ':' in serial:
            adb(None, 'connect', serial, timeout=20, check=False)
        for candidate, state in devices().items():
            if state == 'device' and adb(candidate, 'shell', 'getprop sys.boot_completed', timeout=15, check=False) == '1':
                if adb(candidate, 'shell', 'getprop ro.product.device', check=False) == 'PICOA8110':
                    return candidate
    raise SystemExit('Android did not finish booting; check the headset')


def in_updater(serial):
    return (devices().get(serial) == 'recovery'
            and adb(serial, 'shell', 'getprop ro.pico.recovery.offline_trial', check=False) == MARKER)


def flash(serial, images, wipe, factory_recovery=False):
    if in_updater(serial):
        say('the headset is already in the updater recovery: continuing there')
        rec = serial
    else:
        say('rebooting into the updater recovery')
        adb(serial, 'reboot', 'recovery', timeout=30, check=False)
        rec = wait_recovery()
    write_partitions(rec, images)
    if factory_recovery:
        recovery = {'path': STOCK / 'recovery.img', 'bytes': RECOVERY_BYTES,
                    'sha256': env.LOCK['images']['recovery.img']['sha256']}
        if osi.remote_hash(rec, PART + 'recovery') != recovery['sha256']:
            with open(recovery['path'], 'rb') as reader:
                sent, _ = osi.stream_to_device(rec, reader, PART + 'recovery', RECOVERY_BYTES, verify_existing=True)
            if osi.remote_hash(rec, PART + 'recovery') != recovery['sha256']:
                raise SystemExit('Factory recovery readback mismatch')
        say('recovery: factory 5.13.7 restored')
    if wipe:
        journal({'step': 'wipe'})
        say('wiping userdata (factory recovery binary); the headset reboots when done')
        out = adb(rec, 'shell', '/system/bin/recovery --wipe_data > /tmp/picomisu-wipe.log 2>&1; cat /tmp/picomisu-wipe.log',
                  timeout=900, check=False)
        say(out[-1500:])
    else:
        adb(rec, 'reboot', timeout=30, check=False)
    android = wait_android(serial)
    say('booted: %s' % adb(android, 'shell', 'getprop ro.build.display.id'))
    journal({'step': 'booted', 'display_id': adb(android, 'shell', 'getprop ro.build.display.id')})


# --------------------------------------------------------------------------- commands

def cmd_status(args):
    serial = headset(args.serial)
    get = lambda prop: adb(serial, 'shell', 'getprop ' + prop, check=False)
    info = {'serial': serial, 'state': devices().get(serial), 'display_id': get('ro.build.display.id'),
            'picomisu': get('ro.source.version') or None, 'battery': adb(serial, 'shell', 'dumpsys battery | grep level', check=False)}
    try:
        props = ramdisk_props(Root(serial)) or {}
        info['recovery'] = ('updater ' + props.get('ro.source.updater', '?')) if props.get('ro.pico.recovery.offline_trial') == MARKER else 'not an updater'
    except SystemExit as error:
        info['recovery'] = 'unknown (%s)' % error
    print(json.dumps(info, indent=1, ensure_ascii=False))


def cmd_install(args):
    version, images = release_set()
    verify_local(images)
    serial = headset(args.serial)
    if ':' in serial:
        raise SystemExit('Connect the headset over USB (the updater recovery has no Wi-Fi)')
    if in_updater(serial):
        # An interrupted install: Android is not running, so the release and battery checks were done before.
        say('headset: in the updater recovery -> Picomisu Source %s' % version)
    else:
        current = adb(serial, 'shell', 'getprop ro.source.version', check=False)
        level = int(re.search(r'\d+', adb(serial, 'shell', 'dumpsys battery | grep level')).group(0))
        if level < 30:
            raise SystemExit('Battery %d%% < 30%%' % level)
        say('headset: %s -> Picomisu Source %s' % ('Picomisu ' + current if current else 'factory system', version))
        if not current and not args.wipe:
            raise SystemExit('The first install over the factory system needs --wipe (userdata is erased)')
    if args.wipe:
        confirm(args, 'This ERASES userdata on the headset (games, recordings, settings).', 'WIPE')
    if not in_updater(serial):
        ensure_updater(serial, args)
    journal({'step': 'install', 'version': version, 'wipe': args.wipe})
    flash(serial, images, args.wipe)


def cmd_factory(args):
    images = factory_set()
    verify_local(images)
    serial = headset(args.serial)
    confirm(args, 'Return to factory PICO OS 5.13.7: system, vbmeta and recovery are restored and userdata is ERASED.', 'WIPE')
    if not in_updater(serial):
        ensure_updater(serial, args)
    journal({'step': 'factory'})
    flash(serial, images, wipe=True, factory_recovery=True)


def cmd_recovery(args):
    serial = headset(args.serial)
    write_recovery_from_android(serial, build_updater(), args, 'requested')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('command', nargs='?', default='install', choices=['install', 'factory', 'status', 'recovery', 'build-updater'])
    parser.add_argument('-s', '--serial', default=os.environ.get('ANDROID_SERIAL'))
    parser.add_argument('--wipe', action='store_true', help='erase userdata (required over the factory system)')
    parser.add_argument('--yes', action='store_true', help='do not ask for confirmation')
    args = parser.parse_args()
    if env.LEGACY:
        raise SystemExit('Run from a picomisu repo checkout (picomisu/install.sh)')
    WORK.mkdir(parents=True, exist_ok=True)
    {'install': cmd_install, 'factory': cmd_factory, 'status': cmd_status, 'recovery': cmd_recovery,
     'build-updater': lambda a: build_updater()}[args.command](args)


if __name__ == '__main__':
    main()
