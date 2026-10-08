"""Paths of the Picomisu release pipeline.

Repo layout (manifest checkout, this repository at TOP/picomisu):
  TOP    the repo tree (build/envsetup.sh)          PICOMISU_TOP
  OUT    the build output (OUT_DIR, default TOP/out)
  WORK   factory images, staging, outputs          PICOMISU_WORK (default OUT/picomisu)

Legacy layout (the author's original workspace): the fixed ext4 volume
/mnt/wsl/PHYSICALDRIVE5p3 with source/<PICO_SOURCE_TREE> and out/<tree>; kept so
the existing workspace builds unchanged.
"""
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
_tree = os.environ.get('PICO_SOURCE_TREE', 'aosp-10')
_top = os.environ.get('PICOMISU_TOP') or (str(ROOT.parent) if (ROOT.parent / 'build/envsetup.sh').exists() else '')

if _top:
    LEGACY = False
    TOP = Path(_top).resolve()
    OUT = Path(os.environ.get('OUT_DIR') or TOP / 'out').resolve()
    WORK = Path(os.environ.get('PICOMISU_WORK') or OUT / 'picomisu').resolve()
    VOLUME = None
    SOURCE = TOP
    # A variant out dir (user build) keeps the host tools of the main out dir.
    HOST_OUT = Path(os.environ.get('PICOMISU_HOST_OUT') or OUT / 'host/linux-x86')
    # AVB 1.4 for Python 3 (the CAF tree's avbtool is AVB 1.1 for Python 2), see tools/third_party/avb.
    AVBTOOL = ROOT / 'tools/third_party/avb/avbtool.py'
else:
    LEGACY = True
    VOLUME = Path('/mnt/wsl/PHYSICALDRIVE5p3')
    WORK = VOLUME / 'home/red_panda/RedPandaAndroid/pico4-pro'
    TOP = SOURCE = WORK / 'source' / _tree
    OUT = WORK / 'out' / os.environ.get('PICO_OUT_TREE', _tree)
    HOST_OUT = WORK / 'out' / _tree / 'host/linux-x86'
    AVBTOOL = WORK.parent / 'source/external/avb/avbtool.py'

DEVICE = ROOT / 'device/pico/PICOA8110'
STOCK = WORK / 'stock/5.13.7-SEKO'
REPORTS = (WORK / 'reports' if not LEGACY else ROOT / 'reports')
# The non-root user that owns staging files written by the root steps.
USER = os.environ.get('SUDO_USER') or ('redpanda' if LEGACY else os.environ.get('USER', 'root'))
LOCK = json.loads((ROOT / 'config/stock-firmware.lock.json').read_text())


def guard_volume():
    """Legacy workspace: refuse to run unless the expected ext4 volume is mounted."""
    if not LEGACY:
        return
    found = json.loads(subprocess.check_output(
        ['findmnt', '--json', '-o', 'FSTYPE,UUID', '--target', str(VOLUME)], text=True))['filesystems']
    if found != [{'fstype': 'ext4', 'uuid': 'a00da05f-1eb2-44b6-99f0-9109391f67dc'}]:
        raise RuntimeError('Expected physical ext4 volume is not mounted')
