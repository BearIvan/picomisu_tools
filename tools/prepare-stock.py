"""Fetch pinned PICO inputs and reconstruct factory images; never access a device."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
LOGICAL = {'system', 'vendor', 'product', 'odm'}


def verify(path, expected):
    if path.stat().st_size != expected['bytes']:
        raise ValueError(f'Size mismatch: {path}')
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(4 * 1024 * 1024), b''):
            digest.update(chunk)
    if digest.hexdigest() != expected['sha256']:
        raise ValueError(f'SHA-256 mismatch: {path}')


def fetch(lock, cache, offline=False):
    cache.mkdir(parents=True, exist_ok=True)
    final = cache / lock['filename']
    if final.exists():
        verify(final, lock)
        return final
    if offline:
        raise FileNotFoundError(f'Offline cache missing: {final}')
    if not lock['url'].startswith('https://'):
        raise ValueError('Firmware download requires HTTPS')
    # Use an isolated temporary file; failed downloads never become cache hits.
    with tempfile.TemporaryDirectory(prefix='.download-', dir=cache) as temporary:
        partial = Path(temporary) / 'firmware.zip'
        print(f"Downloading {lock['filename']}", flush=True)
        with urllib.request.urlopen(lock['url'], timeout=60) as source, partial.open('wb') as output:
            if not source.geturl().startswith('https://'):
                raise ValueError('Refusing non-HTTPS redirect')
            total = 0
            for chunk in iter(lambda: source.read(4 * 1024 * 1024), b''):
                total += len(chunk)
                if total > lock['bytes']:
                    raise ValueError('Download exceeds pinned size')
                output.write(chunk)
        verify(partial, lock)
        partial.replace(final)
    return final


def prepare(lock, archive_path, destination):
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path) as archive:
        metadata = dict(line.split('=', 1) for line in
                        archive.read('META-INF/com/android/metadata').decode().splitlines()
                        if '=' in line)
        if any(metadata.get(key) != value for key, value in lock['metadata'].items()):
            raise ValueError('Firmware device/build metadata does not match lock')
        ops = archive.read('dynamic_partitions_op_list').decode('ascii')
        sizes = {fields[1]: int(fields[2]) for line in ops.splitlines()
                 if (fields := line.split()) and fields[0] == 'resize'}
        spec = importlib.util.spec_from_file_location('stock_extract', ROOT / 'tools/extract-stock.py')
        extractor = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(extractor)
        results = {}
        for name, expected in lock['images'].items():
            filename = name + '.img' if name in LOGICAL else Path(name).name
            final = destination / filename
            if final.exists():
                verify(final, expected)
                print(f'Verified cached {filename}', flush=True)
            else:
                print(f'Extracting {filename}', flush=True)
                with tempfile.TemporaryDirectory(prefix='.extract-', dir=destination) as temporary:
                    temporary = Path(temporary)
                    candidate = temporary / filename
                    if name in LOGICAL:
                        if sizes.get(name) != expected['bytes']:
                            raise ValueError(f'Unexpected logical size: {name}')
                        extractor.reconstruct(archive, name, temporary, expected['bytes'])
                    else:
                        if archive.getinfo(name).file_size != expected['bytes']:
                            raise ValueError(f'Unexpected ZIP entry size: {name}')
                        with archive.open(name) as source, candidate.open('xb') as output:
                            shutil.copyfileobj(source, output)
                    verify(candidate, expected)
                    candidate.replace(final)
            results[name] = {'file': str(final.resolve()), **expected}
        report = {'complete': True, 'build': lock['build'],
                  'source_zip_sha256': lock['sha256'], 'images': results,
                  'headset_modified': False}
        (destination / 'prepared-stock.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lock', type=Path, default=ROOT / 'config/stock-firmware.lock.json')
    parser.add_argument('--cache', type=Path, default=ROOT / 'stock')
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--offline', action='store_true')
    args = parser.parse_args()
    lock = json.loads(args.lock.read_text(encoding='utf-8'))
    archive = fetch(lock, args.cache, args.offline)
    prepare(lock, archive, args.out)
    print('Verified PICO factory inputs are ready.', flush=True)


if __name__ == '__main__':
    main()
