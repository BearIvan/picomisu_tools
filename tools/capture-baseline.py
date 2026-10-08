"""Read system and calibration partitions from an already rooted PICO.

No flashing, remounting, configuration changes, or userdata capture.
Requires existing su permission and a destination with at least 9 GiB free.
The resulting boot image includes any currently installed Magisk changes.
"""

import argparse
import datetime
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time


PARTITIONS = {
    "boot": "/dev/block/bootdevice/by-name/boot",
    "dtbo": "/dev/block/bootdevice/by-name/dtbo",
    "vbmeta": "/dev/block/bootdevice/by-name/vbmeta",
    "vbmeta_system": "/dev/block/bootdevice/by-name/vbmeta_system",
    "recovery": "/dev/block/bootdevice/by-name/recovery",
    "persist": "/dev/block/bootdevice/by-name/persist",
    "fsg": "/dev/block/bootdevice/by-name/fsg",
    "picocfg": "/dev/block/bootdevice/by-name/picocfg",
    "odm": "/dev/block/mapper/odm",
    "product": "/dev/block/mapper/product",
    "vendor": "/dev/block/mapper/vendor",
    "system": "/dev/block/mapper/system",
}


def shell(adb, serial, arguments):
    result = subprocess.run([adb, "-s", serial, "shell", *arguments], capture_output=True, text=True, timeout=25)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return result.stdout.strip()


def capture(adb, serial, name, block_device, output):
    size = int(shell(adb, serial, [f"su -c 'blockdev --getsize64 {block_device}'"]))
    if not 0 < size <= 9 * 1024**3:
        raise RuntimeError(f"Unexpected partition size: {name}: {size}")
    final = output / f"{name}.img"
    partial = output / f"{name}.img.partial"
    if final.exists() or partial.exists():
        raise FileExistsError(f"Refusing to replace {final}")
    digest = hashlib.sha256()
    count = 0
    last_progress = time.monotonic()
    if name == "system":
        if size % 4096:
            raise RuntimeError("Unexpected system partition alignment")
        with partial.open("xb", buffering=4 * 1024 * 1024) as destination:
            while count < size:
                expected_chunk = min(64 * 1024 * 1024, size - count)
                command = f"su -c 'dd if={block_device} bs=4096 skip={count // 4096} count={expected_chunk // 4096} 2>/dev/null'"
                result = subprocess.run([adb, "-s", serial, "exec-out", command], capture_output=True, timeout=60)
                if result.returncode or len(result.stdout) != expected_chunk:
                    raise RuntimeError(f"Incomplete system chunk at {count}")
                destination.write(result.stdout)
                digest.update(result.stdout)
                count += len(result.stdout)
                if time.monotonic() - last_progress >= 20:
                    print(f"{name}: {count}/{size} bytes copied", flush=True)
                    last_progress = time.monotonic()
        partial.rename(final)
        print(f"Captured {name}: {count} bytes", flush=True)
        return {"source_block_device": block_device, "file": str(final), "bytes": count, "sha256": digest.hexdigest(), "capture_method": "64 MiB verified reads"}
    command = [adb, "-s", serial, "exec-out", f"su -c 'cat {block_device}'"]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        with partial.open("xb", buffering=4 * 1024 * 1024) as destination:
            for chunk in iter(lambda: process.stdout.read(4 * 1024 * 1024), b""):
                count += len(chunk)
                if count > size:
                    raise RuntimeError("Unexpected data exceeds partition size")
                destination.write(chunk)
                digest.update(chunk)
                if time.monotonic() - last_progress >= 20:
                    print(f"{name}: {count}/{size} bytes copied", flush=True)
                    last_progress = time.monotonic()
        error = process.stderr.read().decode(errors="replace")
        status = process.wait(timeout=30)
        if status or count != size:
            raise RuntimeError(f"Incomplete partition {name}: exit={status}, bytes={count}/{size}, error={error}")
        partial.rename(final)
        result = {"source_block_device": block_device, "file": str(final), "bytes": count, "sha256": digest.hexdigest()}
        print(f"Captured {name}: {count} bytes", flush=True)
        return result
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=10)
        process.stdout.close()
        process.stderr.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    adb = shutil.which("adb")
    if not adb:
        raise RuntimeError("adb not found")
    listing = subprocess.run([adb, "devices"], capture_output=True, text=True, timeout=20)
    serials = [line.split()[0] for line in listing.stdout.splitlines() if len(line.split()) == 2 and line.split()[1] == "device"]
    matches = [serial for serial in serials if shell(adb, serial, ["getprop", "ro.product.device"]) == "PICOA8110"]
    if len(matches) != 1:
        raise RuntimeError("Expected exactly one authorized PICOA8110")
    serial = matches[0]
    fingerprint = shell(adb, serial, ["getprop", "ro.build.fingerprint"])
    if not fingerprint.startswith("Pico/Phoenix_ovs/PICOA8110:10/5.13.7/"):
        raise RuntimeError("Device no longer matches the verified 5.13.7 baseline")
    if shell(adb, serial, ["getprop", "ro.oem.state"]) != "true":
        raise RuntimeError("Device OEM state does not match SEKO baseline")
    identity = shell(adb, serial, ["su -c id"])
    if not identity.startswith("uid=0("):
        raise RuntimeError("Existing su access is not root")
    args.out.mkdir(parents=True, exist_ok=True)
    report_path = args.out / "capture.json"
    if report_path.exists():
        raise FileExistsError(f"Refusing to replace {report_path}")
    if shutil.disk_usage(args.out).free < 9 * 1024**3:
        raise RuntimeError("Insufficient free space")
    report = {
        "started_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "fingerprint": fingerprint, "oem_state": "true", "partitions": {},
        "userdata_captured": False, "device_mutations": False,
        "note": "Read from the running rooted headset. Not a complete factory recovery package or a complete device backup. boot includes current Magisk changes. Calibration partition contents are kept locally.",
    }
    for name, block_device in PARTITIONS.items():
        report["partitions"][name] = capture(adb, serial, name, block_device, args.out)
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    after = shell(adb, serial, ["getprop", "ro.build.fingerprint"])
    if after != fingerprint:
        raise RuntimeError("Device firmware changed during capture")
    report["completed_at_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(str(report_path), flush=True)


if __name__ == "__main__":
    main()
