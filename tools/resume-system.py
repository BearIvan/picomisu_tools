"""Finish this task's interrupted system capture in WSL using Windows ADB."""

import argparse
import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import time


ADB = "/mnt/c/Users/RedPanda/AppData/Local/Android/Sdk/platform-tools/adb.exe"
BLOCK = 4 * 1024 * 1024


def shell(serial, command):
    result = subprocess.run([ADB, "-s", serial, "shell", command], capture_output=True, text=True, timeout=25)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return result.stdout.strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    args = parser.parse_args()
    baseline = args.baseline.resolve(strict=True)
    expected_root = Path("/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro/stock/5.13.7-live").resolve(strict=True)
    if baseline != expected_root:
        raise RuntimeError("Unexpected capture directory")
    report = json.loads((baseline / "capture.json").read_text())
    if "completed_at_utc" in report or "system" in report["partitions"]:
        raise RuntimeError("Capture is already complete")
    listing = subprocess.run([ADB, "devices"], capture_output=True, text=True, timeout=20)
    serials = [line.split()[0] for line in listing.stdout.splitlines() if len(line.split()) == 2 and line.split()[1] == "device"]
    matches = [serial for serial in serials if shell(serial, "getprop ro.build.fingerprint") == report["fingerprint"]]
    if len(matches) != 1:
        raise RuntimeError("Expected exactly one headset matching capture fingerprint")
    serial = matches[0]
    if not shell(serial, "su -c id").startswith("uid=0("):
        raise RuntimeError("Existing root access unavailable")
    partial = baseline / "system.img.partial"
    final = baseline / "system.img"
    if final.exists() or partial.is_symlink():
        raise RuntimeError("Unexpected existing image or symlink")
    expected = int(shell(serial, "su -c 'blockdev --getsize64 /dev/block/mapper/system'"))
    original_offset = partial.stat().st_size
    offset = original_offset - original_offset % BLOCK
    if not 0 < offset < expected:
        raise RuntimeError("Unexpected resume offset")
    print(f"Resuming system at {offset}/{expected} bytes", flush=True)
    if expected % 4096:
        raise RuntimeError("Unexpected logical partition alignment")
    last_progress = time.monotonic()
    with partial.open("r+b", buffering=BLOCK) as destination:
        destination.truncate(offset)
        destination.seek(offset)
        while offset < expected:
            count = min(64 * 1024 * 1024, expected - offset)
            # exec-out on this headset combines the remote stderr stream with
            # stdout. Discard dd's record counters to keep the image binary.
            command = f"su -c 'dd if=/dev/block/mapper/system bs=4096 skip={offset // 4096} count={count // 4096} 2>/dev/null'"
            result = subprocess.run([ADB, "-s", serial, "exec-out", command], capture_output=True, timeout=60)
            if result.returncode or len(result.stdout) != count:
                raise RuntimeError(f"Incomplete chunk at {offset}: bytes={len(result.stdout)}/{count}, exit={result.returncode}")
            destination.write(result.stdout)
            destination.flush()
            offset += count
            if time.monotonic() - last_progress >= 15:
                print(f"system: {offset}/{expected} bytes copied", flush=True)
                last_progress = time.monotonic()
    if shell(serial, "getprop ro.build.fingerprint") != report["fingerprint"]:
        raise RuntimeError("Firmware changed during capture")
    if final.exists():
        raise RuntimeError("Final image appeared during capture")
    partial.rename(final)
    digest = hashlib.sha256()
    with final.open("rb") as source:
        for data in iter(lambda: source.read(BLOCK), b""):
            digest.update(data)
    report["partitions"]["system"] = {"source_block_device": "/dev/block/mapper/system", "file": str(final), "bytes": expected, "sha256": digest.hexdigest()}
    report["system_capture_resumed_at_bytes"] = original_offset
    report["system_capture_method"] = "64 MiB verified reads via Windows ADB from WSL"
    report["completed_at_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    (baseline / "capture.json").write_text(json.dumps(report, indent=2) + "\n")
    print("System capture complete", flush=True)


if __name__ == "__main__":
    main()
