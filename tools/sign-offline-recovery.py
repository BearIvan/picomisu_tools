"""Add a valid development AVB footer to the prepared temporary recovery.

Uses the same existing public AOSP test key as the prototype and preserves the
factory recovery rollback index. Does not change any headset partition.
Run with Python in WSL, taskset 0-7; writes only the Windows task outputs.
"""

import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

PROJECT = Path("/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid")
REPORT = Path("/mnt/c/Users/RedPanda/Documents/ChatGPT/Android/pico4-pro/outputs/vr-preview-01-installation")
AVB = PROJECT / "source/external/avb/avbtool.py"
KEY = PROJECT / "pico4-pro/source/aosp-10/external/avb/test/data/testkey_rsa4096.pem"
STOCK = REPORT.parent / "rollback-5.13.7-for-vr-preview-01/recovery.img"


def avb(*arguments):
    p = subprocess.run(["python3", str(AVB), *map(str, arguments)], capture_output=True, text=True, timeout=90)
    if p.returncode:
        raise RuntimeError(p.stderr.strip())
    return p.stdout + p.stderr


def main():
    mount = subprocess.run(["findmnt", "--json", "-o", "FSTYPE,UUID", "--target", str(PROJECT)], capture_output=True, text=True, check=True)
    device = json.loads(mount.stdout)["filesystems"][0]
    if device["fstype"] != "ext4" or device["uuid"] != "a00da05f-1eb2-44b6-99f0-9109391f67dc":
        raise RuntimeError("Unexpected build volume")
    info = avb("info_image", "--image", STOCK)
    rollback = int(re.search(r"Rollback Index:\s*(\d+)", info).group(1))
    salt = re.search(r"Salt:\s*([a-f0-9]+)", info).group(1)
    if rollback != 1:
        raise RuntimeError("Unexpected recovery rollback index")
    original = json.loads((REPORT / "offline-recovery.json").read_text())
    source = REPORT / "offline-recovery.img"
    if hashlib.sha256(source.read_bytes()).hexdigest() != original["sha256"]:
        raise RuntimeError("Temporary recovery payload changed")
    signed_dir = REPORT / "offline-signed"
    signed_dir.mkdir(exist_ok=True)
    target = signed_dir / "recovery.img"
    if target.exists():
        raise FileExistsError(target)
    shutil.copyfile(source, target)
    avb("add_hash_footer", "--image", target, "--partition_name", "recovery", "--partition_size", "104857600", "--algorithm", "SHA256_RSA4096", "--key", KEY, "--rollback_index", rollback, "--hash_algorithm", "sha256", "--salt", salt)
    verification = avb("verify_image", "--image", target, "--key", KEY)
    signed_info = avb("info_image", "--image", target)
    with target.open("rb") as stream:
        if hashlib.sha256(stream.read(original["bytes"])).hexdigest() != original["sha256"]:
            raise RuntimeError("Payload differs after adding AVB footer")
    windows_path = "C:/Users/RedPanda/Documents/ChatGPT/Android/pico4-pro/outputs/vr-preview-01-installation/offline-signed/recovery.img"
    result = {"path": windows_path, "bytes": target.stat().st_size, "sha256": hashlib.sha256(target.read_bytes()).hexdigest(), "payload_sha256": original["sha256"], "payload_bytes": original["bytes"], "valid_avb_footer": True, "avb_signature_and_hash_verified": True, "rollback_index": rollback, "development_key": "Existing public AOSP testkey_rsa4096.pem", "oem_signed": False, "headset_modified": False}
    (REPORT / "offline-recovery-signed.json").write_text(json.dumps(result, indent=2) + "\n")
    (REPORT / "offline-recovery-avb-verification.txt").write_text(verification + "\n" + signed_info)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
