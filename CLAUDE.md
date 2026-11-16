# tableau-codegen: rules for AI agents and humans

Write Tableau dashboards as code: a spec compiles to a `.twb` that opens in Tableau Desktop.
Target: Tableau Desktop 2026.2.1, which writes `version='18.1'` + a feature-flag manifest.
Read `README.md` (spec + layout), `ROADMAP.md` (scope) and `docs/FORMAT.md` (verified format facts)
before changing the compiler.

## Current status (update this section in every PR that changes it)

- Done: M0 core (CSV + live Snowflake OAuth sources, calcs, marks/encodings, grid dashboards,
  `introspect`) and the dev process (PR #1: reviewer agent, CI, hooks, leak + golden checks).
- PR #2 (docs: this file, README spec reference, `docs/FORMAT.md` evidence log).
- PR #3: live Snowflake metadata now matches REF-SF (integer 131 +
  precision 38/scale 0, date 7, real precision 15).
- PR #4 (M1 part 1): boolean worksheet filters (`true`) + dashboard filter controls,
  from REF-FILTERS (`private/references/filters-legends/`, see `docs/FORMAT.md`).
- PR #5 (M2 part 1): dashboard color legends for dimension color fields, auto-added or picked with
  `legends`; REF-FILTERS + OPEN-M2.
- PR #7 (M1 part 2): string dimension filters kept to 2+ values, + their dashboard controls (also
  from a second data source); REF-FILTERS-CAT (`private/references/filters-categorical/`).
- **Next: M3 Layout.** M2 part 2 (size and
  continuous color legends) needs a reference: in a saved workbook, color a sheet by a measure and
  put a measure on size, show both legends on the dashboard, and save as
  `private/references/legends-size/desktop-saved.twb`.
- Single-value string filters need a reference (filter a string field to one value, save as
  `private/references/filters-single/desktop-saved.twb`); low priority until a dashboard needs it.
- References: always **Save As** into a new `private/references/<feature>/` folder. A plain Save
  overwrote REF-FILTERS on 2026-11-16.
- The human uses Tableau Desktop 2026.2.1 on macOS, Python 3.9, Snowflake with browser SSO.

## Workflow (mandatory)

1. **Never commit to `main`.** Branch per change: `feat/<roadmap-id>-<slug>`, `fix/<slug>`, `chore/<slug>`.
2. **One roadmap item per PR.** Name the item from `ROADMAP.md` in the PR. Unrelated refactors,
   "while I was here" changes, and features not on the roadmap go in a separate PR or nowhere.
3. **Update the docs in the same PR**: the "Current status" section above, `docs/FORMAT.md` (new
   facts + evidence keys, and anything a Desktop open has since verified), `ROADMAP.md`, and
   `README.md` when the spec changes. Docs-only follow-ups are a sign this step was skipped.
   Open a PR with the template filled in. Run `python3 -m unittest discover tests` and
   `python3 scripts/check_leaks.py --require-denylist` first; both must pass, and CI must be green.
4. **Independent review.** Run the `pr-reviewer` agent on the PR (fresh context, not a fork of the
   authoring session). If the session didn't start in this repo, the agent type isn't registered:
   spawn a fresh general-purpose agent told to follow `.claude/agents/pr-reviewer.md` for PR #n.
   It posts `VERDICT: APPROVE` or `VERDICT: CHANGES REQUESTED`. Verify each blocking item yourself,
   fix it, push, wait for green CI, and re-review with a **new** fresh agent until approved.
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
- `scripts/check_leaks.py` must pass. CI checks generic rules only (it has no company denylist);
  the pre-commit hook and the reviewer also check `private/denylist.txt` via `--require-denylist`.
- This is the human's personal GitHub repo (owner `calreed-prof`). The `gh` CLI has more than one
  account signed in: before any push, check `gh api user --jq .login` prints `calreed-prof`
  (switch with `gh auth switch`).
- The git hooks are local and opt-in (`git config core.hooksPath githooks`) and can be bypassed with
  `--no-verify`; never bypass them. GitHub can't enforce review on this plan, so the rules rely on discipline.

## Commands

```bash
python3 -m tabgen build <spec.json> [-o out.twb] [--open]
python3 -m tabgen introspect <existing.twb>     # connections/columns/calcs -> spec JSON
python3 -m unittest discover tests
python3 scripts/check_leaks.py --require-denylist
python3 scripts/refdiff.py clean <desktop-saved.twb>   # strip fingerprints/thumbnails
python3 scripts/refdiff.py diff <reference.twb> <generated.twb>
git config core.hooksPath githooks              # once per clone
```
