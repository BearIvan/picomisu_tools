"""Generate the PICO API runtime fixture from the reconstructed AIDL transactions.

The generated org.picomisu.runtime.PicoApiFixture runs unchanged on the factory and the
Source framework. For every interface method it drives Stub.asInterface() over a recording
IBinder and prints the transaction code, flags and data-parcel bytes; the recorded data is
then passed to Stub.onTransact() of a generated recording implementation, which prints the
unmarshalled arguments and the reply bytes. Parcelable classes are round-tripped with
deterministic field values. Usage:
  python tools/generate-pico-api-fixture.py --reconstruction <reconstruction.json> --out <PicoApiFixture.java>
"""
import argparse
import json
from pathlib import Path
import re

PRIMITIVE = {'I': 'int', 'Z': 'boolean', 'J': 'long', 'F': 'float', 'D': 'double', 'B': 'byte',
             'C': 'char', 'S': 'short', 'V': 'void'}
DEFAULTS = {'int': '0', 'boolean': 'false', 'long': '0L', 'float': '0f', 'double': '0d', 'byte': '(byte) 0',
            'char': "'\\0'", 'short': '(short) 0'}
PARCELABLES = ['com.pxr.bluetooth.BluetoothPxrDeviceProperty', 'com.pxr.net.LinkLayerQuality',
               'com.pxr.net.NetworkQuality', 'com.pxr.net.PxrWifiConnectionInfo']


def params(signature):
    return re.findall(r'\[*(?:[IZJFDBCS]|L[^;]+;)', re.match(r'[^(]*\((.*)\)', signature).group(1))


def java(descriptor):
    dims = len(descriptor) - len(descriptor.lstrip('['))
    base = descriptor[dims:]
    return (PRIMITIVE.get(base) or base[1:-1].replace('/', '.').replace('$', '.')) + '[]' * dims


def implementation(interface, entries):
    simple = 'Impl' + interface.split('.')[-1]
    lines = ['    static final class %s extends %s.Stub {' % (simple, interface)]
    for code in sorted(entries, key=int):
        signature = entries[code]
        name = signature[:signature.index('(')]
        returned = java(signature.split(')')[1])
        args = ['%s a%d' % (java(p), i) for i, p in enumerate(params(signature))]
        lines.append('        @Override')
        lines.append('        public %s %s(%s) {' % (returned, name, ', '.join(args)))
        lines.append('            record("%s", new Object[] {%s});' % (
            name, ', '.join('a%d' % i for i in range(len(args)))))
        if returned != 'void':
            lines.append('            return %s;' % DEFAULTS.get(returned, 'null'))
        lines.append('        }')
    lines.append('    }')
    return simple, '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reconstruction', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--class-name', default='PicoApiFixture')
    parser.add_argument('--prefix', default='pico-api', help='output line prefix')
    parser.add_argument('--parcelables', nargs='*', default=PARCELABLES)
    args = parser.parse_args()
    # services.jar interfaces are not on an application boot class path; they are compared
    # statically by compare-pico-api.py --jar services.jar.
    data = {k: v for k, v in json.loads(args.reconstruction.read_text()).items() if v['jar'] == 'framework.jar'}
    impls, registry = [], []
    for interface in sorted(data):
        simple, text = implementation(interface, data[interface]['signatures'])
        impls.append(text)
        registry.append('        {"%s", %s.class, %d},' % (interface, simple, len(data[interface]['signatures'])))
    expected = sum(2 * len(v['signatures']) + 1 for v in data.values()) + 2 * len(args.parcelables)
    template = (Path(__file__).with_name('pico-api-fixture.java.in')).read_text()
    text = (template.replace('@IMPLEMENTATIONS@', '\n\n'.join(impls))
            .replace('@REGISTRY@', '\n'.join(registry))
            .replace('@PARCELABLES@', ', '.join('"%s"' % p for p in args.parcelables))
            .replace('@CLASS@', args.class_name).replace('@PREFIX@', args.prefix)
            .replace('@EXPECTED@', str(expected)))
    args.out.write_text(text, newline='\n')
    print('generated %d interfaces, %d expected lines' % (len(data), expected))


if __name__ == '__main__':
    main()
