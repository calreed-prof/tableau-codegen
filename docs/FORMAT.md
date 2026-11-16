# TWB format notes (what we know, and how we know it)

This is the evidence log for the XML the compiler emits. Every fact here cites evidence you can check:
a Desktop-saved reference file, or a generated workbook the human opened in Desktop. Anything marked
**Unverified** is emitted today without evidence. So is anything the compiler emits that isn't
listed here, which mostly means structure copied from the references below. Unverified XML needs a
reference before a feature builds on it, and `tabgen` must not grow new unverified XML (see
`CLAUDE.md` → Evidence rule).

Evidence keys:
- **REF-CSV**: `references/csv-basic/desktop-saved.twb` (Desktop 2026.2.1, textscan CSV, bar chart, dashboard).
  The committed copy was cleaned with `refdiff.py clean`: no fingerprint attributes, no thumbnails.
- **REF-SF**: Desktop 2026.2.1 workbook with two live Snowflake tables (with extracts), parameters,
  filters and LOD calcs. Company data, so it lives at `private/references/snowflake-basic/Book1.twb`
  and is not committed. Saved before the `desktop-saved.twb` naming convention existed.
- **REF-FILTERS**: Desktop 2026.2.1 save of our generated private Snowflake example after adding,
  by hand, a boolean LOD calc (`{ FIXED : MAX([RUN_TIMESTAMP]) } = [RUN_TIMESTAMP]`), a worksheet
  filter keeping it to True, its dashboard filter control and a color legend (2026-11-10). Company
  data, so it lives at `private/references/filters-legends/desktop-saved.twb` (next to the `spec.twb`
  it started from, and a `spec.json` that rebuilds it). Diffing against our own output isolates what
  filters and legends add. **Re-saved by accident on 2026-11-16** with REF-FILTERS-CAT's Level filter
  added (and the boolean control re-laid out to 70px), so the file no longer matches the original.
  The facts below that cite REF-FILTERS were recorded from the original save.
- **REF-FILTERS-CAT**: REF-FILTERS's workbook after adding, by hand, a filter keeping the string
  dimension `LEVEL` on `Season Forecast by Level` to two values, and its dashboard control
  (2026-11-16). The dashboard now has controls from two data sources. Company data:
  `private/references/filters-categorical/desktop-saved.twb`, with a `spec.json` that rebuilds it.
- **OPEN-CSV** / **OPEN-SF**: `examples/superstore-mini` and the private Snowflake example were
  generated and opened in Desktop 2026.2.1 by the human, rendering correctly (2026-11-10). Not
  machine-checkable: it's a recorded human observation.
- **OPEN-M2**: generated with PR #5 and opened in Desktop 2026.2.1 by the human, rendering correctly
  (2026-11-16): `examples/superstore-mini` (one legend, no filter control), `generated-m2.twb`
  next to REF-FILTERS (its `spec.json` built with a one-sheet `legends` override; filter + legend), and the private
  Snowflake example (two legends, one on a calculated string field, no filter control).
- **OPEN-M1P2**: `private/references/filters-categorical/generated.twb` (PR #7) opened in Desktop
  2026.2.1 by the human (2026-11-16): renders correctly; side column shows Recent Run, Level (2 values
  ticked) and the Metric legend in that order; ticking another Level value updates the chart.
- **OBS**: other recorded observations from the 2026-11-10 session (no file to grep).

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
The compiler's output for both filters matches the references exactly (checked by rebuilding each
reference's `spec.json`; the expected XML is written out in `tests/test_compiler.py`).

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
| `<dashboard enable-sort-zone-taborder="true">`, `<size>`, `<zones>`; zone coordinates in 1/100000 of the dashboard; outer padding x=800 y=1000 w=98400 h=98000 | REF-CSV |
| Root `layout-basic` zone, sheet zones with `zone-style` margin 4 (sheets) / 8 (root) | REF-CSV |
| Nested `layout-flow` zones: `param="vert"` | REF-CSV (phone layout), REF-SF |
| `param="horz"` | REF-SF |
| Our grid nests horz rows inside a vert container | OPEN-CSV, OPEN-SF |
| Filter controls: Desktop wraps the grid in a `horz` `layout-flow` zone, next to a fixed side column `<zone fixed-size='160' is-fixed='true' param='vert' type-v2='layout-flow' w=160px>` | REF-FILTERS |
| Filter control zone: `<zone name=<sheet> param=<filter field ref> type-v2='filter' values='database'>`, margin 4, h = 89px for a boolean (70px in the 2026-11-16 re-save; we keep 89) | REF-FILTERS |
| Multi-value string control: same zone, h = 203px on a 900px dashboard, for a field keeping 2 values (one sample; Desktop may size others differently) | REF-FILTERS-CAT |
| Controls from two data sources: one `<datasources>` with both, then one `<datasource-dependencies>` per source, in the reference's order, which is both the order the controls were added and the sorted source-name order (we use spec order, which opens fine per OPEN-M1P2; unverified which rule Desktop's own saves follow) | REF-FILTERS-CAT |
| Desktop appends a new control at the bottom of the side column, after any legend; we stack all controls first, then legends, and Desktop accepts that order | REF-FILTERS-CAT, OPEN-M1P2 |
| A dashboard with a filter control gets `<datasources>` and a `<datasource-dependencies>` (filter field's column + column-instance only, not calc inputs) between `<size>` and `<zones>` | REF-FILTERS |
| Color legend: `<zone name=<sheet> pane-specification-id='0' param=<sheet's color field ref> type-v2='color'>`, margin 4, h = 66px, in the same side column below the filter controls | REF-FILTERS |
| A side column holding legends only (no filter control); a legend on a calculated dimension | OPEN-M2 |
| A legend adds nothing to the dashboard's `<datasources>` / `<datasource-dependencies>` (REF-FILTERS lists only the filter's field there, not `METRIC`) | REF-FILTERS |
| Worksheet windows need `<cards>` (left: pages/filters/marks; top: columns/rows/title); dashboard windows need `<viewpoints>`, `<active>` | REF-CSV, OPEN-CSV |

| Unverified / not emitted (legends) | Notes |
|---|---|
| Size legends; color legends for a measure (continuous) or a date part (ordinal) | No reference: auto mode skips them, an explicit `legends` entry is a spec error |
| Legend height for many members | Desktop gave 66px for `METRIC`; we always use 66px and let the zone scroll |
