"""Election night: the frozen forecast, conditioned on the races called so far.

The forecast of record is a joint distribution over every race. Each call
on the night is an observation, and this module works out what the frozen
model implies for everything still uncalled, given the calls and nothing
else. Partial vote counts are deliberately left out: which counties, and
which kinds of ballots, report first differs by state and swings early
margins in ways the model knows nothing about.

The model (simulate.py) writes a race's margin as

    margin_r = mu_r + A_r·θ + sd_r·ε_r

where θ = (national, four regions, fifty states, a House-wide shift) are
the errors races share and ε_r is the race's own error (unit-variance
Student t, ν = 6). Given θ the races are independent, so calls inform the
rest of the map only through θ:

    p(θ | calls) ∝ p(θ) · Π_called P(y_r | θ),
    P(D-side wins r | θ) = T_ν( (mu_r + A_r·θ) / (sd_r·√((ν−2)/ν)) )

θ is drawn by importance sampling from a multivariate-t proposal fitted
to that posterior (its mode and curvature by Newton's method, then one
moment-matching refit), each draw weighted exactly by
p(θ)·Π P(y_r|θ) / q(θ); the uncalled races are simulated from each draw.
`ess`, the effective number of draws ((Σw)²/Σw²), says how much each
estimate rests on. With no calls this reproduces the pre-election
forecast (tests/test_live.py).

Calls only ever say who won, not by how much, and races still out are
treated as uninformative, so the update is conservative: it never reads
more into the night than the calls themselves.

All randomness comes from PCG64's raw bit stream, which numpy keeps
identical across versions (its distribution samplers carry no such
promise), so the web server's copy and the Actions copy agree exactly for
the same calls.
"""

from __future__ import annotations

import math

import numpy as np

from midterms.model.simulate import REGIONS, STATE_REGION

NU_NAT_PROPOSAL = 4      # the national error's proposal: t4 (even ν: chi-square from uniforms)
NAT_INFLATE = 1.1        # its scale over the fitted curvature
CHUNK = 4000


# --------------------------------------------------------------- randomness

def _uniforms(seed: int, stream: int, n: int) -> np.ndarray:
    bits = np.random.PCG64(np.random.SeedSequence([seed, stream])).random_raw(n)
    return ((bits >> np.uint64(11)).astype(np.float64) + 0.5) * (1.0 / 9007199254740992.0)


def _normals(seed: int, stream: int, shape: tuple) -> np.ndarray:
    n = int(np.prod(shape))
    u = _uniforms(seed, stream, 2 * ((n + 1) // 2)).reshape(2, -1)
    r = np.sqrt(-2.0 * np.log(u[0]))
    z = np.concatenate([r * np.cos(2 * np.pi * u[1]), r * np.sin(2 * np.pi * u[1])])[:n]
    return z.reshape(shape)


def _chi2_even(seed: int, stream: int, nu: int, n: int) -> np.ndarray:
    """Chi-square with an even ν: twice a sum of ν/2 unit exponentials."""
    u = _uniforms(seed, stream, n * (nu // 2)).reshape(nu // 2, n)
    return -2.0 * np.log(u).sum(axis=0)


def _t_unit(seed: int, stream: int, nu: int, shape: tuple) -> np.ndarray:
    """Unit-variance Student t draws (ν even)."""
    z = _normals(seed, 2 * stream, shape)
    w = _chi2_even(seed, 2 * stream + 1, nu, int(np.prod(shape))).reshape(shape)
    return z / np.sqrt(w / nu) * math.sqrt((nu - 2.0) / nu)


# ------------------------------------------------------------ t distribution

def t_cdf(z: np.ndarray, nu: int) -> np.ndarray:
    """Student t CDF for integer ν (Abramowitz & Stegun 26.7.3–4)."""
    z = np.asarray(z, dtype=np.float64)
    x2 = nu / (nu + z * z)                      # cos²θ, θ = atan(z/√ν)
    if nu % 2 == 0:
        s, term = np.ones_like(z), np.ones_like(z)
        for j in range(1, nu // 2):
            term = term * x2 * (2 * j - 1) / (2 * j)
            s = s + term
        a = (z / np.sqrt(nu + z * z)) * s
    else:
        th = np.arctan(z / math.sqrt(nu))
        if nu == 1:
            a = 2 * th / math.pi
        else:
            s, term = np.ones_like(z), np.ones_like(z)
            for j in range(1, (nu - 1) // 2):
                term = term * x2 * (2 * j) / (2 * j + 1)
                s = s + term
            a = 2 / math.pi * (th + np.sin(th) * np.cos(th) * s)
    return np.clip(0.5 + 0.5 * a, 1e-300, 1.0)


def t_logpdf(z: np.ndarray, nu: float) -> np.ndarray:
    c = math.lgamma((nu + 1) / 2) - math.lgamma(nu / 2) - 0.5 * math.log(nu * math.pi)
    return c - (nu + 1) / 2 * np.log1p(z * z / nu)


# ------------------------------------------------------------------- engine

class Engine:
    """The frozen forecast's shared-error structure, ready to condition."""

    def __init__(self, sim: dict, version: str = "deluxe"):
        sh = sim["shared"]
        self.version = version
        self.races = sim["races"]
        self.ids = [r["id"] for r in self.races]
        self.index = {rid: i for i, rid in enumerate(self.ids)}
        self.chambers = sim["chambers"]
        R = len(self.races)
        self.states = sorted({r["state"] for r in self.races})
        self.regions = sorted(REGIONS)
        S, G = len(self.states), len(self.regions)
        self.D = 1 + G + S + 1
        self.nu_nat, self.nu_race = float(sh["nu_national"]), int(sh["nu_race"])
        if self.nu_race != sh["nu_race"]:
            raise ValueError("nu_race must be an integer")
        self.c_nat = sh["sd_national"] * math.sqrt((self.nu_nat - 2) / self.nu_nat)
        sd_house = (sh.get("sd_chamber") or {}).get("house", 0.0)
        self.prior_sd = np.array([np.nan] + [sh["sd_region"]] * G + [sh["sd_state"]] * S
                                 + [sd_house or 1.0])
        A = np.zeros((R, self.D))
        self.mu = np.zeros(R)
        self.sd = np.ones(R)
        self.fixed = np.zeros(R, dtype=np.int8)          # +1 D-side, -1 R-side certain
        for i, r in enumerate(self.races):
            A[i, 0] = r.get("lam", 1.0)
            A[i, 1 + self.regions.index(STATE_REGION.get(r["state"], "South"))] = 1.0
            A[i, 1 + G + self.states.index(r["state"])] = 1.0
            if r["chamber"] == "house" and sd_house:
                A[i, -1] = 1.0
            if r.get("fixed"):
                self.fixed[i] = 1 if r["fixed"] == (r.get("d_side") or "D") else -1
            else:
                self.mu[i] = r["mu"][version]
                self.sd[i] = max(r["sd"][version], sh.get("floor_idio", 0.5))
        if not sd_house:
            A[:, -1] = 0.0
        self.A = A
        self.scale = self.sd * math.sqrt((self.nu_race - 2.0) / self.nu_race)
        self.chamber_of = [r["chamber"] for r in self.races]
        parties = {r.get("d_side") or "D" for r in self.races} | {r.get("r_side") or "R" for r in self.races}
        for ch in self.chambers.values():
            parties |= set((ch.get("seats_not_up") or {}))
        parties.add("other")
        self.parties = sorted(parties)
        pc = {p: k for k, p in enumerate(self.parties)}
        self.pcode = pc
        self.d_party = np.array([pc[r.get("d_side") or "D"] for r in self.races])
        self.r_party = np.array([pc[r.get("r_side") or "R"] for r in self.races])

    # --- the posterior over shared errors -------------------------------

    def _log_prior(self, th: np.ndarray) -> np.ndarray:
        u = th[..., 0] / self.c_nat
        lp = -(self.nu_nat + 1) / 2 * np.log1p(u * u / self.nu_nat)
        rest = th[..., 1:] / self.prior_sd[1:]
        return lp - 0.5 * (rest * rest).sum(axis=-1)

    def _obs(self, calls: dict[str, str]):
        idx, y = [], []
        for rid, side in calls.items():
            i = self.index.get(rid)
            if i is None or self.fixed[i] or side not in ("D", "R"):
                continue
            idx.append(i)
            y.append(1.0 if side == "D" else -1.0)
        return np.array(idx, dtype=int), np.array(y)

    def _log_lik(self, th: np.ndarray, idx: np.ndarray, y: np.ndarray) -> np.ndarray:
        if not len(idx):
            return np.zeros(th.shape[:-1])
        z = y * (self.mu[idx] + th @ self.A[idx].T) / self.scale[idx]
        return np.log(t_cdf(z, self.nu_race)).sum(axis=-1)

    def mode(self, idx: np.ndarray, y: np.ndarray, iters: int = 60):
        """Posterior mode of θ and the curvature there (Newton, with a line
        search; non-concave pieces of the heavy-tailed terms are dropped
        from the curvature so it stays negative definite)."""
        th = np.zeros(self.D)
        nu, c = self.nu_nat, self.c_nat
        Ac, s, mu = self.A[idx], self.scale[idx], self.mu[idx]

        def f(t):
            return float(self._log_prior(t) + self._log_lik(t, idx, y))

        def grad_hess(t):
            g = np.zeros(self.D)
            h = np.zeros((self.D, self.D))
            u = t[0] / c
            g[0] = -(nu + 1) * u / (c * (nu + u * u))
            h[0, 0] = -(nu + 1) / (c * c) * max(nu - u * u, 0.25 * nu) / (nu + u * u) ** 2
            g[1:] = -t[1:] / self.prior_sd[1:] ** 2
            h[np.arange(1, self.D), np.arange(1, self.D)] = -1.0 / self.prior_sd[1:] ** 2
            if len(idx):
                z = y * (mu + Ac @ t) / s
                F = t_cdf(z, self.nu_race)
                pdf = np.exp(t_logpdf(z, self.nu_race))
                g1 = pdf / F
                g2 = g1 * (-(self.nu_race + 1) * z / (self.nu_race + z * z) - g1)
                g += Ac.T @ (y * g1 / s)
                h += (Ac.T * (np.minimum(g2, 0.0) / s ** 2)) @ Ac
            return g, h

        fx = f(th)
        for _ in range(iters):
            g, h = grad_hess(th)
            step = np.linalg.solve(-h, g)
            t, ok = 1.0, False
            for _ in range(30):
                cand = th + t * step
                fc = f(cand)
                if fc >= fx - 1e-12:
                    ok = True
                    break
                t *= 0.5
            if not ok:
                break
            moved = np.abs(cand - th).max()
            th, fx = cand, fc
            if moved < 1e-7:
                break
        _, h = grad_hess(th)
        return th, -h

    def _draw(self, loc, cov, seed, stream, n):
        """Proposal draws and their log density: the national error from a
        t with ν = 4 (heavier-tailed than its t5 prior, so no weight can
        blow up in the tails), every other shared error from its Gaussian
        conditional on it — the Laplace fit's correlations, kept."""
        s00 = cov[0, 0]
        b = cov[1:, 0] / s00
        cond = cov[1:, 1:] - np.outer(b, cov[1:, 0])
        L = np.linalg.cholesky(cond + 1e-12 * np.eye(self.D - 1))
        scale = math.sqrt(s00 * (NU_NAT_PROPOSAL - 2) / NU_NAT_PROPOSAL) * NAT_INFLATE
        t_nat = (_normals(seed, 2 * stream, (n,))
                 / np.sqrt(_chi2_even(seed, 2 * stream + 1, NU_NAT_PROPOSAL, n) / NU_NAT_PROPOSAL))
        nat = loc[0] + scale * t_nat
        z = _normals(seed, 2 * stream + 100, (n, self.D - 1))
        rest = loc[1:] + np.outer(nat - loc[0], b) + z @ L.T
        th = np.column_stack([nat, rest])
        log_q = (t_logpdf(t_nat, NU_NAT_PROPOSAL) - math.log(scale)
                 - 0.5 * (z * z).sum(axis=1) - np.log(np.diag(L)).sum())
        return th, log_q

    def _weights(self, th, log_q, idx, y):
        lt = np.concatenate([self._log_prior(th[a:a + CHUNK]) + self._log_lik(th[a:a + CHUNK], idx, y)
                             for a in range(0, len(th), CHUNK)])
        lw = lt - log_q
        w = np.exp(lw - lw.max())
        return w / w.sum()

    def posterior(self, calls: dict[str, str], n: int = 20000, seed: int = 20261103):
        """Weighted draws of θ given the calls: (θ, w, ess)."""
        idx, y = self._obs(calls)
        loc, prec = self.mode(idx, y)
        cov = np.linalg.inv(prec)
        th, lq = self._draw(loc, cov, seed, 1, n)
        w = self._weights(th, lq, idx, y)
        ess = 1.0 / (w * w).sum()
        # one refit to the weighted draws' own mean and spread
        m2 = w @ th
        d = th - m2
        cov2 = (d.T * w) @ d + 1e-9 * np.eye(self.D)
        try:
            th2, lq2 = self._draw(m2, cov2, seed, 2, n)
            w2 = self._weights(th2, lq2, idx, y)
            ess2 = 1.0 / (w2 * w2).sum()
            if ess2 > ess:
                th, w, ess = th2, w2, ess2
        except np.linalg.LinAlgError:
            pass
        return th, w, float(ess)

    # --- outcomes -------------------------------------------------------

    def run(self, calls: dict[str, str], n: int = 20000, seed: int = 20261103) -> dict:
        """Chamber control and seats, and each race's chance, given calls
        (race id -> 'D' | 'R' | 'other')."""
        th, w, ess = self.posterior(calls, n, seed)
        R = len(self.races)
        called = np.zeros(R, dtype=np.int8)                       # +1 D, -1 R, 2 other
        for rid, side in calls.items():
            i = self.index.get(rid)
            if i is not None:
                called[i] = {"D": 1, "R": -1, "other": 2}.get(side, 0)
        free = (called == 0) & (self.fixed == 0)
        p_d = np.where(self.fixed == 1, 1.0, 0.0)
        p_d = np.where(called == 1, 1.0, np.where(np.isin(called, (-1, 2)), 0.0, p_d))
        rb = np.zeros(R)
        tallies = {c: {"D": 0.0, "R": 0.0, "unclear": 0.0, "alt": {"D": 0.0, "R": 0.0, "unclear": 0.0},
                       "hist": {}} for c in self.chambers}
        masks = {c: np.array([ch == c for ch in self.chamber_of]) for c in self.chambers}
        other = self.pcode["other"]
        for a in range(0, n, CHUNK):
            t, wc = th[a:a + CHUNK], w[a:a + CHUNK]
            S = len(t)
            base = self.mu + t @ self.A.T                          # S x R
            rb += wc @ t_cdf(base / self.scale, self.nu_race)
            eps = _t_unit(seed, 10 + a // CHUNK, self.nu_race, (S, R))
            dwin = (base + eps * self.sd) > 0
            dwin = np.where(self.fixed == 1, True, np.where(self.fixed == -1, False, dwin))
            dwin = np.where(called == 1, True, np.where(np.isin(called, (-1, 2)), False, dwin))
            party = np.where(dwin, self.d_party, self.r_party)
            party = np.where(called == 2, other, party)
            for cname, ch in self.chambers.items():
                m = masks[cname]
                if not m.any():
                    continue
                totals = {p: (party[:, m] == k).sum(axis=1) + (ch.get("seats_not_up") or {}).get(p, 0)
                          for p, k in self.pcode.items()}
                dseats, dc, rc = _control(totals, ch, ch.get("caucus") or {})
                tal = tallies[cname]
                tal["D"] += float(wc[dc].sum())
                tal["R"] += float(wc[rc].sum())
                tal["unclear"] += float(wc[~(dc | rc)].sum())
                if ch.get("alt_caucus"):
                    _, ad, ar = _control(totals, ch, ch["alt_caucus"])
                    tal["alt"]["D"] += float(wc[ad].sum())
                    tal["alt"]["R"] += float(wc[ar].sum())
                    tal["alt"]["unclear"] += float(wc[~(ad | ar)].sum())
                for v in np.unique(dseats):
                    tal["hist"][int(v)] = tal["hist"].get(int(v), 0.0) + float(wc[dseats == v].sum())
        p_d = np.where(free, rb, p_d)
        out = {"ess": round(ess), "draws": n, "chambers": {}, "races": {}}
        for i, rid in enumerate(self.ids):
            out["races"][rid] = float(p_d[i])
        for cname, tal in tallies.items():
            xs = sorted(tal["hist"])
            ps = np.array([tal["hist"][x] for x in xs])
            cdf = np.cumsum(ps)

            def q(p):
                return int(xs[min(int(np.searchsorted(cdf, p - 1e-12)), len(xs) - 1)])

            ch = {"p_control": {k: tal[k] for k in ("D", "R", "unclear")},
                  "seats": {"mean": float(np.dot(xs, ps)), "p10": q(0.1), "p50": q(0.5), "p90": q(0.9)},
                  "hist": {int(x): float(p) for x, p in zip(xs, ps)}}
            if self.chambers[cname].get("alt_caucus"):
                ch["p_control_alt"] = dict(tal["alt"])
            out["chambers"][cname] = ch
        return out


def _control(totals: dict, ch: dict, caucus: dict):
    """D-bloc seats and who controls, per draw (simulate._control's rules)."""
    blocs: dict = {}
    for p, cnt in totals.items():
        b = caucus.get(p, p)
        blocs[b] = blocs.get(b, 0) + cnt
    zero = np.zeros_like(next(iter(totals.values())))
    d = blocs.get("D", zero) + zero
    r = blocs.get("R", zero) + zero
    maj = ch["majority"]
    dc, rc = d >= maj, r >= maj
    if ch.get("tie_breaker"):
        tie = (d == maj - 1) & (r == maj - 1)
        if ch["tie_breaker"] == "D":
            dc = dc | tie
        else:
            rc = rc | tie
    return d, dc, rc


# ------------------------------------------------------------- self-check

# Rough poll-closing times (hours after midnight, Eastern, Nov 3) for the
# self-check's simulated nights only — not a display table.
_CLOSE = {**{s: 19.0 for s in "GA IN KY SC VA VT FL".split()},
          **{s: 19.5 for s in "NC OH WV".split()},
          **{s: 20.0 for s in "AL CT DE IL KS ME MD MA MI MS MO NH NJ OK PA RI SD TN TX".split()},
          "AR": 20.5,
          **{s: 21.0 for s in "AZ CO IA LA MN NE NM NY ND WI WY".split()},
          **{s: 22.0 for s in "MT NV UT ID".split()},
          **{s: 23.0 for s in "CA OR WA".split()}, "HI": 24.0, "AK": 25.0}
CHECKPOINTS = [19.5, 20.5, 21.5, 22.5, 23.5, 25.0, 28.0, 48.0]


def _called(margin: float, hours_since_close: float) -> bool:
    """A stylized decision desk: lopsided races at poll close, a 4-point
    race about two hours in, anything inside a point only the next day."""
    if hours_since_close < 0:
        return False
    need = 0.5 if hours_since_close > 20 else max(1.0, 12.0 - 4.0 * hours_since_close)
    return abs(margin) > need


def _truth_control(eng: "Engine", dwin: np.ndarray) -> dict:
    """Who controls each chamber when every race goes as `dwin` says."""
    party = np.where(dwin, eng.d_party, eng.r_party)[None, :]
    out = {}
    for cname, ch in eng.chambers.items():
        m = np.array([c == cname for c in eng.chamber_of])
        totals = {p: (party[:, m] == k).sum(axis=1) + (ch.get("seats_not_up") or {}).get(p, 0)
                  for p, k in eng.pcode.items()}
        _, dc, _ = _control(totals, ch, ch.get("caucus") or {})
        out[cname] = float(dc[0])
    return out


def selfcheck(sim: dict, nights: int = 100, draws: int = 4000, seed: int = 7,
              checkpoints: list[float] = CHECKPOINTS) -> dict:
    """Simulation-based calibration: draw `nights` true outcomes from the
    forecast itself, reveal them as calls the way a decision desk would
    (by poll closing, lopsided races first), and score the live control
    probabilities at each checkpoint against what actually happened —
    next to the pre-election probabilities on the same nights, so the
    luck of the sample cancels: `bias` is the mean of (outcome − p)."""
    eng = Engine(sim)
    rng = np.random.default_rng(seed)
    R = len(eng.ids)
    close = np.array([_CLOSE.get(r["state"], 21.0) for r in eng.races])
    pre = {c: sim["reference"][eng.version][c]["D"] for c in eng.chambers}
    rows = {cp: {c: [] for c in eng.chambers} for cp in checkpoints}
    ess = {cp: [] for cp in checkpoints}
    ncalls = {cp: [] for cp in checkpoints}
    outcomes = {c: [] for c in eng.chambers}
    for k in range(nights):
        th = np.zeros(eng.D)
        th[0] = eng.c_nat * rng.standard_t(eng.nu_nat)
        th[1:] = rng.standard_normal(eng.D - 1) * eng.prior_sd[1:]
        if not eng.A[:, -1].any():
            th[-1] = 0.0
        eps = rng.standard_t(eng.nu_race, R) * math.sqrt((eng.nu_race - 2) / eng.nu_race)
        m = eng.mu + eng.A @ th + eps * eng.sd
        m = np.where(eng.fixed == 1, 99.0, np.where(eng.fixed == -1, -99.0, m))
        side = np.where(m > 0, "D", "R")
        truth = _truth_control(eng, m > 0)
        for c in eng.chambers:
            outcomes[c].append(truth[c])
        for cp in checkpoints:
            calls = {rid: side[i] for i, rid in enumerate(eng.ids)
                     if not eng.fixed[i] and _called(m[i], cp - close[i])}
            out = eng.run(calls, n=draws, seed=1000 + k)
            ess[cp].append(out["ess"])
            ncalls[cp].append(len(calls))
            for c in eng.chambers:
                rows[cp][c].append((out["chambers"][c]["p_control"]["D"], truth[c]))
    report = {"nights": nights, "draws": draws,
              "pre": {c: {"p": round(pre[c], 4), "observed": round(float(np.mean(outcomes[c])), 4),
                          "brier": round(float(np.mean((pre[c] - np.array(outcomes[c])) ** 2)), 4)}
                      for c in eng.chambers},
              "checkpoints": []}
    pooled = []
    for cp in checkpoints:
        row = {"hour_et": cp, "calls": round(float(np.mean(ncalls[cp]))),
               "ess_median": round(float(np.median(ess[cp]))), "ess_min": int(min(ess[cp]))}
        for c in eng.chambers:
            p, o = np.array(rows[cp][c]).T
            row[c] = {"brier": round(float(np.mean((p - o) ** 2)), 4),
                      "bias": round(float(np.mean(o - p)), 4),
                      "bias_pre": round(float(np.mean(o - pre[c])), 4)}
            pooled += list(zip(p, o))
        report["checkpoints"].append(row)
    p, o = np.array(pooled).T
    bins = []
    for lo in np.arange(0, 1, 0.1):
        sel = (p >= lo) & (p < lo + 0.1 if lo < 0.9 else p <= 1.0)
        if sel.sum():
            bins.append({"bin": f"{lo:.1f}-{lo + 0.1:.1f}", "n": int(sel.sum()),
                         "forecast": round(float(p[sel].mean()), 3), "observed": round(float(o[sel].mean()), 3)})
    report["calibration"] = bins
    return report
