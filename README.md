# tableau-codegen

Write Tableau dashboards as code: a JSON spec compiles to a `.twb` that opens in Tableau Desktop
2026.2.1 as a working workbook, with no clicking through the GUI. Stdlib-only Python 3.9+.

```bash
python3 -m tabgen build examples/superstore-mini/spec.json --open   # build and open in Desktop
python3 -m tabgen introspect path/to/existing.twb > start.json       # lift connections/columns/calcs
python3 -m unittest discover tests
```

Status: CSV and live Snowflake (browser SSO) sources, calcs, bar/line/circle charts and grid
dashboards are verified in Desktop. See `ROADMAP.md` for what's next.

## Repo layout

```
tabgen/compiler.py      spec -> .twb (data sources, worksheets, dashboards, windows)
tabgen/introspect.py    existing .twb -> spec "datasources" blocks
tabgen/__main__.py      CLI: build, introspect
tests/                  unit tests + golden tests against Desktop-saved references
references/<feature>/   Desktop-saved .twb + matching spec.json (the evidence; see docs/FORMAT.md)
examples/               runnable specs (Snowflake example uses placeholders)
scripts/refdiff.py      clean a Desktop-saved reference / diff it against generated output
scripts/check_leaks.py  blocks company data, home paths and fingerprints from commits
githooks/               local guards: no commits/pushes to main, leak check, tests
docs/FORMAT.md          verified facts about the TWB format, each with its evidence
private/                git-ignored: real company workbooks, specs, denylist
```

## Spec reference

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
      "calcs": { "Sales K": { "formula": "[SALES_AMT] / 1000", "type": "real", "role": "measure" } }
    }
  },
  "sheets": {
    "Sales by Region": { "datasource": "sales", "cols": "Region", "rows": "sum(Sales)",
                         "color": "Category", "mark": "bar" }
  },
  "dashboards": { "Overview": { "size": [1200, 800], "layout": [["Sales by Region"]] } }
}
```

**Data sources** (keyed by a short name; the first one is the default for sheets):
- `csv`: path relative to the spec. Column types (string/integer/real/date) are inferred.
- `snowflake`: live connection. Required: `server`, `warehouse`, `database`, `schema`, `table`.
  `auth`: `oauth` (aliases `sso`, `browser`; verified, prompts browser sign-in). `password` is
  emitted but **unverified**. Needs a `columns` map: `name -> type` or `{type, caption, role}`;
  types `string integer real date datetime boolean`. ALL_CAPS names get Desktop-style captions
  (`SALES_AMT` → "Sales Amt"). Easiest: `tabgen introspect` an existing workbook on the same table.
- `calcs`: `caption -> formula` (a real measure) or `{formula, type, role}`. Formulas use Tableau
  syntax with raw column names (`[SALES_AMT]`).

**Sheets:**
- `datasource` (optional), `rows`, `cols` (a field or a list), `mark`, and encodings `color`,
  `size`, `label`, `detail`, `tooltip`.
- Fields can be referenced by raw name or caption (`SALES_AMT` or `Sales Amt`), optionally wrapped:
  `sum avg min max count countd` (aggregations), `yr qr mn` (date parts), `none` (as a dimension),
  `agg` (an aggregate calc).
- Defaults:
  - measures → `sum`
  - aggregate calcs (`SUM(..)/SUM(..)`) → used as-is
  - dimensions → `none`
  - dates → `yr`
- Marks: `bar line circle square text pie automatic area`.
- Evidence status:
  - Opened correctly in Desktop: `sum`, `avg`, `none`, aggregate calcs; `bar`, `line`, `circle`;
    `color`.
  - Seen in Desktop-saved files: `label` (text) and `tooltip`, plus marks `square`, `text`, `pie`,
    `automatic`.
  - Unverified (no evidence yet): everything else, e.g. `min`/`max`/`count`/`countd`, `yr`/`qr`/`mn`,
    `area`, `size`, `detail`. See `docs/FORMAT.md`.

**Dashboards:**
- `size` is `[width, height]` in px.
- `layout` is a list of rows, each a list of sheet names. Rows split the height equally, and sheets
  split each row's width equally.

Spec mistakes (unknown field, sheet, mark or aggregation; missing Snowflake settings) stop the build
with a clear message instead of producing a broken workbook.

## Known limitations (see ROADMAP.md)

- No filters, legends, parameters, titles/text boxes, sorting or number formatting yet.
- Layout is equal-split only; long axis labels can be clipped.
- Live connections only (no extracts / `.twbx`).

## Target format

Tableau Desktop 2026.2.1 writes `version='18.1'` with a feature-flag manifest, and that is what we
emit. The `26.2` + `<ManifestByVersion/>` format from
[tableau-document-schemas](https://github.com/tableau/tableau-document-schemas) triggers stricter
internal validation in Desktop, and Desktop-saved files don't pass the published XSD, so the XSD is
advisory only. **Ground truth is files saved by Desktop**; verified facts are in `docs/FORMAT.md`.

## Golden-file workflow (how we learn new features)

1. Build the smallest example of the feature in Tableau Desktop; *Save As* `.twb` into
   `references/<feature>/desktop-saved.twb` (or `private/references/<feature>/` if it uses company data).
2. `python3 scripts/refdiff.py clean <file>` (strips fingerprints/thumbnails), then replace any server,
   username, database, schema and table names before committing.
3. Write `references/<feature>/spec.json` for the same workbook, build it, and
   `python3 scripts/refdiff.py diff <reference.twb> <generated.twb>`.
4. Teach the compiler until the diff is only cosmetic. Add the case to `CASES` in
   `tests/test_golden.py`, record the new facts in `docs/FORMAT.md`, and open the generated file in Desktop.

## Private material

Real company workbooks and specs with live connection details live in `private/` (git-ignored),
along with `private/denylist.txt` (company terms the leak check blocks). Committed examples use
placeholders (`your_account.snowflakecomputing.com`, `YOUR_WAREHOUSE`, ...).

## Development process

See `CLAUDE.md` (rules and current status) and `ROADMAP.md` (scope). In short:
1. Branch, then open a PR.
2. An independent `pr-reviewer` gives a verdict.
3. A human verifies the result in Desktop and merges.

Run `git config core.hooksPath githooks` once per clone to enable the local guards: no commits or
pushes to `main`, plus the leak check and tests before every commit.
