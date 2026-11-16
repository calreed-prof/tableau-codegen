# Roadmap

Goal: describe a real dashboard in a short spec (and later in plain English) and get a `.twb` that
opens in Tableau Desktop looking finished, without clicking through the GUI.

Each item ships as its own PR, backed by a Desktop-saved reference. Done = merged + opened in Desktop.

## Done
- **M0 Core:** CSV and live Snowflake (OAuth) sources, bar/line/circle marks, color encoding,
  row-level vs aggregate calcs, grid dashboards, `introspect`. The compiler also emits other marks
  and `size`/`detail` etc., which are still **unverified** (`docs/FORMAT.md`); they get evidence
  before features build on them.
- **Process (PR #1):** independent PR reviewer agent, CI on Python 3.9, git hooks, leak check,
  golden tests.
- **PR #2:** docs (`CLAUDE.md`, README spec reference, `docs/FORMAT.md` evidence log).
- **Fix (PR #3):** Snowflake metadata remote-types match the Desktop reference.
- **M1 Filters (part 1, PR #4):** boolean worksheet filters + dashboard filter controls.
- **M2 Legends (part 1, PR #5):** dashboard color legends for dimension color fields.
- **PR #6:** docs follow-up to #5 (recorded the Desktop opens, added the docs-in-the-same-PR rule).
- **M1 Filters (part 2, PR #7):** string dimension filters kept to 2+ values, controls from several
  data sources.
- **Dev tooling (PR #8):** reference checks for every reference (private ones locally) and
  hash-pinned references. The read-only bit is local only: re-run `refdiff.py lock` after a clone.
- **PR #9:** docs clarity pass.
- **M3 Layout (PR #10):** Desktop's 8px padding, fixed row heights / column widths, dashboard title,
  one-line text box; `check` now claims the zone tree and every zone's geometry.
- **M4 Parameters (part 1, PR #12):** string list parameters, calcs that use them, dashboard
  parameter controls; `introspect` keeps those calcs; `check` also claims calcs and the Parameters
  source.

## Next (in order)
- **M2 Legends (part 2):** size and continuous color legends; needs a reference (see `CLAUDE.md`).
- **M1 Filters (part 3):** single values, exclude, numeric/date ranges, top-N; each needs a reference.
- **M4 Parameters (part 2):** number/date parameters, ranges, aliases, controls next to filter
  controls; each needs a reference.
- **M5 Formatting:** number formats, axis ranges, sort order, mark labels.
- **M6 Spec v2:** YAML (or a small DSL) front end over the same compiler; JSON stays supported.
- **M7 AI authoring:** plain English → spec via the Claude API, validated by the compiler's errors in
  a repair loop. The model only ever writes the spec, never XML.

## Later (needs a reason before it moves up)
- Extracts (`.hyper`) and packaged `.twbx`
- Dashboard actions (filter / highlight / URL)
- Published data sources on Tableau Server/Cloud; REST publish + Validate Workbook endpoint
- Import: full `.twb` → spec round trip

## Not doing
- Live preview / a custom renderer (dropped 2026-11-10: open the file in Desktop instead)
- Emitting the `26.2` + `ManifestByVersion` format until Desktop itself saves it
- Recreating the Tableau GUI, or a general XML editor
- Data sources nobody here uses (add them when a real dashboard needs one)
