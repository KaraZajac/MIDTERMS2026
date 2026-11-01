"""What each refresh changed: the site's "latest updates" feed.

Every `midterms forecast` compares itself with the forecast it replaces —
the polls that entered an average, the races whose chances moved, the
chambers — and, when anything changed, prepends an entry to
data/forecast/changes.json (the last 96 entries: two days of half-hourly
refreshes). `midterms export` publishes it as data/site/changes.json.

Only the data changes after the freeze, so each entry is, in effect, a
list of new polls (and ratings or nominees) and what they did.
"""

from __future__ import annotations

import json

from midterms.paths import FORECAST

PATH = FORECAST / "changes.json"
KEEP = 96
MOVE = 0.02            # a race "moved" at two points of probability
MAX_POLLS, MAX_MOVED = 40, 25


def _key(p: dict) -> tuple:
    return (p.get("pollster"), p.get("start"), p.get("end"), p.get("n"), p.get("population"),
            p.get("d"), p.get("r"))


def diff(old: dict, old_ledger: dict, new: dict, new_ledger: dict) -> dict | None:
    """One feed entry, or None when nothing a reader would notice changed."""
    head = new["headline"]
    polls = []
    for rid, rows in (new_ledger.get("ledgers") or {}).items():
        seen = {_key(p) for p in (old_ledger.get("ledgers") or {}).get(rid, [])}
        for p in rows:
            if _key(p) not in seen:
                polls.append({"race": rid, "pollster": p.get("pollster"), "end": p.get("end"),
                              "margin": p.get("margin"), "partisan": p.get("partisan") or None,
                              "via": p.get("via", "wikipedia"), "weight": p.get("weight")})
    polls.sort(key=lambda p: (p["end"] or "", p["weight"] or 0), reverse=True)
    moved = []
    o_r = old["versions"][head]["races"]
    for rid, r in new["versions"][head]["races"].items():
        if rid in o_r:
            a, b = o_r[rid]["p_d_side"], r["p_d_side"]
            if abs(b - a) >= MOVE:
                moved.append({"race": rid, "from": round(a, 4), "to": round(b, 4)})
    moved.sort(key=lambda m: abs(m["to"] - m["from"]), reverse=True)
    chambers = {}
    for c, ch in new["versions"][head]["chambers"].items():
        a = old["versions"][head]["chambers"].get(c, {}).get("p_control", {}).get("D")
        b = ch["p_control"].get("D")
        if a is not None and b is not None:
            chambers[c] = {"from": round(a, 4), "to": round(b, 4)}
    if not polls and not moved and all(abs(v["to"] - v["from"]) < 0.001 for v in chambers.values()):
        return None
    return {"t": new["generated"], "previous": old["generated"], "chambers": chambers,
            "polls": polls[:MAX_POLLS], "polls_total": len(polls),
            "moved": moved[:MAX_MOVED], "moved_total": len(moved)}


def record(old: dict | None, old_ledger: dict | None, new: dict, new_ledger: dict) -> dict | None:
    """Prepend this forecast's entry to the log (if anything changed)."""
    if not old or not old_ledger or old.get("generated") == new.get("generated"):
        return None
    try:
        e = diff(old, old_ledger, new, new_ledger)
    except (KeyError, TypeError):
        return None                     # a forecast of another shape: start the log afresh
    if e is None:
        return None
    log = load()
    log["entries"] = [e] + [x for x in log["entries"] if x.get("t") != e["t"]][:KEEP - 1]
    PATH.write_text(json.dumps(log, sort_keys=True))
    return e


def load() -> dict:
    try:
        doc = json.loads(PATH.read_text())
        if isinstance(doc.get("entries"), list):
            return doc
    except (OSError, ValueError):
        pass
    return {"entries": []}
