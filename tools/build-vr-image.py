"""Build and cryptographically verify the staged hybrid VR development image.

Uses the existing public AOSP development AVB key. This is not an OEM update
or a production release, and is not installable through the stock OTA verifier.
All stock blobs retain their original APK/APEX signatures. No headset writes.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid

spec = importlib.util.spec_from_file_location('pico_assembler', Path(__file__).with_name('assemble-vr-system.py'))
pico = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pico)
AVB_FILE = pico.env.AVBTOOL
AVB_SPEC = importlib.util.spec_from_file_location('pico_avbtool', AVB_FILE)
avb = importlib.util.module_from_spec(AVB_SPEC)
AVB_SPEC.loader.exec_module(avb)
KEY = pico.SOURCE / 'external/avb/test/data/testkey_rsa4096.pem'
OUTPUT = pico.PROJECT / 'outputs/vr-preview-01'
STOCK = pico.env.STOCK
TIMESTAMP = 1790603988


def command(arguments, **kwargs):
    result = subprocess.run([str(item) for item in arguments], check=True, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, **kwargs)
    return result.stdout


def avb_command(*arguments):
    return command([sys.executable, AVB_FILE, *arguments])


def image_data(path):
    return avb.Avb()._parse_image(avb.ImageHandler(str(path), read_only=True))


def vbmeta_blob(descriptors, rollback_index=0, flags=0):
    return avb.Avb()._generate_vbmeta_blob(
        algorithm_name='NONE', key_path=None, public_key_metadata_path=None,
        descriptors=descriptors, chain_partitions_use_ab=None,
        chain_partitions_do_not_use_ab=None, rollback_index=rollback_index,
        flags=flags, rollback_index_location=0, props=None, props_from_file=None,
        kernel_cmdlines=None, setup_rootfs_from_kernel=None, ht_desc_to_setup=None,
        include_descriptors_from_image=None, signing_helper=None,
        signing_helper_with_files=None, release_string=None,
        append_to_release_string=None, required_libavb_version_minor=0)


def build():
    pico.guard_volume()
    staging = json.loads((pico.REPORTS / 'staging.json').read_text())
    if not staging['complete'] or Path(staging['tree']) != pico.TREE:
        raise RuntimeError('Expected complete owned staging tree')
    boot_report = json.loads((pico.REPORTS / 'current-boot.json').read_text())
    current_boot = Path(boot_report['current_boot_file'])
    if not boot_report['current_device_readback_matches'] or not boot_report['kernel_and_dtb_equal_factory']:
        raise RuntimeError('Current boot preservation has not passed verification')
    if pico.digest(current_boot) != boot_report['current_boot_sha256']:
        raise RuntimeError('Saved current boot changed after readback verification')
    if OUTPUT.exists() and any(OUTPUT.iterdir()):
        raise RuntimeError('Preserve existing output; validate it instead of overwriting')
    OUTPUT.mkdir(parents=True, exist_ok=True)
    entries = staging['entries']
    lost_found = pico.TREE / 'lost+found'
    expected_lost_found = next(entry for entry in entries if entry['path'] == '/lost+found')
    if (expected_lost_found['uid'], expected_lost_found['gid'], expected_lost_found['mode']) != (0, 0, '0700'):
        raise RuntimeError('Nonstandard lost+found needs explicit metadata handling')
    # e2fsdroid skips canned uid/gid/mode for lost+found. Let mke2fs create the
    # empty directory with its correct root owner instead of importing host uid.
    if lost_found.exists():
        if lost_found.is_symlink() or not lost_found.is_dir() or any(lost_found.iterdir()):
            raise RuntimeError('Preserve nonempty or unexpected staged lost+found')
        lost_found.rmdir()
    metadata = pico.STAGE / 'image-metadata'
    metadata.mkdir(exist_ok=True)
    fs_config = metadata / 'fs_config.txt'
    contexts = metadata / 'file_contexts.txt'
    fs_config.write_text(''.join(
        f'{entry["path"].lstrip("/")} {entry["uid"]} {entry["gid"]} {entry["mode"]} '
        f'capabilities=0x{entry["capabilities"]:x}\n' for entry in entries))
    contexts.write_text(''.join(
        f'{re.escape(entry["path"])} {entry["selinux"]}\n' for entry in entries))
    partition_size = next(partition['bytes'] for partition in json.loads(
        (pico.ROOT / 'reports/board/lp-metadata.json').read_text())['metadata'][0]['partitions']
        if partition['name'] == 'system')
    maximum = int(avb_command('add_hashtree_footer', '--partition_size', partition_size,
                             '--hash_algorithm', 'sha256', '--do_not_generate_fec', '--calc_max_image_size').strip())
    filesystem_size = maximum // 4096 * 4096
    raw = OUTPUT / 'system.img'
    env = dict(os.environ, MKE2FS_CONFIG=str(pico.SOURCE / 'system/extras/ext4_utils/mke2fs.conf'),
               E2FSPROGS_FAKE_TIME=str(TIMESTAMP))
    image_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, 'pico-aosp-vr-preview-01-system'))
    hash_seed = str(uuid.uuid5(uuid.NAMESPACE_DNS, 'pico-aosp-vr-preview-01-directory-hash'))
    command([pico.HOST / 'mke2fs', '-t', 'ext4', '-b', '4096', '-m', '0', '-N', len(entries) + 256,
             '-I', '256', '-L', '/', '-M', '/', '-U', image_uuid, '-O', '^has_journal',
             '-E', 'hash_seed=' + hash_seed,
             raw, filesystem_size // 4096], env=env)
    print(json.dumps({'filesystem_size': filesystem_size, 'partition_size': partition_size}), flush=True)
    population = command([pico.HOST / 'e2fsdroid', '-e', '-s', '-T', TIMESTAMP,
                          '-C', fs_config, '-S', contexts, '-f', pico.TREE, '-a', '/', raw], env=env)
    (metadata / 'e2fsdroid.log').write_text(population)
    print(json.dumps({'ext4_population_complete': True}), flush=True)
    consistency = command([pico.HOST / 'e2fsck', '-f', '-n', raw])
    (metadata / 'e2fsck.log').write_text(consistency)
    salt = hashlib.sha256(b'PICO_AOSP_10_BRINGUP_2026092801/system').hexdigest()
    properties = dict(line.split('=', 1) for line in (pico.TREE / 'system/build.prop').read_text().splitlines()
                      if '=' in line and not line.startswith('#'))
    patch = properties['ro.build.version.security_patch']
    _, stock_system_header, stock_system_descriptors, _ = image_data(STOCK / 'vbmeta_system.img')
    avb_command('add_hashtree_footer', '--image', raw, '--partition_name', 'system',
                '--partition_size', partition_size, '--algorithm', 'SHA256_RSA4096', '--key', KEY,
                '--hash_algorithm', 'sha256', '--salt', salt, '--do_not_generate_fec',
                '--rollback_index', stock_system_header.rollback_index,
                '--prop', 'com.android.build.system.os_version:10',
                '--prop', 'com.android.build.system.security_patch:' + patch)
    stock_child = [descriptor for descriptor in stock_system_descriptors
                   if (isinstance(descriptor, avb.AvbHashtreeDescriptor) and descriptor.partition_name == 'product')
                   or (isinstance(descriptor, avb.AvbPropertyDescriptor) and descriptor.key.startswith('com.android.build.product.'))]
    product_metadata = metadata / 'factory-product.vbmeta'
    product_metadata.write_bytes(vbmeta_blob(stock_child))
    child = OUTPUT / 'vbmeta_system.img'
    avb_command('make_vbmeta_image', '--output', child, '--algorithm', 'SHA256_RSA4096', '--key', KEY,
                '--include_descriptors_from_image', raw, '--include_descriptors_from_image', product_metadata,
                '--rollback_index', stock_system_header.rollback_index, '--padding_size', '65536')
    _, stock_root_header, stock_root_descriptors, _ = image_data(STOCK / 'vbmeta.img')
    preserved_root_descriptors = []
    for descriptor in stock_root_descriptors:
        if isinstance(descriptor, avb.AvbChainPartitionDescriptor):
            continue
        if isinstance(descriptor, avb.AvbHashDescriptor) and descriptor.partition_name == 'boot':
            replacement = avb.AvbHashDescriptor()
            replacement.partition_name = 'boot'
            replacement.image_size = current_boot.stat().st_size
            replacement.hash_algorithm = 'sha256'
            replacement.salt = hashlib.sha256(b'PICO_AOSP_10_BRINGUP_2026092801/current-boot').digest()
            hasher = hashlib.sha256(replacement.salt)
            with current_boot.open('rb') as stream:
                for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b''):
                    hasher.update(chunk)
            replacement.digest = hasher.digest()
            replacement.flags = descriptor.flags
            preserved_root_descriptors.append(replacement)
        else:
            preserved_root_descriptors.append(descriptor)
    root_metadata = metadata / 'factory-root-without-chains.vbmeta'
    root_metadata.write_bytes(vbmeta_blob(preserved_root_descriptors,
                                        rollback_index=stock_root_header.rollback_index,
                                        flags=stock_root_header.flags))
    public = metadata / 'preview.avbpubkey'
    avb_command('extract_public_key', '--key', KEY, '--output', public)
    recovery_chain = next(descriptor for descriptor in stock_root_descriptors
                          if isinstance(descriptor, avb.AvbChainPartitionDescriptor)
                          and descriptor.partition_name == 'recovery')
    recovery_public = metadata / 'factory-recovery.avbpubkey'
    recovery_public.write_bytes(recovery_chain.public_key)
    root = OUTPUT / 'vbmeta.img'
    avb_command('make_vbmeta_image', '--output', root, '--algorithm', 'SHA256_RSA4096', '--key', KEY,
                '--include_descriptors_from_image', root_metadata,
                '--chain_partition', f'recovery:{recovery_chain.rollback_index_location}:{recovery_public}',
                '--chain_partition', f'vbmeta_system:2:{public}',
                '--rollback_index', stock_root_header.rollback_index, '--flags', stock_root_header.flags,
                '--padding_size', '65536')
    (OUTPUT / 'boot.img').symlink_to(current_boot)
    for name in ['dtbo', 'recovery', 'vendor', 'product', 'odm']:
        (OUTPUT / (name + '.img')).symlink_to(STOCK / (name + '.img'))
    finalize()


def embedded_public_key(path):
    footer, header, _, _ = image_data(path)
    offset = footer.vbmeta_offset if footer else 0
    with path.open('rb') as stream:
        stream.seek(offset + 256 + header.authentication_data_block_size + header.public_key_offset)
        return stream.read(header.public_key_size)


def finalize():
    pico.guard_volume()
    raw = OUTPUT / 'system.img'
    root = OUTPUT / 'vbmeta.img'
    child = OUTPUT / 'vbmeta_system.img'
    metadata = pico.STAGE / 'image-metadata'
    public = metadata / 'preview.avbpubkey'
    recovery_public = metadata / 'factory-recovery.avbpubkey'
    if not (metadata / 'e2fsck.log').is_file() or not (metadata / 'e2fsdroid.log').is_file():
        raise RuntimeError('Expected completed owned filesystem build')
    footer, _, system_descriptors, _ = image_data(raw)
    system_descriptor = next(item for item in system_descriptors
                             if isinstance(item, avb.AvbHashtreeDescriptor) and item.partition_name == 'system')
    filesystem_size = footer.original_image_size
    partition_size = raw.stat().st_size
    image_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, 'pico-aosp-vr-preview-01-system'))
    boot_report = json.loads((pico.REPORTS / 'current-boot.json').read_text())
    _, stock_root_header, _, _ = image_data(STOCK / 'vbmeta.img')
    _, stock_system_header, _, _ = image_data(STOCK / 'vbmeta_system.img')
    _, _, root_descriptors, _ = image_data(root)
    recovery_chain = next(item for item in root_descriptors
                          if isinstance(item, avb.AvbChainPartitionDescriptor) and item.partition_name == 'recovery')
    for item in root_descriptors:
        if isinstance(item, avb.AvbChainPartitionDescriptor):
            if embedded_public_key(OUTPUT / (item.partition_name + '.img')) != item.public_key:
                raise RuntimeError('Embedded child key does not match authenticated parent chain: ' + item.partition_name)
    expected = ['--expected_chain_partition', f'recovery:{recovery_chain.rollback_index_location}:{recovery_public}',
                '--expected_chain_partition', f'vbmeta_system:2:{public}']
    # avbtool propagates --key to every recursive child. Pin our root separately;
    # the preserved recovery intentionally uses the manufacturer's different key.
    root_verification = avb_command('verify_image', '--image', root, '--key', KEY, *expected)
    verification = avb_command('verify_image', '--image', root, *expected, '--follow_chain_partitions')
    verification = root_verification + '\nEach chained image public key matched its parent descriptor.\n' + verification
    (metadata / 'avb-verification.log').write_text(verification)
    for name in ['system', 'vbmeta', 'vbmeta_system']:
        (metadata / (name + '-avb-info.txt')).write_text(avb_command('info_image', '--image', OUTPUT / (name + '.img')))
    sparse = OUTPUT / 'system.sparse.img'
    if sparse.exists():
        raise RuntimeError('Preserve existing sparse output')
    command([pico.HOST / 'img2simg', raw, sparse])
    files = {path.name: {'path': str(path), 'bytes': path.stat().st_size, 'sha256': pico.digest(path)}
             for path in [raw, sparse, root, child]}
    report = {'created_at': datetime.now(timezone.utc).isoformat(), 'system_image_built': True,
              'kind': 'hybrid-prototype', 'files': files,
              'filesystem_size': filesystem_size, 'partition_size': partition_size,
              'filesystem_uuid': image_uuid, 'uses_factory_shared_block_format': True,
              'e2fsck_exit_code': 0, 'avb_chain_verification_exit_code': 0,
              'avb_key': 'existing public AOSP testkey_rsa4096.pem; development only',
              'avb_public_key_sha256': pico.digest(public),
              'avb_root_flags': stock_root_header.flags, 'avb_root_rollback_index': stock_root_header.rollback_index,
              'avb_system_rollback_index': stock_system_header.rollback_index,
              'current_boot_sha256': boot_report['current_boot_sha256'],
              'current_boot_and_root_preserved': True, 'boot_flash_required': False,
              'oem_signed_ota': False, 'production_release': False,
              'full_aosp_framework_port_complete': False, 'on_device_vr_tested': False,
              'headset_modified': False, 'filesystem_contents_independently_verified': False,
              'metadata_directory': str(metadata)}
    (pico.REPORTS / 'image.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'image_created': True, 'avb_chain_verified': True,
                      'output': str(OUTPUT), 'on_device_vr_tested': False}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--build', action='store_true')
    group.add_argument('--finalize', action='store_true')
    args = parser.parse_args()
    build() if args.build else finalize()


if __name__ == '__main__':
    main()
