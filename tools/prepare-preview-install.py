"""Verify the approved preview and prepare locally verified rollback images."""

import datetime
import hashlib
import json
from pathlib import Path
import shutil


ROOT = Path(__file__).resolve().parents[1]
PREVIEW = ROOT / "outputs/vr-preview-01"
ROLLBACK = ROOT / "outputs/rollback-5.13.7-for-vr-preview-01"
SOURCE = Path("//wsl.localhost/Ubuntu-24.04/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro/stock/5.13.7-live")
REPORT = ROOT / "outputs/vr-preview-01-installation"
EXPECTED = {
    "system.img": (5638556236, "4117436321cbc9a8c1069933e3a3eb619acb0eb749b2510f33cbffd09579dd15"),
    "vbmeta.img": (65536, "d85c4e651581c1598f9b36fa6bca3cfd434619fbf66fe076d4b4817aacc18c07"),
    "vbmeta_system.img": (65536, "ce696a78373f07499583f03fefc5d6ede3005069c00c1723ae7d8fedf7795f34"),
}


def sha256(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024**2), b""):
            result.update(chunk)
    return result.hexdigest()


def main():
    recording_manifest = ROOT / "outputs/recordings-backup-20260928-195000/backup-manifest.json"
    recordings = json.loads(recording_manifest.read_text(encoding="utf-8"))
    if not recordings["all_files_verified"] or recordings["file_count"] != 9:
        raise RuntimeError("Verified recording backup is missing")
    for row in recordings["files"]:
        file = recording_manifest.parent / row["local_relative_path"]
        if file.stat().st_size != row["bytes"] or sha256(file) != row["local_sha256"]:
            raise RuntimeError("Recording backup no longer matches")
    baseline = json.loads((ROOT / "reports/baseline-5.13.7/verification.json").read_text(encoding="utf-8"))
    verified = {}
    for name, (size, expected_hash) in EXPECTED.items():
        path = PREVIEW / name
        actual_hash = sha256(path)
        if path.stat().st_size != size or actual_hash != expected_hash:
            raise RuntimeError(f"Preview image changed: {name}")
        verified[name] = {"bytes": size, "sha256": actual_hash, "path": str(path)}
        print(f"Preview verified: {name}", flush=True)
    missing_bytes = sum(baseline["images"][Path(name).stem]["bytes"] for name in EXPECTED if not (ROLLBACK / name).exists())
    if shutil.disk_usage(ROOT).free < missing_bytes + 1024**3:
        raise RuntimeError("Insufficient Windows free space for rollback images")
    ROLLBACK.mkdir(exist_ok=True)
    rollback = {}
    for name in EXPECTED:
        expected = baseline["images"][Path(name).stem]
        target = ROLLBACK / name
        if not target.exists():
            source = SOURCE / name
            if source.stat().st_size != expected["bytes"]:
                raise RuntimeError(f"Unexpected rollback source size: {name}")
            partial = target.with_name(name + ".partial")
            if partial.exists():
                raise FileExistsError(partial)
            with source.open("rb") as reader, partial.open("xb") as writer:
                shutil.copyfileobj(reader, writer, 8 * 1024**2)
            if partial.stat().st_size != expected["bytes"] or sha256(partial) != expected["sha256"]:
                raise RuntimeError(f"Rollback copy failed verification: {name}")
            partial.rename(target)
        elif target.stat().st_size != expected["bytes"] or sha256(target) != expected["sha256"]:
            raise RuntimeError(f"Existing rollback image changed: {name}")
        rollback[name] = {"bytes": expected["bytes"], "sha256": expected["sha256"], "path": str(target)}
        print(f"Rollback verified: {name}", flush=True)
    REPORT.mkdir(exist_ok=True)
    result = {
        "prepared_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "authorization": "User approved trial installation after verified recording backup",
        "device": "PICOA8110", "preview": verified, "rollback": rollback,
        "current_boot_sha256": baseline["images"]["boot"]["sha256"],
        "system_expanded_bytes": 5704732672,
        "recordings_backup_file_count": 9,
        "recordings_backup_sha256_rechecked": True,
        "approved_partition_writes": ["system", "vbmeta_system", "vbmeta"],
        "format_userdata": False, "write_boot": False, "change_slot": False,
        "relock_bootloader": False, "disable_verity": False,
        "full_userdata_backup": False,
        "headset_partitions_modified_by_preparation": False,
        "fastbootd_access_verified": False,
    }
    (REPORT / "preparation.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (ROLLBACK / "SHA256SUMS.txt").write_text("\n".join(f"{row['sha256']}  {name}" for name, row in rollback.items()) + "\n", encoding="utf-8")
    print(json.dumps({"installation_report": str(REPORT), "rollback_prepared": True, "recordings_reverified": 9}))


if __name__ == "__main__":
    main()
