"""County results for the statewide races (midterms/pipeline/counties.py)."""

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from midterms.pipeline import civic, counties


def row(st, d, r):
    return {"state": st, "d_cand": d, "r_cand": r, "d_side": "D", "r_side": "R"}


def cand(name, party, votes):
    return {"name": name, "party": party, "votes": votes, "winner": False}


def county(fips, name, pct, d, r, other=0):
    c = [cand("Jon Ossoff", "Democratic", d), cand("Mike Collins", "Republican", r)]
    if other:
        c.append(cand("Write-in", "Independent", other))
    return {"name": name, "type": "County", "fips": fips, "percent_reporting": pct, "candidates": c}


def search_race(cid, typ, st, votes, district=None):
    return {"id": cid, "type": typ, "country": "US", "province": st, "district": district,
            "candidates": [cand("A", "Democratic", votes), cand("B", "Republican", 0)]}


class TestCounties(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir)
        self.out = self.dir / "counties"

    def test_regions(self):
        # counties by FIPS; towns (longer FIPS) added into their county; no FIPS, dropped
        race = row("GA", "Jon Ossoff", "Mike Collins")
        c = {"region_results": {
            "appling": county("13001", "Appling", 40.0, 1000, 3000),
            "fulton": county("13121", "Fulton", 63.0, 300000, 100000, 5000),
            "t1": county("2300160300", "Town A", 100.0, 10, 30),
            "t2": county("2300174790", "Town B", 50.0, 50, 10),
            "district": county(None, "District 1", 10.0, 5, 5),
            "state": county("13", "Georgia", 50.0, 1, 1)}}
        regs, dropped = counties.regions(c, race)
        self.assertEqual(sorted(dropped), ["District 1", "Georgia"])
        by = {g["fips"]: g for g in regs}
        self.assertEqual(sorted(by), ["13001", "13121", "23001"])
        self.assertEqual(by["13121"], {"fips": "13121", "name": "Fulton", "pct_reporting": 63.0,
                                       "votes": {"D": 300000, "R": 100000, "other": 5000}, "margin": 50.0})
        self.assertEqual(by["13001"]["margin"], -50.0)
        town = by["23001"]
        self.assertEqual((town["name"], town["pct_reporting"], town["votes"]),
                         (None, None, {"D": 60, "R": 40, "other": 0}))
        self.assertEqual(town["margin"], 20.0)
        # Virginia's independent cities come without FIPS: found by name
        va = row("VA", "Jon Ossoff", "Mike Collins")
        vc = {"region_results": {
            "rc": county(None, "Richmond City", 80.0, 70, 30),
            "rco": county("51159", "Richmond", 90.0, 10, 30),          # the county, with its FIPS
            "nf": county(None, "City of Norfolk", 50.0, 60, 40),
            "vb": county("", "Virginia Beach", 40.0, 45, 55),
            "x": county(None, "Richmond County", 10.0, 1, 1),         # never the city
            "y": county(None, "Nowhere City", 10.0, 1, 1)}}
        regs, dropped = counties.regions(vc, va)
        self.assertEqual(sorted(g["fips"] for g in regs), ["51159", "51710", "51760", "51810"])
        self.assertEqual(sorted(dropped), ["Nowhere City", "Richmond County"])
        self.assertEqual({g["fips"]: g["name"] for g in regs}["51760"], "Richmond City")
        self.assertEqual(counties.city_fips("NV", "Carson City"), "32510")
        self.assertEqual(counties.city_fips("MD", "Baltimore City"), "24510")
        self.assertIsNone(counties.city_fips("MD", "Baltimore County"))
        # a side that doesn't match: no margin
        odd = {"region_results": {"x": {"fips": "13001", "percent_reporting": 5,
                                        "candidates": [cand("Somebody Else", "Libertarian", 9)]}}}
        self.assertIsNone(counties.regions(odd, race)[0][0]["margin"])

    def _keep(self, races):
        civic._keep(self.dir, "federal", civic.fetch.now_utc(), races)

    def test_run_writes_one_file_per_statewide_race_with_votes(self):
        rows = {"senate:GA": row("GA", "Jon Ossoff", "Mike Collins"),
                "senate:NE": row("NE", "Dan Osborn", "Pete Ricketts"),
                "house:GA-07": row("GA", "X", "Y")}
        self._keep([search_race(87087, "US Senate", "GA", 500),
                    search_race(87254, "US Senate", "NE", 0),           # no votes yet: not fetched
                    search_race(87079, "House of Representatives", "GA", 900, "GA-07")])
        asked = []

        total = [cand("Jon Ossoff", "Democratic", 300), cand("Mike Collins", "Republican", 100)]

        def fake_get(u, **kw):
            asked.append(u)
            return json.dumps({"id": 87087, "candidates": total, "region_results": {
                "fulton": county("13121", "Fulton", 63.0, 300, 100)}}).encode()

        with mock.patch.object(counties.fetch, "get", fake_get):
            got = counties.run(self.dir, self.out, rows=rows)
        self.assertEqual(got, {"written": 1, "failed": 0, "skipped": 0})
        self.assertEqual(asked, ["https://civicapi.org/api/v2/race/87087"])
        doc = json.loads((self.out / "senate" / "ga.json").read_text())
        self.assertEqual((doc["race"], doc["civic_id"], doc["dropped"]), ("senate:GA", 87087, 0))
        self.assertEqual((doc["total"], doc["coverage"]), (400, 1.0))
        self.assertEqual(doc["regions"][0]["margin"], 50.0)
        self.assertNotIn("note", doc)
        self.assertEqual(doc["source"]["credit"], civic.ATTRIBUTION)
        # counties that fall short of the race's total (towns without FIPS): no map
        total[0]["votes"] = 3000
        with mock.patch.object(counties.fetch, "get", fake_get):
            counties.run(self.dir, self.out, rows=rows)
        doc = json.loads((self.out / "senate" / "ga.json").read_text())
        self.assertEqual((doc["regions"], doc["coverage"]), ([], 0.129))
        self.assertIn("don't add up", doc["note"])
        self.assertEqual(counties.path_for(self.out, "senate:OH-special"),
                         self.out / "senate" / "oh-special.json")

    def test_failures_keep_the_last_file_and_end_the_cycle(self):
        sts = ["AL", "CO", "GA", "IA", "KS"]
        rows = {f"senate:{s}": row(s, "A", "B") for s in sts}
        self._keep([search_race(100 + i, "US Senate", s, 10) for i, s in enumerate(sts)])
        old = self.out / "senate" / "ga.json"
        old.parent.mkdir(parents=True)
        old.write_text('{"kept": true}')
        asked = []

        def down(u, **kw):
            asked.append(u)
            raise civic.fetch.DownloadFailed("download failed: … (HTTP 502)", 502)

        with mock.patch.object(counties.fetch, "get", down), mock.patch.object(counties, "WORKERS", 1):
            got = counties.run(self.dir, self.out, rows=rows)
        self.assertEqual(got, {"written": 0, "failed": counties.TRIP, "skipped": len(sts) - counties.TRIP})
        self.assertEqual(len(asked), counties.TRIP)
        self.assertEqual(old.read_text(), '{"kept": true}')

    def test_races_without_a_map_go_first_closest_first_then_the_oldest(self):
        sts = ["AL", "CO", "GA", "IA", "KS", "OK"]
        rows = {f"senate:{s}": row(s, "A", "B") for s in sts}
        self._keep([search_race(100 + i, "US Senate", s, 10) for i, s in enumerate(sts)])
        (self.dir / "live.json").write_text(json.dumps({"races": {
            "senate:AL": {"p_pre": 0.01}, "senate:CO": {"p_pre": 0.9}, "senate:GA": {"p_pre": 0.6},
            "senate:IA": {"p_pre": 0.52}, "senate:KS": {"p_pre": 0.03}, "senate:OK": {"p_pre": 0.02}}}))
        mapped = '{"regions": [{"fips": "01001"}]}'
        for s, body, t in (("al", mapped, 2000), ("ok", mapped, 1000),   # maps: OK's older than AL's
                           ("ks", '{"regions": []}', 3000)):             # empty, from before dropped_names
            p = self.out / "senate" / f"{s}.json"
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(body)
            os.utime(p, (t, t))
        asked = []

        def fake_get(u, **kw):
            asked.append(int(u.rsplit("/", 1)[1]))
            return json.dumps({"region_results": {}}).encode()

        with mock.patch.object(counties.fetch, "get", fake_get), mock.patch.object(counties, "WORKERS", 1):
            counties.run(self.dir, self.out, rows=rows)
        # no map yet, closest first: IA (0.52), GA (0.6), CO (0.9), KS (0.03); then OK, then AL
        self.assertEqual(asked, [103, 102, 101, 104, 105, 100])

    def test_a_cycle_asks_nothing_while_civicapi_is_down(self):
        import datetime as dt
        rows = {"senate:GA": row("GA", "A", "B")}
        self._keep([search_race(87087, "US Senate", "GA", 10)])
        old = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
        (self.dir / "live.json").write_text(json.dumps({"generated": old, "races": {}}))
        with mock.patch.object(counties.fetch, "get", side_effect=AssertionError("no request")):
            got = counties.run(self.dir, self.out, rows=rows)
        self.assertEqual(got, {"written": 0, "failed": 0, "skipped": 1})

    def test_no_kept_answers_no_requests(self):
        with mock.patch.object(counties.fetch, "get", side_effect=AssertionError("no request")):
            got = counties.run(self.dir, self.out, rows={"senate:GA": row("GA", "A", "B")})
        self.assertEqual(got, {"written": 0, "failed": 0, "skipped": 0})


if __name__ == "__main__":
    unittest.main()
