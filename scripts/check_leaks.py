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


class LeakCheckError(SystemExit):
    """Configuration problem: exits with status 2 ("not verified"), never a silent pass."""

    def __init__(self, msg):
        print(f"Leak check NOT VERIFIED: {msg}", file=sys.stderr)
        super().__init__(2)


def denylist_path(explicit=None):
    """An explicit path (--denylist, else $TABGEN_DENYLIST) must exist: no fallback.
    Otherwise use ./private/denylist.txt, then the main checkout's (for git worktrees)."""
    explicit = explicit or os.environ.get("TABGEN_DENYLIST")
    if explicit:
        if not os.path.isfile(explicit):
            raise LeakCheckError(f"denylist not found: {explicit}")
        return explicit
    candidates = [os.path.join(ROOT, "private", "denylist.txt")]
    try:
        common = git("rev-parse", "--path-format=absolute", "--git-common-dir").strip()
        candidates.append(os.path.join(os.path.dirname(common), "private", "denylist.txt"))
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    return next((p for p in candidates if os.path.isfile(p)), None)


def denylist(path):
    if not path:
        return []
    patterns = []
    with open(path, encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, 1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            try:
                patterns.append(re.compile(line, re.I))
            except re.error as e:
                raise LeakCheckError(f"{path}:{lineno}: invalid regex ({e})")
    if not patterns:
        raise LeakCheckError(f"{path} has no patterns (only comments/blank lines)")
    return patterns


def files(staged):
    if staged:
        out = git("diff", "--cached", "--name-only", "--diff-filter=ACMR")
    else:
        out = git("ls-files")
    return [f for f in out.splitlines() if f]


def content(path, staged):
    if staged:
        return subprocess.run(["git", "show", f":{path}"], cwd=ROOT, capture_output=True).stdout
    full = os.path.join(ROOT, path)
    if not os.path.exists(full):
        return b""  # tracked but deleted on disk: nothing to leak
    with open(full, "rb") as fh:
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
