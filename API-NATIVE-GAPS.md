# Picomisu: native API кандидаты, ещё отсутствующие в сравниваемых JAR

Снимок 29 сентября 2026 года, кодовая точка `3c509b0` / 33 патча.

Ниже весь native declaration остаток из проверенного сравнения двух JAR:
76 в framework.jar и 6 в services.jar. Это кандидаты для проверки потребителей,
а не 82 доказанно обязательных VR функции. JNI implementation/registration,
classpath relocation и необходимость для загрузки проверяются отдельно.

Полные class/method/field/access differences: [API-GAPS.json](API-GAPS.json).
План работ и статусы: [REMAINING-WORK.md](REMAINING-WORK.md).

Статус на 30 сентября 2026 года (0124): 9 кандидатов с внешними потребителями перенесены —
`MediaMetadataRetriever._getVRType`, семь `PlayerSpatialHelperImpl` и ранее `Binder.getLastFrozenPid`;
также `ZygoteInit.systemServerMmap/runtimeMmap`, `ActivityThread.nSetSwitchState`,
`ActivityThreadSmtBase.initPrefetch/onPrefetchRealStart`, `Debug.getTimeByQtimer/getMemInfoFast`
(см. `validation/native-parity-port.json`, `validation/smartisan-layer-port.json`). Список ниже — исходный снимок.

## framework.jar — 76

### android.app.ActivityThread

- `nSetSwitchState(II)V`
- `nSysHookInit()V`

### android.app.ActivityThreadSmtBase

- `initPrefetch(Z)V`
- `onPrefetchRealStart(Z)V`

### android.graphics.HardwareRenderer

- `nDoAnimation(JJ)V`
- `nNotifyMonitorStatsChanged(JZ)V`

### android.graphics.SurfaceTexture

- `nativeGetName()Ljava/lang/String;`
- `nativeUpdateTexImageExt()I`

### android.hardware.Camera

- `_getNumberOfCameras()I`
- `native_sendHistogramData()V`
- `native_sendMetaData()V`
- `native_setHistogramMode(Z)V`
- `native_setLongshot(Z)V`
- `native_setMetadataCb(Z)V`

### android.media.AudioSystem

- `canBeSpatialized(Landroid/media/AudioAttributes;Landroid/media/AudioFormat;[Landroid/media/AudioDeviceAttributes;)Z`
- `nativeGetSpatializer(Landroid/media/INativeSpatializerCallback;)Landroid/os/IBinder;`
- `native_register_track_state_callback()V`
- `setRecordSilenced(Ljava/lang/String;Z)I`

### android.media.MediaMetadataRetriever

- `_getVRType(I)I`

### android.media.PlayerSpatialHelperImpl

- `nativeIsSpatializationEnabled()Z`
- `nativeRelease()V`
- `nativeSetAudioOrientation(FFFF)I`
- `nativeSetAudioPose(FFFFFFF)I`
- `nativeSetSessionId(I)V`
- `nativeSetSpatializationEnabled(Z)I`
- `nativeSetup(Ljava/lang/Object;)V`

### android.media.SpatialCoordConverter

- `convertAudioOrientation(FFFFFF[F)I`
- `convertRelativeAudioOrientation(FFFFFFFFFFFF[F)I`
- `release()V`
- `setAdditionalCameraOrientation(FFFFFF)I`
- `setCoordinateTransform([F)I`
- `setup()V`

### android.os.Binder

- `getBinderClientPids(I)[I`
- `getBinderServerPids(I)[I`
- `getCallingTid()I`
- `getLastFrozenPid()I`
- `getTargetCalleePid(II)I`
- `setBinderCtlMask(I)V`
- `setPidFreeze(IZ)I`
- `setPidFreezeWithMode(IZI)I`

### android.os.Debug

- `getAllProcsMeminfoFast(Ljava/lang/String;Ljava/util/ArrayList;)Z`
- `getIonHeapsSizeKb()J`
- `getIonMappedSizeKb()J`
- `getIonPoolsSizeKb()J`
- `getMemInfoFast([J)V`
- `getPss(I[J[J[J)J`
- `getSysJiffes()J`
- `getTimeByQtimer()J`

### android.os.GraphicsEnvironment

- `isDebuggable()Z`

### android.os.Process

- `getChildProcessViaGroup(II)[I`
- `setCgroupProcsProcessGroup(IIIZ)V`
- `setProcessFreezeGroup(IIZ)Ljava/util/ArrayList;`
- `setUIThreadScheduler(II)V`
- `useCGroupFreeze(Z)V`

### android.util.Affinity

- `bindToCpu(I)V`

### android.util.SeempLog

- `seemp_println_native(ILjava/lang/String;)I`

### android.util.StatsLogInternal

- `write(IIIIIIII[BI)I`
- `write(IIIZIIIIZJ)I`
- `write(IILjava/lang/String;IILjava/lang/String;)I`
- `write(ILjava/lang/String;IIIZZI)I`

### android.view.DisplayEventReceiver

- `nativeInit(Ljava/lang/ref/WeakReference;Landroid/os/MessageQueue;II)J`

### android.view.Surface

- `nHwuiNotifyMonitorStatsChanged(JZ)V`
- `nativeAttachAndQueueBufferWithColorSpace(JLandroid/graphics/GraphicBuffer;I)I`
- `nativeSetLastInputTime(JFFJII)V`

### android.view.ThreadedRenderer

- `nNotifyMonitorStatsChanged(JZ)V`

### android.widget.AbsListViewSmtBase

- `nativeResetFsyncAndFdatasync()V`
- `nativeUpdateFsyncAndFdatasync()V`

### com.android.internal.app.ActivityTrigger

- `native_at_deinit()V`
- `native_at_miscActivity(ILjava/lang/String;II)F`
- `native_at_pauseActivity(Ljava/lang/String;)V`
- `native_at_resumeActivity(Ljava/lang/String;)V`
- `native_at_startActivity(Ljava/lang/String;I)I`
- `native_at_startApp(Ljava/lang/String;I)I`
- `native_at_stopActivity(Ljava/lang/String;)V`

### com.android.internal.os.ZygoteInit

- `runtimeMmap()V`
- `systemServerMmap()V`

## services.jar — 6

### com.android.server.ActivityTriggerService

- `notifyAction_native(Ljava/lang/String;JLjava/lang/String;II)V`

### com.android.server.input.InputManagerService

- `nativeSetMotionClassifierEnabled(JZ)V`
- `nativeTransferTouchFocus(JLandroid/view/InputChannel;Landroid/view/InputChannel;)Z`

### com.android.server.lights.LightsService

- `pxrHmdServiceGetBrightness_native(I)I`
- `pxrHmdServiceSetBrightnessAnim_native(II)V`
- `pxrHmdServiceSetBrightness_native(F)V`
