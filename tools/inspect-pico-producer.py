"""Locate command 10000 in the authenticated graphics library for the source port."""
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PROJECT = Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro')
SOURCE = PROJECT / 'source/aosp-10'


def main():
    factory = json.loads((ROOT / 'reports/vr-integration/factory-system.json').read_text())
    entry = next(entry for entry in factory['entries'] if entry['path'] == '/system/lib64/libgui.so')
    binary = Path(factory['tree']) / entry['path'].lstrip('/')
    if hashlib.sha256(binary.read_bytes()).hexdigest() != entry['sha256']:
        raise RuntimeError('Factory graphics library changed')
    tool = SOURCE / 'prebuilts/clang/host/linux-x86/clang-r353983c/bin/llvm-objdump'
    disassembly = subprocess.check_output([str(tool), '-d', '--demangle', str(binary)], text=True)
    directory = PROJECT / 'analysis/graphics-protocol'
    directory.mkdir(parents=True, exist_ok=True)
    (directory / 'libgui.asm.txt').write_text(disassembly)
    lines = disassembly.splitlines()
    matches = []
    for index, line in enumerate(lines):
        if re.search(r'#(?:10000\b|0x2710\b)', line):
            matches.append({'instruction': line, 'context': '\n'.join(lines[max(0, index - 25):index + 45])})
    source_file = SOURCE / 'frameworks/native/libs/gui/IGraphicBufferProducer.cpp'
    source = source_file.read_text().splitlines()
    aosp = []
    for index, line in enumerate(source):
        if 'status_t query(' in line or 'int query(' in line or 'case QUERY:' in line:
            aosp.append({'line': index + 1, 'context': '\n'.join(source[max(0, index - 2):index + 32])})
    server_contexts = []
    server = False
    for index, line in enumerate(lines):
        if re.match(r'^[0-9a-f]{16} ', line):
            server = 'android::BnGraphicBufferProducer::onTransact(' in line
        if server and re.search(r'ldr\s+x\d+, \[x\d+, #120\]', line):
            server_contexts.append('\n'.join(lines[max(0, index - 32):index + 18]))
    report = {'factory_binary': str(binary), 'sha256': entry['sha256'], 'command_10000_matches': matches,
              'full_disassembly': str(directory / 'libgui.asm.txt'), 'aosp_query_implementation': aosp,
              'factory_server_query_contexts': server_contexts,
              'source_patch_validated': False, 'protocol_semantics_confirmed': False}
    (ROOT / 'reports/framework-bridge/producer-protocol.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'command_10000_instruction_matches': len(matches),
                      'instructions': [item['instruction'] for item in matches]}))


if __name__ == '__main__':
    main()
