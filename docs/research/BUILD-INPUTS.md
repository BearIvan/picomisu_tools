# Заводские компоненты Picomisu

Git хранит наши изменения и `config/stock-firmware.lock.json`: официальный URL,
версию, размер и SHA-256 OTA и необходимых образов. Заводские бинарные файлы
получаются локально при подготовке сборки; публиковать их в Git не требуется.

`tools/build-hybrid-base.sh` перед компиляцией вызывает `prepare-stock.py`.
Нужны Python 3 и модуль `brotli`. Кэш и извлечённые образы располагаются
на ext4 рядом с деревом сборки. Для существующего кэша можно задать
`PICO_STOCK_CACHE`; проверенный ZIP повторно не скачивается.

Отдельная подготовка без компиляции и подключения шлема:

```sh
python3 tools/prepare-stock.py --cache /path/to/cache --out /path/to/stock/5.13.7-SEKO
```

`--offline` запрещает скачивание. Перед использованием проверяются полный
SHA-256 ZIP, модель/вариант/версия из OTA metadata и каждый готовый образ.
Отсутствующие образы восстанавливаются из полного BLOCK OTA. Повторный запуск
проверяет и переиспользует готовые файлы. Несовпадение контрольной суммы
останавливает работу; существующие файлы не заменяются автоматически.

Подготовка извлекает system, vendor, product, odm, boot, recovery, dtbo,
vbmeta, vbmeta_system и сертификат OTA. Она не запускает updater из ZIP.
Lock фиксирует ранее проверенный пакет; новая версия требует отдельной
проверки подлинности и совместимости перед изменением lock-файла.

`tools/install-device-tree.py` дополнительно извлекает из проверенного product.img
заводской `/lib64/libcryptfs_hw.so` (SHA-256 e695b935…4d66df) в
`device/pico/PICOA8110/cryptfs_hw/factory/lib64`: с ним линкуется vold
(CONFIG_HW_DISK_ENCRYPTION, как на заводе). В Git этот файл не хранится.

Из проверенного system.img тот же инструмент извлекает заводские class path JAR, которые
Source-образ сохраняет бинарными (SHA-256 каждого в `tools/install-device-tree.py` и
`device/pico/PICOA8110/factory-bootclasspath.json`): sysmonitor-framework, sys-framework,
devicemiddlewareimpl, vrex-framework, tcmiface, QPerformance, UxPerformance, WfdCommon,
vrex-services → `device/pico/PICOA8110/factory-framework/factory/` (модули `dex_import`), и
списки PeroptWhiteListParser `OptPackageWhiteList.xml`, `OptAppInfoWhiteList.xml`,
`AppCompositionWhiteList.xml` → `factory-framework/etc/`. Заводские oat/vdex не используются.

Это автоматизация получения заводских входных образов. Существующая сборка
гибридного VR-образа пока также использует локальные отчёты анализа, извлечённое
дерево system и сохранённый Magisk boot конкретного шлема. Полная сборка
готового дистрибутива с чистого checkout без этих локальных данных ещё требует
отдельной доработки. Устройство и резервные копии этим этапом не изменяются.

Экспорт изменений source-компонентов проверяется отдельно:

```sh
python3 tools/verify-patch-series.py
```

Для существующих локальных репозиториев frameworks/native, frameworks/base и art
скрипт берёт фиксированный upstream из `config/aosp-patches.json`, применяет
патчи по порядку во временном Git index и сравнивает полученное дерево с
сохранённым local commit. Checkout и его основной index не изменяются.
Зафиксированные 124 патча воспроизводят сохранённые Git trees; результат записан в
`validation/patch-series.json`. Эта проверка экспорта требует наличия локальных
коммитов и не заменяет ещё незавершённую сборку дистрибутива с чистого checkout.

Для согласованной Java/JNI runtime группы есть отдельный драйвер:

```sh
bash tools/build-framework-runtime.sh
```

Он собирает framework, libandroid_runtime, libgui, изолированные runtime
fixtures и все 105 boot-image targets (21 boot JAR в заводском порядке) для pinned Android 10 продукта.
Список целей не зависит от сохранённого тестового пакета. Shared VDEX
используются из общего framework directory; architecture-directory symlinks
не передаются Ninja как отдельные цели. Общий драйвер сохраняет build identity
и предел taskset 0–7 / m -j8. Установка на шлем не выполняется.
