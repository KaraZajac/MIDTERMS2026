"""Race-page interpretation: results boxes, infoboxes, incumbents, sides —
regression tests for every quirk found in the 2026 pages."""

import unittest

from midterms.pipeline import racepage as rp
from midterms.pipeline import races
from midterms.pipeline.htmltable import extract_tables

PAGE = """
<table class="infobox"><tr><td>
  <table><tr><th>Nominee</th><td>Amy Klobuchar<br>Ben Schierer</td><td>Lisa Demuth<br>Ryan Wilson</td></tr>
  <tr><th>Party</th><td>Democratic (DFL)</td><td>Republican</td></tr></table>
  <table><tr><td>Incumbent Governor Tim Walz Democratic (DFL)</td></tr></table>
</td></tr></table>
<div class="mw-heading mw-heading2"><h2>General election</h2></div>
<div class="mw-heading mw-heading3"><h3>Polling</h3></div>
<table class="wikitable">
<tr><th>Poll source</th><th>Date(s) administered</th><th>Sample size</th><th>Margin of error</th>
<th>Kurt Alme (R)</th><th>Alani Bankhead (D)</th><th>Seth Bodnar (I)</th><th>Undecided</th></tr>
<tr><td>Poll A</td><td>October 20–23, 2026</td><td>600 (LV)</td><td>± 4%</td><td>44%</td><td>12%</td><td>36%</td><td>8%</td></tr>
<tr><td>Poll B</td><td>October 10–12, 2026</td><td>500 (LV)</td><td>± 4%</td><td>45%</td><td>10%</td><td>35%</td><td>10%</td></tr>
</table>
<div class="hidden-begin mw-collapsible mw-collapsed"><div class="hidden-title">Hypothetical polling</div>
<div class="hidden-content">
<table class="wikitable">
<tr><th>Poll source</th><th>Date(s) administered</th><th>Sample size</th><th>Margin of error</th>
<th>Kurt Alme (R)</th><th>Seth Bodnar (I)</th><th>Undecided</th></tr>
<tr><td>Poll C</td><td>October 1, 2026</td><td>500 (LV)</td><td>± 4%</td><td>50%</td><td>45%</td><td>5%</td></tr>
</table></div></div>
<div class="mw-heading mw-heading3"><h3>Results</h3></div>
<table class="wikitable"><caption>2026 election</caption>
<tr><th>Party</th><th>Party</th><th>Candidate</th><th>Votes</th><th>%</th></tr>
<tr><td></td><td>Republican</td><td>Kurt Alme</td><td>210,000</td><td>48</td></tr>
<tr><td></td><td>Independent</td><td>Seth Bodnar</td><td>190,000</td><td>43</td></tr>
<tr><td></td><td>Democratic</td><td>Alani Bankhead</td><td>30,000</td><td>7</td></tr>
<tr><td></td><td>Working Families</td><td>Alani Bankhead</td><td>2,000</td><td>0.5</td></tr>
<tr><td></td><td>Inactive ballots</td><td>Inactive ballots</td><td>900</td><td></td></tr>
<tr><td colspan="3">Total votes</td><td>432,900</td><td>100</td></tr>
</table>
"""


class TestRacePage(unittest.TestCase):
    def setUp(self):
        self.tables = extract_tables(PAGE)
        self.gen = rp.general(self.tables)

    def test_results_box_fusion_and_noise(self):
        box = rp.results_box(self.gen)
        names = [c["candidate"] for c in box]
        self.assertEqual(names, ["Kurt Alme", "Seth Bodnar", "Alani Bankhead"])
        bank = box[2]
        self.assertEqual(bank["votes"], 32_000)          # D + WF lines merged
        self.assertEqual(bank["fusion"], ["WF"])
        self.assertEqual(box[1]["party_code"], "IND")

    def test_infobox_first_line_and_dfl_incumbent(self):
        noms = rp.infobox_nominees(rp.lead_tables(self.tables, ""))
        self.assertEqual([n["candidate"] for n in noms], ["Amy Klobuchar", "Lisa Demuth"])
        self.assertEqual(noms[0]["party_code"], "D")
        inc = rp.incumbent(self.tables)
        self.assertEqual(inc, {"name": "Tim Walz", "names": ["Tim Walz"], "party_code": "D"})

    def test_two_incumbents_and_new_seats(self):
        two = ("<table><tr><td>Incumbent U.S. Representative<br>Al Green<br>Christian Menefee"
               "<br>Democratic</td></tr></table>")
        inc = rp.incumbent(extract_tables(two))
        self.assertEqual(inc["names"], ["Al Green", "Christian Menefee"])
        self.assertEqual(inc["party_code"], "D")
        inline = ("<table><tr><td>Incumbent U.S. Representative<br>Greg Casar (Democratic)"
                  "<br>Lloyd Doggett (Democratic)</td></tr></table>")
        self.assertEqual(rp.incumbent(extract_tables(inline))["names"], ["Greg Casar", "Lloyd Doggett"])
        new = "<table><tr><td>Incumbent U.S. Representative<br>None<br>(New seat)</td></tr></table>"
        self.assertIsNone(rp.incumbent(extract_tables(new))["name"])

    def test_hypothetical_block_excluded(self):
        polls = [t for t in self.gen if rp.is_polling(t)]
        self.assertEqual(len(polls), 2)
        self.assertEqual(polls[1].hidden, "Hypothetical polling")
        picked = rp.poll_tables(self.gen, "Seth Bodnar", "Kurt Alme")
        self.assertEqual(len(picked), 1)
        self.assertFalse(picked[0].hidden)

    def test_sides_by_poll_share(self):
        box = rp.results_box(self.gen)
        shares = rp.main_poll_shares(self.gen, box)
        d, r, others = races.sides(box, shares)
        self.assertEqual((d["candidate"], r["candidate"]), ("Seth Bodnar", "Kurt Alme"))
        self.assertEqual([o["candidate"] for o in others], ["Alani Bankhead"])

    def test_best_label_prefers_exact(self):
        labels = ["Dan S. Sullivan (R)", "Mary Peltola (D)", "Dan J. Sullivan (R)"]
        self.assertEqual(rp.best_label(labels, "Dan J. Sullivan"), "Dan J. Sullivan (R)")
        self.assertEqual(rp.best_label(labels, "Dan S. Sullivan"), "Dan S. Sullivan (R)")


class TestClassify(unittest.TestCase):
    def c(self, name, party, inc=False):
        return {"candidate": name, "party_code": party, "incumbent": inc, "party": party}

    def test_same_party_top_two_is_fixed(self):
        out = races.classify([self.c("A", "D"), self.c("B", "D")], [], 0)
        self.assertEqual(out["fixed"], "D")

    def test_unopposed_is_fixed(self):
        self.assertEqual(races.classify([self.c("A", "R")], [], 0)["fixed"], "R")

    def test_minor_opponent_safe_unpolled_is_fixed(self):
        preds = [{"source": s, "rating": "Solid D"} for s in
                 ("The Cook Political Report", "Inside Elections", "Sabato's Crystal Ball")]
        out = races.classify([self.c("A", "D"), self.c("B", "IND")], preds, 0)
        self.assertEqual(out["fixed"], "D")
        # ...but not if anyone polled it
        self.assertEqual(races.classify([self.c("A", "D"), self.c("B", "IND")], preds, 3)["fixed"], "")


class TestSiteOthers(unittest.TestCase):
    def test_everyone_but_the_forecasts_two(self):
        # Wikipedia's results box put CA-34's leader first after Election Day,
        # so the race table's D-side became the forecast's 'other' (Nov 4)
        from midterms.pipeline.site_export import others
        m = {"d_cand": "Jimmy Gomez", "r_cand": ""}
        row = {"d_cand": "Angela Gonzales-Torres", "d_side": "D", "r_cand": "", "r_side": "R",
               "others": "Jimmy Gomez (D)"}
        self.assertEqual(others(m, row), ["Angela Gonzales-Torres (D)"])
        # before the reorder (and everywhere else): the table's own others
        row = {"d_cand": "Jimmy Gomez", "d_side": "D", "r_cand": "", "others": "Angela Gonzales-Torres (D)"}
        self.assertEqual(others(m, row), ["Angela Gonzales-Torres (D)"])
        la = {"d_cand": "Lauren Jewett", "r_cand": "Randall Arrington"}
        row = {"d_cand": "Lauren Jewett", "d_side": "D", "r_cand": "Randall Arrington", "r_side": "R",
               "others": "Steve Scalise (R); E. Glass (IND)"}
        self.assertEqual(others(la, row), ["Steve Scalise (R)", "E. Glass (IND)"])


if __name__ == "__main__":
    unittest.main()


class TestCalled(unittest.TestCase):
    BOX = """<div class="mw-heading mw-heading2"><h2>General election</h2></div>
    <div class="mw-heading mw-heading3"><h3>Results</h3></div>
    <table class="wikitable"><tr><th>Party</th><th>Party</th><th>Candidate</th><th>Votes</th><th>%</th></tr>
    <tr><td></td><td>Democratic</td><td>A</td><td>1,000</td><td>51</td></tr>
    <tr><td></td><td>Republican</td><td>B</td><td>960</td><td>49</td></tr>
    {tail}</table>"""

    def test_partial_count_is_not_called(self):
        gen = rp.general(extract_tables(self.BOX.format(tail="")))
        self.assertFalse(rp.results_called(gen))

    def test_hold_or_gain_line_calls_it(self):
        for line in ("Democratic hold", "Democratic gain from Republican"):
            html = self.BOX.format(tail=f"<tr><td colspan='5'>{line}</td></tr>")
            self.assertTrue(rp.results_called(rp.general(extract_tables(html))), line)

    def test_majority_rule_races(self):
        from midterms.journal.score import needs_majority
        self.assertTrue(needs_majority("senate:GA", "GA"))
        self.assertTrue(needs_majority("house:LA-02", "LA"))
        self.assertTrue(needs_majority("senate:ME", "ME"))
        self.assertFalse(needs_majority("house:GA-02", "GA"))
        self.assertFalse(needs_majority("senate:TX", "TX"))
