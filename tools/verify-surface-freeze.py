"""Verify compiled Java callers and both-ABI Surface freeze JNI entries.

Windows Python reads WSL ELF/JAR artifacts. The source-built static ART
dexdumps.exe understands the factory Android 10 hidden-api map. This verifies
compiled declarations/call sites and selected factory instructions. Java runtime
qualification imports the separately executed checkpoint only when artifact
hashes match. Real freezing and complete runtime ABI remain separate checks.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('producer_inspector', ROOT / 'tools/inspect-producer-fence.py')
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)
spec = importlib.util.spec_from_file_location('framework_api', ROOT / 'tools/compare-framework-api.py')
api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(api)
PRODUCT = p.PROJECT / 'out/aosp-10/target/product/PICOA8110'
PINS = {64: '1f558c16d89065d6e07e3202431c3ce73ab9ef710eac31117fd152976e71f1cd',
        32: 'deccb4b074459d2282f0a9cba144dc0934f32a79ee2455b99af2536f2b06bc47'}
CHECKS64 = [(0x11ec38, '820000b4'), (0x11ec48, '600300b4'),
            (0x11ec50, 'fcf50294'), (0x11ec58, 'e80200b4'),
            (0x11ec84, '087d40f9'), (0x11ec88, '00013fd6')]


def native_entry(elf):
    data = elf.data
    pos = data.index(b'nativeFreezeSelfListening\0')
    address = next(s['p_vaddr'] + pos - s['p_offset'] for s in elf.segments
                   if s['p_offset'] <= pos < s['p_offset'] + s['p_filesz'])
    entries = []
    for slot, value in elf.pointers.items():
        if value['address'] != address:
            continue
        signature = elf.pointer(slot + elf.width)['address']
        start = elf.file_offset(signature)
        text = data[start:data.index(b'\0', start)].decode()
        entries.append({'table_slot': hex(slot), 'signature': text,
                        'function': elf.pointer(slot + 2 * elf.width)['address']})
    if len(entries) != 1 or entries[0]['signature'] != '(J)V':
        raise RuntimeError('Surface freeze JNI entry is missing or ambiguous')
    return entries[0]


def relevant_dex(jar, label):
    work = ROOT / 'reports/framework-bridge/surface-freeze-dexchecks'
    work.mkdir(exist_ok=True)
    tool = p.host_path(p.PROJECT / 'out/aosp-10/host/windows-x86/bin/dexdumps.exe')
    blocks = []
    clazz = ''
    method = ''
    current = []

    def flush():
        if clazz in ['Landroid/view/Surface;', 'Landroid/hardware/display/VirtualDisplay;'] and \
                method in ['registerFreezeSelf', 'nativeFreezeSelfListening', '<init>', 'setSurface']:
            blocks.append({'class': clazz, 'method': method, 'dump': '\n'.join(current)})

    with zipfile.ZipFile(jar) as archive:
        for name in archive.namelist():
            if not name.endswith('.dex'):
                continue
            path = work / (label + '-' + Path(name).name)
            path.write_bytes(archive.read(name))
            proc = subprocess.Popen([str(tool), '-d', str(path)], stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace')
            for line in proc.stdout:
                if 'Class descriptor' in line:
                    flush()
                    clazz = line.split("'")[1]
                    method, current = '', []
                if re.match(r'\s*#\d+\s+: \(in ', line):
                    flush()
                    method, current = '', []
                if re.match(r'\s*name\s+:', line):
                    method = line.split("'")[1]
                current.append(line.rstrip())
            error = proc.stderr.read()
            if proc.wait():
                raise RuntimeError('ART DEX dump failed: ' + error[:1000])
            flush()
            method, current = '', []
    return blocks


def main():
    factory_jar = ROOT / 'reports/device/static/system__framework__framework.jar'
    source_jar = p.host_path(PRODUCT / 'system/framework/framework.jar')
    source_api = api.jar_api(source_jar)['Landroid/view/Surface;']['methods']
    if source_api.get('registerFreezeSelf()V') != 1 or source_api.get('nativeFreezeSelfListening(J)V') != 0x10a:
        raise RuntimeError('Compiled Surface Java declaration differs')
    java = []
    for label, jar in [('factory', factory_jar), ('source', source_jar)]:
        blocks = relevant_dex(jar, label)
        wrapper = next(b for b in blocks if b['class'] == 'Landroid/view/Surface;' and b['method'] == 'registerFreezeSelf')
        if 'Surface;.nativeFreezeSelfListening:(J)V' not in wrapper['dump']:
            raise RuntimeError('Surface wrapper does not call the native entry')
        callers = [b for b in blocks if b['class'] == 'Landroid/hardware/display/VirtualDisplay;' and
                   b['method'] in ['<init>', 'setSurface'] and 'Surface;.registerFreezeSelf:()V' in b['dump']]
        if sorted(b['method'] for b in callers) != ['<init>', 'setSurface']:
            raise RuntimeError('VirtualDisplay caller integration differs')
        if label == 'source' and ('monitor-enter' not in wrapper['dump'] or 'monitor-exit' not in wrapper['dump']):
            raise RuntimeError('Source wrapper is missing release synchronization')
        if 'GREYLIST)' not in wrapper['dump']:
            raise RuntimeError('Compiled public wrapper is not in hidden-api greylist')
        java.append({'kind': label, 'jar_sha256': hashlib.sha256(jar.read_bytes()).hexdigest(),
                     'wrapper_signature': '()V', 'native_signature': '(J)V',
                     'virtual_display_callers': sorted(b['method'] for b in callers),
                     'release_synchronization_present': 'monitor-enter' in wrapper['dump'],
                     'greylist_verified': True})
    native = []
    for bits, directory in [(64, 'lib64'), (32, 'lib')]:
        data = p.host_path(p.PROJECT / ('analysis/stock-5.13.7-system/root/system/' + directory + '/libandroid_runtime.so')).read_bytes()
        if hashlib.sha256(data).hexdigest() != PINS[bits]:
            raise RuntimeError('Wrong factory runtime')
        factory = p.pointers.ElfPointers(data)
        if bits == 64:
            for address, expected in CHECKS64:
                start = factory.file_offset(address, 4)
                if data[start:start + 4].hex() != expected:
                    raise RuntimeError('Factory JNI instruction changed at ' + hex(address))
        source_data = p.host_path(PRODUCT / ('symbols/system/' + directory + '/libandroid_runtime.so')).read_bytes()
        source = p.pointers.ElfPointers(source_data)
        entry = native_entry(source)
        aliases = p.aliases(source).get(entry['function'], set())
        if not any('surfaceFreezeSelfListening' in name and 'picomisu' in name for name in aliases):
            raise RuntimeError('Registered JNI function is not the compiled actual bridge source')
        native.append({'abi': bits, 'factory_sha256': PINS[bits],
                       'source_symbols_sha256': hashlib.sha256(source_data).hexdigest(),
                       'factory_entry': native_entry(factory), 'source_entry': entry,
                       'actual_bridge_registered': True})
    runtime_qualified = False
    runtime_evidence = None
    for relative in ['validation/framework-boot-image.json', 'validation/framework-runtime.json']:
        runtime_path = ROOT / relative
        if not runtime_path.is_file():
            continue
        runtime = json.loads(runtime_path.read_text())
        runtime_qualified = (runtime.get('java_execution_with_source_boot_classpath_qualified') is True
                             and runtime.get('java_fixtures_per_abi') in
                                 [{'arm64': 9, 'arm': 9}, {'arm64': 12, 'arm': 12}]
                             and runtime.get('framework_jar_sha256') == java[1]['jar_sha256'])
        for abi, directory in [('arm64', 'lib64'), ('arm', 'lib')]:
            for name in ['libandroid_runtime.so', 'libgui.so', 'libbinder.so']:
                digest = hashlib.sha256(p.host_path(PRODUCT / ('system/' + directory + '/' + name)).read_bytes()).hexdigest()
                runtime_qualified &= runtime.get('native_sha256', {}).get(abi, {}).get(name) == digest
        if runtime_qualified:
            runtime_evidence = relative
            break
    result = {'java': java, 'native': native,
              'factory_arm64_instructions': [{'address': hex(a), 'bytes': b} for a, b in CHECKS64],
              'java_execution_with_source_boot_classpath_qualified': bool(runtime_qualified),
              'runtime_execution_evidence': runtime_evidence,
              'real_process_freeze_qualified': False, 'full_runtime_abi_proven': False}
    (ROOT / 'validation/surface-freeze-compiled.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print('Compiled Surface Java/greylist, both VirtualDisplay callers and both-ABI JNI table entries verified')


if __name__ == '__main__':
    main()
