"""Preserve this task's failed output before correcting filesystem metadata."""
import importlib.util
import json
from pathlib import Path

spec = importlib.util.spec_from_file_location('pico_assembler', Path(__file__).with_name('assemble-vr-system.py'))
pico = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pico)


def main():
    pico.guard_volume()
    source = pico.PROJECT / 'outputs/vr-preview-01'
    target = pico.PROJECT / 'outputs/vr-preview-01-before-metadata-repair'
    report_file = pico.REPORTS / 'image.json'
    report = json.loads(report_file.read_text())
    if report['filesystem_contents_independently_verified'] or target.exists():
        raise RuntimeError('Preserve an already verified output or existing archive')
    if source.is_symlink() or not source.resolve().is_relative_to((pico.PROJECT / 'outputs').resolve()):
        raise RuntimeError('Output path escaped the owned project')
    for name in ['system.img', 'system.sparse.img', 'vbmeta.img', 'vbmeta_system.img']:
        if pico.digest(source / name) != report['files'][name]['sha256']:
            raise RuntimeError('Output changed after the owned build: ' + name)
    source.rename(target)
    report['preserved_failed_output'] = str(target)
    report['failure'] = 'lost+found imported host UID 1000 because e2fsdroid skips canned ownership for this directory'
    for entry in report['files'].values():
        entry['path'] = str(target / Path(entry['path']).name)
    (pico.REPORTS / 'image-before-metadata-repair.json').write_text(json.dumps(report, indent=2) + '\n')
    report_file.unlink()
    print(json.dumps({'failed_output_preserved': str(target)}))


if __name__ == '__main__':
    main()
