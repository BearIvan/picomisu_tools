"""Extract authenticated Ubuntu compatibility packages for the old AOSP Clang.

Uses an isolated APT state; does not install packages or change Ubuntu sources.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import importlib.util as _util

_spec = _util.spec_from_file_location('picomisu_env', Path(__file__).with_name('picomisu_env.py'))
penv = _util.module_from_spec(_spec)
_spec.loader.exec_module(penv)
ROOT = penv.ROOT
PROJECT = penv.WORK
COMPAT = PROJECT / 'toolchains/host-compat'


def main():
    penv.guard_volume()
    COMPAT.mkdir(parents=True, exist_ok=True)
    apt = COMPAT / 'apt'
    for name in ['lists/partial', 'cache/archives/partial']:
        (apt / name).mkdir(parents=True, exist_ok=True)
    sources = apt / 'sources.list'
    sources.write_text('\n'.join(
        f'deb [arch=amd64 signed-by=/usr/share/keyrings/ubuntu-archive-keyring.gpg] '
        f'https://archive.ubuntu.com/ubuntu {suite} main universe'
        for suite in ['jammy', 'jammy-updates', 'jammy-security']) + '\n')
    options = [
        '-o', f'Dir::Etc::sourcelist={sources}', '-o', 'Dir::Etc::sourceparts=-',
        '-o', f'Dir::State::lists={apt / "lists"}',
        '-o', f'Dir::Cache={apt / "cache"}',
        '-o', 'APT::Get::List-Cleanup=0', '-o', 'Acquire::Languages=none',
    ]
    subprocess.run(['apt-get', *options, 'update'], check=True)
    packages = []
    for package in ['libncurses5', 'libtinfo5']:
        metadata = subprocess.check_output(['apt-cache', *options, 'show', package], text=True)
        stanza = metadata.split('\n\n', 1)[0]
        fields = dict(line.split(': ', 1) for line in stanza.splitlines() if ': ' in line and not line.startswith(' '))
        version, expected = fields['Version'], fields['SHA256']
        filename = COMPAT / Path(fields['Filename']).name
        if not filename.exists():
            subprocess.run(['apt-get', *options, 'download', f'{package}={version}'], cwd=COMPAT, check=True)
        actual = hashlib.sha256(filename.read_bytes()).hexdigest()
        if actual != expected:
            raise RuntimeError('APT package checksum mismatch: ' + package)
        subprocess.run(['dpkg-deb', '-x', str(filename), str(COMPAT / 'root')], check=True)
        packages.append({'package': package, 'version': version, 'sha256': actual,
                         'file': str(filename), 'authenticated_apt_metadata': True})
    library_path = COMPAT / 'root/lib/x86_64-linux-gnu'
    env = dict(os.environ, LD_LIBRARY_PATH=str(library_path))
    clang = (PROJECT / 'source/aosp-10' if penv.LEGACY else penv.TOP) / 'prebuilts/clang/host/linux-x86/clang-3289846/bin/clang.real'
    check = subprocess.run([str(clang), '--version'], env=env, check=True, capture_output=True, text=True) if clang.exists() else None
    report = {'packages': packages, 'library_path': str(library_path),
              'clang_version_check': check.stdout.strip() if check else None, 'ubuntu_packages_installed': False}
    destination = penv.REPORTS / 'aosp-preparation/host-compat.json'
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
