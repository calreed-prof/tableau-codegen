"""Golden-file helpers.

  python3 scripts/refdiff.py clean <desktop-saved.twb>
      Strip machine/author fingerprints and thumbnails from a file saved by Tableau
      Desktop, in place, so it is safe to commit as a reference.

  python3 scripts/refdiff.py diff <reference.twb> <generated.twb>
      Normalise both files (generated ids, quoting, UI-only state) and print a unified
      diff, so only meaningful structural differences remain.

  python3 scripts/refdiff.py check <reference-dir>
      Build <dir>/spec.json and compare the parts of <dir>/desktop-saved.twb the compiler claims
      to reproduce (see CLAIMS in check()). Prints mismatches; exit 1 if any. Known, documented
      differences are listed in <dir>/known-diffs.json as {"<claim key>": "<reason>"}.

  python3 scripts/refdiff.py lock <reference-dir>...
      Make each desktop-saved.twb read-only (so Desktop can't save over it) and record its
      SHA-256 in LOCK.json next to the reference dirs. Tests fail if a locked file changes.
"""
import difflib
import hashlib
import json
import os
import re
import stat
import sys
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

ID_PATTERNS = [
    (re.compile(r"(federated|textscan|snowflake|sqlproxy)\.[a-z0-9]{20,}"), r"\1.<id>"),
    (re.compile(r"_[A-F0-9]{32}\b"), "_<objid>"),
    (re.compile(r"uuid=\"\{[^}]+\}\""), 'uuid="<uuid>"'),
    (re.compile(r"\bid=\"-?\d+\""), 'id="<n>"'),
    (re.compile(r"Calculation_\d+"), "Calculation_<n>"),
    (re.compile(r"Parameter \d+"), "Parameter <n>"),
]
FINGERPRINT = re.compile(r"\s_\.fcp\.WorkbookFingerprinting\.true\.\.\.[a-z-]+='[^']*'")


def clean(path):
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    text = FINGERPRINT.sub("", text)
    text = re.sub(r"\s*<_\.fcp\.WorkbookFingerprinting\.true\.\.\.WorkbookFingerprinting />", "", text)
    text = re.sub(r"\s*<thumbnails>.*?</thumbnails>", "", text, flags=re.S)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    print("cleaned", path)


def normalise(path):
    with open(path, encoding="utf-8") as fh:
        text = fh.read().replace("\r\n", "\n")
    text = text.replace("'", '"').replace("&quot;", '"')
    text = FINGERPRINT.sub("", text.replace('"', "'")).replace("'", '"')
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    text = re.sub(r"\s*<thumbnails>.*?</thumbnails>", "", text, flags=re.S)
    for pat, rep in ID_PATTERNS:
        text = pat.sub(rep, text)
    return [ln.rstrip() for ln in text.splitlines() if ln.strip()]


def diff(ref, gen):
    out = list(difflib.unified_diff(normalise(ref), normalise(gen), "reference", "generated", lineterm="", n=2))
    print("\n".join(out) if out else "no structural differences")
    return 1 if out else 0


# ---------------------------------------------------------------- structural check
def _norm(value):
    for pat, rep in ID_PATTERNS:
        value = pat.sub(rep, value)
    return value


def canon(el):
    """Canonical one-line form of an element: tag, sorted attributes (ids normalised), children.
    Ignores whitespace and ids (zone id, uuid) that Desktop renumbers."""
    attrs = " ".join(f'{k}="{_norm(v)}"' for k, v in sorted(el.attrib.items()) if k != "id")
    text = _norm((el.text or "").strip())
    kids = "".join(canon(c) for c in el)
    return f"<{el.tag} {attrs}>{text}{kids}</{el.tag}>"


# Zone attributes we claim for filter controls and legends (x/y follow the outer padding, M3).
ZONE_KEYS = ("name", "type-v2", "param", "values", "pane-specification-id", "mode", "h", "w")


GEOMETRY_KEYS = ("x", "y", "w", "h", "fixed-size", "is-fixed")


def _label(z):
    kind = z.get("type-v2") or "sheet"
    bits = [kind] + [_norm(z.get(k)) for k in ("param", "name") if z.get(k)]
    return ":".join(bits)


def _tree(z):
    """Zone structure without geometry, e.g. layout-basic(layout-flow:vert(title,...))."""
    kids = [c for c in z if c.tag == "zone"]
    return _label(z) + ("(" + ",".join(_tree(c) for c in kids) + ")" if kids else "")


def _paths(z, path):
    """(dotted index path, zone) for every zone, e.g. 1, 1.1, 1.1.2."""
    yield f"{path} {_label(z)}", z
    for i, c in enumerate((c for c in z if c.tag == "zone"), 1):
        yield from _paths(c, f"{path}.{i}")


def claims(root):
    """{claim key: canonical value} for everything the compiler claims to reproduce."""
    out = {}
    dss = root.findall("datasources/datasource")
    out["datasources"] = [_norm(d.get("name")) for d in dss]
    for d in dss:
        key = f"datasource[{d.get('caption') or _norm(d.get('name'))}]"
        if d.get("name") == "Parameters":
            out[key] = canon(d)  # parameters: whole source, with members (M4)
            continue
        # Calcs and the parameter dependencies they need; not connection/metadata (covered by tests).
        out[f"{key}/calcs"] = sorted(canon(c) for c in d.findall("column") if c.find("calculation") is not None)
        out[f"{key}/datasource-dependencies"] = [canon(e) for e in d.findall("datasource-dependencies")]
    for ws in root.iter("worksheet"):
        name = ws.get("name")
        view = ws.find("table/view")
        if view is None:
            raise ValueError(f"worksheet {name!r} has no <table><view>: not a workbook this tool understands")
        out[f"worksheet[{name}]/view children"] = [c.tag for c in view]
        for tag in ("datasources", "datasource-dependencies", "filter", "slices"):
            out[f"worksheet[{name}]/view/{tag}"] = sorted(canon(e) for e in view.findall(tag))
        out[f"worksheet[{name}]/mark"] = [canon(e) for e in ws.findall("table/panes/pane/mark")]
        out[f"worksheet[{name}]/encodings"] = [canon(e) for e in ws.findall("table/panes/pane/encodings")]
        out[f"worksheet[{name}]/rows"] = _norm(ws.findtext("table/rows") or "")
        out[f"worksheet[{name}]/cols"] = _norm(ws.findtext("table/cols") or "")
    for db in root.iter("dashboard"):
        name = db.get("name")
        out[f"dashboard[{name}]/children"] = [c.tag for c in db]
        for tag in ("size", "datasources", "datasource-dependencies"):
            out[f"dashboard[{name}]/{tag}"] = sorted(canon(e) for e in db.findall(tag))
        if db.find("zones") is None:
            raise ValueError(f"dashboard {name!r} has no <zones>: not a workbook this tool understands")
        zones = list(db.find("zones").iter("zone"))  # not <devicelayouts> (phone layout)
        for kind in ("filter", "color", "size", "paramctrl"):
            mine = [z for z in zones if z.get("type-v2") == kind]
            out[f"dashboard[{name}]/{kind} zone count"] = len(mine)
            for z in mine:  # one claim per zone, so a known diff can't hide the others
                key = f"dashboard[{name}]/{kind} zone[{z.get('name')} {_norm(z.get('param', ''))}]"
                out[key] = {k: _norm(z.get(k)) for k in ZONE_KEYS if z.get(k) is not None}
        top = db.find("zones/zone")
        out[f"dashboard[{name}]/zone tree"] = _tree(top)
        for path, z in _paths(top, "1"):
            out[f"dashboard[{name}]/zone {path} geometry"] = {
                k: z.get(k) for k in GEOMETRY_KEYS if z.get(k) is not None}
        side = [z for z in zones if z.get("is-fixed") == "true" and z.get("param") == "vert"]
        out[f"dashboard[{name}]/side column"] = [
            str({k: z.get(k) for k in ("fixed-size", "is-fixed", "param", "type-v2", "w")}) for z in side]
    return out


def compare(ref_root, gen_root, known=()):
    """Return (mismatches, stale): mismatches are [(claim key, reference value, generated value)]
    for claims that differ and aren't known; stale are known-diff keys that no longer differ
    (fixed, or the claim is gone), so a known diff can't keep hiding a claim that now matches."""
    want, got = claims(ref_root), claims(gen_root)
    bad, stale = [], []
    for key in sorted(set(want) | set(got) | set(known)):
        differs = want.get(key) != got.get(key)
        if key in known:
            if not differs:
                stale.append(key)
        elif differs:
            bad.append((key, want.get(key), got.get(key)))
    return bad, stale


def check(ref_dir):
    from tabgen import build
    with open(os.path.join(ref_dir, "spec.json"), encoding="utf-8") as fh:
        spec = json.load(fh)
    known = {}
    kd = os.path.join(ref_dir, "known-diffs.json")
    if os.path.exists(kd):
        with open(kd, encoding="utf-8") as fh:
            known = json.load(fh)
    gen = ET.fromstring(build(spec, ref_dir))
    ref = ET.parse(os.path.join(ref_dir, "desktop-saved.twb")).getroot()
    return compare(ref, gen, known)


def _print_check(ref_dir):
    bad, stale = check(ref_dir)
    for key, want, got in bad:
        print(f"MISMATCH {key}\n  reference: {want}\n  generated: {got}")
    for key in stale:
        print(f"STALE known-diff (no longer differs; remove it): {key}")
    print(f"{ref_dir}: {'OK' if not bad and not stale else f'{len(bad)} mismatch(es)'}")
    return 1 if bad or stale else 0


# ---------------------------------------------------------------- locking
def sha256(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def lock(ref_dirs):
    for d in ref_dirs:
        d = os.path.normpath(d)
        path = os.path.join(d, "desktop-saved.twb")
        manifest = os.path.join(os.path.dirname(d), "LOCK.json")
        entries = {}
        if os.path.exists(manifest):
            with open(manifest, encoding="utf-8") as fh:
                entries = json.load(fh)
        entries[os.path.basename(d)] = sha256(path)
        with open(manifest, "w", encoding="utf-8") as fh:
            json.dump(dict(sorted(entries.items())), fh, indent=2)
            fh.write("\n")
        os.chmod(path, os.stat(path).st_mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))
        print("locked", path)


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "clean":
        for p in sys.argv[2:]:
            clean(p)
    elif len(sys.argv) == 4 and sys.argv[1] == "diff":
        sys.exit(diff(sys.argv[2], sys.argv[3]))
    elif len(sys.argv) >= 3 and sys.argv[1] == "check":
        sys.exit(max(_print_check(d) for d in sys.argv[2:]))
    elif len(sys.argv) >= 3 and sys.argv[1] == "lock":
        lock(sys.argv[2:])
    else:
        print(__doc__)
        sys.exit(2)
