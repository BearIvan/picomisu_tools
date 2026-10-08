"""Download the verified PICO 5.13.7 SEKO URL using up to eight HTTP ranges.

Retains the prefix from the interrupted single-stream download and resumable
range files. Checks range headers, source ETag, final size, MD5 tag, ZIP CRC,
and exact expected headset build fingerprint. Never installs firmware.
"""

import concurrent.futures
import hashlib
import json
from pathlib import Path
import threading
import time
import urllib.request
import urllib.error
import zipfile


URL = "https://lf-stone-iot-va.dlpicovr.com/obj/stone-iot-us/5.13.7-202510301735-RELEASE-user-phoenix-b9665-42be801fae.zip"
NAME = "5.13.7-202510301735-RELEASE-user-phoenix-b9665-42be801fae.zip"
FINGERPRINT = "Pico/Phoenix_ovs/PICOA8110:10/5.13.7/smartcm.1761817909:user/dev-keys"
SIZE = 3723574018
CHUNK = 1024 * 1024


def main():
    directory = Path(__file__).resolve().parents[1] / "stock"
    directory.mkdir(exist_ok=True)
    prefix = directory / (NAME + ".partial")
    final = directory / NAME
    if final.exists():
        raise FileExistsError(f"Refusing to replace {final}")
    head = urllib.request.urlopen(urllib.request.Request(URL, method="HEAD"), timeout=30)
    if int(head.headers["Content-Length"]) != SIZE:
        raise RuntimeError("CDN object size changed")
    etag = head.headers.get("ETag")
    modified = head.headers.get("Last-Modified")
    head.close()
    parts = directory / "5.13.7-ranges"
    parts.mkdir(exist_ok=True)
    state_file = parts / "ranges.json"
    if state_file.exists():
        state = json.loads(state_file.read_text())
        if state["etag"] != etag or state["url"] != URL:
            raise RuntimeError("CDN object changed since partial download")
        prefix_size = state["prefix_bytes"]
    else:
        prefix_size = prefix.stat().st_size if prefix.exists() else 0
        state = {"url": URL, "etag": etag, "prefix_bytes": prefix_size}
        state_file.write_text(json.dumps(state, indent=2))
    if prefix_size > SIZE or (prefix_size and prefix.stat().st_size != prefix_size):
        raise RuntimeError("Single-stream prefix changed; its process must be stopped first")
    remaining = SIZE - prefix_size
    ranges = [(prefix_size + remaining * i // 8, prefix_size + remaining * (i + 1) // 8 - 1) for i in range(8)]
    progress = [0] * 8
    range_validators = [None] * 8
    progress_lock = threading.Lock()

    def download(index, start, end):
        destination = parts / f"{index}.part"
        length = end - start + 1
        if length <= 0:
            destination.touch(exist_ok=True)
            return destination
        for attempt in range(4):
            existing = destination.stat().st_size if destination.exists() else 0
            if existing > length:
                raise RuntimeError("Unexpected range file size")
            with progress_lock:
                progress[index] = existing
            if existing == length:
                return destination
            offset = start + existing
            headers = {"Range": f"bytes={offset}-{end}"}
            if etag:
                headers["If-Match"] = etag
            try:
                with urllib.request.urlopen(urllib.request.Request(URL, headers=headers), timeout=45) as response:
                    if response.status != 206 or response.headers.get("Content-Range") != f"bytes {offset}-{end}/{SIZE}":
                        raise RuntimeError("Server did not honor requested HTTP range")
                    # This CDN reports an opaque ETag for HEAD and an S3
                    # multipart ETag for some range GETs of the same object.
                    # Check modification time and exact range/total size here;
                    # final MD5, ZIP CRC, build identity and OTA signature are
                    # verified separately before using the file.
                    if modified and response.headers.get("Last-Modified") not in (None, modified):
                        raise RuntimeError("CDN modification time changed")
                    range_validators[index] = {"etag": response.headers.get("ETag"), "last_modified": response.headers.get("Last-Modified")}
                    with destination.open("ab") as output:
                        while data := response.read(CHUNK):
                            if existing + len(data) > length:
                                raise RuntimeError("Excess range data")
                            output.write(data)
                            existing += len(data)
                            with progress_lock:
                                progress[index] = existing
                if existing == length:
                    return destination
            except (OSError, urllib.error.URLError):
                if attempt == 3:
                    raise
                time.sleep(2)
        raise RuntimeError("Incomplete HTTP range")

    print(f"Continuing verified CDN object; retaining {prefix_size} bytes", flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(download, index, start, end) for index, (start, end) in enumerate(ranges)]
        while any(not future.done() for future in futures):
            concurrent.futures.wait(futures, timeout=20)
            with progress_lock:
                count = prefix_size + sum(progress)
            print(f"Downloaded {count}/{SIZE} bytes", flush=True)
        files = [future.result() for future in futures]
    assembled = directory / (NAME + ".assembling")
    if assembled.exists():
        raise FileExistsError(f"Refusing to replace {assembled}")
    sha = hashlib.sha256()
    md5 = hashlib.md5()
    with assembled.open("xb") as output:
        sources = ([prefix] if prefix_size else []) + files
        for file in sources:
            with file.open("rb") as source:
                for data in iter(lambda: source.read(4 * CHUNK), b""):
                    output.write(data)
                    sha.update(data)
                    md5.update(data)
    if assembled.stat().st_size != SIZE or not md5.hexdigest().startswith("42be801fae"):
        raise RuntimeError("Downloaded file size/MD5 tag mismatch")
    with zipfile.ZipFile(assembled) as archive:
        bad = archive.testzip()
        if bad:
            raise RuntimeError(f"ZIP CRC mismatch: {bad}")
        metadata_text = archive.read("META-INF/com/android/metadata").decode()
        metadata = dict(line.split("=", 1) for line in metadata_text.splitlines() if "=" in line)
        if metadata.get("post-build") != FINGERPRINT or metadata.get("pre-device") != "PICOA8110" or metadata.get("oem-state") != "true" or metadata.get("post-sdk-level") != "29":
            raise RuntimeError("Downloaded firmware does not match the verified headset build")
    assembled.rename(final)
    report = {"url": URL, "file": str(final), "bytes": SIZE, "head_etag": etag, "source_last_modified": modified, "http_range_validators": range_validators, "sha256": sha.hexdigest(), "md5": md5.hexdigest(), "all_zip_entry_crc_checked": True, "metadata": metadata, "exact_running_build_match": True, "installed": False, "whole_package_signature_verified": False}
    (directory / (NAME + ".verification.json")).write_text(json.dumps(report, indent=2) + "\n")
    (directory / (NAME + ".sha256")).write_text(sha.hexdigest() + "  " + NAME + "\n")
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    main()
