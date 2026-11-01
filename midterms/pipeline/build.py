"""`midterms build` — sources/ -> data/.

Writes (all committed; derived data, CC BY-SA 4.0 — see DATA-RIGHTS.md):

  data/races/house.csv       435 districts: nominees, D-side/R-side, incumbency,
                             fixed outcomes, 2024/2020 presidential margins, lean
  data/races/senate.csv      35 races (33 Class 2 + OH, FL specials)
  data/races/governor.csv    36 races
  data/polls/races.csv       every general-election head-to-head poll, as
                             D-side / R-side shares, with page + revision
  data/polls/generic.csv     generic congressional ballot polls
  data/averages.csv          outside polling averages (270toWin, DDHQ, RCP,
                             Silver Bulletin, ...) — challengers, not inputs
  data/ratings.csv           every handicapper rating Wikipedia compiles
  data/finance.csv           FEC individual contributions per side
  data/pollster_quality.csv  the weight each pollster's polls receive
  data/meta.yaml             provenance: every source's URL, fetch time,
                             sha256, Wikipedia revision ids; counts
"""

from __future__ import annotations

import csv
import datetime
import hashlib
import json
import re
from collections import Counter

import yaml

from midterms.model import pollsters as PQ
from midterms.paths import DATA, POLLS, RACES, SOURCES
from midterms.pipeline import fetch, finance, lean, races, states, wiki
from midterms.pipeline import wikipolls as wp
from midterms.pipeline.htmltable import extract_tables

RACE_COLS = ["id", "chamber", "state", "label", "incumbent", "inc_party", "inc_running",
             "first_elected", "d_cand", "d_side", "r_cand", "r_side", "others", "fixed",
             "lean", "pres24_margin", "pres20_margin", "lean_basis", "notes", "source"]
POLL_COLS = ["race", "pollster", "partisan", "start", "end", "n", "population", "d", "r",
             "other", "undecided", "d_label", "r_label", "source", "table"]


def _write(path, rows, cols):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in cols})


def _page(title: str) -> dict:
    return wiki.fetch_page(title, max_age_hours=None)


# ------------------------------------------------------------- overview

LOC_RE = re.compile(r"^(?P<state>[A-Za-z .]+?)\s+(?P<n>\d+|at-large|at large)$", re.I)


def first_elected() -> dict:
    """district label -> first year elected (incumbent), from the overview."""
    tables = extract_tables(_page(states.OVERVIEW["house"])["html"])
    out = {}
    for t in tables:
        st = states.ABBR.get(t.heading)
        if not st:
            continue
        for row in t.texts()[2:]:
            if len(row) < 5:
                continue
            m = LOC_RE.match(row[0])
            if not m:
                continue
            n = m.group("n")
            label = f"{st}-AL" if not n.isdigit() else f"{st}-{int(n):02d}"
            y = re.search(r"(19|20)\d\d", row[4])
            if y and label not in out:
                out[label] = y.group(0)
    return out


def generic_polls() -> tuple[list[dict], dict]:
    page = _page(states.GENERIC_BALLOT)
    src = f"wikipedia:{page['title']}@{page['revid']}"
    out = []
    asof = datetime.date.today().isoformat()
    for t in extract_tables(page["html"]):
        if not wp.is_poll_table(t):
            continue
        ys = re.findall(r"(20\d\d)", t.heading)
        year = int(ys[-1]) if ys else 2026
        for row in wp.rows(t, year):
            a = row["answers"]
            dk = next((k for k in a if k.lower().startswith("democ")), None)
            rk = next((k for k in a if k.lower().startswith("republ")), None)
            if not dk or not rk or not row["end"]:
                continue
            end = row["end"]
            if end > asof:      # typo'd future year ('December 2026')
                end = f"{int(end[:4]) - 1}{end[4:]}"
            start = row["start"] if row["start"] and row["start"] <= end else end
            out.append({"race": "generic", "pollster": row["pollster"], "partisan": row["partisan"] or "",
                        "start": start, "end": end, "n": row["n"] or "", "population": row["population"] or "",
                        "d": a[dk], "r": a[rk], "other": row["other"] if row["other"] is not None else "",
                        "undecided": row["undecided"] if row["undecided"] is not None else "",
                        "d_label": dk, "r_label": rk, "source": src, "table": t.index})
    return out, {"title": page["title"], "revid": page["revid"]}


def generic_averages() -> list[dict]:
    tables = extract_tables(_page(states.OVERVIEW["house"])["html"])
    out = []
    for t in tables:
        if not wp.is_average_table(t):
            continue
        for a in wp.averages(t, 2026):
            dk = next((k for k in a["answers"] if k.lower().startswith("democ")), None)
            rk = next((k for k in a["answers"] if k.lower().startswith("republ")), None)
            if dk and rk and a["source"].lower() != "average":
                out.append({"race": "generic", "source": a["source"], "end": a["end"] or "",
                            "updated": a["updated"] or "", "d": a["answers"][dk], "r": a["answers"][rk]})
    return out


LEAN_DIR = DATA / "lean"
# Only the blended lean index is committed for districts: The Downballot asks
# that its spreadsheets not be reproduced, and the per-year district margins
# would come close. (State margins are official results and are kept.)
LEAN_COLS = ["id", "lean", "lean_basis", "pres20_source"]


def lean_tables() -> tuple[dict, dict]:
    """Recompute lean when its raw sources are present (writing the derived
    tables to data/lean/), else reuse the committed derived tables — so CI
    refreshes never need the ~125 MB of block files."""
    raw = SOURCES / "lean" / "downballot-2026-lines.csv"
    if raw.exists():
        dist, st = lean.build()
        _write(LEAN_DIR / "districts.csv", [{"id": k, **v} for k, v in dist.items()], LEAN_COLS)
        _write(LEAN_DIR / "states.csv", [{"id": k, **v} for k, v in st.items()],
               ["id", "pres24_margin", "pres20_margin", "lean"])
        files = fetch.load_manifest().get("files", {})
        prov = {k: {"url": v["url"], "fetched": v["fetched"], "sha256": v["sha256"]}
                for k, v in files.items()
                if k.startswith(("downballot-pres-by-cd", "census-cd120", "dra-blocks"))}
        (LEAN_DIR / "sources.yaml").write_text(yaml.safe_dump(prov, sort_keys=True))
        return dist, st
    if not (LEAN_DIR / "districts.csv").exists():
        raise SystemExit("no lean sources and no data/lean/ — run `midterms pull --only lean`")
    with open(LEAN_DIR / "districts.csv", newline="") as f:
        dist = {r.pop("id"): r for r in csv.DictReader(f)}
    with open(LEAN_DIR / "states.csv", newline="") as f:
        st = {r.pop("id"): r for r in csv.DictReader(f)}
    return dist, st


# ----------------------------------------------------------------- main

def main() -> None:
    m = fetch.load_manifest()
    if not m.get("files"):
        raise SystemExit("sources/ is empty — run `midterms pull` first")
    print("build: races")
    house, statewide = [], []
    for rid, ch, title in states.race_pages():
        page = _page(title)
        if ch == "house":
            house += races.house_state(rid.split(":")[1], page)
        else:
            statewide.append(races.statewide(rid, ch, rid.split(":")[1][:2], page))
    # California's two pages each list only their districts; dedupe by id
    seen, uniq = set(), []
    for r in house:
        if r["race"]["id"] not in seen:
            seen.add(r["race"]["id"])
            uniq.append(r)
    house = sorted(uniq, key=lambda r: (r["race"]["state"], r["race"]["label"]))

    print("build: partisan lean")
    dist_lean, state_lean = lean_tables()
    fe = first_elected()
    for r in house:
        x = r["race"]
        L = dist_lean.get(x["label"])
        if L:
            x.update({k: L[k] for k in ("lean", "lean_basis")})
        x["first_elected"] = fe.get(x["label"], "") if x["inc_running"] == "yes" else ""
    for r in statewide:
        x = r["race"]
        L = state_lean[x["state"]]
        x.update({"lean": L["lean"], "pres24_margin": L["pres24_margin"],
                  "pres20_margin": L["pres20_margin"], "lean_basis": "state"})
        if x["d_side"] not in ("D",):
            x["notes"] = f"D-side is {x['d_cand']} ({x['d_side']})"

    print("build: finance (FEC individual contributions)")
    fec_idx = finance.index(finance.load())
    fin_rows = []
    for r in house + statewide:
        x = r["race"]
        office = "H" if x["chamber"] == "house" else ("S" if x["chamber"] == "senate" else None)
        if office is None or x["fixed"]:
            continue
        dist = "00" if office == "S" or x["label"].endswith("-AL") else x["label"].split("-")[1]
        for side, name, party in (("D", x["d_cand"], x["d_side"]), ("R", x["r_cand"], x["r_side"])):
            hit = finance.match(fec_idx, office, x["state"], dist, name, party) if name else None
            fin_rows.append({"race": x["id"], "side": side, "candidate": name,
                             "fec_id": hit["CAND_ID"] if hit else "",
                             "fec_name": hit["CAND_NAME"] if hit else "",
                             "receipts": round(hit["TTL_INDIV_CONTRIB"]) if hit else "",
                             "total_receipts": round(hit["TTL_RECEIPTS"]) if hit else "",
                             "cash_on_hand": round(hit["COH_COP"]) if hit else "",
                             "coverage_end": hit["CVG_END_DT"] if hit else ""})

    print("build: polls, ratings, averages")
    poll_rows = [p for r in house + statewide for p in r["polls"]]
    gen_rows, gen_page = generic_polls()
    rating_rows = [x for r in house + statewide for x in r["ratings"]]
    avg_rows = [x for r in house + statewide for x in r["averages"]] + generic_averages()

    print("build: pollster quality")
    ratings_db = PQ.load_ratings(SOURCES / "pollsters" / "silver-bulletin-2026-01.xlsx",
                                 SOURCES / "pollsters" / "fte-pollster-ratings-2024.csv")
    names = {p["pollster"] for p in poll_rows + gen_rows}
    quality = PQ.quality_table(names, ratings_db)

    by_ch = {"house": [r["race"] for r in house],
             "senate": [r["race"] for r in statewide if r["race"]["chamber"] == "senate"],
             "governor": [r["race"] for r in statewide if r["race"]["chamber"] == "governor"]}
    for ch, rows in by_ch.items():
        _write(RACES / f"{ch}.csv", rows, RACE_COLS)
    _write(POLLS / "races.csv", poll_rows, POLL_COLS)
    _write(POLLS / "generic.csv", gen_rows, POLL_COLS)
    _write(DATA / "ratings.csv", rating_rows, ["race", "rater", "source", "rating", "scale", "asof"])
    _write(DATA / "averages.csv", avg_rows, ["race", "source", "end", "updated", "d", "r"])
    _write(DATA / "finance.csv", fin_rows, ["race", "side", "candidate", "fec_id", "fec_name", "receipts",
                                            "total_receipts", "cash_on_hand", "coverage_end"])
    _write(DATA / "pollster_quality.csv", quality,
           ["pollster", "matched", "grade", "ppm", "banned", "weight", "rating_source"])

    # provenance
    files = m.get("files", {})
    wiki_revs = {k.split(":", 1)[1]: v.get("revid") for k, v in files.items() if k.startswith("wikipedia:")}
    other = {k: {"url": v["url"], "fetched": v["fetched"], "sha256": v["sha256"]}
             for k, v in files.items() if not k.startswith("wikipedia:")}
    digest = hashlib.sha256(json.dumps({"w": wiki_revs, "o": {k: v["sha256"] for k, v in other.items()}},
                                       sort_keys=True).encode()).hexdigest()[:16]
    latest_poll = max([p["end"] for p in poll_rows + gen_rows] or [""])
    meta = {
        "generated": fetch.now_utc(),
        "generator": "python3 -m midterms build",
        "asof": datetime.date.today().isoformat(),
        "election_day": "2026-11-03",
        "sources_digest": digest,
        "counts": {
            "house_races": len(by_ch["house"]), "senate_races": len(by_ch["senate"]),
            "governor_races": len(by_ch["governor"]),
            "fixed": dict(Counter(f"{r['chamber']}:{r['fixed']}" for rs in by_ch.values()
                                  for r in rs if r["fixed"])),
            "race_polls": len(poll_rows), "generic_polls": len(gen_rows),
            "polled_races": len({p["race"] for p in poll_rows}),
            "ratings": len(rating_rows), "outside_averages": len(avg_rows),
            "pollsters": len(quality),
            "pollsters_rated": sum(1 for q in quality if q["rating_source"]),
            "finance_matched": sum(1 for f in fin_rows if f["fec_id"]),
            "finance_rows": len(fin_rows),
            "latest_poll": latest_poll,
        },
        "sources": {"wikipedia_revisions": dict(sorted(wiki_revs.items())), "files": other,
                    "lean": "data/lean/sources.yaml", "backtest": "data/backtest.yaml (sources:)"},
    }
    (DATA / "meta.yaml").write_text(yaml.safe_dump(meta, sort_keys=False, allow_unicode=True))
    c = meta["counts"]
    print(f"✓ build: {c['house_races']} House / {c['senate_races']} Senate / {c['governor_races']} governor races; "
          f"{c['race_polls']} race polls in {c['polled_races']} races, {c['generic_polls']} generic-ballot polls; "
          f"{c['ratings']} ratings; FEC matched {c['finance_matched']}/{c['finance_rows']}; "
          f"pollsters rated {c['pollsters_rated']}/{c['pollsters']}")
