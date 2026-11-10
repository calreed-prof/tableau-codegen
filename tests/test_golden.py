"""Golden tests: generated XML must match workbooks saved by Tableau Desktop (references/).

Each case lists the top-level sections we claim to reproduce exactly (after normalising generated
ids and machine paths). Sections not listed are known to differ and are not claimed yet.
"""
import importlib.util
import json
import os
import re
import tempfile
import unittest

from tabgen import build

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location("refdiff", os.path.join(ROOT, "scripts", "refdiff.py"))
refdiff = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(refdiff)

CASES = [
    # (reference dir, sections that must match exactly)
    ("csv-basic", ["datasources", "worksheets"]),
]


def section(lines, tag):
    text = "\n".join(lines)
    m = re.search(rf"^\s*<{tag}>.*?^\s*</{tag}>", text, re.S | re.M)
    if not m:
        raise AssertionError(f"<{tag}> not found")
    return re.sub(r"directory=\"[^\"]*\"", 'directory="<dir>"', m.group(0)).splitlines()


class GoldenTests(unittest.TestCase):
    def test_references(self):
        for ref, sections in CASES:
            d = os.path.join(ROOT, "references", ref)
            with open(os.path.join(d, "spec.json")) as fh:
                spec = json.load(fh)
            with tempfile.NamedTemporaryFile("w", suffix=".twb", delete=False, encoding="utf-8") as out:
                out.write(build(spec, d))
            want = refdiff.normalise(os.path.join(d, "desktop-saved.twb"))
            got = refdiff.normalise(out.name)
            for tag in sections:
                with self.subTest(ref=ref, section=tag):
                    self.assertEqual(section(want, tag), section(got, tag))


if __name__ == "__main__":
    unittest.main()
