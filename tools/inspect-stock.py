"""Inspect reconstructed ext4 images with debugfs in read-only mode (WSL)."""

import argparse
import json
from pathlib import Path
import re
import stat
import subprocess


PICO = re.compile(r"pico|pvr|pxr|openxr|seethrough|tracking|slam|eyed|facial|qvr|sxr|gd32", re.I)
SAFE_PATH = re.compile(r"^/[A-Za-z0-9_.@+/-]+$")


def read_request(image, request):
    result = subprocess.run(["/usr/sbin/debugfs", "-R", request, str(image)], capture_output=True, timeout=90)
    if result.returncode:
        raise RuntimeError(result.stderr.decode(errors="replace"))
    errors = result.stderr.decode(errors="replace")
    if any(value in errors for value in ("File not found", "Filesystem not open", "Could not", "Bad magic")):
        raise RuntimeError(errors)
    return result.stdout


def list_files(image):
    pending = ["/"]
    result = []
    while pending:
        directory = pending.pop()
        for line in read_request(image, f"ls -p {directory}").decode(errors="replace").splitlines():
            fields = line.split("/")
            if len(fields) < 8 or not fields[1].isdigit() or not fields[2].isdigit():
                continue
            inode, mode, uid, gid, name, size = fields[1:7]
            if name in (".", ".."):
                continue
            path = directory.rstrip("/") + "/" + name
            if not SAFE_PATH.fullmatch(path):
                raise ValueError(f"Unsupported filename: {path!r}")
            mode_int = int(mode, 8)
            result.append({"path": path, "inode": int(inode), "mode": mode, "uid": int(uid), "gid": int(gid), "bytes": int(size or 0)})
            if stat.S_ISDIR(mode_int) and name != "lost+found":
                pending.append(path)
    return sorted(result, key=lambda value: value["path"])


def inspect(image, output, partition):
    files = list_files(image)
    (output / f"{partition}-files.json").write_text(json.dumps(files, indent=2) + "\n", encoding="utf-8")
    (output / f"{partition}-files.txt").write_text("\n".join(value["path"] for value in files) + "\n", encoding="utf-8")
    selected = []
    for value in files:
        path = value["path"]
        mode = int(value["mode"], 8)
        if not stat.S_ISREG(mode):
            continue
        wanted = (
            path.endswith(("/build.prop", "/default.prop", "/prop.default"))
            or (path.endswith(".rc") and PICO.search(path))
            or ("/etc/" in path and path.endswith(".xml") and PICO.search(path))
            or path.endswith(("/fstab.qcom", "/fstab.kona"))
        )
        if wanted and value["bytes"] < 2 * 1024 * 1024:
            target = output / "selected" / partition / path.lstrip("/")
            target.parent.mkdir(parents=True, exist_ok=True)
            contents = read_request(image, f"cat {path}")
            target.write_bytes(contents)
            selected.append(path)
    return {"image": str(image), "entries": len(files), "pico_paths": [value["path"] for value in files if PICO.search(value["path"])], "selected_text_files": selected}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stock", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    result = {}
    for partition in ("odm", "vendor", "product", "system"):
        result[partition] = inspect(args.stock / f"{partition}.img", args.out, partition)
        print(f"{partition}: {result[partition]['entries']} filesystem entries, {len(result[partition]['pico_paths'])} PICO/VR path matches", flush=True)
    (args.out / "stock-inspection.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
