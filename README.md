# tableau-codegen

Write Tableau dashboards as code: a JSON spec compiles to a `.twb` that opens in Tableau Desktop
2026.2.1 as a working workbook, with no clicking through the GUI. Stdlib-only Python 3.9+.

```bash
python3 -m tabgen build examples/superstore-mini/spec.json --open   # build and open in Desktop
python3 -m tabgen introspect path/to/existing.twb > start.json       # lift connections/columns/calcs
python3 -m unittest discover tests
```

What works today and what's next: `ROADMAP.md`. What each piece of XML is backed by: `docs/FORMAT.md`.

## Repo layout

```
tabgen/compiler.py      spec -> .twb (data sources, worksheets, dashboards, windows)
tabgen/introspect.py    existing .twb -> spec "datasources" blocks
tabgen/__main__.py      CLI: build, introspect
tests/                  unit tests + golden tests against Desktop-saved references
references/             Desktop-saved .twb + spec.json per feature, LOCK.json (how-to: references/README.md)
examples/               runnable specs (Snowflake example uses placeholders); built .twb files are
                        git-ignored, regenerate them with `tabgen build`
scripts/refdiff.py      reference tools: clean, diff, check (claimed XML vs Desktop), lock
scripts/check_leaks.py  blocks company data, home paths and fingerprints from commits
githooks/               local guards: no commits/pushes to main (docs-only excepted), leak check, tests
docs/FORMAT.md          verified facts about the TWB format, each with its evidence
private/                git-ignored: real company workbooks, specs, denylist
```

## Spec reference

Smallest working spec (one CSV, one chart, one dashboard). It expects a `sales.csv` with `Region`
and `Sales` columns next to the spec, e.g. save it as `examples/superstore-mini/min.json`. For a
fuller runnable example, start from `examples/superstore-mini/spec.json`.

```json
{
  "datasources": { "sales": { "csv": "sales.csv" } },
  "sheets": { "Sales by Region": { "cols": "Region", "rows": "sum(Sales)", "mark": "bar" } },
  "dashboards": { "Overview": { "layout": [["Sales by Region"]] } }
}
```

Top level: `datasources` (required, at least one), `sheets` (required), `dashboards` (optional),
`parameters` (optional).
Every option:

```json
{
  "parameters": { "Metric Choice": { "type": "string", "values": ["Sales", "Profit"], "value": "Sales" } },
  "datasources": {
    "sales": { "csv": "sales.csv",
               "calcs": { "Profit Ratio": "SUM([Profit]) / SUM([Sales])",
                          "Chosen Metric": "IF [Metric Choice] = 'Sales' THEN [Sales] ELSE [Profit] END" } },
    "orders": {
      "snowflake": { "server": "your_account.snowflakecomputing.com", "warehouse": "YOUR_WAREHOUSE",
                     "database": "YOUR_DATABASE", "schema": "YOUR_SCHEMA", "table": "ORDERS",
                     "username": "YOUR_USERNAME", "role": "", "auth": "oauth" },
      "columns": { "REGION": "string", "SALES_AMT": "real",
                   "FISCAL_YEAR": { "type": "integer", "role": "dimension" },
                   "ORDER_TS": { "type": "datetime", "caption": "Order Time" } },
      "calcs": { "Sales K": { "formula": "[SALES_AMT] / 1000", "type": "real", "role": "measure" },
                 "Recent": { "formula": "{ FIXED : MAX([ORDER_TS]) } = [ORDER_TS]", "type": "boolean" } }
    }
  },
  "sheets": {
    "Sales by Region": { "datasource": "sales", "cols": "Region", "rows": "sum(Sales)",
                         "color": "Category", "mark": "bar" },
    "Orders": { "datasource": "orders", "cols": "Region", "rows": "sum(Sales Amt)",
                "filters": { "Recent": true } }
  },
  "dashboards": { "Overview": { "size": [1200, 800], "layout": [["Sales by Region", "Orders"]],
                                "filters": [{ "sheet": "Orders", "field": "Recent" }],
                                "legends": ["Sales by Region"] },
                  "Metrics": { "layout": [["Sales by Region"]], "parameters": ["Metric Choice"] } }
}
```

**Parameters** (keyed by the name shown in Tableau):
- `type`: `string` (the only type so far). `values`: the list of allowed values, at least one, all
  different. `value` (optional): the current value; default the first.
- Calcs name a parameter like a field: `[Metric Choice]`. A parameter can't share its name with a
  field or calc.
- Numbers, dates, ranges, display names (aliases) and values containing `"` or `\` are a `SpecError`
  until there's a Desktop reference.

**Data sources** (keyed by a short name; the first one is the default for sheets):
- `caption` (optional): the name shown in Tableau. Default: CSV file name / Desktop-style
  `TABLE (DB.TABLE) (SCHEMA)`.
- `csv`: path relative to the spec. Column types (string/integer/real/date) are inferred.
- `snowflake`: live connection.
  - Required: `server`, `warehouse`, `database`, `schema`, `table`. Optional: `username`, `role`.
  - `auth` (default `oauth`):
    - `oauth` (aliases `sso`, `browser`): verified; opening the workbook prompts a browser sign-in.
    - `password` is written as an unverified guess.
    - Any other value is copied into the XML as-is, with no error. Don't use these until there's a
      reference.
  - Needs a `columns` map: `name -> type`, or `{type, caption, role}`. Types: `string integer real
    date datetime boolean`.
  - ALL_CAPS names get Desktop-style captions (`SALES_AMT` → "Sales Amt").
  - Easiest way to fill it in: `tabgen introspect` an existing workbook on the same table. It keeps
    calcs that use string list parameters (and adds a `parameters` block), and drops calcs on other
    parameters.
- `calcs`: `caption -> formula` (a real measure) or `{formula, type, role}`. Formulas use Tableau
  syntax with raw column names (`[SALES_AMT]`).

**Sheets:**
- Keys:
  - `datasource` (optional)
  - `rows`, `cols`: a field or a list of fields, e.g. `"rows": ["sum(Sales)", "sum(Profit)"]`
  - `mark`: default `automatic`
  - encodings `color`, `size`, `label`, `detail`, `tooltip`: one field each, e.g.
    `"color": "Category"`, `"size": "sum(Profit)"`
  - `filters`: `field -> value`. Supported:
    - a boolean field (usually a boolean calc) kept to `true`: `{"Recent": true}`
    - a string dimension kept to two or more values: `{"Region": ["East", "West"]}`

    Anything else (one value, exclude, numbers, dates, ranges, top-N) is a `SpecError` until
    there's a Desktop reference for it.
- A field is written `name` or `wrapper(name)`, e.g. `Region`, `sum(Sales)`, `yr(Order Date)`,
  `agg(Profit Ratio)`. The name is the raw column name or its caption (`SALES_AMT` or `Sales Amt`).
  Wrappers:
  - aggregations: `sum avg min max count countd`
  - date parts: `yr qr mn`
  - `none`: use as a dimension
  - `agg` or `usr`: an aggregate calc
- The wrapper isn't checked against the field type: `yr(Sales)` or `sum(Region)` builds, but makes a
  view Tableau may reject.
- Defaults:
  - measures → `sum`
  - aggregate calcs (`SUM(..)/SUM(..)`) → used as-is
  - dimensions → `none`
  - dates → `yr`
- Marks: `bar line circle square text pie automatic area`.
- Evidence status (details and evidence keys in `docs/FORMAT.md`):
  - Opened correctly in Desktop: `sum`, `avg`, `none`, aggregate calcs; `bar`, `line`, `circle`;
    `color`.
  - Seen in a Desktop-saved reference: `label` (text), `tooltip`, `automatic`.
  - Unverified: `min`/`max`/`count`/`countd`, `yr`/`qr`/`mn`; `square`, `text`, `pie`, `area`;
    `size`, `detail`. The `count`/`countd` shelf prefixes are probably wrong.

**Dashboards:**
- `size` is `[width, height]` in px. Default `[1200, 800]`.
- `layout` is a list of rows, each a list of sheet names. Rows split the height equally, and sheets
  split each row's width equally, unless sized. Tableau re-sizes flexible zones by content, so equal
  shares are written as fixed px on every row/sheet but the last (which fills the rest), the way
  Desktop saves a split you drag to 50/50:
  - `row_heights` (optional): one entry per row, px or `null`, e.g. `[456, null]`. A px row is fixed
    at that height; `null` rows share what's left. At least one must be `null`.
  - `col_widths` (optional): one list per row, one entry per sheet, px or `null`, e.g.
    `[[609, null], [null]]`. Same rules, within the row's width.
- `title` (optional): `true` shows the dashboard's name as a title at the top (42px).
- `text` (optional): one line of plain text shown under the title, above the charts, e.g.
  `"Sales overview for Q3"`.
- `filters` (optional): filter controls, `[{"sheet": ..., "field": ...}]`. The sheet must be in the
  layout and already filter on that field. Controls stack in a fixed 160px column on the right, as
  Desktop places them.
- `legends` (optional): sheet names whose legends to show. Each sheet shows its color legend (for a
  dimension or a measure), then its size legend (for a measure). Default: every sheet in the layout,
  skipping a legend for a field already shown (sheets coloring by the same field share one). `[]` for
  none. Legends stack under the filter controls in the same 160px column. A date part on color and a
  dimension on size get no legend yet; a sheet listed here with no legend to show is an error.
- `parameters` (optional): parameter names whose control (a drop-down) to show, below the legends in
  the same 160px column. Can't be combined with `filters` on one dashboard yet.

Common mistakes stop the build with a clear message instead of producing a broken workbook:
- an unknown field, sheet, data source, mark, aggregation or column type
- a missing, empty or malformed `layout`, or sizes that don't fit
- missing Snowflake settings or `columns`

Validation is not complete yet: some malformed specs crash with a Python traceback, e.g. a missing
or empty `datasources`, a missing `sheets`, a column without `type`, or a list given as an encoding.

## Known limitations (see ROADMAP.md)

- Filters: boolean `true` and lists of 2+ string values only (no single values, exclude, ranges or top-N yet).
- Legends: no legends for a date part on color or a dimension on size yet.
- Layout: fixed px sizes or equal splits; one title (the dashboard name) and one line of text above
  the charts. No custom title text, multi-line or formatted text, or floating objects yet.
- Parameters: string lists only; their controls can't share a dashboard with filter controls yet.
- No sorting or number formatting yet. Long axis labels can be clipped.
- Live connections only (no extracts / `.twbx`).

## Target format

Tableau Desktop 2026.2.1 writes `version='18.1'` with a feature-flag manifest, and that is what we
emit. The `26.2` + `<ManifestByVersion/>` format from
[tableau-document-schemas](https://github.com/tableau/tableau-document-schemas) triggers stricter
internal validation in Desktop, and Desktop-saved files don't pass the published XSD, so the XSD is
advisory only. **Ground truth is files saved by Desktop**; verified facts are in `docs/FORMAT.md`.

## Golden-file workflow (how we learn new features)

New format facts come from workbooks saved by Tableau Desktop, never from guessing. The step-by-step
(who does what in Desktop, then `clean`, `spec.json`, `lock`, `check`) is in `references/README.md`;
the rule itself is in `CLAUDE.md` → Evidence rule.

## Development process

See `CLAUDE.md` (rules and current status) and `ROADMAP.md` (scope). In short:
1. Branch, then open a PR.
2. An independent `pr-reviewer` agent posts its verdict as a PR comment.
3. A human verifies the result in Desktop and merges.

Docs-only changes (Markdown outside `.claude/` and `.github/`) can skip this and go straight to
`main` (the "fast lane"; limits in `CLAUDE.md`). AI agents get a quick reviewer verdict before pushing.

Run `git config core.hooksPath githooks` once per clone to enable the local guards: no commits or
pushes to `main` except docs-only ones, plus the leak check and tests before every commit.
