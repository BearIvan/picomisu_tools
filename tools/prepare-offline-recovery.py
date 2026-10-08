"""Prepare a temporary PICO recovery with root ADB and no recovery installer.

Retains the authenticated factory kernel/DTB and recovery libraries. Disables
the recovery UI process, which could interpret pending BCB commands. No image
is written to the headset by this tool. Its userdata/metadata fstab entries are
    removed; the installer also requires that no block-backed filesystems mount.
    The preferred RAM boot was rejected by this PICO bootloader. Flashing this
    image to recovery requires separate approval to expand the installation scope.
"""

import gzip
import hashlib
import json
from pathlib import Path
import re
import struct


ROOT = Path(__file__).resolve().parents[1]
PICO = Path("//wsl.localhost/Ubuntu-24.04/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro")
OUTPUT = ROOT / "outputs/vr-preview-01-installation"
MARKER = "pico-vr-offline-trial-01"


def elf(data):
    if data[:6] != b"\x7fELF\x02\x01" or struct.unpack_from("<H", data, 18)[0] != 183:
        raise RuntimeError("Expected ARM64 little-endian ELF")
    shoff = struct.unpack_from("<Q", data, 40)[0]
    entsize, count = struct.unpack_from("<HH", data, 58)
    if entsize != 64:
        raise RuntimeError("Unsupported ELF sections")
    sections = [struct.unpack_from("<IIQQQQIIQQ", data, shoff + i * entsize) for i in range(count)]
    needed, imports, exports = [], set(), set()
    for section in sections:
        strings = sections[section[6]] if section[1] in (6, 11) else None
        if strings:
            table = data[strings[4]:strings[4] + strings[5]]
        if section[1] == 6:
            for start in range(section[4], section[4] + section[5], 16):
                tag, value = struct.unpack_from("<qQ", data, start)
                if tag == 1:
                    needed.append(table[value:].split(b"\0", 1)[0].decode("ascii"))
        elif section[1] == 11:
            for start in range(section[4], section[4] + section[5], section[9]):
                name, info, _, index, _, _ = struct.unpack_from("<IBBHQQ", data, start)
                symbol = table[name:].split(b"\0", 1)[0].decode("utf-8")
                if not symbol:
                    continue
                if index == 0 and info >> 4 == 1:
                    imports.add(symbol)
                elif index != 0 and info >> 4 in (1, 2):
                    exports.add(symbol)
    return needed, imports, exports


def parse_cpio(data):
    rows, offset = [], 0
    while offset + 110 <= len(data):
        header = data[offset:offset + 110]
        if header[:6] != b"070701":
            raise RuntimeError("Expected newc recovery archive")
        fields = [int(header[6 + i * 8:14 + i * 8], 16) for i in range(13)]
        size, namesize = fields[6], fields[11]
        name = data[offset + 110:offset + 110 + namesize - 1].decode("utf-8")
        start = (offset + 110 + namesize + 3) // 4 * 4
        content = data[start:start + size]
        offset = (start + size + 3) // 4 * 4
        if name == "TRAILER!!!":
            break
        rows.append({"name": name, "fields": fields, "content": content})
    return rows


def serialize_cpio(rows):
    output = bytearray()
    for row in rows + [{"name": "TRAILER!!!", "fields": [0] * 13, "content": b""}]:
        name = row["name"].encode("utf-8") + b"\0"
        fields = list(row["fields"])
        fields[6], fields[11], fields[12] = len(row["content"]), len(name), 0
        output += b"070701" + "".join(f"{value:08x}" for value in fields).encode("ascii") + name
        output += bytes((-len(output)) % 4)
        output += row["content"]
        output += bytes((-len(output)) % 4)
    output += bytes((-len(output)) % 512)
    return bytes(output)


def main():
    factory = PICO / "stock/5.13.7-SEKO/recovery.img"
    source = factory.read_bytes()
    if hashlib.sha256(source).hexdigest() != "68b368875f31aa57b4468eefbf45fa714b17f6c7091f8ea39105ca26c4db53c8":
        raise RuntimeError("Factory recovery changed")
    header = bytearray(source[:4096])
    word = lambda offset: struct.unpack_from("<I", header, offset)[0]
    ks, rs, ss, page, version = [word(offset) for offset in (8, 16, 24, 36, 40)]
    if page != 4096 or version != 2 or ss != 0 or word(1644) != 1660:
        raise RuntimeError("Unsupported factory recovery layout")
    align = lambda value: (value + page - 1) // page * page
    kernel = source[page:page + ks]
    disk = source[page + align(ks):page + align(ks) + rs]
    dtbo_start = struct.unpack_from("<Q", header, 1636)[0]
    if dtbo_start != page + align(ks) + align(rs):
        raise RuntimeError("Unexpected recovery DTBO offset")
    dtbo = source[dtbo_start:dtbo_start + word(1632)]
    dtb_start = dtbo_start + align(len(dtbo))
    dtb = source[dtb_start:dtb_start + word(1648)]
    if len(dtbo) != word(1632) or len(dtb) != word(1648):
        raise RuntimeError("Incomplete recovery device-tree data")
    rows = parse_cpio(gzip.decompress(disk))
    by_name = {row["name"]: row for row in rows}
    original_contents = {row["name"]: hashlib.sha256(row["content"]).hexdigest() for row in rows}
    init = by_name["init.rc"]["content"].decode()
    if init.count("service recovery /system/bin/recovery\n") != 1:
        raise RuntimeError("Unexpected recovery service")
    init = init.replace("service recovery /system/bin/recovery\n", "service recovery /system/bin/recovery\n    disabled\n")
    by_name["init.rc"]["content"] = init.encode()
    props = by_name["prop.default"]["content"].decode()
    for key, value in {"ro.secure": "0", "ro.adb.secure": "0", "ro.debuggable": "1", "persist.sys.usb.config": "adb"}.items():
        props, count = re.subn(r"^" + re.escape(key) + r"=.*$", key + "=" + value, props, flags=re.MULTILINE)
        if not count:
            raise RuntimeError(f"Missing expected property {key}")
    props += "\nro.pico.recovery.offline_trial=" + MARKER + "\n"
    by_name["prop.default"]["content"] = props.encode()
    fstab = by_name["system/etc/recovery.fstab"]["content"].decode()
    protected = []
    lines = []
    for line in fstab.splitlines():
        columns = line.split()
        if columns and not line.lstrip().startswith("#") and columns[1] in {"/data", "/metadata"}:
            protected.append(columns[1])
            line = "# Disabled in RAM-only offline installer: " + line
        lines.append(line)
    if set(protected) != {"/data", "/metadata"}:
        raise RuntimeError("Unexpected data/metadata fstab")
    by_name["system/etc/recovery.fstab"]["content"] = ("\n".join(lines) + "\n").encode()

    factory_tree = PICO / "analysis/stock-5.13.7-system/root/system"
    dmctl = (factory_tree / "bin/dmctl").read_bytes()
    if hashlib.sha256(dmctl).hexdigest() != "917639b88d258c4493c22f323cb221dc8559d83afe7d3d932c16131b0016dba9":
        raise RuntimeError("Factory dmctl changed")

    def add(name, content, mode):
        row = {"name": name, "fields": [100000 + len(rows), mode, 0, 2000, 1, 0, len(content), 0, 0, 0, 0, len(name.encode()) + 1, 0], "content": content}
        rows.append(row)
        by_name[name] = row

    add("system/bin/dmctl", dmctl, 0o100755)
    closure = {"dmctl": dmctl}
    queue = ["dmctl"]
    added_libraries = []
    while queue:
        name = queue.pop()
        needed, _, _ = elf(closure[name])
        for dependency in needed:
            if dependency in closure:
                continue
            if not re.fullmatch(r"[A-Za-z0-9_.+@-]+\.so", dependency):
                raise RuntimeError("Unexpected library name")
            inside = "system/lib64/" + dependency
            if inside not in by_name:
                add(inside, (factory_tree / "lib64" / dependency).read_bytes(), 0o100644)
                added_libraries.append(dependency)
            closure[dependency] = by_name[inside]["content"]
            queue.append(dependency)
    exports = set()
    for content in closure.values():
        exports.update(elf(content)[2])
    unresolved = {name: sorted(elf(content)[1] - exports) for name, content in closure.items() if elf(content)[1] - exports}
    if unresolved:
        raise RuntimeError(f"Unresolved recovery tool imports: {unresolved}")

    new_disk = gzip.compress(serialize_cpio(rows), compresslevel=9, mtime=0)
    struct.pack_into("<I", header, 16, len(new_disk))
    struct.pack_into("<Q", header, 1636, page + align(ks) + align(len(new_disk)))
    identifier = hashlib.sha1()
    for content in (kernel, new_disk, b"", dtbo, dtb):
        identifier.update(content)
        identifier.update(struct.pack("<I", len(content)))
    header[576:608] = identifier.digest() + bytes(12)
    image = bytes(header) + kernel + bytes(align(len(kernel)) - len(kernel))
    image += new_disk + bytes(align(len(new_disk)) - len(new_disk))
    image += dtbo + bytes(align(len(dtbo)) - len(dtbo))
    image += dtb + bytes(align(len(dtb)) - len(dtb))
    changes = [row["name"] for row in rows if row["name"] not in original_contents or hashlib.sha256(row["content"]).hexdigest() != original_contents[row["name"]]]
    expected = {"init.rc", "prop.default", "system/etc/recovery.fstab", "system/bin/dmctl", *["system/lib64/" + name for name in added_libraries]}
    if set(changes) != expected:
        raise RuntimeError("Unexpected recovery archive changes")
    # Independently unpack the output header's ramdisk location.
    check = parse_cpio(gzip.decompress(image[page + align(ks):page + align(ks) + len(new_disk)]))
    if {r["name"]: r["content"] for r in check} != {r["name"]: r["content"] for r in rows}:
        raise RuntimeError("Recovery archive roundtrip differs")
    target = OUTPUT / "offline-recovery.img"
    if target.exists():
        raise FileExistsError(target)
    target.write_bytes(image)
    result = {
        "kind": "Temporary headless recovery", "path": str(target),
        "bytes": len(image), "sha256": hashlib.sha256(image).hexdigest(),
        "factory_recovery_sha256": hashlib.sha256(source).hexdigest(),
        "kernel_sha256": hashlib.sha256(kernel).hexdigest(), "dtb_sha256": hashlib.sha256(dtb).hexdigest(),
        "factory_kernel_and_dtb_preserved": True,
        "recovery_dtbo_sha256": hashlib.sha256(dtbo).hexdigest(),
        "factory_recovery_dtbo_preserved": True, "recovery_installer_service_disabled": True,
        "data_and_metadata_fstab_entries_disabled": True, "offline_marker": MARKER,
        "changed_entries": changes, "dmctl_dependencies": sorted(closure),
        "unresolved_strong_elf_imports": unresolved, "cpio_roundtrip_verified": True,
        "headset_modified": False, "partition_flash_performed": False,
        "recovery_partition_flash_requires_separate_authorization": True,
    }
    (OUTPUT / "offline-recovery.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
