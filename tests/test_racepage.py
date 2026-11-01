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
        self.assertEqual(inc, {"name": "Tim Walz", "party_code": "D"})

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


if __name__ == "__main__":
    unittest.main()
