"""Assemble the Source trial-boot system image (source-trial-01) offline.

Base: the Source aosp_pico4pro-userdebug system image (124-patch tree). On top of
it the factory 5.13.7 system components that the Source build does not provide
are carried over as declared in device/pico/PICOA8110/source-trial-01.json:
factory-only files byte-exact (factory oat/odex/vdex dropped), the factory
Bluetooth set, the factory PackageInstaller, PICO platform-role APKs re-signed
with the Source key of the same role, three android.uid.system product APKs
shadowed on /system, and generated trial files (build.prop, prop.default,
init.rc, ld.config, public.libraries, mac_permissions, VINTF manifest).
vendor/product/odm/boot stay unchanged; super/LP metadata is not rebuilt.

Steps (run in WSL; nothing touches the headset):
  sudo-less root step:  wsl -u root python3 tools/assemble-source-image.py --source-tree
  user steps:           python3 tools/assemble-source-image.py --stage
                        python3 tools/assemble-source-image.py --build
  root step:            wsl -u root python3 tools/assemble-source-image.py --readback
Checks: tools/check-source-image.py.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import fnmatch
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import subprocess
import sys
import uuid
import zipfile


def _load(name, file):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(file))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


extractor = _load('pico_extractor', 'extract-vr-system.py')
pico = _load('pico_assembler', 'assemble-vr-system.py')

ROOT = pico.ROOT
PROJECT = pico.PROJECT
SOURCE_TREE = pico.SOURCE
OUT = pico.OUT
PRODUCT = pico.PRODUCT
HOST = pico.HOST
env = pico.env
# The release recipe is device/pico/PICOA8110/release.json; its "version" names the release
# (source-<version>: staging, outputs). PICO_TRIAL selects an old per-release config
# device/pico/PICOA8110/<name>.json instead; source-trial-01 keeps its original UUID, salts and
# texts byte for byte.
if os.environ.get('PICO_TRIAL'):
    NAME = os.environ['PICO_TRIAL']
    CONFIG = env.DEVICE / (NAME + '.json')
else:
    CONFIG = env.DEVICE / 'release.json'
    NAME = 'source-' + json.loads(CONFIG.read_text())['version']
TOKEN = NAME.upper().replace('-', '_')
STAGE = PROJECT / 'staging' / NAME
SRC_TREE = STAGE / 'source-tree'
TREE = STAGE / 'root'
META = STAGE / 'image-metadata'
OUTPUT = PROJECT / 'outputs' / NAME
FACTORY = PROJECT / 'analysis/stock-5.13.7-system/root'
PARTITIONS = PROJECT / 'analysis/stock-5.13.7-partitions'
STOCK = env.STOCK
FACTORY_REPORT = pico.REPORTS / 'factory-system.json'
FILE_CONTEXTS = PRODUCT / 'obj/ETC/file_contexts.bin_intermediates/file_contexts.bin'
JAVA = SOURCE_TREE / 'prebuilts/jdk/jdk9/linux-x86/bin/java'
APKSIGNER = pico.HOST_OUT / 'framework/apksigner.jar'
AAPT2 = HOST / 'aapt2'
TIMESTAMP = 1790719200  # 2026-09-30T00:00:00Z, fixed for reproducible images
# Releases whose filesystem UUID, directory hash seed and verity salt were derived from the release name.
LEGACY_IMAGE_IDS = {'source-2.%02d' % n for n in range(12)} | {'source-1.%02d' % n for n in range(5)}
USER = env.USER

digest = pico.digest


def config():
    """The release recipe; in release.json, name and trial_properties may use {version},
    {version_id} (2_21) and {incremental}."""
    cfg = json.loads(CONFIG.read_text())
    if 'version' not in cfg:
        return cfg
    values = {'version': cfg['version'], 'version_id': cfg['version'].replace('.', '_'),
              'incremental': cfg['incremental']}

    def expand(value):
        if isinstance(value, str):
            return value.format(**values) if '{' in value else value
        if isinstance(value, list):
            return [expand(item) for item in value]
        if isinstance(value, dict):
            return {key: expand(item) for key, item in value.items()}
        return value
    for key in ['name', 'trial_properties']:
        cfg[key] = expand(cfg[key])
    return cfg


def run(arguments, **kwargs):
    result = subprocess.run([str(a) for a in arguments], text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, **kwargs)
    if result.returncode != 0:
        raise RuntimeError('%s failed (%d):\n%s' % (arguments[0], result.returncode, result.stdout[-4000:]))
    return result.stdout


def rel(path):
    """Image-relative path without the leading slash ('' is the root)."""
    return path.lstrip('/')


def matches(path, pattern):
    if pattern.endswith('/**'):
        return path == pattern[:-3] or path.startswith(pattern[:-2])
    return fnmatch.fnmatch(path, pattern)


def excluded(path, patterns):
    for pattern in patterns:
        if pattern == '**/oat/**':
            if '/oat/' in '/' + path + '/' or path.endswith('/oat'):
                return pattern
        elif pattern.startswith('**/*.'):
            if path.endswith(pattern[4:]):
                return pattern
        elif matches(path, pattern):
            return pattern
    return None


# --------------------------------------------------------------------------- source tree (root)

def source_tree():
    """Unpack the Source system.img read-only (loop mount as WSL root) into SRC_TREE with its metadata."""
    if os.geteuid() != 0:
        raise RuntimeError('The read-only loop mount requires WSL root')
    pico.guard_volume()
    STAGE.mkdir(parents=True, exist_ok=True)
    user = pwd.getpwnam(USER)
    sparse = PRODUCT / 'system.img'
    raw = STAGE / 'source-system.raw.img'
    if raw.exists():
        raw.unlink()
    run([HOST / 'simg2img', sparse, raw])
    mount = STAGE / 'mnt-source'
    mount.mkdir(exist_ok=True)
    if os.path.ismount(mount) or list(mount.iterdir()):
        raise RuntimeError('Mount point in use: ' + str(mount))
    if SRC_TREE.exists():
        shutil.rmtree(SRC_TREE)
    entries = []
    subprocess.run(['mount', '-t', 'ext4', '-o', 'loop,ro,noload', str(raw), str(mount)], check=True)
    try:
        options = subprocess.check_output(['findmnt', '-n', '-o', 'OPTIONS', '--mountpoint', str(mount)], text=True)
        if 'ro' not in options.strip().split(','):
            raise RuntimeError('Source mount must be read only')
        SRC_TREE.mkdir()
        entries.append(extractor.metadata(mount, '/'))
        for folder, directories, files in os.walk(mount, followlinks=False):
            for name in sorted(directories + files):
                source = Path(folder) / name
                relative = '/' + str(source.relative_to(mount))
                entry = extractor.metadata(source, relative)
                destination = SRC_TREE / relative.lstrip('/')
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
        os.chown(SRC_TREE, user.pw_uid, user.pw_gid)
    finally:
        subprocess.run(['umount', str(mount)], check=True)
    report = {'created_at': datetime.now(timezone.utc).isoformat(), 'complete': True,
              'source_sparse_image': str(sparse), 'source_sparse_sha256': digest(sparse),
              'source_raw_sha256': digest(raw), 'tree': str(SRC_TREE),
              'entries': sorted(entries, key=lambda e: e['path'])}
    raw.unlink()
    (STAGE / 'source-metadata.json').write_text(json.dumps(report, indent=1) + '\n')
    for item in [STAGE, STAGE / 'source-metadata.json', mount]:
        os.chown(item, user.pw_uid, user.pw_gid)
    print(json.dumps({'source_entries': len(entries), 'tree': str(SRC_TREE)}))


# --------------------------------------------------------------------------- helpers for staging

def package_name(apk):
    return run([AAPT2, 'dump', 'packagename', apk]).strip()


def shared_uid(apk):
    tree = run([AAPT2, 'dump', 'xmltree', apk, '--file', 'AndroidManifest.xml'])
    match = re.search(r':sharedUserId\([^)]*\)="([^"]+)"', tree)
    return match.group(1) if match else None


def signers(apk):
    output = subprocess.run([str(JAVA), '-jar', str(APKSIGNER), 'verify', '--print-certs', str(apk)],
                            capture_output=True, text=True)
    if output.returncode != 0:
        raise RuntimeError('apksigner verify failed: ' + str(apk) + ': ' + output.stdout + output.stderr)
    return re.findall(r'Signer #\d+ certificate SHA-256 digest: ([0-9a-f]+)', output.stdout)


def resign(apk, role, report):
    """Replace the APK signature with the Source key of the same role; entry data is kept."""
    keys = SOURCE_TREE / config()['signing']['keys_dir']
    before = signers(apk)
    with zipfile.ZipFile(apk) as archive:
        payload = {i.filename: (i.CRC, i.file_size, i.compress_type) for i in archive.infolist()
                   if not i.filename.startswith('META-INF/')}
    temporary = apk.with_name(apk.name + '.resign')
    run([JAVA, '-jar', APKSIGNER, 'sign', '--key', keys / (role + '.pk8'), '--cert', keys / (role + '.x509.pem'),
         '--out', temporary, apk])
    with zipfile.ZipFile(temporary) as archive:
        after_payload = {i.filename: (i.CRC, i.file_size, i.compress_type) for i in archive.infolist()
                         if not i.filename.startswith('META-INF/')}
    if payload != after_payload:
        raise RuntimeError('Re-signing changed APK payload: ' + str(apk))
    after = signers(temporary)
    if len(after) != 1:
        raise RuntimeError('Unexpected signer count after re-signing: ' + str(apk))
    aligned = subprocess.run([str(HOST / 'zipalign'), '-c', '-p', '4', str(temporary)], capture_output=True, text=True)
    if aligned.returncode != 0:
        raise RuntimeError('Re-signed APK is not aligned: ' + str(apk))
    temporary.replace(apk)
    report.update({'factory_signers': before, 'role': role, 'source_signer': after[0],
                   'payload_entries_unchanged': len(payload), 'sha256': digest(apk)})


def apply_line_edits(text, edits):
    lines = text.split('\n')
    applied = []
    for edit in edits:
        if edit.get('append'):
            if lines and lines[-1] == '':
                lines = lines[:-1] + edit['insert'] + ['']
            else:
                lines += edit['insert']
            applied.append('append')
            continue
        anchor = edit.get('after') or edit.get('before') or edit.get('replace')
        found = [i for i, line in enumerate(lines) if line == anchor]
        if len(found) != 1:
            raise RuntimeError('init.rc anchor must occur exactly once: %r (%d)' % (anchor, len(found)))
        index = found[0]
        if 'after' in edit:
            lines[index + 1:index + 1] = edit['insert']
        elif 'before' in edit:
            lines[index:index] = edit['insert']
        else:
            lines[index:index + 1] = edit['insert']
        applied.append(anchor.strip())
    return '\n'.join(lines), applied


def apply_ld_config_edits(text, edits):
    lines = text.split('\n')
    applied = []
    for edit in edits:
        header = '[%s]' % edit['section']
        starts = [i for i, line in enumerate(lines) if line.strip() == header]
        if len(starts) != 1:
            raise RuntimeError('ld.config section must occur once: ' + header)
        begin = starts[0]
        end = next((i for i in range(begin + 1, len(lines)) if lines[i].startswith('[')), len(lines))
        hits = [i for i in range(begin, end) if lines[i].startswith(edit['after_last_prefix'])]
        if not hits:
            raise RuntimeError('ld.config anchor missing: ' + edit['after_last_prefix'] + ' in ' + header)
        lines[hits[-1] + 1:hits[-1] + 1] = edit['insert']
        applied.append({'section': edit['section'], 'after_line': hits[-1] + 1, 'inserted': edit['insert']})
    return '\n'.join(lines), applied


def properties_file(text, changes):
    """Set keys in a build.prop-style text; existing definitions are replaced in place."""
    for key, value in changes.items():
        pattern = r'^' + re.escape(key) + r'=.*$'
        if re.search(pattern, text, re.MULTILINE):
            text = re.sub(pattern, lambda _: key + '=' + value, text, flags=re.MULTILINE)
        else:
            if not text.endswith('\n'):
                text += '\n'
            text += key + '=' + value + '\n'
    return text


def read_props(path):
    values = {}
    for line in Path(path).read_text(errors='replace').splitlines():
        if '=' in line and not line.lstrip().startswith('#'):
            key, value = line.split('=', 1)
            values[key.strip()] = value
    return values


# --------------------------------------------------------------------------- stage

def stage():
    pico.guard_volume()
    if os.geteuid() == 0:
        raise RuntimeError('Run --stage as the normal WSL user')
    cfg = config()
    selection = cfg['selection']
    source_meta = json.loads((STAGE / 'source-metadata.json').read_text())
    factory_meta = json.loads(FACTORY_REPORT.read_text())
    if not factory_meta['complete'] or not source_meta['complete']:
        raise RuntimeError('Incomplete factory or Source extraction')
    if source_meta['source_sparse_sha256'] != digest(PRODUCT / 'system.img'):
        raise RuntimeError('Source system.img changed after --source-tree; rerun it')
    source = {rel(e['path']): e for e in source_meta['entries']}
    factory = {rel(e['path']): e for e in factory_meta['entries']}
    bluetooth = json.loads((ROOT / selection['factory_bluetooth_config']).read_text())

    # Packages of APKs on the system image (factory and Source).
    def packages(entries, tree):
        result = {}
        paths = [p for p, e in entries.items() if e['kind'] == 'file' and p.endswith('.apk')]
        with ThreadPoolExecutor(8) as pool:
            names = list(pool.map(lambda p: package_name(tree / p), paths))
        for path, name in zip(paths, names):
            result.setdefault(name, []).append(path)
        return result
    factory_packages = packages(factory, FACTORY)
    source_packages = packages(source, SRC_TREE)
    other_partition_packages = set()
    for name in ['factory-apks.json', 'additional-factory-apks.json']:
        for package in json.loads((pico.REPORTS / name).read_text())['packages']:
            other_partition_packages.add(package['package'])
    factory_all = set(factory_packages) | other_partition_packages

    def app_dir(path):
        parts = path.split('/')
        if len(parts) >= 3 and parts[0] == 'system' and parts[1] in ('app', 'priv-app'):
            return '/'.join(parts[:3])
        return None

    decisions = {'packages': {}, 'paths': {}}
    drop_dirs = set()
    factory_package_dirs = set()
    for name, paths in sorted(source_packages.items()):
        if name not in factory_all:
            dirs = {app_dir(p) for p in paths}
            if None in dirs:
                raise RuntimeError('Source-only package outside an app directory: ' + name)
            drop_dirs |= dirs
            decisions['packages'][name] = {'decision': 'drop-source-only', 'source': paths,
                                           'reason': selection['drop_source_packages_reason']}
        elif name in selection['packages_factory_over_source']:
            dirs = {app_dir(p) for p in paths}
            drop_dirs |= dirs
            factory_dirs = {app_dir(p) for p in factory_packages.get(name, [])}
            factory_package_dirs |= factory_dirs
            decisions['packages'][name] = {'decision': 'factory-over-source', 'source': paths,
                                           'factory': factory_packages.get(name),
                                           'reason': selection['packages_factory_over_source'][name]}
        elif name in factory_packages:
            factory_dirs = {app_dir(p) for p in factory_packages[name]}
            extra = [p for p in paths if app_dir(p) not in factory_dirs] if len(paths) > 1 else []
            drop_dirs |= {app_dir(p) for p in extra}
            decisions['packages'][name] = {'decision': 'source', 'source': [p for p in paths if p not in extra],
                                           'factory': factory_packages[name]}
            if extra:
                decisions['packages'][name]['dropped_source_variants'] = extra
                decisions['packages'][name]['variant_reason'] = ('the Source build installs two APKs of this package; '
                                                                 'only the variant the factory image ships is kept '
                                                                 '(PMS would pick one nondeterministically)')
        else:
            decisions['packages'][name] = {'decision': 'source', 'source': paths,
                                           'factory_partition_only': True}
    for name, paths in sorted(factory_packages.items()):
        if name not in source_packages:
            decisions['packages'][name] = {'decision': 'carry-factory', 'factory': paths}

    factory_over = set(selection['factory_over_source']) | set(bluetooth['preserve'])
    exclude = list(selection['exclude_factory'])
    carried_jars = {'system/framework/' + j for j in selection['carried_jars_not_on_classpath']}
    final = {}
    reasons = {}
    for path, entry in source.items():
        if path == 'lost+found':
            reasons[path] = 'created by mke2fs'
            continue
        if any(path == d or path.startswith(d + '/') for d in drop_dirs):
            reasons[path] = 'dropped with its Source package'
            continue
        if path in selection['drop_source_files']:
            reasons[path] = selection['drop_source_files'][path]
            continue
        if path in factory_over:
            if path not in factory:
                raise RuntimeError('factory_over_source path missing in factory: ' + path)
            final[path] = dict(factory[path], origin='factory', path='/' + path)
        else:
            final[path] = dict(entry, origin='source', path='/' + path)
    for path, entry in factory.items():
        if path in source and not any(path == d or path.startswith(d + '/') for d in drop_dirs):
            continue
        if path.startswith('system/framework/') and path.endswith('.jar') and \
                path.count('/') == 2 and path not in carried_jars:
            reasons[path] = 'factory class path JAR, see factory-bootclasspath.json'
            continue
        rule = excluded(path, exclude)
        if rule:
            reasons[path] = rule
            continue
        if path in final:
            continue
        final[path] = dict(entry, origin='factory', path='/' + path)
    # Parents of every entry must exist.
    for path in list(final):
        parent = path.rsplit('/', 1)[0] if '/' in path else ''
        while parent and parent not in final:
            if parent in source:
                final[parent] = dict(source[parent], origin='source', path='/' + parent)
            elif parent in factory:
                final[parent] = dict(factory[parent], origin='factory', path='/' + parent)
            else:
                raise RuntimeError('No metadata for parent directory: ' + parent)
            parent = parent.rsplit('/', 1)[0] if '/' in parent else ''
    final[''] = dict(source[''], origin='source', path='/')

    # Stage the tree.
    if TREE.exists():
        owner = STAGE / 'owner.json'
        if not owner.exists() or json.loads(owner.read_text()).get('tool') != 'assemble-source-image.py':
            raise RuntimeError('Preserve a staging tree that this tool did not create')
        shutil.rmtree(TREE)
    (STAGE / 'owner.json').write_text(json.dumps({'tool': 'assemble-source-image.py', 'name': NAME}) + '\n')
    TREE.mkdir(parents=True)
    for path in sorted(final):
        if not path:
            continue
        entry = final[path]
        base = SRC_TREE if entry['origin'] == 'source' else FACTORY
        destination = TREE / path
        if entry['kind'] == 'directory':
            destination.mkdir(exist_ok=True)
        elif entry['kind'] == 'symlink':
            destination.symlink_to(entry['target'])
        else:
            shutil.copyfile(base / path, destination)
            if digest(destination) != entry['sha256']:
                raise RuntimeError('Staged content differs from its recorded hash: ' + path)

    # Re-sign carried platform-role APKs.
    roles = cfg['signing']['factory_cert_roles']
    resigned = {}
    carried_apks = sorted(p for p, e in final.items() if e['origin'] == 'factory' and p.endswith('.apk')
                          and e['kind'] == 'file')

    def examine(path):
        return path, signers(TREE / path)
    with ThreadPoolExecutor(8) as pool:
        carried_signers = dict(pool.map(examine, carried_apks))
    kept_certificates = {}
    for path in carried_apks:
        certs = carried_signers[path]
        role = roles.get(certs[0]) if len(certs) == 1 else None
        if role:
            record = {}
            resign(TREE / path, role, record)
            resigned[path] = record
            final[path] = dict(final[path], sha256=record['sha256'], bytes=(TREE / path).stat().st_size,
                               origin='factory-resigned', factory_sha256=final[path]['sha256'])
        else:
            kept_certificates[path] = certs

    # Shadow copies of product android.uid.system APKs.
    shadows = {}
    for product_path, target in cfg['signing']['shadow_partition_apks'].items():
        src = PARTITIONS / product_path
        if target in final:
            raise RuntimeError('Shadow target already present: ' + target)
        folder = target.rsplit('/', 1)[0]
        (TREE / folder).mkdir(parents=True, exist_ok=True)
        if folder not in final:
            final[folder] = {'path': '/' + folder, 'kind': 'directory', 'uid': 0, 'gid': 0, 'mode': '0755',
                             'capabilities': 0, 'origin': 'product-shadow'}
        shutil.copyfile(src, TREE / target)
        certs = signers(TREE / target)
        role = roles.get(certs[0]) if len(certs) == 1 else None
        if not role:
            raise RuntimeError('Shadowed APK without a PICO role certificate: ' + product_path)
        record = {'product_path': product_path, 'product_sha256': digest(src), 'shared_uid': shared_uid(src)}
        resign(TREE / target, role, record)
        shadows[target] = record
        final[target] = {'path': '/' + target, 'kind': 'file', 'uid': 0, 'gid': 0, 'mode': '0644',
                         'capabilities': 0, 'origin': 'product-shadow-resigned', 'sha256': record['sha256'],
                         'bytes': (TREE / target).stat().st_size}

    # Generated files.
    generated = {}

    def regenerate(path, text, how):
        target = TREE / path
        target.write_text(text)
        final[path] = dict(final[path], sha256=digest(target), bytes=target.stat().st_size,
                           origin='generated', based_on=final[path].get('sha256'), how=how)
        generated[path] = {'how': how, 'sha256': final[path]['sha256']}

    # build.prop: Source + factory-only keys + trial identity.
    source_props = read_props(SRC_TREE / 'system/build.prop')
    factory_props = read_props(FACTORY / 'system/build.prop')
    extra = {k: v for k, v in factory_props.items() if k not in source_props}
    text = (SRC_TREE / 'system/build.prop').read_text()
    text += '\n# Factory PICO OS 5.13.7 system properties absent from the Source build (%s)\n' % NAME
    text += ''.join('%s=%s\n' % (k, v) for k, v in extra.items())
    text += '# %s identity and trial-only properties\n' % NAME
    text = properties_file(text, cfg['trial_properties']['system/build.prop'])
    regenerate('system/build.prop', text, 'Source + %d factory-only properties + trial properties' % len(extra))
    text = properties_file((SRC_TREE / 'system/etc/prop.default').read_text(),
                           cfg['trial_properties']['system/etc/prop.default'])
    regenerate('system/etc/prop.default', text, 'Source + trial debug properties')
    text, applied = apply_line_edits((SRC_TREE / 'init.rc').read_text(), cfg['init_rc_edits'])
    regenerate('init.rc', text, 'Source + %d PICO edits' % len(applied))
    text, ld_applied = apply_ld_config_edits((SRC_TREE / 'system/etc/ld.config.29.txt').read_text(),
                                             cfg['ld_config_edits'])
    regenerate('system/etc/ld.config.29.txt', text, 'Source + %d PICO edits' % len(ld_applied))
    source_libs = (SRC_TREE / 'system/etc/public.libraries.txt').read_text().splitlines()
    factory_libs = (FACTORY / 'system/etc/public.libraries.txt').read_text().splitlines()
    added = []
    for line in factory_libs:
        if line.strip() and not line.startswith('#') and line not in source_libs and line not in added:
            added.append(line)
    regenerate('system/etc/public.libraries.txt', '\n'.join(source_libs + added) + '\n',
               'Source + %d factory libraries' % len(added))
    mac = (SRC_TREE / 'system/etc/selinux/plat_mac_permissions.xml').read_text()
    factory_mac = (FACTORY / 'system/etc/selinux/plat_mac_permissions.xml').read_text()
    blocks = []
    for match in re.finditer(r'<signer signature="([0-9a-fA-F]+)"\s*>.*?</signer>', factory_mac, re.S):
        cert = hashlib.sha256(bytes.fromhex(match.group(1))).hexdigest()
        if cert in cfg['signing']['mac_permissions_pico_signers']:
            seinfo = re.search(r'<seinfo value="([^"]+)"', match.group(0)).group(1)
            if seinfo != cfg['signing']['mac_permissions_pico_signers'][cert]:
                raise RuntimeError('Unexpected factory seinfo for ' + cert)
            blocks.append(match.group(0))
    if len(blocks) != len(cfg['signing']['mac_permissions_pico_signers']) or mac.count('</policy>') != 1:
        raise RuntimeError('PICO mac_permissions signers not found')
    mac = mac.replace('</policy>', '  <!-- ' + NAME + ': factory PICO certificates (trial only) -->\n  '
                      + '\n  '.join(blocks) + '\n</policy>')
    regenerate('system/etc/selinux/plat_mac_permissions.xml', mac, 'Source + %d PICO signers' % len(blocks))
    manifest = (SRC_TREE / 'system/etc/vintf/manifest.xml').read_text()
    factory_manifest = (FACTORY / 'system/etc/vintf/manifest.xml').read_text()
    source_names = set(re.findall(r'<hal format="\w+"[^>]*>\s*<name>([^<]+)</name>', manifest))
    added_hals = []
    for match in re.finditer(r'[ \t]*<hal format="\w+"[^>]*>\s*<name>([^<]+)</name>.*?</hal>\n', factory_manifest, re.S):
        if match.group(1) not in source_names:
            added_hals.append(match.group(0))
    if manifest.count('</manifest>') != 1:
        raise RuntimeError('Unexpected Source framework manifest')
    manifest = manifest.replace('</manifest>', ''.join(added_hals) + '</manifest>')
    regenerate('system/etc/vintf/manifest.xml', manifest,
               'Source + factory-only HALs: ' + ', '.join(re.search(r'<name>([^<]+)</name>', h).group(1)
                                                          for h in added_hals))

    # Trial-only files that exist in neither Source nor factory (e.g. /adb_keys).
    extra_files = {}
    for path, spec in cfg.get('extra_files', {}).items():
        if path in final:
            raise RuntimeError('Extra file already present: ' + path)
        parent = path.rsplit('/', 1)[0] if '/' in path else ''
        if parent not in final:
            raise RuntimeError('Extra file parent missing: ' + path)
        # Relative sources are in the device tree; ~ is the building user's home.
        source_file = Path(os.path.expanduser(spec['from']))
        if not source_file.is_absolute():
            source_file = env.DEVICE / source_file
        if not source_file.exists() and spec.get('optional'):
            continue
        shutil.copyfile(source_file, TREE / path)
        final[path] = {'path': '/' + path, 'kind': 'file', 'uid': spec['uid'], 'gid': spec['gid'],
                       'mode': spec['mode'], 'capabilities': 0, 'origin': 'trial-extra',
                       'sha256': digest(TREE / path), 'bytes': (TREE / path).stat().st_size}
        extra_files[path] = {'from': str(source_file), 'sha256': final[path]['sha256'],
                             'selinux': spec['selinux'], 'reason': spec['reason']}

    # Every staged path is in the plan and vice versa.
    staged = {''}
    for folder, directories, files in os.walk(TREE, followlinks=False):
        for name in directories + files:
            staged.add(str((Path(folder) / name).relative_to(TREE)))
    if staged != set(final):
        raise RuntimeError('Staging tree differs from plan: extra=%s missing=%s'
                           % (sorted(staged - set(final))[:10], sorted(set(final) - staged)[:10]))
    origins = {}
    for entry in final.values():
        origins[entry['origin']] = origins.get(entry['origin'], 0) + 1
    plan = {'created_at': datetime.now(timezone.utc).isoformat(), 'name': NAME, 'config': str(CONFIG),
            'config_sha256': digest(CONFIG), 'source_metadata_sparse_sha256': source_meta['source_sparse_sha256'],
            'factory_image_sha256': factory_meta['image_sha256'], 'tree': str(TREE),
            'origins': origins, 'package_decisions': decisions['packages'],
            'not_staged': reasons, 'resigned': resigned, 'kept_certificates': kept_certificates,
            'shadows': shadows, 'generated': generated, 'extra_files': extra_files,
            'init_rc_edits_applied': applied,
            'ld_config_edits_applied': ld_applied, 'factory_only_properties': sorted(extra),
            'entries': [dict(final[p], path='/' + p if p else '/') for p in sorted(final)]}
    (STAGE / 'plan.json').write_text(json.dumps(plan, indent=1) + '\n')
    print(json.dumps({'staged_entries': len(final), 'origins': origins,
                      'resigned_apks': len(resigned), 'shadows': sorted(shadows),
                      'dropped_source_packages': sorted(n for n, d in decisions['packages'].items()
                                                        if d['decision'] == 'drop-source-only'),
                      'generated': sorted(generated)}, indent=1))


# --------------------------------------------------------------------------- build

avb_tool = None


def build():
    pico.guard_volume()
    global avb_tool
    builder = _load('pico_vr_image', 'build-vr-image.py')
    avb_tool = builder
    plan = json.loads((STAGE / 'plan.json').read_text())
    if plan['config_sha256'] != digest(CONFIG):
        raise RuntimeError('Config changed after --stage; restage')
    cfg = config()
    # vbmeta carries the hash of the boot image the headset runs: PICOMISU_BOOT (e.g. a Magisk boot
    # read from the headset), else the legacy saved boot, else the factory boot of the pinned OTA.
    if os.environ.get('PICOMISU_BOOT'):
        current_boot = Path(os.environ['PICOMISU_BOOT']).resolve()
        boot_report = {'current_boot_sha256': digest(current_boot), 'source': 'PICOMISU_BOOT'}
    elif env.LEGACY:
        boot_report = json.loads((pico.REPORTS / 'current-boot.json').read_text())
        current_boot = Path(boot_report['current_boot_file'])
        if digest(current_boot) != boot_report['current_boot_sha256']:
            raise RuntimeError('Saved current boot changed')
    else:
        current_boot = STOCK / 'boot.img'
        boot_report = {'current_boot_sha256': digest(current_boot), 'source': 'factory OTA boot.img'}
        if boot_report['current_boot_sha256'] != env.LOCK['images']['boot.img']['sha256']:
            raise RuntimeError('Factory boot differs from the lock')
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for name in ['system.img', 'vbmeta.img', 'vbmeta_system.img', 'system.sparse.img']:
        if (OUTPUT / name).exists():
            (OUTPUT / name).unlink()
    META.mkdir(parents=True, exist_ok=True)
    entries = plan['entries']
    lost = TREE / 'lost+found'
    if lost.exists():
        raise RuntimeError('Unexpected staged lost+found')
    fs_config = META / 'fs_config.txt'
    lines = []
    for entry in entries:
        path = entry['path'].lstrip('/')
        lines.append('%s %d %d %s capabilities=0x%x\n' % (path, entry['uid'], entry['gid'], entry['mode'],
                                                        entry.get('capabilities', 0)))
    fs_config.write_text(''.join(lines))
    if env.LEGACY:
        lp = json.loads((ROOT / 'reports/board/lp-metadata.json').read_text())
        partition_size = next(p['bytes'] for p in lp['metadata'][0]['partitions'] if p['name'] == 'system')
    else:
        partition_size = env.LOCK['images']['system']['bytes']
    if partition_size != 5704732672:
        raise RuntimeError('Unexpected logical system size')
    maximum = int(builder.avb_command('add_hashtree_footer', '--partition_size', partition_size,
                                      '--hash_algorithm', 'sha256', '--do_not_generate_fec',
                                      '--calc_max_image_size').strip())
    filesystem_size = maximum // 4096 * 4096
    raw = OUTPUT / 'system.img'
    env = dict(os.environ, MKE2FS_CONFIG=str(SOURCE_TREE / 'system/extras/ext4_utils/mke2fs.conf'),
               E2FSPROGS_FAKE_TIME=str(TIMESTAMP))
    # Fixed across releases (per-release values changed the metadata checksums and the whole
    # verity hash tree of every release, which inflated the OTA deltas). LEGACY_IMAGE_IDS keeps the
    # per-release values of the releases built before this change, so they rebuild byte-identically.
    id_name = NAME if NAME in LEGACY_IMAGE_IDS else 'source'
    image_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, 'picomisu-%s-system' % id_name))
    hash_seed = str(uuid.uuid5(uuid.NAMESPACE_DNS, 'picomisu-%s-directory-hash' % id_name))
    run([HOST / 'mke2fs', '-t', 'ext4', '-b', '4096', '-m', '0', '-N', len(entries) + 512, '-I', '256',
         '-L', '/', '-M', '/', '-U', image_uuid, '-O', '^has_journal', '-E', 'hash_seed=' + hash_seed,
         raw, filesystem_size // 4096], env=env)
    # Block allocation of this release (-D); with PICO_BASE_RELEASE the files keep the blocks they had
    # in that release (-d), so a changed file no longer shifts every later file and the OTA delta
    # stays the size of the real changes.
    base_fs_out = META / 'base_fs.txt'
    base_args = []
    base_release = os.environ.get('PICO_BASE_RELEASE')
    if base_release:
        base_fs_in = PROJECT / 'staging' / base_release / 'image-metadata' / 'base_fs.txt'
        if not base_fs_in.exists():
            raise RuntimeError('No base_fs for ' + base_release + ': ' + str(base_fs_in))
        base_args = ['-d', base_fs_in]
    elif cfg.get('base_fs'):
        # The block layout of the previous release, kept in the device tree (base_fs/<version>.txt).
        base_release = 'source-' + cfg['base_release']
        base_fs_in = env.DEVICE / cfg['base_fs']
        base_args = ['-d', base_fs_in]
    population = run([HOST / 'e2fsdroid', '-e', '-s', '-T', TIMESTAMP, '-C', fs_config, '-S', FILE_CONTEXTS,
                      '-D', base_fs_out] + base_args + ['-f', TREE, '-a', '/', raw], env=env)
    (META / 'base-release.txt').write_text((base_release or '') + '\n')
    (META / 'e2fsdroid.log').write_text(population)
    consistency = subprocess.run([str(HOST / 'e2fsck'), '-f', '-n', str(raw)], capture_output=True, text=True)
    (META / 'e2fsck.log').write_text(consistency.stdout + consistency.stderr)
    if consistency.returncode != 0:
        raise RuntimeError('e2fsck reported problems: ' + consistency.stdout[-2000:])
    avb = builder.avb
    props = read_props(TREE / 'system/build.prop')
    patch = props['ro.build.version.security_patch']
    _, stock_system_header, stock_system_descriptors, _ = builder.image_data(STOCK / 'vbmeta_system.img')
    salt_token = TOKEN if NAME in LEGACY_IMAGE_IDS else 'SOURCE'
    salt = hashlib.sha256(('PICOMISU_%s/system' % salt_token).encode()).hexdigest()
    key = builder.KEY
    builder.avb_command('add_hashtree_footer', '--image', raw, '--partition_name', 'system',
                        '--partition_size', partition_size, '--algorithm', 'SHA256_RSA4096', '--key', key,
                        '--hash_algorithm', 'sha256', '--salt', salt, '--do_not_generate_fec',
                        '--rollback_index', stock_system_header.rollback_index,
                        '--prop', 'com.android.build.system.os_version:10',
                        '--prop', 'com.android.build.system.security_patch:' + patch)
    stock_child = [d for d in stock_system_descriptors
                   if (isinstance(d, avb.AvbHashtreeDescriptor) and d.partition_name == 'product')
                   or (isinstance(d, avb.AvbPropertyDescriptor) and d.key.startswith('com.android.build.product.'))]
    product_metadata = META / 'factory-product.vbmeta'
    product_metadata.write_bytes(builder.vbmeta_blob(stock_child))
    child = OUTPUT / 'vbmeta_system.img'
    builder.avb_command('make_vbmeta_image', '--output', child, '--algorithm', 'SHA256_RSA4096', '--key', key,
                        '--include_descriptors_from_image', raw, '--include_descriptors_from_image', product_metadata,
                        '--rollback_index', stock_system_header.rollback_index, '--padding_size', '65536')
    _, stock_root_header, stock_root_descriptors, _ = builder.image_data(STOCK / 'vbmeta.img')
    preserved = []
    for descriptor in stock_root_descriptors:
        if isinstance(descriptor, avb.AvbChainPartitionDescriptor):
            continue
        if isinstance(descriptor, avb.AvbHashDescriptor) and descriptor.partition_name == 'boot':
            replacement = avb.AvbHashDescriptor()
            replacement.partition_name = 'boot'
            replacement.image_size = current_boot.stat().st_size
            replacement.hash_algorithm = 'sha256'
            replacement.salt = hashlib.sha256(('PICOMISU_%s/current-boot' % TOKEN).encode()).digest()
            hasher = hashlib.sha256(replacement.salt)
            with current_boot.open('rb') as stream:
                for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b''):
                    hasher.update(chunk)
            replacement.digest = hasher.digest()
            replacement.flags = descriptor.flags
            preserved.append(replacement)
        else:
            preserved.append(descriptor)
    root_metadata = META / 'factory-root-without-chains.vbmeta'
    root_metadata.write_bytes(builder.vbmeta_blob(preserved, rollback_index=stock_root_header.rollback_index,
                                                  flags=stock_root_header.flags))
    public = META / 'trial.avbpubkey'
    builder.avb_command('extract_public_key', '--key', key, '--output', public)
    recovery_chain = next(d for d in stock_root_descriptors
                          if isinstance(d, avb.AvbChainPartitionDescriptor) and d.partition_name == 'recovery')
    system_chain = next(d for d in stock_root_descriptors
                        if isinstance(d, avb.AvbChainPartitionDescriptor) and d.partition_name == 'vbmeta_system')
    recovery_public = META / 'factory-recovery.avbpubkey'
    recovery_public.write_bytes(recovery_chain.public_key)
    root = OUTPUT / 'vbmeta.img'
    builder.avb_command('make_vbmeta_image', '--output', root, '--algorithm', 'SHA256_RSA4096', '--key', key,
                        '--include_descriptors_from_image', root_metadata,
                        '--chain_partition', 'recovery:%d:%s' % (recovery_chain.rollback_index_location, recovery_public),
                        '--chain_partition', 'vbmeta_system:%d:%s' % (system_chain.rollback_index_location, public),
                        '--rollback_index', stock_root_header.rollback_index, '--flags', stock_root_header.flags,
                        '--padding_size', '65536')
    expected = ['--expected_chain_partition', 'recovery:%d:%s' % (recovery_chain.rollback_index_location, recovery_public),
                '--expected_chain_partition', 'vbmeta_system:%d:%s' % (system_chain.rollback_index_location, public)]
    for descriptor in builder.image_data(root)[2]:
        if isinstance(descriptor, avb.AvbChainPartitionDescriptor) and descriptor.partition_name == 'vbmeta_system':
            if builder.embedded_public_key(child) != descriptor.public_key:
                raise RuntimeError('vbmeta_system key does not match its chain descriptor')
    # avbtool verifies descriptors against <partition>.img next to vbmeta.img: link the
    # kept current boot and the unchanged factory partitions for the verification only.
    links = {'boot': current_boot}
    links.update({name: STOCK / (name + '.img') for name in ['dtbo', 'recovery', 'vendor', 'product', 'odm']})
    for name, target in links.items():
        link = OUTPUT / (name + '.img')
        if link.is_symlink():
            link.unlink()
        link.symlink_to(target)
    try:
        verification = builder.avb_command('verify_image', '--image', root, '--key', key, *expected)
        chained = builder.avb_command('verify_image', '--image', root, *expected, '--follow_chain_partitions')
    finally:
        for name in links:
            (OUTPUT / (name + '.img')).unlink()
    (META / 'avb-verification.log').write_text(verification + '\n' + chained)
    for name in ['system', 'vbmeta', 'vbmeta_system']:
        (META / (name + '-avb-info.txt')).write_text(builder.avb_command('info_image', '--image', OUTPUT / (name + '.img')))
    files = {path.name: {'bytes': path.stat().st_size, 'sha256': digest(path)} for path in [raw, root, child]}
    report = {'created_at': datetime.now(timezone.utc).isoformat(), 'name': NAME,
              'plan_created_at': plan['created_at'], 'files': files,
              'partition_size': partition_size, 'filesystem_size': filesystem_size,
              'filesystem_blocks': filesystem_size // 4096, 'filesystem_uuid': image_uuid,
              'e2fsck_exit_code': 0, 'e2fsck_summary': consistency.stdout.strip().splitlines()[-1],
              'avb_chain_verified': True, 'avb_key': 'AOSP external/avb/test/data/testkey_rsa4096.pem (development)',
              'avb_public_key_sha256': digest(public), 'avb_root_flags': stock_root_header.flags,
              'avb_root_rollback_index': stock_root_header.rollback_index,
              'avb_system_rollback_index': stock_system_header.rollback_index,
              'system_security_patch_property': patch,
              'current_boot_sha256': boot_report['current_boot_sha256'],
              'recovery_chain_key': 'factory recovery public key (unchanged descriptor)',
              'super_lp_metadata_rebuilt': False, 'headset_modified': False}
    (STAGE / 'image.json').write_text(json.dumps(report, indent=1) + '\n')
    print(json.dumps(report, indent=1))


# --------------------------------------------------------------------------- readback (root)

def readback():
    if os.geteuid() != 0:
        raise RuntimeError('The read-only loop mount requires WSL root')
    pico.guard_volume()
    plan = json.loads((STAGE / 'plan.json').read_text())
    image = json.loads((STAGE / 'image.json').read_text())
    raw = OUTPUT / 'system.img'
    if digest(raw) != image['files']['system.img']['sha256']:
        raise RuntimeError('Output system changed after --build')
    mount = STAGE / 'mnt-output'
    mount.mkdir(exist_ok=True)
    if os.path.ismount(mount) or list(mount.iterdir()):
        raise RuntimeError('Mount point in use: ' + str(mount))
    expected = {entry['path']: entry for entry in plan['entries']}
    labels, problems = {}, []
    subprocess.run(['mount', '-t', 'ext4', '-o', 'loop,ro,noload', str(raw), str(mount)], check=True)
    try:
        options = subprocess.check_output(['findmnt', '-n', '-o', 'OPTIONS', '--mountpoint', str(mount)], text=True)
        if 'ro' not in options.strip().split(','):
            raise RuntimeError('Readback mount must be read only')
        paths = {'/'}
        for folder, directories, files in os.walk(mount, followlinks=False):
            paths.update('/' + str((Path(folder) / name).relative_to(mount)) for name in directories + files)
        paths.discard('/lost+found')
        if paths != set(expected):
            problems.append({'entries_differ': {'extra': sorted(paths - set(expected))[:50],
                                                'missing': sorted(set(expected) - paths)[:50]}})
        for relative, entry in sorted(expected.items()):
            file = mount / relative.lstrip('/')
            if not os.path.lexists(file):
                continue
            actual = extractor.metadata(file, relative)
            for key in ['kind', 'uid', 'gid', 'mode', 'capabilities']:
                if actual[key] != entry.get(key, 0 if key == 'capabilities' else None):
                    problems.append({'path': relative, 'key': key, 'image': actual[key], 'plan': entry.get(key)})
            if entry['kind'] == 'file' and (actual['bytes'] != entry['bytes'] or digest(file) != entry['sha256']):
                problems.append({'path': relative, 'key': 'content'})
            if entry['kind'] == 'symlink' and actual['target'] != entry['target']:
                problems.append({'path': relative, 'key': 'target'})
            labels[relative] = actual['selinux']
    finally:
        subprocess.run(['umount', str(mount)], check=True)
    report = {'created_at': datetime.now(timezone.utc).isoformat(), 'image_sha256': image['files']['system.img']['sha256'],
              'entries_checked': len(labels), 'problems': problems, 'labels': labels}
    out = STAGE / 'readback.json'
    out.write_text(json.dumps(report, indent=1) + '\n')
    user = pwd.getpwnam(USER)
    os.chown(out, user.pw_uid, user.pw_gid)
    os.chown(mount, user.pw_uid, user.pw_gid)
    print(json.dumps({'entries_checked': len(labels), 'problems': len(problems)}))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = parser.add_mutually_exclusive_group(required=True)
    for flag in ['--source-tree', '--stage', '--build', '--readback']:
        group.add_argument(flag, action='store_true')
    args = parser.parse_args()
    if args.source_tree:
        source_tree()
    elif args.stage:
        stage()
    elif args.build:
        build()
    else:
        readback()


if __name__ == '__main__':
    main()
