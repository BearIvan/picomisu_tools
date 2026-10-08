"""Read selected PICO DEX signatures and candidate JNI registration tables.

Candidates found in native binaries are evidence of the registration entries,
not proof that the routines can be transplanted into another Android build.
"""

import hashlib
import importlib.util
import io
import json
from pathlib import Path
import struct
import zipfile

from elftools.elf.elffile import ELFFile
from elftools.elf.relocation import RelocationSection


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("pico_dex", ROOT / "tools/inspect-live-vr.py")
dex_utils = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dex_utils)


def selected_methods(data, selected):
    if not data.startswith(b"dex\n"):
        raise ValueError("Expected standard DEX")
    string_count, string_base = struct.unpack_from("<II", data, 56)
    type_count, type_base = struct.unpack_from("<II", data, 64)
    _, proto_base = struct.unpack_from("<II", data, 72)
    _, method_base = struct.unpack_from("<II", data, 88)
    class_count, class_base = struct.unpack_from("<II", data, 96)
    strings = []
    for index in range(string_count):
        offset = struct.unpack_from("<I", data, string_base + index * 4)[0]
        _, start = dex_utils.uleb(data, offset)
        strings.append(data[start:data.index(b"\0", start)].decode("utf-8", "replace"))
    types = [strings[struct.unpack_from("<I", data, type_base + index * 4)[0]] for index in range(type_count)]
    result = []
    for index in range(class_count):
        offset = class_base + index * 32
        clazz = types[struct.unpack_from("<I", data, offset)[0]]
        if clazz not in selected:
            continue
        cursor = struct.unpack_from("<I", data, offset + 24)[0]
        if not cursor:
            continue
        sizes = []
        for _ in range(4):
            value, cursor = dex_utils.uleb(data, cursor)
            sizes.append(value)
        for _ in range(sizes[0] + sizes[1]):
            _, cursor = dex_utils.uleb(data, cursor)
            _, cursor = dex_utils.uleb(data, cursor)
        for count in sizes[2:]:
            method_index = 0
            for _ in range(count):
                delta, cursor = dex_utils.uleb(data, cursor)
                method_index += delta
                access, cursor = dex_utils.uleb(data, cursor)
                code, cursor = dex_utils.uleb(data, cursor)
                _, proto, name_index = struct.unpack_from("<HHI", data, method_base + method_index * 8)
                name = strings[name_index]
                if name not in selected[clazz]:
                    continue
                _, returned, parameters = struct.unpack_from("<III", data, proto_base + proto * 12)
                args = ""
                if parameters:
                    size = struct.unpack_from("<I", data, parameters)[0]
                    args = "".join(types[struct.unpack_from("<H", data, parameters + 4 + i * 2)[0]] for i in range(size))
                result.append({"class": clazz, "name": name, "descriptor": "(" + args + ")" + types[returned],
                               "access_flags": hex(access), "native": bool(access & 0x100),
                               "static": bool(access & 0x8), "code_offset": code})
    return result


def candidate_tables(path, names):
    data = path.read_bytes()
    elf = ELFFile(io.BytesIO(data))
    if elf.elfclass != 64 or elf.header.e_machine != "EM_AARCH64" or not elf.little_endian:
        raise ValueError("This scanner expects an ARM64 little-endian ELF")
    segments = [s for s in elf.iter_segments() if s.header.p_type == "PT_LOAD"]

    def file_offset(address, size=1):
        for segment in segments:
            start = segment.header.p_vaddr
            if start <= address and address + size <= start + segment.header.p_filesz:
                return segment.header.p_offset + address - start
        return None

    def cstring(address):
        for segment in segments:
            start = segment.header.p_vaddr
            if start <= address < start + segment.header.p_filesz:
                offset = segment.header.p_offset + address - start
                end = data.find(b"\0", offset, min(offset + 2048, len(data)))
                if end >= offset:
                    return data[offset:end].decode("ascii", "replace")
        return None

    relative = {}
    formats = set()
    dynsym = elf.get_section_by_name(".dynsym")

    def save_relative(slot, addend):
        if slot in relative and relative[slot] != addend:
            raise ValueError("Conflicting relative relocations")
        relative[slot] = addend

    def save_relocation(slot, info, addend):
        kind = info & 0xffffffff
        if kind == 1027:  # R_AARCH64_RELATIVE
            save_relative(slot, addend)
        elif kind == 257 and dynsym is not None:  # R_AARCH64_ABS64
            symbol = dynsym.get_symbol(info >> 32)
            if symbol.entry.st_shndx != "SHN_UNDEF":
                save_relative(slot, symbol.entry.st_value + addend)

    for section in elf.iter_sections():
        if isinstance(section, RelocationSection) and section.is_RELA():
            formats.add("RELA")
            for reloc in section.iter_relocations():
                save_relocation(reloc.entry.r_offset, reloc.entry.r_info, reloc.entry.r_addend)
        elif section.name == ".relr.dyn":
            # Android 10 bionic's RELR iterator: direct slot, then 63-slot bitmaps.
            formats.add("Android RELR")
            base = 0
            slots = []
            for (entry,) in struct.iter_unpack("<Q", section.data()):
                if not entry & 1:
                    slots.append(entry)
                    base = entry + 8
                else:
                    if not base:
                        raise ValueError("RELR bitmap has no base")
                    slots.extend(base + bit * 8 for bit in range(63) if entry & (1 << (bit + 1)))
                    base += 63 * 8
            for slot in slots:
                offset = file_offset(slot, 8)
                if offset is not None:
                    save_relative(slot, struct.unpack_from("<Q", data, offset)[0])
        elif section.data().startswith(b"APS2"):
            formats.add("Android APS2")
            packed = section.data()
            cursor = 4

            def pop():
                nonlocal cursor
                value = shift = 0
                while shift < 70 and cursor < len(packed):
                    byte = packed[cursor]
                    cursor += 1
                    value |= (byte & 127) << shift
                    shift += 7
                    if not byte & 128:
                        return value - (1 << shift) if byte & 64 else value
                raise ValueError("Invalid packed SLEB128 relocation")

            count, slot = pop(), pop()
            if not 0 <= count <= 10000000:
                raise ValueError("Invalid packed relocation count")
            decoded = addend = info = 0
            while decoded < count:
                size, flags = pop(), pop()
                if not 0 < size <= count - decoded or flags & ~15:
                    raise ValueError("Invalid packed relocation group")
                delta = pop() if flags & 2 else None
                if flags & 1:
                    info = pop()
                if flags & 8 and flags & 4:
                    addend += pop()
                elif not flags & 8:
                    addend = 0
                for _ in range(size):
                    slot += delta if delta is not None else pop()
                    if not flags & 1:
                        info = pop()
                    if flags & 8 and not flags & 4:
                        addend += pop()
                    save_relocation(slot, info, addend)
                    decoded += 1
            if cursor != len(packed):
                raise ValueError("Unexpected trailing packed relocation bytes")
    entries = []
    for slot, address in sorted(relative.items()):
        name = cstring(address)
        if name not in names or slot + 8 not in relative or slot + 16 not in relative:
            continue
        descriptor = cstring(relative[slot + 8])
        if descriptor and descriptor.startswith("(") and ")" in descriptor:
            entries.append({"name": name, "descriptor": descriptor, "table_entry_vaddr": hex(slot),
                            "function_vaddr": hex(relative[slot + 16])})
    return {"file": path.name, "sha256": hashlib.sha256(data).hexdigest(),
            "relocation_formats": sorted(formats), "candidate_entries": entries}


def main():
    bridge = json.loads((ROOT / "reports/framework-bridge/api-gaps.json").read_text())
    selected = {clazz: set(value["vr_method_names"]) for clazz, value in bridge["selected_classes"].items()}
    jars = sorted({value["factory_jar"] for value in bridge["selected_classes"].values()})
    methods = []
    for name in jars:
        with zipfile.ZipFile(ROOT / "reports/device/static" / name) as archive:
            for dex in archive.namelist():
                if dex.endswith(".dex"):
                    methods.extend(dict(method, jar=name, dex=dex) for method in selected_methods(archive.read(dex), selected))
    native_names = {method["name"] for method in methods if method["native"]}
    native_dir = ROOT / "reports/device/native"
    binaries = []
    for path in sorted(native_dir.glob("*.so")):
        data = path.read_bytes()
        if any(name.encode() + b"\0" in data for name in native_names):
            binaries.append(path)
    candidates = [candidate_tables(path, native_names) for path in binaries]
    for binary in candidates:
        for entry in binary["candidate_entries"]:
            entry["matching_java_classes"] = sorted({m["class"] for m in methods
                if m["native"] and m["name"] == entry["name"] and m["descriptor"] == entry["descriptor"]})
    result = {"pico_build": "5.13.7 SEKO b9665", "selected_methods": methods,
              "native_candidates": candidates,
              "relocation_format_references": [
                  "https://github.com/aosp-mirror/platform_bionic/blob/android-10.0.0_r47/linker/linker_reloc_iterators.h",
                  "https://github.com/aosp-mirror/platform_bionic/blob/android-10.0.0_r47/linker/linker.cpp",
              ],
              "limitations": "Selected names only. Candidate table entries do not establish class registration flow, method bodies, native object layout, ABI compatibility, or behavior on a custom build."}
    (ROOT / "reports/framework-bridge/jni-signatures.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"selected_method_signatures": len(methods), "native_declarations": len(native_names),
                      "candidate_entries": candidates}, indent=2))


if __name__ == "__main__":
    main()
