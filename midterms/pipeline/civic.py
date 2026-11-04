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
    race/search?…&election_type=Statewide&type=Governor
                                                  the 36 governors (plus
                                                  territories, dropped)

(The governors' search used `query=Governor`, a text search, until civicAPI
began answering it with 503 DATABASE_TIMEOUT on the morning of Nov 3; the
`type` filter returns the same races and does not time out.)

Each civicAPI race maps to one of ours by office, state and district, and
each candidate to our D-side or R-side by name (surname, then first name:
Alaska has two Dan Sullivans). `check()` reports anything that doesn't
map, so a gap shows up before Election Day rather than at 9 PM.

Results are display and conditioning data only: the scorecard still
resolves races from Wikipedia's results boxes (journal/score.py).
"""

from __future__ import annotations

import datetime as dt
import json
import time
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import urlencode

from midterms.pipeline import fetch
from midterms.pipeline.votehub import _name_tokens

SEARCH = "https://civicapi.org/api/v2/race/search"
ELECTION = "2026-11-03"
QUERIES = {
    "federal": {"election_type": "General"},
    "governors": {"election_type": "Statewide", "type": "Governor"},
}
PAGE = 1000
UA = "MIDTERMS2026-live/0.1 (+https://midterms.karazajac.io)"
ATTRIBUTION = "Results and race calls: civicAPI (civicapi.org)"
TYPES = {"House of Representatives": "house", "US Senate": "senate", "Governor": "governor"}
MAJORITY_RULE = {"GA"}             # a runoff when no one passes 50% (Dec 1)
# Louisiana's House: every candidate on one ballot on Nov 3; a majority wins,
# else the top two meet on Dec 12. Our D-side and R-side there are one
# candidate of each party and needn't be the leaders (LA-01's are Jewett and
# Arrington; Scalise won), so these races get no side margin, their top two
# instead, and an outright winner's party.
FIRST_ROUND = "house:LA-"
PARTY = {"Democratic": "D", "Republican": "R", "Libertarian": "L", "Green": "G"}


def party_code(label) -> str:
    """civicAPI's party label as ours: D, R, L, G; anyone else IND."""
    label = str(label or "")
    return next((code for name, code in PARTY.items() if label.startswith(name)), "IND")


def url(name: str, offset: int = 0) -> str:
    q = {"startDate": ELECTION, "endDate": ELECTION, "country": "US", "limit": PAGE,
         "offset": offset, **QUERIES[name]}
    return f"{SEARCH}?{urlencode(q)}"


# civicAPI's searches take 6–10 s to a first byte when its own cache is cold
# (measured Nov 3), which a once-a-minute poll always meets, and at 14:00 UTC
# on Nov 3 it answered two quick tries with 503. So a read may wait TIMEOUT
# seconds, and a failed one (429, 5xx, a network error or a timeout) is tried
# again after 2, 4, 8, then every 10 seconds, or the server's Retry-After, for
# as long as the whole fetch has time left: BUDGET seconds, well inside the
# web server's 110-second limit on the job. TIMEOUT was 25 until 22:58 UTC on
# Nov 3, when three 25-second reads of the governors' search in a row went
# unanswered as the first polls closed: giving up on a slow read only asks
# the same slow search again, so the first read now waits 50 seconds, and a
# second gets what is left of the budget.
TIMEOUT = 50
BUDGET = 80
RETRY = {429, 500, 502, 503, 504, 520, 521, 522, 523, 524}   # 52x: Cloudflare, civicAPI's front


def _get(u: str, deadline: float) -> bytes:
    delay = 2.0
    while True:
        left = deadline - time.monotonic()
        try:
            return fetch.get(u, timeout=max(5, min(TIMEOUT, int(left))), retries=1, gzip=True,
                             headers={"User-Agent": UA, "Accept": "application/json"})
        except fetch.DownloadFailed as e:
            if e.status is not None and e.status not in RETRY:
                raise                                   # a 4xx won't fix itself
            # a 429's Retry-After is honored (to 30 s); a 5xx's only to 10 s:
            # civicAPI's 502s, which come back in 0.2 s, ask for 30 s or more,
            # which left a run two or three tries at a search (Nov 3, 01:00 UTC)
            wait = min(max(delay, e.retry_after or 0.0), 30.0 if e.status == 429 else 10.0)
            if deadline - time.monotonic() < wait + 5:
                raise
            time.sleep(wait)
            delay = min(2 * delay, 10.0)


def _search(name: str, deadline: float) -> list[dict]:
    races, offset = [], 0
    while True:
        raw = _get(url(name, offset), deadline)
        try:
            page = json.loads(raw)
            batch, count = page["races"], int(page["count"])
        except (ValueError, KeyError, TypeError) as e:
            raise SystemExit(f"civicapi: unreadable {name} page at offset {offset}: {e}")
        races += batch
        offset += len(batch)
        if not batch or offset >= count:
            return races


# On election night civicAPI's two searches failed by turns (five runs of the
# web server's job between 23:07 and 00:23 UTC, each on one search, while the
# other answered). So the web server keeps each search's last answer beside
# its live.json, and when one search still fails after its retries, its last
# answer stands in if it is at most KEEP seconds old (live.json says so)
# rather than the whole minute's update being lost. If both fail, nothing
# stands in: the run fails and the last good file stays up, as before.
KEEP = 300
# The governors' search failed alone for long stretches (04:30 UTC on, Nov 4),
# and at 5 minutes its kept answer ran out while the House and Senate still
# answered, so whole fresh updates were lost. Governors' results move slowly:
# their last answer may stand in for 30 minutes; the House and Senate's for 5.
KEEPS = {"federal": KEEP, "governors": 1800}


def _kept_path(cache: Path, name: str) -> Path:
    return cache / f".civic-{name}.json"


def _keep(cache: Path, name: str, fetched: str, races: list[dict]) -> None:
    """Keep a search's answer for the next run (best effort)."""
    path = _kept_path(cache, name)
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(json.dumps({"fetched": fetched, "races": races}, separators=(",", ":")))
        tmp.replace(path)
    except OSError:
        pass


def _kept(cache: Path, name: str, keep: float) -> tuple[list[dict], str] | None:
    """A search's kept answer and when it was fetched, if at most `keep`
    seconds old."""
    try:
        doc = json.loads(_kept_path(cache, name).read_text())
        when = dt.datetime.strptime(doc["fetched"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
        races = doc["races"]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    age = (dt.datetime.now(dt.timezone.utc) - when).total_seconds()
    if not isinstance(races, list) or not 0 <= age <= keep:
        return None
    return races, doc["fetched"]


def fetch_all(*, budget: float = BUDGET, cache: Path | None = None,
              keep: float | None = None) -> tuple[list[dict], str, dict[str, str]]:
    """Every race of both searches (paged; the two run side by side), when
    they were fetched, and the searches that stood in with an earlier answer
    ({name: when that answer was fetched}). Failed reads are retried while
    `budget` seconds last. With a `cache` directory each search's answer is
    kept there, and one failed search is answered from its kept answer if
    that is at most `keep` seconds old. Otherwise any failure raises
    SystemExit: a partial picture is never used."""
    from concurrent.futures import ThreadPoolExecutor
    fetched = fetch.now_utc()
    deadline = time.monotonic() + budget
    with ThreadPoolExecutor(max_workers=len(QUERIES)) as pool:
        jobs = {name: pool.submit(_search, name, deadline) for name in QUERIES}
    answers, errors = {}, {}
    for name, job in jobs.items():
        try:
            answers[name] = job.result()
        except SystemExit as e:
            errors[name] = e
            print(f"  ! civicAPI {name}: {e}", flush=True)       # each failed search, in the log
            continue
        if cache is not None:
            _keep(cache, name, fetched, answers[name])
    stood_in, fresh = {}, bool(answers)              # something must be new this run
    for name, e in errors.items():
        limit = keep if keep is not None else KEEPS.get(name, KEEP)
        old = _kept(cache, name, limit) if cache is not None and fresh else None
        if old is None:
            raise e
        answers[name], stood_in[name] = old
    return [r for name in QUERIES for r in answers[name]], fetched, stood_in


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
    R (the R-side nominee), other (everyone else). In a first round
    (FIRST_ROUND), the top two instead of a side margin, and the party of
    an outright winner who isn't one of our sides."""
    cands = c.get("candidates") or []
    first = str(race.get("id") or "").startswith(FIRST_ROUND)
    i_d, i_r = _find(cands, race.get("d_cand")), _find(cands, race.get("r_cand"))
    if i_d is not None and i_d == i_r:                   # never one candidate on both sides
        i_d = i_r = None
    # a last resort if a name stops matching on the night: the one candidate
    # of the side's major party (never for independents, who are many)
    for side, want in (("D", "Democratic"), ("R", "Republican")):
        if (i_d if side == "D" else i_r) is not None or race.get(f"{side.lower()}_side") != side:
            continue
        taken = i_r if side == "D" else i_d
        hits = [i for i, x in enumerate(cands) if i != taken and str(x.get("party", "")).startswith(want)]
        if len(hits) == 1:
            if side == "D":
                i_d = hits[0]
            else:
                i_r = hits[0]
    votes = {"D": 0, "R": 0, "other": 0}
    each = []                                            # every candidate's votes, in order
    winners = []
    for i, x in enumerate(cands):
        side = "D" if i == i_d else "R" if i == i_r else "other"
        try:
            v = int(x.get("votes") or 0)
        except (TypeError, ValueError):
            v = 0
        votes[side] += v
        each.append(v)
        if x.get("winner") is True:
            winners.append((side, x.get("name"), x.get("party")))
    try:
        pct = float(c.get("percent_reporting") or 0)
    except (TypeError, ValueError):
        pct = 0.0
    total = sum(votes.values())
    out = {"civic_id": c.get("id"), "matched": {"D": i_d is not None, "R": i_r is not None},
           "pct_reporting": round(pct, 1), "votes": votes}
    if len(winners) == 1:
        out.update(status="called", winner=winners[0][0], winner_name=winners[0][1])
        if first and winners[0][0] == "other":
            out["party"] = party_code(winners[0][2])
    elif total == 0:
        out.update(status="awaiting", winner=None)
    else:
        lead = max(each)                                 # one candidate, never a side's lump
        runoff = ((first or race.get("state") in MAJORITY_RULE) and pct >= 99 and lead * 2 <= total)
        out.update(status="runoff" if runoff else "counting", winner=None)
    if total:
        out["pct"] = {k: round(100 * v / total, 1) for k, v in votes.items()}
        two = votes["D"] + votes["R"]
        if two and out["matched"]["D"] and out["matched"]["R"] and not first:
            out["margin"] = round(100 * (votes["D"] - votes["R"]) / two, 1)
        if first:
            top = sorted(range(len(cands)), key=lambda i: -each[i])[:2]
            out["top_two"] = [{"name": cands[i].get("name"), "party": party_code(cands[i].get("party")),
                               "votes": each[i]} for i in top if each[i] > 0]
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
