#!/usr/bin/env python3
"""Compare factory device-tree compatibles against factory and recovery kernel binaries.

Read-only. Parses FDT/DTBO without dtc, applies overlays, collects compatibles of
enabled nodes, then checks which compatible strings each kernel build contains.
"""
import copy, glob, gzip, hashlib, io, json, os, re, struct, sys, tarfile

FDT_MAGIC = 0xD00DFEED
DTBO_MAGIC = 0xD7B7AB1E


class Node:
    def __init__(self, name):
        self.name = name
        self.props = {}
        self.children = {}

    def child(self, name):
        return self.children.get(name)


def parse_fdt(blob, base=0):
    (magic, totalsize, off_struct, off_strings, _rsv, _ver, _lcv, _cpu,
     size_strings, size_struct) = struct.unpack_from(">10I", blob, base)
    assert magic == FDT_MAGIC
    strings = blob[base + off_strings: base + off_strings + size_strings]
    p = base + off_struct
    end = p + size_struct
    stack = []
    root = None
    while p < end:
        tok = struct.unpack_from(">I", blob, p)[0]
        p += 4
        if tok == 1:  # BEGIN_NODE
            e = blob.index(b"\0", p)
            name = blob[p:e].decode("latin1")
            p = base + (((e - base) + 4) & ~3)
            n = Node(name)
            if stack:
                stack[-1].children[name] = n
            else:
                root = n
            stack.append(n)
        elif tok == 2:
            stack.pop()
        elif tok == 3:
            ln, nameoff = struct.unpack_from(">II", blob, p)
            p += 8
            val = blob[p:p + ln]
            p = base + (((p - base) + ln + 3) & ~3)
            pname = strings[nameoff:strings.index(b"\0", nameoff)].decode("latin1")
            stack[-1].props[pname] = val
        elif tok == 4:
            continue
        elif tok == 9:
            break
        else:
            raise ValueError("bad token %x at %d" % (tok, p))
    return root, totalsize


def split_dtbs(blob):
    out, i = [], 0
    while True:
        i = blob.find(struct.pack(">I", FDT_MAGIC), i)
        if i < 0:
            break
        try:
            root, size = parse_fdt(blob, i)
        except Exception:
            i += 4
            continue
        out.append((i, blob[i:i + size], root))
        i += size
    return out


def parse_dtbo(blob):
    magic, total, hsz, esz, cnt, eoff, _pg, _ver = struct.unpack_from(">8I", blob, 0)
    assert magic == DTBO_MAGIC
    res = []
    for k in range(cnt):
        dsz, doff, did, drev, c0, c1, c2, c3 = struct.unpack_from(">8I", blob, eoff + k * esz)
        root, _ = parse_fdt(blob, doff)
        res.append(dict(index=k, id=did, rev=drev, custom=[c0, c1, c2, c3],
                        sha=hashlib.sha256(blob[doff:doff + dsz]).hexdigest(), root=root))
    return res


def boot_dtb(blob):
    assert blob[:8] == b"ANDROID!"
    ksz, _, rsz, _, ssz, _, _, pg, hv = struct.unpack_from("<9I", blob, 8)
    if hv < 2:
        return None
    rdsz = struct.unpack_from("<I", blob, 1632)[0]
    dsz = struct.unpack_from("<I", blob, 1648)[0]
    al = lambda x: (x + pg - 1) // pg * pg
    off = pg + al(ksz) + al(rsz) + al(ssz) + al(rdsz)
    return blob[off:off + dsz]


def sval(v):
    return [s.decode("latin1") for s in v.rstrip(b"\0").split(b"\0")] if v else []


def u32s(v):
    return list(struct.unpack(">%dI" % (len(v) // 4), v)) if v else []


def walk(n, path="/"):
    yield path, n
    for name, c in n.children.items():
        yield from walk(c, (path.rstrip("/") + "/" + name))


def lookup(root, path):
    n = root
    for part in [p for p in path.split("/") if p]:
        n = n.children.get(part)
        if n is None:
            return None
    return n


def merge(dst, src):
    for k, v in src.props.items():
        dst.props[k] = v
    for name, c in src.children.items():
        if name in dst.children:
            merge(dst.children[name], c)
        else:
            dst.children[name] = copy.deepcopy(c)


def apply_overlay(base, ov):
    base = copy.deepcopy(base)
    syms = {k: sval(v)[0] for k, v in (base.child("__symbols__").props.items()
                                        if base.child("__symbols__") else [])}
    # fixups: label -> ["/fragment@0:target:0", ...]
    fix = {}
    if ov.child("__fixups__"):
        for label, v in ov.child("__fixups__").props.items():
            for ref in sval(v):
                fix[ref] = label
    unresolved, applied = [], 0
    for fname, frag in ov.children.items():
        if not fname.startswith("fragment") or "__overlay__" not in frag.children:
            continue
        tgt = None
        if "target-path" in frag.props:
            tgt = lookup(base, sval(frag.props["target-path"])[0])
        elif "target" in frag.props:
            label = fix.get("/%s:target:0" % fname)
            if label and label in syms:
                tgt = lookup(base, syms[label])
            else:
                # local phandle target
                ph = u32s(frag.props["target"])[0]
                for _, n in walk(base):
                    if u32s(n.props.get("phandle", b""))[:1] == [ph]:
                        tgt = n
                        break
        if tgt is None:
            unresolved.append(fname)
            continue
        merge(tgt, frag.children["__overlay__"])
        applied += 1
    return base, applied, unresolved


def enabled(n):
    st = sval(n.props.get("status", b""))
    return not st or st[0] in ("okay", "ok")


def enabled_nodes(root):
    """Yield (path, node) for nodes whose ancestors are all enabled."""
    def rec(n, path):
        if not enabled(n):
            return
        yield path, n
        for name, c in n.children.items():
            if name.startswith("__"):
                continue
            yield from rec(c, path.rstrip("/") + "/" + name)
    yield from rec(root, "/")


STR_RE = re.compile(rb"[\x20-\x7e]{3,}")


def strings_of(data):
    return set(m.group().decode() for m in STR_RE.finditer(data))


def main():
    P = sys.argv[1]
    outdir = sys.argv[2]
    modtar = sys.argv[3]
    os.makedirs(outdir, exist_ok=True)
    stock = P + "/stock"
    rep = {"inputs": {}}

    # ---- device trees
    seko_dtb = open(stock + "/5.13.7-SEKO/boot-unpacked/dtb", "rb").read()
    live_boot = open(stock + "/5.13.7-live/boot.img", "rb").read()
    live_dtb = boot_dtb(live_boot)
    rep["inputs"]["seko_dtb_sha"] = hashlib.sha256(seko_dtb).hexdigest()
    rep["inputs"]["live_boot_dtb_sha"] = hashlib.sha256(live_dtb).hexdigest() if live_dtb else None
    bases = split_dtbs(live_dtb or seko_dtb)
    rep["bases"] = []
    for off, b, root in bases:
        rep["bases"].append(dict(offset=off, model=sval(root.props.get("model", b""))[:1],
                                 compatible=sval(root.props.get("compatible", b"")),
                                 msm_id=u32s(root.props.get("qcom,msm-id", b"")),
                                 board_id=u32s(root.props.get("qcom,board-id", b"")),
                                 sha=hashlib.sha256(b).hexdigest()))
    dtbo_live = parse_dtbo(open(stock + "/5.13.7-live/dtbo.img", "rb").read())
    dtbo_seko = parse_dtbo(open(stock + "/5.13.7-SEKO/dtbo.img", "rb").read())
    rep["dtbo_live_vs_seko_entries_equal"] = [a["sha"] for a in dtbo_live] == [b["sha"] for b in dtbo_seko]
    rep["overlays"] = []
    combos = []
    for e in dtbo_live:
        r = e["root"]
        omsm = u32s(r.props.get("qcom,msm-id", b""))
        obid = u32s(r.props.get("qcom,board-id", b""))
        info = dict(index=e["index"], id=e["id"], rev=e["rev"], model=sval(r.props.get("model", b""))[:1],
                    msm_id=omsm, board_id=obid, sha=e["sha"])
        rep["overlays"].append(info)
        for bi, (off, b, broot) in enumerate(bases):
            bmsm = u32s(broot.props.get("qcom,msm-id", b""))
            # msm-id cells: pairs (soc-id, rev); match on soc-id+rev pairs intersect
            bp = set(zip(bmsm[0::2], bmsm[1::2]))
            op = set(zip(omsm[0::2], omsm[1::2]))
            if bp & op or not omsm:
                combos.append((bi, e["index"]))
    rep["combos"] = []
    trees = {}
    for bi, oi in combos:
        merged, applied, unres = apply_overlay(bases[bi][2], dtbo_live[oi]["root"])
        trees[(bi, oi)] = merged
        rep["combos"].append(dict(base=bi, overlay=oi, fragments_applied=applied, unresolved=unres))

    # compat -> {paths, combos}
    nodes = {}
    for key, t in trees.items():
        for path, n in enabled_nodes(t):
            comp = sval(n.props.get("compatible", b""))
            if not comp:
                continue
            k = (path, tuple(comp))
            nodes.setdefault(k, set()).add(key)

    # ---- kernel strings
    fk = open(stock + "/5.13.7-SEKO/boot-unpacked/kernel", "rb").read()
    factory_k = strings_of(fk)
    factory_m = {}
    for ko in sorted(glob.glob(P + "/analysis/stock-5.13.7-partitions/vendor/lib/modules/*.ko")):
        factory_m[os.path.basename(ko)] = strings_of(open(ko, "rb").read())
    ours_img = P + "/out/phoenix-kernel-recovery/obj/arch/arm64/boot/Image"
    ok = open(ours_img, "rb").read()
    rep["inputs"]["ours_image_sha"] = hashlib.sha256(ok).hexdigest()
    rep["inputs"]["ours_image_mtime"] = os.path.getmtime(ours_img)
    ours_k = strings_of(ok)
    ours_m = {}
    with tarfile.open(modtar) as tf:
        for m in tf.getmembers():
            if m.name.endswith(".ko"):
                ours_m[os.path.basename(m.name)] = strings_of(tf.extractfile(m).read())
    rep["inputs"]["factory_modules"] = len(factory_m)
    rep["inputs"]["ours_modules"] = len(ours_m)

    def where(c, kset, mods):
        hits = []
        if c in kset:
            hits.append("kernel")
        hits += [m for m, s in mods.items() if c in s]
        return hits

    allc = sorted({c for (_, comp) in nodes for c in comp})
    cmap = {c: dict(factory=where(c, factory_k, factory_m), ours=where(c, ours_k, ours_m)) for c in allc}
    ncombos = len(trees)
    rows = []
    for (path, comp), keys in sorted(nodes.items()):
        f = [c for c in comp if cmap[c]["factory"]]
        o = [c for c in comp if cmap[c]["ours"]]
        cls = ("ok" if f and o else "LOST" if f and not o else "neither" if not f and not o else "ours-only")
        # module-only availability in ours vs kernel
        rows.append(dict(path=path, compatible=list(comp), cls=cls,
                         in_all_combos=len(keys) == ncombos, combos=len(keys),
                         factory_where=sorted({w for c in f for w in cmap[c]["factory"]}),
                         ours_where=sorted({w for c in o for w in cmap[c]["ours"]})))
    rep["rows"] = rows
    rep["summary"] = {k: sum(1 for r in rows if r["cls"] == k) for k in ("ok", "LOST", "neither", "ours-only")}
    lostc = sorted({c for c in allc if cmap[c]["factory"] and not cmap[c]["ours"]})
    rep["lost_compatibles"] = {c: cmap[c]["factory"] for c in lostc}
    json.dump(rep, open(outdir + "/dt-compat-check.json", "w"), indent=1)

    # dump decompiled-ish text of first combo for later property checks
    for key, t in trees.items():
        with open(outdir + "/merged-base%d-ov%d.txt" % key, "w") as fh:
            for path, n in walk(t):
                if "/__" in path:
                    continue
                for pn, pv in n.props.items():
                    try:
                        s = sval(pv)
                        txt = s if pv.endswith(b"\0") and all(STR_RE.fullmatch(x.encode()) or x == "" for x in s) and pv[:1] != b"\0" else None
                    except Exception:
                        txt = None
                    if txt is not None:
                        fh.write("%s:%s = %s\n" % (path, pn, json.dumps(txt)))
                    else:
                        fh.write("%s:%s = <%s>\n" % (path, pn, " ".join("0x%x" % x for x in u32s(pv[:len(pv) // 4 * 4]))))
    print(json.dumps(dict(summary=rep["summary"], bases=rep["bases"], overlays=rep["overlays"],
                          combos=rep["combos"], dtbo_equal=rep["dtbo_live_vs_seko_entries_equal"],
                          inputs=rep["inputs"]), indent=1))


if __name__ == "__main__":
    main()
