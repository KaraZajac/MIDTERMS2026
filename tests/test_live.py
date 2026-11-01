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


if __name__ == "__main__":
    unittest.main()
