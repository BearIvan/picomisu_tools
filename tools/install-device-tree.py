"""Install the owned PICO configuration into the separate ext4 AOSP tree."""

import os
import hashlib
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
VOLUME = Path("/mnt/wsl/PHYSICALDRIVE5p3")
PROJECT = VOLUME / "home/red_panda/RedPandaAndroid/pico4-pro"
SOURCE = PROJECT / "source" / os.environ.get("PICO_SOURCE_TREE", "aosp-10")
ADDON = ROOT / "device/pico/PICOA8110"
TARGET = SOURCE / "device/pico/PICOA8110"
TREE = os.environ.get("PICO_SOURCE_TREE", "aosp-10")
REPORT = ROOT / "reports/board" / ("device-tree-installation.json" if TREE == "aosp-10" else "device-tree-installation-" + TREE + ".json")
# On the CAF tree tcmiface is built from vendor/qcom/opensource/commonsys/dpm (same module name).
CAF = TREE.startswith("caf")
# Factory product files that Source modules link against (not stored in Git).
FACTORY_PRODUCT_FILES = {
    "cryptfs_hw/factory/lib64/libcryptfs_hw.so": (
        "/lib64/libcryptfs_hw.so",
        "e695b935f63a4f15e8eee3455adbadfd47b62e78172b3c212c8e03691d4d66df"),
}
# Factory system class path JARs kept as binaries on the Source class paths
# (factory-bootclasspath.json, factory-framework/Android.bp; not stored in Git).
FACTORY_SYSTEM_FILES = {
    "factory-framework/factory/" + name + ".jar": ("/system/framework/" + name + ".jar", sha256)
    for name, sha256 in [
        ("sysmonitor-framework", "f5210d68e6d64cf856f1086b1bcdd509f7291822a44c208d2f3f45c40d600500"),
        ("sys-framework", "6d2bed55033a8b23be7f4d8ad51720f748d2cfcdb5b1cc3c399fc178f9614ac1"),
        ("devicemiddlewareimpl", "fd208b7b48dd963373bf4ff45ec2ec60219e7395c8c75f87af1051c6eb9500d4"),
        ("vrex-framework", "8dcc98da32409a588e4b481e4eda0c9549879db5242a96a69ecd61b38c4956fd"),
        ("tcmiface", "202cc0277d614d83b68ffae040c1af570c726c3b14f56fba34ae8a55e8395fc9"),
        ("QPerformance", "44c1b57b3a0571757837eeefac74c6d0ee0d61a4f740b45fb62af717ec264e90"),
        ("UxPerformance", "721bcaacb5a2a66e72f247fdbb14c377d9750f4faf07daedbe2c7ed628624327"),
        ("WfdCommon", "7ce102a3585bf6d5eddc8e8ae502f59daab3e06e91568176f6932f5860ada430"),
        ("sys-services", "fdac1687b2dc8d4a4a0f2d4d1624b70559cd4d50d87c408750744ac065e78b1f"),
        ("sysmonitor-services", "51ac945b8d822e7074e47175b36c6a9c20a8b252b425538a040f8896d0b03a79"),
        ("vrex-services", "8448e7e64a32bb4cd4a03315843a8c85692e59da8ecfe77705e25598118b2ebb"),
    ]
}
# Default Smartisan PeroptWhiteListParser lists of the factory /system/etc.
FACTORY_SYSTEM_FILES.update({
    "factory-framework/etc/" + name: ("/system/etc/" + name, sha256)
    for name, sha256 in [
        ("OptPackageWhiteList.xml", "2ccb6677541d086853517dcb6e79432486f0bcea84bb6d1b9c4284d463863425"),
        ("OptAppInfoWhiteList.xml", "3a3544958e03d7f5bc247b82bd0bbe51f7ba038cdc66648a15332e5ef6a1a160"),
        ("AppCompositionWhiteList.xml", "828c569b7bb663d0ecff7f5f748033d53985e2124e7a631df499c0c2cfa28c00"),
    ]
})
# Factory PICO libraries that Source system libraries link directly, as the factory ones do
# (factory-libs/Android.bp): libhwui/libsurfaceflinger, the audio server, libstagefright.
FACTORY_SYSTEM_FILES.update({
    "factory-libs/factory/" + path: ("/system/" + path, sha256)
    for path, sha256 in [
        ("lib/libsysperftracker.so", "409254ca297f9ab1adcc0b99d9f2c98f494bdfaec5ec8b802038846016be4678"),
        ("lib64/libsysperftracker.so", "8c766a8f83ff0ae3a82cbb85b6a5c2e54ed3b5cc480e532f5fa6f07ce6071ec0"),
        ("lib64/libaudioeventtracking.so", "e103ff7447776a985f69ea71f54a58eeebc9dc0c6032ab894c8ea4e6af676c6b"),
        ("lib/libpxrmediametrics.so", "a9f0471ae715e92e3c2b72bf081022169f2e3612e9ae9ac7af8bca02c467df8b"),
        ("lib64/libpxrmediametrics.so", "70e6ccec65b52d3d293d117007a5bb47e5a54ec6edf6a4a64e9151da909dcd42"),
        # QTI mm-parser media extractor (closed vendor/qcom/proprietary/mm-parser, not in the
        # CodeLinaro tree); media.extractor loads it from /system/lib*/extractors.
        ("lib/extractors/libmmparserextractor.so", "9c041c5bf1e637008b246cb12eb133bc7562b0bcbc76bc63699e838072c9bba4"),
        ("lib64/extractors/libmmparserextractor.so", "0ee2cf6554f11627dae09ca98d6d1ef0c588e85ee3d7481a0028a567f16dc448"),
        # QTI 3D/VR audio service library that the factory audioserver links.
        ("lib/libvraudio.so", "50db921f04d71a22773f0316fd0c1816c81663e7039e46b9b7bcf7886642d831"),
        ("lib64/libvraudio.so", "67bd8a801dbabdd2c31fa8393dddf95e1b2a3ebcb8d51ebc20a7313118a643af"),
    ]
})


def main():
    if sys.platform != "linux":
        raise RuntimeError("Run inside WSL")
    mounted = json.loads(subprocess.check_output([
        "findmnt", "--json", "--output", "FSTYPE,UUID", "--target", str(VOLUME),
    ], text=True))["filesystems"]
    if len(mounted) != 1 or mounted[0]["fstype"] != "ext4" or mounted[0]["uuid"] != "a00da05f-1eb2-44b6-99f0-9109391f67dc":
        raise RuntimeError("Expected physical ext4 volume is not mounted")
    if not (SOURCE / ".repo/manifest.xml").exists() or not TARGET.resolve().is_relative_to(SOURCE.resolve()):
        raise RuntimeError("Unexpected AOSP source/target directory")
    metadata = json.loads((ROOT / "reports/board/lp-metadata.json").read_text())
    capture = json.loads((ROOT / "reports/baseline-5.13.7/capture.json").read_text())
    current = metadata["metadata"][0]
    if not metadata["geometry"]["checksum_valid"] or not current["header_checksum_valid"] or not current["tables_checksum_valid"]:
        raise RuntimeError("LP metadata has not passed checksum verification")
    for partition in current["partitions"]:
        if capture["partitions"][partition["name"]]["bytes"] != partition["bytes"]:
            raise RuntimeError("LP layout differs from the captured factory-compatible partitions")
    previous = json.loads(REPORT.read_text()) if REPORT.exists() else {"files": {}}
    desired = {str(path.relative_to(ADDON)): path.read_bytes() for path in ADDON.rglob("*") if path.is_file()}
    if CAF:
        # CAF system/libhidl builds the real android.hidl.base@1.0 (as the factory image has);
        # the empty r47 compatibility library would be a duplicate module.
        desired = {name: data for name, data in desired.items() if not name.startswith("hidl-compat/")}
        # Context entries that the CAF platform policy (system/sepolicy and the device/qcom/sepolicy
        # directories of BOARD_PLAT_PRIVATE_SEPOLICY_DIR) already has are duplicates there (r47 lacked them).
        platform_dirs = ["system/sepolicy/private", "device/qcom/sepolicy/generic/private", "device/qcom/sepolicy/qva/private",
                         "system/sepolicy/public", "device/qcom/sepolicy/generic/public", "device/qcom/sepolicy/qva/public"]
        for name in ["genfs_contexts", "file_contexts", "property_contexts", "service_contexts", "hwservice_contexts"]:
            ours = "sepolicy/private/" + name
            if ours not in desired:
                continue
            key = (lambda line: tuple(line.split()[1:3])) if name == "genfs_contexts" else (lambda line: line.split()[0])
            entry = lambda line: line.strip() and not line.lstrip().startswith("#")
            platform = set()
            for directory in platform_dirs:
                path = SOURCE / directory / name
                if path.exists():
                    platform |= {key(line) for line in path.read_text().split("\n") if entry(line)}
            desired[ours] = "\n".join(line for line in desired[ours].decode().split("\n")
                                      if not (entry(line) and key(line) in platform)).encode()
        bp = desired["factory-framework/Android.bp"].decode()
        block = ('dex_import {\n    name: "tcmiface",\n'
                 '    jars: ["factory/tcmiface.jar"],\n}\n\n')
        if bp.count(block) != 1:
            raise RuntimeError("Unexpected factory-framework/Android.bp tcmiface block")
        desired["factory-framework/Android.bp"] = bp.replace(block, "").encode()
    for name, data in desired.items():
        path = TARGET / name
        if path.is_symlink():
            raise RuntimeError("Preserve a pre-existing source symlink: " + str(path))
        if path.exists() and path.read_bytes() != data:
            old_hash = previous["files"].get(name, {}).get("sha256")
            if hashlib.sha256(path.read_bytes()).hexdigest() != old_hash:
                raise RuntimeError("Preserve local changes in: " + str(path))
    files = {}
    for name, data in desired.items():
        path = TARGET / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        files[name] = {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
    stock = TARGET / "stock"
    stock.mkdir(exist_ok=True)
    links = {}
    for partition in ["vendor", "product", "odm"]:
        image = PROJECT / "stock/5.13.7-SEKO" / (partition + ".img")
        if not image.is_file() or image.stat().st_size != capture["partitions"][partition]["bytes"]:
            raise RuntimeError("Expected verified factory image is unavailable: " + partition)
        link = stock / image.name
        if link.is_symlink():
            if link.resolve() != image.resolve():
                raise RuntimeError("Preserve a different pre-existing stock symlink")
        elif link.exists():
            raise RuntimeError("Preserve a pre-existing stock file")
        else:
            link.symlink_to(image)
        links[partition] = {"image": str(image), "bytes": image.stat().st_size,
                            "capture_sha256": capture["partitions"][partition]["sha256"]}
    # vold links the factory product libcryptfs_hw (cryptfs_hw/Android.bp); the
    # kept factory class path JARs come from the factory system image.
    extracted = {}
    for partition, factory_files in [("product", FACTORY_PRODUCT_FILES), ("system", FACTORY_SYSTEM_FILES)]:
        image = PROJECT / "stock/5.13.7-SEKO" / (partition + ".img")
        for name, (image_path, sha256) in factory_files.items():
            if CAF and name.endswith("/tcmiface.jar"):
                continue
            out = TARGET / name
            out.parent.mkdir(parents=True, exist_ok=True)
            temporary = out.with_name(out.name + ".tmp")
            subprocess.run(["debugfs", "-R", "dump " + image_path + " " + str(temporary),
                            str(image)], check=True, capture_output=True)
            digest = hashlib.sha256(temporary.read_bytes()).hexdigest()
            if digest != sha256:
                temporary.unlink()
                raise RuntimeError("Unexpected factory " + partition + " file: " + image_path)
            if out.exists() and hashlib.sha256(out.read_bytes()).hexdigest() != sha256:
                temporary.unlink()
                raise RuntimeError("Preserve a different pre-existing file: " + str(out))
            temporary.replace(out)
            extracted[name] = {partition + "_path": image_path, "sha256": digest}
    report = {"source_root": str(SOURCE), "device_tree": str(TARGET),
              "lunch_target": "aosp_pico4pro-userdebug", "files": files, "stock_links": links,
              "factory_product_files": extracted,
              "hardware_configuration_only": True, "vr_integration_complete": False,
              "build_configuration_validated": False, "system_image_built": False}
    REPORT.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"device_tree": str(TARGET), "files_installed": len(files),
                      "lunch_target": report["lunch_target"], "vr_integration_complete": False}))


if __name__ == "__main__":
    main()
