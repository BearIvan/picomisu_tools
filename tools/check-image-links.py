#!/usr/bin/env python3
"""Static native link checker for PICO 4 Pro (PICOA8110) Source images.

Every ARM/AArch64 ELF in the assembled system tree, in the factory vendor/product/odm
partitions and in the system APEXes is resolved the way the Android 10 bionic linker
would: DT_NEEDED through the linker namespaces of /system/etc/ld.config.29.txt (or an
APEX's own etc/ld.config.txt), device symlinks (/system/lib64/libc.so -> /apex/...),
then every undefined non-weak dynamic symbol is looked up (with GNU symbol versioning,
bionic check_symbol_version rules) in

  * closure: the BFS DT_NEEDED closure of the ELF itself (+ the linker), i.e. what a
    dlopen() of that ELF as a root sees;
  * tree:    for executables, the whole load tree of the executable (bionic local group),
    i.e. the exact set that decides "CANNOT LINK EXECUTABLE ... cannot locate symbol".

The same check runs on the factory system tree (baseline) with the same
vendor/product/odm, and findings are split into REGRESSIONS (absent from the factory)
and pre-existing factory gaps.  Exit status 1 when regressions exist.

Runs in WSL (needs unzip support from Python and debugfs from e2fsprogs to unpack the
APEX ext4 payloads).  Example (defaults are the project paths):

  python3 tools/check-image-links.py --release source-2.04 --json out.json
"""

import argparse
import collections
import hashlib
import json
import mmap
import os
import posixpath
import struct
import subprocess
import sys
import zipfile

PROJECT = "/mnt/wsl/PHYSICALDRIVE5p3/home/red_panda/RedPandaAndroid/pico4-pro"
DEFAULT_FACTORY_SYSTEM = PROJECT + "/analysis/stock-5.13.7-system/root"
DEFAULT_PARTITIONS = PROJECT + "/analysis/stock-5.13.7-partitions"

EM_ARM, EM_AARCH64 = 40, 183
PT_LOAD, PT_DYNAMIC, PT_INTERP = 1, 2, 3
DT_NULL, DT_NEEDED, DT_HASH, DT_STRTAB, DT_SYMTAB, DT_STRSZ, DT_SONAME = 0, 1, 4, 5, 6, 10, 14
DT_GNU_HASH = 0x6ffffef5
DT_VERSYM, DT_VERDEF, DT_VERDEFNUM, DT_VERNEED, DT_VERNEEDNUM = (
    0x6ffffff0, 0x6ffffffc, 0x6ffffffd, 0x6ffffffe, 0x6fffffff)
STB_GLOBAL, STB_WEAK, STB_GNU_UNIQUE = 1, 2, 10
VERSYM_HIDDEN = 0x8000
VERSYM_GLOBAL = 1


class ElfError(Exception):
    pass


class Elf:
    """Dynamic view of an ELF (from PT_DYNAMIC, like the linker; section headers unused)."""

    __slots__ = ("path", "bits", "machine", "is_exec", "needed", "soname", "undefs",
                 "exports", "verdefs", "has_versym", "sha256")

    def __init__(self, path):
        self.path = path
        with open(path, "rb") as f:
            data = f.read()
        self.sha256 = hashlib.sha256(data).hexdigest()
        if data[:4] != b"\x7fELF":
            raise ElfError("not ELF")
        cls, enc = data[4], data[5]
        if enc != 1:
            raise ElfError("big endian")
        self.bits = 64 if cls == 2 else 32
        is64 = self.bits == 64
        e_type, e_machine = struct.unpack_from("<HH", data, 16)
        self.machine = e_machine
        if e_machine not in (EM_ARM, EM_AARCH64):
            raise ElfError("machine %d" % e_machine)
        if is64:
            e_phoff, = struct.unpack_from("<Q", data, 32)
            e_phentsize, e_phnum = struct.unpack_from("<HH", data, 54)
        else:
            e_phoff, = struct.unpack_from("<I", data, 28)
            e_phentsize, e_phnum = struct.unpack_from("<HH", data, 42)
        loads, dyn, interp = [], None, False
        for i in range(e_phnum):
            o = e_phoff + i * e_phentsize
            if is64:
                p_type, _, p_offset, p_vaddr, _, p_filesz, _, _ = struct.unpack_from("<IIQQQQQQ", data, o)
            else:
                p_type, p_offset, p_vaddr, _, p_filesz, _, _, _ = struct.unpack_from("<IIIIIIII", data, o)
            if p_type == PT_LOAD:
                loads.append((p_vaddr, p_offset, p_filesz))
            elif p_type == PT_DYNAMIC:
                dyn = (p_offset, p_filesz)
            elif p_type == PT_INTERP:
                interp = True
        if dyn is None:
            raise ElfError("static")
        self.is_exec = e_type == 2 or (e_type == 3 and interp)

        def off(vaddr):
            for v, o, sz in loads:
                if v <= vaddr < v + sz:
                    return vaddr - v + o
            raise ElfError("vaddr %x unmapped" % vaddr)

        tags = collections.defaultdict(list)
        efmt, esz = ("<qQ", 16) if is64 else ("<iI", 8)
        o, end = dyn[0], dyn[0] + dyn[1]
        while o + esz <= end:
            tag, val = struct.unpack_from(efmt, data, o)
            o += esz
            if tag == DT_NULL:
                break
            tags[tag].append(val)
        strtab = off(tags[DT_STRTAB][0])

        def cstr(i):
            s = strtab + i
            return data[s:data.index(b"\0", s)].decode("utf-8", "replace")

        self.needed = [cstr(v) for v in tags.get(DT_NEEDED, [])]
        self.soname = cstr(tags[DT_SONAME][0]) if DT_SONAME in tags else None
        symtab = off(tags[DT_SYMTAB][0]) if DT_SYMTAB in tags else None
        nsyms = 0
        if DT_HASH in tags:
            nsyms = struct.unpack_from("<I", data, off(tags[DT_HASH][0]) + 4)[0]
        elif DT_GNU_HASH in tags:
            h = off(tags[DT_GNU_HASH][0])
            nbuckets, symoffset, bloom_size, _ = struct.unpack_from("<IIII", data, h)
            b = h + 16 + bloom_size * (8 if is64 else 4)
            buckets = struct.unpack_from("<%dI" % nbuckets, data, b)
            chain = b + 4 * nbuckets
            last = max(buckets) if buckets else 0
            if last < symoffset:
                nsyms = symoffset
            else:
                while not (struct.unpack_from("<I", data, chain + 4 * (last - symoffset))[0] & 1):
                    last += 1
                nsyms = last + 1
        versym = None
        self.has_versym = DT_VERSYM in tags
        if self.has_versym:
            versym = struct.unpack_from("<%dH" % nsyms, data, off(tags[DT_VERSYM][0]))
        # version definitions: name -> index
        self.verdefs = {}
        if DT_VERDEF in tags:
            p = off(tags[DT_VERDEF][0])
            for _ in range(tags[DT_VERDEFNUM][0] if DT_VERDEFNUM in tags else 1 << 16):
                _, flags, ndx, cnt, _, aux, nxt = struct.unpack_from("<HHHHIII", data, p)
                if cnt:
                    name = cstr(struct.unpack_from("<I", data, p + aux)[0])
                    self.verdefs.setdefault(name, ndx)
                if not nxt:
                    break
                p += nxt
        vneed = {}
        if DT_VERNEED in tags:
            p = off(tags[DT_VERNEED][0])
            for _ in range(tags[DT_VERNEEDNUM][0] if DT_VERNEEDNUM in tags else 1 << 16):
                _, cnt, _, aux, nxt = struct.unpack_from("<HHIII", data, p)
                a = p + aux
                for _ in range(cnt):
                    _, _, other, vname, anext = struct.unpack_from("<IHHII", data, a)
                    vneed[other] = cstr(vname)
                    if not anext:
                        break
                    a += anext
                if not nxt:
                    break
                p += nxt
        undefs, exports = [], {}
        if symtab is not None:
            ssz = 24 if is64 else 16
            for i in range(1, nsyms):
                so = symtab + i * ssz
                if is64:
                    st_name, st_info, st_other, st_shndx = struct.unpack_from("<IBBH", data, so)
                else:
                    st_name, st_info, st_other, st_shndx = struct.unpack_from("<I8xBBH", data, so)
                bind = st_info >> 4
                if not st_name:
                    continue
                if st_shndx == 0:
                    if bind == STB_GLOBAL:
                        req = None
                        if versym is not None:
                            vi = versym[i] & 0x7fff
                            if vi >= 2:
                                req = vneed.get(vi)
                        undefs.append((cstr(st_name), req))
                elif bind in (STB_GLOBAL, STB_WEAK, STB_GNU_UNIQUE) and (st_other & 3) in (0, 3):
                    v = versym[i] if versym is not None else 0
                    exports.setdefault(cstr(st_name), []).append(v)
        self.undefs = undefs
        self.exports = exports

    def provides(self, name, req):
        """bionic soinfo::find_symbol_by_name + check_symbol_version."""
        vers = self.exports.get(name)
        if vers is None:
            return False
        if not self.has_versym:
            return True
        if req is None:
            return any(not (v & VERSYM_HIDDEN) for v in vers)
        want = self.verdefs.get(req, VERSYM_GLOBAL)
        return any((v & 0x7fff) == want for v in vers)


def read_elf_class(path):
    try:
        with open(path, "rb") as f:
            h = f.read(20)
    except OSError:
        return None
    if len(h) < 20 or h[:4] != b"\x7fELF":
        return None
    machine = struct.unpack_from("<H", h, 18)[0]
    if machine not in (EM_ARM, EM_AARCH64):
        return None
    return 64 if h[4] == 2 else 32


class DeviceFS:
    """Maps device paths to host paths with device-side symlink resolution."""

    def __init__(self, mounts, overlays=None):
        self.mounts = sorted(mounts.items(), key=lambda kv: -len(kv[0]))
        # overlays: {device prefix: host dir}; a regular file there replaces an existing image file
        # at the same device path (e.g. a fresh build output over the assembled staging tree)
        self.overlays = sorted((overlays or {}).items(), key=lambda kv: -len(kv[0]))
        self._cache = {}

    def overlay(self, dev, host):
        for prefix, ohost in self.overlays:
            if dev.startswith(prefix + "/"):
                cand = ohost + dev[len(prefix):]
                if os.path.isfile(cand) and not os.path.islink(cand) and os.path.isfile(host):
                    return cand
                break
        return host

    def to_host(self, dev):
        for prefix, host in self.mounts:
            if prefix == "/":
                return host + dev
            if dev == prefix or dev.startswith(prefix + "/"):
                return host + dev[len(prefix):]
        return None

    def realpath(self, dev):
        """Return (device realpath, host path) of an existing regular file/dir, else None."""
        if dev in self._cache:
            return self._cache[dev]
        result = None
        path = posixpath.normpath(dev)
        for _ in range(40):
            comps = [c for c in path.split("/") if c]
            cur = "/"
            restarted = False
            for idx, comp in enumerate(comps):
                nxt = posixpath.join(cur, comp)
                host = self.to_host(nxt)
                if host is None:
                    break
                if os.path.islink(host):
                    target = os.readlink(host)
                    rest = comps[idx + 1:]
                    base = target if target.startswith("/") else posixpath.join(cur, target)
                    path = posixpath.normpath(posixpath.join(base, *rest)) if rest else posixpath.normpath(base)
                    restarted = True
                    break
                if not os.path.lexists(host):
                    break
                cur = nxt
            else:
                result = (cur, self.overlay(cur, self.to_host(cur)))
                break
            if not restarted:
                break
        self._cache[dev] = result
        return result


def parse_ldconfig(text):
    dirs, sections, cur = [], {}, None
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            cur = line[1:-1].strip()
            sections[cur] = {}
            continue
        if "+=" in line:
            k, v = line.split("+=", 1)
            add = True
        elif "=" in line:
            k, v = line.split("=", 1)
            add = False
        else:
            continue
        k, v = k.strip(), v.strip()
        if cur is None:
            if k.startswith("dir."):
                dirs.append((k[4:], v))
            continue
        props = sections[cur]
        if add:
            props.setdefault(k, []).append(v)
        else:
            props[k] = [v]
    return dirs, sections


class Namespace:
    def __init__(self, key, search, links):
        self.key = key                  # "<config>:<section>:<name>"
        self.search = search            # device dirs (per bitness)
        self.links = links              # [(target_key, set(shared_libs) or None=allow_all)]


class LinkerConfig:
    def __init__(self, label, text, vndk_ver="29"):
        self.label = label
        self.dirs, sections = parse_ldconfig(text)
        self.sections = list(sections)
        self.ns = {}                    # (bits, section, name) -> Namespace
        for sec, props in sections.items():
            names = ["default"]
            for v in props.get("additional.namespaces", []):
                names += [n.strip() for n in v.split(",") if n.strip()]
            for bits in (32, 64):
                lib = "lib64" if bits == 64 else "lib"

                def sub(s):
                    return s.replace("${LIB}", lib).replace("${VNDK_VER}", "-" + vndk_ver)
                for name in names:
                    pre = "namespace.%s." % name
                    search = []
                    for v in props.get(pre + "search.paths", []):
                        search += [sub(p.strip()) for p in v.split(":") if p.strip()]
                    links = []
                    for lv in props.get(pre + "links", []):
                        for t in [x.strip() for x in lv.split(",") if x.strip()]:
                            if props.get(pre + "link.%s.allow_all_shared_libs" % t, ["false"])[-1] == "true":
                                links.append(((bits, sec, t), None))
                            else:
                                libs = set()
                                for v in props.get(pre + "link.%s.shared_libs" % t, []):
                                    libs |= {x.strip() for x in v.split(":") if x.strip()}
                                links.append(((bits, sec, t), libs))
                    self.ns[(bits, sec, name)] = Namespace("%s:%s:%s" % (label, sec, name), search, links)

    def section_for(self, devpath):
        best, blen = None, -1
        for sec, d in self.dirs:
            d2 = d.rstrip("/")
            if (devpath == d2 or devpath.startswith(d2 + "/")) and len(d2) > blen:
                best, blen = sec, len(d2)
        return best


def extract_apex(apex_path, cache_root):
    st = os.stat(apex_path)
    key = hashlib.sha256(("%s:%d:%d" % (os.path.realpath(apex_path), st.st_size, int(st.st_mtime))).encode()).hexdigest()[:20]
    out = os.path.join(cache_root, os.path.basename(apex_path) + "-" + key)
    done = os.path.join(out, ".done")
    with zipfile.ZipFile(apex_path) as z:
        names = z.namelist()
        if "apex_manifest.json" in names:
            name = json.loads(z.read("apex_manifest.json"))["name"]
        else:
            pb = z.read("apex_manifest.pb")
            ln = pb[1]
            name = pb[2:2 + ln].decode()
        if os.path.exists(done):
            return name, os.path.join(out, "root")
        os.makedirs(os.path.join(out, "root"), exist_ok=True)
        img = os.path.join(out, "payload.img")
        with z.open("apex_payload.img") as src, open(img, "wb") as dst:
            while True:
                buf = src.read(1 << 20)
                if not buf:
                    break
                dst.write(buf)
    cmds = os.path.join(out, "cmds")
    with open(cmds, "w") as f:
        for d in ("bin", "lib", "lib64", "etc"):
            f.write("rdump /%s %s\n" % (d, os.path.join(out, "root")))
    subprocess.run(["debugfs", "-f", cmds, img], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    os.remove(img)
    open(done, "w").close()
    return name, os.path.join(out, "root")


class Image:
    """One assembled device view: system root + vendor/product/odm + extracted system APEXes."""

    def __init__(self, label, system_root, vendor, product, odm, cache_root, vndk_ver="29",
                 overlays=None):
        self.label = label
        mounts = {"/": system_root}
        for mp, host in (("/vendor", vendor), ("/product", product), ("/odm", odm)):
            if host:
                mounts[mp] = host
        self.apex = {}
        apex_dir = os.path.join(system_root, "system", "apex")
        if os.path.isdir(apex_dir):
            for fn in sorted(os.listdir(apex_dir)):
                p = os.path.join(apex_dir, fn)
                if fn.endswith(".apex") and os.path.isfile(p):
                    name, root = extract_apex(p, cache_root)
                    self.apex[name] = root
                    mounts["/apex/" + name] = root
                elif os.path.isdir(p):      # flattened APEX
                    self.apex[fn] = p
                    mounts["/apex/" + fn] = p
        self.mounts = mounts
        self.fs = DeviceFS(mounts, overlays)
        cfg = self.fs.realpath("/system/etc/ld.config.%s.txt" % vndk_ver) or self.fs.realpath("/system/etc/ld.config.txt")
        if cfg is None:
            raise SystemExit("%s: no ld.config" % label)
        with open(cfg[1]) as f:
            self.config = LinkerConfig(label, f.read(), vndk_ver)
        self.apex_configs = {}
        for name, root in self.apex.items():
            p = os.path.join(root, "etc", "ld.config.txt")
            if os.path.isfile(p):
                with open(p) as f:
                    self.apex_configs[name] = LinkerConfig("%s/apex:%s" % (label, name), f.read(), vndk_ver)
        self.app_ns = {}

    def walk(self):
        """Yield device paths of all dynamically linked ARM ELFs (regular files only)."""
        for mp, host in sorted(self.mounts.items()):
            for dirpath, dirnames, filenames in os.walk(host):
                rel = os.path.relpath(dirpath, host)
                devdir = posixpath.normpath(posixpath.join(mp, rel.replace(os.sep, "/")))
                if mp == "/":
                    # mount points of other trees are walked separately
                    dirnames[:] = [d for d in dirnames
                                   if posixpath.join(devdir, d) not in self.mounts and d != "lost+found"]
                for fn in filenames:
                    hp = os.path.join(dirpath, fn)
                    if os.path.islink(hp) or not os.path.isfile(hp):
                        continue
                    dev = posixpath.join(devdir, fn)
                    hp = self.fs.overlay(dev, hp)
                    if read_elf_class(hp):
                        yield dev, hp


class Checker:
    def __init__(self, image, elf_cache):
        self.img = image
        self.elves = elf_cache          # host path -> Elf or ElfError
        self.find_cache = {}
        self.closure_cache = {}
        self.unres_cache = {}
        self.linkers = {}

    def elf(self, host):
        e = self.elves.get(host)
        if e is None:
            try:
                e = Elf(host)
            except (ElfError, struct.error, ValueError, IndexError, OSError) as ex:
                e = ElfError(str(ex))
            self.elves[host] = e
        return e

    def namespace(self, key):
        cfgname, sec, name, bits = key
        if cfgname == "app":
            return self.app_namespace(sec, bits)
        cfg = self.img.config if cfgname == "main" else self.img.apex_configs[cfgname]
        return cfg.ns.get((bits, sec, name))

    def app_namespace(self, appdir, bits):
        """Classloader namespace of a system/product/vendor app (shared with default, as for
        apps on system partitions in Android 10)."""
        k = (appdir, bits)
        ns = self.img.app_ns.get(k)
        if ns is None:
            ns = Namespace("app:" + appdir, [appdir], [((bits, "system", "default"), None)])
            self.img.app_ns[k] = ns
        return ns

    def ns_links(self, key):
        cfgname, sec, name, bits = key
        ns = self.namespace(key)
        if cfgname == "app":
            return [(("main", "system", "default", bits), None)]
        if ns is None:
            print("warning: no namespace %r" % (key,), file=sys.stderr)
            return []
        return [((cfgname, t[1], t[2], bits), libs) for t, libs in ns.links]

    def search_in(self, key, soname, bits):
        ns = self.namespace(key)
        if ns is None:
            return None
        for d in ns.search:
            r = self.img.fs.realpath(posixpath.join(d, soname))
            if r and os.path.isfile(r[1]) and read_elf_class(r[1]) == bits:
                return r
        return None

    def find(self, key, soname, bits):
        """bionic find_library_internal: own namespace, then linked namespaces (one level)."""
        ck = (key, soname)
        if ck in self.find_cache:
            return self.find_cache[ck]
        res = None
        if "/" in soname:
            r = self.img.fs.realpath(soname)
            if r and read_elf_class(r[1]) == bits:
                res = (r, key)
        else:
            r = self.search_in(key, soname, bits)
            if r:
                res = (r, key)
            else:
                for target, libs in self.ns_links(key):
                    if libs is None or soname in libs:
                        r = self.search_in(target, soname, bits)
                        if r:
                            res = (r, target)
                            break
        self.find_cache[ck] = res
        return res

    def context(self, devpath, bits, is_exec):
        """Namespace key an ELF is loaded in."""
        d = posixpath.dirname(devpath)
        configs = [("main", self.img.config)]
        if devpath.startswith("/apex/"):
            apex = devpath.split("/")[2]
            if apex in self.img.apex_configs:
                configs.insert(0, (apex, self.img.apex_configs[apex]))
        if is_exec:
            for cname, cfg in configs:
                sec = cfg.section_for(devpath)
                if sec:
                    return (cname, sec, "default", bits)
            return ("main", "system", "default", bits)
        parts = devpath.split("/")
        if len(parts) > 4 and parts[1] in ("system", "product", "vendor", "odm") and parts[2] in ("app", "priv-app"):
            # /system/app/<name>/lib/<abi>/libx.so
            return ("app", d, "app", bits)
        real_d = self.img.fs.realpath(d)
        real_d = real_d[0] if real_d else d
        for cname, cfg in configs:
            prefer = cfg.section_for(devpath)
            if prefer is None and devpath.startswith(("/vendor/", "/odm/")) and "vendor" in cfg.sections:
                # vendor libraries are loaded by vendor processes ([vendor] section); system
                # processes reach only SP-HALs and are covered by the same default namespace
                secs = ["vendor"]
            else:
                secs = ([prefer] if prefer else []) + [s for s in cfg.sections if s != prefer]
            for sec in secs:
                for (b, s, name), ns in cfg.ns.items():
                    if b != bits or s != sec:
                        continue
                    for sp in ns.search:
                        r = self.img.fs.realpath(sp)
                        if r and r[0] == real_d:
                            return (cname, sec, name, bits)
        # not in any search path (e.g. /vendor/lib64/hw, /apex/.../bionic): the default
        # namespace of the section owning the path (vendor for /vendor and /odm)
        sec = self.img.config.section_for(devpath)
        if sec is None:
            sec = "vendor" if devpath.startswith(("/vendor/", "/odm/")) else "system"
        return ("main", sec, "default", bits)

    def linker(self, bits):
        if bits not in self.linkers:
            r = self.img.fs.realpath("/system/bin/linker64" if bits == 64 else "/system/bin/linker")
            e = self.elf(r[1]) if r else None
            self.linkers[bits] = e if isinstance(e, Elf) else None
        return self.linkers[bits]

    def closure(self, host, devreal, key):
        """BFS load order [(devreal, host, key, Elf)] and list of missing DT_NEEDED."""
        ck = (host, key)
        if ck in self.closure_cache:
            return self.closure_cache[ck]
        root = self.elf(host)
        order, missing, seen = [], [], set()
        queue = collections.deque([(devreal, host, key, root)])
        seen.add(host)
        while queue:
            dv, hp, k, e = queue.popleft()
            order.append((dv, hp, k, e))
            if not isinstance(e, Elf):
                continue
            for n in e.needed:
                r = self.find(k, n, e.bits)
                if r is None:
                    missing.append((dv, n, k))
                    continue
                (rdev, rhost), rk = r
                if rhost in seen:
                    continue
                seen.add(rhost)
                queue.append((rdev, rhost, rk, self.elf(rhost)))
        res = (order, missing)
        self.closure_cache[ck] = res
        return res

    def unresolved_in_closure(self, host, devreal, key):
        ck = (host, key)
        if ck in self.unres_cache:
            return self.unres_cache[ck]
        order, _ = self.closure(host, devreal, key)
        e = order[0][3]
        out = []
        if isinstance(e, Elf):
            provs = [x[3] for x in order[1:] if isinstance(x[3], Elf)]
            lk = self.linker(e.bits)
            if lk is not None:
                provs.append(lk)
            for name, req in e.undefs:
                if not any(p.provides(name, req) for p in provs):
                    out.append((name, req))
        self.unres_cache[ck] = out
        return out

    def check(self, devpath, host):
        e = self.elf(host)
        if not isinstance(e, Elf):
            return None
        real = self.img.fs.realpath(devpath)
        devreal = real[0] if real else devpath
        key = self.context(devpath, e.bits, e.is_exec)
        order, missing = self.closure(host, devreal, key)
        res = {
            "path": devpath, "bits": e.bits, "exec": e.is_exec, "namespace": "%s:%s:%s" % key[:3],
            "sha256": e.sha256,
            "missing_libs": sorted({"%s needs %s" % (dv, n) for dv, n, _ in missing}),
            "closure_undef": sorted("%s%s" % (n, "@" + r if r else "") for n, r in self.unresolved_in_closure(host, devreal, key)),
            "tree_undef": [],
        }
        if e.is_exec:
            provs = [x[3] for x in order if isinstance(x[3], Elf)]
            lk = self.linker(e.bits)
            if lk is not None:
                provs.append(lk)
            tree = []
            for dv, hp, k, m in order:
                if not isinstance(m, Elf):
                    continue
                for name, req in self.unresolved_in_closure(hp, dv, k):
                    if not any(p.provides(name, req) for p in provs):
                        tree.append("%s: %s%s" % (dv, name, "@" + req if req else ""))
            res["tree_undef"] = sorted(set(tree))
        return res


def run(image, elf_cache, progress=True):
    ch = Checker(image, elf_cache)
    results = {}
    files = list(image.walk())
    for i, (dev, host) in enumerate(files):
        r = ch.check(dev, host)
        if r is not None:
            results[dev] = r
        if progress and i % 500 == 0:
            print("  [%s] %d/%d" % (image.label, i, len(files)), file=sys.stderr)
    return results


def findings(results):
    out = set()
    for dev, r in results.items():
        for m in r["missing_libs"]:
            out.add((dev, "missing_lib", m))
        for s in r["closure_undef"]:
            out.add((dev, "closure_undef", s))
        for s in r["tree_undef"]:
            out.add((dev, "tree_undef", s))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--release", help="staging/<release>/root as the system root (e.g. source-2.04)")
    ap.add_argument("--system-root", help="assembled system-as-root tree (contains system/)")
    ap.add_argument("--vendor", default=DEFAULT_PARTITIONS + "/vendor")
    ap.add_argument("--product", default=DEFAULT_PARTITIONS + "/product")
    ap.add_argument("--odm", default=DEFAULT_PARTITIONS + "/odm")
    ap.add_argument("--baseline-system-root", default=DEFAULT_FACTORY_SYSTEM,
                    help="factory system tree for comparison ('' to skip)")
    ap.add_argument("--cache-dir", default=os.path.expanduser("~/.cache/pico-image-links"))
    ap.add_argument("--vndk-version", default="29")
    ap.add_argument("--overlay", action="append", default=[], metavar="DEVPREFIX=HOSTDIR",
                    help="replace image files under DEVPREFIX by the files in HOSTDIR (same relative "
                         "path), e.g. /system=$OUT/system to check rebuilt modules before reassembly")
    ap.add_argument("--json", help="write full results here")
    ap.add_argument("--all", action="store_true", help="also list pre-existing factory gaps")
    args = ap.parse_args()
    if args.release:
        args.system_root = "%s/staging/%s/root" % (PROJECT, args.release)
    if not args.system_root:
        ap.error("--release or --system-root required")
    os.makedirs(args.cache_dir, exist_ok=True)
    elf_cache = {}
    overlays = dict(o.split("=", 1) for o in args.overlay)
    img = Image("image", args.system_root, args.vendor, args.product, args.odm, args.cache_dir,
                args.vndk_version, overlays)
    res = run(img, elf_cache)
    base_res = {}
    if args.baseline_system_root:
        bimg = Image("factory", args.baseline_system_root, args.vendor, args.product, args.odm,
                     args.cache_dir, args.vndk_version)
        base_res = run(bimg, elf_cache)
    cur, base = findings(res), findings(base_res)
    regress = sorted(cur - base) if args.baseline_system_root else sorted(cur)
    fixed = sorted(base - cur)
    base_sha = {d: r["sha256"] for d, r in base_res.items()}

    def origin(dev):
        if dev not in base_sha:
            return "new"
        return "factory-carried" if base_sha[dev] == res[dev]["sha256"] else "rebuilt"

    def counts(fs):
        c = collections.Counter(k for _, k, _ in fs)
        return {k: c.get(k, 0) for k in ("missing_lib", "tree_undef", "closure_undef")}

    print("ELFs checked: image %d, factory %d" % (len(res), len(base_res)))
    print("image findings:   %s (ELFs with any: %d)" % (counts(cur), len({d for d, _, _ in cur})))
    if args.baseline_system_root:
        print("factory findings: %s (ELFs with any: %d)" % (counts(base), len({d for d, _, _ in base})))
        print("REGRESSIONS:      %s (ELFs: %d)" % (counts(regress), len({d for d, _, _ in regress})))
        print("gone vs factory:  %s" % counts(fixed))
    print()
    order = {"missing_lib": 0, "tree_undef": 1, "closure_undef": 2}
    for dev, kind, detail in sorted(regress, key=lambda f: (order[f[1]], f[0], f[2])):
        print("REGRESSION %-13s %-60s [%s] %s" % (kind, dev, origin(dev), detail))
    if args.all:
        for dev, kind, detail in sorted(cur & base, key=lambda f: (order[f[1]], f[0], f[2])):
            print("factory-gap %-13s %-60s %s" % (kind, dev, detail))
    if args.json:
        with open(args.json, "w") as f:
            json.dump({
                "system_root": args.system_root, "baseline": args.baseline_system_root,
                "counts": {"image": counts(cur), "factory": counts(base), "regressions": counts(regress)},
                "regressions": [{"path": d, "kind": k, "detail": x, "origin": origin(d)} for d, k, x in regress],
                "factory_gaps": [{"path": d, "kind": k, "detail": x} for d, k, x in sorted(cur & base)],
                "gone_vs_factory": [{"path": d, "kind": k, "detail": x} for d, k, x in fixed],
                "image": res, "factory": base_res,
            }, f, indent=1, sort_keys=True)
    return 1 if regress else 0


if __name__ == "__main__":
    sys.exit(main())
