"""Update local project reports after successful factory/baseline validation."""

import json
from pathlib import Path
import shutil


root = Path(__file__).resolve().parents[1]
name = "5.13.7-202510301735-RELEASE-user-phoenix-b9665-42be801fae.zip"
download_file = root / "stock" / (name + ".verification.json")
download = json.loads(download_file.read_text())
signature = json.loads((root / "reports" / "stock-5.13.7" / "signature" / "verification.json").read_text())
baseline_check = json.loads((root / "reports" / "baseline-5.13.7" / "verification.json").read_text())
if not signature["whole_package_signature_verified"] or not signature["matches_installed_ota_trust_store"] or not baseline_check["all_match"]:
    raise RuntimeError("Final verification is incomplete")
download["whole_package_signature_verified"] = True
download["matches_installed_ota_trust_store"] = True
download["signer_cert_sha256"] = signature["signer_cert_sha256"]
download_file.write_text(json.dumps(download, indent=2) + "\n")
shutil.copyfile(download_file, root / "reports" / "stock-5.13.7" / "download-verification.json")

linux_stock = Path(r"\\wsl.localhost\Ubuntu-24.04\mnt\wsl\PHYSICALDRIVE5p3\home\red_panda\RedPandaAndroid\pico4-pro\stock")
shutil.copyfile(linux_stock / "5.13.7-live" / "capture.json", root / "reports" / "baseline-5.13.7" / "capture.json")
shutil.copyfile(linux_stock / "5.13.7-SEKO" / "extraction.json", root / "reports" / "stock-5.13.7" / "extraction.json")

profile_file = root / "device-profile.json"
profile = json.loads(profile_file.read_text())
profile["preferred_donor_firmware"] = {
    "pico_os": "5.13.7", "variant": "SEKO", "build_number": 9665,
    "source_zip": str(root / "stock" / name), "sha256": download["sha256"],
    "exact_running_build_match": True, "whole_package_signature_verified": True,
    "clean_factory_boot_available": True,
}
profile_file.write_text(json.dumps(profile, indent=2) + "\n")

verification_file = root / "reports" / "verification.json"
verification = json.loads(verification_file.read_text())
verification["downloaded_factory_ota"] = {
    "pico_os": "5.13.7", "build": 9665, "variant": "SEKO",
    "bytes": download["bytes"], "sha256": download["sha256"], "md5": download["md5"],
    "exact_running_build_match": True, "all_zip_entry_crc_checked": True,
    "whole_package_signature_verified": True,
    "signer_matches_installed_ota_trust_store": True,
    "signer_cert_sha256": signature["signer_cert_sha256"],
    "avb_verification_exit_code": 0,
    "avb_images_checked": ["boot", "dtbo", "recovery", "system", "vendor", "product", "odm"],
    "logical_image_source": "Read from the running 5.13.7; checked against factory AVB descriptors from the authenticated OTA.",
    "installed_on_headset": False,
}
verification["baseline_capture"] = {
    "all_twelve_copies_re_read_and_sha256_verified": True,
    "system_capture_method": "64 MiB reads; exact binary byte counts checked",
    "userdata_captured": False, "device_mutations": False,
    "calibration_captured_from_running_device": True, "restore_tested": False,
    "complete_device_backup": False,
}
verification_file.write_text(json.dumps(verification, indent=2) + "\n")
print(json.dumps({"download": download["file"], "whole_package_signature_verified": True, "exact_running_build_match": True, "baseline_copies_verified": len(baseline_check["images"])}, indent=2))
