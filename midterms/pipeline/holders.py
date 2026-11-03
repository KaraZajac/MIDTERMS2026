"""Who holds each seat now: the baseline for "seats that changed hands".

House: the Clerk of the House's member list (clerk.house.gov, MemberData.xml)
by district number, a vacant seat counting for its last member's party. That
is the convention AP and Wikipedia use for gains ("Republican gain from
Democratic"), redrawn districts included: a seat changes hands when its
winner's party differs from the party of the member now holding that number.
Senate and governors: the incumbents in data/races/ (Wikipedia).

Pinned in data/holders/: holders.csv (race, held, holder, note) and
sources.yaml (the Clerk file's URL, publish date, fetch time and sha256).

    python -m midterms.pipeline.holders [MemberData.xml]   rebuild the table
"""

from __future__ import annotations

import csv
import datetime as dt
import hashlib
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import yaml

from midterms.paths import DATA, RACES

CLERK_URL = "https://clerk.house.gov/xml/lists/MemberData.xml"
DIR = DATA / "holders"
PATH = DIR / "holders.csv"
COLS = ["race", "held", "holder", "note"]
CODE = {"I": "IND"}              # the Clerk's party letters -> data/races party codes


def _race_id(sd: str) -> str | None:
    """'TX23' -> 'house:TX-23', 'AK00' -> 'house:AK-AL'."""
    if len(sd) != 4 or not sd[:2].isalpha() or not sd[2:].isdigit():
        return None
    return f"house:{sd[:2]}-{'AL' if sd[2:] == '00' else sd[2:]}"


def from_clerk(xml_text: str | bytes) -> tuple[dict[str, dict], str]:
    """race id -> {held, holder, note} for every House seat, and the file's
    publish date. A vacancy counts for its last member's party."""
    root = ET.fromstring(xml_text)
    published = root.get("publish-date", "")
    out = {}
    for m in root.iter("member"):
        rid = _race_id(m.findtext("statedistrict") or "")
        mi = m.find("member-info")
        if rid is None or mi is None:
            continue
        party = (mi.findtext("party") or "").strip()
        name = (mi.findtext("official-name") or "").strip()
        note = ""
        if not party:
            pi = m.find("predecessor-info")
            if pi is None:
                continue
            party = (pi.findtext("pred-party") or "").strip()
            name = (pi.findtext("pred-official-name") or "").strip()
            note = (pi.findtext("pred-footnote") or "vacant").strip()
        if party:
            out[rid] = {"held": CODE.get(party, party), "holder": name, "note": note}
    return out, published


def build(clerk: dict[str, dict]) -> list[dict]:
    rows = []
    for ch in ("house", "senate", "governor"):
        with open(RACES / f"{ch}.csv", newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if ch == "house" and r["id"] in clerk:
                    rows.append({"race": r["id"], **clerk[r["id"]]})
                elif r.get("inc_party"):
                    rows.append({"race": r["id"], "held": r["inc_party"], "holder": r.get("incumbent", ""),
                                 "note": "" if ch != "house" else "not in the Clerk's list: the incumbent running"})
    return rows


def load() -> dict[str, str]:
    """race id -> the party holding the seat now (empty if the table is missing)."""
    try:
        with open(PATH, newline="", encoding="utf-8") as f:
            return {r["race"]: r["held"] for r in csv.DictReader(f) if r.get("held")}
    except OSError:
        return {}


def main(argv: list[str]) -> None:
    if argv:
        raw = Path(argv[0]).read_bytes()
    else:
        import urllib.request
        req = urllib.request.Request(CLERK_URL, headers={
            "User-Agent": "MIDTERMS2026-pipeline/0.1 (+https://github.com/KaraZajac/MIDTERMS2026)"})
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read()
    clerk, published = from_clerk(raw)
    rows = build(clerk)
    DIR.mkdir(parents=True, exist_ok=True)
    with open(PATH, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLS, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    (DIR / "sources.yaml").write_text(yaml.safe_dump({"clerk": {
        "url": CLERK_URL, "published": published,
        "fetched": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "note": "House seats by district number; Senate and governors from data/races (incumbents)"}},
        sort_keys=False))
    print(f"✓ holders: {len(rows)} seats (Clerk list published {published}) -> {PATH}")


if __name__ == "__main__":
    main(sys.argv[1:])
