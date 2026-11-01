"""HTML table extraction and Wikipedia poll-table interpretation."""

import unittest

from midterms.model import ratings
from midterms.pipeline import wikipolls as wp
from midterms.pipeline.htmltable import extract_tables, wikitables

POLL_HTML = """
<div class="mw-heading mw-heading2"><h2 id="General_election">General election</h2></div>
<div class="mw-heading mw-heading3"><h3 id="Polling">Polling</h3></div>
<table class="wikitable sortable">
<tbody><tr>
<th>Poll source</th><th>Date(s)<br>administered</th>
<th>Sample<br>size<sup class="reference"><a href="#n">[b]</a></sup></th>
<th>Margin<br>of error</th>
<th>Susan<br>Collins (R)</th><th>Troy<br>Jackson (D)</th>
<th>Other</th><th>Undecided</th></tr>
<tr><td colspan="8">Platner suspends his campaign</td></tr>
<tr><td rowspan="2">Marist University</td><td rowspan="2">October 22–25, 2026</td>
<td>1,240 (LV)</td><td>± 3.5%</td><td>47%</td><td><b>49%</b></td><td>1%</td><td>3%</td></tr>
<tr><td>1,449 (RV)</td><td>± 3.2%</td><td>44%</td><td><b>53%</b></td><td>&lt;1%</td><td>2%</td></tr>
<tr><td>Data for Progress (D)<sup class="reference">[A]</sup></td>
<td>Sep 29 – Oct 2, 2026</td><td>652 (LV)</td><td>± 4.5%</td>
<td>45%</td><td><span class="sortkey" style="display:none">99</span><b>50%</b></td>
<td>—</td><td>4%</td></tr>
</tbody></table>
<table class="wikitable"><tr><th>Source of poll aggregation</th><th>Dates administered</th>
<th>Dates updated</th><th>Susan Collins (R)</th><th>Troy Jackson (D)</th><th>Margin</th></tr>
<tr><td>270toWin</td><td>October 16–27, 2026</td><td>October 31, 2026</td><td>45.6%</td>
<td>49.2%</td><td>Jackson +3.6%</td></tr></table>
"""


class TestHtmlTable(unittest.TestCase):
    def test_spans_and_headings(self):
        ts = wikitables(POLL_HTML)
        self.assertEqual(len(ts), 2)
        t = ts[0]
        self.assertEqual(t.heading, "General election > Polling")
        g = t.texts()
        # rowspan carried the pollster + dates into the RV row
        self.assertEqual(g[3][0], "Marist University")
        self.assertEqual(g[3][1], "October 22–25, 2026")
        self.assertEqual(g[3][2], "1,449 (RV)")
        # footnote and hidden sort key stripped
        self.assertEqual(g[0][2], "Sample size")
        self.assertEqual(g[4][5], "50%")

    def test_nested_tables_do_not_leak(self):
        html = ("<table class='wikitable'><tr><td>outer"
                "<table><tr><td>inner</td></tr></table></td></tr></table>")
        ts = extract_tables(html)
        self.assertEqual(len(ts), 2)
        outer = [t for t in ts if "wikitable" in t.classes][0]
        self.assertEqual(outer.texts()[0][0], "outer")


class TestPollRows(unittest.TestCase):
    def setUp(self):
        self.t, self.avg = wikitables(POLL_HTML)

    def test_rows(self):
        self.assertTrue(wp.is_poll_table(self.t))
        rows = wp.rows(self.t, 2026)
        self.assertEqual(len(rows), 3)          # annotation row dropped
        lv, rv, dfp = rows
        self.assertEqual((lv["n"], lv["population"]), (1240, "LV"))
        self.assertEqual((rv["n"], rv["population"]), (1449, "RV"))
        self.assertEqual(rv["other"], 0.5)      # '<1%' -> 0.5
        self.assertEqual(lv["answers"], {"Susan Collins (R)": 47.0, "Troy Jackson (D)": 49.0})
        self.assertEqual(lv["leader_bold"], ["Troy Jackson (D)"])
        self.assertEqual(dfp["pollster"], "Data for Progress")
        self.assertEqual(dfp["partisan"], "D")
        self.assertEqual((dfp["start"], dfp["end"]), ("2026-09-29", "2026-10-02"))
        self.assertIsNone(dfp["other"])

    def test_averages(self):
        self.assertTrue(wp.is_average_table(self.avg))
        self.assertFalse(wp.is_poll_table(self.avg))
        (a,) = wp.averages(self.avg, 2026)
        self.assertEqual(a["source"], "270toWin")
        self.assertEqual(a["end"], "2026-10-27")
        self.assertEqual(a["updated"], "2026-10-31")

    def test_dates(self):
        cases = {
            "October 30, 2026": ("2026-10-30", "2026-10-30"),
            "December 28, 2025 – January 3, 2026": ("2025-12-28", "2026-01-03"),
            "Oct 30 – Nov 1": ("2026-10-30", "2026-11-01"),
        }
        for text, want in cases.items():
            self.assertEqual(wp.dates(text, 2026), want, text)

    def test_pollster_flags(self):
        self.assertEqual(wp.pollster("Cygnal (R)"), ("Cygnal", "R"))
        self.assertIsNone(wp.pollster("Beacon Research (D)/Shaw & Company (R)")[1])
        self.assertEqual(wp.label_party("Dan Osborn (I)"), ("Dan Osborn", "I"))


class TestRatings(unittest.TestCase):
    def test_scale(self):
        self.assertEqual(ratings.scale("Lean R"), -1.0)
        self.assertEqual(ratings.scale("Safe D"), 3.0)
        self.assertEqual(ratings.scale("Tossup"), 0.0)
        self.assertEqual(ratings.scale("Tilt D (flip)"), 0.5)
        self.assertEqual(ratings.scale("Lean I", d_side_party="I"), 1.0)
        self.assertIsNone(ratings.scale("—"))

    def test_implied_margin_monotone(self):
        xs = [-3, -2, -1, -0.5, 0, 0.5, 1, 2, 3]
        ms = [ratings.implied_margin(x) for x in xs]
        self.assertEqual(ms, sorted(ms))
        self.assertEqual(ratings.implied_margin(1.0), 5.5)
        self.assertEqual(ratings.implied_margin(-2.0), -11.0)


if __name__ == "__main__":
    unittest.main()
