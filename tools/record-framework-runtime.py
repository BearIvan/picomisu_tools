"""Save the verified both-ABI Java checkpoint without committing private runtime logs."""
import argparse
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, required=True)
    args = parser.parse_args()
    manifest_path = args.package / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    use_image = manifest.get('boot_image_used') is True
    report_name = 'framework-boot-image-test.json' if use_image else 'framework-runtime-test.json'
    report = json.loads((ROOT / 'reports/framework-bridge' / report_name).read_text())
    if manifest['files'] != report['source_sha256']:
        raise RuntimeError('Runtime report refers to different artifacts')
    if manifest.get('test_artifacts_in_system_image') is not False:
        raise RuntimeError('Test-only artifact placement was not verified')
    for relative, digest in manifest['files'].items():
        if hashlib.sha256((args.package / relative).read_bytes()).hexdigest() != digest:
            raise RuntimeError('Runtime artifact changed: ' + relative)
    for name in ['fingerprint_unchanged', 'boot_completed', 'temporary_files_removed']:
        if report.get(name) is not True:
            raise RuntimeError('Runtime postcondition failed: ' + name)
    if report.get('error') or report['system_partitions_modified'] or report['vr_services_replaced']:
        raise RuntimeError('Unexpected runtime side effect or failure')
    if use_image and (report.get('boot_image_requested') is not True or
                      report.get('boot_image_used') is not True):
        raise RuntimeError('Compiled Source boot image was not qualified')
    fixtures = ['source-runtime-and-local-service', 'empty-and-released-surface-noop',
                'java-surface-registers-producer', 'repeated-java-registration-is-shared',
                'java-surface-jni-producer-recovery', 'virtual-display-constructor-recovery',
                'virtual-display-set-surface-recovery', 'unchanged-virtual-display-surface-noop',
                'virtual-display-null-surface-detaches']
    passed = report['results'].get('arm64', {}).get('passed')
    if passed in (12, 19, 23, 24, 25, 26, 27, 28, 29, 30):
        fixtures += ['surface-control-display-flags-jni-values',
                     'surface-control-display-flags-static-wrapper',
                     'surface-control-display-flags-null-token-validation']
    canvas_fixtures = ['vr-canvas-released-surface-validation',
                       'vr-canvas-extension-identity',
                       'vr-canvas-native-pixel-and-retained-surface',
                       'vr-canvas-lock-and-identity-errors-preserve-reference',
                       'vr-canvas-unlock-detaches-without-queue',
                       'vr-canvas-repeated-lifetime',
                       'vr-canvas-retains-original-surface-on-transfer']
    policy_fixtures = ['vr-policy-shared-scenarios',
                       'draw-software-vr-skip-routes-to-vr-canvas',
                       'draw-software-vr-skip-repeated-without-queue',
                       'draw-software-regular-windows-use-lock-canvas']
    has_canvas = passed in (19, 23, 24, 25, 26, 27, 28, 29, 30)
    has_policy = passed in (23, 24, 25, 26, 27, 28, 29, 30)
    has_pico_api = passed in (24, 25, 26, 27, 28, 29, 30)
    has_qcom_api = passed in (25, 26, 27, 28, 29, 30)
    has_audio_api = passed in (26, 27, 28, 29, 30)
    has_shifted_aidl = passed in (27, 28, 29, 30)
    has_appended_aidl = passed in (28, 29, 30)
    has_factory_only_aidl = passed in (29, 30)
    has_factory_classpath = passed == 30
    if has_canvas:
        fixtures += canvas_fixtures
    if has_policy:
        fixtures += policy_fixtures
    if has_pico_api:
        fixtures.append('pico-api-wire-scenarios')
    if has_qcom_api:
        fixtures.append('qcom-api-wire-scenarios')
    if has_audio_api:
        fixtures.append('audio-api-wire-scenarios')
    if has_shifted_aidl:
        fixtures.append('shifted-aidl-wire-scenarios')
    if has_appended_aidl:
        fixtures.append('appended-aidl-wire-scenarios')
    if has_factory_only_aidl:
        fixtures.append('factory-only-aidl-wire-scenarios')
    if has_factory_classpath:
        fixtures.append('factory-classpath-classes')
    selected = ['libart.so', 'libart-compiler.so', 'libandroid_runtime.so', 'libgui.so', 'libbinder.so',
                'libnativehelper.so', 'libnativeloader.so', 'libjavacore.so', 'libopenjdk.so']
    if use_image:
        selected += ['source-linker', 'libc.so', 'libm.so', 'libdl.so', 'libartpalette-system.so']
    image_jars = manifest.get('boot_image_jars', 11)
    boot_jars = len(manifest['boot_classpath'])
    native = {}
    for abi in ['arm64', 'arm']:
        result = report['results'][abi]
        if result['exit_code'] or result.get('passed') != len(fixtures):
            raise RuntimeError('Java runtime checkpoint incomplete: ' + abi)
        for label in fixtures:
            if 'framework-runtime ' + label + '=1' not in result['output']:
                raise RuntimeError('Missing executed Java fixture: ' + label)
        if set(result['source_libraries_verified']) != {'libart.so', 'libandroid_runtime.so', 'libgui.so'}:
            raise RuntimeError('Source library origin was not verified')
        if use_image:
            expected = {p for p in manifest['files'] if p.startswith('system/framework/' + abi + '/')
                        and p.endswith(('.art', '.oat'))}
            if len(expected) != 2 * image_jars or set(result.get('mapped_source_images', [])) != expected:
                raise RuntimeError('Incomplete compiled Source boot image mapping: ' + abi)
            if result.get('source_bionic_and_core_jni_verified') is not True:
                raise RuntimeError('Source Bionic/core JNI was not verified: ' + abi)
            gui_path = result['source_libraries_verified']['libgui.so']
            prefix = gui_path.removesuffix('/' + abi + '/libgui.so')
            actual_images = set(re.findall(r'^runtime-image (\S+)$', result['output'], re.MULTILINE))
            if actual_images != {prefix + '/' + p for p in expected}:
                raise RuntimeError('Unexpected compiled image origin: ' + abi)
            if 'Unexpected CPU variant' in result['output']:
                raise RuntimeError('Source ART rejects the installed CPU variant')
        native[abi] = {name: manifest['files'][abi + '/' + name] for name in selected}
    config = json.loads((ROOT / 'config/aosp-patches.json').read_text())
    commits = {p['path']: p['local_commit'] for p in config['projects']}
    result = {'framework_commit': commits['frameworks/base'], 'native_commit': commits['frameworks/native'],
              'patch': 'patches/0025-source-framework-runtime-probe.patch',
              'package': str(args.package.resolve().relative_to(ROOT)).replace('\\', '/'),
              'manifest_sha256': hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
              'source_artifact_count': len(manifest['files']),
              'framework_jar_sha256': manifest['files']['system/framework/framework.jar'],
              'boot_jar_sha256': {p: manifest['files'][p] for p in manifest['boot_classpath']},
              'native_sha256': native,
              'component_patches': {p['path']: [x for x in [p.get('patch'), *p.get('additional_patches', [])] if x]
                                    for p in config['projects']},
              'surface_control_display_flags_jni_qualified': len(fixtures) >= 12,
              'source_vr_canvas_fixtures_per_abi': {'arm64': 7, 'arm': 7} if has_canvas else {},
              'source_vr_canvas_api_qualified': has_canvas,
              'source_vr_policy_fixtures_per_abi': {'arm64': 4, 'arm': 4} if has_policy else {},
              'source_vr_policy_fixtures_passed': has_policy,
              'pico_api_wire_fixture_passed': has_pico_api,
              'qcom_api_wire_fixture_passed': has_qcom_api,
              'audio_api_wire_fixture_passed': has_audio_api,
              'shifted_aidl_wire_fixture_passed': has_shifted_aidl,
              'appended_aidl_wire_fixture_passed': has_appended_aidl,
              'factory_only_aidl_wire_fixture_passed': has_factory_only_aidl,
              'factory_classpath_fixture_passed': has_factory_classpath,
              'vr_activity_skip_draw_policy_qualified': False,
              'runtime_verified_source_libraries': ['libart.so', 'libandroid_runtime.so', 'libgui.so'],
              'java_fixtures_per_abi': {'arm64': len(fixtures), 'arm': len(fixtures)},
              'fixtures': fixtures, 'test_artifacts_in_system_image': False,
              'java_execution_with_source_boot_classpath_qualified': True,
              'compiled_boot_image_qualified': use_image, 'jit_code_generation_qualified': False,
              'real_binder_service_calls_qualified': False, 'real_process_freeze_qualified': False,
              'gpu_fences_qualified': False, 'full_runtime_abi_proven': False,
              'fingerprint_unchanged': True, 'boot_completed': True, 'temporary_files_removed': True,
              'system_partitions_modified': False,
              'scope': 'Source app_process registers full Source JNI and executes Java VirtualDisplay/Surface '
                       'on Source ART with ' + str(boot_jars) + ' Source boot JARs; local display/freeze services and synthetic '
                       'buffers, imageless VM, fixture reflection with hidden API policy disabled',
              'pending': ['coherent CPU properties and Source boot-image qualification',
                          'real Binder services, freeze events, GPU rendering and full VR qualification']}
    if any('Unexpected CPU variant' in r['output'] for r in report['results'].values()):
        result['observed_runtime_warning'] = 'Source JIT rejects installed factory ARM64 variant kryo300; '
        result['observed_runtime_warning'] += 'compiled-code qualification remains open'
    destination = 'framework-runtime.json'
    if use_image:
        result.update({
            'art_commit': commits['art'],
            'patches': ['patches/0025-source-framework-runtime-probe.patch',
                        'patches/0026-source-runtime-mapping-probe.patch',
                        'patches/0027-art-relocated-bootclasspath-kryo300.patch'],
            'source_linker_and_bionic_qualified': True,
            'source_boot_image_mappings_per_abi': {'arm64': 2 * image_jars, 'arm': 2 * image_jars},
            'boot_image_sha256': {p: digest for p, digest in manifest['files'].items()
                                 if p.startswith('system/framework/')
                                 and p.endswith(('.art', '.oat', '.vdex'))},
            'aot_method_entry_instrumented': False,
            'scope': 'Source app_process, linker, Bionic and ART register full Source JNI and execute '
                     'Java VirtualDisplay/Surface, available SurfaceControl flags and Source VR canvas fixtures '
                     'with ' + str(boot_jars) + ' Source boot JARs and ' + str(2 * image_jars) + ' mapped compiled '
                     'boot-image files per ABI; local display/freeze services, synthetic buffers '
                     'and fixture reflection with hidden API policy disabled',
            'pending': ['AOT method-entry evidence and JIT code-generation qualification',
                        'real Binder services, freeze events, GPU rendering and full VR qualification'],
        })
        if has_policy:
            result['scope'] += ('; VR activity policy scenarios shared with the factory comparison and '
                                'ViewRootImpl.drawSoftware routing on a fixture Surface')
            result['vr_policy_evidence'] = 'validation/vr-policy-port.json'
        if has_pico_api:
            result['scope'] += '; PICO API AIDL wire-format and parcelable scenarios shared with the factory'
            result['pico_api_evidence'] = 'validation/pico-api-port.json'
        if has_qcom_api:
            result['scope'] += '; Qualcomm-ordered AOSP AIDL wire-format scenarios shared with the factory'
            result['qcom_api_evidence'] = 'validation/qualcomm-api-port.json'
        if has_factory_classpath:
            result['scope'] += ('; every class of the kept factory boot class path JARs loaded through '
                                'the boot class loader with its boot-image class status, shared with the factory')
            result['factory_classpath_evidence'] = 'validation/factory-classpath-wire.json'
        destination = 'framework-boot-image.json'
    (ROOT / 'validation' / destination).write_text(json.dumps(result, indent=2) + '\n')
    if use_image and has_canvas:
        abi = json.loads((ROOT / 'validation/vr-canvas-api.json').read_text())
        if abi['source_framework_sha256'] != result['framework_jar_sha256']:
            raise RuntimeError('VR canvas API evidence refers to another framework')
        for architecture in ('arm64', 'arm'):
            if abi['abis'][architecture]['source_sha256'] != native[architecture]['libandroid_runtime.so']:
                raise RuntimeError('VR canvas JNI evidence refers to another runtime')
        current_path = ROOT / 'validation/native-runtime-current.json'
        current = json.loads(current_path.read_text())
        package = json.loads((ROOT / current['package'] / 'manifest.json').read_text())
        for architecture in ('arm64', 'arm'):
            for library in ('libgui.so', 'libbinder.so'):
                if package['files'][architecture + '/' + library] != native[architecture][library]:
                    raise RuntimeError('Native and Source Java groups used different GUI/Binder')
        current.update(framework_commit=commits['frameworks/base'],
                       compiled_framework_commit=commits['frameworks/base'],
                       art_commit=commits['art'],
                       java_runtime_fixtures_per_abi={'arm64': len(fixtures), 'arm': len(fixtures)},
                       compiled_boot_image_fixtures_per_abi={'arm64': len(fixtures), 'arm': len(fixtures)},
                       source_vr_canvas_fixtures_per_abi={'arm64': 7, 'arm': 7},
                       vr_canvas_api_evidence='validation/vr-canvas-api.json',
                       vr_activity_skip_draw_policy_qualified=False,
                       evidence_packages=[current['package'], result['package']],
                       scope='Isolated native graphics comparisons and Source Java/JNI/ART/Bionic '
                             'with compiled boot images and VR canvas API'
                             + ('; VR activity policy and drawSoftware routing fixtures, full private '
                                'ABI and real GPU/VR remain unqualified on hardware' if has_policy else
                                '; ActivityInfo/ViewRoot policy, full private ABI and real GPU/VR '
                                'remain unqualified'))
        current_path.write_text(json.dumps(current, indent=2) + '\n')
    print('Recorded Source Java/JNI/ART checkpoint: ' + str(len(fixtures)) +
          ' fixtures on each ABI; compiled image=' + str(use_image))


if __name__ == '__main__':
    main()
