"""Campaign finance from the FEC's bulk 'House/Senate current campaigns'
file (webl26.zip; public domain, rebuilt nightly).

The model's fundraising signal is each side's *individual contributions*
(TTL_INDIV_CONTRIB) — like FiveThirtyEight's, it ignores self-funding and
transfers, which buy ads but don't measure support. Nominees are matched
to FEC candidates by office, state, district, party and surname.
"""

from __future__ import annotations

import io
import re
import unicodedata
import zipfile

from midterms.paths import SOURCES
from midterms.pipeline import fetch

WEBL = "https://www.fec.gov/files/bulk-downloads/2026/webl26.zip"
COLS = ["CAND_ID", "CAND_NAME", "CAND_ICI", "PTY_CD", "CAND_PTY_AFFILIATION", "TTL_RECEIPTS",
        "TRANS_FROM_AUTH", "TTL_DISB", "TRANS_TO_AUTH", "COH_BOP", "COH_COP", "CAND_CONTRIB",
        "CAND_LOANS", "OTHER_LOANS", "CAND_LOAN_REPAY", "OTHER_LOAN_REPAY", "DEBTS_OWED_BY",
        "TTL_INDIV_CONTRIB", "CAND_OFFICE_ST", "CAND_OFFICE_DISTRICT", "SPEC_ELECTION",
        "PRIM_ELECTION", "RUN_ELECTION", "GEN_ELECTION", "GEN_ELECTION_PRECENT",
        "OTHER_POL_CMTE_CONTRIB", "POL_PTY_CONTRIB", "CVG_END_DT", "INDIV_REFUNDS", "CMTE_REFUNDS"]
PARTY = {"DEM": "D", "DFL": "D", "REP": "R", "IND": "IND", "NPA": "IND", "NNE": "IND",
         "UN": "IND", "LIB": "L", "GRE": "G"}


def pull(force: bool = False) -> None:
    print("fec: 2026 House/Senate campaigns")
    try:
        fetch.fetch_to("fec-webl26", WEBL, "fec/webl26.zip", force=force,
                       max_age_hours=None if not force else 0)
    except SystemExit as e:
        # an outage must not stop a poll refresh: build keeps data/finance.csv
        print(f"  ! {e} — keeping the committed filings")


def load() -> list[dict]:
    path = SOURCES / "fec" / "webl26.zip"
    with zipfile.ZipFile(path) as z:
        name = next(n for n in z.namelist() if n.lower().endswith(".txt"))
        text = io.TextIOWrapper(z.open(name), encoding="latin-1").read()
    out = []
    for line in text.splitlines():
        p = line.split("|")
        if len(p) < len(COLS):
            continue
        r = dict(zip(COLS, p))
        for k in ("TTL_RECEIPTS", "TTL_INDIV_CONTRIB", "COH_COP", "TTL_DISB"):
            try:
                r[k] = float(r[k] or 0)
            except ValueError:
                r[k] = 0.0
        r["party"] = PARTY.get(r["CAND_PTY_AFFILIATION"], r["CAND_PTY_AFFILIATION"])
        out.append(r)
    return out


SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "mr", "mrs", "ms", "dr"}


def _ascii(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()


def _tokens(s: str) -> list[str]:
    s = re.sub(r"\(.*?\)|\".*?\"", " ", _ascii(s).lower())
    return [t for t in re.sub(r"[^a-z' -]", " ", s).replace("-", " ").split()
            if t.strip("'") and t.strip("'") not in SUFFIXES]


def _surname(name: str) -> str:
    """FEC 'BEGICH, NICHOLAS III' / wiki 'Nick Begich' -> 'begich'."""
    n = name.strip()
    toks = _tokens(n.split(",")[0]) if "," in n else _tokens(n)[-1:]
    return "".join(t.replace("'", "") for t in toks)


def _names_match(wiki: str, fec: str) -> bool:
    """Does an FEC 'LAST, FIRST' name belong to this Wikipedia nominee?
    Handles compound and accented surnames (Wasserman Schultz, De La Cruz,
    Luján) and the FEC's occasional swapped fields ('NICK, LALOTA')."""
    w = [t.replace("'", "") for t in _tokens(wiki)]
    if not w:
        return False
    last, _, first = fec.partition(",")
    fl = "".join(t.replace("'", "") for t in _tokens(last))
    ff = [t.replace("'", "") for t in _tokens(first)]
    # FEC surname equals the wiki name's last k tokens joined (k = 1..3)
    for k in (1, 2, 3):
        if len(w) >= k and fl == "".join(w[-k:]):
            return True
    # swapped: the FEC 'first' field holds the surname
    if ff and "".join(ff) == w[-1] and fl and fl[:1] == w[0][:1]:
        return True
    # filed under a legal surname, public name in the first-name field
    # ('ARENHOLZ, ASHLEY HINSON' is Ashley Hinson)
    if len(w) >= 2 and len(ff) >= 2 and ff[-1] == w[-1] and ff[0] == w[0]:
        return True
    return False


def index(rows: list[dict]) -> dict:
    """(office 'H'/'S', state, district '07'|'00') -> [rows]"""
    idx: dict[tuple, list] = {}
    for r in rows:
        office = r["CAND_ID"][:1]
        dist = r["CAND_OFFICE_DISTRICT"].zfill(2) if office == "H" else "00"
        idx.setdefault((office, r["CAND_OFFICE_ST"], dist), []).append(r)
    return idx


def match(idx: dict, office: str, state: str, district: str, name: str, party: str) -> dict | None:
    pool = idx.get((office, state, district), [])
    hits = [r for r in pool if _names_match(name, r["CAND_NAME"])]
    if len(hits) > 1:
        hits = [r for r in hits if r["party"] == party] or hits
    if not hits and party in ("D", "R"):
        # surname spelled differently (hyphenation, nickname): unique party match
        same = [r for r in pool if r["party"] == party]
        if len(same) == 1:
            hits = same
    if not hits:
        return None
    return max(hits, key=lambda r: r["TTL_INDIV_CONTRIB"])
