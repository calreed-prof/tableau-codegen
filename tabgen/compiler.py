"""Compile a declarative spec into a Tableau .twb.

Emits the format Tableau Desktop 2026.2.1 itself writes (version 18.1 + feature manifest),
modelled on reference workbooks saved from Desktop (see references/).
"""
import csv
import datetime
import hashlib
import os
import re
import uuid
import xml.etree.ElementTree as ET

TWB_VERSION = "18.1"
SOURCE_BUILD = "2026.2.1 (20262.26.0708.1337)"
# Feature manifest as Desktop 2026.2.1 writes it (minus the fingerprinting flag).
MANIFEST = ["AccessibleZoneTabOrder", "AnimationOnByDefault", "AutoCreateAndUpdateDSDPhoneLayouts",
            "MarkAnimation", "ObjectModelEncapsulateLegacy", "ObjectModelTableType",
            "SchemaViewerObjectModel", "SetMembershipControl", "SheetIdentifierTracking",
            "WindowsPersistSimpleIdentifiers"]

# Tableau shelf encoding: [ds].[derivation:Field:typekey]
AGG = {"sum": "Sum", "avg": "Avg", "min": "Min", "max": "Max", "count": "Count",
       "countd": "CountD", "none": "None", "usr": "User", "yr": "Year", "mn": "Month", "qr": "Quarter"}
DATE_DERIVS = ("yr", "qr", "mn")
TYPEKEY = {"nominal": "nk", "ordinal": "ok", "quantitative": "qk"}
MARKS = {"bar": "Bar", "line": "Line", "area": "Area", "circle": "Circle",
         "square": "Square", "text": "Text", "automatic": "Automatic", "pie": "Pie"}
DATATYPES = ("string", "integer", "real", "date", "datetime", "boolean")
DEFAULT_AGG = {"string": "Count", "boolean": "Count", "date": "Year", "datetime": "Year",
               "real": "Sum", "integer": "Sum"}


class SpecError(SystemExit):
    """Raised for user-facing spec mistakes (exits with the message when uncaught)."""


def sid(seed):
    """Deterministic id so regenerating a workbook gives a stable diff."""
    return hashlib.md5(seed.encode()).hexdigest()[:28]


def hex32(seed):
    return hashlib.md5(seed.encode()).hexdigest().upper()


def guid(seed):
    return "{" + str(uuid.uuid5(uuid.NAMESPACE_URL, seed)).upper() + "}"


def sub(parent, tag, text=None, **attrs):
    el = ET.SubElement(parent, tag, {k.replace("_", "-"): str(v) for k, v in attrs.items() if v is not None})
    if text is not None:
        el.text = text
    return el


def zone_style(zone, margin):
    zs = sub(zone, "zone-style")
    for attr, val in (("border-color", "#000000"), ("border-style", "none"),
                      ("border-width", "0"), ("margin", margin)):
        sub(zs, "format", attr=attr, value=val)


def make_column(name, datatype, ordinal=None, caption=None, role=None):
    if datatype not in DATATYPES:
        raise SpecError(f"Column {name!r}: unknown type {datatype!r} (use one of {', '.join(DATATYPES)})")
    measure = datatype in ("integer", "real")
    role = role or ("measure" if measure else "dimension")
    if role == "measure":
        typ = "quantitative"
    elif datatype in ("date", "datetime"):
        typ = "ordinal"
    elif measure:
        typ = "quantitative"  # numeric dimension, e.g. a year column
    else:
        typ = "nominal"
    return {"name": name, "ordinal": ordinal, "datatype": datatype, "role": role,
            "type": typ, "caption": caption}


AGG_FUNCS = re.compile(r"\b(SUM|AVG|MIN|MAX|COUNT|COUNTD|MEDIAN|ATTR|STDEV|STDEVP|VAR|VARP|"
                       r"PERCENTILE|WINDOW_\w+|RUNNING_\w+|INDEX|RANK\w*|LOOKUP|TOTAL)\s*\(", re.I)


def is_aggregate_calc(c):
    """Aggregate calcs (SUM([x])/SUM([y])) go on shelves as usr:; row-level ones get SUM by default.
    LOD expressions ({ FIXED ... }) are row-level from the view's point of view."""
    f = c.get("formula")
    if not f:
        return False
    return bool(AGG_FUNCS.search(re.sub(r"\{[^}]*\}", "", f)))


def friendly_caption(name):
    """Desktop's auto-caption for ALL_CAPS database columns: SEASON_FORECAST -> Season Forecast."""
    if name.upper() == name and re.search("[A-Z]", name):
        return " ".join(w.capitalize() for w in name.split("_") if w)
    return None


# ---------------------------------------------------------------- data sources
class DataSource:
    """Shared behaviour: columns, calcs, field resolution and shelf references."""

    def __init__(self, key):
        self.key = key
        self.columns = {}   # internal name -> column dict
        self.lookup = {}    # name or caption -> internal name

    def add_column(self, col):
        self.columns[col["name"]] = col
        self.lookup[col["name"]] = col["name"]
        if col.get("caption"):
            self.lookup[col["caption"]] = col["name"]

    def add_calc(self, caption, spec):
        if isinstance(spec, str):
            spec = {"formula": spec}
        internal = "Calculation_" + str(int(sid("calc" + self.key + caption), 16))[:16]
        col = make_column(internal, spec.get("type", "real"), caption=caption, role=spec.get("role"))
        col["formula"] = spec["formula"]
        self.add_column(col)

    def col(self, field):
        if field not in self.lookup:
            known = sorted(c.get("caption") or c["name"] for c in self.columns.values())
            raise SpecError(f"Unknown field {field!r} in data source {self.key!r}. Known: {', '.join(known)}")
        return self.columns[self.lookup[field]]

    def ref(self, field, agg=None):
        """Return (shelf string, column-instance attrs) for a use of a field."""
        c = self.col(field)
        if agg is None:
            if c["role"] == "measure":
                agg = "usr" if is_aggregate_calc(c) else "sum"
            else:
                agg = "yr" if c["datatype"] in ("date", "datetime") else "none"
        agg = "usr" if agg == "agg" else agg
        if agg not in AGG:
            raise SpecError(f"Unknown aggregation {agg!r} on {field!r} (use one of {', '.join(AGG)})")
        if agg == "none":
            typ = c["type"]
        elif agg in DATE_DERIVS:
            typ = "ordinal"
        else:
            typ = "quantitative"
        inst = f"[{agg}:{c['name']}:{TYPEKEY[typ]}]"
        return f"[{self.name}].{inst}", {"column": f"[{c['name']}]", "derivation": AGG[agg],
                                          "name": inst, "pivot": "key", "type": typ}

    def calc_inputs(self, c):
        """Columns a calc's formula names directly ([X] by internal name or caption). Desktop lists
        them in a sheet's datasource-dependencies (REF-FILTERS)."""
        found = []
        for token in re.findall(r"\[([^\[\]]+)\]", c.get("formula", "")):
            name = self.lookup.get(token)
            if name and name != c["name"] and self.columns[name] not in found:
                found.append(self.columns[name])
        return found

    def column_xml(self, parent, c):
        el = sub(parent, "column", caption=c.get("caption"), datatype=c["datatype"],
                 name=f"[{c['name']}]", role=c["role"], type=c["type"])
        if "formula" in c:
            sub(el, "calculation", **{"class": "tableau", "formula": c["formula"]})
        return el

    def physical(self):
        return [c for c in self.columns.values() if "formula" not in c]


class CsvSource(DataSource):
    REMOTE_TYPE = {"string": 129, "date": 133, "datetime": 135, "real": 5, "integer": 20, "boolean": 11}

    def __init__(self, key, spec, base_dir):
        super().__init__(key)
        self.path = os.path.abspath(os.path.join(base_dir, spec["csv"]))
        self.fname = os.path.basename(self.path)
        self.caption = spec.get("caption", os.path.splitext(self.fname)[0])
        self.name = "federated." + sid("ds" + key)
        self.conn = "textscan." + sid("conn" + key)
        self.object_id = self.fname + "_" + hex32("obj" + key)
        for c in self.infer_columns():
            self.add_column(c)

    def infer_columns(self):
        with open(self.path, newline="", encoding="utf-8") as fh:
            rows = list(csv.reader(fh))
        header, body = rows[0], rows[1:]
        out = []
        for i, name in enumerate(header):
            vals = [r[i] for r in body if i < len(r) and r[i] != ""]

            def all_(fn):
                try:
                    return bool(vals) and all(fn(v) is not None for v in vals)
                except (ValueError, IndexError):
                    return False
            if all_(int):
                dt = "integer"
            elif all_(float):
                dt = "real"
            elif all_(lambda v: datetime.date.fromisoformat(v[:10])):
                dt = "date"
            else:
                dt = "string"
            out.append(make_column(name, dt, ordinal=i))
        return out

    def _relation(self, parent):
        rel = sub(parent, "relation", connection=self.conn, name=self.fname,
                  table="[" + self.fname.replace(".", "#") + "]", type="table")
        rcols = sub(rel, "columns", character_set="UTF-8", header="yes", locale="en_US", separator=",")
        for c in self.physical():
            sub(rcols, "column", datatype=c["datatype"], name=c["name"], ordinal=c["ordinal"])

    def to_xml(self, parent):
        ds = sub(parent, "datasource", caption=self.caption, inline="true", name=self.name, version=TWB_VERSION)
        conn = sub(ds, "connection", **{"class": "federated"})
        nc = sub(sub(conn, "named-connections"), "named-connection", caption=self.caption, name=self.conn)
        sub(nc, "connection", **{"class": "textscan", "directory": os.path.dirname(self.path),
                                 "filename": self.fname, "password": "", "server": ""})
        self._relation(conn)

        mrs = sub(conn, "metadata-records")
        cap = sub(mrs, "metadata-record", **{"class": "capability"})
        sub(cap, "remote-name")
        sub(cap, "remote-type", "0")
        sub(cap, "parent-name", f"[{self.fname}]")
        sub(cap, "remote-alias")
        sub(cap, "aggregation", "Count")
        sub(cap, "contains-null", "true")
        attrs = sub(cap, "attributes")
        for k, v in (("character-set", "UTF-8"), ("collation", "en_US"), ("field-delimiter", ","),
                     ("header-row", "true"), ("locale", "en_US"), ("single-char", "")):
            sub(attrs, "attribute", f'"{v}"', datatype="string", name=k)
        for c in self.physical():
            mr = sub(mrs, "metadata-record", **{"class": "column"})
            sub(mr, "remote-name", c["name"])
            sub(mr, "remote-type", str(self.REMOTE_TYPE[c["datatype"]]))
            sub(mr, "local-name", f"[{c['name']}]")
            sub(mr, "parent-name", f"[{self.fname}]")
            sub(mr, "remote-alias", c["name"])
            sub(mr, "ordinal", str(c["ordinal"]))
            sub(mr, "local-type", c["datatype"])
            sub(mr, "aggregation", DEFAULT_AGG[c["datatype"]])
            if c["datatype"] == "string":
                sub(mr, "scale", "1")
                sub(mr, "width", "1073741823")
            sub(mr, "contains-null", "true")
            if c["datatype"] == "string":
                sub(mr, "collation", flag="0", name="LEN_RUS")
            sub(mr, "object-id", f"[{self.object_id}]")

        sub(ds, "aliases", enabled="yes")
        for c in self.columns.values():
            if "formula" in c:
                self.column_xml(ds, c)
        sub(ds, "column", caption=self.fname, datatype="table",
            name=f"[__tableau_internal_object_id__].[{self.object_id}]", role="measure", type="quantitative")
        finish_datasource(ds, self.fname, self.object_id, self._relation)
        return ds


class SnowflakeSource(DataSource):
    """Live Snowflake table. Connection attributes mirror references/snowflake-basic."""
    # Live metadata as saved by Desktop (REF-SF, docs/FORMAT.md). Extract metadata uses other codes.
    REMOTE_TYPE = {"string": 129, "date": 7, "datetime": 7, "real": 5, "integer": 131, "boolean": 11}
    PRECISION = {"real": ("15", None), "integer": ("38", "0")}  # (precision, scale), REF-SF
    AUTH = {"oauth": "oauth", "sso": "oauth", "browser": "oauth", "password": "Username Password"}

    def __init__(self, key, spec):
        super().__init__(key)
        sf = spec["snowflake"]
        missing = [k for k in ("server", "warehouse", "database", "schema", "table") if not sf.get(k)]
        if missing:
            raise SpecError(f"Snowflake source {key!r} is missing: {', '.join(missing)}")
        self.sf = sf
        self.server = sf["server"].replace("https://", "").rstrip("/")
        self.db, self.schema, self.table = sf["database"], sf["schema"], sf["table"]
        self.caption = spec.get("caption", f"{self.table} ({self.db}.{self.table}) ({self.schema})")
        self.name = "federated." + sid("ds" + key)
        self.conn = "snowflake." + sid("conn" + key)
        self.object_id = f"{self.table} ({self.db}.{self.table})_{hex32('obj' + key)}"
        cols = spec.get("columns")
        if not cols:
            raise SpecError(f"Snowflake source {key!r} needs a 'columns' map "
                            f"(tip: python3 -m tabgen introspect <existing.twb>)")
        for i, (name, c) in enumerate(cols.items(), 1):
            c = {"type": c} if isinstance(c, str) else c
            self.add_column(make_column(name, c["type"], ordinal=i,
                                        caption=c.get("caption", friendly_caption(name)),
                                        role=c.get("role")))

    def _relation(self, parent):
        sub(parent, "relation", connection=self.conn, name=self.table,
            table=f"[{self.db}].[{self.schema}].[{self.table}]", type="table")

    def to_xml(self, parent):
        sf = self.sf
        auth = self.AUTH.get(sf.get("auth", "oauth"), sf.get("auth"))
        ds = sub(parent, "datasource", caption=self.caption, inline="true", name=self.name, version=TWB_VERSION)
        conn = sub(ds, "connection", **{"class": "federated"})
        nc = sub(sub(conn, "named-connections"), "named-connection", caption=self.server, name=self.conn)
        sub(nc, "connection", **{
            "authentication": auth, "class": "snowflake", "dbname": self.db,
            "instanceurl": "https://" + self.server, "max-varchar-size": "",
            "oauth-config-id": "default" if auth == "oauth" else None,
            "odbc-connect-string-extras": "", "one-time-sql": "", "role": sf.get("role", ""),
            "schema": self.schema, "server": self.server, "server-oauth": "", "service": "",
            "temp-table-detection": "optimized", "username": sf.get("username", ""),
            "warehouse": sf["warehouse"]})
        self._relation(conn)

        mrs = sub(conn, "metadata-records")
        for c in self.physical():
            mr = sub(mrs, "metadata-record", **{"class": "column"})
            sub(mr, "remote-name", c["name"])
            sub(mr, "remote-type", str(self.REMOTE_TYPE[c["datatype"]]))
            sub(mr, "local-name", f"[{c['name']}]")
            sub(mr, "parent-name", f"[{self.table}]")
            sub(mr, "remote-alias", c["name"])
            sub(mr, "ordinal", str(c["ordinal"]))
            sub(mr, "local-type", c["datatype"])
            sub(mr, "aggregation", DEFAULT_AGG[c["datatype"]])
            if c["datatype"] in self.PRECISION:
                precision, scale = self.PRECISION[c["datatype"]]
                sub(mr, "precision", precision)
                if scale is not None:
                    sub(mr, "scale", scale)
            if c["datatype"] == "string":
                sub(mr, "width", "8000")
            sub(mr, "contains-null", "true")
            if c["datatype"] == "string":
                sub(mr, "collation", flag="0", name="binary")
            sub(mr, "object-id", f"[{self.object_id}]")

        sub(ds, "aliases", enabled="yes")
        for c in sorted(self.columns.values(), key=lambda c: c["name"]):
            self.column_xml(ds, c)
        sub(ds, "column", caption=self.table, datatype="table",
            name=f"[__tableau_internal_object_id__].[{self.object_id}]", role="measure", type="quantitative")
        finish_datasource(ds, self.table, self.object_id, self._relation)
        return ds


def finish_datasource(ds, obj_caption, object_id, relation_fn):
    sub(ds, "layout", dim_ordering="alphabetic", measure_ordering="alphabetic", show_structure="true")
    sv = sub(ds, "semantic-values")
    sub(sv, "semantic-value", key="[Country].[Name]", value='"United States"')
    obj = sub(sub(sub(ds, "object-graph"), "objects"), "object", caption=obj_caption, id=object_id)
    relation_fn(sub(obj, "properties", context=""))


def make_source(key, spec, base_dir):
    if "csv" in spec:
        src = CsvSource(key, spec, base_dir)
    elif "snowflake" in spec:
        src = SnowflakeSource(key, spec)
    else:
        raise SpecError(f"Data source {key!r} needs a 'csv' or 'snowflake' block")
    for caption, calc in spec.get("calcs", {}).items():
        src.add_calc(caption, calc)
    return src


def parse_field(s):
    """'sum(Sales)' -> ('Sales', 'sum'); 'Region' -> ('Region', None)"""
    s = s.strip()
    m = re.fullmatch(r"([a-zA-Z]+)\((.+)\)", s)
    if m:
        return m.group(2).strip(), m.group(1).lower()
    return s, None


# ---------------------------------------------------------------- worksheets
def sheet_filters(sheet, spec, ds):
    """Validate a sheet's "filters" map; return [(field, column-instance name)].
    Only boolean fields kept to True are backed by a Desktop reference so far (REF-FILTERS)."""
    filters = spec.get("filters", {})
    if not isinstance(filters, dict):
        raise SpecError(f"Sheet {sheet!r}: 'filters' must be a map of field -> value, "
                        f"e.g. {{\"Recent Run\": true}}")
    out = []
    for field, value in filters.items():
        c = ds.col(field)
        if c["datatype"] != "boolean" or value is not True:
            raise SpecError(f"Sheet {sheet!r}: filter on {field!r} must be a boolean field kept to true "
                            f"(other filter kinds aren't supported yet)")
        out.append((field, ds.ref(field, "none")[1]["name"]))
    return out


def worksheet_xml(parent, name, spec, ds):
    ws = sub(parent, "worksheet", name=name)
    table = sub(ws, "table")
    view = sub(table, "view")
    sub(sub(view, "datasources"), "datasource", caption=ds.caption, name=ds.name)
    deps = sub(view, "datasource-dependencies", datasource=ds.name)

    used = {}

    def use(fieldspec):
        f, agg = parse_field(fieldspec)
        shelf, inst = ds.ref(f, agg)
        used[inst["name"]] = (ds.col(f), inst)
        return shelf

    def shelf(items):
        if isinstance(items, str):
            items = [items]
        return " / ".join(use(i) for i in items) if items else None

    rows = shelf(spec.get("rows", []))
    cols = shelf(spec.get("cols", []))
    enc = {k: use(spec[k]) for k in ("color", "size", "label", "detail", "tooltip") if k in spec}
    filters = [(use(f), inst_name) for f, inst_name in sheet_filters(name, spec, ds)]

    # Columns: every field used, plus the columns a used calc names (no column-instance for those).
    dep_cols = {}
    for col, _ in used.values():
        dep_cols[col["name"]] = col
        for inp in ds.calc_inputs(col):
            dep_cols.setdefault(inp["name"], inp)
    for cname in sorted(dep_cols):
        ds.column_xml(deps, dep_cols[cname])
    for _, inst in sorted(used.values(), key=lambda x: x[1]["name"]):
        sub(deps, "column-instance", **inst)
    for ref, level in filters:
        f = sub(view, "filter", **{"class": "categorical", "column": ref})
        sub(f, "groupfilter", **{"function": "member", "level": level, "member": "true",
                                 "user:ui-domain": "database", "user:ui-enumeration": "inclusive",
                                 "user:ui-marker": "enumerate"})
    if filters:
        slices = sub(view, "slices")
        for ref, _ in filters:
            sub(slices, "column", ref)
    sub(view, "aggregation", value="true")

    sub(table, "style")
    pane = sub(sub(table, "panes"), "pane", selection_relaxation_option="selection-relaxation-allow")
    sub(sub(pane, "view"), "breakdown", value="auto")
    mark = spec.get("mark", "automatic")
    if mark not in MARKS:
        raise SpecError(f"Sheet {name!r}: unknown mark {mark!r} (use one of {', '.join(MARKS)})")
    sub(pane, "mark", **{"class": MARKS[mark]})
    if enc:
        encs = sub(pane, "encodings")
        tagmap = {"label": "text", "detail": "lod"}
        for k, ref in enc.items():
            sub(encs, tagmap.get(k, k), column=ref)
    sub(table, "rows", rows)
    sub(table, "cols", cols)
    sub(ws, "simple-id", uuid=guid("ws" + name))


# ---------------------------------------------------------------- dashboards
SIDE_PX = 160         # Desktop's fixed-width column for filter controls/legends (REF-FILTERS)
FILTER_CARD_PX = 89   # height Desktop gave a boolean filter control (REF-FILTERS)


def dashboard_controls(name, spec, sheets, sheet_source):
    """Validate a dashboard's "filters" list; return [(sheet, data source, field)]."""
    controls = spec.get("filters", [])
    if not isinstance(controls, list):
        raise SpecError(f"Dashboard {name!r}: 'filters' must be a list of {{\"sheet\": ..., \"field\": ...}}")
    placed = {s for row in spec["layout"] for s in row}
    out = []
    for ctl in controls:
        if not isinstance(ctl, dict) or set(ctl) != {"sheet", "field"}:
            raise SpecError(f"Dashboard {name!r}: each filter control needs exactly 'sheet' and 'field'")
        sheet, field = ctl["sheet"], ctl["field"]
        if sheet not in placed:
            raise SpecError(f"Dashboard {name!r}: filter control sheet {sheet!r} is not in its layout")
        if field not in sheets[sheet].get("filters", {}):
            raise SpecError(f"Dashboard {name!r}: sheet {sheet!r} has no filter on {field!r} "
                            f"(add it to the sheet's 'filters' first)")
        out.append((sheet, sheet_source(sheet), field))
    return out


def dashboard_xml(parent, name, spec, ids, controls=()):
    W, H = spec.get("size", [1200, 800])
    db = sub(parent, "dashboard", enable_sort_zone_taborder="true", name=name)
    sub(db, "style")
    sub(db, "size", maxheight=H, maxwidth=W, minheight=H, minwidth=W)
    if controls:
        # Desktop lists the filtered fields (column + instance only, not calc inputs) on the dashboard.
        by_ds = {}
        for _, ds, field in controls:
            fields = by_ds.setdefault(ds.name, (ds, []))[1]
            if field not in fields:
                fields.append(field)
        dss = sub(db, "datasources")
        for ds, _ in by_ds.values():
            sub(dss, "datasource", caption=ds.caption, name=ds.name)
        for ds, fields in by_ds.values():
            deps = sub(db, "datasource-dependencies", datasource=ds.name)
            cols = sorted({ds.col(f)["name"]: ds.col(f) for f in fields}.items())
            for _, c in cols:
                ds.column_xml(deps, c)
            for inst in sorted((ds.ref(f, "none")[1] for f in fields), key=lambda i: i["name"]):
                sub(deps, "column-instance", **inst)
    zones = sub(db, "zones")
    grid = spec["layout"]
    # Zone coordinates are in 1/100000ths of the dashboard; outer padding as Desktop does.
    X0, Y0, IW, IH = 800, 1000, 98400, 98000
    root = sub(zones, "zone", h=100000, id=next(ids), type_v2="layout-basic", w=100000, x=0, y=0)
    side_w = round(SIDE_PX * 100000 / W) if controls else 0
    GW = IW - side_w
    if controls:
        # Grid and a fixed-width side column, side by side (REF-FILTERS).
        outer = sub(root, "zone", h=IH, id=next(ids), param="horz", type_v2="layout-flow", w=IW, x=X0, y=Y0)
    else:
        outer = root
    vert = sub(outer, "zone", h=IH, id=next(ids), param="vert", type_v2="layout-flow", w=GW, x=X0, y=Y0)
    rh = IH // len(grid)
    for r, row in enumerate(grid):
        y = Y0 + r * rh
        horz = sub(vert, "zone", h=rh, id=next(ids), param="horz", type_v2="layout-flow", w=GW, x=X0, y=y)
        cw = GW // len(row)
        for c, sheet in enumerate(row):
            z = sub(horz, "zone", h=rh, id=next(ids), name=sheet, w=cw, x=X0 + c * cw, y=y)
            zone_style(z, "4")
    if controls:
        sx = X0 + GW
        side = sub(outer, "zone", fixed_size=SIDE_PX, h=IH, id=next(ids), is_fixed="true", param="vert",
                   type_v2="layout-flow", w=side_w, x=sx, y=Y0)
        fh = round(FILTER_CARD_PX * 100000 / H)
        for i, (sheet, ds, field) in enumerate(controls):
            z = sub(side, "zone", h=fh, id=next(ids), name=sheet, param=ds.ref(field, "none")[0],
                    type_v2="filter", values="database", w=side_w, x=sx, y=Y0 + i * fh)
            zone_style(z, "4")
    zone_style(root, "8")
    sub(db, "simple-id", uuid=guid("db" + name))


def windows_xml(parent, sheets, dashboards):
    wins = sub(parent, "windows", source_height="30")
    for s in sheets:
        w = sub(wins, "window", **{"class": "worksheet", "name": s})
        cards = sub(w, "cards")
        left = sub(sub(cards, "edge", name="left"), "strip", size="160")
        for t in ("pages", "filters", "marks"):
            sub(left, "card", type=t)
        top = sub(cards, "edge", name="top")
        for t, size in (("columns", "2147483647"), ("rows", "2147483647"), ("title", "31")):
            sub(sub(top, "strip", size=size), "card", type=t)
        sub(w, "simple-id", uuid=guid("win-ws" + s))
    for i, (d, dspec) in enumerate(dashboards.items()):
        w = sub(wins, "window", **{"class": "dashboard", "maximized": "true" if i == 0 else None, "name": d})
        vps = sub(w, "viewpoints")
        for s in sorted({s for row in dspec["layout"] for s in row}):
            sub(sub(vps, "viewpoint", name=s), "zoom", type="entire-view")
        sub(w, "active", id="-1")
        sub(w, "simple-id", uuid=guid("win-db" + d))


# ---------------------------------------------------------------- workbook
def build(spec, base_dir):
    wb = ET.Element("workbook", {"original-version": TWB_VERSION, "source-build": SOURCE_BUILD,
                                 "source-platform": "mac", "version": TWB_VERSION,
                                 "xmlns:user": "http://www.tableausoftware.com/xml/user"})
    man = sub(wb, "document-format-change-manifest")
    for m in MANIFEST:
        sub(man, m)
    prefs = sub(wb, "preferences")
    sub(prefs, "preference", name="ui.encoding.shelf.height", value="24")
    sub(prefs, "preference", name="ui.shelf.height", value="26")

    sources = {k: make_source(k, v, base_dir) for k, v in spec["datasources"].items()}
    dsx = sub(wb, "datasources")
    for ds in sources.values():
        ds.to_xml(dsx)

    default_ds = next(iter(sources.values()))

    def sheet_source(name):
        key = spec["sheets"][name].get("datasource")
        if key is not None and key not in sources:
            raise SpecError(f"Sheet {name!r} uses unknown data source {key!r}")
        return sources[key] if key else default_ds

    wss = sub(wb, "worksheets")
    for name, ws in spec["sheets"].items():
        worksheet_xml(wss, name, ws, sheet_source(name))

    dashboards = spec.get("dashboards", {})
    if dashboards:
        dbs = sub(wb, "dashboards")
        ids = iter(range(1, 100_000))
        for name, d in dashboards.items():
            for row in d["layout"]:
                for s in row:
                    if s not in spec["sheets"]:
                        raise SpecError(f"Dashboard {name!r} references unknown sheet {s!r}")
            dashboard_xml(dbs, name, d, ids, dashboard_controls(name, d, spec["sheets"], sheet_source))

    windows_xml(wb, list(spec["sheets"]), dashboards)
    ET.indent(wb, space="  ")
    return ET.tostring(wb, encoding="unicode", xml_declaration=False)
