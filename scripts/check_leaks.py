"""Fail if company or machine-specific data is about to be committed.

  python3 scripts/check_leaks.py            # scan all tracked files (CI)
  python3 scripts/check_leaks.py --staged   # scan staged content (pre-commit hook)

Generic rules live here. Company-specific words (employer, account, table names) go in
private/denylist.txt, one regex per line; that file is git-ignored so the list never leaks.
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


def denylist():
    path = os.path.join(ROOT, "private", "denylist.txt")
    if not os.path.exists(path):
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
    staged = "--staged" in sys.argv
    extra = denylist()
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
    print(f"Leak check passed ({'staged' if staged else 'tracked'} files"
          f"{', with private denylist' if extra else ', no private denylist found'}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
