"""Interpret Wikipedia poll tables as normalized poll records.

A Wikipedia poll table is a header row naming columns — "Poll source",
"Date(s) administered", "Sample size", "Margin of error", one column per
candidate (often with a party tag, "Susan Collins (R)"), then "Other",
"Undecided", sometimes "Lead" — followed by one row per poll *version*
(the same poll can appear once per population, LV/RV/A, or per question
wording, with the pollster and date cells row-spanned). Annotation rows
("Platner suspends his campaign") span every column and are dropped.

Output: one dict per poll row:

    {pollster, partisan ('D'|'R'|None), start, end, n, population,
     moe, answers: {column label: pct}, other, undecided,
     table_heading, table_index, row}

Interpretation of which candidate is which party happens later, against the
race's nominee list; this module only reads what the table says.
"""

from __future__ import annotations

import datetime
import re

from midterms.pipeline.htmltable import Table

MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august",
     "september", "october", "november", "december"], start=1)}
MONTHS.update({k[:3]: v for k, v in list(MONTHS.items())})
MONTHS["sept"] = 9

DASHES = "–—−-‒―"
_DASH_RE = re.compile(r"\s*[" + re.escape(DASHES) + r"]\s*")

ROLE_PATTERNS = [
    ("updated", re.compile(r"^dates? updated", re.I)),
    ("pollster", re.compile(r"^(poll(ing)? (source|firm)|pollster|source of poll|polling organi[sz]ation|source)\b", re.I)),
    ("dates", re.compile(r"^(date|dates?\(s\)|date\(s\)|fieldwork|administered|dates? administered)", re.I)),
    ("sample", re.compile(r"^sample", re.I)),
    ("moe", re.compile(r"^(margin|moe|±)", re.I)),
    ("undecided", re.compile(r"^(undecided|unsure|don.?t know|no opinion|not sure)", re.I)),
    ("other", re.compile(r"^(others?|other\s*/|someone else|third part|another)", re.I)),
    ("lead", re.compile(r"^(lead|margin\b|net\b|spread)", re.I)),
    ("round", re.compile(r"^(rcv )?round\b", re.I)),
]


def _role(label: str) -> str | None:
    lab = label.strip()
    # "Margin of error" must win over "Margin" (lead); order matters above
    if re.match(r"^margin\s+of\s+error", lab, re.I):
        return "moe"
    for role, pat in ROLE_PATTERNS:
        if pat.search(lab):
            return role
    return None


# ------------------------------------------------------------------ values

def pct(text: str) -> float | None:
    t = (text or "").strip().replace(",", "")
    if not t or t[0] in DASHES or t.lower() in ("n/a", "–", "—", "?"):
        return None
    if t.startswith("<"):
        m = re.search(r"(\d+(?:\.\d+)?)", t)
        return float(m.group(1)) / 2 if m else None
    m = re.match(r"^~?\s*(\d+(?:\.\d+)?)\s*%?", t)
    return float(m.group(1)) if m else None


POP_RE = re.compile(r"\(\s*(LV|RV|A|V|RV/LV|LV/RV)\s*\)", re.I)


def sample(text: str) -> tuple[int | None, str | None]:
    t = text or ""
    pop = None
    m = POP_RE.search(t)
    if m:
        pop = m.group(1).upper()
        if "/" in pop:
            pop = "LV"
    n = None
    m = re.search(r"(\d[\d,]*)", POP_RE.sub("", t))
    if m:
        try:
            n = int(m.group(1).replace(",", ""))
        except ValueError:
            n = None
    if n is not None and n < 50:   # footnote digits, not a sample size
        n = None
    return n, pop


def moe(text: str) -> float | None:
    m = re.search(r"(\d+(?:\.\d+)?)", text or "")
    return float(m.group(1)) if m else None


PARTISAN_RE = re.compile(r"\((D|R|I|L|G)\)\s*$")


def pollster(text: str) -> tuple[str, str | None]:
    """'Data for Progress (D)' -> ('Data for Progress', 'D')."""
    t = (text or "").strip()
    # bipartisan teams (Fox News: 'Beacon Research (D)/Shaw & Company (R)')
    # are nonpartisan polls, not R-affiliated ones
    if re.search(r"\(D\)", t) and re.search(r"\(R\)", t):
        return t, None
    m = PARTISAN_RE.search(t)
    party = None
    if m:
        party = m.group(1)
        t = t[: m.start()].strip()
    return t, party if party in ("D", "R") else None


def _date_parts(s: str) -> tuple[int | None, int | None, int | None]:
    """'October 23' / 'Oct 23, 2026' / '23' / 'October 2026' -> (y, m, d)."""
    s = s.strip().strip(",").strip()
    y = m = d = None
    my = re.search(r"\b(20\d\d|19\d\d)\b", s)
    if my:
        y = int(my.group(1))
        s = (s[: my.start()] + s[my.end():]).strip().strip(",").strip()
    for tok in re.findall(r"[A-Za-z]+\.?|\d+", s):
        tl = tok.lower().rstrip(".")
        if tl in MONTHS:
            m = MONTHS[tl]
        elif tok.isdigit():
            d = int(tok)
    return y, m, d


def dates(text: str, default_year: int | None = None) -> tuple[str | None, str | None]:
    """Parse a Wikipedia date-range cell into ISO (start, end).

    Handles 'October 23–27, 2026', 'Sep 29 – Oct 2, 2026', 'October 30, 2026',
    'December 28, 2025 – January 3, 2026', 'Oct. 2026'."""
    t = (text or "").replace(" ", " ").strip()
    if not t:
        return None, None
    parts = [p for p in _DASH_RE.split(t, maxsplit=1) if p.strip()]
    if not parts:
        return None, None
    end = _date_parts(parts[-1])
    start = _date_parts(parts[0]) if len(parts) > 1 else end
    ey, em, ed = end
    sy, sm, sd = start
    if em is None and sm is not None:
        em = sm                                  # 'October 23–27'
    if sm is None:
        sm = em
    if ey is None:
        ey = default_year
    if sy is None:
        sy = ey if (sm or 0) <= (em or 0) else (ey - 1 if ey else None)
    if ed is None and sd is None:                # month-only: use mid-month
        sd = ed = 15
    if ed is None:
        ed = sd
    if sd is None:
        sd = ed
    try:
        s_iso = datetime.date(sy, sm, sd).isoformat() if sy and sm and sd else None
        e_iso = datetime.date(ey, em, ed).isoformat() if ey and em and ed else None
    except ValueError:
        return None, None
    return s_iso, e_iso


# ------------------------------------------------------------------ tables

def _header_rows(grid) -> int:
    """Count leading rows made only of header cells (or blanks)."""
    k = 0
    for row in grid:
        cells = [c for c in row if c is not None]
        if cells and all(c.header or not c.text for c in cells):
            k += 1
        else:
            break
    return k


def is_poll_table(t: Table) -> bool:
    g = t.grid()
    if not g:
        return False
    head = " ".join(c.text.lower() for c in g[0] if c)
    return (("poll" in head or "pollster" in head or "firm" in head)
            and ("date" in head or "administered" in head)
            and "dates updated" not in head)


def is_average_table(t: Table) -> bool:
    g = t.grid()
    if not g:
        return False
    head = " ".join(c.text.lower() for c in g[0] if c)
    return "aggrega" in head or "dates updated" in head


def columns(t: Table) -> tuple[list[dict], int]:
    """Column descriptors from the header rows: [{'label', 'role'}...]."""
    g = t.grid()
    nh = max(1, _header_rows(g))
    width = max(len(r) for r in g)
    cols = []
    for j in range(width):
        labels = []
        for i in range(nh):
            c = g[i][j] if j < len(g[i]) else None
            if c is not None and c.text and c.text not in labels:
                labels.append(c.text)
        label = " ".join(labels).strip()
        cols.append({"label": label, "role": _role(label) if label else None})
    # every unlabeled-role, labeled column is an answer (candidate / option)
    for c in cols:
        if c["role"] is None and c["label"]:
            c["role"] = "answer"
    return cols, nh


def rows(t: Table, default_year: int | None = None) -> list[dict]:
    cols, nh = columns(t)
    g = t.grid()
    out = []
    for i, row in enumerate(g[nh:], start=nh):
        cells = [c for c in row if c is not None]
        if not cells:
            continue
        texts = {c.text for c in cells}
        if len(texts) == 1 and len(cells) > 3:   # spanning annotation row
            continue
        rec = {"answers": {}, "other": None, "undecided": None, "pollster": None, "round": None,
               "refs": [],
               "partisan": None, "start": None, "end": None, "n": None,
               "population": None, "moe": None, "table_heading": t.heading,
               "table_index": t.index, "row": i, "leader_bold": []}
        for j, c in enumerate(row):
            if c is None or j >= len(cols):
                continue
            role, label = cols[j]["role"], cols[j]["label"]
            if role == "pollster":
                rec["pollster"], rec["partisan"] = pollster(c.text)
                rec["refs"] = list(c.refs)
            elif role == "dates":
                rec["start"], rec["end"] = dates(c.text, default_year)
            elif role == "sample":
                rec["n"], rec["population"] = sample(c.text)
            elif role == "moe":
                rec["moe"] = moe(c.text)
            elif role == "round":
                v = pct(c.text)
                rec["round"] = int(v) if v is not None else None
            elif role == "other":
                rec["other"] = pct(c.text)
            elif role == "undecided":
                rec["undecided"] = pct(c.text)
            elif role == "answer":
                v = pct(c.text)
                if v is not None:
                    rec["answers"][label] = v
                    if c.bold:
                        rec["leader_bold"].append(label)
        if rec["pollster"] and rec["end"] and len(rec["answers"]) >= 2:
            out.append(rec)
    return out


def averages(t: Table, default_year: int | None = None) -> list[dict]:
    """Aggregator rows ('270toWin', 'Decision Desk HQ', ...) from an
    average table: {source, start, end, updated, answers}."""
    cols, nh = columns(t)
    g = t.grid()
    out = []
    for row in g[nh:]:
        rec = {"source": None, "end": None, "updated": None, "answers": {}}
        for j, c in enumerate(row):
            if c is None or j >= len(cols):
                continue
            role, label = cols[j]["role"], cols[j]["label"]
            if role == "pollster":
                rec["source"] = c.text
            elif role == "dates":
                rec["end"] = dates(c.text.replace("through", ""), default_year)[1]
            elif role == "updated":
                rec["updated"] = dates(c.text, default_year)[1]
            elif role == "answer":
                v = pct(c.text)
                if v is not None:
                    rec["answers"][label] = v
        if rec["source"] and len(rec["answers"]) >= 2:
            out.append(rec)
    return out


CAND_PARTY_RE = re.compile(r"\((D|R|I|L|G|DFL|Ind\.?|Independent|Democratic|Republican)\)\s*$", re.I)


def label_party(label: str) -> tuple[str, str | None]:
    """'Susan Collins (R)' -> ('Susan Collins', 'R')."""
    m = CAND_PARTY_RE.search(label or "")
    if not m:
        return (label or "").strip(), None
    p = m.group(1).upper().rstrip(".")
    p = {"DFL": "D", "DEMOCRATIC": "D", "REPUBLICAN": "R", "IND": "I",
         "INDEPENDENT": "I"}.get(p, p)
    return label[: m.start()].strip(), p
