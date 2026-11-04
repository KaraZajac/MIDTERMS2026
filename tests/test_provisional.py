"""The provisional scoreboard on the races called so far (journal/score.py)."""

import unittest

from midterms.journal import score as S


class TestProvisional(unittest.TestCase):
    def test_scored_on_the_calls(self):
        fc = {"headline": "deluxe",
              "versions": {"deluxe": {"races": {"a": {"p_d_side": 0.8}, "b": {"p_d_side": 0.3},
                                                "c": {"p_d_side": 0.6}, "d": {"p_d_side": 0.9}}}}}
        contenders = {"deluxe": {"a": 0.8, "b": 0.3, "c": 0.6, "d": 0.9},
                      "coin-flip": {"a": 0.5, "b": 0.5, "c": 0.5, "d": 0.5},
                      "ratings": {"a": 0.9, "b": 0.2}}           # prices a and b only
        live = {"generated": "2026-11-04T04:00:00Z", "races": {
            "a": {"status": "called", "winner": "D"},
            "b": {"status": "called", "winner": "D"},              # an upset
            "c": {"status": "counting"},
            "d": {"status": "called", "winner": "other"},          # neither side: not scored
            "e": {"status": "called", "winner": "R"}}}             # no forecast: not scored
        p = S.provisional(fc, contenders, live)
        self.assertEqual((p["asof"], p["called"]), ("2026-11-04T04:00:00Z", 2))
        self.assertEqual(p["races"], [["a", "D", 0.8], ["b", "D", 0.3]])
        self.assertEqual(p["scoreboard"]["deluxe"], {"n": 2, "brier": 0.265, "log_loss": 0.7136,
                                                     "calls": "1/2"})
        self.assertEqual(p["scoreboard"]["coin-flip"]["brier"], 0.25)
        self.assertIsNone(S.provisional(fc, contenders, None))


def rating(race, rater, label, scale, asof):
    return {"race": race, "rater": rater, "source": rater, "rating": label, "scale": str(scale),
            "asof": asof}


class TestOthers(unittest.TestCase):
    def test_final_ratings_are_the_last_before_election_day(self):
        seal = "2026-11-03T09:10:29Z"
        versions = [
            (seal, [rating("a", "Cook", "Lean R", -1.0, "2026-10-27"),
                    rating("a", "Sabato", "Tossup", 0.0, "2026-10-27"),
                    rating("b", "RCP", "Lean I", 1.0, "2026-11-02"),
                    rating("c", "DDHQ", "Lean D", 1.0, "2026-11-03")]),       # pulled before polls opened
            ("2026-11-03T23:00:00Z", [
                rating("a", "Sabato", "Lean D", 1.0, "2026-11-02"),           # a final update: taken
                rating("b", "RCP", "Tossup", 0.0, "2026-11-02"),              # same date, changed: left out
                rating("c", "DDHQ", "Likely D", 2.0, "2026-11-03"),           # dated Election Day: left out
                rating("d", "Cook", "Lean R", -1.0, "2026-11-01"),            # new, dated before: taken
                rating("e", "Cook", "Lean R", -1.0, "2026-11-03")]),          # new, Election Day: left out
            ("2026-11-04T10:00:00Z", [rating("a", "Sabato", "Lean D", 1.0, "2026-11-02")])]
        got = {(r["race"], r["rater"]): (r["rating"], r["seen"]) for r in S.final_ratings(versions)}
        self.assertEqual(got, {("a", "Cook"): ("Lean R", seal),
                               ("a", "Sabato"): ("Lean D", "2026-11-03T23:00:00Z"),
                               ("b", "RCP"): ("Lean I", seal),
                               ("c", "DDHQ"): ("Lean D", seal),
                               ("d", "Cook"): ("Lean R", "2026-11-03T23:00:00Z")})

    def test_each_forecaster_against_ours_on_its_races(self):
        import csv
        import tempfile
        from pathlib import Path
        fc = {"headline": "deluxe",
              "params": {"national": {"sd": 3.0}, "shared": {"sd_region": 2.0, "sd_state": 2.0},
                         "ratings": {"sd": 5.5, "k": 1.25}},
              "races": {"x": {}, "y": {}, "z": {}},
              "versions": {"deluxe": {"races": {"x": {"p_d_side": 0.7}, "y": {"p_d_side": 0.4},
                                                "z": {"p_d_side": 0.02}}}}}
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "ratings_final.csv"
            with open(path, "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["race", "rater", "source", "rating", "scale", "asof", "seen"])
                w.writeheader()
                for r in (rating("x", "Cook", "Lean D", 1.0, "2026-11-01"),
                          rating("y", "Cook", "Toss-up", 0.0, "2026-11-01"),
                          rating("z", "Cook", "Solid R", -3.0, "2026-11-01"),
                          rating("x", "Sabato", "Likely D", 2.0, "2026-11-02"),
                          rating("w", "Cook", "Lean D", 1.0, "2026-11-01")):     # a race the model doesn't price
                    w.writerow({**r, "source": {"Cook": "The Cook Political Report"}.get(r["rater"], r["rater"]),
                                "seen": "2026-11-03T09:10:29Z"})
            probs, names, competitive = raters = S.rater_probs(fc, path)
            self.assertIsNone(S.others(fc, {}, ({}, {}, set())))
        self.assertEqual(probs["Cook"]["y"], 0.5)                     # a Toss-up picks no side
        self.assertTrue(0.75 < probs["Cook"]["x"] < probs["Sabato"]["x"] < 0.99)
        self.assertLess(probs["Cook"]["z"], 0.001)
        self.assertNotIn("w", probs["Cook"])
        self.assertEqual(names["Cook"], "The Cook Political Report")
        self.assertEqual(competitive, {"x", "y"})                     # not Safe/Solid by Cook or Sabato
        res = {"x": {"winner_side": "D"}, "y": {"winner_side": "R"}, "z": {"winner_side": "R"}}
        o = S.others(fc, res, raters)
        self.assertEqual([r["name"] for r in o["raters"]], ["Cook", "Sabato"])    # most races first
        cook = o["raters"][0]
        self.assertEqual((cook["n"], cook["theirs"]["calls"], cook["theirs"]["tossups"]), (3, "2/2", 1))
        self.assertEqual(cook["ours"], S.score({"x": 0.7, "y": 0.4, "z": 0.02}, res))
        self.assertEqual(cook["ours"]["calls"], "3/3")
        self.assertEqual((cook["competitive"]["n"], cook["competitive"]["ours"]["calls"]), (2, "2/2"))
        self.assertEqual(o["versus"], "deluxe")
        # the provisional scoreboard carries the same comparison on the calls
        live = {"generated": "2026-11-04T04:00:00Z", "races": {
            "x": {"status": "called", "winner": "D"}, "y": {"status": "counting"}}}
        contenders = {"deluxe": {"x": 0.7, "y": 0.4, "z": 0.02}}
        p = S.provisional(fc, contenders, live, raters)
        self.assertEqual([(r["name"], r["n"]) for r in p["others"]["raters"]], [("Cook", 1), ("Sabato", 1)])
        self.assertNotIn("others", S.provisional(fc, contenders, live))


if __name__ == "__main__":
    unittest.main()
