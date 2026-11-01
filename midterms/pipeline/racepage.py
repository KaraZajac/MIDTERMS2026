"""Read one race out of a Wikipedia election page.

Senate and governor pages hold one race; House state pages hold one
section per district ("District 7"), each laid out the same way:

    <prefix> > General election > Predictions   Source | Ranking | As of
    <prefix> > General election > Polling       poll tables (+ averages)
    <prefix> > General election > Fundraising   Candidate | Raised | Spent | COH
    <prefix> > General election > Results       the results box

Before Election Day the results box lists the general-election candidates
(party, name, "(incumbent)"); after it, the same box carries the votes —
so one parser feeds both the forecast and the scorecard.
"""

from __future__ import annotations

import re

from midterms.pipeline import wikipolls as wp
from midterms.pipeline.htmltable import Table

PARTY_CODES = {
    "democratic": "D", "democratic party": "D", "democratic–farmer–labor": "D",
    "democratic-farmer-labor": "D", "dfl": "D",
    "republican": "R", "republican party": "R",
    "independent": "IND", "nonpartisan": "IND", "no party preference": "IND",
    "libertarian": "L", "green": "G", "constitution": "C",
    "working families": "WF", "forward": "FWD", "alaska independence": "AKIP",
    "independent party": "IND", "unaffiliated": "IND",
}


def party_code(name: str) -> str:
    n = re.sub(r"\[.*?\]", "", name or "").strip().lower()
    n = re.sub(r"\s+party$", "", n)
    if n in PARTY_CODES:
        return PARTY_CODES[n]
    if n.startswith("democratic"):
        return "D"
    if n.startswith("republican"):
        return "R"
    if "independent" in n:
        return "IND"
    return n.upper()[:12] if n else ""


def general(tables: list[Table], prefix: str = "") -> list[Table]:
    """Tables in '<prefix> > General election > ...' (or the page-level
    'General election' section when prefix is empty)."""
    want = f"{prefix} > General election" if prefix else "General election"
    out = []
    for t in tables:
        h = t.heading
        if h == want or h.startswith(want + " > "):
            out.append(t)
    return out


def subsection(t: Table) -> str:
    parts = t.heading.split(" > ")
    try:
        i = parts.index("General election")
        return parts[i + 1] if i + 1 < len(parts) else ""
    except ValueError:
        return ""


_NUM = re.compile(r"[\d,]+")


def results_box(tables: list[Table]) -> list[dict] | None:
    """[{party, party_code, candidate, incumbent, votes, pct}] from the
    general-election results box, or None if there isn't one."""
    for t in tables:
        if subsection(t) not in ("Results", ""):
            continue
        g = t.grid()
        if not g:
            continue
        head = [c.text.lower() if c else "" for c in g[0]]
        if "candidate" not in head or "party" not in head:
            continue
        ci = head.index("candidate")
        vi = head.index("votes") if "votes" in head else None
        pi = head.index("%") if "%" in head else None
        out = []
        for row in g[1:]:
            if len(row) <= ci or row[ci] is None:
                continue
            # first line = the candidate (a governor's running mate follows)
            cell = row[ci]
            cand = cell.lines[0] if cell.lines else cell.text
            if any(re.match(r"^\(\s*incumbent\s*\)$", ln, re.I) for ln in cell.lines[1:]):
                cand += " (incumbent)"
            party = row[ci - 1].text if ci >= 1 and row[ci - 1] else ""
            low = cand.lower()
            if not cand or low.startswith(("total", "turnout", "registered", "majority",
                                           "plurality", "blank", "rejected")):
                continue
            if party.lower().startswith(("total", "turnout")):
                continue
            if re.search(r"\b(hold|gain|flip)\b", party.lower() + " " + low):
                continue
            inc = bool(re.search(r"\(\s*incumbent\s*\)", cand, re.I))
            name = re.sub(r"\(.*?\)", "", cand).strip()
            if name.lower() in ("write-in", "write-ins", "write in", "scattering",
                                "none of these candidates", "candidate", "tbd", "tba") or \
                    re.match(r"^(inactive|exhausted|blank|void|over|under)[\s-]*(ballots|votes)", name, re.I):
                continue
            if party.strip().upper() == "PARTY":
                continue
            votes = None
            if vi is not None and vi < len(row) and row[vi] is not None:
                m = _NUM.search(row[vi].text)
                votes = int(m.group(0).replace(",", "")) if m and m.group(0).strip(",") else None
            pct = wp.pct(row[pi].text) if pi is not None and pi < len(row) and row[pi] else None
            dup = next((o for o in out if _norm(o["candidate"]) == _norm(name)), None)
            if dup is not None:            # fusion line (NY/CT Working Families etc.)
                if votes is not None:
                    dup["votes"] = (dup["votes"] or 0) + votes
                dup.setdefault("fusion", []).append(party_code(party))
                continue
            out.append({"party": party, "party_code": party_code(party), "candidate": name,
                        "incumbent": inc, "votes": votes, "pct": pct})
        if out:
            return out
    return None


def predictions(tables: list[Table], default_year: int = 2026) -> list[dict]:
    out = []
    for t in tables:
        if subsection(t) not in ("Predictions", "Ratings"):
            continue
        g = t.texts()
        if not g or [c.lower() for c in g[0][:2]] != ["source", "ranking"]:
            continue
        for row in g[1:]:
            if len(row) < 2 or not row[0]:
                continue
            asof = wp.dates(row[2], default_year)[1] if len(row) > 2 else None
            out.append({"source": row[0], "rating": row[1], "asof": asof})
    return out


_MONEY = re.compile(r"\$?\s*([\d,]+(?:\.\d+)?)")


def money(text: str) -> float | None:
    m = _MONEY.search(text or "")
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", ""))
    except ValueError:
        return None


def fundraising(tables: list[Table], default_year: int = 2026) -> tuple[list[dict], str | None]:
    for t in tables:
        if subsection(t) != "Fundraising":
            continue
        g = t.texts()
        if len(g) < 3:
            continue
        asof = None
        m = re.search(r"as of (.+)$", g[0][0] if g[0] else "")
        if m:
            asof = wp.dates(m.group(1), default_year)[1]
        hdr = next((i for i, r in enumerate(g) if r and r[0].lower() == "candidate"), None)
        if hdr is None:
            continue
        out = []
        for row in g[hdr + 1:]:
            if not row or not row[0] or row[0].lower().startswith("source"):
                continue
            name, party = wp.label_party(row[0])
            out.append({"candidate": name, "party_code": party,
                        "raised": money(row[1]) if len(row) > 1 else None,
                        "spent": money(row[2]) if len(row) > 2 else None,
                        "cash_on_hand": money(row[3]) if len(row) > 3 else None})
        return out, asof
    return [], None


def _norm(s: str) -> str:
    s = re.sub(r"\(.*?\)", "", s or "")
    s = re.sub(r"[^a-z ]", "", s.lower())
    return " ".join(s.split())


def _last(s: str) -> str:
    toks = _norm(s).split()
    toks = [t for t in toks if t not in ("jr", "sr", "ii", "iii", "iv")]
    return toks[-1] if toks else ""


def match_label(label: str, candidate: str) -> bool:
    """Does a poll column label ('Ryan Mackenzie (R)') name this candidate?"""
    a, b = _norm(label), _norm(candidate)
    if not a or not b:
        return False
    return a == b or _last(a) == _last(b) and (a.split()[0][:1] == b.split()[0][:1]
                                                  or len(a.split()) == 1)


def best_label(labels: list[str], candidate: str) -> str | None:
    """The column naming this candidate: exact normalized match first (two
    Dan Sullivans are on Alaska's ballot), then the last-name fallback."""
    exact = [lab for lab in labels if _norm(lab) == _norm(candidate)]
    if exact:
        return exact[0]
    loose = [lab for lab in labels if match_label(lab, candidate)]
    return loose[0] if len(loose) == 1 else None


def is_polling(t: Table) -> bool:
    sub = subsection(t)
    return sub == "Polling" or t.heading.split(" > ")[-1].lower().endswith("polls")


def poll_tables(tables: list[Table], d_name: str, r_name: str) -> list[Table]:
    """General-election poll tables whose answer columns include both
    nominees — the actual matchup; collapsed 'Hypothetical polling' blocks
    are excluded."""
    out = []
    for t in tables:
        if not is_polling(t) or not wp.is_poll_table(t) or t.hidden:
            continue
        cols, _ = wp.columns(t)
        labels = [c["label"] for c in cols if c["role"] == "answer"]
        if best_label(labels, d_name) and best_label(labels, r_name):
            out.append(t)
    return out


def main_poll_shares(tables: list[Table], cands: list[dict]) -> dict:
    """Mean first-choice share per nominee across the actual-matchup poll
    tables (used to decide who is the D-side / R-side in a multi-candidate
    race). {candidate name: mean share}."""
    sums: dict[str, list[float]] = {}
    for t in tables:
        if not is_polling(t) or not wp.is_poll_table(t) or t.hidden:
            continue
        cols, _ = wp.columns(t)
        labels = [c["label"] for c in cols if c["role"] == "answer"]
        hit = {c["candidate"]: best_label(labels, c["candidate"]) for c in cands}
        if sum(1 for v in hit.values() if v) < 2:
            continue
        for row in wp.rows(t, 2026):
            if row.get("round") not in (None, 1):
                continue
            for name, lab in hit.items():
                if lab and lab in row["answers"]:
                    sums.setdefault(name, []).append(row["answers"][lab])
    return {k: sum(v) / len(v) for k, v in sums.items() if v}


def average_tables(tables: list[Table]) -> list[Table]:
    return [t for t in tables if is_polling(t) and wp.is_average_table(t) and not t.hidden]


_INC_RE = re.compile(
    r"^(?:Incumbent|Before election)\s+(?:U\.S\.\s+)?(?:Representative|Senator|Governor|Delegate)?\s*"
    r"(?P<name>.+?)\s+(?P<party>Democratic(?:[-–]Farmer[-–]Labor)?|Republican|Independent|Libertarian|"
    r"Nonpartisan|Vacant)(?:\s*\((?:DFL|D|R)\))?\s*$", re.I)


def incumbent(section_tables: list[Table]) -> dict | None:
    """{'name', 'party_code'} of the officeholder going into the election,
    from the race infobox ('Incumbent U.S. Representative Dwight Evans
    Democratic'). Vacant seats return {'name': None, 'party_code': ''}."""
    for t in section_tables:
        for row in t.grid():
            for c in row:
                if c is None or not c.text:
                    continue
                if not re.match(r"^(Incumbent|Before election)\b", c.text):
                    continue
                if re.search(r"\bvacant\b", c.text, re.I):
                    return {"name": None, "party_code": ""}
                m = _INC_RE.match(c.text)
                if m:
                    return {"name": m.group("name").strip(),
                            "party_code": party_code(m.group("party"))}
    return None


def section_tables(tables: list[Table], prefix: str) -> list[Table]:
    """Every table under a top-level section heading ('District 3')."""
    out = []
    for t in tables:
        if t.heading == prefix or t.heading.startswith(prefix + " > "):
            out.append(t)
    return out


def lead_tables(tables: list[Table], prefix: str) -> list[Table]:
    """Tables in a section's lead (before its first subsection): where the
    race infobox lives. prefix '' = the page lead."""
    if prefix:
        return [t for t in tables if t.heading == prefix]
    return [t for t in tables if not t.headings[0]]


def infobox_nominees(lead: list[Table]) -> list[dict]:
    """[{party, party_code, candidate, incumbent=False}] from the infobox
    rows 'Nominee | A | B' / 'Party | Democratic | Republican'."""
    for t in lead:
        g = t.texts()
        names = next((r for r in g if r and r[0].lower() in ("nominee", "candidate", "nominees")), None)
        if names:   # first line of each cell (drops running mates)
            grow = next(r for r in t.grid() if r and r[0] and r[0].text.lower() in ("nominee", "candidate", "nominees"))
            names = [c.lines[0] if (c and c.lines) else (c.text if c else "") for c in grow]
        parties = next((r for r in g if r and r[0].lower() == "party"), None)
        if not names or not parties:
            continue
        out = []
        for i in range(1, len(names)):
            nm = names[i].strip()
            if not nm:
                continue
            pa = parties[i] if i < len(parties) else ""
            out.append({"party": pa, "party_code": party_code(pa), "candidate": nm,
                        "incumbent": False, "votes": None, "pct": None})
        if out:
            return out
    return []
