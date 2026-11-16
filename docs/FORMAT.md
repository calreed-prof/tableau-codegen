# TWB format notes (what we know, and how we know it)

The evidence log for the XML the compiler emits: each fact cites a Desktop-saved reference or a
recorded Desktop open. Rules for adding facts are in `CLAUDE.md` → Evidence rule.

- **Unverified** rows are emitted today without evidence; find them with `grep -n Unverified`.
  Anything emitted but not listed here is also unverified, mostly structure copied from the references.
- **How it's checked:** `tests/test_references.py` rebuilds every reference's `spec.json` and compares
  the claimed XML (`scripts/refdiff.py` → `claims()`), with accepted differences and reasons in each
  reference's `known-diffs.json`. That is the authoritative check. Unit tests in
  `tests/test_compiler.py` also spell out a few expected values, so CI covers private references too.

**Terms:** *federated* = Tableau's wrapper data source around one or more connections;
*textscan* = the CSV connector; *LOD* = a `{ FIXED ... }` level-of-detail calc; *zone* = a box in
a dashboard layout (`layout-flow` = a row/column container, `layout-basic` = the root);
*remote-type* = the database type code in a column's metadata record; `usr:` = the shelf prefix
for an aggregate calc. Tableau's published schemas:
[tableau-document-schemas](https://github.com/tableau/tableau-document-schemas) (advisory only,
see below).

## Evidence keys

`REF-x` = a workbook saved by Tableau Desktop; `OPEN-x` = the human opened our generated output in
Desktop and it rendered correctly (a recorded observation, not machine-checkable); `OBS` = other
recorded observations. **Private** files are in git-ignored `private/` (company data), so only the
maintainer can open them; their facts are summarised here and in PRs.

| Key | What | Where |
|---|---|---|
| **REF-CSV** | Desktop 2026.2.1: textscan CSV, bar chart, dashboard. Cleaned with `refdiff.py clean` (no fingerprints or thumbnails) | committed: `references/csv-basic/` |
| **REF-SF** | Desktop 2026.2.1: two live Snowflake tables (with extracts), parameters, filters, LOD calcs. Predates the `desktop-saved.twb` naming | private: `private/references/snowflake-basic/Book1.twb` |
| **REF-FILTERS** | Desktop 2026.2.1 save of our generated Snowflake example (`spec.twb` next to it) plus, added by hand: a boolean LOD calc (`{ FIXED : MAX([RUN_TIMESTAMP]) } = [RUN_TIMESTAMP]`), a filter keeping it to True, its dashboard control, a color legend (2026-11-10). **The original file is lost:** it was saved over on 2026-11-16 (a Level filter was added, and the boolean control was re-laid out to 70px). Facts citing REF-FILTERS were recorded from the original | private: `private/references/filters-legends/` (current file + a `spec.json` describing it) |
| **REF-FILTERS-CAT** | Desktop 2026.2.1: REF-FILTERS plus a filter keeping the string dimension `LEVEL` to two values and its dashboard control, so the dashboard has controls from two data sources (2026-11-16) | private: `private/references/filters-categorical/` |
| **REF-LAYOUT** | Desktop 2026.2.1: `examples/superstore-mini` built by us, then by hand: top row fixed to 456px, its first sheet to 609px wide, Show Title, a text box above the charts (2026-11-16). Cleaned; directory replaced | committed: `references/layout-basic/` |
| **OPEN-CSV**, **OPEN-SF** | `examples/superstore-mini` and the private Snowflake example opened correctly in Desktop 2026.2.1 (2026-11-10) | observation |
| **OPEN-M2** | PR #5 output opened correctly (2026-11-16): superstore-mini (a legend, no filter control); `generated-m2.twb` next to REF-FILTERS, a rebuild with one legend (filter + legend); the private Snowflake example (two legends, one on a calculated field) | observation |
| **OPEN-M1P2** | PR #7 output (`private/references/filters-categorical/generated.twb`) opened correctly (2026-11-16): side column shows Recent Run, Level (2 values) and the Metric legend, in that order; changing Level updates the chart | observation |
| **OBS** | Other observations from the 2026-11-10 session | observation |

## Workbook envelope

| Fact | Evidence |
|---|---|
| Desktop 2026.2.1 saves `version='18.1'` / `original-version='18.1'` with a list of feature flags in `<document-format-change-manifest>`, **not** `26.2` + `<ManifestByVersion/>` | REF-CSV, REF-SF |
| Emitting `26.2` + `ManifestByVersion` triggers Desktop's internal schema errors (requires `<worksheet-number>`, a `type` on `<mark>`, ...) that the published XSD doesn't declare | OBS (Desktop load error D2E8DA72) |
| Desktop-saved files fail the published XSD because of `_.fcp.*` fingerprint attributes, so the XSD is advisory only | REF-SF (the committed REF-CSV has been cleaned of them) |
| The published XSDs don't compile in `xmllint` as shipped (missing `schemaLocation` for the `xml` and `user` namespaces) | OBS (reproducible with any of the published XSDs) |
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
| `min`, `max`, `yr`, `qr`, `mn` (→ prefixes `min` `max` `yr` `qr` `mn`; derivations `Min` `Max` `Year` `Quarter` `Month`) | **Unverified** |
| `count`, `countd` (→ prefixes `count` `countd`; derivations `Count` `CountD`) | **Unverified**, and the prefixes are probably wrong: Desktop may use other short prefixes. Get a reference before relying on them |

Each used field also appears in the worksheet's `<datasource-dependencies>` as a `<column>` plus a
`<column-instance column= derivation= name= pivot="key" type=>` (REF-CSV).

| Marks / encodings | Evidence |
|---|---|
| `<mark class=>`: `Bar`, `Line`, `Circle` | OPEN-CSV, OPEN-SF |
| `Automatic` | REF-SF |
| `Square`, `Text`, `Pie`, `Area` | **Unverified** |
| `<encodings>`: `<color column=>` | OPEN-CSV, OPEN-SF |
| `<text>`, `<tooltip>` | REF-SF |
| `<size>`, `<lod>` | **Unverified** |

## Calculated fields

| Fact | Evidence |
|---|---|
| `<column caption= datatype= name="[Calculation_<digits>]" role= type=><calculation class="tableau" formula=/></column>` | REF-SF, OPEN-CSV |
| Row-level measures (e.g. `[X] / 100`) go on shelves with a normal aggregation (`avg:Calculation_...`); aggregate calcs (`SUM(..)/SUM(..)`) use `usr:` | OPEN-SF, OPEN-CSV |
| A sheet's `<datasource-dependencies>` also lists the columns a used calc names (e.g. `[METRIC]` for `IF [METRIC] = ...`), as `<column>` only, with no `<column-instance>`; all columns sorted by name | REF-FILTERS (two sheets) |
| Boolean calc: `datatype="boolean" role="dimension" type="nominal"`, on shelves/filters as `[none:Calculation_...:nk]` | REF-FILTERS |
| Calcs that reference `[Parameters].[...]` need the Parameters datasource (not supported yet; `introspect` drops them) | REF-SF |

## Filters

Worksheet filter keeping a boolean field to True (REF-FILTERS), inside the sheet's `<view>` after
`<datasource-dependencies>` and before `<aggregation>`:

```xml
<filter class='categorical' column='[federated.X].[none:Calculation_N:nk]'>
  <groupfilter function='member' level='[none:Calculation_N:nk]' member='true'
               user:ui-domain='database' user:ui-enumeration='inclusive' user:ui-marker='enumerate' />
</filter>
<slices>
  <column>[federated.X].[none:Calculation_N:nk]</column>
</slices>
```

Worksheet filter keeping a string dimension to several values (REF-FILTERS-CAT). The ui attributes
move to an outer `union`; string members are written in double quotes (`&quot;` in the attribute):

```xml
<filter class='categorical' column='[federated.X].[none:LEVEL:nk]'>
  <groupfilter function='union' user:ui-domain='database' user:ui-enumeration='inclusive' user:ui-marker='enumerate'>
    <groupfilter function='member' level='[none:LEVEL:nk]' member='&quot;Company&quot;' />
    <groupfilter function='member' level='[none:LEVEL:nk]' member='&quot;Division&quot;' />
  </groupfilter>
</filter>
```

The filtered field also gets a `<column>` + `<column-instance>` in the sheet's dependencies.
The compiler's output for both filters matches the references exactly (`tests/test_references.py`).

| Unverified / not emitted | Notes |
|---|---|
| A single string value (probably one `member` groupfilter like the boolean case), `member='false'`, exclude lists, numeric/date members, empty values or values containing `"` or `\`, ranges, top-N, context filters | No reference yet: the spec rejects them. REF-SF has examples of some, but they're on parameter-driven fields |
| Calc inputs that are themselves calcs: we list direct references only, not their inputs | REF-FILTERS's calcs only name database columns |
| Desktop also wrote `<viewpoint><highlight><color-one-way><field>` (the filter field) in the sheet's window | Optional per OPEN-CSV/OPEN-SF; omitted |

## Data sources

Every source is `<datasource name="federated.<id>" inline="true" version="18.1">` with a
`<connection class="federated">`, a `<named-connection>`, a `<relation>`, `<metadata-records>`,
an `[__tableau_internal_object_id__].[<object id>]` column, and an `<object-graph>` holding the same
relation (REF-CSV, REF-SF).

**CSV (textscan)**, all from REF-CSV:
- connection: `<connection class="textscan" directory= filename= password="" server=""/>`
- relation `table="[file#csv]"`, with `<columns>`
- one `capability` metadata record
- column remote-types: 129 string, 133 date, 5 real
- string columns: `width 1073741823`, collation `LEN_RUS`
- object id: `<file>_<32 hex>`
- CSV integer columns aren't in REF-CSV. The compiler writes remote-type 20 for them, which is
  **unverified**.

**Snowflake (live):**
- named-connection `snowflake.<id>`, with the server as its caption (REF-SF)
- connection attributes (REF-SF, OPEN-SF; the browser SSO prompt appears on open):
  `authentication="oauth" class="snowflake" dbname instanceurl="https://<server>" max-varchar-size=""
  oauth-config-id="default" odbc-connect-string-extras="" one-time-sql="" role schema server
  server-oauth="" service="" temp-table-detection="optimized" username warehouse`
- relation `table="[DB].[SCHEMA].[TABLE]"`, with no `<columns>`; no capability record (REF-SF)
- string columns: `width 8000`, collation `binary` (REF-SF)
- object id: `<TABLE> (<DB>.<TABLE>)_<32 hex>` (REF-SF)
- Desktop auto-captions ALL_CAPS columns, e.g. `SEASON_FORECAST` → "Season Forecast" (REF-SF)

Live metadata remote-types in REF-SF:

| local-type | remote-type | extra |
|---|---|---|
| string | 129 | |
| real | 5 | `<precision>15</precision>` |
| integer | **131** | `<precision>38</precision><scale>0</scale>` |
| date | **7** | |
| datetime | 7 | |
| boolean | 11 | |

(REF-SF's *extract* metadata uses different codes. Don't confuse the two.)

The compiler emits exactly these, with precision/scale placed after `<aggregation>` as in REF-SF
(`tests/test_compiler.py` → `test_metadata_records_match_desktop_reference`). Before
`fix/snowflake-remote-types` it wrote integer 20 / date 133 with no precision, and Desktop still
opened it (OPEN-SF).

| Unverified / known mismatch | Notes |
|---|---|
| `auth` other than `oauth`/`sso`/`browser` | `password` → `authentication="Username Password"` is a guess. Any other value is written into `authentication=` verbatim, with no error. Every non-oauth value omits `oauth-config-id` |
| Extracts (`<extract>` + `.hyper`) | Seen in REF-SF but not emitted |

## Dashboards and windows

| Fact | Evidence |
|---|---|
| `<dashboard enable-sort-zone-taborder="true">`, `<size>`, `<zones>`; zone coordinates in 1/100000 of the dashboard | REF-CSV |
| Outer padding is 8px per side: x = round(8/W·100000), y = round(8/H·100000), w = 100000 − 2x, h = 100000 − 2y (1000 wide: 800; 1200x800: 667/1000; 1400x900: 571/889) | REF-CSV, REF-LAYOUT, REF-FILTERS |
| Title and text box: Desktop wraps the content in a `vert` `layout-flow` zone holding `<zone type-v2='title'>` (42px, no text stored: it shows the dashboard name), then `<zone type-v2='text'>` (25px for one line) with `<formatted-text><run>…</run></formatted-text>`, then the previous content. Both get margin 4 | REF-LAYOUT |
| Fixed row: its `horz` container gets `fixed-size=<height px> is-fixed='true'`. Fixed sheet: `fixed-size=<width px − 8> is-fixed='true'` (fixed-size excludes the two 4px margins). Flexible siblings share the rest | REF-LAYOUT |
| Desktop puts a dashboard's lone sheet straight in the root zone; our vert/horz grid containers open fine | REF-CSV, OPEN-CSV |
| Color legend height grows with members: 66px for 2 (REF-FILTERS), 86px for 3 (REF-LAYOUT), i.e. 26 + 20·n from two samples. We always emit 66px | REF-FILTERS, REF-LAYOUT |
| Root `layout-basic` zone, sheet zones with `zone-style` margin 4 (sheets) / 8 (root) | REF-CSV |
| Nested `layout-flow` zones: `param="vert"` | REF-CSV (phone layout), REF-SF |
| `param="horz"` | REF-SF |
| Our grid nests horz rows inside a vert container | OPEN-CSV, OPEN-SF |
| Filter controls: Desktop wraps the grid in a `horz` `layout-flow` zone, next to a fixed side column `<zone fixed-size='160' is-fixed='true' param='vert' type-v2='layout-flow' w=160px>` | REF-FILTERS |
| Filter control zone: `<zone name=<sheet> param=<filter field ref> type-v2='filter' values='database'>`, margin 4, h = 89px for a boolean. Desktop's 2026-11-16 re-saves show 70px; we keep 89, which opens fine (accepted in `known-diffs.json`) | REF-FILTERS, OPEN-M1P2 |
| Multi-value string control: same zone, h = 203px on a 900px dashboard, for a field keeping 2 values (one sample; Desktop may size others differently) | REF-FILTERS-CAT |
| Controls from two data sources: one `<datasources>` with both, then one `<datasource-dependencies>` per source, in the reference's order, which is both the order the controls were added and the sorted source-name order (we use spec order, which opens fine per OPEN-M1P2; unverified which rule Desktop's own saves follow) | REF-FILTERS-CAT |
| Desktop appends a new control at the bottom of the side column, after any legend; we stack all controls first, then legends, and Desktop accepts that order | REF-FILTERS-CAT, OPEN-M1P2 |
| A dashboard with a filter control gets `<datasources>` and a `<datasource-dependencies>` (filter field's column + column-instance only, not calc inputs) between `<size>` and `<zones>` | REF-FILTERS |
| Color legend: `<zone name=<sheet> pane-specification-id='0' param=<sheet's color field ref> type-v2='color'>`, margin 4, h = 66px, in the same side column below the filter controls | REF-FILTERS |
| A side column holding legends only (no filter control); a legend on a calculated dimension | OPEN-M2 |
| A legend adds nothing to the dashboard's `<datasources>` / `<datasource-dependencies>` (REF-FILTERS lists only the filter's field there, not `METRIC`) | REF-FILTERS |
| Worksheet windows need `<cards>` (left: pages/filters/marks; top: columns/rows/title); dashboard windows need `<viewpoints>`, `<active>` | REF-CSV, OPEN-CSV |

| Unverified / not emitted (layout) | Notes |
|---|---|
| Title or text box on a dashboard without a side column (we nest our grid's `vert` inside the title's `vert`) | REF-LAYOUT has a side column; needs an open (M3 PR) |
| Custom title text, multi-line or formatted text, text elsewhere than above the charts, floating zones, all-fixed rows/columns | No reference: the spec has no way to ask for them |
| Desktop's own split of flexible space (unequal, content-based); we split equally | Accepted in the private references' `known-diffs.json` |

| Unverified / not emitted (legends) | Notes |
|---|---|
| Size legends; color legends for a measure (continuous) or a date part (ordinal) | No reference: auto mode skips them, an explicit `legends` entry is a spec error |
| Legend height for many members | Desktop gave 66px for `METRIC`; we always use 66px and let the zone scroll |
