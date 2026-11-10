# tableau-codegen

Write dashboards as code and get a `.twb` that opens in Tableau Desktop as a working workbook.

```bash
python3 -m tabgen build examples/superstore-mini/spec.json --open
python3 -m unittest discover tests
```

## Spec (current JSON form)

```json
{
  "datasources": { "sales": { "csv": "sales.csv", "calcs": { "Profit Ratio": "SUM([Profit]) / SUM([Sales])" } } },
  "sheets": {
    "Sales by Region": { "cols": "Region", "rows": "sum(Sales)", "color": "Category", "mark": "bar" }
  },
  "dashboards": { "Overview": { "size": [1200, 800], "layout": [["Sales by Region"]] } }
}
```

- Field refs: `Region` (dimension), `sum(Sales)`, `avg(...)`, `countd(...)`, `yr(Order Date)`; aggregate calcs need no wrapper.
- Encodings: `color`, `size`, `label`, `detail`, `tooltip`.
- Marks: `bar`, `line`, `area`, `circle`, `square`, `text`, `pie`, `automatic`.
- Dashboard `layout` is a list of rows, each a list of sheet names.

## Target format

Tableau Desktop 2026.2.1 writes `version='18.1'` with a feature-flag manifest, and that is what we emit.
The `26.2` + `<ManifestByVersion/>` format from
[tableau-document-schemas](https://github.com/tableau/tableau-document-schemas) triggers stricter
internal validation in Desktop (undocumented required elements), and Desktop-saved files don't pass the
published XSD, so the XSD is advisory only. **Ground truth is files saved by Desktop.**

## Golden-file workflow (how we learn new features)

1. Build the smallest example of the feature in Tableau Desktop; *Save As* `.twb` into `references/<feature>/desktop-saved.twb`.
2. `python3 scripts/refdiff.py clean references/<feature>/desktop-saved.twb` (strips fingerprints/thumbnails).
3. Write `references/<feature>/spec.json` describing the same workbook, build it, and
   `python3 scripts/refdiff.py diff references/<feature>/desktop-saved.twb <generated.twb>`.
4. Teach the compiler until the diff is only cosmetic; open the generated file in Desktop to confirm.

## Private material

Real company workbooks and specs with live connection details live in `private/` (git-ignored).
Committed examples use placeholders (`your_account.snowflakecomputing.com`, `YOUR_WAREHOUSE`, ...).
Before committing a new reference saved from Desktop, run `scripts/refdiff.py clean` and replace
server, username, database, schema and table names.

## Development process

See `CLAUDE.md` (rules), `ROADMAP.md` (scope). In short: branch → PR → independent `pr-reviewer`
verdict → human verifies in Desktop and squash-merges. Run `git config core.hooksPath githooks` once
per clone to enable the local guards (no commits/pushes to `main`, leak check, tests).
