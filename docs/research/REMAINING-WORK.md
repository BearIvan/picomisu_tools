# Picomisu: оставшаяся работа

Снимок на 30 сентября 2026 года, 126 патчей.
Native: `611325dad0e3017d966dbe560accf1a2322a59fc`;
framework: `144d2a35fa27e9a06403390f17b594caf21f0287`;
build/make: `d224f24cebae6685c6af9ae7fb22bb4162e29e9b`;
prebuilts/abi-dumps/vndk: `44f589a4d08435e2dbab33409c63b42e6671e1b1`;
vendor/codeaurora/telephony: `27d0001003086c8e8889b69fbfa260bb7804740e` (CodeLinaro, без изменений);
vendor/qcom/opensource/fm-commonsys: `2259abfa6048b73341e5dce9a17a88ac3a30a19a`;
system/bt: `b4d6e87a425154a332234ddad6ab03b0656f8af2`;
packages/apps/Bluetooth: `a65c7b27e6e6931603bac2e33dcaa78de027c280`;
frameworks/av: `1accb032cdd99fb1d4712c0ddd4710ca0425dc9b`;
frameworks/opt/telephony: `ad8c52cc0ae89303fa13e1f9351ea61d1322974e`;
frameworks/opt/net/ims: `c71c952e1f1e67ad981a78791b4ff3f33d5f92cf`;
wifi: `6cb69f3f6fa34203b18a06c3f44de6afae3abf95`;
build/soong: `1725e6ee745ff1c24b11e3cd63d5c85e0d2162ad`;
ART: `fe5349b2731357313891c9e0ced8340edb4887a8`;
system/sepolicy: `b70dcb852d79b48b8698d71b0199482b85910d3a`;
device/qcom/sepolicy: `830b6eb97a27468a23fe5e91ef912d4df0d22066` (CodeLinaro, без изменений);
system/vold: `06a50b10bd9f9e398450e4f3ab1ea56fcc6be884`;
system/core: `e50e65e1f3878c0816e671407ee81d3d51fc2d88`;
system/extras: `72fdb7cfdc0a3a84191e9ebdc48cd8a18b682565`.

Это полный перечень известных незавершённых работ и проверок на этой точке.
Окончательный перечень требуемых OEM API ещё нужно вывести из вызовов и
эффективных classpath/ELF dependencies. Декларативная разница двух JAR
не определяет все требования загрузки или VR.

Статусы: **перенос** — реализации ещё нет; **интеграция** — проверенный
компонент ещё не включён в общую систему; **проверка** — реализация есть,
но указанное поведение ещё не подтверждено; **аудит** — необходимость или
совместимость ещё не установлена.

## Что уже готово

- AOSP 10 r47 для PICOA8110 собирается через WSL/ext4 с пределом 8 CPU.
- 126 патчей точно воспроизводят 29 сохранённых component Git tree.
- Пробный образ source-trial-01 собран и проверен offline (`tools/assemble-source-image.py`,
  `tools/check-source-image.py`, `validation/source-trial-01.json`, [source-trial-01-plan.md](source-trial-01-plan.md)):
  readback 5766 записей, e2fsck, AVB, VINTF, class path, 0 отказов PMS, набор пакетов = заводскому (186).
- Полная сборка droid проходит (0070–0124, `validation/full-build.json`).
- Native-паритет (0116–0124, `validation/native-parity.json`, `validation/native-parity-port.json`): libbinder
  экспортирует заводской PICO/Smartisan-слой (SceneInfoManager/SceneData для заводского pxrmediametrics,
  FreezeManager в заводском виде, ProcessState 2/4 МиБ, freeze/pids ioctl, TF_REPORT_FROZEN, IProducerListener
  security context, BinderCallsStats через новую VNDK-SP libbinder_call_stat) — остаток 7/6 шаблонов readAligned;
  libhwui даёт 16 импортов заводской libpxrguiex (ImageManagerExt, VR SurfaceTexture, раскладка/vtable как у
  factory); перенесены 9 нужных natives (`_getVRType` со всей цепочкой libmedia/libstagefright,
  PlayerSpatialHelperImpl с libspatialaudio и клиентом spatializer libaudioclient). На шлеме: 26 factory/Source
  fixtures libbinder, 9 контрольных точек удалённой регистрации FreezeManager, связывание libpxrguiex с Source
  libhwui, gtests группы (`bufferqueue-test-34`) и 30 Java fixtures/все wire-наборы (`framework-boot-image-test-28`).
- BOOTCLASSPATH/DEX2OATBOOTCLASSPATH/SYSTEMSERVERCLASSPATH Source-образа в заводском порядке (0110–0115,
  `device/pico/PICOA8110/factory-bootclasspath.json`, `validation/factory-bootclasspath.json`): 23 boot JAR,
  21 в boot image. telephony-ext и qcom.fmradio из CodeLinaro (36/36, 27/27 классов и hidden-API флаги как
  у factory), заводские DEX tcmiface/QPerformance/UxPerformance/WfdCommon и PICO/Smartisan
  sysmonitor-framework/sys-framework/devicemiddlewareimpl/vrex-framework, vrex-services. Для всех 11
  сохранённых JAR `tools/check-factory-component.py`: 0 неразрешённых ссылок (3 принятых в sys-framework —
  VMDebug libcore/ART), AIDL-таблицы как у factory, пакеты в whitelist. Smartisan-слой framework
  (`validation/smartisan-layer-port.json`): 52 новых класса framework (47 идентичны factory), 20 services (18).
  FactoryClassPathFixture: 218/218 классов с тем же boot-image статусом, что на заводе (`framework-boot-image-test-27`,
  30 fixtures на обоих ABI; прежние wire-наборы 100%).
- Сигнатуры 6 AIDL-таблиц и 18 интерфейсов только factory с потребителями перенесены (0106–0109,
  `validation/factory-only-aidl-port.json`): 838/857 таблиц идентичны по именам/кодам, сверка полных сигнатур
  (`compare-aidl-tables.py --signatures`) 756/756; CodeLinaro (IVibratorService AudioAttributes, gesture exclusion
  unrestricted, forceUpdateIfaces без VpnInfo, IBluetoothPan pkgName, IStatsManager rollback reason, ICarStatsService
  и statsd CarStatsPuller), PICO/Smartisan из DEX (IBackupAgent paths, FreezeManager, SceneInfoManager, Prefetch,
  PowerAdvisor, TransferServer, SysTransServer, keyguard callbacks и др.). framework 163/164, services 30/35;
  FactoryOnlyAidlFixture 332/332 на обоих ABI (`framework-boot-image-test-26`, 29 fixtures).
- 17 AIDL-таблиц с заводскими методами в конце совпадают с factory (0097–0105,
  `validation/appended-aidl-port.json`): 820/857 таблиц идентичны; CodeLinaro (split permissions, subscription
  plans, deferred recents cancel, IImsUt, camera open/close, notePhoneDataConnectionState serviceType), PICO из DEX
  (backup/restore, installer flags, virtual input, USB accessory, ext volume, sensor screen feature, thread cpuset,
  activity timeout) и минимальный Smartisan-перенос (SmtEx/SysMoEx/OptEx интерфейсы и серверы с мостами по умолчанию).
  framework 166/174, services 84/125, telephony-common 8/15 классов по перенесённым членам; AppendedAidlFixture
  1790/1790 wire-сценариев на обоих ABI (`framework-boot-image-test-25`, 28 fixtures).
- Шифрование userdata ключами ICE, обёрнутыми keymaster (`fileencryption=ice,wrappedkey`),
  перенесено из CodeLinaro (0091–0096): дерево vold = CodeLinaro (кроме Android.bp), флаг
  wrappedkey в fs_mgr, per-boot ключ libfscrypt, теги keymaster FBE_ICE/KEY_TYPE,
  CONFIG_HW_DISK_ENCRYPTION(_PERF) с заводским libcryptfs_hw. Source vold совпадает с заводским
  по DT_NEEDED (порядок тоже) и импорту libcryptfs_hw (`validation/vold-wrappedkey-port.json`).
- Платформенная SELinux-политика совпадает с factory по объявлениям, allow/dontaudit/allowx,
  переходам, genfscon и контекстам (0088–0090, донор device/qcom/sepolicy, реконструкция PICO):
  offline boot compile с заводскими vendor/product проходит, 1254 versioned-атрибута
  отображаются как у factory, 0 расхождений меток 5992 путей system (`validation/sepolicy-parity.json`).
- 19 AIDL-таблиц со сдвигом кодов совпадают с factory (0075–0087, `validation/shifted-aidl-port.json`):
  794/857 таблиц идентичны; framework 95/96, services 65/83, telephony-common 17/20 перенесённых
  классов; ShiftedAidlFixture 1207/1207 wire-сценариев на обоих ABI (`framework-boot-image-test-24`).
- IAudioService совпадает с заводской таблицей (131), перенесены Spatializer (бэкпорт Android 13)
  и аудио-служба CodeLinaro (0073–0074, `validation/audio-port.json`): framework 102/103,
  services 36/38. AudioApiFixture 346/346 на шлеме на обоих ABI (`validation/audio-api-wire.json`).
- Заводской Bluetooth-стек подключён к Source framework (0067–0069, device tree, SELinux):
  `validation/factory-bluetooth.json`, `validation/factory-bluetooth-port.json`.
- QTI Wi-Fi (0059–0066): wifi-service, wificond и android.net.wifi синхронизированы с CodeLinaro
  LA.UM.8.12.c3-64900 (QtiClientModeImpl/второй STA, DPP, getCapabilities, doDriverCmd, hostapd/FST
  vendor HIDL). wifi-service: 2250/2327 классов совпали с factory (QTI путь 606/618), все
  929 HIDL классов идентичны по инструкциям, 69 hash chain совпали с .hal/current.txt;
  раскладка StaLinkLayerStats VNDK = factory (`validation/qti-wifi-port.json`).
- Хвост VR-цепочки (0058): 76/78 сценариев VrPolicyFixture совпали с factory, 2 ожидаемых
  (`validation/vr-policy-port.json`, `validation/vrchain-port.json`).
- Перенесены Qualcomm API из CodeLinaro с заводскими таблицами AIDL и серверами:
  1190/1190 wire-сценариев совпали с factory на обоих ABI (`validation/qualcomm-api-port.json`).
- Перенесён PICO API без открытых доноров: 15 AIDL, клиентские классы, Features/PicoUtils,
  permissions и hidden-API флаги; 313/313 wire-сценариев совпали с factory на обоих ABI.
- Заводская 5.13.7 автоматически скачивается по pinned URL/SHA-256 и извлекается.
- Перенесены исследованные графические query/fence/freeze/cache/display-flags,
  single-layer composition, EGL tracker, SurfaceClient и SurfaceMonitor API.
- В исследованном графе 493 ARM64 ELF нет отсутствующих используемых импортов
  libgui; исследованные размеры vtable не расходятся.
- 378 native gtests прошли для текущих GUI/Binder; Source/factory monitor
  сравнения дали 148 совпавших снимков состояния с Binder/file/lookup traces.
- Перенесён Surface VR canvas API и цепочка VR-политики ActivityInfo →
  PackageParser → ActivityThread → ViewRootImpl.drawSoftware. Source
  Java/JNI/ART/Bionic с compiled boot images прошли по 23 fixtures на ABI;
  на заводском framework 58 из 60 общих сценариев совпали на каждом ABI,
  два отличия ожидаемые (обработка null вместо NullPointerException).
- Выполнен статический скан заводских потребителей OEM API (ниже).
- Гибридный preview установлен. Пользователь подтвердил домашний VR экран,
  трекинг, контроллеры и трекинг в игре. Большая часть установленной системы
  пока заводская; этот результат не подтверждает VR на полном Source стеке.
- Девять ценных видеозаписей сохранены и проверены по хешам. Это не полный
  backup userdata. Замена выбранных ключей сейчас не входит в задачу.

## 0. Блокеры загрузки Source образа

Образ для первой пробы: `outputs/source-trial-01` (system c91884b3…, vbmeta 0782a10f…, vbmeta_system db553e3f…),
установка — [source-trial-01-plan.md](source-trial-01-plan.md), рекомендована очистка userdata/metadata.

| Работа | Статус | Что должно подтвердить завершение |
|---|---|---|
| Загрузка source-trial-01 | проверка | boot_completed, /data разблокирован, system_server и VR-службы (pvrtracking, pxr*, xrtruntime, XRShell/VRShell) работают; проверка пользователем изображения, контроллеров, 6DoF, passthrough. Логи и повторная установка без отката — раздел 6 плана |
| Подписи: platform-ключ PICO недоступен | проверка | 77 заводских APK переподписаны ключом Source, 3 android.uid.system из product продублированы на /system, android.uid.phone и прочие APK product/vendor остаются PICO (seinfo через заводские записи mac_permissions в пробном образе). Проверить на шлеме: установка всех 186 пакетов, platform-права PICO-приложений, проверка сертификата в store2d (MD5 platform PICO зашит в DEX) |
| SettingsProvider версии 183 (PICO) | перенос | Source — 182; с сохранёнными данными 5.13.7 настройки пересоздаются. Найти и перенести заводской шаг 182→183 |
| Оставшиеся native-разрывы перенесённых заводских библиотек | перенос/аудит | libavenhancements/libstagefright_wfd (QTI AV/WFD), libmmparserextractor (MEDIA_MIMETYPE_* QTI), libbpfserver/nettools (`bpf::loadProgWithUnlink`), libmeminfo_utils (`ReadIonHeapsSizeKb`), BrowserChrome → `smartisanos.config.ProductConfig` |
| Место в logical system | аудит | Source-слой на ~80 МиБ больше заводского; убрано демо-видео 300 МиБ (свободно ≈298 МиБ). Для полноты: release-вариант runtime APEX или пересмотр pre_resource |
| Trial-only настройки | интеграция | ro.adb.secure=0, logcatd, disable_rescue, PICO-подписи в mac_permissions, исключение install-recovery.sh — убрать или заменить для релиза |
| SELinux: заводская vendor/product политика поверх Source plat policy | проверка | Offline решено (0088–0090): init-компиляция secilc проходит, factory-only типов/allow/контекстов 0, 1254 versioned-атрибута как у factory, метки 5992 путей совпадают (`tools/check-sepolicy.py`). Осталось: загрузка в enforcing без новых denials; 970/921 различий exception lists neverallow (при загрузке не проверяются, `-N`); 1 свойство `ctl.android.hardware.dumpstate` (r47 exact) |
| vold/fs_mgr: wrapped keys ICE (`fileencryption=ice,wrappedkey`) | проверка | Статически решено (0091–0096, `validation/vold-wrappedkey-port.json`): все 16 флагов заводского fstab разбираются (раньше `wrappedkey` игнорировался); vold генерирует/экспортирует ключи через keymaster (exportKey RAW, upgradeKey, FBE_ICE/KEY_TYPE) как заводской; маркеры и DT_NEEDED Source vold, libfs_mgr, libfscrypt, init совпадают с factory. First-stage init остаётся заводским (boot сохранён). Осталось только при загрузке: разблокировка существующего userdata (TA keymaster принимает заводские blob, PFK принимает ключи), unlock CE через Source LockSettings/Gatekeeper, откат checkpoint=fs, отсутствие denials. Не перенесено (не связано с ключами): PICO NTFS/exFAT и логи в vold, stabd/kernellog в fs_mgr, FFU/memcg/cpuset в init |

## 1. Framework и Java/JNI

| Работа | Статус | Что должно подтвердить завершение |
|---|---|---|
| ActivityInfo/ApplicationInfo VR extensions: flags, 2D metadata, copy, Parcel | проверка | Перенесено (0034); значения, copy и байты Parcel совпали с factory. Осталось: VR metadata до приложения через настоящий PackageManager/Binder на общем образе |
| PackageParser: заполнение VR metadata из манифеста | перенос/проверка | parseVrFlags (0035), ExtPackageParserUtils, parseBaseApkCommon, ActivityThread/ViewRootImpl/Display хуки и полный PicoSystemConfig (0058): 76/78 сценариев совпали, 2 ожидаемых. Осталось: проверка на реальных APK |
| ActivityThread: выбор matching Activity и force-render | проверка | Перенесено (0036), 8 сценариев совпали, запись без Activity — задокументированное отличие. Осталось: другие hooks IExtActivityThread, реальные Activity |
| ViewRootImpl: cached setting, permission-controller exemption, display ID 0, drawSoftware routing | проверка | Перенесено (0037); 12 сценариев политики совпали с factory, drawSoftware маршрутизирован на fixture Surface. Осталось: реальные окна/2D-панели на общем образе, прочие hooks IExtViewRootImpl |
| Display/ExtDisplay: VR loading, VR 2D, non-focusable flags | перенос/аудит | Исследованные predicates и передача flags от system_server до окон |
| WindowManager/display policy для VR окон и virtual displays | перенос/аудит | Lifecycle окон, surfaces, фокус и размеры на общем Source system_server |
| PhoneWindowManager: VR settings, системные кнопки, отправка событий PVR | перенос/аудит | Сопоставление factory вызовов и работа кнопок/навигации |
| LightsService: PXR HMD brightness и animation JNI | перенос | Три factory JNI сигнатуры, рабочее управление яркостью |
| SysTrans/TransferServer Java interfaces, managers и серверная интеграция | перенос/аудит | Настоящие регистрации служб и совместимые Binder команды/config replies |
| Binder Java/JNI: calling TID, frozen PID, target/client/server PID, freeze controls | перенос/проверка | libbinder-часть перенесена (0116): setPidFreeze/getTargetCalleePid/getBinder*Pids, TF_REPORT_FROZEN в BpBinder, ProcessState 2/4 МиБ (+ natives ZygoteInit 0124); 26 factory/Source fixtures с перехваченными ioctl совпали. Осталось: Java-natives Binder setPidFreeze*/getTargetCalleePid/setBinderCtlMask и JNI getBinder*Pids (только для сохраняемых sys-/sysmonitor- JAR), FrozenObjectException, реальные межпроцессные сценарии на заводском kernel |
| Process/cgroup/freezer/CPU affinity и scheduling дополнения | перенос/аудит | Выделить используемые VR вызовы; проверить поведение с выбранным kernel/cgroup |
| HardwareRenderer/ThreadedRenderer/HWUI, Surface last-input/monitor/color-space, SurfaceTexture extensions | перенос/аудит | SurfaceTexture VR/ImageManagerExt для заводской libpxrguiex перенесены (0123): 16 импортов, раскладка/vtable как у factory, связывание на шлеме. Осталось: RenderProxy setSurface(bool)/doAnimation/notifyMonitorStatsChanged и natives HardwareRenderer/SurfaceTexture без потребителей, GL-путь libpxrguiex на общем образе, реальное аппаратное рисование |
| Spatial audio orientation/pose, AudioSystem и multimedia VR type | перенос/аудит | Java Spatializer/IAudioService перенесены (0073). Клиентская часть перенесена (0120–0122): PlayerSpatialHelper(Impl) с 7 natives, libspatialaudio, клиент ISpatializer/INativeSpatializerCallback и коды IAudioPolicyService 73–76 в libaudioclient; `MediaMetadataRetriever.getVRType` со всей цепочкой libmedia/libmediaplayerservice/libstagefright (OMX_IndexConfigSyncVRTypeDetect). Осталось: серверный Spatializer audioserver (libaudiopolicyservice, pose controller, spatializer output в APM, libvraudio) — Source отвечает UNKNOWN_TRANSACTION; сдвиг vtable IAudioPolicyService после setSurroundFormatEnabled (заводские setParameters(String8), `bool*` в getOutputForAttr); SpatialCoordConverter Java/JNI; MediaCodec::updateVrTypeCalculator (libpxrmediametrics); AudioSystem.TrackStateCallback (native нет и на заводе); PICO ExtAudioService/AudioEventTracker; аппаратные audio/media сценарии |
| Camera/input native дополнения | перенос/аудит | Установить потребителей; проверить passthrough/camera/input пути |
| Остальные OEM классы, методы, поля, interface lists и resources | перенос/аудит | Скан выполнен (`validation/api-consumers.json`). PICO API без доноров перенесён (0039–0045, `validation/pico-api-port.json`). Qualcomm-часть перенесена (0046–0057), QTI Wi-Fi vendor путь (0059–0066). Bluetooth — заводской стек (0067–0069). IAudioService совпадает (0073), 19 таблиц со сдвигом кодов (0075–0087) и 17 с добавлениями в конец (0097–0105) совпадают. Сигнатуры 6 таблиц и 18 интерфейсов только factory с потребителями перенесены (0106–0109). Осталось: 19 заводских интерфейсов без Source (`validation/aidl-table-parity.json`): 5 без потребителей (IClipboardSmtEx, IPowerManagerSmtEx/MonitorEx, ISmsSecurityAgent/Service) и HIDL IServicetracker (HAL на vendor нет) — не переносятся; 13 из других boot JAR — решение boot classpath (ниже), Smartisan-состояние за перенесёнными SmtEx-серверами (писатели prefetch/freeze/last-word/top-stack полей, реализации мостов sys-/sysmonitor- JAR, ActivityManagerSmtBase/StrictMode/PeroptWhiteListParser/WindowSessionSmtBase/LightsService вызывающие), PICO ExtAudioServiceImpl (вызывающий IPlayer.setExtVolume), ActivityManagerSmtBase (prefetch, getSmtEx для FreezeManager.init PicoSyshub/XRRuntime), DeviceIdleControllerSmtEx, SmtPCUtilsSmtBase, PowerAdvisorInternal, телеметрия NetworkStatusCollect (не переносится), vold wrapped keys (ICE) для заводского fstab, PICO-логика wifi-service без донора (NetworkStatusCollect, NetworkPxrAdapter, SWIFT, 9-значный signal poll wificond), security-патчи после r47, SmtBase/FreezeManager и др., 647 preserved-кандидатов sys-/sysmonitor- JAR, серверные реализации PICO служб |
| Boot classpath: заводские JAR вне framework.jar | интеграция/проверка | Решено статически и в изолированном runtime (0110–0115): порядок class path как на заводе, telephony-ext/qcom.fmradio из CodeLinaro, остальные boot JAR — заводские DEX, проверка `tools/check-factory-component.py` проходит; заводской product Settings.apk больше не падает на IExtTelephony$Stub (класс на BOOTCLASSPATH). Осталось: sys-services и sysmonitor-services не на SYSTEMSERVERCLASSPATH — 531 и 129 неразрешённых ссылок на серверный Smartisan-слой (ProcessRecordSmtBase, ActivityManagerServiceSmtBase, WindowProcessControllerSmtBase, ISysSvsFactory 57 методов, IApplicationFreezer и др.) и ~724 заводских вызывающих метода services; Debug.dumpHprofDataCrop/dumpSysMonitorInfo (Smartisan VMDebug libcore/ART); FrozenObjectException из JNI Binder; libmeminfo GFX_cached/MemAvailable; ExtendedRemoteDisplayHelper (потребитель WfdCommon в CodeLinaro services); заводские telephony-common/ConnectivityExt-потребители IExtTelephony; JNI/HAL FM не собираются (нет FM-приёмника); загрузка на общем образе |
| Hidden API policy, permissions и доступ PICO приложений | проверка/интеграция | Флаги PICO API и permissions совпадают с factory (greylist-packages + whitelist через патч soong). Осталось: запуск приложений при нормальной политике на общем образе, переводы строк permissions |

Полный сохранённый перечень декларативных различий —
[API-GAPS.json](API-GAPS.json), читаемый native appendix —
[API-NATIVE-GAPS.md](API-NATIVE-GAPS.md). На этой точке: 76 native declarations
в framework.jar, 6 в services.jar; 773 и 834 factory-only class declarations
соответственно. Есть также изменения деклараций 549 и 414 общих классов.
Эти числа включают другие OEM изменения, compiler-generated members и
возможные перемещения между JAR. Для каждого кандидата ещё надо определить:
перенести, сохранить нужный заводской компонент либо доказать отсутствие
требуемых потребителей. Создавать пустые заглушки вместо нужного поведения
недостаточно.

### Скан потребителей API

`tools/scan-api-consumers.py` (WSL, `taskset -c 0-7`) разбирает DEX всех
заводских APK/JAR 5.13.7 (system, product, vendor, odm: 293 контейнера,
248 с DEX) и 3 951 ELF. Ссылки разрешаются через эффективный заводской
BOOTCLASSPATH/SYSTEMSERVERCLASSPATH, включая унаследованные члены и overrides;
app-загрузчики видят только boot-кандидатов. Кандидаты сверяются с Source
classpath (`init.environ.rc` сборки): перемещённые классы и члены,
найденные через Source superclass, получают `present_in_source`.
Внутри пары framework/services нужда распространяется от нужных кандидатов,
включая реализацию, которую конструктор сохраняет в нужное поле
(`ExtImplFactory.getImpl(IExtX)` → `ExtXImpl`). JAR/ELF, которые Source
собирает по тому же пути (wifi-service, telephony-common, libandroid_runtime),
не создают нужды и перечисляются отдельно.

| Решение | framework.jar | services.jar | Всего |
|---|---|---|---|
| needed — APK, JAR вне classpath или ELF | 370 | 6 | 376 |
| needed_by_preserved_factory_component — только sys-/sysmonitor-/vrex-/devicemiddleware JAR | 179 | 468 | 647 |
| not_needed — нет статических потребителей | 2 695 | 2 726 | 5 421 |
| present_in_source | 12 | 16 | 28 |

Нужные группы: `com.pxr.net` (43, PxrNetworkService и StreamingAssistant),
`com.pvr` AIDL IPvrManagerService/IPvrCallback/ISysDataSyncService (16),
`com.pico.api` (13), `com.pvr.configuration`, `com.pxr.pxrapi`,
`com.pxr.bluetooth`; `android.app` (101: SmtBase/FreezeManager/observers),
`android.bluetooth` (52), `android.net`/wifi (39), `ActivityInfo.getExt`/
`ApplicationInfo.getExt` с Ext-реализациями (SystemExt), services
`IPxrNotificationService` по Binder descriptor. Из 82 native declarations:
9 needed (`MediaMetadataRetriever._getVRType`, семь `PlayerSpatialHelperImpl`,
`Binder.getLastFrozenPid`) — перенесены (0116–0124), 15 только для сохраняемых sys-/sysmonitor- JAR,
58 без потребителей. Импорты ELF: заводская `libpxrguiex.so` (ARM64 и ARM32)
требовала из libhwui `SurfaceTexture::{setTexName,createFence,acquireTexture,
releaseTexture}` и `ImageManagerExt` — 16 символов; теперь они есть (0123, `validation/native-parity.json`).

`not_needed` не отменяет поведенческие хуки: `ExtViewRootImplImpl`,
`ExtActivityThreadImpl` и `ExtPackageParserImpl` не имеют внешних потребителей,
но входят в заводскую VR skip-draw политику. Скан статический: имена,
собранные во время выполнения, inlined константы, ресурсы, permission-строки
манифестов, APEX payload и код, загружаемый позже, не отслеживаются.

## 2. Нативная графика и Binder

| Работа | Статус | Что должно подтвердить завершение |
|---|---|---|
| Граф зависимостей ARM32 | аудит | Полный граф реальных потребителей; сейчас inspected ELF count = 0 |
| Полный private C++ ABI: поля, inheritance, virtual slots, lifetimes | аудит/проверка | Проверка всех требуемых границ factory/Source, а не только экспортов и размеров vtable |
| SurfaceMonitor: неизвестная область из 40 bytes | аудит | Установить её назначение/потребителей или доказать, что она не нужна на используемых границах |
| MonitoredProducer: factory connect/disconnect state и потребители dequeue telemetry | перенос/аудит | Восстановленные пути и их использование в Source SurfaceFlinger |
| Freeze remote registration и доставка callbacks | проверка | Перенесено в заводском виде (0116): регистрация в сервисе и linkToDeath, реестры пусты, callbacks не доставляются — 9 контрольных точек совпали с factory на обоих ABI. Осталось: реальные freeze/unfreeze события службы «freeze» (sys-services) |
| Реальные remote Binder caller-ID запросы/OEM ioctl | проверка | Работа между настоящими процессами на factory kernel, без перехвата ioctl |
| HWC/RenderEngine/SurfaceFlinger общий frame path | проверка/интеграция | Настоящие GPU buffers, acquire/release fences, single/multi-layer, ошибки и lifecycle |
| EGL image lifecycle | проверка | Настоящие create/destroy и dump при работе GLES/GPU |
| SurfaceMonitor display-frequency requests и callbacks | проверка/интеграция | Реальная смена поддерживаемых частот и правильный обратный callback |
| Совместимость libui/libhwui/libbinder и других Source/factory библиотек | аудит/интеграция | libbinder/libbinder_call_stat/libhwui/libmedia_jni/libspatialaudio/libandroid_runtime сверены (`tools/check-native-parity.py`): остаток объяснён, у 262 сохранённых заводских потребителей нет неразрешённых символов из этих библиотек. Найдено вне этой части: заводские libavenhancements/libstagefright_wfd (QTI AV extensions/WFD) не разрешаются Source libstagefright/libmedia/libmediaplayerservice/libaudioclient/libstagefright_foundation; libpvrtrackingcamera — `AImageReader_setRtMode` (libmediandk); libbpfserver/nettools — `bpf::loadProgWithUnlink`; libui и остальные медиа-библиотеки не сверены |

## 3. Общая AOSP система

- **Интеграция:** собрать framework JAR/resources, system_server/services,
  JNI, ART/APEX/Bionic, HWUI/SurfaceFlinger/GUI/Binder в согласованную систему.
- **Интеграция:** получить и упаковать нужные закрытые PICO VR/OpenXR службы,
  библиотеки и приложения из проверенной заводской прошивки; исходные
  сертификаты и связанные permissions/shared UID должны оставаться согласованы.
- **Аудит/интеграция:** init services, UID/GID, SELinux, capabilities,
  namespaces/VNDK, cgroups, properties, feature XML, permissions и resources.
- **Проверка:** запуск zygote/system_server, package manager, settings,
  display/input/audio/camera служб и регистрации PICO служб без аварийных циклов.
- **Проверка:** ART на общем образе: загрузка compiled images, реальное
  исполнение AOT entrypoints, JIT code generation, dexopt и приложения обоих ABI.
- **Интеграция:** исключить тестовые probes, fake services и fixture настройки
  из устанавливаемого system image.
- **Проверка:** AVB цепочка, logical partitions/LP geometry, filesystem metadata,
  rollback metadata и подписанный установочный комплект для реального устройства.

Ядро, DTB/DTBO и vendor/product/odm сначала остаются заводскими. Переписывание
их в открытые исходники не требуется для первого AOSP 10 прототипа с VR.
Точное соответствие опубликованного phoenix-kernel установленной Pro SEKO
прошивке ещё не подтверждено; это отдельный аудит перед заменой kernel.

## 4. Проверка на шлеме и данные

- **Проверка:** загрузка именно общей Source группы, не только временного
  процесса и ранее установленного гибридного preview.
- **Проверка:** существующий userdata открывается после перехода; настройки,
  приложения и recordings доступны, Keymaster/encryption/Root of Trust совместимы.
- **Подготовка/проверка:** актуальные backup нужных данных и разделов, recovery
  и рабочий откат с новым комплектом. Старые backup не заменяют проверку отката.
- **Проверка:** Magisk/root и ADB сохраняются согласно выбранному варианту.
- **Проверка:** cold boot, повторная загрузка, восстановление после неудачной
  загрузки и отсутствие boot loop. Wipe/relock/slot changes не входят в текущий план.

## 5. Полная аппаратная VR проверка

Каждый пункт должен проверяться на общем AOSP образе с нужными PICO blobs.
Проверка preview или локальных mocks не завершает эти пункты.

- Стереоизображение, размеры/ориентация, искажения, корректный compositor.
- 6DoF головы, оба контроллера: pose, кнопки, вибрация, reconnect.
- Игры и OpenXR runtime: запуск, pause/resume, tracking и frame submission.
- Android 2D окна/панели в VR: открытие, фокус, клавиатура, permissions.
- Граница/guardian и recenter.
- Passthrough и MR камеры.
- Eye/face tracking и их калибровки.
- IPD и настройки дисплея; brightness и поддерживаемые refresh modes.
- Speakers, microphones, spatial audio и orientation/pose updates.
- Сон, пробуждение, proximity и переключение приложений.
- Wi-Fi/Bluetooth/USB и восстановление подключения устройств.
- Запись экрана и воспроизведение сохранённых записей.
- Длительный игровой прогон: frame time, latency, dropped frames,
  thermals/throttling, battery drain и memory leaks.

## 6. Воспроизводимость, Git и обновления

- **Доработка:** убрать зависимость финального image builder от локальных
  reports, извлечённого вручную system tree и device-specific saved Magisk boot.
- **Доработка:** конфигурируемые пути/WSL mount/toolchain и подготовка host deps.
- **Проверка:** новый checkout → pinned AOSP → наши patches → проверенный
  factory download/extraction → coherent image, без приватного старого окружения.
- **Проверка:** повторная сборка с теми же входами; версии, hashes и provenance.
- **Публикация:** подключить/создать авторизованный BearIvan/Picomisu remote
  и отправить наши изменения. Сейчас сохранены локальные коммиты.
- **Подготовка:** installer/recovery/OTA подходящего для PICO формата,
  применение обновлений, проверка версии/подписи, сохранение данных и откат.
- **Подготовка релиза:** имя/версия Picomisu, release notes, инструкции
  установки/восстановления, полный набор результатов и hashes.
- **Аудит безопасности:** определить реальное покрытие security patches;
  старые factory SPL metadata не доказывают актуальное покрытие.

Собственные production signing keys и смена build type с userdebug на user
могут стать отдельным последующим решением. Пользователь сейчас выбрал
сохранить существующие ключи; их замена не блокирует текущий прототип.

## Отложенное: собственный QTI Bluetooth-стек

Текущее решение пользователя — заводской Bluetooth (Bluetooth.apk и libbluetooth_qti
из 5.13.7). Позже попытаться восстановить QTI-стек: сначала найти открытого донора в
CodeLinaro (vendor/qcom-opensource/bluetooth, system/bt-ext семейства LA.UM.8.12), иначе
восстановить из заводского ELF. Критерий: socket opts, clock sync и нумерация кодеков
Qualcomm совпадают с factory, контроллеры PICO работают без заводской библиотеки.
Сейчас не выполняется. Клон bluetooth_ext из CodeLinaro уже есть в
analysis/framework-reference/caf-bluetooth-ext.git.

## Запланировано: трекинг глаз и лица как часть системы

Решение пользователя: встроить демоны трекинга в Source образ без Magisk, режим выбирается
в Settings (раздел LAB рядом с Eye/Face Tracking): «Выкл», «VRCFT (UDP 9030)» или
«Baballonia (MJPEG 4442)». Режимы взаимоисключающие (так требуют гайды pico4.wiki).

- VRCFT: picofacialdatadaemon из исходников github.com/thoricelli/PicoFacialDataDaemon
  (MIT, клон в analysis/eye-face-daemons, коммит ab30918), сборка Android.bp с системными
  libbinder/libutils вместо приложенных prebuilt; init-служба со своим SELinux-доменом
  (binder к pxreyetrackingservice, UDP/multicast).
- Baballonia: eyed + eyestream (toonlink) есть только бинарниками без лицензии
  (pico4.wiki/downloads). Пользователь спрашивает автора об исходниках/разрешении;
  иначе — своя открытая совместимая реализация (/data/local/tmp/eyed.sock, /left,
  /right, /mouth на 4442).
- Заводской pxreyetrackingservice падает после сна и на официальной прошивке (init его
  перезапускает); службы режимов перезапускаются вслед за ним, в picofacialdatadaemon —
  binder death recipient (предложить апстриму).
- Magisk-модули пользователя на текущей прошивке не трогаются.

## Ближайший порядок

1. Display/window policy для VR окон (серверная сторона 2D virtual display).
2. Требуемые service API по результату скана потребителей (`validation/api-consumers.json`); медиа-экспорты
   QTI AV extensions/WFD, libmediandk и libbpf_android для сохраняемых заводских библиотек (`validation/native-parity.json`).
3. Перенос wrapped keys в vold/fs_mgr (блокер userdata, раздел 0).
4. Согласованный Source image, dependency/ABI/config проверка.
5. Загрузка с готовым откатом и сохранением данных, полный VR тест.
6. Чистая воспроизводимая сборка, Git remote и обновления.

Основные доказательства текущей точки: `validation/native-runtime-current.json`,
`validation/framework-boot-image.json`, `validation/libgui-abi.json`,
`validation/vr-canvas-api.json`, `validation/vr-skip-draw-policy-plan.json`,
`validation/vr-policy-port.json`, `validation/vrchain-port.json`, `validation/pico-api-port.json`, `validation/api-consumers.json`,
`validation/patch-series.json`, `validation/sepolicy-parity.json`, `validation/factory-bootclasspath.json`, `validation/smartisan-layer-port.json`,
`validation/native-parity.json`, `validation/native-parity-port.json`. Файл — снимок для планирования; после новых
переносов/проверок статусы и API appendix нужно обновлять.
