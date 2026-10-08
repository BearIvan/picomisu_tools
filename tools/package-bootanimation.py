"""Package a rendered Picomisu PNG as a stored Android bootanimation ZIP."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import zipfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('png', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    data = args.png.read_bytes()
    if data[:8] != b'\x89PNG\r\n\x1a\n':
        raise ValueError('Expected a PNG frame')
    width, height = struct.unpack('>II', data[16:24])
    if not (0 < width <= 1080 and 0 < height <= 1080):
        raise ValueError('Frame must fit within one INNOLUX5K eye view')
    desc = f'{width} {height} 15\np 1 0 part0\np 0 0 part1\n'.encode()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.output, 'w', compression=zipfile.ZIP_STORED) as archive:
        for name, content in [('desc.txt', desc), ('part0/01.png', data), ('part1/01.png', data)]:
            entry = zipfile.ZipInfo(name, (2026, 10, 3, 0, 0, 0))
            entry.external_attr = 0o100644 << 16
            archive.writestr(entry, content)
    with zipfile.ZipFile(args.output) as archive:
        assert archive.testzip() is None
        assert all(entry.compress_type == zipfile.ZIP_STORED for entry in archive.infolist())
        assert archive.read('desc.txt') == desc
        assert archive.read('part0/01.png') == archive.read('part1/01.png') == data
    print(json.dumps({'file': str(args.output), 'width': width, 'height': height,
                      'fps': 15, 'stored': True, 'crc_valid': True,
                      'sha256': hashlib.sha256(args.output.read_bytes()).hexdigest()}, indent=2))


if __name__ == '__main__':
    main()
