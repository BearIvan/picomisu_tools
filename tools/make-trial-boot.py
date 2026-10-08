"""Build a RAM-boot (fastboot boot) image: the current boot.img with only the kernel replaced.

Header v2 fields, cmdline, ramdisk and dtb are copied unchanged. Nothing is flashed or sent to a device.
"""
import argparse
import hashlib
import json
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha(b):
    return hashlib.sha256(b).hexdigest()


def parse(b):
    if b[:8] != b'ANDROID!':
        raise SystemExit('not an Android boot image')
    f = dict(zip(['kernel_size', 'kernel_addr', 'ramdisk_size', 'ramdisk_addr', 'second_size', 'second_addr',
                  'tags_addr', 'page_size', 'header_version', 'os_version'], struct.unpack_from('<10I', b, 8)))
    if f['header_version'] != 2:
        raise SystemExit('expected boot header v2')
    f['recovery_dtbo_size'], f['recovery_dtbo_offset'], f['header_size'] = struct.unpack_from('<IQI', b, 1632)
    f['dtb_size'], f['dtb_addr'] = struct.unpack_from('<IQ', b, 1648)
    pg = f['page_size']
    al = lambda x: (x + pg - 1) // pg * pg
    off = pg
    parts = {}
    for name in ['kernel', 'ramdisk', 'second', 'recovery_dtbo', 'dtb']:
        size = f[name + '_size']
        parts[name] = b[off:off + size]
        off += al(size)
    return f, parts


def build(header, parts):
    f, _ = parse(header)
    page = f['page_size']
    al = lambda x: (x + page - 1) // page * page
    out = bytearray(header[:page])
    struct.pack_into('<I', out, 8, len(parts['kernel']))
    # The image id (SHA-1 over sections in mkbootimg) is informational for ABL; recompute it the mkbootimg way.
    h = hashlib.sha1()
    for name in ['kernel', 'ramdisk', 'second', 'recovery_dtbo', 'dtb']:
        h.update(parts[name])
        h.update(struct.pack('<I', len(parts[name])))
    out[576:608] = h.digest().ljust(32, b'\0')
    for name in ['kernel', 'ramdisk', 'second', 'recovery_dtbo', 'dtb']:
        data = parts[name]
        out += data + b'\0' * (al(len(data)) - len(data))
    return bytes(out)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--base', required=True, type=Path, help='current boot.img (read from the device)')
    p.add_argument('--kernel', required=True, type=Path, help='raw arm64 Image')
    p.add_argument('--out', required=True, type=Path)
    a = p.parse_args()
    base = a.base.read_bytes()
    kernel = a.kernel.read_bytes()
    if kernel[56:60] != b'ARMd':
        raise SystemExit('kernel is not a raw arm64 Image')
    f, parts = parse(base)
    # The base id must match the mkbootimg digest, otherwise the id recomputation below is wrong.
    if build(base, parts)[576:608] != base[576:608]:
        raise SystemExit('base image id does not follow mkbootimg; refusing to rewrite it')
    parts['kernel'] = kernel
    img = build(base, parts)
    g, check = parse(img)
    for k in f:
        if k != 'kernel_size' and f[k] != g[k]:
            raise SystemExit('header field changed: ' + k)
    if base[64:576] != img[64:576] or base[608:1632] != img[608:1632] or base[48:64] != img[48:64]:
        raise SystemExit('cmdline/name changed')
    for name in ['ramdisk', 'second', 'recovery_dtbo', 'dtb']:
        if check[name] != parse(base)[1][name]:
            raise SystemExit(name + ' changed')
    if check['kernel'] != kernel:
        raise SystemExit('kernel mismatch')
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_bytes(img)
    report = {'base': str(a.base), 'base_sha256': sha(base), 'kernel': str(a.kernel), 'kernel_sha256': sha(kernel),
              'image': str(a.out), 'image_sha256': sha(img), 'image_bytes': len(img),
              'header': {k: (hex(v) if 'addr' in k or k == 'os_version' else v) for k, v in g.items()},
              'cmdline': (img[64:576].rstrip(b'\0') + img[608:1632].rstrip(b'\0')).decode(),
              'unchanged': ['header fields except kernel_size', 'name', 'cmdline', 'ramdisk', 'second', 'recovery_dtbo', 'dtb'],
              'purpose': 'fastboot boot (RAM only); not for flashing', 'device_modified': False}
    a.out.with_suffix('.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
