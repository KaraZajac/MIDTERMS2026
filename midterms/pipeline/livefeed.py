"""`midterms live` — election night: live.json for the site.

Fetches every race's count and call from civicAPI (civicapi.org), maps
them onto the forecast's races, and conditions the forecast of record on
the calls so far (model/live.py). Two places run it:

  * the web server, every minute through the night:
        python3 -m midterms live --out /srv/live/…/live.json.tmp
    It writes only that file: nothing on any failure (the last good file
    stays up), no caches, no other writes. The previous file beside it
    (the same name without .tmp) carries each call's first-seen time and
    the list of calls.
  * the refresh workflow, every 10–60 minutes: data/site/live.json, the
    committed record of the night and the site's build-time fallback.
    Same shape; the site shows whichever copy is newer.

    midterms live [--out PATH] [--previous PATH] [--draws N]
    midterms live --fixture HOUR --out PATH    a simulated night (testing)

The contract is in docs/site-data.md (live.json).
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import math
from pathlib import Path

import numpy as np
import yaml

from midterms.model import live as L
from midterms.paths import CURATED, FORECAST, RACES, SITE
from midterms.pipeline import civic

DEADLINE = "2026-11-03T10:00:00Z"
DRAWS = 40000            # ~7 s on one core; ±0.2 pts of simulation noise on control
SEED = 20261103
EVENTS_KEPT = 120
MIN_MAPPED = 480          # of 506: fewer means civicAPI returned a partial list
RELIABLE_ESS = 400
FIXTURE_SEED = 3
METHOD = ("The frozen forecast of record, updated only for the races called so far: each "
          "call shifts the errors races share (national, regional, state), and the races "
          "still out follow. Partial vote counts are not used.")


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _csv(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def race_rows() -> dict[str, dict]:
    return {r["id"]: r for ch in ("house", "senate", "governor") for r in _csv(RACES / f"{ch}.csv")}


def forecast_of_record(now: str) -> tuple[dict, str, bool]:
    """After the deadline, the last snapshot generated before it (what the
    scorecard grades); before it, the latest forecast."""
    if now >= DEADLINE:
        cut = DEADLINE.replace("-", "").replace(":", "")            # 20261103T100000Z
        snaps = [p for p in sorted((FORECAST / "snapshots").glob("*.json"))
                 if p.stem.replace("-", "") < cut]
        if snaps:
            fc = json.loads(snaps[-1].read_text())
            if fc["generated"] < DEADLINE:
                return fc, snaps[-1].name, True
    return json.loads((FORECAST / "latest.json").read_text()), "latest.json", False


def _sim(fc: dict, rows: dict) -> dict:
    from midterms.pipeline.site_export import sim_params
    cur = yaml.safe_load((CURATED / "chambers.yaml").read_text())
    return sim_params(fc, cur, rows)


def _hist(h: dict) -> dict:
    xs = [x for x in sorted(h) if h[x] >= 5e-5] or sorted(h)
    lo, hi = xs[0], xs[-1]
    return {"min": lo, "p": [round(h.get(x, 0.0), 4) for x in range(lo, hi + 1)]}


def _r(x, k=4):
    return None if x is None else round(float(x), k)


def assemble(fc: dict, snapshot: str, of_record: bool, rows: dict, res: dict[str, dict],
             fetched: str | None, previous: dict | None, generated: str, *,
             draws: int = DRAWS, fixture: bool = False) -> dict:
    head = fc["headline"]
    sim = _sim(fc, rows)
    eng = L.Engine(sim, version=head)
    calls = {rid: r["winner"] for rid, r in res.items()
             if r.get("status") == "called" and not fc["races"][rid].get("fixed")}
    if calls:
        out = eng.run(calls, n=draws, seed=SEED)
    else:                   # nothing called yet: exactly the forecast of record, no simulation noise
        out = {"ess": draws, "draws": draws, "races": {rid: v["p_d_side"] for rid, v in
                                                       fc["versions"][head]["races"].items()},
               "chambers": {c: {"p_control": ch["p_control"],
                                "seats": {"mean": ch["d_seats_mean"], "p10": ch["d_seats_p10"],
                                          "p50": ch["d_seats_p50"], "p90": ch["d_seats_p90"]},
                                "hist": {int(k): v for k, v in ch["hist"].items()},
                                **({"p_control_alt": ch["p_control_alt"]} if "p_control_alt" in ch else {})}
                            for c, ch in fc["versions"][head]["chambers"].items()}}
    prev_races = (previous or {}).get("races", {})
    events = list((previous or {}).get("events", []))
    pre = fc["versions"][head]
    races = {}
    for rid, m in fc["races"].items():
        r = res.get(rid, {})
        p_pre = pre["races"][rid]["p_d_side"]
        fixed = m.get("fixed")
        status = "uncontested" if fixed else r.get("status", "awaiting")
        row = {"status": status}
        if fixed:
            row["winner"] = "D" if fixed == m.get("d_side") else "R"
        elif status == "called":
            row["winner"] = r["winner"]
            if r["winner"] == "other" and r.get("winner_name"):
                row["winner_name"] = r["winner_name"]       # the nominees are in races.json
            was = prev_races.get(rid, {})
            row["called_at"] = (was.get("called_at") if was.get("status") == "called"
                                and was.get("winner") == r["winner"] else None) or generated
            if r["winner"] in ("D", "R"):
                p_w = p_pre if r["winner"] == "D" else 1 - p_pre
                row["upset"] = p_w < 0.5
        if r.get("votes") and sum(r["votes"].values()):
            row["pct_reporting"] = r.get("pct_reporting", 0.0)
            row["votes"] = r["votes"]
            if r.get("margin") is not None:
                row["margin"] = r["margin"]
        row["p_pre"] = _r(p_pre)
        row["p_live"] = _r(out["races"][rid])
        races[rid] = row
    # the night's log: new calls, changed calls, retractions
    after = {c: _r(out["chambers"][c]["p_control"].get("D", 0)) for c in out["chambers"]}
    new_events = []
    for rid, row in races.items():
        was = prev_races.get(rid, {})
        if row["status"] == "called" and (was.get("status") != "called" or was.get("winner") != row["winner"]):
            p_pre = row["p_pre"]
            new_events.append({"t": generated, "race": rid,
                               "type": "call" if was.get("status") != "called" else "changed",
                               "winner": row["winner"],
                               "p_winner_pre": _r(p_pre if row["winner"] == "D" else 1 - p_pre)
                               if row["winner"] in ("D", "R") else None,
                               "upset": row.get("upset", False), "after": after})
        elif was.get("status") == "called" and row["status"] != "called":
            new_events.append({"t": generated, "race": rid, "type": "retracted",
                               "winner": was.get("winner"), "after": after})
    new_events.sort(key=lambda e: (e["race"].split(":")[0] != "senate", e["race"]))
    events = (new_events + events)[:EVENTS_KEPT]
    chambers = {}
    for c, ch in sim["chambers"].items():
        ids = [rid for rid, m in fc["races"].items() if m["chamber"] == c]
        party = lambda rid, w: (fc["races"][rid]["d_side"] if w == "D" else
                                (rows.get(rid, {}).get("r_side") or "R") if w == "R" else "other")
        fixed, called, upsets = {}, {}, []
        n_called = won = 0
        for rid in ids:
            row = races[rid]
            if row["status"] == "uncontested":
                p = party(rid, row["winner"])
                fixed[p] = fixed.get(p, 0) + 1
            elif row["status"] == "called":
                p = party(rid, row["winner"])
                called[p] = called.get(p, 0) + 1
                if row["winner"] in ("D", "R"):
                    n_called += 1
                    won += not row.get("upset", False)
                    if row.get("upset"):
                        upsets.append(rid)
        upsets.sort(key=lambda rid: races[rid]["p_pre"] if races[rid]["winner"] == "D"
                    else 1 - races[rid]["p_pre"])
        not_up = dict(ch.get("seats_not_up") or {})
        caucus = ch.get("caucus") or {}
        bloc = {"D": 0, "R": 0, "other": 0}
        for src in (not_up, fixed, called):
            for p, k in src.items():
                b = caucus.get(p, p)
                bloc[b if b in ("D", "R") else "other"] += k
        pc = pre["chambers"][c]
        lc = out["chambers"][c]
        chambers[c] = {
            "seats": len(ids) + sum(not_up.values()), "majority": ch["majority"],
            "not_up": not_up, "fixed": fixed, "called": called,
            "uncalled": sum(1 for rid in ids if races[rid]["status"] not in ("called", "uncontested")),
            "bloc": bloc,
            "pre": {"p_control": {k: _r(v) for k, v in pc["p_control"].items()},
                    "seats": {"mean": _r(pc["d_seats_mean"], 1), "p10": pc["d_seats_p10"],
                              "p50": pc["d_seats_p50"], "p90": pc["d_seats_p90"]}},
            "live": {"p_control": {k: _r(v) for k, v in lc["p_control"].items()},
                     **({"p_control_alt": {k: _r(v) for k, v in lc["p_control_alt"].items()}}
                        if "p_control_alt" in lc else {}),
                     "seats": {"mean": _r(lc["seats"]["mean"], 1), **{k: lc["seats"][k] for k in ("p10", "p50", "p90")}},
                     "hist": _hist(lc["hist"]),
                     "ess": out["ess"], "draws": out["draws"], "reliable": out["ess"] >= RELIABLE_ESS},
            "favorites": {"called": n_called, "won": won},
            "upsets": upsets,
        }
    statuses = [r["status"] for r in races.values()]
    counts = {s: statuses.count(s) for s in ("awaiting", "counting", "called", "runoff", "uncontested")}
    status = ("awaiting" if counts["counting"] + counts["called"] + counts["runoff"] == 0 else
              "complete" if counts["counting"] + counts["awaiting"] == 0 else "counting")
    return {
        "generated": generated, "asof": generated[:10], "fixture": fixture, "status": status,
        "source": {"name": "civicAPI", "url": "https://civicapi.org", "fetched": fetched,
                   "credit": civic.ATTRIBUTION,
                   "note": "Counts from secretaries of state; calls by civicAPI's decision desk"},
        "forecast": {"snapshot": snapshot, "generated": fc["generated"], "of_record": of_record,
                     "version": head},
        "method": METHOD,
        "counts": counts,
        "chambers": chambers,
        "races": races,
        "events": events,
    }


# ------------------------------------------------------------------ fixture

def fixture_results(fc: dict, rows: dict, hour_et: float, seed: int = FIXTURE_SEED) -> dict[str, dict]:
    """A simulated night at `hour_et` (hours after midnight Eastern, Nov 3):
    one outcome drawn from the forecast itself, counted and called the way
    the self-check's stylized decision desk does. For building the site."""
    sim = _sim(fc, rows)
    eng = L.Engine(sim, version=fc["headline"])
    rng = np.random.default_rng(seed)
    th = np.zeros(eng.D)
    th[0] = eng.c_nat * rng.standard_t(eng.nu_nat)
    th[1:] = rng.standard_normal(eng.D - 1) * eng.prior_sd[1:]
    eps = rng.standard_t(eng.nu_race, len(eng.ids)) * math.sqrt((eng.nu_race - 2) / eng.nu_race)
    margin = eng.mu + eng.A @ th + eps * eng.sd
    out = {}
    for i, rid in enumerate(eng.ids):
        m = fc["races"][rid]
        h = hour_et - L._CLOSE.get(m["state"], 21.0)
        if m.get("fixed") or h < 0:
            out[rid] = {"status": "awaiting", "votes": {"D": 0, "R": 0, "other": 0}, "pct_reporting": 0.0}
            continue
        pct = float(min(99.0, 25 + 22 * h + rng.uniform(-10, 10)))
        size = (260_000 if m["chamber"] == "house" else 3_200_000) * pct / 100
        shown = margin[i] + rng.normal(0, 6 / (1 + h))          # early counts wander
        d = size * 0.98 * (0.5 + max(-49.0, min(49.0, shown)) / 200)
        votes = {"D": int(d), "R": int(size * 0.98 - d), "other": int(size * 0.02)}
        row = {"votes": votes, "pct_reporting": round(pct, 1),
               "margin": round(100 * (votes["D"] - votes["R"]) / max(1, votes["D"] + votes["R"]), 1)}
        if L._called(margin[i], h):
            w = "D" if margin[i] > 0 else "R"
            row.update(status="called", winner=w, winner_name=m["d_cand"] if w == "D" else m["r_cand"])
        else:
            row["status"] = "counting"
        out[rid] = row
    return out


# --------------------------------------------------------------------- main

def _previous(out: Path | None, explicit: str | None) -> dict | None:
    cands = [Path(explicit)] if explicit else []
    if out is not None and out.name.endswith(".tmp"):
        cands.append(out.with_name(out.name[:-4]))
    cands.append(SITE / "live.json")
    for p in cands:
        try:
            if p.exists():
                doc = json.loads(p.read_text())
                if isinstance(doc, dict) and isinstance(doc.get("races"), dict) and not doc.get("fixture"):
                    return doc
        except (OSError, ValueError):
            continue
    return None


def main(out: str | None = None, previous: str | None = None, draws: int = DRAWS,
         fixture: float | None = None, seed: int = FIXTURE_SEED) -> None:
    generated = now_utc()
    rows = race_rows()
    if fixture is not None:
        fc, snapshot, of_record = forecast_of_record(generated)
        res, fetched = fixture_results(fc, rows, fixture, seed=seed), None
        prev = json.loads(Path(previous).read_text()) if previous else None      # a fixture sequence
    else:
        civic_races, fetched = civic.fetch_all()
        res = civic.results(civic_races, rows)
        if len(res) < MIN_MAPPED:
            raise SystemExit(f"civicapi: only {len(res)} of {len(rows)} races mapped — not writing")
        fc, snapshot, of_record = forecast_of_record(generated)
        prev = _previous(Path(out) if out else None, previous)
    doc = assemble(fc, snapshot, of_record, rows, res, fetched, prev, generated,
                   draws=draws, fixture=fixture is not None)
    text = json.dumps(doc, separators=(",", ":"), ensure_ascii=False)
    path = Path(out) if out else SITE / "live.json"
    path.write_text(text)
    h, s, g = (doc["chambers"][c]["live"]["p_control"].get("D", 0) for c in ("house", "senate", "governor"))
    print(f"✓ live ({doc['status']}{', FIXTURE' if doc['fixture'] else ''}): {doc['counts']['called']} called, "
          f"{doc['counts']['counting']} counting; D control — House {h:.1%}, Senate {s:.1%}, "
          f"governors {g:.1%}; ess {doc['chambers']['house']['live']['ess']}; {len(text) / 1024:.0f} KB -> {path}")
