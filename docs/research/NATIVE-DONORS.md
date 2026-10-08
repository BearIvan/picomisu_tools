# Открытые исходники для графического стека Picomisu

Сравнение выполнено для libgui, а не для полного PICO OS. Проверены 14
выбранных API-маркеров, обнаруженных в заводской прошивке. Это определения
и отдельные признаки сигнатур; количество совпадений не является процентом
готовности порта и не подтверждает бинарную совместимость целой библиотеки.

| Источник | Фиксированная ревизия | Найденные маркеры из 14 |
|---|---|---:|
| Текущая исходная AOSP 10 r47 | `013eb744f289c70e6d3fe180500d9a414ac55539` | 0 |
| AOSP 10 QPR3 | `71e1890b755f126274e8225875050c7b785006e4` | 5 |
| Qualcomm Q / LA.UM.8.12.c3 | `bf08d9a8a251099a2735b6f69fdae315d44015da` | 6 |
| AOSP 11 r1 | `b8293fd0e0fdf278b0adc7315bf04fafd48b9ca7` | 5 |

Текущие авторские VR-патчи не включались в baseline r47 этого сравнения.
Рабочие исходники, сборка и шлем при сравнении не менялись.

## Подтверждённые источники интерфейсов

В AOSP QPR3 и Qualcomm Q найдены определения:

- BnProducerListener::onBuffersDiscarded с vector<int32_t>;
- DisplayEventReceiver с параметрами VsyncSource и ConfigChanged;
- Surface::connect с SurfaceListener;
- Surface::attachAndQueueBufferWithDataspace;
- DebugEGLImageTracker::getInstance.

Это пять именованных API из набора отсутствующих импортов, записанного
в `validation/libgui-abi.json`. Объявления/определения дают источник для
переноса; поведение и совпадение ABI каждой реализации надо проверять отдельно.
Dataspace в Surface — alias ui::Dataspace; SurfaceListener-overload проверен
отдельно от уже существующего connect с IProducerListener.

Qualcomm Q дополнительно содержит SurfaceControl::VpsExtension, также
экспортируемый заводской libgui PICO. В AOSP QPR3 и Android 11 r1 этого
расширения нет. Это дополнительное свидетельство связи с Qualcomm-веткой,
но оно не доказывает точный исходный commit PICO.

Между baseline r47 и Qualcomm Q в libgui различаются 22 файла:
602 добавленные и 89 удалённых строк. Между AOSP QPR3 и Qualcomm Q —
5 файлов, 98 добавленных и 8 удалённых строк. BufferItem.cpp идентичен
в обеих этих парах. Полученный ранее результат 204 wire-fixture сравнений
относится к установленной заводской библиотеке и нашей текущей AOSP-сборке.

В исследованных источниках не найдены private PICO API:
onBufferReleasedWithFence, getLatchAcquireSlotLocked, setDisplayFlags,
SurfaceMonitor, SurfaceClient, VirtualDisplayProducerListener,
producer QUERY 10000 и consumer configuration 10000.
Их отсутствия в этих четырёх деревьях недостаточно, чтобы утверждать,
что публичной реализации нигде не существует.

## Применение к текущему порту

Патч 0031 переносит DebugEGLImageTracker из pinned AOSP QPR3 вместе с
вызовами учёта в GLConsumer, RenderEngine и SurfaceFlinger dump. Header и тело
открытого tracker перенесены без изменений; байты совпадают с pinned donor.
Порядок virtual methods совпал с PICO в обоих ABI; по 72 process-local
source/factory fixture comparisons прошли. Это не проверка аппаратного
EGL lifecycle. SurfaceClient и его Binder caller query восстановлены
отдельно по заводским ELF; публичный QPR3-донор для них не использовался.

Ближайший из проверенных доноров libgui — Qualcomm Q с обновлениями,
совпадающими с AOSP QPR3. План: переносить нужные связные группы изменений
из фиксированных исходников, сохраняя уже проверенные VR-патчи и тесты.
Массовое переключение всей AOSP-системы на другой tag этим исследованием
не обосновано. После каждого переноса повторяется необходимая проверка
сигнатур, Binder-протокола и соответствующих вызовов на устройстве.

Первая связная группа — onBuffersDiscarded, SurfaceListener/Surface proxy,
уведомления BufferQueueCore и HIDL-обёртки ProducerListener. Закрытая камера
трекинга также требует onBufferReleasedWithFence. Его Binder transport и
VirtualDisplay listener теперь перенесены по factory-анализу и проверены
на обоих ABI. Затем перенесены local consumer fence-readiness, dequeue wait,
special release-detach и latch slot. Следующие связанные пути — queued-buffer
replacement callback и ConsumerBase ABI. onDisconnect уже присутствует
в pinned AOSP, поэтому прежнее указание на необходимость его переноса было
ошибочным. Одно совпадение экспортов не доказывает весь ABI.

Доступный Qualcomm tag `LA.UM.8.12.c3-64900-sm8250.0` и несколько других
тегов этой семьи указывают для данного репозитория на тот же commit bf08d9a8.
Совпадение commit frameworks/native не означает идентичности всего BSP.

## Повторение сравнения

`tools/compare-native-donors.py` использует отдельный bare-кэш на ext4:
`analysis/qualcomm-reference/native.git`. Его refs/research/aosp-r47,
refs/research/aosp-qpr3, refs/research/qualcomm-q и refs/research/aosp-r1
должны содержать перечисленные выше ревизии. Скрипт проверяет UUID тома,
читает Git-объекты и формирует `validation/native-source-comparison.json`.
Он не выполняет fetch и не изменяет рабочие репозитории.

Первичные источники:

- [AOSP QPR3 IProducerListener](https://android.googlesource.com/platform/frameworks/native/+/71e1890b755f126274e8225875050c7b785006e4/libs/gui/include/gui/IProducerListener.h)
- [Qualcomm Q SurfaceControl](https://git.codelinaro.org/clo/la/platform/frameworks/native/-/blob/bf08d9a8a251099a2735b6f69fdae315d44015da/libs/gui/include/gui/SurfaceControl.h)
- [Qualcomm repository](https://git.codelinaro.org/clo/la/platform/frameworks/native)

Тексты получены через Git с официальных серверов Google и CodeLinaro.
Полные исходники доноров остаются в локальном research-кэше; в Git Picomisu
сохраняются результаты сравнения и инструменты.
