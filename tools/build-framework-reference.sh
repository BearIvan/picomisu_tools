#!/usr/bin/env bash
# Build baseline JARs for interface comparison, not a complete headset image.
set -eo pipefail
pico_project=/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro
cd "$pico_project/source/aosp-10"
export OUT_DIR="$pico_project/out/aosp-10"
export BUILD_NUMBER=PICO_AOSP_10_BRINGUP_2026092801
source build/envsetup.sh
lunch aosp_pico4pro-userdebug
m -j8 framework services
