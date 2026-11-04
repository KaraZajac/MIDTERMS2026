"""County results for the statewide races (Senate, governor), from civicAPI.

    midterms counties --cache-dir DIR --out-dir DIR/counties

The web server runs this every few minutes on election night. civicAPI's
`race/{id}` carries a race's results by county (`region_results`: name,
FIPS, percent reporting, each candidate's votes). The race ids come from the
searches the live job keeps beside its live.json (civic.KEEP's files), so
this adds no searches. Only races with votes are fetched, a few at a time,
one try each; a cycle stops after a few failures in a row, so it never adds
to an outage, and a race that fails keeps its last file. One file per race,
at <out-dir>/<chamber>/<slug>.json (the race page's path: senate/ga.json,
senate/oh-special.json); the contract is in docs/site-data.md.

Counties are keyed by 5-digit FIPS. Where civicAPI reports towns with longer
FIPS (New England's county subdivisions), they are added up into their
county, whose percent reporting is then unknown (null). Regions without a
FIPS (Alaska's legislative districts) are dropped: such a file may have no
regions, and the page then shows no map.
"""

from __future__ import annotations

import datetime as dt
import functools
import json
import random
import re
import unicodedata
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from midterms.paths import ROOT
from midterms.pipeline import civic, fetch

RACE = "https://civicapi.org/api/v2/race/{id}"
CHAMBERS = ("senate", "governor")
WORKERS = 3
BUDGET = 150          # seconds for a whole cycle (the server's limit on the job is 200)
TIMEOUT = 25
TRIP = 5              # failures in a row that end a cycle
KEEP_IDS = 3600       # a kept search answer this old still names the races
DOWN = 360            # a live.json older than this: civicAPI isn't answering; skip the cycle
                      # (the live job's last run failed, every minute or every 5 minutes)


def _side_rows() -> dict[str, dict]:
    """Our races with their nominees as frozen in the forecast of record,
    as `midterms live` matches them."""
    from midterms.pipeline import livefeed
    fc, _, _ = livefeed.forecast_of_record(livefeed.now_utc())
    rows = livefeed.race_rows()
    return {rid: {**rows.get(rid, {}), **{k: m[k] for k in ("state", "d_cand", "r_cand", "d_side") if m.get(k)}}
            for rid, m in fc["races"].items()}


def targets(cache: Path, rows: dict[str, dict]) -> dict[str, int]:
    """race id -> civicAPI id, for the statewide races with votes in the
    kept search answers."""
    ids, out = set(rows), {}
    for name in civic.QUERIES:
        kept = civic._kept(cache, name, KEEP_IDS)
        for c in (kept[0] if kept else []):
            rid = civic.race_id(c, ids)
            if rid is None or rid.split(":")[0] not in CHAMBERS or c.get("id") is None:
                continue
            votes = 0
            for x in c.get("candidates") or []:
                try:
                    votes += int(x.get("votes") or 0)
                except (TypeError, ValueError):
                    pass
            if votes > 0:
                out[rid] = c["id"]
    return out


# Independent cities are county equivalents with their own FIPS, and civicAPI
# sends them without one (Virginia's 38 held a quarter of its Senate votes at
# 02:05 UTC, Nov 4). Codes as in the site's county shapes (us-atlas, Census).
CITIES = {
    "VA": {"alexandria": "51510", "bristol": "51520", "buena vista": "51530", "charlottesville": "51540",
           "chesapeake": "51550", "colonial heights": "51570", "covington": "51580", "danville": "51590",
           "emporia": "51595", "fairfax": "51600", "falls church": "51610", "franklin": "51620",
           "fredericksburg": "51630", "galax": "51640", "hampton": "51650", "harrisonburg": "51660",
           "hopewell": "51670", "lexington": "51678", "lynchburg": "51680", "manassas": "51683",
           "manassas park": "51685", "martinsville": "51690", "newport news": "51700", "norfolk": "51710",
           "norton": "51720", "petersburg": "51730", "poquoson": "51735", "portsmouth": "51740",
           "radford": "51750", "richmond": "51760", "roanoke": "51770", "salem": "51775",
           "staunton": "51790", "suffolk": "51800", "virginia beach": "51810", "waynesboro": "51820",
           "williamsburg": "51830", "winchester": "51840"},
    "MD": {"baltimore": "24510"},
    "NV": {"carson": "32510"},
}


def city_fips(state: str | None, name: str | None) -> str | None:
    """'Richmond City', 'City of Richmond' or 'Richmond' (a region sent
    without FIPS, so not the county of that name, which comes with one)."""
    n = " ".join((name or "").lower().replace("saint ", "st. ").split())
    if not n or "county" in n:
        return None
    if n.startswith("city of "):
        n = n[8:]
    if n.endswith(" city"):
        n = n[:-5]
    return CITIES.get(state or "", {}).get(n.strip())


SHAPES = ROOT / "site" / "src" / "data" / "county-shapes"     # [fips, name, path] per state (Census)
COUNTY_TYPES = {"county", "parish", "borough", "city", "independent city"}


def _norm(name: str | None) -> str:
    """'Lac Qui Parle' = 'Lac qui Parle', 'Mcleod' = 'McLeod', 'Saint Louis' =
    'St. Louis', 'Doña Ana' = 'Dona Ana', 'De Kalb' = 'DeKalb'."""
    s = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode().lower()
    s = re.sub(r"\s*\(.*\)\s*$", "", s)           # "Albany (Active Registered Voters: 211,266)"
    s = re.sub(r"\bsaint\b", "st", s)
    s = re.sub(r"\b(county|parish|borough)\b", "", s)
    return re.sub(r"[^a-z0-9]", "", s)


@functools.lru_cache(maxsize=None)
def county_names(state: str) -> dict[str, str]:
    """A state's county names -> FIPS, from the site's county shapes, so a
    match is always a county the map can draw. A name two counties share
    (Virginia's Richmond city and county) is left out."""
    try:
        rows = json.loads((SHAPES / f"{state}.json").read_text())["counties"]
    except (OSError, ValueError, KeyError, TypeError):
        return {}
    seen: dict[str, set] = {}
    for row in rows:
        seen.setdefault(_norm(row[1]), set()).add(str(row[0]))
    return {k: next(iter(v)) for k, v in seen.items() if k and len(v) == 1}


def name_fips(state: str | None, name: str | None, kind: str | None) -> str | None:
    """A county sent without FIPS, by its name (civicAPI sent all 62 of New
    York's that way, and Minnesota's 'Mcleod'); never a town or a state."""
    if kind and str(kind).lower() not in COUNTY_TYPES:
        return None
    return county_names(state or "").get(_norm(name))


def aggregate(g: dict | None) -> bool:
    """New York's feed carries an 'All Counties' row beside its counties."""
    return _norm((g or {}).get("name")).startswith("allcounties")


def regions(c: dict, race: dict) -> tuple[list[dict], list[str]]:
    """A civicAPI race's counties, by our sides; and the names of the regions
    without a usable FIPS (left out)."""
    rr = c.get("region_results") or {}
    counties: dict[str, dict] = {}
    dropped: list[str] = []
    for g in (rr.values() if isinstance(rr, dict) else rr):
        if aggregate(g):
            continue                                 # the counties again, summed
        fips = str((g or {}).get("fips") or "")
        if not fips.isdigit() or len(fips) < 5:
            fips = (city_fips(race.get("state"), (g or {}).get("name"))
                    or name_fips(race.get("state"), (g or {}).get("name"), (g or {}).get("type")) or "")
        if not fips.isdigit() or len(fips) < 5:
            dropped.append(str((g or {}).get("name") or "?"))
            continue
        r = civic.result(g, race)
        key, town = fips[:5], len(fips) > 5
        row = counties.setdefault(key, {"fips": key, "name": None if town else g.get("name"),
                                        "pct_reporting": None if town else r["pct_reporting"],
                                        "votes": {"D": 0, "R": 0, "other": 0},
                                        "matched": True})
        for k in ("D", "R", "other"):
            row["votes"][k] += r["votes"][k]
        row["matched"] = row["matched"] and r["matched"]["D"] and r["matched"]["R"]
    out = []
    for key in sorted(counties):
        row = counties[key]
        v, both = row["votes"], row.pop("matched")
        two = v["D"] + v["R"]
        row["margin"] = round(100 * (v["D"] - v["R"]) / two, 1) if two and both else None
        out.append(row)
    return out, dropped


def _votes(cands) -> int:
    total = 0
    for x in cands or []:
        try:
            total += int(x.get("votes") or 0)
        except (TypeError, ValueError):
            pass
    return total


def double_counted(c: dict) -> int | None:
    """The votes of an 'All Counties' row when the race's total is it plus the
    counties again (civicAPI's New York feed: every race exactly double,
    checked on NY-12, NY-16, NY-17 and the governor, Nov 4); else None."""
    rr = c.get("region_results") or {}
    agg = [g for g in (rr.values() if isinstance(rr, dict) else rr) if aggregate(g)]
    if len(agg) != 1:
        return None
    a, total = _votes(agg[0].get("candidates")), _votes(c.get("candidates"))
    return a if a and abs(total - 2 * a) <= 0.01 * total else None


def coverage(c: dict, regs: list[dict]) -> float | None:
    """The counties' votes as a share of the race's own total (None before
    any votes). Where civicAPI reports below the county level without FIPS
    (Massachusetts' 351 towns), the counties fall short of the total, and a
    map of them would show counted places as empty."""
    total = _votes(c.get("candidates")) - (double_counted(c) or 0)
    if not total:
        return None
    return sum(sum(g["votes"].values()) for g in regs) / total


COMPLETE = (0.97, 1.03)     # the counties must add up to the race's total, within this


def _write(path: Path, doc: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(doc, separators=(",", ":"), ensure_ascii=False))
    tmp.replace(path)


def path_for(out_dir: Path, rid: str) -> Path:
    chamber, slug = rid.split(":")
    return out_dir / chamber / f"{slug.lower()}.json"


def run(cache: Path, out_dir: Path, *, rows: dict[str, dict] | None = None,
        budget: float = BUDGET) -> dict[str, int]:
    """One cycle: fetch each target race's counties and write its file.
    Returns counts: written, failed, skipped (not tried: the cycle tripped
    or ran out of time)."""
    rows = rows if rows is not None else _side_rows()
    todo = targets(cache, rows)
    deadline = time.monotonic() + budget
    lock, state = threading.Lock(), {"run": 0, "tripped": False, "written": 0, "failed": 0, "skipped": 0}

    def one(rid: str, cid: int) -> None:
        with lock:
            left = deadline - time.monotonic()
            if state["tripped"] or left < 10:
                state["skipped"] += 1
                return
        fetched = fetch.now_utc()
        try:
            raw = fetch.get(RACE.format(id=cid), timeout=max(5, min(TIMEOUT, int(left) - 5)), retries=1,
                            gzip=True, headers={"User-Agent": civic.UA, "Accept": "application/json"})
            c = json.loads(raw)
            if not isinstance(c, dict) or "region_results" not in c:
                raise ValueError("no region_results")
            regs, dropped = regions(c, rows[rid])
        except (SystemExit, Exception) as e:          # a download, a bad body: this race only
            with lock:
                state["failed"] += 1
                state["run"] += 1
                state["tripped"] = state["tripped"] or state["run"] >= TRIP
            print(f"  ! counties {rid}: {e}", flush=True)
            return
        cov = coverage(c, regs)
        doc = {"generated": fetch.now_utc(), "fetched": fetched, "race": rid, "civic_id": cid,
               "source": {"name": "civicAPI", "url": "https://civicapi.org", "credit": civic.ATTRIBUTION},
               "total": _votes(c.get("candidates")) - (double_counted(c) or 0),
               "double_counted": double_counted(c) is not None,
               "coverage": None if cov is None else round(cov, 3),
               "regions": regs, "dropped": len(dropped), "dropped_names": sorted(dropped)[:60]}
        if cov is not None and not COMPLETE[0] <= cov <= COMPLETE[1]:
            doc["regions"] = []                       # counties that don't add up: no map
            doc["note"] = ("civicAPI reports this state's results by town" if dropped
                           else "civicAPI's county results don't add up to the state's total yet")
        try:
            _write(path_for(out_dir, rid), doc)
        except OSError as e:
            with lock:
                state["failed"] += 1
            print(f"  ! counties {rid}: not written: {e}", flush=True)
            return
        with lock:
            state["written"] += 1
            state["run"] = 0

    try:                                         # the live job's file: each race's forecast
        live = json.loads((cache / "live.json").read_text())
    except (OSError, ValueError):
        live = None
    try:
        p_pre = {rid: r.get("p_pre") for rid, r in live["races"].items()}
    except (KeyError, TypeError, AttributeError):
        p_pre = {}
    try:                                         # civicAPI down (Nov 4, 04:14 UTC on): ask nothing
        made = dt.datetime.strptime(live["generated"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
        age = (dt.datetime.now(dt.timezone.utc) - made).total_seconds()
    except (KeyError, TypeError, ValueError):
        age = None
    if age is not None and age > DOWN:
        print(f"✓ counties: skipped; live.json is {age / 60:.0f} min old, so civicAPI isn't answering")
        return {"written": 0, "failed": 0, "skipped": len(todo)}

    def need(rid: str) -> tuple[int, float]:
        """(0, 0) for a race with no map yet (no file, or an empty one from
        before dropped_names, which today's code may fill); else (1, age)."""
        p = path_for(out_dir, rid)
        try:
            d = json.loads(p.read_text())
            if isinstance(d, dict) and (d.get("regions") or "dropped_names" in d):
                return 1, p.stat().st_mtime
        except (OSError, ValueError):
            pass
        return 0, 0.0

    def close(rid: str) -> float:
        p = p_pre.get(rid)
        return abs(p - 0.5) if isinstance(p, (int, float)) else 1.0

    # races without a map first, the closest first (Iowa before Wyoming), then
    # the oldest file: a cycle that stops early (civicAPI failing) doesn't keep
    # retrying the same few races, and the races people watch fill in first
    order = sorted(todo, key=lambda rid: (*need(rid), close(rid), random.random()))
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for rid in order:
            pool.submit(one, rid, todo[rid])
    out = {k: state[k] for k in ("written", "failed", "skipped")}
    print(f"✓ counties: {len(todo)} races with votes; {out['written']} written, {out['failed']} failed, "
          f"{out['skipped']} not tried{' (stopped after failures)' if state['tripped'] else ''} -> {out_dir}")
    return out


def main(cache_dir: str, out_dir: str) -> None:
    run(Path(cache_dir), Path(out_dir))
