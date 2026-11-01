"""`midterms export` — data/site/*.json, the contract the website reads.

The schema is documented in docs/site-data.md and checked by `midterms
verify`. Every forecast run rebuilds these files (and the refresh workflow
commits them), so the site — which rebuilds from the committed files — is
never more than one refresh behind. Every file is an object carrying
`generated` (UTC ISO) and `asof`.

  summary.json    topline: control odds, seat histograms, tipping points,
                  the House x Senate joint table, national environment,
                  measured poll adjustments
  races.json      every race: candidates, incumbency, ratings, the inputs and
                  their weights, per-version probabilities and margin
                  distributions
  polls.json      per race: the poll ledger (weight, adjusted margin, source
                  URL) and the daily polling-average trend with an 80% band
  generic.json    the generic-ballot daily average (80% band) and its polls
  history.json    the topline across frozen snapshots (the ex-ante record)
  sim.json        parameters for the in-browser simulator (sim/simulator.mjs)
  backtest.json   out-of-sample accuracy: Brier, log loss, calibration bins
  meta.json       phase, provenance, counts, licensing, state reference data
  scorecard.json  after Election Day: the frozen forecast graded (if any)
"""

from __future__ import annotations

import csv
import datetime
import json
from collections import defaultdict

import yaml

from midterms.model.simulate import QUANTILES, REGIONS
from midterms.paths import CURATED, DATA, FORECAST, RACES, SITE
from midterms.pipeline.states import STATES

VERSIONS = ("lite", "classic", "deluxe")
DEADLINE = "2026-11-03T10:00:00Z"

# A standard state tile grid (column, row) for tile maps / cartograms.
TILE = {
    "AK": (0, 0), "ME": (11, 0), "VT": (10, 1), "NH": (11, 1),
    "WA": (1, 2), "ID": (2, 2), "MT": (3, 2), "ND": (4, 2), "MN": (5, 2), "IL": (6, 2),
    "WI": (7, 2), "MI": (8, 2), "NY": (9, 2), "RI": (10, 2), "MA": (11, 2),
    "OR": (1, 3), "NV": (2, 3), "WY": (3, 3), "SD": (4, 3), "IA": (5, 3), "IN": (6, 3),
    "OH": (7, 3), "PA": (8, 3), "NJ": (9, 3), "CT": (10, 3),
    "CA": (1, 4), "UT": (2, 4), "CO": (3, 4), "NE": (4, 4), "MO": (5, 4), "KY": (6, 4),
    "WV": (7, 4), "VA": (8, 4), "MD": (9, 4), "DE": (10, 4),
    "AZ": (2, 5), "NM": (3, 5), "KS": (4, 5), "AR": (5, 5), "TN": (6, 5), "NC": (7, 5),
    "SC": (8, 5),
    "OK": (4, 6), "LA": (5, 6), "MS": (6, 6), "AL": (7, 6), "GA": (8, 6),
    "HI": (0, 7), "TX": (4, 7), "FL": (9, 7),
}
RULES = {
    "senate:ME": "Ranked-choice voting", "governor:ME": "Ranked-choice voting",
    "senate:AK": "Top-four primary, ranked-choice general",
    "governor:AK": "Top-four primary, ranked-choice general",
    "house:AK-AL": "Top-four primary, ranked-choice general",
    "senate:GA": "Majority required; runoff Dec 1 if no one clears 50%",
    "governor:GA": "Majority required; runoff Dec 1 if no one clears 50%",
}
# Only URLs we are sure of; anything else falls back to the Wikipedia revision.
SOURCE_URLS = {
    "Cook": "https://www.cookpolitical.com/ratings",
    "Sabato": "https://centerforpolitics.org/crystalball/",
    "Inside Elections": "https://insideelections.com/ratings",
    "Split Ticket": "https://split-ticket.org/",
    "DDHQ": "https://decisiondeskhq.com/",
    "Decision Desk HQ": "https://decisiondeskhq.com/",
    "RCP": "https://www.realclearpolling.com/",
    "RealClearPolitics": "https://www.realclearpolling.com/",
    "RealClearPolling": "https://www.realclearpolling.com/",
    "Silver Bulletin": "https://www.natesilver.net/",
    "270toWin": "https://www.270towin.com/",
    "The Economist": "https://www.economist.com/",
    "NBC News": "https://www.nbcnews.com/",
    "Fox News": "https://www.foxnews.com/",
    "CBS News": "https://www.cbsnews.com/",
    "CNN": "https://www.cnn.com/",
    "ABC News": "https://abcnews.go.com/",
    "Politico": "https://www.politico.com/",
}


def _csv(path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def _f(x):
    try:
        return None if x in (None, "") else float(x)
    except ValueError:
        return None


def _r(x, k=3):
    return None if x is None else round(x, k)


def slug(rid: str) -> str:
    ch, _, rest = rid.partition(":")
    return f"{ch}/{rest.lower()}"


def phase(now: str, scorecard: dict | None) -> str:
    if now < DEADLINE:
        return "forecast"
    if scorecard and scorecard.get("resolved", 0) > 0:
        return "results"
    return "frozen"


class Writer:
    def __init__(self, generated: str, asof: str) -> None:
        self.generated, self.asof = generated, asof

    def __call__(self, name: str, body: dict) -> None:
        SITE.mkdir(parents=True, exist_ok=True)
        doc = {"generated": self.generated, "asof": self.asof, **body}
        (SITE / name).write_text(json.dumps(doc, separators=(",", ":"), ensure_ascii=False))


def _hist(h: dict) -> dict:
    xs = sorted(int(k) for k in h)
    lo, hi = xs[0], xs[-1]
    return {"min": lo, "p": [_r(h.get(str(x), h.get(x, 0.0)), 6) or 0.0 for x in range(lo, hi + 1)]}


def _chamber(fc: dict, name: str, cur: dict) -> dict:
    out = {"versions": {}}
    for v in VERSIONS:
        c = fc["versions"][v]["chambers"][name]
        out["versions"][v] = {
            "p_control": {k: _r(x, 4) for k, x in c["p_control"].items()},
            "p_control_alt": ({k: _r(x, 4) for k, x in c["p_control_alt"].items()}
                              if c.get("p_control_alt") else None),
            "seats": {"mean": _r(c["d_seats_mean"], 2), "p10": c["d_seats_p10"],
                      "p50": c["d_seats_p50"], "p90": c["d_seats_p90"]},
            "hist": _hist(c["hist"]),
        }
    head = fc["versions"][fc["headline"]]["races"]
    tips = sorted(((r["tipping"].get(name, 0), rid) for rid, r in head.items()
                   if name in r["tipping"]), reverse=True)[:15]
    out["tipping"] = [{"id": rid, "slug": slug(rid), "label": fc["races"][rid]["label"], "p": _r(t, 4)}
                      for t, rid in tips if t > 0]
    ids = [rid for rid, m in fc["races"].items() if m["chamber"] == name]
    out["n_races"] = len(ids)
    out["competitive"] = sum(1 for rid in ids if 0.1 < head[rid]["p_d_side"] < 0.9)
    out["fixed"] = sum(1 for rid in ids if fc["races"][rid].get("fixed"))
    if name == "house":
        out.update({"seats": cur["house"]["seats"], "majority": cur["house"]["majority"],
                    "seats_not_up": {}})
    elif name == "senate":
        s = cur["senate"]
        out.update({"seats": 100, "majority": s["majority"], "tie_breaker": s["tie_breaker"],
                    "seats_not_up": s["seats_not_up"], "caucus": s["caucus"],
                    "note": "Democrats need 51 (Sanders and King caucus with them); Republicans "
                            "need 50 with Vice President Vance's tiebreak. An independent who "
                            "hasn't picked a caucus counts as neither ('unclear'); "
                            "p_control_alt counts them with Democrats."})
    else:
        g = cur["governor"]
        out.update({"seats": 50, "majority": g["majority"], "seats_not_up": g["seats_not_up"],
                    "not_up": g["not_up"]})
    return out


def _joint(j: dict) -> dict:
    grid = {"house_D": {"senate_D": j.get("DD", 0.0), "senate_R": j.get("DR", 0.0)},
            "house_R": {"senate_D": j.get("RD", 0.0), "senate_R": j.get("RR", 0.0)}}
    other = sum(v for k, v in j.items() if "?" in k)
    return {"grid": {h: {s: _r(p, 4) for s, p in row.items()} for h, row in grid.items()},
            "unclear": _r(other, 4)}


def summary(fc: dict, meta: dict, cur: dict, averages: list[dict], ph: str) -> dict:
    head = fc["versions"][fc["headline"]]
    nat = fc["national"]
    adj = fc["adjustments"]
    gen_avgs = [{"source": a["source"], "d": _f(a["d"]), "r": _f(a["r"]),
                 "margin_raw": _r(_f(a["d"]) - _f(a["r"]), 2), "updated": a["updated"] or None,
                 "url": SOURCE_URLS.get(a["source"])}
                for a in averages if a["race"] == "generic"]
    return {
        "phase": ph, "election_day": "2026-11-03", "deadline": DEADLINE,
        "n_sims": fc["n_sims"], "seed": fc["seed"], "headline": fc["headline"],
        "versions": list(VERSIONS), "model": fc["model"],
        "national": {
            "generic": {"margin": _r(nat["generic_ballot"]["margin"], 2),
                        "n_polls": nat["generic_ballot"]["n_polls"],
                        "pollsters": nat["generic_ballot"]["pollsters"],
                        "latest": nat["generic_ballot"]["latest"],
                        "basis": "two-party margin, D minus R, points"},
            "environment_sd": fc["params"]["national"]["sd"],
            "popular_vote": {k: _r(v, 2) for k, v in head["popular_vote"].items()},
            "outside_averages": gen_avgs,
        },
        "chambers": {c: _chamber(fc, c, cur) for c in ("house", "senate", "governor")},
        "joint": _joint(head["joint"]),
        "adjustments": {
            "population_shift": adj["population_shift"], "population_pairs": adj["population_pairs"],
            "sponsor_lean": adj["sponsor_lean"], "sponsor_polls": adj["sponsor_polls"],
            "house_effects": [{"pollster": k, "points": v["points"], "polls": v["polls"]}
                              for k, v in list(adj["house_effects"].items())[:40] if v["polls"] >= 3],
        },
        "counts": meta.get("counts", {}),
    }


def races(fc: dict, ratings: list[dict], averages: list[dict], finance: list[dict],
          race_rows: dict) -> list[dict]:
    rat = defaultdict(dict)
    for r in ratings:
        cur = rat[r["race"]].get(r["rater"])
        if cur is None or r["asof"] > cur["asof"]:
            rat[r["race"]][r["rater"]] = {"rating": r["rating"], "asof": r["asof"] or None,
                                          "scale": _f(r["scale"]), "url": SOURCE_URLS.get(r["rater"])}
    avg = defaultdict(list)
    for a in averages:
        if a["race"] != "generic":
            d, r = _f(a["d"]), _f(a["r"])
            avg[a["race"]].append({"source": a["source"], "d": d, "r": r,
                                   "margin_raw": _r(d - r, 2), "end": a["end"] or None,
                                   "updated": a["updated"] or None,
                                   "url": SOURCE_URLS.get(a["source"])})
    fin = defaultdict(dict)
    for f in finance:
        fin[f["race"]][f["side"]] = {"name": f["candidate"], "receipts": _f(f["receipts"]),
                                     "fec_id": f["fec_id"] or None,
                                     "url": (f"https://www.fec.gov/data/candidate/{f['fec_id']}/"
                                             if f["fec_id"] else None)}
    out = []
    for rid, m in fc["races"].items():
        row = race_rows.get(rid, {})
        det = fc["detail"].get(rid) or {}
        st, label = m["state"], m["label"]
        district = None
        if m["chamber"] == "house":
            n = label.split("-")[1]
            district = 0 if n == "AL" else int(n)
        page = (row.get("source") or "").removeprefix("wikipedia:")
        title, _, rev = page.rpartition("@")
        d_party = m["d_side"] or "D"
        r_party = row.get("r_side") or "R"
        forecast = {}
        for v in VERSIONS:
            r = fc["versions"][v]["races"][rid]
            dv = (det.get("versions") or {}).get(v) or {}
            p = r["p_d_side"]
            p_party = {d_party: _r(p, 4)}
            p_party[r_party] = _r((p_party.get(r_party) or 0) + (1 - p), 4)
            forecast[v] = {
                "p_d_side": _r(p, 4), "p_party": p_party,
                "estimate": {"mu": dv.get("mu"), "sd": dv.get("sd"), "weights": dv.get("weights")},
                "margin": None if m.get("fixed") else {
                    "mean": _r(r.get("margin_mean"), 2), "sd": _r(r.get("margin_sd"), 2),
                    **(r.get("margin_q") or {})},
                "tipping": _r(r["tipping"].get(m["chamber"], 0.0), 4),
            }
        F, Pc, E = det.get("fundamentals"), det.get("polls"), det.get("ratings")
        inc_party = m.get("inc_party") or None
        p_head = forecast[fc["headline"]]["p_d_side"]
        fav = d_party if p_head >= 0.5 else r_party
        out.append({
            "id": rid, "slug": slug(rid), "chamber": m["chamber"], "state": st,
            "state_name": STATES[st], "label": label, "district": district,
            "special": rid.endswith("-special"),
            "d": {"name": m["d_cand"] or None, "party": d_party},
            "r": {"name": m["r_cand"] or None, "party": r_party},
            "others": [o.strip() for o in (row.get("others") or "").split(";") if o.strip()],
            "incumbent": {"name": m.get("incumbent") or None, "party": inc_party,
                          "running": m.get("inc_running") == "yes",
                          "first_elected": row.get("first_elected") or None},
            "fixed": m.get("fixed") or None,
            "lean": _f(m.get("lean")),
            "rules": RULES.get(rid) or (
                "Majority-vote first round Nov 3; runoff Dec 12" if rid.startswith("house:LA-") else None),
            "ratings": rat.get(rid, {}),
            "inputs": {
                "fundamentals": None if not F else {"mu": _r(F["mu"], 2), "sd": F["sd"], "parts": F["parts"]},
                "polls": None if not Pc else {k: (_r(v, 2) if isinstance(v, float) else v)
                                              for k, v in Pc.items()},
                "ratings": None if not E else {"mu": _r(E["mu"], 2), "sd": _r(E["sd"], 2),
                                               "scale": E["scale"], "raters": E["raters"]},
            },
            "forecast": forecast,
            "favorite": None if m.get("fixed") else fav,
            "flip": (None if not inc_party or m.get("fixed") else
                     (fav != inc_party and p_head not in (0.0, 1.0))),
            "outside_averages": avg.get(rid, []),
            "finance": fin.get(rid) or None,
            "source": {"title": title or None, "revid": int(rev) if rev.isdigit() else None,
                       "url": f"https://en.wikipedia.org/w/index.php?oldid={rev}" if rev.isdigit() else None},
        })
    order = {"senate": 0, "governor": 1, "house": 2}
    out.sort(key=lambda r: (order[r["chamber"]], r["state"], r["district"] or 0, r["id"]))
    return out


def polls(led: dict, trends: dict, race_rows: dict) -> dict:
    out = {}
    for rid, rows in led.items():
        if rid == "generic":
            continue
        page = (race_rows.get(rid, {}).get("source") or "").removeprefix("wikipedia:")
        rev = page.rpartition("@")[2]
        wiki = f"https://en.wikipedia.org/w/index.php?oldid={rev}" if rev.isdigit() else None
        out[rid] = {
            "polls": [{**p, "sponsor": p.get("partisan") or None, "wikipedia": wiki} for p in rows],
            "trend": trends.get(rid, []),
        }
    return out


def history() -> list[dict]:
    rows = []
    for p in sorted((FORECAST / "snapshots").glob("*.json")):
        s = json.loads(p.read_text())
        v = s["versions"][s["headline"]]
        row = {"generated": s["generated"], "asof": s["asof"], "snapshot": p.name,
               "ex_ante": s["generated"] < DEADLINE,
               "generic": _r(s["national"]["generic_ballot"]["margin"], 2)}
        for c in ("house", "senate", "governor"):
            ch = v["chambers"][c]
            row[c] = {"p": _r(ch["p_control"].get("D", 0), 4), "p50": ch["d_seats_p50"],
                      "p10": ch["d_seats_p10"], "p90": ch["d_seats_p90"]}
        rows.append(row)
    return rows


def sim_params(fc: dict, cur: dict, race_rows: dict) -> dict:
    p = fc["params"]
    out = []
    for rid, m in fc["races"].items():
        det = fc["detail"].get(rid) or {}
        lam = p["national"]["loading"][m["chamber"]]
        row = {"id": rid, "chamber": m["chamber"], "state": m["state"], "lam": lam,
               "d_side": m["d_side"] or "D", "r_side": race_rows.get(rid, {}).get("r_side") or "R",
               "fixed": m.get("fixed") or None}
        if not row["fixed"]:
            row["mu"] = {v: det["versions"][v]["mu"] for v in VERSIONS}
            row["sd"] = {v: det["versions"][v]["sd"] for v in VERSIONS}
        out.append(row)
    s, g = cur["senate"], cur["governor"]
    return {
        "n_sims_reference": fc["n_sims"], "seed": fc["seed"],
        "national_mu": fc["national"]["environment"]["mu"],
        "shared": {"sd_national": p["national"]["sd"], "nu_national": p["national"]["nu"],
                   "sd_region": p["shared"]["sd_region"], "sd_state": p["shared"]["sd_state"],
                   "nu_race": p["shared"]["nu_race"],
                   "sd_chamber": {"house": p["house"]["translation_sd"]}, "floor_idio": 0.5},
        "regions": {k: v.split() for k, v in REGIONS.items()},
        "chambers": {
            "house": {"majority": cur["house"]["majority"], "seats_not_up": {}, "tie_breaker": None,
                      "caucus": {}, "alt_caucus": None},
            "senate": {"majority": s["majority"], "seats_not_up": s["seats_not_up"],
                       "tie_breaker": s["tie_breaker"], "caucus": s["caucus"],
                       "alt_caucus": {**s["caucus"], "IND": "D"}},
            "governor": {"majority": g["majority"], "seats_not_up": g["seats_not_up"],
                         "tie_breaker": None, "caucus": {}, "alt_caucus": None},
        },
        "reference": {v: {c: fc["versions"][v]["chambers"][c]["p_control"]
                          for c in ("house", "senate", "governor")} for v in VERSIONS},
        "races": out,
    }


def backtest() -> dict:
    out = {}
    bt = DATA / "backtest.yaml"
    if bt.exists():
        b = yaml.safe_load(bt.read_text())
        out["house_fundamentals"] = {
            "what": "House fundamentals (lean, incumbency, fundraising) fit on one midterm, "
                    "scored on the other given its national environment",
            "fit": b["fit"], "per_year": b["per_year"], "sample": b["sample"],
            "out_of_sample": [{"train": o["train"], "test": o["test"], "n": o["n"],
                               "brier": o["brier"], "log_loss": o.get("log_loss"),
                               "rmse": o["rmse"], "mean_error": o["mean_error"],
                               "calibration": o["reliability"]} for o in b["out_of_sample"]],
        }
    sw = DATA / "backtest_statewide.yaml"
    if sw.exists():
        s = yaml.safe_load(sw.read_text())
        out["statewide_polls"] = {
            "what": s["what"], "n_races": s["n_races"], "by_year": s["by_year"],
            "error": s["error"], "fit": s["fit"], "national_error": s["national_error"],
            "scores": s["scores"], "generic_ballot": s.get("generic_ballot"),
            "races": [{k: x[k] for k in ("id", "year", "chamber", "state", "d", "d_party", "r",
                                         "actual", "poll_avg", "error", "n_polls")}
                      for x in s["races"]],
        }
    return out


def main() -> None:
    fc = json.loads((FORECAST / "latest.json").read_text())
    ledger = json.loads((FORECAST / "ledger.json").read_text())
    meta = yaml.safe_load((DATA / "meta.yaml").read_text()) or {}
    cur = yaml.safe_load((CURATED / "chambers.yaml").read_text())
    averages = _csv(DATA / "averages.csv")
    race_rows = {r["id"]: r for ch in ("house", "senate", "governor") for r in _csv(RACES / f"{ch}.csv")}
    revs = (meta.get("sources") or {}).get("wikipedia_revisions", {})
    sc_path = DATA / "scorecard.yaml"
    scorecard = yaml.safe_load(sc_path.read_text()) if sc_path.exists() else None
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    ph = phase(now, scorecard)
    w = Writer(fc["generated"], fc["asof"])

    w("summary.json", summary(fc, meta, cur, averages, ph))
    w("races.json", {"races": races(fc, _csv(DATA / "ratings.csv"), averages,
                                    _csv(DATA / "finance.csv"), race_rows)})
    w("polls.json", {"basis": "two-party margin, D-side minus R-side, points; weight = share "
                              "of the race's polling average",
                     "races": polls(ledger["ledgers"], ledger.get("trends", {}), race_rows)})
    w("generic.json", {"basis": "two-party margin, D minus R, points",
                       "average": ledger.get("trends", {}).get("generic", []),
                       "polls": [{**p, "sponsor": p.get("partisan") or None}
                                 for p in ledger["ledgers"].get("generic", [])],
                       "outside_averages": summary(fc, meta, cur, averages, ph)["national"]["outside_averages"]})
    w("history.json", {"snapshots": history()})
    w("sim.json", sim_params(fc, cur, race_rows))
    w("backtest.json", backtest())
    if scorecard:
        w("scorecard.json", scorecard)
    w("meta.json", {
        "phase": ph, "exported": now, "deadline": DEADLINE, "election_day": "2026-11-03",
        "counts": meta.get("counts", {}), "sources_digest": meta.get("sources_digest"),
        "quantiles": [f"q{k:02d}" for k in QUANTILES],
        "wikipedia": [{"title": t, "revid": r, "url": f"https://en.wikipedia.org/w/index.php?oldid={r}"}
                      for t, r in sorted(revs.items())],
        "states": {st: {"name": name, "tile": TILE.get(st),
                        "region": next(k for k, v in REGIONS.items() if st in v.split())}
                   for st, name in STATES.items()},
        "license": {"code": "MIT", "data": "CC BY-SA 4.0"},
        "repo": "https://github.com/KaraZajac/MIDTERMS2026",
        "site": "https://midterms.karazajac.io",
        "attribution": [
            "Race pages, polls and ratings: Wikipedia contributors (CC BY-SA 4.0)",
            "Presidential results by district: The Downballot (the-downballot.com/p/data)",
            "2020 results on redrawn lines: Dave's Redistricting App block data (VEST, CC BY 4.0); "
            "This data was generated using data from the Redistricting Data Hub.",
            "Campaign finance: Federal Election Commission",
            "Pollster ratings: Silver Bulletin; FiveThirtyEight (CC BY 4.0)",
        ],
    })
    sizes = {p.name: p.stat().st_size for p in sorted(SITE.glob("*.json"))}
    print(f"✓ export ({ph}): " + ", ".join(f"{k} {v / 1024:.0f}K" for k, v in sizes.items()))
