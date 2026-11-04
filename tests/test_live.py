"""Election night: the civicAPI map and the conditioned forecast."""

import json
import math
import unittest

import numpy as np

from midterms.model import live as L
from midterms.paths import SITE
from midterms.pipeline import civic

SIM = json.loads((SITE / "sim.json").read_text())


class TestT(unittest.TestCase):
    def test_cdf(self):
        # textbook quantiles: t(6) 0.975 = 2.447, t(5) 0.95 = 2.015, t(3) 0.9 = 1.638
        for nu, z, p in ((6, 2.447, 0.975), (5, 2.015, 0.95), (3, 1.638, 0.9), (4, 0.0, 0.5)):
            self.assertAlmostEqual(float(L.t_cdf(np.array(z), nu)), p, places=3)
            self.assertAlmostEqual(float(L.t_cdf(np.array(-z), nu)), 1 - p, places=3)

    def test_stream_is_ours(self):
        # the same seed gives the same draws (raw PCG64 bits, no numpy sampler)
        a, b = L._t_unit(5, 1, 6, (3, 4)), L._t_unit(5, 1, 6, (3, 4))
        self.assertTrue(np.array_equal(a, b))
        z = L._normals(1, 0, (200_000,))
        self.assertAlmostEqual(float(z.mean()), 0, delta=0.01)
        self.assertAlmostEqual(float(z.std()), 1, delta=0.01)
        t = L._t_unit(2, 0, 6, (200_000,))
        self.assertAlmostEqual(float(t.std()), 1, delta=0.03)       # unit variance


class TestEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.eng = L.Engine(SIM)

    def test_no_calls_is_the_forecast(self):
        out = self.eng.run({}, n=8000, seed=1)
        self.assertGreater(out["ess"], 6000)
        for c in ("house", "senate", "governor"):
            self.assertAlmostEqual(out["chambers"][c]["p_control"]["D"], SIM["reference"]["deluxe"][c]["D"],
                                   delta=0.03, msg=c)

    def test_everything_called(self):
        # every race called for the D-side: control is certain, and seats add up
        calls = {r["id"]: "D" for r in SIM["races"] if not r["fixed"]}
        out = self.eng.run(calls, n=500, seed=2)
        self.assertAlmostEqual(out["chambers"]["house"]["p_control"]["D"], 1.0, places=9)
        # D-bloc seats: every D-side that is a Democrat (Alaska's D-side is an independent)
        dems = sum(1 for r in SIM["races"] if r["chamber"] == "house"
                   and ((not r["fixed"] and r["d_side"] == "D") or r["fixed"] == "D"))
        self.assertEqual(out["chambers"]["house"]["seats"]["p50"], dems)
        self.assertTrue(all(out["races"][rid] == 1.0 for rid in calls))

    def test_calls_move_the_rest(self):
        # Republicans sweeping the close House seats makes every chamber harder for Democrats
        close = [r["id"] for r in SIM["races"] if r["chamber"] == "house" and not r["fixed"]
                 and abs(r["mu"]["deluxe"]) < 4]
        base = self.eng.run({}, n=6000, seed=3)
        swept = self.eng.run({rid: "R" for rid in close}, n=6000, seed=3)
        for c in ("house", "senate", "governor"):
            self.assertLess(swept["chambers"][c]["p_control"]["D"], base["chambers"][c]["p_control"]["D"] - 0.05, c)
        self.assertGreater(swept["ess"], 300)
        # and the races still out follow: the uncalled Senate races lean further right
        out = [r["id"] for r in SIM["races"] if r["chamber"] == "senate" and not r["fixed"]]
        before = sum(base["races"][rid] for rid in out)
        after = sum(swept["races"][rid] for rid in out)
        self.assertLess(after, before - 0.5)

    def test_deterministic(self):
        calls = {"senate:ME": "R", "house:PA-07": "D"}
        a, b = self.eng.run(calls, n=3000, seed=4), self.eng.run(calls, n=3000, seed=4)
        self.assertEqual(a["chambers"], b["chambers"])


def civic_race(**kw):
    c = {"id": 1, "type": "US Senate", "election_type": "General", "country": "US", "province": "ME",
         "district": None, "percent_reporting": 40,
         "candidates": [{"name": "Troy Jackson", "party": "Democratic", "votes": 120, "winner": False},
                        {"name": "Susan Collins", "party": "Republican", "votes": 100, "winner": False},
                        {"name": "Write-in", "party": "Write-in", "votes": 5, "winner": False}]}
    c.update(kw)
    return c


RACES = {"senate:ME": {"id": "senate:ME", "state": "ME", "d_cand": "Troy Jackson", "r_cand": "Susan Collins"},
         "senate:OH-special": {"id": "senate:OH-special", "state": "OH", "d_cand": "Sherrod Brown",
                               "r_cand": "Jon Husted"},
         "house:SD-AL": {"id": "house:SD-AL", "state": "SD", "d_cand": "Nikki Gronli", "r_cand": "Marty Jackley"},
         "senate:GA": {"id": "senate:GA", "state": "GA", "d_cand": "Jon Ossoff", "r_cand": "Mike Collins"}}


class TestHistory(unittest.TestCase):
    """live.json's `history`: the chances of control through the night."""

    @staticmethod
    def doc(t, live, called, races=None, events=None):
        ch = {c: {"pre": {"p_control": {"D": p}}, "live": {"p_control": {"D": q}}}
              for c, p, q in zip(("house", "senate", "governor"), (0.9461, 0.7672, 0.8231), live)}
        return {"generated": t, "chambers": ch, "counts": {"called": called},
                "races": races or {}, "events": events or []}

    def test_seeded_from_the_forecast_and_the_calls_in_events(self):
        from midterms.pipeline import livefeed as F
        races = {"a": {"status": "called", "called_at": "T1"}, "b": {"status": "called", "called_at": "T1"},
                 "c": {"status": "called", "called_at": "T2"}, "d": {"status": "counting"}}
        after1 = {"house": 0.95, "senate": 0.77, "governor": 0.83}
        after2 = {"house": 0.954, "senate": 0.7771, "governor": 0.8331}
        events = [{"t": "T2", "type": "call", "after": after2},                 # newest first
                  {"t": "T1", "type": "call", "after": after1}, {"t": "T1", "type": "call", "after": after1}]
        d = self.doc("T3", (0.954, 0.7771, 0.8331), 3, races, events)
        h = F.history(None, d)
        self.assertEqual(h, [[F.DEADLINE, 0.9461, 0.7672, 0.8231, 0],
                             ["T1", 0.95, 0.77, 0.83, 2],
                             ["T2", 0.954, 0.7771, 0.8331, 3]])     # T3 changed nothing: no point
        # a history carried from 3-decimal points gets its forecast point redone exactly
        old = [[F.DEADLINE, 0.946, 0.767, 0.823, 0]] + h[1:]
        self.assertEqual(F.history({"history": old}, d)[0], h[0])
        # carried on: a change adds a point, no change adds none
        d2 = self.doc("T4", (0.96, 0.7771, 0.8331), 4)
        h2 = F.history({"history": h}, d2)
        self.assertEqual(h2[-1], ["T4", 0.96, 0.7771, 0.8331, 4])
        self.assertEqual(F.history({"history": h2}, self.doc("T5", (0.96, 0.7771, 0.8331), 4)), h2)
        # capped, oldest dropped
        long = [["t%d" % i, 0.5, 0.5, 0.5, i] for i in range(F.HISTORY_KEPT + 10)]
        h3 = F.history({"history": long}, self.doc("T6", (0.1, 0.1, 0.1), 9999))
        self.assertEqual((len(h3), h3[-1][0]), (F.HISTORY_KEPT, "T6"))


class TestUndouble(unittest.TestCase):
    def test_new_york_halved_while_the_county_job_finds_the_double_count(self):
        import shutil
        import tempfile
        from pathlib import Path
        from midterms.pipeline import livefeed as F
        d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, d)
        rows = {"house:NY-16": {"state": "NY"}, "house:NJ-07": {"state": "NJ"}}

        def res():
            return {"house:NY-16": {"votes": {"D": 120000, "R": 67992, "other": 0}, "margin": 27.7},
                    "house:NJ-07": {"votes": {"D": 1000, "R": 900, "other": 10}, "margin": 5.3}}
        self.assertEqual(F.undouble(res(), rows, None), [])
        self.assertEqual(F.undouble(res(), rows, d), [])                     # no county file yet
        (d / "governor").mkdir()
        for flag, want in ((False, []), (True, ["house:NY-16"])):
            (d / "governor" / "ny.json").write_text(json.dumps({"double_counted": flag}))
            r = res()
            self.assertEqual(F.undouble(r, rows, d), want)
        self.assertEqual(r["house:NY-16"], {"votes": {"D": 60000, "R": 33996, "other": 0}, "margin": 27.7})
        self.assertEqual(r["house:NJ-07"]["votes"], {"D": 1000, "R": 900, "other": 10})


class TestCivic(unittest.TestCase):
    def test_fetch_all(self):
        # both searches side by side, each paged, in a fixed order; gzip, and a patient timeout
        from unittest import mock
        from urllib.parse import parse_qs, urlparse
        seen = []

        def fake_get(u, **kw):
            q = parse_qs(urlparse(u).query)
            seen.append((kw.get("gzip"), kw.get("timeout"), kw.get("retries")))
            off = int(q["offset"][0])
            if q.get("type") == ["Governor"]:
                return json.dumps({"count": 1, "races": [{"id": "g0"}]}).encode()
            return json.dumps({"count": 3, "races": [{"id": f"f{off}"}] if off < 3 else []}).encode()

        with mock.patch.object(civic.fetch, "get", fake_get):
            races, _, stood_in = civic.fetch_all()
        self.assertEqual([r["id"] for r in races], ["f0", "f1", "f2", "g0"])
        self.assertEqual(stood_in, {})
        # one attempt per call: civic retries, against its own time budget
        self.assertTrue(all(g and t >= 20 and r == 1 for g, t, r in seen))

    class Clock:
        """time.monotonic and time.sleep, without the waiting."""
        def __init__(self):
            self.t, self.slept = 1000.0, []

        def monotonic(self):
            return self.t

        def sleep(self, s):
            self.slept.append(s)
            self.t += s

    def _governors_fail(self, *errors):
        """fetch.get where the governors' search raises each of `errors` in
        turn (then answers), and the federal one answers at once."""
        left = list(errors)

        def fake_get(u, **kw):
            if "Governor" in u:
                if left:
                    raise left.pop(0)
                return json.dumps({"count": 1, "races": [{"id": "g0"}]}).encode()
            return json.dumps({"count": 1, "races": [{"id": "f0"}]}).encode()
        return fake_get

    def test_a_busy_server_is_tried_again(self):
        # 14:00 UTC, Nov 3: a 503 to two quick tries sank the web server's run
        from unittest import mock
        clock = self.Clock()
        busy = civic.fetch.DownloadFailed("download failed: … (HTTP 503)", 503)
        slow = civic.fetch.DownloadFailed("download failed: … (HTTP 503)", 503, retry_after=7.0)
        cut = civic.fetch.DownloadFailed("download failed: … (The read operation timed out)")
        with mock.patch.object(civic.fetch, "get", self._governors_fail(busy, slow, cut)), \
                mock.patch.object(civic, "time", clock):
            races, _, stood_in = civic.fetch_all()
        self.assertEqual([r["id"] for r in races], ["f0", "g0"])
        self.assertEqual(clock.slept, [2.0, 7.0, 8.0])        # backoff, Retry-After, backoff

    def test_a_long_retry_after_on_a_5xx_is_capped(self):
        # civicAPI's quick 502s ask for 30 s or more: wait 10 s, so a run gets
        # several tries at a search; a 429's Retry-After is still honored
        from unittest import mock
        for status, ra, want in ((502, 30.0, [10.0, 10.0, 10.0]), (429, 30.0, [30.0, 30.0]),
                                 (522, None, [2.0])):           # Cloudflare's origin errors too
            clock = self.Clock()
            err = civic.fetch.DownloadFailed(f"download failed: … (HTTP {status})", status, retry_after=ra)
            with mock.patch.object(civic.fetch, "get", self._governors_fail(*[err] * len(want))), \
                    mock.patch.object(civic, "time", clock):
                races, _, _ = civic.fetch_all()
            self.assertEqual([r["id"] for r in races], ["f0", "g0"])
            self.assertEqual(clock.slept, want)

    def _governors_slow(self, clock, takes, asked):
        """fetch.get where the governors' search answers after `takes`
        seconds (None: never), timing out like a socket when the read's
        timeout is shorter; the federal one answers at once."""
        def fake_get(u, timeout, **kw):
            if "Governor" not in u:
                return json.dumps({"count": 1, "races": [{"id": "f0"}]}).encode()
            asked.append(timeout)
            if takes is None or timeout < takes:
                clock.t += timeout
                raise civic.fetch.DownloadFailed("download failed: … (The read operation timed out)")
            clock.t += takes
            return json.dumps({"count": 1, "races": [{"id": "g0"}]}).encode()
        return fake_get

    def test_a_slow_answer_is_waited_for(self):
        # 22:58 UTC, Nov 3: three 25-second reads of the governors' search went
        # unanswered and the run failed; an answer 40 s away now comes on the first read
        from unittest import mock
        clock, asked = self.Clock(), []
        with mock.patch.object(civic.fetch, "get", self._governors_slow(clock, 40, asked)), \
                mock.patch.object(civic, "time", clock):
            races, _, stood_in = civic.fetch_all()
        self.assertEqual([r["id"] for r in races], ["f0", "g0"])
        self.assertEqual((asked, clock.slept), ([civic.TIMEOUT], []))

    def test_a_silent_server_is_given_up_on_in_time(self):
        # never answering: one long read, a second with what is left, then out
        from unittest import mock
        clock, asked = self.Clock(), []
        start = clock.t
        with mock.patch.object(civic.fetch, "get", self._governors_slow(clock, None, asked)), \
                mock.patch.object(civic, "time", clock):
            with self.assertRaises(SystemExit) as cm:
                civic.fetch_all()
        self.assertIn("timed out", str(cm.exception))
        self.assertEqual(asked, [civic.TIMEOUT, civic.BUDGET - civic.TIMEOUT - 2])
        self.assertLessEqual(clock.t - start, civic.BUDGET)

    def test_fetch_all_is_all_or_nothing(self):
        # still failing when the budget runs out: no file rather than half a picture
        from unittest import mock
        clock = self.Clock()
        busy = civic.fetch.DownloadFailed("download failed: … (HTTP 503)", 503)
        with mock.patch.object(civic.fetch, "get", self._governors_fail(*[busy] * 100)), \
                mock.patch.object(civic, "time", clock):
            with self.assertRaises(SystemExit) as cm:
                civic.fetch_all()
        self.assertIn("HTTP 503", str(cm.exception))
        self.assertLessEqual(sum(clock.slept), civic.BUDGET - 5)
        self.assertGreaterEqual(len(clock.slept), 6)

    def test_a_failed_search_stands_in_with_its_last_answer(self):
        # election night: the two searches failed by turns; on the web server a
        # failed search answers from its last answer, if at most KEEP seconds old
        import datetime as dt
        import shutil
        import tempfile
        from pathlib import Path
        from unittest import mock
        from midterms.pipeline import livefeed
        cache = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, cache)
        bad = civic.fetch.DownloadFailed("download failed: … (HTTP 502)", 502)

        def run(fake, where=cache):
            clock = self.Clock()
            with mock.patch.object(civic.fetch, "get", fake), mock.patch.object(civic, "time", clock):
                return civic.fetch_all(cache=where)

        _, first, stood_in = run(self._governors_fail())
        self.assertEqual(stood_in, {})
        kept = cache / ".civic-governors.json"
        self.assertEqual(json.loads(kept.read_text()), {"fetched": first, "races": [{"id": "g0"}]})
        # the governors' search fails all the way through: its last answer stands in
        races, _, stood_in = run(self._governors_fail(*[bad] * 100))
        self.assertEqual([r["id"] for r in races], ["f0", "g0"])
        self.assertEqual(stood_in, {"governors": first})
        # never without a cache, never when every search failed, never past KEEP
        with self.assertRaises(SystemExit):
            run(self._governors_fail(*[bad] * 100), where=None)

        def all_fail(u, **kw):
            raise bad
        with self.assertRaises(SystemExit):
            run(all_fail)
        old = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=civic.KEEPS["governors"] + 60)
        kept.write_text(json.dumps({"fetched": old.strftime("%Y-%m-%dT%H:%M:%SZ"), "races": [{"id": "g0"}]}))
        with self.assertRaises(SystemExit) as cm:
            run(self._governors_fail(*[bad] * 100))
        self.assertIn("HTTP 502", str(cm.exception))
        # governors' results may stand in for 30 minutes, the House and Senate's for 5
        mid = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=20)).strftime("%Y-%m-%dT%H:%M:%SZ")
        kept.write_text(json.dumps({"fetched": mid, "races": [{"id": "g0"}]}))
        self.assertEqual(run(self._governors_fail(*[bad] * 100))[2], {"governors": mid})
        (cache / ".civic-federal.json").write_text(json.dumps({"fetched": mid, "races": [{"id": "f0"}]}))

        def federal_fails(u, **kw):
            if "Governor" in u:
                return json.dumps({"count": 1, "races": [{"id": "g0"}]}).encode()
            raise bad
        with self.assertRaises(SystemExit):
            run(federal_fails)
        # a broken kept file is no answer
        kept.write_text("{")
        with self.assertRaises(SystemExit):
            run(self._governors_fail(*[bad] * 100))
        self.assertEqual(livefeed.et_clock("2026-11-04T00:19:01Z"), "7:19 p.m. ET")
        self.assertEqual(livefeed.et_clock("2026-11-04T05:05:00Z"), "12:05 a.m. ET")

    def test_a_refusal_is_not_retried(self):
        from unittest import mock
        clock = self.Clock()
        gone = civic.fetch.DownloadFailed("download failed: … (HTTP 404)", 404)
        with mock.patch.object(civic.fetch, "get", self._governors_fail(gone)), \
                mock.patch.object(civic, "time", clock):
            with self.assertRaises(SystemExit):
                civic.fetch_all()
        self.assertEqual(clock.slept, [])

    def test_download_failed(self):
        # fetch.get says why: the status and Retry-After, or None for the network
        from unittest import mock
        from urllib.error import HTTPError
        f = civic.fetch
        for err, want in ((HTTPError("https://x", 503, "busy", {"Retry-After": "7"}, None), (503, 7.0)),
                          (HTTPError("https://x", 429, "slow down", {"Retry-After": "Wed, 04 Nov 2026 01:00:00 GMT"},
                                     None), (429, None)),
                          (ConnectionResetError("reset"), (None, None)),
                          (TimeoutError("The read operation timed out"), (None, None))):
            if isinstance(err, HTTPError):
                self.addCleanup(err.close)
            with mock.patch.object(f, "urlopen", side_effect=err):
                with self.assertRaises(f.DownloadFailed) as cm:
                    f.get("https://x", retries=1)
            self.assertEqual((cm.exception.status, cm.exception.retry_after), want)
            self.assertIsInstance(cm.exception, SystemExit)

    def test_race_ids(self):
        ids = set(RACES)
        self.assertEqual(civic.race_id(civic_race(), ids), "senate:ME")
        self.assertEqual(civic.race_id(civic_race(province="OH"), ids), "senate:OH-special")
        self.assertEqual(civic.race_id(civic_race(type="House of Representatives", province="SD",
                                                  district="SD-AL"), ids), "house:SD-AL")
        self.assertIsNone(civic.race_id(civic_race(province="US"), ids))           # the national summary
        self.assertIsNone(civic.race_id(civic_race(type="State Senate"), ids))

    def test_counting_and_called(self):
        r = civic.result(civic_race(), RACES["senate:ME"])
        self.assertEqual((r["status"], r["votes"], r["margin"]), ("counting", {"D": 120, "R": 100, "other": 5}, 9.1))
        c = civic_race()
        c["candidates"][1]["winner"] = True
        r = civic.result(c, RACES["senate:ME"])
        self.assertEqual((r["status"], r["winner"]), ("called", "R"))
        self.assertEqual(civic.result(civic_race(candidates=[
            {"name": "Troy Jackson", "votes": 0}, {"name": "Susan Collins", "votes": 0}]), RACES["senate:ME"])["status"],
            "awaiting")

    def test_georgia_runoff(self):
        c = civic_race(province="GA", percent_reporting=100, candidates=[
            {"name": "Jon Ossoff", "votes": 495}, {"name": "Mike Collins", "votes": 490},
            {"name": "Someone Else", "votes": 20}])
        self.assertEqual(civic.result(c, RACES["senate:GA"])["status"], "runoff")

    def test_louisiana_first_round(self):
        # every candidate on one ballot, and our two sides aren't the leaders
        # (LA-01 on Nov 3: Jewett vs Arrington read D+80; Scalise won)
        race = {"id": "house:LA-01", "state": "LA", "d_cand": "Lauren Jewett", "r_cand": "Randall Arrington",
                "d_side": "D", "r_side": "R"}
        cands = [{"name": "Steve Scalise", "party": "Republican", "votes": 159890, "winner": False},
                 {"name": "Lauren Jewett", "party": "Democratic", "votes": 89428, "winner": False},
                 {"name": "Randall Arrington", "party": "Republican", "votes": 9776, "winner": False},
                 {"name": 'E. "Liddy" Glass', "party": "Nonpartisan", "votes": 4279, "winner": False}]
        c = civic_race(type="House of Representatives", province="LA", district="LA-01",
                       percent_reporting=60, candidates=cands)
        r = civic.result(c, race)
        self.assertEqual((r["status"], r["votes"]), ("counting", {"D": 89428, "R": 9776, "other": 164169}))
        self.assertNotIn("margin", r)
        self.assertEqual(r["top_two"], [{"name": "Steve Scalise", "party": "R", "votes": 159890},
                                        {"name": "Lauren Jewett", "party": "D", "votes": 89428}])
        cands[0]["winner"] = True
        r = civic.result(c, race)
        self.assertEqual((r["status"], r["winner"], r["winner_name"], r["party"]),
                         ("called", "other", "Steve Scalise", "R"))
        # no majority once it's all counted: the top two meet on Dec 12 (LA-05)
        five = {"id": "house:LA-05", "state": "LA", "d_cand": "Dan McKay", "r_cand": "Stewart Cathey Jr.",
                "d_side": "D", "r_side": "R"}
        cands = [{"name": 'Patricia "Pat" Moore', "party": "Democratic", "votes": 40789},
                 {"name": "Gabe Firment", "party": "Republican", "votes": 39131},
                 {"name": "Stewart Cathey, Jr.", "party": "Republican", "votes": 28160},
                 {"name": "Dan McKay", "party": "Democratic", "votes": 16047}]
        r = civic.result(civic_race(type="House of Representatives", province="LA", district="LA-05",
                                    percent_reporting=100, candidates=cands), five)
        self.assertEqual(r["status"], "runoff")
        self.assertEqual([(x["name"], x["party"]) for x in r["top_two"]],
                         [('Patricia "Pat" Moore', "D"), ("Gabe Firment", "R")])
        r = civic.result(civic_race(type="House of Representatives", province="LA", district="LA-05",
                                    percent_reporting=97, candidates=cands), five)
        self.assertEqual(r["status"], "counting")
        # everywhere else, as before: a side margin, no top two, no party for an 'other' winner
        me = civic.result(civic_race(), RACES["senate:ME"])
        self.assertEqual((me["margin"], "top_two" in me), (9.1, False))
        c = civic_race()
        c["candidates"][2]["winner"] = True
        self.assertNotIn("party", civic.result(c, RACES["senate:ME"]))
        self.assertEqual([civic.party_code(p) for p in ("Democratic", "Republican", "Libertarian", "Nonpartisan", None)],
                         ["D", "R", "L", "IND", "IND"])

    def test_names(self):
        f = civic._find
        cands = [{"name": "Austin Scott"}, {"name": "Kelly Etsi"}]
        self.assertEqual(f(cands, "Kelly Esti"), 1)                                 # transposed
        self.assertEqual(f([{"name": "Hank Johnson"}, {"name": "James Duffie"}], "James Duffe"), 1)
        self.assertEqual(f([{"name": "Terri Yarbrough Green"}, {"name": "Rick Crawford"}], "Terri Yarbrough"), 0)
        sullivans = [{"name": "Mary Peltola"}, {"name": "Dan Sullivan"}, {"name": "Daniel J. Jr. Sullivan"}]
        self.assertEqual(f(sullivans, "Dan S. Sullivan"), 1)
        self.assertIsNone(f([{"name": "Ann Smith"}, {"name": "Bob Jones"}], "Carl Wu"))


class TestSafetyNets(unittest.TestCase):
    def test_party_fallback(self):
        # a nominee whose name no longer matches is found by party (D/R only)
        race = {"d_cand": "Kelly Nobody", "r_cand": "Austin Scott", "d_side": "D", "r_side": "R", "state": "GA"}
        c = civic_race(province="GA", candidates=[{"name": "Austin Scott", "party": "Republican", "votes": 10},
                                                 {"name": "Kelly Etsi", "party": "Democratic", "votes": 5}])
        self.assertEqual(civic.result(c, race)["matched"], {"D": True, "R": True})
        race["d_side"] = "IND"                                     # never for an independent
        self.assertFalse(civic.result(c, race)["matched"]["D"])

    def test_wikipedia_reconciles(self):
        from midterms.pipeline import livefeed as F
        out = F.reconcile({"senate:ME": {"status": "called", "winner": "R"},
                           "house:PA-07": {"status": "counting"}},
                          {"senate:ME": "D", "house:PA-07": "D"})
        self.assertEqual(out["senate:ME"]["status"], "counting")          # disputed: not used
        self.assertTrue(out["senate:ME"]["disputed"])
        self.assertEqual((out["house:PA-07"]["status"], out["house:PA-07"]["called_by"]), ("called", "wikipedia"))


class TestSeatsAndClosings(unittest.TestCase):
    """What a viewer watching the night needs beside the calls: which seats
    changed hands, and when each state's polls close."""

    def test_clerk_list(self):
        from midterms.pipeline import holders
        xml = """<MemberData publish-date="October 1, 2026"><members>
          <member><statedistrict>AK00</statedistrict><member-info><official-name>Ann Bee</official-name>
            <party>R</party></member-info></member>
          <member><statedistrict>CA03</statedistrict><member-info><official-name>Cal Dee</official-name>
            <party>I</party></member-info></member>
          <member><statedistrict>TX23</statedistrict><member-info><official-name /><party /></member-info>
            <predecessor-info><pred-official-name>Eve Eff</pred-official-name><pred-party>R</pred-party>
            <pred-footnote>Vacancy due to the resignation of Eve Eff.</pred-footnote></predecessor-info></member>
        </members></MemberData>"""
        out, published = holders.from_clerk(xml)
        self.assertEqual(published, "October 1, 2026")
        self.assertEqual(out["house:AK-AL"]["held"], "R")                   # at-large: 00 -> AL
        self.assertEqual(out["house:CA-03"]["held"], "IND")                 # the Clerk's I
        self.assertEqual((out["house:TX-23"]["held"], out["house:TX-23"]["holder"]), ("R", "Eve Eff"))

    def test_every_race_has_a_holder(self):
        from midterms.paths import FORECAST
        from midterms.pipeline import holders
        held = holders.load()
        fc = json.loads((FORECAST / "latest.json").read_text())
        self.assertEqual(sorted(set(fc["races"]) - set(held)), [])
        self.assertTrue(set(held.values()) <= {"D", "R", "IND"})

    def test_flips(self):
        from midterms.paths import FORECAST
        from midterms.pipeline import livefeed as F
        fc = json.loads((FORECAST / "latest.json").read_text())
        res = {"senate:ME": {"status": "called", "winner": "D"},           # a pickup
               "senate:GA": {"status": "called", "winner": "D"},           # a hold
               "governor:AZ": {"status": "counting", "votes": {"D": 10, "R": 9, "other": 0},
                               "pct_reporting": 3.0, "margin": 5.3}}
        doc = F.assemble(fc, "latest.json", False, F.race_rows(), res, None, None, "2026-11-04T01:30:00Z",
                         draws=2000, held={"senate:ME": "R", "senate:GA": "D", "governor:AZ": "D"})
        me, ga, az = (doc["races"][k] for k in ("senate:ME", "senate:GA", "governor:AZ"))
        self.assertEqual((me["held"], me["party"], me.get("flip")), ("R", "D", True))
        self.assertEqual((ga["held"], ga["party"], ga.get("flip")), ("D", "D", None))
        self.assertEqual((az["held"], az.get("party"), az.get("flip")), ("D", None, None))   # not called
        s = doc["chambers"]["senate"]
        self.assertEqual((s["gains"], s["losses"], s["flips"]), ({"D": 1}, {"R": 1}, ["senate:ME"]))
        self.assertEqual(doc["chambers"]["governor"]["flips"], [])
        ev = {e["race"]: e for e in doc["events"]}
        self.assertTrue(ev["senate:ME"]["flip"])
        self.assertFalse(ev["senate:GA"]["flip"])
        self.assertIn("held_note", doc)

    def test_a_first_round_winner_counts_for_their_party(self):
        from midterms.paths import FORECAST
        from midterms.pipeline import livefeed as F
        fc = json.loads((FORECAST / "latest.json").read_text())
        top = [{"name": "Steve Scalise", "party": "R", "votes": 159890},
               {"name": "Lauren Jewett", "party": "D", "votes": 89428}]
        res = {"house:LA-01": {"status": "called", "winner": "other", "winner_name": "Steve Scalise",
                               "party": "R", "pct_reporting": 100.0, "top_two": top,
                               "votes": {"D": 89428, "R": 9776, "other": 164169}},
               "house:LA-06": {"status": "runoff", "pct_reporting": 100.0,
                               "votes": {"D": 50878, "R": 49241, "other": 161832},
                               "top_two": [{"name": "Chauna Banks", "party": "D", "votes": 50878},
                                           {"name": "Blake Miguez", "party": "R", "votes": 50213}]}}
        for held, flip in (("R", None), ("D", True)):
            doc = F.assemble(fc, "latest.json", False, F.race_rows(), res, None, None, "2026-11-04T07:18:01Z",
                             draws=2000, held={"house:LA-01": held, "house:LA-06": "D"})
            one, six = doc["races"]["house:LA-01"], doc["races"]["house:LA-06"]
            self.assertEqual((one["winner"], one["winner_name"], one["party"], one.get("flip")),
                             ("other", "Steve Scalise", "R", flip))
            self.assertEqual((one["top_two"], "margin" in one, one["p_live"]), (top, False, 0.0))
            house = doc["chambers"]["house"]
            self.assertEqual(house["called"], {"R": 1})                 # not 'other'
            self.assertEqual(house["gains"], {"R": 1} if flip else {})
            self.assertEqual((six["status"], "winner" in six, [x["name"] for x in six["top_two"]]),
                             ("runoff", False, ["Chauna Banks", "Blake Miguez"]))
            self.assertEqual(doc["events"][0]["party"], "R")

    def test_poll_closings(self):
        from midterms.pipeline import livefeed as F
        pc = F.poll_closings()
        self.assertEqual(len(pc["states"]), 50)
        self.assertEqual(pc["states"]["IN"]["first"], "2026-11-03T23:00:00Z")   # 6 p.m. ET
        self.assertEqual(pc["states"]["NC"]["last"], "2026-11-04T00:30:00Z")    # 7:30 p.m. ET
        self.assertEqual(pc["states"]["AK"]["last"], "2026-11-04T06:00:00Z")    # 1 a.m. ET
        self.assertEqual(pc["races"]["house:FL-01"], {"first": "2026-11-04T01:00:00Z",
                                                      "last": "2026-11-04T01:00:00Z"})
        self.assertEqual(pc["races"]["house:FL-07"]["last"], "2026-11-04T00:00:00Z")   # all Eastern: 7 p.m.
        self.assertEqual(sum(k.startswith("house:FL-") for k in pc["races"]), 28)
        for st, v in pc["states"].items():
            self.assertLessEqual(v["first"], v["last"], st)
            self.assertEqual("note" in v, v["first"] != v["last"], st)


if __name__ == "__main__":
    unittest.main()
