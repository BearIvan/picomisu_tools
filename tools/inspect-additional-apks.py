"""Verify package identities from the unchanged product/vendor/odm images."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess

spec = importlib.util.spec_from_file_location('pico_assembler', Path(__file__).with_name('assemble-vr-system.py'))
pico = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pico)


def main():
    pico.guard_volume()
    directory = pico.PROJECT / 'analysis/additional-factory-apks'
    directory.mkdir(parents=True, exist_ok=True)
    report_file = pico.REPORTS / 'additional-factory-apks.json'
    if report_file.exists():
        previous = json.loads(report_file.read_text())
        if previous['complete']:
            print(json.dumps({'already_verified': True, 'packages': len(previous['packages'])}))
            return
        raise RuntimeError('Preserve existing unfinished verification')
    if pico.env.LEGACY:
        verified = json.loads((pico.ROOT / 'reports/baseline-5.13.7/verification.json').read_text())
    else:
        # The pinned factory OTA is the trust anchor; the APK list comes from the image itself.
        verified = {'images': pico.env.LOCK['images']}
    packages = []
    for partition in ['product', 'vendor', 'odm']:
        image = pico.env.STOCK / (partition + '.img')
        if pico.digest(image) != verified['images'][partition]['sha256']:
            raise RuntimeError('Factory partition changed: ' + partition)
        if pico.env.LEGACY:
            inventory = json.loads((pico.ROOT / f'reports/baseline-5.13.7/{partition}-files.json').read_text())
        else:
            tree = pico.PROJECT / 'analysis/stock-5.13.7-partitions' / partition
            inventory = [{'path': '/' + str(path.relative_to(tree)), 'bytes': path.stat().st_size}
                         for path in sorted(tree.rglob('*.apk')) if path.is_file() and not path.is_symlink()]
        for entry in inventory:
            if not entry['path'].endswith('.apk'):
                continue
            stem = hashlib.sha256((partition + entry['path']).encode()).hexdigest()
            output = directory / (stem + '.apk')
            if output.exists():
                raise RuntimeError('Preserve existing unverified APK cache file')
            subprocess.run(['debugfs', '-R', f'dump "{entry["path"]}" "{output}"', str(image)],
                           check=True, capture_output=True, text=True)
            if output.stat().st_size != entry['bytes']:
                raise RuntimeError('Incomplete factory APK extraction')
            packages.append(dict(pico.apk_identity(output), path='/' + partition + entry['path'],
                                 sha256=pico.digest(output), origin='factory'))
            if len(packages) % 20 == 0:
                print(json.dumps({'verified_additional_apks': len(packages)}), flush=True)
    report = {'complete': True, 'packages': packages, 'all_signatures_verified': True,
              'source_image_sha256': {name: verified['images'][name]['sha256'] for name in ['product', 'vendor', 'odm']}}
    report_file.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'verified_additional_apks': len(packages)}))


if __name__ == '__main__':
    main()
