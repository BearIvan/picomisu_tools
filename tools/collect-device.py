"""Read a PICO headset through ADB without changing its configuration."""

import argparse
import datetime
import json
from pathlib import Path
import shutil
import subprocess
import sys


PROPERTIES = (
    "ro.product.device", "ro.product.name", "ro.product.model",
    "ro.product.manufacturer", "ro.product.board", "ro.board.platform",
    "ro.hardware", "ro.boot.hardware", "ro.boot.hardware.sku",
    "ro.boot.product.hardware.sku", "ro.oem.state", "ro.secure_boot_tag",
    "ro.build.fingerprint", "ro.build.display.id", "ro.build.version.release",
    "ro.build.version.sdk", "ro.build.version.incremental",
    "ro.build.version.security_patch", "ro.build.date.utc", "ro.build.type",
    "ro.build.tags", "ro.product.cpu.abilist", "ro.treble.enabled",
    "ro.vndk.version", "ro.vendor.build.version.sdk",
    "ro.vendor.build.security_patch", "ro.vendor.build.fingerprint",
    "ro.product.first_api_level", "ro.boot.flash.locked",
    "ro.boot.verifiedbootstate", "ro.boot.vbmeta.device_state",
    "ro.boot.slot_suffix", "ro.build.ab_update", "ro.boot.dynamic_partitions",
    "ro.boot.dynamic_partitions_retrofit", "ro.boot.super_partition",
    "ro.bootmode", "ro.secure", "ro.debuggable", "ro.adb.secure",
)

COMMANDS = {
    "identity": ["id"],
    "kernel": ["uname", "-a"],
    "partitions": ["ls", "-l", "/dev/block/bootdevice/by-name"],
    "mounts": ["cat", "/proc/mounts"],
    "binder-services": ["service", "list"],
    "hal-services": ["lshal"],
    "system-packages": ["pm", "list", "packages", "-s", "-f"],
    "processes": ["ps", "-A", "-o", "USER,PID,NAME"],
    "vr-manager": ["dumpsys", "vrmanager"],
    "vendor-init-files": ["ls", "-l", "/vendor/etc/init"],
    "system-init-files": ["ls", "-l", "/system/etc/init"],
}


def run(adb, serial, arguments):
    return subprocess.run(
        [adb, "-s", serial, "shell", *arguments],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=30,
    )


def properties(adb, serial):
    result = run(adb, serial, ["getprop"])
    if result.returncode:
        raise RuntimeError("Unable to read properties through ADB")
    values = {}
    for line in result.stdout.splitlines():
        if line.startswith("[") and "]: [" in line and line.endswith("]"):
            key, value = line[1:-1].split("]: [", 1)
            if key in PROPERTIES:
                values[key] = value
    return values


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial")
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parents[1] / "reports" / "device")
    args = parser.parse_args()
    adb = shutil.which("adb")
    if not adb:
        raise RuntimeError("adb is not on PATH")
    result = subprocess.run([adb, "devices"], capture_output=True, text=True, timeout=20)
    candidates = [line.split()[0] for line in result.stdout.splitlines() if len(line.split()) == 2 and line.split()[1] == "device"]
    matches = []
    for serial in candidates:
        if args.serial and serial != args.serial:
            continue
        values = properties(adb, serial)
        if values.get("ro.product.device") == "PICOA8110":
            matches.append((serial, values))
    if len(matches) != 1:
        raise RuntimeError(f"Expected one authorized PICOA8110 headset; found {len(matches)}. Check USB debugging or specify --serial.")
    serial, values = matches[0]
    args.out.mkdir(parents=True, exist_ok=True)
    snapshot = {
        "collected_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "properties": values,
        "commands": {},
        "device_serial_saved": False,
        "device_mutations": False,
    }
    for name, arguments in COMMANDS.items():
        try:
            result = run(adb, serial, arguments)
            stdout = result.stdout.replace(serial, "<serial-hidden>")
            stderr = result.stderr.replace(serial, "<serial-hidden>")
            snapshot["commands"][name] = {
                "argv": arguments, "exit_code": result.returncode,
                "stdout": stdout, "stderr": stderr,
            }
            (args.out / f"{name}.txt").write_text(stdout + stderr, encoding="utf-8")
        except subprocess.TimeoutExpired:
            snapshot["commands"][name] = {"argv": arguments, "error": "timeout"}
    (args.out / "snapshot.json").write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "report": str(args.out / "snapshot.json"),
        "properties": values,
        "shell_identity": snapshot["commands"]["identity"].get("stdout", "").strip(),
        "kernel": snapshot["commands"]["kernel"].get("stdout", "").strip(),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(2)
