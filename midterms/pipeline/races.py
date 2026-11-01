"""Assemble race rows (+ their polls, ratings and outside averages) from
the Wikipedia race pages.

Each race is reduced to a head-to-head between a D-side and an R-side
candidate. Normally that is the Democratic and Republican nominees; where a
party fields nobody, the strongest other candidate takes that side (Dan
Osborn, an independent, is Nebraska's D-side). A race is `fixed` — decided
before Election Day — when only one side's party can win: one candidate,
two candidates of the same party (California/Washington top-two), or a
major-party nominee facing only minor candidates in a race every core
rater calls Safe/Solid and nobody has polled.
"""

from __future__ import annotations

import re

from midterms.model import ratings as R
from midterms.pipeline import racepage as rp
from midterms.pipeline import wikipolls as wp
from midterms.pipeline.htmltable import Table, extract_tables, references
from midterms.pipeline.states import AT_LARGE, STATES

MINOR = {"L", "G", "C", "WF", "FWD", "AKIP"}


def _ordinal_label(st: str, n: int | None) -> str:
    return f"{st}-AL" if n is None else f"{st}-{n:02d}"


def sides(cands: list[dict], shares: dict | None = None) -> tuple[dict | None, dict | None, list[dict]]:
    """Pick (d_side, r_side, others) from a results-box candidate list.

    With poll shares: the R side is the best-polling Republican (Alaska's
    top-four can carry three), the D side the best-polling non-Republican
    (Montana's independent Bodnar outpolls the Democratic nominee)."""
    shares = shares or {}
    if shares and sum(1 for c in cands if c["candidate"] in shares) >= 2:
        rs = sorted((c for c in cands if c["party_code"] == "R"),
                    key=lambda c: -shares.get(c["candidate"], -1))
        nonr = sorted((c for c in cands if c["party_code"] != "R"),
                      key=lambda c: -shares.get(c["candidate"], -1))
        d = nonr[0] if nonr else None
        r = rs[0] if rs else None
        if d is not None and r is not None and d["candidate"] in shares and r["candidate"] in shares:
            others = [c for c in cands if c is not d and c is not r]
            return d, r, others
    ds = [c for c in cands if c["party_code"] == "D"]
    rs = [c for c in cands if c["party_code"] == "R"]
    rest = [c for c in cands if c["party_code"] not in ("D", "R")]
    d = ds[0] if ds else None
    r = rs[0] if rs else None
    others = ds[1:] + rs[1:] + rest
    if d is None and rest:
        # strongest non-R: an independent before minor-party candidates
        pick = sorted(rest, key=lambda c: (c["party_code"] in MINOR,))[0]
        d = pick
        others = [c for c in others if c is not pick]
    elif r is None and rest:
        pick = sorted(rest, key=lambda c: (c["party_code"] in MINOR,))[0]
        r = pick
        others = [c for c in others if c is not pick]
    return d, r, others


def _core_safe(preds: list[dict], party: str) -> bool:
    core = [p for p in preds if R.rater(p["source"]) in R.CORE]
    if not core:
        return False
    want = 3.0 if party == "D" else -3.0
    return all(R.scale(p["rating"]) == want for p in core)


def classify(cands: list[dict], preds: list[dict], n_polls: int, shares: dict | None = None) -> dict:
    d, r, others = sides(cands, shares)
    out = {"d": d, "r": r, "others": others, "fixed": ""}
    if d is None and r is None:
        return out
    if d is None or r is None:
        only = d or r
        out["fixed"] = only["party_code"]
        return out
    if d["party_code"] == r["party_code"]:                 # D-vs-D top-two
        out["fixed"] = d["party_code"]
        return out
    # a major-party nominee facing only an independent/minor candidate
    if r["party_code"] != "R" and n_polls == 0 and _core_safe(preds, "D"):
        out["fixed"] = "D"
    elif d["party_code"] != "D" and n_polls == 0 and _core_safe(preds, "R"):
        out["fixed"] = "R"
    return out


def _poll_rows(race_id: str, tables: list[Table], d: dict, r: dict, src: str,
               urls: dict | None = None) -> list[dict]:
    urls = urls or {}
    out = []
    for t in rp.poll_tables(tables, d["candidate"], r["candidate"]):
        cols, _ = wp.columns(t)
        labels = [c["label"] for c in cols if c["role"] == "answer"]
        dl = rp.best_label(labels, d["candidate"])
        rl = rp.best_label(labels, r["candidate"])
        rows = wp.rows(t, 2026)
        # ranked-choice tables list every round: keep each poll's final round
        final = {}
        for row in rows:
            k = (row["pollster"], row["start"], row["end"], row["population"])
            if row.get("round") is not None:
                if k not in final or row["round"] > final[k]["round"]:
                    final[k] = row
        if final:
            rows = list(final.values())
        for row in rows:
            a = row["answers"]
            if dl not in a or rl not in a:
                continue
            out.append({"race": race_id, "pollster": row["pollster"], "partisan": row["partisan"] or "",
                        "start": row["start"] or "", "end": row["end"], "n": row["n"] or "",
                        "population": row["population"] or "", "d": a[dl], "r": a[rl],
                        "other": "" if row["other"] is None else row["other"],
                        "undecided": "" if row["undecided"] is None else row["undecided"],
                        "d_label": dl, "r_label": rl, "source": src, "table": t.index,
                        "url": next((urls[x] for x in row.get("refs", []) if x in urls), "")})
    return out


def _avg_rows(race_id: str, tables: list[Table], d: dict, r: dict) -> list[dict]:
    out = []
    for t in rp.average_tables(tables):
        for a in wp.averages(t, 2026):
            dk = rp.best_label(list(a["answers"]), d["candidate"])
            rk = rp.best_label(list(a["answers"]), r["candidate"])
            dv = a["answers"].get(dk) if dk else None
            rv = a["answers"].get(rk) if rk else None
            if dv is None or rv is None or a["source"].lower() == "average":
                continue
            out.append({"race": race_id, "source": a["source"], "end": a["end"] or "",
                        "updated": a["updated"] or "", "d": dv, "r": rv})
    return out


def _rating_rows(race_id: str, preds: list[dict], d_party: str) -> list[dict]:
    out = []
    for p in preds:
        name = R.rater(p["source"])
        s = R.scale(p["rating"], d_side_party=d_party)
        out.append({"race": race_id, "rater": name or p["source"], "source": p["source"],
                    "rating": p["rating"], "scale": "" if s is None else s,
                    "asof": p["asof"] or ""})
    return out


def one_race(race_id: str, chamber: str, state: str, label: str, tables: list[Table],
             prefix: str, src: str, urls: dict | None = None) -> dict:
    gen = rp.general(tables, prefix)
    inc = rp.incumbent(rp.section_tables(tables, prefix) if prefix else tables)
    cands = rp.results_box(gen) or []
    cand_source = "results-box"
    if not cands:
        # editors add the results box late; the race infobox names the nominees
        cands = rp.infobox_nominees(rp.lead_tables(tables, prefix))
        cand_source = "infobox"
    # the '(incumbent)' tag is applied inconsistently; the infobox's
    # 'Incumbent U.S. Representative <name>' row is the authority
    if inc and inc.get("name"):
        for c in cands:
            if rp._norm(c["candidate"]) == rp._norm(inc["name"]) or (
                    rp.match_label(c["candidate"], inc["name"])
                    and c["party_code"] == inc.get("party_code")):
                c["incumbent"] = True
    preds = rp.predictions(gen)
    shares = rp.main_poll_shares(gen, cands) if len(cands) > 2 else {}
    d, r, others = sides(cands, shares)
    polls = _poll_rows(race_id, gen, d, r, src, urls) if (d and r) else []
    cls = classify(cands, preds, len(polls), shares)
    d, r = cls["d"], cls["r"]
    inc_name = inc["name"] if inc else ""
    inc_party = inc["party_code"] if inc else ""
    running = any(c["incumbent"] for c in cands)
    row = {
        "id": race_id, "chamber": chamber, "state": state, "label": label,
        "incumbent": inc_name or "", "inc_party": inc_party,
        "inc_running": "yes" if running else "no",
        "d_cand": d["candidate"] if d else "", "d_side": d["party_code"] if d else "D",
        "r_cand": r["candidate"] if r else "", "r_side": r["party_code"] if r else "R",
        "others": "; ".join(f"{c['candidate']} ({c['party_code']})" for c in cls["others"]),
        "fixed": cls["fixed"], "source": src, "cand_source": cand_source if cands else "",
    }
    if running:
        inc_c = next(c for c in cands if c["incumbent"])
        row["inc_party"] = inc_c["party_code"] or inc_party
    fund, fund_asof = rp.fundraising(gen)
    return {"race": row,
            "polls": polls,
            "ratings": _rating_rows(race_id, preds, row["d_side"]),
            "averages": _avg_rows(race_id, gen, d, r) if (d and r) else [],
            "fundraising": [{"race": race_id, "candidate": f["candidate"],
                             "party": f["party_code"] or "", "raised": f["raised"] or "",
                             "cash_on_hand": f["cash_on_hand"] or "", "asof": fund_asof or ""}
                            for f in fund],
            "cands": cands}


DISTRICT_RE = re.compile(r"^District (\d+)$")


def house_state(st: str, page: dict) -> list[dict]:
    tables = extract_tables(page["html"])
    urls = references(page["html"])
    src = f"wikipedia:{page['title']}@{page['revid']}"
    if st in AT_LARGE:
        label = _ordinal_label(st, None)
        # at-large pages put the general election at the top level
        return [one_race(f"house:{label}", "house", st, label, tables, "", src, urls)]
    seen = []
    for t in tables:
        top = t.headings[0]
        m = DISTRICT_RE.match(top or "")
        if m and int(m.group(1)) not in seen:
            seen.append(int(m.group(1)))
    out = []
    for n in sorted(seen):
        label = _ordinal_label(st, n)
        out.append(one_race(f"house:{label}", "house", st, label, tables, f"District {n}", src, urls))
    return out


def statewide(race_id: str, chamber: str, st: str, page: dict) -> dict:
    tables = extract_tables(page["html"])
    src = f"wikipedia:{page['title']}@{page['revid']}"
    label = f"{STATES[st]}" + (" (special)" if race_id.endswith("-special") else "")
    return one_race(race_id, chamber, st, label, tables, "", src, references(page["html"]))
