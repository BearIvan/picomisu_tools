#!/usr/bin/env bash
# Build the pinned Android 10 Java/JNI group and all installed boot-image files.
# The image names follow this product's boot JARs outside the updatable APEXes,
# in the factory PICO OS 5.13.7 order (device/pico/PICOA8110/factory-bootclasspath.json).
# VDEX is shared between ARM and ARM64; architecture-directory copies are
# symlinks, not targets.
set -eo pipefail
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
pico_project=/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro
product="$pico_project/out/aosp-10/target/product/PICOA8110"
images=(boot boot-core-libart boot-okhttp boot-bouncycastle boot-apache-xml
        boot-sysmonitor-framework boot-sys-framework boot-devicemiddlewareimpl
        boot-vrex-framework boot-framework boot-ext boot-telephony-common
        boot-voip-common boot-ims-common boot-android.test.base boot-tcmiface
        boot-telephony-ext boot-qcom.fmradio boot-QPerformance boot-UxPerformance
        boot-WfdCommon)
targets=()
for abi in arm64 arm; do
    for image in "${images[@]}"; do
        targets+=("$product/system/framework/$abi/$image.art"
                  "$product/system/framework/$abi/$image.oat")
    done
done
for image in "${images[@]}"; do
    targets+=("$product/system/framework/$image.vdex")
done
# The common driver applies taskset 0-7 and m -j8, keeps the selected build
# identity, verifies the physical ext4 mount, and does not flash the headset.
exec bash "$script_dir/build-vr-bridge.sh" picomisu-framework-runtime-probe \
    libpicomisu_framework_runtime_probe "${targets[@]}" "$@"
