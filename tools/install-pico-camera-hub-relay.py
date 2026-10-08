"""Install the camera-hub relay slice, preserving differing local sources."""
from pathlib import Path
import hashlib
import json
import subprocess

SOURCE = Path('/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro/source/phoenix-kernel-recovery')


def main():
    root = Path(__file__).resolve().parent.parent
    if subprocess.check_output(['git', '-C', str(SOURCE), 'rev-parse', 'HEAD'], text=True).strip() != 'ceafd3afc0208c03e0eb7a1a60939d147f92d72a':
        raise RuntimeError('Unexpected recovery base')
    directory = 'techpack/camera/drivers/cam_core/'
    files = [directory + name for name in ('pico_camera_hub.c', 'pico_camera_hub.h', 'pico_camera_hub_registry.c',
                                         'pico_camera_hub_file.c', 'pico_camera_hub_file.h', 'pico_camera_hub_events.c',
                                         'pico_camera_hub_ioctl.c', 'pico_camera_hub_ioctl.h',
                                         'pico_camera_hub_resources.c', 'pico_camera_hub_resources.h',
                                         'pico_camera_hub_cleanup.c', 'pico_camera_hub_cleanup.h',
                                         'pico_camera_hub_fops.c', 'pico_camera_hub_fops.h',
                                         'pico_camera_hub_dispatch.c', 'pico_camera_hub_dispatch.h',
                                         'pico_camera_hub_registration.c', 'pico_camera_hub_registration.h',
                                         'pico_camera_hub_irq.c', 'pico_camera_hub_irq.h',
                                         'pico_camera_hub_subdevice.c', 'pico_camera_hub_subdevice.h',
                                         'pico_camera_memento.c', 'pico_camera_memento.h',
                                         'pico_camera_hub_subscriptions.c', 'pico_camera_hub_subscriptions.h',
                                         'pico_camera_hub_subscription_callbacks.c', 'pico_camera_hub_subscription_callbacks.h')]
    content = {name: (root / 'kernel-recovery' / name).read_bytes().replace(b'\r\n', b'\n') for name in files}
    for name, data in content.items():
        target = SOURCE / name
        if target.exists() and target.read_bytes() != data:
            old_digest = hashlib.sha256(target.read_bytes()).hexdigest()
            # Only replace exact earlier managed files; preserve manual edits.
            previous = {
                directory + 'pico_camera_hub_subdevice.c': ('0d52c2960322e92d5e81d65780fab11309c1274bb99bd08170b88bb283fdfcad', 'b5f21061e079137631238f5c7f31b144cad97412e10d3297dd85c3a67458e8f8'),
                directory + 'pico_camera_hub_subdevice.h': ('494ecf5cdd5581bf99b6a79d34ad2ab14ea53ee51dd5cead8259c3eaeee877a4', 'e9b4fa3fe07f31e87c7bd9553f4b679142fdfadeb64b4f14618af3fb70a6bb15'),
                directory + 'pico_camera_hub_cleanup.c': ('424c3f034b82937daab4cb1551811976d7979fcffc3006abb0de7e9c390ca29b',),
                directory + 'pico_camera_hub_registration.c': ('d32017e825e6e80b493ed9f57cd6c08f8e731e844f59e2297c1182efe1540ee4', '40f6533ae55c0ec109f518d19f8c167410063f6d5fca271d4790421909edb5a6', '91b06295392d3533ee9dde4a0fbccab0e21f7d8f360f11808f4289034c81dddf'),
                directory + 'pico_camera_hub_dispatch.c': ('c9f77cc81d2a0d9855c8baa454cc450bab394a5078c6f88b9451d6adb3119aa3', '339e2e140356dcbd62eae2bb124de6c16a7a6a9fb68a2770548f37d9a6afa94e'),
                directory + 'pico_camera_hub_fops.c': ('58ebef1472e0d07ed0fc2e79002488f1c3cb3640efda7114870b37ec0b3c1ad2', '71c4bcdcc9df3da4da4b8d3c893ffa75566a42d9cd6819e2cca03ace2f91a215', '6432a14704152df448e76b9a651fd508208f9be63ff4cc868b4a6dd3d80dbc0c'),
                directory + 'pico_camera_hub_fops.h': ('b3c307751934007e27cf11524998ac5ebff8e30576642c3527455a2f3d778fc1', '137f0257ce2cd72b17b58fe5ac561203a21b8cb332227e9fcd74856db5b2cd83'),
                directory + 'pico_camera_hub_resources.c': ('cc9fba2f3e6719ff801465c96e1c6f6d22d8a3693d8f4ccded28907fb77bed55',),
                directory + 'pico_camera_hub_ioctl.c': ('7da35b46dea52d6b62bd060e07029982b99540b6a303a0bae0dde0a178747eff',),
                directory + 'pico_camera_hub_ioctl.h': ('9d12730078f5edd38c036ce5f1dbea4a464966b62ca6a8a0c99990ef72c373b6',),
                directory + 'pico_camera_hub.h': ('b08871d3c7753465bf42b1828ab3dcdfcb1b40cceaa8bacff34121bca0966644', '1e4dda34f4643e3ea44c4adad15c946be1b2c934293e29962689e45433a03233', 'fcd3194b17ac0bddae65009c966b5b3e56cee0876104edf64dca5c28be9137ac', '0afae4ff19440db811845e0d277c4e78c6759b937b8a7fde1c8ba5e00cd757fa', '7d15be402b82a6e66cf56b3a58c4085d0f90e1000e07b8c3040804af7e2e23df'),
                directory + 'pico_camera_hub.c': ('ae60ac6e98e547db74bc8ec8313905dfd1d986bccd18ec1c938bbe9e58886713', 'ae20af7bc90b464e7ce82b8b0d54d4d41f5633543ad5ee51da7e4ff720cf300f'),
                directory + 'pico_camera_hub_registry.c': ('1ef764f49415b3712736627a00711d461e10afb548d327e3e5e03e1c22ff6784', '0552b565d5548d9adf702a1b4d6181b01609c190710c833a9d8054e1f0be2bb5', '1ad409bc43564e4bef5e6fd9a55b93ce67744525d54470cb63532cce90be2a1f', 'e59ef45ccc73793dc7ca82ac7ea4e332711ad3df2a532569390e1ff463ccbb35', 'adda8b6aa125eb475abc39bebbe8caca5409e38d74035c73a1641a70ca5dd7e0', '2c22a3a57dd8fe739cb0c502cd215cf092f8d75b228c44cbd92b480bbbec201f', '091cfc33f6abec9e9625ec52f01e97208c5a19e279ed71a7ccdc6e927c32fc7e'),
                directory + 'pico_camera_hub_file.c': ('7e5b3593d95076494e64651d53f5b8c2f1cb600461c34bc60ba2b02fc97c01de',),
                directory + 'pico_camera_hub_file.h': ('31b62e9417f2aceeda0d9c50d413fc9d71089dba2debb1622025a9fa7b52809d',),
                directory + 'pico_camera_hub_events.c': ('333b8940c7caed2e6d7ebe582b1f34468602c55e37617b9825e24ea3251e2a00', '2047293f38c521453d6c292107a8133e9be03933df786c20aa0f7656f2fa9d68', 'd102c65e7065164dde74c2d7fd8e984d8f4d9cf9cfec071aaaee6e11cb59a3ab', '3770a7d2a82e169cb4a44b72c2cbe0c89255568d7eac36161691902972657cfd'),
            }
            if old_digest not in previous.get(name, ()):
                raise RuntimeError('Preserve differing recovery source: ' + name)
    for name, data in content.items():
        if not (SOURCE / name).exists() or (SOURCE / name).read_bytes() != data:
            (SOURCE / name).write_bytes(data)
    makefile = SOURCE / directory / 'Makefile'
    text = makefile.read_text()
    line = 'obj-$(CONFIG_SPECTRA_CAMERA) += pico_camera_hub.o\n'
    if line not in text:
        text += '\n# Recovered PICO hub relay; full hub registration remains pending\n' + line
    registry_line = 'obj-$(CONFIG_SPECTRA_CAMERA) += pico_camera_hub_registry.o\n'
    if registry_line not in text:
        text += registry_line
    file_line = 'obj-$(CONFIG_SPECTRA_CAMERA) += pico_camera_hub_file.o\n'
    if file_line not in text:
        text += file_line
    event_line = 'obj-$(CONFIG_SPECTRA_CAMERA) += pico_camera_hub_events.o\n'
    if event_line not in text:
        text += event_line
    ioctl_line = 'obj-$(CONFIG_SPECTRA_CAMERA) += pico_camera_hub_ioctl.o\n'
    if ioctl_line not in text:
        text += ioctl_line
    subscription_line = 'obj-$(CONFIG_SPECTRA_CAMERA) += pico_camera_hub_subscriptions.o\n'
    if subscription_line not in text:
        text += subscription_line
    callback_line = 'obj-$(CONFIG_SPECTRA_CAMERA) += pico_camera_hub_subscription_callbacks.o\n'
    if callback_line not in text:
        text += callback_line
    resource_line = 'obj-$(CONFIG_SPECTRA_CAMERA) += pico_camera_hub_resources.o\n'
    if resource_line not in text:
        text += resource_line
    cleanup_line = 'obj-$(CONFIG_SPECTRA_CAMERA) += pico_camera_hub_cleanup.o\n'
    if cleanup_line not in text:
        text += cleanup_line
    fops_line = 'obj-$(CONFIG_SPECTRA_CAMERA) += pico_camera_hub_fops.o\n'
    if fops_line not in text:
        text += fops_line
    dispatch_line = 'obj-$(CONFIG_SPECTRA_CAMERA) += pico_camera_hub_dispatch.o\n'
    if dispatch_line not in text:
        text += dispatch_line
    registration_line = 'obj-$(CONFIG_SPECTRA_CAMERA) += pico_camera_hub_registration.o\n'
    if registration_line not in text:
        text += registration_line
    irq_line = 'obj-$(CONFIG_SPECTRA_CAMERA) += pico_camera_hub_irq.o\n'
    if irq_line not in text:
        text += irq_line
    subdevice_line = 'obj-$(CONFIG_SPECTRA_CAMERA) += pico_camera_hub_subdevice.o\n'
    if subdevice_line not in text:
        text += subdevice_line
    memento_line = 'obj-$(CONFIG_SPECTRA_CAMERA) += pico_camera_memento.o\n'
    if memento_line not in text:
        text += memento_line
    if makefile.read_text() != text:
        makefile.write_text(text)
    hooks_path = root / 'reports/kernel-source/recovery-20261003/camera-hub-registration-hooks.json'
    hooks = json.loads(hooks_path.read_text()) if hooks_path.exists() else None
    irq_hooks_path = root / 'reports/kernel-source/recovery-20261003/camera-hub-irq-hooks.json'
    irq_hooks = json.loads(irq_hooks_path.read_text()) if irq_hooks_path.exists() else None
    if hooks and irq_hooks:
        hooks['sources'].update(irq_hooks['sources'])
    wired = bool(hooks and all((SOURCE / name).exists() and
                              hashlib.sha256((SOURCE / name).read_bytes()).hexdigest() == digest
                              for name, digest in hooks['sources'].items()))
    report = {'sources': {name: hashlib.sha256(data).hexdigest() for name, data in content.items()},
              'scope': 'Hub video registration/fops/dispatch and IRQ source installed; subdevice/memento remains pending' if wired and irq_hooks else ('Hub video registration/fops/dispatch source installed; IRQ/subdevice/memento wiring remains pending' if wired else 'Hub foundations installed; native node registration remains pending'),
              'irq_producers_wired': bool(wired and irq_hooks),
              'registration_wired': wired, 'runtime_verified': False, 'device_modified': False}
    (root / 'reports/kernel-source/recovery-20261003/camera-subdevice-lifetime-source.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
