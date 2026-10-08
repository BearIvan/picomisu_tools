"""Record direct references to the identified factory VR field, without device access.

Offset matches are candidates only: registers must be traced to BufferQueueCore
before interpreting a match as a VR status access. Reports remain local.
"""
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PROJECT = Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro')


def main():
    factory = json.loads((ROOT / 'reports/vr-integration/factory-system.json').read_text())
    tool = PROJECT / 'source/aosp-10/prebuilts/clang/host/linux-x86/clang-r353983c/bin/llvm-objdump'
    directory = PROJECT / 'analysis/graphics-protocol'
    directory.mkdir(parents=True, exist_ok=True)
    reports = []
    for name in ('libgui.so', 'libsurfaceflinger.so'):
        path = '/system/lib64/' + name
        entry = next(row for row in factory['entries'] if row['path'] == path)
        binary = Path(factory['tree']) / path.lstrip('/')
        digest = hashlib.sha256(binary.read_bytes()).hexdigest()
        if digest != entry['sha256']:
            raise RuntimeError('Factory binary changed: ' + str(binary))
        disassembly = subprocess.check_output([str(tool), '-d', '--demangle', str(binary)], text=True)
        (directory / (name + '.asm.txt')).write_text(disassembly)
        matches = []
        function = None
        for line in disassembly.splitlines():
            if re.match(r'^[0-9a-f]{16} ', line):
                function = line
            if re.search(r'#(?:5776|5780|5784|5785)(?:\]|\s|$)', line):
                matches.append({'function': function, 'instruction': line.strip()})
        reports.append({'binary': name, 'sha256': digest, 'offsets': [5776, 5780, 5784, 5785],
                        'direct_offset_candidates': matches,
                        'indirect_accesses_not_excluded': True})
    destination = ROOT / 'reports/framework-bridge/bufferqueue-status-references.json'
    destination.write_text(json.dumps(reports, indent=2) + '\n')
    print(json.dumps(reports, indent=2))


if __name__ == '__main__':
    main()
