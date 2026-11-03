"""The refresh chain: phases, slots, and the cron watchdog."""

import datetime as dt
import unittest

from midterms.pipeline import cadence as C


def t(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


class TestSlots(unittest.TestCase):
    def test_phases(self):
        for now, want in [("2026-11-01T23:00:00Z", "forecast"), ("2026-11-03T09:29:59Z", "forecast"),
                          ("2026-11-03T09:30:00Z", "hold"), ("2026-11-03T10:00:00Z", "score"),
                          ("2026-11-03T23:00:00Z", "results"), ("2026-11-04T14:00:00Z", "counting"),
                          ("2026-11-06T00:00:00Z", "late"), ("2026-11-10T00:00:00Z", "done")]:
            self.assertEqual(C.phase(t(now)), want, now)

    def test_next_run(self):
        for now, want in [
            ("2026-11-01T23:10:00Z", "2026-11-01T23:37:00Z"),     # every 30 min at :07/:37
            ("2026-11-01T23:37:00Z", "2026-11-02T00:07:00Z"),     # strictly after now
            ("2026-11-03T09:07:30Z", "2026-11-03T10:07:00Z"),     # 09:37 falls in the hold
            ("2026-11-03T09:45:00Z", "2026-11-03T10:07:00Z"),
            ("2026-11-03T22:07:00Z", "2026-11-03T23:02:00Z"),     # results start at 23:00
            ("2026-11-03T23:02:10Z", "2026-11-03T23:12:00Z"),     # then every 10 min
            ("2026-11-04T13:55:00Z", "2026-11-04T14:07:00Z"),
        ]:
            self.assertEqual(C.next_run(t(now)), t(want), now)
        self.assertIsNone(C.next_run(t("2026-11-09T23:30:00Z")))   # the chain ends

    def test_full_runs(self):
        self.assertTrue(C.full(t("2026-11-03T23:02:00Z")))
        self.assertTrue(C.full(t("2026-11-03T23:12:00Z")))        # Wikipedia every run overnight
        self.assertTrue(C.full(t("2026-11-03T23:33:00Z")))        # :32, a minute late
        self.assertTrue(C.full(t("2026-11-04T15:07:00Z")))        # counting: always full
        self.assertTrue(C.full(t("2026-11-02T12:07:00Z")))


class TestWatchdog(unittest.TestCase):
    now = t("2026-11-02T12:20:00Z")

    def test_dispatched_runs_work_and_chain(self):
        d = C.decide(self.now, "workflow_dispatch", 9, [])
        self.assertEqual((d["work"], d["chain"], d["next"]),
                         (True, True, int(t("2026-11-02T12:37:00Z").timestamp())))

    def test_cron_stands_aside_while_the_chain_lives(self):
        sleeping = [{"databaseId": 8, "event": "workflow_dispatch", "status": "in_progress",
                     "createdAt": "2026-11-02T12:07:01Z"}]
        d = C.decide(self.now, "schedule", 9, sleeping)
        self.assertEqual((d["work"], d["chain"]), (False, False))

    def test_cron_restarts_a_dead_chain(self):
        dead = [{"databaseId": 8, "event": "workflow_dispatch", "status": "completed",
                 "createdAt": "2026-11-02T10:37:00Z"},
                {"databaseId": 7, "event": "schedule", "status": "completed",     # a watchdog
                 "createdAt": "2026-11-02T12:00:00Z"}]                            # that stood aside
        d = C.decide(self.now, "schedule", 9, dead)
        self.assertEqual((d["work"], d["chain"]), (True, True))

    def test_hold_and_done(self):
        d = C.decide(t("2026-11-03T09:40:00Z"), "workflow_dispatch", 9, [])
        self.assertEqual((d["phase"], d["work"], d["chain"]), ("hold", False, True))
        d = C.decide(t("2026-11-11T00:17:00Z"), "schedule", 9, [])
        self.assertEqual((d["phase"], d["work"], d["chain"]), ("done", True, False))


if __name__ == "__main__":
    unittest.main()
