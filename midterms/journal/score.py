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

And head to head, on the races each one rated: every forecaster Wikipedia's
prediction tables list (Cook, Sabato, Inside Elections, DDHQ, Silver
Bulletin, The Economist, ...), scored on its final rating before Election
Day (data/ratings_final.csv) through the same map as the raters' consensus.

Metrics: Brier score, log loss, and 'calls' (P > 0.5 on the winner).
Results: data/scorecard.yaml.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import json
import math
import subprocess
from collections import defaultdict
from pathlib import Path

import yaml

from midterms.model import ratings as R
from midterms.paths import DATA, FORECAST, RACES, ROOT, SITE
from midterms.pipeline import civic, fetch
from midterms.pipeline import racepage as rp
from midterms.pipeline import races as racemod
from midterms.pipeline import states, wiki
from midterms.pipeline.htmltable import extract_tables

DEADLINE = "2026-11-03T10:00:00Z"
VERSIONS = ("lite", "classic", "deluxe")


def frozen_forecast() -> tuple[dict, Path]:
    snaps = sorted((FORECAST / "snapshots").glob("*.json"))
    eligible = [p for p in snaps if json.loads(p.read_text())["generated"] < DEADLINE]
    if not eligible:
        raise SystemExit("no snapshot generated before the deadline — nothing can be scored")
    path = eligible[-1]
    return json.loads(path.read_text()), path


MAJORITY_RULE = {"GA"}            # statewide: runoff (Dec 1) below 50%
RCV = {"ME", "AK"}                 # ranked-choice: first-round totals can mislead


def needs_majority(rid: str, state: str) -> bool:
    ch = rid.split(":")[0]
    # Maine's ranked choices are for Congress; its governor wins by plurality
    rcv = state in RCV and not (state == "ME" and ch == "governor")
    return (rcv or (state in MAJORITY_RULE and ch != "house")
            or (state == "LA" and ch == "house"))      # Louisiana: Nov 3 is round one


def resolve(rid: str, m: dict, cands: list[dict], state: str) -> dict | None:
    """One race's outcome from its called results box, or None (still open).

    Both sides need votes, and where a majority decides (Georgia, ranked-
    choice Alaska, and Maine's races for Congress) the leader needs one. Louisiana's House first
    round is scored by party. Every candidate was on one ballot, and our
    D-side and R-side there are one candidate of each party, not
    necessarily the leaders (LA-01: Jewett and Arrington; Scalise won). So
    the leader, with a majority, wins for the side of their party; the
    model forecasts the eventual party winner (method §9). A winner of
    neither side's party leaves the race open."""
    votes = {c["candidate"]: c["votes"] for c in cands if c.get("votes")}
    total = sum(votes.values())
    if rid.startswith(civic.FIRST_ROUND):
        lead = max((c for c in cands if c.get("votes")), key=lambda c: c["votes"], default=None)
        if lead is None or lead["votes"] * 2 <= total:
            return None
        side = ("D" if lead.get("party_code") == m.get("d_side") else
                "R" if lead.get("party_code") == (m.get("r_side") or "R") else None)
        if side is None:
            return None
        return {"winner_side": side, "winner_name": lead["candidate"], "margin": None}
    dv, rv = votes.get(m["d_cand"]), votes.get(m["r_cand"])
    if dv is None or rv is None:
        return None
    if needs_majority(rid, state) and max(dv, rv) <= total / 2:
        return None
    return {"winner_side": "D" if dv > rv else "R", "d_votes": dv, "r_votes": rv,
            "margin": round(100 * (dv - rv) / (dv + rv), 2)}


def outcomes() -> dict:
    """race id -> {'winner_side': 'D'|'R', 'margin', ...} (resolve()) for
    races that are *called*: the results box carries its hold/gain line, so
    partial election-night counts never resolve a race. Everything else
    stays open until a later refresh."""
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
        tables = None
        for r in rows:
            x = r["race"]
            m = meta.get(x["id"])
            if not m or m.get("fixed"):
                continue
            if tables is None:
                tables = extract_tables(page["html"])
            prefix = ""
            if ch == "house" and not x["label"].endswith("-AL"):
                prefix = f"District {int(x['label'].split('-')[1])}"
            if not rp.results_called(rp.general(tables, prefix)):
                continue
            o = resolve(x["id"], m, r["cands"], x["state"])
            if o:
                out[x["id"]] = o
    return out


def _phi(z: float) -> float:
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def _rating_sd(fc: dict) -> float:
    """The spread around a rating's implied margin: the race-level ratings
    error plus the forecast's own shared error (national, region, state)."""
    p = fc["params"]
    shared = math.sqrt(p["national"]["sd"] ** 2 + p["shared"]["sd_region"] ** 2
                       + p["shared"]["sd_state"] ** 2)
    return math.sqrt(p["ratings"]["sd"] ** 2 + shared ** 2)


def challengers(fc: dict) -> dict:
    """race id -> {contender: P(D side)} for the non-model contenders."""
    out = {}
    nat = fc["national"]["environment"]["mu"] or 0.0
    # the raters alone, through the same fitted map
    total_sd = _rating_sd(fc)
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


def score(probs: dict, res: dict, tossups: bool = False) -> dict:
    """Brier, log loss and right calls. With `tossups`, a probability of
    exactly 0.5 (a rater's Toss-up) picks no side: it counts in the Brier
    score and log loss but not in the calls, and the count is reported."""
    ids = [r for r in res if r in probs]
    if not ids:
        return {"n": 0}
    b = ll = calls = 0.0
    tu = 0
    for r in ids:
        p = min(max(probs[r], 1e-4), 1 - 1e-4)
        y = 1.0 if res[r]["winner_side"] == "D" else 0.0
        b += (p - y) ** 2
        ll += -(y * math.log(p) + (1 - y) * math.log(1 - p))
        if tossups and probs[r] == 0.5:
            tu += 1
        else:
            calls += 1.0 if (p > 0.5) == (y == 1.0) else 0.0
    n = len(ids)
    out = {"n": n, "brier": round(b / n, 4), "log_loss": round(ll / n, 4),
           "calls": f"{int(calls)}/{n - tu}"}
    if tossups:
        out["tossups"] = tu
    return out


# --- the other forecasters, head to head -------------------------------------

FINAL_RATINGS = DATA / "ratings_final.csv"
SEAL = "forecast-of-record"        # the release tag: the commit the forecast of record came from
ELECTION_EVE = "2026-11-02"        # a rating dated later can't show it came before polls opened
OTHERS_BASIS = ("each forecaster's final rating before Election Day, as Wikipedia's prediction "
                "tables list it, turned into a probability by the map the model uses for the "
                "raters' consensus; scored against the headline version on the races it rated")
COMPETITIVE_RULE = "races at least one of Cook, Sabato and Inside Elections didn't rate Safe or Solid"


def final_ratings(versions: list[tuple[str, list[dict]]]) -> list[dict]:
    """Each forecaster's final pre-election rating per race, from successive
    pulls of data/ratings.csv as (when pulled, rows). The first pull is the
    one the forecast of record used: all of it was public before polls
    opened. A later pull's rating replaces it only when it is dated strictly
    later and no later than Election Eve, a final update Wikipedia listed
    after the seal (Sabato's Nov 2 ratings). A same-date change, or a
    rating dated Election Day, is left out: its date can't show it came
    before polls opened. `seen` is when the chosen rating was first pulled."""
    out: dict[tuple[str, str], dict] = {}
    for i, (seen, rows) in enumerate(versions):
        for r in rows:
            key = (r["race"], r["rater"])
            if i == 0 or (r["asof"] <= ELECTION_EVE
                          and (key not in out or r["asof"] > out[key]["asof"])):
                out[key] = {**r, "seen": seen}
    return [out[k] for k in sorted(out)]


def freeze_ratings(path: Path = FINAL_RATINGS) -> None:
    """Write data/ratings_final.csv from the git history of data/ratings.csv
    (needs a full clone: run once, by hand, after the raters' final updates
    reach Wikipedia). Pinned, so later edits to the prediction tables can't
    change the comparison."""
    def git(*a: str) -> str:
        return subprocess.run(["git", "-C", str(ROOT), *a], capture_output=True, text=True,
                              check=True).stdout

    def utc(ts: str) -> str:
        return dt.datetime.fromtimestamp(int(ts), dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    rel = "data/ratings.csv"
    revs = [(utc(git("log", "-1", "--format=%ct", SEAL).strip()), SEAL)]
    for line in reversed(git("log", "--format=%H %ct", f"{SEAL}..HEAD", "--", rel).splitlines()):
        h, ts = line.split()
        revs.append((utc(ts), h))
    versions = [(t, list(csv.DictReader(io.StringIO(git("show", f"{rev}:{rel}"))))) for t, rev in revs]
    rows = final_ratings(versions)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["race", "rater", "source", "rating", "scale", "asof", "seen"])
        w.writeheader()
        w.writerows(rows)
    print(f"✓ {len(rows)} final ratings from {len(versions)} pulls -> {path}")


def rater_probs(fc: dict, path: Path = FINAL_RATINGS) -> tuple[dict, dict, set]:
    """({rater: {race: P(D side)}}, {rater: its full name}, the competitive
    races) from the final ratings, through the same rating -> margin ->
    probability map as the raters' consensus (a Toss-up is exactly 0.5)."""
    if not path.exists():
        return {}, {}, set()
    sd, k = _rating_sd(fc), fc["params"]["ratings"]["k"]
    probs: dict[str, dict[str, float]] = defaultdict(dict)
    names: dict[str, str] = {}
    competitive: set[str] = set()
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            if r["race"] not in fc["races"] or r["scale"] in ("", None):
                continue
            s = float(r["scale"])
            probs[r["rater"]][r["race"]] = _phi(R.implied_margin(s, k=k) / sd)
            names.setdefault(r["rater"], r["source"] or r["rater"])
            if r["rater"] in R.CORE and abs(s) < 3:
                competitive.add(r["race"])
    return dict(probs), names, competitive


def others(fc: dict, res: dict, raters: tuple[dict, dict, set]) -> dict | None:
    """Every forecaster against the headline version on the races it rated
    (and on the competitive ones among them), most races first."""
    probs, names, competitive = raters
    if not probs:
        return None
    head = fc["headline"]
    ours = {rid: r["p_d_side"] for rid, r in fc["versions"][head]["races"].items()}
    rows = []
    for name, theirs in probs.items():
        ids = {r: res[r] for r in res if r in theirs and r in ours}
        if not ids:
            continue
        row = {"name": name, "source": names.get(name, name), "n": len(ids),
               "theirs": score(theirs, ids, tossups=True), "ours": score(ours, ids)}
        comp = {r: v for r, v in ids.items() if r in competitive}
        if comp:
            row["competitive"] = {"n": len(comp), "theirs": score(theirs, comp, tossups=True),
                                  "ours": score(ours, comp)}
        rows.append(row)
    rows.sort(key=lambda r: (-r["n"], r["name"]))
    return {"basis": OTHERS_BASIS, "versus": head, "competitive_rule": COMPETITIVE_RULE,
            "raters": rows}


LIVE_URL = "https://midterms.karazajac.io/live.json"     # the web server's, newest


def latest_live() -> dict | None:
    """The newest live.json there is: the web server's (fetched) or the
    committed copy, whichever was generated later. Only real nights of the
    forecast of record count."""
    docs = []
    try:
        docs.append(json.loads(fetch.get(LIVE_URL, timeout=30, retries=2, gzip=True)))
    except (SystemExit, ValueError):
        pass
    p = SITE / "live.json"
    if p.exists():
        try:
            docs.append(json.loads(p.read_text()))
        except ValueError:
            pass
    docs = [d for d in docs if isinstance(d, dict) and isinstance(d.get("races"), dict)
            and not d.get("fixture") and (d.get("forecast") or {}).get("of_record")]
    return max(docs, key=lambda d: d.get("generated") or "") if docs else None


def provisional(fc: dict, contenders: dict, live: dict | None,
                raters: tuple[dict, dict, set] | None = None) -> dict | None:
    """The same scoreboard on the races called so far (civicAPI's decision
    desk, or Wikipedia's results where it called first): calls, not final
    results, so kept apart from the scorecard of record, which resolves
    races from Wikipedia's results boxes alone."""
    if not live:
        return None

    def side(rid: str, r: dict) -> str | None:
        """The winning side; a first-round winner who isn't one of our
        sides goes by party (live.json carries it), as in resolve()."""
        w = r.get("winner")
        if w == "other" and r.get("party"):
            d_side = (fc.get("races") or {}).get(rid, {}).get("d_side")
            w = "D" if r["party"] == d_side else "R" if r["party"] == "R" else None
        return w if w in ("D", "R") else None

    res = {rid: {"winner_side": side(rid, r)} for rid, r in live["races"].items()
           if r.get("status") == "called" and side(rid, r)}
    common = set(res)
    for probs in contenders.values():
        common &= set(probs)
    called = {r: res[r] for r in common}
    head = fc["headline"]
    rows = []
    for rid in sorted(called):
        win_d = called[rid]["winner_side"] == "D"
        p_d = fc["versions"][head]["races"][rid]["p_d_side"]
        rows.append([rid, "D" if win_d else "R", round(p_d if win_d else 1 - p_d, 4)])
    out = {"basis": "race calls so far (civicAPI's decision desk), not final results",
           "asof": live.get("generated"), "called": len(called),
           "scoreboard": {name: score(probs, called) for name, probs in contenders.items()},
           "races": rows}                           # [race, winning side, headline P(winner)]
    oth = others(fc, called, raters) if raters else None
    if oth:
        out["others"] = oth
    return out


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
            "winner_name": o.get("winner_name") or (m["d_cand"] if win_d else m["r_cand"]),
            "margin": o["margin"],                       # D-side minus R-side, two-party (None: a first round)
            "p_winner": round(p_d if win_d else 1 - p_d, 4),   # the headline version's
            "p_d_side": {v: round(fc["versions"][v]["races"][rid]["p_d_side"], 4) for v in VERSIONS},
            "called_right": (p_d > 0.5) == win_d,
        })
    out = {"forecast": path.name, "forecast_generated": fc["generated"], "deadline": DEADLINE,
           "headline": head, "resolved": len(resolved), "open": open_races[:60],
           "open_count": len(open_races), "scoreboard": board, "races": table}
    raters = rater_probs(fc)
    oth = others(fc, resolved, raters)
    if oth:
        out["others"] = oth
    prov = provisional(fc, contenders, latest_live(), raters)
    if prov:
        out["provisional"] = prov
        s = prov["scoreboard"].get(head) or {}
        if s.get("n"):
            print(f"  provisional, {prov['called']} races called (as of {prov['asof']}): "
                  f"{head} Brier {s['brier']:.4f}, calls {s['calls']}")
        rows = (prov.get("others") or {}).get("raters") or []
        if rows:
            ahead = sum(1 for r in rows if r["ours"]["brier"] < r["theirs"]["brier"])
            print(f"  head to head on their races: {head} ahead of {ahead} of {len(rows)} forecasters")
    (DATA / "scorecard.yaml").write_text(yaml.safe_dump(out, sort_keys=False))
    print(f"scoring {path.name} (generated {fc['generated']}) on {len(resolved)} resolved races")
    for name, s in sorted(board.items(), key=lambda kv: kv[1].get("brier", 9)):
        if s.get("n"):
            print(f"  {name:10s} Brier {s['brier']:.4f}  log {s['log_loss']:.4f}  calls {s['calls']}")
    print(f"  {len(open_races)} races unresolved")
    from midterms.pipeline import site_export
    site_export.main()               # scorecard.json + phase for the site
    return out
