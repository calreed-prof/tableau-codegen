# Roadmap

Goal: describe a real dashboard in a short spec (and later in plain English) and get a `.twb` that
opens in Tableau Desktop looking finished, without clicking through the GUI.

Each item ships as its own PR, backed by a Desktop-saved reference. Done = merged + opened in Desktop.

## Done
- **M0 Core:** CSV and live Snowflake (OAuth) sources, bar/line/circle/etc. marks, color/size/label/
  detail/tooltip encodings, row-level vs aggregate calcs, grid dashboards, `introspect`.
  Some emitted options are still unverified (see `docs/FORMAT.md`); they get evidence before features
  build on them.
- **Process (PR #1):** independent PR reviewer agent, CI on Python 3.9, git hooks, leak check,
  golden tests.

## Next (in order)
- **Fix: Snowflake metadata remote-types** to match the Desktop reference (see `docs/FORMAT.md`).
- **M1 Filters:** worksheet filters (categorical, boolean, top-N later) and dashboard filter controls.
  Needs the Desktop reference described in `CLAUDE.md` → Current status.
- **M2 Legends:** auto-add color/size legends to dashboards for sheets that use them.
- **M3 Layout:** row heights / column widths, dashboard title, text boxes.
- **M4 Parameters:** list parameters, parameter controls, calcs that reference parameters
  (lets `introspect` keep parameter-driven calcs).
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
