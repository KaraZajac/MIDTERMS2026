"""The build's fallback when the generic-ballot page can't be read: the
committed polls carry over (Wikipedia deleted the template they came from
on Nov 13, 2026, and every refresh stopped at the build)."""

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


if __name__ == "__main__":
    unittest.main()
