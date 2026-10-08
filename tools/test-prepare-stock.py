"""Exercise cache validation and full BLOCK OTA extraction with tiny fixtures."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
import brotli

spec = importlib.util.spec_from_file_location('prepare_stock', Path(__file__).with_name('prepare-stock.py'))
prep = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prep)


def expected(data):
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


class StockPreparation(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.archive = self.root / 'stock.zip'
        self.payload = b'x' * 4096
        with zipfile.ZipFile(self.archive, 'w') as archive:
            archive.writestr('META-INF/com/android/metadata', 'pre-device=PICOA8110\n')
            archive.writestr('dynamic_partitions_op_list', 'resize system 8192\n')
            archive.writestr('system.transfer.list', '4\n2\n0\n0\nnew 2,0,1\nzero 2,1,2\n')
            archive.writestr('system.new.dat.br', brotli.compress(self.payload))
            archive.writestr('boot.img', b'boot')
        self.lock = {'build': 'test', 'filename': 'stock.zip',
                     'metadata': {'pre-device': 'PICOA8110'},
                     **expected(self.archive.read_bytes()),
                     'images': {'system': expected(self.payload + bytes(4096)),
                                'boot.img': expected(b'boot')}}
        self.out = self.root / 'images'

    def test_extract_and_reuse_without_rewrite(self):
        prep.fetch(self.lock, self.root, offline=True)
        prep.prepare(self.lock, self.archive, self.out)
        image = self.out / 'system.img'
        stamp = image.stat().st_mtime_ns
        prep.prepare(self.lock, self.archive, self.out)
        self.assertEqual(image.stat().st_mtime_ns, stamp)
        self.assertEqual(image.read_bytes(), self.payload + bytes(4096))

    def test_reject_corrupt_cached_archive(self):
        self.archive.write_bytes(b'bad')
        with self.assertRaises(ValueError):
            prep.fetch(self.lock, self.root, offline=True)

    def test_reject_changed_cached_image(self):
        prep.prepare(self.lock, self.archive, self.out)
        (self.out / 'boot.img').write_bytes(b'evil')
        with self.assertRaises(ValueError):
            prep.prepare(self.lock, self.archive, self.out)

    def test_reject_wrong_device(self):
        self.lock['metadata']['pre-device'] = 'other'
        with self.assertRaises(ValueError):
            prep.prepare(self.lock, self.archive, self.out)
        self.assertFalse((self.out / 'prepared-stock.json').exists())

    def test_failed_image_hash_is_not_promoted(self):
        self.lock['images']['system']['sha256'] = '0' * 64
        with self.assertRaises(ValueError):
            prep.prepare(self.lock, self.archive, self.out)
        self.assertFalse((self.out / 'system.img').exists())


if __name__ == '__main__':
    unittest.main()
