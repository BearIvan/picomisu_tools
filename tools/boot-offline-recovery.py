"""Temporarily boot the verified offline recovery through the known PICO bootloader.

Only a RAM boot is requested. No partition is flashed, erased, or formatted.
"""

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


def save(state):
    (REPORT / "state.json").write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def devices(tool):
    result = subprocess.run([str(SDK / (tool + ".exe")), "devices"], capture_output=True, text=True, timeout=15, check=True)
    return [p[0] for line in result.stdout.splitlines() if len(p := line.split()) >= 2 and p[1] == ("device" if tool == "adb" else "fastboot")]


def read(tool, serial, arguments, timeout=25):
    try:
        result = subprocess.run([str(SDK / (tool + ".exe")), "-s", serial, *arguments], capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"{tool} command timed out; inspect USB state before retrying") from None
    output = (result.stdout + result.stderr).replace(serial, "<device>").strip()
    if result.returncode or "FAILED" in output:
        raise RuntimeError(output)
    return output


def getvar(serial, name):
    output = read("fastboot", serial, ["getvar", name])
    match = re.search(re.escape(name) + r":\s*([^\r\n]*)", output)
    if not match:
        raise RuntimeError("Missing fastboot variable: " + name)
    return match.group(1).strip()


def main():
    state = json.loads((REPORT / "state.json").read_text(encoding="utf-8"))
    recovery = json.loads((REPORT / "offline-recovery.json").read_text(encoding="utf-8"))
    signed = json.loads((REPORT / "offline-recovery-signed.json").read_text(encoding="utf-8"))
    image = Path(signed["path"])
    if image.stat().st_size != signed["bytes"] or hashlib.sha256(image.read_bytes()).hexdigest() != signed["sha256"]:
        raise RuntimeError("Offline recovery image changed")
    current = devices("adb")
    if current:
        if len(current) != 1 or hashlib.sha256(current[0].encode()).hexdigest() != state["device_serial_sha256"]:
            raise RuntimeError("Expected the original PICO ADB connection")
        serial = current[0]
        if read("adb", serial, ["shell", "getprop ro.product.device"]) != "PICOA8110":
            raise RuntimeError("Unexpected device")
        boot = read("adb", serial, ["shell", "su -c 'toybox sha256sum /dev/block/bootdevice/by-name/boot'"], 90).split()[0]
        if boot != state["boot_sha256"]:
            raise RuntimeError("Current boot changed; do not use the prepared AVB kit")
        read("adb", serial, ["reboot", "bootloader"])
        print("Entering the verified PICO bootloader", flush=True)
    for _ in range(30):
        current = devices("fastboot")
        if len(current) == 1:
            break
        time.sleep(2)
    else:
        raise RuntimeError("Bootloader USB did not appear")
    serial = current[0]
    if hashlib.sha256(serial.encode()).hexdigest() != state["bootloader_serial_sha256"]:
        raise RuntimeError("Bootloader identity changed")
    if getvar(serial, "product") != "kona" or getvar(serial, "unlocked") != "yes":
        raise RuntimeError("Unexpected bootloader state")
    event = {"requested_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(), "image_sha256": signed["sha256"], "partition_write": False, "status": "requested"}
    state.setdefault("temporary_boots", []).append(event)
    state["stage"] = "booting-offline-recovery"
    save(state)
    try:
        output = read("fastboot", serial, ["boot", str(image)], 45)
        print(output, flush=True)
        event["status"] = "boot-command-accepted"
    except RuntimeError as error:
        event["status"] = "boot-command-error"
        event["error"] = str(error)
        save(state)
        raise
    save(state)
    print("Waiting for temporary recovery root ADB", flush=True)
    for _ in range(60):
        current = devices("adb")
        if len(current) == 1:
            serial = current[0]
            marker = read("adb", serial, ["shell", "getprop ro.pico.recovery.offline_trial"])
            if marker != recovery["offline_marker"]:
                time.sleep(2)
                continue
            device = read("adb", serial, ["shell", "getprop ro.product.device"])
            identity = read("adb", serial, ["shell", "id -u"])
            mounts = read("adb", serial, ["shell", "cat /proc/mounts"])
            if device != "PICOA8110" or identity != "0" or any(line.split()[0].startswith("/dev/block") for line in mounts.splitlines()):
                raise RuntimeError("Offline recovery does not meet root/unmounted requirements")
            state.update({"stage": "offline-recovery-ready", "offline_adb_serial_sha256": hashlib.sha256(serial.encode()).hexdigest(), "offline_root_uid": 0, "block_backed_filesystems_mounted": False})
            event["status"] = "verified-root-adb"
            save(state)
            result = {"device": device, "root_uid": 0, "offline_marker": marker, "mounts": mounts, "partition_writes": False}
            (REPORT / "offline-boot.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
            print(json.dumps({"temporary_root_adb_verified": True, "block_filesystems_unmounted": True, "partitions_written": False}), flush=True)
            return
        time.sleep(2)
    raise RuntimeError("Temporary recovery root ADB did not appear; no partitions flashed")


if __name__ == "__main__":
    main()
