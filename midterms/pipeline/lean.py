"""Partisan lean of every district (2026 lines) and state.

lean = w * (district 2024 two-party margin - national 2024)
     + (1 - w) * (district 2020 two-party margin - national 2020),  w = 0.75

(the 75/25 weighting Cook uses for its 2025 PVI; two-party margins in
points, D minus R). Where a district has no 2020 figure on its 2026 lines,
lean is 2024-only and flagged.

Sources, in order of preference:
  2024, all 435 districts   The Downballot, presidential results by
                            congressional district on the 2026 lines
  2020, unchanged lines     the same sheet
  2020, redrawn but some    The Downballot's 2024-lines sheet, for districts
    districts unchanged     whose 2024 votes are identical on both maps
  2020, the rest            Dave's Redistricting App block-level 2020
                            presidential votes (VEST) aggregated to the
                            2026 districts with the Census Bureau's
                            120th-Congress block equivalency file

The Downballot asks that its spreadsheets not be reproduced wholesale, so
raw copies stay in sources/ (gitignored); data/ carries only the derived
margins and leans, with attribution.
"""

from __future__ import annotations

import csv
import io
import zipfile
from collections import defaultdict

from midterms.paths import SOURCES
from midterms.pipeline import fetch

DB_2026 = ("https://docs.google.com/spreadsheets/d/1eZfaFI-c-PFOoKx1-zZA2MP0_dxRq_LVK0re3BOQqy0/"
           "export?format=csv&gid=1491069057")
DB_2024 = ("https://docs.google.com/spreadsheets/d/1ng1i_Dm_RMDnEvauH44pgE6JCUsapcuu8F2pCfeLWFo/"
           "export?format=csv&gid=1491069057")
BEF = ("https://www2.census.gov/programs-surveys/decennial/rdo/mapping-files/2027/"
       "120-congressional-district-befs/cd120.zip")
DRA = "https://data.dra2020.net/file/dra-block-data/Election_Data_Block_{st}.v07.zip"
REDRAWN = ["AL", "CA", "FL", "LA", "NC", "OH", "TN", "TX", "UT"]
FIPS = {"AL": "01", "CA": "06", "FL": "12", "LA": "22", "NC": "37", "OH": "39",
        "TN": "47", "TX": "48", "UT": "49"}

# National presidential popular vote (two-party), FEC official results
NATIONAL = {2024: (75_017_613, 77_302_580), 2020: (81_283_501, 74_223_975)}
W24 = 0.75


def two_party(d: float, r: float) -> float:
    return 100.0 * (d - r) / (d + r)


def national_margin(year: int) -> float:
    d, r = NATIONAL[year]
    return two_party(d, r)


def pull(force: bool = False) -> None:
    print("lean: presidential results by district")
    fetch.fetch_to("downballot-pres-by-cd-2026-lines", DB_2026, "lean/downballot-2026-lines.csv",
                   force=force)
    fetch.fetch_to("downballot-pres-by-cd-2024-lines", DB_2024, "lean/downballot-2024-lines.csv",
                   force=force)
    fetch.fetch_to("census-cd120-bef", BEF, "blocks/cd120.zip", force=force)
    for st in REDRAWN:
        fetch.fetch_to(f"dra-blocks-{st}", DRA.format(st=st), f"blocks/dra-{st}.zip", force=force)


def _num(x: str) -> int | None:
    x = (x or "").replace(",", "").strip()
    try:
        return int(x) if x else None
    except ValueError:
        return None


def read_downballot(path) -> dict:
    """district -> {'d24','r24','t24','d20','r20','t20'} (ints or None)."""
    out = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.reader(f):
            if not row or "-" not in row[0] or len(row[0]) > 6:
                continue
            st, _, n = row[0].partition("-")
            if len(st) != 2 or not (n == "AL" or n.isdigit()):
                continue
            g = row + [""] * 17
            out[row[0]] = {"d24": _num(g[4]), "r24": _num(g[5]), "t24": _num(g[6]),
                           "d20": _num(g[11]), "r20": _num(g[12]), "t20": _num(g[13]),
                           "incumbent": g[1], "party": g[2].strip("()")}
    return out


def aggregate_blocks(states: list[str]) -> dict:
    """district -> {'d20','r20','d24','r24'} from DRA block data + the BEF."""
    bef = SOURCES / "blocks" / "cd120.zip"
    want = {FIPS[s]: s for s in states}
    blk2cd: dict[str, str] = {}
    with zipfile.ZipFile(bef) as z:
        names = z.namelist()
        for fips, st in want.items():
            # one file per state (CD120_48.txt); fall back to the national file
            name = next((n for n in names if n.endswith(f"CD120_{fips}.txt")), None) or \
                next(n for n in names if "national" in n.lower())
            with z.open(name) as f:
                t = io.TextIOWrapper(f, encoding="utf-8")
                next(t)
                for line in t:
                    p = line.rstrip("\n").split(",")
                    if len(p) > 5 and p[1] == fips:
                        blk2cd[p[0]] = f"{st}-" + ("AL" if p[5] == "00" else p[5])
    fields = ["E_20_PRES_Dem", "E_20_PRES_Rep", "E_24_PRES_Dem", "E_24_PRES_Rep"]
    agg: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0, 0])
    for st in states:
        path = SOURCES / "blocks" / f"dra-{st}.zip"
        with zipfile.ZipFile(path) as z:
            name = next(n for n in z.namelist() if n.endswith(".csv"))
            with z.open(name) as f:
                r = csv.reader(io.TextIOWrapper(f, encoding="utf-8"))
                hdr = next(r)
                idx = [hdr.index(c) for c in fields]
                for row in r:
                    if not row:
                        continue
                    cd = blk2cd.get(row[0])
                    if cd is None:
                        continue
                    a = agg[cd]
                    for i, j in enumerate(idx):
                        a[i] += int(float(row[j] or 0))
    return {cd: {"d20": a[0], "r20": a[1], "d24": a[2], "r24": a[3]} for cd, a in agg.items()}


def build() -> tuple[dict, dict]:
    """(district rows, state rows) keyed 'TX-28' / 'TX'."""
    db26 = read_downballot(SOURCES / "lean" / "downballot-2026-lines.csv")
    db24 = read_downballot(SOURCES / "lean" / "downballot-2024-lines.csv")
    if len(db26) != 435:
        raise SystemExit(f"downballot 2026-lines sheet: {len(db26)} districts, want 435")
    need_blocks = sorted({cd.split("-")[0] for cd, v in db26.items() if v["d20"] is None})
    have_blocks = all((SOURCES / "blocks" / f"dra-{st}.zip").exists() for st in need_blocks) \
        and (SOURCES / "blocks" / "cd120.zip").exists()
    blocks = aggregate_blocks(need_blocks) if (need_blocks and have_blocks) else {}
    n24, n20 = national_margin(2024), national_margin(2020)
    rows = {}
    for cd, v in sorted(db26.items()):
        m24 = two_party(v["d24"], v["r24"])
        src20 = "downballot-2026-lines"
        d20, r20 = v["d20"], v["r20"]
        if d20 is None:
            old = db24.get(cd)
            if old and (old["d24"], old["r24"]) == (v["d24"], v["r24"]) and old["d20"]:
                d20, r20, src20 = old["d20"], old["r20"], "downballot-2024-lines (unchanged)"
            elif cd in blocks:
                d20, r20, src20 = blocks[cd]["d20"], blocks[cd]["r20"], "dra-blocks"
            else:
                src20 = ""
        m20 = two_party(d20, r20) if d20 is not None else None
        rel24 = m24 - n24
        if m20 is not None:
            lean = W24 * rel24 + (1 - W24) * (m20 - n20)
        else:
            lean = rel24
        rows[cd] = {"pres24_margin": round(m24, 2), "pres20_margin": "" if m20 is None else round(m20, 2),
                    "lean": round(lean, 2), "lean_basis": "2024+2020" if m20 is not None else "2024-only",
                    "pres20_source": src20,
                    "_votes": (v["d24"], v["r24"], d20, r20)}
    # states: sum their districts (districts partition each state exactly)
    st_sum = defaultdict(lambda: [0, 0, 0, 0, True])
    for cd, row in rows.items():
        d24, r24, d20, r20 = row["_votes"]
        s = st_sum[cd.split("-")[0]]
        s[0] += d24
        s[1] += r24
        if d20 is None:
            s[4] = False
        else:
            s[2] += d20
            s[3] += r20
    states = {}
    for st, (d24, r24, d20, r20, ok20) in sorted(st_sum.items()):
        m24 = two_party(d24, r24)
        m20 = two_party(d20, r20) if ok20 else None
        lean = W24 * (m24 - n24) + (1 - W24) * (m20 - n20) if m20 is not None else m24 - n24
        states[st] = {"pres24_margin": round(m24, 2),
                      "pres20_margin": "" if m20 is None else round(m20, 2),
                      "lean": round(lean, 2)}
    for row in rows.values():
        row.pop("_votes")
    return rows, states
