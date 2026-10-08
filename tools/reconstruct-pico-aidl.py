"""Reconstruct PICO AIDL interface definitions from factory 5.13.7 DEX.

Reads the generated Stub/Stub$Proxy classes of the authenticated factory framework.jar
and services.jar and writes .aidl files whose declaration order reproduces the factory
transaction codes. From each Proxy method: arguments written before transact() are "in",
arguments read back afterwards "out", both "inout"; transact flag 1 means "oneway";
parameter names come from the Proxy debug information. Typed-list element classes come
from the Stub unmarshalling. compare-pico-api.py compares the generated Java with the
factory DEX. Run on the Windows host: python tools/reconstruct-pico-aidl.py --out <dir>
"""
import argparse
import json
from pathlib import Path
import re
import subprocess
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
# The Windows host dexdumps understands the factory hidden-API map item (0xf000).
DEXDUMP = Path(r'\\wsl.localhost\Ubuntu-24.04\mnt\wsl\PHYSICALDRIVE5p3\home\red_panda\RedPandaAndroid'
               r'\pico4-pro\out\aosp-10\host\windows-x86\bin\dexdumps.exe')
JARS = {'framework.jar': ROOT / 'reports/device/static/system__framework__framework.jar',
        'services.jar': ROOT / 'reports/device/static/system__framework__services.jar'}
INTERFACES = {
    'framework.jar': ['com.pvr.IPvrManagerService', 'com.pvr.IPvrCallback', 'com.pvr.IPvrCallbackNative',
                      'com.pvr.ISysDataSyncService', 'com.pvr.configuration.IConfigServiceInterface',
                      'com.pico.api.app.IApiLayer', 'com.pico.api.app.IAppSession',
                      'com.pxr.pxrapi.IScreenCaptureInterface', 'com.pxr.net.IPxrNetworkManager',
                      'com.pxr.net.INetworkQualityListener', 'com.pxr.net.ILinkLayerQualityListener',
                      'com.pxr.bluetooth.IBluetoothPxr', 'com.pxr.bluetooth.IBluetoothPxrDeviceCallback'],
    'services.jar': ['com.pvr.pxrnotification.aidl.IPxrNotificationService',
                     'com.pvr.pxrnotification.aidl.IPxrNotificationCallback'],
}
PRIMITIVE = {'I': 'int', 'Z': 'boolean', 'J': 'long', 'F': 'float', 'D': 'double', 'B': 'byte',
             'C': 'char', 'S': 'short', 'V': 'void'}


def split_params(signature):
    return re.findall(r'\[*(?:[IZJFDBCS]|L[^;]+;)', re.match(r'\((.*)\)', signature).group(1))


def simple_type(descriptor):
    dims = len(descriptor) - len(descriptor.lstrip('['))
    base = descriptor[dims:]
    name = PRIMITIVE.get(base) or base[1:-1].split('/')[-1].replace('$', '.')
    return name + '[]' * dims


def dump_classes(jar):
    """Return {descriptor: dexdump text} for all classes of a JAR."""
    result = {}
    with zipfile.ZipFile(jar) as archive, tempfile.TemporaryDirectory() as tmp:
        for name in sorted(n for n in archive.namelist() if re.fullmatch(r'classes\d*\.dex', n)):
            path = Path(tmp) / name
            path.write_bytes(archive.read(name))
            text = subprocess.run([str(DEXDUMP), '-d', str(path)], capture_output=True,
                                  text=True, errors='replace').stdout
            for block in re.split(r'\n(?=Class #\d+)', text):
                match = re.search(r"Class descriptor  : '([^']+)'", block)
                if match:
                    result[match.group(1)] = block
    return result


def members(block):
    return re.split(r'\n(?=    #\d+\s+: \(in )', block)


def methods(block):
    """Yield (name, signature, registers, ins, code lines, {register: local name})."""
    for part in members(block):
        name = re.search(r"name          : '([^']+)'", part)
        sig = re.search(r"type          : '([^']+)'", part)
        if not name or not sig or '(' not in sig.group(1):
            continue
        regs = re.search(r'registers     : (\d+)', part)
        ins = re.search(r'ins           : (\d+)', part)
        code = [line for _, line in re.findall(r'\|([0-9a-f]{4}): (.*)$', part, re.MULTILINE)]
        names = {int(r): n for r, n in re.findall(r'reg=(\d+) (\S+) \S+', part)}
        yield (name.group(1), sig.group(1), int(regs.group(1)) if regs else 0,
               int(ins.group(1)) if ins else 0, code, names)


def constants(block):
    """static final interface constants with their dexdump values."""
    for part in members(block):
        name = re.search(r"name          : '([^']+)'", part)
        sig = re.search(r"type          : '([^']+)'", part)
        value = re.search(r'value         : (.*)$', part, re.MULTILINE)
        access = re.search(r'access        : (0x[0-9a-f]+)', part)
        if name and sig and value and '(' not in sig.group(1) and int(access.group(1), 16) & 0x18 == 0x18:
            yield name.group(1), sig.group(1), value.group(1)


def analyze_proxy(block):
    """Per interface method: transaction code, oneway, directions, kinds and names."""
    result = []
    for name, signature, registers, ins, code, names in methods(block):
        if name.startswith('<') or name in ('asBinder', 'getInterfaceDescriptor'):
            continue
        transact = next(i for i, line in enumerate(code) if 'IBinder;.transact:' in line)
        consts = {}
        for line in code[:transact]:
            match = re.match(r'const(?:/4|/16)? (v\d+), #int (-?\d+)', line)
            if match:
                consts[match.group(1)] = int(match.group(2))
        call = re.search(r'\{v\d+, (v\d+), v\d+, v\d+, (v\d+)\}', code[transact])
        reg = registers - ins + 1
        params = []
        for param in split_params(signature):
            token = re.compile(r'[{ ]v%d[,}]' % reg)
            before = [line for line in code[:transact] if token.search(line)]
            after = [line for line in code[transact:] if token.search(line) and 'getDefaultImpl' not in line
                     and ';.' + name + ':' not in line]
            wrote = any('Parcel;.write' in line or 'writeToParcel' in line or '.asBinder:' in line
                        or line.startswith('if-eqz') for line in before)
            read = any('Parcel;.read' in line or 'readFromParcel' in line for line in after)
            element = None
            if param == 'Ljava/util/List;':
                joined = '\n'.join(before + after)
                element = ('String' if 'StringList' in joined else 'IBinder' if 'BinderList' in joined
                           else 'TYPED' if 'TypedList' in joined else None)
            params.append({'descriptor': param, 'name': names.get(reg, 'arg%d' % len(params)),
                           'direction': 'inout' if wrote and read else 'out' if read else 'in',
                           'interface': any('.asBinder:' in line for line in before), 'element': element})
            reg += 2 if param in ('J', 'D') else 1
        result.append({'name': name, 'signature': signature, 'code': consts[call.group(1)],
                       'oneway': consts[call.group(2)] == 1, 'params': params})
    return result


def typed_list_elements(stub_block):
    """CREATOR classes used by Stub.onTransact, in code (= transaction) order."""
    for name, _, _, _, code, _ in methods(stub_block):
        if name == 'onTransact':
            return [m.group(1) for m in (re.search(r'sget-object v\d+, (L[^;]+;)\.CREATOR', line)
                                         for line in code) if m]
    return []


def render(interface, info, fixed, public):
    package, simple = interface.rsplit('.', 1)
    imports = set()
    for entry in info:
        for param in split_params(entry['signature']) + [entry['signature'].split(')')[1]]:
            base = param.lstrip('[')
            if base.startswith('L') and not base.startswith(('Ljava/lang/', 'Ljava/util/')):
                # The Android 10 aidl compiler also needs imports for same-package types.
                imports.add(base[1:-1].replace('/', '.').replace('$', '.'))
    lines = ['// Copyright 2026 Picomisu contributors', '// SPDX-License-Identifier: Apache-2.0',
             '// Reconstructed from the factory PICO OS 5.13.7 DEX by tools/reconstruct-pico-aidl.py.',
             'package ' + package + ';', '']
    for entry in info:
        for param in entry['params']:
            if param['element'] and param['element'] not in ('String', 'IBinder'):
                imports.add(param['element_class'])
    lines += ['import ' + name + ';' for name in sorted(imports)] + ([''] if imports else [])
    if not public:
        lines.append('/** @hide */')
    lines.append('interface ' + simple + ' {')
    for name, signature, value in fixed:
        lines.append('    const %s %s = %s;' % (simple_type(signature), name, value))
    for entry in sorted(info, key=lambda e: e['code']):
        rendered = []
        for param in entry['params']:
            descriptor = param['descriptor']
            type_name = simple_type(descriptor)
            if param['element']:
                type_name = 'List<%s>' % param['element']
            # AIDL takes a direction only for arrays, parcelables and containers.
            directional = descriptor.startswith('[') or (
                descriptor.startswith('L') and not param['interface']
                and descriptor not in ('Ljava/lang/String;', 'Landroid/os/IBinder;'))
            rendered.append((param['direction'] + ' ' if directional else '') + type_name + ' '
                            + param['name'])
        head = ('oneway ' if entry['oneway'] else '') + simple_type(entry['signature'].split(')')[1])
        lines.append('    %s %s(%s);' % (head, entry['name'], ', '.join(rendered)))
    lines.append('}')
    return '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--public', nargs='*', default=[], help='Interfaces whitelisted in the factory')
    args = parser.parse_args()
    report = {}
    for jar, interfaces in INTERFACES.items():
        classes = dump_classes(JARS[jar])
        for interface in interfaces:
            descriptor = 'L' + interface.replace('.', '/') + ';'
            stub = classes[descriptor[:-1] + '$Stub;']
            info = analyze_proxy(classes[descriptor[:-1] + '$Stub$Proxy;'])
            codes = sorted(e['code'] for e in info)
            if codes != list(range(1, len(codes) + 1)):
                raise RuntimeError('Non-contiguous transaction codes in ' + interface + ': ' + str(codes))
            elements = iter(typed_list_elements(stub))
            for entry in sorted(info, key=lambda e: e['code']):
                for param in entry['params']:
                    if param['element'] == 'TYPED':
                        element = next(elements)
                        param['element'] = simple_type(element)
                        param['element_class'] = element[1:-1].replace('/', '.').replace('$', '.')
            text = render(interface, info, list(constants(classes[descriptor])), interface in args.public)
            target = args.out / (interface.replace('.', '/') + '.aidl')
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, newline='\n')
            report[interface] = {'jar': jar, 'methods': len(info),
                                 'transactions': {e['name']: e['code'] for e in info},
                                 'signatures': {str(e['code']): e['name'] + e['signature'] for e in info},
                                 'oneway': sorted(e['name'] for e in info if e['oneway']),
                                 'non_in_parameters': sorted(e['name'] + '.' + p['name'] for e in info
                                                             for p in e['params'] if p['direction'] != 'in')}
    (args.out / 'reconstruction.json').write_text(json.dumps(report, indent=1) + '\n')
    print(json.dumps({k: v['methods'] for k, v in report.items()}))


if __name__ == '__main__':
    main()
