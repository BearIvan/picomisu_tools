"""Write the reviewable preview documentation after all image checks passed."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    report = json.loads((ROOT / 'reports/vr-integration/image.json').read_text())
    if not report['filesystem_contents_independently_verified']:
        raise RuntimeError('Do not mark an unverified image ready')
    staging = json.loads((ROOT / 'reports/vr-integration/staging.json').read_text())
    output = json.loads((ROOT / 'reports/vr-integration/windows-output.json').read_text())
    profile_file = ROOT / 'device-profile.json'
    profile = json.loads(profile_file.read_text())
    profile['status'] = 'vr-preview-built-awaiting-device-boot-test'
    profile['build_configuration'].update(custom_build_started=True, system_image_built=True,
                                           aosp_input_build_completed=True, aosp_input_build_exit_code=0,
                                           source_query_protocol_patch_compiled=True,
                                           build_datetime=1790603988,
                                           build_number='PICO_AOSP_10_BRINGUP_2026092801',
                                           xml_audio_policy_configuration=1)
    profile['vr_integration'] = {
        'kind': 'hybrid-prototype', 'factory_vr_layer_packaged': True,
        'factory_firmware': '5.13.7 SEKO b9665',
        'aosp_boot_replacements': list(staging['aosp_replacements']),
        'aosp_additions': list(staging['aosp_additions']),
        'factory_framework_and_graphics_preserved': True,
        'full_aosp_framework_port_complete': False,
        'on_device_vr_tested': False, 'installed_on_headset': False,
        'independently_verified_filesystem_entries': report['independently_verified_entries'],
        'avb_chain_verified': True, 'sparse_roundtrip_verified': True,
        'current_boot_and_root_preserved': True,
        'bound_current_boot_sha256': report['current_boot_sha256'],
        'boot_flash_required': False, 'production_release': False,
        'development_avb_key': 'Existing public AOSP testkey_rsa4096.pem',
        'windows_output': 'outputs/vr-preview-01',
    }
    profile_file.write_text(json.dumps(profile, indent=2) + '\n')
    installation_file = ROOT / 'reports/board/device-tree-installation.json'
    installation = json.loads(installation_file.read_text())
    installation.update(build_configuration_validated=True, hardware_configuration_only=False,
                        external_vr_image_packaging_configured=True, system_image_built=True,
                        vr_integration_complete=False, on_device_vr_tested=False)
    installation_file.write_text(json.dumps(installation, indent=2) + '\n')
    text = f'''# PICO AOSP VR preview 01

Собран и проверен первый гибридный образ для PICO 4 Pro SEKO / PICOA8110.
Это этап подготовки AOSP 10 с VR. Полный перенос framework в исходники
не завершён; загрузка этого образа и работа VR на шлеме ещё не проверялись.

## Что входит в образ

| Компонент | Реализация |
|---|---|
| Регистрация системных Binder-служб | `servicemanager`, собранный из AOSP android-10.0.0_r47 |
| Дополнительные инструменты | AOSP `sh`, `toybox`, `logcat` в `/system/xbin/aosp` |
| Самостоятельное приложение | AOSP DeskClock, отдельный package `com.android.deskclock`, без общего UID PICO |
| Android framework и system_server | Согласованные заводские JAR, ресурсы и preopt 5.13.7 |
| ART/APEX, графика, JNI, ARM32/ARM64-библиотеки | Заводские компоненты 5.13.7 |
| VR, OpenXR, оболочка и приложения PICO | Заводские бинарные компоненты с исходными сертификатами |
| Kernel/DTB и root | Текущий boot шлема сохранён; kernel и DTB проверены против factory |
| Vendor/product/odm и калибровки | Используются существующие данные шлема |

Обычные `sh`, `toybox`, `logcat` в `/system/bin` сохранены заводскими.
В AOSP Toybox отсутствует заводской `gtop`; отдельный каталог исключает
изменение существующих команд и скриптов загрузки.

В исходники AOSP применён и успешно скомпилирован патч
`patches/0001-pico-query-value-payload.patch`: PICO передаёт дополнительный
int32 в QUERY графического producer, а команда 10000 использует его как
входной VR-статус. Патч покрывает передачу параметра, не весь графический
стек. В этом VR-образе сохраняется заводской libgui; частично перенесённая
исходная библиотека в него не подставляется.

## Результаты проверок

- AOSP input `systemimage`, DeskClock и инструменты: сборка завершилась с кодом 0.
- Режим сборки: CPU 0–7, `m -j8`; исходники и out на проверенном физическом ext4.
- Все 187 заводских APK из system/product/vendor/odm проверены apksigner.
- Сертификат platform и всех APK с `android.uid.system` согласован.
- Сильные ELF-импорты добавляемых компонентов разрешаются в сохранённых factory-библиотеках.
- AOSP sh, Toybox и logcat прошли отдельные тесты на текущем шлеме; SHA-256 тестовых данных совпал. Временные файлы удалены.
- В итоговом образе независимо прочитаны {report['independently_verified_entries']} файлов/каталогов/ссылок: содержимое, UID/GID, modes, SELinux и capabilities совпали с планом.
- ext4/e2fsck и AVB-цепочка проверены. Ключи дочерних образов сопоставлены с родительскими дескрипторами.
- Android sparse восстановлен в raw с точным совпадением SHA-256.
- Windows-копии независимо проверены по SHA-256.

## Комплект для просмотра

Windows: `C:/Users/RedPanda/Documents/ChatGPT/Android/pico4-pro/outputs/vr-preview-01`.

| Файл | Назначение | Размер файла |
|---|---|---:|
| system.img | Android sparse; разворачивается в {report['partition_size']} байт | {output['copied']['system.img']['bytes']} |
| vbmeta.img | Корневая цепочка под текущий boot и новый system | 65536 |
| vbmeta_system.img | Метаданные нового system и сохранённого product | 65536 |

Контрольные суммы лежат в `SHA256SUMS.txt`, результаты — в `verification.json`.
Raw system остаётся на ext4 в `pico4-pro/outputs/vr-preview-01/system.img`.
Образ соответствует текущему размеру logical system; super и LP-метаданные
не пересобраны, стандартная схема A/B не предполагается.

AVB подписан существующим публичным development-ключом AOSP. Это
экспериментальный комплект для открытого загрузчика, а не production-релиз
и не OTA, принимаемый заводским установщиком PICO. Закрытые ключи PICO
и рабочие ключи Pixel не использованы. Уровень rollback сохранён.

Метаданные factory SPL 2021-04-05 и времени 5.13.7 сохранены для совместимости
с текущей системой, Keymaster и восстановлением. Исходный AOSP объявляет
SPL 2019-09-05; покрытие патчами безопасности гибридного образа не подтверждено.
Собственная дата и версия сборки отмечены отдельными ro.pico.aosp.* свойствами.

## Перед загрузочным испытанием

Установка требует отдельного запроса пользователя. Сейчас прошивка на шлеме
не изменена; перезагрузки, установки APK, смены слотов и записи разделов не было.

Комплект привязан к проверенному текущему boot:
`{report['current_boot_sha256']}`.
Перед записью нужно повторно проверить этот хеш, доступность fastbootd,
имена logical partitions и путь восстановления. Испытание предполагает
запись system, vbmeta и vbmeta_system; boot перепрошивать не требуется.

После разрешённой установки необходимы проверки Android/system_server,
регистрации служб, стереоизображения, 6DoF, контроллеров, passthrough,
границы, IPD, глаз/лица и OpenXR-приложения. Они ещё не выполнены на этой системе.
'''
    (ROOT / 'docs/research/vr-integration.md').write_text(text, encoding='utf-8')
    (ROOT / 'outputs/vr-preview-01/README.md').write_text(text, encoding='utf-8')
    readme_file = ROOT / 'docs/research/project-notes.md'
    readme = readme_file.read_text(encoding='utf-8')
    first = readme.split('\n\n', 2)
    first[1] = ('Собран первый проверочный гибридный образ PICO AOSP VR preview 01. '
                'AOSP 10 r47 и первый патч VR-протокола успешно скомпилированы; '
                'в образ подключён AOSP servicemanager, сохранён согласованный заводской '
                'framework/runtime PICO 5.13.7. Файлы, права, AVB и Windows-копии проверены. '
                'Полный source-порт framework и проверка загрузки/VR остаются незавершёнными. '
                'Комплект и точные границы — [vr-integration.md](vr-integration.md).')
    readme = '\n\n'.join(first)
    readme = readme.replace('AVB/APK-подпись\nрелиза и упаковка VR пока не настроены.',
                            'Проверочная упаковка VR и development AVB настроены внешними\nскриптами. Production-подпись и проверка на шлеме не завершены.')
    readme = readme.replace('Образ с работающим VR ещё не создан.',
                            'Проверочный VR-образ создан; работа VR на нём ещё не проверена.')
    readme_file.write_text(readme, encoding='utf-8')
    print(json.dumps({'reports_updated': True, 'on_device_vr_tested': False}))


if __name__ == '__main__':
    main()
