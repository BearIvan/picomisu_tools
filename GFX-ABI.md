# Совместимость графического стека Picomisu

Патч 0033 добавляет Source Surface VR canvas Java/JNI API. Оба Source JNI
набора соответствуют factory DEX descriptors; runtime проверены 19 fixtures
на ABI с compiled boot images. Pixel storage Source выделяет полноценный
RGBA pixel на canvas вместо factory shared byte. Политика ActivityInfo и
ViewRoot drawSoftware routing ещё не перенесены; API перенос не доказывает
hardware rendering. Native libgui checkpoint ниже не менялся.


Актуальная точка после патча 0032: SurfaceMonitor подключён к
MonitoredProducer вместе с SurfaceClient. На ARM64/ARM32 прошли 378
уникальных native gtests и 148 source/factory снимков monitor с совпадающими
Binder/file/lookup traces. Пакет Source Java/JNI/ART/Bionic с compiled boot
images прошёл по 12 fixtures на ABI. В графе 493 ARM64 ELF отсутствующих
используемых импортов libgui теперь **0**, отличий исследованных размеров
vtable нет. ARM32 runtime-граф не исследован. Неизвестная область из 40
bytes monitor сохранена; полный private C++ ABI, реальные Binder/GPU
события, смена display frequency и VR на общем Source образе ещё открыты.
Свидетельства: `validation/surface-monitor-port.json`,
`validation/surface-monitor-abi.json` и `validation/libgui-abi.json`.

Предыдущая точка после патча 0031: DebugEGLImageTracker и SurfaceClient
перенесены вместе с зависимым Binder getCallingTid. На каждом ABI прошли
72 tracker, 22 frame-history и 8 caller-query source/factory сравнений.
Прежние 368 native gtests и 24 Java/JNI fixtures с compiled Source boot
images также прошли. В исследованном графе 493 ARM64 ELF остаются **5**
отсутствующих используемых импортов libgui, все из SurfaceMonitor. Данные
ARM32 runtime-графа отсутствуют. Полный private ABI, remote caller query,
реальный EGL lifecycle и GPU/VR ещё не квалифицированы. Актуальные данные:
`validation/frame-diagnostics-port.json`, `validation/libgui-abi.json` и
`validation/native-runtime-current.json`.

Предыдущая точка после патчей 0029/0030: Source flags API и связанный
single-layer compositor path перенесены. Прошли по 17 factory flags
сравнений, 14 новых SF cases и 55 composition/display cases на ABI.
368 уникальных native gtests и по 12 Java/JNI fixtures с compiled Source boot
images проверены; GPU/VR и полный private ABI остаются открытыми. В libgui
оставалось 11 используемых отсутствующих ARM64 символов. Свидетельства этапа:
`validation/display-flags-port.json`, `validation/libgui-abi.json` и
`validation/native-runtime-current.json`.

Предыдущая точка после патча 0028: PICO single-layer/private-consumer dequeue
allowances перенесены и прошли по 108 сравнений с factory на ARM64/ARM32.
236 native-тестов и шесть actual-source/factory JNI сравнений на каждом ABI
также прошли. Java VirtualDisplay/Surface исполняется с Source ART, Bionic и
compiled boot images: по девять Java-проверок на ABI. В libgui остаются 12
используемых отсутствующих ARM64 символов. Real freeze/GPU events, private
C++ ABI целиком и полный VR ещё не квалифицированы. Подробности:
`validation/dequeue-count-port.json`, `validation/framework-boot-image.json`
и `validation/native-runtime-current.json`.

Для single-layer ветки найдено свойство `persist.sys.skip_single_layer`
(factory default true) и дополнительная команда producer `-2`. Source теперь
воспроизводит её count/status поведение, включая private consumer allowance
и abandon. Source SurfaceFlinger caller и связанные display/layer conditions
были следующим этапом до патчей 0029/0030. Их текущая реализация и границы
проверки описаны выше; аппаратная проверка композиции ещё впереди.


Аудит `tools/audit-libgui-compat.py` сравнивает экспортируемые имена заводской
и собранной AOSP libgui для ARM64/ARM32. Для 493 ELF из сохранённого runtime-
графа ARM64 дополнительно проверены сильные импорты. Подлинность заводских
копий подтверждается сохранёнными SHA-256. Результат исследования сохраняется
локально в reports; компактный итог — `validation/libgui-abi.json`.

В исходном снимке ARM64 обнаружен 21 отсутствующий импорт у 10 заводских библиотек.
Например:

- libpvrtrackingcamera, libmedia_jni и libstagefright требуют
  `BnProducerListener::onBuffersDiscarded` и `onBufferReleasedWithFence`.
- libhwui и libsurfaceflinger требуют `ConsumerBase::getLatchAcquireSlotLocked`.
- Несколько компонентов требуют DisplayEventReceiver с параметром ConfigChanged.
- libandroid_runtime требует setDisplayFlags и attachAndQueueBufferWithDataspace.
- libsurfaceflinger использует дополнительные SurfaceClient/SurfaceMonitor
  и VirtualDisplayProducerListener.

В исходном снимке различались размеры 28 экспортируемых таблиц виртуальных методов ARM64,
включая IGraphicBufferProducer, IGraphicBufferConsumer и IProducerListener.
Поэтому наличие существующих имён методов не гарантирует правильных вызовов
из закрытых бинарных клиентов. Нужен перенос их контрактов и порядка методов,
а также отдельная проверка C++ object layout и поведения.

Отсутствующие экспорты, которые ни один исследованный клиент не импортирует,
сами по себе не являются доказанными блокерами. Не каждый символ libgui
с отдельным экспортом является OEM VR-расширением: есть изменения платформы,
отладочные компоненты и шаблоны C++. Полное дерево зависимостей ещё не охвачено.

Из runtime-графа не получено ARM32-клиентов. Для ARM32 проверено только
сравнение экспортов/vtable, а не совместимость всех заводских потребителей.
Версии символов в этом аудите нормализованы; versioning не проверен.

Группа QPR3 onBuffersDiscarded/SurfaceListener перенесена и прошла 44 теста
в изолированных процессах. Она устранила два отсутствующих используемых
символа: BnProducerListener::onBuffersDiscarded и Surface::connect с
SurfaceListener. После неё в исследованном графе остаются 19 отсутствующих
используемых символов. Размер Surface vtable совпал с заводским, но полная
совместимость порядка методов и object layout не доказана.

Producer fence callback и VirtualDisplayProducerListener перенесены следующим
патчем. 64 native-теста прошли; 12 проверок на ABI совпали с factory libgui
в отдельном probe. Порядок четырёх callback, размеры vtable и primary prefixes
проверены для шести классов в ARM64/ARM32. После этого в графе ARM64 осталось
15 используемых отсутствующих символов, а отличий размеров vtable — 17
в каждом ABI. Устранены Bn fence callback, VirtualDisplay setCallback,
VTT и vtable. См. `validation/producer-fence.json`.

Consumer/dequeue ready-handshake и special release-detach теперь перенесены.
84 native-теста прошли; три локальных consumer проверки на ABI совпали
с factory libgui. Размеры четырёх consumer vtable и их local-only tail
совпали; getter latch slot имеет одинаковое машинное тело в обоих ABI.
Используемых отсутствующих символов осталось 14, отличий размеров vtable — 12
в каждом ABI. См. `validation/consumer-fence.json` и `consumer-fence-abi.json`.

Callback с флагом true при замене queued буфера реализован в рабочем дереве
и собран; расширенный frame-path probe ещё не выполнен на шлеме.
Pipe проверяет FD, а GPU fence и настоящий Binder IPC не проверены.
Системная libgui на шлеме остаётся заводской.

Дополнительная проверка `inspect-consumer-listener.py` исправляет прежнее
предположение: onDisconnect уже есть в pinned AOSP, включая Binder-команду 1.
В шести проверенных классах порядок consumer callback соответствует factory
(имена pure-virtual slots отдельно не доказаны). У пяти классов также совпадают
размеры vtable и primary prefixes. Это не проверка всего object layout.

До патча 0008 ConsumerBase был несовместимым: factory getter виртуальный, расположен
по смещению 128 от начала vtable ARM64 / 64 ARM32; у source этого слота нет.
Размеры vtable factory/source — 248/240 и 124/120 байт соответственно.
Смещение виртуальной базы RefBase — 1688/1672 и 1076/1068 соответственно.
Одинаковое тело getter и присутствие экспортируемого имени не устраняют
эти расхождения. Строгая проверка до исправления возвращала код 1.

В ARM64 factory конструкторы инициализируют поле 1672 нулём и поле 1680
значением -1. onFrameAvailable и onFrameReplaced, когда обычный weak listener
не удалось получить, вызывают указатель из 1672 с int из 1680, если указатель
ненулевой и аргумент не -1. Вызов идёт после освобождения frame mutex.
ARM32 Thumb подтверждает те же проверки и поля по смещениям 1068/1072.
Патч 0008 добавляет эти поля, fallback-поведение и виртуальный getter.
Имена полей реконструированы; callback моделируется как void(int), результат
заводского вызова игнорируется. Запись callback клиентами ещё требует исследования.

После патча 0008 сборка завершилась успешно для ARM64/ARM32. Строгий
`inspect-consumer-listener.py --require-layout-match` проходит: для шести
классов совпадают проверенные callback slots, размеры vtable и primary prefixes;
для ConsumerBase также совпало положение виртуального getter.
Отчёт — `validation/consumer-listener.json`. Общий аудит теперь показывает
8 отличий размера vtable на ABI; 14 отсутствующих используемых ARM64 символов
сохраняются. Полный ABI не доказан. Новые тесты собраны, но не выполнены:
пакет `bufferqueue-test-08` ожидает 51 тест на ABI и 5 consumer probe fixtures.
Шлем недоступен по ADB; последний подтверждённый runtime — 42 теста на ABI.

Патч 0009 добавляет QPR3 DisplayEventReceiver(VsyncSource, ConfigChanged)
и проводит настройку через Binder, SurfaceFlinger, Scheduler и EventThread.
В factory ARM64 и ARM32 статически подтверждены два int32 после interface
token, транзакция 4 и flags 0. Соответствующие библиотеки и штатные unit-тесты
SurfaceFlinger собраны успешно. Используемых отсутствующих ARM64 символов
осталось 13; отличий размера vtable — 8 на ABI. Запуск тестов на шлеме и
сравнение реальных выходов proxy отдельным probe пока не выполнены.

Патч 0010 добавляет `picomisu_display_config_probe` для ARM64/ARM32.
Оба бинарника собраны. Probe использует локальный BBinder relay, проверяет
все четыре сочетания source/config и default app/suppress, записывает
байты запросов и проверяет команду/flags. Настоящий Binder IPC, Bn-обработчик
и доставка событий работающим SurfaceFlinger в охват этого probe не входят.
Пакет `outputs/bufferqueue-test-09` содержит 116 файлов с SHA-256.
Для запуска runner нужны `--expected-tests 51 --fence-probe
--consumer-fence-probe --expected-consumer-fixtures 5 --display-config-probe`,
путь к пакету и ADB. Выполнение ожидает подключения проверенного шлема;
наличие собранного probe не считается успешным runtime-результатом.

Патч 0011 добавляет Surface::attachAndQueueBufferWithDataspace. Тело функции
точно совпадает с фиксированным QPR3; ARM64 factory control flow соответствует
этому донору. Старый attachAndQueueBuffer сохранён. Dataspace восстанавливается
после успешного queue; ранние ошибки сразу возвращаются, как в factory/QPR3.
Сборка прошла для обоих ABI. В отдельном тестовом subclass проверяются порядок
вызовов, успех, null buffer и шесть точек отказа без GPU allocation.
Тесты только собраны, не выполнены: runner не обнаружил проверенный шлем
и остановился до push. Пакет `outputs/bufferqueue-test-10` ожидает 54 теста
на ABI; probe flags те же, что для пакета 09. Отчёт —
`validation/surface-dataspace.json`. Отсутствующих используемых ARM64 символов
осталось 12; отличий размера vtable — 8 на ABI. Это не полная совместимость.

Исследование setDisplayFlags: в проверенных QPR3/Qualcomm Q/Android 11 донорах
метод не найден. ARM64 factory DisplayState добавляет uint32 после height
(offset 72, default 0). Setter и merge используют what bit 0x10; Parcel write/read
передают поле последним. Обработчик SurfaceFlinger переносит значение в
DisplayDeviceState+124 и запрашивает display transaction при изменении.
Создание и обновление дисплея сохраняют полные flags и извлекают bit 20.
Этот bit, вместе с ещё не разобранными дополнительными условиями, включает
ветку композиции, которая проверяет usage mask 0xf00000000 и значения
0x400000000/0x800000000. Это связь с ранее исследованными ready/timeout buffers,
но полный эффект ветки и её RenderSurface вызовы ещё не восстановлены.

`tools/inspect-display-flags.py` сверяет SHA-256 обоих factory ELF и 46 точных
ARM64 instruction checkpoints; результат — `validation/display-flags-research.json`.
Это воспроизводимая проверка исследованных мест, не доказательство всей
семантики или ABI. ARM32, весь путь композиции и runtime остаются открытыми.
Исходники display flags пока не изменены: экспорт без связанного поведения
не считается завершённым переносом.

Дальнейшая сверка RenderSurface vtable установила методы factory по смещениям
152/160/168/176/184 от address point: flipClientTarget, attachBuffer,
setSingleLayer, setMultiLayerFlag, getMultiLayerFlag. Три последних передают
вызовы в DisplaySurface по слотам 72/80/88. У текущего AOSP RenderSurface
vtable 168 байт против 208 в PICO; это отдельный интерфейс libsurfaceflinger,
который не входит в счётчик 12 отсутствующих символов libgui.

В исследованной ветке требуется один элемент размером 288 байт. Она читает
GraphicBuffer usage, распознаёт nibble 4/8 и очищает nibble в буфере.
При разрешённом режиме одного слоя вызывается RenderSurface::attachBuffer;
обычный путь использует dequeueBuffer и рендеринг. Factory attachBuffer
ставит nibble 1 перед Surface::attachBuffer и nibble 2 после него, а при
ошибке очищает nibble. Проверка исходного буфера также может вернуть -17
при совпадающем buffer ID. Это подтверждает связь с перенесённым BufferQueue
протоколом. Полные условия переключения, flipClientTarget, concrete
DisplaySurface implementations и управление release fences ещё не перенесены.

flipClientTarget в factory занимает ровно 12 байт: нормализует bool и пишет
RenderSurface+73. queueBuffer проверяет этот флаг до обычных условий HWC,
а при отправке и отмене буфера использует FD -1 вместо dup(readyFence).
Это не самостоятельная операция отправки кадра; состояние применяется позже.
Полный цикл release fence пока не доказан.

ARM64 RenderSurface хранит отдельный Surface* в +32, последний прикреплённый
GraphicBuffer в +40, текущий в +48, DisplaySurface в +56; protected/flip
находятся в +72/+73, счётчик кадров — в +76. Конструктор получает Surface
из RenderSurfaceCreationArgs+24, а не преобразует ANativeWindow. В текущем
AOSP такого аргумента нет. Потребуется согласованное расширение параметров
создания, DisplayDevice и фабрики NativeWindowSurface с сохранением mock-пути.
Одного изменения RenderSurface без этой цепочки недостаточно.

Патч 0012 реализует передачу typed Surface через указанную цепочку создания.
Новый виртуальный getter фабрики имеет default nullptr для mock-пути;
производственная фабрика возвращает тот же Surface, который предоставляет
ANativeWindow. Surface хранится отдельным strong reference в RenderSurface.
Сборка композитора и двух наборов unit-тестов успешна; runtime ещё не проверен.
Это подготовка объектов, а не завершённый перенос прямой композиции или всего
factory layout. Проверки pending описаны в `validation/typed-surface.json`.

Актуализация runtime: пакет 12 проверен на шлеме через Wi-Fi ADB. Все 54
BufferQueue/Surface теста прошли на каждом ABI; 31 RenderSurfaceTest прошёл
на ARM64. С factory совпали producer-fence (12), consumer-fence (5) и
display-config (5) fixtures на ABI. Это закрывает ожидание устройства для
перечисленных исходных тестов. Исторические записи pending выше относятся
к моменту подготовки соответствующих пакетов. Полный GPU/VR runtime и
global ABI остаются непроверенными.

Патч 0013 добавляет первый PICO RenderSurface virtual — flipClientTarget —
и его использование в queueBuffer/cancelBuffer. Factory slot order сохраняется
для перенесённого префикса; оставшиеся четыре метода и полный object layout
не завершены. Тесты используют pipe FD, проверяя выбор/ownership дескриптора,
а не GPU sync fence. Системные библиотеки шлема не заменены.

Патч 0014 переносит RenderSurface::attachBuffer. Usage nibble становится 1
на время Surface::attachBuffer, затем 2 при успехе; при ошибке очищается,
текущий буфер сбрасывается. Last-attempt ID сохраняется и при ошибке:
повтор этого ID возвращает ALREADY_EXISTS. Добавлены проверки null buffer
(BAD_VALUE) и отсутствующего typed Surface (NO_INIT); factory предполагает
корректные входы. Базовый RenderSurface имеет default NO_ERROR, как factory.

Пакет 13 прошёл 54 теста на ABI и 35 RenderSurfaceTest на ARM64, включая
четыре новые поведенческие проверки. Прежние factory probes также совпали.
Прямого выполнения factory RenderSurface::attachBuffer пока нет: поведение
сопоставлено статически, новые тесты выполняют source implementation с mock
Surface. Слоты flipClientTarget/attachBuffer совпали; setSingleLayer,
setMultiLayerFlag, getMultiLayerFlag и concrete DisplaySurface путь ещё
требуют переноса. См. `validation/render-surface-attach.json`.

Патч 0015 переносит оставшиеся три forwarding метода RenderSurface и
соответствующие virtual defaults DisplaySurface. Сигнатура setSingleLayer
использует именно android::Layer, а не compositionengine::Layer. Default
setSingleLayer возвращает NO_ERROR, setter multi-layer ничего не меняет,
getter возвращает true — это подтверждено factory machine code.

Пакет 14 прошёл 54 BufferQueue/Surface и 39 RenderSurfaceTest на каждом ABI
(186 тестов). Проверены forwarding аргументов, возврат ошибки/успеха, обе
установки multi-layer и default true. Прежние factory probes совпадают.
У ARM64 совпали полные символы и позиции пяти расширений RenderSurface,
размеры vtable RenderSurface, impl::RenderSurface и DisplaySurface.
Это не доказательство всего object layout или VR-композиции. Реальные
VirtualDisplaySurface setSingleLayer/release-fence callbacks ещё не перенесены;
нынешние default implementations не включают production direct path.
См. `validation/display-surface-forwarding.json`.

Concrete VirtualDisplaySurface ARM64 найден через конструктор и private vtable
с address point 0x184fc0. Slots 72/80/88 ведут к setSingleLayer (0xb07f8),
setMultiLayerFlag (0xb0c6c), getMultiLayerFlag (0xb0c78). Constructor устанавливает
multi-layer=true; setter/getter используют поле +3560.

setSingleLayer блокирует mutex +3520, отклоняет null layer/buffer и хранит
запись по buffer ID. Запись 32 байта содержит slot в +4, strong GraphicBuffer
в +8, strong Layer в +16 и outstanding count в +24. Повторный ID заменяет
запись новыми данными и увеличенным счётчиком. Slot захватывается из состояния
composition layer. Это счётчик ожидаемых освобождений, не просто последний ID.

Найден release callback: UINT64_MAX отклоняется; пустой реестр возвращает OK,
неизвестный ID в непустом реестре — BAD_VALUE. Пока счётчик после уменьшения
положителен, callback возвращается без передачи fence в Layer. При последнем
освобождении запись удаляется, mutex отпускается, затем Layer vslot 560
получает fence/buffer/slot. Для BufferQueueLayer этот слот разрешён как
notifyFenceReady; он передаёт вызов в BufferLayerConsumer. При replacement=true
дополнительно вызывается vslot 552 — releasePendingBuffer(systemTime(1)).
Consumer при совпадении ожидающего буфера/слота добавляет release fence,
после чего вызывает ранее перенесённый IGraphicBufferConsumer::notifyFenceReady.

`inspect-virtual-display-fence.py` проверяет pinned ELF, private vtable,
имена двух Layer callbacks и 21 checkpoint. Регистрация/срок жизни callback,
очистка реестра при disconnect и ARM32 ещё требуют разбора. Concrete путь
не перенесён и не проверен выполнением factory функций. Результат находится
в `validation/virtual-display-fence-research.json`.

Регистрация callback уточнена: producer connect создаёт собственный
VirtualDisplayProducerListener; std::bind хранит raw this и виртуальный
member-pointer (offset 96, adjustment 0). Private primary slot 96 разрешён
в callback 0xb0528, slot 104 — в helper 0xb01c0. Disconnect сначала снимает
callback через setCallback(empty), затем вызывает helper и отключает sink.
Helper собирает strong references на записи под mutex и после unlock
вызывает Layer::notifyFenceReady с NO_FENCE. Явного erase реестра в этом
helper не найдено: это уведомление по снимку, его нельзя без доказательств
заменять очисткой map. Destructor lifetime и гонки ещё требуют проверки.
Расширенный анализатор проверяет member-pointer representation, closure
invoker, NO_FENCE relocation и 32 instruction checkpoints.

Патч 0016 реализует нижнюю часть цепочки fence: Layer default no-op,
BufferQueueLayer forwarding и BufferLayerConsumer notifyFenceReady под mMutex.
При совпадении pending buffer ID и slot добавляется release fence, затем
consumer получает fence/ID/slot. Source дополнительно защищён от callback
после abandon и null buffer при сравнении pending ID.

Пять ASan tests прошли на ARM64 и ARM32. Один первоначальный тест неверно
ожидал идентичности fence при merge с NO_FENCE; исправленный тест проверяет
первую вставку в изначально пустой slot fence. Pipe не является GPU sync-file:
слияние и тайминги настоящих GPU fences здесь не проверяются. Проверены
маршрутизация, matching/stale ID, несовпадающий slot и late callback.
Остальные 186 тестов прошли в пакете 15; пакет 16 изменил только исправленные
ASan unit binaries, что подтверждено сравнением всех SHA-256. Текущий результат
196 тестов отражён в `validation/native-runtime-current.json`.
Этот исторический этап дополнен патчами 0017–0018; актуальный результат приведён в начале документа.
