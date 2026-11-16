"""Read an existing .twb and emit spec 'datasources' blocks (connection + columns + calcs), plus
the string list 'parameters' those calcs use.

Lets you start a new spec from tables your existing workbooks already connect to.
"""
import re
import xml.etree.ElementTree as ET

from .compiler import friendly_caption

LOCAL_TYPES = ("string", "integer", "real", "date", "datetime", "boolean")


def _slug(text):
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_") or "ds"


def _unquote(v):
    return v[1:-1] if v and len(v) >= 2 and v[0] == v[-1] == '"' else None


def _parameters(root):
    """{internal name: (caption, spec)} for parameters the compiler supports: string, a plain list of
    values (no aliases), values without '"' or '\\'. Others map to None, so calcs using them are dropped."""
    out = {}
    for ds in root.findall("datasources/datasource"):
        if ds.get("name") != "Parameters":
            continue
        for c in ds.findall("column"):
            name = c.get("name", "").strip("[]")
            members = c.findall("members/member")
            values = [_unquote(m.get("value")) for m in members]
            value = _unquote(c.get("value"))
            ok = (c.get("datatype") == "string" and c.get("param-domain-type") == "list" and c.get("caption")
                  and values and all(values) and not any(m.get("alias") is not None for m in members)
                  and not any('"' in v or "\\" in v for v in values) and value in values
                  and len(set(values)) == len(values))
            out[name] = (c.get("caption"), {"type": "string", "values": values, "value": value}) if ok else None
    return out


def introspect(path):
    root = ET.parse(path).getroot()
    out = {}
    params = _parameters(root)
    used_params = {}
    for ds in root.find("datasources") or []:
        conn = ds.find("connection")
        if conn is None or conn.get("class") != "federated":
            continue  # Parameters pseudo-source, etc.
        inner = conn.find("named-connections/named-connection/connection")
        rel = conn.find("relation")
        if inner is None or rel is None:
            continue
        cls = inner.get("class")

        # Column types from metadata-records, captions/roles from <column> elements.
        types, order = {}, []
        for mr in conn.iter("metadata-record"):
            if mr.get("class") != "column":
                continue
            name = mr.findtext("remote-name")
            lt = mr.findtext("local-type")
            if name and lt in LOCAL_TYPES and name not in types:
                types[name] = lt
                order.append(name)
        meta = {c.get("name", "").strip("[]"): c for c in ds.findall("column")}

        columns, calcs = {}, {}
        for name in order:
            c = meta.get(name)
            entry = {"type": types[name]}
            if c is not None:
                cap = c.get("caption")
                if cap and cap != friendly_caption(name):
                    entry["caption"] = cap
                default_role = "measure" if types[name] in ("integer", "real") else "dimension"
                if c.get("role") and c.get("role") != default_role:
                    entry["role"] = c.get("role")
            columns[name] = entry["type"] if list(entry) == ["type"] else entry
        for name, c in meta.items():
            calc = c.find("calculation")
            if calc is None or not c.get("caption"):
                continue
            formula = calc.get("formula") or ""
            refs = re.findall(r"\[Parameters\]\.\[([^\]]+)\]", formula)
            if any(params.get(r) is None for r in refs):
                continue  # uses a parameter the compiler can't write yet
            for r in refs:
                caption, pspec = params[r]
                used_params[caption] = pspec
                formula = formula.replace(f"[Parameters].[{r}]", f"[{caption}]")
            calcs[c.get("caption")] = {"formula": formula, "type": c.get("datatype"),
                                       "role": c.get("role")}

        if cls == "snowflake":
            db, schema, table = re.findall(r"\[([^\]]+)\]", rel.get("table", ""))[-3:]
            block = {"snowflake": {
                "server": inner.get("server"), "warehouse": inner.get("warehouse"),
                "database": db, "schema": schema, "table": table,
                "username": inner.get("username"), "role": inner.get("role", ""),
                "auth": "oauth" if inner.get("authentication") == "oauth" else inner.get("authentication")},
                "columns": columns}
            key = _slug(table)
        elif cls == "textscan":
            block = {"csv": inner.get("directory", "") + "/" + inner.get("filename", "")}
            key = _slug(inner.get("filename", "csv"))
        else:
            block = {"unsupported_connection": cls, "columns": columns}
            key = _slug(ds.get("caption") or cls)
        if calcs:
            block["calcs"] = calcs
        if ds.find("extract") is not None:
            block["note"] = "source workbook uses an extract; tabgen emits a live connection"
        while key in out:
            key += "_2"
        out[key] = block
    if used_params:
        return {"parameters": used_params, "datasources": out}
    return {"datasources": out}
