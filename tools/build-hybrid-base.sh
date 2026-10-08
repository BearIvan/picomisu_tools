#!/usr/bin/env bash
# Compile the AOSP input image. assemble-vr-system.py makes the separate VR image.
set -eo pipefail
pico_project=/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro
pico_volume=/mnt/wsl/PHYSICALDRIVE5p3
test "$(findmnt -n -o FSTYPE --target "$pico_volume")" = ext4
test "$(findmnt -n -o UUID --target "$pico_volume")" = a00da05f-1eb2-44b6-99f0-9109391f67dc
pico_tools=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
taskset -c 0-7 python3 "$pico_tools/prepare-stock.py" \
  --cache "${PICO_STOCK_CACHE:-$pico_project/stock}" \
  --out "$pico_project/stock/5.13.7-SEKO"
cd "$pico_project/source/aosp-10"
export OUT_DIR="$pico_project/out/aosp-10"
export BUILD_NUMBER=PICO_AOSP_10_BRINGUP_2026092801
export BUILD_DATETIME=1790603988
export LD_LIBRARY_PATH="$pico_project/toolchains/host-compat/root/lib/x86_64-linux-gnu${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
source build/envsetup.sh
lunch aosp_pico4pro-userdebug
m -j8 systemimage DeskClock aapt2 apksigner e2fsdroid mke2fs simg2img img2simg
