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

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from midterms.pipeline import civic, fetch

RACE = "https://civicapi.org/api/v2/race/{id}"
CHAMBERS = ("senate", "governor")
WORKERS = 3
BUDGET = 150          # seconds for a whole cycle (the server's limit on the job is 200)
TIMEOUT = 25
TRIP = 3              # failures in a row that end a cycle
KEEP_IDS = 3600       # a kept search answer this old still names the races


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


def regions(c: dict, race: dict) -> tuple[list[dict], int]:
    """A civicAPI race's counties, by our sides; and how many regions had no
    usable FIPS."""
    rr = c.get("region_results") or {}
    counties: dict[str, dict] = {}
    dropped = 0
    for g in (rr.values() if isinstance(rr, dict) else rr):
        fips = str((g or {}).get("fips") or "")
        if not fips.isdigit() or len(fips) < 5:
            dropped += 1
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


def coverage(c: dict, regs: list[dict]) -> float | None:
    """The counties' votes as a share of the race's own total (None before
    any votes). Where civicAPI reports below the county level without FIPS
    (Massachusetts' 351 towns), the counties fall short of the total, and a
    map of them would show counted places as empty."""
    total = _votes(c.get("candidates"))
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
               "total": _votes(c.get("candidates")), "coverage": None if cov is None else round(cov, 3),
               "regions": regs, "dropped": dropped}
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

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for rid, cid in sorted(todo.items()):
            pool.submit(one, rid, cid)
    out = {k: state[k] for k in ("written", "failed", "skipped")}
    print(f"✓ counties: {len(todo)} races with votes; {out['written']} written, {out['failed']} failed, "
          f"{out['skipped']} not tried{' (stopped after failures)' if state['tripped'] else ''} -> {out_dir}")
    return out


def main(cache_dir: str, out_dir: str) -> None:
    run(Path(cache_dir), Path(out_dir))
