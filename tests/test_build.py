"""The build's carry-overs: the generic-ballot polls when their page can't
be read (Wikipedia deleted the template they came from on Nov 13, 2026, and
every refresh stopped at the build), and the FEC filings, which no Wikipedia
edit may drop."""

import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from midterms.pipeline import build

OLD = "Template:2026 United States elections/polling"
ROW = {"race": "generic", "pollster": "Reuters/Ipsos", "partisan": "", "start": "2026-10-28",
       "end": "2026-11-02", "n": "1212", "population": "LV", "d": "52.0", "r": "44.0", "other": "4.0",
       "undecided": "", "d_label": "Democratic", "r_label": "Republican",
       "source": f"wikipedia:{OLD}@1384068090", "table": "2", "url": "https://www.ipsos.com/x.pdf"}


class TestGenericLedger(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.polls = Path(tmp.name)
        patch = mock.patch.object(build, "POLLS", self.polls)
        patch.start()
        self.addCleanup(patch.stop)

    def commit(self):
        build._write(self.polls / "generic.csv", [ROW], build.POLL_COLS)

    def ledger(self, **page):
        out = io.StringIO()
        with mock.patch.object(build, "generic_polls", **page), contextlib.redirect_stdout(out):
            rows, revs = build.generic_ledger()
        return rows, revs, out.getvalue()

    def test_a_missing_page_keeps_the_committed_polls(self):
        self.commit()
        gone = SystemExit(f"wikipedia: {OLD!r}: The page you specified doesn't exist.")
        rows, revs, said = self.ledger(side_effect=gone)
        self.assertEqual(rows, [ROW])
        self.assertEqual(revs, {OLD: 1384068090})        # their page stays in meta.yaml
        self.assertIn("keeping the committed data/polls/generic.csv", said)

    def test_a_page_without_polls_keeps_them_too(self):
        self.commit()
        rows, revs, said = self.ledger(return_value=([], {"title": "x", "revid": 1}))
        self.assertEqual((rows, revs), ([ROW], {OLD: 1384068090}))
        self.assertIn("no generic-ballot polls", said)

    def test_the_page_read_this_run_wins(self):
        self.commit()
        fresh = {**ROW, "source": "wikipedia:2026 United States elections polling@1384702311", "table": "1"}
        rows, revs, said = self.ledger(return_value=([fresh], {"title": "x", "revid": 1384702311}))
        self.assertEqual((rows, revs, said), ([fresh], {}, ""))

    def test_nothing_committed_still_stops_the_build(self):
        with self.assertRaises(SystemExit):
            self.ledger(side_effect=SystemExit("wikipedia: gone"))


def filing(race, side, candidate, fec_id="", fec_name="", receipts=""):
    return {"race": race, "side": side, "candidate": candidate, "fec_id": fec_id, "fec_name": fec_name,
            "receipts": receipts, "total_receipts": receipts, "cash_on_hand": "1", "coverage_end": "10/14/2026"}


class TestCarryFiling(unittest.TestCase):
    """What happened to 26 filings between Nov 4 and Nov 15, 2026."""

    BUCK = filing("house:NV-01", "R", "Carrie Buck", "H6NV01331", "BUCK, CARRIE", "1789814")
    PRATT = filing("house:MN-02", "R", "Eric Pratt", "H6MN02263", "PRATT, ERIC", "479952")
    WAGNER = filing("house:MO-02", "R", "Ann Wagner", "H2MO02102", "WAGNER, ANN L.", "2354886")

    def test_a_respelled_nominee_keeps_the_filing(self):
        row = build.carry_filing(self.BUCK, "house:NV-01", "R", "Carrie Ann Buck")
        self.assertEqual(row, {**self.BUCK, "candidate": "Carrie Ann Buck"})

    def test_a_wrong_name_for_a_while_leaves_the_filing_with_its_nominee(self):
        row = build.carry_filing(self.PRATT, "house:MN-02", "R", "Joe Teirab")
        self.assertEqual(row, self.PRATT)
        # and the page put right: still there
        self.assertEqual(build.carry_filing(row, "house:MN-02", "R", "Eric Pratt"), self.PRATT)

    def test_a_page_without_names_drops_nothing(self):
        self.assertEqual(build.carry_filing(self.WAGNER, "house:MO-02", "R", ""), self.WAGNER)

    def test_a_side_without_a_filing_takes_the_new_name(self):
        none = filing("house:MO-01", "R", "Paul Berry")
        self.assertEqual(build.carry_filing(none, "house:MO-01", "R", "Paul Berry III"),
                         {**dict.fromkeys(build.FIN_COLS, ""), "race": "house:MO-01", "side": "R",
                          "candidate": "Paul Berry III"})
        self.assertEqual(build.carry_filing(None, "house:MO-01", "R", "Paul Berry III")["fec_id"], "")


if __name__ == "__main__":
    unittest.main()
