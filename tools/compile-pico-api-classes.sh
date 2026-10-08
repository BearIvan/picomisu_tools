#!/usr/bin/env bash
# Compile reconstructed PICO API sources (.java and .aidl) against the built Source
# framework and core libraries into one DEX JAR, for compare-pico-api.py before a full
# framework build. Usage: compile-pico-api-classes.sh <source-dir> <output.jar>
set -eo pipefail
if [[ ${PICOMISU_CPU_BOUND:-0} != 1 ]]; then
    exec env PICOMISU_CPU_BOUND=1 taskset -c 0-7 bash "$0" "$@"
fi
src=$(realpath "$1")
output=$(realpath -m "$2")
project=/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro
aosp=$project/source/aosp-10
out=$project/out/aosp-10
test "$(findmnt -n -o UUID --target "$project")" = a00da05f-1eb2-44b6-99f0-9109391f67dc
jdk=$aosp/prebuilts/jdk/jdk9/linux-x86/bin
inter=$out/soong/.intermediates
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
mkdir -p "$work/gen" "$work/classes"
while IFS= read -r -d '' aidl; do
    # framework.jar is built with generate_get_transaction_name.
    "$out/host/linux-x86/bin/aidl" --transaction_names -I"$src" -I"$aosp/frameworks/base/core/java" \
        -I"$aosp/frameworks/base/graphics/java" -I"$aosp/frameworks/base/wifi/java" \
        -I"$aosp/frameworks/native/aidl/gui" -I"$aosp/frameworks/native/aidl/binder" \
        -o"$work/gen" "$aidl"
done < <(find "$src" -name '*.aidl' -print0)
# Parcelable declarations produce no Java.
find "$src" "$work/gen" -name '*.java' > "$work/sources"
"$jdk/javac" -encoding UTF-8 -source 1.8 -target 1.8 -g -nowarn \
    -bootclasspath "$inter/libcore/core-oj/android_common/javac/core-oj.jar:$inter/libcore/core-libart/android_common/javac/core-libart.jar" \
    -cp "$inter/frameworks/base/framework/android_common/turbine-combined/framework.jar" \
    -d "$work/classes" @"$work/sources"
(cd "$work/classes" && "$jdk/jar" cf "$work/classes.jar" .)
"$jdk/java" -cp "$out/soong/host/linux-x86/framework/d8.jar" com.android.tools.r8.D8 \
    --min-api 29 --output "$output" \
    --lib "$inter/libcore/core-oj/android_common/javac/core-oj.jar" \
    --lib "$inter/frameworks/base/framework/android_common/turbine-combined/framework.jar" \
    "$work/classes.jar"
echo "$output"
