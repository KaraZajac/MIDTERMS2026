"""`midterms live` — election night: live.json for the site.

Fetches every race's count and call from civicAPI (civicapi.org), maps
them onto the forecast's races, and conditions the forecast of record on
the calls so far (model/live.py). Two places run it:

  * the web server, every minute through the night:
        python3 -m midterms live --out /srv/live/…/live.json.tmp
    It writes only that file: nothing on any failure (the last good file
    stays up), no caches, no other writes. The previous file beside it
    (the same name without .tmp) carries each call's first-seen time and
    the list of calls.
  * the refresh workflow, every 10–60 minutes: data/site/live.json, the
    committed record of the night and the site's build-time fallback.
    Same shape; the site shows whichever copy is newer.

    midterms live [--out PATH] [--previous PATH] [--draws N]
    midterms live --fixture HOUR --out PATH    a simulated night (testing)

The contract is in docs/site-data.md (live.json).
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import math
from pathlib import Path

import numpy as np
import yaml

from midterms.model import live as L
from midterms.paths import CURATED, DATA, FORECAST, RACES, SITE
from midterms.pipeline import civic, holders

DEADLINE = "2026-11-03T10:00:00Z"
MIDNIGHT_ET = dt.datetime(2026, 11, 3, 5, tzinfo=dt.timezone.utc)   # Nov 3, 00:00 EST (UTC-5)
HELD_NOTE = ("A seat changes hands when its winner's party differs from the party holding it now: "
             "House seats by district number (the Clerk of the House's member list; a vacant seat "
             "counts for its last member's party), Senate seats and governorships by incumbent.")
DRAWS = 40000            # ~7 s on one core; ±0.2 pts of simulation noise on control
SEED = 20261103
EVENTS_KEPT = 120
MIN_MAPPED = 480          # of 506: fewer means civicAPI returned a partial list
RELIABLE_ESS = 400
FIXTURE_SEED = 3
METHOD = ("The frozen forecast of record, updated only for the races called so far: each "
          "call shifts the errors races share (national, regional, state), and the races "
          "still out follow. Partial vote counts are not used.")


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _csv(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def race_rows() -> dict[str, dict]:
    return {r["id"]: r for ch in ("house", "senate", "governor") for r in _csv(RACES / f"{ch}.csv")}


def forecast_of_record(now: str) -> tuple[dict, str, bool]:
    """After the deadline, the last snapshot generated before it (what the
    scorecard grades); before it, the latest forecast."""
    if now >= DEADLINE:
        cut = DEADLINE.replace("-", "").replace(":", "")            # 20261103T100000Z
        snaps = [p for p in sorted((FORECAST / "snapshots").glob("*.json"))
                 if p.stem.replace("-", "") < cut]
        if snaps:
            fc = json.loads(snaps[-1].read_text())
            if fc["generated"] < DEADLINE:
                return fc, snaps[-1].name, True
    return json.loads((FORECAST / "latest.json").read_text()), "latest.json", False


def wikipedia_calls(fc: dict) -> dict[str, str]:
    """Races Wikipedia's results boxes have settled (data/scorecard.yaml,
    written by `midterms score` from the hold/gain lines): race -> side.
    A cross-check on civicAPI's calls, and the fallback when it is down."""
    path = DATA / "scorecard.yaml"
    if not path.exists():
        return {}
    try:
        sc = yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError:
        return {}
    out = {}
    for row in sc.get("races") or []:
        m = fc["races"].get(row.get("id"))
        if m and row.get("winner_name"):
            out[row["id"]] = "D" if row["winner_name"] == m.get("d_cand") else "R"
    return out


def _sim(fc: dict, rows: dict) -> dict:
    from midterms.pipeline.site_export import sim_params
    cur = yaml.safe_load((CURATED / "chambers.yaml").read_text())
    return sim_params(fc, cur, rows)


def _hist(h: dict) -> dict:
    xs = [x for x in sorted(h) if h[x] >= 5e-5] or sorted(h)
    lo, hi = xs[0], xs[-1]
    return {"min": lo, "p": [round(h.get(x, 0.0), 4) for x in range(lo, hi + 1)]}


def _r(x, k=4):
    return None if x is None else round(float(x), k)


def poll_closings() -> dict:
    """curated/poll_closing.yaml for live.json: each state's first and last
    poll closing (and districts that differ from their state) in UTC."""
    doc = yaml.safe_load((CURATED / "poll_closing.yaml").read_text())
    iso = lambda h: (MIDNIGHT_ET + dt.timedelta(hours=float(h))).strftime("%Y-%m-%dT%H:%M:%SZ")
    span = lambda v: {"first": iso(v["first"]), "last": iso(v["last"]),
                      **({"note": v["note"]} if v.get("note") else {})}
    return {"source": doc["source"],
            "states": {st: span(v) for st, v in doc["states"].items()},
            "races": {rid: span(v) for rid, v in (doc.get("races") or {}).items()}}


def reconcile(res: dict[str, dict], wiki: dict[str, str]) -> dict[str, dict]:
    """civicAPI's calls against Wikipedia's settled results: a race the two
    call differently is disputed (shown, not used); a race only Wikipedia
    has settled counts as called."""
    out = {rid: dict(r) for rid, r in res.items()}
    for rid, side in wiki.items():
        r = out.setdefault(rid, {"status": "awaiting"})
        if r.get("status") == "called" and r.get("winner") in ("D", "R") and r["winner"] != side:
            r.update(status="counting", disputed=True)
            r.pop("winner", None)
        elif r.get("status") != "called":
            r.update(status="called", winner=side, called_by="wikipedia")
    return out


def assemble(fc: dict, snapshot: str, of_record: bool, rows: dict, res: dict[str, dict],
             fetched: str | None, previous: dict | None, generated: str, *,
             draws: int = DRAWS, fixture: bool = False, wiki: dict | None = None,
             held: dict[str, str] | None = None) -> dict:
    head = fc["headline"]
    held = holders.load() if held is None else held
    res = reconcile(res, wiki or {})
    sim = _sim(fc, rows)
    eng = L.Engine(sim, version=head)
    def side_of(rid: str, r: dict) -> str:
        """The side a call goes to: an outright first-round winner who isn't
        one of our sides counts for the side of their party (Scalise: R)."""
        if r["winner"] == "other" and r.get("party"):
            if r["party"] == fc["races"][rid].get("d_side"):
                return "D"
            if r["party"] == (rows.get(rid, {}).get("r_side") or "R"):
                return "R"
        return r["winner"]

    calls = {rid: side_of(rid, r) for rid, r in res.items()
             if r.get("status") == "called" and not fc["races"][rid].get("fixed")}
    if calls:
        out = eng.run(calls, n=draws, seed=SEED)
    else:                   # nothing called yet: exactly the forecast of record, no simulation noise
        out = {"ess": draws, "draws": draws, "races": {rid: v["p_d_side"] for rid, v in
                                                       fc["versions"][head]["races"].items()},
               "chambers": {c: {"p_control": ch["p_control"],
                                "seats": {"mean": ch["d_seats_mean"], "p10": ch["d_seats_p10"],
                                          "p50": ch["d_seats_p50"], "p90": ch["d_seats_p90"]},
                                "hist": {int(k): v for k, v in ch["hist"].items()},
                                **({"p_control_alt": ch["p_control_alt"]} if "p_control_alt" in ch else {})}
                            for c, ch in fc["versions"][head]["chambers"].items()}}
    prev_races = (previous or {}).get("races", {})
    events = list((previous or {}).get("events", []))
    pre = fc["versions"][head]

    def party(rid: str, w: str) -> str:
        """The party code of a race's winning side ('other': not a nominee)."""
        return (fc["races"][rid]["d_side"] if w == "D" else
                (rows.get(rid, {}).get("r_side") or "R") if w == "R" else "other")

    races = {}
    for rid, m in fc["races"].items():
        r = res.get(rid, {})
        p_pre = pre["races"][rid]["p_d_side"]
        fixed = m.get("fixed")
        status = "uncontested" if fixed else r.get("status", "awaiting")
        row = {"status": status}
        if fixed:
            row["winner"] = "D" if fixed == m.get("d_side") else "R"
        elif status == "called":
            row["winner"] = r["winner"]
            if r["winner"] == "other" and r.get("winner_name"):
                row["winner_name"] = r["winner_name"]       # the nominees are in races.json
            was = prev_races.get(rid, {})
            row["called_at"] = (was.get("called_at") if was.get("status") == "called"
                                and was.get("winner") == r["winner"] else None) or generated
            if r["winner"] in ("D", "R"):
                p_w = p_pre if r["winner"] == "D" else 1 - p_pre
                row["upset"] = p_w < 0.5
            if r.get("called_by"):
                row["called_by"] = r["called_by"]
        if held.get(rid):
            row["held"] = held[rid]
        if row.get("winner") in ("D", "R"):
            row["party"] = party(rid, row["winner"])
        elif row.get("winner") == "other" and r.get("party"):
            row["party"] = r["party"]                               # a first-round winner's
        if row.get("party") and held.get(rid) and row["party"] != held[rid]:
            row["flip"] = True                                      # the seat changes hands
        if r.get("disputed"):
            row["disputed"] = True
        if r.get("votes") and sum(r["votes"].values()):
            row["pct_reporting"] = r.get("pct_reporting", 0.0)
            row["votes"] = r["votes"]
            if r.get("margin") is not None:
                row["margin"] = r["margin"]
            if r.get("top_two"):
                row["top_two"] = r["top_two"]
        row["p_pre"] = _r(p_pre)
        row["p_live"] = _r(out["races"][rid])
        races[rid] = row
    # the night's log: new calls, changed calls, retractions
    after = {c: _r(out["chambers"][c]["p_control"].get("D", 0)) for c in out["chambers"]}
    new_events = []
    for rid, row in races.items():
        was = prev_races.get(rid, {})
        if row["status"] == "called" and (was.get("status") != "called" or was.get("winner") != row["winner"]):
            p_pre = row["p_pre"]
            new_events.append({"t": generated, "race": rid,
                               "type": "call" if was.get("status") != "called" else "changed",
                               "winner": row["winner"],
                               "p_winner_pre": _r(p_pre if row["winner"] == "D" else 1 - p_pre)
                               if row["winner"] in ("D", "R") else None,
                               "upset": row.get("upset", False),
                               "party": row.get("party"), "flip": row.get("flip", False),
                               "after": after})
        elif was.get("status") == "called" and row["status"] != "called":
            new_events.append({"t": generated, "race": rid, "type": "retracted",
                               "winner": was.get("winner"), "after": after})
    new_events.sort(key=lambda e: (e["race"].split(":")[0] != "senate", e["race"]))
    events = (new_events + events)[:EVENTS_KEPT]
    chambers = {}
    for c, ch in sim["chambers"].items():
        ids = [rid for rid, m in fc["races"].items() if m["chamber"] == c]
        fixed, called, upsets = {}, {}, []
        gains, losses, flips = {}, {}, []
        n_called = won = 0
        for rid in ids:
            row = races[rid]
            if row.get("flip"):
                gains[row["party"]] = gains.get(row["party"], 0) + 1
                losses[row["held"]] = losses.get(row["held"], 0) + 1
                flips.append(rid)
            if row["status"] == "uncontested":
                p = party(rid, row["winner"])
                fixed[p] = fixed.get(p, 0) + 1
            elif row["status"] == "called":
                p = row.get("party") or party(rid, row["winner"])
                called[p] = called.get(p, 0) + 1
                if row["winner"] in ("D", "R"):
                    n_called += 1
                    won += not row.get("upset", False)
                    if row.get("upset"):
                        upsets.append(rid)
        upsets.sort(key=lambda rid: races[rid]["p_pre"] if races[rid]["winner"] == "D"
                    else 1 - races[rid]["p_pre"])
        flips.sort(key=lambda rid: races[rid].get("called_at") or "", reverse=True)   # newest first
        not_up = dict(ch.get("seats_not_up") or {})
        caucus = ch.get("caucus") or {}
        bloc = {"D": 0, "R": 0, "other": 0}
        for src in (not_up, fixed, called):
            for p, k in src.items():
                b = caucus.get(p, p)
                bloc[b if b in ("D", "R") else "other"] += k
        pc = pre["chambers"][c]
        lc = out["chambers"][c]
        chambers[c] = {
            "seats": len(ids) + sum(not_up.values()), "majority": ch["majority"],
            "not_up": not_up, "fixed": fixed, "called": called,
            "uncalled": sum(1 for rid in ids if races[rid]["status"] not in ("called", "uncontested")),
            "bloc": bloc,
            "pre": {"p_control": {k: _r(v) for k, v in pc["p_control"].items()},
                    "seats": {"mean": _r(pc["d_seats_mean"], 1), "p10": pc["d_seats_p10"],
                              "p50": pc["d_seats_p50"], "p90": pc["d_seats_p90"]}},
            "live": {"p_control": {k: _r(v) for k, v in lc["p_control"].items()},
                     **({"p_control_alt": {k: _r(v) for k, v in lc["p_control_alt"].items()}}
                        if "p_control_alt" in lc else {}),
                     "seats": {"mean": _r(lc["seats"]["mean"], 1), **{k: lc["seats"][k] for k in ("p10", "p50", "p90")}},
                     "hist": _hist(lc["hist"]),
                     "ess": out["ess"], "draws": out["draws"], "reliable": out["ess"] >= RELIABLE_ESS},
            "favorites": {"called": n_called, "won": won},
            "upsets": upsets,
            "gains": gains, "losses": losses, "flips": flips,
        }
    statuses = [r["status"] for r in races.values()]
    counts = {s: statuses.count(s) for s in ("awaiting", "counting", "called", "runoff", "uncontested")}
    status = ("awaiting" if counts["counting"] + counts["called"] + counts["runoff"] == 0 else
              "complete" if counts["counting"] + counts["awaiting"] == 0 else "counting")
    return {
        "generated": generated, "asof": generated[:10], "fixture": fixture, "status": status,
        "source": {"name": "civicAPI", "url": "https://civicapi.org", "fetched": fetched,
                   "credit": civic.ATTRIBUTION,
                   "note": "counts from secretaries of state; calls by civicAPI's decision desk"},
        "forecast": {"snapshot": snapshot, "generated": fc["generated"], "of_record": of_record,
                     "version": head},
        "method": METHOD,
        "held_note": HELD_NOTE,
        "polls_close": poll_closings(),
        "counts": counts,
        "chambers": chambers,
        "races": races,
        "events": events,
    }


# ------------------------------------------------------------------ fixture

def fixture_results(fc: dict, rows: dict, hour_et: float, seed: int = FIXTURE_SEED) -> dict[str, dict]:
    """A simulated night at `hour_et` (hours after midnight Eastern, Nov 3):
    one outcome drawn from the forecast itself, counted and called the way
    the self-check's stylized decision desk does. For building the site."""
    sim = _sim(fc, rows)
    eng = L.Engine(sim, version=fc["headline"])
    close = {st: v["last"] for st, v in
             yaml.safe_load((CURATED / "poll_closing.yaml").read_text())["states"].items()}
    rng = np.random.default_rng(seed)
    th = np.zeros(eng.D)
    th[0] = eng.c_nat * rng.standard_t(eng.nu_nat)
    th[1:] = rng.standard_normal(eng.D - 1) * eng.prior_sd[1:]
    eps = rng.standard_t(eng.nu_race, len(eng.ids)) * math.sqrt((eng.nu_race - 2) / eng.nu_race)
    margin = eng.mu + eng.A @ th + eps * eng.sd
    out = {}
    for i, rid in enumerate(eng.ids):
        m = fc["races"][rid]
        h = hour_et - close.get(m["state"], 21.0)
        if m.get("fixed") or h < 0:
            out[rid] = {"status": "awaiting", "votes": {"D": 0, "R": 0, "other": 0}, "pct_reporting": 0.0}
            continue
        pct = float(min(99.0, 25 + 22 * h + rng.uniform(-10, 10)))
        size = (260_000 if m["chamber"] == "house" else 3_200_000) * pct / 100
        shown = margin[i] + rng.normal(0, 6 / (1 + h))          # early counts wander
        d = size * 0.98 * (0.5 + max(-49.0, min(49.0, shown)) / 200)
        votes = {"D": int(d), "R": int(size * 0.98 - d), "other": int(size * 0.02)}
        row = {"votes": votes, "pct_reporting": round(pct, 1),
               "margin": round(100 * (votes["D"] - votes["R"]) / max(1, votes["D"] + votes["R"]), 1)}
        if L._called(margin[i], h):
            w = "D" if margin[i] > 0 else "R"
            row.update(status="called", winner=w, winner_name=m["d_cand"] if w == "D" else m["r_cand"])
        else:
            row["status"] = "counting"
        out[rid] = row
    return out


# --------------------------------------------------------------------- main

STOOD_IN = {"federal": "House and Senate results", "governors": "governors' results"}
HALVED_NOTE = "New York's vote counts halved: civicAPI's New York feed counts every vote twice"


def undouble(res: dict[str, dict], rows: dict[str, dict], counties_dir: Path | None) -> list[str]:
    """civicAPI's New York feed lists each race's counties and an 'All
    Counties' row of the same votes, so every New York total is exactly
    double (NY-12, NY-16, NY-17 and the governor checked, Nov 4). While the
    county job still finds that in New York's governor race
    (counties/governor/ny.json: double_counted), every New York race's votes
    are halved; shares and margins don't change. The races halved."""
    if counties_dir is None:
        return []
    try:
        flag = json.loads((counties_dir / "governor" / "ny.json").read_text()).get("double_counted")
    except (OSError, ValueError, AttributeError):
        return []
    if flag is not True:
        return []
    out = []
    for rid, r in res.items():
        if (rows.get(rid) or {}).get("state") == "NY" and isinstance(r.get("votes"), dict):
            r["votes"] = {k: round(v / 2) for k, v in r["votes"].items()}
            out.append(rid)
    return sorted(out)
CHAMBERS = ("house", "senate", "governor")
HISTORY_KEPT = 1500


def history(prev: dict | None, doc: dict) -> list[list]:
    """[t, house, senate, governor, called]: each chamber's chance of
    Democratic control given the calls (4 decimals, as p_control) and the number of races
    called, whenever either changed, oldest first, from the forecast of
    record on. Carried over from the previous live.json; a file without one
    starts from the forecast of record and the calls still in its events."""
    def r4(x) -> float:
        return round(float(x), 4)

    pts = [p for p in ((prev or {}).get("history") or []) if isinstance(p, list) and len(p) == 5]
    start = [DEADLINE, *(r4(doc["chambers"][c]["pre"]["p_control"].get("D", 0)) for c in CHAMBERS), 0]
    if pts and pts[0][0] == DEADLINE:
        pts[0] = start                                 # the forecast exactly as the page shows it
    if not pts:
        pts = [start]
        after = {}                                     # each call time's chances (one per batch)
        for e in doc.get("events") or []:
            a = e.get("after") or {}
            if e.get("type") == "call" and e.get("t") and all(c in a for c in CHAMBERS):
                after.setdefault(e["t"], a)
        times = sorted(r.get("called_at") or "" for r in doc["races"].values() if r.get("status") == "called")
        for t in sorted(after):
            n = sum(1 for x in times if x and x <= t)
            pt = [t, *(r4(after[t][c]) for c in CHAMBERS), n]
            if pt[1:] != pts[-1][1:]:
                pts.append(pt)
    now = [doc["generated"], *(r4(doc["chambers"][c]["live"]["p_control"].get("D", 0)) for c in CHAMBERS),
           doc["counts"]["called"]]
    if now[1:] != pts[-1][1:]:
        pts.append(now)
    return pts[-HISTORY_KEPT:]


def et_clock(iso: str) -> str:
    """'7:19 p.m. ET', as the site writes times, for a UTC time (Eastern
    Standard Time, UTC-5, from Nov 1, 2026)."""
    t = dt.datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ") - dt.timedelta(hours=5)
    return f"{t.hour % 12 or 12}:{t.minute:02d} {'a.m.' if t.hour < 12 else 'p.m.'} ET"


def _previous(out: Path | None, explicit: str | None) -> dict | None:
    cands = [Path(explicit)] if explicit else []
    if out is not None and out.name.endswith(".tmp"):
        cands.append(out.with_name(out.name[:-4]))
    cands.append(SITE / "live.json")
    for p in cands:
        try:
            if p.exists():
                doc = json.loads(p.read_text())
                if isinstance(doc, dict) and isinstance(doc.get("races"), dict) and not doc.get("fixture"):
                    return doc
        except (OSError, ValueError):
            continue
    return None


def main(out: str | None = None, previous: str | None = None, draws: int | None = None,
         fixture: float | None = None, seed: int = FIXTURE_SEED) -> None:
    draws = draws or DRAWS
    generated = now_utc()
    fc, snapshot, of_record = forecast_of_record(generated)
    # nominees as frozen in the forecast (the build re-reads Wikipedia on
    # Election Day, when editors are reshaping the pages); r_side from data/races
    rows = race_rows()
    rows = {rid: {**rows.get(rid, {}), **{k: m[k] for k in ("state", "d_cand", "r_cand", "d_side") if m.get(k)}}
            for rid, m in fc["races"].items()}
    stood_in, halved = {}, []
    if fixture is not None:
        res, fetched = fixture_results(fc, rows, fixture, seed=seed), None
        prev = json.loads(Path(previous).read_text()) if previous else None      # a fixture sequence
    else:
        wiki = wikipedia_calls(fc)
        prev = _previous(Path(out) if out else None, previous)
        try:
            # the web server (--out) keeps each search's last answer beside its live.json
            civic_races, fetched, stood_in = civic.fetch_all(cache=Path(out).parent if out else None)
            res = civic.results(civic_races, rows)
            if len(res) < MIN_MAPPED:
                raise SystemExit(f"civicapi: only {len(res)} of {len(rows)} races mapped — not writing")
            halved = undouble(res, rows, Path(out).parent / "counties" if out else None)
        except SystemExit as e:
            # the web server writes nothing (its last good file stays up). The
            # committed copy carries on with Wikipedia's settled races alone only
            # if civicAPI never answered tonight: a picture from Wikipedia alone,
            # newer than the server's last good one but with far fewer calls,
            # would take its place on the page and retract calls civicAPI made
            had_calls = any(r.get("status") == "called" and not r.get("called_by")
                            for r in ((prev or {}).get("races") or {}).values())
            if out is not None or not wiki or had_calls:
                raise
            print(f"  ! {e} — calls from Wikipedia's results boxes only")
            res, fetched, stood_in, halved = {}, None, {}, []
    doc = assemble(fc, snapshot, of_record, rows, res, fetched, prev, generated,
                   draws=draws, fixture=fixture is not None, wiki=wiki if fixture is None else None)
    doc["history"] = history(prev, doc)
    if fixture is None and fetched is None:
        doc["source"]["note"] = "civicAPI was unreachable: calls from Wikipedia's results boxes, no counts"
    elif stood_in:
        # a search that failed this run answered from its last answer (civic.KEEP)
        doc["source"]["fetched"] = min(stood_in.values())
        doc["source"]["note"] += "".join(f"; {STOOD_IN[name]} as of {et_clock(when)}"
                                         for name, when in sorted(stood_in.items()))
        print(f"  ! civicAPI: {', '.join(sorted(stood_in))} from the last answer ({min(stood_in.values())})")
    if halved:
        doc["source"]["note"] += f"; {HALVED_NOTE}"
        print(f"  ! civicAPI: {len(halved)} New York races halved (its feed counts every vote twice)")
    text = json.dumps(doc, separators=(",", ":"), ensure_ascii=False)
    path = Path(out) if out else SITE / "live.json"
    path.write_text(text)
    h, s, g = (doc["chambers"][c]["live"]["p_control"].get("D", 0) for c in ("house", "senate", "governor"))
    print(f"✓ live ({doc['status']}{', FIXTURE' if doc['fixture'] else ''}): {doc['counts']['called']} called, "
          f"{doc['counts']['counting']} counting; D control — House {h:.1%}, Senate {s:.1%}, "
          f"governors {g:.1%}; ess {doc['chambers']['house']['live']['ess']}; {len(text) / 1024:.0f} KB -> {path}")
