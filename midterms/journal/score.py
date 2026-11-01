"""`midterms score` — the scorecard, after results land.

The record is strictly ex-ante. The forecast that counts is the last
snapshot in data/forecast/snapshots/ generated before polls open on
Election Day (DEADLINE: 06:00 Eastern, Nov 3 = 10:00 UTC; Hawaii and Alaska
close later but nothing generated after the first polls open is scored).

Results come from the same Wikipedia results boxes that named the
candidates (`midterms pull --only wiki --force` after Election Day), so
the resolution source is CC BY-SA and pinned by revision like every input.
A race resolves when its box carries votes for both sides; races whose
winner isn't settled (a Georgia runoff, a Louisiana Dec 12 runoff, RCV
tabulation, a recount) stay open and are listed.

Scored, on identical resolved races, for every contender:

  lite / classic / deluxe   this model's three versions
  ratings                   Cook/Sabato/Inside Elections consensus, through
                            the same rating -> margin -> probability map
  lean-only                 partisan lean + generic ballot, nothing else
  coin-flip                 0.5 everywhere (the floor)

Metrics: Brier score, log loss, and 'calls' (P > 0.5 on the winner).
Results: data/scorecard.yaml.
"""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path

import yaml

from midterms.model import ratings as R
from midterms.paths import DATA, FORECAST, RACES
from midterms.pipeline import races as racemod
from midterms.pipeline import states, wiki

DEADLINE = "2026-11-03T10:00:00Z"
VERSIONS = ("lite", "classic", "deluxe")


def frozen_forecast() -> tuple[dict, Path]:
    snaps = sorted((FORECAST / "snapshots").glob("*.json"))
    eligible = [p for p in snaps if json.loads(p.read_text())["generated"] < DEADLINE]
    if not eligible:
        raise SystemExit("no snapshot generated before the deadline — nothing can be scored")
    path = eligible[-1]
    return json.loads(path.read_text()), path


def outcomes() -> dict:
    """race id -> {'winner_side': 'D'|'R', 'd_votes', 'r_votes'} for races
    whose results box has votes for both sides."""
    meta = {}
    for ch in ("house", "senate", "governor"):
        with open(RACES / f"{ch}.csv", newline="") as f:
            for r in csv.DictReader(f):
                meta[r["id"]] = r
    out = {}
    for rid, ch, title in states.race_pages():
        page = wiki.fetch_page(title, max_age_hours=None)
        rows = (racemod.house_state(rid.split(":")[1], page) if ch == "house"
                else [racemod.statewide(rid, ch, rid.split(":")[1][:2], page)])
        for r in rows:
            x = r["race"]
            m = meta.get(x["id"])
            if not m or m.get("fixed"):
                continue
            votes = {c["candidate"]: c["votes"] for c in r["cands"] if c.get("votes")}
            dv, rv = votes.get(m["d_cand"]), votes.get(m["r_cand"])
            if dv is None or rv is None:
                continue
            out[x["id"]] = {"winner_side": "D" if dv > rv else "R", "d_votes": dv, "r_votes": rv,
                            "margin": round(100 * (dv - rv) / (dv + rv), 2)}
    return out


def _phi(z: float) -> float:
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def challengers(fc: dict) -> dict:
    """race id -> {contender: P(D side)} for the non-model contenders."""
    out = {}
    nat = fc["national"]["environment"]["mu"] or 0.0
    total_sd = 6.5    # the rating map's calibration scale (see model/ratings.py)
    for rid, meta in fc["races"].items():
        det = fc["detail"].get(rid) or {}
        c = {"coin-flip": 0.5}
        E = det.get("ratings")
        if E:
            c["ratings"] = _phi(E["mu"] / total_sd)
        lean = meta.get("lean")
        if lean not in (None, ""):
            c["lean-only"] = _phi((float(lean) + nat) / 7.0)
        out[rid] = c
    return out


def score(probs: dict, res: dict) -> dict:
    ids = [r for r in res if r in probs]
    if not ids:
        return {"n": 0}
    b = ll = calls = 0.0
    for r in ids:
        p = min(max(probs[r], 1e-4), 1 - 1e-4)
        y = 1.0 if res[r]["winner_side"] == "D" else 0.0
        b += (p - y) ** 2
        ll += -(y * math.log(p) + (1 - y) * math.log(1 - p))
        calls += 1.0 if (p > 0.5) == (y == 1.0) else 0.0
    n = len(ids)
    return {"n": n, "brier": round(b / n, 4), "log_loss": round(ll / n, 4),
            "calls": f"{int(calls)}/{n}"}


def main() -> dict:
    fc, path = frozen_forecast()
    res = outcomes()
    ch = challengers(fc)
    contenders = {v: {rid: r["p_d_side"] for rid, r in fc["versions"][v]["races"].items()}
                  for v in VERSIONS}
    for name in ("ratings", "lean-only", "coin-flip"):
        contenders[name] = {rid: c[name] for rid, c in ch.items() if name in c}
    # every contender scored on the same races: those all of them priced
    common = set(res)
    for probs in contenders.values():
        common &= set(probs)
    resolved = {r: res[r] for r in common}
    board = {name: score(probs, resolved) for name, probs in contenders.items()}
    open_races = sorted(set(fc["races"]) - set(res) - {r for r, m in fc["races"].items() if m.get("fixed")})
    head = fc["headline"]
    table = []
    for rid in sorted(resolved):
        m, o = fc["races"][rid], resolved[rid]
        win_d = o["winner_side"] == "D"
        p_d = fc["versions"][head]["races"][rid]["p_d_side"]
        table.append({
            "id": rid, "slug": rid.split(":")[0] + "/" + rid.split(":")[1].lower(),
            "label": m["label"],
            "winner": m["d_side"] if win_d else "R",
            "winner_name": m["d_cand"] if win_d else m["r_cand"],
            "margin": o["margin"],                       # D-side minus R-side, two-party
            "p_winner": round(p_d if win_d else 1 - p_d, 4),   # the headline version's
            "p_d_side": {v: round(fc["versions"][v]["races"][rid]["p_d_side"], 4) for v in VERSIONS},
            "called_right": (p_d > 0.5) == win_d,
        })
    out = {"forecast": path.name, "forecast_generated": fc["generated"], "deadline": DEADLINE,
           "headline": head, "resolved": len(resolved), "open": open_races[:60],
           "open_count": len(open_races), "scoreboard": board, "races": table}
    (DATA / "scorecard.yaml").write_text(yaml.safe_dump(out, sort_keys=False))
    print(f"scoring {path.name} (generated {fc['generated']}) on {len(resolved)} resolved races")
    for name, s in sorted(board.items(), key=lambda kv: kv[1].get("brier", 9)):
        if s.get("n"):
            print(f"  {name:10s} Brier {s['brier']:.4f}  log {s['log_loss']:.4f}  calls {s['calls']}")
    print(f"  {len(open_races)} races unresolved")
    from midterms.pipeline import site_export
    site_export.main()               # scorecard.json + phase for the site
    return out
