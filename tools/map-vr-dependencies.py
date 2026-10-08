"""Map factory ELF DT_NEEDED edges against observed PICO process mappings.

Read-only debugfs accesses the authenticated 5.13.7 image set. Extracted
analysis copies and APEX payloads stay on ext4; no native code is executed.
This describes factory resolution, not ABI compatibility with a new AOSP.
"""

import datetime
import hashlib
import json
from pathlib import Path
import re
import stat
import subprocess
import sys
import zipfile


ROOT = Path(__file__).resolve().parents[1]
VOLUME = Path("/mnt/wsl/PHYSICALDRIVE5p3")
PROJECT = VOLUME / "home/red_panda/RedPandaAndroid/pico4-pro"
STOCK = PROJECT / "stock/5.13.7-SEKO"
CACHE = PROJECT / "analysis/stock-5.13.7-native"
REPORT = ROOT / "reports/vr-dependencies"
SAFE = re.compile(r"^/[A-Za-z0-9_.@+/-]+$")


def debugfs(image, request):
    result = subprocess.run(["/usr/sbin/debugfs", "-R", request, str(image)],
                            capture_output=True, timeout=45)
    errors = result.stderr.decode("utf-8", "replace")
    if result.returncode or any(s in errors for s in ["File not found", "Filesystem not open", "Could not", "Bad magic"]):
        raise RuntimeError(errors)
    return result.stdout


def extract(image, inside):
    if not SAFE.fullmatch(inside):
        raise ValueError("Unsafe image filename")
    key = hashlib.sha256((str(image) + ":" + inside).encode()).hexdigest()
    target = CACHE / "objects" / (key + "__" + Path(inside).name)
    if not target.exists():
        debugfs(image, "dump " + inside + " " + str(target))
    if not target.is_file() or target.stat().st_size == 0:
        raise RuntimeError("Empty or missing extraction: " + inside)
    return target


def main():
    if sys.platform != "linux":
        raise RuntimeError("Run inside WSL")
    mounted = json.loads(subprocess.check_output([
        "findmnt", "--json", "--output", "FSTYPE,UUID", "--target", str(VOLUME),
    ], text=True))["filesystems"]
    if len(mounted) != 1 or mounted[0]["fstype"] != "ext4" or mounted[0]["uuid"] != "a00da05f-1eb2-44b6-99f0-9109391f67dc":
        raise RuntimeError("Expected physical ext4 volume is not mounted")
    if not CACHE.resolve().is_relative_to(PROJECT.resolve()):
        raise RuntimeError("Analysis cache escapes the PICO project")
    (CACHE / "objects").mkdir(parents=True, exist_ok=True)
    (CACHE / "apex").mkdir(exist_ok=True)
    REPORT.mkdir(parents=True, exist_ok=True)
    maps = json.loads((ROOT / "reports/device/runtime-maps.json").read_text())
    seeds = sorted({path for process in maps.values() for path in process["paths"]
                    if path.endswith(".so") or "/bin/" in path})
    inventory = {}
    for partition in ["system", "vendor", "product", "odm"]:
        rows = json.loads((ROOT / "reports/baseline-5.13.7" / (partition + "-files.json")).read_text())
        for row in rows:
            if stat.S_ISREG(int(row["mode"], 8)):
                virtual = row["path"] if partition == "system" else "/" + partition + row["path"]
                inventory[virtual] = dict(row, partition=partition)
    apex = {}
    needed_apex = {path.split("/")[2] for path in seeds if path.startswith("/apex/")}
    for virtual, row in inventory.items():
        if not virtual.startswith("/system/apex/") or not virtual.endswith(".apex"):
            continue
        archive = extract(STOCK / "system.img", row["path"])
        with zipfile.ZipFile(archive) as zipped:
            manifest = json.loads(zipped.read("apex_manifest.json"))
            name = manifest["name"]
            if name not in needed_apex:
                continue
            if not re.fullmatch(r"[A-Za-z0-9_.]+", name):
                raise ValueError("Unexpected APEX package name")
            payload = CACHE / "apex" / (name + ".img")
            data = zipped.read("apex_payload.img")  # zipfile verifies CRC while reading.
            if payload.exists() and hashlib.sha256(payload.read_bytes()).digest() != hashlib.sha256(data).digest():
                raise RuntimeError("Preserve a different existing APEX payload")
            if not payload.exists():
                payload.write_bytes(data)
            apex[name] = {"image": payload, "archive": virtual,
                          "sha256": hashlib.sha256(data).hexdigest()}
    inspected = {}
    unavailable = []
    for index, virtual in enumerate(seeds, 1):
        try:
            if virtual.startswith("/apex/"):
                package = virtual.split("/")[2]
                image = apex[package]["image"]
                inside = "/" + virtual.split("/", 3)[3]
                source = {"image": str(image), "path_inside_image": inside,
                          "apex_archive": apex[package]["archive"]}
            else:
                row = inventory[virtual]
                image = STOCK / (row["partition"] + ".img")
                inside = row["path"]
                source = {"image": str(image), "path_inside_image": inside,
                          "mode": row["mode"], "uid": row["uid"], "gid": row["gid"]}
            file = extract(image, inside)
            data = file.read_bytes()
            if not data.startswith(b"\x7fELF"):
                raise ValueError("Mapped candidate is not an ELF file")
            result = subprocess.run(["readelf", "--wide", "--dynamic", str(file)],
                                    capture_output=True, text=True, timeout=30)
            if result.returncode:
                raise RuntimeError(result.stderr)
            needed = re.findall(r"\(NEEDED\).*?Shared library: \[([^]]+)\]", result.stdout)
            soname = re.findall(r"\(SONAME\).*?Library soname: \[([^]]+)\]", result.stdout)
            inspected[virtual] = {"elf_class": 64 if data[4] == 2 else 32, "needed": needed,
                                  "soname": soname[0] if soname else Path(virtual).name,
                                  "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
                                  "analysis_copy": str(file), "source": source}
        except (KeyError, RuntimeError, ValueError) as error:
            unavailable.append({"path": virtual, "error": str(error)[:600]})
        if index % 50 == 0 or index == len(seeds):
            print("Factory ELF inspected:", index, "/", len(seeds), flush=True)
    factory_names = {}
    for virtual in inventory:
        if "/lib64/" in virtual and virtual.endswith(".so"):
            factory_names.setdefault(Path(virtual).name, set()).add(virtual)
    for virtual, item in inspected.items():
        if item["elf_class"] == 64 and virtual.endswith(".so"):
            for identifier in {Path(virtual).name, item["soname"]}:
                factory_names.setdefault(identifier, set()).add(virtual)
    processes = {}
    for name, process in maps.items():
        mapped = [path for path in process["paths"] if path in inspected]
        providers = {}
        for path in mapped:
            for identifier in {Path(path).name, inspected[path]["soname"]}:
                providers.setdefault(identifier, []).append(path)
        edges = []
        unresolved = []
        ambiguous = []
        for path in mapped:
            for needed in inspected[path]["needed"]:
                candidates = sorted(set(providers.get(needed, [])))
                edge = {"from": path, "needed": needed, "observed_provider_candidates": candidates,
                        "factory_64bit_path_candidates": sorted(factory_names.get(needed, []))}
                edges.append(edge)
                if not candidates:
                    unresolved.append(edge)
                elif len(candidates) > 1:
                    ambiguous.append(edge)
        processes[name] = {"mapped_elf_count": len(mapped), "dependency_edges": edges,
                           "unresolved_in_observed_map": unresolved,
                           "multiple_observed_provider_candidates": ambiguous}
    output = {
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "pico_build": "5.13.7 SEKO b9665", "source_images": str(STOCK),
        "processes": processes, "elf_files": inspected, "unavailable": unavailable,
        "apex_payloads": {name: dict(info, image=str(info["image"])) for name, info in apex.items()},
        "aosp_abi_compatibility_proven": False,
        "limitations": [
            "Only the nine previously captured process mappings are covered; lazy/dlopen paths and other Pro daemons may add dependencies.",
            "Multiple providers with one SONAME may belong to separate linker namespaces; no arbitrary provider is selected.",
            "ELF availability and DT_NEEDED edges do not establish imported-symbol/version compatibility with AOSP replacements.",
            "A captured mapping path is not a hash of the live mapped object; overlays/injection may differ from the factory file at that path.",
            "This is an analysis cache, not a validated list of binaries to ship.",
        ],
    }
    (REPORT / "factory-graph.json").write_text(json.dumps(output, indent=2) + "\n")
    summary = {"factory_elf_files": len(inspected), "unavailable_files": len(unavailable),
               "apex_payloads": sorted(apex), "processes": {name: {
                   "elf_files": value["mapped_elf_count"], "edges": len(value["dependency_edges"]),
                   "unresolved": len(value["unresolved_in_observed_map"]),
                   "ambiguous": len(value["multiple_observed_provider_candidates"]),
                   "needed_names_absent_from_factory_index": sum(not edge["factory_64bit_path_candidates"] for edge in value["dependency_edges"]),
               } for name, value in processes.items()}}
    (REPORT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
