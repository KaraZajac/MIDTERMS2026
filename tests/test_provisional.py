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

    def test_a_first_round_winner_scores_by_party(self):
        # Louisiana: live.json's 'other' winner carries a party (Scalise: R)
        fc = {"headline": "deluxe", "races": {k: {"d_side": "D"} for k in ("la1", "la5", "x")},
              "versions": {"deluxe": {"races": {"la1": {"p_d_side": 0.01}, "la5": {"p_d_side": 0.02},
                                                "x": {"p_d_side": 0.5}}}}}
        contenders = {"deluxe": {"la1": 0.01, "la5": 0.02, "x": 0.5}}
        live = {"generated": "2026-11-04T21:00:00Z", "races": {
            "la1": {"status": "called", "winner": "other", "winner_name": "Steve Scalise", "party": "R"},
            "la5": {"status": "called", "winner": "other", "winner_name": "Patricia Moore", "party": "D"},
            "x": {"status": "called", "winner": "other", "winner_name": "Someone", "party": "IND"}}}
        p = S.provisional(fc, contenders, live)
        self.assertEqual(p["races"], [["la1", "R", 0.99], ["la5", "D", 0.02]])     # IND: not scored


class TestResolve(unittest.TestCase):
    """The scorecard of record: a race from its called Wikipedia results box."""

    def test_louisiana_first_round_by_party(self):
        m = {"d_cand": "Lauren Jewett", "d_side": "D", "r_cand": "Randall Arrington", "r_side": "R"}
        one = [{"candidate": "Steve Scalise", "party_code": "R", "votes": 159890},
               {"candidate": "Lauren Jewett", "party_code": "D", "votes": 89428},
               {"candidate": "Randall Arrington", "party_code": "R", "votes": 9776},
               {"candidate": "E. Glass", "party_code": "IND", "votes": 4279}]
        self.assertEqual(S.resolve("house:LA-01", m, one, "LA"),
                         {"winner_side": "R", "winner_name": "Steve Scalise", "margin": None})
        five = {"d_cand": "Dan McKay", "d_side": "D", "r_cand": "Stewart Cathey Jr.", "r_side": "R"}
        first = [{"candidate": "Patricia Moore", "party_code": "D", "votes": 40789},
                 {"candidate": "Gabe Firment", "party_code": "R", "votes": 39131},
                 {"candidate": "Dan McKay", "party_code": "D", "votes": 16047},
                 {"candidate": "Stewart Cathey Jr.", "party_code": "R", "votes": 28160}]
        self.assertIsNone(S.resolve("house:LA-05", five, first, "LA"))            # no majority: Dec 12
        runoff = [{"candidate": "Patricia Moore", "party_code": "D", "votes": 61000},
                  {"candidate": "Gabe Firment", "party_code": "R", "votes": 59000}]
        self.assertEqual(S.resolve("house:LA-05", five, runoff, "LA"),
                         {"winner_side": "D", "winner_name": "Patricia Moore", "margin": None})
        ind = [{"candidate": "Al Ind", "party_code": "IND", "votes": 100},
               {"candidate": "Lauren Jewett", "party_code": "D", "votes": 10}]
        self.assertIsNone(S.resolve("house:LA-01", m, ind, "LA"))                 # neither side's party

    def test_everywhere_else_the_two_sides(self):
        m = {"d_cand": "Troy Jackson", "d_side": "D", "r_cand": "Susan Collins", "r_side": "R"}
        c = [{"candidate": "Troy Jackson", "votes": 120}, {"candidate": "Susan Collins", "votes": 100},
             {"candidate": "Write-in", "votes": 5}]
        self.assertEqual(S.resolve("senate:ME", m, c, "ME"),
                         {"winner_side": "D", "d_votes": 120, "r_votes": 100, "margin": 9.09})
        c[2]["votes"] = 30                                              # ranked choice: no majority yet
        self.assertIsNone(S.resolve("senate:ME", m, c, "ME"))
        self.assertEqual(S.resolve("senate:NH", m, c, "NH")["winner_side"], "D")   # plurality
        self.assertIsNone(S.resolve("senate:NH", m, c[:1], "NH"))                  # one side only

    def test_maine_ranks_choices_for_congress_not_governor(self):
        m = {"d_cand": "A", "d_side": "D", "r_cand": "B", "r_side": "R"}
        c = [{"candidate": "A", "votes": 120}, {"candidate": "B", "votes": 100},
             {"candidate": "C", "votes": 30}]                         # no majority
        self.assertIsNone(S.resolve("house:ME-02", m, c, "ME"))
        self.assertIsNone(S.resolve("governor:AK", m, c, "AK"))
        self.assertEqual(S.resolve("governor:ME", m, c, "ME")["winner_side"], "D")  # plurality


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
