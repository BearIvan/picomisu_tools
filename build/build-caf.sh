#!/usr/bin/env bash
# Picomisu system build on CAF LA.UM.8.12.c3-64900-sm8250.0: build-caf.sh [make targets...]
#   PICOMISU_TREE     repo checkout (default: current directory)
#   PICOMISU_VARIANT  userdebug (default) or user
#   OUT_DIR           build output (default: $PICOMISU_TREE/out)
#   PICOMISU_HOST_COMPAT  directory with libncurses.so.5/libtinfo.so.5 for the old prebuilt Clang
#                     (tools/prepare-host-compat.py; not needed if the host has them)
#   JOBS              make -j (default 8)
#   PICOMISU_CPUS     pin the build to these CPUs (taskset list, e.g. 0-7); default: no pinning
# Default target: systemimage.
set -eo pipefail
if [[ -n ${PICOMISU_CPUS:-} && ${PICOMISU_CPU_BOUND:-0} != 1 ]]; then
    exec env PICOMISU_CPU_BOUND=1 taskset -c "$PICOMISU_CPUS" bash "$0" "$@"
fi
cd "${PICOMISU_TREE:-$PWD}"
test -f build/envsetup.sh -a -d device/pico/PICOA8110 || { echo "not a picomisu checkout: $PWD" >&2; exit 1; }
test -f device/pico/PICOA8110/factory-libs/factory/lib64/libvraudio.so || {
    echo "factory files missing: run device/pico/PICOA8110/extract-files.py <factory 5.13.7 images>" >&2; exit 1; }
export OUT_DIR="${OUT_DIR:-$PWD/out}"
export BUILD_NUMBER="${BUILD_NUMBER:-PICO_CAF_10_BRINGUP_2026100101}"
export BUILD_DATETIME="${BUILD_DATETIME:-1790603988}"
if [[ -n $PICOMISU_HOST_COMPAT ]]; then
    export LD_LIBRARY_PATH="$PICOMISU_HOST_COMPAT${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
fi
# CAF soong requires SDCLANG_PATH even when the Snapdragon LLVM (closed, not in the open manifest) is off.
export SDCLANG=false SDCLANG_PATH=/nonexistent/sdclang SDCLANG_PATH_2=/nonexistent/sdclang
# Vendor-side open QTI modules (audio HAL, fm hci, fstman...) link closed QTI libraries; they are not
# part of the system image. A system module with a missing dependency still fails when it is built.
export ALLOW_MISSING_DEPENDENCIES=true
# ABI reference dumps are regenerated after the first CAF build (rebase plan phase 6).
export SKIP_ABI_CHECKS=true
source build/envsetup.sh
lunch "aosp_pico4pro-${PICOMISU_VARIANT:-userdebug}"
# CAF envsetup make() (not m()): builds hidl-gen, generates the QTI HIDL Android.bp files, then builds.
set +e +o pipefail
make -j"${JOBS:-8}" "${@:-systemimage}"
