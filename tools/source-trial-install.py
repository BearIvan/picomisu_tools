"""Install a Source trial kit on the PICO 4 Pro with the method used for preview 01.

Method (outputs/vr-preview-01-installation/state.json): PICO OEM session
authorization in the bootloader (fastboot oem <key> unlock on the already
unlocked device), RAM boot of the signed offline recovery (fastboot boot, no
recovery partition write), kernel-only dm-linear mapping of the logical system
inside super (dmctl, LP metadata untouched), SHA-256-verified adb-sync chunks
written with dd, readback of system/vbmeta_system/vbmeta, reboot. Boot (Magisk)
and super/LP metadata are never written. The factory recovery partition stays.

The kit directory (default outputs/source-trial-01-installation) holds kit.json
(inputs and accepted current hashes) and state.json (authorizations and a write
journal). Every stage that writes requires its authorization in state.json,
which the operator sets only after the user's explicit consent:
  check      local only: kit files, sizes and SHA-256 (no device access)
  preflight  read only: Android ADB identity, boot/recovery/system/vbmeta hashes
  authorize  bootloader: fastboot oem <key> unlock session authorization  [authorized.fastboot]
  ram-boot   bootloader: fastboot boot of the offline recovery (RAM only)  [authorized.fastboot]
  map        offline recovery: LP guard, dm mapping, current hashes, transport fixture (no writes)
  flash      offline recovery: system, vbmeta_system, vbmeta + readback  [authorized.flash]
  bcb-wipe   offline recovery: misc BCB 'boot-recovery / --wipe_data'     [authorized.wipe]
  logs       offline recovery or Android: read-only log collection (pstore, dmesg, props)
  rollback   offline recovery: write kit.rollback[<name>] images            [authorized.rollback]
Nothing in this file runs automatically; each stage is invoked explicitly.
"""
import argparse
import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
SDK = Path('C:/Users/RedPanda/AppData/Local/Android/Sdk/platform-tools')
ADB = str(SDK / 'adb.exe')
FASTBOOT = os.environ.get('PICO_FASTBOOT', str(SDK / 'fastboot.exe'))
KEY_SOURCE = Path('C:/Users/RedPanda/Downloads/picounlock-windows-x86_64/FAILSAFE_UNLOCK.bat')
OFFLINE_MARKER = 'pico-vr-offline-trial-01'


def load_osi(kit):
    spec = importlib.util.spec_from_file_location('offline_system_install', Path(__file__).with_name('offline-system-install.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.REPORT = kit
    module.STATE = kit / 'state.json'
    return module


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def sha(value):
    return hashlib.sha256(value.encode()).hexdigest()


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 ** 2), b''):
            digest.update(chunk)
    return digest.hexdigest()


class Kit:
    def __init__(self, directory):
        self.dir = Path(directory)
        self.kit = json.loads((self.dir / 'kit.json').read_text(encoding='utf-8'))
        self.state_file = self.dir / 'state.json'
        self.state = json.loads(self.state_file.read_text(encoding='utf-8'))

    def save(self):
        self.state_file.write_text(json.dumps(self.state, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    def require(self, name):
        if not self.state.get('authorized', {}).get(name):
            raise RuntimeError('Not authorized in state.json: ' + name + ' (needs the user\'s explicit consent)')

    def verify_file(self, row):
        path = Path(row['path'])
        if path.stat().st_size != row['bytes'] or file_hash(path) != row['sha256']:
            raise RuntimeError('Local kit file failed verification: ' + str(path))


def run(tool, arguments, timeout=30, check=True):
    try:
        result = subprocess.run([tool, *arguments], capture_output=True, text=True, timeout=timeout,
                                encoding='utf-8', errors='replace')
    except subprocess.TimeoutExpired:
        raise RuntimeError(Path(tool).name + ' timed out; inspect the USB state before retrying') from None
    output = (result.stdout + result.stderr).strip()
    if check and (result.returncode or 'FAILED' in output):
        raise RuntimeError(output)
    return output


def devices(tool):
    output = run(ADB if tool == 'adb' else FASTBOOT, ['devices'], 15, check=False)
    wanted = {'device', 'recovery'} if tool == 'adb' else {'fastboot'}
    return [p[0] for line in output.splitlines() if len(p := line.split()) >= 2 and p[1] in wanted]


def android_shell(serial, command, root=False, timeout=90):
    """Android shell; root through adbd root (Source userdebug) or Magisk su (preview/factory)."""
    if root and run(ADB, ['-s', serial, 'shell', 'id -u'], 15) != '0':
        if run(ADB, ['-s', serial, 'shell', 'getprop ro.debuggable'], 15) == '1':
            run(ADB, ['-s', serial, 'root'], 30, False)
            run(ADB, ['-s', serial, 'wait-for-device'], 60)
        if run(ADB, ['-s', serial, 'shell', 'id -u'], 15) != '0':
            command = 'su -c ' + shlex.quote(command)
    return run(ADB, ['-s', serial, 'shell', command], timeout)


# --------------------------------------------------------------------------- stages

def check(kit):
    rows = dict(kit.kit['images'])
    rows['offline_recovery'] = kit.kit['offline_recovery']
    rows['factory_recovery'] = kit.kit['factory_recovery']
    rows['bcb_wipe'] = kit.kit['bcb_wipe']
    for name, images in kit.kit['rollback'].items():
        for part, row in images.items():
            rows['rollback/' + name + '/' + part] = row
    result = {}
    for name, row in rows.items():
        kit.verify_file(row)
        result[name] = row['sha256']
    bcb = Path(kit.kit['bcb_wipe']['path']).read_bytes()
    if len(bcb) != 2048 or not bcb.startswith(b'boot-recovery\0') or b'--wipe_data' not in bcb[64:832]:
        raise RuntimeError('Unexpected BCB file')
    print(json.dumps({'kit_files_verified': result, 'device_accessed': False}, indent=1))


def preflight(kit):
    active = devices('adb')
    if len(active) != 1:
        raise RuntimeError('Expected exactly one ADB device')
    serial = active[0]
    if run(ADB, ['-s', serial, 'shell', 'getprop ro.product.device']) != 'PICOA8110':
        raise RuntimeError('Unexpected model')
    report = {'at_utc': now(), 'serial_sha256': sha(serial),
              'fingerprint': run(ADB, ['-s', serial, 'shell', 'getprop ro.build.fingerprint']),
              'boot_completed': run(ADB, ['-s', serial, 'shell', 'getprop sys.boot_completed'])}
    for name in ['boot', 'recovery', 'vbmeta', 'vbmeta_system']:
        report[name] = android_shell(serial, 'toybox sha256sum /dev/block/bootdevice/by-name/' + name, True, 180).split()[0]
    report['system'] = android_shell(serial, 'toybox sha256sum /dev/block/mapper/system', True, 600).split()[0]
    report['battery_level'] = re.search(r'level: (\d+)', run(ADB, ['-s', serial, 'shell', 'dumpsys battery'])).group(1)
    accepted = kit.kit['accepted_current']
    report['checks'] = {
        'boot_is_kit_boot': report['boot'] == kit.kit['boot_sha256'],
        'recovery_is_factory': report['recovery'] == kit.kit['factory_recovery']['sha256'],
        **{name + '_accepted': report[name] in accepted[name] for name in ['system', 'vbmeta_system', 'vbmeta']}}
    kit.state.setdefault('preflights', []).append(report)
    kit.save()
    print(json.dumps(report, indent=1))
    if not all(report['checks'].values()):
        raise RuntimeError('Preflight failed: ' + str(report['checks']))


def oem_key():
    text = KEY_SOURCE.read_text(encoding='utf-8-sig')
    match = re.search(r'set\s+"PICO=(pico[A-Z0-9]+)"', text, re.I)
    if not match:
        raise RuntimeError('Saved OEM key was not found')
    return match.group(1)


def bootloader(kit, from_android):
    if from_android:
        active = devices('adb')
        if len(active) != 1:
            raise RuntimeError('Expected exactly one ADB device')
        serial = active[0]
        boot = android_shell(serial, 'toybox sha256sum /dev/block/bootdevice/by-name/boot', True, 120).split()[0]
        if boot != kit.kit['boot_sha256']:
            raise RuntimeError('Boot changed; the kit vbmeta is bound to the current boot')
        run(ADB, ['-s', serial, 'reboot', 'bootloader'])
    for _ in range(45):
        active = devices('fastboot')
        if len(active) == 1:
            break
        time.sleep(2)
    else:
        raise RuntimeError('Bootloader USB did not appear (use the key combination if Android does not boot)')
    serial = active[0]
    if sha(serial) != kit.state['bootloader_serial_sha256']:
        raise RuntimeError('Unexpected bootloader identity')
    if not re.search(r'unlocked:\s*yes', run(FASTBOOT, ['-s', serial, 'getvar', 'unlocked'])):
        raise RuntimeError('Bootloader must already be unlocked; never run an unlock workflow here')
    return serial


def authorize(kit, from_android):
    kit.require('fastboot')
    serial = bootloader(kit, from_android)
    output = run(FASTBOOT, ['-s', serial, 'oem', oem_key(), 'unlock'])
    event = {'at_utc': now(), 'stage': 'oem-session-authorization', 'output': output.replace(oem_key(), '<key>')}
    kit.state.setdefault('events', []).append(event)
    kit.save()
    print(json.dumps(event))


def ram_boot(kit):
    kit.require('fastboot')
    row = kit.kit['offline_recovery']
    kit.verify_file(row)
    active = devices('fastboot')
    if len(active) != 1 or sha(active[0]) != kit.state['bootloader_serial_sha256']:
        raise RuntimeError('Expected the authorized PICO bootloader')
    event = {'at_utc': now(), 'stage': 'ram-boot-offline-recovery', 'image_sha256': row['sha256'], 'partition_write': False}
    kit.state.setdefault('events', []).append(event)
    kit.save()
    run(FASTBOOT, ['-s', active[0], 'boot', row['path']], 60)
    for _ in range(60):
        adb = devices('adb')
        if len(adb) == 1 and run(ADB, ['-s', adb[0], 'shell', 'getprop ro.pico.recovery.offline_trial'], 15, False) == OFFLINE_MARKER:
            if run(ADB, ['-s', adb[0], 'shell', 'id -u']) != '0':
                raise RuntimeError('Offline recovery without root')
            mounts = run(ADB, ['-s', adb[0], 'shell', 'cat /proc/mounts'])
            if any(line.split()[0].startswith('/dev/block') for line in mounts.splitlines()):
                raise RuntimeError('Block-backed filesystem mounted in offline recovery')
            if sha(adb[0]) != kit.state['offline_adb_serial_sha256']:
                raise RuntimeError('Unexpected offline recovery ADB identity')
            event['status'] = 'verified-root-adb'
            # A new RAM-booted recovery has no dm mapping and needs a new transport check.
            for key in ['offline_mapping', 'offline_binary_transport']:
                kit.state.pop(key, None)
            kit.state['stage'] = 'offline-recovery-ready'
            kit.save()
            print(json.dumps(event))
            return
        time.sleep(2)
    raise RuntimeError('Offline recovery ADB did not appear; nothing was written')


def mapped(kit, osi):
    serial = osi.root_device(kit.state)
    if osi.remote_hash(serial, '/dev/block/bootdevice/by-name/boot') != kit.kit['boot_sha256']:
        raise RuntimeError('Boot changed')
    target = osi.map_system(serial, kit.state)
    return serial, target


def map_stage(kit, osi, resume=False):
    serial, target = mapped(kit, osi)
    current = {'system': osi.remote_hash(serial, target)}
    for part in ['vbmeta_system', 'vbmeta']:
        current[part] = osi.remote_hash(serial, '/dev/block/bootdevice/by-name/' + part)
    # --resume: a partition partially written by this kit's own interrupted write is accepted.
    interrupted = {w['partition'] for w in kit.state.get('writes', [])
                   if w.get('status') in ('failed', 'started') and w.get('scope') == kit.kit['name']
                   and w.get('image_sha256') == kit.kit['images'][w['partition']]['sha256']}
    for part, value in current.items():
        if value not in kit.kit['accepted_current'][part]:
            if not (resume and part in interrupted):
                raise RuntimeError('Current ' + part + ' is not an accepted known state: ' + value)
            kit.state.setdefault('events', []).append({'at_utc': now(), 'stage': 'resume-accepted-partial-write',
                                                       'partition': part, 'current_sha256': value})
    osi.fixture(serial, kit.state)
    kit.state['current_before_write'] = current
    kit.state['stage'] = 'offline-write-preflight-passed'
    kit.save()
    print(json.dumps({'mapping': kit.state['offline_mapping']['path'], 'current': current, 'transport_verified': True}))


def write_set(kit, osi, images, scope):
    serial, target = mapped(kit, osi)
    if kit.state.get('stage') != 'offline-write-preflight-passed':
        raise RuntimeError('Run the map stage first in this offline recovery session')
    for part in ['system', 'vbmeta_system', 'vbmeta']:
        kit.verify_file(images[part])
    for part in ['system', 'vbmeta_system', 'vbmeta']:
        osi.root_device(kit.state)
        osi.lp_guard(serial)
        block = target if part == 'system' else '/dev/block/bootdevice/by-name/' + part
        row = images[part]
        if int(osi.shell(serial, 'blockdev --getsize64 ' + block)) != row['bytes']:
            raise RuntimeError('Target size mismatch: ' + part)
        event = {'partition': part, 'scope': scope, 'image_sha256': row['sha256'], 'bytes': row['bytes'],
                 'status': 'started', 'at_utc': now()}
        kit.state.setdefault('writes', []).append(event)
        kit.save()

        def progress(count):
            event['bytes_sent'] = count
            kit.save()
            print(part + ': %d/%d bytes' % (count, row['bytes']), flush=True)
        try:
            with Path(row['path']).open('rb') as reader:
                sent, output = osi.stream_to_device(serial, reader, block, row['bytes'], progress,
                                                    verify_existing=True)
            if sent != row['sha256']:
                raise RuntimeError('Input changed during transfer')
            readback = osi.remote_hash(serial, block)
            if readback != row['sha256']:
                raise RuntimeError('Readback mismatch')
            event.update(status='verified', readback_sha256=readback, dd_output=output, finished_at_utc=now())
            kit.save()
        except BaseException as error:
            event.update(status='failed', error=str(error))
            kit.state['stage'] = 'offline-write-failed'
            kit.save()
            raise
    osi.shell(serial, 'sync', timeout=90)
    osi.lp_guard(serial)
    if osi.remote_hash(serial, '/dev/block/bootdevice/by-name/boot') != kit.kit['boot_sha256']:
        raise RuntimeError('Boot changed after writes')
    kit.state['stage'] = scope + '-written'
    kit.save()
    print(json.dumps({'written': scope, 'readback_verified': True, 'boot_preserved': True, 'lp_metadata_preserved': True}))


def bcb_wipe(kit, osi):
    kit.require('wipe')
    serial = osi.root_device(kit.state)
    row = kit.kit['bcb_wipe']
    kit.verify_file(row)
    misc = '/dev/block/bootdevice/by-name/misc'
    before = osi.shell(serial, 'dd if=' + misc + ' bs=2048 count=1 2>/dev/null', binary=True)
    if len(before) != 2048:
        raise RuntimeError('Could not read the current BCB')
    (kit.dir / ('misc-bcb-before-wipe-%d.bin' % int(time.time()))).write_bytes(before)
    remote = '/tmp/pico-bcb-wipe.bin'
    run(ADB, ['-s', serial, 'push', row['path'], remote], 60)
    if osi.remote_hash(serial, remote) != row['sha256']:
        raise RuntimeError('Staged BCB hash mismatch')
    event = {'partition': 'misc', 'scope': 'bcb-wipe-data', 'bytes': 2048, 'image_sha256': row['sha256'],
             'before_sha256': hashlib.sha256(before).hexdigest(), 'at_utc': now()}
    kit.state.setdefault('writes', []).append(event)
    kit.save()
    osi.shell(serial, 'dd if=' + remote + ' of=' + misc + ' bs=2048 count=1 conv=notrunc,fsync')
    after = osi.shell(serial, 'dd if=' + misc + ' bs=2048 count=1 2>/dev/null', binary=True)
    if hashlib.sha256(after).hexdigest() != row['sha256']:
        event['status'] = 'failed-readback'
        kit.save()
        raise RuntimeError('BCB readback mismatch')
    osi.shell(serial, 'rm -f ' + remote)
    event['status'] = 'verified'
    kit.save()
    print(json.dumps(event))


def logs(kit):
    active = devices('adb')
    if len(active) != 1:
        raise RuntimeError('Expected exactly one ADB device')
    serial = active[0]
    folder = kit.dir / ('logs-' + datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
    folder.mkdir()
    offline = run(ADB, ['-s', serial, 'shell', 'getprop ro.pico.recovery.offline_trial'], 15, False) == OFFLINE_MARKER
    commands = {'getprop.txt': 'getprop', 'dmesg.txt': 'dmesg', 'mounts.txt': 'cat /proc/mounts',
                'pstore-list.txt': 'ls -la /sys/fs/pstore'}
    if offline:
        # pstore is a RAM-backed pseudo filesystem; mounting it writes no partition.
        run(ADB, ['-s', serial, 'shell', 'mountpoint -q /sys/fs/pstore || mount -t pstore pstore /sys/fs/pstore'], 15, False)
    else:
        run(ADB, ['-s', serial, 'root'], 30, False)
        time.sleep(3)
        commands.update({'logcat-all.txt': 'logcat -b all -d', 'logcat-last-boot.txt': 'logcat -L -b all -d',
                         'tombstones.txt': 'ls -la /data/tombstones', 'dropbox.txt': 'dumpsys dropbox --print',
                         'bootreason.txt': 'getprop | grep -i reason', 'avc.txt': 'dmesg | grep -i avc',
                         'logd-persist.txt': 'ls -la /data/misc/logd'})
    for name, command in commands.items():
        (folder / name).write_text(run(ADB, ['-s', serial, 'shell', command], 300, False), encoding='utf-8')
    names = run(ADB, ['-s', serial, 'shell', 'ls /sys/fs/pstore'], 30, False).split()
    for name in names:
        run(ADB, ['-s', serial, 'pull', '/sys/fs/pstore/' + name, str(folder / ('pstore-' + name))], 120, False)
    if offline:
        # Trial diagnostics (01c+) on the unencrypted /cache; read-only mount without journal replay.
        cache = '/tmp/trial-cache'
        run(ADB, ['-s', serial, 'shell', 'mkdir -p %s && mount -t ext4 -o ro,noload '
                  '/dev/block/bootdevice/by-name/cache %s' % (cache, cache)], 30, False)
        try:
            (folder / 'cache-trial-list.txt').write_text(
                run(ADB, ['-s', serial, 'shell', 'ls -laR %s/trial; df %s' % (cache, cache)], 30, False), encoding='utf-8')
            run(ADB, ['-s', serial, 'pull', cache + '/trial', str(folder / 'cache-trial')], 600, False)
        finally:
            run(ADB, ['-s', serial, 'shell', 'umount ' + cache], 30, False)
    else:
        run(ADB, ['-s', serial, 'pull', '/data/misc/logd', str(folder / 'logd')], 600, False)
        run(ADB, ['-s', serial, 'pull', '/data/tombstones', str(folder / 'tombstones')], 300, False)
    print(json.dumps({'logs': str(folder), 'offline_recovery': offline, 'pstore': names}))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('stage', choices=['check', 'preflight', 'authorize', 'ram-boot', 'map', 'flash',
                                          'bcb-wipe', 'logs', 'rollback'])
    parser.add_argument('--kit', default=str(ROOT / 'outputs/source-trial-01-installation'))
    parser.add_argument('--from-bootloader', action='store_true',
                        help='authorize: the device already shows the bootloader (Android not reachable)')
    parser.add_argument('--rollback-set', help='rollback: name of the kit.rollback entry')
    parser.add_argument('--resume', action='store_true',
                        help='map: accept a partition left partially written by this kit\'s interrupted write')
    args = parser.parse_args()
    kit = Kit(args.kit)
    if args.stage == 'check':
        check(kit)
    elif args.stage == 'preflight':
        preflight(kit)
    elif args.stage == 'authorize':
        authorize(kit, not args.from_bootloader)
    elif args.stage == 'ram-boot':
        ram_boot(kit)
    elif args.stage == 'logs':
        logs(kit)
    else:
        osi = load_osi(kit.dir)
        if args.stage == 'map':
            map_stage(kit, osi, args.resume)
        elif args.stage == 'flash':
            kit.require('flash')
            write_set(kit, osi, kit.kit['images'], kit.kit['name'])
        elif args.stage == 'bcb-wipe':
            bcb_wipe(kit, osi)
        else:
            kit.require('rollback')
            write_set(kit, osi, kit.kit['rollback'][args.rollback_set], 'rollback-' + args.rollback_set)


if __name__ == '__main__':
    main()
