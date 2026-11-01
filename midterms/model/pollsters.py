"""Pollster quality: Silver Bulletin's ratings (Jan 2026) -> poll weights.

Silver Bulletin's "Predictive Plus-Minus" (PPM) is the expected error of a
pollster's polls relative to an average pollster, after mean reversion —
negative is better. A poll's quality weight is exp(-0.35 * PPM), clamped
to [0.35, 1.6]: the best shops (PPM ~ -1.1) count ~1.5x an average one,
weak ones (PPM ~ +2) ~0.5x. Unrated pollsters get 0.7; pollsters Silver
Bulletin bans get 0 (excluded). FiveThirtyEight's final 2024 ratings fill
in pollsters Silver Bulletin doesn't rate, through the same mapping
(538's POLLSCORE is on the same plus-minus scale).

Names never match exactly across Wikipedia, VoteHub and the ratings
("CBS News/YouGov" vs "YouGov"), so lookup tries the full canonical name,
then each '/'-separated part, then a token-overlap match.
"""

from __future__ import annotations

import csv
import math
import re
from pathlib import Path

from midterms.pipeline.xlsx import xlsx_rows

UNRATED = 0.7

ALIASES = {
    "nyt": "new york times siena",
    "new york times siena": "new york times siena",
    "siena": "new york times siena",
    "the new york times siena": "new york times siena",
    "marist": "marist",
    "marist university": "marist",
    "marist college": "marist",
    "ssrs": "cnn ssrs",
    "cnn ssrs": "cnn ssrs",
    "abc news washington post ipsos": "abc news washington post",
    "fox news": "fox news",
    "beacon research d shaw company r": "fox news",
    "beacon research shaw company": "fox news",
    "atlasintel": "atlasintel",
    "atlas intel": "atlasintel",
}


def canon(name: str) -> str:
    n = (name or "").lower()
    n = re.sub(r"\[.*?\]|\(.*?\)", " ", n)
    n = n.replace("&", " ").replace("’", "'")
    n = re.sub(r"[^a-z0-9/ ]", " ", n)
    for junk in (" university", " college", " poll ", " polling", " research", " inc",
                 " llc", " group", " strategies", " associates", " institute", " center",
                 " the ", " company"):
        n = (" " + n + " ").replace(junk + " ", " ")
    n = re.sub(r"^the ", "", n.strip())
    return " ".join(n.split())


def weight_from_ppm(ppm: float) -> float:
    return max(0.35, min(1.6, math.exp(-0.35 * ppm)))


RATING_COLS = ["source", "pollster", "grade", "ppm", "banned"]


def rating_rows(sb_xlsx: Path | None, fte_csv: Path | None) -> list[dict]:
    """The raw ratings files cut down to the fields the model uses, in load
    order: FiveThirtyEight's first, Silver Bulletin's over them. Values are
    kept as the files spell them, so the committed table
    (data/pollster_ratings/ratings.csv) reproduces the weights exactly."""
    rows = []
    if fte_csv and fte_csv.exists():
        with open(fte_csv, newline="") as f:
            for r in csv.DictReader(f):
                try:
                    ppm = float(r.get("POLLSCORE") or "nan")
                except ValueError:
                    continue
                if math.isnan(ppm):
                    continue
                rows.append({"source": "538-2024", "pollster": r["pollster"],
                             "grade": r.get("numeric_grade", ""), "ppm": r["POLLSCORE"], "banned": ""})
    if sb_xlsx and sb_xlsx.exists():
        for r in xlsx_rows(sb_xlsx)[1:]:
            if len(r) < 9 or not r[1]:
                continue
            try:
                float(r[7])
            except ValueError:
                continue
            rows.append({"source": "silver-bulletin-2026-01", "pollster": r[1], "grade": r[8],
                         "ppm": r[7], "banned": "yes" if r[5].strip().lower() == "yes" else ""})
    return rows


def read_rating_rows(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_ratings(rows: list[dict]) -> dict:
    """canonical name -> {name, grade, ppm, banned, source}"""
    out: dict[str, dict] = {}
    for r in rows:
        out[canon(r["pollster"])] = {"name": r["pollster"], "grade": r["grade"], "ppm": float(r["ppm"]),
                                     "banned": r["banned"] == "yes", "source": r["source"]}
    for k in list(out):
        a = ALIASES.get(k)
        if a and a not in out:
            out[a] = out[k]
    return out


def _tokens(s: str) -> set:
    return {t for t in s.replace("/", " ").split() if len(t) > 2}


def lookup(name: str, ratings: dict) -> dict | None:
    c = canon(name)
    c = ALIASES.get(c, c)
    if c in ratings:
        return ratings[c]
    parts = [ALIASES.get(p.strip(), p.strip()) for p in c.split("/") if p.strip()]
    for p in reversed(parts):          # 'CBS News/YouGov' -> YouGov does the fieldwork
        if p in ratings:
            return ratings[p]
    best, score = None, 0.0
    tq = _tokens(c)
    if not tq:
        return None
    for k, v in ratings.items():
        tk = _tokens(k)
        if not tk:
            continue
        j = len(tq & tk) / len(tq | tk)
        if j > score:
            best, score = v, j
    return best if score >= 0.6 else None


def quality_table(pollster_names: set, ratings: dict) -> list[dict]:
    rows = []
    for name in sorted(pollster_names):
        hit = lookup(name, ratings)
        if hit is None:
            w, grade, ppm, src, banned = UNRATED, "", "", "", False
        else:
            banned = hit["banned"]
            w = 0.0 if banned else weight_from_ppm(hit["ppm"])
            grade, ppm, src = hit["grade"], round(hit["ppm"], 3), hit["source"]
        rows.append({"pollster": name, "matched": hit["name"] if hit else "",
                     "grade": grade, "ppm": ppm, "banned": "yes" if banned else "",
                     "weight": round(w, 3), "rating_source": src})
    return rows
