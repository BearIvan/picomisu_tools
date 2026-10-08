"""Verify the saved current boot and its factory kernel/DTB without changing USB state."""
import hashlib
import json
from pathlib import Path
import struct
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PROJECT = Path('//wsl.localhost/Ubuntu-24.04/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro')
ADB = Path('C:/Users/RedPanda/AppData/Local/Android/Sdk/platform-tools/adb.exe')


def chunks(path):
    with path.open('rb') as stream:
        header = stream.read(4096)
        if header[:8] != b'ANDROID!':
            raise RuntimeError('Unexpected boot image header')
        word = lambda offset: struct.unpack_from('<I', header, offset)[0]
        kernel_size, ramdisk_size, second_size, page, version = [word(offset) for offset in [8, 16, 24, 36, 40]]
        if version != 2 or page != 4096 or word(1632) != 0:
            raise RuntimeError('Unexpected boot v2 layout')
        align = lambda size: (size + page - 1) // page * page
        stream.seek(page)
        kernel = stream.read(kernel_size)
        stream.seek(page + align(kernel_size) + align(ramdisk_size) + align(second_size))
        dtb = stream.read(word(1648))
    if len(kernel) != kernel_size or len(dtb) != word(1648):
        raise RuntimeError('Incomplete boot kernel/DTB')
    return {'kernel_sha256': hashlib.sha256(kernel).hexdigest(), 'dtb_sha256': hashlib.sha256(dtb).hexdigest(),
            'kernel_bytes': kernel_size, 'dtb_bytes': len(dtb)}


def main():
    captured = PROJECT / 'stock/5.13.7-live/boot.img'
    factory = PROJECT / 'stock/5.13.7-SEKO/boot.img'
    capture = json.loads((ROOT / 'reports/baseline-5.13.7/verification.json').read_text())['images']['boot']
    actual = hashlib.sha256(captured.read_bytes()).hexdigest()
    if actual != capture['sha256']:
        raise RuntimeError('Saved current boot changed')
    current_parts, factory_parts = chunks(captured), chunks(factory)
    if current_parts != factory_parts:
        raise RuntimeError('Current boot kernel or DTB differs from authenticated factory boot')
    state = subprocess.check_output([str(ADB), 'get-state'], text=True, timeout=30).strip()
    model = subprocess.check_output([str(ADB), 'shell', 'getprop', 'ro.product.device'], text=True, timeout=30).strip()
    if state != 'device' or model != 'PICOA8110':
        raise RuntimeError('Expected one authorized PICO headset; no device modifications made')
    readback = subprocess.check_output([str(ADB), 'shell', "su -c 'toybox sha256sum /dev/block/bootdevice/by-name/boot'"],
                                      text=True, timeout=90).strip().split()[0]
    if readback != actual:
        raise RuntimeError('Current headset boot differs from captured boot; preserve the new state')
    report = {'current_boot_sha256': actual, 'current_boot_bytes': captured.stat().st_size,
              'current_device_readback_matches': True, 'kernel_and_dtb_equal_factory': True,
              'current_boot_file': '/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro/stock/5.13.7-live/boot.img',
              'preserve_current_boot_and_root': True, 'boot_flash_required': False,
              'parts': current_parts, 'headset_modified': False}
    (ROOT / 'reports/vr-integration/current-boot.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'boot_readback_matches': True, 'factory_kernel_and_dtb_preserved': True,
                      'boot_flash_required': False}))


if __name__ == '__main__':
    main()
