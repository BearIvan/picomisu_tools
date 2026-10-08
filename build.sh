#!/usr/bin/env bash
# Build the Picomisu release image from a repo checkout. No arguments:
#
#   repo init -u https://github.com/BearIvan/picomisu_manifest.git -b main --depth=1
#   repo sync -c -j8
#   picomisu/build.sh
#
# The version comes from device/pico/PICOA8110/release.json. Result: out/picomisu/outputs/source-<version>/.
# Optional environment:
#   PICOMISU_BOOT     boot image the headset runs (e.g. a Magisk boot read from it); vbmeta carries
#                     its hash. Default: the factory boot of the pinned OTA.
#   PICOMISU_VARIANT  userdebug (default) or user
#   OUT_DIR, PICOMISU_WORK, JOBS
# Root steps (read-only loop mounts of the factory/built images) run through sudo.
set -euo pipefail
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
top=$(cd "$here/.." && pwd)
cd "$top"
export PICOMISU_TOP=$top
export OUT_DIR=${OUT_DIR:-$top/out}
export PICOMISU_WORK=${PICOMISU_WORK:-$OUT_DIR/picomisu}
sudo=${PICOMISU_SUDO:-sudo}
stock=$PICOMISU_WORK/stock/5.13.7-SEKO
version=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["version"])' device/pico/PICOA8110/release.json)
step() { printf '\n==> %s\n' "$*"; }
as_root() {
    $sudo --preserve-env=PICOMISU_TOP,OUT_DIR,PICOMISU_WORK,PICOMISU_BOOT,PICOMISU_HOST_OUT python3 "$@"
    # Directories the root step created stay writable for the next (user) step.
    $sudo --preserve-env=PICOMISU_WORK chown -R "$(id -u):$(id -g)" "$PICOMISU_WORK"
}

[[ $(id -u) != 0 ]] || { echo "Run as a normal user; root steps use sudo." >&2; exit 1; }
test -f build/envsetup.sh -a -d device/pico/PICOA8110 || { echo "Not a picomisu repo checkout: $top" >&2; exit 1; }
missing=()
for tool in python3 debugfs rsync readelf; do command -v $tool >/dev/null || missing+=("$tool"); done
python3 -c 'import brotli' 2>/dev/null || [[ -f $stock/system.img ]] || missing+=(python3-brotli)
if ((${#missing[@]})); then
    echo "Missing: ${missing[*]}  (Ubuntu: sudo apt install python3-brotli e2fsprogs rsync binutils)" >&2; exit 1
fi
mkdir -p "$PICOMISU_WORK"
echo "Picomisu Source $version  tree=$top  work=$PICOMISU_WORK"

step "1/6 Factory PICO OS 5.13.7: download and verify the pinned OTA, reconstruct the images"
python3 picomisu/tools/prepare-stock.py --cache "$PICOMISU_WORK/download" --out "$stock"

step "2/6 Factory files for the device tree (extract-files.py, SHA-256 checked)"
python3 device/pico/PICOA8110/extract-files.py "$stock"

if ! ldconfig -p | grep -q 'libncurses.so.5'; then
    step "Host compatibility libraries for the prebuilt Clang (libncurses5, libtinfo5)"
    python3 picomisu/tools/prepare-host-compat.py
    export PICOMISU_HOST_COMPAT=$PICOMISU_WORK/toolchains/host-compat/root/lib/x86_64-linux-gnu
fi

step "3/6 Build: system image and host tools"
picomisu/build/build-caf.sh systemimage apksigner aapt2 e2fsck e2fsdroid img2simg mke2fs simg2img \
    zipalign checkvintf avbtool signapk host_init_verifier

step "4/6 Factory system tree and APK inventory"
as_root picomisu/tools/extract-vr-system.py
python3 picomisu/tools/inspect-factory-apks.py
python3 picomisu/tools/inspect-additional-apks.py

step "5/6 Release image source-$version"
as_root picomisu/tools/assemble-source-image.py --source-tree
python3 picomisu/tools/assemble-source-image.py --stage
as_root picomisu/tools/assemble-source-image.py --build
as_root picomisu/tools/assemble-source-image.py --readback

step "6/6 Offline checks"
python3 picomisu/tools/check-source-image.py

out=$PICOMISU_WORK/outputs/source-$version
(cd "$out" && sha256sum system.img vbmeta_system.img vbmeta.img > SHA256SUMS.txt)
printf '\nDone: %s\n' "$out"
cat "$out/SHA256SUMS.txt"
