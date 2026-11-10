# TWB format notes (what we know, and how we know it)

The compiler emits only what is listed here as **verified**. Each fact cites its evidence:
a Desktop-saved reference, a workbook that opened correctly in Desktop, or both. "Unverified" items
are emitted today but have no reference yet; they need one before anything is built on them.

Evidence keys:
- **REF-CSV**: `references/csv-basic/desktop-saved.twb` (Desktop 2026.2.1, textscan CSV, bar chart, dashboard)
- **REF-SF**: a Desktop 2026.2.1 workbook with two live Snowflake tables, parameters, filters,
  LOD calcs and extracts. Company data, so kept in `private/references/snowflake-basic/` (not committed)
- **OPEN-CSV** / **OPEN-SF**: `examples/superstore-mini` / the private Snowflake example were generated
  and opened in Desktop 2026.2.1 with correct rendering (2026-11-10)
- **SAMPLES**: older Desktop-saved workbooks seen on the dev machine (format 18.1)

## Workbook envelope

| Fact | Evidence |
|---|---|
| Desktop 2026.2.1 saves `version='18.1'` / `original-version='18.1'` with a list of feature flags in `<document-format-change-manifest>`, **not** `26.2` + `<ManifestByVersion/>` | REF-CSV, REF-SF |
| Emitting `26.2` + `ManifestByVersion` triggers Desktop's internal schema errors (requires `<worksheet-number>`, a `type` on `<mark>`, ...) that the published XSD doesn't declare | Load error in Desktop (Error Code D2E8DA72), 2026-11-10 |
| Desktop-saved files fail the published XSD (`_.fcp.*` fingerprint attributes), so the XSD is advisory only | REF-CSV |
| The published XSDs don't compile in `xmllint` as shipped (missing `schemaLocation` for the `xml` and `user` namespaces) | Tried 2026-11-10 |
| Our manifest = REF-CSV's flags minus the workbook-fingerprinting flag | REF-CSV, OPEN-CSV |
| `<thumbnails>`, `<devicelayouts>`, window `<viewpoint><highlight>` are optional (we omit them) | OPEN-CSV, OPEN-SF |

## Field references (shelves and encodings)

`[<datasource name>].[<derivation>:<column>:<typekey>]`, e.g. `[federated.x].[sum:Sales:qk]`.
typekey: `nk` nominal, `ok` ordinal, `qk` quantitative. Multiple fields on a shelf: ` / `.

| Derivation (spec → XML) | Evidence |
|---|---|
| `none` → `None` (dimension), e.g. `[none:Region:nk]`, numeric dim `[none:SALES_YEAR_WEEK:qk]` | REF-CSV, REF-SF |
| `sum` → `Sum` | REF-CSV, REF-SF |
| `avg` → `Avg` | OPEN-SF |
| aggregate calc → `User` / prefix `usr` | OPEN-CSV (Profit Ratio) |
| `min`, `max`, `count`, `countd`, `yr`, `qr`, `mn` (→ `Min`, `Max`, `Count`, `CountD`, `Year`, `Quarter`, `Month`) | **Unverified** |

Each used field also appears in the worksheet's `<datasource-dependencies>` as a `<column>` plus a
`<column-instance column= derivation= name= pivot="key" type=>` (REF-CSV).

| Marks / encodings | Evidence |
|---|---|
| `<mark class=>`: `Bar`, `Line`, `Circle` | OPEN-CSV, OPEN-SF |
| `Automatic`, `Pie`, `Square`, `Text` | SAMPLES |
| `Area` | **Unverified** |
| `<encodings>`: `<color column=>` | OPEN-CSV, OPEN-SF |
| `<text>`, `<tooltip>` | REF-SF |
| `<size>`, `<lod>` | **Unverified** |

## Calculated fields

| Fact | Evidence |
|---|---|
| `<column caption= datatype= name="[Calculation_<digits>]" role= type=><calculation class="tableau" formula=/></column>` | REF-SF, OPEN-CSV |
| Row-level measures (e.g. `[X] / 100`) go on shelves with a normal aggregation (`avg:Calculation_...`); aggregate calcs (`SUM(..)/SUM(..)`) use `usr:` | OPEN-SF, OPEN-CSV |
| Calcs that reference `[Parameters].[...]` need the Parameters datasource (not supported yet) | REF-SF |

## Data sources

Every source is `<datasource name="federated.<id>" inline="true" version="18.1">` with a
`<connection class="federated">`, a `<named-connection>`, a `<relation>`, `<metadata-records>`,
an `[__tableau_internal_object_id__].[<object id>]` column, and an `<object-graph>` holding the same
relation (REF-CSV, REF-SF).

**CSV (textscan):** `<connection class="textscan" directory= filename= password="" server=""/>`;
relation `table="[file#csv]"` with `<columns>`; a `capability` metadata record; string columns use
`remote-type 129`, `width 1073741823`, collation `LEN_RUS`; object id `<file>_<32 hex>` (REF-CSV).

**Snowflake (live):** named-connection `snowflake.<id>`, caption = server. Connection attributes:
`authentication="oauth" class="snowflake" dbname instanceurl="https://<server>" max-varchar-size=""
oauth-config-id="default" odbc-connect-string-extras="" one-time-sql="" role schema server
server-oauth="" service="" temp-table-detection="optimized" username warehouse` (REF-SF, OPEN-SF;
browser SSO prompts on open). Relation `table="[DB].[SCHEMA].[TABLE]"` with no `<columns>`; no
capability record; string columns `width 8000`, collation `binary`. remote-type codes: 129 varchar,
5 real, 20 integer, 7 timestamp, 133 date, 11 boolean (REF-SF). Object id
`<TABLE> (<DB>.<TABLE>)_<32 hex>` (REF-SF). Desktop auto-captions ALL_CAPS columns
(`SEASON_FORECAST` → "Season Forecast") (REF-SF).

| Unverified | Notes |
|---|---|
| Snowflake `auth: "password"` → `authentication="Username Password"` | Guessed value; needs a reference before use |
| Extracts (`<extract>` + `.hyper`) | Seen in REF-SF but not emitted |

## Dashboards and windows

| Fact | Evidence |
|---|---|
| `<dashboard enable-sort-zone-taborder="true">`, `<size>`, `<zones>`; zone coordinates in 1/100000 of the dashboard; outer padding x=800 y=1000 w=98400 h=98000 | REF-CSV |
| Root `layout-basic` zone, sheet zones with `zone-style` margin 4 (sheets) / 8 (root) | REF-CSV |
| Nested `layout-flow` zones with `param="vert"` / `"horz"` for grids | Seen in REF-CSV's phone layout; OPEN-CSV, OPEN-SF |
| Worksheet windows need `<cards>` (left: pages/filters/marks; top: columns/rows/title); dashboard windows need `<viewpoints>`, `<active>` | REF-CSV, OPEN-CSV |
