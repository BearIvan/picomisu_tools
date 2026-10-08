#!/usr/bin/env bash
# Compile the experimental Java/JNI bridge; do not package or flash an image.
set -eo pipefail
if [[ ${PICOMISU_CPU_BOUND:-0} != 1 ]]; then
    exec env PICOMISU_CPU_BOUND=1 taskset -c 0-7 bash "$0" "$@"
fi
pico_project=/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro
test "$(findmnt -n -o FSTYPE --target "$pico_project")" = ext4
test "$(findmnt -n -o UUID --target "$pico_project")" = a00da05f-1eb2-44b6-99f0-9109391f67dc
cd "$pico_project/source/aosp-10"
export OUT_DIR="$pico_project/out/aosp-10"
export BUILD_NUMBER=PICO_AOSP_10_BRINGUP_2026092801
export BUILD_DATETIME=1790603988
export LD_LIBRARY_PATH="$pico_project/toolchains/host-compat/root/lib/x86_64-linux-gnu${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
source build/envsetup.sh
lunch aosp_pico4pro-userdebug
m -j8 framework libandroid_runtime libgui "$@"
