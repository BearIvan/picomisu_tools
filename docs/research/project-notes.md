<p align="center"><img src="logo/picomisu.png" alt="Picomisu" width="320"></p>

> Picomisu build and install tools, checked out at `picomisu/` by `repo sync`. Build: `picomisu/build.sh`. Guide: [picomisu](https://github.com/BearIvan/picomisu#readme).

# Picomisu — AOSP 10 с VR для PICO 4 Pro SEKO

Название проекта, выбранное пользователем: **Picomisu**. Имя уже установленного образа — PICO AOSP VR preview 01; новое название предназначено для последующих сборок.

Подробный список оставшейся работы: [REMAINING-WORK.md](REMAINING-WORK.md).
Полный native API appendix: [API-NATIVE-GAPS.md](API-NATIVE-GAPS.md);
машиночитаемые декларативные различия: [API-GAPS.json](API-GAPS.json).
Открытые доноры для недостающих framework API: [FRAMEWORK-DONORS.md](FRAMEWORK-DONORS.md).

Текущая исходная точка включает 126 патчей к фиксированным AOSP-компонентам (29 компонентов).
Собран и проверен offline первый пробный образ Source system **source-trial-01** (Source framework/ART/SELinux/vold
плюс заводские VR-службы, библиотеки и APK, переподписанные ключом Source): состав, проверки, анализ подписей,
установка, получение логов и откат — [source-trial-01-plan.md](source-trial-01-plan.md). На шлем не записывался.
Native-паритет с factory (0116–0124, `validation/native-parity.json`): libbinder экспортирует заводской
PICO/Smartisan-слой (SceneInfoManager/SceneData, FreezeManager в заводском виде, ProcessState 2/4 МиБ,
freeze-ioctl, TF_REPORT_FROZEN, BinderCallsStats через новую VNDK-SP libbinder_call_stat), libhwui — 16 импортов
заводской libpxrguiex (ImageManagerExt, VR SurfaceTexture), перенесены 9 нужных natives (`_getVRType`,
PlayerSpatialHelperImpl с libspatialaudio); 26 factory/Source fixtures libbinder совпали на шлеме.
838 из 857 AIDL-таблиц framework совпадают с factory по именам и кодам, полные сигнатуры
(in/out, oneway) общих таблиц — 756 из 756: перенесены 6 таблиц с изменённой на заводе сигнатурой
и 18 интерфейсов только factory с потребителями (CodeLinaro, PICO/Smartisan из DEX),
FactoryOnlyAidlFixture 332/332 wire-сценариев на шлеме (`validation/factory-only-aidl-port.json`).
BOOTCLASSPATH и SYSTEMSERVERCLASSPATH Source-образа идут в заводском порядке (0110–0115,
`device/pico/PICOA8110/factory-bootclasspath.json`): telephony-ext и qcom.fmradio собираются из
CodeLinaro (36/36 и 27/27 классов и hidden-API флаги как у factory), закрытые QTI (tcmiface,
QPerformance, UxPerformance, WfdCommon) и PICO/Smartisan (sysmonitor-framework, sys-framework,
devicemiddlewareimpl, vrex-framework, vrex-services) — заводские DEX, связанные с перенесённым
Smartisan-слоем framework; `tools/check-factory-component.py` → `validation/factory-bootclasspath.json`.
sys-services и sysmonitor-services пока не на classpath (серверный Smartisan-слой, REMAINING-WORK).
Все 17 AIDL-таблиц framework с заводскими методами в конце совпадают с factory: CodeLinaro, PICO и
минимальный Smartisan-перенос, AppendedAidlFixture 1790/1790 (`validation/appended-aidl-port.json`).
vold/fs_mgr/libfscrypt поддерживают заводское шифрование userdata ключами ICE, обёрнутыми
keymaster (`fileencryption=ice,wrappedkey`): перенос из CodeLinaro, сверка с заводскими
бинарниками в `validation/vold-wrappedkey-port.json`; проверка разблокировки — только загрузкой.
Платформенная SELinux-политика совпадает с заводской: CodeLinaro device/qcom/sepolicy плюс
восстановленная из factory CIL политика PICO; заводские vendor/product компилируются с ней
при загрузке (offline-проверка `tools/check-sepolicy.py`, `validation/sepolicy-parity.json`).
QTI Wi-Fi vendor путь (второй STA, DPP, vendor supplicant/hostapd/FST HIDL) перенесён из CodeLinaro: `validation/qti-wifi-port.json`.
Перенесён собственный PICO API без открытых доноров (com.pvr, com.pico.api,
com.pxr, Features/PicoUtils, permissions, hidden-API флаги как у factory):
313 из 313 wire-сценариев совпали с заводским framework на обоих ABI.
Qualcomm API (Bluetooth, Wi-Fi, Telephony, UiMode, LockSettings, Face, View
content capture) перенесены с заводскими таблицами AIDL: 1190 из 1190 сценариев.
Хвост VR-цепочки (ActivityThread/ViewRootImpl/Display хуки, ExtPackageParserUtils,
PicoSystemConfig): 76 из 78 сценариев политики совпали, 2 ожидаемых отличия.
Перенесена цепочка VR-политики: ActivityInfo/ApplicationInfo extensions,
PackageParser VR metadata, ActivityThread force-render и маршрутизация
`ViewRootImpl.drawSoftware` на Surface VR canvas. Source framework/ART/Bionic с
compiled boot images прошли 23 проверки на каждом ABI; общий fixture на заводском
framework дал 58 совпадений из 60 сценариев на ABI и два задокументированных
отличия. Полного VR-рисования на общем образе этот этап не подтверждает.
Скан заводских потребителей OEM API: `validation/api-consumers.json`.

Предыдущая native-точка:
Перенесён PICO SurfaceMonitor и подключена запись кадров в MonitoredProducer.
На ARM64/ARM32 прошли 378 уникальных native gtests, 148 source/factory
сравнений состояния monitor и 24 Java/JNI проверки с compiled Source boot
images, ART и Bionic. Прежние tracker, frame-history и caller-ID проверки
также прошли. В исследованном графе 493 ARM64 ELF отсутствующих используемых
импортов libgui теперь нет; ARM32 runtime-граф ещё не исследован.
Проверки изолированы; общий образ с AOSP framework/ART/графикой на шлеме
и полная аппаратная проверка VR ещё впереди.

Собран первый проверочный гибридный образ PICO AOSP VR preview 01. AOSP 10 r47 и первый патч VR-протокола успешно скомпилированы; в образ подключён AOSP servicemanager, сохранён согласованный заводской framework/runtime PICO 5.13.7. Файлы, права, AVB и Windows-копии проверены. Загрузка проверена; пользователь подтвердил VR, контроллеры и трекинг в игре. Полный source-порт framework остаётся незавершённым. Актуальный ход переноса — [VR-PORT-STATUS.md](VR-PORT-STATUS.md). Комплект и точные границы — [vr-integration.md](vr-integration.md).

## Проверенные сведения

| Параметр | Результат |
|---|---|
| Устройство / продукт | `PICOA8110 / Phoenix_ovs`, модель `A8110` |
| Вариант | Пользователь указывает SEKO; на устройстве `ro.oem.state=true`, ZIP требует то же значение |
| Установленная система | PICO OS 5.13.7, Android 10, API 29 |
| Приложенный ZIP | PICO OS 5.13.8, Android 10, API 29; это другая версия |
| Выбранная заводская база | Скачанная 5.13.7 SEKO b9665 с fingerprint `smartcm.1761817909`; совпадает с установленной системой |
| Платформа / ABI | `kona`, ARM64 с поддержкой 32-битных ARM-приложений |
| Ядро на шлеме | `4.19.81-perf+` |
| Загрузчик | Свойства сообщают `unlocked`, `flash.locked=0`, `verifiedbootstate=orange` |
| Root | Обычный ADB shell имеет UID 2000; `su -c id` даёт UID 0 через Magisk |
| Treble / VNDK | Treble включён, VNDK 29 |
| Разделы | `system`, `vendor`, `product`, `odm` внутри динамического `super`; стандартная схема A/B-слотов не подтверждена |
| Super / группа | 8 589 934 592 байта; `qti_dynamic_partitions` — 8 585 740 288 байт |
| Метаданные LP | Два слота и резервные копии; все checksum проверены, размеры слота 0 совпадают с сохранённой 5.13.7, в слоте 1 другие размеры |

Подробный профиль находится в `device-profile.json`, результаты проверок — в `reports/verification.json`.

## Почему требуется порт VR

VR PICO занимает несколько слоёв системы. Сохранение одного `vendor.img` не переносит эти компоненты целиком.

| Слой | Наблюдения и необходимые действия |
|---|---|
| Ядро и низкоуровневые драйверы | На первом этапе использовать согласованные заводские kernel/DTB/DTBO и vendor/odm. Найден официальный `bytedance/phoenix-kernel` с базой 4.19.81 и конфигурацией KONA/PVR. Точное соответствие исходников установленной 5.13.7 Pro SEKO не подтверждено. |
| Нативные VR-службы в system | Работают `pvrtrackingservice`, `pxrcontrollerservice`, `pxrhmdservice`, `pxreyetrackingservice`, `pxrseethroughservice`, `pxrmrsystemservice`; их init-файлы находятся в `/system/etc/init`. Потребуются библиотеки, права, группы и cgroup-настройки этих служб. |
| Framework и system_server | В `framework.jar` определены классы `android.pico.*`, `com.pico.*`, а у `android.view.Surface` есть `setPvrStatus` и `nativeSetPvrStatus`. Найдены расширения VR-окон, поверхностей и системных служб. Порядок дополнительных JAR сохранён в `reports/device/classpaths.json`. Требуется перенос совместимых расширений или проверенная схема использования заводских компонентов. |
| Графика и JNI | Сохранены нативные зависимости и библиотеки, включая `libgui`, `libsurfaceflinger`, `libandroid_runtime`. Например, factory `libsurfaceflinger` зависит от дополнительных Qualcomm/OEM-библиотек. Совместимость с библиотеками будущей сборки AOSP ещё не проверена; наличие одинакового API 29 её не доказывает. |
| OpenXR и VR-оболочка | `com.pico.xr.openxr_runtime` установлен из `/system/priv-app/XRRuntime`. Он использует `android.uid.system` и сертификат PICO, отличающийся от стандартного AOSP platform certificate. Для новой системы требуется согласовать подписи, системные разрешения, загрузку runtime и взаимодействие с оболочкой. |
| Индивидуальная калибровка | Init PICO обращается к данным в `/mnt/vendor/persist/pvr` и `/mnt/vendor/pvr`. Эти данные конкретного шлема нужны для работы аппаратуры и не заменяются общим ZIP. |

На устройстве работают службы глаз и лица (`pxreyetrackingservice`, `eyed`, `picofacialdatadaemon`). Их перенос также входит в проверку функций Pro; факт работающего процесса ещё не является проверкой точности трекинга.

## Опубликованные исходники Phoenix

Найден официальный [репозиторий ByteDance phoenix-kernel](https://github.com/bytedance/phoenix-kernel), соответствующий подсказке пользователя о кодовом названии. README описывает VR-шлем Phoenix на SXR2130P, Android 10 и Linux 4.19.81. Зафиксирована ревизия `ceafd3afc0208c03e0eb7a1a60939d147f92d72a` от 15 сентября 2022 года; репозиторий архивирован. Это опубликованный код ядра, а не полный комплект исходников ОС PICO или готовый Android device tree.

В `arch/arm64/configs/vendor/kona-perf_defconfig` включены `CONFIG_ARCH_KONA`, `CONFIG_PVR_IPD` и `CONFIG_PVR_CAMERA_TEMP`. Те же параметры подтверждены чтением `/proc/config.gz` с работающего шлема. Аппаратные свойства сообщают KONA, SoC ID 356 и `qcom,kona-mtp`.

В опубликованном дереве найдены `drivers/char/pvr_ipd.c`, `pvr_cam_temp.c`, дополнения камеры `pico_utils` и `pvr_kernel_config`. Каталог `arch/arm64/boot/dts/vendor` с описаниями платы KONA в этом снимке отсутствует. В `drivers/char/Makefile` строка включения `pvr_ipd.o` закомментирована, хотя соответствующий параметр есть в defconfig. Это требует отдельной проверки схемы сборки и аппаратного варианта; наличие файла драйвера само по себе не подтверждает возможность заменить заводское ядро.

Метаданные и read-only сведения устройства сохранены в `reports/kernel-source/`. Исходники скачаны отдельно на ext4 в `pico4-pro/source/phoenix-kernel`; HEAD и tree совпали с зафиксированными данными GitHub, рабочее дерево чистое. Полный путь — `/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro/source/phoenix-kernel`. В конфигурации работающего ядра включён `CONFIG_PICO_RTT`, упоминаний которого в опубликованном коде не найдено. Обнаружены четыре различия значений параметров, явно заданных в public defconfig; это не сравнение двух полностью сгенерированных конфигураций. Точное соответствие исходников 5.13.7, полная сборка ядра и проверка загрузки пока не подтверждены.

Для первого прототипа оставляем проверенный заводской комплект kernel/DTB/DTBO и vendor/odm из 5.13.7. Публичный код используем для исследования драйверов и их интерфейсов. Перенос framework/system_server, графики, VR-служб и OpenXR остаётся необходимым этапом.

## Сравнение расширений framework с AOSP

Для первоначального исследовательского сравнения загружены восемь файлов официального `frameworks/base` из `android-10.0.0_r47`, commit `dff3deab5d25f8bbfd49abfb423043c9be47b7db`. Этот tag затем выбран как фиксированная экспериментальная база. Его соответствие исходной ревизии PICO не утверждается.

В семи выбранных классах PICO обнаружены 16 имён VR-методов, отсутствующих в соответствующих файлах AOSP: среди них `Surface.setPvrStatus`, операции рисования 2D-панелей в VR, управление яркостью HMD и обработка VR-клавиш. Результат находится в `reports/framework-bridge/api-gaps.json`. Это ограниченное сравнение имён; тела методов, поток регистрации JNI, Binder, ресурсы, нативный ABI и поведение ещё не проверены. Оно не является готовой реализацией совместимости.

Уточнены 17 Java-сигнатур, в том числе шесть native-деклараций. В заводских `libandroid_runtime.so` и `libandroid_servers.so` прочитаны кандидатные JNI-записи с учётом Android APS2/RELR и ELF-релокаций. Пять записей совпали по имени и дескриптору с выбранными Java-декларациями; для `nativeLockCanvasFor2DVr` найденная запись имеет другой тип результата. Поток регистрации классов и фактическая реализация этих методов ещё требуют исследования; такое совпадение не подтверждает ABI или работоспособность переноса. Результат — `reports/framework-bridge/jni-signatures.json`.

Хеши сохранённых `framework.jar`, `services.jar`, `libandroid_runtime.so` и `libservices.so` совпали с файлами проверенного заводского `system.img` 5.13.7. Дополнительная JNI-библиотека `libandroid_servers.so` извлечена непосредственно из этого образа. Это отдельная проверка выбранных файлов, а не проверка всех возможных Magisk-наложений.

Полное сравнение деклараций с собранной базой AOSP находится в
`reports/framework-bridge/full-declarations-diff.json`:

| JAR | Классы PICO / AOSP | Дополнительные классы в JAR PICO | Общие классы с различиями деклараций | Дополнительные native-декларации |
|---|---|---|---|---|
| framework.jar | 17 380 / 16 619 | 776 | 549 | 82 |
| services.jar | 6 763 / 6 061 | 834 | 414 | 6 |

В эти числа входят сгенерированные компилятором члены и изменения OEM вне VR;
они не являются количеством патчей, которые нужно переносить. Сравнивались
два JAR, а не весь эффективный classpath. Тела методов и совместимость native
библиотек не проверены. Помимо VR-поверхностей, различаются Binder, планирование
процессов, дисплейные события, камеры и пространственное аудио.

Для `nativeSetPvrStatus` сохранён разбор кода проверенного заводского
`libandroid_runtime.so`: вызывается `Surface::getIGraphicBufferProducer`, затем
виртуальный метод с кодом 10000 и указателем на входной статус. Точная обработка
этого кода и формат Parcel ещё требуют проверки. Это дополнительный аргумент
за согласованный набор factory framework/JNI/графики для первого VR-прототипа.
Материалы — `surface-native-analysis.json` и `native-set-pvr-status.asm.txt`.

## Сборочная основа AOSP

Полностью синхронизированы 733 проекта `android-10.0.0_r47`; manifest commit —
`aaf063a1ac9b5dd39b891350c5a4bf06b905a7f6`. Точные ревизии каждого проекта
записаны в `reports/aosp-preparation/revisions.xml`. Используется проверенный
`repo v2.68.1`; синхронизация завершилась с кодом 0. Деревья Pixel сохранены.

```text
Исходники: /mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro/source/aosp-10
Выход:     /mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro/out/aosp-10
Продукт:   aosp_pico4pro-userdebug
Устройство: device/pico/PICOA8110
```

Исходный device tree хранится в Windows-каталоге `device/pico/PICOA8110` и
копируется в отдельное дерево AOSP. Проверка `lunch`, SDK 29, ARM64/ARM32 и
`m -j8 nothing` прошла; это проверка конфигурации и графа сборки, а не образа
или VR. Vendor/product/odm подключены ссылками на проверенные образы 5.13.7.
Сборка super отключена; стандартный A/B boot не предполагается. Проверочная упаковка VR и development AVB настроены внешними
скриптами. Production-подпись и проверка на шлеме не завершены.

В Android 10 `BOARD_BUILD_SYSTEM_ROOT_IMAGE=false` сохраняет first-stage
ramdisk, при этом system.img всё равно содержит root и system. Это совпадает
с заводской структурой и [правилами AOSP](https://source.android.com/docs/core/architecture/partitions/system-as-root).
Флаг динамических размеров обязателен для этого Android 10; размер конечного
образа нужно отдельно сверить с существующей LP-разметкой перед испытанием.

Сборка базовых `framework`/`services` завершилась с кодом 0; получены JAR,
а также автоматически построенные ART/dexpreopt-артефакты. В WSL добавлен
недостающий GNU m4 1.4.19, нужный flex/bison старой ветки. Сборка и дочерние
процессы ограничены CPU 0–7 и `-j8`. Проверочный VR-образ создан; работа VR на нём ещё не проверена.

## Граф заводских VR-зависимостей

По картам девяти ранее сохранённых процессов проанализированы 493 ELF-файла
проверенной 5.13.7, включая содержимое APEX `com.android.runtime` и
`com.android.conscrypt`. Для каждого DT_NEEDED сохранены кандидаты из карты
процесса и из заводской файловой инвентаризации. Все имена зависимостей имеют
кандидатов в заводском наборе. В system_server 18 зависимостей не отражены в
сохранённой карте, хотя файлы есть в образах; также есть несколько библиотек
с одинаковыми SONAME в разных пространствах linker. Выбор правильного
пространства и ABI-совместимость с AOSP ещё не проверены.

Путь `/system/lib64/agent_frame.so` из живого процесса отсутствует в заводских
образах; его содержимое не перенесено в набор заводских компонентов. Путь в
карте процесса сам по себе не подтверждает хеш загруженного объекта.

Граф — `reports/vr-dependencies/factory-graph.json`, итоги — `summary.json`.
Копии библиотек и APEX для анализа остаются на ext4 в
`pico4-pro/analysis/stock-5.13.7-native`. Это исследовательский набор, который
пока не является готовым списком компонентов прошивки; другие службы Pro и
ленивая загрузка могут добавлять зависимости.

## Исследовательские материалы

Крупные образы хранятся на физическом ext4-диске WSL отдельно от завершённых сборок Pixel:

```text
/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro/stock/5.13.8-SEKO
/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro/stock/5.13.7-live
/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro/stock/5.13.7-SEKO
```

Первый каталог содержит восстановленные `system/vendor/product/odm`, `boot`, `recovery`, `DTBO`, `vbmeta`, VINTF-описания и `extraction.json`. CRC всех файлов ZIP и хеши/hashtree образов проверены. Проверка AVB использовала встроенные публичные ключи; отдельная доверенная привязка к ключу производителя и подпись всего OTA не проверялись.

UUID раздела ext4 — `a00da05f-1eb2-44b6-99f0-9109391f67dc`. После остановки WSL ручное монтирование может исчезать; перед обращением к образам нужно проверить `lsblk -f` и mountpoint и восстановить подключение проверенного UUID. Отсутствие каталога после остановки WSL не означает потерю файлов.

Второй каталог содержит завершённые копии 12 разделов установленной 5.13.7 и калибровок. Все файлы независимо перечитаны, размеры и SHA-256 совпали с журналом захвата. Копия `boot` включает текущие изменения Magisk. Это не полный резервный образ устройства: `userdata`, полная GPT и все физические firmware-разделы не копируются. Калибровки сняты с работающего устройства; восстановление этих копий не испытывалось.

Третий каталог содержит чистые заводские boot/recovery/DTBO/vbmeta и ссылки на проверенные системные разделы из второго каталога. AVB-проверка подтвердила соответствие `system/vendor/product/odm` заводским подписанным описаниям 5.13.7.

Исходный [ZIP 5.13.7 SEKO b9665](C:/Users/RedPanda/Documents/ChatGPT/Android/pico4-pro/stock/5.13.7-202510301735-RELEASE-user-phoenix-b9665-42be801fae.zip) сохранён в Windows-проекте. Размер — 3 723 574 018 байт. MD5 — `42be801fae5de28d37347d5984b2ee96`; его первые десять символов совпадают с опубликованным MD5 tag `42be801fae`. CRC всех ZIP-записей проверен. Подпись всего OTA проверена OpenSSL и привязана к публичному OTA-сертификату установленной прошивки. Совпадение модели, OEM state, API 29 и полного fingerprint проверено по метаданным самого ZIP.

SHA-256 скачанного ZIP:

```text
00b2610888995558878a7d246996e38da51729011f45dd7ef114f9396aa6feba
```

Ссылка на файл найдена в [таблице автора исследования PICO](https://pico.crx.moe/docs/picoos-research/version-table/); байты загружены непосредственно с [CDN PICO](https://lf-stone-iot-va.dlpicovr.com/obj/stone-iot-us/5.13.7-202510301735-RELEASE-user-phoenix-b9665-42be801fae.zip). На шлем ничего не устанавливалось.

В Windows-проекте сохранены:

- `reports/device/`: свойства, службы, init/fstab, пути библиотек процессов, копии выбранных ELF/JAR/APK, результаты анализа DEX и ELF;
- `reports/stock-5.13.8/`: полный список файлов четырёх ext4-образов, выбранные текстовые конфигурации и хеши;
- `reports/stock-5.13.7/`: проверка загрузки, подписи OTA и извлечения чистых заводских компонентов;
- `reports/baseline-5.13.7/`: журнал захвата 12 разделов, независимая проверка копий и список файлов установленной системы;
- `reports/verification.json`: границы выполненной проверки.

Серийный номер не записывается в диагностический профиль. Калибровки и системные бинарные копии остаются локально. Файлы updater-script из ZIP прочитаны как данные; инструкции установщика не выполнялись.

## Следующий этап разработки

1. Зафиксировать одну согласованную базу компонентов; для первого прототипа предпочтительна установленная и работающая 5.13.7. Не смешивать её framework, нативные библиотеки и драйверы с 5.13.8 без проверки ABI и интерфейсов.
2. База AOSP 10 r47, начальная конфигурация PICO и сравнение деклараций собранных framework/services уже подготовлены. Следующий шаг — упаковка согласованного заводского VR-framework/runtime в экспериментальный AOSP с последующим переносом расширений в исходники. Это гибридный первый прототип; полный framework-порт ещё не реализован.
3. По девяти процессам построен граф 493 заводских ELF. Дополнить его другими службами Pro и ленивой загрузкой, разрешить linker namespaces и проверить Java/JNI, Binder/HIDL и графические интерфейсы между заводскими файлами и AOSP.
4. Реализовать интеграцию framework/system_server, нативных VR-компонентов и OpenXR. Согласовать подписи APK с системным UID и разрешениями. Схема подписи нового проекта пока не настроена.
5. Собрать экспериментальный образ. Ограничение проекта — максимум 8 CPU: `taskset` на восемь доступных CPU, `m -j8`, для синхронизации `repo sync -j8`.
6. После готовности образа отдельно согласовать проверку загрузки на устройстве. Критерии результата: стереоизображение, стабильная частота кадров, 6DoF, контроллеры, passthrough, границы игровой зоны, IPD, глаза/лицо и запуск OpenXR-приложения. Эти проверки на новой системе ещё не проводились.

## Инструменты

Windows Python уже содержит `brotli`, `pyelftools` и `cryptography`. `inspect-stock.py` использует Python и read-only `debugfs` внутри WSL. Android SDK предоставляет ADB, AAPT и APK signer.

- `tools/collect-device.py`: read-only снимок устройства через ADB;
- `tools/extract-stock.py`: восстановление образов полного BLOCK OTA из Brotli и transfer-list v4; incremental-команды отклоняются;
- `tools/capture-baseline.py`: чтение разделов проверенной 5.13.7 через существующий root, без записи на шлем;
- `tools/verify-baseline.py`: независимое повторное чтение копий и сравнение размеров/SHA-256 с журналом захвата;
- `tools/resume-system.py`: продолжение частичной копии system блоками по 64 МБ внутри WSL;
- `tools/download-5.13.7.py`: возобновляемая загрузка конкретной заводской 5.13.7 с проверкой диапазонов и итогового файла;
- `tools/verify-ota-signature.py`: проверка подписи всего Android OTA и сертификата подписанта по сохранённым публичным OTA-сертификатам;
- `tools/inspect-live-vr.py`: анализ классов и методов DEX, при явном `--collect-maps` — чтение путей библиотек VR-процессов через su;
- `tools/inspect-native.py`: зависимости ELF и символы VR;
- `tools/inspect-stock.py`: инвентаризация ext4 и извлечение выбранных настроек без монтирования образов.
- `tools/map-framework-bridge.py`: ограниченное сравнение имён выбранных VR-методов с зафиксированным AOSP framework;
- `tools/fetch-phoenix-kernel.py`: загрузка фиксированной ревизии официального ядра Phoenix на проверенный ext4, без выполнения его сборочных скриптов;
- `tools/inspect-phoenix-kernel.py`: сравнение опубликованной конфигурации ядра с конфигурацией работающего шлема и проверка состава исходников.
- `tools/inspect-vr-jni.py`: выбранные DEX-сигнатуры и кандидатные JNI-таблицы в сохранённых ARM64-библиотеках;
- `tools/verify-framework-copy.py`: сверка выбранных JAR/ELF с проверенным заводским system через read-only debugfs;
- `tools/extract-android-servers.py`: извлечение JNI-библиотеки system_server из заводского образа без запуска её кода.
- `tools/prepare-aosp.py`: инициализация/синхронизация зафиксированного AOSP на ext4, максимум восемь CPU;
- `tools/map-vr-dependencies.py`: граф DT_NEEDED по заводским ELF и наблюдаемым картам процессов, включая APEX;
- `tools/parse-lp-metadata.py`: проверки SHA-256 геометрии и всех прочитанных LP-копий, сравнение с захваченными разделами;
- `tools/install-device-tree.py`: установка собственного device tree с сохранением возможных локальных изменений;
- `tools/validate-device-config.sh`: `lunch`, dumpvars и `m -j8 nothing` для проверки конфигурации;
- `tools/build-framework-reference.sh`: сборка базовых JAR для анализа деклараций;
- `tools/compare-framework-api.py`: сравнение объявленных классов, методов и полей скомпилированного AOSP и заводских JAR.

Скрипты создания образов отказываются заменять уже существующие файлы. Их результат является материалом исследования, а не готовой прошивкой.

Первичные сведения об архитектуре: [GSI в документации Android](https://developer.android.com/topic/generic-system-image), [разделение system/vendor/product](https://source.android.com/docs/core/architecture/partitions/shared-system-image). Официальные публичные [репозитории PICO Developer](https://github.com/Pico-Developer) содержат SDK и примеры приложений. Найдены отдельные официальные исходники ядра [Phoenix](https://github.com/bytedance/phoenix-kernel); полный проверенный комплект исходников ОС для этого устройства пока не найден.
