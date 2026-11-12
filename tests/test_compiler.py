import os
import unittest
import xml.etree.ElementTree as ET

from tabgen import build

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLE = os.path.join(ROOT, "examples", "superstore-mini")


def spec(**over):
    s = {
        "datasources": {"sales": {"csv": "sales.csv", "calcs": {"Profit Ratio": "SUM([Profit]) / SUM([Sales])"}}},
        "sheets": {"S1": {"cols": "Region", "rows": "sum(Sales)", "color": "Category", "mark": "bar"}},
        "dashboards": {"D": {"layout": [["S1"]]}},
    }
    s.update(over)
    return s


class CompilerTests(unittest.TestCase):
    def compile(self, s):
        return ET.fromstring(build(s, EXAMPLE))

    def test_desktop_native_version(self):
        wb = self.compile(spec())
        self.assertEqual(wb.get("version"), "18.1")

    def test_shelf_encoding(self):
        wb = self.compile(spec())
        rows = wb.find(".//worksheet/table/rows").text
        cols = wb.find(".//worksheet/table/cols").text
        self.assertRegex(rows, r"^\[federated\.\w+\]\.\[sum:Sales:qk\]$")
        self.assertRegex(cols, r"^\[federated\.\w+\]\.\[none:Region:nk\]$")

    def test_type_inference(self):
        wb = self.compile(spec())
        types = {c.get("name"): c.get("datatype") for c in wb.findall(".//relation/columns/column")}
        self.assertEqual(types["Category"], "string")
        self.assertEqual(types["Order Date"], "date")
        self.assertEqual(types["Sales"], "real")

    def test_aggregated_calc_uses_user_derivation(self):
        s = spec(sheets={"S1": {"cols": "Region", "rows": "Profit Ratio"}})
        wb = self.compile(s)
        self.assertRegex(wb.find(".//worksheet/table/rows").text, r"\[usr:Calculation_\d+:qk\]")

    def test_unknown_field_errors(self):
        with self.assertRaises(SystemExit) as cm:
            build(spec(sheets={"S1": {"rows": "sum(Revenue)"}}), EXAMPLE)
        self.assertIn("Revenue", str(cm.exception))

    def test_unknown_sheet_in_dashboard_errors(self):
        with self.assertRaises(SystemExit):
            build(spec(dashboards={"D": {"layout": [["Nope"]]}}), EXAMPLE)

    def test_deterministic(self):
        self.assertEqual(build(spec(), EXAMPLE), build(spec(), EXAMPLE))

    def test_zone_ids_unique(self):
        wb = self.compile(spec(dashboards={"A": {"layout": [["S1"]]}, "B": {"layout": [["S1"]]}}))
        ids = [z.get("id") for z in wb.iter("zone")]
        self.assertEqual(len(ids), len(set(ids)))



SNOWFLAKE = {
    "snowflake": {"server": "acct.snowflakecomputing.com", "warehouse": "WH", "database": "DB",
                  "schema": "SCH", "table": "ORDERS", "username": "ME", "auth": "oauth"},
    "columns": {"REGION": "string", "SALES_AMT": "real", "ORDER_TS": "datetime",
                "FISCAL_YEAR": {"type": "integer", "role": "dimension"}},
    "calcs": {"Margin": "SUM([SALES_AMT]) / 2", "Sales K": "[SALES_AMT] / 1000"},
}


class SnowflakeTests(unittest.TestCase):
    def compile(self, sheet):
        s = {"datasources": {"sf": SNOWFLAKE}, "sheets": {"S": sheet}}
        return ET.fromstring(build(s, EXAMPLE))

    def test_connection_attributes(self):
        wb = self.compile({"cols": "Region", "rows": "sum(Sales Amt)"})
        c = wb.find(".//named-connection/connection")
        self.assertEqual(c.get("class"), "snowflake")
        self.assertEqual(c.get("authentication"), "oauth")
        self.assertEqual(c.get("instanceurl"), "https://acct.snowflakecomputing.com")
        self.assertEqual(wb.find(".//connection/relation").get("table"), "[DB].[SCH].[ORDERS]")

    def test_caption_and_raw_name_resolve_to_same_field(self):
        a = self.compile({"rows": "sum(Sales Amt)"}).find(".//rows").text
        b = self.compile({"rows": "sum(SALES_AMT)"}).find(".//rows").text
        self.assertEqual(a, b)
        self.assertTrue(a.endswith("[sum:SALES_AMT:qk]"))

    def test_numeric_dimension_and_date_default(self):
        wb = self.compile({"cols": "Fiscal Year", "rows": "Order Ts"})
        self.assertTrue(wb.find(".//cols").text.endswith("[none:FISCAL_YEAR:qk]"))
        self.assertTrue(wb.find(".//rows").text.endswith("[yr:ORDER_TS:ok]"))

    def test_row_level_vs_aggregate_calcs(self):
        self.assertIn("[usr:Calculation_", self.compile({"rows": "Margin"}).find(".//rows").text)
        self.assertIn("[sum:Calculation_", self.compile({"rows": "Sales K"}).find(".//rows").text)

    def test_metadata_records_match_desktop_reference(self):
        # Values and child order from a Desktop 2026.2.1 save of a live Snowflake table (REF-SF in
        # docs/FORMAT.md; the workbook is private, so the expected values are written out here).
        s = {"datasources": {"sf": dict(SNOWFLAKE, columns={
            "S": "string", "R": "real", "I": "integer", "D": "date", "T": "datetime", "B": "boolean"})},
            "sheets": {"X": {"rows": "sum(R)"}}}
        wb = ET.fromstring(build(s, EXAMPLE))
        recs = {m.findtext("remote-name"): m for m in wb.iter("metadata-record") if m.get("class") == "column"}
        expected = {
            "S": ("129", [("width", "8000"), ("contains-null", "true"), ("collation", None)]),
            "R": ("5", [("precision", "15"), ("contains-null", "true")]),
            "I": ("131", [("precision", "38"), ("scale", "0"), ("contains-null", "true")]),
            "D": ("7", [("contains-null", "true")]),
            "T": ("7", [("contains-null", "true")]),
            "B": ("11", [("contains-null", "true")]),
        }
        for name, (remote_type, after_agg) in expected.items():
            mr = recs[name]
            self.assertEqual(mr.findtext("remote-type"), remote_type, name)
            tags = [c.tag for c in mr]
            tail = [(c.tag, c.text) for c in mr][tags.index("aggregation") + 1:tags.index("object-id")]
            self.assertEqual([(t, v if t != "collation" else None) for t, v in tail], after_agg, name)

    # ---- M1 filters: expected XML from a Desktop 2026.2.1 save (REF-FILTERS in docs/FORMAT.md; private)
    def filtered(self, dash_filters=None, sheet_filters=None):
        sf = dict(SNOWFLAKE, calcs=dict(SNOWFLAKE["calcs"], **{
            "Recent": {"formula": "{ FIXED : MAX([ORDER_TS]) } = [ORDER_TS]", "type": "boolean"}}))
        s = {"datasources": {"sf": sf},
             "sheets": {"S": {"cols": "Region", "rows": "sum(Sales Amt)",
                              "filters": {"Recent": True} if sheet_filters is None else sheet_filters}},
             "dashboards": {"D": {"size": [1400, 900], "layout": [["S"]],
                                  "filters": [{"sheet": "S", "field": "Recent"}]
                                  if dash_filters is None else dash_filters}}}
        return ET.fromstring(build(s, EXAMPLE))

    def test_boolean_filter_on_worksheet(self):
        wb = self.filtered()
        view = wb.find(".//worksheet/table/view")
        ref = view.find("filter").get("column")
        self.assertRegex(ref, r"^\[federated\.\w+\]\.\[none:Calculation_\d+:nk\]$")
        self.assertEqual(view.find("filter").get("class"), "categorical")
        g = view.find("filter/groupfilter")
        U = "{http://www.tableausoftware.com/xml/user}"
        self.assertEqual(dict(g.attrib), {
            "function": "member", "level": ref[ref.index("].[") + 2:], "member": "true",
            U + "ui-domain": "database", U + "ui-enumeration": "inclusive", U + "ui-marker": "enumerate"})
        self.assertEqual([c.text for c in view.find("slices")], [ref])
        # Desktop's order inside <view>: datasources, dependencies, filter, slices, aggregation.
        self.assertEqual([c.tag for c in view],
                         ["datasources", "datasource-dependencies", "filter", "slices", "aggregation"])

    def test_calc_inputs_listed_in_dependencies(self):
        deps = self.filtered().find(".//worksheet//datasource-dependencies")
        cols = [c.get("name") for c in deps.findall("column")]
        insts = [c.get("name") for c in deps.findall("column-instance")]
        self.assertIn("[ORDER_TS]", cols)  # named by the Recent calc; not on any shelf
        self.assertFalse(any("ORDER_TS" in i for i in insts))
        self.assertEqual(cols, sorted(cols))

    def test_no_filters_no_slices(self):
        view = self.filtered(dash_filters=[], sheet_filters={}).find(".//worksheet/table/view")
        self.assertIsNone(view.find("filter"))
        self.assertIsNone(view.find("slices"))

    def test_dashboard_filter_control(self):
        db = self.filtered().find(".//dashboard")
        self.assertEqual([c.tag for c in db][:5],
                         ["style", "size", "datasources", "datasource-dependencies", "zones"])
        deps = db.find("datasource-dependencies")
        self.assertEqual([c.get("caption") for c in deps.findall("column")], ["Recent"])
        self.assertEqual(len(deps.findall("column-instance")), 1)
        outer = db.find("zones/zone/zone")
        self.assertEqual((outer.get("param"), outer.get("type-v2")), ("horz", "layout-flow"))
        grid, side = outer.findall("zone")
        self.assertEqual(grid.get("param"), "vert")
        self.assertEqual({k: side.get(k) for k in ("fixed-size", "is-fixed", "param", "w")},
                         {"fixed-size": "160", "is-fixed": "true", "param": "vert", "w": "11429"})
        ctl = side.find("zone")
        filt = self.filtered().find(".//worksheet//filter").get("column")
        self.assertEqual({k: ctl.get(k) for k in ("name", "param", "type-v2", "values", "h", "w")},
                         {"name": "S", "param": filt, "type-v2": "filter", "values": "database",
                          "h": "9889", "w": "11429"})
        self.assertEqual(int(grid.get("w")) + int(side.get("w")), int(outer.get("w")))

    def test_dashboard_without_controls_unchanged(self):
        db = self.filtered(dash_filters=[]).find(".//dashboard")
        self.assertIsNone(db.find("datasources"))
        self.assertEqual(db.find("zones/zone/zone").get("param"), "vert")
        self.assertFalse([z for z in db.iter("zone") if z.get("type-v2") == "filter"])

    def test_filter_errors(self):
        for sheet_filters, msg in (({"Region": True}, "boolean"), ({"Recent": False}, "true"),
                                   ({"Nope": True}, "Unknown field"), (["Recent"], "map")):
            with self.assertRaises(SystemExit) as cm:
                self.filtered(dash_filters=[], sheet_filters=sheet_filters)
            self.assertIn(msg, str(cm.exception))
        for dash, msg in (([{"sheet": "X", "field": "Recent"}], "not in its layout"),
                          ([{"sheet": "S", "field": "Region"}], "no filter on"),
                          ([{"sheet": "S"}], "exactly"), ({"S": "Recent"}, "list")):
            with self.assertRaises(SystemExit) as cm:
                self.filtered(dash_filters=dash)
            self.assertIn(msg, str(cm.exception))

    def test_missing_columns_errors(self):
        bad = {"snowflake": SNOWFLAKE["snowflake"]}
        with self.assertRaises(SystemExit) as cm:
            build({"datasources": {"sf": bad}, "sheets": {}}, EXAMPLE)
        self.assertIn("introspect", str(cm.exception))


class IntrospectTests(unittest.TestCase):
    def test_round_trip_from_generated_workbook(self):
        import tempfile
        from tabgen.introspect import introspect
        xml = build({"datasources": {"sf": SNOWFLAKE}, "sheets": {"S": {"rows": "sum(SALES_AMT)"}}}, EXAMPLE)
        with tempfile.NamedTemporaryFile("w", suffix=".twb", delete=False) as fh:
            fh.write(xml)
        ds = introspect(fh.name)["datasources"]["orders"]
        self.assertEqual(ds["snowflake"]["table"], "ORDERS")
        self.assertEqual(ds["columns"]["SALES_AMT"], "real")
        self.assertEqual(ds["columns"]["FISCAL_YEAR"], {"type": "integer", "role": "dimension"})


if __name__ == "__main__":
    unittest.main()
