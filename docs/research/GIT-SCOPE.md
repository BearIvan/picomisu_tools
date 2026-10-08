# Picomisu: состав Git-репозитория

В Git сохраняются изменения проекта: конфигурация устройства, патчи к AOSP,
скрипты сборки, исследования и установки, документация.
Исходная база AOSP: android-10.0.0_r47. Неизменённые исходники AOSP
и заводская прошивка не копируются в этот репозиторий.

Локальные отчёты, профиль конкретного шлема, дампы разделов, сборки,
резервные копии записей и ключи исключены из Git. Они остаются на диске.
Скрипты пока содержат пути исходного рабочего окружения и могут требовать
этих локальных файлов; один этот репозиторий не является полной резервной
копией окружения сборки или готовым универсальным установщиком.

`manifests/aosp-pinned.xml` фиксирует upstream-ревизии всех 733 проектов,
а `config/aosp-patches.json` связывает изменённые проекты с нашими патчами
и локальными коммитами. Manifest использует официальный сервер AOSP;
локальные коммиты не подставляются вместо доступных upstream-ревизий.
Сейчас экспорт охватывает frameworks/native, frameworks/base, ART, build/soong, build/make, system/bt,
packages/apps/Bluetooth, packages/services/Telecomm и Telephony, frameworks/opt/net/wifi,
frameworks/opt/telephony, system/connectivity/wificond, hardware/interfaces,
prebuilts/abi-dumps/vndk, prebuilts/abi-dumps/ndk, packages/apps/Settings, system/vold, system/core, system/extras,
packages/modules/NetworkStack, packages/apps/Nfc, system/sepolicy, frameworks/av, frameworks/opt/net/ims,
frameworks/layoutlib, vendor/qcom/opensource/interfaces, device/qcom/sepolicy,
vendor/codeaurora/telephony и vendor/qcom/opensource/fm-commonsys.
Четыре последних проекта не входят в AOSP manifest. Их upstream — коммиты CodeLinaro
тега LA.UM.8.12.c3-64900-sm8250.0: `platform/vendor/qcom-opensource/interfaces`
(a13dc017), `device/qcom/sepolicy` (830b6eb9, без патчей: QTI system policy как в QSSI),
`platform/vendor/codeaurora/telephony` (27d00010, без патчей: boot JAR telephony-ext) и
`platform/vendor/qcom-opensource/fm-commonsys` (0d397db4, 0115: FM HAL-клиенты только с
BOARD_HAVE_QCOM_FM; boot JAR qcom.fmradio).
Поля `upstream_remote`/`upstream_ref` находятся в `config/aosp-patches.json`.
system/core и system/extras (r47) несут только перенос CodeLinaro для wrapped keys ICE:
флаг fstab wrappedkey, обработку монтирования /data, per-boot ключ libfscrypt (0092–0093).
frameworks/av и frameworks/opt/net/ims несут заводские добавления к AIDL-таблицам (CodeLinaro
ICameraServiceListener и IImsUt, PICO IPlayer.setExtVolume, requestThreadCpuset, 0099/0101),
prebuilts/abi-dumps/ndk — эталон ABI libaaudio (0104), frameworks/layoutlib — метод IPowerManager (0105).
system/bt и packages/apps/Bluetooth дополнительно несут сигнатуру CodeLinaro IBluetoothPan.setBluetoothTethering
с пакетом вызывающего (0108–0109); PanService остаётся в сборке, в образ ставится заводской Bluetooth.apk.
build/make (0110) добавляет PRODUCT_BOOT_JARS_BEFORE_FRAMEWORK/PRODUCT_SYSTEM_SERVER_JARS_BEFORE_SERVICES
для заводского порядка class path; frameworks/native (0111) — Smartisan SoundSettings в libbinder,
prebuilts/abi-dumps/vndk (0112) — эталон ABI libbinder. Native-паритет (0116–0124): frameworks/native —
заводской слой libbinder и новая VNDK-SP libbinder_call_stat (0116), индекс OMX VR type (0117);
prebuilts/abi-dumps/vndk — эталоны libbinder/libbinder_call_stat (0118); build/make — список VNDK-SP (0119);
frameworks/av — цепочка getVRType (0120), клиент spatializer и libspatialaudio (0121); frameworks/base —
PlayerSpatialHelper/getVRType (0122), ImageManagerExt/VR SurfaceTexture в libhwui (0123), natives
ZygoteInit systemServerMmap/runtimeMmap (0124). Для source-trial-01: frameworks/av — AImageReader_setRtMode и
ALooper::getThreadId (0125), prebuilts/abi-dumps/vndk — эталон ABI libstagefright_foundation (0126); device.mk
наследует updatable_apex.mk (APEX-файлы вместо flattened, как требует заводской ro.apex.updatable=true). Заводские class path JAR и XML-списки
PeroptWhiteListParser в Git не хранятся: их извлекает `tools/install-device-tree.py`.
`tools/verify-patch-series.py` проверяет точное воспроизведение каждого дерева.
Файлы `pico_factory.te` в system/sepolicy и device tree создаёт
`tools/reconstruct-factory-sepolicy.py` из заводского plat_sepolicy.cil.

Изменения в деревьях исходников WSL следует отдельно сверять и сохранять
в виде патчей или коммитов соответствующих проектов. Первый коммит здесь
сохраняет текущие авторские файлы Windows-проекта и имеющийся патч.

Текущий гибридный preview загрузился на PICO 4 Pro SEKO. Пользователь
подтвердил работу домашнего VR-экрана, контроллеров и трекинга в игре.
Полный перенос framework и графики на AOSP ещё не выполнен.
Некоторые старые документы описывают этап подготовки до установки.
