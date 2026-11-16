# Desktop references

Only `csv-basic/` is committed; company-data references live in git-ignored `private/references/`
(maintainer only). Each folder is one feature's evidence: a workbook **saved by Tableau Desktop**, plus a `spec.json`
that rebuilds it. Company-data references follow the same layout under `private/references/`
(git-ignored). See `docs/FORMAT.md` for what each reference proves.

```
<feature>/desktop-saved.twb   saved by Desktop (read-only once locked)
<feature>/spec.json           spec that rebuilds it
<feature>/known-diffs.json    optional: {"<claim key>": "<why this difference is accepted>"}
LOCK.json                     SHA-256 of every desktop-saved.twb in this folder
```

## Making a new reference (human, in Desktop)

1. Start from the smallest workbook that shows the feature. Often that's a generated one: `python3 -m
   tabgen build <spec> --open`.
2. Make the change by hand in Desktop.
3. **File → Save As** into a **new** folder (a plain Save overwrote REF-FILTERS on 2026-11-16) `references/<feature>/desktop-saved.twb` (or
   `private/references/<feature>/` for company data). Never plain *Save* over an existing reference.
   Locked references are read-only, so Desktop will refuse instead of overwriting.
4. Tell the agent the folder name and what you changed.

## Then (agent)

1. Committed references only: `python3 scripts/refdiff.py clean <file>`, and replace server, username,
   database, schema and table names.
2. Write `spec.json` so it describes the saved workbook, then lock it:
   `python3 scripts/refdiff.py lock <dir>`.
3. `python3 scripts/refdiff.py check <dir>` shows each claimed piece of XML that differs.
   `tests/test_references.py` runs the same check for every reference. Private ones run locally and
   in the pre-commit hook, and are skipped in CI.
4. Teach the compiler until `check` passes, or record an accepted difference in `known-diffs.json`
   with its reason. Add the facts to `docs/FORMAT.md`.

Git doesn't keep the read-only bit, so in a fresh clone the hash in `LOCK.json` is the only guard
until you run `lock` again. If Desktop saves by writing a new file and renaming it over the old one,
a read-only file may not stop it; the hash test still catches the change.

To replace a reference on purpose, `chmod u+w` it, save the new one, and lock it again. A changed
hash otherwise fails `test_references_locked`.
