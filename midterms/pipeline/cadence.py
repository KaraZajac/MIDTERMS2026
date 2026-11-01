"""When the refresh runs, and what each run does.

GitHub's scheduler runs cron jobs late or not at all under load: on Nov 1
it skipped the 06:17 UTC slot, ran 12:17 at 13:30 and ran 18:17 at 22:05.
So the refresh (.github/workflows/refresh.yml) keeps its own clock: every
run ends by dispatching the next one at its phase's cadence, and the cron
entries are only a watchdog that restarts the chain if it ever breaks.

    phase      from (UTC)           every   the run
    forecast   now                  30 min  pull, build, forecast + snapshot
    hold       Nov 3 09:30          —       nothing: every snapshot that can
                                            be the record is committed
                                            before polls open
    score      Nov 3 10:00          60 min  pull, build, score (no results
                                            yet; seals the forecast of record)
    results    Nov 3 23:00          10 min  live results and calls (civicAPI);
                                            pull + build + score every 30 min
    counting   Nov 4 14:00          30 min  the same, slower
    late       Nov 6 00:00          60 min
    done       Nov 10 00:00         —       the chain stops; the six-hourly
                                            cron keeps scoring (runoffs, recounts)

    midterms cadence [--event E] [--run-id N] [--runs runs.json]
        prints phase=, work=, full=, chain=, next= lines for $GITHUB_OUTPUT
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

UTC = dt.timezone.utc


def _t(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


DEADLINE = _t("2026-11-03T10:00:00Z")
# (starts, phase, every minutes, minute offset of the slots)
PHASES = [
    (None, "forecast", 30, 7),
    (_t("2026-11-03T09:30:00Z"), "hold", None, None),
    (DEADLINE, "score", 60, 7),
    (_t("2026-11-03T23:00:00Z"), "results", 10, 2),
    (_t("2026-11-04T14:00:00Z"), "counting", 30, 7),
    (_t("2026-11-06T00:00:00Z"), "late", 60, 7),
    (_t("2026-11-10T00:00:00Z"), "done", None, None),
]
LIVE = {"results", "counting", "late"}      # civicAPI results are pulled every run
FULL_EVERY = 30                             # ... and Wikipedia + scoring this often


def _row(now: dt.datetime):
    row = PHASES[0]
    for p in PHASES[1:]:
        if now >= p[0]:
            row = p
    return row


def phase(now: dt.datetime) -> str:
    return _row(now)[1]


def every(now: dt.datetime) -> int | None:
    return _row(now)[2]


def next_run(now: dt.datetime) -> dt.datetime | None:
    """The first slot after `now` at the cadence of the phase it falls in
    (skipping the hold); None once the chain is done."""
    t = now.replace(second=0, microsecond=0) + dt.timedelta(minutes=1)
    for _ in range(60 * 24 * 10):
        _, name, step, off = _row(t)
        if name == "done":
            return None
        if step and (t.minute - off) % step == 0:
            return t
        t += dt.timedelta(minutes=1)
    return None


def full(now: dt.datetime) -> bool:
    """In the live phases: is this one of the runs that also re-pulls
    Wikipedia and rescores (every 30 min), not only the live results?"""
    if phase(now) not in LIVE:
        return True
    step, off = _row(now)[2], _row(now)[3]
    slot = (now.minute - off) % 60 // step * step        # this run's slot within the hour
    return slot % FULL_EVERY == 0 or step >= FULL_EVERY


def decide(now: dt.datetime, event: str, run_id: int | None = None,
           runs: list[dict] | None = None) -> dict:
    """What this run does. A dispatched run (the chain, or a manual run)
    always works and passes the chain on. A cron run is the watchdog: it
    stands aside while the chain is alive — another refresh is queued or
    running, or one started within a cadence — and restarts it otherwise."""
    ph = phase(now)
    step = every(now)
    nxt = next_run(now)
    out = {"phase": ph, "work": ph != "hold", "full": full(now),
           "chain": nxt is not None, "next": int(nxt.timestamp()) if nxt else ""}
    if ph == "done":
        out["chain"], out["next"] = False, ""
    elif event == "schedule":
        others = [r for r in (runs or []) if r.get("databaseId") != run_id]
        busy = any(r.get("status") not in ("completed", None) for r in others)
        # the chain's own runs are dispatched; a watchdog that stood aside isn't one
        last = max((_t(r["createdAt"]) for r in others
                    if r.get("event") == "workflow_dispatch" and r.get("createdAt")), default=None)
        if busy or (last is not None and now - last < dt.timedelta(minutes=(step or 30) + 5)):
            out.update(work=False, chain=False, next="")
    return out


def main(event: str = "workflow_dispatch", run_id: int | None = None,
         runs_path: str | None = None, now: dt.datetime | None = None) -> None:
    now = now or dt.datetime.now(UTC)
    runs = []
    if runs_path and Path(runs_path).exists():
        try:
            runs = json.loads(Path(runs_path).read_text() or "[]")
        except ValueError:
            runs = []
    d = decide(now, event, run_id, runs)
    for k, v in d.items():
        print(f"{k}={str(v).lower() if isinstance(v, bool) else v}")
