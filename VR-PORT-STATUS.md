# Picomisu: состояние переноса VR


## Текущая точка: пробный образ Source system source-trial-01 (0125–0126)

Собран offline первый образ для загрузочной пробы: Source system (framework, services, ART и остальные APEX,
SELinux, vold, native, boot image 21 JAR) + заводские компоненты, которых Source не даёт. Шлем не изменялся;
на нём сейчас preview 01 (system ae6b3cb8…, boot Magisk 475ec054…, recovery заводской). Подробно —
[source-trial-01-plan.md](source-trial-01-plan.md).

- **Состав** (`device/pico/PICOA8110/source-trial-01.json`, `tools/assemble-source-image.py`): 3022 записи Source,
  2654 заводских байт-в-байт (VR-службы и их rc, 637 ELF PICO/QTI (69 исполняемых), модели и конфиги VR, шрифты, media, keylayout,
  13 JAR вне class path), 77 заводских APK с сертификатом PICO platform/media/shared переподписаны ключом Source
  той же роли, 3 теневых android.uid.system из product (Settings, QdcmFF, PowerOffAlarm), 7 сгенерированных файлов
  (build.prop с 96 заводскими свойствами и пробной идентичностью, init.rc с правками PICO, ld.config с soundfx/vklayer/
  libstationclient, public.libraries, mac_permissions, framework manifest + sigma_miracast/atcmdfwd). Пакеты: общие
  AOSP — Source, Bluetooth и PackageInstaller — заводские, 16 пакетов, которых нет на заводе, не ставятся.
- **Найдено и исправлено для загрузки:** заводской vendor/build.prop задаёт ro.apex.updatable=true (перекрывает
  system) — Source собран с updatable_apex.mk (APEX-файлы); libpvrtrackingcamera (pvrtrackingservice,
  pxrseethroughservice, камеры глаз) требовала `AImageReader_setRtMode` — перенесено из заводского машинного кода
  с `ALooper::getThreadId` (0125, SCHED_FIFO 26 для потока колбэков), эталон VNDK ABI (0126).
- **Подписи:** platform-ключа PICO нет; по коду PMS r47 framework-res фиксирует сертификат android.uid.system,
  остальные участники с другим сертификатом не ставятся, не отсканированный системный пакет теряет данные.
  Поэтому переподпись + теневые копии; симуляция сканирования: 0 отказов, 186 пакетов = заводским.
  Рекомендация: первая проба с очисткой userdata/metadata (SettingsProvider 182 против 183 на заводских данных).
- **Проверки** (`tools/check-source-image.py`, `validation/source-trial-01.json`): readback 5766/0, e2fsck, AVB-цепочка,
  метки SELinux (1 объяснённое отличие), host_init_verifier 94 rc, переходы доменов служб, class path, 97 APK/JAR
  (1 ссылка BrowserChrome), 2226 ELF (разрывы только QTI AV/WFD/extractor, bpf, meminfo), checkvintf — совместимо,
  заводских oat нет. Образ: system c91884b35f1264f289b28436095609c6d5d91e84c9e16884860730cf0cf50e7b,
  vbmeta 0782a10f…, vbmeta_system db553e3f….
- **Установка** тем же методом, что preview 01 (OEM-авторизация fastboot, RAM-загрузка офлайн-recovery, dmctl,
  adb-sync, readback), новый `tools/source-trial-install.py` с авторизациями в state.json; очистка через BCB
  `--wipe_data` и заводской recovery; при неудаче — логи из pstore/офлайн-recovery и сразу следующая сборка.


## Текущая проверенная точка: native-паритет libbinder, libhwui и 9 JNI (0116–0124)

Этап 3, часть 6. Заводские экспорты native-библиотек, которые видят заводские потребители, и
связанное с ними поведение восстановлены из машинного кода factory 5.13.7 (llvm-objdump из
prebuilts clang, MiniDebugInfo `.gnu_debugdata`). Сверка экспортов, классификация остатка и
разрешение символов заводских потребителей — `tools/check-native-parity.py` →
`validation/native-parity.json` (пояснения — `config/native-parity-explanations.json`), итог и
доказательства ABI — `validation/native-parity-port.json`.

- **libbinder (0116, frameworks/native).** Было 137 заводских экспортов без пары в Source
  (ARM64 system и vndk-29; ARM32 — 136). Осталось 7/6 вне-строчных `Parcel::readAligned<T>` (у Source
  то же тело встроено) и 2 шаблона libc++ только в Source. Потребители: заводской
  `/system/bin/pxrmediametrics` (SceneInfoManager/SceneData) и заводская libandroid_runtime
  (ProcessState/IPCThreadState, её заменяет Source). Перенесено:
  - `SceneInfoManager`, `ISceneInfoManager`/`BpSceneInfoManager` (android.app.ISceneInfoManager, код 1),
    `SceneData` (как MetaDataBase, ключи String16 и таблица строк; повтор строкового ключа не
    перезаписывает значение, как на заводе), `scenemtx`/`mSceneMutex`, checkService «sceneinfo_service»;
  - `FreezeManager` в заводском виде: объект 144/56 байт, записи KeyPair/CallBackData/
    RemoteDeathNotifier, глобальные `Mutex* mMutex` и `std::mutex mtx`, getService через checkService
    («Waiting too long for freeze service, giving up»), `containsKey`, `Callback::unFreezeCallback`,
    удалённая регистрация по `getLastFrozenPid`. Заводские ошибки воспроизведены: удалённая
    регистрация пишет в копию реестра (удалённые реестры пусты, callbacks не доставляются —
    как в `validation/freeze-remote-research.json`), записи не освобождаются, callbacks выполняются
    под блокировкой реестра. Отступления прежнего переноса (рекурсивная блокировка, shared_ptr,
    освобождение записи) убраны; gtest freeze registry проверяет заводское поведение;
  - `ProcessState`: буфер транзакций по умолчанию 2 МиБ − 2 страницы (в AOSP — 1 МиБ),
    `selfForSystemServer` (4 МиБ), `selfForRuntime`, конструктор с размером; деструктор, как на заводе,
    снимает 2 МиБ;
  - `IPCThreadState::setPidFreeze/getTargetCalleePid/getBinderServerPids/getBinderClientPids`
    (ioctl PICO 'b' 34/30/14/15, `binder_remote_pids` 48 байт);
  - `BpBinder::transact` всегда просит TF_REPORT_FROZEN (0x80): замороженный адресат даёт DEAD_OBJECT
    без смерти прокси или UNKNOWN_ERROR+9, если флаг задал вызывающий; `flatten_binder` ставит
    FLAT_BINDER_FLAG_TXN_SECURITY_CTX локальным `android.gui.IProducerListener`; исправление
    безопасности `readString16Inplace` (b/172655291), которое есть в заводской библиотеке;
  - `BBinder::setObserver/transact/dump` и новая VNDK-SP **libbinder_call_stat** (нативный
    BinderCallsStats: `dumpsys <svc> --enable|--disable|--sample-interval N`). Экспорты равны
    заводским на lib64, lib, vndk-sp-29 ×2, NEEDED как у factory. Воспроизведены заводские
    ошибки: 32-битный процесс падает (ubsan mul-overflow) на первом замеренном вызове, дамп
    очищает данные. Лишний импорт `__write_chk` (FORTIFY Source).
  Размеры объектов на обоих ABI совпали с `operator new` заводского кода.
- **VNDK (0117–0119):** эталоны ABI libbinder и libbinder_call_stat пересобраны (29/64 arm64 и arm),
  header-abi-diff — COMPATIBLE; libbinder_call_stat добавлена в список VNDK-SP (как в заводском
  vndksp.libraries.29.txt); заголовок OMX `OMX_IndexConfigSyncVRTypeDetect` (0117) — только
  новый перечислитель.
- **libhwui (0123):** определены 16 импортов заводской `libpxrguiex.so` (8 на ABI:
  `SurfaceTexture::setTexName/createFence/acquireTexture/releaseTexture`, `ImageManagerExt` ctor и
  `initThread`, `Singleton<ImageManagerExt>::sLock/sInstance`). Восстановлены ImageManagerExt (поток
  кэширования EGLImage, очередь, Barrier, слушатели, `persist.pvr.debug.image_manager`), EGLConsumer
  как ImageManagerListener (VR-режим, отложенный буфер, кэш 5 буферов), SurfaceTexture
  `setFromVrCompositor` (транзакция 10000, 3 буфера). Раскладка и vtable как у factory: sizeof
  ImageManagerExt 296/76, поля 1672/1680 и 4872/4873 (ARM32 1068/1072 и 2776/2777). Все
  UND-символы libpxrguiex разрешаются Source-библиотеками на обоих ABI.
- **9 native-методов (0120–0122):** `MediaMetadataRetriever._getVRType` — JNI → libmedia
  (IMediaMetadataRetriever код 11) → MetadataRetrieverClient → StagefrightMetadataRetriever →
  FrameDecoder/ACodec (`OMX_IndexConfigSyncVRTypeDetect`, флаги выходных буферов); семь natives
  `PlayerSpatialHelperImpl` — JNI → новая `libspatialaudio` (экспорты и NEEDED как у factory) →
  клиент ISpatializer/INativeSpatializerCallback в libaudioclient (коды IAudioPolicyService 73–76);
  Java PlayerSpatialHelper/PlayerBase, hidden-API как у factory. `Binder.getLastFrozenPid` уже был.
  Таблицы JNI libmedia_jni совпадают с factory по именам, сигнатурам и порядку на обоих ABI.
  Серверный Spatializer audioserver не переносился: Source audioserver отвечает UNKNOWN_TRANSACTION,
  клиенты ведут себя как factory без spatializer.
- **ZygoteInit (0124):** заводские natives `systemServerMmap`/`runtimeMmap` (system_server — 4 МиБ,
  `com.pico.xr.openxr_runtime` — selfForRuntime) и их вызовы в ZygoteInit/ZygoteConnection.
- **Проверка на шлеме** (adb 192.168.1.230:5555, временные файлы в /data/local/tmp, удалены, отпечаток
  не изменился):
  - `outputs/framework-boot-image-test-28`: **30 fixtures** на ARM64 и ARM32; wire —
    factory-classpath 218/218, factory-only 332/332, appended 1790/1790, shifted 1207/1207,
    PICO 313/313, Qualcomm 1190/1190, audio 346/346 на обоих ABI; VR policy 76/78 + 2 ожидаемых;
    inspect-vr-canvas и record-framework-runtime пройдены.
  - `outputs/bufferqueue-test-34`: все gtests группы (bufferqueue 54, freeze registry 4, RenderSurface 39,
    layer/display fence 21, pico_composition 14, composition_regression 55, monitored_producer 5 на ABI)
    и прежние factory fixtures. Новые: **26 factory/Source fixtures libbinder** (размер буфера
    ProcessState, SceneData/Parcel, BpSceneInfoManager и SceneInfoManager с поддельным
    servicemanager, flatten IProducerListener, readString16Inplace, TF_REPORT_FROZEN, ioctl
    freeze/pids) совпали на обоих ABI; удалённая регистрация FreezeManager Source совпала с factory
    во всех 9 контрольных точках (+9 размеров корней ARM64); заводская libpxrguiex связывается с
    Source libhwui/libgui/libandroid_runtime (`hwui_pxrguiex_test --link-only`, ARM64 и ARM32). GL-часть
    теста изолированно не запускается: загрузчик EGL открывает обёртки /system по абсолютному пути.
- Полная сборка droid проходит (`validation/full-build.json`, header-abi-diff VNDK), verify-patch-series:
  124 патча, 29 компонентов.
- **Осталось** (REMAINING-WORK): серверный Spatializer audioserver; сдвиг vtable
  IAudioPolicyService после setSurroundFormatEnabled (заводские setParameters и `bool*` в
  getOutputForAttr, коды транзакций совпадают); SpatialCoordConverter Java/JNI и
  `MediaCodec::updateVrTypeCalculator` (метрики libpxrmediametrics); прочие заводские экспорты
  медиа-библиотек (QTI AV extensions/WFD: libavenhancements и libstagefright_wfd не разрешаются
  Source libstagefright/libmedia/libstagefright_foundation), `AImageReader_setRtMode` (libmediandk,
  потребитель libpvrtrackingcamera), `bpf::loadProgWithUnlink` (libbpf_android); JNI
  ExtSurfaceImpl 2D-VR, freeze-group Process и Binder pids без потребителей.

## Предыдущая точка: состав boot classpath и Smartisan-слой (0110–0115)

Этап 3, часть 5. Source-образ получил заводские BOOTCLASSPATH, DEX2OATBOOTCLASSPATH и
SYSTEMSERVERCLASSPATH (порядок как в factory `init.environ.rc`). Решение по каждому JAR —
`device/pico/PICOA8110/factory-bootclasspath.json`, проверка — `tools/check-factory-component.py`
(обобщение check-factory-bluetooth, конфиг JSON) → `validation/factory-bootclasspath.json`.

- **QTI открытые, собраны из CodeLinaro LA.UM.8.12.c3-64900 (новые компоненты):**
  - telephony-ext — `vendor/codeaurora/telephony` (27d00010, без изменений): 36/36 классов и все
    481 hidden-API флаг совпадают с factory. Заводской product Settings.apk
    (`SettingsActivity.switchToFragment` → `IExtTelephony$Stub.asInterface`) больше не получает
    NoClassDefFoundError; сервера «extphone» нет и на заводе.
  - qcom.fmradio — `vendor/qcom/opensource/fm-commonsys` (0d397db4): 27/27 классов и флаги как у factory.
    0115 собирает FM HAL-клиенты (fm_hci, helium) только с BOARD_HAVE_QCOM_FM; FM-приёмника и
    потребителей нет, JNI/HAL не собираются.
- **QTI закрытые — заводские DEX:** tcmiface (нет в CodeLinaro), QPerformance, UxPerformance
  (BoostFramework грузит их рефлексией), WfdCommon (CodeLinaro wfd-commonsys содержит только libaac).
- **PICO/Smartisan — заводские DEX:** sysmonitor-framework, sys-framework, devicemiddlewareimpl,
  vrex-framework (boot), vrex-services (system server). `dex_import`-модули
  `device/pico/PICOA8110/factory-framework`; DEX (SHA-256 проверяется) и три XML-списка
  PeroptWhiteListParser извлекает из заводского system.img `tools/install-device-tree.py`, в Git их нет.
  Заводские oat/vdex не используются: 21 JAR компилируется в Source boot image, hidden-API флаги
  заводского DEX сохраняются.
- **Не на classpath:** sys-services и sysmonitor-services. Они линкуются к серверному Smartisan-слою
  services.jar и вызываются из ~724 заводских методов services, которых в Source нет: 531 и 129
  неразрешённых ссылок после этой части (было 612 и 156). Загруженные частично, они работали бы без
  парных хуков (например, freezer без unfreeze). Source SysOptBridge/SysMonitorSvcBridge ведут себя
  как factory при отсутствии их классов.
- **build/make (0110):** PRODUCT_BOOT_JARS_BEFORE_FRAMEWORK и PRODUCT_SYSTEM_SERVER_JARS_BEFORE_SERVICES,
  пакеты новых boot JAR и smartisanos.os/tnt в whitelist check_boot_jars.
- **Smartisan-слой framework/services (0113), восстановлен из заводского DEX** (донора нет:
  smartisan-base.git — Android 6 без этих классов):
  - ActivityManagerSmtBase (prefetch, обёртки IActivityManagerSmtEx для FreezeManager.init PicoSyshub/XRRuntime,
    SystemExt, OsTeaTracker), ActivityManagerMonitorEx, ActivityManager.getSmtEx/getMonitorEx, SysClient,
    SysMonitorFwBridge/ISysMonitorFwFactory, полный ISysFwFactory, хуки SysMonitor в ActivityThread,
    LoadedApk, BroadcastReceiver, InputEventReceiver, ViewRootImpl, BootReceiver.
  - ActivityThreadSmtBase: сообщения 1011/3000, делегирование из ActivityThread.H, prefetch при bind,
    транзакции ApplicationThreadEx 1021–1032.
  - Battery OptEx/SmtEx, MemInfoReaderSmtEx (getMemInfoFast), BoostFrameworkSmtBase (mSmtEx),
    SmtPCUtilsSmtBase, PowerAdvisorInternal (заводской advisor по умолчанию в SystemServer),
    WindowSessionSmtBase, SysDataSyncServiceManager, IApitest1/2 и smartisanos.tnt, LightsService
    (PXR HMD brightness JNI, Light.getBrightnessSmt/setBrightnessAnimSmt).
  - PeroptWhiteListParser (~5000 инструкций) с ActivityInfoSmtBase (parcel ActivityInfo как у factory),
    PackageParserSmtBase, PMS SmartisanOSInit и флаги, пропуск single-layer composition в
    WindowStateAnimator и VirtualDisplayAdapter.
  - ProcessListSmtBase, DeviceIdleControllerSmtEx, мосты SysOptBridge.getMultiPlatFactory и SysOptJobBridge.
  - Natives как на заводе: Debug.getTimeByQtimer (CNTVCT/CNTFRQ, lib64 и lib), getMemInfoFast,
    ActivityThread.nSetSwitchState (новая восстановленная libswitchstate), initPrefetch/onPrefetchRealStart
    (Smartisan SoundSettings в libbinder, 0111; эталон VNDK ABI 0112).
  Сверка новых классов с factory (`validation/smartisan-layer-port.json`): framework 47/52, services 18/20.
  Отличия объяснены: подмножества ConnectivityManagerSmtEx/ProcessSmtEx/ReflectUtil/ISysPerfMonitorService/
  ProcessRecordMonitorEx и размещение констант D8 в 5 XML-парсерах PeroptWhiteListParser.
- **Проверка сохранённых JAR:**
  - Все 11: 0 неразрешённых ссылок, совпадают вид (static/instance, class/interface) и доступ.
    Абстрактные методы реализованы, final не переопределяются, пакеты в whitelist, boot-image файлы есть,
    DEX совпадает с factory. Для этого BatteryStatsImpl$Uid.addProcState*TimesMs стали public, как на заводе.
  - Приняты 3 ссылки sys-framework — Debug.dumpHprofDataCrop/dumpSysMonitorInfo: Smartisan VMDebug
    libcore/ART. Их вызывают только запросы sys-services.
  - AIDL-таблицы, которые используют JAR, совпадают.
- **Runtime на шлеме** (adb 192.168.1.230:5555, временные файлы в /data/local/tmp от shell UID, удалены):
  - Пакет `outputs/framework-boot-image-test-27`: 23 boot JAR, 42 compiled boot-image файла на ABI,
    **30 fixtures** на ARM64 и ARM32.
  - Новый FactoryClassPathFixture: каждый класс 10 сохранённых boot JAR загружен boot class loader'ом без
    инициализации; статус класса из boot image и члены совпали с factory — **218/218** на обоих ABI
    (`validation/factory-classpath-wire.json`).
  - Wire-наборы против заводского framework не изменились: factory-only 332/332, appended 1790/1790,
    shifted 1207/1207, PICO 313/313, Qualcomm 1190/1190, audio 346/346; VR policy 76/78 + 2 ожидаемых;
    inspect-vr-canvas и record-framework-runtime пройдены.
  - libbinder изменилась, поэтому native-группа перезапущена: `outputs/bufferqueue-test-33`, 378 native
    gtests и factory fixtures на обоих ABI.
- Полная сборка droid проходит (boot image, hiddenapi, check_boot_jars, VNDK ABI; `validation/full-build.json`).
  verify-patch-series: 115 патчей, 29 компонентов.
- **Осталось** (REMAINING-WORK):
  - серверный Smartisan-слой для sys-/sysmonitor-services;
  - FrozenObjectException в JNI Binder;
  - handleSpecialIntentSmt (IntentSmtBase);
  - теги libmeminfo GFX_cached/MemAvailable;
  - CodeLinaro ExtendedRemoteDisplayHelper (WFD);
  - PICO-расширение WindowState для applyGravityAndUpdateFrame и CodeLinaro perf boost для
    ActivityDisplay/appDiedLocked.

## Предыдущая точка: сигнатуры 6 AIDL-таблиц и интерфейсы только factory (0106–0109)

Этап 3, часть 4. `tools/compare-aidl-tables.py --signatures` теперь сравнивает не только имена и коды,
но и полную сигнатуру, направления in/out/inout и oneway каждой транзакции общих AIDL Proxy.
До части: 732 из 738 таблиц; после — **756 из 756** (18 новых таблиц тоже сверены). Таблицы по
именам/кодам: **838 из 857** идентичны (было 820), только на заводе — 19 (было 37).

- **Сигнатуры, изменённые на заводе «на месте»:**
  - CodeLinaro LA.UM.8.12.c3-64900: IVibratorService.vibrate с AudioAttributes (обход DND для
    привилегированных, USAGE_NOTIFICATION_EVENT); ISystemGestureExclusionListener с unrestricted-областью
    (журналирование ограничений exclusion, атомы 223/224, EdgeBackGestureHandler, PointerLocationView);
    INetworkStatsService.forceUpdateIfaces без VpnInfo (учёт VPN в NetworkStatsFactory, несколько
    underlying-интерфейсов); IBluetoothPan.setBluetoothTethering(value, pkgName) — system/bt (0108),
    BluetoothPan, PanService (0109), сервер образа — заводской Bluetooth.apk с той же сигнатурой;
    IStatsManager.sendWatchdogRollbackOccurredAtom с причиной отката (PackageWatchdog, AppErrors,
    RollbackPackageHealthObserver, statsd, biometric latency, публичный StatsLog.write(int, Object...)).
  - PICO из DEX: IBackupAgent.doFullBackup с include/exclude путями (ExtBackupAgentImpl, BackupAgent DEBUG,
    FullBackupEngine). Заводские ошибки воспроизведены (пути одного домена перезаписывают друг друга).
- **Интерфейсы только factory в framework.jar с потребителями (18, 0106):** IFreezeManager/IUnFreezeCallback
  с FreezeManager и Binder.getLastFrozenPid (PicoSyshub, XRRuntime; сервер «freeze» в sys-services, тот же
  протокол, что у native FreezeManager libbinder), ISceneInfoManager/IDataListener с SceneInfoManager,
  DataListener, SceneData (PicoSyshub), IPrefetchManager/Observer/Callback с PrefetchInfo, IPowerAdvisor
  (XRRuntime, PicoSyshub, OsTeaTracker, store2d), ITransferServer с AppMainMsgInfo (PicoFeedback, XRShell),
  ISysTransServer, три IKeyguard*VerifyCallback (PicoKeyguard), IPackageManagerMonitorEx
  (PackageManagerServiceMonitorEx наследует Stub), IDeviceIdleControllerSmtEx, IVirtualInputService
  (явные id), ISmtPCManager — восстановлены из заводского DEX; ICarStatsService и statsd CarStatsPuller —
  CodeLinaro (заводской statsd содержит CarStatsPuller). Hidden-API флаги как у factory.
- **Без потребителей (не перенесены, доказательства в JSON):** IClipboardSmtEx, IPowerManagerSmtEx,
  IPowerManagerMonitorEx, ISmsSecurityAgent/Service, HIDL IServicetracker (на заводском vendor нет HAL
  servicetracker, заводские вызовы всегда неуспешны).
- **Решение boot classpath (не framework.jar, 13):** sysmonitor-framework (IDataReport*, casthal) —
  Smartisan/sys-часть; QPerformance.jar IPerfManager (закрытый, сервер /system/bin/perfservice);
  WfdCommon.jar (закрытый, сервер WfdService.apk, потребитель ExtendedRemoteDisplayHelper в services);
  telephony-ext.jar IExtTelephony/IDsda/INetworkCallback/IDepersoResCallback — открыт в CodeLinaro
  platform/vendor/codeaurora/telephony, сервера «extphone» на заводе нет, но заводской product
  Settings.apk безусловно вызывает IExtTelephony$Stub.asInterface в SettingsActivity.switchToFragment:
  без JAR на BOOTCLASSPATH он упадёт с NoClassDefFoundError.

Статически (`validation/factory-only-aidl-port.json`, изменённые члены с hidden-API флагами):
framework.jar **163/164**, services.jar **30/35** классов идентичны. Отличия объяснены: способ создания Ext
(ExtImplFactory), непортированные PICO/Smartisan/QTI поля в конструкторах WMS/WindowState/DisplayContent,
сдвиг ID framework-res, заводские MORE_DEBUG/localLOGV логи, PICO canShowAnrDialog в AppErrors. Строки
Source statsd совпадают с заводским (CarStatsPuller, «statsd terminated on receiving signal»).
Оставлено для Smartisan-части: ActivityManagerSmtBase (prefetch, getSmtEx — путь FreezeManager.init в
PicoSyshub/XRRuntime), DeviceIdleControllerSmtEx, SmtPCUtilsSmtBase, PowerAdvisorInternal,
SysTransManager и серверы sys-/sysmonitor-services.

Новый `FactoryOnlyAidlFixture` (0107): 24 интерфейса (18 только factory и 6 с новыми сигнатурами) и
2 Parcelable, 332 строки. Пакет `outputs/framework-boot-image-test-26` на шлеме (adb 192.168.1.230:5555,
временные fixtures в /data/local/tmp от shell UID): **29 fixtures** на ARM64 и ARM32; wire против
заводского framework — factory-only **332/332**, appended 1790/1790, shifted 1207/1207, PICO 313/313,
Qualcomm 1190/1190, audio 346/346 на обоих ABI; VR policy 76/78 + 2 ожидаемых; inspect-vr-canvas и
record-framework-runtime пройдены. Полная сборка droid проходит (`validation/full-build.json`).
verify-patch-series: 109 патчей, 27 компонентов.

## Предыдущая точка: 17 AIDL-таблиц с добавлениями в конец (0097–0105)

Этап 3, часть 3. У 17 интерфейсов framework заводская таблица — это Source-таблица плюс методы,
добавленные в конец. Теперь все 17 таблиц совпадают с factory 5.13.7 (`tools/compare-aidl-tables.py`:
**820 из 857** идентичны, было 794; со сдвигом кодов — 0, с добавлением в конец — 0, только на
заводе — 37, было 46). Перенесены таблицы, клиенты и серверы:

- **CodeLinaro LA.UM.8.12.c3-64900 (0097, 0099–0102):**
  - IPackageManager.getSplitPermissions: SplitPermissionInfoParcelable, PermissionManager, SystemConfig,
    PackageParser, PermissionManagerService.
  - INetworkPolicyListener.onSubscriptionPlansChanged: SubscriptionPlan network types (формат Parcel
    как у factory), NPMS dispatch/проверка планов, ключи 5G unmetered; DcTracker/DataConnection
    (frameworks/opt/telephony), DataSaverBackend (Settings).
  - IRecentsAnimationController.setDeferCancelUntilNextTransition: RecentsAnimationController целиком
    как CodeLinaro, SystemUI shared compat.
  - IImsUt.queryCFForServiceClass: ImsUtImplBase (system API, как CodeLinaro), ImsUt (новый компонент
    frameworks/opt/net/ims), GsmCdmaPhone/ImsPhone/ImsPhoneMmiCode.
  - ICameraServiceListener.onCameraOpened/onCameraClosed: новый компонент frameworks/av — CameraService
    с разрешением CAMERA_OPEN_CLOSE_LISTENER, NDK/тестовые слушатели; CameraManager. Заводской
    libcameraservice содержит тот же updateOpenCloseStatus.
  - Полная сверка сигнатур всех общих таблиц нашла внутри IBatteryStats notePhoneDataConnectionState
    с serviceType (имя то же, сигнатура другая): перенесено из CodeLinaro вместе с бинами
    out-of-service/emergency BatteryStats (CHECKIN_VERSION 35, как на заводе).
- **PICO, восстановлено из заводского DEX:** IBackupManager backup/restore и
  IFullBackupRestoreObserver.onBackupRestoreErr (ExtTrampoline, ExtUserBackupManagerService,
  PicoFullBackupTask/PicoFullRestoreTask, хуки FullBackupEngine/FullRestoreEngine);
  IPackageInstallerSession.getInstallFlags; IInputManager.getVitualInputDevice (InputManager и
  InputManagerService Ext); IUsbManager.startAccessory (ExtUsbDeviceManager);
  IPlayer.setExtVolume (PlayerBase Java и C++ PlayerBase::setExtVolume из дизассемблирования
  libaudioclient/libaaudio, ссылка NDK ABI libaaudio обновлена — 0104, размеры vtable как у factory);
  IPowerManager.setSensorControlScreenFeatureState (ExtPowerManagerService, layoutlib — 0105);
  ISchedulingPolicyService.requestThreadCpuset (сервер и libmediautils);
  IApplicationThread.scheduleActivityTimeout (ExtActivityStack для таймаутов pause/stop/destroy).
- **Smartisan, минимальное точное подмножество из DEX:** IActivityManager getMonitorEx/getISmtEx/
  keepProcessAliveBackground, IApplicationThread onPrefetchRealStart/completePrefetchBindApplication/
  configArtTracer/scheduleMethodTrace, getISmtEx у IPackageManager и IWindowSession,
  IBatteryStats.getIBatteryStatsOptEx. Добавлены заводские AIDL IActivityManagerSmtEx,
  IActivityManagerSysMoEx, IPackageManagerSmtEx, IWindowSessionSmtEx, IBatteryStatsOptEx, ISysClient,
  IMemClient, IActivityLifeCycleObserver, IAppStartEventObserver, parcelable AppInfoItem/
  AppStartEventItem, серверные объекты и достигнутые члены *SmtBase/SysOptBridge/SysMonitorSvcBridge/
  SysFwBridge с заводскими реализациями по умолчанию (поведение factory без sys-/sysmonitor- JAR).
  Hidden-API флаги как у factory (PrefetchRegister GREYLIST, ApplicationInfo appInfoJsonConfig/
  appLastTime WHITELIST), smartisanos.util в whitelist boot jars (0103).

Статически (`validation/appended-aidl-port.json`, изменённые члены с hidden-API флагами):
framework.jar **166/174**, services.jar **84/125**, telephony-common.jar **8/15** классов идентичны
по перенесённым членам (с учётом заводских членов, которые не переносились: 158/51/8). Все отличия
объяснены: способ создания Ext (ExtImplFactory против прямого new), непортированные PICO/Smartisan/QTI
поля в тех же конструкторах, отладочные логи factory (MORE_DEBUG, DEBUG_RECENTS_ANIMATIONS),
Android 11 BackupWakeLock, нумерация access$/лямбд/анонимных классов, соседние функции CodeLinaro
(bandwidth/NR в DcTracker, RTT-ключи CarrierConfig). Заводские отказы воспроизведены как есть
(ClassCastException в Session.getISmtEx и getIBatteryStatsOptEx без sys JAR и др.).

Оставлено для Smartisan-части: писатели mPrefetchApps, mLastWordMap, curFrozenStat,
mTopFullScreenStack, mAllTaskPersistPackages, mPrefetchData; пути до реализаций по умолчанию
мостов (ArtTracer, MemMonitor, Prefetch, MemoryProcessController, AnrMonitor, TransferController и др.);
вызывающие ActivityManagerSmtBase/StrictMode, ActivityManagerMonitorEx, PeroptWhiteListParser,
WindowSessionSmtBase, LightsService, ProcessListSmtBase и sys-/sysmonitor- JAR. Для других частей:
ExtAudioServiceImpl (вызывающий setExtVolume), IBackupAgent.doFullBackup с путями (factory меняет
сигнатуру на месте), LED/DP ExtPowerManagerService, PICO USB startAccessoryMode(boolean).
Сверка сигнатур нашла ещё 6 интерфейсов с тем же именем метода, но другой сигнатурой: IBackupAgent,
IBluetoothPan, INetworkStatsService, IStatsManager, IVibratorService, ISystemGestureExclusionListener
(перенесены в 0106–0109).

Новый `AppendedAidlFixture` (0098): 26 интерфейсов (17 таблиц и 9 заводских Smartisan) и 3 Parcelable,
1790 строк. Пакет `outputs/framework-boot-image-test-25` на шлеме (adb 192.168.1.230:5555, временные
fixtures в /data/local/tmp от shell UID): **28 fixtures** на ARM64 и ARM32; wire против заводского
framework — appended-aidl **1790/1790**, shifted-aidl 1207/1207, PICO 313/313, Qualcomm 1190/1190,
audio 346/346 на обоих ABI; VR policy 76/78 + 2 ожидаемых; inspect-vr-canvas и
record-framework-runtime пройдены. Полная сборка droid проходит (`validation/full-build.json`).
verify-patch-series: 105 патчей, 27 компонентов.

## Предыдущая точка: userdata с wrapped keys ICE (0091–0096)

Блокер загрузки Source образа. Заводской fstab (`vendor/etc/fstab.qcom`, идентичен
`fstab.qcom` в ramdisk boot) монтирует userdata с
`latemount,wait,check,formattable,fileencryption=ice,wrappedkey,quota,reservedsize=128M,checkpoint=fs`,
/metadata — с `wrappedkey,first_stage_mount` без `keydirectory=` (metadata encryption нет).
Из 16 флагов fs_mgr r47 не знал только `wrappedkey`: предупреждал и игнорировал его. Source vold
ставил сырые случайные ключи и не вызывал keymaster exportKey. Поэтому ключи с существующего
userdata нельзя было превратить в ключи ICE.

- **Донор:** CodeLinaro LA.UM.8.12.c3-64900-sm8250.0.
  - 0091 system/vold (020b06a): дерево совпадает с CodeLinaro во всех 95 файлах, кроме Android.bp.
    - При `wrappedkey` на /data ключи DE/CE/system генерируются в keymaster (KM_TAG_FBE_ICE,
      KM_TAG_KEY_TYPE) и хранятся как blob. Перед установкой blob экспортируется как ephemeral
      wrapped key (exportKey RAW; upgradeKey при KEY_REQUIRES_UPGRADE). Ссылка ключа строится
      по первым 32 байтам. CE blob удаляется в keymaster при evict. Есть wrapped-варианты
      add/clearUserKeyAuth.
    - `fscrypt_initialize_systemwide_keys` добавляет per-boot ключ. installKey пробует
      `type_hwkm` и откатывается на logon fscrypt_key.
    - CONFIG_HW_DISK_ENCRYPTION(_PERF): req-crypt и libcryptfs_hw. Также ICE для UFS-card и
      исправления Checkpoint/EncryptInplace/Loop/secdiscard.
    - Отличие Android.bp: libvold берёт только заголовки libcryptfs_hw. Заводская библиотека есть
      только для arm64, а vold линкует её как в CodeLinaro.
  - 0092 system/core (новый компонент): флаг `wrappedkey` (FstabEntry wrapped_key). В fs_mgr_mount_all
    /data пропускается в ffbm, сбой metadata-монтирования даёт `NEEDS_RECOVERY_WIPE_PROMPT`,
    для f2fs есть принудительный fsck `-f`. Init вызывает `--prompt_and_wipe_data`,
    init.rc создаёт /data/per_boot. fs_mgr.cpp, fs_mgr.h и fstab.h равны CodeLinaro.
  - 0093 system/extras (новый компонент): libfscrypt ставит per-boot политику и понимает
    `ice_wrapped_key_supported` → FS_ENCRYPTION_MODE_PRIVATE. checkpoint_gc разрешает symlink.
    Файлы равны CodeLinaro.
  - 0094 hardware/interfaces: KM_TAG_FBE_ICE (BOOL 16201), KM_TAG_KEY_TYPE (UINT 16202).
  - 0095/0096 build/soong и build/make: `Device_support_hwfde(_perf)` из
    `TARGET_HW_DISK_ENCRYPTION(_PERF)`.
  - Device tree: оба флага включены. `cryptfs_hw/` содержит заголовок CodeLinaro и prebuilt
    заводского `product/lib64/libcryptfs_hw.so`. Исходник CodeLinaro требует закрытый HAL
    vendor.qti.hardware.cryptfshw@1.0, а образ и так загружает этот файл из заводского product.
- **Сверка с заводскими бинарниками:**
  - Source `/system/bin/vold`: DT_NEEDED совпадает с factory 5.13.7 по составу и порядку.
    Совпадают импорты libcryptfs_hw (6 функций, включая set_ice_param, т.е. _PERF)
    и все 19 маркеров wrapped-key/per-boot/req-crypt/checkpoint.
  - libfscrypt.so, libfs_mgr.so (wrappedkey, metadata→wipe prompt, ffbm) и /system/bin/init
    (`--prompt_and_wipe_data`): маркеры и DT_NEEDED совпадают. /data/per_boot есть в init.rc
    обоих образов.
  - First-stage init берётся из сохранённого заводского boot и уже знает `wrappedkey`.
    Второй этап init, libfs_mgr, libfscrypt и vold берутся из Source.
  - Заводской keymaster HAL: `android.hardware.keymaster@4.0::IKeymasterDevice/default`,
    libqtikeymaster4 с exportKey/upgradeKey/deleteKey. Теги FBE передаются в TA как есть.
  - В ядре есть fscrypt_ice/PFK и нет `type_hwkm`. Поэтому ключ ставится по старому пути:
    logon fscrypt_key, contents mode 127, как на заводе.
- **Остаток:** PICO-добавки без донора, не связанные с ключами userdata:
  - vold: NTFS/exFAT, логи PublicVolume, countryCode; поэтому на заводе есть ещё импорты
    strtok/wait/__vsprintf_chk.
  - libfs_mgr: stabd, kernellog, разбор mountinfo, GSI developer ключи.
  - init: FFU UFS, memcg, cpuset audio-app, триггеры factory-fs/mmi.
- **Только загрузкой** можно проверить:
  - что TA принимает существующие blob (upgradeKey при смене patch level);
  - что PFK принимает ключи;
  - разблокировку CE через Source LockSettings/Gatekeeper;
  - откат checkpoint=fs и отсутствие SELinux denials.

Сборка целей vold/vdc/init/libfs_mgr/libfscrypt и полная `droid -k` проходят
(`validation/full-build.json`). verify-patch-series: 96 патчей, 23 компонента.

## Предыдущая точка: платформенная SELinux-политика factory (0088–0090)

Блокер загрузки Source образа. Образ сохраняет заводские vendor/product/odm 5.13.7, и init
компилирует их политику вместе с Source plat policy. Раньше Source plat (r47) не определял
363 заводских типа: vendor через mapping 29.0 ссылался на 261 из них, а атрибуты `*_29_0`
оставались пустыми. Заводской `product_sepolicy.cil` называет plat-типы напрямую, поэтому
secilc завершался ошибкой `Failed to resolve typeattributeset`.

- **Донор без изменений:** новый компонент `device/qcom/sepolicy` — CodeLinaro
  LA.UM.8.12.c3-64900-sm8250.0 (`830b6eb9`). Каталоги generic и qva public/private подключены
  как в QSSI через `BOARD_PLAT_PUBLIC/PRIVATE_SEPOLICY_DIR`. Android 10 принимает списки
  (`+=` в system/sepolicy/Android.mk). Донор дал 77 из 363 типов (bt_logger, qvrd,
  dun-server, dpmd и др.). Прежние bt_logger/Bluetooth-файлы device tree удалены: они есть
  в доноре.
- **Реконструкция:** остальные 286 типов, 10 атрибутов и вся PICO-политика восстановлены из
  заводского `plat_sepolicy.cil` (`tools/reconstruct-factory-sepolicy.py`). Инструмент
  вычитает baseline «r47 + донор». Объявления размещены по порядку заводского CIL:
  43 в system/sepolicy (41 public, 2 private; PICO VR-службы, hal_*_default, свойства и файлы);
  253 в `device/pico/PICOA8110/sepolicy` (215 public, 38 private).
  Тип public ⇔ он есть в factory mapping/29.0 (246). Атрибут, членство или правило public ⇔
  оно есть в factory `plat_pub_versioned.cil`.
  Восстановлено: 14 746 allow-кортежей «право–класс», 39 dontaudit, 25 allowx,
  39 type_transition, 171 neverallow с PICO-именами, 103 членства в атрибутах,
  64 genfscon, контексты file 148, property 94, service 46, hwservice 4.
- **system/sepolicy (новый компонент):**
  - 0088 — класс `perf_event`: заводской бэкпорт Android 11. Типы
    hal_{atrace,audio,bluetooth,camera}_default перенесены из AOSP vendor в platform public:
    заводской vendor их использует, но не объявляет.
  - 0089 — объявления PICO-типов и `28.0.ignore.cil`.
  - 0090 — заводские исключения neverallow: 61 правка в 20 файлах. Сюда входят exception
    lists, +21 домен в `dac_override_allowed` и `app_domain(system_app)` без file neverallow.
    Neverallow system_server execute_no_trans и device_config_runtime_native_prop удалены,
    `sdcard_type` заменён на `{ sdcard_type -sdcardfs }`. Treble violator test принимает только
    заводских нарушителей.
  - Всё зеркалировано в prebuilts/api/29.0 для `sepolicy_freeze_test`.

`tools/check-sepolicy.py` → `validation/sepolicy-parity.json`:

- **Boot compile:** компиляция как в init (`secilc -m -M true -G -N -c 30`: Source plat + mapping 29.0 +
  заводские product, mapping, plat_pub_versioned и vendor_sepolicy) — **код 0**; контроль с
  factory plat — код 0. Все 1254 versioned-атрибута vendor/product отображаются в те же типы,
  что у factory: 0 пустых, 0 различий. Хеш plat+mapping отличается, поэтому odm
  precompiled_sepolicy не используется и init компилирует политику сам.
- **Паритет «до чанка → после донора → итог»:**
  - типы factory-only 363 → 286 → **0**;
  - allow factory-only 14 746 → **0**, dontaudit 39 → **0**;
  - allowx, type_transition, genfscon и членства factory-only → **0**;
  - контексты factory-only: file 178 → 148 → 0, property 123 → 94 → 0, service 67 → 46 → 0,
    hwservice 5 → 4 → 0, seapp 2 → 0.
- **Остаток:**
  - Source-only 9 типов: qcc/qtrservice из более нового CodeLinaro, qti-testscripts
    (userdebug), apex_test r47. Allow source-only 1577: userdebug/r47/CodeLinaro.
    Dontaudit source-only 7035: su и qti-testscripts, userdebug.
  - Neverallow factory-only 970 / source-only 921: exception lists AOSP-правил. При загрузке
    они не проверяются (`-N`), Source-правила их не нарушают.
- **Метки:**
  - 5992 пути заводского system: **0 расхождений** plat_file_contexts.
  - 1181 имя свойства: одно расхождение, `ctl.android.hardware.dumpstate`: r47 exact →
    ctl_dumpstate_prop, factory → ctl_default_prop.
  - service/hwservice совпадают.

Сборка `selinux_policy` и полная `droid -k` проходят. Это neverallow-проверки
checkpolicy/secilc, freeze test и treble tests 26.0–28.0 (`validation/full-build.json`).

Остаётся блокер userdata: заводской fstab использует `fileencryption=ice,wrappedkey`, а в
Source vold/fs_mgr нет wrapped keys. Этот этап его не решает (REMAINING-WORK).

## Предыдущая точка: 19 AIDL-таблиц со сдвигом кодов (0075–0087)

Этап 3, часть 2. У 19 интерфейсов framework коды транзакций расходились с заводскими
в середине таблицы: заводской бинарник, вызывающий Source-сторону, попал бы в другой метод.
Теперь все 19 таблиц совпадают с factory 5.13.7 (`tools/compare-aidl-tables.py`:
**794 из 857** таблиц идентичны, было 774; со сдвигом кодов — 0, с добавлением в конец —
17, только на заводе — 46). Заводские таблицы — это CodeLinaro LA.UM.8.12.c3-64900 плюс
PICO; перенесены таблицы, клиентские и серверные реализации:

- 0075 (frameworks/base): IAccountManager без shared-account методов; INotificationManager
  silenceNotificationSound (громкость в PhoneWindowManager) и pullStats (PulledStats,
  статистика undecorated RemoteViews, statsd atom 10066); ITaskStackListener
  onSingleTaskDisplayDrawn/Empty (TRANSIT_SHOW_SINGLE_TASK_DISPLAY, SystemUI shared);
  IWindow locationInParentDisplayChanged (смещение окон embedded display, a11y bounds);
  IDisplayManager createVirtualDisplayExt (PICO, код 16) — восстановлен из заводского DEX на
  основе Android 11: VirtualDisplayConfig, DisplayManager/DisplayManagerGlobal,
  DisplayManagerService/VirtualDisplayAdapter с displayIdToMirror.
- 0076: IUserManager (pre-created users, UserInfo.preCreated в Parcel как на заводе),
  IBiometricService canAuthenticate(userId)/hasEnrolledBiometrics, IStorageManager
  clearUserKeyAuth, IInstalld без markBootComplete.
- 0077: IBluetoothManager factoryReset/onFactoryReset, INfcAdapter vendor interface,
  networkstack AIDL версии 5 (CodeLinaro) с PICO INetworkMonitor updateDnsEvent/
  updateDnsEvents (коды 8/9) и пакетной отправкой DNS-событий из ConnectivityService.
- 0078: ISms, ITelephonyRegistry (phoneId), IConnectionService addParticipantWithConference.
- Компоненты: system/bt (0080), frameworks/native installd (0081), новые system/vold (0082,
  clearUserKeyAuth и трёхаргументный fdeChangePassword), packages/modules/NetworkStack (0083,
  синхронизация с CodeLinaro), packages/apps/Nfc (0084), frameworks/opt/telephony (0085),
  TeleService (0086), Telecomm (0087).

Статически (`validation/shifted-aidl-port.json`, только перенесённые члены, с hidden-API
флагами): framework.jar **95/96**, services.jar **65/83**, telephony-common.jar **17/20**,
NetworkStack.apk против заводского InProcessNetworkStack.apk **13/20**. Все отличия
объяснены: PICO/Smartisan хуки без донора в тех же методах (IExt*, SysOptBridge,
BootEventStat, capture displays), отладочные логи, скомпилированные на заводе, ID ресурсов
framework-res, нумерация access$/лямбд/анонимных классов D8, соседние функции CodeLinaro
вне таблиц (essential SIM records, RTT remote, avoidMoveToFront), R8-сжатие заводского
InProcessNetworkStack. Не перенесено сознательно: сборщик телеметрии ByteDance
NetworkStatusCollect/Slardar (единственный заводской потребитель updateDnsEvent), реакция
BubbleController (на заводе нет SystemUI), остальные атомы statsd CodeLinaro.

Новый `ShiftedAidlFixture` (0079) прогоняет 15 интерфейсов boot class path и Parcel UserInfo,
VirtualDisplayConfig, AdnRecord; 4 networkstack-интерфейса services.jar сверены статически.
Пакет `outputs/framework-boot-image-test-24` на шлеме (adb 192.168.1.230:5555, временные
fixtures в /data/local/tmp от shell UID): **27 fixtures** на ARM64 и ARM32; wire против
заводского framework — shifted-aidl **1207/1207**, PICO **313/313**, Qualcomm **1190/1190**,
audio **346/346** на обоих ABI; VR policy 76/78 + 2 ожидаемых; inspect-vr-canvas и
record-framework-runtime пройдены. Полная сборка droid проходит (`validation/full-build.json`).

Риск для полного Source образа: заводской fstab использует `fileencryption=ice,wrappedkey`,
а Source vold/fs_mgr не поддерживает wrapped keys (clearUserKeyAuth перенесён для
не-wrapped пути). Нужен отдельный перенос vold CodeLinaro до монтирования userdata.

## Предыдущая точка: IAudioService и Spatializer (0073–0074)

Этап 3, часть 1. Заводской framework.jar 5.13.7 — это аудио-служба CodeLinaro
LA.UM.8.12.c3-64900 плюс PICO-бэкпорт Spatializer из Android 13 (донор
android-13.0.0_r1, frameworks/base и frameworks/av). Патч 0073 даёт IAudioService
заводскую таблицу из 131 транзакции (было 96; с кода 61 —
handleBluetoothA2dpActiveDeviceChange, в конце — setAllowed/getAllowedCapturePolicy,
семейство Spatializer и PICO setRecordSilenced) и переносит реализацию:

- framework: AIDL ISpatializer (с PICO-методами releasePlayer/setPlayerSessionId/
  enableSpatialization/isSpatializationEnabled/setAudioOrientation/setAudioPose),
  INativeSpatializerCallback, ISpatializer*Callback, SpatializationLevel/Mode и
  SpatializerHeadTrackingMode как интерфейсы с константами (как на заводе); Spatializer,
  CallbackUtil, AudioDeviceAttributes/AudioProfile/AudioDescriptor, android.media.permission;
  флаги пространственного звука AudioAttributes (включая PICO SPATIALIZATION_BEHAVIOR_ALWAYS
  и тип ambisonic, восстановлены из DEX), AudioManager/AudioSystem, Settings.Secure.
  SPATIAL_AUDIO_ENABLED, 89 hidden-API флагов whitelist как на заводе;
- services: SpatializerHelper в заводском виде (маршрут по legacy stream type, head tracker
  всегда доступен, без поиска сенсоров), связка в AudioService, AudioDeviceBroker/
  AudioDeviceInventory/BtHelper/PlaybackActivityMonitor из CodeLinaro — сквозная цепочка
  handleBluetoothA2dpActiveDeviceChange для заводского Bluetooth.apk, TWS+ и кэш capture policy.

Статически (`validation/audio-port.json`): framework.jar **102/103**, services.jar **36/38**
с hidden-API флагами; все 12 AIDL, Spatializer, SpatializerHelper, AudioDeviceBroker/
Inventory байт-в-байт по ссылкам. Объяснённые отличия: ID ресурса framework-res
(AudioManager.isBluetoothScoAvailableOffCall), PICO-маскирование устройств в
AudioService.getDeviceForStream без донора, нумерация кодеков QTI в BtHelper (стек QTI не
переносится). `tools/compare-aidl-tables.py`: IAudioService идентична заводской; совпадают
774 из 857 таблиц (было 762), 19 со сдвигом кодов, 18 с добавлением в конец, 46 только на
заводе. `tools/check-factory-bluetooth.py`: Java-пробел Bluetooth.apk
handleBluetoothA2dpActiveDeviceChange исчез. Полная сборка droid с Metalava API checks
проходит (`validation/full-build.json`).

Нативная зависимость (`validation/audio-members/native-dependency.json`): на заводе JNI
setRecordSilenced/nativeGetSpatializer/canBeSpatialized вызывает AudioSystem:: в PICO
libaudioclient (IAudioPolicyService заводской сборки AIDL-генерированный), а реализация —
Spatializer, SpatializerPoseController и per-player spatialization в libaudiopolicyservice,
spatializer output и setRecordSilencedState в libaudiopolicymanagerdefault, libspatialaudio/
libvraudio; vendor задаёт ro.audio.spatializer_enabled=true. В Android 10 audioserver
Source этого нет, поэтому JNI сообщает состояние сервера без spatializer (null, false,
AUDIO_STATUS_ERROR) — SpatializerHelper уходит в STATE_NOT_SUPPORTED без падения
system_server. Перенос нативного Spatializer — отдельная часть этапа 3.

0074 добавляет `AudioApiFixture` (346 строк: IAudioService и 11 Spatializer AIDL) в Source
probe; число fixtures растёт до 26. Проверено на шлеме с `outputs/framework-boot-image-test-23`:
26 fixtures на ARM64 и ARM32, wire PICO 313/313, Qualcomm 1190/1190, audio **346/346** на
обоих ABI (`validation/audio-api-wire.json`, включено в `validation/audio-port.json`),
VR policy 76/78 + 2 ожидаемых. IAudioService подтверждён на устройстве.

## Предыдущая точка: полная сборка droid (0070–0072)

Полная сборка `aosp_pico4pro-userdebug` (`m droid`, 8 CPU) проходит, включая system.img,
check_boot_jars, VNDK header-abi-diff и VINTF (`validation/full-build.json`):

- 0070 — Settings передаёт userId в заводские сигнатуры FaceManager (из 0046) ровно как
  CodeLinaro Settings LA.UM.8.12.c3-64900-sm8250.0; это была наша регрессия.
- 0071 — новый компонент build/make: в whitelist boot jars добавлены ровно 13
  перенесённых пакетов PICO из framework.jar.
- 0072 — эталонные VNDK ABI-дампы libbinder и libstagefright_bufferqueue_helper
  (arm64, arm). Расширение libbinder (FreezeManager, IUnFreezeCallback,
  getLastFrozenPid) совпадает с экспортами заводской vndk-29 libbinder, смещение поля
  IPCThreadState то же (arm64 460, arm 244); размеры vtable IProducerListener/
  ProducerListener совпадают с заводскими на обоих ABI. Открыто для этапа 3: ~150
  PICO/Smartisan экспортов заводской libbinder, которых нет в Source.

## Предыдущая точка: заводской Bluetooth на Source framework (0067–0069)

Решение пользователя: Source образ оставляет заводской PICO/QTI Bluetooth-стек 5.13.7
(Bluetooth.apk, BluetoothExt.apk с сервером IBluetoothDun, libbluetooth_qti и его
замыкание, bt_logger, /etc/bluetooth) вместо AOSP Bluetooth. Набор записан в
`device/pico/PICOA8110/factory-bluetooth.json`; заводские oat/vdex не копируются.
`tools/check-factory-bluetooth.py` проверяет его против сборки Source
(`validation/factory-bluetooth.json`):

- 15 ELF: все DT_NEEDED и символы разрешаются в Source. Для
  `android.hidl.base@1.0.so` (только DT_NEEDED, символы в libhidlbase) device tree
  добавляет пустую совместимую библиотеку, как libhidltransport в AOSP 10.
- Java: все ссылки Bluetooth.apk/BluetoothExt.apk разрешаются, кроме
  `AudioManager.handleBluetoothA2dpActiveDeviceChange` (этап 3, таблица IAudioService).
- AIDL-таблицы 39 интерфейсов, которые APK реализуют или вызывают, совпадают с factory;
  у IBatteryStats заводской getIBatteryStatsOptEx добавлен в конец (Smartisan, этап 3).
- Разрешения, SELinux (домен bt_logger, свойства vendor Bluetooth), hidden-API
  whitelist обоих пакетов — совпадают.

Патчи: 0067 — IBluetoothLeCallback (восстановлен из factory) и IBluetoothGatt
registerCallback/unregisterCallback (56/57) в system/bt; 0068 — javax.obex MTU из
CodeLinaro; 0069 — AOSP Bluetooth (запасной стек) уведомляет IBluetoothLeCallback как
factory. Статически (`validation/factory-bluetooth-port.json`): 5/5 классов AIDL
идентичны вместе с hidden-API флагами, javax.obex 25/25, GattService отличается только
отключённым DBG-логированием. `framework-boot-image-test-22`: 25 fixtures на обоих ABI,
PICO wire 313/313, Qualcomm 1190/1190, VR policy 76/78 + 2 ожидаемых.

Сравнение всех AIDL-таблиц framework (`tools/compare-aidl-tables.py`,
`validation/aidl-table-parity.json`): 762 из 857 совпадают, 20 со сдвигом кодов
(в т.ч. IAudioService 131/96), 18 с добавлением в конец, 57 только на заводе — вход этапа 3.

## Предыдущая точка: QTI Wi-Fi vendor путь (патчи 0059–0066)

Заводской wifi-service.jar 5.13.7 — это CodeLinaro LA.UM.8.12.c3-64900 плюс
PICO-дополнения. Поэтому frameworks/opt/net/wifi и system/connectivity/wificond
синхронизированы с этим тегом (0063, 0065; возвращено удаление Passpoint R2
broadcasts из r47, которое есть и на заводе): QtiClientModeImpl/QtiClientModeManager/
QtiWifiConnectivityManager и второй STA в WifiServiceImpl/ActiveModeWarden/WifiInjector,
вызовы vendor.qti supplicant@2.0–2.2 в SupplicantStaIfaceHal (DPP, getCapabilities,
doDriverCmd, Wi-Fi generation), hostapd@1.0–1.2 в HostapdHal, fstman@1.0
FstManagerGroupHal, FST в libwifi_system. Новый компонент
vendor/qcom/opensource/interfaces (CodeLinaro, 0059) даёт .hal и hidl-gen модули;
Java-библиотеки статически входят в wifi-service, как на заводе. android.net.wifi
взят из CodeLinaro frameworks/base с PICO полями WifiConfiguration (0062), плюс
wifi.proto, настройки, ресурсы, SystemUI и Settings (0066) для SoftAP callbacks.

Заводской android.hardware.wifi@1.0 содержит PICO поля contention_atime_* в
StaLinkLayerIfacePacketStats (48 байт, radios по смещению 200). Заводской vendor
HAL собран под эту раскладку, а VNDK-библиотека на /system — Source, поэтому .hal
изменён (0060), обновлены ссылки ABI VNDK (0061, только изменённые записи) и
WifiLinkLayerStats/WifiVendorHal (0064).

Статически (`validation/qti-wifi-port.json`): wifi-service.jar **2250/2327**
классов совпали с factory, QTI путь 606/618; android.net.wifi 393/394 с
hidden-API флагами; **929/929** HIDL классов (vendor.qti, android.hardware.wifi,
android.hidl) идентичны по инструкциям и регистрам; 69 hash chain совпали с
hidl-gen по Source .hal и current.txt донора; смещения StaLinkLayerStats в
VNDK (arm64/arm) и символы C++ библиотек vendor.qti supplicant/hostapd совпали с
factory. Остальные 77 отличий объяснены: PICO без донора (NetworkStatusCollect,
NetworkPxrAdapter, SWIFT, 9-значный signal poll PICO wificond, autoConnect/needLogin,
FEAT_* и др.), security-патчи AOSP после r47, ID ресурсов framework-res, SeempLog.
Runtime HIDL fixture невозможен: локальный Java HwBinder нельзя transact
(CHECK в JHwBinder_native_transact), HwParcel нельзя перемотать/выгрузить,
а регистрация в hwservicemanager для shell UID запрещена.

Пакет `framework-boot-image-test-21`: 25 fixtures на ARM64 и ARM32; PICO wire
313/313, Qualcomm wire 1190/1190, VR policy 76/78 + 2 ожидаемых на каждом ABI.
Qualcomm отчёт обновлён: framework.jar 92/97, wifi-service.jar 4/6.
Сборка Settings, сломанная ранее перенесённым Qualcomm FaceManager (0046), исправлена
патчем 0070; изменение SoftAP в Settings проверено компиляцией.

## Предыдущая точка: хвост цепочки PICO VR (патч 0058)

Патч 0058 переносит остаток VR-цепочки framework: ExtPackageParserUtils
(2D virtual display), PackageParser.parseBaseApkCommon с PICO хуками,
полные ExtActivityThreadImpl/IExtActivityThread и ExtViewRootImplImpl/
IExtViewRootImpl с вызовами из ActivityThread/ViewRootImpl, android.pico.ns,
IExtDisplay/ExtDisplayImpl (Display.mExt), хук пропуска ThreadedRenderer.draw
(по той же политике, не безусловный пропуск) и полный PicoSystemConfig.

`VrPolicyFixture` расширен до 78 сценариев: 76 совпали с factory на ARM64 и
ARM32, 2 — ожидаемые отличия (`validation/vr-policy-port.json`). Статически
(`validation/vrchain-port.json`): 30 классов, 24 байт-в-байт; 6 объяснённых
отличий — создание через ExtImplFactory/Smartisan поля, более поздняя ревизия
AOSP 10 (split permissions, inputFeatures), одна регистровая const/4 от D8 и
null-check в isActivityForceRender. PICO и Qualcomm wire (313/313, 1190/1190)
повторно подтверждены на `framework-boot-image-test-20`, 25 fixtures на ABI.

## Предыдущая точка: Qualcomm API из CodeLinaro LA.UM.8.12.c3

Патчи 0046–0057 переносят needed-кандидатов с точным донором CodeLinaro
`LA.UM.8.12.c3-64900-sm8250.0` (frameworks/base 4eb3b752 и соответствующие
opt/net/wifi, opt/telephony, packages/apps/Bluetooth, Telecomm, Telephony,
system/bt, wificond). Заводские таблицы AIDL отличались от AOSP в середине,
поэтому перенесены целиком вместе с серверными реализациями:
IWifiManager (110 транзакций, +IWifiNotificationCallback, WifiDppConfig),
IBluetooth (85), IBluetoothHeadsetPhone (12), новый IBluetoothDun, ITelephony
(255), ISub (47), ILockSettings (43), IUiModeManager (8), IFaceService (22).
Клиентская сторона: BluetoothDun/QualityReport/Codec*/Device/Socket, LE
Transport Discovery Data, WifiManager и shareThisAp/simNum, TelephonyManager/
SubscriptionManager, BoostFramework, View content capture (backport Android 11
в View/ViewGroup/ViewRootImpl/TextView/WebView), UiModeManager, LockPatternUtils,
FaceManager, FileSystemProvider.onDocIdDeleted (AOSP 11).

Сравнение с factory (`validation/qualcomm-api-port.json`, только перенесённые
члены): framework.jar 90/97, services.jar 12/15, wifi-service.jar 3/6,
telephony-common.jar 2/2, Bluetooth.apk 2/3; каждое оставшееся отличие
объяснено (непортированные соседние поля/ветки, ID ресурсов, QTI vendor).
`QcomApiFixture`: **1190 из 1190 wire-сценариев совпали с factory на ARM64 и
ARM32**; пакет `framework-boot-image-test-19` — 25 fixtures на ABI.

Требует решения/подсистем: Bluetooth vendor-методы (socket opts, clock sync)
и нумерация кодеков Qualcomm зависят от QTI-стека `libbluetooth_qti`, которого
нет в AOSP Bluetooth; Wi-Fi getCapabilities/dpp*/doDriverCmd/второй STA —
от HAL `vendor.qti.hardware.wifi.supplicant`; BoostFramework.mSmtEx и
IAudioService — этап 3. Сервер DUN (BluetoothExt.apk) и TeleService в заводском
образе отсутствуют в Source/на заводе соответственно.

## Предыдущая точка: собственный PICO API без открытых доноров

Патчи 0039–0045 переносят нужные по `validation/api-consumers.json` API PICO,
для которых нет открытого донора (FRAMEWORK-DONORS.md):

- **AIDL** — 15 интерфейсов восстановлены из заводских Stub/Proxy
  (`tools/reconstruct-pico-aidl.py`): порядок и коды транзакций, oneway,
  направления и имена параметров. com.pvr IPvrManagerService (20 методов,
  как на заводе; SDK-копии имеют 16 и перегрузку `updateUserSettings(String)`,
  которой нет у factory), IPvrCallback(Native), ISysDataSyncService,
  IConfigServiceInterface (71 метод), com.pico.api IApiLayer/IAppSession,
  com.pxr.pxrapi IScreenCaptureInterface, com.pxr.net и com.pxr.bluetooth.
  IPxrNotificationService/Callback в services.jar написаны вручную в заводском
  стиле старого генератора AIDL (без `$Default`).
- **Клиентские классы** — AppSession/AppSessionCallback, RemoteCallbackProxy,
  NetworkPxrAdapter с parcelables и com.pxr.net.common/util,
  BluetoothPxrDeviceProperty, android.pico.utils Features и PicoUtils,
  Smartisan ApplicationInfoSmtBase (Parcel перед PICO extension, как на заводе)
  и Qualcomm поля WifiInfo из CodeLinaro LA.UM.8.12.
- **Permissions** — EYE/FACE_TRACKING с группами, BACKGROUND_PLAYBACK,
  PICO SEND/RECEIVE_BROADCAST, POWER_SCENE_CHANGE, Smartisan lifecycle/startevent,
  AUTHORIZE_OUTGOING_SMS, CAMERA_OPEN_CLOSE_LISTENER с заводскими protectionLevel;
  platform.xml — miracast audio grants для media и split ACCESS_MEDIA_LOCATION.
- **Hidden API** — флаги как у factory: com.pxr.net через greylist-packages;
  whitelist PICO интерфейсов и трёх permission полей через новый
  `config/hiddenapi-whitelist.txt`, который build/soong (патч 0039) передаёт
  в `generate_hiddenapi_lists.py`. Без whitelist сторонние приложения со
  встроенной SDK-копией `com.pvr` не могли бы вызвать boot-классы.

Сравнение классов (`tools/compare-pico-api.py`: члены, флаги доступа,
static values, упорядоченные ссылки/строки/константы каждого метода и
hiddenapi-флаги): framework.jar — **94 из 96 классов идентичны**; отличаются
`Features.disableSystemAlert` (встроенный ID `R.id.spacer` зависит от
раскладки framework-res) и не перенесённый PicoUtilsDeprecated; services.jar
PxrNotification AIDL — 6 из 6. Permissions совпадают по именам, группам и
protectionLevel.

Пакет `framework-boot-image-test-18`: **24 fixtures на ARM64 и ARM32** с
Source compiled boot images. Новый `PicoApiFixture` проводит каждый метод 13
framework-интерфейсов через `Stub.asInterface` над записывающим binder и через
`Stub.onTransact` с теми же байтами, плюс round-trip четырёх parcelables.
Тот же probe JAR на заводском framework: **313 из 313 сценариев совпали на
каждом ABI** — коды транзакций, флаги, байты data/reply, разобранные аргументы
и байты parcelables. Fingerprint и загрузка сохранены, временные файлы удалены.

Не перенесено: серверные реализации (живут в заводских sys-JAR/приложениях),
com.pxr.bluetooth adapter/profile/manager и android.pico.ns (без потребителей),
ApplicationInfoMonitorEx, переводы новых строк framework-res. Реальный Binder
с заводскими службами и работа приложений на общем образе не проверены.
Framework commit `ef65422f04fb6612d19130ae0e80537dab4a5271`, build/soong
`1725e6ee745ff1c24b11e3cd63d5c85e0d2162ad`; 45 патчей воспроизводят все
component commits. Свидетельство: `validation/pico-api-port.json`.

## Предыдущая точка: цепочка VR-политики Activity → ViewRootImpl

Патчи 0034–0037 переносят заводскую политику VR skip-draw, 0038 добавляет fixtures:

- **0034** — `IExtActivityInfo`/`ExtActivityInfoImpl` (vrActivityFlag, force-render
  бит, 2D-позиция/тема/свойства из metadata `pico.vr.*`) и
  `IExtApplicationInfo`/`ExtApplicationInfoImpl` (VR-флаги приложения, launch
  orientation, поля 2D virtual display). Расширения создаются вместе с
  ActivityInfo/ApplicationInfo и проходят copy и Parcel в заводском порядке полей.
- **0035** — `ExtPackageParserImpl.parseVrFlags`, вызываемый для свежего и
  кэшированного результата `PackageParser.parsePackage`, как на заводе:
  `com.picovr.type`/`pvr.app.type`, VR-категории с MAIN, `requestedVrComponent`,
  белый список, `forceRenderActivity`, targetActivity alias, останов на
  AppDetailsActivity, launcher orientation. `PicoSystemConfig` перенесён только
  в части white/black list.
- **0036** — `ExtActivityThreadImpl.isActivityForceRender`: решает первая Activity,
  чей decor подключён к этому ViewRootImpl и которая является VR Activity;
  без такой Activity рисование принудительное.
- **0037** — `ExtViewRootImplImpl.isSkipDrawVrActivity` и маршрутизация
  `ViewRootImpl.drawSoftware`: VR canvas только при кэшированном на ViewRootImpl
  `vr_activity_skip_render_enabled` = 1 (default 1), VR Activity без force-render,
  заголовке без `com.android.permissioncontroller` и display ID 0. Остальные окна
  используют обычный `lockCanvas`/`unlockCanvasAndPost`; безусловного пропуска нет.

Пакет `framework-boot-image-test-17`: **23 Java/JNI fixtures на ARM64 и 23 на
ARM32** прошли с Source compiled boot images, ART и Bionic. Новые четыре на ABI:
60 общих сценариев политики и `drawSoftware` на fixture Surface. Пропускаемое
VR-окно рисует в canvas 1×1, producer queue/dequeue не меняется, native Surface
reference возвращается; пять вариантов обычных окон (setting 0, permission
controller, display 1, force-render, не-VR) уходят в `lockCanvas`.

Сравнение с factory: тот же probe JAR запущен обычным `app_process` на
установленном заводском framework (SHA-256 сверен) на обоих ABI. Из 60 сценариев
**58 совпали на каждом ABI**, включая байты Parcel обоих расширений. Два
ожидаемых отличия: запись без Activity и отсутствие ActivityThread — factory
бросает NullPointerException, Source пропускает запись/рисует обычно. Статическое
сравнение байткода 50 перенесённых методов (вызовы, поля, строки) не нашло
необъяснённых различий; factory-only остались вызовы 2D virtual-display
конфигурации `ExtPackageParserUtils` и Smartisan `verifyLibraryFiles`.

Не перенесено: `ExtPackageParserUtils` (2D virtual display), `parseBaseApkCommon`
(ET/FT permission filter), остальные hooks IExtActivityThread/IExtViewRootImpl
(NS client, input, lifecycle, display), SmtEx-данные Parcel перед PICO
расширением, reflection `ExtImplFactory` (Source создаёт реализации напрямую).
Fixture заменяет Settings provider, ViewRootImpl/ActivityThread/Activity
создаются без конструкторов; настоящая загрузка общего образа, 2D-панели в VR и
GPU/аппаратная VR-проверка остаются открытыми. Fingerprint и normal boot
сохранены, временные файлы удалены, системные разделы не менялись.

Framework commit: `7cb6259f025580ee90f5f4f7c85a571fe3c12a34`; 38 патчей
воспроизводят все component commits. Свидетельства: `validation/vr-policy-port.json`,
`validation/vr-skip-draw-policy-plan.json`, `validation/framework-boot-image.json`.
Скан потребителей API: `validation/api-consumers.json` (см. REMAINING-WORK).

## Предыдущая точка: Surface VR canvas API

Патч 0033 переносит Surface.getExt, IExtBase/IExtSurface/ExtSurfaceImpl и
три JNI canvas метода. Для VR skip-draw выдаётся opaque RGBA canvas 1×1;
producer buffer не блокируется и не ставится в очередь. Java удерживает
дополнительную native Surface reference до unlock/finally, включая случай
замены mNativeObject. Проверки повторного lock, неверного canvas и отсутствия
lock воспроизводят исследованные factory исключения.

Источник исследования — аутентифицированный framework.jar и обе factory
libandroid_runtime. Factory DEX и экспортированный lock возвращают Surface
pointer, но factory registration table указывает V. Source регистрирует
правильный J descriptor. Поток вызова factory registration не доказан.
ARM64 factory выделяет один malloc byte под RGBA canvas с rowBytes=4;
Source использует полноценное owned SkBitmap storage для каждого canvas.
Совпадение allocation/concurrency semantics с factory не заявляется.

Пакет `framework-boot-image-test-16`: 19 Java/JNI fixtures на ARM64 и 19
на ARM32 прошли с Source compiled boot images, ART, linker и Bionic.
Семь новых fixtures на ABI проверяют released Surface, extension identity,
canvas size/opaque/pixel drawing, +1 native reference при lock, ошибки
identity/double-lock, detach/release, повторные циклы и замену native Surface.
Fixture producer считает реальные queue/dequeue вызовы; их число не меняется.
Fingerprint и normal boot сохранены, temporary files удалены, system
partitions и установленные VR-службы не заменялись.

Framework commit: `ee1f82abfffe76146055e9022b0d87960cde707b`.
Все 33 патча воспроизводят настроенные component commits. Native/GUI/Binder
не изменялись относительно этапа 0032; предыдущие 378 native gtests остаются
свидетельством для этих же бинарных файлов. После текущего API переноса
структурный аудит двух JAR показывает 76 дополнительных native declarations
в factory framework и 6 в services. Это не число обязательных VR функций:
в аудит входят и другие OEM дополнения и перемещения между JAR.

Следующий production участок — цепочка ActivityInfo/PackageParser →
ActivityThread → ViewRootImpl. Factory skip-draw учитывает setting
vr_activity_skip_render_enabled, extended vrActivityFlag, matching Activity,
display ID 0 и исключение permission-controller окон. Source Surface API
готов, но эта политика и вызовы drawSoftware ещё не подключены. Не заменять
их безусловным пропуском рисования. Общая загрузка и GPU/VR остаются открытыми.
Свидетельства: `validation/vr-canvas-api.json`,
`validation/vr-skip-draw-policy-plan.json`, `validation/framework-boot-image.json`.

## Предыдущая проверенная точка: SurfaceMonitor и MonitoredProducer

Патч 0032 восстанавливает исследованные методы PICO SurfaceMonitor:
историю 120 кадров, анализ задержек и FPS, конфигурацию частот, параметры,
отчёты и запросы через Binder. MonitoredProducer записывает dequeue/queue
отметки, длительность успешного dequeue в Layer и кадровый слот в
SurfaceClient; принимает PICO-команду 1110 с проверкой interface token.

Пакет `bufferqueue-test-32` прошёл на обоих ABI. Всего проверены 378
уникальных native gtests, включая пять новых MonitoredProducer tests на
ABI. В 17 сценариях SurfaceMonitor на каждом ABI с factory совпали 74
снимка состояния, Binder parcels, service lookup и файловые обращения:
всего 148 снимков. Услуги, свойства, часы и caller ID заменяются внутри
probe-процесса; реальные запросы смены частоты не отправлялись.
Прежние tracker/fence/freeze/cache/dequeue/flags comparisons также прошли.

Пакет `framework-boot-image-test-14` использует те же Source GUI/Binder.
Прошли 12 Java/JNI fixtures на каждом ABI с Source compiled boot images,
ART, linker и Bionic. Fingerprint и normal boot сохранены, временные файлы
удалены; системные разделы и установленные VR-службы не заменялись.

Native commit: `1f40e20f880516fdb4926d26cd8dd69f7f972b67`.
Все 32 патча точно воспроизводят configured component commits от pinned
upstream. В исследованном графе 493 ARM64 ELF отсутствующих используемых
libgui symbols теперь **0**; отличий исследованных размеров vtable нет.
ARM32 runtime-граф ещё не исследован, поэтому его остаток не определён.
У SurfaceMonitor остаётся область из 40 factory bytes с неизвестным
назначением. Полный private C++ ABI и физическая смена частоты не доказаны.
Source MonitoredProducer не заявляет совпадение полного private layout;
factory connect/disconnect state и другие потребители dequeue telemetry
ещё требуют разбора. Невалидные конфигурационные входы имеют защитные
проверки Source; сравнения выполнены для default/valid конфигураций.
Свидетельства: `validation/surface-monitor-port.json`,
`validation/surface-monitor-abi.json`, `validation/libgui-abi.json` и
`validation/native-runtime-current.json`.

Далее остаются остальные необходимые PICO framework/JNI API, общий
системный образ с AOSP services/ART/графикой, его загрузка и аппаратные VR
сценарии. Чистая воспроизводимая сборка ещё должна перестать зависеть от
локальных отчётов и сохранённых приватных входов. GitHub remote пока
не подключён; изменения сохраняются локально.

## Предыдущая точка: EGL tracker и SurfaceClient

Патч 0031 переносит открытый `DebugEGLImageTracker` из фиксированного AOSP
QPR3 и связывает его с EGL image lifecycle в GLConsumer, RenderEngine и
diagnostic dump SurfaceFlinger. `SurfaceClient` восстановлен по PICO:
120 записей по 168 байт, четыре временные отметки, поиск последних восьми
кадров, ограничение имени 127 байт и кэширование ID вызывающего потока.
Зависимый `IPCThreadState::getCallingTid` выполняет OEM ioctl `0x8004621f`
с int32 reply, начальным нулём и возвратом -1 при ошибке. Новых полей
в IPCThreadState для этого вызова не добавляется.

Пакет `bufferqueue-test-30` прошёл на ARM64/ARM32: по 72 tracker, 22 frame
history и 8 caller-query сравнений с аутентифицированными заводскими ELF.
Проверены virtual methods, enabled/no-op modes, многопоточные счётчики,
возвращаемые адреса/байты записей, rollover и lookup window. Свойство, часы
и OEM query подменяются только внутри тестового процесса. Реальный remote
Binder caller query и аппаратный EGL lifecycle этим не квалифицированы.

Прежние 368 уникальных native gtests также прошли. Пакет
`framework-boot-image-test-13` с текущими GUI/Binder прошёл по 12 Java/JNI
fixtures на обоих ABI с compiled Source boot images, ART и Bionic.
Fingerprint/normal boot сохранены, временные файлы удалены; системные
разделы и установленный заводской VR-стек этим этапом не менялись.

Native commit: `925ecca90db6b8a45962b32946184b34fe1e6251`.
Все 31 патч точно воспроизводят configured component commits от pinned
upstream. В исследованном графе 493 ARM64 ELF остаются **5** отсутствующих
используемых libgui symbols, все из `SurfaceMonitor`. ARM32 runtime-граф
по-прежнему отсутствует; нулевой остаток для него не утверждается.
Полный private C++ ABI, реальный GPU/VR и дальнейший framework port остаются
открытыми. Свидетельства: `validation/frame-diagnostics-port.json`,
`validation/libgui-abi.json` и `validation/native-runtime-current.json`.

## Предыдущая точка: display flags, Source boot image, ART и Bionic

Патчи 0029/0030 переносят `SurfaceControl.setDisplayFlags` целиком по Source
цепочке Java/JNI → Transaction → DisplayState Parcel/merge → SurfaceFlinger
state → DisplayDevice. Все uint32 flags сохраняются; bit 20 вместе со свойством
`persist.sys.skip_single_layer` управляет single-layer путём. Layer creation
bit 20 включает producer-команду `-2`; virtual display получает согласованный
выбор two-sink buffers.

В производственную `doComposeSurfaces` подключён проверяемый helper ветки:
один буфер, usage nibble, multi-layer gate, attach и tracking. Повторный buffer
ID пропускает кадр. NO_INIT вызывает render/track fallback; другие ошибки и
usage 4/8 фиксируют sticky fallback, как в исследованном factory коде. Dequeue
перенесён к фактическому draw, чтобы успешный attach обходил RenderEngine.

Пакет `bufferqueue-test-29`: по **17 factory flags сравнений**, **14 новых SF
проверок** и **55 composition/display проверок** на ABI прошли. Пересечение
filters учтено: всего 368 уникальных native gtests на обоих ABI. Прежние
fence/freeze/cache/dequeue/JNI comparisons также прошли. Новый frame path
проверен с mocks и pipe fence; GPU/VR на глобально заменённом compositor,
весь private ABI и аппаратные сценарии ещё требуют квалификации.
Свидетельство: `validation/display-flags-port.json`.

После патчей 0029/0030 в ARM64 графе оставалось **11** используемых
отсутствующих символов: экспорт setDisplayFlags был устранён.

Патч 0028 переносит дополнительный лимит dequeue, обнаруженный при разборе
single-layer композиции. Команда `setMaxDequeuedBufferCount(-2)` включает
добавочный слот только для SurfaceFlinger producer. Отдельный private consumer
marker добавляет ещё два слота и ограничивает итог снизу единицей. Другие
запросы проходят обычные quota checks. Специальная команда принимается и
после abandon, как в factory; Source синхронизирует доступ к режиму mutex.

Пакет `bufferqueue-test-28`: **108 source/factory сравнений на каждом ABI**,
236 native-тестов и шесть сравнений actual JNI bridge на каждом ABI прошли.
Проверены обычные/SF producers, private consumer, повторный `-2`, отрицательные
и граничные int32 значения, abandon. Очереди локальные и используют padded
storage для factory objects; GraphicBuffer и GPU в новом probe не выделяются.
Full private C++ ABI и concurrency equivalence не доказаны.

Найдено глобальное условие `persist.sys.skip_single_layer`, default true;
factory сочетает его с display flag bit 20 и дополнительными layer conditions.
Source-вызовы этого режима и полная ветка композиции ещё не перенесены.
Свидетельства: `validation/dequeue-count-abi.json`, `validation/dequeue-count-port.json`.
На этапе патча 0028 оставалось 12 отсутствующих используемых ARM64 символов.

Пакет `framework-boot-image-test-12` содержит 468 Source файлов и 13 boot JAR.
На проверенном шлеме прошли **12 Java/JNI-проверок на ARM64 и 12 на ARM32**,
включая flags JNI values, static wrapper и null-token validation. Транзакции
остаются локальными; `apply` и работающий SurfaceFlinger не вызываются.
Source app_process запускается через Source linker с Source Bionic и ART;
проверены происхождение ключевых библиотек и все 22 отображения `.art`/`.oat`
на каждом ABI. Исполняется настоящий Java VirtualDisplay/Surface с полным
Source JNI и локальными fixture services. Прежняя проверка VM без boot image
сохранена отдельно в `validation/framework-runtime.json`.

Патч 0026 добавляет наблюдение отображённых image-файлов и библиотек.
Патч 0027 исправляет выбор физического DEX-файла при абсолютной логической
location: явно перенесённый bootclasspath теперь открывает Source JAR вместо
установленного factory JAR с другим порядком методов. Поведение относительных
location без совпадающего suffix сохранено. Временная ART-диагностика удалена.
Также перенесено распознавание `kryo300` из
[официального ART Android 10 GSI](https://android.googlesource.com/platform/art/+/refs/heads/android10-gsi/runtime/arch/arm64/instruction_set_features_arm64.cc)
без принудительного включения дополнительных ISA features. Предупреждение о
неизвестном CPU variant в окончательном запуске отсутствует.

Для частного процесса создан linker config с runtime/conscrypt/media и vendor
sphal namespaces; глобальная конфигурация загрузчика не менялась. GPU-рендеринг,
реальные Binder/freeze events, выполнение конкретных AOT entrypoints,
генерация JIT-кода и полный VR остаются открытыми. GraphicBuffer синтетические,
hidden API policy отключена для fixture reflection. Системные разделы не
менялись; fingerprint и normal boot сохранены, временный каталог удалён.
Свидетельство текущей runtime-проверки: `validation/framework-boot-image.json`.
На этапе 0029/0030 оставалось 11 используемых отсутствующих ARM64 символов.

## Предыдущая точка: Java VirtualDisplay без compiled boot image

Патч 0025 добавляет исполняемый Java/runtime probe. Пакет
`framework-runtime-test-06` содержит 13 Source boot JAR и 386 Source файлов.
На шлеме прошли **9 Java-проверок на ARM64 и 9 на ARM32**. Неизменённый Source
app_process регистрирует полный Source JNI и вызывает настоящий Java-код
VirtualDisplay/Surface на Source ART. Подтверждены происхождение libart,
libandroid_runtime и libgui, constructor и setter до slot recovery,
released/null handling, duplicate registration и detach.

Display/freeze services локальные, GraphicBuffer синтетические. VM работает
без compiled boot image; hidden API policy отключена для fixture reflection.
Source JIT сообщает о неподдерживаемом заводском ARM64 CPU variant `kryo300`;
генерация JIT-кода и Source boot image требуют отдельной квалификации.
Native fixture устанавливается только в data/nativetest; Java DEX не
устанавливается в system. Временный комплект удалён, normal boot и fingerprint
сохранены. Свидетельство: `validation/framework-runtime.json`.

Патч 0024 добавляет `Surface.registerFreezeSelf()` и JNI entry
`nativeFreezeSelfListening (J)V`. VirtualDisplay вызывает wrapper для non-null
Surface в constructor и после смены backing Surface, как в factory DEX.
Source сериализует wrapper с release через mLock; released/null native Surface
и Surface без producer игнорируются. JNI держит strong Surface reference и
вызывает проверенный local producer listener.

Пакет `bufferqueue-test-26`: шесть actual-source/factory JNI сравнений прошли
на ARM64 и ARM32, включая null handling, duplicate registration и переход от
JNI к slot recovery. Factory JNI body вызывается только после сверки SHA-256
установленной libandroid_runtime с pinned factory ELF. Проверены compiled
Java declarations, greylist, оба VirtualDisplay call sites и обе JNI tables.
Исполнение Java с новым boot classpath проверено пакетом runtime-test-06;
real freeze и полный VR ещё не квалифицированы.
GUI-библиотеки в пакете 26 совпали с проверенным пакетом 25; общий native suite
сохраняет 236 прошедших тестов. Системные разделы не изменялись.

Свидетельства нового моста: `validation/surface-freeze-port.json` и
`validation/surface-freeze-compiled.json`.

Патч 0023 переносит `BufferQueueProducer::listenFreezeSelf`, удаление self-key в destructor и восстановление слота после self-unfreeze. Если кадр уже был queued и число dequeued slots достигло лимита, pending event разрешает cancel одного последнего active slot с ненулевым dequeue count. Слот переносится в free buffers, fence очищается, событие потребляется. Успешный queueBuffer также очищает pending event. Source callback захватывает shared atomic flag; прямого доступа к уничтожаемому producer нет.

Пакет `bufferqueue-test-25` проверен на шлеме: **236 тестов**, включая по четыре ASan lifetime-теста действительного FreezeManager.cpp. Дополнительно совпали по 9 producer self-unfreeze, 10 frozen-reply, 15 freeze-registry, 12 freeze-wire, 10 cached-buffer, 12 producer-fence, 5 consumer-fence и 5 display-config сравнений с PICO на ARM64 и ARM32. Новый probe использует fake freeze service, локальные очереди и синтетические GraphicBuffer. Проверены virtual listener, PID filter, потребление события, последний из нескольких producer-slots, сохранение consumer-only slot, queue-success reset и destructor unregister. Отпечаток системы не изменился, временные файлы удалены.

В отдельном factory-only исследовании (`bufferqueue-test-24`) remote registration вызвала service registration и linkToDeath, но callbacks не доставлялись в девяти checkpoints на каждом ABI; у ARM64 root maps оставались пустыми. Заводская libgui импортирует только getInstance и self register/unregister. Remote API не заменяется выдуманной реализацией. Вызывающий Java/JNI код self-path перенесён патчем 0024; реальные process freeze, shared-buffer edge cases, GPU fences и полный private producer/core ABI не квалифицированы. В libgui остаются 12 используемых отсутствующих символов. Полный новый VR-образ ещё не квалифицирован; установленный preview остаётся прежним.

Свидетельства: `validation/native-runtime-current.json`, `validation/producer-unfreeze-port.json`, `validation/producer-unfreeze-abi.json`, `validation/freeze-remote-research.json`, `validation/frozen-reply-port.json`, `validation/frozen-reply-abi.json`, `validation/freeze-registry-port.json`, `validation/freeze-registry-abi.json`, `validation/freeze-wire-abi.json`, `validation/virtual-display-abi.json`.

## Установленный прототип

Гибридный preview 01 успешно загрузился. Пользователь подтвердил работу
домашнего VR-экрана, контроллеров и трекинга в игре. Заводской framework,
графические библиотеки, VR-службы, ядро и драйверы пока сохранены.
Из AOSP установлены servicemanager, дополнительные sh/toybox/logcat и DeskClock.

Текущий source-аудит: 12 используемых отсутствующих символов libgui в
исследованном ARM64 графе и 236 изолированных тестов. Новые графические
библиотеки пока не установлены в систему.

## Экспериментальные изменения в исходниках

База: AOSP `android-10.0.0_r47`. Локальные ветки: `codex/picomisu-vr`.

1. `frameworks/native`: патч `0001-pico-query-value-payload.patch` добавляет
   входное значение в Binder QUERY. Для частного запроса 10000 передаётся
   VR-статус, для стандартных запросов — ноль. Сервер также принимает обычные
   AOSP-запросы без дополнительного поля.
2. `frameworks/base`: патч `0002-pico-surface-vr-status-jni.patch` добавляет
   скрытый Java-метод `Surface.setPvrStatus(int)`, native `(JI)V` и регистрацию
   JNI. Вызов защищён существующей блокировкой Surface и проверкой освобождения.
   JNI передаёт статус producer через QUERY 10000 и, как заводской обработчик,
   не использует возвращаемое значение. `@UnsupportedAppUsage` сохраняет
   доступ к Java-методу для существующих клиентов через hidden API greylist.
3. `frameworks/native`: патч `0003-pico-bufferqueue-status-store.patch`
   добавляет защищённое mutex поле `mPicoVrStatus`, начальное значение 0
   и обработчик QUERY 10000. Входное int32 сохраняется и возвращается без
   преобразования. Проверки null/abandoned и стандартные запросы сохранены.
   Поле добавлено к структуре AOSP; бинарная совместимость её размещения
   с заводским BufferQueueCore не утверждается.
4. `frameworks/native`: патч `0004-pico-consumer-callback-buffer.patch`
   обрабатывает частную consumer-транзакцию 10000 с id и флагом журналирования.
   Отдельный marker сохраняет GraphicBuffer в callback для отмеченного
   consumer; локальная ссылка очищается после callback. Обычный consumer
   сохраняет поведение AOSP. Mutex защищает настройки, а очередь использует
   их снимок, сделанный под тем же mutex. Ожидание EGL fence не меняется.
5. `frameworks/native`: патч `0005-qpr3-discarded-buffer-notifications.patch`
   переносит связанную группу из AOSP QPR3: onBuffersDiscarded в Binder
   и hybrid proxy, независимый флаг onBufferReleased, уведомления очереди,
   SurfaceListener и очистку кэша Surface по индексам удалённых буферов.
   Существующий attachAndQueueBuffer сохранён; dataspace и damage-изменения
   QPR3 в этот этап не включены. Старые VR-патчи сохранены.
6. `frameworks/native`: патч `0006-pico-producer-release-fence.patch`
   добавляет четвёртый callback ProducerListener и Binder transaction 4:
   flattened Fence, uint64 buffer ID и bool. Bp и hybrid proxy передают
   сообщение с FLAG_ONEWAY; Bn проверяет интерфейс и ошибки чтения до callback.
   Default Bn callback пустой, как в factory. VirtualDisplayProducerListener
   хранит std::function перед mutex, синхронизирует установку и вызов обработчика
   и игнорирует его int-результат, как заводская реализация. Это перенос
   transport/listener; consumer fence-readiness и специальный detach-путь
   очереди ещё не включены.
7. `frameworks/native`: патч `0007-pico-consumer-fence-ready.patch`
   добавляет local-only notifyFenceReady, fence/ready flag слота и condition
   для ожидания producer. После совпадения buffer ID consumer будит producer;
   dequeue потребляет ready-fence и очищает состояние. Ожидание ограничено
   13,88 мс; служебный usage nibble отмечает успешное получение, timeout
   или пробуждение без ready. Режим также выбирает готовые свободные буферы.
   Буферы с factory usage nibble 1 освобождаются через detachBufferLocked,
   затем вне mutex вызывается fence callback с флагом false. ConsumerBase
   хранит последний успешно acquired slot; getLatchAcquireSlotLocked читает его.

Обоснование: исследованный заводской `libandroid_runtime.so` содержит JNI-запись
`nativeSetPvrStatus (JI)V`; обработчик вызывает `getIGraphicBufferProducer()`
и запрос 10000 с адресом входного int. Заводской Binder-сервер читает второе
поле int, а producer сохраняет VR-статус. Это подтверждает выбранный маршрут
передачи, но не все эффекты VR-статуса в графическом стеке.

Проверка сборки: `bash tools/build-vr-bridge.sh` собирает `framework`,
`libandroid_runtime`, `libgui`, с ограничением CPU 0–7 и `-j8`.
Эти экспериментальные изменения не включены в установленный preview.

Проверка 28 сентября 2026: сборка завершилась с кодом 0. Подтверждены
Java-сигнатуры `(I)V` и `(JI)V`, JNI-регистрация в ARM32/ARM64 и `greylist`
для публичного `setPvrStatus`. Контрольные суммы записаны в
`validation/surface-status.json`. Runtime-проверка этого моста ещё не выполнена.

BufferQueue проверен отдельно на шлеме: 6 тестов для ARM64 и 6 для ARM32
прошли с собранной AOSP libgui в изолированных процессах. Проверены signed
значения, независимость очередей, ошибки, стандартные queries, реальный
Bp/Bn-транспорт и старый QUERY без входного поля. Это не тест Java/JNI-моста
и не замена системной libgui. Временные библиотеки удалены после тестов.
Результат: `validation/bufferqueue-status.json`.

Следующая проверка consumer callback: 12 тестов на ARM64 и 12 на ARM32
прошли в изолированных процессах на шлеме. Дополнительно 102 варианта
сериализации BufferItem для каждого ABI совпали между заводской libgui
и AOSP. Проверены POD-поля и Region без GraphicBuffer/Fence descriptors
и без заполненных HDR metadata; полная совместимость всех содержимых
BufferItem этим не доказана. Результат: `validation/consumer-callback.json`.
Формат BufferItem на основе этих проверок не изменялся.

Группа onBuffersDiscarded проверена 22 тестами для каждого ABI (44 всего),
включая предыдущие BufferQueue/VR-regression тесты. Новые тесты проверяют
Binder vector, старые команды, malformed сообщения, release opt-out,
доставку GraphicBuffer в SurfaceListener, очистку кэша, проверку slot bounds
и безопасное поведение после уничтожения Surface. Графические буферы
в тестах пустые; GPU-выделение и реальные отрисованные кадры не проверялись.
Тесты выполнены из временной папки; firmware fingerprint и normal boot
сохранены, временные файлы удалены. См. `validation/discarded-buffers.json`.

Factory ARM64 libgui независимо подтверждает transaction 3 и Int32Vector
для onBuffersDiscarded. HIDL 1.0/2.0 не определяют такого события; их H2B
адаптеры сохраняют upstream default no-op, а обновлённый hybrid proxy
компилируется. Runtime-проверка события через настоящий HIDL сервис
не заявляется.

29 сентября проверен producer fence: сборка завершилась с кодом 0; 32 теста
на ARM64 и 32 на ARM32 прошли в изолированных процессах. Дополнительно один
и тот же probe выполнен с AOSP и заводской libgui: совпали 12 проверок для
каждого ABI, включая bytes восьми no-FD Binder-пакетов, команду/FLAG_ONEWAY,
64-битный buffer ID, bool, ручной пакет сервера, передачу FD и установку,
замену и очистку VirtualDisplay callback. Для FD использована pipe: это
проверяет transport/ownership, а не реальную GPU-синхронизацию. Bp/Hp→Bn
в этих тестах проходит через локальный BBinder relay; настоящий Binder IPC
между процессами ещё не проверен.

`inspect-producer-fence.py --compare-built` разбирает factory APS2/RELR
и mini debug symbols, проверяет пустой default fence callback и порядок
четырёх callback. Для шести классов совпали размеры vtable и primary prefixes
в обоих ABI. Этот аудит не доказывает весь libgui object layout. Наблюдаемые
поля VirtualDisplay listener дополнительно проверены выполнением factory
методов на объектах, созданных probe по новым заголовкам.
Результат — `validation/producer-fence.json`. Fingerprint и normal boot
сохранены, временные файлы удалены; новая libgui не установлена.
Legacy HIDL 1.0/2.0 не определяет fence-событие; H2B наследует default no-op.

Consumer/dequeue группа прошла 42 теста на ARM64 и 42 на ARM32, включая
предыдущие regression tests. Проверены ready consumption, stale buffer ID,
ошибочные аргументы, local-only default proxy, timeout, wake без ready,
асинхронный notify, сброс consumed state, callback без queue mutex и latch slot.
Consumer-attached буфер при первом dequeue возвращает положительный
BUFFER_NEEDS_REALLOCATION flag; это предусмотренное API поведение.

Одинаковый probe с AOSP и factory libgui дополнительно прошёл три проверки
на ABI: proxy не отправляет новую Binder-команду, ready-fence проходит через
dequeue вместе с pipe descriptor, special release detaches и вызывает callback.
Probe запрещает allocation и использует пустые GraphicBuffer с синтетическими
полями. Конструкторы вызываются из выбранной библиотеки в увеличенной heap
storage, чтобы не выделять factory private objects по source sizeof.
Проверка не включает GPU buffers, реальные sync fences или frame queue callbacks.

`inspect-consumer-fence.py` проверил vtable tail четырёх consumer классов
и идентичные machine-code getter bodies для latch slot в обоих ABI.
Результаты — `validation/consumer-fence.json` и `consumer-fence-abi.json`.
Source использует нормализованное относительное ожидание chrono вместо
factory realtime timespec; invalid arguments у local notify проверяются строже.
Полная битовая идентичность всех ошибок и таймерных краевых случаев не заявляется.
Установленная графика шлема сохраняется, временные тестовые файлы удалены.

Сборка тестов: `bash tools/build-vr-bridge.sh picomisu_bufferqueue_test`.
`package-bufferqueue-test.py` собирает отдельный набор библиотек, а
`run-bufferqueue-test.py` сверяет ранее записанную идентичность шлема,
проверяет SHA-256 загруженных файлов и удаляет только свою временную папку.

## Следующие зависимости

Патч 0016 добавляет Layer::notifyFenceReady, forwarding BufferQueueLayer и
BufferLayerConsumer. Fence добавляется к pending release только при совпадении
ID и слота; уведомление передаётся в IGraphicBufferConsumer. Поздний callback
после abandon безопасно игнорируется. Пять новых ASan tests прошли на каждом
ABI. Вместе с проверенными в пакете 15 неизменными артефактами результат —
196 тестов; исправленные ASan tests выполнены из пакета 16.
Сравнение SHA-256 подтвердило, что между пакетами поменялись только два
libsurfaceflinger_unittest. См. `validation/layer-fence-bridge.json`.
Следующий участок — сам реестр VirtualDisplaySurface и регистрация listener.

Актуальный checkpoint — пакет 14 / патч 0015. Прошли 186 тестов на шлеме:
54 BufferQueue/Surface и 39 RenderSurfaceTest на каждом ABI. Пять расширений
RenderSurface совпали с factory по полным символам и слотам; размеры трёх
interface vtable также совпали. Перенесены forwarding методы и factory
defaults с multi-layer=true. Далее нужен concrete VirtualDisplaySurface:
сохранение одного слоя, callback возврата fence, привязка buffer ID и слотов.
Production direct path ещё не включён, системные библиотеки не заменены.

Последний checkpoint — пакет 13, патч 0014: attachBuffer перенесён и прошёл
четыре новые source-проверки. Общий результат: 54 native-теста на каждом ABI
и 35 ARM64 RenderSurfaceTest; factory probes по-прежнему совпадают.
После запуска подтверждены normal boot, неизменный fingerprint и cleanup.
Следующий участок — setSingleLayer/multi-layer forwarding и конкретные
DisplaySurface callbacks. Системные библиотеки остаются заводскими.

Актуальный runtime checkpoint: пакет 12 выполнен на проверенном шлеме через
Wi-Fi ADB. Прошли 54 теста ARM64 и 54 ARM32, а также 31 ARM64 RenderSurfaceTest.
С factory совпали 12 producer-fence, 5 consumer-fence и 5 display-config
fixtures на каждый ABI. Fingerprint и normal boot сохранены, временные файлы
удалены. См. `validation/native-runtime-current.json`. Описанные ниже ожидания
подключения относятся к прежним пакетам: их новые тесты теперь покрыты этим
запуском. GPU fences, полный compositor ABI и системная установка не проверены.

Патч 0013 переносит flipClientTarget и выбор FD -1 при queue/cancel в этом
режиме. Три новых теста проверяют обход HWC decision, обработку ошибки и
возврат в обычный режим. Методы attachBuffer/setSingleLayer и конкретный
DisplaySurface путь всё ещё требуют переноса; production frame path пока
не переключён на этот режим.

Патч 0012 добавляет отдельный Surface по цепочке NativeWindowSurface →
SurfaceFlinger → DisplayDevice → RenderSurfaceCreationArgs → RenderSurface.
Фабрика возвращает принадлежащий ей Surface; для mock ANativeWindow указатель
может отсутствовать. Приведение произвольного ANativeWindow к Surface не используется.
Сборка libsurfaceflinger, libsurfaceflinger_unittest и libcompositionengine_test
прошла. Добавлены две проверки создания; весь RenderSurfaceTest включает 28 тестов.
Пакет `bufferqueue-test-11` содержит 129 файлов и поддерживает изолированный
запуск этой ARM64 suite с `--render-surface-tests`, вместе с прежними 54 тестами
на ABI и probes. Шлем не обнаружен, запуск остановился до push.
Прямой путь композиции ещё не включён; layout RenderSurface с PICO целиком
не совпадает. Следующий этап — связанные методы и поля прямого пути.

Последняя исходная группа — патч 0011 Surface dataspace. Сборка ARM64/ARM32
прошла; проверка серии патчей воспроизводит native commit. Текущий общий аудит:
12 отсутствующих используемых ARM64 символов, 8 отличий размера vtable на ABI.
Пакет `bufferqueue-test-10` ожидает 54 теста на ABI и сравнительные probes.
Запуск остановлен до загрузки файлов: проверенный шлем недоступен по ADB.
Последний подтверждённый runtime-результат остаётся 42 теста на ABI.
Охват и границы новых проверок описаны в `GFX-ABI.md`.

Патч 0009 переносит ConfigChanged из QPR3: конструктор DisplayEventReceiver,
ISurfaceComposer proxy/stub, передачу параметра через SurfaceFlinger/Scheduler
и фильтр событий EventThread. Существующий r47 resync callback сохранён.
Перенесены QPR3 EventThread tests, включая suppressConfigChanged, и обновлены
затронутые mocks. ARM64 factory proxy использует команду 4, flags 0 и два
int32 после interface token; запись контракта — `validation/display-config-plan.json`.
Исходники воспроизводятся серией патчей. Компиляция framework, JNI, libgui,
libsurfaceflinger и libsurfaceflinger_unittest завершилась с кодом 0.
ARM32 proxy также проверен статически в Thumb: команда 4, flags 0, два int32.
В общем аудите осталось 13 отсутствующих используемых ARM64 символов и
8 отличий размера vtable на ABI. Выполнение unit-тестов, сравнительный
runtime wire-probe и проверка всего ABI остаются открытыми. Новые компоненты
не установлены на шлем.

- Проследить дальнейшие эффекты статуса. В исследованной ARM64 libgui
  найдены прямые записи по идентифицированному смещению в конструкторе
  и producer query; прямых чтений по этому смещению в libgui/SurfaceFlinger
  не найдено. Косвенный доступ не исключён. Перенос значения в BufferItem
  пока не добавляется, поскольку такое поведение ещё не доказано.
- Проверить Java-поведение OEM-метода и вызовы из заводских клиентов на устройстве.
- Перенести необходимые дополнительные графические интерфейсы. Аудит
  493 исследованных заводских ARM64 ELF выявил 21 отсутствующий импорт
  libgui у 10 библиотек и 28 отличий размеров экспортируемых vtable.
  Среди отсутствующих callbacks — IProducerListener, используемые камерой
  трекинга. Данные о runtime-клиентах ARM32 в исходном графе отсутствуют;
  сравнение экспортов ARM32 выполнено отдельно. См. `GFX-ABI.md`.
  После группы onBuffersDiscarded отсутствующих используемых символов
  осталось 19: устранены BnProducerListener::onBuffersDiscarded и Surface
  connect с SurfaceListener. Размер Surface vtable совпал с заводским;
  это не доказывает порядок всех методов и полный object layout.
  После producer fence осталось 15 используемых отсутствующих символов,
  а отличий размеров vtable — 17 в каждом ABI. Устранены Bn fence callback,
  VirtualDisplay setCallback, VTT и vtable. Охват ARM64 графа остался 493 ELF;
  отсутствие ARM32 runtime-графа сохраняется.
- Consumer/dequeue ready-handshake и special release перенесены. Текущий
  аудит оставляет 14 отсутствующих используемых символов и 12 отличий размера
  vtable в каждом ABI; устранён getLatchAcquireSlotLocked. Размеры четырёх
  consumer vtable совпали, но весь object layout и методный порядок не доказаны.
- Fence callback с флагом true при замене queued буфера с usage nibble 1
  реализован в рабочем дереве и собран. Новые runtime-проверки ещё не выполнены:
  ADB не видит шлем. Последний подтверждённый результат остаётся 84 теста.
- Патч 0008 исправляет виртуальный getter и поля ConsumerBase, добавляет
  fallback callback. Сборка и строгая проверка шести vtable прошли в обоих ABI;
  runtime остаётся непроверенным. Общий аудит: 14 отсутствующих используемых
  ARM64 символов, 8 отличий размера vtable на ABI. См. `GFX-ABI.md`.
- onDisconnect уже присутствует в pinned AOSP, включая Binder-команду 1.
  Отдельный перенос этого метода не нужен. Порядок callback проверен
  `inspect-consumer-listener.py`; после патча 0008 проверка
  `--require-layout-match` проходит. Это не доказательство всего libgui ABI.
- Сравнение открытых доноров libgui завершено: пять необходимых API найдены
  в AOSP QPR3, а Qualcomm Q дополнительно содержит VpsExtension. Для переноса
  используем эти фиксированные доноры; текущий tag всей сборки пока сохраняется.
  Подробности, ревизии и границы проверки — `NATIVE-DONORS.md`.
- Перенести остальные требуемые JNI/Java-интерфейсы; один добавленный метод
  не делает AOSP framework совместимым со всем VR-стеком PICO.
- Только после совместной проверки зависимостей готовить следующий образ.

Новые ключи не создаются. Заводские подписи компонентов и текущие тестовые
AVB-ключи пока сохраняются по решению пользователя. Системные разделы шлема
этим этапом не меняются.
