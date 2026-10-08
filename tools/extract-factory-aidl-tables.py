"""Extract factory AIDL transaction tables (code -> method signature) for fixture generation.

Usage: python tools/extract-factory-aidl-tables.py --out <tables.json> <interface>...
The output has the reconstruction.json shape used by generate-pico-api-fixture.py.
"""
import argparse
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('pico_aidl', ROOT / 'tools/reconstruct-pico-aidl.py')
aidl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(aidl)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--explicit-ids', nargs='*', default=[],
                        help='interfaces declared with explicit transaction ids (codes may have gaps)')
    parser.add_argument('interfaces', nargs='+')
    args = parser.parse_args()
    classes = aidl.dump_classes(aidl.JARS['framework.jar'])
    result = {}
    for interface in args.interfaces:
        proxy = classes['L' + interface.replace('.', '/') + '$Stub$Proxy;']
        info = aidl.analyze_proxy(proxy)
        codes = sorted(e['code'] for e in info)
        if codes != list(range(1, len(codes) + 1)) and interface not in args.explicit_ids:
            raise RuntimeError('Non-contiguous transaction codes in ' + interface)
        result[interface] = {'jar': 'framework.jar', 'methods': len(info),
                             'transactions': {e['name']: e['code'] for e in info},
                             'signatures': {str(e['code']): e['name'] + e['signature'] for e in info},
                             'oneway': sorted(e['name'] for e in info if e['oneway'])}
    args.out.write_text(json.dumps(result, indent=1) + '\n', newline='\n')
    print({k: v['methods'] for k, v in result.items()})


if __name__ == '__main__':
    main()
