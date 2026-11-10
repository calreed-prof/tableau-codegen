"""Fail if company or machine-specific data is about to be committed.

  python3 scripts/check_leaks.py                      # scan all tracked files (CI: generic rules only)
  python3 scripts/check_leaks.py --staged             # scan staged content (pre-commit hook)
  python3 scripts/check_leaks.py --require-denylist   # fail unless the company denylist was loaded
  python3 scripts/check_leaks.py --denylist PATH      # explicit denylist (or env TABGEN_DENYLIST)

Generic rules live here. Company-specific words (employer, account, table names) go in
private/denylist.txt, one regex per line; that file is git-ignored so the list never leaks.
The denylist is found automatically in this checkout's private/ or, from a git worktree, in the
main checkout's private/. CI has no denylist, so CI only enforces the generic rules; the
pre-commit hook and the reviewer run with --require-denylist.
"""
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLACEHOLDER_HOSTS = {"your_account.snowflakecomputing.com", "acct.snowflakecomputing.com"}

RULES = [
    ("real Snowflake host", re.compile(r"[\w.-]+\.snowflakecomputing\.com")),
    ("absolute home path", re.compile(r"/(?:Users|home)/[\w.-]+/")),
    ("Desktop fingerprint", re.compile(r"WorkbookFingerprinting")),
    ("private/ file", None),  # path rule, handled separately
]
SELF = {"scripts/check_leaks.py", "scripts/refdiff.py"}  # these mention the patterns on purpose


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout


def denylist_path(explicit=None):
    """First existing candidate: --denylist, $TABGEN_DENYLIST, ./private, main checkout's private/."""
    candidates = [explicit, os.environ.get("TABGEN_DENYLIST"), os.path.join(ROOT, "private", "denylist.txt")]
    try:
        common = git("rev-parse", "--path-format=absolute", "--git-common-dir").strip()
        candidates.append(os.path.join(os.path.dirname(common), "private", "denylist.txt"))
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    for path in candidates:
        if path and os.path.isfile(path):
            return path
    if explicit:
        raise SystemExit(f"Denylist not found: {explicit}")
    return None


def denylist(path):
    if not path:
        return []
    with open(path, encoding="utf-8") as fh:
        return [re.compile(ln.strip(), re.I) for ln in fh if ln.strip() and not ln.startswith("#")]


def files(staged):
    if staged:
        out = git("diff", "--cached", "--name-only", "--diff-filter=ACMR")
    else:
        out = git("ls-files")
    return [f for f in out.splitlines() if f]


def content(path, staged):
    if staged:
        return subprocess.run(["git", "show", f":{path}"], cwd=ROOT, capture_output=True).stdout
    with open(os.path.join(ROOT, path), "rb") as fh:
        return fh.read()


def main():
    import argparse
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--staged", action="store_true", help="scan staged content instead of tracked files")
    ap.add_argument("--denylist", help="path to the company denylist")
    ap.add_argument("--require-denylist", action="store_true",
                    help="fail if no denylist is found (otherwise company terms go unchecked)")
    args = ap.parse_args()
    staged = args.staged
    dl_path = denylist_path(args.denylist)
    if args.require_denylist and not dl_path:
        print("Leak check NOT VERIFIED: no company denylist found (private/denylist.txt, "
              "--denylist or $TABGEN_DENYLIST). Company terms were not checked.")
        return 2
    extra = denylist(dl_path)
    problems = []
    for f in files(staged):
        if f.startswith("private/"):
            problems.append(f"{f}: files under private/ must never be committed")
            continue
        if f in SELF:
            continue
        text = content(f, staged).decode("utf-8", errors="ignore")
        for lineno, line in enumerate(text.splitlines(), 1):
            for label, rx in RULES:
                if rx is None:
                    continue
                for m in rx.finditer(line):
                    if label == "real Snowflake host" and m.group(0).lower() in PLACEHOLDER_HOSTS:
                        continue
                    problems.append(f"{f}:{lineno}: {label}: {m.group(0)}")
            for rx in extra:
                if rx.search(line):
                    problems.append(f"{f}:{lineno}: denylisted term (private/denylist.txt)")
    if problems:
        print("Leak check FAILED:\n  " + "\n  ".join(problems))
        print("\nScrub these (see CLAUDE.md > Data hygiene) or move the file to private/.")
        return 1
    scope = "staged" if staged else "tracked"
    if dl_path:
        print(f"Leak check passed ({scope} files, generic rules + company denylist).")
    else:
        print(f"Leak check passed ({scope} files, generic rules only: NO company denylist, "
              f"company terms not checked).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
