#!/usr/bin/env bash
# Run through taskset -c 0-7. This validates configuration; it creates no ROM.
set -eo pipefail

pico_project=/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro
pico_source="$pico_project/source/aosp-10"
pico_log="$pico_project/logs/aosp"
mkdir -p "$pico_log"
cd "$pico_source"
export OUT_DIR="$pico_project/out/aosp-10"
export BUILD_NUMBER=PICO_AOSP_10_BRINGUP_2026092801

# envsetup accesses unset variables in these old branches; do not use set -u.
source build/envsetup.sh
lunch aosp_pico4pro-userdebug

build/soong/soong_ui.bash --dumpvars-mode --vars='PLATFORM_SDK_VERSION PLATFORM_VERSION TARGET_PRODUCT TARGET_DEVICE TARGET_ARCH TARGET_2ND_ARCH TARGET_DEVICE_DIR TARGET_BUILD_VARIANT PRODUCT_SHIPPING_API_LEVEL BOARD_VNDK_VERSION BOARD_SYSTEMIMAGE_PARTITION_SIZE BOARD_SYSTEMIMAGE_FILE_SYSTEM_TYPE BOARD_PREBUILT_VENDORIMAGE BOARD_PREBUILT_PRODUCTIMAGE BOARD_PREBUILT_ODMIMAGE PRODUCT_USE_DYNAMIC_PARTITIONS PRODUCT_USE_DYNAMIC_PARTITION_SIZE PRODUCT_BUILD_SUPER_PARTITION BOARD_BUILD_SYSTEM_ROOT_IMAGE OUT_DIR' \
    > "$pico_log/pico-build-vars.txt"

m -j8 nothing
