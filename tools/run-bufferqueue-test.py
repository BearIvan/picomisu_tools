"""Run isolated BufferQueue tests on the previously verified headset, without flashing."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import uuid

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--adb', required=True)
    parser.add_argument('--serial', help='ADB transport ID, including a Wi-Fi IP:port')
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--expected-tests', type=int, default=6)
    parser.add_argument('--wire-probe', action='store_true')
    parser.add_argument('--fence-probe', action='store_true')
    parser.add_argument('--consumer-fence-probe', action='store_true')
    parser.add_argument('--display-config-probe', action='store_true')
    parser.add_argument('--display-flags-probe', action='store_true')
    parser.add_argument('--egl-image-tracker-probe', action='store_true')
    parser.add_argument('--surface-client-probe', action='store_true')
    parser.add_argument('--pico-composition-tests', action='store_true')
    parser.add_argument('--composition-regression-tests', action='store_true')
    parser.add_argument('--monitored-producer-tests', action='store_true')
    parser.add_argument('--only-monitored-producer-tests', action='store_true')
    parser.add_argument('--dequeue-count-probe', action='store_true')
    parser.add_argument('--cached-buffer-probe', action='store_true')
    parser.add_argument('--freeze-wire-probe', action='store_true')
    parser.add_argument('--freeze-registry-probe', action='store_true')
    parser.add_argument('--freeze-registry-tests', action='store_true')
    parser.add_argument('--frozen-reply-probe', action='store_true')
    parser.add_argument('--freeze-remote-observation', action='store_true',
                        help='Observe factory remote registration with fake service/token and intercepted Binder reads')
    parser.add_argument('--only-freeze-remote-observation', action='store_true')
    parser.add_argument('--producer-freeze-probe', action='store_true')
    parser.add_argument('--binder-parity-probe', action='store_true',
                        help='Compare the factory and Source libbinder PICO/Smartisan fixtures (chunk 6)')
    parser.add_argument('--only-binder-parity-probe', action='store_true')
    parser.add_argument('--pxrguiex-test', action='store_true',
                        help='dlopen the factory libpxrguiex.so against the Source libhwui (chunk 6)')
    parser.add_argument('--surface-freeze-probe', action='store_true')
    parser.add_argument('--only-surface-freeze-probe', action='store_true')
    parser.add_argument('--render-surface-tests', action='store_true')
    parser.add_argument('--layer-fence-tests', action='store_true')
    parser.add_argument('--only-layer-fence-tests', action='store_true')
    parser.add_argument('--virtual-display-fence-tests', action='store_true',
                        help='Also run the VirtualDisplaySurface registry/lifetime tests')
    parser.add_argument('--expected-virtual-display-tests', type=int, default=16)
    parser.add_argument('--expected-render-surface-tests', type=int, default=39)
    parser.add_argument('--expected-consumer-fixtures', type=int, default=3)
    args = parser.parse_args()
    if args.only_monitored_producer_tests:
        if any([args.wire_probe, args.fence_probe, args.consumer_fence_probe,
                args.display_config_probe, args.display_flags_probe,
                args.egl_image_tracker_probe, args.surface_client_probe,
                args.pico_composition_tests, args.composition_regression_tests,
                args.dequeue_count_probe, args.cached_buffer_probe, args.freeze_wire_probe,
                args.freeze_registry_probe, args.freeze_registry_tests, args.frozen_reply_probe,
                args.freeze_remote_observation, args.only_freeze_remote_observation,
                args.producer_freeze_probe, args.surface_freeze_probe, args.only_surface_freeze_probe,
                args.render_surface_tests, args.layer_fence_tests, args.only_layer_fence_tests,
                args.virtual_display_fence_tests]):
            parser.error('--only-monitored-producer-tests cannot be combined with other suites')
        args.monitored_producer_tests = True
    if args.pico_composition_tests or args.composition_regression_tests or args.monitored_producer_tests:
        args.layer_fence_tests = True
    if args.virtual_display_fence_tests:
        args.layer_fence_tests = True
    if args.only_layer_fence_tests:
        if any([args.wire_probe, args.fence_probe, args.consumer_fence_probe,
                args.display_config_probe, args.cached_buffer_probe, args.freeze_wire_probe,
                args.freeze_registry_probe, args.freeze_registry_tests, args.frozen_reply_probe,
                args.freeze_remote_observation, args.only_freeze_remote_observation,
                args.producer_freeze_probe, args.dequeue_count_probe, args.display_flags_probe, args.egl_image_tracker_probe, args.surface_client_probe,
                args.pico_composition_tests, args.composition_regression_tests, args.monitored_producer_tests,
                args.surface_freeze_probe, args.only_surface_freeze_probe,
                args.render_surface_tests]):
            parser.error('--only-layer-fence-tests cannot be combined with other suites')
        args.layer_fence_tests = True
    if args.only_freeze_remote_observation:
        if any([args.wire_probe, args.fence_probe, args.consumer_fence_probe,
                args.display_config_probe, args.cached_buffer_probe, args.freeze_wire_probe,
                args.freeze_registry_probe, args.freeze_registry_tests, args.frozen_reply_probe,
                args.producer_freeze_probe, args.dequeue_count_probe, args.display_flags_probe, args.egl_image_tracker_probe, args.surface_client_probe,
                args.pico_composition_tests, args.composition_regression_tests, args.monitored_producer_tests,
                args.surface_freeze_probe, args.only_surface_freeze_probe,
                args.render_surface_tests, args.layer_fence_tests, args.only_layer_fence_tests]):
            parser.error('--only-freeze-remote-observation cannot be combined with other suites')
        args.freeze_remote_observation = True
    if args.only_surface_freeze_probe:
        if any([args.wire_probe, args.fence_probe, args.consumer_fence_probe,
                args.display_config_probe, args.cached_buffer_probe, args.freeze_wire_probe,
                args.freeze_registry_probe, args.freeze_registry_tests, args.frozen_reply_probe,
                args.producer_freeze_probe, args.dequeue_count_probe, args.display_flags_probe, args.egl_image_tracker_probe, args.surface_client_probe,
                args.pico_composition_tests, args.composition_regression_tests, args.monitored_producer_tests,
                args.freeze_remote_observation, args.only_freeze_remote_observation,
                args.render_surface_tests, args.layer_fence_tests, args.only_layer_fence_tests]):
            parser.error('--only-surface-freeze-probe cannot be combined with other suites')
        args.surface_freeze_probe = True
    if args.only_binder_parity_probe:
        if any([args.wire_probe, args.fence_probe, args.consumer_fence_probe,
                args.display_config_probe, args.cached_buffer_probe, args.freeze_wire_probe,
                args.freeze_registry_probe, args.freeze_registry_tests, args.frozen_reply_probe,
                args.producer_freeze_probe, args.dequeue_count_probe, args.display_flags_probe,
                args.egl_image_tracker_probe, args.surface_client_probe, args.pico_composition_tests,
                args.composition_regression_tests, args.monitored_producer_tests,
                args.freeze_remote_observation, args.only_freeze_remote_observation,
                args.surface_freeze_probe, args.only_surface_freeze_probe,
                args.render_surface_tests, args.layer_fence_tests, args.only_layer_fence_tests]):
            parser.error('--only-binder-parity-probe cannot be combined with other suites')
        args.binder_parity_probe = True
    state = json.loads((ROOT / 'outputs/vr-preview-01-installation/state.json').read_text())
    manifest = json.loads((args.package / 'manifest.json').read_text())
    listing = subprocess.check_output([args.adb, 'devices'], text=True)
    devices = [row.split()[0] for row in listing.splitlines()[1:]
               if len(row.split()) == 2 and row.split()[1] == 'device']
    if args.serial:
        if args.serial not in devices:
            raise RuntimeError('Requested ADB transport is unavailable')
        serial = args.serial
    else:
        verified_usb = [d for d in devices if hashlib.sha256(d.encode()).hexdigest() == state['device_serial_sha256']]
        if len(verified_usb) == 1:
            serial = verified_usb[0]
        elif len(devices) == 1:
            serial = devices[0]
        else:
            raise RuntimeError('Expected previously verified headset; select a transport with --serial')

    def adb(*arguments, timeout=60):
        for attempt in range(3):
            result = subprocess.run([args.adb, '-s', serial, *arguments], capture_output=True,
                                    text=True, timeout=timeout, encoding='utf-8', errors='replace')
            output = (result.stdout + result.stderr).replace(serial, '<device>')
            if not result.returncode:
                return output.strip()
            # These startup failures happen before dispatch; retry only a local
            # command that never reached the device, not arbitrary shell errors.
            daemon_unavailable = ('cannot connect to daemon' in output or
                                  'could not read ok from ADB Server' in output or
                                  'failed to start daemon' in output)
            if not daemon_unavailable or attempt == 2:
                raise RuntimeError(output)
            subprocess.run([args.adb, 'start-server'], capture_output=True,
                           text=True, timeout=20, encoding='utf-8', errors='replace')

    identity = subprocess.run([args.adb, '-s', serial, 'shell', 'getprop ro.serialno'],
                              capture_output=True, text=True, timeout=20)
    if identity.returncode:
        raise RuntimeError('Cannot verify hardware identity')
    hardware_serial = identity.stdout.strip()
    if hashlib.sha256(hardware_serial.encode()).hexdigest() != state['device_serial_sha256']:
        raise RuntimeError('Hardware identity differs from previously verified headset')
    if adb('shell', 'getprop ro.product.device') != 'PICOA8110':
        raise RuntimeError('Wrong model')
    fingerprint = adb('shell', 'getprop ro.build.fingerprint')
    for name, digest in manifest['files'].items():
        if hashlib.sha256((args.package / name).read_bytes()).hexdigest() != digest:
            raise RuntimeError('Package changed: ' + name)
    remote = '/data/local/tmp/picomisu-bq-test-' + uuid.uuid4().hex
    report = {'system_partitions_modified': False, 'factory_vr_services_replaced': False,
              'test_library_sha256': manifest['files'], 'results': {}}
    try:
        adb('shell', 'mkdir ' + remote)
        for abi in ('arm64', 'arm'):
            adb('push', str(args.package / abi), remote + '/', timeout=120)
            if args.pxrguiex_test:
                adb('push', str(args.package / ('pxrguiex-' + abi)), remote + '/', timeout=300)
        for name, digest in manifest['files'].items():
            actual = adb('shell', 'toybox sha256sum ' + remote + '/' + name).split()[0]
            if actual != digest:
                raise RuntimeError('Device test file differs: ' + name)
        for abi in (() if args.only_layer_fence_tests or args.only_freeze_remote_observation or args.only_surface_freeze_probe or args.only_monitored_producer_tests or args.only_binder_parity_probe else ('arm64', 'arm')):
            directory = remote + '/' + abi
            adb('shell', 'chmod 700 ' + directory + '/picomisu_bufferqueue_test')
            output = adb('shell', 'LD_LIBRARY_PATH=' + directory + ' ' + directory
                         + '/picomisu_bufferqueue_test --gtest_color=no', timeout=90)
            if f'[  PASSED  ] {args.expected_tests} tests.' not in output:
                raise RuntimeError('Unexpected test summary: ' + output)
            report['results'][abi] = {'passed': args.expected_tests, 'output': output}
            print(f'{abi}: {args.expected_tests} tests passed', flush=True)
            if args.wire_probe:
                probe = directory + '/picomisu_bufferitem_wire_probe'
                adb('shell', 'chmod 700 ' + probe)
                source_output = adb('shell', 'LD_LIBRARY_PATH=' + directory + ' ' + probe)
                factory_output = adb('shell', 'LD_LIBRARY_PATH= ' + probe)
                source_lines = [line for line in source_output.splitlines() if line.startswith('wire ')]
                factory_lines = [line for line in factory_output.splitlines() if line.startswith('wire ')]
                if len(source_lines) != 102 or source_lines != factory_lines:
                    raise RuntimeError('BufferItem factory/AOSP wire fixtures differ for ' + abi)
                report['results'][abi]['factory_bufferitem_wire_fixtures_matched'] = 102
                report['results'][abi]['wire_fixtures_sha256'] = hashlib.sha256(
                    '\n'.join(source_lines).encode()).hexdigest()
                print(abi + ': 102 factory/AOSP wire fixtures matched', flush=True)
            if args.fence_probe:
                probe = directory + '/picomisu_producer_fence_probe'
                adb('shell', 'chmod 700 ' + probe)
                source_output = adb('shell', 'LD_LIBRARY_PATH=' + directory + ' ' + probe)
                factory_output = adb('shell', 'LD_LIBRARY_PATH= ' + probe)
                source_lines = [line for line in source_output.splitlines() if line.startswith('fence-wire ')]
                factory_lines = [line for line in factory_output.splitlines() if line.startswith('fence-wire ')]
                if (len(source_lines) != 11 or source_lines != factory_lines or
                        'fence-probe passed=12' not in source_output or
                        'fence-probe passed=12' not in factory_output):
                    raise RuntimeError('Producer fence factory/AOSP fixtures differ for ' + abi
                                       + '\nSOURCE\n' + source_output + '\nFACTORY\n' + factory_output)
                report['results'][abi]['factory_producer_fence_fixtures_matched'] = 12
                report['results'][abi]['producer_fence_wire_sha256'] = hashlib.sha256(
                    '\n'.join(source_lines).encode()).hexdigest()
                report['results'][abi]['producer_fence_source_output'] = source_output
                report['results'][abi]['producer_fence_factory_output'] = factory_output
                print(abi + ': 12 factory/AOSP producer fence fixtures matched', flush=True)
            if args.consumer_fence_probe:
                probe = directory + '/picomisu_consumer_fence_probe'
                adb('shell', 'chmod 700 ' + probe)
                source_output = adb('shell', 'LD_LIBRARY_PATH=' + directory + ' ' + probe)
                factory_output = adb('shell', 'LD_LIBRARY_PATH= ' + probe)
                source_lines = [line for line in source_output.splitlines() if line.startswith('consumer-fence ')]
                factory_lines = [line for line in factory_output.splitlines() if line.startswith('consumer-fence ')]
                fixtures = args.expected_consumer_fixtures
                if (len(source_lines) != fixtures or source_lines != factory_lines or
                        f'consumer-probe passed={fixtures}' not in source_output or
                        f'consumer-probe passed={fixtures}' not in factory_output):
                    raise RuntimeError('Consumer fence factory/AOSP fixtures differ for ' + abi
                                       + '\nSOURCE\n' + source_output + '\nFACTORY\n' + factory_output)
                report['results'][abi]['factory_consumer_fence_fixtures_matched'] = fixtures
                report['results'][abi]['consumer_fence_source_output'] = source_output
                report['results'][abi]['consumer_fence_factory_output'] = factory_output
                print(abi + f': {fixtures} factory/AOSP consumer fence fixtures matched', flush=True)
            if args.display_config_probe:
                probe = directory + '/picomisu_display_config_probe'
                adb('shell', 'chmod 700 ' + probe)
                source_output = adb('shell', 'LD_LIBRARY_PATH=' + directory + ' ' + probe)
                factory_output = adb('shell', 'LD_LIBRARY_PATH= ' + probe)
                source_lines = [line for line in source_output.splitlines() if line.startswith('display-config ')]
                factory_lines = [line for line in factory_output.splitlines() if line.startswith('display-config ')]
                if (len(source_lines) != 5 or source_lines != factory_lines or
                        'display-config-probe passed=5' not in source_output or
                        'display-config-probe passed=5' not in factory_output):
                    raise RuntimeError('Display config factory/AOSP fixtures differ for ' + abi
                                       + '\nSOURCE\n' + source_output + '\nFACTORY\n' + factory_output)
                report['results'][abi]['factory_display_config_fixtures_matched'] = 5
                report['results'][abi]['display_config_source_output'] = source_output
                report['results'][abi]['display_config_factory_output'] = factory_output
                print(abi + ': 5 factory/AOSP display config fixtures matched', flush=True)
            if args.display_flags_probe:
                expected_factory = {'arm64': '7b52e5bc29cf5d68c1b24ce6701535dcae64131e3c83b685713ea4a0b4b6dcc5',
                                    'arm': '09e91a368003bf8112abaf4adc98f1a78df9ac88ada3f9c81f1eb12f51e68db0'}[abi]
                library_dir = 'lib64' if abi == 'arm64' else 'lib'
                if adb('shell', 'toybox sha256sum /system/' + library_dir + '/libgui.so').split()[0] != expected_factory:
                    raise RuntimeError('Factory flags ELF differs: ' + abi)
                probe = directory + '/picomisu_display_flags_probe'
                adb('shell', 'chmod 700 ' + probe)
                source_output = adb('shell', 'LD_LIBRARY_PATH=' + directory + ' ' + probe)
                factory_output = adb('shell', 'LD_LIBRARY_PATH= ' + probe)
                source_lines = [line for line in source_output.splitlines() if line.startswith('display-flags ')]
                factory_lines = [line for line in factory_output.splitlines() if line.startswith('display-flags ')]
                if (len(source_lines) != 17 or source_lines != factory_lines or
                        'display-flags-probe passed=17' not in source_output or
                        'display-flags-probe passed=17' not in factory_output):
                    raise RuntimeError('Display flags fixtures differ for ' + abi + '\nSOURCE\n' + source_output + '\nFACTORY\n' + factory_output)
                report['results'][abi].update(factory_display_flags_fixtures_matched=17,
                        display_flags_source_output=source_output, display_flags_factory_output=factory_output)
                print(abi + ': 17 factory/AOSP display flags fixtures matched', flush=True)
            if args.egl_image_tracker_probe:
                expected_factory = {'arm64': '7b52e5bc29cf5d68c1b24ce6701535dcae64131e3c83b685713ea4a0b4b6dcc5',
                                    'arm': '09e91a368003bf8112abaf4adc98f1a78df9ac88ada3f9c81f1eb12f51e68db0'}[abi]
                library_dir = 'lib64' if abi == 'arm64' else 'lib'
                if adb('shell', 'toybox sha256sum /system/' + library_dir + '/libgui.so').split()[0] != expected_factory:
                    raise RuntimeError('Factory tracker ELF differs: ' + abi)
                probe = directory + '/picomisu_egl_image_tracker_probe'
                adb('shell', 'chmod 700 ' + probe)
                property_before = adb('shell', 'getprop debug.sf.enable_egl_image_tracker').strip()
                comparisons = {}
                for mode in ('default', 'zero', 'one', 'negative', 'two', 'garbage',
                             'hex', 'suffix', 'space', 'empty', 'minus-zero', 'leading-zero'):
                    source_output = adb('shell', 'LD_LIBRARY_PATH=' + directory + ' ' + probe + ' ' + mode)
                    factory_output = adb('shell', 'LD_LIBRARY_PATH= ' + probe + ' ' + mode)
                    source_lines = [line for line in source_output.splitlines() if line.startswith('egl-tracker ')]
                    factory_lines = [line for line in factory_output.splitlines() if line.startswith('egl-tracker ')]
                    if (len(source_lines) != 6 or source_lines != factory_lines or
                            'egl-tracker-probe passed=6' not in source_output or
                            'egl-tracker-probe passed=6' not in factory_output):
                        raise RuntimeError('Tracker fixtures differ for ' + abi + '/' + mode +
                                           '\nSOURCE\n' + source_output + '\nFACTORY\n' + factory_output)
                    comparisons[mode] = {'matched': 6, 'source_output': source_output,
                                         'factory_output': factory_output}
                if adb('shell', 'getprop debug.sf.enable_egl_image_tracker').strip() != property_before:
                    raise RuntimeError('System tracker property changed during isolated test')
                report['results'][abi].update(factory_egl_image_tracker_fixtures_matched=72,
                        egl_image_tracker_comparisons=comparisons,
                        egl_image_tracker_system_property_unchanged=True)
                print(abi + ': 72 factory/AOSP EGL tracker fixtures matched', flush=True)
            if args.surface_client_probe:
                library_dir = 'lib64' if abi == 'arm64' else 'lib'
                expected_factory = {
                        'arm64': {'libgui.so': '7b52e5bc29cf5d68c1b24ce6701535dcae64131e3c83b685713ea4a0b4b6dcc5',
                                  'libbinder.so': '9e5bdf585d73baddf17bbc646b4daea0e2b15d4fb6d8dc244d08412dd1be86a9'},
                        'arm': {'libgui.so': '09e91a368003bf8112abaf4adc98f1a78df9ac88ada3f9c81f1eb12f51e68db0',
                                'libbinder.so': '0d0459e40cde072ade682b87ff45da9333a30f2efdf908b92255ecd8924e6823'}}[abi]
                for library, digest in expected_factory.items():
                    if adb('shell', 'toybox sha256sum /system/' + library_dir + '/' + library).split()[0] != digest:
                        raise RuntimeError('Factory SurfaceClient dependency differs: ' + abi + '/' + library)
                probe = directory + '/picomisu_surface_client_probe'
                adb('shell', 'chmod 700 ' + probe)
                source_output = adb('shell', 'LD_LIBRARY_PATH=' + directory + ' ' + probe)
                factory_output = adb('shell', 'LD_LIBRARY_PATH= ' + probe)
                prefix = ('surface-client ', 'calling-tid ')
                source_lines = [line for line in source_output.splitlines() if line.startswith(prefix)]
                factory_lines = [line for line in factory_output.splitlines() if line.startswith(prefix)]
                if (len(source_lines) != 30 or source_lines != factory_lines or
                        'surface-client-probe passed=22 calling-tid=8' not in source_output or
                        'surface-client-probe passed=22 calling-tid=8' not in factory_output):
                    raise RuntimeError('SurfaceClient fixtures differ for ' + abi +
                                       '\nSOURCE\n' + source_output + '\nFACTORY\n' + factory_output)
                report['results'][abi].update(factory_surface_client_fixtures_matched=22,
                        factory_calling_tid_fixtures_matched=8,
                        surface_client_source_output=source_output, surface_client_factory_output=factory_output,
                        surface_client_layout_runtime_matched=True,
                        calling_tid_query_intercepted=True)
                print(abi + ': 22 SurfaceClient and 8 caller-ID factory/AOSP fixtures matched', flush=True)
            if args.dequeue_count_probe:
                library_dir = 'lib64' if abi == 'arm64' else 'lib'
                expected_factory = {
                    'arm64': '7b52e5bc29cf5d68c1b24ce6701535dcae64131e3c83b685713ea4a0b4b6dcc5',
                    'arm': '09e91a368003bf8112abaf4adc98f1a78df9ac88ada3f9c81f1eb12f51e68db0',
                }[abi]
                actual_factory = adb('shell', 'toybox sha256sum /system/' + library_dir + '/libgui.so').split()[0]
                if actual_factory != expected_factory:
                    raise RuntimeError('Factory dequeue-count ELF differs: ' + abi)
                probe = directory + '/picomisu_dequeue_count_probe'
                adb('shell', 'chmod 700 ' + probe)
                source_output = adb('shell', 'LD_LIBRARY_PATH=' + directory + ' ' + probe)
                factory_output = adb('shell', 'LD_LIBRARY_PATH= ' + probe)
                source_lines = [line for line in source_output.splitlines() if line.startswith('dequeue-count ')]
                factory_lines = [line for line in factory_output.splitlines() if line.startswith('dequeue-count ')]
                if (len(source_lines) != 108 or source_lines != factory_lines or
                        'dequeue-count-probe passed=108' not in source_output or
                        'dequeue-count-probe passed=108' not in factory_output):
                    raise RuntimeError('Dequeue count factory/AOSP fixtures differ for ' + abi +
                                       '\nSOURCE\n' + source_output + '\nFACTORY\n' + factory_output)
                report['results'][abi]['factory_dequeue_count_fixtures_matched'] = 108
                report['results'][abi]['dequeue_count_source_output'] = source_output
                report['results'][abi]['dequeue_count_factory_output'] = factory_output
                report['results'][abi]['dequeue_count_factory_sha256'] = expected_factory
                print(abi + ': 108 factory/AOSP dequeue count fixtures matched', flush=True)
            if args.cached_buffer_probe:
                probe = directory + '/picomisu_cached_buffer_probe'
                adb('shell', 'chmod 700 ' + probe)
                source_output = adb('shell', 'LD_LIBRARY_PATH=' + directory + ' ' + probe)
                factory_output = adb('shell', 'LD_LIBRARY_PATH= ' + probe)
                source_lines = [line for line in source_output.splitlines() if line.startswith('cached-buffer ')]
                factory_lines = [line for line in factory_output.splitlines() if line.startswith('cached-buffer ')]
                if len(source_lines) != 10 or source_lines != factory_lines:
                    raise RuntimeError('Cached buffer factory/AOSP fixtures differ for ' + abi
                                       + '\nSOURCE\n' + source_output + '\nFACTORY\n' + factory_output)
                report['results'][abi]['factory_cached_buffer_fixtures_matched'] = 10
                report['results'][abi]['cached_buffer_source_output'] = source_output
                report['results'][abi]['cached_buffer_factory_output'] = factory_output
                print(abi + ': 10 factory/AOSP cached buffer fixtures matched', flush=True)
            if args.freeze_wire_probe:
                probe = directory + '/picomisu_freeze_wire_probe'
                adb('shell', 'chmod 700 ' + probe)
                source_output = adb('shell', 'LD_LIBRARY_PATH=' + directory + ' ' + probe)
                factory_output = adb('shell', 'LD_LIBRARY_PATH= ' + probe)
                source_lines = [line for line in source_output.splitlines() if line.startswith('freeze-wire ')]
                factory_lines = [line for line in factory_output.splitlines() if line.startswith('freeze-wire ')]
                if (len(source_lines) != 12 or source_lines != factory_lines or
                        'freeze-wire-probe passed=12' not in source_output or
                        'freeze-wire-probe passed=12' not in factory_output):
                    raise RuntimeError('Freeze Binder factory/AOSP fixtures differ for ' + abi
                                       + '\nSOURCE\n' + source_output + '\nFACTORY\n' + factory_output)
                report['results'][abi]['factory_freeze_wire_fixtures_matched'] = 12
                report['results'][abi]['freeze_wire_source_output'] = source_output
                report['results'][abi]['freeze_wire_factory_output'] = factory_output
                print(abi + ': 12 factory/AOSP freeze Binder fixtures matched', flush=True)
            if args.freeze_registry_probe:
                probe = directory + '/picomisu_freeze_registry_probe'
                adb('shell', 'chmod 700 ' + probe)
                source_output = adb('shell', 'LD_LIBRARY_PATH=' + directory + ' ' + probe)
                factory_output = adb('shell', 'LD_LIBRARY_PATH= ' + probe)
                source_lines = [line for line in source_output.splitlines() if line.startswith('freeze-registry ')]
                factory_lines = [line for line in factory_output.splitlines() if line.startswith('freeze-registry ')]
                if (len(source_lines) != 15 or source_lines != factory_lines or
                        'freeze-registry-probe passed=15' not in source_output or
                        'freeze-registry-probe passed=15' not in factory_output):
                    raise RuntimeError('Freeze registry factory/AOSP fixtures differ for ' + abi
                                       + '\nSOURCE\n' + source_output + '\nFACTORY\n' + factory_output)
                report['results'][abi]['factory_freeze_registry_fixtures_matched'] = 15
                report['results'][abi]['freeze_registry_source_output'] = source_output
                report['results'][abi]['freeze_registry_factory_output'] = factory_output
                print(abi + ': 15 factory/AOSP freeze registry fixtures matched', flush=True)
            if args.frozen_reply_probe:
                probe = directory + '/picomisu_frozen_reply_probe'
                adb('shell', 'chmod 700 ' + probe)
                source_output = adb('shell', 'LD_LIBRARY_PATH=' + directory + ' ' + probe)
                factory_output = adb('shell', 'LD_LIBRARY_PATH= ' + probe)
                source_lines = [line for line in source_output.splitlines() if line.startswith('frozen-reply ')]
                factory_lines = [line for line in factory_output.splitlines() if line.startswith('frozen-reply ')]
                if (len(source_lines) != 10 or source_lines != factory_lines or
                        'frozen-reply-probe passed=10' not in source_output or
                        'frozen-reply-probe passed=10' not in factory_output):
                    raise RuntimeError('Frozen reply factory/AOSP fixtures differ for ' + abi
                                       + '\nSOURCE\n' + source_output + '\nFACTORY\n' + factory_output)
                report['results'][abi]['factory_frozen_reply_fixtures_matched'] = 10
                report['results'][abi]['frozen_reply_source_output'] = source_output
                report['results'][abi]['frozen_reply_factory_output'] = factory_output
                print(abi + ': 10 factory/AOSP frozen reply fixtures matched', flush=True)
            if args.producer_freeze_probe:
                probe = directory + '/picomisu_producer_freeze_probe'
                adb('shell', 'chmod 700 ' + probe)
                source_output = adb('shell', 'LD_LIBRARY_PATH=' + directory + ' ' + probe)
                factory_output = adb('shell', 'LD_LIBRARY_PATH= ' + probe)
                source_lines = [line for line in source_output.splitlines() if line.startswith('producer-freeze ')]
                factory_lines = [line for line in factory_output.splitlines() if line.startswith('producer-freeze ')]
                if (len(source_lines) != 9 or source_lines != factory_lines or
                        'producer-freeze-probe passed=9' not in source_output or
                        'producer-freeze-probe passed=9' not in factory_output):
                    raise RuntimeError('Producer self-unfreeze factory/AOSP fixtures differ for ' + abi
                                       + '\nSOURCE\n' + source_output + '\nFACTORY\n' + factory_output)
                report['results'][abi]['factory_producer_freeze_fixtures_matched'] = 9
                report['results'][abi]['producer_freeze_source_output'] = source_output
                report['results'][abi]['producer_freeze_factory_output'] = factory_output
                print(abi + ': 9 factory/AOSP producer self-unfreeze fixtures matched', flush=True)
        if args.freeze_remote_observation:
            for abi in ('arm64', 'arm'):
                directory = remote + '/' + abi
                probe = directory + '/picomisu_freeze_remote_probe'
                adb('shell', 'chmod 700 ' + probe)
                output = adb('shell', 'LD_LIBRARY_PATH= ' + probe)
                lines = [line for line in output.splitlines() if line.startswith('freeze-remote ')]
                if len(lines) != 9 or 'freeze-remote-observation completed=1' not in output:
                    raise RuntimeError('Incomplete factory remote registration observation for ' + abi + ': ' + output)
                report['results'].setdefault(abi, {})['factory_freeze_remote_observation'] = output
                print(abi + ': factory remote registration observed at 9 checkpoints', flush=True)
                # The Source FreezeManager reproduces the factory remote registry (chunk 6):
                # the same checkpoints (and ARM64 root map sizes) must be observed.
                source_output = adb('shell', 'LD_LIBRARY_PATH=' + directory + ' ' + probe)
                source_lines = [line for line in source_output.splitlines()
                                if line.startswith(('freeze-remote ', 'freeze-remote-map '))]
                factory_lines = [line for line in output.splitlines()
                                 if line.startswith(('freeze-remote ', 'freeze-remote-map '))]
                if source_lines != factory_lines or 'freeze-remote-observation completed=1' not in source_output:
                    raise RuntimeError('Remote freeze registry factory/AOSP observations differ for ' + abi
                                       + '\nSOURCE\n' + source_output + '\nFACTORY\n' + output)
                report['results'][abi]['source_freeze_remote_observation'] = source_output
                report['results'][abi]['factory_freeze_remote_checkpoints_matched'] = len(source_lines)
                print(abi + ': %d factory/AOSP remote registration checkpoints matched' % len(source_lines),
                      flush=True)
        if args.binder_parity_probe:
            for abi in ('arm64', 'arm'):
                directory = remote + '/' + abi
                probe = directory + '/picomisu_binder_parity_probe'
                adb('shell', 'chmod 700 ' + probe)
                source_output = adb('shell', 'LD_LIBRARY_PATH=' + directory + ' ' + probe)
                factory_output = adb('shell', 'LD_LIBRARY_PATH= ' + probe)
                source_lines = [line for line in source_output.splitlines() if line.startswith('binder-parity ')]
                factory_lines = [line for line in factory_output.splitlines() if line.startswith('binder-parity ')]
                if (len(source_lines) < 20 or source_lines != factory_lines or
                        'binder-parity-probe completed=1' not in source_output or
                        'binder-parity-probe completed=1' not in factory_output):
                    raise RuntimeError('libbinder factory/AOSP parity fixtures differ for ' + abi
                                       + '\nSOURCE\n' + source_output + '\nFACTORY\n' + factory_output)
                report['results'].setdefault(abi, {})['factory_binder_parity_fixtures_matched'] = len(source_lines)
                report['results'][abi]['binder_parity_output'] = source_output
                print(abi + ': %d factory/AOSP libbinder parity fixtures matched' % len(source_lines), flush=True)
        if args.pxrguiex_test:
            for abi, suffix in (('arm64', '64'), ('arm', '32')):
                directory = remote + '/pxrguiex-' + abi
                test = directory + '/hwui_pxrguiex_test' + suffix
                adb('shell', 'chmod 700 ' + test)
                output = adb('shell', 'LD_LIBRARY_PATH=' + directory + ' ' + test + ' --link-only; echo exit=$?', timeout=120)
                if ('RESULT: PASS' not in output or 'exit=0' not in output or
                        'libhwui: ' + directory + '/libhwui.so' not in output):
                    log = adb('shell', 'logcat -d -t 300 -s libEGL:* linker:* OpenGLRenderer:* ImageManagerExt:*')
                    raise RuntimeError('libpxrguiex against the Source libhwui failed for ' + abi + ':\n' + output
                                       + '\nLOGCAT\n' + log)
                checks = [line for line in output.splitlines() if line.startswith('OK')]
                report['results'].setdefault(abi, {})['pxrguiex_checks_passed'] = len(checks)
                report['results'][abi]['pxrguiex_output'] = output
                print(abi + ': factory libpxrguiex with Source libhwui passed %d checks' % len(checks), flush=True)
        if args.surface_freeze_probe:
            expected_runtime = {
                'arm64': '1f558c16d89065d6e07e3202431c3ce73ab9ef710eac31117fd152976e71f1cd',
                'arm': 'deccb4b074459d2282f0a9cba144dc0934f32a79ee2455b99af2536f2b06bc47',
            }
            for abi in ('arm64', 'arm'):
                system_directory = 'lib64' if abi == 'arm64' else 'lib'
                actual = adb('shell', 'toybox sha256sum /system/' + system_directory + '/libandroid_runtime.so').split()[0]
                if actual != expected_runtime[abi]:
                    raise RuntimeError('Factory JNI address cannot be used with changed libandroid_runtime')
                directory = remote + '/' + abi
                probe = directory + '/picomisu_surface_freeze_probe'
                adb('shell', 'chmod 700 ' + probe)
                source_output = adb('shell', 'LD_LIBRARY_PATH=' + directory + ' ' + probe)
                factory_output = adb('shell', 'LD_LIBRARY_PATH= ' + probe + ' --factory')
                source_lines = [line for line in source_output.splitlines() if line.startswith('surface-freeze ')]
                factory_lines = [line for line in factory_output.splitlines() if line.startswith('surface-freeze ')]
                if (len(source_lines) != 6 or source_lines != factory_lines or
                        'surface-freeze-probe passed=6' not in source_output or
                        'surface-freeze-probe passed=6' not in factory_output):
                    raise RuntimeError('Surface freeze JNI factory/source fixtures differ for ' + abi
                                       + '\nSOURCE\n' + source_output + '\nFACTORY\n' + factory_output)
                report['results'].setdefault(abi, {}).update(
                    factory_surface_freeze_fixtures_matched=6,
                    surface_freeze_source_output=source_output,
                    surface_freeze_factory_output=factory_output,
                    factory_android_runtime_sha256=actual)
                print(abi + ': 6 factory/source Surface freeze JNI fixtures matched', flush=True)
        if args.freeze_registry_tests:
            for abi in ('arm64', 'arm'):
                directory = remote + '/' + abi
                test = directory + '/picomisu_freeze_registry_test'
                adb('shell', 'chmod 700 ' + test)
                output = adb('shell', 'LD_LIBRARY_PATH=' + directory + ' ' + test
                             + ' --gtest_color=no', timeout=90)
                if '[  PASSED  ] 4 tests.' not in output:
                    raise RuntimeError('Unexpected freeze registry summary for ' + abi + ': ' + output)
                report['freeze_registry_' + abi] = {'passed': 4, 'output': output}
                print(abi + ': 4 freeze registry ASan tests passed', flush=True)
        if args.render_surface_tests:
            for abi in ('arm64', 'arm'):
                directory = remote + '/' + abi
                test = directory + '/libcompositionengine_test'
                adb('shell', 'chmod 700 ' + test)
                output = adb('shell', 'LD_LIBRARY_PATH=' + directory + ' ' + test
                             + ' --gtest_color=no --gtest_filter=RenderSurfaceTest.*', timeout=90)
                if f'[  PASSED  ] {args.expected_render_surface_tests} tests.' not in output:
                    raise RuntimeError('Unexpected RenderSurface test summary for ' + abi + ': ' + output)
                report['render_surface_' + abi] = {'passed': args.expected_render_surface_tests,
                                                  'output': output}
                print(f'{abi}: {args.expected_render_surface_tests} RenderSurface tests passed', flush=True)
        if args.layer_fence_tests and not args.only_monitored_producer_tests:
            test_filter = 'BufferLayerConsumerFenceTest.*'
            expected = 5
            result_key = 'layer_fence_'
            if args.virtual_display_fence_tests:
                test_filter += ':VirtualDisplaySurfaceFenceTest.*'
                expected += args.expected_virtual_display_tests
                result_key = 'virtual_display_and_layer_fence_'
            for abi in ('arm64', 'arm'):
                directory = remote + '/' + abi
                test = directory + '/libsurfaceflinger_unittest'
                adb('shell', 'chmod 700 ' + test)
                output = adb('shell', 'LD_LIBRARY_PATH=' + directory + ' ' + test
                             + ' --gtest_color=no --gtest_filter=' + test_filter, timeout=90)
                if f'[  PASSED  ] {expected} tests.' not in output:
                    raise RuntimeError('Unexpected layer fence summary for ' + abi + ': ' + output)
                report[result_key + abi] = {'passed': expected, 'output': output}
                print(f'{abi}: {expected} layer/display fence tests passed', flush=True)
        for enabled, suite, test_filter, expected in [
                (args.pico_composition_tests, 'pico_composition_',
                 'PicoSingleLayerCompositionTest.*:DisplayTransactionTest.PicoFlags*', 14),
                (args.composition_regression_tests, 'composition_regression_',
                 'CompositionTest.*:DisplayTransactionTest.*', None),
                (args.monitored_producer_tests, 'monitored_producer_',
                 'PicoMonitoredProducerTest.*', 5)]:
            if not enabled:
                continue
            for abi in ('arm64', 'arm'):
                directory = remote + '/' + abi
                test = directory + '/libsurfaceflinger_unittest'
                adb('shell', 'chmod 700 ' + test)
                output = adb('shell', 'LD_LIBRARY_PATH=' + directory + ' ' + test +
                             ' --gtest_color=no --gtest_filter=' + test_filter, timeout=150)
                summary = re.search(r'^\[\s+PASSED\s+\]\s+(\d+) tests\.', output, re.MULTILINE)
                passed = int(summary.group(1)) if summary else 0
                if not passed or (expected is not None and passed != expected):
                    raise RuntimeError('Unexpected composition summary for ' + abi + ': ' + output)
                report[suite + abi] = {'passed': passed, 'output': output}
                print(abi + ': ' + str(passed) + ' ' + suite.rstrip('_') + ' tests passed', flush=True)
        report['fingerprint_unchanged'] = adb('shell', 'getprop ro.build.fingerprint') == fingerprint
        report['boot_completed'] = adb('shell', 'getprop sys.boot_completed') == '1'
    finally:
        # Only the unique directory created by this invocation is removed.
        adb('shell', 'rm -rf ' + remote)
        report['temporary_files_removed'] = True
        name = 'freeze-remote-observation.json' if args.only_freeze_remote_observation else 'bufferqueue-runtime-test.json'
        if args.only_surface_freeze_probe:
            name = 'surface-freeze-runtime-test.json'
        if args.only_binder_parity_probe:
            name = 'binder-parity-runtime-test.json'
        destination = ROOT / 'reports/framework-bridge' / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
