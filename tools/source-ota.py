"""Source releases (1.00, 1.01, ...) and the Source updater: block delta updates over ADB.

The PICO 4 Pro has no A/B slots, so an update is applied by the updater recovery
(tools/prepare-updater-recovery.py, device/pico/PICOA8110/source-updater.sh) while system is
not mounted. From the running Source (ADB over USB or Wi-Fi, adbd root on userdebug) this tool
stages a package on the cache partition (source-ota/) and reboots to recovery; the updater writes the changed
system blocks (SHA-256 of every region before/after), then vbmeta_system and vbmeta, and boots
Android again. No fastboot, no bootloader session, no USB needed.

On Source /cache is a symlink to /data/cache (encrypted, unreadable in recovery); the cache
partition itself (ext4, 2.5 GB) is not mounted by Android. This tool mounts it only while it
stages or reads a package.

  releases                       list the registered releases (outputs/releases.json)
  register VERSION TRIAL_NAME    register outputs/<TRIAL_NAME> images as release VERSION
  make TO [--base FROM]          build the delta package outputs/ota/<FROM>-to-<TO> (local only)
  package TO [--base FROM]       sign that delta as one zip for the in-headset Source Update app
                                 (outputs/ota/packages/source-<FROM>-to-<TO>.zip, Source OTA key)
  publish DIR [--base-url URL]   copy the signed packages to DIR and write DIR/manifest.json
  serve DIR [--port 8000]        serve DIR over HTTP and answer the app's LAN discovery
                                 ("Find server", UDP 39031), so no URL has to be typed
  status                         device: release, recovery (factory/updater), /cache space
  install-recovery               write the updater recovery to the recovery partition  [authorized.recovery]
  restore-factory-recovery       write the factory 5.13.7 recovery back                [authorized.recovery]
  update TO                      stage, reboot to the updater, wait, verify              [authorized.update]
  switch SET [--wipe]            full system/vbmeta_system/vbmeta write over USB ADB in the updater
                                 recovery (SET = factory-5.13.7 or a registered release), optional
                                 userdata wipe by the factory recovery binary   [authorized.update, .wipe]

Authorizations (set only after the user's consent) and a journal live in outputs/ota/state.json.
"""
import argparse
import datetime
import gzip
import hashlib
import json
import os
from pathlib import Path
import shlex
import socket
import subprocess
import sys
import threading
import time
import zipfile

ROOT = Path(__file__).resolve().parents[1]
ADB = str(Path('C:/Users/RedPanda/AppData/Local/Android/Sdk/platform-tools/adb.exe'))
RELEASES = ROOT / 'outputs/releases.json'
OTA = ROOT / 'outputs/ota'
STATE = OTA / 'state.json'
UPDATER_DIR = ROOT / 'outputs/source-updater'
UPDATER = UPDATER_DIR / 'updater-v2'
FACTORY_SET = ROOT / 'outputs/rollback-5.13.7-for-vr-preview-01'
OFFLINE_MARKER = 'pico-vr-offline-trial-01'
FACTORY_RECOVERY = ROOT / 'outputs/rollback-5.13.7-for-vr-preview-01/recovery.img'
FACTORY_RECOVERY_SHA256 = '68b368875f31aa57b4468eefbf45fa714b17f6c7091f8ea39105ca26c4db53c8'
LP = ROOT / 'reports/board/lp-metadata.json'

BLOCK = 4096
SYSTEM_BYTES = 5704732672
SYSTEM_SECTORS = 11142056
SYSTEM_SUPER_START_SECTOR = 2457536
SUPER_BYTES = 8589934592
MERGE_GAP_BLOCKS = 16
MAX_CHUNK_BLOCKS = 4096
PART = '/dev/block/bootdevice/by-name/'
CACHE_MOUNT = '/mnt/source-ota-cache'
REMOTE = CACHE_MOUNT + '/source-ota'


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def file_hash(path, start=0, length=None):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        stream.seek(start)
        left = length
        while left is None or left > 0:
            data = stream.read(8 * 1024 ** 2 if left is None else min(left, 8 * 1024 ** 2))
            if not data:
                break
            digest.update(data)
            if left is not None:
                left -= len(data)
    return digest.hexdigest()


def load(path, default):
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def journal(event):
    state = load(STATE, {'authorized': {}, 'events': []})
    event = {'at_utc': now(), **event}
    state['events'].append(event)
    save(STATE, state)
    print(json.dumps(event, ensure_ascii=False))


def require(name):
    if not load(STATE, {}).get('authorized', {}).get(name):
        raise SystemExit('Not authorized in outputs/ota/state.json: ' + name + " (needs the user's explicit consent)")


# --------------------------------------------------------------------------- device

def adb(serial, *arguments, timeout=60, check=True):
    command = [ADB] + (['-s', serial] if serial else []) + list(arguments)
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, encoding='utf-8', errors='replace')
    except subprocess.TimeoutExpired:
        raise RuntimeError('adb timed out: ' + ' '.join(arguments[:2])) from None
    output = (result.stdout + result.stderr).strip()
    if check and result.returncode:
        raise RuntimeError(output)
    return output


def connected(serial):
    rows = [line.split() for line in adb(None, 'devices', timeout=15).splitlines()[1:]]
    return {row[0]: row[1] for row in rows if len(row) >= 2}.get(serial)


def pick_device(serial):
    if serial:
        if ':' in serial and connected(serial) != 'device':
            adb(None, 'connect', serial, timeout=20, check=False)
        if connected(serial) not in ('device', 'recovery'):
            raise SystemExit('Device not connected: ' + serial)
        return serial
    rows = [line.split() for line in adb(None, 'devices', timeout=15).splitlines()[1:]]
    active = [row[0] for row in rows if len(row) >= 2 and row[1] in ('device', 'recovery')]
    if len(active) != 1:
        raise SystemExit('Expected exactly one ADB device (use -s): %s' % active)
    return active[0]


def shell(serial, command, timeout=120):
    return adb(serial, 'shell', command, timeout=timeout)


def root(serial):
    if shell(serial, 'id -u') == '0':
        return
    if shell(serial, 'getprop ro.debuggable') != '1':
        raise SystemExit('Not a debuggable Source build; adbd root is required')
    adb(serial, 'root', timeout=30, check=False)
    for _ in range(30):
        time.sleep(2)
        if ':' in serial:
            adb(None, 'connect', serial, timeout=20, check=False)
        if connected(serial) == 'device' and adb(serial, 'shell', 'id -u', timeout=15, check=False) == '0':
            return
    raise SystemExit('adbd did not restart as root')


def remote_hash(serial, path, timeout=300):
    value = shell(serial, 'sha256sum ' + shlex.quote(path), timeout).split()[0]
    if len(value) != 64:
        raise RuntimeError('Unexpected sha256sum output for ' + path)
    return value


# Source 2.14+ mounts the cache partition at boot for source_updaterd (source_updaterd.rc); only a
# mount made here is undone.
MOUNTED_HERE = set()


def mount_cache(serial):
    if CACHE_MOUNT + ' ' not in shell(serial, 'cat /proc/mounts'):
        shell(serial, 'mkdir -p %s && mount -t ext4 -o nosuid,nodev,noatime %scache %s' % (CACHE_MOUNT, PART, CACHE_MOUNT))
        MOUNTED_HERE.add(serial)


def umount_cache(serial):
    if serial in MOUNTED_HERE:
        shell(serial, 'sync; umount %s 2>/dev/null; rmdir %s 2>/dev/null; true' % (CACHE_MOUNT, CACHE_MOUNT))
        MOUNTED_HERE.discard(serial)
    else:
        shell(serial, 'sync')


def device_release(serial):
    version = shell(serial, 'getprop ro.source.version')
    if version:
        return version
    build_id = shell(serial, 'getprop ro.build.id')
    for name, row in load(RELEASES, {}).items():
        if row.get('build_id') == build_id:
            return name
    return None


def updater_kinds():
    return ['updater-v' + load(i, {})['updater_version'] for i in UPDATER_DIR.glob('updater-v*/recovery.json')]


def recovery_kind(serial):
    current = remote_hash(serial, PART + 'recovery')
    for info in UPDATER_DIR.glob('updater-v*/recovery.json'):
        updater = load(info, {})
        if current == updater.get('sha256'):
            return 'updater-v' + updater['updater_version'], current
    if current == FACTORY_RECOVERY_SHA256:
        return 'factory-5.13.7', current
    return 'unknown', current


# --------------------------------------------------------------------------- local

def cmd_releases(args):
    for version, row in sorted(load(RELEASES, {}).items()):
        print(version, row['name'], row['build_id'], row['system']['sha256'][:16])


def cmd_register(args):
    releases = load(RELEASES, {})
    directory = ROOT / 'outputs' / args.trial
    config = json.loads((ROOT / 'device/pico/PICOA8110' / (args.trial + '.json')).read_text(encoding='utf-8'))
    props = config['trial_properties']['system/build.prop']
    row = {'name': args.trial, 'build_id': props['ro.build.id'], 'incremental': props['ro.build.version.incremental'],
           'display_id': props['ro.build.display.id'], 'registered_at_utc': now()}
    for part in ['system', 'vbmeta_system', 'vbmeta']:
        path = directory / (part + '.img')
        row[part] = {'path': path.as_posix(), 'bytes': path.stat().st_size, 'sha256': file_hash(path)}
    if row['system']['bytes'] != SYSTEM_BYTES:
        raise SystemExit('Unexpected system size')
    old = releases.get(args.version)
    if old and old['system']['sha256'] != row['system']['sha256']:
        raise SystemExit('Release %s is already registered with other images' % args.version)
    releases[args.version] = row
    save(RELEASES, releases)
    print(json.dumps({args.version: row}, indent=1))


def verify_release(row):
    for part in ['system', 'vbmeta_system', 'vbmeta']:
        item = row[part]
        if Path(item['path']).stat().st_size != item['bytes'] or file_hash(item['path']) != item['sha256']:
            raise SystemExit('Release image changed: ' + item['path'])


def changed_runs(base, target):
    runs, start, last, index = [], None, None, 0
    with open(base, 'rb') as fa, open(target, 'rb') as fb:
        while True:
            a, b = fa.read(BLOCK * 256), fb.read(BLOCK * 256)
            if not b:
                break
            for offset in range(0, len(b), BLOCK):
                if a[offset:offset + BLOCK] != b[offset:offset + BLOCK]:
                    if start is not None and index - last <= MERGE_GAP_BLOCKS and index - start < MAX_CHUNK_BLOCKS:
                        last = index
                    else:
                        if start is not None:
                            runs.append((start, last - start + 1))
                        start = last = index
                index += 1
    if start is not None:
        runs.append((start, last - start + 1))
    return runs


def cmd_make(args):
    releases = load(RELEASES, {})
    target = releases[args.to]
    base_version = args.base or max(v for v in releases if v < args.to)
    base = releases[base_version]
    verify_release(base)
    verify_release(target)
    out = OTA / ('%s-to-%s' % (base_version, args.to))
    if out.exists():
        raise SystemExit('Package exists: ' + str(out))
    out.mkdir(parents=True)
    runs = changed_runs(base['system']['path'], target['system']['path'])
    rows = []
    with open(base['system']['path'], 'rb') as fa, open(target['system']['path'], 'rb') as fb:
        for number, (offset, count) in enumerate(runs):
            fa.seek(offset * BLOCK)
            fb.seek(offset * BLOCK)
            old, new = fa.read(count * BLOCK), fb.read(count * BLOCK)
            name = 'c%04d.gz' % number
            packed = gzip.compress(new, compresslevel=6, mtime=0)
            (out / name).write_bytes(packed)
            rows.append({'name': name, 'offset_blocks': offset, 'count_blocks': count,
                         'base_sha256': hashlib.sha256(old).hexdigest(), 'target_sha256': hashlib.sha256(new).hexdigest(),
                         'file_sha256': hashlib.sha256(packed).hexdigest(), 'file_bytes': len(packed)})
    (out / 'chunks.list').write_bytes(''.join('%(name)s %(offset_blocks)d %(count_blocks)d %(base_sha256)s %(target_sha256)s %(file_sha256)s\n' % r
                                              for r in rows).encode())
    for part in ['vbmeta_system', 'vbmeta']:
        (out / (part + '.img')).write_bytes(Path(target[part]['path']).read_bytes())
    lp = json.loads(LP.read_text(encoding='utf-8'))
    conf = {'VERSION': args.to, 'BASE_VERSION': base_version,
            'BASE_SYSTEM_SHA256': base['system']['sha256'], 'SYSTEM_SHA256': target['system']['sha256'],
            'SYSTEM_BYTES': SYSTEM_BYTES, 'SYSTEM_SECTORS': SYSTEM_SECTORS, 'SYSTEM_SUPER_START_SECTOR': SYSTEM_SUPER_START_SECTOR,
            'SUPER_BYTES': SUPER_BYTES, 'SUPER_LP_SHA256': lp['input_sha256'],
            'vbmeta_system_sha256': target['vbmeta_system']['sha256'], 'vbmeta_sha256': target['vbmeta']['sha256']}
    (out / 'update.conf').write_bytes(''.join('%s=%s\n' % item for item in conf.items()).encode())
    files = {p.name: {'bytes': p.stat().st_size, 'sha256': file_hash(p)} for p in sorted(out.iterdir())}
    manifest = {'created_at_utc': now(), 'version': args.to, 'base_version': base_version,
                'target': target['name'], 'base': base['name'], 'conf': conf, 'chunks': rows, 'files': files,
                'changed_blocks': sum(r['count_blocks'] for r in rows),
                'package_bytes': sum(f['bytes'] for f in files.values())}
    save(out / 'package.json', manifest)
    print(json.dumps({'package': str(out), 'chunks': len(rows), 'changed_MiB': round(manifest['changed_blocks'] * BLOCK / 2 ** 20, 1),
                      'package_MiB': round(manifest['package_bytes'] / 2 ** 20, 1)}))


PACKAGES = OTA / 'packages'
OTA_KEY = ROOT / 'keys/source-ota/source-ota.pk8'
OTA_CERT = ROOT / 'keys/source-ota/source-ota.x509.pem'
WSL_SOURCE = '/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro/source/caf-10'
WSL_OUT = '/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro/out/caf-10'


def wsl_path(path):
    path = str(Path(path).resolve()).replace(chr(92), '/')
    return '/mnt/' + path[0].lower() + path[2:]


def release_notes(version):
    """The release decision text of device/pico/PICOA8110/source-<version>.json (first part)."""
    config = ROOT / 'device/pico/PICOA8110' / ('source-%s.json' % version)
    decision = json.loads(config.read_text(encoding='utf-8')).get('decision', '') if config.exists() else ''
    return decision.split(' Based on ')[0].strip()


def cmd_package(args):
    """One signed zip per delta: what the Source Update app downloads or reads from /sdcard/dload.

    Entries: package.json (version, base, sizes, hashes, notes), update.conf, chunks.list, the gzip
    chunks (stored) and vbmeta_system.img / vbmeta.img; the whole file is signed with the Source OTA
    key (signapk -w), verified on the headset with RecoverySystem.verifyPackage against
    /system/etc/security/source_otacerts.zip before the package is staged.
    """
    releases = load(RELEASES, {})
    base_version = args.base or max(v for v in releases if v < args.to)
    delta = OTA / ('%s-to-%s' % (base_version, args.to))
    manifest = load(delta / 'package.json', None)
    if not manifest:
        raise SystemExit('No delta %s (run: make %s --base %s)' % (delta.name, args.to, base_version))
    for name, row in manifest['files'].items():
        if file_hash(delta / name) != row['sha256']:
            raise SystemExit('Delta file changed: ' + name)
    if not OTA_KEY.exists():
        raise SystemExit('Missing ' + str(OTA_KEY))
    PACKAGES.mkdir(parents=True, exist_ok=True)
    out = PACKAGES / ('source-%s-to-%s.zip' % (base_version, args.to))
    unsigned = out.with_suffix('.unsigned.zip')
    info = {'format': 1, 'version': args.to, 'base_version': base_version,
            'display_id': 'Picomisu Source ' + args.to, 'notes': args.notes or release_notes(args.to),
            'base_system_sha256': manifest['conf']['BASE_SYSTEM_SHA256'],
            'system_sha256': manifest['conf']['SYSTEM_SHA256'],
            'staged_bytes': sum(f['bytes'] for n, f in manifest['files'].items() if n != 'package.json'),
            'files': {n: f for n, f in manifest['files'].items() if n != 'package.json'},
            'created_at_utc': now()}
    fixed = (1980, 1, 1, 0, 0, 0)
    with zipfile.ZipFile(unsigned, 'w') as z:
        entry = zipfile.ZipInfo('package.json', fixed)
        entry.compress_type = zipfile.ZIP_DEFLATED
        z.writestr(entry, json.dumps(info, indent=1, sort_keys=True))
        for name in sorted(info['files']):
            entry = zipfile.ZipInfo(name, fixed)
            # The chunks are gzip already; store them so the stager can stream them.
            entry.compress_type = zipfile.ZIP_STORED if name.endswith('.gz') else zipfile.ZIP_DEFLATED
            with open(delta / name, 'rb') as f:
                z.writestr(entry, f.read())
    command = ('%s/prebuilts/jdk/jdk9/linux-x86/bin/java -Djava.library.path=%s/host/linux-x86/lib64 '
               '-jar %s/host/linux-x86/framework/signapk.jar -w %s %s %s %s'
               % (WSL_SOURCE, WSL_OUT, WSL_OUT, shlex.quote(wsl_path(OTA_CERT)), shlex.quote(wsl_path(OTA_KEY)),
                  shlex.quote(wsl_path(unsigned)), shlex.quote(wsl_path(out))))
    result = subprocess.run(['wsl', '-e', 'bash', '-c', command], capture_output=True, text=True)
    unsigned.unlink()
    if result.returncode != 0 or not out.exists():
        raise SystemExit('signapk failed: ' + result.stdout + result.stderr)
    row = {'version': args.to, 'base_version': base_version, 'file': out.name, 'bytes': out.stat().st_size,
           'sha256': file_hash(out), 'notes': info['notes'], 'created_at_utc': info['created_at_utc']}
    save(out.with_suffix('.json'), row)
    print(json.dumps(row, ensure_ascii=False))


def cmd_publish(args):
    """DIR/manifest.json for the Source Update app (any static HTTP server; the URL is set in the app).

    {"format": 1, "latest": "2.13", "packages": [{"version", "base_version", "url", "bytes",
    "sha256", "notes", "created_at_utc"}]}; url is relative to the manifest unless --base-url.
    """
    target = Path(args.dir)
    target.mkdir(parents=True, exist_ok=True)
    rows = []
    for meta in sorted(PACKAGES.glob('source-*-to-*.json')):
        row = load(meta, None)
        package = PACKAGES / row['file']
        if not package.exists() or file_hash(package) != row['sha256']:
            raise SystemExit('Package changed or missing: ' + row['file'])
        copy = target / row['file']
        if not copy.exists() or file_hash(copy) != row['sha256']:
            copy.write_bytes(package.read_bytes())
        row = dict(row)
        row['url'] = (args.base_url.rstrip('/') + '/' if args.base_url else '') + row.pop('file')
        rows.append(row)
    if not rows:
        raise SystemExit('No packages in ' + str(PACKAGES))
    latest = max((r['version'] for r in rows), key=lambda v: [int(x) for x in v.split('.')])
    save(target / 'manifest.json', {'format': 1, 'latest': latest, 'packages': rows})
    print(json.dumps({'manifest': str(target / 'manifest.json'), 'latest': latest, 'packages': len(rows)}))


DISCOVERY_PORT = 39031
DISCOVER = b'SOURCE_UPDATE_DISCOVER 1'


def cmd_serve(args):
    """HTTP for DIR (manifest.json and packages) plus the discovery responder.

    The app broadcasts 'SOURCE_UPDATE_DISCOVER 1' to UDP 39031; each server replies to the sender
    with 'SOURCE_UPDATE_SERVER 1 <url> <name>', the url using the address the sender reaches it on.
    """
    import functools
    import http.server
    root = Path(args.dir).resolve()
    if not (root / 'manifest.json').exists():
        raise SystemExit('No manifest.json in %s (run publish first)' % root)
    name = socket.gethostname()

    def respond():
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(('', DISCOVERY_PORT))
        while True:
            data, sender = sock.recvfrom(512)
            if data.strip() != DISCOVER:
                continue
            probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                probe.connect(sender)
                address = probe.getsockname()[0]
            finally:
                probe.close()
            url = 'http://%s:%d/' % (address, args.port)
            sock.sendto(('SOURCE_UPDATE_SERVER 1 %s %s' % (url, name)).encode(), sender)
            print('discovery: %s -> %s' % (sender[0], url), flush=True)

    threading.Thread(target=respond, daemon=True).start()
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(root))
    server = http.server.ThreadingHTTPServer(('', args.port), handler)
    print('serving %s on port %d, discovery on UDP %d' % (root, args.port, DISCOVERY_PORT), flush=True)
    server.serve_forever()


# --------------------------------------------------------------------------- device stages

def cmd_status(args):
    serial = pick_device(args.serial)
    root(serial)
    kind, current = recovery_kind(serial)
    mount_cache(serial)
    try:
        cache = shell(serial, 'df -k %s | tail -n 1' % CACHE_MOUNT)
        last = shell(serial, 'cat %s/status 2>/dev/null; true' % REMOTE)
    finally:
        umount_cache(serial)
    print(json.dumps({'release': device_release(serial), 'display_id': shell(serial, 'getprop ro.build.display.id'),
                      'recovery': kind, 'recovery_sha256': current,
                      'cache_partition': cache,
                      'battery': shell(serial, 'dumpsys battery | grep level'),
                      'last_update_status': last}, ensure_ascii=False, indent=1))


def write_recovery(serial, image, expected_kinds):
    require('recovery')
    root(serial)
    kind, before = recovery_kind(serial)
    if kind not in expected_kinds:
        raise SystemExit('Current recovery is %s (%s); expected %s' % (kind, before, expected_kinds))
    local = file_hash(image)
    if Path(image).stat().st_size != 104857600:
        raise SystemExit('Recovery image is not the partition size')
    if file_hash(FACTORY_RECOVERY) != FACTORY_RECOVERY_SHA256:
        raise SystemExit('Local factory recovery backup changed')
    if int(shell(serial, 'blockdev --getsize64 ' + PART + 'recovery')) != 104857600:
        raise SystemExit('Unexpected recovery partition size')
    temp = '/data/local/tmp/source-recovery.img'
    adb(serial, 'push', str(image), temp, timeout=300)
    if remote_hash(serial, temp) != local:
        raise SystemExit('Pushed recovery image differs; nothing written')
    journal({'stage': 'recovery-write', 'status': 'started', 'from': kind, 'from_sha256': before, 'image_sha256': local})
    shell(serial, 'dd if=%s of=%srecovery bs=1048576 && sync' % (temp, PART), 120)
    after = remote_hash(serial, PART + 'recovery')
    shell(serial, 'rm -f ' + temp)
    if after != local:
        journal({'stage': 'recovery-write', 'status': 'failed', 'readback_sha256': after})
        raise SystemExit('Readback mismatch after the recovery write')
    journal({'stage': 'recovery-write', 'status': 'verified', 'readback_sha256': after})


def cmd_install_recovery(args):
    serial = pick_device(args.serial)
    write_recovery(serial, UPDATER / 'recovery.img',
                   ['factory-5.13.7'] + updater_kinds() + (['unknown'] if args.allow_unknown else []))


def cmd_restore_factory_recovery(args):
    serial = pick_device(args.serial)
    write_recovery(serial, FACTORY_RECOVERY, updater_kinds())


def wait_for_android(serial, minutes):
    deadline = time.time() + minutes * 60
    seen_recovery = False
    while time.time() < deadline:
        time.sleep(10)
        try:
            if ':' in serial:
                adb(None, 'connect', serial, timeout=20, check=False)
            state = connected(serial)
        except RuntimeError:
            # adb connect hangs while the headset is off the network (updater, boot).
            continue
        if state == 'recovery':
            if not seen_recovery:
                print('updater recovery is up (USB)', flush=True)
            seen_recovery = True
            status = adb(serial, 'shell', 'cat /tmp/source-ota-cache/source-ota/status', timeout=15, check=False)
            if status.startswith('failed'):
                raise SystemExit('Updater failed and stays in recovery: ' + status)
        elif state == 'device':
            if adb(serial, 'shell', 'getprop sys.boot_completed', timeout=15, check=False) == '1':
                return
    raise SystemExit('Android did not come back within %d minutes' % minutes)


def cmd_update(args):
    require('update')
    releases = load(RELEASES, {})
    serial = pick_device(args.serial)
    root(serial)
    current = device_release(serial)
    if current == args.to:
        raise SystemExit('Device already runs ' + args.to)
    package = OTA / ('%s-to-%s' % (current, args.to))
    manifest = load(package / 'package.json', None)
    if not manifest:
        raise SystemExit('No package %s (run: make %s --base %s)' % (package.name, args.to, current))
    for name, row in manifest['files'].items():
        if file_hash(package / name) != row['sha256']:
            raise SystemExit('Package file changed: ' + name)
    kind, _ = recovery_kind(serial)
    if not kind.startswith('updater-'):
        raise SystemExit('The recovery partition holds %s, not the updater (run install-recovery)' % kind)
    level = int(shell(serial, 'dumpsys battery | grep level').split(':')[1])
    if level < args.min_battery:
        raise SystemExit('Battery %d%% < %d%%' % (level, args.min_battery))
    print('hashing the installed system (about a minute)', flush=True)
    installed = remote_hash(serial, '/dev/block/mapper/system', 600)
    if installed != releases[current]['system']['sha256']:
        raise SystemExit('Installed system is not release %s (%s)' % (current, installed))

    mount_cache(serial)
    shell(serial, 'rm -rf %s && mkdir -p %s' % (REMOTE, REMOTE))
    free = int(shell(serial, 'df -k %s | tail -n 1' % CACHE_MOUNT).split()[3]) * 1024
    if free < manifest['package_bytes'] + 64 * 2 ** 20:
        umount_cache(serial)
        raise SystemExit('Not enough space on the cache partition: %d bytes free' % free)
    for name in manifest['files']:
        if name != 'package.json':
            adb(serial, 'push', str(package / name), REMOTE + '/' + name, timeout=600)
    listing = shell(serial, 'cd %s && sha256sum *' % REMOTE, 300)
    remote = {line.split()[1]: line.split()[0] for line in listing.splitlines()}
    for name, row in manifest['files'].items():
        if name != 'package.json' and remote.get(name) != row['sha256']:
            raise SystemExit('Staged file differs on the device: ' + name)
    shell(serial, 'touch %s/ready && sync' % REMOTE)
    umount_cache(serial)
    journal({'stage': 'update', 'status': 'staged', 'from': current, 'to': args.to, 'package_sha256': file_hash(package / 'package.json')})
    adb(serial, 'reboot', 'recovery', timeout=30, check=False)
    print('rebooted to the updater; waiting for Android', flush=True)
    time.sleep(20)
    finish(serial, package, args.to, args.wait_minutes)


def cmd_finish(args):
    # Verify an update whose staging run was interrupted on the PC side.
    serial = args.serial or pick_device(None)
    finish(serial, OTA / ('%s-to-%s' % (args.base, args.to)), args.to, args.wait_minutes)


def finish(serial, package, to, wait_minutes):
    wait_for_android(serial, wait_minutes)
    root(serial)
    mount_cache(serial)
    status = shell(serial, 'cat %s/status' % REMOTE)
    log = shell(serial, 'cat %s/apply.log' % REMOTE)
    (package / ('apply-%d.log' % int(time.time()))).write_text(log + '\n', encoding='utf-8')
    running = device_release(serial)
    if status != 'ok ' + to or running != to:
        umount_cache(serial)
        journal({'stage': 'update', 'status': 'not-applied', 'updater_status': status, 'running': running})
        raise SystemExit('Update not applied: %s, running %s' % (status, running))
    shell(serial, 'cd %s && rm -f *.gz *.img chunks.list update.conf' % REMOTE)
    umount_cache(serial)
    journal({'stage': 'update', 'status': 'verified', 'running': running, 'display_id': shell(serial, 'getprop ro.build.display.id')})


def image_set(name):
    if name == 'factory-5.13.7':
        sums = {line.split()[1]: line.split()[0]
                for line in (FACTORY_SET / 'SHA256SUMS.txt').read_text().splitlines() if line.strip()}
        return {part: {'path': (FACTORY_SET / (part + '.img')).as_posix(),
                       'bytes': (FACTORY_SET / (part + '.img')).stat().st_size,
                       'sha256': sums[part + '.img']} for part in ['system', 'vbmeta_system', 'vbmeta']}
    row = load(RELEASES, {})[name]
    return {part: row[part] for part in ['system', 'vbmeta_system', 'vbmeta']}


def load_osi(state_file):
    import importlib.util
    spec = importlib.util.spec_from_file_location('offline_system_install',
                                                  Path(__file__).with_name('offline-system-install.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.REPORT = OTA
    module.STATE = state_file
    return module


def wait_for_updater_recovery(osi, state, minutes=10):
    print('waiting for the updater recovery on USB (connect the USB cable)', flush=True)
    deadline = time.time() + minutes * 60
    while time.time() < deadline:
        time.sleep(5)
        rows = [line.split() for line in adb(None, 'devices', timeout=15, check=False).splitlines()[1:]]
        for row in rows:
            if len(row) < 2 or row[1] not in ('recovery', 'device'):
                continue
            if hashlib.sha256(row[0].encode()).hexdigest() != state['offline_adb_serial_sha256']:
                continue
            serial = row[0]
            if adb(serial, 'shell', 'getprop ro.pico.recovery.offline_trial', timeout=15, check=False) != OFFLINE_MARKER:
                continue
            if adb(serial, 'shell', 'getprop init.svc.source_updater', timeout=15, check=False) == 'running':
                continue
            return osi.root_device(state)
    raise SystemExit('The updater recovery did not appear on USB')


def cmd_switch(args):
    require('update')
    if args.wipe:
        require('wipe')
    images = image_set(args.set)
    for part, row in images.items():
        if Path(row['path']).stat().st_size != row['bytes'] or file_hash(row['path']) != row['sha256']:
            raise SystemExit('Local image changed: ' + row['path'])
    state_file = OTA / 'switch-state.json'
    state = load(state_file, {})
    state.update({'offline_adb_serial_sha256': load(STATE, {}).get('offline_adb_serial_sha256'), 'set': args.set})
    state.pop('offline_mapping', None)
    save(state_file, state)
    if not state['offline_adb_serial_sha256']:
        raise SystemExit('outputs/ota/state.json lacks offline_adb_serial_sha256')
    osi = load_osi(state_file)
    if args.serial and (':' not in args.serial or connected(args.serial) == 'device'
                        or 'connected' in adb(None, 'connect', args.serial, timeout=20, check=False)):
        serial = pick_device(args.serial)
        if connected(serial) == 'device':
            root(serial)
            kind, _ = recovery_kind(serial)
            if not kind.startswith('updater-'):
                raise SystemExit('The recovery partition holds %s, not the updater' % kind)
            if args.wipe and kind == 'updater-v1':
                raise SystemExit('updater-v1 cannot wipe (no /data in its fstab); run install-recovery first')
            journal({'stage': 'switch', 'status': 'reboot-recovery', 'set': args.set, 'wipe': args.wipe})
            adb(serial, 'reboot', 'recovery', timeout=30, check=False)
    serial = wait_for_updater_recovery(osi, state)
    # A resumed run finds the mapping of the interrupted one; recreate it.
    adb(serial, 'shell', 'dmctl delete pico-vr-system > /dev/null 2>&1; true', timeout=30, check=False)
    target = osi.map_system(serial, state)
    osi.fixture(serial, state)
    for part in ['system', 'vbmeta_system', 'vbmeta']:
        row = images[part]
        block = target if part == 'system' else PART + part
        if int(osi.shell(serial, 'blockdev --getsize64 ' + block)) != row['bytes']:
            raise SystemExit('Size mismatch: ' + part)
        if osi.remote_hash(serial, block) == row['sha256']:
            print(part + ': already the target', flush=True)
            continue
        journal({'stage': 'switch', 'status': 'writing', 'partition': part, 'image_sha256': row['sha256']})

        def progress(count, part=part, size=row['bytes']):
            print('%s: %d/%d MiB' % (part, count >> 20, size >> 20), flush=True)
        with open(row['path'], 'rb') as reader:
            sent, _ = osi.stream_to_device(serial, reader, block, row['bytes'], progress, verify_existing=True)
        readback = osi.remote_hash(serial, block)
        if sent != row['sha256'] or readback != row['sha256']:
            journal({'stage': 'switch', 'status': 'failed', 'partition': part, 'readback_sha256': readback})
            raise SystemExit('Readback mismatch: ' + part)
        journal({'stage': 'switch', 'status': 'verified', 'partition': part})
    osi.shell(serial, 'sync; dmctl delete pico-vr-system', timeout=60)
    if args.wipe:
        journal({'stage': 'switch', 'status': 'wipe-started'})
        out = adb(serial, 'shell', '/system/bin/recovery --wipe_data > /tmp/source-wipe.log 2>&1; cat /tmp/source-wipe.log',
                  timeout=900, check=False)
        print(out[-2000:], flush=True)
        print('wipe requested; the recovery reboots when done', flush=True)
    else:
        adb(serial, 'reboot', timeout=30, check=False)
    journal({'stage': 'switch', 'status': 'done', 'set': args.set, 'wipe': args.wipe})


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('-s', '--serial', default=os.environ.get('ANDROID_SERIAL'))
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('releases').set_defaults(func=cmd_releases)
    p = sub.add_parser('register')
    p.add_argument('version')
    p.add_argument('trial')
    p.set_defaults(func=cmd_register)
    p = sub.add_parser('make')
    p.add_argument('to')
    p.add_argument('--base')
    p.set_defaults(func=cmd_make)
    p = sub.add_parser('package')
    p.add_argument('to')
    p.add_argument('--base')
    p.add_argument('--notes')
    p.set_defaults(func=cmd_package)
    p = sub.add_parser('publish')
    p.add_argument('dir')
    p.add_argument('--base-url')
    p.set_defaults(func=cmd_publish)
    p = sub.add_parser('serve')
    p.add_argument('dir')
    p.add_argument('--port', type=int, default=8000)
    p.set_defaults(func=cmd_serve)
    sub.add_parser('status').set_defaults(func=cmd_status)
    p = sub.add_parser('install-recovery')
    p.add_argument('--allow-unknown', action='store_true', help='the current recovery is not the factory one (e.g. an older updater)')
    p.set_defaults(func=cmd_install_recovery)
    sub.add_parser('restore-factory-recovery').set_defaults(func=cmd_restore_factory_recovery)
    p = sub.add_parser('update')
    p.add_argument('to')
    p.add_argument('--min-battery', type=int, default=30)
    p.add_argument('--wait-minutes', type=int, default=20)
    p.set_defaults(func=cmd_update)
    p = sub.add_parser('switch')
    p.add_argument('set')
    p.add_argument('--wipe', action='store_true')
    p.set_defaults(func=cmd_switch)
    p = sub.add_parser('finish')
    p.add_argument('base')
    p.add_argument('to')
    p.add_argument('--wait-minutes', type=int, default=20)
    p.set_defaults(func=cmd_finish)
    args = parser.parse_args()
    args.func(args)


if __name__ == '__main__':
    sys.exit(main())
