"""Package source-built tests and non-bionic dependencies for isolated execution."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--product', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--wire-probe', action='store_true')
    parser.add_argument('--fence-probe', action='store_true')
    parser.add_argument('--consumer-fence-probe', action='store_true')
    parser.add_argument('--display-config-probe', action='store_true')
    parser.add_argument('--display-flags-probe', action='store_true')
    parser.add_argument('--egl-image-tracker-probe', action='store_true')
    parser.add_argument('--surface-client-probe', action='store_true')
    parser.add_argument('--surface-monitor-probe', action='store_true')
    parser.add_argument('--dequeue-count-probe', action='store_true')
    parser.add_argument('--cached-buffer-probe', action='store_true')
    parser.add_argument('--freeze-wire-probe', action='store_true')
    parser.add_argument('--freeze-registry-probe', action='store_true')
    parser.add_argument('--freeze-registry-tests', action='store_true')
    parser.add_argument('--frozen-reply-probe', action='store_true')
    parser.add_argument('--freeze-remote-observation', action='store_true')
    parser.add_argument('--producer-freeze-probe', action='store_true')
    parser.add_argument('--binder-parity-probe', action='store_true')
    parser.add_argument('--pxrguiex-test', action='store_true')
    parser.add_argument('--surface-freeze-probe', action='store_true')
    parser.add_argument('--render-surface-tests', action='store_true')
    parser.add_argument('--layer-fence-tests', action='store_true')
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    manifest = {'system_libraries_used': ['libc.so', 'libdl.so', 'libm.so'], 'files': {}}
    for abi, directory, tests in [('arm64', 'lib64', 'nativetest64'), ('arm', 'lib', 'nativetest')]:
        destination = args.out / abi
        destination.mkdir()
        queue = [args.product / 'data' / tests / 'picomisu_bufferqueue_test/picomisu_bufferqueue_test']
        if args.wire_probe:
            queue.append(args.product / 'data' / tests /
                         'picomisu_bufferitem_wire_probe/picomisu_bufferitem_wire_probe')
        if args.fence_probe:
            queue.append(args.product / 'data' / tests /
                         'picomisu_producer_fence_probe/picomisu_producer_fence_probe')
        if args.consumer_fence_probe:
            queue.append(args.product / 'data' / tests /
                         'picomisu_consumer_fence_probe/picomisu_consumer_fence_probe')
        if args.display_config_probe:
            queue.append(args.product / 'data' / tests /
                         'picomisu_display_config_probe/picomisu_display_config_probe')
        if args.display_flags_probe:
            queue.append(args.product / 'data' / tests /
                         'picomisu_display_flags_probe/picomisu_display_flags_probe')
        if args.egl_image_tracker_probe:
            queue.append(args.product / 'data' / tests /
                         'picomisu_egl_image_tracker_probe/picomisu_egl_image_tracker_probe')
        if args.surface_client_probe:
            queue.append(args.product / 'data' / tests /
                         'picomisu_surface_client_probe/picomisu_surface_client_probe')
        if args.surface_monitor_probe:
            queue.append(args.product / 'data' / tests /
                         'picomisu_surface_monitor_probe/picomisu_surface_monitor_probe')
        if args.dequeue_count_probe:
            queue.append(args.product / 'data' / tests /
                         'picomisu_dequeue_count_probe/picomisu_dequeue_count_probe')
        if args.cached_buffer_probe:
            queue.append(args.product / 'data' / tests /
                         'picomisu_cached_buffer_probe/picomisu_cached_buffer_probe')
        if args.freeze_wire_probe:
            queue.append(args.product / 'data' / tests /
                         'picomisu_freeze_wire_probe/picomisu_freeze_wire_probe')
        if args.freeze_registry_probe:
            queue.append(args.product / 'data' / tests /
                         'picomisu_freeze_registry_probe/picomisu_freeze_registry_probe')
        if args.freeze_registry_tests:
            queue.append(args.product / 'data' / tests /
                         'picomisu_freeze_registry_test/picomisu_freeze_registry_test')
        if args.frozen_reply_probe:
            queue.append(args.product / 'data' / tests /
                         'picomisu_frozen_reply_probe/picomisu_frozen_reply_probe')
        if args.freeze_remote_observation:
            queue.append(args.product / 'data' / tests /
                         'picomisu_freeze_remote_probe/picomisu_freeze_remote_probe')
        if args.producer_freeze_probe:
            queue.append(args.product / 'data' / tests /
                         'picomisu_producer_freeze_probe/picomisu_producer_freeze_probe')
        if args.surface_freeze_probe:
            queue.append(args.product / 'data' / tests /
                         'picomisu_surface_freeze_probe/picomisu_surface_freeze_probe')
        if args.binder_parity_probe:
            queue.append(args.product / 'data' / tests /
                         'picomisu_binder_parity_probe/picomisu_binder_parity_probe')
        if args.render_surface_tests:
            queue.append(args.product / 'data' / tests /
                         'libcompositionengine_test/libcompositionengine_test')
        if args.layer_fence_tests:
            queue.append(args.product / 'data' / tests /
                         'libsurfaceflinger_unittest/libsurfaceflinger_unittest')
        seen = set()
        while queue:
            source = queue.pop()
            if source.name in seen:
                continue
            seen.add(source.name)
            target = destination / source.name
            shutil.copyfile(source, target)
            manifest['files'][str(target.relative_to(args.out))] = hashlib.sha256(target.read_bytes()).hexdigest()
            dynamic = subprocess.check_output(['readelf', '-d', str(source)], text=True)
            if source.name in ('picomisu_bufferitem_wire_probe', 'picomisu_producer_fence_probe', 'picomisu_consumer_fence_probe', 'picomisu_display_config_probe', 'picomisu_display_flags_probe', 'picomisu_dequeue_count_probe', 'picomisu_cached_buffer_probe', 'picomisu_freeze_wire_probe', 'picomisu_freeze_registry_probe', 'picomisu_frozen_reply_probe', 'picomisu_freeze_remote_probe', 'picomisu_producer_freeze_probe', 'picomisu_surface_freeze_probe', 'picomisu_binder_parity_probe') and re.search(r'\((?:RUNPATH|RPATH)\)', dynamic):
                raise RuntimeError('Wire probe must use only explicit library search paths')
            if source.name in ('picomisu_frozen_reply_probe', 'picomisu_freeze_remote_probe', 'picomisu_binder_parity_probe'):
                exports = subprocess.check_output(['readelf', '--dyn-syms', '--wide', str(source)], text=True)
                if not re.search(r'GLOBAL\s+DEFAULT\s+(?!UND\b)\S+\s+ioctl\b', exports):
                    raise RuntimeError('Frozen reply probe must export intercepted ioctl')
            if source.name == 'picomisu_egl_image_tracker_probe':
                if re.search(r'\((?:RUNPATH|RPATH)\)', dynamic):
                    raise RuntimeError('Tracker probe must use explicit library search paths')
                exports = subprocess.check_output(['readelf', '--dyn-syms', '--wide', str(source)], text=True)
                if not re.search(r'GLOBAL\s+DEFAULT\s+(?!UND\b)\S+\s+property_get\b', exports):
                    raise RuntimeError('Tracker probe must export its local property interception')
            if source.name == 'picomisu_surface_client_probe':
                if re.search(r'\((?:RUNPATH|RPATH)\)', dynamic):
                    raise RuntimeError('SurfaceClient probe must use explicit library search paths')
                exports = subprocess.check_output(['readelf', '--dyn-syms', '--wide', str(source)], text=True)
                for symbol in ('ioctl', 'systemTime'):
                    if not re.search(r'GLOBAL\s+DEFAULT\s+(?!UND\b)\S+\s+' + symbol + r'\b', exports):
                        raise RuntimeError('SurfaceClient probe must export intercepted ' + symbol)
            if source.name == 'picomisu_surface_monitor_probe':
                if re.search(r'\((?:RUNPATH|RPATH)\)', dynamic):
                    raise RuntimeError('Monitor probe must use explicit library search paths')
                exports = subprocess.check_output(['readelf', '--dyn-syms', '--wide', str(source)], text=True)
                for symbol in ('property_get', 'property_get_int32', 'systemTime', 'getpid', 'fopen',
                               '_ZN7android21defaultServiceManagerEv',
                               '_ZN7android12ProcessState13getDriverNameEv',
                               '_ZNK7android14IPCThreadState13getCallingPidEv',
                               '_ZN7android14IPCThreadState13getCallingTidEv'):
                    if not re.search(r'GLOBAL\s+DEFAULT\s+(?!UND\b)\S+\s+' + symbol + r'\b', exports):
                        raise RuntimeError('Monitor probe must export intercepted ' + symbol)
            if source.name == 'libsurfaceflinger_unittest':
                exports = subprocess.check_output(['readelf', '--dyn-syms', '--wide', str(source)], text=True)
                if not re.search(r'GLOBAL\s+DEFAULT\s+(?!UND\b)\S+\s+property_get_int32\b', exports):
                    raise RuntimeError('Compositor unit tests must export local monitor isolation')
            if source.name in ('picomisu_freeze_registry_probe', 'picomisu_freeze_registry_test', 'picomisu_freeze_remote_probe', 'picomisu_binder_parity_probe', 'picomisu_producer_freeze_probe', 'picomisu_surface_freeze_probe', 'picomisu_dequeue_count_probe'):
                exports = subprocess.check_output(['readelf', '--dyn-syms', '--wide', str(source)], text=True)
                if not re.search(r'GLOBAL\s+DEFAULT\s+(?!UND\b)\S+\s+_ZN7android21defaultServiceManagerEv\b', exports):
                    raise RuntimeError('Fake service manager must be exported for interposition')
            for name in re.findall(r'\(NEEDED\).*?\[([^\]]+)\]', dynamic):
                if name in manifest['system_libraries_used']:
                    continue
                dependency = args.product / 'system' / directory / name
                if not dependency.is_file():
                    raise RuntimeError('Missing AOSP dependency: ' + str(dependency))
                queue.append(dependency)
        if args.pxrguiex_test:
            # Separate group: the factory libpxrguiex.so stays on /system and is dlopen'ed with
            # the Source libhwui, libgui and libandroid_runtime (its NEEDED) from this directory.
            # Only linking is checked in isolation: the EGL loader dlopens its wrappers by the
            # absolute /system path, so a GL context would mix in the installed EGL stack.
            group = args.out / ('pxrguiex-' + abi)
            group.mkdir()
            system_graphics = set()
            suffix = '64' if abi == 'arm64' else '32'
            pending = [args.product / 'data' / tests / ('hwui_pxrguiex_test/hwui_pxrguiex_test' + suffix),
                       args.product / 'system' / directory / 'libandroid_runtime.so']
            copied = set()
            while pending:
                source = pending.pop()
                if source.name in copied:
                    continue
                copied.add(source.name)
                target = group / source.name
                shutil.copyfile(source, target)
                manifest['files'][str(target.relative_to(args.out))] = hashlib.sha256(target.read_bytes()).hexdigest()
                dynamic = subprocess.check_output(['readelf', '-d', str(source)], text=True)
                if re.search(r'\((?:RUNPATH|RPATH)\)', dynamic):
                    raise RuntimeError('pxrguiex group must use explicit library search paths')
                for name in re.findall(r'\(NEEDED\).*?\[([^\]]+)\]', dynamic):
                    if name in manifest['system_libraries_used'] or name in system_graphics:
                        continue
                    dependency = args.product / 'system' / directory / name
                    if not dependency.is_file():
                        # libandroid_runtime also needs Source runtime APEX libraries.
                        dependency = args.product / 'system/apex/com.android.runtime.debug' / directory / name
                    if not dependency.is_file():
                        raise RuntimeError('Missing AOSP dependency: ' + str(dependency))
                    pending.append(dependency)
    (args.out / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(f"Packaged {len(manifest['files'])} files")


if __name__ == '__main__':
    main()
