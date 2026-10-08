"""Compare selected PICO framework method names to a pinned AOSP reference.

This is a bounded API investigation, not an ABI compatibility check or an
implementation of the PICO VR bridge. Reference sources are kept on ext4.
"""

import hashlib
import importlib.util
import json
from pathlib import Path
import re
import urllib.request
import zipfile


ROOT = Path(__file__).resolve().parents[1]
TAG = "android-10.0.0_r47"
REPO = "aosp-mirror/platform_frameworks_base"
SOURCE_ROOT = Path(r"\\wsl.localhost\Ubuntu-24.04\mnt\wsl\PHYSICALDRIVE5p3\home\red_panda\RedPandaAndroid\pico4-pro\reference\aosp-10.0.0_r47")
SOURCES = {
    "Landroid/view/Surface;": "core/java/android/view/Surface.java",
    "Landroid/view/ExtSurfaceImpl;": "core/java/android/view/Surface.java",
    "Landroid/view/ExtDisplayImpl;": "core/java/android/view/Display.java",
    "Landroid/view/ExtViewRootImplImpl;": "core/java/android/view/ViewRootImpl.java",
    "Lcom/android/server/lights/LightsService;": "services/core/java/com/android/server/lights/LightsService.java",
    "Lcom/android/server/policy/ExtPhoneWindowManagerImpl;": "services/core/java/com/android/server/policy/PhoneWindowManager.java",
    "Lcom/android/server/wm/ExtWindowManagerServiceImpl;": "services/core/java/com/android/server/wm/WindowManagerService.java",
}


def get(url):
    request = urllib.request.Request(url, headers={"User-Agent": "PICO-AOSP-bringup", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def main():
    SOURCE_ROOT.mkdir(parents=True, exist_ok=True)
    ref = json.loads(get(f"https://api.github.com/repos/{REPO}/git/ref/tags/{TAG}"))
    obj = ref["object"]
    tag_sha = obj["sha"]
    while obj["type"] == "tag":
        annotated = json.loads(get(obj["url"]))
        obj = annotated["object"]
    commit = obj["sha"]
    if obj["type"] != "commit" or not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise RuntimeError("Unexpected AOSP tag target")
    source_text = {}
    records = []
    for path in sorted(set(SOURCES.values()) | {"core/jni/android_view_Surface.cpp", "services/java/com/android/server/SystemServer.java"}):
        target = SOURCE_ROOT / path
        url = f"https://raw.githubusercontent.com/{REPO}/{commit}/{path}"
        data = get(url)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and target.read_bytes() != data:
            raise RuntimeError(f"Reference source unexpectedly changed: {target}")
        target.write_bytes(data)
        source_text[path] = data.decode()
        records.append({"path": path, "url": url, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)})
    spec = importlib.util.spec_from_file_location("pico_dex_inspection", ROOT / "tools" / "inspect-live-vr.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    candidates = {}
    for jar in sorted((ROOT / "reports" / "device" / "static").glob("*.jar")):
        with zipfile.ZipFile(jar) as archive:
            for dex in archive.namelist():
                if not dex.endswith(".dex"):
                    continue
                inspection = module.inspect_dex(archive.read(dex))
                for clazz, path in SOURCES.items():
                    if clazz not in inspection["all_defined_classes"]:
                        continue
                    names = inspection["vr_related_declared_methods"].get(clazz, [])
                    missing = [name for name in names if not re.search(r"\b" + re.escape(name) + r"\b", source_text[path])]
                    candidates[clazz] = {"factory_jar": jar.name, "dex": dex, "aosp_source_compared": path, "vr_method_names": names, "names_absent_from_compared_aosp_source": missing}
    result = {
        "reference_only_not_final_build_selection": True,
        "aosp_tag": TAG, "tag_object_sha": tag_sha, "frameworks_base_commit": commit,
        "source_repository": "https://github.com/" + REPO,
        "source_root": str(SOURCE_ROOT), "source_files": records,
        "pico_build": "5.13.7 SEKO b9665",
        "selected_classes": candidates,
        "limitations": "Only selected class/method names are compared. Method bodies, descriptors, resource IDs, JNI registration, native ABI, and runtime behavior still need analysis. This reference tag is not a claim about the original PICO source revision.",
    }
    (SOURCE_ROOT / "reference-lock.json").write_text(json.dumps(result, indent=2) + "\n")
    output = ROOT / "reports" / "framework-bridge"
    output.mkdir(parents=True, exist_ok=True)
    (output / "api-gaps.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"frameworks_base_commit": commit, "reference_files": len(records), "selected_classes": candidates}, indent=2))


if __name__ == "__main__":
    main()
