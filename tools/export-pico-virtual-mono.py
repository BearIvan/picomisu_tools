"""Save a separate kernel prototype and evidence, preserving earlier outputs.

Do not pair this new Image with modules verified against the earlier Image.
No signing or device operation is performed here.
"""
from pathlib import Path
import argparse
from datetime import datetime
import hashlib
import json
import shutil
import subprocess

BASE = Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro')
SOURCE = BASE / 'source/phoenix-kernel-recovery'
OUT = BASE / 'out/phoenix-kernel-recovery'


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--sensor-hook', action='store_true')
    parser.add_argument('--hub-relay', action='store_true')
    parser.add_argument('--hub-registry', action='store_true')
    parser.add_argument('--hub-file', action='store_true')
    parser.add_argument('--hub-events', action='store_true')
    parser.add_argument('--hub-ioctl', action='store_true')
    parser.add_argument('--hub-subscriptions', action='store_true')
    parser.add_argument('--hub-subscription-callbacks', action='store_true')
    parser.add_argument('--hub-resources', action='store_true')
    parser.add_argument('--hub-cleanup', action='store_true')
    parser.add_argument('--hub-fops', action='store_true')
    parser.add_argument('--hub-dispatch', action='store_true')
    parser.add_argument('--hub-registration', action='store_true')
    parser.add_argument('--hub-irq', action='store_true')
    parser.add_argument('--cci-ops', action='store_true')
    parser.add_argument('--subdevice-lifetime', action='store_true')
    parser.add_argument('--subdevice-media', action='store_true')
    parser.add_argument('--memento-ledger', action='store_true')
    parser.add_argument('--memento-node', action='store_true')
    parser.add_argument('--csiphy-rollback', action='store_true')
    parser.add_argument('--memento-sensor', action='store_true')
    parser.add_argument('--memento-mono', action='store_true')
    parser.add_argument('--memento-actuator', action='store_true')
    parser.add_argument('--memento-ois', action='store_true')
    parser.add_argument('--memento-eeprom', action='store_true')
    parser.add_argument('--memento-flash', action='store_true')
    parser.add_argument('--memento-capture', action='store_true')
    parser.add_argument('--sensor-acquire-unwind', action='store_true')
    parser.add_argument('--sensor-io-unwind', action='store_true')
    parser.add_argument('--sensor-fsin-irq', action='store_true')
    parser.add_argument('--sensor-acquire-retry', action='store_true')
    parser.add_argument('--sensor-release-retry', action='store_true')
    parser.add_argument('--peer-acquire-capture', action='store_true')
    parser.add_argument('--eeprom-acquire-retry', action='store_true')
    parser.add_argument('--eeprom-shutdown-retry', action='store_true')
    parser.add_argument('--eeprom-power-retry', action='store_true')
    parser.add_argument('--eeprom-parser-unwind', action='store_true')
    parser.add_argument('--eeprom-command-bounds', action='store_true')
    parser.add_argument('--eeprom-write-payload', action='store_true')
    parser.add_argument('--eeprom-packet-routing', action='store_true')
    parser.add_argument('--eeprom-output-copy', action='store_true')
    parser.add_argument('--eeprom-packet-snapshot', action='store_true')
    parser.add_argument('--eeprom-command-snapshot', action='store_true')
    parser.add_argument('--eeprom-power-decode', action='store_true')
    parser.add_argument('--actuator-acquire-retry', action='store_true')
    parser.add_argument('--actuator-release-retry', action='store_true')
    parser.add_argument('--actuator-shutdown-retry', action='store_true')
    parser.add_argument('--actuator-power-retry', action='store_true')
    parser.add_argument('--actuator-write-routing', action='store_true')
    parser.add_argument('--actuator-request-cleanup', action='store_true')
    parser.add_argument('--actuator-callback-gates', action='store_true')
    parser.add_argument('--camera-callback-borrow', action='store_true')
    parser.add_argument('--v4l2-media-pin', action='store_true')
    parser.add_argument('--v4l2-lifetime', action='store_true')
    parser.add_argument('--actuator-probe-publication', action='store_true')
    parser.add_argument('--crm-ops-snapshot', action='store_true')
    parser.add_argument('--crm-flush-result', action='store_true')
    parser.add_argument('--shared-pinctrl-state', action='store_true')
    parser.add_argument('--shared-gpio-lock', action='store_true')
    parser.add_argument('--camera-power-down-phases', action='store_true')
    parser.add_argument('--camera-power-up-unwind', action='store_true')
    parser.add_argument('--isp-bufdone', action='store_true')
    parser.add_argument('--cdm-kthread-pool', action='store_true')
    parser.add_argument('--binder-extensions', action='store_true')
    parser.add_argument('--kgsl-ctxprio', action='store_true')
    parser.add_argument('--display-temp-pwm', action='store_true')
    parser.add_argument('--batch-20261008', action='store_true')
    args = parser.parse_args()
    args.display_temp_pwm = args.display_temp_pwm or args.batch_20261008
    args.kgsl_ctxprio = args.kgsl_ctxprio or args.display_temp_pwm
    args.binder_extensions = args.binder_extensions or args.kgsl_ctxprio
    args.cdm_kthread_pool = args.cdm_kthread_pool or args.binder_extensions
    args.isp_bufdone = args.isp_bufdone or args.cdm_kthread_pool
    args.camera_power_up_unwind = args.camera_power_up_unwind or args.isp_bufdone
    args.camera_power_down_phases = args.camera_power_down_phases or args.camera_power_up_unwind
    args.shared_gpio_lock = args.shared_gpio_lock or args.camera_power_down_phases
    args.shared_pinctrl_state = args.shared_pinctrl_state or args.shared_gpio_lock
    args.crm_flush_result = args.crm_flush_result or args.shared_pinctrl_state
    args.crm_ops_snapshot = args.crm_ops_snapshot or args.crm_flush_result
    args.actuator_probe_publication = args.actuator_probe_publication or args.crm_ops_snapshot
    args.v4l2_lifetime = args.v4l2_lifetime or args.actuator_probe_publication
    args.v4l2_media_pin = args.v4l2_media_pin or args.v4l2_lifetime
    args.camera_callback_borrow = args.camera_callback_borrow or args.v4l2_media_pin
    args.actuator_callback_gates = args.actuator_callback_gates or args.camera_callback_borrow
    args.actuator_request_cleanup = args.actuator_request_cleanup or args.actuator_callback_gates
    args.actuator_write_routing = args.actuator_write_routing or args.actuator_request_cleanup
    args.actuator_power_retry = args.actuator_power_retry or args.actuator_write_routing
    args.actuator_shutdown_retry = args.actuator_shutdown_retry or args.actuator_power_retry
    args.actuator_release_retry = args.actuator_release_retry or args.actuator_shutdown_retry
    args.actuator_acquire_retry = args.actuator_acquire_retry or args.actuator_release_retry
    args.eeprom_power_decode = args.eeprom_power_decode or args.actuator_acquire_retry
    args.eeprom_command_snapshot = args.eeprom_command_snapshot or args.eeprom_power_decode
    args.eeprom_packet_snapshot = args.eeprom_packet_snapshot or args.eeprom_command_snapshot
    args.eeprom_output_copy = args.eeprom_output_copy or args.eeprom_packet_snapshot
    args.eeprom_packet_routing = args.eeprom_packet_routing or args.eeprom_output_copy
    args.eeprom_write_payload = args.eeprom_write_payload or args.eeprom_packet_routing
    args.eeprom_command_bounds = args.eeprom_command_bounds or args.eeprom_write_payload
    args.eeprom_parser_unwind = args.eeprom_parser_unwind or args.eeprom_command_bounds
    args.eeprom_power_retry = args.eeprom_power_retry or args.eeprom_parser_unwind
    args.eeprom_shutdown_retry = args.eeprom_shutdown_retry or args.eeprom_power_retry
    args.eeprom_acquire_retry = args.eeprom_acquire_retry or args.eeprom_shutdown_retry
    args.peer_acquire_capture = args.peer_acquire_capture or args.eeprom_acquire_retry
    args.sensor_release_retry = args.sensor_release_retry or args.peer_acquire_capture
    args.sensor_acquire_retry = args.sensor_acquire_retry or args.sensor_release_retry
    args.sensor_fsin_irq = args.sensor_fsin_irq or args.sensor_acquire_retry
    args.sensor_io_unwind = args.sensor_io_unwind or args.sensor_fsin_irq
    args.sensor_acquire_unwind = args.sensor_acquire_unwind or args.sensor_io_unwind
    args.memento_capture = args.memento_capture or args.sensor_acquire_unwind
    args.memento_flash = args.memento_flash or args.memento_capture
    args.memento_eeprom = args.memento_eeprom or args.memento_flash
    args.memento_ois = args.memento_ois or args.memento_eeprom
    args.memento_actuator = args.memento_actuator or args.memento_ois
    args.memento_mono = args.memento_mono or args.memento_actuator
    args.memento_sensor = args.memento_sensor or args.memento_mono
    args.csiphy_rollback = args.csiphy_rollback or args.memento_sensor
    args.memento_node = args.memento_node or args.csiphy_rollback
    args.memento_ledger = args.memento_ledger or args.memento_node
    args.subdevice_media = args.subdevice_media or args.memento_ledger
    args.subdevice_lifetime = args.subdevice_lifetime or args.subdevice_media
    args.cci_ops = args.cci_ops or args.subdevice_lifetime
    args.hub_irq = args.hub_irq or args.cci_ops
    args.hub_registration = args.hub_registration or args.hub_irq
    args.hub_dispatch = args.hub_dispatch or args.hub_registration
    args.hub_fops = args.hub_fops or args.hub_dispatch
    args.hub_cleanup = args.hub_cleanup or args.hub_fops
    args.hub_resources = args.hub_resources or args.hub_cleanup
    args.hub_subscription_callbacks = args.hub_subscription_callbacks or args.hub_resources
    hub_subscriptions = args.hub_subscriptions or args.hub_subscription_callbacks
    hub_ioctl = args.hub_ioctl or hub_subscriptions
    hub_events = args.hub_events or hub_ioctl
    hub_file = args.hub_file or hub_events
    hub_registry = args.hub_registry or hub_file
    hub_relay = args.hub_relay or hub_registry
    sensor_hook = args.sensor_hook or hub_relay
    label = 'kernel-camera-hub-subscription-callbacks' if args.hub_subscription_callbacks else ('kernel-camera-hub-subscriptions' if hub_subscriptions else ('kernel-camera-hub-ioctl' if hub_ioctl else ('kernel-camera-hub-events' if hub_events else ('kernel-camera-hub-file' if hub_file else ('kernel-camera-hub-registry' if hub_registry else ('kernel-camera-hub-relay' if hub_relay else ('kernel-sensor-mono-hook' if sensor_hook else 'kernel-virtual-mono')))))))
    root = Path(__file__).resolve().parent.parent
    if args.hub_resources:
        label = 'kernel-camera-hub-resources'
    if args.hub_cleanup:
        label = 'kernel-camera-hub-cleanup'
    if args.hub_fops:
        label = 'kernel-camera-hub-fops'
    if args.hub_dispatch:
        label = 'kernel-camera-hub-dispatch'
    if args.hub_registration:
        label = 'kernel-camera-hub-registration'
    if args.hub_irq:
        label = 'kernel-camera-hub-irq'
    if args.cci_ops:
        label = 'kernel-camera-cci-ops'
    if args.subdevice_lifetime:
        label = 'kernel-camera-subdevice-lifetime'
    if args.subdevice_media:
        label = 'kernel-camera-subdevice-media'
    if args.memento_ledger:
        label = 'kernel-camera-memento-ledger'
    if args.memento_node:
        label = 'kernel-camera-memento-node'
    if args.csiphy_rollback:
        label = 'kernel-camera-csiphy-rollback'
    if args.memento_sensor:
        label = 'kernel-camera-memento-sensor'
    if args.memento_mono:
        label = 'kernel-camera-memento-mono'
    if args.memento_actuator:
        label = 'kernel-camera-memento-actuator'
    if args.memento_ois:
        label = 'kernel-camera-memento-ois'
    if args.memento_eeprom:
        label = 'kernel-camera-memento-eeprom'
    if args.memento_flash:
        label = 'kernel-camera-memento-flash'
    if args.memento_capture:
        label = 'kernel-camera-memento-capture'
    if args.sensor_acquire_unwind:
        label = 'kernel-camera-sensor-acquire-unwind'
    if args.sensor_io_unwind:
        label = 'kernel-camera-sensor-io-unwind'
    if args.sensor_fsin_irq:
        label = 'kernel-camera-sensor-fsin-irq'
    if args.sensor_acquire_retry:
        label = 'kernel-camera-sensor-acquire-retry'
    if args.sensor_release_retry:
        label = 'kernel-camera-sensor-release-retry'
    if args.peer_acquire_capture:
        label = 'kernel-camera-peer-acquire-capture'
    if args.eeprom_acquire_retry:
        label = 'kernel-camera-eeprom-acquire-retry'
    if args.eeprom_shutdown_retry:
        label = 'kernel-camera-eeprom-shutdown-retry'
    if args.eeprom_power_retry:
        label = 'kernel-camera-eeprom-power-retry'
    if args.eeprom_parser_unwind:
        label = 'kernel-camera-eeprom-parser-unwind'
    if args.eeprom_command_bounds:
        label = 'kernel-camera-eeprom-command-bounds'
    if args.eeprom_write_payload:
        label = 'kernel-camera-eeprom-write-payload'
    if args.eeprom_packet_routing:
        label = 'kernel-camera-eeprom-packet-routing'
    if args.eeprom_output_copy:
        label = 'kernel-camera-eeprom-output-copy'
    if args.eeprom_packet_snapshot:
        label = 'kernel-camera-eeprom-packet-snapshot'
    if args.eeprom_command_snapshot:
        label = 'kernel-camera-eeprom-command-snapshot'
    if args.eeprom_power_decode:
        label = 'kernel-camera-eeprom-power-decode'
    if args.actuator_acquire_retry:
        label = 'kernel-camera-actuator-acquire-retry'
    if args.actuator_release_retry:
        label = 'kernel-camera-actuator-release-retry'
    if args.actuator_shutdown_retry:
        label = 'kernel-camera-actuator-shutdown-retry'
    if args.actuator_power_retry:
        label = 'kernel-camera-actuator-power-retry'
    if args.actuator_write_routing:
        label = 'kernel-camera-actuator-write-routing'
    if args.actuator_request_cleanup:
        label = 'kernel-camera-actuator-request-cleanup'
    if args.actuator_callback_gates:
        label = 'kernel-camera-actuator-callback-gates'
    if args.camera_callback_borrow:
        label = 'kernel-camera-callback-borrow'
    if args.v4l2_media_pin:
        label = 'kernel-v4l2-media-pin'
    if args.v4l2_lifetime:
        label = 'kernel-v4l2-lifetime'
    if args.actuator_probe_publication:
        label = 'kernel-actuator-probe-publication'
    if args.crm_ops_snapshot:
        label = 'kernel-crm-ops-snapshot'
    if args.crm_flush_result:
        label = 'kernel-crm-flush-result'
    if args.shared_pinctrl_state:
        label = 'shared-pinctrl-state'
    if args.shared_gpio_lock:
        label = 'shared-gpio-lock'
    if args.camera_power_down_phases:
        label = 'camera-power-down-phases'
    if args.camera_power_up_unwind:
        label = 'camera-power-up-unwind'
    if args.isp_bufdone:
        label = 'isp-bufdone'
    if args.cdm_kthread_pool:
        label = 'cdm-kthread-pool'
    if args.binder_extensions:
        label = 'binder-extensions'
    if args.kgsl_ctxprio:
        label = 'kgsl-ctxprio'
    if args.display_temp_pwm:
        label = 'display-temp-pwm'
    # batch stages are listed in kernel-recovery/batch-20261008.json; a file touched by a later
    # batch stage supersedes the install-time hash recorded by an earlier stage
    batch, superseded = [], set()
    if args.batch_20261008:
        label = 'batch-20261008'
        batch = json.loads((root / 'kernel-recovery/batch-20261008.json').read_text())['stages']
        for stage in batch:
            stage_hooks = json.loads((root / stage['hooks']).read_text())
            superseded.update(stage_hooks['sources'])
    target = root / 'outputs' / (label + ('-20261008' if args.kgsl_ctxprio else '-20261004' if args.v4l2_media_pin else '-20261003'))
    build = json.loads((OUT / (label + '-build-result.json')).read_text())
    tests = json.loads((OUT / 'virtual-mono-tests/result.json').read_text())
    if build['exit_code'] or tests['exit_code']:
        raise RuntimeError('Build/tests did not succeed')
    relative = 'techpack/camera/drivers/cam_core/pico_virtual_mono.c'
    if sha(SOURCE / relative) != tests['source_sha256']:
        raise RuntimeError('Source changed since tests')
    new_paths = [relative, 'techpack/camera/drivers/cam_core/pico_virtual_mono.h']
    patch_paths = ['techpack/camera/drivers/cam_core/Makefile', *new_paths]
    sensor_tests = None
    init_order = None
    if sensor_hook:
        sensor_tests = json.loads((OUT / 'sensor-mono-hook-tests/result.json').read_text())
        if sensor_tests['exit_code']:
            raise RuntimeError('Sensor tests failed')
        for name, digest in sensor_tests['sources'].items():
            if sha(SOURCE / name) != digest:
                raise RuntimeError('Source changed since sensor tests')
        patch_paths.append('techpack/camera/drivers/cam_sensor_module/cam_sensor/cam_sensor_dev.c')
        symbols = {name: int(address, 16) for address, _, name in
                   (line.split() for line in (OUT / 'obj/System.map').read_text().splitlines())}
        order = ['__initcall_virtual_driver_init6', '__initcall_cam_sensor_driver_init6',
                 '__initcall_cam_req_mgr_late_init7']
        init_order = {name: hex(symbols[name]) for name in order}
        if not symbols[order[0]] < symbols[order[1]] < symbols[order[2]]:
            raise RuntimeError('Unexpected initcall order')
    hub_tests = None
    if hub_relay:
        hub_tests = json.loads((OUT / 'camera-hub-relay-tests/result.json').read_text())
        hub_source = 'techpack/camera/drivers/cam_core/pico_camera_hub.c'
        if hub_tests['exit_code'] or sha(SOURCE / hub_source) != hub_tests['source_sha256']:
            raise RuntimeError('Hub relay tests failed or source changed')
        new_paths.extend([hub_source, 'techpack/camera/drivers/cam_core/pico_camera_hub.h'])
        patch_paths.extend(new_paths[-2:])
    registry_tests = None
    if hub_registry:
        registry_tests = json.loads((OUT / 'camera-hub-registry-tests/result.json').read_text())
        registry_source = 'techpack/camera/drivers/cam_core/pico_camera_hub_registry.c'
        if registry_tests['exit_code'] or sha(SOURCE / registry_source) != registry_tests['source_sha256']:
            raise RuntimeError('Registry tests failed or source changed')
        new_paths.append(registry_source)
        patch_paths.append(registry_source)
    file_tests = None
    if hub_file:
        file_tests = json.loads((OUT / 'camera-hub-file-tests/result.json').read_text())
        file_source = 'techpack/camera/drivers/cam_core/pico_camera_hub_file.c'
        file_header = 'techpack/camera/drivers/cam_core/pico_camera_hub_file.h'
        if file_tests['exit_code'] or sha(SOURCE / file_source) != file_tests['source_sha256'] or sha(SOURCE / file_header) != file_tests['header_sha256']:
            raise RuntimeError('File worker tests failed or source/header changed')
        new_paths.extend([file_source, file_header])
        patch_paths.extend([file_source, file_header])
    event_tests = None
    if hub_events:
        event_tests = json.loads((OUT / 'camera-hub-events-tests/result.json').read_text())
        if event_tests['exit_code']:
            raise RuntimeError('Event tests failed')
        for name, digest in event_tests['sources'].items():
            if sha(SOURCE / name) != digest:
                raise RuntimeError('Source changed since event tests: ' + name)
        event_source = 'techpack/camera/drivers/cam_core/pico_camera_hub_events.c'
        new_paths.append(event_source)
        patch_paths.append(event_source)
    ioctl_tests = None
    if hub_ioctl:
        ioctl_tests = json.loads((OUT / 'camera-hub-ioctl-tests/result.json').read_text())
        if ioctl_tests['exit_code']:
            raise RuntimeError('Ioctl tracking tests failed')
        for name, digest in ioctl_tests['sources'].items():
            if sha(SOURCE / name) != digest:
                raise RuntimeError('Source changed since ioctl tests: ' + name)
        ioctl_paths = ['techpack/camera/drivers/cam_core/pico_camera_hub_ioctl.c',
                       'techpack/camera/drivers/cam_core/pico_camera_hub_ioctl.h']
        new_paths.extend(ioctl_paths)
        patch_paths.extend(ioctl_paths)
    subscription_tests = None
    if hub_subscriptions:
        subscription_tests = json.loads((OUT / 'camera-hub-subscriptions-tests/result.json').read_text())
        if subscription_tests['exit_code']:
            raise RuntimeError('Subscription count tests failed')
        for name, digest in subscription_tests['sources'].items():
            if sha(SOURCE / name) != digest:
                raise RuntimeError('Source changed since subscription tests: ' + name)
        subscription_paths = ['techpack/camera/drivers/cam_core/pico_camera_hub_subscriptions.c',
                              'techpack/camera/drivers/cam_core/pico_camera_hub_subscriptions.h']
        new_paths.extend(subscription_paths)
        patch_paths.extend(subscription_paths)
    callback_tests = None
    if args.hub_subscription_callbacks:
        callback_tests = json.loads((OUT / 'camera-hub-subscription-callbacks-tests/result.json').read_text())
        if callback_tests['exit_code']:
            raise RuntimeError('Subscription callback tests failed')
        for name, digest in callback_tests['sources'].items():
            if sha(SOURCE / name) != digest:
                raise RuntimeError('Source changed since subscription callback tests: ' + name)
        callback_paths = ['techpack/camera/drivers/cam_core/pico_camera_hub_subscription_callbacks.c',
                          'techpack/camera/drivers/cam_core/pico_camera_hub_subscription_callbacks.h']
        new_paths.extend(callback_paths)
        patch_paths.extend(callback_paths)
    if args.hub_resources:
        resource_paths = ['techpack/camera/drivers/cam_core/pico_camera_hub_resources.c',
                          'techpack/camera/drivers/cam_core/pico_camera_hub_resources.h']
        for name in resource_paths:
            if name not in ioctl_tests['sources']:
                raise RuntimeError('Resource sources not covered by ioctl tests')
        new_paths.extend(resource_paths)
        patch_paths.extend(resource_paths)
    cleanup_tests = None
    if args.hub_cleanup:
        cleanup_tests = json.loads((OUT / 'camera-hub-cleanup-tests/result.json').read_text())
        if cleanup_tests['exit_code']:
            raise RuntimeError('Cleanup tests failed')
        for name, digest in cleanup_tests['sources'].items():
            if sha(SOURCE / name) != digest:
                raise RuntimeError('Source changed since cleanup tests: ' + name)
        cleanup_paths = ['techpack/camera/drivers/cam_core/pico_camera_hub_cleanup.c',
                         'techpack/camera/drivers/cam_core/pico_camera_hub_cleanup.h']
        new_paths.extend(cleanup_paths)
        patch_paths.extend(cleanup_paths)
    fops_tests = None
    if args.hub_fops:
        fops_tests = json.loads((OUT / 'camera-hub-fops-tests/result.json').read_text())
        if fops_tests['exit_code']:
            raise RuntimeError('Fops tests failed')
        for name, digest in fops_tests['sources'].items():
            if sha(SOURCE / name) != digest:
                raise RuntimeError('Source changed since fops tests: ' + name)
        fops_paths = ['techpack/camera/drivers/cam_core/pico_camera_hub_fops.c',
                      'techpack/camera/drivers/cam_core/pico_camera_hub_fops.h']
        new_paths.extend(fops_paths)
        patch_paths.extend(fops_paths)
    dispatch_tests = None
    if args.hub_dispatch:
        dispatch_tests = json.loads((OUT / 'camera-hub-dispatch-tests/result.json').read_text())
        if dispatch_tests['exit_code']:
            raise RuntimeError('Dispatch tests failed')
        for name, digest in dispatch_tests['sources'].items():
            if sha(SOURCE / name) != digest:
                raise RuntimeError('Source changed since dispatch tests: ' + name)
        dispatch_paths = ['techpack/camera/drivers/cam_core/pico_camera_hub_dispatch.c',
                          'techpack/camera/drivers/cam_core/pico_camera_hub_dispatch.h']
        new_paths.extend(dispatch_paths)
        patch_paths.extend(dispatch_paths + ['techpack/camera/drivers/cam_req_mgr/cam_req_mgr_dev.c',
                                           'techpack/camera/drivers/cam_sync/cam_sync.c'])
    registration_tests = None
    registration_hooks = None
    if args.hub_registration:
        registration_tests = json.loads((OUT / 'camera-hub-registration-tests/result.json').read_text())
        if registration_tests['exit_code']:
            raise RuntimeError('Registration tests failed')
        for name, digest in registration_tests['sources'].items():
            if sha(SOURCE / name) != digest:
                raise RuntimeError('Source changed since registration tests: ' + name)
        registration_hooks = json.loads((root / 'reports/kernel-source/recovery-20261003/camera-hub-registration-hooks.json').read_text())
        if args.hub_irq:
            irq_hooks = json.loads((root / 'reports/kernel-source/recovery-20261003/camera-hub-irq-hooks.json').read_text())
            registration_hooks['sources'].update(irq_hooks['sources'])
        for name, digest in registration_hooks['sources'].items():
            if sha(SOURCE / name) != digest:
                raise RuntimeError('Native registration hooks changed: ' + name)
        registration_paths = ['techpack/camera/drivers/cam_core/pico_camera_hub_registration.c',
                              'techpack/camera/drivers/cam_core/pico_camera_hub_registration.h']
        new_paths.extend(registration_paths)
        patch_paths.extend(registration_paths)
    irq_tests = None
    if args.hub_irq:
        irq_tests = json.loads((OUT / 'camera-hub-irq-tests/result.json').read_text())
        if irq_tests['exit_code']:
            raise RuntimeError('IRQ tests failed')
        for name, digest in irq_tests['sources'].items():
            if sha(SOURCE / name) != digest:
                raise RuntimeError('Source changed since IRQ tests: ' + name)
        irq_paths = ['techpack/camera/drivers/cam_core/pico_camera_hub_irq.c',
                     'techpack/camera/drivers/cam_core/pico_camera_hub_irq.h']
        new_paths.extend(irq_paths)
        patch_paths.extend(irq_paths + ['techpack/camera/drivers/cam_sync/cam_sync_util.c'])
    cci_tests = None
    if args.cci_ops:
        cci_tests = json.loads((OUT / 'camera-cci-ops-tests/result.json').read_text())
        if cci_tests['exit_code']:
            raise RuntimeError('CCI ops tests failed')
        for name, digest in cci_tests['sources'].items():
            if sha(SOURCE / name) != digest:
                raise RuntimeError('Source changed since CCI ops tests: ' + name)
        patch_paths.append('techpack/camera/drivers/cam_sensor_module/cam_cci/cam_cci_dev.c')
    if args.subdevice_lifetime:
        lifetime_tests = json.loads((OUT / 'camera-subdevice-lifetime-tests/result.json').read_text())
        if lifetime_tests['exit_code']:
            raise RuntimeError('Subdevice lifetime tests failed')
        for name, digest in lifetime_tests['sources'].items():
            if sha(SOURCE / name) != digest:
                raise RuntimeError('Source changed since subdevice lifetime tests: ' + name)
        lifetime_paths = ['techpack/camera/drivers/cam_core/pico_camera_hub_subdevice.c',
                          'techpack/camera/drivers/cam_core/pico_camera_hub_subdevice.h']
        new_paths.extend(lifetime_paths)
        patch_paths.extend(lifetime_paths)
    if args.memento_ledger:
        memento_tests = json.loads((OUT / 'camera-memento-tests/result.json').read_text())
        if memento_tests['exit_code']:
            raise RuntimeError('Memento ledger tests failed')
        for name, digest in memento_tests['sources'].items():
            if sha(SOURCE / name) != digest:
                raise RuntimeError('Source changed since memento tests: ' + name)
        memento_paths = ['techpack/camera/drivers/cam_core/pico_camera_memento.c',
                         'techpack/camera/drivers/cam_core/pico_camera_memento.h']
        new_paths.extend(memento_paths)
        patch_paths.extend(memento_paths)
    if args.memento_node:
        node_tests = json.loads((OUT / 'camera-memento-node-tests/result.json').read_text())
        if node_tests['exit_code']:
            raise RuntimeError('Memento node adapter tests failed')
        for name, digest in node_tests['sources'].items():
            if sha(SOURCE / name) != digest:
                raise RuntimeError('Source changed since node adapter tests: ' + name)
        node_paths = ['techpack/camera/drivers/cam_core/pico_camera_memento_node.h',
                      'techpack/camera/drivers/cam_core/pico_camera_memento_node.inc']
        new_paths.extend(node_paths)
        patch_paths.extend(node_paths + ['techpack/camera/drivers/cam_core/cam_node.c'])
    if args.csiphy_rollback:
        csiphy_tests = json.loads((OUT / 'csiphy-rollback-tests/result.json').read_text())
        if csiphy_tests['exit_code']:
            raise RuntimeError('CSIPHY rollback tests failed')
        for name, digest in csiphy_tests['sources'].items():
            if sha(SOURCE / name) != digest:
                raise RuntimeError('Source changed since CSIPHY rollback tests: ' + name)
        csiphy_dir = 'techpack/camera/drivers/cam_sensor_module/cam_csiphy/'
        new_paths.append(csiphy_dir + 'pico_csiphy_rollback.inc')
        patch_paths.extend([csiphy_dir + name for name in ['pico_csiphy_rollback.inc', 'cam_csiphy_core.c', 'cam_csiphy_core.h']])
    if args.memento_sensor:
        sensor_adapter_tests = json.loads((OUT / 'memento-sensor-tests/result.json').read_text())
        if sensor_adapter_tests['exit_code']:
            raise RuntimeError('Sensor rollback tests failed')
        for name, digest in sensor_adapter_tests['sources'].items():
            if sha(SOURCE / name) != digest:
                raise RuntimeError('Source changed since sensor rollback tests: ' + name)
        sensor_dir = 'techpack/camera/drivers/cam_sensor_module/cam_sensor/'
        sensor_adapter_paths = [sensor_dir + name for name in ['pico_memento_sensor.h', 'pico_memento_sensor.inc']]
        new_paths.extend(sensor_adapter_paths)
        patch_paths.extend(sensor_adapter_paths + [sensor_dir + 'cam_sensor_core.c'])
    if args.memento_mono:
        if not tests.get('memento_mono_rollback_tested') or tests.get('mono_release_opcode') != 0x106:
            raise RuntimeError('Mono memento and release ABI evidence missing')
        if sha(SOURCE / tests['uapi_source']) != tests['uapi_source_sha256']:
            raise RuntimeError('Mono UAPI source changed after test')
    if args.memento_actuator:
        actuator_tests = json.loads((OUT / 'memento-actuator-tests/result.json').read_text())
        if actuator_tests['exit_code']:
            raise RuntimeError('Actuator rollback tests failed')
        for name, digest in actuator_tests['sources'].items():
            if sha(SOURCE / name) != digest:
                raise RuntimeError('Source changed since actuator rollback tests: ' + name)
        actuator_dir = 'techpack/camera/drivers/cam_sensor_module/cam_actuator/'
        actuator_paths = [actuator_dir + name for name in ['pico_memento_actuator.h', 'pico_memento_actuator.inc']]
        new_paths.extend(actuator_paths)
        patch_paths.extend(actuator_paths + [actuator_dir + 'cam_actuator_core.c'])
    if args.memento_ois:
        ois_tests = json.loads((OUT / 'memento-ois-tests/result.json').read_text())
        if ois_tests['exit_code']:
            raise RuntimeError('OIS rollback tests failed')
        for name, digest in ois_tests['sources'].items():
            if sha(SOURCE / name) != digest:
                raise RuntimeError('Source changed since OIS rollback tests: ' + name)
        ois_dir = 'techpack/camera/drivers/cam_sensor_module/cam_ois/'
        ois_paths = [ois_dir + name for name in ['pico_memento_ois.h', 'pico_memento_ois.inc']]
        new_paths.extend(ois_paths)
        patch_paths.extend(ois_paths + [ois_dir + 'cam_ois_core.c'])
    if args.memento_eeprom:
        eeprom_tests = json.loads((OUT / 'memento-eeprom-tests/result.json').read_text())
        if eeprom_tests['exit_code']:
            raise RuntimeError('EEPROM rollback tests failed')
        for name, digest in eeprom_tests['sources'].items():
            if sha(SOURCE / name) != digest:
                raise RuntimeError('Source changed since EEPROM rollback tests: ' + name)
        eeprom_dir = 'techpack/camera/drivers/cam_sensor_module/cam_eeprom/'
        eeprom_paths = [eeprom_dir + name for name in ['pico_memento_eeprom.h', 'pico_memento_eeprom.inc']]
        new_paths.extend(eeprom_paths)
        patch_paths.extend(eeprom_paths + [eeprom_dir + 'cam_eeprom_core.c'])
    if args.memento_flash:
        flash_tests = json.loads((OUT / 'memento-flash-tests/result.json').read_text())
        if flash_tests['exit_code']:
            raise RuntimeError('Flash rollback tests failed')
        for name, digest in flash_tests['sources'].items():
            if sha(SOURCE / name) != digest:
                raise RuntimeError('Source changed since Flash rollback tests: ' + name)
        flash_dir = 'techpack/camera/drivers/cam_sensor_module/cam_flash/'
        flash_paths = [flash_dir + name for name in ['pico_memento_flash.h', 'pico_memento_flash.inc']]
        new_paths.extend(flash_paths)
        patch_paths.extend(flash_paths + [flash_dir + 'cam_flash_dev.c'])
    if args.memento_capture:
        capture_tests = json.loads((OUT / 'memento-capture-tests/result.json').read_text())
        if capture_tests['exit_code']:
            raise RuntimeError('Memento capture tests failed')
        for name, digest in capture_tests['sources'].items():
            if sha(SOURCE / name) != digest:
                raise RuntimeError('Source changed since capture tests: ' + name)
        capture_paths = ['techpack/camera/drivers/cam_core/pico_camera_memento_capture.' + suffix for suffix in ['c', 'h']]
        new_paths.extend(capture_paths)
        patch_paths.extend(capture_paths)
    if args.sensor_io_unwind:
        io_unwind_tests = json.loads((OUT / 'sensor-io-unwind-tests/result.json').read_text())
        if io_unwind_tests['exit_code']:
            raise RuntimeError('Sensor I/O unwind tests failed')
        for name, digest in io_unwind_tests['sources'].items():
            if sha(SOURCE / name) != digest:
                raise RuntimeError('Source changed since sensor I/O unwind tests: ' + name)
    if args.sensor_fsin_irq:
        fsin_tests = json.loads((OUT / 'sensor-fsin-irq-tests/result.json').read_text())
        if fsin_tests['exit_code']:
            raise RuntimeError('FSIN IRQ tests failed')
        for name, digest in fsin_tests['sources'].items():
            if sha(SOURCE / name) != digest:
                raise RuntimeError('Source changed since FSIN IRQ tests: ' + name)
        fsin_dir = 'techpack/camera/drivers/cam_sensor_module/cam_sensor/'
        new_paths.append(fsin_dir + 'pico_sensor_fsin_irq.inc')
        patch_paths.extend([fsin_dir + 'pico_sensor_fsin_irq.inc', fsin_dir + 'cam_sensor_dev.h'])
    if args.sensor_acquire_retry:
        acquire_retry_tests = json.loads((OUT / 'sensor-acquire-retry-tests/result.json').read_text())
        if acquire_retry_tests['exit_code']:
            raise RuntimeError('Native acquire retry tests failed')
        for name, digest in acquire_retry_tests['sources'].items():
            if sha(SOURCE / name) != digest:
                raise RuntimeError('Source changed since acquire retry tests: ' + name)
        retry_dir = 'techpack/camera/drivers/cam_sensor_module/cam_sensor/'
        retry_paths = [retry_dir + 'pico_sensor_acquire_unwind.' + suffix for suffix in ['inc', 'h']]
        new_paths.extend(retry_paths)
        patch_paths.extend(retry_paths)
    if args.peer_acquire_capture:
        peer_capture_tests = json.loads((OUT / 'peer-acquire-capture-tests/result.json').read_text())
        if peer_capture_tests['exit_code']:
            raise RuntimeError('Peer acquire capture tests failed')
        for name, digest in peer_capture_tests['sources'].items():
            if sha(SOURCE / name) != digest:
                raise RuntimeError('Source changed since peer capture tests: ' + name)
    if args.eeprom_acquire_retry:
        eeprom_retry_tests = json.loads((OUT / 'eeprom-acquire-retry-tests/result.json').read_text())
        if eeprom_retry_tests['exit_code']:
            raise RuntimeError('EEPROM acquire retry tests failed')
        for name, digest in eeprom_retry_tests['sources'].items():
            if sha(SOURCE / name) != digest:
                raise RuntimeError('Source changed since EEPROM retry tests: ' + name)
        eeprom_dir = 'techpack/camera/drivers/cam_sensor_module/cam_eeprom/'
        retry_paths = [eeprom_dir + 'pico_eeprom_acquire_unwind.' + e for e in ['inc', 'h']]
        new_paths.extend(retry_paths)
        patch_paths.extend([*retry_paths, eeprom_dir + 'cam_eeprom_dev.h'])
    if args.eeprom_shutdown_retry:
        eeprom_shutdown_tests = json.loads((OUT / 'eeprom-shutdown-retry-tests/result.json').read_text())
        if eeprom_shutdown_tests['exit_code']:
            raise RuntimeError('EEPROM shutdown retry tests failed')
        for name, digest in eeprom_shutdown_tests['sources'].items():
            if sha(SOURCE / name) != digest:
                raise RuntimeError('Source changed since EEPROM shutdown tests: ' + name)
    if args.eeprom_power_retry:
        eeprom_power_tests = json.loads((OUT / 'eeprom-power-retry-tests/result.json').read_text())
        if eeprom_power_tests['exit_code']:
            raise RuntimeError('EEPROM power retry tests failed')
        for name, digest in eeprom_power_tests['sources'].items():
            if sha(SOURCE / name) != digest:
                raise RuntimeError('Source changed since EEPROM power tests: ' + name)
    if args.eeprom_parser_unwind:
        eeprom_parser_tests = json.loads((OUT / 'eeprom-parser-unwind-tests/result.json').read_text())
        if eeprom_parser_tests['exit_code']:
            raise RuntimeError('EEPROM parser unwind tests failed')
        for name, digest in eeprom_parser_tests['sources'].items():
            if sha(SOURCE / name) != digest:
                raise RuntimeError('Source changed since EEPROM parser tests: ' + name)
    if args.eeprom_command_bounds:
        eeprom_command_tests = json.loads((OUT / 'eeprom-command-bounds-tests/result.json').read_text())
        if eeprom_command_tests['exit_code']:
            raise RuntimeError('EEPROM command bounds tests failed')
        for name, digest in eeprom_command_tests['sources'].items():
            if sha(SOURCE / name) != digest:
                raise RuntimeError('Source changed since EEPROM command tests: ' + name)
    if args.eeprom_write_payload:
        eeprom_payload_tests = json.loads((OUT / 'eeprom-write-payload-tests/result.json').read_text())
        if eeprom_payload_tests['exit_code']:
            raise RuntimeError('EEPROM write payload tests failed')
        for name, digest in eeprom_payload_tests['sources'].items():
            if sha(SOURCE / name) != digest:
                raise RuntimeError('Source changed since EEPROM payload tests: ' + name)
    if args.eeprom_output_copy:
        mem_copy_tests = json.loads((OUT / 'mem-output-copy-tests/result.json').read_text())
        if mem_copy_tests['exit_code']:
            raise RuntimeError('Memory output copy tests failed')
        for name, digest in mem_copy_tests['sources'].items():
            if sha(SOURCE / name) != digest:
                raise RuntimeError('Source changed since memory copy tests: ' + name)
        mem_dir = 'techpack/camera/drivers/cam_req_mgr/'
        copy_paths = [mem_dir + 'pico_mem_copy.' + e for e in ['inc', 'h']]
        new_paths.extend(copy_paths)
        patch_paths.extend([*copy_paths, mem_dir + 'cam_mem_mgr.c'])
    if args.eeprom_power_decode:
        power_decode_tests = json.loads((OUT / 'eeprom-power-decode-tests/result.json').read_text())
        if power_decode_tests['exit_code']:
            raise RuntimeError('EEPROM power decoder tests failed')
        for name, digest in power_decode_tests['sources'].items():
            if sha(SOURCE / name) != digest:
                raise RuntimeError('Source changed since power decoder tests: ' + name)
        power_adapter = 'techpack/camera/drivers/cam_sensor_module/cam_eeprom/pico_eeprom_power_decode.inc'
        new_paths.append(power_adapter)
        patch_paths.append(power_adapter)
    if args.actuator_acquire_retry:
        actuator_retry_tests = json.loads((OUT / 'actuator-acquire-retry-tests/result.json').read_text())
        if actuator_retry_tests['exit_code']:
            raise RuntimeError('Actuator acquire retry tests failed')
        for name, digest in actuator_retry_tests['sources'].items():
            if sha(SOURCE / name) != digest:
                raise RuntimeError('Source changed since actuator retry tests: ' + name)
        actuator_dir = 'techpack/camera/drivers/cam_sensor_module/cam_actuator/'
        retry_paths = [actuator_dir + 'pico_actuator_acquire_unwind.' + e for e in ['inc', 'h']]
        new_paths.extend(retry_paths)
        patch_paths.extend([*retry_paths, actuator_dir + 'cam_actuator_dev.h'])
    if args.actuator_release_retry:
        actuator_release_tests = json.loads((OUT / 'actuator-release-retry-tests/result.json').read_text())
        if actuator_release_tests['exit_code']:
            raise RuntimeError('Actuator release retry tests failed')
        for name, digest in actuator_release_tests['sources'].items():
            if sha(SOURCE / name) != digest:
                raise RuntimeError('Source changed since actuator release tests: ' + name)
    if args.actuator_shutdown_retry:
        actuator_shutdown_tests = json.loads((OUT / 'actuator-shutdown-retry-tests/result.json').read_text())
        if actuator_shutdown_tests['exit_code']:
            raise RuntimeError('Actuator shutdown retry tests failed')
        for name, digest in actuator_shutdown_tests['sources'].items():
            if sha(SOURCE / name) != digest:
                raise RuntimeError('Source changed since actuator shutdown tests: ' + name)
    if args.actuator_power_retry:
        actuator_power_tests = json.loads((OUT / 'actuator-power-retry-tests/result.json').read_text())
        if actuator_power_tests['exit_code']:
            raise RuntimeError('Actuator power retry tests failed')
        for name, digest in actuator_power_tests['sources'].items():
            if sha(SOURCE / name) != digest:
                raise RuntimeError('Source changed since actuator power tests: ' + name)
    if args.actuator_write_routing:
        actuator_write_tests = json.loads((OUT / 'actuator-write-routing-tests/result.json').read_text())
        if actuator_write_tests['exit_code']:
            raise RuntimeError('Actuator write routing tests failed')
        for name, digest in actuator_write_tests['sources'].items():
            if sha(SOURCE / name) != digest:
                raise RuntimeError('Source changed since actuator write routing tests: ' + name)
    if args.actuator_request_cleanup:
        actuator_request_tests = json.loads((OUT / 'actuator-request-cleanup-tests/result.json').read_text())
        if actuator_request_tests['exit_code']:
            raise RuntimeError('Actuator request cleanup tests failed')
        for name, digest in actuator_request_tests['sources'].items():
            if sha(SOURCE / name) != digest:
                raise RuntimeError('Source changed since actuator request cleanup tests: ' + name)
    if args.actuator_callback_gates:
        actuator_callback_tests = json.loads((OUT / 'actuator-callback-gates-tests/result.json').read_text())
        if actuator_callback_tests['exit_code']:
            raise RuntimeError('Actuator callback gate tests failed')
        for name, digest in actuator_callback_tests['sources'].items():
            if sha(SOURCE / name) != digest:
                raise RuntimeError('Source changed since actuator callback gate tests: ' + name)
    if args.camera_callback_borrow:
        callback_borrow_tests = json.loads((OUT / 'camera-callback-borrow-tests/result.json').read_text())
        if callback_borrow_tests['exit_code']:
            raise RuntimeError('Camera callback borrow tests failed')
        for name, digest in callback_borrow_tests['sources'].items():
            if sha(SOURCE / name) != digest:
                raise RuntimeError('Source changed since camera callback borrow tests: ' + name)
        for name in ['techpack/camera/drivers/cam_req_mgr/cam_req_mgr_util.c', 'techpack/camera/drivers/cam_req_mgr/cam_req_mgr_util.h']:
            if name not in patch_paths:
                patch_paths.append(name)
    if args.v4l2_media_pin:
        media_pin_tests = json.loads((OUT / 'v4l2-media-pin-tests/result.json').read_text())
        if media_pin_tests['exit_code']:
            raise RuntimeError('V4L2 media pin tests failed')
        for name, digest in media_pin_tests['sources'].items():
            if sha(SOURCE / name) != digest:
                raise RuntimeError('Source changed since V4L2 media pin tests: ' + name)
            if name not in patch_paths:
                patch_paths.append(name)
        new_paths.append('drivers/media/v4l2-core/pico-v4l2-media-pin.h')
    if args.v4l2_lifetime:
        lifetime_tests = json.loads((OUT / 'v4l2-lifetime-tests/result.json').read_text())
        if lifetime_tests['exit_code']:
            raise RuntimeError('V4L2 lifetime tests failed')
        for name, digest in lifetime_tests['sources'].items():
            if sha(SOURCE / name) != digest:
                raise RuntimeError('Source changed since V4L2 lifetime tests: ' + name)
            if name not in patch_paths:
                patch_paths.append(name)
        new_paths.extend(['drivers/media/v4l2-core/pico-v4l2-lifetime.inc', 'include/media/pico-v4l2-lifetime.h'])
    if args.actuator_probe_publication:
        probe_tests = json.loads((OUT / 'actuator-probe-publication-tests/result.json').read_text())
        if probe_tests['exit_code']:
            raise RuntimeError('Actuator probe publication tests failed')
        for name, digest in probe_tests['sources'].items():
            if sha(SOURCE / name) != digest:
                raise RuntimeError('Source changed since actuator probe tests: ' + name)
            if name not in patch_paths:
                patch_paths.append(name)
    if args.crm_ops_snapshot:
        crm_ops_tests = json.loads((OUT / 'crm-ops-snapshot-tests/result.json').read_text())
        if crm_ops_tests['exit_code']:
            raise RuntimeError('CRM ops snapshot tests failed')
        for name, digest in crm_ops_tests['sources'].items():
            if sha(SOURCE / name) != digest:
                raise RuntimeError('Source changed since CRM ops snapshot tests: ' + name)
        for name in ['techpack/camera/drivers/cam_req_mgr/cam_req_mgr_util.c', 'techpack/camera/drivers/cam_req_mgr/cam_req_mgr_util.h', 'techpack/camera/drivers/cam_req_mgr/cam_req_mgr_core.c']:
            if name not in patch_paths:
                patch_paths.append(name)
    if args.crm_flush_result:
        flush_result_tests = json.loads((OUT / 'crm-flush-result-tests/result.json').read_text())
        if flush_result_tests['exit_code']:
            raise RuntimeError('CRM flush result tests failed')
        for name, digest in flush_result_tests['sources'].items():
            if sha(SOURCE / name) != digest:
                raise RuntimeError('Source changed since CRM flush result tests: ' + name)
        flush_paths = ['techpack/camera/drivers/cam_req_mgr/' + name for name in ['cam_req_mgr_core.c', 'cam_req_mgr_workq.c', 'cam_req_mgr_workq.h', 'pico_crm_flush_result.inc']]
        new_paths.append(flush_paths[-1])
        for name in flush_paths:
            if name not in patch_paths:
                patch_paths.append(name)
    if args.shared_pinctrl_state:
        pinctrl_tests = json.loads((OUT / 'shared-pinctrl-state-tests/result.json').read_text())
        if pinctrl_tests['exit_code']:
            raise RuntimeError('Shared pinctrl state tests failed')
        for name, digest in pinctrl_tests['sources'].items():
            if sha(SOURCE / name) != digest:
                raise RuntimeError('Source changed since shared pinctrl state tests: ' + name)
            if name not in patch_paths:
                patch_paths.append(name)
    if args.shared_gpio_lock:
        gpio_tests = json.loads((OUT / 'shared-gpio-lock-tests/result.json').read_text())
        if gpio_tests['exit_code']:
            raise RuntimeError('Shared GPIO lock tests failed')
        for name, digest in gpio_tests['sources'].items():
            if sha(SOURCE / name) != digest:
                raise RuntimeError('Source changed since shared GPIO lock tests: ' + name)
            if name not in patch_paths:
                patch_paths.append(name)
    if args.camera_power_down_phases:
        power_phases_tests = json.loads((OUT / 'camera-power-down-phases-tests/result.json').read_text())
        if power_phases_tests['exit_code']:
            raise RuntimeError('Camera power-down phase tests failed')
        for name, digest in power_phases_tests['sources'].items():
            if sha(SOURCE / name) != digest:
                raise RuntimeError('Source changed since power-down phase tests: ' + name)
            if name not in patch_paths:
                patch_paths.append(name)
        new_paths.append('techpack/camera/drivers/cam_sensor_module/cam_sensor_utils/pico_camera_power_down.inc')
    if args.camera_power_up_unwind:
        power_up_tests = json.loads((OUT / 'camera-power-up-unwind-tests/result.json').read_text())
        if power_up_tests['exit_code']:
            raise RuntimeError('Camera power-up unwind tests failed')
        for name, digest in power_up_tests['sources'].items():
            if sha(SOURCE / name) != digest:
                raise RuntimeError('Source changed since power-up unwind tests: ' + name)
            if name not in patch_paths:
                patch_paths.append(name)
        new_paths.append('techpack/camera/drivers/cam_sensor_module/cam_sensor_utils/pico_camera_power_up.inc')
    if args.isp_bufdone:
        isp_tests = json.loads((OUT / 'isp-bufdone-tests/result.json').read_text())
        if isp_tests['exit_code']:
            raise RuntimeError('ISP buf-done tests failed')
        isp_hooks = json.loads((root / 'reports/kernel-source/recovery-20261004/isp-bufdone-hooks.json').read_text())
        for name, digest in list(isp_tests['sources'].items()) + list(isp_hooks['sources'].items()):
            if sha(SOURCE / name) != digest:
                raise RuntimeError('Source changed since ISP buf-done tests/install: ' + name)
            if name not in patch_paths:
                patch_paths.append(name)
    if args.cdm_kthread_pool:
        cdm_tests = json.loads((OUT / 'cdm-kthread-pool-tests/result.json').read_text())
        if cdm_tests['exit_code']:
            raise RuntimeError('CDM kthread pool tests failed')
        cdm_hooks = json.loads((root / 'reports/kernel-source/recovery-20261004/cdm-kthread-pool-hooks.json').read_text())
        for name, digest in list(cdm_tests['sources'].items()) + list(cdm_hooks['sources'].items()):
            if sha(SOURCE / name) != digest:
                raise RuntimeError('Source changed since CDM pool tests/install: ' + name)
            if name not in patch_paths:
                patch_paths.append(name)
    if args.binder_extensions:
        binder_tests = json.loads((OUT / 'binder-extensions-tests/result.json').read_text())
        if binder_tests['exit_code']:
            raise RuntimeError('Binder extension tests failed')
        binder_hooks = json.loads((root / 'reports/kernel-source/recovery-20261004/binder-extensions-hooks.json').read_text())
        for name, digest in list(binder_tests['sources'].items()) + [kv for kv in binder_hooks['sources'].items() if kv[0] not in superseded]:
            if sha(SOURCE / name) != digest:
                raise RuntimeError('Source changed since binder tests/install: ' + name)
            if name not in patch_paths:
                patch_paths.append(name)
    if args.display_temp_pwm:
        disp_tests = json.loads((OUT / 'display-temp-pwm-tests/result.json').read_text())
        if disp_tests['exit_code']:
            raise RuntimeError('display temp pwm tests failed')
        disp_hooks = json.loads((root / 'reports/kernel-source/recovery-20261008/display-temp-pwm-hooks.json').read_text())
        for name, digest in list(disp_tests['sources'].items()) + [kv for kv in disp_hooks['sources'].items() if kv[0] not in superseded]:
            if sha(SOURCE / name) != digest:
                raise RuntimeError('Source changed since display temp pwm tests/install: ' + name)
            if name not in patch_paths:
                patch_paths.append(name)
    if args.kgsl_ctxprio:
        kgsl_tests = json.loads((OUT / 'kgsl-ctxprio-tests/result.json').read_text())
        if kgsl_tests['exit_code']:
            raise RuntimeError('kgsl priority tests failed')
        kgsl_hooks = json.loads((root / 'reports/kernel-source/recovery-20261008/kgsl-ctxprio-hooks.json').read_text())
        for name, digest in list(kgsl_tests['sources'].items()) + [kv for kv in kgsl_hooks['sources'].items() if kv[0] not in superseded]:
            if sha(SOURCE / name) != digest:
                raise RuntimeError('Source changed since kgsl priority tests/install: ' + name)
            if name not in patch_paths:
                patch_paths.append(name)
    batch_report = []
    if batch:
        expected = {}
        for stage in batch:
            stage_hooks = json.loads((root / stage['hooks']).read_text())
            expected.update(stage_hooks['sources'])
            for new_file in stage_hooks.get('new_files', []):
                if new_file not in new_paths:
                    new_paths.append(new_file)
            stage_tests = []
            for test_dir in stage['tests']:
                result = json.loads((OUT / test_dir / 'result.json').read_text())
                if result['exit_code']:
                    raise RuntimeError('Batch stage tests failed: ' + test_dir)
                for name, digest in result['sources'].items():
                    if sha(SOURCE / name) != digest:
                        raise RuntimeError('Source changed since batch tests %s: %s' % (test_dir, name))
                stage_tests.append({'dir': test_dir, 'stdout': result['stdout'], 'harness_sha256': result['harness_sha256']})
            mutations = [json.loads((root / m).read_text()) for m in stage.get('mutations', [])]
            for m in mutations:
                if m['killed'] != m['total']:
                    raise RuntimeError('Batch stage has surviving mutants: ' + stage['name'])
            batch_report.append({'name': stage['name'], 'hooks': stage_hooks, 'tests': stage_tests,
                                 'mutations': [{'killed': m['killed'], 'total': m['total']} for m in mutations]})
        # latest writer wins: every file must match the hash left by the last stage that patched it
        for name, digest in expected.items():
            if sha(SOURCE / name) != digest:
                raise RuntimeError('Source changed since batch install: ' + name)
            if name not in patch_paths:
                patch_paths.append(name)
    started = datetime.fromisoformat(build['started_utc']).timestamp()
    for name in patch_paths:
        if (SOURCE / name).stat().st_mtime > started:
            raise RuntimeError('Source modified after this build started: ' + name)
    target.mkdir(exist_ok=True)
    subprocess.run(['git', '-C', str(SOURCE), 'add', '-N', '--', *new_paths], check=True)
    diff = subprocess.check_output(['git', '-C', str(SOURCE), 'diff', '--binary', 'HEAD', '--',
                                    *patch_paths])
    (target / 'pico-virtual-mono.patch').write_bytes(diff)
    artifacts = {}
    for name in ['Image', 'Image.gz']:
        original = OUT / 'obj/arch/arm64/boot' / name
        shutil.copy2(original, target / name)
        digest = sha(original)
        if sha(target / name) != digest:
            raise RuntimeError('Export hash mismatch')
        artifacts[name] = {'sha256': digest, 'bytes': original.stat().st_size}
    shutil.copy2(OUT / (label + '-build.log'), target / 'build.log')
    report = {'build': build, 'tests': tests, 'artifacts': artifacts,
              'source_sha256': sha(SOURCE / relative), 'runtime_verified': False,
              'factory_callback_tables': str(root / 'reports/kernel-source/recovery-20261003/virtual-mono-factory-tables.json'),
              'module_set_revalidated_for_this_image': False,
              'pending': ['camera hub wrappers and hooks at CRM/sync registration and CCI ops change',
                          'video-device/open-file lifetime on remove',
                          'real VB2 queue and camera runtime', 'all other kernel recovery gaps'],
              'device_modified': False}
    if sensor_hook:
        report['sensor_hook_tests'] = sensor_tests
        report['initcall_order'] = init_order
        report['crm_registration_guard_changed'] = False
    if hub_relay:
        report['hub_relay_tests'] = hub_tests
        report['hub_registration_wired'] = False
        report['hub_source_sha256'] = sha(SOURCE / hub_source)
        report['factory_shadow_ops'] = json.loads((root / 'reports/kernel-source/recovery-20261003/camera-hub-shadow-ops.json').read_text())
    if hub_registry:
        report['hub_registry_tests'] = registry_tests
        report['hub_registry_source_sha256'] = sha(SOURCE / registry_source)
        report['hub_registry_wired_to_v4l2_registration'] = False
    if hub_file:
        report['hub_file_worker_tests'] = file_tests
        report['hub_file_helpers_wired_to_fops'] = False
        report['timeout_semantics'] = 'Initial completion wait is bounded; running work is drained before return, potentially beyond timeout'
        factory = BASE / 'analysis/kernel-recovery/camera-file-worker'
        report['factory_file_worker'] = json.loads((factory / 'functions.json').read_text())
        shutil.copy2(factory / '_video_device_workfn-0.S', target / 'factory-file-worker.S')
    if hub_events:
        report['hub_event_tests'] = event_tests
        report['hub_events_wired_to_ioctl_or_irq'] = False
        report['event_context'] = 'Process context under registry mutex; IRQ delivery and lifetime mechanism remain pending'
        event_factory = BASE / 'analysis/kernel-recovery/camera-event-routing'
        report['factory_event_routing'] = json.loads((event_factory / 'functions.json').read_text())
        for name in ['cam_device_hub_handle_event', 'cam_device_hub_send_sync_device_event',
                     'cam_device_hub_send_vnode_device_event']:
            shutil.copy2(event_factory / (name + '-0.S'), target / (name + '-factory.S'))
    if hub_ioctl:
        report['hub_ioctl_tracking_tests'] = ioctl_tests
        report['hub_ioctl_tracker_wired_to_dispatcher'] = False
        report['tracked_ioctl_operations'] = ['CRM create/destroy session', 'Sync create/destroy object']
    if hub_subscriptions:
        report['hub_subscription_count_tests'] = subscription_tests
        report['hub_subscription_callbacks_wired'] = False
        report['decoded_video_event_lock_offset'] = 248
        counter_factory = BASE / 'analysis/kernel-recovery/camera-subscription-counts'
        report['factory_subscription_counter'] = json.loads((counter_factory / 'functions.json').read_text())
        shutil.copy2(counter_factory / 'add_evt_and_fetch-0.S', target / 'factory-subscription-counter.S')
    if args.hub_subscription_callbacks:
        report['hub_subscription_callback_tests'] = callback_tests
        report['hub_subscription_callback_helpers_implemented'] = True
        report['hub_subscription_callbacks_installed_in_ops_tables'] = False
        callback_factory = BASE / 'analysis/kernel-recovery/camera-subscription-callbacks'
        report['factory_subscription_callbacks'] = json.loads((callback_factory / 'functions.json').read_text())
        for name in ['video_device_subscribe_event', 'video_device_unsubscribe_event']:
            shutil.copy2(callback_factory / (name + '-0.S'), target / (name + '-factory.S'))
    if args.hub_resources:
        report['tracked_ioctl_operations'].extend(['CRM ALLOC/MAP/RELEASE buffer', 'CRM LINK v1/v2/UNLINK'])
        report['resource_cleanup_wired_to_close'] = False
        report['original_driver_rollback_after_tracking_failure_implemented'] = False
        report['resource_semantics'] = 'Post-success bookkeeping only; MAP retains only handle; hardware cleanup and dispatcher remain pending'
    if args.hub_cleanup:
        report['hub_cleanup_tests'] = cleanup_tests
        report['resource_cleanup_helpers_implemented'] = True
        report['cleanup_driver_calls'] = ['cam_req_mgr_unlink', 'cam_req_mgr_destroy_session(false)', 'cam_sync_destroy', 'cam_mem_mgr_release']
        report['cleanup_failure_semantics'] = 'Stop at first driver failure; restore pending records for retry; do not repeat successful releases'
        report['cleanup_driver_calls_hold_registry_mutex'] = False
        report['memento_cleanup_implemented'] = False
    if args.hub_fops:
        report['hub_fops_tests'] = fops_tests
        report['hub_fops_helpers_implemented'] = True
        report['hub_fops_installed_on_real_nodes'] = False
        report['hub_file_helpers_wired_to_fops'] = True
        report['resource_cleanup_wired_to_prepared_release_callback'] = True
        report['resource_cleanup_wired_to_close'] = False
        report['shared_file_open_semantics'] = 'Native open once in a drained worker; task-local wrapper recursion bypass; no live fops swaps'
        report['failed_close_semantics'] = 'Keep registered client/FH/runtime and shared file; retry in delayed work; EBUSY stop; no closed-FH event delivery'
        report['runtime_stop_semantics'] = 'Blocks new lookups/opens; refuses owned refs or clients before registry detach; registration must preserve parent and physical driver lifetime'
        fops_symbols = ['pico_hub_video_open', 'pico_hub_video_release', 'pico_hub_video_runtime_init',
                        'pico_hub_video_runtime_stop', 'pico_hub_retry_client_close', 'pico_hub_video_fops']
        report['hub_fops_kernel_symbols'] = {name: hex(symbols[name]) for name in fops_symbols}
        lifecycle_factory = BASE / 'analysis/kernel-recovery/camera-file-lifecycle'
        report['factory_file_lifecycle'] = json.loads((lifecycle_factory / 'functions.json').read_text())
        for name in ['video_device_open', 'video_device_close']:
            shutil.copy2(lifecycle_factory / (name + '-0.S'), target / (name + '-factory.S'))
        report['pending'].extend(['install hub fops/ioctl tables and runtime during actual registration', 'complete native ioctl dispatch/rollback and memento subdevice lifecycle'])
    if args.hub_dispatch:
        report['pending'] = [item for item in report['pending'] if item != 'complete native ioctl dispatch/rollback and memento subdevice lifecycle']
        report['pending'].append('memento subdevice lifecycle and full ioctl/runtime validation on PICO')
        report['hub_dispatch_tests'] = dispatch_tests
        report['hub_native_packet_tracking_wired_to_prepared_dispatcher'] = True
        report['hub_dispatch_installed_on_real_nodes'] = False
        report['hub_native_driver_hooks_wired'] = True
        report['dispatch_semantics'] = 'Original callback with shared file and client FH; preallocated ownership captured from native kernel packet before output usercopy; kernel-packet destructive ownership validation'
        report['dispatch_output_failure_semantics'] = 'Rollback newly created resource using actual driver functions; on rollback failure retain owned record for close cleanup'
        report['dispatch_session_destroy_semantics'] = 'Successful native session destroy implicitly unlinks session links; corresponding records removed across registered clients'
        report['native_driver_hooks'] = json.loads((root / 'reports/kernel-source/recovery-20261003/camera-hub-dispatch-hooks.json').read_text())
        dispatch_symbols = ['pico_hub_vidioc_default', 'pico_hub_validate_native_release',
                            'pico_hub_complete_native_ioctl', 'pico_hub_video_ioctl_ops']
        report['hub_dispatch_kernel_symbols'] = {name: hex(symbols[name]) for name in dispatch_symbols}
        dispatch_factory = BASE / 'analysis/kernel-recovery/camera-ioctl-dispatch'
        report['factory_ioctl_dispatch'] = json.loads((dispatch_factory / 'functions.json').read_text())
        shutil.copy2(dispatch_factory / 'video_device_ioctl_default-0.S', target / 'factory-ioctl-dispatch.S')
        report['pending'].append('actual node registration and IRQ/subdevice/memento wiring; validation of native packets and module set on PICO')
    if args.hub_registration:
        report['hub_registration_tests'] = registration_tests
        report['native_registration_hooks'] = registration_hooks
        report['hub_registration_wired_in_source'] = True
        report['hub_registration_wired'] = True
        report['hub_registry_wired_to_v4l2_registration'] = True
        report['hub_fops_wired_in_registration_code'] = True
        report['hub_dispatch_wired_in_registration_code'] = True
        report['resource_cleanup_wired_in_registration_code'] = True
        report['registration_runtime_verified_on_pico'] = False
        report['forced_platform_unbind_with_live_clients_verified'] = False
        report['registration_semantics'] = 'Consume original allocation; publish original and hub with static ops; ready gate until native probe complete; V4L2 refcounted registration/media/original lifetimes'
        report['native_driver_hooks_before_registration'] = report['native_driver_hooks']
        report['native_driver_hooks'] = {'sources': registration_hooks['sources'], 'scope': 'Native packet hooks preserved and registration lifecycle added'}
        report['pending'] = ['IRQ-safe event routing into hub clients', 'subdevice hub/CCI/memento lifetime and routing',
                             'forced platform removal quiescence with live clients', 'real VR/camera/device runtime and module validation', 'all other original kernel recovery gaps']
        registration_symbols = ['pico_hub_register_video_device', 'pico_hub_activate_video_device',
                                'pico_hub_unregister_video_device', 'pico_hub_video_runtime_activate',
                                'cam_v4l2_device_release', 'cam_sync_v4l2_release']
        report['hub_registration_kernel_symbols'] = {name: hex(symbols[name]) for name in registration_symbols}
        registration_factory = BASE / 'analysis/kernel-recovery/camera-node-registration'
        report['factory_node_registration'] = json.loads((registration_factory / 'functions.json').read_text())
        for name in ['cam_device_hub_handle_video_device_register', 'cam_device_hub_handle_video_device_unregister']:
            shutil.copy2(registration_factory / (name + '-0.S'), target / (name + '-factory.S'))
    if args.hub_irq:
        report['hub_irq_tests'] = irq_tests
        report['native_irq_hooks'] = irq_hooks
        report['hub_event_producers_wired_in_source'] = True
        report['hub_events_wired_to_ioctl_or_irq'] = True
        report['irq_delivery_semantics'] = 'Single CRM/sync providers selected by explicit scalar entity + handle; spin-protected enrolled FH/index and handle lists; lock held through direct v4l2_event_queue_fh; no producer device-pointer dereference, IRQ mutex/allocation or delayed copies'
        report['irq_lock_order'] = 'Process registry mutex -> IRQ index spinlock -> V4L2 FH spinlock; IRQ path acquires only latter two'
        report['native_event_packets'] = 'Zeroed event structs; sync payload length validated against event data capacity minus header'
        report['event_context'] = 'Native producer route is IRQ-safe; legacy route_event_locked remains process-context only'
        report['pending'] = ['subdevice hub/CCI/memento lifecycle and routing', 'forced platform removal quiescence with live clients',
                             'real VR/camera/device runtime and module validation', 'all other original kernel recovery gaps']
        irq_symbols = ['pico_hub_route_irq_event', 'pico_hub_irq_attach_client_locked',
                       'pico_hub_irq_detach_client_locked', 'pico_hub_mark_client_closed_locked']
        report['hub_irq_kernel_symbols'] = {name: hex(symbols[name]) for name in irq_symbols}
    if args.cci_ops:
        report['cci_ops_tests'] = cci_tests
        report['cci_late_ops_notification_wired_in_source'] = True
        report['subdevice_shadow_registration_wired'] = False
        report['cci_ops_semantics'] = 'Native original devnode fops write precedes hook; update saved native fops only for multi-client entries; reject self/live-table changes; non-multi CCI unchanged'
        report['factory_multi_client_policy'] = json.loads((root / 'reports/kernel-source/recovery-20261003/camera-cci-ops-hook.json').read_text())
        cci_symbols = ['cam_device_hub_handle_v4l2_subdevice_ops_changed', 'pico_hub_entity_multi_client']
        report['cci_ops_kernel_symbols'] = {name: hex(symbols[name]) for name in cci_symbols}
        cci_factory = BASE / 'analysis/kernel-recovery/camera-cci-ops-change'
        report['factory_cci_ops_change'] = json.loads((cci_factory / 'functions.json').read_text())
        for name in ['cam_device_hub_handle_v4l2_subdevice_ops_changed', 'cam_cci_late_init']:
            shutil.copy2(cci_factory / (name + '-0.S'), target / (name + '-factory.S'))
        probe_factory = BASE / 'analysis/kernel-recovery/camera-cci-probe'
        report['factory_cci_probe'] = json.loads((probe_factory / 'functions.json').read_text())
        shutil.copy2(probe_factory / 'cam_cci_platform_probe-0.S', target / 'cam_cci_platform_probe-factory.S')
    if args.subdevice_lifetime:
        report['subdevice_lifetime_tests'] = lifetime_tests
        report['owned_unpublished_subdevice_context'] = True
        report['subdevice_shadow_registration_wired'] = False
        report['subdevice_lifetime_semantics'] = 'Owned unpublished mirror; relay kref and native module pin; closing gate; destroy busy until callbacks drain; direct registry detach refused; caller must retain physical original state until successful destroy'
        report['pending'] = ['subdevice mirror publication, file routing and memento',
                             'physical original-driver remove quiescence with live callbacks/clients',
                             'real VR/camera/device runtime and module validation',
                             'all other original kernel recovery gaps']
        lifetime_symbols = ['pico_hub_prepare_subdevice', 'pico_hub_destroy_prepared_subdevice',
                            'pico_hub_acquire_subdevice_relay', 'pico_hub_release_subdevice_relay']
        report['subdevice_lifetime_kernel_symbols'] = {name: hex(symbols[name]) for name in lifetime_symbols}
    if args.subdevice_media:
        report['subdevice_media_registration_helper'] = True
        report['subdevice_media_kernel_symbols'] = {'pico_hub_register_prepared_subdevice': hex(symbols['pico_hub_register_prepared_subdevice'])}
        report['subdevice_lifetime_semantics'] = 'Owned mirror with media pads initialization; optional V4L2/media-only attachment and parent V4L2 reference; callback/registration krefs and closing gate; destroy unregisters owned media attachment after drain; devnode publication refused; original driver memory retained by caller contract'
        report['subdevice_media_scope'] = 'Compiled helper and host tests of real helper bodies with modeled media/V4L2 APIs; not connected to native CRM late registration yet; no subdevice file nodes created'
    if args.memento_ledger:
        report['memento_ledger_tests'] = memento_tests
        report['memento_file_hooks_wired'] = False
        report['memento_ledger_semantics'] = 'Factory two-class policy and JPEG exception; acquire 24-byte kernel packet, explicit or implicit start keys with CSIPHY exception; reserve allocation before native operation; commit only native success; stop before release and retain failed records for retry'
        report['memento_scope'] = 'Ledger compiled but native kernel packet capture, rollback adapters and subdevice file hooks remain pending'
        memento_symbols = ['pico_memento_init', 'pico_memento_entity_class', 'pico_memento_prepare',
                           'pico_memento_commit', 'pico_memento_cancel', 'pico_memento_cleanup']
        report['memento_kernel_symbols'] = {name: hex(symbols[name]) for name in memento_symbols}
        factory = BASE / 'analysis/kernel-recovery/camera-memento'
        report['factory_memento'] = json.loads((factory / 'functions.json').read_text())
        for name in ['memento_hook_subdevice_ioctl_after', 'recoder_sensor_ioctl_info',
                     'memento_hook_subdevice_close_before', 'memento_triger_acquire_release_rollback']:
            shutil.copy2(factory / (name + '-0.S'), target / (name + '-factory.S'))
    if args.memento_node:
        report['memento_node_tests'] = node_tests
        report['memento_node_adapter_compiled'] = True
        report['memento_node_kernel_symbols'] = {name: hex(symbols[name]) for name in ['pico_memento_node_init', 'pico_memento_node_rollback']}
        report['memento_node_semantics'] = 'Class1 kernel-payload native cam_node stop; native context release errors propagated; retain acquisition context ref and completed-release phase through handle-destroy failure; retry skips repeated native release; drop ref only after successful handle destruction'
        report['memento_scope'] = 'Class1 adapter compiled and tested with actual ledger/native stop bodies and modeled release/handles/ref API; class0/CSIPHY adapters, capture and close/file hooks pending'
        report['native_memento_node_hooks'] = json.loads((root / 'reports/kernel-source/recovery-20261003/camera-memento-node-hooks.json').read_text())
    if args.csiphy_rollback:
        report['csiphy_rollback_tests'] = csiphy_tests
        report['csiphy_rollback_kernel_symbols'] = {'rollback_cam_csiphy_core_cfg': hex(symbols['rollback_cam_csiphy_core_cfg'])}
        report['csiphy_rollback_scope'] = 'Kernel-payload native stop/release recovery compiled; invalid-input guards normalized; factory counter/state mutations on hardware/handle errors retained; phased retry adapter and memento close wiring still pending'
        report['native_csiphy_rollback_hooks'] = json.loads((root / 'reports/kernel-source/recovery-20261003/csiphy-rollback-hooks.json').read_text())
        factory = BASE / 'analysis/kernel-recovery/camera-csiphy-rollback'
        report['factory_csiphy_rollback'] = json.loads((factory / 'functions.json').read_text())
        shutil.copy2(factory / 'rollback_cam_csiphy_core_cfg-0.S', target / 'rollback_cam_csiphy_core_cfg-factory.S')
    if args.memento_sensor:
        report['memento_sensor_tests'] = sensor_adapter_tests
        report['memento_sensor_kernel_symbols'] = {name: hex(symbols[name]) for name in ['pico_memento_sensor_init', 'pico_memento_sensor_rollback']}
        report['memento_sensor_scope'] = 'Primary sensor entity 0x10001 only; compiled native kernel cleanup using streamoff/power/resource/IRQ/handle primitives and phased retry; class0 actuator/flash/eeprom/OIS/mono, capture and subdevice file/close integration pending'
        report['memento_sensor_semantics'] = 'Native streamoff failure retains START; link/power errors propagate; successful power/resource/IRQ stages retained across handle error; retry skips completed stages; handles and INIT committed only after successful destroy'
        report['native_memento_sensor_hooks'] = json.loads((root / 'reports/kernel-source/recovery-20261003/memento-sensor-hooks.json').read_text())
    if args.memento_mono:
        report['memento_mono_kernel_symbols'] = {'pico_memento_mono_rollback': hex(symbols['pico_memento_mono_rollback'])}
        report['mono_release_opcode_corrected'] = 'Factory raw 0x106 CAM_RELEASE_DEV, replacing erroneous CAM_CONFIG_DEV 0x105; test now uses actual cam_defs UAPI rather than mislabeled mock constant'
        report['memento_mono_scope'] = 'Native queue-release callback drains both queues and in-flight DQBUF; original sd/controller lifetime and exclusive acquisition retained by caller contract; memento/subdevice close hooks not wired'
        mono_factory = BASE / 'analysis/kernel-recovery/camera-full'
        report['factory_mono_ioctl'] = json.loads((mono_factory / 'functions.json').read_text())
        shutil.copy2(mono_factory / 'virtual_mono_subdev_ioctl-0.S', target / 'virtual_mono_subdev_ioctl-factory.S')
    if args.memento_actuator:
        report['memento_actuator_tests'] = actuator_tests
        report['memento_actuator_kernel_symbols'] = {name: hex(symbols[name]) for name in ['pico_memento_actuator_init', 'pico_memento_actuator_rollback']}
        report['memento_actuator_scope'] = 'Actuator 0x10009 kernel-payload stop/release adapter compiled; real delete_request tested with allocated I2C buffers, power/handle API modeled; subdevice close hooks pending'
        report['memento_actuator_semantics'] = 'Stop deletes valid per-frame requests; link/power errors retained; successful power-down retained across handle error; retry skips power-down; handles/state/power-buffer release committed after handle destruction'
        report['native_memento_actuator_hooks'] = json.loads((root / 'reports/kernel-source/recovery-20261003/memento-actuator-hooks.json').read_text())
    if args.memento_ois:
        report['memento_ois_tests'] = ois_tests
        report['memento_ois_kernel_symbols'] = {name: hex(symbols[name]) for name in ['pico_memento_ois_init', 'pico_memento_ois_rollback']}
        report['memento_ois_scope'] = 'OIS 0x1000d kernel-payload stop/release compiled; actual ledger/delete_request and allocated I2C/power buffers tested with modeled power/handle API; subdevice close hooks pending'
        report['memento_ois_semantics'] = 'Invalid stop preserves state; link/power/handle failures retained; completed power-down and cleared native mode/calib/init lists retained for retry; final buffers/handles/INIT after successful destroy'
        report['native_memento_ois_hooks'] = json.loads((root / 'reports/kernel-source/recovery-20261003/memento-ois-hooks.json').read_text())
    if args.memento_eeprom:
        report['memento_eeprom_tests'] = eeprom_tests
        report['memento_eeprom_kernel_symbols'] = {name: hex(symbols[name]) for name in ['pico_memento_eeprom_init', 'pico_memento_eeprom_rollback']}
        report['memento_eeprom_scope'] = 'EEPROM 0x1000c acquisition release and implicit no-op stop compiled; actual ledger/adapter/CRM handle destroy tested with current UAPI/table definitions and modeled locking/bitmap API; subdevice close hooks pending'
        report['memento_eeprom_semantics'] = 'ACQUIRE/identity/link validation; table/destroy errors retain controller and ledger record; successful native handle destruction precedes controller handle reset/INIT'
        report['native_memento_eeprom_hooks'] = json.loads((root / 'reports/kernel-source/recovery-20261003/memento-eeprom-hooks.json').read_text())
    if args.memento_flash:
        report['memento_flash_tests'] = flash_tests
        report['memento_flash_kernel_symbols'] = {name: hex(symbols[name]) for name in ['pico_memento_flash_init', 'pico_memento_flash_rollback']}
        report['memento_flash_scope'] = 'Flash 0x1000b phased kernel-payload cleanup compiled; actual ledger/adapter/native flash_off with modeled LED/GPIO/flush/power/handle APIs; subdevice close hooks pending'
        report['memento_flash_semantics'] = 'Off/flush/power-down phase retention; provider/link/handle errors retained; release handles configuration-induced START without separate journal start; successful destroy precedes handles/INIT reset'
        report['native_memento_flash_hooks'] = json.loads((root / 'reports/kernel-source/recovery-20261003/memento-flash-hooks.json').read_text())
    if args.memento_capture:
        report['memento_capture_tests'] = capture_tests
        report['memento_capture_kernel_symbols'] = {name: hex(symbols[name]) for name in ['pico_memento_capture_begin', 'pico_memento_capture_end', 'pico_memento_capture_native']}
        report['memento_capture_semantics'] = 'Synchronous caller-owned capture scope keyed by current task/physical owner/entity/opcode; first kernel packet preserved; native sensor acquire hook before usercopy/powerup; observed handle side effect distinct from final ioctl success'
        report['memento_capture_scope'] = 'Sensor acquire observer wired; other native hooks, calling subdevice dispatcher and partial-acquire rollback pending; no completed memento/file integration'
        report['native_memento_capture_hooks'] = json.loads((root / 'reports/kernel-source/recovery-20261003/memento-capture-hooks.json').read_text())
    if args.sensor_acquire_unwind:
        if not capture_tests.get('sensor_pre_power_unwind_tested'):
            raise RuntimeError('Native acquire unwind test evidence missing')
        report['sensor_acquire_unwind_kernel_symbols'] = {'pico_memento_capture_unwind': hex(symbols['pico_memento_capture_unwind'])}
        report['sensor_acquire_unwind_semantics'] = 'Positive copyin remainder becomes EFAULT; signed invalid create handle stops acquire before bridge assignment/IRQ/power; failed copyout attempts handle destruction, clears bridge only on success and separately records unwind outcome'
        report['sensor_acquire_unwind_scope'] = 'Native pre-power error fixes tested with real acquire body and modeled usercopy/create/destroy/power API; destroy failure retains handles and pending evidence; power-up failure cleanup and calling subdevice dispatcher remain pending'
        report['native_sensor_acquire_unwind_hooks'] = json.loads((root / 'reports/kernel-source/recovery-20261003/sensor-acquire-unwind-hooks.json').read_text())
    if args.sensor_io_unwind:
        report['sensor_io_unwind_tests'] = io_unwind_tests
        report['sensor_io_unwind_kernel_symbols'] = {'pico_memento_capture_power_cleanup': hex(symbols['pico_memento_capture_power_cleanup'])}
        report['sensor_io_unwind_semantics'] = 'Failed camera_io_init after core power-up invokes native core power-down and records power-only cleanup status; original init errno preserved; private-address workaround skipped on init error; BoB restore attempted after successful core cleanup'
        report['sensor_io_unwind_scope'] = 'Actual sensor power_up/camera_io_init/observer bodies tested with modeled core/CCI/BoB helpers; full IRQ/handle/acquire cleanup and live hardware remain pending'
        report['native_sensor_io_unwind_hooks'] = json.loads((root / 'reports/kernel-source/recovery-20261003/sensor-io-unwind-hooks.json').read_text())
    if args.sensor_fsin_irq:
        report['sensor_fsin_irq_tests'] = fsin_tests
        report['sensor_fsin_irq_kernel_symbols'] = {name: hex(symbols[name]) for name in ['cam_sensor_register_irq', 'cam_sensor_unregister_irq']}
        report['sensor_fsin_irq_semantics'] = 'Mutex-protected shared GPIO/IRQ transaction; count and per-controller reference only after success; stable IRQ cookie and original GPIO retained; duplicate acquire rejected and unowned release idempotent; native acquire propagates IRQ failure and attempts handle unwind'
        report['sensor_fsin_irq_scope'] = 'Real helper/native acquire bodies with modeled GPIO/IRQ and pthread concurrency; prefix field appended; failed power-up IRQ cleanup and physical hot-remove/hardware validation pending'
        report['native_sensor_fsin_irq_hooks'] = json.loads((root / 'reports/kernel-source/recovery-20261003/sensor-fsin-irq-hooks.json').read_text())
    if args.sensor_acquire_retry:
        report['sensor_acquire_retry_tests'] = acquire_retry_tests
        report['sensor_acquire_retry_kernel_symbols'] = {'pico_sensor_acquire_unwind_locked': hex(symbols['pico_sensor_acquire_unwind_locked'])}
        report['sensor_acquire_retry_semantics'] = 'Driver-owned core/BoB/I-O/IRQ/pending-acquire phases; native copyout/IRQ/power failures unwind or retain remaining phases; CAM_RELEASE_DEV retries pending cleanup from INIT; completed stages skipped; non-release/config commands gated while pending'
        report['sensor_acquire_retry_scope'] = 'Actual native acquire/release/power/up/down/unwind/observer pipeline tested with modeled lower providers; logical cleanup verified, physical hardware/hot-remove/subdevice-file integration pending'
        report['native_sensor_acquire_retry_hooks'] = json.loads((root / 'reports/kernel-source/recovery-20261003/sensor-acquire-retry-hooks.json').read_text())
    if args.sensor_release_retry:
        if not acquire_retry_tests.get('sensor_release_retry_tested'):
            raise RuntimeError('Normal native release retry evidence missing')
        report['sensor_release_retry_semantics'] = 'Normal release preserves handles/state on destroy error; driver-owned pending/resource phase gates configuration and skips completed power/I-O/IRQ/request cleanup; final handles/INIT only after successful destroy; memento sensor adapter shares resource phase'
        report['sensor_release_retry_scope'] = 'Actual native release pipeline and memento adapter tested with modeled lower providers; controller lifecycle/hardware/subdevice-file/hot-remove validation pending'
        report['native_sensor_release_retry_hooks'] = json.loads((root / 'reports/kernel-source/recovery-20261003/sensor-release-retry-hooks.json').read_text())
    if args.peer_acquire_capture:
        report['peer_acquire_capture_tests'] = peer_capture_tests
        report['peer_acquire_capture_semantics'] = 'Native actuator/OIS/EEPROM/Flash kernel acquire24 packet observed before copyout; task/physical owner/entity/op identity and signed created-handle status; capture does not alter original results or declare completed acquire'
        report['peer_acquire_capture_scope'] = 'Four real acquire/helper bodies and observer tested with actual UAPI and modeled create/usercopy; peer partial-acquire cleanup, dispatcher and hardware remain pending'
        report['native_peer_acquire_capture_hooks'] = json.loads((root / 'reports/kernel-source/recovery-20261003/peer-acquire-capture-hooks.json').read_text())
    if args.eeprom_acquire_retry:
        report['eeprom_acquire_retry_tests'] = eeprom_retry_tests
        report['native_eeprom_acquire_retry_hooks'] = json.loads((root / 'reports/kernel-source/recovery-20261003/eeprom-acquire-retry-hooks.json').read_text())
        report['eeprom_acquire_retry_semantics'] = 'Negative/zero handle rejects acquire before copyout; failed copyout rolls back handle; failed destroy retains pending INIT acquisition for native release or memento retry; native normal release preserves handles/ACQUIRE on destroy failure'
        report['eeprom_acquire_retry_scope'] = 'Actual native ioctl/helper/capture and ledger/adapter/CRM handle-table destruction bodies tested; lower API models; shutdown, hardware, subdevice dispatch and removal remain pending'
    if args.eeprom_shutdown_retry:
        report['eeprom_shutdown_retry_tests'] = eeprom_shutdown_tests
        report['native_eeprom_shutdown_retry_hooks'] = json.loads((root / 'reports/kernel-source/recovery-20261003/eeprom-shutdown-retry-hooks.json').read_text())
        report['eeprom_shutdown_retry_semantics'] = 'Native shutdown handles pending INIT acquire; failed power-down keeps CONFIG; failed handle destroy keeps ACQUIRE/handles/power allocations; successful completed power stage is skipped on retry; allocation freeing follows successful destroy'
        report['eeprom_shutdown_retry_scope'] = 'Actual shutdown/open/last-close/unwind and native state enum tested with lower API models; close returns native zero despite cleanup error, remove still frees controller unconditionally, physical lifetime/hardware and individual power provider retries remain unresolved'
    if args.eeprom_power_retry:
        report['eeprom_power_retry_tests'] = eeprom_power_tests
        report['native_eeprom_power_retry_hooks'] = json.loads((root / 'reports/kernel-source/recovery-20261003/eeprom-power-retry-hooks.json').read_text())
        report['eeprom_power_retry_semantics'] = 'Driver-owned core/I-O phases; init failure attempts core unwind preserving original init errno; parser error tails retain power settings/maps while cleanup remains; native release/shutdown/memento use phases and free retained allocations after successful handle destroy; config blocked during pending cleanup'
        report['eeprom_power_retry_scope'] = 'Actual power helpers/release/shutdown/adapter/userspace parser cleanup tail tested with lower API models; complete DT/read/write parser paths and lower-provider partial side effects, remove/lifetime, physical runtime remain unverified'
    if args.eeprom_parser_unwind:
        report['eeprom_parser_unwind_tests'] = eeprom_parser_tests
        report['native_eeprom_parser_unwind_hooks'] = json.loads((root / 'reports/kernel-source/recovery-20261003/eeprom-parser-unwind-hooks.json').read_text())
        report['eeprom_parser_unwind_semantics'] = 'Primary read/output/erase/write errno preserved across cleanup; erase/write failures enter phased power-down; common cleanup destroys remaining write request list and frees transaction allocations after successful cleanup; DT map parse failure frees partial map, repeated DT reads preserve DT settings'
        report['eeprom_parser_unwind_scope'] = 'Complete actual packet orchestrator/DT read/get-cal/write/delete-request/power/free/release/shutdown bodies tested with real public UAPI and native enums; nested command payload parsers, mappings/providers modeled, physical EEPROM/remove/runtime remain pending'
    if args.eeprom_command_bounds:
        report['eeprom_command_bounds_tests'] = eeprom_command_tests
        report['native_eeprom_command_bounds_hooks'] = json.loads((root / 'reports/kernel-source/recovery-20261003/eeprom-command-bounds-hooks.json').read_text())
        report['eeprom_command_bounds_semantics'] = 'Aligned descriptor windows, checked nonzero/aligned/bounded command progress and callback errors; unknown write command terminates; count-bound continuous writes; full conditional-wait/map-index bounds; power command consumes remaining descriptor bytes'
        report['eeprom_command_bounds_scope'] = 'Actual nested read/write loops and memory-map decoder tested with native enums/map/common-header types and public command UAPI; lower continuous-write/delay/power/mapping helpers modeled; actual continuous payload copy/list/delay and descriptor-table/mapping ownership, providers/remove/runtime remain pending'
    if args.eeprom_write_payload:
        report['eeprom_write_payload_tests'] = eeprom_payload_tests
        report['native_eeprom_write_payload_hooks'] = json.loads((root / 'reports/kernel-source/recovery-20261003/eeprom-write-payload-hooks.json').read_text())
        report['eeprom_write_payload_semantics'] = 'Continuous UAPI data fills native register tables with correct types/mode/count; node published only after table allocation; invalid opcode/type allocates nothing; delay helper leaves pointer advance to caller; actual CCI/QUP adapters select burst/seq modes; native request destruction frees reg and seq allocations'
        report['eeprom_write_payload_scope'] = 'Actual allocator/payload/delay/parser/delete/write/I-O/CCI-QUP dispatch bodies tested with real UAPI and native types; lower allocation/mapping/providers and CCI command enum values modeled; factory symbol match, erase/eebin policy, bus/remove/runtime remain unverified'
    if args.eeprom_packet_routing:
        report['native_eeprom_packet_routing_hooks'] = json.loads((root / 'reports/kernel-source/recovery-20261003/eeprom-packet-routing-hooks.json').read_text())
        report['eeprom_packet_routing_semantics'] = 'Actual common packet range validator remains unchanged; EEPROM rejects unaligned descriptor/config offsets, avoids truncation of config offset, accepts exact packet fit; get-cal advances every IO config'
        report['eeprom_packet_routing_scope'] = 'Existing complete parser suite now executes actual common range validator and checks multi-IO separate outputs/second-entry errors, oversized descriptor count and invalid offsets; mappings/nested payload providers modeled; mapping ownership, erase policy, remove/hardware remain pending'
    if args.eeprom_output_copy:
        report['mem_output_copy_tests'] = mem_copy_tests
        report['native_eeprom_output_copy_hooks'] = json.loads((root / 'reports/kernel-source/recovery-20261003/eeprom-output-copy-hooks.json').read_text())
        report['eeprom_output_copy_semantics'] = 'EEPROM output bytes copied under native m_lock/q_lock with active/full-handle/KMD/address/range revalidation; release and q_lock destruction excluded while copying; manager lifecycle retained by caller; original exported APIs and table layout unchanged'
        report['eeprom_output_copy_scope'] = 'Actual copy and native slot retirement host concurrency tested; complete EEPROM suite models copy API; full DMA unmap/deinit/input packet snapshot and providers/remove/hardware remain pending'
    if args.eeprom_packet_snapshot:
        report['native_eeprom_packet_snapshot_hooks'] = json.loads((root / 'reports/kernel-source/recovery-20261003/eeprom-packet-snapshot-hooks.json').read_text())
        report['eeprom_packet_snapshot_semantics'] = 'Packet copied to owned vmalloc memory under native m_lock/q_lock; size/header consistency checked; common validator runs against copied length; EEPROM wrapper always vfree after owned parser returns'
        report['eeprom_packet_snapshot_scope'] = 'Actual memory helper/retirement tests prove owned packet survives release/source overwrite and allocation/header-change cleanup; EEPROM suite models snapshot API; nested command inputs, manager lifecycle/deinit/full DMA/provider/hardware proof remain pending'
    if args.eeprom_command_snapshot:
        report['native_eeprom_command_snapshot_hooks'] = json.loads((root / 'reports/kernel-source/recovery-20261003/eeprom-command-snapshot-hooks.json').read_text())
        report['eeprom_command_snapshot_semantics'] = 'Exact nonempty descriptor windows duplicated under native m_lock/q_lock; source offset applied once; read/write parser owns current copy and frees it at next descriptor/all exits; retained map/register/power data use owned allocations'
        report['eeprom_command_snapshot_scope'] = 'Actual range helper tested with boundary/allocation/ownership failures; actual nested parsers model dup API and verify source overwrite/nonzero offset/multidescriptor failure without leaked copies; lower power source inspected for value copy, full lifecycle/DMA/provider/hardware remain pending'
    if args.eeprom_power_decode:
        report['eeprom_power_decode_tests'] = power_decode_tests
        report['native_eeprom_power_decode_hooks'] = json.loads((root / 'reports/kernel-source/recovery-20261003/eeprom-power-decode-hooks.json').read_text())
        report['eeprom_power_decode_semantics'] = 'EEPROM prevalidates complete counted power/window lengths, decodes into staged arrays; first power descriptor replaces settings, subsequent descriptors append up/down arrays within native MAX_POWER_CONFIG; old arrays untouched on decode/merge allocation errors; generic sensor decoder unchanged'
        report['eeprom_power_decode_scope'] = 'Actual generic validator/decoder and EEPROM adapter tested with native settings/types/enums/limit and real UAPI; native nested parser flags tested with adapter model; GPIO/regulator/providers/lifecycle/hardware remain pending'
    if args.actuator_acquire_retry:
        report['actuator_acquire_retry_tests'] = actuator_retry_tests
        report['native_actuator_acquire_retry_hooks'] = json.loads((root / 'reports/kernel-source/recovery-20261003/actuator-acquire-retry-hooks.json').read_text())
        report['actuator_acquire_retry_semantics'] = 'INIT/positive copyin remainder/created-handle guards; kernel acquire captured before copyout, negative errno preserved; copyout failure rolls back handle and captures cleanup result; failed cleanup retains INIT handles/pending flag for release/memento, config/start gate while query allowed'
        report['actuator_acquire_retry_scope'] = 'Actual native acquire/release/query fragments, pending gate/helper/capture/UAPI/state and memento tested with lower API models; normal release phases, shutdown/power/provider/removal/hardware remain pending'
    if args.actuator_release_retry:
        report['actuator_release_retry_tests'] = actuator_release_tests
        report['native_actuator_release_retry_hooks'] = json.loads((root / 'reports/kernel-source/recovery-20261003/actuator-release-retry-hooks.json').read_text())
        report['actuator_release_retry_semantics'] = 'Native release state/handle/link guards precede power-down; failed destroy retains handles/state/allocations and reported-successful power stage; pending config/start/stop gate; native/memento share driver-owned stage and clear final ownership only after successful destroy'
        report['actuator_release_retry_scope'] = 'Actual native release and memento tested on the same modeled controller with allocated power buffers and lower power/destroy APIs; no lower core/I-O/BOB retry, shutdown/remove/lifecycle or hardware proof'
    if args.actuator_shutdown_retry:
        report['actuator_shutdown_retry_tests'] = actuator_shutdown_tests
        report['native_actuator_shutdown_retry_hooks'] = json.loads((root / 'reports/kernel-source/recovery-20261003/actuator-shutdown-retry-hooks.json').read_text())
        report['actuator_shutdown_retry_semantics'] = 'Void native shutdown handles pending INIT before soc access, preserves state/resources on failed power or handle deletion, shares reported-successful release power stage, final ownership reset only after success; forced START/linked close retained'
        report['actuator_shutdown_retry_scope'] = 'Actual shutdown/open/last-close/native release tested with allocated power buffers and lower API models; zero-return close semantics, per-frame/CRM quiescence, physical remove/lifecycle and individual power/I-O/providers/hardware remain pending'
    if args.actuator_power_retry:
        report['actuator_power_retry_tests'] = actuator_power_tests
        report['native_actuator_power_retry_hooks'] = json.loads((root / 'reports/kernel-source/recovery-20261003/actuator-power-retry-hooks.json').read_text())
        report['actuator_power_retry_semantics'] = 'Driver-owned core/I-O phases; failed init attempts core unwind retaining primary errno and failed core cleanup; release/shutdown/memento use phases even in ACQUIRE; failed I/O release preserves IO phase and completed core power-down is skipped'
        report['actuator_power_retry_scope'] = 'Actual power helpers/native release/memento/shutdown tested with allocated settings, native state/UAPI and modeled lower providers/types; default construction/core provider partial effects/full packet/per-frame/CRM/lifecycle/remove/hardware remain pending'
    if args.actuator_write_routing:
        report['actuator_write_routing_tests'] = actuator_write_tests
        report['native_actuator_write_routing_hooks'] = json.loads((root / 'reports/kernel-source/recovery-20261003/actuator-write-routing-hooks.json').read_text())
        report['actuator_write_routing_semantics'] = 'Native actuator sequential mode QUP enum versus CCI/SPI flag; actual caller and I/O/CCI/QUP dispatch exercised with real op enums, payload/errors and modeled bus providers'
        report['actuator_write_routing_scope'] = 'No physical bus/factory packet/per-frame/lifecycle/runtime proof; existing shared mode API preserved'
    if args.actuator_request_cleanup:
        report['actuator_request_cleanup_tests'] = actuator_request_tests
        report['native_actuator_request_cleanup_hooks'] = json.loads((root / 'reports/kernel-source/recovery-20261003/actuator-request-cleanup-hooks.json').read_text())
        report['actuator_request_cleanup_semantics'] = 'Drain initialized init/per-frame lists after successful power/handle teardown in native release/shutdown/memento; retain settings on earlier failure, reset request IDs, preserve initialized list heads'
        report['actuator_request_cleanup_scope'] = 'Actual native release case/shutdown/memento/common drain/native delete_request with allocated settings; lower power/handle/controller modeled; other regression tests model the drain; CRM callback quiescence/physical remove/factory hardware pending'
    if args.actuator_callback_gates:
        report['actuator_callback_gates_tests'] = actuator_callback_tests
        report['native_actuator_callback_gates_hooks'] = json.loads((root / 'reports/kernel-source/recovery-20261003/actuator-callback-gates-hooks.json').read_text())
        report['actuator_callback_gates_semantics'] = 'Revalidate current handle under actuator mutex in apply/flush/link; block pending apply/link enable, retain unlink, guard frame pointer under mutex'
        report['actuator_callback_gates_scope'] = 'Actual callback bodies with threaded lookup-to-lock handle replacement on a still-live modeled controller; raw-pointer physical remove lifetime and CRM global quiescence remain unresolved'
    if args.camera_callback_borrow:
        report['camera_callback_borrow_tests'] = callback_borrow_tests
        report['native_camera_callback_borrow_hooks'] = json.loads((root / 'reports/kernel-source/recovery-20261003/camera-callback-borrow-hooks.json').read_text())
        report['camera_callback_borrow_scope'] = 'Native get/put/quiesce and actuator apply/flush/link reader integration; host SRCU modeled by pthread rwlock; physical remove/V4L2 integration remains unwired and unsafe'
    if args.v4l2_media_pin:
        report['v4l2_media_pin_tests'] = media_pin_tests
        report['native_v4l2_media_pin_hooks'] = json.loads((root / 'reports/kernel-source/recovery-20261003/v4l2-media-pin-hooks.json').read_text())
        report['v4l2_media_pin_scope'] = 'Private file module pin replaces close/error-path media-entity dereference; parent snapshot serialized with detach; owner still must remain alive, pending driver/node retirement integration'
    if args.v4l2_lifetime:
        report['v4l2_lifetime_tests'] = lifetime_tests
        report['native_v4l2_lifetime_hooks'] = json.loads((root / 'reports/kernel-source/recovery-20261003/v4l2-lifetime-hooks.json').read_text())
        report['v4l2_lifetime_scope'] = 'Optional bind/retire registry plus native node pin/final release; actuator callers and physical removal integration still absent, module pin requires explicit retirement'
    if args.actuator_probe_publication:
        report['actuator_probe_publication_tests'] = probe_tests
        report['native_actuator_probe_publication_hooks'] = json.loads((root / 'reports/kernel-source/recovery-20261003/actuator-probe-publication-hooks.json').read_text())
        report['actuator_probe_publication_scope'] = 'Initialize callback-visible fields before I2C/platform V4L2 registration; publication failure cleans probe-owned allocations; owner bind/retire, DT internal resource cleanup and physical remove still pending'
    if args.crm_ops_snapshot:
        report['crm_ops_snapshot_tests'] = crm_ops_tests
        report['native_crm_ops_snapshot_hooks'] = json.loads((root / 'reports/kernel-source/recovery-20261003/crm-ops-snapshot-hooks.json').read_text())
        report['crm_ops_snapshot_scope'] = 'Link-owned callback table bytes, atomic handle-locked snapshot and native V1/V2 selection; callback code/module pin, partial link rollback/workqueue lifetime and physical remove still pending'
    if args.crm_flush_result:
        report['crm_flush_result_tests'] = flush_result_tests
        report['native_crm_flush_result_hooks'] = json.loads((root / 'reports/kernel-source/recovery-20261003/crm-flush-result-hooks.json').read_text())
        report['crm_flush_result_scope'] = 'First callback failure returned to flush waiter; per-request result refs survive timeout and late worker; owned enqueue handles cancel/failure and preserves legacy ABI; real scheduler/link/remove lifetime pending'
    if args.shared_pinctrl_state:
        report['shared_pinctrl_state_tests'] = pinctrl_tests
        report['native_shared_pinctrl_state_hooks'] = json.loads((root / 'reports/kernel-source/recovery-20261004/shared-pinctrl-state-hooks.json').read_text())
        report['shared_pinctrl_state_scope'] = 'Native shared ACTIVE/SUSPEND state commits only on provider success; host failure/retry/hold tests. Shared put, GPIO/clock counter ownership, phased common power-down, physical remove and hardware proof remain pending.'
    if args.shared_gpio_lock:
        report['shared_gpio_lock_tests'] = gpio_tests
        report['native_shared_gpio_lock_hooks'] = json.loads((root / 'reports/kernel-source/recovery-20261004/shared-gpio-lock-hooks.json').read_text())
        report['shared_gpio_lock_scope'] = 'Shared record lookup, counter update and hardware write under record removal mutex. Actual body with modeled retirement and pthread contention; manager lifetime, vote ownership on retries and hardware proof remain pending.'
    if args.camera_power_down_phases:
        report['camera_power_down_phases_tests'] = power_phases_tests
        report['native_camera_power_down_phases_hooks'] = json.loads((root / 'reports/kernel-source/recovery-20261004/camera-power-down-phases-hooks.json').read_text())
        report['camera_power_down_phases_scope'] = 'Retained common shutdown phases and native actuator error propagation; fully acquired host fixture with modeled providers. Native partial power-up unwind, other owners, manager/devres lifetime, real concurrency and hardware remain pending.'
    if args.camera_power_up_unwind:
        report['camera_power_up_unwind_tests'] = power_up_tests
        report['native_camera_power_up_unwind_hooks'] = json.loads((root / 'reports/kernel-source/recovery-20261004/camera-power-up-unwind-hooks.json').read_text())
        report['camera_power_up_unwind_mutations'] = json.loads((root / 'reports/kernel-source/recovery-20261004/camera-power-up-unwind-tests/mutations.json').read_text())
        report['camera_power_up_unwind_scope'] = 'Validated power-up with real errors; partial acquisition unwound through retained ledger retried by power-up/down; factory-tolerant shutdown of unmatched/unknown steps. Modeled providers, single-threaded; manager/devres lifetime, other owners and hardware pending.'
    if args.isp_bufdone:
        report['isp_bufdone_tests'] = isp_tests
        report['native_isp_bufdone_hooks'] = isp_hooks
        report['isp_bufdone_mutations'] = json.loads((root / 'reports/kernel-source/recovery-20261004/isp-bufdone-tests/mutations.json').read_text())
        report['isp_bufdone_scope'] = 'CAF last-consumed-address chain and factory deferred buf-done acks; RDI bubble infinite loop fixed; RDI SOF late buf done. Host model only; VFE register semantics, IRQ timing and camera runtime unverified.'
    if args.cdm_kthread_pool:
        report['cdm_kthread_pool_tests'] = cdm_tests
        report['native_cdm_kthread_pool_hooks'] = cdm_hooks
        report['cdm_kthread_pool_mutations'] = json.loads((root / 'reports/kernel-source/recovery-20261004/cdm-kthread-pool-tests/mutations.json').read_text())
        report['cdm_kthread_pool_scope'] = 'Factory RT kthread worker pool for HW/virtual CDM work; teardown UAF and creation leak fixed. pthread-emulated workers; real IRQ/RT scheduling and CDM hardware unverified.'
    if args.binder_extensions:
        report['binder_extensions_tests'] = binder_tests
        report['native_binder_extensions_hooks'] = binder_hooks
        report['binder_extensions_mutations'] = json.loads((root / 'reports/kernel-source/recovery-20261004/binder-extensions-tests/mutations.json').read_text())
        report['binder_extensions_scope'] = 'libbinder PICO ioctls b,14/15/30/31 and the system_server async-space guard; signal 58 replaced by a log. Host model of the two new bodies; ioctl numbers checked at build time; device behaviour unverified.'
    if args.kgsl_ctxprio:
        report['kgsl_ctxprio_tests'] = kgsl_tests
        report['native_kgsl_ctxprio_hooks'] = kgsl_hooks
        report['kgsl_ctxprio_mutations'] = json.loads((root / 'reports/kernel-source/recovery-20261008/kgsl-ctxprio-tests/mutations.json').read_text())
        if args.display_temp_pwm:
            report['display_temp_pwm_tests'] = disp_tests
            report['native_display_temp_pwm_hooks'] = disp_hooks
            report['display_temp_pwm_mutations'] = json.loads((root / 'reports/kernel-source/recovery-20261008/display-temp-pwm-tests/mutations.json').read_text())
            report['display_temp_pwm_scope'] = ('Temperature dependent backlight PWM (DSI panel work + DCS group write) and sde-crtc bl_pwm_timing/vsync_timing nodes. '
                                                'Factory 5.13.7 dtbo carries qcom,response-temp-curve and io-channels on the nt57900/ls026b3sa panels but not '
                                                'qcom,temperature-dependent-pwm, so with the stock DT the PWM work stays disabled and bl_pwm_timing reads 0,0,0,0. Host model only.')
        if batch_report:
            report['batch_20261008'] = batch_report
        report['kgsl_ctxprio_scope'] = 'IOCTL_KGSL_CTXPRIO_SHIFT (system_server VR GPU boost): barrier at queue head on the last submitted timestamp, priority/rb/plist switch. Host model; real GPU preemption/rb behaviour unverified.'
    (target / 'verification.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
