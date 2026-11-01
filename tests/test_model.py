"""Poll averaging and the correlated simulator."""

import unittest

from midterms.model import polls as P
from midterms.model.simulate import Chamber, Race, Shared, simulate


def poll(race, who, end, margin, **kw):
    return P.Poll(race=race, pollster=who, end=end, margin=margin, **kw)


class TestPolls(unittest.TestCase):
    def test_two_party(self):
        self.assertAlmostEqual(P.two_party(50, 45), 100 * 5 / 95)

    def test_versions_prefer_lv(self):
        ps = [poll("x", "Marist", "2026-10-25", 9.0, start="2026-10-22", population="RV"),
              poll("x", "Marist", "2026-10-25", 2.0, start="2026-10-22", population="LV")]
        (one,) = P.pick_versions(ps)
        self.assertEqual(one.population, "LV")

    def test_population_shift_measured(self):
        ps = []
        for i in range(10):
            d = f"2026-10-{10 + i:02d}"
            ps.append(poll(f"r{i}", "A", d, 1.0, start=d, population="LV"))
            ps.append(poll(f"r{i}", "A", d, 3.0, start=d, population="RV"))
        adj = P.fit_adjustments(ps, pop_prior_n=0)
        self.assertAlmostEqual(adj.population["RV"], -2.0)
        self.assertEqual(adj.population_n["RV"], 10)

    def test_house_effect_recovered(self):
        # three honest pollsters at 0, one with a +4 lean, many races
        ps = []
        for r in range(20):
            for k, who in enumerate(["A", "B", "C"]):
                ps.append(poll(f"r{r}", who, f"2026-10-{10 + k:02d}", 0.0))
            ps.append(poll(f"r{r}", "Lean", "2026-10-12", 4.0))
        adj = P.fit_adjustments(ps, house_prior_n=0)
        self.assertGreater(adj.house["lean"], 3.0)
        self.assertLess(abs(adj.house.get("a", 0.0)), 1.5)

    def test_average_recency(self):
        ps = [poll("x", "Old", "2026-08-01", -10.0, n=800),
              poll("x", "New", "2026-10-30", 4.0, n=800)]
        a = P.average(ps, "2026-10-31", P.Adjustments())
        self.assertGreater(a.margin, 3.0)          # old poll ~6 half-lives back
        self.assertEqual(a.n_polls, 2)
        self.assertGreater(a.sd, 3.0)


class TestSimulate(unittest.TestCase):
    def test_symmetric_house(self):
        races = [Race(id=f"h{i}", chamber="house", state="OH", mu=(i - 217) * 0.5, sd=5)
                 for i in range(435)]
        out = simulate(races, Shared(), {"house": Chamber("house", majority=218)},
                       n_sims=4000, seed=1)
        h = out["chambers"]["house"]
        self.assertAlmostEqual(sum(h["hist"].values()), 1.0, places=6)
        self.assertTrue(0.35 < h["p_control"]["D"] < 0.65)
        tp = sum(v["tipping"]["house"] for v in out["races"].values())
        self.assertAlmostEqual(tp, 1.0, places=6)

    def test_fixed_and_senate_tiebreak(self):
        # 35 races; D needs 17 of them for 51 (34 D-bloc seats not up).
        races = [Race(id=f"s{i}", chamber="senate", state="TX", mu=0.0, sd=0.01,
                      fixed=("D" if i < 16 else "R")) for i in range(35)]
        ch = {"senate": Chamber("senate", seats_not_up={"D": 32, "I": 2, "R": 31},
                                majority=51, tie_breaker="R", caucus={"I": "D"})}
        out = simulate(races, Shared(), ch, n_sims=500, seed=2)
        s = out["chambers"]["senate"]
        self.assertEqual(s["d_seats_p50"], 50)           # 34 + 16 = 50-50
        self.assertEqual(s["p_control"]["R"], 1.0)       # VP breaks the tie
        self.assertEqual(out["races"]["s0"]["p_d_side"], 1.0)

    def test_independent_can_leave_control_unclear(self):
        races = [Race(id=f"s{i}", chamber="senate", state="NE", mu=0, sd=0.01,
                      fixed=("D" if i < 16 else "R")) for i in range(34)]
        races.append(Race(id="osborn", chamber="senate", state="NE", fixed="I", d_side="I"))
        ch = {"senate": Chamber("senate", seats_not_up={"D": 32, "I": 2, "R": 31},
                                majority=51, tie_breaker="R", caucus={"I": "D"})}
        # with I -> D caucusing, Osborn's seat makes 51
        out = simulate(races, Shared(), ch, n_sims=200, seed=3)
        self.assertEqual(out["chambers"]["senate"]["p_control"]["D"], 1.0)
        # treated as non-caucusing, nobody has a majority (D 50, R 49, I 1)
        ch["senate"].caucus = {}
        ch["senate"].seats_not_up = {"D": 34, "R": 31}
        out = simulate(races, Shared(), ch, n_sims=200, seed=3)
        self.assertEqual(out["chambers"]["senate"]["p_control"]["unclear"], 1.0)


if __name__ == "__main__":
    unittest.main()
