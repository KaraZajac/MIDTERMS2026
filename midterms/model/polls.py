"""Polling averages, FiveThirtyEight-style, with every adjustment measured.

A poll enters the average as a two-party margin (D-side minus R-side,
normalized by their combined share, in points) and is weighted by

    recency    0.5 ** (age / half_life)
    sample     sqrt(clamp(n, 200, 3000) / 600)
    quality    pollster rating weight (unknown pollsters get a discount)
    sponsor    partisan (candidate/party-affiliated) polls at half weight
    crowding   1/sqrt(k) for a pollster's k polls in the window

and adjusted for

    house effect   each pollster's average lean against everyone else
                   polling the same race at the same time, estimated
                   jointly across all races and shrunk toward zero
    population     RV/A polls shifted by the LV-minus-RV gap measured
                   from polls that published both versions
    sponsor bias   the measured average lean of D- and R-affiliated polls
    trend line     state/district polls taken weeks ago are moved by the
                   national generic-ballot change since they were fielded

None of these magnitudes is assumed: `fit_adjustments` measures each one
from the poll set itself and returns the estimates (with the number of
observations behind them) so they can be reported. Shrinkage priors keep
thinly observed adjustments near zero.
"""

from __future__ import annotations

import datetime
import math
from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class Poll:
    race: str                      # race id, or 'generic' / 'approval'
    pollster: str
    end: str                       # ISO date fieldwork ended
    margin: float                  # D-side minus R-side, two-party, points
    start: str | None = None
    n: int | None = None
    population: str | None = None  # LV / RV / A / V
    partisan: str | None = None    # 'D' / 'R' if affiliated / sponsored
    d: float | None = None         # raw D-side share
    r: float | None = None
    source: str = ""               # provenance (page + revision)
    key: str = ""                  # identity of the underlying poll


def two_party(d: float, r: float) -> float:
    return 100.0 * (d - r) / (d + r)


def days_between(a: str, b: str) -> int:
    return (datetime.date.fromisoformat(b) - datetime.date.fromisoformat(a)).days


def canonical_pollster(name: str) -> str:
    n = name.lower()
    for junk in (" university", " college", " poll", " polling", " research", " inc.",
                 " llc", " group", " strategies", " associates", " &", ",", "the "):
        n = n.replace(junk, " ")
    return " ".join(n.split())


POP_RANK = {"LV": 0, "V": 1, "RV": 2, "A": 3, None: 4}


def pick_versions(polls: list[Poll]) -> list[Poll]:
    """One version per underlying poll: prefer LV > V > RV > A, then the
    first-listed version (Wikipedia lists the headline question first)."""
    best: dict[tuple, Poll] = {}
    for p in polls:
        k = (p.race, canonical_pollster(p.pollster), p.start, p.end, p.partisan)
        cur = best.get(k)
        if cur is None or POP_RANK.get(p.population, 4) < POP_RANK.get(cur.population, 4):
            best[k] = p
    return list(best.values())


@dataclass
class Adjustments:
    house: dict = field(default_factory=dict)        # canonical pollster -> points
    house_n: dict = field(default_factory=dict)      # pollster -> polls behind it
    population: dict = field(default_factory=dict)  # 'RV'/'A' -> add to reach LV
    population_n: dict = field(default_factory=dict)
    sponsor: dict = field(default_factory=dict)      # 'D'/'R' -> measured lean
    sponsor_n: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        top = sorted(self.house.items(), key=lambda kv: -abs(kv[1]))
        return {
            "population_shift": {k: round(v, 2) for k, v in self.population.items()},
            "population_pairs": self.population_n,
            "sponsor_lean": {k: round(v, 2) for k, v in self.sponsor.items()},
            "sponsor_polls": self.sponsor_n,
            "house_effects": {k: {"points": round(v, 2), "polls": self.house_n.get(k, 0)}
                              for k, v in top},
        }


def _shrunk_mean(xs: list[float], prior_n: float) -> float:
    return sum(xs) / (len(xs) + prior_n) if xs else 0.0


def fit_adjustments(polls_all: list[Poll], *, window_days: int = 21,
                    house_prior_n: float = 6.0, sponsor_prior_n: float = 10.0,
                    pop_prior_n: float = 5.0, iters: int = 3) -> Adjustments:
    """Measure population, sponsor and house effects from the polls.

    Population shift: for polls that published both an LV and an RV (or A)
    version, the mean (LV - RV) margin — shrunk toward 0.

    House and sponsor effects: a poll's residual is its margin minus the
    mean margin of *other pollsters'* polls of the same race within
    +/- window_days. Sponsor lean is the shrunk mean residual of
    D- (R-) affiliated polls; house effects are the shrunk mean residual by
    pollster after removing sponsor lean. Iterated so each estimate is made
    against already-adjusted comparators.
    """
    adj = Adjustments()
    # -- population: paired versions
    groups: dict[tuple, dict] = defaultdict(dict)
    for p in polls_all:
        k = (p.race, canonical_pollster(p.pollster), p.start, p.end)
        groups[k].setdefault(p.population, p)
    diffs: dict[str, list[float]] = {"RV": [], "A": []}
    for g in groups.values():
        if "LV" in g:
            for pop in ("RV", "A"):
                if pop in g:
                    diffs[pop].append(g["LV"].margin - g[pop].margin)
    for pop, xs in diffs.items():
        adj.population[pop] = _shrunk_mean(xs, pop_prior_n)
        adj.population_n[pop] = len(xs)

    polls = pick_versions(polls_all)
    by_race: dict[str, list[Poll]] = defaultdict(list)
    for p in polls:
        by_race[p.race].append(p)

    def adjusted(p: Poll) -> float:
        m = p.margin + adj.population.get(p.population, 0.0)
        m -= adj.house.get(canonical_pollster(p.pollster), 0.0)
        if p.partisan:
            m -= adj.sponsor.get(p.partisan, 0.0)
        return m

    for _ in range(iters):
        resid_by_pollster: dict[str, list[float]] = defaultdict(list)
        resid_by_sponsor: dict[str, list[float]] = defaultdict(list)
        for race, ps in by_race.items():
            if len(ps) < 3:
                continue
            for p in ps:
                cp = canonical_pollster(p.pollster)
                comps = [adjusted(q) for q in ps
                         if canonical_pollster(q.pollster) != cp
                         and abs(days_between(q.end, p.end)) <= window_days]
                if len(comps) < 2:
                    continue
                base = sum(comps) / len(comps)
                raw = p.margin + adj.population.get(p.population, 0.0)
                if p.partisan:
                    resid_by_sponsor[p.partisan].append(raw - base)
                resid = raw - base - (adj.sponsor.get(p.partisan, 0.0) if p.partisan else 0.0)
                resid_by_pollster[cp].append(resid)
        adj.sponsor = {k: _shrunk_mean(v, sponsor_prior_n) for k, v in resid_by_sponsor.items()}
        adj.sponsor_n = {k: len(v) for k, v in resid_by_sponsor.items()}
        adj.house = {k: _shrunk_mean(v, house_prior_n) for k, v in resid_by_pollster.items()}
        adj.house_n = {k: len(v) for k, v in resid_by_pollster.items()}
    return adj


def margin_sampling_sd(n: int | None) -> float:
    """Sampling sd of a two-candidate margin, in points (n=600 -> ~4.1)."""
    n = n if n and n >= 100 else 600
    return 100.0 / math.sqrt(n)


@dataclass
class Average:
    margin: float | None
    sd: float | None          # race-level uncertainty of the average
    n_polls: int
    n_eff: float
    latest: str | None
    pollsters: int
    weights: list            # (poll, weight, adjusted margin) for display
    partisan_share: float = 0.0


def average(polls: list[Poll], asof: str, adj: Adjustments, *,
            half_life: float = 14.0, max_age: int = 150,
            quality: dict | None = None, trend=None, lam: float = 1.0,
            sd_nonsampling: float = 3.0, sd_floor: float = 2.0,
            sd_partisan: float = 3.5) -> Average:
    """Weighted, adjusted average of one race's polls as of `asof`.

    `trend(date) -> national margin` enables the trend-line adjustment.
    `quality` maps canonical pollster -> weight multiplier.
    """
    ps = [p for p in pick_versions(polls)
          if 0 <= days_between(p.end, asof) <= max_age]
    if not ps:
        return Average(None, None, 0, 0.0, None, 0, [], 0.0)
    counts = defaultdict(int)
    for p in ps:
        counts[canonical_pollster(p.pollster)] += 1
    rows = []
    now_nat = trend(asof) if trend else None
    for p in ps:
        cp = canonical_pollster(p.pollster)
        age = days_between(p.end, asof)
        w = 0.5 ** (age / half_life)
        n = p.n if p.n else 500
        w *= math.sqrt(min(max(n, 200), 3000) / 600)
        w *= (quality or {}).get(cp, 0.75)
        if p.partisan:
            w *= 0.5
        w /= math.sqrt(counts[cp])
        m = p.margin + adj.population.get(p.population, 0.0)
        m -= adj.house.get(cp, 0.0)
        if p.partisan:
            m -= adj.sponsor.get(p.partisan, 0.0)
        if trend and now_nat is not None:
            then = trend(p.end)
            if then is not None:
                m += lam * (now_nat - then)
        rows.append((p, w, m))
    sw = sum(w for _, w, _ in rows)
    mean = sum(w * m for _, w, m in rows) / sw
    n_eff = sw * sw / sum(w * w for _, w, _ in rows)
    samp_var = sum((w / sw) ** 2 * margin_sampling_sd(p.n) ** 2 for p, w, _ in rows)
    latest = max(p.end for p, _, _ in rows)
    stale = days_between(latest, asof)
    # a race nobody has polled lately may have moved: +1.5pt sd per month
    stale_var = (1.5 ** 2) * (stale / 30.0)
    # an average built from campaign/party-sponsored polls can't be checked
    # against independent ones: their release bias varies race to race
    partisan_share = sum(w for p, w, _ in rows if p.partisan) / sw
    partisan_var = (sd_partisan ** 2) * partisan_share
    sd = math.sqrt(sd_nonsampling ** 2 + samp_var + stale_var + partisan_var)
    return Average(mean, max(sd, sd_floor), len(rows), n_eff, latest,
                   len(counts), rows, partisan_share)


def daily_series(polls: list[Poll], adj: Adjustments, start: str, end: str, **kw) -> dict:
    """Average as of each day in [start, end] (for the national trend line
    and the site's chart). Returns {iso_date: (margin, sd, n_polls)}."""
    out = {}
    d = datetime.date.fromisoformat(start)
    stop = datetime.date.fromisoformat(end)
    while d <= stop:
        a = average(polls, d.isoformat(), adj, **kw)
        if a.margin is not None:
            out[d.isoformat()] = (a.margin, a.sd, a.n_polls)
        d += datetime.timedelta(days=1)
    return out
