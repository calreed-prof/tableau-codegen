# tableau-codegen: rules for AI agents and humans

Write Tableau dashboards as code: a spec compiles to a `.twb` that opens in Tableau Desktop.
Target: Tableau Desktop 2026.2.1, which writes `version='18.1'` + a feature-flag manifest.

## Workflow (mandatory)

1. **Never commit to `main`.** Branch per change: `feat/<roadmap-id>-<slug>`, `fix/<slug>`, `chore/<slug>`.
2. **One roadmap item per PR.** Name the item from `ROADMAP.md` in the PR. Unrelated refactors,
   "while I was here" changes, and features not on the roadmap go in a separate PR or nowhere.
3. Open a PR with the template filled in. Run `python3 -m unittest discover tests` and
   `python3 scripts/check_leaks.py` first; both must pass.
4. **Independent review.** Run the `pr-reviewer` agent on the PR (fresh context, not a fork of the
   authoring session). It posts `VERDICT: APPROVE` or `VERDICT: CHANGES REQUESTED`.
   Address every blocking item, push, and re-review until approved.
5. **The human merges** (squash) after the approval *and* after confirming the generated workbook
   opens in Tableau Desktop when the PR changes generated XML. AI agents do not merge.

## Evidence rule (no guessing the file format)

Tableau's real format is only partly documented, and the published XSD doesn't match Desktop.
- Every change to what the compiler emits must be backed by a workbook **saved by Tableau Desktop**
  under `references/<feature>/` (or `private/references/` if it holds company data, then
  summarised in the PR), plus a test that checks the generated XML against it.
- Do not invent element names, attributes or enum values. If no reference shows it, get one:
  ask the human to build the smallest example in Desktop and *Save As* `.twb`.
- PR descriptions say what was verified and how; "should work" is not evidence.

## Scope guardrails

- Stdlib-only Python, compatible with 3.9. New dependencies need a roadmap item that says why.
- Keep the spec small and declarative. A spec key is added only when a real dashboard needs it.
- Prefer clear spec errors (`SpecError`) over silently emitting XML Tableau may reject.

## Data hygiene

- Real company workbooks, specs and connection details live only in `private/` (git-ignored).
- Committed examples use placeholders (`your_account.snowflakecomputing.com`, `YOUR_WAREHOUSE`).
- New Desktop references: run `python3 scripts/refdiff.py clean <file>` and replace server,
  username, database, schema and table names before committing.
- `scripts/check_leaks.py` (pre-commit hook and CI) must pass.

## Commands

```bash
python3 -m tabgen build <spec.json> [-o out.twb] [--open]
python3 -m tabgen introspect <existing.twb>     # connections/columns/calcs -> spec JSON
python3 -m unittest discover tests
python3 scripts/check_leaks.py
python3 scripts/refdiff.py diff <reference.twb> <generated.twb>
git config core.hooksPath githooks              # once per clone
```
