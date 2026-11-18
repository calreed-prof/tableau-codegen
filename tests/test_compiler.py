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


    # ---- M3 layout (REF-LAYOUT: references/layout-basic, also checked by tests/test_references.py)
    def layout_db(self, **dash):
        d = {"size": [1200, 800], "layout": [["S1", "S2"], ["S3"]], "legends": []}
        d.update(dash)
        sheets = {n: {"cols": "Region", "rows": "sum(Sales)"} for n in ("S1", "S2", "S3")}
        return self.compile(spec(sheets=sheets, dashboards={"D": d})).find(".//dashboard")

    def test_padding_is_8px(self):
        root = self.layout_db().find("zones/zone")
        grid = root.find("zone")
        self.assertEqual({k: grid.get(k) for k in "xywh"}, {"x": "667", "y": "1000", "w": "98666", "h": "98000"})
        grid = self.layout_db(size=[1400, 900]).find("zones/zone/zone")
        self.assertEqual({k: grid.get(k) for k in "xywh"}, {"x": "571", "y": "889", "w": "98858", "h": "98222"})

    def test_title_text_and_fixed_sizes(self):
        db = self.layout_db(title=True, text="Hello", row_heights=[456, None], col_widths=[[609, None], [None]])
        outer = db.find("zones/zone/zone")
        title, text, grid = outer.findall("zone")
        self.assertEqual((outer.get("param"), title.get("type-v2"), text.get("type-v2")), ("vert", "title", "text"))
        self.assertEqual((title.get("h"), text.get("h"), grid.get("y")), ("5250", "3125", "9375"))
        self.assertEqual(text.find("formatted-text/run").text, "Hello")
        top, bottom = grid.findall("zone")
        self.assertEqual((top.get("fixed-size"), top.get("is-fixed"), top.get("h")), ("456", "true", "57000"))
        self.assertIsNone(bottom.get("is-fixed"))
        self.assertEqual(int(top.get("h")) + int(bottom.get("h")), int(grid.get("h")))
        s1, s2 = top.findall("zone")
        self.assertEqual((s1.get("fixed-size"), s1.get("w"), s2.get("x")), ("601", "50750", str(667 + 50750)))
        self.assertEqual(int(s1.get("w")) + int(s2.get("w")), int(top.get("w")))

    def test_equal_split_is_pinned(self):
        # Desktop re-splits flexible zones by content on open, so equal shares are written as fixed
        # px on every flexible slot but the last (REF-EVEN-SPLIT: 1184px -> 592px, fixed-size 584).
        grid = self.layout_db().find("zones/zone/zone")
        top, bottom = grid.findall("zone")
        self.assertEqual((top.get("fixed-size"), top.get("is-fixed")), ("392", "true"))  # (800 - 16) / 2
        self.assertIsNone(bottom.get("is-fixed"))
        s1, s2 = top.findall("zone")
        self.assertEqual((s1.get("fixed-size"), s1.get("is-fixed"), s1.get("w")), ("584", "true", "49333"))
        self.assertIsNone(s2.get("is-fixed"))
        self.assertIsNone(bottom.find("zone").get("is-fixed"))  # a lone sheet stays flexible

    def test_equal_split_shares_what_fixed_slots_leave(self):
        db = self.layout_db(layout=[["S1", "S2", "S3"]], col_widths=[[300, None, None]])
        s1, s2, s3 = db.find("zones/zone/zone/zone").findall("zone")
        self.assertEqual((s1.get("fixed-size"), s2.get("fixed-size"), s3.get("is-fixed")), ("292", "434", None))

    def test_equal_split_after_title_and_side_column(self):
        sheets = {n: {"cols": "Region", "rows": "sum(Sales)", "color": "Category"} for n in ("S1", "S2", "S3")}
        d = {"size": [1200, 800], "layout": [["S1", "S2"], ["S3"]], "title": True}
        db = self.compile(spec(sheets=sheets, dashboards={"D": d})).find(".//dashboard")
        horz = [z for z in db.iter("zone") if z.get("param") == "horz" and z.get("fixed-size")]
        # Height: 800 - 16 - 42 title = 742 -> 371. Width: 1200 - 16 - 160 side = 1024 -> 512 -> 504.
        self.assertEqual([z.get("fixed-size") for z in horz], ["371"])
        self.assertEqual([z.get("fixed-size") for z in db.iter("zone") if z.get("name") == "S1"][0], "504")

    def test_missing_layout_is_spec_error(self):
        with self.assertRaises(SystemExit) as cm:
            build(spec(dashboards={"D": {"size": [1200, 800]}}), EXAMPLE)
        self.assertIn("'layout' must be", str(cm.exception))
        self.assertNotIsInstance(cm.exception, KeyError)

    def test_no_title_no_wrapper(self):
        self.assertEqual(self.layout_db().find("zones/zone/zone").get("param"), "vert")
        self.assertFalse([z for z in self.layout_db().iter("zone") if z.get("type-v2") in ("title", "text")])

    def test_layout_errors(self):
        for dash, msg in (({"row_heights": [100]}, "needs 2"), ({"row_heights": [100, 100]}, "at least one null"),
                          ({"row_heights": [0, None]}, "positive"), ({"row_heights": [True, None]}, "positive"),
                          ({"row_heights": [5000, None]}, "no room"), ({"col_widths": [[100, None]]}, "one list"),
                          ({"col_widths": [[100, None], [100]]}, "at least one null"),
                          ({"col_widths": [[5000, None], [None]]}, "no room"),
                          ({"title": "Hi"}, "true or false"), ({"text": ""}, "one non-empty line"),
                          ({"text": "a\nb"}, "one non-empty line"), ({"layout": []}, "non-empty"),
                          ({"layout": None}, "non-empty"), ({"layout": [["S1"], "S2x"]}, "non-empty"),
                          ({"layout": [["S1", 3]]}, "sheet names"),
                          ({"col_widths": [[8, None], [None]]}, "more than 8px"),
                          ({"layout": [["S1", "S2", "S3"]], "col_widths": [[1190, None, None]]}, "no room"),
                          ({"size": [100, 800], "layout": [["S1", "S2", "S3"] * 4]}, "too many sheets"),
                          ({"size": [1200, 30], "layout": [["S1"]] * 15}, "too many rows")):
            with self.assertRaises(SystemExit) as cm:
                self.layout_db(**dash)
            self.assertIn(msg, str(cm.exception))


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
        for sheet_filters, msg in (({"Region": True}, "two or more"), ({"Recent": False}, "true"),
                                   ({"Nope": True}, "Unknown field"), (["Recent"], "map"),
                                   ({"Region": ["East"]}, "two or more"), ({"Region": "East"}, "two or more"),
                                   ({"Region": ["E", "E"]}, "different"), ({"Region": ["a\"b", "c"]}, "contain"),
                                   ({"Region": ["", "c"]}, "empty"), ({"Region": ["a\\b", "c"]}, "contain"),
                                   ({"Sales Amt": [1, 2]}, "string dimension"),
                                   ({"Order Ts": ["a", "b"]}, "string dimension")):
            with self.assertRaises(SystemExit) as cm:
                self.filtered(dash_filters=[], sheet_filters=sheet_filters)
            self.assertIn(msg, str(cm.exception))
        for dash, msg in (([{"sheet": "X", "field": "Recent"}], "not in its layout"),
                          ([{"sheet": "S", "field": "Region"}], "no filter on"),
                          ([{"sheet": "S"}], "exactly"), ({"S": "Recent"}, "list")):
            with self.assertRaises(SystemExit) as cm:
                self.filtered(dash_filters=dash)
            self.assertIn(msg, str(cm.exception))

    # ---- M1 part 2: string member filters, from REF-FILTERS-CAT (Desktop 2026.2.1, private)
    def test_string_member_filter_on_worksheet(self):
        wb = self.filtered(dash_filters=[], sheet_filters={"Region": ["Company", "Division"]})
        view = wb.find(".//worksheet/table/view")
        f = view.find("filter")
        self.assertTrue(f.get("column").endswith("[none:REGION:nk]"))
        U = "{http://www.tableausoftware.com/xml/user}"
        (union,) = list(f)
        self.assertEqual(dict(union.attrib), {"function": "union", U + "ui-domain": "database",
                                              U + "ui-enumeration": "inclusive", U + "ui-marker": "enumerate"})
        self.assertEqual([dict(g.attrib) for g in union],
                         [{"function": "member", "level": "[none:REGION:nk]", "member": '"Company"'},
                          {"function": "member", "level": "[none:REGION:nk]", "member": '"Division"'}])
        self.assertEqual([c.text for c in view.find("slices")], [f.get("column")])
        xml = build({"datasources": {"sf": SNOWFLAKE},
                     "sheets": {"S": {"cols": "Region", "filters": {"Region": ["Company", "Division"]}}}},
                    EXAMPLE)
        self.assertIn('member="&quot;Company&quot;"', xml)  # Desktop writes member='&quot;Company&quot;'

    def test_dashboard_controls_from_two_sources(self):
        sf2 = dict(SNOWFLAKE, snowflake=dict(SNOWFLAKE["snowflake"], table="OTHER"),
                   calcs={"Recent": {"formula": "{ FIXED : MAX([ORDER_TS]) } = [ORDER_TS]", "type": "boolean"}})
        s = {"datasources": {"a": sf2, "b": SNOWFLAKE},
             "sheets": {"W": {"datasource": "a", "cols": "Region", "filters": {"Recent": True}},
                        "L": {"datasource": "b", "cols": "Region",
                              "filters": {"Region": ["Company", "Division"]}}},
             "dashboards": {"D": {"size": [1400, 900], "layout": [["W", "L"]], "legends": [],
                                  "filters": [{"sheet": "W", "field": "Recent"},
                                              {"sheet": "L", "field": "Region"}]}}}
        db = ET.fromstring(build(s, EXAMPLE)).find(".//dashboard")
        # One <datasources> entry and one <datasource-dependencies> per source, in control order.
        names = [d.get("name") for d in db.find("datasources")]
        self.assertEqual([d.get("datasource") for d in db.findall("datasource-dependencies")], names)
        self.assertEqual([d.find("column").get("caption") for d in db.findall("datasource-dependencies")],
                         ["Recent", "Region"])
        ctls = [z for z in db.iter("zone") if z.get("type-v2") == "filter"]
        self.assertEqual([(z.get("name"), z.get("h")) for z in ctls], [("W", "9889"), ("L", "22556")])
        self.assertEqual(int(ctls[1].get("y")), int(ctls[0].get("y")) + int(ctls[0].get("h")))

    # ---- M2 legends: expected zone from REF-FILTERS (Desktop 2026.2.1, private; values written out here)
    def legends_wb(self, legends=None, sheets=None):
        sheets = sheets or {"A": {"cols": "Fiscal Year", "rows": "sum(Sales Amt)", "color": "Region"},
                            "B": {"cols": "Fiscal Year", "rows": "sum(Sales Amt)", "color": "Region"},
                            "C": {"cols": "Region", "rows": "sum(Sales Amt)", "color": "sum(Sales Amt)"},
                            "N": {"cols": "Region", "rows": "sum(Sales Amt)"}}
        dash = {"size": [1400, 900], "layout": [list(sheets)]}
        if legends is not None:
            dash["legends"] = legends
        s = {"datasources": {"sf": SNOWFLAKE}, "sheets": sheets, "dashboards": {"D": dash}}
        return ET.fromstring(build(s, EXAMPLE))

    def color_zones(self, wb):
        return [z for z in wb.iter("zone") if z.get("type-v2") == "color"]

    def test_color_legend_zone_matches_reference(self):
        wb = self.legends_wb(["B"])
        (z,) = self.color_zones(wb)
        enc = [w for w in wb.iter("worksheet") if w.get("name") == "B"][0].find(".//encodings/color")
        self.assertEqual({k: z.get(k) for k in ("name", "pane-specification-id", "param", "type-v2", "h", "w")},
                         {"name": "B", "pane-specification-id": "0", "param": enc.get("column"),
                          "type-v2": "color", "h": "7333", "w": "11429"})
        self.assertTrue(enc.get("column").endswith("[none:REGION:nk]"))
        self.assertEqual(z.find("zone-style/format[@attr='margin']").get("value"), "4")
        side = wb.find(".//dashboard/zones/zone/zone").findall("zone")[1]
        self.assertEqual((side.get("is-fixed"), side.get("fixed-size")), ("true", "160"))
        # Legends add no dashboard-level datasources/dependencies (REF-FILTERS lists only the filter).
        self.assertIsNone(wb.find(".//dashboard/datasources"))

    def test_auto_legends_dedupe(self):
        zones = self.color_zones(self.legends_wb())
        self.assertEqual([z.get("name") for z in zones], ["A", "C"])  # B repeats A's field

    # ---- M2 part 2: values from REF-LEGENDS-SIZE (references/legends-size, 1200x800: 65px, 106px)
    def test_continuous_color_and_size_legends(self):
        sheets = {"M": {"cols": "Region", "rows": "Fiscal Year", "color": "sum(Sales Amt)",
                        "size": "sum(Sales Amt)", "mark": "circle"}}
        side = [z for z in self.legends_wb(["M"], sheets).iter("zone") if z.get("pane-specification-id")]
        self.assertEqual([(z.get("type-v2"), z.get("h")) for z in side],
                         [("color", "7222"), ("size", "11778")])  # 65px, 106px of 900
        self.assertTrue(all(z.get("param").endswith("[sum:SALES_AMT:qk]") for z in side))
        self.assertEqual(int(side[1].get("y")), int(side[0].get("y")) + int(side[0].get("h")))

    def test_unsupported_legend_encodings_skipped(self):
        # A dimension on size and a date part on color have no reference: no legend for them.
        sheets = {"S": {"cols": "Region", "rows": "sum(Sales Amt)", "size": "Region"},
                  "T": {"cols": "Region", "rows": "sum(Sales Amt)", "color": "Order Ts"}}  # yr:...:ok
        wb = self.legends_wb(None, sheets)
        self.assertFalse([z for z in wb.iter("zone") if z.get("pane-specification-id")])
        for legends in (["S"], ["T"]):
            with self.assertRaises(SystemExit) as cm:
                self.legends_wb(legends, sheets)
            self.assertIn("no legend to show", str(cm.exception))

    def test_legends_off(self):
        wb = self.legends_wb([])
        self.assertFalse(self.color_zones(wb))
        self.assertEqual(wb.find(".//dashboard/zones/zone/zone").get("param"), "vert")

    def test_legend_stacks_below_filter_control(self):
        wb = self.filtered()  # sheet S has no color: no legend
        self.assertFalse(self.color_zones(wb))
        sf = dict(SNOWFLAKE, calcs={"Recent": {"formula": "{ FIXED : MAX([ORDER_TS]) } = [ORDER_TS]",
                                               "type": "boolean"}})
        s = {"datasources": {"sf": sf},
             "sheets": {"S": {"cols": "Region", "rows": "sum(Sales Amt)", "color": "Region",
                              "filters": {"Recent": True}}},
             "dashboards": {"D": {"size": [1400, 900], "layout": [["S"]],
                                  "filters": [{"sheet": "S", "field": "Recent"}]}}}
        side = ET.fromstring(build(s, EXAMPLE)).find(".//dashboard/zones/zone/zone").findall("zone")[1]
        filt, leg = side.findall("zone")
        self.assertEqual((filt.get("type-v2"), leg.get("type-v2")), ("filter", "color"))
        self.assertEqual(int(leg.get("y")), int(filt.get("y")) + int(filt.get("h")))

    def test_legend_errors(self):
        for legends, msg in ((["X"], "not in its layout"), (["N"], "no legend to show"),
                             ("A", "list")):
            with self.assertRaises(SystemExit) as cm:
                self.legends_wb(legends)
            self.assertIn(msg, str(cm.exception))

    def test_missing_columns_errors(self):
        bad = {"snowflake": SNOWFLAKE["snowflake"]}
        with self.assertRaises(SystemExit) as cm:
            build({"datasources": {"sf": bad}, "sheets": {}}, EXAMPLE)
        self.assertIn("introspect", str(cm.exception))


class ParameterTests(unittest.TestCase):
    """M4 parameters (REF-PARAMS: references/parameters-list)."""

    def compile(self, s):
        return ET.fromstring(build(s, EXAMPLE))

    PARAMS = {"Metric Choice": {"type": "string", "values": ["Sales", "Profit"]}}
    CHOSEN = "IF [Metric Choice] = 'Sales' THEN [Sales] ELSE [Profit] END"

    def params_spec(self, params=None, calcs=None, dashboard=None, sheets=None):
        return spec(parameters=self.PARAMS if params is None else params,
                    datasources={"sales": {"csv": "sales.csv",
                                           "calcs": calcs or {"Chosen Metric": self.CHOSEN}}},
                    sheets=sheets or {"S1": {"rows": "Category", "cols": "sum(Chosen Metric)"},
                                      "S2": {"cols": "Region", "rows": "sum(Sales)"}},
                    dashboards={"D": dashboard or {"layout": [["S1", "S2"]], "parameters": ["Metric Choice"]}})

    def test_parameter_source_and_formula(self):
        wb = self.compile(self.params_spec())
        dss = wb.findall("datasources/datasource")
        self.assertEqual([d.get("name") for d in dss][1:], ["Parameters"])  # after the real sources
        p = dss[1].find("column")
        self.assertEqual((p.get("caption"), p.get("param-domain-type"), p.get("value")),
                         ("Metric Choice", "list", '"Sales"'))
        self.assertRegex(p.get("name"), r"^\[Parameter \d{16}\]$")
        self.assertEqual(p.find("calculation").get("formula"), '"Sales"')
        self.assertEqual([m.get("value") for m in p.findall("members/member")], ['"Sales"', '"Profit"'])
        calc = [c for c in dss[0].findall("column") if c.get("caption") == "Chosen Metric"][0]
        self.assertEqual(calc.find("calculation").get("formula"),
                         f"IF [Parameters].{p.get('name')} = 'Sales' THEN [Sales] ELSE [Profit] END")
        # The data source lists the parameter its calc uses, without members, before object-graph.
        tags = [c.tag for c in dss[0]]
        self.assertLess(tags.index("datasource-dependencies"), tags.index("object-graph"))
        dep = dss[0].find("datasource-dependencies")
        self.assertEqual(dep.get("datasource"), "Parameters")
        self.assertIsNone(dep.find("column/members"))

    def test_parameter_sheet_dependencies(self):
        wb = self.compile(self.params_spec())
        s1, s2 = wb.findall(".//worksheet/table/view")
        self.assertEqual([d.get("name") for d in s1.findall("datasources/datasource")][1], "Parameters")
        self.assertEqual([d.get("datasource") for d in s1.findall("datasource-dependencies")][0], "Parameters")
        self.assertEqual(len(s2.findall("datasources/datasource")), 1)  # doesn't use the calc
        self.assertEqual(len(s2.findall("datasource-dependencies")), 1)

    def test_parameter_control_zone(self):
        wb = self.compile(self.params_spec())
        db = wb.find(".//dashboard")
        self.assertEqual([d.get("name") for d in db.findall("datasources/datasource")], ["Parameters"])
        self.assertEqual(len(db.findall("datasource-dependencies/column/members/member")), 2)
        z = [z for z in db.iter("zone") if z.get("type-v2") == "paramctrl"][0]
        self.assertEqual((z.get("mode"), z.get("name"), z.get("h")), ("compact", None, "6500"))  # 52px of 800
        self.assertTrue(z.get("param").startswith("[Parameters].[Parameter "))

    def test_no_parameters_no_source(self):
        wb = self.compile(spec())
        self.assertNotIn("Parameters", [d.get("name") for d in wb.findall("datasources/datasource")])

    def test_parameter_errors(self):
        cases = [
            (self.params_spec(params={"P": {"type": "integer", "values": ["1", "2"]}}), "only string"),
            (self.params_spec(params={"P": {"values": []}}), "'values' must be"),
            (self.params_spec(params={"P": {"values": ["a", "a"]}}), "'values' must be"),
            (self.params_spec(params={"P": {"values": ['a"b']}}), "can't be empty"),
            (self.params_spec(params={"P": {"values": ["a"], "value": "b"}}), "not one of"),
            (self.params_spec(params={"P": {"values": ["a"], "range": [1, 2]}}), "must be"),
            (self.params_spec(params={"Region": {"values": ["a"]}}), "same name as a field"),
            (self.params_spec(params={"Chosen Metric": {"values": ["a"]}}), "same name as a field"),
            (self.params_spec(dashboard={"layout": [["S1"]], "parameters": ["Nope"]}), "unknown parameter"),
            (self.params_spec(dashboard={"layout": [["S1"]], "parameters": "Metric Choice"}), "list of parameter"),
            (self.params_spec(sheets={"S1": {"rows": "Category", "filters": {"Region": ["East", "West"]}}},
                              dashboard={"layout": [["S1"]], "parameters": ["Metric Choice"],
                                         "filters": [{"sheet": "S1", "field": "Region"}]}), "aren't supported yet"),
        ]
        for s, msg in cases:
            with self.subTest(msg=msg), self.assertRaises(SystemExit) as cm:
                build(s, EXAMPLE)
            self.assertIn(msg, str(cm.exception))

    def test_parameter_rewrite_leaves_qualified_refs(self):
        wb = self.compile(self.params_spec(calcs={"C": "[Metric Choice] + [Parameters].[Metric Choice]"},
                                                 sheets={"S1": {"rows": "Category"}, "S2": {"rows": "Region"}}))
        f = [c for c in wb.findall("datasources/datasource/column") if c.get("caption") == "C"][0]
        self.assertRegex(f.find("calculation").get("formula"),
                         r"^\[Parameters\]\.\[Parameter \d+\] \+ \[Parameters\]\.\[Metric Choice\]$")


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

    def test_keeps_string_list_parameter_calcs(self):
        from tabgen.introspect import introspect
        out = introspect(os.path.join(ROOT, "references", "parameters-list", "desktop-saved.twb"))
        self.assertEqual(out["parameters"], {"Metric Choice": {"type": "string", "values": ["Sales", "Profit"],
                                                               "value": "Sales"}})
        calcs = next(iter(out["datasources"].values()))["calcs"]
        self.assertEqual(calcs["Chosen Metric"]["formula"],
                         "IF [Metric Choice] = 'Sales' THEN [Sales] ELSE [Profit] END")

    def test_drops_calcs_on_unsupported_parameters(self):
        import tempfile
        from tabgen.introspect import introspect
        with open(os.path.join(ROOT, "references", "parameters-list", "desktop-saved.twb"), encoding="utf-8") as fh:
            xml = fh.read().replace("param-domain-type='list'", "param-domain-type='range'")
        with tempfile.NamedTemporaryFile("w", suffix=".twb", delete=False) as fh:
            fh.write(xml)
        out = introspect(fh.name)
        self.assertNotIn("parameters", out)
        self.assertNotIn("Chosen Metric", next(iter(out["datasources"].values()))["calcs"])


if __name__ == "__main__":
    unittest.main()
