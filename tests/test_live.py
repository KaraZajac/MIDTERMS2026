"""Election night: the civicAPI map and the conditioned forecast."""

import json
import math
import unittest

import numpy as np

from midterms.model import live as L
from midterms.paths import SITE
from midterms.pipeline import civic

SIM = json.loads((SITE / "sim.json").read_text())


class TestT(unittest.TestCase):
    def test_cdf(self):
        # textbook quantiles: t(6) 0.975 = 2.447, t(5) 0.95 = 2.015, t(3) 0.9 = 1.638
        for nu, z, p in ((6, 2.447, 0.975), (5, 2.015, 0.95), (3, 1.638, 0.9), (4, 0.0, 0.5)):
            self.assertAlmostEqual(float(L.t_cdf(np.array(z), nu)), p, places=3)
            self.assertAlmostEqual(float(L.t_cdf(np.array(-z), nu)), 1 - p, places=3)

    def test_stream_is_ours(self):
        # the same seed gives the same draws (raw PCG64 bits, no numpy sampler)
        a, b = L._t_unit(5, 1, 6, (3, 4)), L._t_unit(5, 1, 6, (3, 4))
        self.assertTrue(np.array_equal(a, b))
        z = L._normals(1, 0, (200_000,))
        self.assertAlmostEqual(float(z.mean()), 0, delta=0.01)
        self.assertAlmostEqual(float(z.std()), 1, delta=0.01)
        t = L._t_unit(2, 0, 6, (200_000,))
        self.assertAlmostEqual(float(t.std()), 1, delta=0.03)       # unit variance


class TestEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.eng = L.Engine(SIM)

    def test_no_calls_is_the_forecast(self):
        out = self.eng.run({}, n=8000, seed=1)
        self.assertGreater(out["ess"], 6000)
        for c in ("house", "senate", "governor"):
            self.assertAlmostEqual(out["chambers"][c]["p_control"]["D"], SIM["reference"]["deluxe"][c]["D"],
                                   delta=0.03, msg=c)

    def test_everything_called(self):
        # every race called for the D-side: control is certain, and seats add up
        calls = {r["id"]: "D" for r in SIM["races"] if not r["fixed"]}
        out = self.eng.run(calls, n=500, seed=2)
        self.assertAlmostEqual(out["chambers"]["house"]["p_control"]["D"], 1.0, places=9)
        # D-bloc seats: every D-side that is a Democrat (Alaska's D-side is an independent)
        dems = sum(1 for r in SIM["races"] if r["chamber"] == "house"
                   and ((not r["fixed"] and r["d_side"] == "D") or r["fixed"] == "D"))
        self.assertEqual(out["chambers"]["house"]["seats"]["p50"], dems)
        self.assertTrue(all(out["races"][rid] == 1.0 for rid in calls))

    def test_calls_move_the_rest(self):
        # Republicans sweeping the close House seats makes every chamber harder for Democrats
        close = [r["id"] for r in SIM["races"] if r["chamber"] == "house" and not r["fixed"]
                 and abs(r["mu"]["deluxe"]) < 4]
        base = self.eng.run({}, n=6000, seed=3)
        swept = self.eng.run({rid: "R" for rid in close}, n=6000, seed=3)
        for c in ("house", "senate", "governor"):
            self.assertLess(swept["chambers"][c]["p_control"]["D"], base["chambers"][c]["p_control"]["D"] - 0.05, c)
        self.assertGreater(swept["ess"], 300)
        # and the races still out follow: the uncalled Senate races lean further right
        out = [r["id"] for r in SIM["races"] if r["chamber"] == "senate" and not r["fixed"]]
        before = sum(base["races"][rid] for rid in out)
        after = sum(swept["races"][rid] for rid in out)
        self.assertLess(after, before - 0.5)

    def test_deterministic(self):
        calls = {"senate:ME": "R", "house:PA-07": "D"}
        a, b = self.eng.run(calls, n=3000, seed=4), self.eng.run(calls, n=3000, seed=4)
        self.assertEqual(a["chambers"], b["chambers"])


def civic_race(**kw):
    c = {"id": 1, "type": "US Senate", "election_type": "General", "country": "US", "province": "ME",
         "district": None, "percent_reporting": 40,
         "candidates": [{"name": "Troy Jackson", "party": "Democratic", "votes": 120, "winner": False},
                        {"name": "Susan Collins", "party": "Republican", "votes": 100, "winner": False},
                        {"name": "Write-in", "party": "Write-in", "votes": 5, "winner": False}]}
    c.update(kw)
    return c


RACES = {"senate:ME": {"id": "senate:ME", "state": "ME", "d_cand": "Troy Jackson", "r_cand": "Susan Collins"},
         "senate:OH-special": {"id": "senate:OH-special", "state": "OH", "d_cand": "Sherrod Brown",
                               "r_cand": "Jon Husted"},
         "house:SD-AL": {"id": "house:SD-AL", "state": "SD", "d_cand": "Nikki Gronli", "r_cand": "Marty Jackley"},
         "senate:GA": {"id": "senate:GA", "state": "GA", "d_cand": "Jon Ossoff", "r_cand": "Mike Collins"}}


class TestCivic(unittest.TestCase):
    def test_fetch_all(self):
        # both searches side by side, each paged, in a fixed order; gzip, and a patient timeout
        from unittest import mock
        from urllib.parse import parse_qs, urlparse
        seen = []

        def fake_get(u, **kw):
            q = parse_qs(urlparse(u).query)
            seen.append((kw.get("gzip"), kw.get("timeout"), kw.get("retries")))
            off = int(q["offset"][0])
            if q.get("query") == ["Governor"]:
                return json.dumps({"count": 1, "races": [{"id": "g0"}]}).encode()
            return json.dumps({"count": 3, "races": [{"id": f"f{off}"}] if off < 3 else []}).encode()

        with mock.patch.object(civic.fetch, "get", fake_get):
            races, _ = civic.fetch_all()
        self.assertEqual([r["id"] for r in races], ["f0", "f1", "f2", "g0"])
        self.assertTrue(all(g and t >= 20 and r >= 2 for g, t, r in seen))

    def test_fetch_all_is_all_or_nothing(self):
        from unittest import mock

        def fake_get(u, **kw):
            if "Governor" in u:
                raise SystemExit("download failed: (The read operation timed out)")
            return json.dumps({"count": 1, "races": [{"id": "f0"}]}).encode()

        with mock.patch.object(civic.fetch, "get", fake_get):
            with self.assertRaises(SystemExit):
                civic.fetch_all()

    def test_race_ids(self):
        ids = set(RACES)
        self.assertEqual(civic.race_id(civic_race(), ids), "senate:ME")
        self.assertEqual(civic.race_id(civic_race(province="OH"), ids), "senate:OH-special")
        self.assertEqual(civic.race_id(civic_race(type="House of Representatives", province="SD",
                                                  district="SD-AL"), ids), "house:SD-AL")
        self.assertIsNone(civic.race_id(civic_race(province="US"), ids))           # the national summary
        self.assertIsNone(civic.race_id(civic_race(type="State Senate"), ids))

    def test_counting_and_called(self):
        r = civic.result(civic_race(), RACES["senate:ME"])
        self.assertEqual((r["status"], r["votes"], r["margin"]), ("counting", {"D": 120, "R": 100, "other": 5}, 9.1))
        c = civic_race()
        c["candidates"][1]["winner"] = True
        r = civic.result(c, RACES["senate:ME"])
        self.assertEqual((r["status"], r["winner"]), ("called", "R"))
        self.assertEqual(civic.result(civic_race(candidates=[
            {"name": "Troy Jackson", "votes": 0}, {"name": "Susan Collins", "votes": 0}]), RACES["senate:ME"])["status"],
            "awaiting")

    def test_georgia_runoff(self):
        c = civic_race(province="GA", percent_reporting=100, candidates=[
            {"name": "Jon Ossoff", "votes": 495}, {"name": "Mike Collins", "votes": 490},
            {"name": "Someone Else", "votes": 20}])
        self.assertEqual(civic.result(c, RACES["senate:GA"])["status"], "runoff")

    def test_names(self):
        f = civic._find
        cands = [{"name": "Austin Scott"}, {"name": "Kelly Etsi"}]
        self.assertEqual(f(cands, "Kelly Esti"), 1)                                 # transposed
        self.assertEqual(f([{"name": "Hank Johnson"}, {"name": "James Duffie"}], "James Duffe"), 1)
        self.assertEqual(f([{"name": "Terri Yarbrough Green"}, {"name": "Rick Crawford"}], "Terri Yarbrough"), 0)
        sullivans = [{"name": "Mary Peltola"}, {"name": "Dan Sullivan"}, {"name": "Daniel J. Jr. Sullivan"}]
        self.assertEqual(f(sullivans, "Dan S. Sullivan"), 1)
        self.assertIsNone(f([{"name": "Ann Smith"}, {"name": "Bob Jones"}], "Carl Wu"))


class TestSafetyNets(unittest.TestCase):
    def test_party_fallback(self):
        # a nominee whose name no longer matches is found by party (D/R only)
        race = {"d_cand": "Kelly Nobody", "r_cand": "Austin Scott", "d_side": "D", "r_side": "R", "state": "GA"}
        c = civic_race(province="GA", candidates=[{"name": "Austin Scott", "party": "Republican", "votes": 10},
                                                 {"name": "Kelly Etsi", "party": "Democratic", "votes": 5}])
        self.assertEqual(civic.result(c, race)["matched"], {"D": True, "R": True})
        race["d_side"] = "IND"                                     # never for an independent
        self.assertFalse(civic.result(c, race)["matched"]["D"])

    def test_wikipedia_reconciles(self):
        from midterms.pipeline import livefeed as F
        out = F.reconcile({"senate:ME": {"status": "called", "winner": "R"},
                           "house:PA-07": {"status": "counting"}},
                          {"senate:ME": "D", "house:PA-07": "D"})
        self.assertEqual(out["senate:ME"]["status"], "counting")          # disputed: not used
        self.assertTrue(out["senate:ME"]["disputed"])
        self.assertEqual((out["house:PA-07"]["status"], out["house:PA-07"]["called_by"]), ("called", "wikipedia"))


class TestSeatsAndClosings(unittest.TestCase):
    """What a viewer watching the night needs beside the calls: which seats
    changed hands, and when each state's polls close."""

    def test_clerk_list(self):
        from midterms.pipeline import holders
        xml = """<MemberData publish-date="October 1, 2026"><members>
          <member><statedistrict>AK00</statedistrict><member-info><official-name>Ann Bee</official-name>
            <party>R</party></member-info></member>
          <member><statedistrict>CA03</statedistrict><member-info><official-name>Cal Dee</official-name>
            <party>I</party></member-info></member>
          <member><statedistrict>TX23</statedistrict><member-info><official-name /><party /></member-info>
            <predecessor-info><pred-official-name>Eve Eff</pred-official-name><pred-party>R</pred-party>
            <pred-footnote>Vacancy due to the resignation of Eve Eff.</pred-footnote></predecessor-info></member>
        </members></MemberData>"""
        out, published = holders.from_clerk(xml)
        self.assertEqual(published, "October 1, 2026")
        self.assertEqual(out["house:AK-AL"]["held"], "R")                   # at-large: 00 -> AL
        self.assertEqual(out["house:CA-03"]["held"], "IND")                 # the Clerk's I
        self.assertEqual((out["house:TX-23"]["held"], out["house:TX-23"]["holder"]), ("R", "Eve Eff"))

    def test_every_race_has_a_holder(self):
        from midterms.paths import FORECAST
        from midterms.pipeline import holders
        held = holders.load()
        fc = json.loads((FORECAST / "latest.json").read_text())
        self.assertEqual(sorted(set(fc["races"]) - set(held)), [])
        self.assertTrue(set(held.values()) <= {"D", "R", "IND"})

    def test_flips(self):
        from midterms.paths import FORECAST
        from midterms.pipeline import livefeed as F
        fc = json.loads((FORECAST / "latest.json").read_text())
        res = {"senate:ME": {"status": "called", "winner": "D"},           # a pickup
               "senate:GA": {"status": "called", "winner": "D"},           # a hold
               "governor:AZ": {"status": "counting", "votes": {"D": 10, "R": 9, "other": 0},
                               "pct_reporting": 3.0, "margin": 5.3}}
        doc = F.assemble(fc, "latest.json", False, F.race_rows(), res, None, None, "2026-11-04T01:30:00Z",
                         draws=2000, held={"senate:ME": "R", "senate:GA": "D", "governor:AZ": "D"})
        me, ga, az = (doc["races"][k] for k in ("senate:ME", "senate:GA", "governor:AZ"))
        self.assertEqual((me["held"], me["party"], me.get("flip")), ("R", "D", True))
        self.assertEqual((ga["held"], ga["party"], ga.get("flip")), ("D", "D", None))
        self.assertEqual((az["held"], az.get("party"), az.get("flip")), ("D", None, None))   # not called
        s = doc["chambers"]["senate"]
        self.assertEqual((s["gains"], s["losses"], s["flips"]), ({"D": 1}, {"R": 1}, ["senate:ME"]))
        self.assertEqual(doc["chambers"]["governor"]["flips"], [])
        ev = {e["race"]: e for e in doc["events"]}
        self.assertTrue(ev["senate:ME"]["flip"])
        self.assertFalse(ev["senate:GA"]["flip"])
        self.assertIn("held_note", doc)

    def test_poll_closings(self):
        from midterms.pipeline import livefeed as F
        pc = F.poll_closings()
        self.assertEqual(len(pc["states"]), 50)
        self.assertEqual(pc["states"]["IN"]["first"], "2026-11-03T23:00:00Z")   # 6 p.m. ET
        self.assertEqual(pc["states"]["NC"]["last"], "2026-11-04T00:30:00Z")    # 7:30 p.m. ET
        self.assertEqual(pc["states"]["AK"]["last"], "2026-11-04T06:00:00Z")    # 1 a.m. ET
        self.assertEqual(pc["races"]["house:FL-01"], {"first": "2026-11-04T01:00:00Z",
                                                      "last": "2026-11-04T01:00:00Z"})
        self.assertEqual(pc["races"]["house:FL-07"]["last"], "2026-11-04T00:00:00Z")   # all Eastern: 7 p.m.
        self.assertEqual(sum(k.startswith("house:FL-") for k in pc["races"]), 28)
        for st, v in pc["states"].items():
            self.assertLessEqual(v["first"], v["last"], st)
            self.assertEqual("note" in v, v["first"] != v["last"], st)


if __name__ == "__main__":
    unittest.main()
