# Открытые доноры для недостающих framework API

Сравнение показывает, для каких недостающих Java API заводской PICO OS 5.13.7
есть открытый исходник с тем же DEX-дескриптором. Входные данные —
`validation/api-consumers.json`: 376 кандидатов `needed` и отдельно
647 `needed_by_preserved_factory_component`. Для каждого кандидата в
`validation/api-donor-coverage.json` записаны найденные совпадения с
ревизией и путём, качество совпадения и решение из api-consumers.

Совпадение декларации не означает готовности порта. Оно показывает, что есть
исходник для переноса. Поведение, Binder transaction codes, parcel layout
и JNI при переносе проверяются отдельно.

## Проверенные источники

| Донор | Репозиторий | Фиксированная ревизия |
|---|---|---|
| `qualcomm_q` | CodeLinaro frameworks/base, tag `LA.UM.8.12.c3-64900-sm8250.0` | `4eb3b752040390816158621041879b4bcc171324` |
| | CodeLinaro system/bt, тот же tag | `336e28a2e9f58222b4c3a57050d3c180c3c81d39` |
| `aosp_11_r48` | AOSP frameworks/base `android-11.0.0_r48` | `1d9b9ab57d844b18b3b1b4297725141e7788109b` |
| | AOSP system/bt `android-11.0.0_r48` | `30098cc2b2fc751f76018ba9e013a86cb883fbd3` |
| `aosp_12.1_r27` | AOSP frameworks/base `android-12.1.0_r27` | `8fbdc326cfd7bb7f2b617f31802c733f56014491` |
| | AOSP system/bt `android-12.1.0_r27` | `e140c133342a5dd2cf201c01ef39c3baab86c386` |
| | AOSP frameworks/av `android-12.1.0_r27` (только справочно) | `ae5c3b1fe0c949fde91c585e00876dac8e32edfd` |
| `smartisan_m` | SmartisanTech/android_frameworks_base, `smartisan-m` | `b7565cbac901f563beed63522bd66ea3b1b0418a` |
| `smartisan_m_onestep` | та же, `smartisan-m-onestep_bigboom` | `51497c830b171d5bc63abdaf54da0d1c217c029c` |
| `pico_sdk` | 119 репозиториев Pico-Developer и picoxr, HEAD ветки по умолчанию | commit каждого репозитория в JSON |
| Контроль | AOSP frameworks/base `android-10.0.0_r47` | `dff3deab5d25f8bbfd49abfb423043c9be47b7db` |
| | AOSP system/bt `android-10.0.0_r47` | `3fd0365a822ca165ad6cd1cba57966c94c7c8a91` |

Теги Android 10 QSSI (`LA.QSSI.10.*`) для frameworks/base на CodeLinaro
отсутствуют: в репозитории есть QSSI-ветки начиная с 11.0. Поэтому
использована линия LA.UM.8.12.c3 (sm8250, Android 10), та же семья, что
и для native-доноров в [NATIVE-DONORS.md](NATIVE-DONORS.md). Последний
tag этой линии, `LA.UM.8.12.c3-77400-sm8250.0`, указывает на тот же commit
frameworks/base, что и c3-64900.

`system/bt` добавлен к frameworks/base потому, что в Android 10–12
AIDL `android.bluetooth` (IBluetooth*, IBluetoothDun) находится в
`system/bt/binder`, а не в frameworks/base.

Контроль r47 не является донором. Он показывает, есть ли дескриптор уже
в базовом AOSP 10.

## Метод

- Java-исходники разбираются в объявления: классы, включая вложенные,
  поля, методы и конструкторы. Тела методов пропускаются.
- Каждый тип параметра, возвращаемого значения и поля переводится в
  DEX-дескриптор. Учитываются package, imports, вложенные и унаследованные
  member types, индекс классов всего дерева донора и стирание generics.
  Добавляются неявные параметры конструкторов inner-классов и enum.
- Для AIDL-интерфейсов создаются классы, которые генерирует компилятор AIDL:
  `I`, `I$Stub`, `I$Stub$Proxy`, `I$Default`.
- Из PICO SDK читаются class-файлы в JAR/AAR. Сравниваются точные
  дескрипторы определений и call sites клиентского кода.
- Качество `exact` — совпадает двоичное имя класса или имя члена вместе
  с полным дескриптором. Член может быть унаследован от супертипа
  в доноре.
- Качество `name-only` — совпадает только простое имя класса в другом
  пакете либо имя члена при другом дескрипторе. Сюда же относятся
  сгенерированные компилятором классы (`$1`, лямбды), если в доноре есть
  внешний класс. Такие классы никогда не считаются `exact`.

Самопроверка парсера: для классов, общих с заводскими framework.jar и
services.jar, парсер воспроизводит 99,87 % (209374 из 209647) заводских дескрипторов
членов в контроле r47 и 99,96 % (212088 из 212175) в Qualcomm Q. Сравниваются только члены,
имя которых есть в доноре. Остаток — в основном реальные изменения PICO
(например, `Debug.getPss(I[J[J[J)J`), а не ошибки разбора.

## Итог: needed (376)

- `exact`: **113 из 376 (30,1 %)**; `name-only`: 6;
  не найдено: 257.
- Без 32 сгенерированных компилятором классов: 113 из
  344 (32,8 %).
- По видам: методы — 76 из 98, поля — 10 из
  19, классы — 27 из 259.
- По донорам (`exact`): Qualcomm Q — 106, AOSP 11 — 26,
  AOSP 12.1 — 21, PICO SDK — 6, Smartisan M — 0.
  Только Qualcomm Q даёт 81 кандидат. Qualcomm Q и AOSP 11/12 вместе — 25.
  Только AOSP — 1 (`FileSystemProvider.onDocIdDeleted`). Только SDK — 6.
- Ни один из 113 `exact` не объявлен в контроле AOSP 10 r47. Это
  действительно новый для базы API.

Что закрывают доноры:

- Qualcomm Q: Bluetooth (`BluetoothDun`, `BluetoothQualityReport`, TWS+,
  socket options, `IBluetooth*` из system/bt, расширения
  `ScanFilter`/`AdvertiseData`), Wi-Fi (`IWifiManager`/`WifiManager`
  `*2`-методы и feature-переключатели, `WifiInfo` Wi-Fi generation/8ss,
  `WifiEnterpriseConfig` SIM number), `BoostFramework` и вложенные
  классы, `AudioManager/IAudioService.handleBluetoothA2dpActiveDeviceChange`
  с 5 параметрами, `TelephonyManager/ITelephony.getMergedSubscriberIdsFromGroup`,
  `LockPatternUtils/ILockSettings.sanitizePassword`.
- AOSP 11 и Qualcomm Q: content capture и `mPrivateFlags4` в `View`, `FaceManager`/`IFaceService` enroll/get/setFeature
  с новыми сигнатурами, `BluetoothCodecConfig` helpers,
  `UiModeManager.setNightModeActivated`,
  `SubscriptionManager/ISub.getActiveDataSubscriptionId`.
  В AOSP 12.1 сигнатуры `IFaceService` уже другие.
- PICO SDK: копии AIDL `com.pvr.IPvrManagerService` и `IPvrCallback`
  (интерфейс, `$Stub`, `$Stub$Proxy`) в 65 репозиториях. `$Default` в них
  нет, это более старый AIDL-компилятор.

Покрытие по группам (needed):

| JAR | Группа | Всего | exact | name-only | нет | Доля exact |
|---|---|---:|---:|---:|---:|---:|
| framework | `android.app` | 101 | 2 | 0 | 99 | 2 % |
| framework | `android.bluetooth` | 38 | 35 | 3 | 0 | 92 % |
| framework | `android.bluetooth.le` | 14 | 10 | 0 | 4 | 71 % |
| framework | `android.content.pm` | 12 | 0 | 0 | 12 | 0 % |
| framework | `android.hardware.face` | 6 | 6 | 0 | 0 | 100 % |
| framework | `android.hardware.usb` | 2 | 0 | 0 | 2 | 0 % |
| framework | `android.media` | 10 | 2 | 0 | 8 | 20 % |
| framework | `android.media.projection` | 1 | 0 | 0 | 1 | 0 % |
| framework | `android.net` | 4 | 0 | 0 | 4 | 0 % |
| framework | `android.net.wifi` | 35 | 34 | 0 | 1 | 97 % |
| framework | `android.os` | 12 | 0 | 0 | 12 | 0 % |
| framework | `android.pico.utils` | 2 | 0 | 0 | 2 | 0 % |
| framework | `android.telephony` | 2 | 2 | 0 | 0 | 100 % |
| framework | `android.util` | 9 | 5 | 0 | 4 | 56 % |
| framework | `android.view` | 6 | 6 | 0 | 0 | 100 % |
| framework | `com.android.internal.app` | 4 | 0 | 0 | 4 | 0 % |
| framework | `com.android.internal.content` | 1 | 1 | 0 | 0 | 100 % |
| framework | `com.android.internal.os` | 2 | 0 | 0 | 2 | 0 % |
| framework | `com.android.internal.policy` | 12 | 0 | 0 | 12 | 0 % |
| framework | `com.android.internal.telephony` | 2 | 2 | 0 | 0 | 100 % |
| framework | `com.android.internal.widget` | 2 | 2 | 0 | 0 | 100 % |
| framework | `com.android.server` | 1 | 0 | 0 | 1 | 0 % |
| framework | `com.pico.api.app` | 10 | 0 | 0 | 10 | 0 % |
| framework | `com.pico.api.os` | 3 | 0 | 0 | 3 | 0 % |
| framework | `com.pvr` | 16 | 6 | 0 | 10 | 38 % |
| framework | `com.pvr.configuration` | 4 | 0 | 0 | 4 | 0 % |
| framework | `com.pxr.bluetooth` | 10 | 0 | 0 | 10 | 0 % |
| framework | `com.pxr.net` | 28 | 0 | 0 | 28 | 0 % |
| framework | `com.pxr.net.common.log` | 1 | 0 | 1 | 0 | 0 % |
| framework | `com.pxr.net.common.score` | 1 | 0 | 0 | 1 | 0 % |
| framework | `com.pxr.net.common.utils` | 1 | 0 | 1 | 0 | 0 % |
| framework | `com.pxr.net.common.wifi` | 7 | 0 | 0 | 7 | 0 % |
| framework | `com.pxr.net.util` | 5 | 0 | 1 | 4 | 0 % |
| framework | `com.pxr.pxrapi` | 4 | 0 | 0 | 4 | 0 % |
| framework | `smartisanos.config` | 1 | 0 | 0 | 1 | 0 % |
| framework | `smartisanos.util` | 1 | 0 | 0 | 1 | 0 % |
| services | `com.pvr.pxrnotification.aidl` | 6 | 0 | 0 | 6 | 0 % |
| | **Итого** | **376** | **113** | **6** | **257** | **30 %** |

## Итог: needed_by_preserved_factory_component (647)

Эти кандидаты нужны только если заводские JAR (`sys-*`, `sysmonitor-*`,
`vrex-*`, `devicemiddlewareimpl`, Qualcomm boot JAR) сохраняются вместо
переноса.

- `exact`: **20 из 647 (3,1 %)**; `name-only`: 9;
  не найдено: 618.
- Без 172 сгенерированных компилятором классов: 20 из
  475 (4,2 %).
- 13 из 20 уже есть в контроле r47. Это 13 кандидатов
  `*_visibility`, для которых PICO только расширила доступ. В донорах эти
  члены в основном `private` или package-private. `public` есть только в
  Qualcomm Q, для 5 из 13.
- Новый API с донором — 7:
  - `ActivityTriggerService` и два вложенных класса (Qualcomm);
  - `ActivityManagerService.mStackSupervisor` (Qualcomm);
  - `ActivityManagerService.startActivityAsUserEmpty(Bundle)` (Qualcomm);
  - `UidRecord.procRecords` (AOSP 11);
  - `BatteryStatsImpl.isScreenOn()Z` (Smartisan M).
- Практически весь слой `*SmtBase`, `*SmtEx`, `*OptEx`, `*MonitorEx`,
  `Ext*Impl`, `IExt*`, `smartisanos.*`, `com.android.server.api`,
  freezer/prefetch/sysmonitor не имеет открытого донора. Это касается
  и публичного Smartisan M: там совпадают только имена отдельных
  AOSP-классов (`RemoteCallback`), но не Smt-расширения.

Покрытие по группам (needed_by_preserved_factory_component):

| JAR | Группа | Всего | exact | name-only | нет | Доля exact |
|---|---|---:|---:|---:|---:|---:|
| framework | `android.app` | 25 | 0 | 0 | 25 | 0 % |
| framework | `android.app.doppelganger` | 1 | 0 | 0 | 1 | 0 % |
| framework | `android.app.job` | 4 | 0 | 0 | 4 | 0 % |
| framework | `android.content` | 3 | 0 | 0 | 3 | 0 % |
| framework | `android.content.pm` | 16 | 0 | 0 | 16 | 0 % |
| framework | `android.content.res` | 3 | 0 | 0 | 3 | 0 % |
| framework | `android.dvr` | 4 | 0 | 0 | 4 | 0 % |
| framework | `android.media` | 5 | 0 | 0 | 5 | 0 % |
| framework | `android.net` | 2 | 0 | 0 | 2 | 0 % |
| framework | `android.os` | 37 | 0 | 1 | 36 | 0 % |
| framework | `android.pc` | 4 | 0 | 0 | 4 | 0 % |
| framework | `android.util` | 4 | 0 | 0 | 4 | 0 % |
| framework | `android.view` | 15 | 0 | 0 | 15 | 0 % |
| framework | `android.widget` | 1 | 0 | 0 | 1 | 0 % |
| framework | `com.android.internal.app` | 11 | 0 | 0 | 11 | 0 % |
| framework | `com.android.internal.app.procstats` | 4 | 0 | 0 | 4 | 0 % |
| framework | `com.android.internal.os` | 11 | 3 | 1 | 7 | 27 % |
| framework | `com.android.internal.util` | 4 | 0 | 0 | 4 | 0 % |
| framework | `smartisanos.api` | 2 | 0 | 0 | 2 | 0 % |
| framework | `smartisanos.os` | 19 | 0 | 2 | 17 | 0 % |
| framework | `smartisanos.tnt` | 2 | 0 | 0 | 2 | 0 % |
| framework | `smartisanos.util` | 2 | 0 | 0 | 2 | 0 % |
| services | `com.android.server` | 132 | 3 | 0 | 129 | 2 % |
| services | `com.android.server.am` | 148 | 5 | 5 | 138 | 3 % |
| services | `com.android.server.api` | 34 | 0 | 0 | 34 | 0 % |
| services | `com.android.server.audio` | 1 | 0 | 0 | 1 | 0 % |
| services | `com.android.server.display` | 2 | 0 | 0 | 2 | 0 % |
| services | `com.android.server.inputmethod` | 1 | 1 | 0 | 0 | 100 % |
| services | `com.android.server.job` | 4 | 0 | 0 | 4 | 0 % |
| services | `com.android.server.job.controllers` | 4 | 0 | 0 | 4 | 0 % |
| services | `com.android.server.lights` | 2 | 0 | 0 | 2 | 0 % |
| services | `com.android.server.location` | 1 | 0 | 0 | 1 | 0 % |
| services | `com.android.server.net` | 1 | 0 | 0 | 1 | 0 % |
| services | `com.android.server.notification` | 1 | 0 | 0 | 1 | 0 % |
| services | `com.android.server.pm` | 14 | 0 | 0 | 14 | 0 % |
| services | `com.android.server.policy` | 3 | 0 | 0 | 3 | 0 % |
| services | `com.android.server.power` | 9 | 0 | 0 | 9 | 0 % |
| services | `com.android.server.wm` | 111 | 8 | 0 | 103 | 7 % |
| | **Итого** | **647** | **20** | **9** | **618** | **3 %** |

## Пробелы без донора

Для needed нет ни `exact`, ни `name-only` ни в одном источнике:

- SysMonitor/Smartisan-слой в `android.app`: `FreezeManager`,
  `IFreezeManager`, `IUnFreezeCallback`, prefetch (`IPrefetch*`,
  `PrefetchInfo`), `SceneInfoManager`, `ISysClient`, `IMemClient`,
  `ActivityManagerSmtBase`, `IActivityManagerSmtEx`,
  `ActivityManager.keepAliveBackground` и
  `IActivityManager.keepProcessAliveBackground`;
- расширения `ApplicationInfo`/`ActivityInfo` (`mExt`, `mSmtEx`,
  `IExt*Info`, `Ext*InfoImpl`, `appInfoJsonConfig`),
  `ConnectivityManagerSmtEx`, `NetworkCapabilitiesSmtEx`, `DebugSmtEx`,
  `BoostFrameworkSmtBase`, `SmtSysLog`, `smartisanos.config.ProductConfig`,
  `smartisanos.util.FeatLog`;
- PICO: `android.pico.utils.Features`/`PicoUtils`, `com.pico.api.*`
  (`IApiLayer`, `IAppSession`, `RemoteCallbackProxy`), `com.pxr.net.*`
  (сетевой менеджер и Wi-Fi-классы, кроме совпадений по имени),
  `com.pxr.bluetooth.*`, `com.pvr.configuration.IConfigServiceInterface`,
  `com.pvr.ISysDataSyncService`, `IPvrCallbackNative`,
  `com.pvr.pxrnotification.aidl.*`, `com.pxr.pxrapi.IScreenCaptureInterface`,
  `SysDataSyncServiceManager`;
- медиа: `PlayerSpatialHelper`/`PlayerSpatialHelperImpl`,
  `PlayerBase.mSpatialHelper/getSpatialHelper`,
  `MediaMetadataRetriever.getVRType/_getVRType`,
  `AudioManager/IAudioService.setRecordSilenced`,
  `MediaProjectionManager.createMediaProjection()`;
- система: `Binder.getLastFrozenPid`, `Build.getInfoFromSN`/`getModel`/
  `getSerialFromFile`, `PowerManager/IPowerManager.setSensorControlScreenFeatureState`,
  `PowerManager.mAppToken`, `IPowerAdvisor`, `UsbManager/IUsbManager.startAccessory`,
  `WifiConfiguration.needLogin`, `IBluetoothLeCallback`;
- `com.android.internal.policy.IKeyguard*VerifyCallback`,
  `ITransferServer`, `IBatteryStats*OptEx`.

Эти API нужно восстанавливать по заводским DEX и поведению PICO,
как это уже делалось для native-частей.

## Смежные области доноров вне needed

Для справки тот же разбор выполнен для 5421 кандидата `not_needed`:
`exact` — 2157 (39,8 %), из них Qualcomm Q — 1926,
AOSP 11/12.1 — 1043. Отдельные совпадения в JSON не записаны,
только сводка.

- Spatializer. AOSP 12.1 frameworks/base точно объявляет 128 из 210
  связанных `not_needed`-кандидатов. Среди них AudioService/IAudioService
  spatializer API и `canBeSpatialized`. frameworks/av 12.1 содержит
  `AudioSystem::getSpatializer`, `canBeSpatialized`, `ISpatializer.aidl` и
  audiopolicy `Spatializer`. PICO-специфичный `PlayerSpatialHelper`
  (needed) там отсутствует.
- DisplayEventReceiver `nativeInit(WeakReference, MessageQueue, II)` и
  конструктор `(Looper, II)`: `exact` в Qualcomm Q и AOSP 11. Все
  четыре кандидата — `not_needed`.
- Freezer. AOSP 11 содержит `CachedAppOptimizer`,
  `Process.setProcessFrozen` и `enableFreezer`. PICO-кандидаты
  (`Binder.setPidFreeze*`, `getLastFrozenPid`,
  `Process.setProcessFreezeGroup`, `useCGroupFreeze`, `FreezeManager`)
  имеют другие имена и сигнатуры. Из 32 кандидатов needed/preserved с
  `Freez` в имени ни один не найден ни в одном доноре. AOSP 11 может служить образцом механизма, но не
  источником этого API.
- QTI-классы `ActivityTrigger`, `SeempLog`, Camera histogram и longshot
  найдены в Qualcomm Q, но все, кроме `ActivityTriggerService`, —
  `not_needed`.

## Проверка PICO AIDL по SDK

Сравнивались заводской framework.jar и копии AIDL в SDK.

- `com.pvr.IPvrManagerService`: в заводском интерфейсе 20 методов, в
  SDK-копии 16, общих 15. Метод `updateUserSettings(Ljava/lang/String;)V`
  есть только в SDK-копии: заводской вариант — `(Ljava/lang/String;Z)V`.
  В одном репозитории (`picoxr/Broadcast`) клиентский код вызывает
  отсутствующую в заводском интерфейсе перегрузку. Остальные 15 вызываемых
  SDK методов есть в заводском интерфейсе.
- `com.pvr.IPvrCallback`: единственный метод
  `onEventChanged(Landroid/os/Bundle;)V` совпадает.
- Для `com.pico.api.app.*`, `com.pxr.*`, `IConfigServiceInterface`,
  `ISysDataSyncService`, `IPxrNotification*` в опубликованных SDK нет
  ни копий AIDL, ни вызовов.
- Transaction codes и порядок методов не сравнивались.

## Ограничения

- Это разбор объявлений, а не компиляция. Типы, которые индекс донора
  не разрешил, оставляют перегрузку в `name-only`. В текущем прогоне
  таких совпадений нет.
- Читаются только `.java`/`.aidl` вне `tests/` в frameworks/base
  (и system/bt). Сгенерированные при сборке исходники и другие проекты
  (frameworks/opt/*, packages/modules/*, vendor/qcom-opensource, закрытые
  сервисы Smartisan) в донорах отсутствуют. Это прежде всего влияет на
  `com.pxr.net`, `com.pico.api` и Smartisan-слой.
- Публичный Smartisan frameworks_base относится к Android 6. В нём нет
  Smt-расширений, появившихся в PICO OS. `exact` там — 2 кандидата, из них
  новый API — один (`BatteryStatsImpl.isScreenOn()Z`).
- PICO SDK зафиксирован на HEAD ветки по умолчанию на момент загрузки.
  30 файлов SDK не удалось получить. Kotlin-исходники не разбирались.
- `name-only` для сгенерированных компилятором классов не доказывает
  совпадения номеров `$N` или лямбд.
- frameworks/av использован только для текстовых маркеров Spatializer.
  В покрытие он не входит.
- Совпадение дескриптора не доказывает одинаковое поведение, коды
  Binder-транзакций или parcel layout.

## Повторение

Доноры лежат в отдельных bare-кэшах на ext4-томе исследований:
`analysis/framework-reference/` (`caf-base.git`, `caf-bt.git`,
`aosp-base.git`, `aosp-bt.git`, `aosp-av.git`, `smartisan-base.git`,
`pico-sdk/*.git`). Ревизии закреплены в `refs/research/*`.

Кэши созданы так: `git fetch --depth 1 --filter=blob:none` для
фиксированного tag или ветки. Затем догружены только blob-файлы
`.java`/`.aidl` (для SDK — ещё `.jar`/`.aar`/`.kt`) командой
`git fetch --filter=blob:none origin --stdin`. Рабочие деревья и
`source/` не затрагивались.

Запуск: `taskset -c 0-7 python3 tools/compare-framework-donors.py` в WSL.
Скрипт проверяет UUID тома, сам ничего не загружает и не вызывает
lazy fetch. Разбор кэшируется в `analysis/framework-reference/parsed-*.pickle`.
Результат — `validation/api-donor-coverage.json`.
