"""The forecast: inputs -> per-race estimates -> correlated simulation.

Three versions, as FiveThirtyEight published them:

  lite     polls; where a race has none, its partisan lean plus the
           national environment (the generic ballot) — nothing else
  classic  lite + fundamentals: incumbency, fundraising, lean
  deluxe   classic + expert ratings (Cook, Sabato, Inside Elections)

Within a version, each available component is an independent noisy
measurement of the race's two-party margin and they are precision-weighted.
The simulator then adds the error the races share (national, regional,
state). `deluxe` is the headline, as it was at 538; all three are written so
the scorecard can show what each layer of information bought.
"""

from __future__ import annotations

import csv
import datetime
import json
import math
from collections import defaultdict
from pathlib import Path

import yaml

from midterms.model import polls as P
from midterms.model import ratings as R
from midterms.model.simulate import Chamber, Race, Shared, simulate
from midterms.paths import CURATED, DATA, FORECAST, POLLS, RACES, ROOT

PARAMS = Path(__file__).with_name("params.yaml")
VERSIONS = ("lite", "classic", "deluxe")


def _v(params: dict, *keys):
    node = params
    for k in keys:
        node = node[k]
    return node["value"] if isinstance(node, dict) and "value" in node else node


def _csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def _f(x) -> float | None:
    try:
        return None if x in (None, "") else float(x)
    except ValueError:
        return None


# ------------------------------------------------------------------ inputs

def load_inputs() -> dict:
    races = []
    for chamber in ("house", "senate", "governor"):
        for r in _csv(RACES / f"{chamber}.csv"):
            r["chamber"] = chamber
            races.append(r)
    polls = defaultdict(list)
    for r in _csv(POLLS / "races.csv"):
        d, rr = _f(r["d"]), _f(r["r"])
        if d is None or rr is None or d + rr <= 0:
            continue
        polls[r["race"]].append(P.Poll(
            race=r["race"], pollster=r["pollster"], start=r["start"] or None, end=r["end"],
            n=int(r["n"]) if r.get("n") else None, population=r.get("population") or None,
            partisan=r.get("partisan") or None, d=d, r=rr, margin=P.two_party(d, rr),
            source=r.get("source", "")))
    generic = []
    for r in _csv(POLLS / "generic.csv"):
        d, rr = _f(r["d"]), _f(r["r"])
        if d is None or rr is None:
            continue
        generic.append(P.Poll(
            race="generic", pollster=r["pollster"], start=r["start"] or None, end=r["end"],
            n=int(r["n"]) if r.get("n") else None, population=r.get("population") or None,
            partisan=r.get("partisan") or None, d=d, r=rr, margin=P.two_party(d, rr)))
    ratings = defaultdict(list)
    for r in _csv(DATA / "ratings.csv"):
        s = _f(r.get("scale"))
        if s is not None:
            ratings[r["race"]].append({"rater": r["rater"], "scale": s,
                                       "label": r.get("rating", ""), "asof": r.get("asof", "")})
    finance = defaultdict(dict)
    for r in _csv(DATA / "finance.csv"):
        finance[r["race"]][r["side"]] = _f(r.get("receipts")) or 0.0
    quality = {}
    for r in _csv(DATA / "pollster_quality.csv"):
        quality[P.canonical_pollster(r["pollster"])] = float(r["weight"])
    return {"races": races, "polls": polls, "generic": generic, "ratings": ratings,
            "finance": finance, "quality": quality,
            "chambers": yaml.safe_load((CURATED / "chambers.yaml").read_text()),
            "meta": yaml.safe_load((DATA / "meta.yaml").read_text()) if (DATA / "meta.yaml").exists() else {}}


# --------------------------------------------------------------- national

def national(inp: dict, asof: str, params: dict, adj: P.Adjustments) -> dict:
    hl = _v(params, "national", "generic_half_life_days")
    gb = P.average(inp["generic"], asof, adj, half_life=hl, quality=inp["quality"],
                   max_age=120, sd_nonsampling=0.0, sd_floor=0.0)
    start = (datetime.date.fromisoformat(asof) - datetime.timedelta(days=150)).isoformat()
    series = P.daily_series(inp["generic"], adj, start, asof, half_life=hl,
                            quality=inp["quality"], max_age=120, sd_nonsampling=0.0, sd_floor=0.0)
    return {
        "generic_ballot": {"margin": gb.margin, "n_polls": gb.n_polls, "n_eff": gb.n_eff,
                           "latest": gb.latest, "pollsters": gb.pollsters,
                           "sampling_sd": gb.sd},
        "environment": {"mu": gb.margin, "sd": _v(params, "national", "sd")},
        "series": {d: round(v[0], 3) for d, v in series.items()},
    }


def make_trend(series: dict):
    days = sorted(series)

    def trend(date: str) -> float | None:
        if not days:
            return None
        if date <= days[0]:
            return series[days[0]]
        # last day on or before `date`
        lo, hi = 0, len(days) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if days[mid] <= date:
                lo = mid
            else:
                hi = mid - 1
        return series[days[lo]]
    return trend


# ------------------------------------------------------------- components

def fundamentals(race: dict, nat_mu: float, params: dict, finance: dict) -> dict | None:
    lean = _f(race.get("lean"))
    if lean is None:
        return None
    ch = race["chamber"]
    b = _v(params, ch, "lean_coef")
    lam = _v(params, ch, "national_coef") if ch == "governor" else 1.0
    parts = {"lean": round(b * lean, 2), "national": round(lam * nat_mu, 2)}
    inc_party = race.get("inc_party", "")
    running = race.get("inc_running", "") == "yes"
    inc = 0.0
    if running and inc_party:
        size = _v(params, ch, "incumbency")
        if ch == "house" and race.get("first_elected") == "2024":
            size += _v(params, "house", "freshman_bonus")
        if inc_party == race.get("d_side", "D"):
            inc = size
        elif inc_party == "R":
            inc = -size
    parts["incumbency"] = inc
    money = 0.0
    if ch == "house":
        f = finance.get(race["id"], {})
        if f.get("D") is not None and f.get("R") is not None:
            ratio = (f.get("D", 0) + 5000) / (f.get("R", 0) + 5000)
            cap = _v(params, "house", "money_cap")
            money = max(-cap, min(cap, _v(params, "house", "money_coef") * math.log2(ratio)))
    parts["fundraising"] = round(money, 2)
    mu = sum(parts.values())
    if ch == "house":
        sd = _v(params, "house", "sd_fundamentals" if running else "sd_fundamentals_open")
    else:
        sd = _v(params, ch, "sd_fundamentals")
    return {"mu": mu, "sd": sd, "parts": parts}


def lite_prior(race: dict, nat_mu: float, params: dict) -> dict | None:
    """Lite's stand-in for an unpolled race: lean + national environment."""
    lean = _f(race.get("lean"))
    if lean is None:
        return None
    ch = race["chamber"]
    lam = _v(params, ch, "national_coef") if ch == "governor" else 1.0
    sd = (_v(params, "house", "sd_fundamentals_open") if ch == "house"
          else _v(params, ch, "sd_fundamentals")) + 0.5
    return {"mu": _v(params, ch, "lean_coef") * lean + lam * nat_mu, "sd": sd}


def poll_component(race: dict, polls: list, asof: str, adj, params: dict,
                   quality: dict, trend) -> dict | None:
    if not polls:
        return None
    lam = _v(params, "governor", "national_coef") if race["chamber"] == "governor" else 1.0
    key = "sd_nonsampling_house" if race["chamber"] == "house" else "sd_nonsampling"
    a = P.average(polls, asof, adj, half_life=_v(params, "polls", "half_life_days"),
                  max_age=_v(params, "polls", "max_age_days"), quality=quality,
                  trend=trend, lam=lam * _v(params, "polls", "trend_lambda"),
                  sd_nonsampling=_v(params, "polls", key),
                  sd_partisan=_v(params, "polls", "sd_partisan"))
    if a.margin is None:
        return None
    return {"mu": a.margin, "sd": a.sd, "n_polls": a.n_polls, "n_eff": round(a.n_eff, 2),
            "latest": a.latest, "pollsters": a.pollsters,
            "partisan_share": round(a.partisan_share, 3)}


def rating_component(race_ratings: list, params: dict, has_polls: bool) -> dict | None:
    core = set(params["ratings"]["raters"])
    latest: dict[str, dict] = {}
    for r in race_ratings:
        if r["rater"] in core:
            cur = latest.get(r["rater"])
            if cur is None or r["asof"] > cur["asof"]:
                latest[r["rater"]] = r
    if not latest:
        return None
    s = sum(r["scale"] for r in latest.values()) / len(latest)
    sd = _v(params, "ratings", "sd") * (1.3 if has_polls else 1.0)  # raters read polls too
    return {"mu": R.implied_margin(s), "sd": sd, "scale": round(s, 3),
            "raters": {k: v["label"] for k, v in latest.items()}}


def combine(comps: list[dict]) -> dict:
    comps = [c for c in comps if c]
    prec = [1.0 / c["sd"] ** 2 for c in comps]
    tot = sum(prec)
    mu = sum(p * c["mu"] for p, c in zip(prec, comps)) / tot
    return {"mu": mu, "sd": tot ** -0.5, "weights": [round(p / tot, 3) for p in prec]}


# ------------------------------------------------------------------- run

def chambers_from(cur: dict) -> dict:
    s, g, h = cur["senate"], cur["governor"], cur["house"]
    return {
        "house": Chamber("house", majority=h["majority"]),
        # 'IND' = an independent who has not said whom they would caucus with
        # (Nebraska's Osborn). Headline control counts them as neither; the
        # alt tally reports control if they sided with Democrats.
        "senate": Chamber("senate", seats_not_up=dict(s["seats_not_up"]),
                          majority=s["majority"], tie_breaker=s["tie_breaker"],
                          caucus=dict(s["caucus"]),
                          alt_caucus={**s["caucus"], "IND": "D"}),
        "governor": Chamber("governor", seats_not_up=dict(g["seats_not_up"]),
                            majority=g["majority"]),
    }


def run(inp: dict, asof: str, params: dict, *, sims: int, seed: int) -> dict:
    all_polls = [p for ps in inp["polls"].values() for p in ps] + inp["generic"]
    adj = P.fit_adjustments(all_polls)
    nat = national(inp, asof, params, adj)
    nat_mu = nat["environment"]["mu"]
    trend = make_trend(nat["series"])
    shared = Shared(sd_national=_v(params, "national", "sd"),
                    nu_national=_v(params, "national", "nu"),
                    sd_region=_v(params, "shared", "sd_region"),
                    sd_state=_v(params, "shared", "sd_state"),
                    nu_race=_v(params, "shared", "nu_race"),
                    sd_chamber={"house": _v(params, "house", "translation_sd")})
    chambers = chambers_from(inp["chambers"])

    detail = {}
    sim_races = {v: [] for v in VERSIONS}
    for race in inp["races"]:
        rid = race["id"]
        fixed = race.get("fixed") or None
        d_side = race.get("d_side") or "D"
        lam = _v(params, "governor", "national_coef") if race["chamber"] == "governor" else 1.0
        if fixed:
            for v in VERSIONS:
                sim_races[v].append(Race(rid, race["chamber"], race["state"], fixed=fixed,
                                         d_side=d_side, lam=lam))
            detail[rid] = {"fixed": fixed}
            continue
        F = fundamentals(race, nat_mu, params, inp["finance"])
        Pc = poll_component(race, inp["polls"].get(rid, []), asof, adj, params,
                            inp["quality"], trend)
        E = rating_component(inp["ratings"].get(rid, []), params, Pc is not None)
        L = lite_prior(race, nat_mu, params)
        versions = {
            "lite": combine([Pc] if Pc else [L]),
            "classic": combine([F, Pc]) if F else combine([Pc] if Pc else [L]),
            "deluxe": combine([F, Pc, E]) if (F or Pc or E) else combine([L]),
        }
        detail[rid] = {"fundamentals": F, "polls": Pc, "ratings": E,
                       "versions": {k: {"mu": round(v["mu"], 3), "sd": round(v["sd"], 3),
                                        "weights": v["weights"]} for k, v in versions.items()}}
        for v in VERSIONS:
            sim_races[v].append(Race(rid, race["chamber"], race["state"],
                                     mu=versions[v]["mu"], sd=versions[v]["sd"],
                                     lam=lam, d_side=d_side))
    out_versions = {}
    for v in VERSIONS:
        out_versions[v] = simulate(sim_races[v], shared, chambers, n_sims=sims, seed=seed)
        nat_q = out_versions[v].pop("national_error")
        out_versions[v]["popular_vote"] = {
            "mu": nat_mu, "p10": nat_mu + nat_q["p10"], "p90": nat_mu + nat_q["p90"]}
    return {"national": nat, "adjustments": adj.as_dict(), "detail": detail,
            "versions": out_versions}


def load_params() -> dict:
    """params.yaml, with the House fundamentals replaced by the backtest's
    fitted values when data/backtest.yaml exists (`basis: fit`)."""
    params = yaml.safe_load(PARAMS.read_text())
    bt_path = DATA / "backtest.yaml"
    if bt_path.exists():
        fit = yaml.safe_load(bt_path.read_text())["fit"]
        h = params["house"]
        for key, val in (("lean_coef", fit["lean_coef"]), ("incumbency", fit["incumbency"]),
                         ("money_coef", fit["money_coef"]),
                         ("sd_fundamentals", fit["sd_incumbent"]),
                         ("sd_fundamentals_open", fit["sd_open"])):
            h[key] = {"value": val, "basis": "fit"}
        offs = list(fit["intercept_minus_national"].values())
        mean = sum(offs) / len(offs)
        sd = (sum((o - mean) ** 2 for o in offs) / len(offs)) ** 0.5
        params["house"]["translation_sd"] = {"value": round(sd, 2), "basis": "fit"}
    return params


def main(*, sims: int = 50_000, seed: int = 20261103, asof: str | None = None,
         snapshot: bool = False) -> dict:
    params = load_params()
    inp = load_inputs()
    if not inp["races"]:
        raise SystemExit("no races in data/races/ — run `midterms build` first")
    asof = asof or datetime.date.today().isoformat()
    res = run(inp, asof, params, sims=sims, seed=seed)
    generated = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    races_meta = {r["id"]: {k: r.get(k, "") for k in
                            ("chamber", "state", "label", "d_cand", "r_cand", "d_side",
                             "incumbent", "inc_party", "inc_running", "fixed", "lean")}
                  for r in inp["races"]}
    doc = {"generated": generated, "asof": asof, "headline": "deluxe",
           "model": "midterms2026-0.1", "n_sims": sims, "seed": seed,
           "sources": inp["meta"].get("sources_digest"),
           "params": {k: {kk: _v(params, k, kk) for kk in v} if isinstance(v, dict) else v
                      for k, v in params.items()},
           "races": races_meta, **res}
    FORECAST.mkdir(parents=True, exist_ok=True)
    (FORECAST / "latest.json").write_text(json.dumps(doc, indent=1, sort_keys=True))
    if snapshot:
        snap = FORECAST / "snapshots"
        snap.mkdir(exist_ok=True)
        (snap / f"{generated.replace(':', '')}.json").write_text(json.dumps(doc, sort_keys=True))
    summarize(doc)
    update_readme(doc)
    return doc


def update_readme(doc: dict) -> None:
    """Rewrite the README's <!-- forecast:start/end --> block so the
    headline numbers on GitHub are always the latest run's."""
    path = ROOT / "README.md"
    if not path.exists():
        return
    text = path.read_text()
    a, b = "<!-- forecast:start -->", "<!-- forecast:end -->"
    if a not in text or b not in text:
        return
    v = doc["versions"][doc["headline"]]
    gb = doc["national"]["generic_ballot"]["margin"]

    def row(name: str, label: str) -> str:
        c = v["chambers"][name]
        p = c["p_control"].get("D", 0)
        bold = "**" if name != "governor" else ""
        return (f"| {label} | {bold}{p:.1%}{bold} | {c['d_seats_p50']} | "
                f"{c['d_seats_p10']}–{c['d_seats_p90']} |")

    def tips(ch: str, n: int = 3) -> str:
        rs = sorted(((r["tipping"].get(ch, 0), rid) for rid, r in v["races"].items()
                     if ch in r["tipping"]), reverse=True)[:n]
        return ", ".join(doc["races"][rid]["label"].replace(" (special)", " (special)") for _, rid in rs)

    block = "\n".join([
        a,
        f"**Forecast as of {doc['asof']}** (deluxe version, {doc['n_sims']:,} simulations) · "
        f"generic ballot D{gb:+.1f} (two-party)",
        "",
        "| | Democrats win | Median D seats | 80% interval |",
        "|---|---:|---:|---:|",
        row("house", "House (218 for control)"),
        row("senate", "Senate (51; VP breaks ties)"),
        row("governor", "Governorships (26 of 50)"),
        "",
        f"House tipping points: {tips('house')}. Senate: {tips('senate')}.",
        b,
    ])
    start, end = text.index(a), text.index(b) + len(b)
    path.write_text(text[:start] + block + text[end:])


def summarize(doc: dict) -> None:
    d = doc["versions"][doc["headline"]]
    nat = doc["national"]["generic_ballot"]
    print(f"\nMIDTERMS2026 forecast as of {doc['asof']}  ({doc['n_sims']:,} simulations)")
    if nat["margin"] is not None:
        print(f"  generic ballot: D{nat['margin']:+.1f} (two-party) from {nat['n_polls']} polls, "
              f"latest {nat['latest']}")
    for cname in ("house", "senate", "governor"):
        if cname not in d["chambers"]:
            continue
        c = d["chambers"][cname]
        pc = c["p_control"]
        extra = f"  unclear {pc['unclear']:.1%}" if pc.get("unclear", 0) > 0.0005 else ""
        label = {"house": "House", "senate": "Senate", "governor": "Governors"}[cname]
        print(f"  {label:9s} D seats {c['d_seats_p50']} (80%: {c['d_seats_p10']}–{c['d_seats_p90']})"
              f"   P(D majority) {pc.get('D', 0):.1%}  P(R) {pc.get('R', 0):.1%}{extra}")
    for v in VERSIONS:
        ch = doc["versions"][v]["chambers"]
        print(f"    {v:8s} House D {ch['house']['p_control'].get('D', 0):.1%}"
              + (f"   Senate D {ch['senate']['p_control'].get('D', 0):.1%}" if 'senate' in ch else ""))


def show(rid: str) -> None:
    doc = json.loads((FORECAST / "latest.json").read_text())
    meta = doc["races"].get(rid)
    if not meta:
        raise SystemExit(f"no race {rid!r}; ids look like house:PA-07, senate:ME, governor:AZ")
    print(json.dumps({"race": meta, "detail": doc["detail"].get(rid),
                      "result": {v: doc["versions"][v]["races"][rid] for v in VERSIONS}},
                     indent=1))
