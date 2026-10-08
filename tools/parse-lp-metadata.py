"""Validate the bounded super metadata read using Android 10 LP structures."""

import hashlib
import json
from pathlib import Path
import re
import struct


ROOT = Path(__file__).resolve().parents[1]
BOARD = ROOT / "reports/board"
FORMAT_SOURCE = "https://github.com/aosp-mirror/platform_system_core/blob/android-10.0.0_r47/fs_mgr/liblp/include/liblp/metadata_format.h"


def valid_checksum(data, offset):
    mutable = bytearray(data)
    expected = bytes(mutable[offset:offset + 32])
    mutable[offset:offset + 32] = bytes(32)
    return hashlib.sha256(mutable).digest() == expected


def name(value):
    text = value.split(b"\0", 1)[0].decode("ascii")
    if not re.fullmatch(r"[A-Za-z0-9_]+", text):
        raise ValueError("Unexpected LP name")
    return text


def main():
    data = (BOARD / "super-first-mib.bin").read_bytes()
    if len(data) != 1048576:
        raise ValueError("Expected the bounded first MiB of super")
    geometry = data[4096:4148]
    magic, size, _, max_size, slots, block = struct.unpack("<II32sIII", geometry)
    if magic != 0x616c4467 or size != 52 or not valid_checksum(geometry, 8):
        raise ValueError("Invalid primary LP geometry")
    backup_geometry = data[8192:8244]
    if backup_geometry != geometry or not valid_checksum(backup_geometry, 8):
        raise ValueError("LP geometry backup differs")
    if not 1 <= slots <= 32 or max_size < 128 or max_size % 512 or 12288 + 2 * slots * max_size > len(data):
        raise ValueError("Metadata copies exceed the bounded input")
    capture = json.loads((ROOT / "reports/baseline-5.13.7/capture.json").read_text())
    report = {"format_source": FORMAT_SOURCE, "input_sha256": hashlib.sha256(data).hexdigest(),
              "geometry": {"magic": hex(magic), "struct_size": size, "checksum_valid": True,
                           "backup_equal": True, "max_metadata_size": max_size,
                           "metadata_slots": slots, "logical_block_size": block}, "metadata": []}
    for index in range(slots * 2):
        offset = 12288 + index * max_size
        magic, major, minor, hsize = struct.unpack_from("<IHHI", data, offset)
        if magic != 0x414c5030 or (major, minor, hsize) != (10, 0, 128):
            raise ValueError("This reader supports LP metadata 10.0 / 128-byte headers")
        header = data[offset:offset + hsize]
        tables_size = struct.unpack_from("<I", header, 44)[0]
        if hsize + tables_size > max_size:
            raise ValueError("LP tables exceed their metadata slot")
        tables = data[offset + hsize:offset + hsize + tables_size]
        if not valid_checksum(header, 12) or hashlib.sha256(tables).digest() != header[48:80]:
            raise ValueError("LP metadata header/table checksum failed")
        descriptors = [struct.unpack_from("<III", header, 80 + j * 12) for j in range(4)]
        if [d[2] for d in descriptors] != [52, 24, 48, 64]:
            raise ValueError("Unexpected LP table entry sizes")
        parsed = {"offset": offset, "slot": index % slots,
                  "copy_type": "primary" if index < slots else "backup",
                  "magic": hex(magic), "version": "10.0", "header_size": hsize,
                  "tables_size": tables_size, "header_checksum_valid": True,
                  "tables_checksum_valid": True, "descriptors": descriptors,
                  "partitions": [], "extents": [], "groups": [], "block_devices": []}
        for kind, (base, count, entry_size) in enumerate(descriptors):
            if base + count * entry_size > len(tables):
                raise ValueError("LP descriptor points outside its tables")
            for n in range(count):
                entry = tables[base + n * entry_size:base + (n + 1) * entry_size]
                if kind == 0:
                    label, attrs, first, number, group = struct.unpack("<36sIIII", entry)
                    parsed["partitions"].append({"name": name(label), "attributes": attrs,
                        "first_extent": first, "num_extents": number, "group": group})
                elif kind == 1:
                    sectors, target_type, target_sector, source = struct.unpack("<QIQI", entry)
                    parsed["extents"].append({"sectors": sectors, "target_type": target_type,
                        "target_sector": target_sector, "source": source})
                elif kind == 2:
                    label, flags, maximum = struct.unpack("<36sIQ", entry)
                    parsed["groups"].append({"name": name(label), "flags": flags, "max_bytes": maximum})
                else:
                    first, align, align_offset, total, label, flags = struct.unpack("<QIIQ36sI", entry)
                    parsed["block_devices"].append({"first_logical_sector": first, "alignment": align,
                        "alignment_offset": align_offset, "bytes": total, "name": name(label), "flags": flags})
        for partition in parsed["partitions"]:
            end = partition["first_extent"] + partition["num_extents"]
            if end > len(parsed["extents"]) or partition["group"] >= len(parsed["groups"]):
                raise ValueError("Invalid partition extent/group reference")
            partition["bytes"] = sum(e["sectors"] * 512 for e in parsed["extents"][partition["first_extent"]:end])
        parsed["matches_captured_logical_sizes"] = all(
            partition["name"] in capture["partitions"] and
            capture["partitions"][partition["name"]]["bytes"] == partition["bytes"]
            for partition in parsed["partitions"])
        report["metadata"].append(parsed)
    matches = [m["slot"] for m in report["metadata"] if m["copy_type"] == "primary" and m["matches_captured_logical_sizes"]]
    if len(matches) != 1:
        raise ValueError("Captured layout does not identify exactly one metadata slot")
    report["slot_matching_captured_layout"] = matches[0]
    report["standard_ab_boot_scheme_proven"] = False
    (BOARD / "lp-metadata.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"all_metadata_checksums_valid": True, "slots": slots,
                      "slot_matching_capture": matches[0], "standard_ab_boot_scheme_proven": False}))


if __name__ == "__main__":
    main()
