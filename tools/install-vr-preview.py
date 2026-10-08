"""Explicit stages for the approved three-partition PICO VR trial installation.

No erase, format, unlock, relock, slot changes, boot writes, or verity overrides.
Reads prepared reports and checks userspace fastboot before partition writes.
"""

import argparse
import datetime
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time


ROOT = Path(__file__).resolve().parents[1]
SDK = Path("C:/Users/RedPanda/AppData/Local/Android/Sdk/platform-tools")
REPORT = ROOT / "outputs/vr-preview-01-installation"
STATE = REPORT / "state.json"
PARTITIONS = ["system", "vbmeta_system", "vbmeta"]


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def save(state):
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def serial_hash(serial):
    return hashlib.sha256(serial.encode()).hexdigest()


def connected(tool):
    result = subprocess.run([str(SDK / (tool + ".exe")), "devices"], capture_output=True, text=True, timeout=15, check=True)
    lines = result.stdout.splitlines()
    return [p[0] for line in lines if len(p := line.split()) >= 2 and p[1] == ("device" if tool == "adb" else "fastboot")]


def capture(tool, serial, arguments, timeout=25):
    result = subprocess.run([str(SDK / (tool + ".exe")), "-s", serial, *arguments], capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="replace")
    output = (result.stdout + result.stderr).replace(serial, "<device>").strip()
    if result.returncode:
        raise RuntimeError(f"{tool} {' '.join(arguments)}: {output}")
    return output


def getvar(serial, name):
    output = capture("fastboot", serial, ["getvar", name])
    match = re.search(r"(?:\(bootloader\)\s*)?" + re.escape(name) + r":\s*([^\r\n]*)", output)
    if not match:
        raise RuntimeError(f"Missing fastboot variable {name}: {output}")
    return match.group(1).strip()


def fastboot_device(state):
    devices = connected("fastboot")
    if len(devices) != 1 or serial_hash(devices[0]) != state["device_serial_sha256"]:
        raise RuntimeError("Expected exactly the previously verified PICO in fastboot")
    return devices[0]


def inspect(serial, prepared):
    required = ["is-userspace", "product", "unlocked", "max-download-size"]
    required += [f"{prefix}:{part}" for part in PARTITIONS for prefix in ["partition-size", "has-slot", "is-logical"]]
    values = {name: getvar(serial, name) for name in required}
    if values["is-userspace"] != "yes" or values["unlocked"] != "yes":
        raise RuntimeError("Need unlocked userspace fastboot; no writes performed")
    if values["product"] not in {"PICOA8110", "Phoenix_ovs", "A8110"}:
        raise RuntimeError(f"Unexpected fastboot product: {values['product']}")
    for part in PARTITIONS:
        expected_size = prepared["system_expanded_bytes"] if part == "system" else 65536
        if int(values[f"partition-size:{part}"], 0) != expected_size:
            raise RuntimeError(f"Unexpected size of {part}")
        if values[f"has-slot:{part}"] != "no":
            raise RuntimeError(f"Unexpected slot layout for {part}")
    if values["is-logical:system"] != "yes":
        raise RuntimeError("system is not the expected logical partition")
    return values


def flash(serial, part, path, chunk_mb, state, scope):
    if part not in PARTITIONS:
        raise RuntimeError("Partition is outside approved scope")
    event = {"at_utc": now(), "scope": scope, "partition": part, "image": str(path), "status": "started"}
    state.setdefault("writes", []).append(event)
    save(state)
    command = [str(SDK / "fastboot.exe"), "--unbuffered", "-s", serial, "-S", f"{chunk_mb}M", "flash", part, str(path)]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
    with (REPORT / f"{scope}-{part}.log").open("x", encoding="utf-8") as log:
        for line in process.stdout:
            line = line.replace(serial, "<device>")
            log.write(line)
            log.flush()
            print(line.rstrip(), flush=True)
    status = process.wait()
    event["exit_code"] = status
    event["finished_at_utc"] = now()
    event["status"] = "success" if status == 0 else "failed"
    save(state)
    if status:
        raise RuntimeError(f"Write to {part} failed; remain in fastboot for recovery")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=["enter", "inspect", "flash", "reboot", "rollback"])
    args = parser.parse_args()
    prepared = json.loads((REPORT / "preparation.json").read_text(encoding="utf-8"))
    current = json.loads((REPORT / "current-partitions.json").read_text(encoding="utf-8"))
    if not current["matches_saved_rollback"] or prepared["approved_partition_writes"] != PARTITIONS:
        raise RuntimeError("Missing verified installation preparation")
    if args.stage == "enter":
        if STATE.exists():
            raise RuntimeError("Installation session already exists; inspect existing state")
        devices = connected("adb")
        if len(devices) != 1:
            raise RuntimeError("Expected one authorized PICO in ADB")
        serial = devices[0]
        if capture("adb", serial, ["shell", "getprop ro.product.device"]) != "PICOA8110":
            raise RuntimeError("Unexpected ADB device")
        boot = capture("adb", serial, ["shell", "su -c 'toybox sha256sum /dev/block/bootdevice/by-name/boot'"], 90).split()[0]
        if boot != prepared["current_boot_sha256"]:
            raise RuntimeError("Current boot changed")
        state = {"created_at_utc": now(), "device_serial_sha256": serial_hash(serial), "boot_sha256": boot, "stage": "entering-fastbootd", "writes": [], "userdata_formatted": False, "boot_written": False}
        save(state)
        capture("adb", serial, ["reboot", "fastboot"])
        print("Requested userspace fastboot; waiting for USB", flush=True)
        for _ in range(45):
            devices = connected("fastboot")
            if len(devices) == 1:
                serial = fastboot_device(state)
                values = inspect(serial, prepared)
                state.update({"stage": "fastbootd-ready", "fastboot_vars": values, "inspected_at_utc": now()})
                save(state)
                print(json.dumps(values), flush=True)
                return
            time.sleep(2)
        raise RuntimeError("Fastboot USB did not appear within 90 seconds; no partition writes performed")

    state = json.loads(STATE.read_text(encoding="utf-8"))
    serial = fastboot_device(state)
    values = inspect(serial, prepared)
    state.update({"fastboot_vars": values, "inspected_at_utc": now()})
    save(state)
    if args.stage == "inspect":
        print(json.dumps(values), flush=True)
        return
    if args.stage == "reboot":
        if state["stage"] not in {"preview-written", "rollback-written"}:
            raise RuntimeError("Refusing normal boot without a complete verified write sequence")
        capture("fastboot", serial, ["reboot"])
        state["stage"] = "awaiting-android-boot"
        state["reboot_requested_at_utc"] = now()
        save(state)
        print("Reboot requested", flush=True)
        return
    scope = "preview" if args.stage == "flash" else "rollback"
    if scope == "preview" and state["writes"]:
        raise RuntimeError("Preview writes already attempted; do not repeat blindly")
    images = prepared[scope]
    # Recheck local bytes immediately before the write sequence.
    for part in PARTITIONS:
        row = images[part + ".img"]
        path = Path(row["path"])
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(8 * 1024**2), b""):
                digest.update(chunk)
        if path.stat().st_size != row["bytes"] or digest.hexdigest() != row["sha256"]:
            raise RuntimeError(f"Local {scope} image changed: {part}")
    chunk_mb = min(256, int(values["max-download-size"], 0) // (1024**2))
    if chunk_mb < 1:
        raise RuntimeError("Unexpected fastboot maximum download size")
    for part in PARTITIONS:
        flash(serial, part, Path(images[part + ".img"]["path"]), chunk_mb, state, scope)
    state["stage"] = "preview-written" if scope == "preview" else "rollback-written"
    state["completed_write_at_utc"] = now()
    save(state)
    print(json.dumps({"stage": state["stage"], "partitions": PARTITIONS, "userdata_formatted": False, "boot_written": False}), flush=True)


if __name__ == "__main__":
    main()
