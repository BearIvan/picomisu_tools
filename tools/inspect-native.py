"""Read dynamic dependencies and VR symbols from captured ELF files."""

import argparse
import json
from pathlib import Path
import re

from elftools.elf.elffile import ELFFile


VR = re.compile(r"pvr|pxr|pico|openxr|seethrough|tracking|compositor", re.I)


def inspect(path):
    with path.open("rb") as stream:
        elf = ELFFile(stream)
        dynamic = elf.get_section_by_name(".dynamic")
        symbols = elf.get_section_by_name(".dynsym")
        needed = []
        if dynamic:
            needed = [tag.needed for tag in dynamic.iter_tags() if tag.entry.d_tag == "DT_NEEDED"]
        imported = []
        exported = []
        if symbols:
            for symbol in symbols.iter_symbols():
                if symbol.name and VR.search(symbol.name):
                    (imported if symbol.entry.st_shndx == "SHN_UNDEF" else exported).append(symbol.name)
        return {
            "elf_class": elf.elfclass, "machine": elf.header.e_machine,
            "needed": needed, "vr_imports": sorted(set(imported)),
            "vr_exports": sorted(set(exported)),
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device-dir", type=Path, default=Path(__file__).resolve().parents[1] / "reports" / "device")
    args = parser.parse_args()
    results = {file.name: inspect(file) for file in sorted((args.device_dir / "native").iterdir()) if file.is_file()}
    (args.device_dir / "native-inspection.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "files_inspected": len(results),
        "tracking_service": results.get("system__bin__pvrtrackingservice"),
        "libgui_custom_surface_exports": [name for name in results.get("system__lib64__libgui.so", {}).get("vr_exports", []) if "Pvr" in name or "PVR" in name],
        "libandroid_runtime_pvr_symbols": [name for name in results.get("system__lib64__libandroid_runtime.so", {}).get("vr_exports", []) if "Pvr" in name],
        "custom_library_import_examples": {key: value["vr_imports"][:8] for key, value in results.items() if value["vr_imports"] and key in ("system__lib64__libpvrtrackingcamera.so", "system__lib64__libpxrguiex.so", "system__lib64__libpxr_xrsdk_native.so")},
    }, indent=2))


if __name__ == "__main__":
    main()
