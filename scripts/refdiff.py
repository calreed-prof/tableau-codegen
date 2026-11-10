"""Golden-file helpers.

  python3 scripts/refdiff.py clean <desktop-saved.twb>
      Strip machine/author fingerprints and thumbnails from a file saved by Tableau
      Desktop, in place, so it is safe to commit as a reference.

  python3 scripts/refdiff.py diff <reference.twb> <generated.twb>
      Normalise both files (generated ids, quoting, UI-only state) and print a unified
      diff, so only meaningful structural differences remain.
"""
import difflib
import re
import sys

ID_PATTERNS = [
    (re.compile(r"(federated|textscan|snowflake|sqlproxy)\.[a-z0-9]{20,}"), r"\1.<id>"),
    (re.compile(r"_[A-F0-9]{32}\b"), "_<objid>"),
    (re.compile(r"uuid=\"\{[^}]+\}\""), 'uuid="<uuid>"'),
    (re.compile(r"\bid=\"-?\d+\""), 'id="<n>"'),
    (re.compile(r"Calculation_\d+"), "Calculation_<n>"),
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


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "clean":
        for p in sys.argv[2:]:
            clean(p)
    elif len(sys.argv) == 4 and sys.argv[1] == "diff":
        sys.exit(diff(sys.argv[2], sys.argv[3]))
    else:
        print(__doc__)
        sys.exit(2)
