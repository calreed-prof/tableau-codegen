"""Reference checks: generated XML vs every Desktop-saved reference, and reference integrity.

For each references/<dir> and private/references/<dir> holding spec.json + desktop-saved.twb, build
the spec and compare everything the compiler claims to reproduce (scripts/refdiff.py claims()).
Allowed, documented differences live in <dir>/known-diffs.json. private/ is git-ignored, so its
cases run locally (pre-commit hook) and are skipped in CI.

Each reference root's LOCK.json pins the SHA-256 of its desktop-saved.twb files, so a reference
that Desktop (or anyone) saved over fails here instead of silently changing the evidence.
"""
import importlib.util
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location("refdiff", os.path.join(ROOT, "scripts", "refdiff.py"))
refdiff = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(refdiff)

ROOTS = [os.path.join(ROOT, "references"), os.path.join(ROOT, "private", "references")]


def ref_dirs(root, need_spec):
    if not os.path.isdir(root):
        return []
    out = []
    for name in sorted(os.listdir(root)):
        d = os.path.join(root, name)
        if os.path.isfile(os.path.join(d, "desktop-saved.twb")) and (
                not need_spec or os.path.isfile(os.path.join(d, "spec.json"))):
            out.append(d)
    return out


class ReferenceTests(unittest.TestCase):
    def test_claims_match_references(self):
        dirs = [d for r in ROOTS for d in ref_dirs(r, need_spec=True)]
        self.assertTrue(dirs)
        for d in dirs:
            with self.subTest(ref=os.path.relpath(d, ROOT)):
                bad, stale = refdiff.check(d)
                msg = "\n".join(f"{k}\n  reference: {w}\n  generated: {g}" for k, w, g in bad)
                self.assertEqual(bad, [], "\n" + msg)
                self.assertEqual(stale, [], "known-diffs.json lists claims that no longer exist")

    def test_references_locked(self):
        for root in ROOTS:
            dirs = ref_dirs(root, need_spec=False)
            if not dirs:
                continue
            manifest = os.path.join(root, "LOCK.json")
            with self.subTest(root=os.path.relpath(root, ROOT)):
                self.assertTrue(os.path.isfile(manifest),
                                f"missing {manifest}: run python3 scripts/refdiff.py lock <dir>...")
                import json
                with open(manifest, encoding="utf-8") as fh:
                    locked = json.load(fh)
                for d in dirs:
                    name = os.path.basename(d)
                    self.assertIn(name, locked, f"{name} is not locked: python3 scripts/refdiff.py lock {d}")
                    self.assertEqual(refdiff.sha256(os.path.join(d, "desktop-saved.twb")), locked[name],
                                     f"{name}/desktop-saved.twb changed since it was locked. If Desktop saved "
                                     f"over it, restore it; only re-lock a deliberately replaced reference")


if __name__ == "__main__":
    unittest.main()
