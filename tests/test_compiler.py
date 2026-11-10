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
