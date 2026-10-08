"""Verify the unchanged system APKs and identify their shared-UID signing groups."""
import importlib.util
import json
from pathlib import Path

spec = importlib.util.spec_from_file_location('pico_assembler', Path(__file__).with_name('assemble-vr-system.py'))
assembler = importlib.util.module_from_spec(spec)
spec.loader.exec_module(assembler)


def main():
    assembler.guard_volume()
    factory = json.loads((assembler.REPORTS / 'factory-system.json').read_text())
    packages = []
    for entry in factory['entries']:
        if entry['kind'] == 'file' and entry['path'].endswith('.apk'):
            path = Path(factory['tree']) / entry['path'].lstrip('/')
            if assembler.digest(path) != entry['sha256']:
                raise RuntimeError('Factory APK changed: ' + entry['path'])
            packages.append(dict(assembler.apk_identity(path), path=entry['path'], sha256=entry['sha256']))
            if len(packages) % 20 == 0:
                print(json.dumps({'verified_apks': len(packages)}), flush=True)
    platform = next(package for package in packages if package['package'] == 'android')
    mismatches = [package['path'] for package in packages
                  if package['shared_uid'] == 'android.uid.system'
                  and package['signer_sha256'] != platform['signer_sha256']]
    report = {'complete': True, 'packages': packages, 'platform_certificate': platform['signer_sha256'],
              'system_uid_signer_mismatches': mismatches, 'all_signatures_verified': True,
              'factory_image_sha256': factory['image_sha256']}
    (assembler.REPORTS / 'factory-apks.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'verified_apks': len(packages), 'system_uid_signer_mismatches': mismatches}))


if __name__ == '__main__':
    main()
