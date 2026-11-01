"""The VoteHub supplement: race mapping, side matching, de-duplication."""

import csv
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from midterms.pipeline import votehub as vh

RACES = {
    "senate:MI": {"id": "senate:MI", "d_cand": "Mallory McMorrow", "r_cand": "Mike Rogers", "fixed": ""},
    "senate:OH-special": {"id": "senate:OH-special", "d_cand": "Sherrod Brown", "r_cand": "Jon Husted",
                          "fixed": ""},
    "senate:AK": {"id": "senate:AK", "d_cand": "Mary Peltola", "r_cand": "Dan S. Sullivan", "fixed": ""},
    "governor:OH": {"id": "governor:OH", "d_cand": "Amy Acton", "r_cand": "Vivek Ramaswamy", "fixed": ""},
    "house:AK-AL": {"id": "house:AK-AL", "d_cand": "Bill Hill", "r_cand": "Nick Begich III", "fixed": ""},
    "house:PA-10": {"id": "house:PA-10", "d_cand": "Janelle Stelson", "r_cand": "Scott Perry", "fixed": ""},
    "house:AL-07": {"id": "house:AL-07", "d_cand": "Terri Sewell", "r_cand": "", "fixed": "D"},
}


def poll(**kw):
    p = {"id": "x1", "poll_type": "us-senator", "subject": "2026 Michigan", "seat_name": None,
         "pollster": "Glengariff Group", "sponsors": [], "partisan": None, "population": "lv",
         "sample_size": 600, "start_date": "2026-10-19", "end_date": "2026-10-22",
         "url": "https://example.org/poll",
         "answers": [{"choice": "Mallory McMorrow", "pct": 51.0}, {"choice": "Mike Rogers", "pct": 45.0},
                     {"choice": "Undecided", "pct": 4.0}]}
    p.update(kw)
    return p


def wiki(**kw):
    w = {"race": "senate:MI", "pollster": "Glengariff Group", "end": "2026-10-22", "n": "600",
         "d": "51.0", "r": "45.0", "source": "wikipedia:2026 United States Senate election in Michigan@1"}
    w.update(kw)
    return w


class TestRaceId(unittest.TestCase):
    def test_mapping(self):
        ids = set(RACES)
        cases = [
            (dict(poll_type="us-senator", subject="2026 Michigan"), "senate:MI"),
            (dict(poll_type="us-senator", subject="2026 Ohio"), "senate:OH-special"),
            (dict(poll_type="governor", subject="2026 Ohio"), "governor:OH"),
            (dict(poll_type="us-representative", subject="2026 PA-10", seat_name=None), "house:PA-10"),
            (dict(poll_type="us-representative", subject="2026 AK-01", seat_name="AK-01"), "house:AK-AL"),
            (dict(poll_type="us-senator", subject="2026 Texas Republican"), None),   # a primary
            (dict(poll_type="governor", subject="2025 Virginia"), None),             # another year
            (dict(poll_type="approval", subject="Donald Trump"), None),
            (dict(poll_type="us-senator", subject="2026 Iowa"), None),               # not in the race set
        ]
        for p, want in cases:
            self.assertEqual(vh.race_id(p, ids), want, p)


class TestCandidateRows(unittest.TestCase):
    def test_row(self):
        (r,) = vh.candidate_rows([poll(partisan="DEM", population="rv", sponsors=["Detroit News"])],
                                 RACES, until="2026-11-01")
        self.assertEqual((r["race"], r["d"], r["r"]), ("senate:MI", 51.0, 45.0))
        self.assertEqual((r["partisan"], r["population"], r["n"]), ("D", "RV", 600))
        self.assertEqual((r["undecided"], r["other"]), (4.0, ""))
        self.assertEqual(r["source"], "votehub:x1")
        self.assertEqual(r["_sponsors"], ["Detroit News"])

    def test_skips(self):
        rows = vh.candidate_rows([
            poll(answers=[{"choice": "Mallory McMorrow", "pct": 50.0},
                          {"choice": "Bill Huizenga", "pct": 44.0}]),        # not the nominee
            poll(end_date="2026-11-05"),                                      # after the build date
            poll(poll_type="us-representative", subject="2026 AL-07"),       # uncontested
        ], RACES, until="2026-11-01")
        self.assertEqual(rows, [])

    def test_two_sullivans(self):
        ans = [{"choice": "Mary Peltola", "pct": 48.0}, {"choice": "Dan Sullivan", "pct": 46.0},
               {"choice": "Daniel Sullivan Jr.", "pct": 2.0}]
        (r,) = vh.candidate_rows([poll(subject="2026 Alaska", answers=ans)], RACES, until="2026-11-01")
        self.assertEqual((r["d"], r["r"], r["other"]), (48.0, 46.0, 2.0))

    def test_final_round_kept(self):
        first = [{"choice": "Bill Hill", "pct": 41.0}, {"choice": "Nick Begich", "pct": 44.0},
                 {"choice": "Eric Hafner", "pct": 9.0}]
        final = [{"choice": "Bill Hill", "pct": 49.0}, {"choice": "Nick Begich", "pct": 51.0}]
        kw = dict(poll_type="us-representative", subject="2026 AK-01", seat_name="AK-01")
        (r,) = vh.candidate_rows([poll(id="a", answers=first, **kw), poll(id="b", answers=final, **kw)],
                                 RACES, until="2026-11-01")
        self.assertEqual((r["d"], r["r"], r["source"]), (49.0, 51.0, "votehub:b"))


class TestDuplicates(unittest.TestCase):
    def v(self, **kw):
        (r,) = vh.candidate_rows([poll(**kw)], RACES, until="2026-11-01")
        return r

    def test_same_poll_under_another_name(self):
        self.assertTrue(vh.is_duplicate(self.v(pollster="CNN/SSRS"), wiki(pollster="SSRS", n="768")))
        self.assertTrue(vh.is_duplicate(self.v(pollster="Beacon Research/Shaw & Company Research",
                                               sponsors=["Fox News"], sample_size=1001),
                                        wiki(pollster="Fox News", n="", d="49", r="47")))
        self.assertTrue(vh.is_duplicate(self.v(pollster="Public Policy Polling"),
                                        wiki(pollster="Public Policy Polling", end="2026-10-27")))

    def test_same_numbers(self):
        # different names, same sample size or same topline, days apart
        self.assertTrue(vh.is_duplicate(self.v(pollster="Mitchell"),
                                        wiki(pollster="MRG", end="2026-10-25", d="48", r="44")))
        self.assertTrue(vh.is_duplicate(self.v(pollster="Mitchell", sample_size=636),
                                        wiki(pollster="MRG", end="2026-10-20", n="", d="51.4", r="45.2")))

    def test_distinct_polls(self):
        self.assertFalse(vh.is_duplicate(self.v(pollster="EPIC-MRA", sample_size=400),
                                         wiki(pollster="Glengariff Group", end="2026-10-20", d="49", r="45")))
        # the same pollster a fortnight later is a new poll
        self.assertFalse(vh.is_duplicate(self.v(end_date="2026-10-22"),
                                         wiki(end="2026-10-08", n="500", d="48", r="46")))

    def test_supplement(self):
        other = [{"choice": "Mallory McMorrow", "pct": 49.0}, {"choice": "Mike Rogers", "pct": 46.0}]
        cands = [self.v(id="new", pollster="EPIC-MRA", sample_size=400, answers=other), self.v(id="dup")]
        added, dupes = vh.supplement(cands, [wiki(), wiki(race="senate:ME")])
        self.assertEqual(([r["source"] for r in added], dupes), (["votehub:new"], 1))


class TestFabricators(unittest.TestCase):
    def test_match(self):
        from midterms.pipeline import excluded
        self.assertEqual(excluded.match("Wedgewood Polls")["name"], "Wedgewood Polls")
        self.assertEqual(excluded.match("WEDGEWOOD")["name"], "Wedgewood Polls")
        self.assertIsNotNone(excluded.match("Median Strategies (R)"))
        self.assertIsNone(excluded.match("Marist University"))
        self.assertIsNone(excluded.match("SoCal Strategies"))      # disputed, not excluded

    def test_votehub_drops_them(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "polls.json"
            other = [{"choice": "Mallory McMorrow", "pct": 49.0}, {"choice": "Mike Rogers", "pct": 46.0}]
            path.write_text(__import__("json").dumps(
                [poll(id="fake", pollster="Wedgewood Polls"),
                 poll(id="real", pollster="EPIC-MRA", sample_size=400, answers=other)]))
            with mock.patch.object(vh, "PATH", path):
                added, info = vh.build_rows(RACES, [], Path(tmp) / "none.csv", until="2026-11-01")
        self.assertEqual([r["source"] for r in added], ["votehub:real"])
        self.assertEqual(info["excluded_fabricated"], 1)


class TestCarryOver(unittest.TestCase):
    def test_outage_keeps_committed_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            committed = Path(tmp) / "races.csv"
            cols = ["race", "pollster", "partisan", "start", "end", "n", "population", "d", "r",
                    "source"]
            with open(committed, "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=cols)
                w.writeheader()
                w.writerow({"race": "senate:MI", "pollster": "EPIC-MRA", "end": "2026-10-20", "n": "400",
                            "d": "49", "r": "44", "source": "votehub:old"})
                w.writerow(wiki(n="600") | {"start": "", "partisan": "", "population": "LV"})
            with mock.patch.object(vh, "PATH", Path(tmp) / "missing.json"):
                added, info = vh.build_rows(RACES, [wiki()], committed, until="2026-11-01")
        self.assertEqual([r["source"] for r in added], ["votehub:old"])
        self.assertTrue(info["basis"].startswith("carried over"))


if __name__ == "__main__":
    unittest.main()
