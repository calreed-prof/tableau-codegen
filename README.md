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
githooks/               local guards: no commits/pushes to main, leak check, tests
docs/FORMAT.md          verified facts about the TWB format, each with its evidence
private/                git-ignored: real company workbooks, specs, denylist
```

## Spec reference

Smallest working spec (one CSV, one chart, one dashboard). For a fuller runnable example, start from
`examples/superstore-mini/spec.json`.

```json
{
  "datasources": { "sales": { "csv": "sales.csv" } },
  "sheets": { "Sales by Region": { "cols": "Region", "rows": "sum(Sales)", "mark": "bar" } },
  "dashboards": { "Overview": { "layout": [["Sales by Region"]] } }
}
```

Top level: `datasources` (required, at least one), `sheets` (required), `dashboards` (optional).
Every option:

```json
{
  "datasources": {
    "sales": { "csv": "sales.csv",
               "calcs": { "Profit Ratio": "SUM([Profit]) / SUM([Sales])" } },
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
                                "legends": ["Sales by Region"] } }
}
```

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
  - Easiest way to fill it in: `tabgen introspect` an existing workbook on the same table. It drops
    calcs that reference parameters.
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
  split each row's width equally.
- `filters` (optional): filter controls, `[{"sheet": ..., "field": ...}]`. The sheet must be in the
  layout and already filter on that field. Controls stack in a fixed 160px column on the right, as
  Desktop places them.
- `legends` (optional): sheet names whose color legend to show. Default: one legend per distinct
  color field among the layout's sheets (sheets coloring by the same field share one). `[]` for none.
  Legends stack under the filter controls in the same 160px column. Only color legends for a
  dimension are supported: a sheet listed here with no color, or colored by a measure, is an error
  (the default just skips those). No size legends yet.

Common mistakes stop the build with a clear message instead of producing a broken workbook:
- an unknown field, sheet, data source, mark, aggregation or column type
- missing Snowflake settings or `columns`

Validation is not complete yet: some malformed specs crash with a Python traceback, e.g. a missing
`datasources`, `sheets` or `layout`, an empty `layout`, a column without `type`, or a list given as
an encoding.

## Known limitations (see ROADMAP.md)

- Filters: boolean `true` and lists of 2+ string values only (no single values, exclude, ranges or top-N yet).
- Legends: color legends for dimensions only (no size or continuous color legends).
- No parameters, titles/text boxes, sorting or number formatting yet.
- Layout is equal-split only; long axis labels can be clipped.
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

## Private material

Real company workbooks and specs with live connection details live in `private/` (git-ignored),
along with `private/denylist.txt` (company terms the leak check blocks). Committed examples use
placeholders (`your_account.snowflakecomputing.com`, `YOUR_WAREHOUSE`, ...).

## Development process

See `CLAUDE.md` (rules and current status) and `ROADMAP.md` (scope). In short:
1. Branch, then open a PR.
2. An independent `pr-reviewer` agent posts its verdict as a PR comment.
3. A human verifies the result in Desktop and merges.

Run `git config core.hooksPath githooks` once per clone to enable the local guards: no commits or
pushes to `main`, plus the leak check and tests before every commit.
