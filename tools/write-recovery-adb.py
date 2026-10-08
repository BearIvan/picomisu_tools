"""Write and verify only the authorized inactive recovery using existing root.

Normal Android uses Magisk su and a unique /data/local/tmp staging file.
Offline recovery uses root directly and a unique /tmp RAM staging file.
Boot and mounted partitions are never written by this tool.
"""

import argparse
import datetime
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import uuid

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "outputs/vr-preview-01-installation"
ADB = "C:/Users/RedPanda/AppData/Local/Android/Sdk/platform-tools/adb.exe"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=["temporary", "restore"])
    args = parser.parse_args()
    state = json.loads((REPORT / "state.json").read_text(encoding="utf-8"))
    if not state.get("recovery_flash_authorized"):
        raise RuntimeError("Missing recovery flash authorization")
    row = json.loads((REPORT / ("offline-recovery-signed.json" if args.stage == "temporary" else "recovery-rollback.json")).read_text(encoding="utf-8"))
    image = Path(row["path"])
    digest = hashlib.sha256()
    with image.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024**2), b""):
            digest.update(block)
    if image.stat().st_size != 104857600 or digest.hexdigest() != row["sha256"]:
        raise RuntimeError("Recovery image failed local size/hash verification")
    p = subprocess.run([ADB, "devices"], capture_output=True, text=True, timeout=15, check=True)
    active = [v[0] for line in p.stdout.splitlines()[1:] if len(v := line.split()) >= 2 and v[1] in {"device", "recovery"}]
    allowed = {state["device_serial_sha256"], state.get("offline_adb_serial_sha256")}
    if len(active) != 1 or hashlib.sha256(active[0].encode()).hexdigest() not in allowed:
        raise RuntimeError("Expected the verified PICO ADB connection")
    serial = active[0]

    def shell(command, root=False, binary=False, timeout=90):
        if root and not offline:
            command = "su -c " + shlex.quote(command)
        result = subprocess.run([ADB, "-s", serial, "exec-out" if binary else "shell", command], capture_output=True, timeout=timeout)
        if result.returncode:
            raise RuntimeError(result.stderr.decode("utf-8", errors="replace").replace(serial, "<device>"))
        return result.stdout if binary else result.stdout.decode("utf-8").strip()

    offline = False
    marker = shell("getprop ro.pico.recovery.offline_trial")
    offline = marker == "pico-vr-offline-trial-01"
    if shell("getprop ro.product.device") != "PICOA8110" or shell("id -u", root=True) != "0":
        raise RuntimeError("Unexpected model or root unavailable")
    if not offline and shell("getprop sys.boot_completed") != "1":
        raise RuntimeError("Android is not booted for inactive recovery update")
    block = "/dev/block/bootdevice/by-name/recovery"
    real = shell("readlink -f " + block, root=True)
    mounts = shell("cat /proc/mounts", root=True)
    for line in mounts.splitlines():
        source = line.split()[0]
        if source.startswith("/dev/") and shell("readlink -f " + shlex.quote(source), root=True) == real:
            raise RuntimeError("Recovery is mounted; refuse write")
    if shell("blockdev --getsize64 " + block, root=True) != "104857600" or shell("blockdev --getro " + block, root=True) != "0":
        raise RuntimeError("Recovery size/writeability mismatch")
    if shell("toybox sha256sum /dev/block/bootdevice/by-name/boot", root=True).split()[0] != state["boot_sha256"]:
        raise RuntimeError("Boot changed since preparation")
    before = shell("toybox sha256sum " + block, root=True).split()[0]
    if args.stage == "temporary" and before != "68b368875f31aa57b4468eefbf45fa714b17f6c7091f8ea39105ca26c4db53c8":
        raise RuntimeError("Recovery is no longer the captured original")
    if args.stage == "temporary" and not (REPORT / "misc-bcb-before-recovery.bin").exists():
        message = shell("dd if=/dev/block/bootdevice/by-name/misc bs=2048 count=1 2>/dev/null", root=True, binary=True)
        if len(message) != 2048 or message[:32].split(b"\0")[0] not in {b"", b"bootonce-bootloader"}:
            raise RuntimeError("Unexpected existing boot command; preserve it before changing recovery mode")
        (REPORT / "misc-bcb-before-recovery.bin").write_bytes(message)
        state["boot_control_message_before_recovery"] = {"bytes": 2048, "sha256": hashlib.sha256(message).hexdigest(), "command": message[:32].split(b"\0")[0].decode("ascii")}
    staging = ("/tmp/" if offline else "/data/local/tmp/") + "pico-recovery-" + uuid.uuid4().hex + ".img"

    def save():
        (REPORT / "state.json").write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")

    event = {"partition": "recovery", "scope": "root-temporary-recovery" if args.stage == "temporary" else "root-restore-recovery", "at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(), "image_sha256": row["sha256"], "bytes": row["bytes"], "before_sha256": before, "status": "preparing"}
    state["writes"].append(event)
    save()
    try:
        result = subprocess.run([ADB, "-s", serial, "push", str(image), staging], capture_output=True, timeout=120)
        if result.returncode:
            raise RuntimeError(result.stderr.decode("utf-8", errors="replace"))
        if shell("toybox sha256sum " + staging, root=True).split()[0] != row["sha256"]:
            raise RuntimeError("Staged image hash mismatch")
        event["status"] = "writing"
        save()
        output = shell("dd if=" + staging + " of=" + block + " bs=4194304 conv=fsync", root=True)
        after = shell("toybox sha256sum " + block, root=True).split()[0]
        if after != row["sha256"]:
            raise RuntimeError("Recovery readback failed hash verification")
        event.update({"status": "verified", "readback_sha256": after, "dd_output": output, "finished_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat()})
        state["recovery_temporary_installed"] = args.stage == "temporary"
        state["stage"] = "temporary-recovery-written-through-root" if args.stage == "temporary" else "factory-recovery-restored-through-root"
        save()
        print(json.dumps({"recovery_write_and_readback_verified": True, "temporary_installed": state["recovery_temporary_installed"], "boot_written": False, "userdata_formatted": False}), flush=True)
    except BaseException as error:
        event.update({"status": "failed", "error": str(error)})
        save()
        raise
    finally:
        shell("rm -f " + staging, root=True)


if __name__ == "__main__":
    main()
