"""Write only system/vbmeta_system/vbmeta from the authorized offline recovery.

Checks root, no mounted storage, fixed LP geometry, binary ADB transport, and
all readback hashes. Never erases, formats, resizes, rewrites LP metadata,
changes slots, or writes boot/calibration/userdata/metadata.
"""

import argparse
import datetime
import hashlib
import io
import json
from pathlib import Path
import re
import shlex
import subprocess
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "outputs/vr-preview-01-installation"
ADB = "C:/Users/RedPanda/AppData/Local/Android/Sdk/platform-tools/adb.exe"
STATE = REPORT / "state.json"
MAPPER = "pico-vr-system"
SIZE = 5704732672
PARTITIONS = ["system", "vbmeta_system", "vbmeta"]


def stamp():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def save(state):
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def shell(serial, command, timeout=30, binary=False):
    try:
        result = subprocess.run([ADB, "-s", serial, "exec-out" if binary else "shell", command], capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise RuntimeError("ADB command timed out; inspect recovery before retrying") from None
    if result.returncode:
        raise RuntimeError(result.stderr.decode("utf-8", errors="replace").replace(serial, "<device>"))
    return result.stdout if binary else result.stdout.decode("utf-8").strip()


def root_device(state):
    result = subprocess.run([ADB, "devices"], capture_output=True, text=True, timeout=15, check=True)
    active = [p[0] for line in result.stdout.splitlines()[1:] if len(p := line.split()) >= 2 and p[1] in {"device", "recovery"}]
    if len(active) != 1 or hashlib.sha256(active[0].encode()).hexdigest() != state.get("offline_adb_serial_sha256"):
        raise RuntimeError("Expected the verified offline recovery ADB connection")
    serial = active[0]
    if shell(serial, "getprop ro.pico.recovery.offline_trial") != "pico-vr-offline-trial-01" or shell(serial, "id -u") != "0":
        raise RuntimeError("Not the expected root offline recovery")
    mounts = shell(serial, "cat /proc/mounts")
    if any(line.split()[0].startswith("/dev/") and line.split()[2] not in {"tmpfs", "devtmpfs"} for line in mounts.splitlines()):
        raise RuntimeError("A storage filesystem is mounted; do not write")
    return serial


def remote_hash(serial, path):
    value = shell(serial, "toybox sha256sum " + shlex.quote(path), timeout=180).split()[0]
    if not re.fullmatch(r"[a-f0-9]{64}", value):
        raise RuntimeError("Unexpected SHA-256 output")
    return value


def lp_guard(serial):
    expected = json.loads((ROOT / "reports/board/lp-metadata.json").read_text(encoding="utf-8"))
    data = shell(serial, "dd if=/dev/block/bootdevice/by-name/super bs=4096 count=256 2>/dev/null", binary=True)
    if len(data) != 1048576 or hashlib.sha256(data).hexdigest() != expected["input_sha256"]:
        raise RuntimeError("Super LP metadata changed; do not map or write")
    if int(shell(serial, "blockdev --getsize64 /dev/block/bootdevice/by-name/super")) != 8589934592:
        raise RuntimeError("Unexpected super partition size")
    metadata = next(v for v in expected["metadata"] if v["copy_type"] == "primary" and v["slot"] == expected["slot_matching_captured_layout"])
    part = next(v for v in metadata["partitions"] if v["name"] == "system")
    extents = metadata["extents"][part["first_extent"]:part["first_extent"] + part["num_extents"]]
    if expected["slot_matching_captured_layout"] != 0 or part["bytes"] != SIZE or extents != [{"sectors": 11142056, "target_type": 0, "target_sector": 2457536, "source": 0}]:
        raise RuntimeError("Unexpected system extent layout")
    return expected["input_sha256"]


def map_system(serial, state):
    checksum = lp_guard(serial)
    if not state.get("offline_mapping"):
        shell(serial, "dmctl create pico-vr-system linear 0 11142056 /dev/block/bootdevice/by-name/super 2457536")
        path = shell(serial, "dmctl getpath pico-vr-system")
        if not re.fullmatch(r"/dev/block/dm-[0-9]+", path):
            raise RuntimeError("Unexpected mapped block-device path")
        for _ in range(20):
            try:
                size = int(shell(serial, "blockdev --getsize64 " + path))
                break
            except (RuntimeError, ValueError):
                time.sleep(0.25)
        else:
            raise RuntimeError("Mapped node did not appear")
        if size != SIZE or shell(serial, "blockdev --getro " + path) != "0":
            raise RuntimeError("Mapped system size/writeability mismatch")
        state["offline_mapping"] = {"name": MAPPER, "path": path, "bytes": SIZE, "start_sector": 2457536, "sectors": 11142056, "super_metadata_sha256": checksum, "kernel_only_mapping": True}
        save(state)
    else:
        path = shell(serial, "dmctl getpath pico-vr-system")
        if path != state["offline_mapping"]["path"] or int(shell(serial, "blockdev --getsize64 " + path)) != SIZE:
            raise RuntimeError("Existing mapping changed")
    state["offline_mapping"]["table"] = shell(serial, "dmctl table pico-vr-system")
    save(state)
    return path


def stream_to_device(serial, reader, target, size, progress=None, verify_existing=False):
    # Windows adb shell stdin treats 0x1a as EOF in this environment.
    # Use the binary-safe sync protocol and a bounded RAM staging file instead.
    if size % 4096:
        raise RuntimeError("Expected a 4 KiB-aligned image")
    token = uuid.uuid4().hex
    local = REPORT / ("transfer-" + token + ".bin")
    remote = "/tmp/pico-transfer-" + token + ".bin"
    count, last = 0, time.monotonic()
    digest = hashlib.sha256()
    chunks = 0
    skipped = 0
    try:
        for block in iter(lambda: reader.read(64 * 1024**2), b""):
            if not block or len(block) % 4096 or count + len(block) > size:
                raise RuntimeError("Unexpected input size/alignment")
            expected = hashlib.sha256(block).hexdigest()
            if verify_existing:
                check = ("dd if=" + shlex.quote(target) + " bs=4096 skip=" + str(count // 4096)
                         + " count=" + str(len(block) // 4096) + " 2>/dev/null | toybox sha256sum")
                if shell(serial, check, timeout=120).split()[0] == expected:
                    digest.update(block)
                    count += len(block)
                    skipped += 1
                    if progress and time.monotonic() - last >= 15:
                        progress(count)
                        last = time.monotonic()
                    continue
            local.write_bytes(block)
            result = subprocess.run([ADB, "-s", serial, "push", str(local), remote], capture_output=True, timeout=120)
            if result.returncode:
                raise RuntimeError(result.stderr.decode("utf-8", errors="replace").replace(serial, "<device>"))
            if remote_hash(serial, remote) != expected:
                raise RuntimeError("RAM staging chunk failed SHA-256 verification")
            command = ("dd if=" + remote + " of=" + shlex.quote(target)
                       + " bs=4096 seek=" + str(count // 4096)
                       + " count=" + str(len(block) // 4096) + " conv=notrunc,fsync")
            shell(serial, command, timeout=120)
            digest.update(block)
            count += len(block)
            chunks += 1
            if progress and time.monotonic() - last >= 15:
                progress(count)
                last = time.monotonic()
        if count != size:
            raise RuntimeError(f"Incomplete input: {count}/{size}")
        return digest.hexdigest(), f"{chunks} adb-sync chunks written; {skipped} chunks already matched; all {count} bytes checked"
    finally:
        if local.exists():
            local.unlink()
        shell(serial, "rm -f " + remote)


def fixture(serial, state):
    path = "/tmp/pico-vr-binary-" + uuid.uuid4().hex
    payload = bytes(range(256)) * 4096
    try:
        actual, output = stream_to_device(serial, io.BytesIO(payload), path, len(payload))
        expected = hashlib.sha256(payload).hexdigest()
        if actual != expected or remote_hash(serial, path) != expected:
            raise RuntimeError("Binary ADB stdin transport corrupted the RAM fixture")
        state["offline_binary_transport"] = {"verified": True, "bytes": len(payload), "sha256": expected, "contains_all_byte_values": True, "method": "adb-push-verified-ram-chunks", "dd_output": output}
        save(state)
    finally:
        shell(serial, "rm -f " + shlex.quote(path))


def file_hash(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024**2), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=["map", "flash", "resume", "rollback"])
    args = parser.parse_args()
    state = json.loads(STATE.read_text(encoding="utf-8"))
    if not state.get("recovery_flash_authorized") or not state.get("preview_installation_authorized"):
        raise RuntimeError("Missing installation authorization")
    serial = root_device(state)
    if remote_hash(serial, "/dev/block/bootdevice/by-name/boot") != state["boot_sha256"]:
        raise RuntimeError("Boot no longer matches the verified current boot")
    target = map_system(serial, state)
    baseline = json.loads((ROOT / "reports/baseline-5.13.7/verification.json").read_text(encoding="utf-8"))["images"]
    prepared = json.loads((REPORT / "preparation.json").read_text(encoding="utf-8"))
    if args.stage == "map":
        expected = baseline["system"]["sha256"]
        if remote_hash(serial, target) != expected:
            raise RuntimeError("Mapped system does not match captured factory partition")
        for part in PARTITIONS[1:]:
            block = "/dev/block/bootdevice/by-name/" + part
            if int(shell(serial, "blockdev --getsize64 " + block)) != 65536 or remote_hash(serial, block) != baseline[part]["sha256"]:
                raise RuntimeError("Original AVB partition changed")
        fixture(serial, state)
        state["stage"] = "offline-write-preflight-passed"
        save(state)
        print("Logical system mapping, original hashes and binary ADB transport verified", flush=True)
        return

    scope = "preview" if args.stage in {"flash", "resume"} else "rollback"
    if scope == "preview":
        if args.stage == "resume":
            attempted = [v for v in state["writes"] if v.get("partition") in PARTITIONS]
            if state.get("stage") != "offline-write-failed" or not attempted or any(v["partition"] != "system" for v in attempted):
                raise RuntimeError("Resume requires the recorded interrupted system-only write")
        elif state.get("stage") != "offline-write-preflight-passed" or any(v.get("partition") in PARTITIONS for v in state["writes"]):
            raise RuntimeError("Preview preflight missing or writes already attempted")
        inputs = {"system": json.loads((REPORT / "offline-raw-system.json").read_text(encoding="utf-8")), **{name: prepared["preview"][name + ".img"] for name in PARTITIONS[1:]}}
    else:
        inputs = {name: prepared["rollback"][name + ".img"] for name in PARTITIONS}
    for part, row in inputs.items():
        image = Path(row["path"])
        if image.stat().st_size != row["bytes"] or file_hash(image) != row["sha256"]:
            raise RuntimeError("Local input image failed verification: " + part)
    if not state.get("offline_binary_transport", {}).get("verified"):
        fixture(serial, state)
    for part in PARTITIONS:
        root_device(state)
        lp_guard(serial)
        block = target if part == "system" else "/dev/block/bootdevice/by-name/" + part
        row = inputs[part]
        if int(shell(serial, "blockdev --getsize64 " + block)) != row["bytes"]:
            raise RuntimeError("Target partition size changed")
        if scope == "preview" and not (args.stage == "resume" and part == "system") and remote_hash(serial, block) != baseline[part]["sha256"]:
            raise RuntimeError("Target changed since preflight")
        event = {"partition": part, "scope": scope, "image_sha256": row["sha256"], "bytes": row["bytes"], "status": "started", "at_utc": stamp()}
        state["writes"].append(event)
        save(state)
        def progress(count):
            event["bytes_sent"] = count
            save(state)
            print(f"{part}: {count}/{row['bytes']} bytes sent", flush=True)
        try:
            with Path(row["path"]).open("rb") as reader:
                sent_hash, output = stream_to_device(serial, reader, block, row["bytes"], progress, verify_existing=args.stage == "resume")
            if sent_hash != row["sha256"]:
                raise RuntimeError("Transmitted input image changed")
            readback = remote_hash(serial, block)
            if readback != row["sha256"]:
                raise RuntimeError("Partition readback hash mismatch")
            event.update({"status": "verified", "bytes_sent": row["bytes"], "readback_sha256": readback, "dd_output": output, "finished_at_utc": stamp()})
            save(state)
            print(f"{part}: write and SHA-256 readback verified", flush=True)
        except BaseException as error:
            event.update({"status": "failed", "error": str(error)})
            state["stage"] = "offline-write-failed"
            save(state)
            raise
    shell(serial, "sync", timeout=90)
    lp_guard(serial)
    if remote_hash(serial, "/dev/block/bootdevice/by-name/boot") != state["boot_sha256"]:
        raise RuntimeError("Unexpected boot change after partition writes")
    state["stage"] = "preview-written-offline" if scope == "preview" else "factory-partitions-restored-offline"
    state["boot_preserved_after_write"] = True
    state["super_metadata_preserved_after_write"] = True
    state["userdata_formatted"] = False
    save(state)
    print(json.dumps({"stage": state["stage"], "partitions": PARTITIONS, "readback_sha256_verified": True, "boot_preserved": True, "lp_metadata_preserved": True, "userdata_formatted": False}), flush=True)


if __name__ == "__main__":
    main()
