# tableau-codegen: rules for AI agents and humans

Write Tableau dashboards as code: a spec compiles to a `.twb` that opens in Tableau Desktop.
Target: Tableau Desktop 2026.2.1, which writes `version='18.1'` + a feature-flag manifest.
Read `README.md` (spec + layout), `ROADMAP.md` (scope) and `docs/FORMAT.md` (verified format facts)
before changing the compiler.

## Current status (keep this short; history lives in `ROADMAP.md` → Done)

- **Next: M3 Layout** (row heights / column widths, dashboard title, text boxes). It should also fix
  the outer padding (Desktop: x=571/y=889 at 1400x900; we use 800/1000) so `refdiff.py check` can
  claim zone x/y.
- **Waiting on a Desktop reference** (the human builds these; see `references/README.md`):
  - M2 part 2, size + continuous color legends: color a sheet by a measure, put a measure on size,
    show both legends on a dashboard → `private/references/legends-size/desktop-saved.twb`.
  - Single-value string filter (low priority): → `private/references/filters-single/desktop-saved.twb`.
- The human uses Tableau Desktop 2026.2.1 on macOS, Python 3.9, Snowflake with browser SSO.

**Evidence keys** (REF-SF, REF-FILTERS, OPEN-M2, ...) appear across these docs. `REF-x` = a workbook
saved by Desktop, `OPEN-x` = the human opened our output in Desktop, `OBS` = a recorded observation.
All are defined, with where the file lives, at the top of `docs/FORMAT.md`. Most are in `private/`
(maintainer only).

## Workflow (mandatory)

1. **Never commit to `main`.** Branch per change: `feat/<roadmap-id>-<slug>`, `fix/<slug>`, `chore/<slug>`
   (`chore/` for tooling and docs-only changes).
2. **One roadmap item per PR.** Name the item from `ROADMAP.md` in the PR. Unrelated refactors,
   "while I was here" changes, and features not on the roadmap go in a separate PR or nowhere.
3. **Update the docs in the same PR** as the change it describes:
   - "Current status" above, if the next step or open reference requests change;
   - `ROADMAP.md` → Done, for a finished item (one line, with the PR number);
   - `docs/FORMAT.md`: new facts with their evidence keys, and anything a Desktop open has since
     verified;
   - `README.md`, when the spec changes.

   A docs-only PR is fine for docs work itself, but not as a follow-up to a change that skipped this step.
4. **Check, then open the PR.**
   - Run `python3 -m unittest discover tests` and `python3 scripts/check_leaks.py --require-denylist`.
     Both must pass.
   - Without `private/denylist.txt` (outside contributors), the leak check exits 2 ("NOT VERIFIED").
     Say so in the PR; the maintainer's review runs the full check.
   - Open the PR with the template filled in. CI must be green.
5. **Independent review.** Run the `pr-reviewer` agent on the PR (fresh context, not a fork of the
   authoring session). If the session didn't start in this repo, the agent type isn't registered:
   spawn a fresh general-purpose agent told to follow `.claude/agents/pr-reviewer.md` for PR #n.
   - It posts `VERDICT: APPROVE` or `VERDICT: CHANGES REQUESTED` as a PR comment. Link that comment
     in the template's Review section.
   - Verify each blocking item yourself, fix it, push, wait for green CI, and re-review with a
     **new** fresh agent until approved.
6. **The human merges** (squash) after the approval *and* after confirming the generated workbook
   opens in Tableau Desktop when the PR changes generated XML. AI agents do not merge.

## Evidence rule (no guessing the file format)

Tableau's real format is only partly documented, and the published XSD doesn't match Desktop.
- Every change to what the compiler emits must be backed by a workbook **saved by Tableau Desktop**
  under `references/<feature>/` (or `private/references/` if it holds company data, then
  summarised in the PR), plus a test that checks the generated XML against it.
- Do not invent element names, attributes or enum values. If no reference shows it, get one:
  ask the human to build the smallest example in Desktop, following `references/README.md`.
- PR descriptions say what was verified and how; "should work" is not evidence.

## Scope guardrails

- Stdlib-only Python, compatible with 3.9. New dependencies need a roadmap item that says why.
- Keep the spec small and declarative. A spec key is added only when a real dashboard needs it.
- Prefer clear spec errors (`SpecError`) over silently emitting XML Tableau may reject.

## Data hygiene

- Real company workbooks, specs and connection details live only in `private/` (git-ignored).
- Committed examples use placeholders (`your_account.snowflakecomputing.com`, `YOUR_WAREHOUSE`).
- New Desktop references: follow `references/README.md` (Save As into a new folder, `clean`, a
  `spec.json`, `lock`, `check`). Replace server, username, database, schema and table names before
  committing.
- `scripts/check_leaks.py` must pass. CI checks generic rules only (it has no company denylist);
  the pre-commit hook and the reviewer also check `private/denylist.txt` via `--require-denylist`.
- Maintainer setup: this is the human's personal GitHub repo (owner `calreed-prof`). The `gh` CLI has more than one
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
python3 scripts/refdiff.py check <reference-dir>        # claimed XML vs Desktop (tests run it too)
python3 scripts/refdiff.py lock <reference-dir>         # read-only + SHA-256 in LOCK.json
git config core.hooksPath githooks              # once per clone
```
