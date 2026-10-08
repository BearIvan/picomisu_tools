"""Copy an inspected shared-storage media list and verify every copy.

Only reads the connected PICO. Does not change device files or flash anything.
The destination must be a new directory in the project's ignored outputs tree.
"""

import argparse
import datetime
import hashlib
import json
from pathlib import Path, PurePosixPath
import shlex
import shutil
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("discovery", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--adb", default=shutil.which("adb"))
    args = parser.parse_args()
    if not args.adb:
        raise RuntimeError("ADB is not available")
    outputs = (Path(__file__).resolve().parents[1] / "outputs").resolve()
    destination = args.destination.resolve()
    if destination.parent != outputs or destination.exists():
        raise RuntimeError("Destination must be a new directory directly under outputs")
    discovery = json.loads(args.discovery.read_text(encoding="utf-8"))
    rows = discovery["files"]
    if not rows:
        raise RuntimeError("No recordings in discovery report")
    total = sum(row["bytes"] for row in rows)
    if shutil.disk_usage(outputs).free < total + 512 * 1024**2:
        raise RuntimeError("Insufficient free space for recordings")

    devices = subprocess.run(
        [args.adb, "devices"], capture_output=True, text=True, check=True, timeout=20
    ).stdout.splitlines()[1:]
    authorized = [parts[0] for line in devices if len(parts := line.split()) >= 2 and parts[1] == "device"]
    if len(authorized) != 1:
        raise RuntimeError(f"Expected one authorized device, found {len(authorized)}")
    serial = authorized[0]

    def remote(command):
        result = subprocess.run(
            [args.adb, "-s", serial, "exec-out", command],
            capture_output=True, timeout=90,
        )
        if result.returncode:
            raise RuntimeError(result.stderr.decode("utf-8", errors="replace"))
        return result.stdout.decode("utf-8").strip()

    def metadata(path):
        values = remote("toybox stat -c %s:%Y " + shlex.quote(path)).split(":")
        return {"bytes": int(values[0]), "mtime_unix": int(values[1])}

    def digest(path):
        value = remote("toybox sha256sum " + shlex.quote(path)).split()[0]
        if len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
            raise RuntimeError("Unexpected remote SHA-256 output")
        return value

    if remote("getprop ro.product.device") != "PICOA8110":
        raise RuntimeError("Unexpected device")
    if remote("getprop ro.build.fingerprint") != discovery["fingerprint"]:
        raise RuntimeError("Device firmware changed since discovery")

    # Validate every path before creating the destination or copying files.
    targets = []
    used = set()
    reserved = {"CON", "PRN", "AUX", "NUL", *[f"{p}{n}" for p in ("COM", "LPT") for n in range(1, 10)]}
    for row in rows:
        source = PurePosixPath(row["remote_path"])
        relative = source.relative_to("/storage/emulated/0")
        if not relative.parts or relative.parts[0] in {"Android", "pre_resource"}:
            raise RuntimeError("Source is outside inspected media scope")
        for part in relative.parts:
            if (part in {".", ".."} or part.endswith((".", " "))
                    or any(c in '<>:"\\|?*' or ord(c) < 32 for c in part)
                    or part.split(".")[0].upper() in reserved):
                raise RuntimeError("Recording name requires explicit Windows filename mapping")
        key = relative.as_posix().casefold()
        if key in used:
            raise RuntimeError("Destination filenames collide")
        used.add(key)
        targets.append((row, destination.joinpath(*relative.parts)))

    destination.mkdir()
    manifest = {
        "created_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "device": "PICOA8110",
        "fingerprint": discovery["fingerprint"],
        "scope": "Shared-storage screen/media recordings from inspected discovery list",
        "full_userdata_backup": False,
        "source_files_modified": False,
        "all_files_verified": False,
        "files": [],
    }
    manifest_path = destination / "backup-manifest.json"

    def save_manifest():
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    save_manifest()
    for index, (row, target) in enumerate(targets, 1):
        source = row["remote_path"]
        before = metadata(source)
        if before != {key: row[key] for key in ("bytes", "mtime_unix")}:
            raise RuntimeError("Recording changed since discovery; refresh list before retrying")
        source_hash_before = digest(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        partial = target.with_name(target.name + ".partial")
        subprocess.run(
            [args.adb, "-s", serial, "pull", "-a", source, str(partial)],
            capture_output=True, check=True, timeout=180,
        )
        local_hash = hashlib.sha256()
        with partial.open("rb") as stream:
            for chunk in iter(lambda: stream.read(4 * 1024**2), b""):
                local_hash.update(chunk)
        after = metadata(source)
        source_hash_after = digest(source)
        verified = (
            before == after and partial.stat().st_size == before["bytes"]
            and source_hash_before == source_hash_after == local_hash.hexdigest()
        )
        manifest["files"].append({
            **row, "local_relative_path": target.relative_to(destination).as_posix(),
            "source_sha256_before": source_hash_before,
            "source_sha256_after": source_hash_after,
            "local_sha256": local_hash.hexdigest(), "verified": verified,
        })
        save_manifest()
        if not verified:
            raise RuntimeError("Recording changed or copy failed hash verification; partial retained")
        partial.rename(target)
        print(f"Verified recording {index}/{len(targets)} ({before['bytes']} bytes)", flush=True)

    manifest["all_files_verified"] = True
    manifest["file_count"] = len(targets)
    manifest["total_bytes"] = total
    manifest["completed_at_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    save_manifest()
    lines = [f"{row['local_sha256']}  {row['local_relative_path']}" for row in manifest["files"]]
    (destination / "SHA256SUMS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"destination": str(destination), "file_count": len(targets), "total_bytes": total, "all_files_verified": True}))


if __name__ == "__main__":
    main()
