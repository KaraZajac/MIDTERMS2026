"""Validation gate: structural and consistency checks over data/ and the
forecast. Run by `make verify`, the pre-commit hook and CI; a non-zero exit
blocks the commit.

Checks only what must be true regardless of source quirks:
  - every state has its 2020-apportionment number of districts (435 total),
    ids unique, exactly one row per district
  - 35 Senate races (33 Class 2 + OH/FL specials), 36 governorships
  - polls: valid dates (not after the as-of date), shares in [0, 100]
  - forecast: probabilities in [0, 1], seat histograms sum to 1, every race
    on the ballot has a forecast, fixed races are certain
"""

from __future__ import annotations

import csv
import datetime
import json
import math
from collections import Counter, defaultdict

import yaml

from midterms.paths import CURATED, DATA, FORECAST, POLLS, RACES
from midterms.pipeline import excluded, votehub

APPORTIONMENT_2020 = {
    "AL": 7, "AK": 1, "AZ": 9, "AR": 4, "CA": 52, "CO": 8, "CT": 5, "DE": 1,
    "FL": 28, "GA": 14, "HI": 2, "ID": 2, "IL": 17, "IN": 9, "IA": 4, "KS": 4,
    "KY": 6, "LA": 6, "ME": 2, "MD": 8, "MA": 9, "MI": 13, "MN": 8, "MS": 4,
    "MO": 8, "MT": 2, "NE": 3, "NV": 4, "NH": 2, "NJ": 12, "NM": 3, "NY": 26,
    "NC": 14, "ND": 1, "OH": 15, "OK": 5, "OR": 6, "PA": 17, "RI": 2, "SC": 7,
    "SD": 1, "TN": 9, "TX": 38, "UT": 4, "VT": 1, "VA": 11, "WA": 10, "WV": 2,
    "WI": 8, "WY": 1,
}
assert sum(APPORTIONMENT_2020.values()) == 435


class Gate:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.checks = 0

    def check(self, ok: bool, msg: str) -> None:
        self.checks += 1
        if not ok:
            self.errors.append(msg)


def _csv(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def check_races(g: Gate) -> None:
    house = RACES / "house.csv"
    if house.exists():
        rows = _csv(house)
        ids = [r["id"] for r in rows]
        g.check(len(ids) == 435, f"house.csv has {len(ids)} rows, want 435")
        dup = [k for k, v in Counter(ids).items() if v > 1]
        g.check(not dup, f"duplicate house ids: {dup[:5]}")
        per_state = Counter(r["state"] for r in rows)
        for st, n in APPORTIONMENT_2020.items():
            g.check(per_state.get(st, 0) == n,
                    f"house: {st} has {per_state.get(st, 0)} districts, want {n}")
        for r in rows:
            if r.get("lean") not in (None, ""):
                lean = float(r["lean"])
                g.check(-100 < lean < 100, f"house {r['id']}: lean {lean} out of range")
            g.check(r.get("fixed", "") in ("", "D", "R", "I", "L", "G", "O"),
                    f"house {r['id']}: bad fixed {r.get('fixed')!r}")
    cur = yaml.safe_load((CURATED / "chambers.yaml").read_text())
    for chamber, want in (("senate", 35), ("governor", 36)):
        path = RACES / f"{chamber}.csv"
        if not path.exists():
            continue
        rows = _csv(path)
        g.check(len(rows) == want, f"{chamber}.csv has {len(rows)} races, want {want}")
        g.check(len({r['id'] for r in rows}) == len(rows), f"{chamber}: duplicate ids")
    sen = cur["senate"]
    g.check(len(sen["class2"]) == 33, "curated senate.class2 must list 33 states")
    g.check(sum(sen["seats_not_up"].values()) + 35 == 100, "senate seats must total 100")
    gov = cur["governor"]
    g.check(len(gov["up"]) == 36 and len(gov["not_up"]) == 14, "governor lists 36 + 14")


def check_polls(g: Gate, asof: str) -> None:
    if not POLLS.exists():
        return
    for path in sorted(POLLS.glob("*.csv")):
        for i, r in enumerate(_csv(path)):
            where = f"{path.name}:{i + 2}"
            try:
                end = datetime.date.fromisoformat(r["end"])
            except (KeyError, ValueError):
                g.check(False, f"{where}: bad end date {r.get('end')!r}")
                continue
            g.check(end.isoformat() <= asof, f"{where}: poll ends after as-of ({end})")
            for k in ("d", "r", "approve", "disapprove"):
                if r.get(k) not in (None, ""):
                    v = float(r[k])
                    g.check(0 <= v <= 100, f"{where}: {k}={v} outside [0,100]")
            src = r.get("source") or ""
            g.check(src.startswith(("wikipedia:", "votehub:")), f"{where}: unknown source {src!r}")
            fake = excluded.match(r.get("pollster", ""))
            g.check(fake is None, f"{where}: {r.get('pollster')!r} is excluded as a fabricator "
                    f"({fake and fake['name']}, curated/excluded_pollsters.yaml)")
    # the VoteHub supplement never double-counts a poll Wikipedia carries
    races_csv = POLLS / "races.csv"
    if races_csv.exists():
        rows = _csv(races_csv)
        wiki_by_race = defaultdict(list)
        for r in rows:
            if (r.get("source") or "").startswith("wikipedia:"):
                wiki_by_race[r["race"]].append(r)
        for r in rows:
            if (r.get("source") or "").startswith("votehub:"):
                dup = next((w for w in wiki_by_race[r["race"]] if votehub.is_duplicate(r, w)), None)
                g.check(dup is None, f"races.csv: VoteHub poll {r['source']} ({r['race']}, "
                        f"{r['pollster']} {r['end']}) duplicates Wikipedia's "
                        f"{dup and dup['pollster']} {dup and dup['end']}")


def check_forecast(g: Gate) -> None:
    path = FORECAST / "latest.json"
    if not path.exists():
        return
    fc = json.loads(path.read_text())
    for version, v in fc.get("versions", {}).items():
        for cname, ch in v["chambers"].items():
            s = sum(ch["hist"].values())
            g.check(abs(s - 1) < 1e-6, f"{version}/{cname}: histogram sums to {s}")
            pc = ch["p_control"]
            g.check(abs(sum(pc.values()) - 1) < 1e-6, f"{version}/{cname}: control sums != 1")
        for rid, r in v["races"].items():
            p = r["p_d_side"]
            g.check(0 <= p <= 1 and not math.isnan(p), f"{version}/{rid}: p={p}")
    races = fc.get("races", {})
    for rid, r in races.items():
        if r.get("fixed"):
            for version, v in fc.get("versions", {}).items():
                p = v["races"][rid]["p_d_side"]
                g.check(p in (0.0, 1.0), f"{version}/{rid}: fixed race has p={p}")


def check_site(g: Gate) -> None:
    """data/site/ must be complete and agree with the forecast it came from."""
    from midterms.paths import SITE
    want = ["summary", "races", "polls", "generic", "history", "sim", "backtest", "meta"]
    if not SITE.exists():
        return
    for name in want:
        g.check((SITE / f"{name}.json").exists(), f"data/site/{name}.json missing")
    path = FORECAST / "latest.json"
    if not (path.exists() and (SITE / "summary.json").exists() and (SITE / "races.json").exists()):
        return
    fc = json.loads(path.read_text())
    summ = json.loads((SITE / "summary.json").read_text())
    g.check(summ["generated"] == fc["generated"], "data/site/ is stale: rerun `midterms export`")
    for name in want:
        path_n = SITE / f"{name}.json"
        if path_n.exists():
            doc = json.loads(path_n.read_text())
            g.check(isinstance(doc, dict) and "generated" in doc and "asof" in doc,
                    f"data/site/{name}.json lacks the generated/asof envelope")
    races = json.loads((SITE / "races.json").read_text())["races"]
    g.check(len(races) == len(fc["races"]), f"races.json has {len(races)} races, forecast {len(fc['races'])}")
    slugs = [r["slug"] for r in races]
    g.check(len(set(slugs)) == len(slugs), "duplicate race slugs")
    for r in races:
        for v, f in r["forecast"].items():
            p = f["p_d_side"]
            g.check(abs(sum(f["p_party"].values()) - 1) < 1e-3, f"site {r['id']}/{v}: p_party sums to "
                    f"{sum(f['p_party'].values())}")
            g.check(p is not None and 0 <= p <= 1, f"site {r['id']}/{v}: p={p}")
            if r["fixed"]:
                g.check(p in (0.0, 1.0), f"site {r['id']}: fixed race p={p}")


def main() -> int:
    g = Gate()
    meta_path = DATA / "meta.yaml"
    asof = datetime.date.today().isoformat()
    if meta_path.exists():
        meta = yaml.safe_load(meta_path.read_text()) or {}
        asof = max(asof, str(meta.get("asof", asof)))
    check_races(g)
    check_polls(g, asof)
    check_forecast(g)
    check_site(g)
    if g.errors:
        print(f"✗ verify: {len(g.errors)} of {g.checks} checks failed")
        for e in g.errors[:40]:
            print("  -", e)
        return 1
    print(f"✓ verify: {g.checks} checks passed")
    return 0
