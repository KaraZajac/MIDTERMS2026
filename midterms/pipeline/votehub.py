"""VoteHub's public polls API (api.votehub.com/polls, CC BY 4.0) as a
supplement to Wikipedia's poll tables.

Wikipedia stays the poll ledger of record; VoteHub only adds the
general-election polls those tables are missing. A VoteHub poll joins the
ledger when

  * it polls a 2026 race the model covers, between that race's two sides
    (each side's nominee found by name among its answers), and
  * no Wikipedia poll of the same race could be the same poll: none from
    the same pollster (or a sponsor) ending within 7 days, and none ending
    within 4 days with the same sample size or the same topline (both
    shares within half a point), and
  * its pollster isn't a known fabricator (curated/excluded_pollsters.yaml:
    the feed still carried Wedgewood's fake polls on 2026-11-01, weeks
    after Wikipedia and the other aggregators dropped them).

Doubt counts as a match. A poll counted twice gets double weight in its
race's average; a poll skipped costs only a little information.
"""

from __future__ import annotations

import csv
import datetime
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

from midterms.model import pollsters as PQ
from midterms.paths import SOURCES
from midterms.pipeline import excluded
from midterms.pipeline.states import ABBR, AT_LARGE

PATH = SOURCES / "votehub" / "polls.json"
TYPES = {"us-senator": "senate", "governor": "governor", "us-representative": "house"}
POPULATION = {"lv": "LV", "rv": "RV", "a": "A", "v": "V"}
PARTISAN = {"DEM": "D", "REP": "R"}
UNDECIDED = re.compile(r"undecided|not sure|unsure|don.?t know|no opinion|refused", re.I)
SUFFIXES = {"jr", "sr", "ii", "iii", "iv"}
# words too common in pollster names to identify one ('Public Policy
# Polling' and 'Public Opinion Strategies' share nothing that remains)
COMMON = {"the", "and", "for", "university", "college", "research", "group", "polling", "poll",
          "polls", "strategies", "strategy", "insights", "associates", "partners", "company",
          "inc", "llc", "news", "center", "institute", "public", "opinion", "survey", "surveys",
          "policy", "data", "analytics", "communications", "consulting", "media", "affairs",
          "school", "lab", "state", "studies"}
SAME_POLLSTER_DAYS = 7
SAME_NUMBERS_DAYS = 4


def load(path: Path = PATH) -> list[dict]:
    return json.loads(path.read_text())


def _ascii(s: str) -> str:
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()


def _name_tokens(name: str) -> list[str]:
    s = re.sub(r"\(.*?\)|\".*?\"", " ", _ascii(name))
    s = re.sub(r"[^a-z' -]", " ", s).replace("-", " ").replace("'", "")
    return [t for t in s.split() if t not in SUFFIXES]


def race_id(p: dict, race_ids: set[str]) -> str | None:
    """The model's race id for a VoteHub poll, or None (another year, a
    primary, an office the model doesn't cover)."""
    chamber = TYPES.get(p.get("poll_type"))
    year, _, rest = (p.get("subject") or "").strip().partition(" ")
    if chamber is None or year != "2026":
        return None
    if chamber == "house":
        m = re.fullmatch(r"([A-Z]{2})-(\d{1,2})", (p.get("seat_name") or rest).strip())
        if not m:
            return None
        st, n = m.group(1), int(m.group(2))
        rid = f"house:{st}-AL" if st in AT_LARGE else f"house:{st}-{n:02d}"
    else:
        st = ABBR.get(rest.strip())           # 'Texas Republican' (a primary) -> None
        if not st:
            return None
        rid = f"{chamber}:{st}"
        if rid not in race_ids and f"{rid}-special" in race_ids:
            rid += "-special"                 # Ohio's and Florida's 2026 seats are specials
    return rid if rid in race_ids else None


def find_answer(answers: list[dict], name: str) -> dict | None:
    """The answer naming this nominee: by surname, then by first name when
    two answers share the surname (Alaska has two Dan Sullivans)."""
    want = _name_tokens(name)
    if not want:
        return None
    hits = [a for a in answers if _name_tokens(a.get("choice", ""))[-1:] == want[-1:]]
    if len(hits) > 1:
        hits = [a for a in hits if _name_tokens(a["choice"])[:1] == want[:1]]
    return hits[0] if len(hits) == 1 else None


def candidate_rows(polls: list[dict], races: dict[str, dict], until: str) -> list[dict]:
    """VoteHub polls of each race's two sides, as data/polls/races.csv rows
    (one per poll and population; when a poll asked several versions of
    the question, the one with the fewest choices: the head-to-head or a
    ranked-choice final round)."""
    ids = set(races)
    best: dict[tuple, tuple[int, dict]] = {}
    for p in polls:
        rid = race_id(p, ids)
        if rid is None:
            continue
        race = races[rid]
        if race.get("fixed") or not race.get("d_cand") or not race.get("r_cand"):
            continue
        end = p.get("end_date") or ""
        try:
            datetime.date.fromisoformat(end)
        except ValueError:
            continue
        if end > until:
            continue
        answers = [a for a in p.get("answers") or []
                   if isinstance(a.get("pct"), (int, float)) and a.get("choice")]
        da, ra = find_answer(answers, race["d_cand"]), find_answer(answers, race["r_cand"])
        if da is None or ra is None or da is ra:
            continue
        rest = [a for a in answers if a is not da and a is not ra]
        undecided = [a["pct"] for a in rest if UNDECIDED.search(a["choice"])]
        other = [a["pct"] for a in rest if not UNDECIDED.search(a["choice"])]
        row = {"race": rid, "pollster": p.get("pollster") or "",
               "partisan": PARTISAN.get(p.get("partisan") or "", ""),
               "start": p.get("start_date") or "", "end": end, "n": p.get("sample_size") or "",
               "population": POPULATION.get((p.get("population") or "").lower(), ""),
               "d": float(da["pct"]), "r": float(ra["pct"]),
               "other": round(sum(other), 1) if other else "",
               "undecided": round(sum(undecided), 1) if undecided else "",
               "d_label": da["choice"], "r_label": ra["choice"],
               "source": f"votehub:{p.get('id')}", "table": "", "url": p.get("url") or "",
               "_sponsors": list(p.get("sponsors") or [])}
        key = (rid, PQ.canon(row["pollster"]), end, row["population"])
        if key not in best or len(answers) < best[key][0]:
            best[key] = (len(answers), row)
    return sorted((r for _, r in best.values()), key=lambda r: (r["race"], r["end"], r["pollster"]))


def _words(*names: str) -> set[str]:
    out = set()
    for n in names:
        out |= {w for w in re.sub(r"[^a-z0-9 ]", " ", _ascii(n)).split()
                if len(w) > 2 and w not in COMMON}
    return out


def _num(x) -> float | None:
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _days(a: str, b: str) -> int:
    return abs((datetime.date.fromisoformat(a) - datetime.date.fromisoformat(b)).days)


def is_duplicate(v: dict, w: dict) -> bool:
    """Could VoteHub row v be Wikipedia row w (same race) under another name?"""
    gap = _days(v["end"], w["end"])
    same_pollster = (PQ.canon(v["pollster"]) == PQ.canon(w["pollster"])
                     or bool(_words(v["pollster"], *v.get("_sponsors", [])) & _words(w["pollster"])))
    if same_pollster and gap <= SAME_POLLSTER_DAYS:
        return True
    if gap > SAME_NUMBERS_DAYS:
        return False
    nv, nw = _num(v.get("n")), _num(w.get("n"))
    if nv and nw and nv == nw:
        return True
    dv, rv, dw, rw = _num(v.get("d")), _num(v.get("r")), _num(w.get("d")), _num(w.get("r"))
    return None not in (dv, rv, dw, rw) and abs(dv - dw) <= 0.5 and abs(rv - rw) <= 0.5


def supplement(candidates: list[dict], wiki_rows: list[dict]) -> tuple[list[dict], int]:
    """(the candidates no Wikipedia poll could be, how many were dropped as duplicates)"""
    by_race = defaultdict(list)
    for w in wiki_rows:
        by_race[w["race"]].append(w)
    added = [v for v in candidates if not any(is_duplicate(v, w) for w in by_race.get(v["race"], []))]
    return added, len(candidates) - len(added)


def build_rows(races: dict[str, dict], wiki_rows: list[dict], committed: Path,
               until: str) -> tuple[list[dict], dict]:
    """The VoteHub rows for this build. Without a fresh download (an API
    outage during a refresh) the VoteHub rows already committed to
    data/polls/races.csv carry over, re-checked against today's Wikipedia
    polls, so an outage never silently drops polls from the forecast."""
    cands, basis = None, "none"
    if PATH.exists():
        try:
            cands, basis = candidate_rows(load(PATH), races, until), "api"
        except (ValueError, TypeError, KeyError, AttributeError) as e:
            print(f"  ! {PATH.name} unreadable ({e!r}) — carrying over the committed VoteHub polls")
    if cands is None and committed.exists():
        with open(committed, newline="") as f:
            cands = [r for r in csv.DictReader(f) if (r.get("source") or "").startswith("votehub:")]
        basis = "carried over from data/polls/races.csv"
    # fabricated polls the feed still carries (curated/excluded_pollsters.yaml)
    cands, fabricated = excluded.split(cands or [])
    added, dupes = supplement(cands, wiki_rows)
    return added, {"basis": basis, "candidates": len(cands), "already_on_wikipedia": dupes,
                   "added": len(added), "excluded_fabricated": len(fabricated)}
