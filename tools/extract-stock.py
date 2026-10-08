"""Reconstruct raw stock images from a full BLOCK OTA, without executing it.

Supports transfer-list v4 new/zero/erase operations. Incremental OTA commands
are rejected before writing images. Requires the brotli Python module.
"""

import argparse
from collections import Counter
import hashlib
import io
import json
from pathlib import Path
import shutil
import time
import zipfile



BLOCK = 4096


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ranges(value):
    fields = [int(field) for field in value.split(",")]
    if fields[0] != len(fields) - 1 or fields[0] % 2:
        raise ValueError("Invalid block range list")
    result = list(zip(fields[1::2], fields[2::2]))
    if any(start < 0 or end <= start for start, end in result):
        raise ValueError("Invalid block range bounds")
    return result


def transfer(archive, partition, image_size):
    lines = archive.read(f"{partition}.transfer.list").decode("ascii").splitlines()
    if lines[0] != "4" or int(lines[2]) or int(lines[3]):
        raise ValueError("Only full v4 transfer lists without stashes are supported")
    commands = []
    all_ranges = []
    for line in lines[4:]:
        if not line.strip():
            continue
        command, value = line.split()
        if command not in ("new", "zero", "erase"):
            raise ValueError(f"Incremental/unsupported command: {command}")
        blocks = ranges(value)
        if any(end * BLOCK > image_size for _, end in blocks):
            raise ValueError(f"Range exceeds {partition} logical partition size")
        commands.append((command, blocks))
        all_ranges.extend(blocks)
    ordered = sorted(all_ranges)
    if any(left[1] > right[0] for left, right in zip(ordered, ordered[1:])):
        raise ValueError("Overlapping transfer ranges are not supported")
    new_ranges = [bounds for command, blocks in commands if command == "new" for bounds in blocks]
    return commands, new_ranges


def reconstruct(archive, partition, destination, image_size):
    commands, new_ranges = transfer(archive, partition, image_size)
    expected = sum((end - start) * BLOCK for start, end in new_ranges)
    final = destination / f"{partition}.img"
    partial = destination / f"{partition}.img.partial"
    if final.exists() or partial.exists():
        raise FileExistsError(f"Refusing to overwrite image: {final}")
    import brotli  # only needed when images are reconstructed (python3-brotli)
    decompressor = brotli.Decompressor()
    index = 0
    written_in_range = 0
    total = 0
    compressed_read = 0
    compressed_size = archive.getinfo(f"{partition}.new.dat.br").file_size
    last_progress = time.monotonic()
    with partial.open("xb") as output, archive.open(f"{partition}.new.dat.br") as source:
        output.truncate(image_size)
        for chunk in iter(lambda: source.read(64 * 1024), b""):
            compressed_read += len(chunk)
            decoded = memoryview(decompressor.process(chunk))
            position = 0
            while position < len(decoded):
                if index >= len(new_ranges):
                    raise ValueError("Unexpected trailing decompressed data")
                start, end = new_ranges[index]
                remaining = (end - start) * BLOCK - written_in_range
                count = min(remaining, len(decoded) - position)
                output.seek(start * BLOCK + written_in_range)
                output.write(decoded[position:position + count])
                position += count
                written_in_range += count
                total += count
                if written_in_range == (end - start) * BLOCK:
                    index += 1
                    written_in_range = 0
            if time.monotonic() - last_progress >= 20:
                print(f"{partition}: read {compressed_read}/{compressed_size} compressed bytes, wrote {total}/{expected} data bytes", flush=True)
                last_progress = time.monotonic()
        if not decompressor.is_finished() or total != expected or index != len(new_ranges):
            raise ValueError(f"Incomplete Brotli stream/data: {total} != {expected}")
    partial.rename(final)
    result = {
        "file": str(final), "logical_size": image_size,
        "new_data_bytes": total, "sha256": sha256(final),
        "transfer_commands": dict(Counter(command for command, _ in commands)),
        "zip_entry_crc_checked": True,
        "zero_and_erase_ranges": "zero-filled in fresh image",
    }
    print(f"Completed {partition}: {result['sha256']}", flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zip", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--partitions", nargs="+", choices=("odm", "vendor", "product", "system"), default=("odm", "vendor", "product", "system"))
    parser.add_argument("--metadata-only", action="store_true", help="Extract metadata, clean boot/recovery/DTBO/vbmeta; skip large logical images")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    report_path = args.out / "extraction.json"
    if report_path.exists():
        raise FileExistsError(f"Refusing to replace extraction report: {report_path}")
    print("Computing source ZIP SHA-256...", flush=True)
    report = {"source_zip": str(args.zip.resolve()), "source_zip_bytes": args.zip.stat().st_size, "source_zip_sha256": sha256(args.zip), "images": {}}
    with zipfile.ZipFile(args.zip) as archive:
        report["zip_entries"] = [{"name": item.filename, "bytes": item.file_size, "crc32": f"{item.CRC:08x}"} for item in archive.infolist()]
        metadata = archive.read("META-INF/com/android/metadata").decode("utf-8")
        report["metadata"] = dict(line.split("=", 1) for line in metadata.splitlines() if "=" in line)
        (args.out / "ota-metadata.txt").write_text(metadata, encoding="utf-8")
        ops = archive.read("dynamic_partitions_op_list").decode("ascii")
        (args.out / "dynamic_partitions_op_list.txt").write_text(ops, encoding="utf-8")
        sizes = {fields[1]: int(fields[2]) for line in ops.splitlines() if (fields := line.split()) and fields[0] == "resize"}
        compat_dir = args.out / "compatibility"
        compat_dir.mkdir(exist_ok=True)
        with zipfile.ZipFile(io.BytesIO(archive.read("compatibility.zip"))) as compat:
            for item in compat.infolist():
                if item.filename in ("vendor_manifest.xml", "vendor_matrix.xml", "system_manifest.xml", "system_matrix.xml"):
                    (compat_dir / item.filename).write_bytes(compat.read(item))
        (args.out / "updater-script.txt").write_bytes(archive.read("META-INF/com/google/android/updater-script"))
        for name in ("boot.img", "recovery.img", "firmware-update/dtbo.img", "firmware-update/vbmeta.img", "firmware-update/vbmeta_system.img", "META-INF/com/android/otacert"):
            final = args.out / Path(name).name
            with final.open("xb") as output, archive.open(name) as source:
                shutil.copyfileobj(source, output, length=1024 * 1024)
            report["images"][name] = {"file": str(final), "bytes": final.stat().st_size, "sha256": sha256(final), "zip_entry_crc_checked": True}
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        for partition in (() if args.metadata_only else args.partitions):
            report["images"][partition] = reconstruct(archive, partition, args.out, sizes[partition])
            report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    report["all_zip_entry_crc_checked"] = False
    report["note"] = "CRC verified for entries read. OTA signature and boot on headset not verified. Images are research inputs, not a custom firmware."
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(str(report_path), flush=True)


if __name__ == "__main__":
    main()
