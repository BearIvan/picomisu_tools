"""Guarded stages for the separately approved temporary recovery installation."""

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


def stamp():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def save(state):
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024**2), b""):
            value.update(block)
    return value.hexdigest()


def devices(tool):
    result = subprocess.run([str(SDK / (tool + ".exe")), "devices"], capture_output=True, text=True, timeout=15, check=True)
    return [p[0] for line in result.stdout.splitlines() if len(p := line.split()) >= 2 and p[1] == ("device" if tool == "adb" else "fastboot")]


def identity(serial):
    return hashlib.sha256(serial.encode()).hexdigest()


def command(tool, serial, arguments, timeout=30):
    try:
        result = subprocess.run([str(SDK / (tool + ".exe")), "-s", serial, *arguments], capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"{tool} command timed out; inspect device before retrying") from None
    output = (result.stdout + result.stderr).replace(serial, "<device>").strip()
    if result.returncode or "FAILED" in output:
        raise RuntimeError(output)
    return output


def getvar(serial, name):
    output = command("fastboot", serial, ["getvar", name])
    match = re.search(re.escape(name) + r":\s*([^\r\n]*)", output)
    if not match:
        raise RuntimeError("Missing variable: " + name)
    return match.group(1).strip()


def bootloader(state):
    active = devices("fastboot")
    if len(active) != 1 or identity(active[0]) != state["bootloader_serial_sha256"]:
        raise RuntimeError("Expected the previously verified PICO bootloader")
    serial = active[0]
    if getvar(serial, "product") != "kona" or getvar(serial, "unlocked") != "yes":
        raise RuntimeError("Unexpected bootloader state")
    if int(getvar(serial, "partition-size:recovery"), 0) != 104857600:
        raise RuntimeError("Recovery partition size changed")
    return serial


def verify_file(row):
    path = Path(row["path"])
    if path.stat().st_size != row["bytes"] or digest(path) != row["sha256"]:
        raise RuntimeError("Image failed size/hash verification: " + path.name)
    return path


def flash_recovery(serial, row, state, restoring):
    path = verify_file(row)
    label = "restore-recovery" if restoring else "temporary-recovery"
    events = state.setdefault("writes", [])
    event = {"partition": "recovery", "scope": label, "at_utc": stamp(), "image_sha256": row["sha256"], "status": "started"}
    logfile = REPORT / f"{len(events) + 1:03d}-{label}.log"
    with logfile.open("x", encoding="utf-8") as log:
        events.append(event)
        save(state)
        process = subprocess.Popen([str(SDK / "fastboot.exe"), "--unbuffered", "-s", serial, "flash", "recovery", str(path)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
        failed_line = False
        for line in process.stdout:
            line = line.replace(serial, "<device>")
            failed_line |= "FAILED" in line
            log.write(line)
            log.flush()
            print(line.rstrip(), flush=True)
        status = process.wait()
    event.update({"exit_code": status, "finished_at_utc": stamp(), "status": "success" if status == 0 and not failed_line else "failed"})
    state["recovery_temporary_installed"] = not restoring if event["status"] == "success" else state.get("recovery_temporary_installed")
    state["stage"] = ("factory-recovery-written" if restoring else "temporary-recovery-written") if event["status"] == "success" else "recovery-flash-failed"
    save(state)
    if event["status"] != "success":
        raise RuntimeError("Recovery flash failed; inspect error and restore original without unlocking or wiping")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=["enter", "flash", "restore", "recovery", "normal"])
    args = parser.parse_args()
    state = json.loads(STATE.read_text(encoding="utf-8"))
    if not state.get("recovery_flash_authorized"):
        raise RuntimeError("Separate recovery flash authorization is required")
    original = json.loads((REPORT / "recovery-rollback.json").read_text(encoding="utf-8"))
    temporary = json.loads((REPORT / "offline-recovery.json").read_text(encoding="utf-8"))
    verify_file(original)
    verify_file(temporary)
    if args.stage == "enter":
        active = devices("adb")
        allowed = {state["device_serial_sha256"], state.get("offline_adb_serial_sha256")}
        if len(active) != 1 or identity(active[0]) not in allowed:
            raise RuntimeError("Expected the known PICO in ADB")
        serial = active[0]
        if command("adb", serial, ["shell", "getprop ro.product.device"]) != "PICOA8110":
            raise RuntimeError("Unexpected model")
        marker = command("adb", serial, ["shell", "getprop ro.pico.recovery.offline_trial"])
        if marker == temporary["offline_marker"]:
            if command("adb", serial, ["shell", "id -u"]) != "0":
                raise RuntimeError("Offline recovery lost root")
            boot_command = "toybox sha256sum /dev/block/bootdevice/by-name/boot"
        else:
            boot_command = "su -c 'toybox sha256sum /dev/block/bootdevice/by-name/boot'"
        boot = command("adb", serial, ["shell", boot_command], 90).split()[0]
        if boot != state["boot_sha256"]:
            raise RuntimeError("Boot changed; preserve the new state before installing")
        command("adb", serial, ["reboot", "bootloader"])
        print("Entering the known PICO bootloader", flush=True)
        for _ in range(30):
            if devices("fastboot"):
                bootloader(state)
                state["stage"] = "bootloader-ready-for-recovery"
                save(state)
                print("Bootloader identity, unlock state and recovery size verified", flush=True)
                return
            time.sleep(2)
        raise RuntimeError("Bootloader did not appear")

    serial = bootloader(state)
    if args.stage in {"flash", "restore"}:
        if args.stage == "flash" and state.get("recovery_temporary_installed"):
            raise RuntimeError("Temporary recovery is already installed")
        flash_recovery(serial, temporary if args.stage == "flash" else original, state, args.stage == "restore")
        return
    if args.stage == "normal":
        if state.get("recovery_temporary_installed"):
            raise RuntimeError("Restore factory recovery before normal trial boot")
        output = command("fastboot", serial, ["reboot"])
        print(output, flush=True)
        state["stage"] = "awaiting-android-after-recovery-restoration"
        save(state)
        return
    if not state.get("recovery_temporary_installed"):
        raise RuntimeError("Temporary recovery has not been written")
    state["stage"] = "booting-flashed-offline-recovery"
    save(state)
    try:
        output = command("fastboot", serial, ["reboot", "recovery"], 15)
        print(output, flush=True)
    except RuntimeError as error:
        state["recovery_reboot_command_error"] = str(error)
        save(state)
        print("Checking USB after recovery reboot request", flush=True)
    fallback = False
    root_requested = False
    for _ in range(75):
        active = devices("adb")
        if len(active) == 1:
            serial = active[0]
            try:
                marker = command("adb", serial, ["shell", "getprop ro.pico.recovery.offline_trial"])
                if marker == temporary["offline_marker"]:
                    if command("adb", serial, ["shell", "getprop ro.product.device"]) != "PICOA8110":
                        raise RuntimeError("Unexpected recovery model")
                    uid = command("adb", serial, ["shell", "id -u"])
                    if uid != "0" and not root_requested:
                        print(command("adb", serial, ["root"]), flush=True)
                        root_requested = True
                        time.sleep(3)
                        continue
                    mounts = command("adb", serial, ["shell", "cat /proc/mounts"])
                    if uid != "0" or any(line.split()[0].startswith("/dev/block") for line in mounts.splitlines()):
                        raise RuntimeError("Recovery is not root or a storage filesystem is mounted")
                    state.update({"stage": "offline-recovery-ready", "offline_adb_serial_sha256": identity(serial), "offline_root_uid": 0, "block_backed_filesystems_mounted": False})
                    save(state)
                    (REPORT / "offline-boot.json").write_text(json.dumps({"verified_at_utc": stamp(), "root_uid": 0, "marker": marker, "mounts": mounts}, indent=2) + "\n", encoding="utf-8")
                    print("Temporary recovery root ADB verified; storage filesystems are unmounted", flush=True)
                    return
                if identity(serial) == state["device_serial_sha256"] and not fallback and command("adb", serial, ["shell", "getprop sys.boot_completed"]) == "1":
                    print("Recovery reboot returned Android; using target ADB reboot recovery", flush=True)
                    command("adb", serial, ["reboot", "recovery"])
                    fallback = True
                    time.sleep(8)
                    continue
            except RuntimeError as error:
                state["offline_recovery_last_probe_error"] = str(error)
                save(state)
        time.sleep(2)
    raise RuntimeError("Offline recovery root ADB did not become available; restore factory recovery")


if __name__ == "__main__":
    main()
