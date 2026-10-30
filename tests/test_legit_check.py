import copy
import datetime as dt
import json
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import legit_check as lc  # noqa: E402

TODAY = dt.date(2026, 10, 30)


def load(name):
    return json.loads((ROOT / "examples" / name).read_text(encoding="utf-8"))


def by_check(result):
    return {f["check"]: f for f in result["findings"]}


class ExampleProfiles(unittest.TestCase):
    def test_clean_supplier_proceeds(self):
        r = lc.evaluate(load("northgate_supplies.json"), TODAY)
        self.assertEqual(r["verdict"], "proceed")
        self.assertTrue(r["expensive_evidence"])

    def test_red_flag_trader_does_not_proceed(self):
        r = lc.evaluate(load("quickship_trading.json"), TODAY)
        self.assertEqual(r["verdict"], "verify")
        checks = by_check(r)
        self.assertEqual(checks["payment_rails"]["status"], "fail")
        self.assertEqual(checks["references"]["status"], "fail")
        self.assertEqual(checks["email_domain"]["status"], "warn")


class CostToFake(unittest.TestCase):
    def test_cheap_evidence_alone_never_proceeds(self):
        p = {"name": "Shiny Site", "contact_email": "hi@shiny.example", "domain": "shiny.example",
             "address": {},
             "website": {"https": True, "privacy_policy": True, "terms": True,
                         "domain_created": "2015-01-01", "company_number_on_site": True}}
        r = lc.evaluate(p, TODAY)
        self.assertEqual(r["score"], 1.0)
        self.assertFalse(r["expensive_evidence"])
        self.assertEqual(r["verdict"], "verify")

    def test_dissolved_company_stops(self):
        p = load("northgate_supplies.json")
        p["registry"]["status"] = "dissolved"
        self.assertEqual(lc.evaluate(p, TODAY)["verdict"], "stop")

    def test_missing_licence_stops(self):
        p = load("northgate_supplies.json")
        p["licence"] = {"required": True, "register": "FCA Financial Services Register", "found": False}
        self.assertEqual(lc.evaluate(p, TODAY)["verdict"], "stop")

    def test_sanctions_hit_stops(self):
        p = load("northgate_supplies.json")
        p["screening"]["sanctions_hit"] = True
        self.assertEqual(lc.evaluate(p, TODAY)["verdict"], "stop")

    def test_unknown_checks_do_not_count_against_score(self):
        p = load("northgate_supplies.json")
        p["registry"] = {"found": None}
        r = lc.evaluate(p, TODAY)
        self.assertEqual(by_check(r)["registry_record"]["status"], "unknown")
        self.assertEqual(r["verdict"], "proceed")  # references still carry high cost evidence

    def test_fresh_incorporation_warns(self):
        p = copy.deepcopy(load("northgate_supplies.json"))
        p["registry"]["incorporated"] = "2026-08-01"
        self.assertEqual(by_check(lc.evaluate(p, TODAY))["registry_consistency"]["status"], "warn")


class Rules(unittest.TestCase):
    def test_email_domain_mismatch(self):
        f = lc.check_contact({"domain": "a.example", "contact_email": "x@b.example", "address": {}}, TODAY)
        self.assertEqual(f[0].status, "warn")

    def test_mixed_payment_rails_pass(self):
        f = lc.check_payment({"payment_methods": ["wire", "card"]}, TODAY)
        self.assertEqual(f[0].status, "pass")

    def test_review_burst_flagged(self):
        f = lc.check_reputation({"reviews": {"count": 50, "five_star_share": 0.8, "max_same_day": 15}}, TODAY)
        self.assertEqual(f[0].status, "warn")

    def test_bad_date_is_input_error(self):
        self.assertEqual(lc.main(["--today", "2026-10-30", str(ROOT / "tests" / "bad_date.json")]), 3)


if __name__ == "__main__":
    unittest.main()
