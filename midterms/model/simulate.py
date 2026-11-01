"""Correlated Monte Carlo over every race on the ballot.

Each race arrives with an expected two-party margin `mu` (D-side minus
R-side, in points) and a race-level standard deviation `sd` — the error of
that estimate *excluding* the error everything shares. The simulator
supplies the shared part, the way FiveThirtyEight's models did:

    margin[s, r] = mu[r]
                 + lam[r] * national[s]            fat-tailed (Student t)
                 + region[s, region(r)]            Census-region swing
                 + state[s, state(r)]              statewide swing (House
                                                   districts share it with
                                                   their state's Senate and
                                                   governor races)
                 + idio[s, r]                      fat-tailed, race-specific

The race-specific scale is chosen so the *total* spread of each race equals
sqrt(sd^2 + lam^2 sd_nat^2 + sd_region^2 + sd_state^2) — i.e. `sd` is
preserved exactly and the shared terms add correlation, not double counting.

Races decided before Election Day (uncontested; same-party top-two generals)
carry `fixed`: the party that will win with certainty.

Outputs are summaries: per-race win probabilities and margin quantiles, the
seat-count distribution per chamber, control probabilities, tipping-point
frequencies, and joint House x Senate outcomes. Draws are processed in
chunks so memory stays flat at any simulation count.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field

import numpy as np

REGIONS = {  # Census regions
    "Northeast": "CT ME MA NH RI VT NJ NY PA",
    "Midwest": "IL IN MI OH WI IA KS MN MO NE ND SD",
    "South": "DE DC FL GA MD NC SC VA WV AL KY MS TN AR LA OK TX",
    "West": "AZ CO ID MT NV NM UT WY AK CA HI OR WA",
}
STATE_REGION = {s: r for r, ss in REGIONS.items() for s in ss.split()}
QUANTILES = [1, 5, 10, 25, 50, 75, 90, 95, 99]


@dataclass
class Race:
    id: str
    chamber: str               # house | senate | governor
    state: str
    mu: float = 0.0            # expected D-side minus R-side margin (points)
    sd: float = 6.0            # race-level sd (excluding shared error)
    lam: float = 1.0           # loading on the national error
    fixed: str | None = None   # 'D' / 'R' / other: decided with certainty
    d_side: str = "D"          # party of the D-side candidate ('D', or 'I' e.g. Osborn)
    r_side: str = "R"


@dataclass
class Shared:
    sd_national: float = 2.8   # national environment / systematic poll error
    nu_national: float = 5.0   # t degrees of freedom (fat tails)
    sd_region: float = 1.5
    sd_state: float = 1.8
    nu_race: float = 6.0
    floor_idio: float = 0.5
    # an extra shared shift per chamber, e.g. {'house': 2.1}: the year-to-year
    # instability of the national-vote -> district-baseline translation
    sd_chamber: dict = field(default_factory=dict)


@dataclass
class Chamber:
    """How seats roll up into control for one chamber."""
    name: str
    seats_not_up: dict = field(default_factory=dict)   # party -> count
    majority: int = 218
    tie_breaker: str | None = None   # party that wins a tie (Senate: VP's party)
    caucus: dict = field(default_factory=dict)          # party -> caucus ('I' -> 'D')
    alt_caucus: dict | None = None   # a second mapping to report control under


def _control(totals: dict, ch: "Chamber", caucus: dict, S: int):
    """Roll party seat totals into blocs and decide control per simulation."""
    blocs = {}
    for p, cnt in totals.items():
        b = caucus.get(p, p)
        blocs[b] = blocs.get(b, 0) + cnt
    zero = np.zeros(S, dtype=int)
    dseats = blocs.get("D", zero) + zero
    rseats = blocs.get("R", zero) + zero
    maj = ch.majority
    d_ctrl = dseats >= maj
    r_ctrl = rseats >= maj
    if ch.tie_breaker:
        half = maj - 1   # e.g. 50 of 100
        tie = (dseats == half) & (rseats == half)
        if ch.tie_breaker == "D":
            d_ctrl = d_ctrl | tie
        else:
            r_ctrl = r_ctrl | tie
    return dseats, rseats, d_ctrl, r_ctrl


def _t(rng: np.random.Generator, nu: float, size) -> np.ndarray:
    """Student-t draws rescaled to unit variance."""
    if not np.isfinite(nu) or nu > 200:
        return rng.standard_normal(size)
    return rng.standard_t(nu, size) * np.sqrt((nu - 2.0) / nu)


def simulate(races: list[Race], shared: Shared, chambers: dict[str, Chamber], *,
             n_sims: int = 40_000, seed: int = 20261103, chunk: int = 5_000,
             keep_hist: bool = True) -> dict:
    rng = np.random.default_rng(seed)
    R = len(races)
    states = sorted({r.state for r in races})
    regions = sorted(set(REGIONS))
    s_idx = np.array([states.index(r.state) for r in races])
    g_idx = np.array([regions.index(STATE_REGION.get(r.state, "South")) for r in races])
    mu = np.array([r.mu for r in races], dtype=np.float64)
    lam = np.array([r.lam for r in races], dtype=np.float64)
    sd = np.array([r.sd for r in races], dtype=np.float64)
    sd_idio = np.maximum(sd, shared.floor_idio)
    fixed_mask = np.array([r.fixed is not None for r in races])
    # +inf/-inf margins encode certain D-side / R-side wins
    fixed_val = np.array([(np.inf if r.fixed == r.d_side else -np.inf) if r.fixed else 0.0
                          for r in races])

    by_chamber = {c: np.array([r.chamber == c for r in races]) for c in chambers}
    # seat accounting per chamber: winners' parties, as small int codes
    all_parties = sorted({r.d_side for r in races} | {r.r_side for r in races}
                         | {p for ch in chambers.values() for p in ch.seats_not_up})
    pcode = {p: i for i, p in enumerate(all_parties)}
    d_party = np.array([pcode[r.d_side] for r in races], dtype=np.int16)
    r_party = np.array([pcode[r.r_side] for r in races], dtype=np.int16)

    win_sum = np.zeros(R)
    margin_samples = []               # thin sample for quantiles
    keep_every = max(1, n_sims // 10000)
    seat_hist = {c: {} for c in chambers}
    control = {c: {} for c in chambers}
    control_alt: dict = {}
    party_seats: dict = {}
    tipping = {c: np.zeros(R) for c in chambers}
    joint = {}
    national_draws = []

    done = 0
    while done < n_sims:
        S = min(chunk, n_sims - done)
        nat = _t(rng, shared.nu_national, S) * shared.sd_national
        reg = rng.standard_normal((S, len(regions))) * shared.sd_region
        st = rng.standard_normal((S, len(states))) * shared.sd_state
        idio = _t(rng, shared.nu_race, (S, R)) * sd_idio
        m = mu + lam * nat[:, None] + reg[:, g_idx] + st[:, s_idx] + idio
        for cname, sdc in shared.sd_chamber.items():
            cmask = by_chamber.get(cname)
            if cmask is not None and sdc > 0:
                m[:, cmask] += (rng.standard_normal(S) * sdc)[:, None]
        m[:, fixed_mask] = fixed_val[fixed_mask]
        dwin = m > 0
        win_sum += dwin.sum(axis=0)
        margin_samples.append(np.where(np.isfinite(m[::keep_every]), m[::keep_every], np.nan))
        national_draws.append(nat)

        outcome = {}
        for cname, ch in chambers.items():
            mask = by_chamber[cname]
            if not mask.any():
                continue
            wins_party = np.where(dwin[:, mask], d_party[mask], r_party[mask])  # S x Rc
            totals = {}
            for p in all_parties:
                totals[p] = (wins_party == pcode[p]).sum(axis=1) + ch.seats_not_up.get(p, 0)
            dseats, rseats, d_ctrl, r_ctrl = _control(totals, ch, ch.caucus, S)
            maj = ch.majority
            # histogram of D-bloc seats
            vals, cnts = np.unique(dseats, return_counts=True)
            for v, c in zip(vals.tolist(), cnts.tolist()):
                seat_hist[cname][v] = seat_hist[cname].get(v, 0) + c
            other = ~(d_ctrl | r_ctrl)
            for key, arr in (("D", d_ctrl), ("R", r_ctrl), ("unclear", other)):
                control[cname][key] = control[cname].get(key, 0) + int(arr.sum())
            if ch.alt_caucus is not None:     # e.g. 'if Osborn caucuses with D'
                _, _, ad, ar = _control(totals, ch, ch.alt_caucus, S)
                alt = control_alt.setdefault(cname, {})
                for key, arr in (("D", ad), ("R", ar), ("unclear", ~(ad | ar))):
                    alt[key] = alt.get(key, 0) + int(arr.sum())
            for p, cnt in totals.items():     # seats won by each party label
                if p not in ("D", "R"):
                    party_seats.setdefault(cname, {}).setdefault(p, 0)
                    party_seats[cname][p] += int(cnt.sum()) if hasattr(cnt, "sum") else cnt * S
            outcome[cname] = np.where(d_ctrl, "D", np.where(r_ctrl, "R", "?"))
            # tipping point: the race whose outcome delivers the decisive seat.
            # Order this chamber's races by D margin; the decisive race for D
            # is the k-th best, k = majority - D seats not up for election.
            sub = m[:, mask]
            k_d = maj - sum(n for p, n in ch.seats_not_up.items() if ch.caucus.get(p, p) == "D")
            k_r = maj - sum(n for p, n in ch.seats_not_up.items() if ch.caucus.get(p, p) == "R")
            if ch.tie_breaker == "R":
                k_r -= 1
            if ch.tie_breaker == "D":
                k_d -= 1
            order = np.argsort(-sub, axis=1)          # best-for-D first
            nrc = sub.shape[1]
            idx_c = np.flatnonzero(mask)
            pick = np.where(d_ctrl, np.clip(k_d - 1, 0, nrc - 1),
                            np.clip(nrc - k_r, 0, nrc - 1))
            tp = order[np.arange(S), pick]
            np.add.at(tipping[cname], idx_c[tp], 1)
        if "house" in outcome and "senate" in outcome:
            pairs = np.char.add(outcome["house"].astype(str), outcome["senate"].astype(str))
            vals, cnts = np.unique(pairs, return_counts=True)
            for v, c in zip(vals.tolist(), cnts.tolist()):
                joint[v] = joint.get(v, 0) + c
        done += S

    ms = np.concatenate(margin_samples, axis=0)
    with warnings.catch_warnings():          # fixed races are all-NaN columns
        warnings.simplefilter("ignore", RuntimeWarning)
        qs = np.nanpercentile(ms, QUANTILES, axis=0)
        mean_m = np.nanmean(ms, axis=0)
        sd_m = np.nanstd(ms, axis=0)
    q = qs[[QUANTILES.index(10), QUANTILES.index(50), QUANTILES.index(90)]]
    nat_all = np.concatenate(national_draws)
    out = {
        "n_sims": n_sims,
        "seed": seed,
        "races": {},
        "chambers": {},
        "joint": {k: v / n_sims for k, v in sorted(joint.items())},
        "national_error": {
            "p10": float(np.percentile(nat_all, 10)),
            "p90": float(np.percentile(nat_all, 90)),
        },
    }
    for i, r in enumerate(races):
        out["races"][r.id] = {
            "p_d_side": float(win_sum[i] / n_sims),
            "margin_mean": None if r.fixed else float(mean_m[i]),
            "margin_sd": None if r.fixed else float(sd_m[i]),
            "margin_q": None if r.fixed else {f"q{k:02d}": round(float(qs[j, i]), 2)
                                              for j, k in enumerate(QUANTILES)},
            "margin_p10": None if r.fixed else float(q[0, i]),
            "margin_p50": None if r.fixed else float(q[1, i]),
            "margin_p90": None if r.fixed else float(q[2, i]),
            "tipping": {c: float(tipping[c][i] / n_sims) for c in chambers if by_chamber[c][i]},
        }
    for cname, ch in chambers.items():
        hist = seat_hist[cname]
        if not hist:
            continue
        xs = np.array(sorted(hist))
        ps = np.array([hist[x] for x in xs]) / n_sims
        cdf = np.cumsum(ps)
        def qx(p):
            return int(xs[np.searchsorted(cdf, p)])
        out["chambers"][cname] = {
            "d_seats_mean": float((xs * ps).sum()),
            "d_seats_p10": qx(0.10),
            "d_seats_p50": qx(0.50),
            "d_seats_p90": qx(0.90),
            "hist": {int(x): float(p) for x, p in zip(xs, ps)},
            "p_control": {k: v / n_sims for k, v in control[cname].items()},
            "majority": ch.majority,
        }
        if cname in control_alt:
            out["chambers"][cname]["p_control_alt"] = {
                k: v / n_sims for k, v in control_alt[cname].items()}
        if cname in party_seats:
            out["chambers"][cname]["other_seats_mean"] = {
                p: v / n_sims - ch.seats_not_up.get(p, 0)
                for p, v in party_seats[cname].items()}
    return out
