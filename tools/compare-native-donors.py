"""Compare pinned public libgui sources with API markers observed in PICO.

Checks definitions and selected signature shapes, not compiled ABI or behavior.
Uses a separate bare research repository; never changes the AOSP build tree.
"""
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PROJECT = Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro')
REPO = PROJECT / 'analysis/qualcomm-reference/native.git'

FEATURES = [
    ('discarded_buffers', 'BnProducerListener::onBuffersDiscarded',
     ['IProducerListener.cpp'], r'BnProducerListener::onBuffersDiscarded\s*\(\s*const\s+std::vector<int32_t>\s*&'),
    ('release_with_fence', 'BnProducerListener::onBufferReleasedWithFence',
     ['IProducerListener.cpp'], r'BnProducerListener::onBufferReleasedWithFence\s*\('),
    ('display_config_events', 'DisplayEventReceiver(VsyncSource, ConfigChanged)',
     ['DisplayEventReceiver.cpp'], r'DisplayEventReceiver::DisplayEventReceiver\s*\([^)]*ISurfaceComposer::ConfigChanged'),
    ('surface_listener_connect', 'Surface::connect with SurfaceListener',
     ['Surface.cpp'], r'Surface::connect\s*\([^)]*const\s+sp<\s*SurfaceListener\s*>\s*&'),
    ('attach_with_dataspace', 'Surface::attachAndQueueBufferWithDataspace',
     ['Surface.cpp'], r'Surface::attachAndQueueBufferWithDataspace\s*\([^)]*Dataspace'),
    ('display_flags', 'Transaction::setDisplayFlags',
     ['SurfaceComposerClient.cpp'], r'Transaction::setDisplayFlags\s*\('),
    ('latch_acquire_slot', 'ConsumerBase::getLatchAcquireSlotLocked',
     ['ConsumerBase.cpp', 'include/gui/ConsumerBase.h'], r'getLatchAcquireSlotLocked\s*\('),
    ('egl_image_tracker', 'DebugEGLImageTracker::getInstance',
     ['DebugEGLImageTracker.cpp'], r'DebugEGLImageTracker::getInstance\s*\('),
    ('vps_extension', 'SurfaceControl::VpsExtension',
     ['SurfaceControl.cpp'], r'SurfaceControl::VpsExtension::VpsExtension\s*\('),
    ('surface_monitor', 'SurfaceMonitor',
     ['SurfaceMonitor.cpp', 'include/gui/SurfaceMonitor.h'], r'(?:class\s+SurfaceMonitor\b|SurfaceMonitor::SurfaceMonitor\s*\()'),
    ('surface_client', 'SurfaceClient',
     ['SurfaceClient.cpp', 'include/gui/SurfaceClient.h'], r'(?:class\s+SurfaceClient\b|SurfaceClient::SurfaceClient\s*\()'),
    ('virtual_display_listener', 'VirtualDisplayProducerListener',
     ['IProducerListener.cpp', 'include/gui/IProducerListener.h'], r'class\s+VirtualDisplayProducerListener\b'),
    ('producer_vr_query', 'Producer QUERY 10000',
     ['BufferQueueProducer.cpp'], r'(?:case\s+10000\s*:|kPicoQuerySetPvrStatus)'),
    ('consumer_private_config', 'Consumer transaction 10000',
     ['BufferQueueConsumer.cpp'], r'(?:case\s+10000\s*:|kPicoConsumerConfiguration)'),
]
SOURCES = [
    ('aosp_10_r47', 'refs/research/aosp-r47', 'https://android.googlesource.com/platform/frameworks/native'),
    ('aosp_10_qpr3', 'refs/research/aosp-qpr3', 'https://android.googlesource.com/platform/frameworks/native'),
    ('qualcomm_q', 'refs/research/qualcomm-q', 'https://git.codelinaro.org/clo/la/platform/frameworks/native.git'),
    ('aosp_11_r1', 'refs/research/aosp-r1', 'https://android.googlesource.com/platform/frameworks/native'),
]


def git(*args):
    return subprocess.check_output(['git', '-C', str(REPO), *args], text=True)


def without_comments(text):
    text = re.sub(r'/\*.*?\*/', lambda match: '\n' * match.group().count('\n'), text, flags=re.S)
    return re.sub(r'//[^\n]*', '', text)


def main():
    mounted = subprocess.check_output(['findmnt', '-n', '-o', 'FSTYPE,UUID', '--target', str(PROJECT)], text=True).split()
    if mounted != ['ext4', 'a00da05f-1eb2-44b6-99f0-9109391f67dc']:
        raise RuntimeError('Expected ext4 research volume')
    results = []
    for name, ref, remote in SOURCES:
        commit = git('rev-parse', ref + '^{commit}').strip()
        paths = set(git('ls-tree', '-r', '--name-only', commit, 'libs/gui').splitlines())
        texts = {}
        features = {}
        for key, label, filenames, pattern in FEATURES:
            hits = []
            for filename in filenames:
                path = 'libs/gui/' + filename
                if path not in paths:
                    continue
                if path not in texts:
                    texts[path] = git('show', commit + ':' + path)
                text = without_comments(texts[path])
                match = re.search(pattern, text, re.S)
                if match:
                    hits.append({'path': path, 'line': text[:match.start()].count('\n') + 1,
                                 'source_file_sha256': hashlib.sha256(texts[path].encode()).hexdigest()})
            features[key] = {'label': label, 'found': bool(hits), 'evidence': hits}
        results.append({'name': name, 'repository': remote, 'commit': commit,
                        'commit_date': git('log', '-1', '--format=%cI', commit).strip(),
                        'features': features,
                        'matched_api_markers': sum(value['found'] for value in features.values()),
                        'marker_count': len(FEATURES), 'full_abi_compatibility_proven': False})
    pairs = [('aosp_10_r47', 'qualcomm_q'), ('aosp_10_qpr3', 'qualcomm_q')]
    by_name = {row['name']: row for row in results}
    differences = {}
    for left, right in pairs:
        differences[left + '..' + right] = {
            'libgui_numstat': git('diff', '--numstat', by_name[left]['commit'], by_name[right]['commit'], '--', 'libs/gui').splitlines(),
            'bufferitem_cpp_identical': not git('diff', by_name[left]['commit'], by_name[right]['commit'], '--', 'libs/gui/BufferItem.cpp'),
        }
    refs_file = REPO.parent / 'native-refs.txt'
    aliases = [line.split('\t')[1] for line in refs_file.read_text().splitlines()
               if line.startswith(by_name['qualcomm_q']['commit'] + '\t')
               and 'LA.UM.8.12.c3-' in line]
    report = {'sources': results, 'differences': differences,
              'qualcomm_same_commit_tag_refs': aliases,
              'scope': 'Selected source API definitions and signature shapes; no candidate ABI rebuild',
              'pico_evidence': ['validation/libgui-abi.json', 'reports/framework-bridge/producer-protocol.json',
                                'reports/framework-bridge/bufferqueue-status-references.json'],
              'build_tree_modified': False, 'headset_modified': False}
    (ROOT / 'reports/framework-bridge/native-source-comparison.json').write_text(json.dumps(report, indent=2) + '\n')
    (ROOT / 'validation/native-source-comparison.json').write_text(json.dumps(report, indent=2) + '\n')
    for row in results:
        print(row['name'] + ': ' + str(row['matched_api_markers']) + '/' + str(row['marker_count']))
        print('  ' + ', '.join(key for key, value in row['features'].items() if value['found']))


if __name__ == '__main__':
    main()
