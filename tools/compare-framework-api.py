"""Compare declared DEX classes/methods/fields in factory and built AOSP JARs.

This compares API shapes, not method bodies, resources, effective classpath
selection, JNI class registration, native object layout, or runtime behavior.
"""

import hashlib
import importlib.util
import json
from pathlib import Path
import re
import struct
import zipfile


ROOT = Path(__file__).resolve().parents[1]
BASELINE = Path(r"\\wsl.localhost\Ubuntu-24.04\mnt\wsl\PHYSICALDRIVE5p3\home\red_panda\RedPandaAndroid\pico4-pro\out\aosp-10\target\product\PICOA8110\system\framework")
REPORT = ROOT / "reports/framework-bridge"
spec = importlib.util.spec_from_file_location("pico_dex", ROOT / "tools/inspect-live-vr.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
VR = re.compile(r"pico|pvr|pxr|openxr|seethrough|(?:^|[^a-z])VR|Vr(?=[A-Z]|$)", re.I)


def declarations(data):
    if not data.startswith(b"dex\n"):
        raise ValueError("Expected standard DEX")
    strings_n, strings_at = struct.unpack_from("<II", data, 56)
    types_n, types_at = struct.unpack_from("<II", data, 64)
    _, protos_at = struct.unpack_from("<II", data, 72)
    _, fields_at = struct.unpack_from("<II", data, 80)
    _, methods_at = struct.unpack_from("<II", data, 88)
    classes_n, classes_at = struct.unpack_from("<II", data, 96)
    strings = []
    for index in range(strings_n):
        pos = struct.unpack_from("<I", data, strings_at + index * 4)[0]
        _, pos = module.uleb(data, pos)
        strings.append(data[pos:data.index(b"\0", pos)].decode("utf-8", "replace"))
    types = [strings[struct.unpack_from("<I", data, types_at + index * 4)[0]] for index in range(types_n)]

    def method_signature(index):
        owner, proto, identifier = struct.unpack_from("<HHI", data, methods_at + index * 8)
        _, returned, parameters = struct.unpack_from("<III", data, protos_at + proto * 12)
        args = ""
        if parameters:
            count = struct.unpack_from("<I", data, parameters)[0]
            args = "".join(types[struct.unpack_from("<H", data, parameters + 4 + i * 2)[0]] for i in range(count))
        return types[owner], strings[identifier] + "(" + args + ")" + types[returned]

    classes = {}
    for index in range(classes_n):
        pos = classes_at + index * 32
        type_index, access, superclass = struct.unpack_from("<III", data, pos)
        clazz = types[type_index]
        record = {"access_flags": access, "superclass": types[superclass] if superclass != 0xffffffff else None,
                  "methods": {}, "fields": {}}
        cursor = struct.unpack_from("<I", data, pos + 24)[0]
        if cursor:
            sizes = []
            for _ in range(4):
                value, cursor = module.uleb(data, cursor)
                sizes.append(value)
            for count in sizes[:2]:
                field_index = 0
                for _ in range(count):
                    delta, cursor = module.uleb(data, cursor)
                    field_index += delta
                    flags, cursor = module.uleb(data, cursor)
                    owner, field_type, identifier = struct.unpack_from("<HHI", data, fields_at + field_index * 8)
                    if types[owner] != clazz:
                        raise ValueError("Field definition owner mismatch")
                    record["fields"][strings[identifier] + ":" + types[field_type]] = flags
            for count in sizes[2:]:
                method_index = 0
                for _ in range(count):
                    delta, cursor = module.uleb(data, cursor)
                    method_index += delta
                    flags, cursor = module.uleb(data, cursor)
                    _, cursor = module.uleb(data, cursor)
                    owner, signature = method_signature(method_index)
                    if owner != clazz:
                        raise ValueError("Method definition owner mismatch")
                    record["methods"][signature] = flags
        classes[clazz] = record
    return classes


def jar_api(path):
    result = {}
    with zipfile.ZipFile(path) as archive:
        dex_files = [name for name in archive.namelist() if name.endswith(".dex")]
        if not dex_files:
            raise ValueError("Built JAR contains no DEX: " + str(path))
        for dex in dex_files:
            classes = declarations(archive.read(dex))
            if result.keys() & classes.keys():
                raise ValueError("Duplicate classes within JAR")
            result.update(classes)
    return result


def compare(factory, aosp):
    changed = {}
    for clazz in sorted(factory.keys() & aosp.keys()):
        old, new = aosp[clazz], factory[clazz]
        delta = {}
        for kind in ["methods", "fields"]:
            added = sorted(new[kind].keys() - old[kind].keys())
            removed = sorted(old[kind].keys() - new[kind].keys())
            flags = {key: {"aosp": old[kind][key], "factory": new[kind][key]}
                     for key in sorted(old[kind].keys() & new[kind].keys()) if old[kind][key] != new[kind][key]}
            if added or removed or flags:
                delta[kind] = {"added_in_factory": added, "absent_from_factory_jar": removed,
                               "access_flags_changed": flags}
        if old["superclass"] != new["superclass"]:
            delta["superclass"] = {"aosp": old["superclass"], "factory": new["superclass"]}
        if old["access_flags"] != new["access_flags"]:
            delta["class_access_flags"] = {"aosp": old["access_flags"], "factory": new["access_flags"]}
        if delta:
            changed[clazz] = delta
    added_classes = sorted(factory.keys() - aosp.keys())
    added_native = {clazz: sorted(signature for signature, flags in record["methods"].items()
                                  if flags & 0x100 and signature not in aosp.get(clazz, {}).get("methods", {}))
                    for clazz, record in factory.items()}
    return {"factory_class_count": len(factory), "aosp_class_count": len(aosp),
            "classes_added_in_factory_jar": added_classes,
            "classes_absent_from_factory_jar": sorted(aosp.keys() - factory.keys()),
            "existing_class_declaration_changes": changed,
            "added_native_declarations": {key: value for key, value in added_native.items() if value},
            "vr_named_added_classes": [clazz for clazz in added_classes if VR.search(clazz)]}


def main():
    result = {"aosp_tag": "android-10.0.0_r47", "pico_build": "5.13.7 SEKO b9665", "jars": {},
              "limitations": ["Only framework.jar and services.jar are compared, not the complete effective boot/system-server classpaths.",
                  "Class relocation to other JARs, compiler-generated members, and unrelated OEM changes may contribute to these differences.",
                  "Method bodies, interface lists, field values, resources, JNI registration and native ABI still need analysis."]}
    for name in ["framework.jar", "services.jar"]:
        original = ROOT / "reports/device/static" / ("system__framework__" + name)
        built = BASELINE / name
        compared = compare(jar_api(original), jar_api(built))
        compared["factory_sha256"] = hashlib.sha256(original.read_bytes()).hexdigest()
        compared["aosp_sha256"] = hashlib.sha256(built.read_bytes()).hexdigest()
        compared["aosp_file"] = str(built)
        result["jars"][name] = compared
    (REPORT / "full-declarations-diff.json").write_text(json.dumps(result, indent=2) + "\n")
    summary = {name: {"factory_classes": r["factory_class_count"], "aosp_classes": r["aosp_class_count"],
                      "added_classes": len(r["classes_added_in_factory_jar"]),
                      "changed_existing_class_declarations": len(r["existing_class_declaration_changes"]),
                      "added_native_declarations": sum(map(len, r["added_native_declarations"].values())),
                      "vr_named_added_classes": len(r["vr_named_added_classes"])} for name, r in result["jars"].items()}
    (REPORT / "full-declarations-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
