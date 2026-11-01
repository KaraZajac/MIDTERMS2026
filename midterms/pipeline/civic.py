"""civicAPI (civicapi.org): election-night results and race calls.

civicAPI aggregates results from secretaries of state (refreshed every
5–10 seconds while votes are counted) and calls races with its own
decision desk. It is free and needs no key; its terms: "free for all
personal, non-commercial, or commercial purposes … Attribution is required
for non-personal projects — please either link to civicapi.org or list our
name somewhere." Two searches cover every race the model forecasts:

    race/search?…&election_type=General           435 House districts and
                                                  the 35 Senate races (plus
                                                  state-legislative rows,
                                                  dropped)
    race/search?…&query=Governor&election_type=Statewide
                                                  the 36 governors (plus
                                                  territories, dropped)

Each civicAPI race maps to one of ours by office, state and district, and
each candidate to our D-side or R-side by name (surname, then first name:
Alaska has two Dan Sullivans). `check()` reports anything that doesn't
map, so a gap shows up before Election Day rather than at 9 PM.

Results are display and conditioning data only: the scorecard still
resolves races from Wikipedia's results boxes (journal/score.py).
"""

from __future__ import annotations

import json
from difflib import SequenceMatcher
from urllib.parse import urlencode

from midterms.pipeline import fetch
from midterms.pipeline.votehub import _name_tokens

SEARCH = "https://civicapi.org/api/v2/race/search"
ELECTION = "2026-11-03"
QUERIES = {
    "federal": {"election_type": "General"},
    "governors": {"query": "Governor", "election_type": "Statewide"},
}
PAGE = 1000
UA = "MIDTERMS2026-live/0.1 (+https://midterms.karazajac.io)"
ATTRIBUTION = "Results and race calls: civicAPI (civicapi.org)"
TYPES = {"House of Representatives": "house", "US Senate": "senate", "Governor": "governor"}
MAJORITY_RULE = {"GA"}             # a runoff when no one passes 50% (Dec 1)


def url(name: str, offset: int = 0) -> str:
    q = {"startDate": ELECTION, "endDate": ELECTION, "country": "US", "limit": PAGE,
         "offset": offset, **QUERIES[name]}
    return f"{SEARCH}?{urlencode(q)}"


def fetch_all(*, timeout: int = 12, retries: int = 1) -> tuple[list[dict], str]:
    """Every race of both searches (paged), and when they were fetched.
    Raises SystemExit on any failure: a partial picture is never used."""
    races, fetched = [], fetch.now_utc()
    for name in QUERIES:
        offset = 0
        while True:
            raw = fetch.get(url(name, offset), timeout=timeout, retries=retries,
                            headers={"User-Agent": UA, "Accept": "application/json"})
            try:
                page = json.loads(raw)
                batch, count = page["races"], int(page["count"])
            except (ValueError, KeyError, TypeError) as e:
                raise SystemExit(f"civicapi: unreadable {name} page at offset {offset}: {e}")
            races += batch
            offset += len(batch)
            if not batch or offset >= count:
                break
    return races, fetched


def race_id(c: dict, ids: set[str]) -> str | None:
    """Our race id for a civicAPI race, or None (a territory, a summary
    row, an office the model doesn't cover)."""
    chamber = TYPES.get(c.get("type"))
    st = (c.get("province") or "").upper()
    if chamber is None or c.get("country") != "US" or len(st) != 2 or st == "US":
        return None
    if chamber == "house":
        rid = f"house:{(c.get('district') or '').upper()}"
    else:
        rid = f"{chamber}:{st}"
        if rid not in ids and f"{rid}-special" in ids:
            rid += "-special"                    # Ohio's and Florida's 2026 seats
    return rid if rid in ids else None


def _find(cands: list[dict], name: str) -> int | None:
    """The candidate who is this nominee: the same surname (then first
    name, when two share it); else the surname among their names ('Terri
    Yarbrough' is 'Terri Yarbrough Green'); else one clearly closest
    spelling (Wikipedia's 'James Duffe' is civicAPI's 'James Duffie')."""
    want = _name_tokens(name or "")
    if not want:
        return None
    toks = [_name_tokens(c.get("name", "")) for c in cands]
    hits = [i for i, t in enumerate(toks) if t[-1:] == want[-1:]]
    if len(hits) > 1:
        hits = [i for i in hits if toks[i][:1] == want[:1]]
    if len(hits) == 1:
        return hits[0]
    if hits:
        return None
    hits = [i for i, t in enumerate(toks) if want[-1] in t]
    if len(hits) == 1:
        return hits[0]
    score = sorted(((SequenceMatcher(None, want[-1], t[-1]).ratio() if t else 0.0, i)
                    for i, t in enumerate(toks)), reverse=True)
    if score and score[0][0] >= 0.8 and (len(score) == 1 or score[1][0] < 0.6):
        return score[0][1]
    # a transposed surname ('Esti' / 'Etsi'): the one candidate with the
    # same first name and a surname of the same letters
    hits = [i for i, t in enumerate(toks)
            if t[:1] == want[:1] and len(t) > 1 and sorted(t[-1]) == sorted(want[-1])]
    return hits[0] if len(hits) == 1 else None


def result(c: dict, race: dict) -> dict:
    """One race's state of play, by our sides: D (the D-side nominee),
    R (the R-side nominee), other (everyone else)."""
    cands = c.get("candidates") or []
    i_d, i_r = _find(cands, race.get("d_cand")), _find(cands, race.get("r_cand"))
    if i_d is not None and i_d == i_r:                   # never one candidate on both sides
        i_d = i_r = None
    votes = {"D": 0, "R": 0, "other": 0}
    winners = []
    for i, x in enumerate(cands):
        side = "D" if i == i_d else "R" if i == i_r else "other"
        try:
            votes[side] += int(x.get("votes") or 0)
        except (TypeError, ValueError):
            pass
        if x.get("winner") is True:
            winners.append((side, x.get("name")))
    try:
        pct = float(c.get("percent_reporting") or 0)
    except (TypeError, ValueError):
        pct = 0.0
    total = sum(votes.values())
    out = {"civic_id": c.get("id"), "matched": {"D": i_d is not None, "R": i_r is not None},
           "pct_reporting": round(pct, 1), "votes": votes}
    if len(winners) == 1:
        out.update(status="called", winner=winners[0][0], winner_name=winners[0][1])
    elif total == 0:
        out.update(status="awaiting", winner=None)
    else:
        lead = max(votes["D"], votes["R"], votes["other"])
        runoff = (race.get("state") in MAJORITY_RULE and pct >= 99 and lead * 2 <= total)
        out.update(status="runoff" if runoff else "counting", winner=None)
    if total:
        out["pct"] = {k: round(100 * v / total, 1) for k, v in votes.items()}
        two = votes["D"] + votes["R"]
        if two and out["matched"]["D"] and out["matched"]["R"]:
            out["margin"] = round(100 * (votes["D"] - votes["R"]) / two, 1)
    return out


def results(civic_races: list[dict], races: dict[str, dict]) -> dict[str, dict]:
    """race id -> result, for every forecast race civicAPI lists."""
    ids = set(races)
    out = {}
    for c in civic_races:
        rid = race_id(c, ids)
        if rid is None:
            continue
        if rid in out:                                   # a duplicate row: keep the fuller one
            if sum(out[rid]["votes"].values()) >= sum(int(x.get("votes") or 0)
                                                      for x in c.get("candidates") or []):
                continue
        out[rid] = result(c, races[rid])
    return out


def check(civic_races: list[dict], races: dict[str, dict]) -> list[str]:
    """Every way the map could fail on the night: a contested race civicAPI
    doesn't list, or a nominee it lists under a name we can't match."""
    res = results(civic_races, races)
    problems = []
    for rid, r in sorted(races.items()):
        if r.get("fixed"):
            continue
        if rid not in res:
            problems.append(f"{rid}: not in civicAPI")
            continue
        for side, key in (("D", "d_cand"), ("R", "r_cand")):
            if r.get(key) and not res[rid]["matched"][side]:
                names = [x.get("name") for x in next(
                    c for c in civic_races if c.get("id") == res[rid]["civic_id"])["candidates"]]
                problems.append(f"{rid}: {side}-side {r[key]!r} not among {names}")
    return problems
