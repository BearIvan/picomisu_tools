"""Verify an Android whole-file OTA signature against installed public certs.

Runs in WSL with OpenSSL. Reads the archive as data. Uses -noverify for CA
validation because Android OTA trust uses pinned self-signed certs; the actual
signer certificate is independently matched to the provided otacerts.zip.
"""

import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import zipfile


def fingerprint(file):
    pem = file.read_bytes().startswith(b"-----BEGIN")
    command = ["/usr/bin/openssl", "x509", "-in", str(file), "-outform", "DER"]
    if not pem:
        command.extend(["-inform", "DER"])
    result = subprocess.run(command, capture_output=True, timeout=15)
    if result.returncode:
        raise RuntimeError("Invalid public certificate")
    return hashlib.sha256(result.stdout).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zip", type=Path, required=True)
    parser.add_argument("--trusted-certs", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    length = args.zip.stat().st_size
    with args.zip.open("rb") as stream:
        stream.seek(length - 6)
        footer = stream.read(6)
        signature_start, marker, comment_size = struct.unpack("<HHH", footer)
        if marker != 0xFFFF or signature_start < 6 or signature_start > comment_size:
            raise RuntimeError("No valid Android OTA signature footer")
        eocd_start = length - comment_size - 22
        stream.seek(eocd_start)
        eocd = stream.read(22 + comment_size)
        if eocd[:4] != b"PK\x05\x06" or struct.unpack_from("<H", eocd, 20)[0] != comment_size:
            raise RuntimeError("Malformed OTA ZIP end record")
        if b"PK\x05\x06" in eocd[4:]:
            raise RuntimeError("Duplicate ZIP end marker inside OTA signature comment")
        stream.seek(length - signature_start)
        signature = stream.read(signature_start - 6)
    signature_file = args.out / "ota-signature.der"
    signature_file.write_bytes(signature)
    signer_file = args.out / "signer.pem"
    verify = subprocess.Popen([
        "/usr/bin/openssl", "cms", "-verify", "-binary", "-inform", "DER",
        "-in", str(signature_file), "-noverify", "-content", "/dev/stdin",
        "-signer", str(signer_file), "-out", "/dev/null",
    ], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    signed_bytes = length - comment_size - 2
    try:
        with args.zip.open("rb") as stream:
            remaining = signed_bytes
            while remaining:
                data = stream.read(min(4 * 1024 * 1024, remaining))
                if not data:
                    raise RuntimeError("Truncated OTA signed content")
                verify.stdin.write(data)
                remaining -= len(data)
        verify.stdin.close()
        log = verify.stderr.read().decode(errors="replace")
        status = verify.wait(timeout=30)
        (args.out / "openssl-verification.txt").write_text(log)
        if status:
            raise RuntimeError(f"OTA CMS signature verification failed: {log}")
    finally:
        if verify.poll() is None:
            verify.terminate()
            verify.wait(timeout=10)
    signer_hash = fingerprint(signer_file)
    trusted_hashes = []
    with zipfile.ZipFile(args.trusted_certs) as archive:
        for index, name in enumerate(archive.namelist()):
            if name.endswith("/"):
                continue
            file = args.out / f"trusted-certificate-{index}.pem"
            file.write_bytes(archive.read(name))
            trusted_hashes.append({"name": name, "sha256": fingerprint(file)})
    matched = [value for value in trusted_hashes if value["sha256"] == signer_hash]
    if not matched:
        raise RuntimeError("Valid CMS signature, but signer is not trusted by captured installed firmware")
    result = {
        "file": str(args.zip), "whole_package_signature_verified": True,
        "signed_content_bytes": signed_bytes, "signer_cert_sha256": signer_hash,
        "matches_installed_ota_trust_store": True, "matching_certificates": matched,
        "trust_source": str(args.trusted_certs), "device_installed": False,
    }
    (args.out / "verification.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2), flush=True)


if __name__ == "__main__":
    main()
