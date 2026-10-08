#!/usr/bin/env bash
# Assemble a Source release image from a finished CAF build: assemble-release.sh VERSION [BASE_VERSION]
#   e.g. assemble-release.sh 2.21 2.20  -> device/pico/PICOA8110/source-2.21.json, outputs/source-2.21
# Runs in WSL from the picomisu checkout; the steps marked (root) use sudo, as the tool requires.
set -euo pipefail
version=$1
cd "$(dirname "$0")/.."
export PICO_SOURCE_TREE="${PICO_SOURCE_TREE:-caf-10}"
export PICO_TRIAL="source-$version"
[[ $# -ge 2 ]] && export PICO_BASE_RELEASE="source-$2"
test -f "device/pico/PICOA8110/$PICO_TRIAL.json" || { echo "no release config $PICO_TRIAL.json" >&2; exit 1; }
keep="PICO_SOURCE_TREE=$PICO_SOURCE_TREE PICO_TRIAL=$PICO_TRIAL PICO_BASE_RELEASE=${PICO_BASE_RELEASE:-}"
sudo env $keep python3 tools/assemble-source-image.py --source-tree   # (root) read the built system.img
python3 tools/assemble-source-image.py --stage                        # factory + Source merge plan
sudo env $keep python3 tools/assemble-source-image.py --build         # (root) ext4, vbmeta, AVB
sudo env $keep python3 tools/assemble-source-image.py --readback      # (root) image == plan
python3 tools/check-source-image.py                                   # offline SELinux/init/native checks
echo "Images: outputs/$PICO_TRIAL (copy system.img, vbmeta.img, vbmeta_system.img to the Windows outputs/$PICO_TRIAL)"
echo "Then on Windows: python tools/source-ota.py register $version $PICO_TRIAL"
