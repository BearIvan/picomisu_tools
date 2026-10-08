"""Inspect static framework DEX classes and names of loaded VR libraries."""

import argparse
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import zipfile


PATTERN = re.compile(r"pico|pvr|pxr|openxr|seethrough", re.I)
CLASS_PATTERN = re.compile(r"/(?:pico|pvr|pxr)/|/[^/;$]*(?:Pico|Pvr|Pxr|PVR|PXR|OpenXR|Seethrough|SeeThrough)")
METHOD_PATTERN = re.compile(r"Pico|Pvr|Pxr|PVR|PXR|OpenXR|Seethrough|SeeThrough|VR|Vr(?=[A-Z]|$)|vr(?=[A-Z])|pvr|pxr")
PROCESSES = (
    "pvrtrackingservice", "pxrcontrollerservice", "pxrhmdservice",
    "pxreyetrackingservice", "pxrseethroughservice", "pxrmrsystemservice",
    "surfaceflinger", "system_server", "com.pico.xr.openxr_runtime",
)


def uleb(data, offset):
    value = shift = 0
    for _ in range(5):
        byte = data[offset]
        offset += 1
        value |= (byte & 127) << shift
        if byte < 128:
            return value, offset
        shift += 7
    raise ValueError("Invalid DEX ULEB128")


def inspect_dex(data):
    if not data.startswith(b"dex\n"):
        raise ValueError("Not a standard DEX file")
    strings_size, strings_offset = struct.unpack_from("<II", data, 56)
    types_size, types_offset = struct.unpack_from("<II", data, 64)
    methods_size, methods_offset = struct.unpack_from("<II", data, 88)
    classes_size, classes_offset = struct.unpack_from("<II", data, 96)
    strings = []
    for index in range(strings_size):
        offset = struct.unpack_from("<I", data, strings_offset + index * 4)[0]
        _, start = uleb(data, offset)
        strings.append(data[start:data.index(b"\0", start)].decode("utf-8", errors="replace"))
    types = [strings[struct.unpack_from("<I", data, types_offset + index * 4)[0]] for index in range(types_size)]
    methods = [strings[struct.unpack_from("<I", data, methods_offset + index * 8 + 4)[0]] for index in range(methods_size)]
    defined = []
    all_defined = []
    vr_methods = {}
    for index in range(classes_size):
        offset = classes_offset + index * 32
        class_index = struct.unpack_from("<I", data, offset)[0]
        name = types[class_index]
        all_defined.append(name)
        if CLASS_PATTERN.search(name) and "/-$$Lambda$" not in name:
            defined.append(name)
        class_data = struct.unpack_from("<I", data, offset + 24)[0]
        if not class_data:
            continue
        cursor = class_data
        sizes = []
        for _ in range(4):
            size, cursor = uleb(data, cursor)
            sizes.append(size)
        for _ in range(sizes[0] + sizes[1]):
            _, cursor = uleb(data, cursor)
            _, cursor = uleb(data, cursor)
        for count in sizes[2:]:
            method_index = 0
            for _ in range(count):
                difference, cursor = uleb(data, cursor)
                method_index += difference
                _, cursor = uleb(data, cursor)
                _, cursor = uleb(data, cursor)
                method_name = methods[method_index]
                if METHOD_PATTERN.search(method_name) and not method_name.startswith("lambda$"):
                    vr_methods.setdefault(name, []).append(method_name)
    return {
        "defined_class_count": classes_size,
        "all_defined_classes": sorted(all_defined),
        "defined_pico_classes": sorted(defined),
        "vr_related_declared_methods": {key: sorted(set(value)) for key, value in sorted(vr_methods.items())},
    }


def collect_maps(adb, directory):
    devices = subprocess.run([adb, "devices"], capture_output=True, text=True, timeout=20)
    serials = [line.split()[0] for line in devices.stdout.splitlines() if len(line.split()) == 2 and line.split()[1] == "device"]
    matches = []
    for serial in serials:
        value = subprocess.run([adb, "-s", serial, "shell", "getprop", "ro.product.device"], capture_output=True, text=True, timeout=20)
        if value.stdout.strip() == "PICOA8110":
            matches.append(serial)
    if len(matches) != 1:
        raise RuntimeError("Expected one authorized PICOA8110 headset")
    serial = matches[0]
    result = {}
    for name in PROCESSES:
        found = subprocess.run([adb, "-s", serial, "shell", "pidof", name], capture_output=True, text=True, timeout=20)
        pids = [int(value) for value in found.stdout.split() if value.isdigit()]
        if not pids:
            continue
        pid = pids[0]
        command = f"su -c 'cat /proc/{pid}/maps'"
        maps = subprocess.run([adb, "-s", serial, "shell", command], capture_output=True, text=True, timeout=20)
        paths = sorted({line.split()[-1] for line in maps.stdout.splitlines() if line.split() and line.split()[-1].startswith(("/system/", "/vendor/", "/apex/", "/product/"))})
        result[name] = {"pid": pid, "exit_code": maps.returncode, "paths": paths}
    (directory / "runtime-maps.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    binaries = directory / "native"
    binaries.mkdir(exist_ok=True)
    pull_paths = {"/system/bin/" + name for name in PROCESSES[:7]}
    pull_paths.update(("/system/lib64/libsurfaceflinger.so", "/system/lib64/libgui.so", "/system/lib64/libandroid_runtime.so", "/system/lib64/libservices.so"))
    pull_paths.update(path for process in result.values() for path in process["paths"] if PATTERN.search(path) and path.endswith(".so"))
    pulls = []
    for path in sorted(pull_paths):
        target = binaries / path.replace("/", "__").lstrip("_")
        pulled = subprocess.run([adb, "-s", serial, "pull", path, str(target)], capture_output=True, text=True, timeout=40)
        pulls.append({"path": path, "exit_code": pulled.returncode, "file": str(target) if pulled.returncode == 0 else None})
    (directory / "native-pulls.json").write_text(json.dumps(pulls, indent=2) + "\n", encoding="utf-8")
    return {
        "processes": {name: {"mapped_system_files": len(value["paths"]), "pico_libraries": [path for path in value["paths"] if PATTERN.search(path)]} for name, value in result.items()},
        "native_files_pulled": sum(value["exit_code"] == 0 for value in pulls),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device-dir", type=Path, default=Path(__file__).resolve().parents[1] / "reports" / "device")
    parser.add_argument("--collect-maps", action="store_true", help="Read /proc maps via existing su access and pull selected system libraries")
    args = parser.parse_args()
    frameworks = {}
    for file in sorted((args.device_dir / "static").glob("*.jar")):
        with zipfile.ZipFile(file) as archive:
            frameworks[file.name] = {name: inspect_dex(archive.read(name)) for name in archive.namelist() if name.endswith(".dex")}
    (args.device_dir / "framework-inspection.json").write_text(json.dumps(frameworks, indent=2) + "\n", encoding="utf-8")
    summary = {"frameworks": {file: {name: {"defined_classes": value["defined_class_count"], "pico_classes": len(value["defined_pico_classes"]), "examples": value["defined_pico_classes"][:8], "surface_methods": value["vr_related_declared_methods"].get("Landroid/view/Surface;", [])} for name, value in dex_files.items()} for file, dex_files in frameworks.items()}}
    if args.collect_maps:
        adb = shutil.which("adb")
        if not adb:
            raise RuntimeError("adb not found")
        summary["runtime"] = collect_maps(adb, args.device_dir)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
