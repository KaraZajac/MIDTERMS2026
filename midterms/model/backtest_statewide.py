"""The statewide polling backtest: how accurate is *this* polling average?

The Senate and governor forecasts lean mostly on polls, so this replays the
exact averaging code (`model/polls.py`: version selection, recency /
sample / quality / sponsor / crowding weights, house effects and LV-RV and
sponsor adjustments fit on that year's polls only) on every Senate and
governor race of 2014–2024, as of three days before each election, and
compares the average with the result.

Inputs are the same kind of Wikipedia race pages the 2026 forecast reads
(poll tables, the results box, the dated 'Predictions' table), fetched and
cached like any source. Races are kept when the result has a Republican
and a non-Republican side (D or an independent) and at least one poll.

Outputs (data/backtest_statewide.yaml):
  per-year mean error — the systematic, shared miss (what the national
    error term must cover) — and RMSE;
  the race-level spread after removing each year's shared miss (what the
    race and state/region terms must cover);
  win-probability calibration and Brier/log scores for polls alone,
    ratings alone, and the two blended, using the forecast's own
    uncertainty assumptions (params.yaml).

Caveats: Silver Bulletin's 2026 pollster ratings, used for quality weights,
were themselves informed by these races' results (a mild leak); no trend-
line adjustment (it needs that year's generic-ballot series, ~zero effect
three days out); and Wikipedia's historical tables are what editors kept.
"""

from __future__ import annotations

import datetime
import math
from collections import defaultdict

import numpy as np
import yaml

from midterms.model import polls as P
from midterms.model import ratings as R
from midterms.model.forecast import PARAMS, _v
from midterms.paths import DATA, SOURCES
from midterms.pipeline import racepage as rp
from midterms.pipeline import races as racemod
from midterms.pipeline import wiki
from midterms.pipeline.htmltable import extract_tables, references
from midterms.pipeline.states import STATES

ELECTION = {2014: "2014-11-04", 2016: "2016-11-08", 2018: "2018-11-06",
            2020: "2020-11-03", 2022: "2022-11-08", 2024: "2024-11-05",
            2025: "2025-11-04"}   # the off-year NJ/VA governorships: polled under this administration
MIDTERM_LIKE = (2014, 2018, 2022, 2025)     # no presidential race on the ballot
CLASS = {
    1: "AZ CA CT DE FL HI IN ME MD MA MI MN MS MO MT NE NV NJ NM NY ND OH PA RI TN TX UT VT VA WA WV WI WY",
    2: "AL AK AR CO DE GA ID IL IA KS KY LA ME MA MI MN MS MT NE NH NJ NM NC OK OR RI SC SD TN TX VA WV WY",
    3: "AL AK AZ AR CA CO CT FL GA HI ID IL IN IA KS KY LA MD MO NV NH NY NC ND OH OK OR PA SC SD UT VT WA WI",
}
YEAR_CLASS = {2014: 2, 2016: 3, 2018: 1, 2020: 2, 2022: 3, 2024: 1}
SPECIALS = {2014: ["HI", "OK", "SC"], 2018: ["MN", "MS"], 2020: ["AZ", "GA"], 2022: ["OK"],
            2024: ["NE"]}
GOV36 = ("AL AK AZ AR CA CO CT FL GA HI ID IL IA KS ME MD MA MI MN NE NV NH NM NY OH OK OR PA "
         "RI SC SD TN TX VT WI WY")
GOV11 = "DE IN MO MT NH NC ND UT VT WA WV"
GOVS = {2014: GOV36, 2018: GOV36, 2022: GOV36, 2016: GOV11, 2020: GOV11, 2024: GOV11,
        2025: "NJ VA"}


def pages() -> list[tuple[int, str, str, str]]:
    """(year, chamber, state, title)"""
    out = []
    for y in ELECTION:
        for st in (CLASS[YEAR_CLASS[y]].split() if y in YEAR_CLASS else []):
            out.append((y, "senate", st, f"{y} United States Senate election in {STATES[st]}"))
        for st in SPECIALS.get(y, []):
            out.append((y, "senate", st, f"{y} United States Senate special election in {STATES[st]}"))
        for st in GOVS[y].split():
            out.append((y, "governor", st, f"{y} {STATES[st]} gubernatorial election"))
    out.append((2016, "governor", "OR", "2016 Oregon gubernatorial special election"))
    return out


def results_any(tables, gen) -> list[dict]:
    box = rp.results_box(gen) or []
    if not box:   # some pages keep the box in a top-level 'Results' section
        res = [t for t in tables if t.headings[0].lower().startswith("results")]
        box = rp.results_box([t for t in res if not rp.subsection(t)]) or rp.results_box(res) or []
    return box


def race_record(year: int, chamber: str, st: str, title: str) -> dict | None:
    try:
        page = wiki.fetch_page(title, max_age_hours=None)
    except SystemExit:
        return None
    tables = extract_tables(page["html"])
    gen = rp.general(tables)
    box = [c for c in results_any(tables, gen) if c.get("votes")]
    if len(box) < 2:
        return None
    rs = sorted((c for c in box if c["party_code"] == "R"), key=lambda c: -c["votes"])
    nonr = sorted((c for c in box if c["party_code"] != "R"), key=lambda c: -c["votes"])
    if not rs or not nonr:
        return None
    d, r = nonr[0], rs[0]
    top2 = sorted(box, key=lambda c: -c["votes"])[:2]
    if {c["party_code"] for c in top2} == {"R"}:      # e.g. Alaska 2022 (two Republicans)
        return None
    rid = f"{chamber}:{st}:{year}"
    src = f"wikipedia:{page['title']}@{page['revid']}"
    polls = racemod._poll_rows(rid, gen, d, r, src, references(page["html"]))
    preds = rp.predictions(gen, default_year=year)
    actual = 100.0 * (d["votes"] - r["votes"]) / (d["votes"] + r["votes"])
    return {"id": rid, "year": year, "chamber": chamber, "state": st, "title": page["title"],
            "revid": page["revid"], "d": d["candidate"], "d_party": d["party_code"],
            "r": r["candidate"], "actual": actual, "polls": polls, "preds": preds}


def _phi(z: float) -> float:
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def fit_poll_error(rows: list[dict], params: dict, nu: float = 6.0) -> dict:
    """Grid-search maximum likelihood for (race-shared, per-poll) nonsampling
    sds under the simulator's own unit-variance Student-t race error."""
    xs = [x for x in rows if x["d_party"] == "D"]
    ym = defaultdict(list)
    for x in rows:
        ym[x["year"]].append(x["error"])
    ym = {y: float(np.mean(v)) for y, v in ym.items()}
    r = np.array([x["error"] - ym[x["year"]] for x in xs])
    neff = np.array([x["n_eff"] for x in xs])
    other = np.array([x["other_var"] for x in xs])
    shared = _v(params, "shared", "sd_region") ** 2 + _v(params, "shared", "sd_state") ** 2
    c = math.lgamma((nu + 1) / 2) - math.lgamma(nu / 2) - 0.5 * math.log(nu * math.pi)

    def ll(sc, sp):
        s2 = (shared + sc ** 2 + sp ** 2 / neff + other) * (nu - 2) / nu
        return float(np.sum(c - 0.5 * np.log(s2) - (nu + 1) / 2 * np.log1p(r ** 2 / (nu * s2))))

    best = max(((ll(sc, sp), sc, sp) for sc in np.arange(0.0, 6.01, 0.1)
                for sp in np.arange(0.0, 15.01, 0.25)), key=lambda t: t[0])
    cur = ll(_v(params, "polls", "sd_nonsampling"), _v(params, "polls", "sd_per_poll"))
    return {"sd_nonsampling": round(float(best[1]), 2), "sd_per_poll": round(float(best[2]), 2),
            "n": int(len(r)), "loglik": round(best[0], 1), "loglik_at_params": round(cur, 1),
            "likelihood": f"Student t, {nu:g} df (the simulator's race error)"}


def national_error(year_stats: dict, race_var: float) -> dict:
    """The shared, cycle-level miss. A year's mean error = national error +
    race-level noise / n, so its variance net of noise estimates the national
    error variance: E[mean^2] - race_var / n, per cycle."""
    net = {y: s["mean_error"] ** 2 - race_var / s["n"] for y, s in year_stats.items()}

    def pooled(ys):
        v = [net[y] for y in ys if y in net]
        return round(float(np.sqrt(max(np.mean(v), 0.0))), 2) if v else None

    return {
        "year_means": {y: s["mean_error"] for y, s in year_stats.items()},
        "sd_estimate_midterm_like": pooled(MIDTERM_LIKE),
        "sd_estimate_all_cycles": pooled(list(year_stats)),
        "sd_estimate_presidential": pooled([2016, 2020, 2024]),
        "mean_year_mean": round(float(np.mean([s["mean_error"] for s in year_stats.values()])), 2),
        "note": "sd of the national (cycle-level) polling miss, net of race-level noise; "
                "midterm-like = no presidential race (2014, 2018, 2022, 2025). Its sign is not "
                "modeled: see docs/method.md, Accuracy."}


def fit_ratings(rows: list[dict], fit: dict, params: dict) -> dict:
    """Rescale the rating -> margin anchors (k) and choose the rating sd,
    both by leave-one-cycle-out log loss of the polls + ratings blend."""
    rated = [x for x in rows if x["rating_scale"] is not None]
    years = sorted({x["year"] for x in rated})
    shared = math.sqrt(_v(params, "national", "sd") ** 2 + _v(params, "shared", "sd_region") ** 2
                       + _v(params, "shared", "sd_state") ** 2)

    def k_of(xs):
        X = np.array([R.implied_margin(x["rating_scale"]) for x in xs])
        Y = np.array([x["actual"] for x in xs])
        return float((X @ Y) / (X @ X))

    def loyo(sd_r):
        loss = n = 0
        for y in years:
            k = k_of([x for x in rated if x["year"] != y])
            for x in rated:
                if x["year"] != y:
                    continue
                sd_p = math.sqrt(fit["sd_nonsampling"] ** 2 + fit["sd_per_poll"] ** 2 / x["n_eff"]
                                 + x["other_var"])
                w1, w2 = 1 / sd_p ** 2, 1 / (sd_r * 1.3) ** 2
                mu = (w1 * x["poll_avg"] + w2 * k * R.implied_margin(x["rating_scale"])) / (w1 + w2)
                sd = (w1 + w2) ** -0.5
                p = min(max(_phi(mu / math.sqrt(sd ** 2 + shared ** 2)), 1e-4), 1 - 1e-4)
                yv = 1 if x["actual"] > 0 else 0
                loss += -(yv * math.log(p) + (1 - yv) * math.log(1 - p))
                n += 1
        return loss / n

    grid = {sd: round(loyo(sd), 4) for sd in (1.5, 2.5, 3.5, 4.5, 5.5, 6.5)}
    return {"k": round(k_of(rated), 3),
            "k_leave_one_cycle_out": {y: round(k_of([x for x in rated if x["year"] != y]), 3) for y in years},
            "loyo_log_loss_by_sd": grid, "n": len(rated),
            "sd_note": "Not adopted: the loss falls monotonically as the rating sd shrinks, i.e. "
                       "'trust raters over polls' -- because 2014-2024 polls overstated Democrats "
                       "and raters were more cautious. That is the directional correction the "
                       "model declines to make (2025 ran the other way); the rating sd stays at "
                       "its prior. k, a scale calibration, is adopted."}


def generic_ballot_check(params: dict, quality_db: dict) -> dict | None:
    """The generic-ballot average (this code, 3 days out, on FiveThirtyEight's
    archived polls) against the national House vote (FEC) and against the
    district baseline the House backtest fit (data/backtest.yaml)."""
    import csv
    path = SOURCES / "history" / "fte-generic-ballot-polls-historical.csv"
    if not path.exists():
        return None
    from midterms.model import backtest as house_bt
    from midterms.model import pollsters as PQ
    rows = list(csv.DictReader(open(path, newline="", encoding="utf-8")))

    def iso(s):
        m, d, y = s.split("/")
        return datetime.date(2000 + int(y), int(m), int(d)).isoformat()

    hb = yaml.safe_load((DATA / "backtest.yaml").read_text()) if (DATA / "backtest.yaml").exists() else {}
    intercepts = (hb.get("fit") or {}).get("year_intercepts", {})
    out = {}
    for y in (2018, 2020, 2022):
        asof = (datetime.date.fromisoformat(ELECTION[y]) - datetime.timedelta(days=3)).isoformat()
        ps = []
        for r in rows:
            if r["cycle"] != str(y) or not r["dem"] or not r["rep"]:
                continue
            d, rr = float(r["dem"]), float(r["rep"])
            if d + rr <= 0:
                continue
            ps.append(P.Poll(race="generic", pollster=r["display_name"] or r["pollster"],
                             start=iso(r["start_date"]), end=iso(r["end_date"]),
                             n=int(float(r["sample_size"])) if r["sample_size"] else None,
                             population={"lv": "LV", "rv": "RV", "a": "A", "v": "V"}.get(r["population"]),
                             partisan={"DEM": "D", "REP": "R"}.get((r["partisan"] or "").upper()),
                             d=d, r=rr, margin=P.two_party(d, rr)))
        ps = [p for p in ps if p.end <= asof]
        adj = P.fit_adjustments(ps)
        quality = {P.canonical_pollster(q["pollster"]): q["weight"]
                   for q in PQ.quality_table({p.pollster for p in ps}, quality_db)}
        a = P.average(ps, asof, adj, half_life=_v(params, "national", "generic_half_life_days"),
                      max_age=120, quality=quality, sd_nonsampling=0.0, sd_floor=0.0)
        try:
            _, national = house_bt.results(y)
        except (FileNotFoundError, StopIteration):
            national = None
        row = {"average": round(a.margin, 2), "n_polls": a.n_polls,
               "house_vote": None if national is None else round(national, 2)}
        if national is not None:
            row["miss_vs_vote"] = round(national - a.margin, 2)
        if y in intercepts:
            row["district_baseline"] = intercepts[y]
            row["miss_vs_baseline"] = round(intercepts[y] - a.margin, 2)
        out[y] = row
    return {"what": "generic-ballot average 3 days out vs the national two-party House vote and "
                    "vs the fitted district baseline (the quantity the House model needs)",
            "source": "FiveThirtyEight generic-ballot poll archive (CC BY 4.0) via the Internet Archive",
            "cycles": out}


def score(ps: list[float], ys: list[int]) -> dict:
    ps = [min(max(p, 1e-4), 1 - 1e-4) for p in ps]
    n = len(ps)
    brier = sum((p - y) ** 2 for p, y in zip(ps, ys)) / n
    ll = -sum(y * math.log(p) + (1 - y) * math.log(1 - p) for p, y in zip(ps, ys)) / n
    calls = sum(1 for p, y in zip(ps, ys) if (p > 0.5) == (y == 1)) / n
    bins = defaultdict(lambda: [0, 0, 0.0])
    for p, y in zip(ps, ys):
        b = min(9, int(p * 10))
        bins[b][0] += 1
        bins[b][1] += y
        bins[b][2] += p
    return {"n": n, "brier": round(brier, 4), "log_loss": round(ll, 4), "calls": round(calls, 3),
            "calibration": [{"bin": f"{b / 10:.1f}-{(b + 1) / 10:.1f}", "n": v[0],
                             "forecast": round(v[2] / v[0], 3), "observed": round(v[1] / v[0], 3)}
                            for b, v in sorted(bins.items())]}


def main() -> dict:
    params = yaml.safe_load(PARAMS.read_text())
    from midterms.model import pollsters as PQ
    qdb = PQ.load_ratings(SOURCES / "pollsters" / "silver-bulletin-2026-01.xlsx",
                          SOURCES / "pollsters" / "fte-pollster-ratings-2024.csv")
    recs = []
    for year, chamber, st, title in pages():
        rec = race_record(year, chamber, st, title)
        if rec:
            recs.append(rec)
    sd_nat = _v(params, "national", "sd")
    shared = math.sqrt(sd_nat ** 2 + _v(params, "shared", "sd_region") ** 2
                       + _v(params, "shared", "sd_state") ** 2)
    rows = []
    for year in ELECTION:
        asof = (datetime.date.fromisoformat(ELECTION[year]) - datetime.timedelta(days=3)).isoformat()
        yr = [r for r in recs if r["year"] == year]
        allp = []
        for r in yr:
            r["P"] = [P.Poll(race=r["id"], pollster=p["pollster"], start=p["start"] or None,
                             end=p["end"], n=int(p["n"]) if p["n"] else None,
                             population=p["population"] or None, partisan=p["partisan"] or None,
                             d=p["d"], r=p["r"], margin=P.two_party(p["d"], p["r"]))
                      for p in r["polls"] if p["end"] and p["end"] <= asof and p["d"] + p["r"] > 0]
            allp += r["P"]
        adj = P.fit_adjustments(allp)
        names = {p.pollster for p in allp}
        quality = {P.canonical_pollster(q["pollster"]): q["weight"]
                   for q in PQ.quality_table(names, qdb)}
        for r in yr:
            if not r["P"]:
                continue
            a = P.average(r["P"], asof, adj, half_life=_v(params, "polls", "half_life_days"),
                          max_age=_v(params, "polls", "max_age_days"), quality=quality,
                          sd_nonsampling=_v(params, "polls", "sd_nonsampling"),
                          sd_partisan=_v(params, "polls", "sd_partisan"))
            if a.margin is None:
                continue
            # final pre-election ratings from the core raters
            latest = {}
            for pr in r["preds"]:
                name = R.rater(pr["source"])
                if name in R.CORE and (pr["asof"] or "") <= ELECTION[year]:
                    s = R.scale(pr["rating"], d_side_party=r["d_party"])
                    if s is not None and (name not in latest or (pr["asof"] or "") >= latest[name][1]):
                        latest[name] = (s, pr["asof"] or "")
            rating = (sum(v[0] for v in latest.values()) / len(latest)) if latest else None
            rows.append({"id": r["id"], "year": year, "chamber": r["chamber"], "state": r["state"],
                         "d": r["d"], "d_party": r["d_party"], "r": r["r"],
                         "actual": round(r["actual"], 2), "poll_avg": round(a.margin, 2),
                         "poll_sd": round(a.sd, 2), "n_polls": a.n_polls,
                         "n_eff": round(a.n_eff, 3), "other_var": round(a.samp_var, 3),
                         "error": round(r["actual"] - a.margin, 2),
                         "rating_scale": rating, "title": r["title"], "revid": r["revid"]})
    # --- fit the poll-error components (t(6) likelihood, D-nominee races,
    # each year's shared miss removed; region + state terms held at params)
    fit = fit_poll_error(rows, params)
    for x in rows:
        x["poll_sd"] = round(math.sqrt(fit["sd_nonsampling"] ** 2
                                       + fit["sd_per_poll"] ** 2 / x["n_eff"] + x["other_var"]), 2)
    # --- error structure
    by_year = defaultdict(list)
    for x in rows:
        by_year[x["year"]].append(x)
    year_stats, resid = {}, []
    for y, xs in sorted(by_year.items()):
        e = np.array([x["error"] for x in xs])
        year_stats[y] = {"n": len(xs), "mean_error": round(float(e.mean()), 2),
                         "rmse": round(float(np.sqrt((e ** 2).mean())), 2),
                         "mae": round(float(np.abs(e).mean()), 2)}
        resid += list(e - e.mean())
    e_all = np.array([x["error"] for x in rows])
    means = np.array([v["mean_error"] for v in year_stats.values()])
    # --- probabilities: polls alone, ratings alone, blended — the forecast's
    # sds and the fitted rating-map scale (k barely moves between held-out cycles)
    rf = fit_ratings(rows, fit, params)
    ys = [1 if x["actual"] > 0 else 0 for x in rows]
    sd_rating = _v(params, "ratings", "sd") * 1.3
    p_polls, p_ratings, p_blend, y_r = [], [], [], []
    for x, y in zip(rows, ys):
        tot_p = math.sqrt(x["poll_sd"] ** 2 + shared ** 2)
        p_polls.append(_phi(x["poll_avg"] / tot_p))
        if x["rating_scale"] is not None:
            mu_e = R.implied_margin(x["rating_scale"], k=rf["k"])
            p_ratings.append(_phi(mu_e / math.sqrt(_v(params, "ratings", "sd") ** 2 + shared ** 2)))
            w1, w2 = 1 / x["poll_sd"] ** 2, 1 / sd_rating ** 2
            mu_b = (w1 * x["poll_avg"] + w2 * mu_e) / (w1 + w2)
            sd_b = (w1 + w2) ** -0.5
            p_blend.append(_phi(mu_b / math.sqrt(sd_b ** 2 + shared ** 2)))
            y_r.append(y)
    p_polls_r = [p for p, x in zip(p_polls, rows) if x["rating_scale"] is not None]
    out = {
        "generated_by": "python3 -m midterms backtest",
        "what": "this model's polling average, as of 3 days out, vs. results: every Senate and "
                "governor race 2014-2024 with a poll and a Republican vs non-Republican result",
        "n_races": len(rows),
        "by_year": year_stats,
        "error": {"mean": round(float(e_all.mean()), 2), "rmse": round(float(np.sqrt((e_all ** 2).mean())), 2),
                  "mae": round(float(np.abs(e_all).mean()), 2),
                  "sd_of_year_means": round(float(means.std(ddof=1)), 2),
                  "rms_of_year_means": round(float(np.sqrt((means ** 2).mean())), 2),
                  "race_sd_after_year_mean": round(float(np.std(resid, ddof=len(year_stats))), 2)},
        "fit": fit,
        "national_error": national_error(year_stats, float(np.var(resid))),
        "model_assumptions": {"sd_national": sd_nat, "shared_sd": round(shared, 2),
                              "typical_poll_sd": round(float(np.median([x["poll_sd"] for x in rows])), 2)},
        "ratings_fit": rf,
        "generic_ballot": generic_ballot_check(params, qdb),
        "scores": {"polls": score(p_polls, ys),
                   "polls_on_rated": score(p_polls_r, y_r) if y_r else None,
                   "ratings": score(p_ratings, y_r) if y_r else None,
                   "polls_plus_ratings": score(p_blend, y_r) if y_r else None},
        "races": rows,
    }
    (DATA / "backtest_statewide.yaml").write_text(yaml.safe_dump(out, sort_keys=False, allow_unicode=True))
    e = out["error"]
    print(f"statewide backtest: {len(rows)} races (Senate + governor, 2014-2025)")
    for y, s in year_stats.items():
        print(f"  {y}: n={s['n']:3d} mean error {s['mean_error']:+.2f} (D-side minus poll avg)  "
              f"RMSE {s['rmse']:.2f}")
    print(f"  pooled RMSE {e['rmse']}  sd of year means {e['sd_of_year_means']}  "
          f"race sd after year mean {e['race_sd_after_year_mean']}")
    print(f"  fit (t likelihood): sd_nonsampling {fit['sd_nonsampling']}  sd_per_poll "
          f"{fit['sd_per_poll']}  (loglik {fit['loglik']} vs {fit['loglik_at_params']} at params)")
    ne = out["national_error"]
    print(f"  national-miss sd (net of noise): midterm-like {ne['sd_estimate_midterm_like']}, "
          f"all cycles {ne['sd_estimate_all_cycles']}, presidential {ne['sd_estimate_presidential']}")
    rf = out["ratings_fit"]
    print(f"  ratings map: k {rf['k']} (leave-one-out {min(rf['k_leave_one_cycle_out'].values())}-"
          f"{max(rf['k_leave_one_cycle_out'].values())}); rating-sd grid (not adopted) "
          f"{rf['loyo_log_loss_by_sd']}")
    gb = out.get("generic_ballot")
    if gb:
        for y, c in gb["cycles"].items():
            print(f"  generic {y}: average {c['average']:+.2f}; miss vs House vote "
                  f"{c.get('miss_vs_vote')}; vs district baseline {c.get('miss_vs_baseline')}")
    for k, s in out["scores"].items():
        if s:
            print(f"  {k:18s} n={s['n']} Brier {s['brier']} log {s['log_loss']} calls {s['calls']}")
    return out
