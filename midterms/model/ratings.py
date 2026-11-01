"""Expert race ratings -> a numeric scale -> an implied margin.

Labels from Cook, Sabato's Crystal Ball, Inside Elections and the other
handicappers Wikipedia compiles are normalized to a signed scale for the
D-side candidate:

    Solid/Safe +3   Likely +2   Lean +1   Tilt +0.5   Toss-up 0

(negative for the R side). The implied two-party margin for a scale value
is piecewise linear through the anchor points below. With the race-level
and shared error the simulator adds (total sd ~6.5 pts for a typical
contested race), these anchors reproduce the raters' long-run hit rates:
Tilt ~65%, Lean ~80%, Likely ~95%, Solid >99.9%. In the Deluxe blend a
rating is one more noisy measurement of the margin, not an override.
"""

from __future__ import annotations

import re

# scale value -> implied two-party margin (points), for the D side
ANCHORS = [(0.0, 0.0), (0.5, 2.5), (1.0, 5.5), (2.0, 11.0), (3.0, 22.0)]

_LEVEL = [
    (re.compile(r"\b(solid|safe)\b", re.I), 3.0),
    (re.compile(r"\blikely\b", re.I), 2.0),
    (re.compile(r"\blean(s)?\b", re.I), 1.0),
    (re.compile(r"\btilt(s)?\b", re.I), 0.5),
    (re.compile(r"\btoss[\s-]?up\b|\btossup\b|\bpure toss\b", re.I), 0.0),
]
_SIDE = re.compile(r"\b(D|R|I|DFL|Dem|Rep|Ind|Democratic|Republican|Independent)\b\.?", re.I)


def scale(label: str, d_side_party: str = "D") -> float | None:
    """'Lean R' -> -1.0 ; 'Tossup' -> 0 ; 'Likely I' (Osborn) -> +2 when the
    independent is the D-side candidate. None if unparseable."""
    t = (label or "").strip()
    if not t or t in ("—", "–", "-", "N/A"):
        return None
    lvl = None
    for pat, v in _LEVEL:
        if pat.search(t):
            lvl = v
            break
    if lvl is None:
        return None
    if lvl == 0.0:
        return 0.0
    m = _SIDE.search(re.sub(r"\(flip\)", "", t, flags=re.I))
    if not m:
        return None
    side = m.group(1).upper()
    side = {"DFL": "D", "DEM": "D", "DEMOCRATIC": "D", "REP": "R", "REPUBLICAN": "R",
            "IND": "I", "INDEPENDENT": "I"}.get(side, side)
    if side == "R":
        return -lvl
    if side == d_side_party or (side == "D" and d_side_party in ("D", "I")):
        return lvl
    if side == "I" and d_side_party != "I":
        return None          # an independent the model doesn't treat as D-side
    return lvl


def implied_margin(s: float, anchors=ANCHORS) -> float:
    sign = 1.0 if s >= 0 else -1.0
    x = abs(s)
    for (x0, y0), (x1, y1) in zip(anchors, anchors[1:]):
        if x <= x1:
            return sign * (y0 + (y1 - y0) * (x - x0) / (x1 - x0))
    return sign * anchors[-1][1]


# Raters weighted equally by default; the three long-running shops plus the
# newer handicappers Wikipedia tracks. Unknown sources are ignored.
RATERS = {
    "cook political report": "Cook",
    "the cook political report": "Cook",
    "cook": "Cook",
    "sabato's crystal ball": "Sabato",
    "sabato": "Sabato",
    "inside elections": "Inside Elections",
    "rothenberg political report": "Inside Elections",    # IE's name before 2018
    "the rothenberg political report": "Inside Elections",
    "rothenberg & gonzales political report": "Inside Elections",
    "the rothenberg & gonzales political report": "Inside Elections",
    "rothenberg and gonzales political report": "Inside Elections",
    "split ticket": "Split Ticket",
    "decision desk hq": "DDHQ",
    "ddhq": "DDHQ",
    "cnalysis": "CNalysis",
    "elections daily": "Elections Daily",
    "race to the wh": "Race to the WH",
    "realclearpolitics": "RCP",
    "realclearpolling": "RCP",
    "fox news": "Fox News",
    "cnn": "CNN",
    "cbs news": "CBS News",
    "abc news": "ABC News",
    "nbc news": "NBC News",
    "the economist": "The Economist",
    "politico": "Politico",
    "the hill": "The Hill",
    "the downballot": "The Downballot",
    "silver bulletin": "Silver Bulletin",
    "strength in numbers": "Strength In Numbers",
}

CORE = ("Cook", "Sabato", "Inside Elections")


def rater(name: str) -> str | None:
    n = re.sub(r"\[.*?\]", "", (name or "")).strip().lower()
    n = re.sub(r"\s+", " ", n)
    if n in RATERS:
        return RATERS[n]
    for k, v in RATERS.items():
        if n.startswith(k):
            return v
    return None
