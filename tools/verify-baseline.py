"""Independently re-read captured files and compare their size and SHA-256."""

import argparse
import hashlib
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    capture = json.loads((args.baseline / "capture.json").read_text())
    if "completed_at_utc" not in capture:
        raise RuntimeError("Capture is not complete")
    results = {}
    for name, expected in capture["partitions"].items():
        if not name.isalnum() and name != "vbmeta_system":
            raise ValueError("Unexpected partition name in report")
        file = args.baseline / f"{name}.img"
        digest = hashlib.sha256()
        with file.open("rb") as stream:
            for data in iter(lambda: stream.read(4 * 1024 * 1024), b""):
                digest.update(data)
        actual = digest.hexdigest()
        success = actual == expected["sha256"] and file.stat().st_size == expected["bytes"]
        results[name] = {"sha256": actual, "bytes": file.stat().st_size, "matches_capture": success}
        print(f"{name}: {'verified' if success else 'MISMATCH'}", flush=True)
    report = {"fingerprint": capture["fingerprint"], "independent_file_read": True, "all_match": all(value["matches_capture"] for value in results.values()), "images": results}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if not report["all_match"]:
        raise RuntimeError("Captured image verification failed")


if __name__ == "__main__":
    main()
