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


if __name__ == "__main__":
    unittest.main()
