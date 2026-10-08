"""Combine compare-pico-api.py --only reports into one validation file with explanations.

Usage: python tools/record-member-comparisons.py --out <validation.json> --explanations <json>
         --report <label>=<compare.json> ... [--wire <wire-report.json>] [--attach <key>=<evidence.json>]
Every class with differences must have an explanation (class descriptor key) or the tool fails.
"""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--explanations', type=Path, required=True)
    parser.add_argument('--report', action='append', required=True)
    parser.add_argument('--wire', type=Path)
    parser.add_argument('--attach', action='append', default=[],
                        help='<key>=<json>: embed further evidence (e.g. check-hidl-wire.py output); '
                        'a report with a non-empty "problems" list fails')
    parser.add_argument('--title', default='')
    args = parser.parse_args()
    explanations = json.loads(args.explanations.read_text(encoding='utf-8'))
    result = {'title': args.title, 'static': {}, 'unexplained': []}
    for item in args.report:
        label, path = item.split('=', 1)
        data = json.loads(Path(path).read_text())
        different = {}
        for row in data['rows']:
            if row['differences']:
                reason = explanations.get(row['class'])
                if reason is None:
                    result['unexplained'].append(label + ':' + row['class'])
                different[row['class']] = reason or row['differences']
        result['static'][label] = {'classes': data['classes'], 'identical': data['identical'],
                                   'explained_differences': different}
    if args.wire:
        wire = json.loads(args.wire.read_text(encoding='utf-8'))
        result['wire'] = {k: wire[k] for k in ('fixture', 'package', 'factory_framework_sha256',
                                                'source_framework_sha256', 'probe_sha256', 'interfaces',
                                                'unexpected_differences', 'factory_run')}
        result['wire']['comparison'] = {abi: {k: v for k, v in c.items() if k != 'mismatched'}
                                        for abi, c in wire['comparison'].items()}
    for item in args.attach:
        key, path = item.split('=', 1)
        result[key] = json.loads(Path(path).read_text(encoding='utf-8'))
        if result[key].get('problems'):
            result['unexplained'].append(key + ':' + ', '.join(result[key]['problems']))
    config = json.loads((ROOT / 'config/aosp-patches.json').read_text())
    result['component_commits'] = {p['path']: p['local_commit'] for p in config['projects']}
    result['system_partitions_modified'] = False
    args.out.write_text(json.dumps(result, indent=1, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps({k: (v['classes'], v['identical']) for k, v in result['static'].items()}))
    if result['unexplained']:
        print('unexplained:', result['unexplained'])
        raise SystemExit(1)


if __name__ == '__main__':
    main()
