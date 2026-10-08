# Picomisu source-trial-01: состав, проверки, установка и откат

Первый пробный образ Source system для PICO 4 Pro SEKO (PICOA8110). Собран и проверен
только offline; на шлем ничего не записывалось. Установку выполняет отдельная сессия после
явного согласия пользователя на каждый пишущий шаг.

## 1. Что в образе

| Слой | Источник | Количество записей |
|---|---|---:|
| Framework, services, framework-res, boot image 21 JAR (оба ABI), ART/runtime и остальные APEX (.apex, не flattened), SELinux plat policy, init/vold/fs_mgr, native libs, AOSP-приложения | Source aosp_pico4pro-userdebug, 126 патчей (29 компонентов) | 3022 |
| Заводские файлы, которых нет в Source: VR-службы (pvrtrackingservice, pxr*, stationservice, gd32ipdservice, qvrservice, virtual_input …) и их init rc, 637 заводских ELF (69 исполняемых) PICO/QTI, VR-модели/конфиги (/system/etc/pxr, pvr, qvr, sensors, AlgSwift …), шрифты PICOSans, media, pre_resource, keylayout/idc, 13 JAR-библиотек вне class path, APK без platform-роли | factory 5.13.7 байт-в-байт | 2654 |
| 77 заводских APK с сертификатом PICO platform/media/shared (XRRuntime, XRShell, VRShell2, PVRHome, PvrManager, PicoSyshub, settings, Bluetooth/BluetoothExt, PicoPackageInstaller …) | factory 5.13.7, заново подписаны ключом Source той же роли; содержимое записей APK не изменено | 77 |
| Теневые копии android.uid.system из product: Settings, QdcmFF, PowerOffAlarm | product 5.13.7, подписаны Source platform | 3 (+3 каталога) |
| Сгенерированные: build.prop, prop.default, init.rc, ld.config.29.txt, public.libraries.txt, plat_mac_permissions.xml, vintf/manifest.xml | Source + заводские дополнения + пробные свойства | 7 |

Правила выбора — `device/pico/PICOA8110/source-trial-01.json`, сборка — `tools/assemble-source-image.py`,
проверки — `tools/check-source-image.py` → `validation/source-trial-01.json`.

- Путь, которого нет в Source, переносится с завода; путь, который есть в обоих, остаётся Source, кроме списка
  `factory_over_source` (keylayout PICO, cgroups/task_profiles, rc-настройки audioserver/cameraserver/servicemanager/
  hwservicemanager/atrace/perfetto, fonts.xml, hiddenapi whitelist, ueventd.rc, init.zygote*.rc, init.usb.configfs.rc)
  и заводского Bluetooth-набора (`factory-bluetooth.json`).
- Пакеты: из 43 общих AOSP-пакетов берётся Source (нет ссылок на PICO API), кроме com.android.bluetooth и
  com.android.packageinstaller (заводские). 16 пакетов, которых нет в 5.13.7 (TeleService, Telecom, ContactsProvider,
  NetworkStack, NfcNci, PrintSpooler …), и вторые варианты NetworkPermissionConfig/CaptivePortalLogin не ставятся:
  набор пакетов равен заводскому (186 = 186, симуляция сканирования PMS).
- Не переносятся: заводские APEX, SELinux, oat/odex/vdex, sys-services.jar и sysmonitor-services.jar (не на class path),
  install-recovery.sh + recovery-from-boot.p (пробный образ не должен переписывать recovery) и 300-МиБ демо-видео
  pre_resource/.../8K_Video_Demo_360.mp4: Source-слой на ~80 МиБ больше заводского, а заводской образ имел лишь 53 МиБ
  свободных в неизменяемом logical system 5 704 732 672 байт. Теперь свободно 76 291 блок (≈298 МиБ).
- Для этого образа добавлены в Source: `updatable_apex.mk` в device.mk (factory vendor/build.prop задаёт
  ro.apex.updatable=true и перекрывает system; с flattened APEX apexd не активировал бы runtime — загрузка
  невозможна), патчи 0125 (frameworks/av: `AImageReader_setRtMode`, `ALooper::getThreadId` из заводского кода —
  без них libpvrtrackingcamera, а значит pvrtrackingservice, pxrseethroughservice и камеры трекинга глаз не
  линкуются) и 0126 (эталон VNDK ABI libstagefright_foundation). verify-patch-series: 126 патчей воспроизводят деревья.

## 2. Подписи и shared UID (PMS android-10.0.0_r47)

Факты (номера строк — `frameworks/base/services/core/java/com/android/server/pm/PackageManagerService.java` дерева Source):

- Порядок сканирования (2626–2828): overlay, `/system/framework` (framework-res), `/system/priv-app`, `/system/app`,
  vendor, odm, oem, `/product/priv-app`, `/product/app`. Внутри каталога разбор параллельный.
- `reconcilePackagesLocked` (16585–16661): при несовпадении подписи пакета из системного каталога —
  «System package … signature changed; retaining data» (данные сохраняются). Для shared user первый
  отсканированный участник задаёт сертификат; каждый следующий с другим сертификатом при
  ro.product.first_api_level ≤ 29 получает `INSTALL_PARSE_FAILED_INCONSISTENT_CERTIFICATES` и не ставится.
- Системный пакет, который не отсканирован, удаляется из packages.xml: «System package … no longer exists; it's
  data will be wiped» (2892). Дубликат имени пакета отбрасывается: «already installed. Skipping duplicate» (11780).
- Разрешения signature, исключение hidden API (`isSignedWithPlatformKey`) и seinfo=platform
  (`plat_mac_permissions.xml`) зависят от совпадения с сертификатом framework-res.

Следствия: Source framework-res подписан тестовым platform-ключом AOSP (c8a2e9bc…), закрытого ключа PICO
(dc30289e…) нет. framework-res первым фиксирует android.uid.system → все заводские участники с сертификатом
PICO не установятся, остальные PICO-приложения потеряют platform-разрешения, исключение hidden API и домен
platform_app. Решение (оно одинаково нужно и с сохранением, и с очисткой данных):

1. 77 заводских APK системного раздела с сертификатами PICO platform/media/shared заново подписаны ключом Source
   той же роли (apksigner v1+v2 из сборки, проверка: содержимое записей не изменилось, zipalign, один подписант).
2. Участники android.uid.system на неизменяемом product (Settings, QdcmFF, PowerOffAlarm) продублированы на /system
   с подписью Source: /system сканируется раньше, копия из product отбрасывается как дубликат.
3. Группа android.uid.phone (4 APK product + IWlanService vendor) и прочие PICO-APK product/vendor остаются с
   сертификатом PICO: группа внутренне согласована; для них в plat_mac_permissions.xml пробного образа добавлены
   заводские записи PICO platform/media, поэтому seinfo такой же, как на 5.13.7. Без platform-подписи остаются 13
   пакетов (QTI telephony/colorservice/TimeService/gpudrivers …, overlays не в счёт) — для VR не нужны.
4. Жёстко зашитый сертификат PICO найден сканом всех DEX/ELF/XML 5.13.7 только в `store2d.apk` (MD5 платформенного
   сертификата): магазин PICO может отвергать проверку подписи системы/обновлений.

Результат симуляции PMS: 0 отказов установки, сертификаты групп: system/shell/bluetooth/networkstack — Source
platform, shared/media — Source, phone — PICO.

### Userdata: сохранить (a) или очистить (b)

(a) Сохранение технически возможно (подписи системных пакетов меняются с сохранением данных, группы согласованы),
но с известными потерями: SettingsProvider Source имеет SETTINGS_VERSION 182, а данные 5.13.7 — 183 → «Settings
rebuilt!», настройки global/secure/system сбрасываются; обновление com.bytedance.pico.matrix в /data сохранит
сертификат PICO (без platform-прав); ключи FBE/keystore 5.13.7 должны разблокироваться перенесённым vold
(проверяется только загрузкой); dalvik-cache и oat в /data устарели; Magisk-модули остаются.

(b) **Рекомендуется для первой пробы: очистить userdata и metadata** — детерминированное состояние PMS и
SettingsProvider, новые ключи FBE создаёт Source vold (проверка wrappedkey без зависимости от старых blob),
нет конфликтов обновлений. Пользователь разрешил очистку. Последствия: удаляются все данные /data — Magisk-модули
в /data/adb (eyed, eyestream, picoextrafunctionalities, picofacialdatadaemon) и приложение Magisk, Wi-Fi сети и
сопряжение ADB по Wi-Fi, аккаунт PICO и настройки, сторонние приложения (Steam Link и др.); PICO first-run
(provision2d) придётся пройти в шлеме. Boot с Magisk остаётся. ADB по USB в пробном образе работает без
авторизации (userdebug, ro.adb.secure=0, persist.sys.usb.config=adb).

## 3. Другие офлайн-проверки (все пройдены, если не указано иное)

| Проверка | Результат |
|---|---|
| Размер / ext4 | 5 704 732 672 байт (как logical system в super, LP не пересобирается), ФС 5 659 738 112 байт, e2fsck чисто, 1 305 481 / 1 381 772 блоков |
| AVB | vbmeta (флаги 0, rollback 0) → chain recovery (заводской ключ) и vbmeta_system (dev-ключ AOSP testkey_rsa4096, rollback 1617580800) → hashtree system + заводской product; hash boot = текущий Magisk boot 475ec054…; `avbtool verify_image --follow_chain_partitions` проходит |
| Readback | образ смонтирован read-only: 5766 записей = план (содержимое, uid/gid/mode/capabilities), 0 расхождений |
| SELinux | метки из Source file_contexts; все перенесённые файлы совпадают с заводскими метками, кроме `/system/etc/pvr/psmvrapi_config_ext.ini` (в заводском образе system_etc_pvr_file вопреки заводскому же plat_file_contexts; у нас system_psmvrapi_file, как в контекстах); unlabeled 0; `check-sepolicy.py` (политика не менялась) |
| init | host_init_verifier: 94 rc без ошибок; 298 служб: у всех служб /system есть переход домена, кроме dump_sched и vendor.move_{wifi,time}_data (так же на заводе); flash_recovery без скрипта — намеренно |
| Class path | BOOTCLASSPATH, DEX2OAT, SYSTEMSERVERCLASSPATH = заводской порядок; 11 заводских JAR проходят check-factory-component |
| Java | 97 перенесённых APK/JAR: DEX есть у всех, AIDL-таблицы и разрешения совпадают; единственная неразрешённая ссылка — `smartisanos.config.ProductConfig` в BrowserChrome (серверный Smartisan-слой не перенесён) |
| Native | 2226 ELF: новые разрывы только у известных не-VR библиотек: libavenhancements/libstagefright_wfd (QTI AV/WFD), libmmparserextractor (QTI MIME-константы; остаются AOSP-экстракторы), libbpfserver/nettools (`bpf::loadProgWithUnlink`), libmeminfo_utils (`ReadIonHeapsSizeKb`); ложные: libc_scudo/libscudo_wrapper/ppp-плагины (символы хоста) |
| VINTF | `checkvintf --check-compat` с заводскими vendor/odm/product: совместимо; к framework manifest добавлены заводские HAL sigma_miracast и atcmdfwd |
| dexpreopt | заводских oat/odex/vdex в образе нет; boot image 21 JAR на обоих ABI; 41 APK Source preopt; 84 перенесённых APK и ~20 APK product/vendor (их oat собран под заводской boot image) компилируются на устройстве |

Первая загрузка: PMS выполняет dexopt всех некомпилированных пакетов с `pm.dexopt.first-boot=quicken`; ожидаемо
5–15 минут экрана «оптимизация» (оценка, не измерено), затем фоновая компиляция speed-profile.

SELinux: заводской boot передаёт `androidboot.selinux=permissive` (так же на 5.13.7); Source userdebug init это
учитывает, поэтому пробный образ работает в permissive. Критерий «enforcing» заменяется на «permissive как на заводе,
denials с permissive=1 собраны как вход для политики».

## 4. Как ставился preview 01 (фактический метод)

Журнал `outputs/vr-preview-01-installation/state.json`: fastboot flash recovery и fastboot boot до авторизации
отвергались (`unknown command`). Сработало: `fastboot oem <key> unlock` на уже разблокированном загрузчике
(авторизация сессии PICO, данные не стирались), восстановление заводского recovery через fastboot, RAM-загрузка
подписанного офлайн-recovery (`fastboot boot`, раздел recovery не менялся), dm-linear отображение system внутри
super через dmctl (LP-метаданные не изменялись), запись system/vbmeta_system/vbmeta кусками по 64 МиБ через
adb push в RAM + dd, чтение и сверка SHA-256, перезагрузка. Текущее состояние шлема (проверено read-only 30.09):
system = preview 01 `ae6b3cb8…`, vbmeta `d85c4e65…`, vbmeta_system `ce696a78…`, boot Magisk `475ec054…`,
recovery заводской `68b36887…`, SELinux permissive (cmdline).

## 5. Установка source-trial-01

Инструмент: `tools/source-trial-install.py` (использует проверенные функции `offline-system-install.py`),
комплект: `outputs/source-trial-01-installation/{kit.json,state.json,misc-bcb-wipe-data.bin}`. Каждая пишущая
стадия требует `state.json → authorized.{fastboot,flash,wipe}` = true, которые ставятся только после явного
согласия пользователя в чате. Все команды из каталога проекта Windows, USB-кабель подключён.

1. `python tools/source-trial-install.py check` — локально: размеры и SHA-256 всех файлов комплекта.
2. `python tools/source-trial-install.py preflight` — read-only ADB: PICOA8110, boot = 475ec054…, recovery =
   заводской, system/vbmeta/vbmeta_system ∈ accepted_current (preview 01 / 5.13.7 / этот комплект), заряд ≥ 60 %.
3. `python tools/source-trial-install.py authorize` — `adb reboot bootloader`, проверка идентичности и `unlocked: yes`,
   `fastboot oem <key> unlock` (ключ из FAILSAFE_UNLOCK.bat не печатается).
4. `python tools/source-trial-install.py ram-boot` — `fastboot boot offline-recovery.signed.img` (b220f32a…), ждать
   root ADB с меткой `pico-vr-offline-trial-01` и без смонтированных блочных ФС.
5. `python tools/source-trial-install.py map` — проверка LP (SHA-256 первого МиБ super = 99e201f7…), dmctl-отображение
   system (сектор 2457536, 11142056 секторов), текущие хеши ∈ accepted_current, проверка бинарного транспорта.
6. `python tools/source-trial-install.py flash` — system (уже совпадающие 64-МиБ куски пропускаются), vbmeta_system,
   vbmeta; чтение и сверка SHA-256 каждого раздела; boot и LP проверяются после записи.
7. Очистка (рекомендовано, `authorized.wipe`): `python tools/source-trial-install.py bcb-wipe` — сохраняет текущие
   2048 байт misc, пишет BCB `boot-recovery` + `recovery\n--wipe_data\n` (bd6b67e8…), сверяет. Затем
   `adb reboot` из офлайн-recovery: загрузчик видит boot-recovery → заводской recovery (он в разделе) выполняет
   wipe_data (форматирует /data f2fs с флагами fstab и /metadata), очищает BCB, перезагружается в Source.
   Без очистки: пропустить шаг 7 и выполнить `adb reboot`.
8. Первая загрузка: ждать до 20 минут (dexopt). Затем `python tools/source-trial-install.py logs` (USB, adb без ключа).

Критерии успеха (проверять по порядку, результат записывать): `sys.boot_completed=1`; `ro.build.fingerprint` =
`Pico/Phoenix_ovs/PICOA8110:10/SOURCE_TRIAL_01/2026093001:userdebug/test-keys`; `getenforce` = Permissive (как на
заводе) и список avc; `ro.crypto.state=encrypted`, `/data` смонтирован, `vold.decrypt`/unlock пользователя 0
(`dumpsys user`), нет перезагрузок `init` по fs_mgr; `pidof system_server`, `dumpsys package` без failures,
`service list` содержит pvr_manager, pvrtracking, xrtruntime, ConfigurationService, pxr_notification,
virtual_input; процессы pvrtrackingservice, pxrcontrollerservice, pxrhmdservice, pxreyetrackingservice,
pxrseethroughservice, com.pico.xr.openxr_runtime, com.picoxr.xrshell/com.pvr.vrshell, com.pvr.home; затем
пользователь: изображение в шлеме, first-run, контроллеры, 6DoF, passthrough, Bluetooth, Wi-Fi.

## 6. Если загрузка не удалась: логи без возврата старой системы

Решение пользователя: между попытками не откатываться, а ставить следующую Source-сборку.

- Android поднялся хотя бы до `on boot` (adbd запускается, даже если zygote/system_server падают): `logs` собирает
  `logcat -b all`, `logcat -L` (pmsg прошлой загрузки, если ядро ведёт pmsg-ramoops), dmesg, /data/tombstones,
  dropbox, `/data/misc/logd` (logcatd пробного образа пишет до 1024 × 1 МиБ), причины перезагрузки.
- Перезагрузки до adbd / init fatal (4 падения критической службы → загрузчик): загрузчик показывает только `getvar`
  и `oem device-info` — логов нет. Далее `authorize --from-bootloader` → `ram-boot` → `logs`: офлайн-recovery монтирует
  pstore (RAM, не раздел) и забирает `console-ramoops*`/`pmsg-ramoops*` предыдущей загрузки (ядро с
  `ramoops_memreserve=2M`, нужна тёплая перезагрузка; наличие консоли ramoops ещё не подтверждено) и dmesg. /data
  зашифрован и из recovery недоступен.
- Следующая успешная загрузка: `logs` берёт pstore, `logcat -L`, накопленные `/data/misc/logd` и dropbox
  (SYSTEM_BOOT, SYSTEM_LAST_KMSG).
- В загрузчик без Android: сочетание клавиш питания и громкости (для этого шлема не проверено) или автоматически после
  init fatal.

Быстрая установка следующей сборки тем же методом: собрать новый комплект (`assemble-source-image.py`, новый kit.json
с добавлением текущего образа в accepted_current), затем `authorize` (из Android или `--from-bootloader`) →
`ram-boot` → `map` → `flash` (передаются только изменившиеся 64-МиБ куски) → при необходимости `bcb-wipe` → `adb reboot`.
Раздел recovery не трогается, поэтому заводской recovery всегда доступен для wipe.

Пробные (trial-only) изменения образа: `ro.adb.secure=0`, `persist.logd.logpersistd=logcatd` (+ size 1024,
`persist.logd.size=16M`), `persist.sys.disable_rescue=true` (RescueParty не отправит в recovery с запросом wipe),
заводские записи PICO в plat_mac_permissions, исключение install-recovery.sh. userdebug и `ro.debuggable=1` — свойства
сборки.

## 7. Комплект отката (только для экстренных случаев)

| Набор | system | vbmeta_system | vbmeta |
|---|---|---|---|
| factory-5.13.7 (`outputs/rollback-5.13.7-for-vr-preview-01`) | f61a27aa0ab0a91883e7d6f44b30609cc918fc293083a405f0f39110d76266f2 | c386ef8add95da92f7929b31a94433e03c6676d89f798c95e06dec4148278e45 | 635294b457fe7895ad011b66c950f8b6c79b82c1841548d16af19210754e15cb |
| vr-preview-01, установлен сейчас (`outputs/vr-preview-01-installation/system.raw.img`, `outputs/vr-preview-01`) | ae6b3cb890da878c2125df214e047bb1bbd2354447a3e312775dd1e158754a3f | ce696a78373f07499583f03fefc5d6ede3005069c00c1723ae7d8fedf7795f34 | d85c4e651581c1598f9b36fa6bca3cfd434619fbf66fe076d4b4817aacc18c07 |

Заводской recovery: 68b368875f31aa57b4468eefbf45fa714b17f6c7091f8ea39105ca26c4db53c8 (100 МиБ), офлайн-recovery:
b220f32af55395c75e112defc945fdd6bfe3dd28a454263e1f76159fcf042fff; boot не меняется (475ec054…). Все хеши файлов
перепроверены 30.09.

Шаги: `authorize` → `ram-boot` → `map` → `rollback --rollback-set factory-5.13.7` (или `vr-preview-01`, нужен
`authorized.rollback`) → `bcb-wipe` → `adb reboot`. После того как /data создан Source-образом, **очистка при откате
нужна**: packages.xml с тестовыми сертификатами Source, SETTINGS_VERSION и ключи FBE, созданные Source vold, заводской
системой не проверялись; без очистки допустима одна попытка загрузки, при зависании или цикле — wipe через BCB.
