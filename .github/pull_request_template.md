## Roadmap item
<!-- e.g. M1 Filters. One item per PR. Use "fix" or "chore" if not a roadmap item. -->

## What changed
<!-- Short. What the spec can now express and what the compiler emits. -->

## Evidence
<!-- Desktop-saved reference(s) this is based on: references/<feature>/... (or a private/ reference,
     summarised). Which test compares generated output against it. -->

## Verification
- [ ] `python3 -m unittest discover tests` passes
- [ ] `python3 scripts/check_leaks.py --require-denylist` passes (CI runs generic rules only)
- [ ] Generated workbook opened in Tableau Desktop 2026.2.1 and looked right (human, if emitted XML changed)
- [ ] README updated if the spec changed

## Review
- [ ] `pr-reviewer` verdict: APPROVE (link the comment)
