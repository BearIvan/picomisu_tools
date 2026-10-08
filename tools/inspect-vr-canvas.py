"""Inspect the PICO Surface extension DEX contract and both-ABI JNI tables."""
import hashlib
import importlib.util
import io
import json
import lzma
from pathlib import Path

from elftools.elf.elffile import ELFFile
from elftools.elf.sections import SymbolTableSection

ROOT = Path(__file__).resolve().parents[1]


def module(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'tools' / file)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


p = module('pico_elf', 'inspect-producer-fence.py')
api = module('pico_api', 'compare-framework-api.py')
METHODS = {'nativeLockCanvasFor2DVr': '(JLandroid/graphics/Canvas;)J',
           'nativeUnlockCanvasAndPostFor2DVr': '(JLandroid/graphics/Canvas;)V',
           'nativeReleaseSurfaceObject': '(J)V'}
FACTORY = {'arm64': '1f558c16d89065d6e07e3202431c3ce73ab9ef710eac31117fd152976e71f1cd',
           'arm': 'deccb4b074459d2282f0a9cba144dc0934f32a79ee2455b99af2536f2b06bc47'}
JAR_HASH = 'ea5998f856b692f8cd112b26d65e6a4f371dca825348bf5b247eabc56274ed0e'


def cstring(elf, address):
    try:
        offset = elf.file_offset(address)
    except ValueError:
        # Relocated pointers also reference BSS and other non-file-backed data.
        return None
    if offset is None:
        return None
    end = elf.data.find(b'\0', offset, offset + 256)
    if end < 0:
        return None
    return elf.data[offset:end].decode('ascii', errors='replace')


def functions(elf):
    sources = [elf.elf]
    section = elf.elf.get_section_by_name('.gnu_debugdata')
    if section is not None:
        sources.append(ELFFile(io.BytesIO(lzma.decompress(section.data()))))
    found = {}
    for source in sources:
        for section in source.iter_sections():
            if not isinstance(section, SymbolTableSection):
                continue
            for symbol in section.iter_symbols():
                if symbol.entry.st_info.type == 'STT_FUNC' and symbol.entry.st_size:
                    found[symbol.entry.st_value & ~1] = symbol.entry.st_size
    return found


def entries(path):
    data = path.read_bytes()
    elf = p.pointers.ElfPointers(data)
    sizes = functions(elf)
    found = {}
    for slot in elf.pointers:
        pointer = elf.pointer(slot)
        if pointer['address'] is None:
            continue
        name = cstring(elf, pointer['address'])
        if name not in METHODS:
            continue
        descriptor = elf.pointer(slot + elf.width)
        routine = elf.pointer(slot + 2 * elf.width)
        if descriptor['address'] is None or routine['address'] is None:
            continue
        text = cstring(elf, descriptor['address'])
        start = routine['address'] & ~1
        size = sizes.get(start)
        if not text or not text.startswith('(') or not size:
            continue
        offset = elf.file_offset(start, size)
        if offset is None:
            continue
        if name in found:
            raise RuntimeError('Ambiguous JNI entry: ' + name)
        found[name] = {'descriptor': text, 'table_address': hex(slot),
                       'function_address': hex(routine['address']), 'function_bytes': size,
                       'function_sha256': hashlib.sha256(data[offset:offset + size]).hexdigest()}
    if set(found) != set(METHODS):
        raise RuntimeError('Incomplete JNI table: ' + str(path))
    return hashlib.sha256(data).hexdigest(), found


def main():
    factory_jar = ROOT / 'reports/device/static/system__framework__framework.jar'
    if hashlib.sha256(factory_jar.read_bytes()).hexdigest() != JAR_HASH:
        raise RuntimeError('Factory framework is not the authenticated 5.13.7 JAR')
    source_jar = p.host_path(p.PROJECT / 'out/aosp-10/target/product/PICOA8110/system/framework/framework.jar')
    factory = api.jar_api(factory_jar)
    source = api.jar_api(source_jar)
    classes = ('Lcom/pico/util/IExtBase;', 'Landroid/view/IExtSurface;', 'Landroid/view/ExtSurfaceImpl;')
    declarations = {}
    for clazz in classes:
        if clazz not in source or source[clazz]['methods'] != factory[clazz]['methods']:
            raise RuntimeError('Extension method descriptors/access differ: ' + clazz)
        declarations[clazz] = sorted(source[clazz]['methods'])
    if 'getExt()Landroid/view/IExtSurface;' not in source['Landroid/view/Surface;']['methods']:
        raise RuntimeError('Source Surface.getExt is missing')
    abis = {}
    for abi, directory in (('arm64', 'lib64'), ('arm', 'lib')):
        factory_path = ROOT / 'reports/device/native' / ('system__' + directory + '__libandroid_runtime.so')
        source_path = p.host_path(p.PROJECT / 'out/aosp-10/target/product/PICOA8110/system' / directory / 'libandroid_runtime.so')
        factory_hash, old = entries(factory_path)
        source_hash, new = entries(source_path)
        if factory_hash != FACTORY[abi]:
            raise RuntimeError('Factory runtime hash mismatch: ' + abi)
        if any(new[name]['descriptor'] != descriptor for name, descriptor in METHODS.items()):
            raise RuntimeError('Source JNI does not match the factory DEX contract')
        abis[abi] = {'factory_sha256': factory_hash, 'source_sha256': source_hash,
                     'factory_entries': old, 'source_entries': new,
                     'factory_lock_table_matches_dex': old['nativeLockCanvasFor2DVr']['descriptor'] == METHODS['nativeLockCanvasFor2DVr'],
                     'factory_registration_flow_proven': False}
    result = {'factory_framework_sha256': JAR_HASH,
              'source_framework_sha256': hashlib.sha256(source_jar.read_bytes()).hexdigest(),
              'extension_methods': declarations, 'abis': abis,
              'factory_arm64_bitmap': {'width': 1, 'height': 1, 'color_type': 4, 'alpha_type': 1,
                                       'malloc_bytes': 1, 'row_bytes': 4},
              'source_pixel_storage': 'Owned SkBitmap pixels for each canvas; a full RGBA pixel',
              'factory_pixel_storage_equivalence_proven': False,
              'vr_activity_skip_draw_policy_ported': False,
              'scope': 'DEX methods/access and compiled JNI entries; factory ARM64 canvas shape/allocation '
                       'from inspected code; Source ownership/allocation differs; '
                       'does not qualify ActivityInfo policy, ViewRoot routing or hardware VR'}
    (ROOT / 'validation/vr-canvas-api.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print('PICO extension method declarations and both-ABI Source JNI tables match the DEX contract')


if __name__ == '__main__':
    main()
