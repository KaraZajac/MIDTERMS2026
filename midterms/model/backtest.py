"""`midterms backtest` — fit the House fundamentals on past midterms.

For each contested district in 2018 and 2022 (one Democrat, one
Republican on the November ballot):

    margin  = a_year + b * lean + I * incumbent + m * log2(D money / R money) + e

  margin     two-party House margin, D minus R (FEC official results)
  lean       district presidential margin minus the national one, on the
             lines in use that year (The Downballot): 2018 = 75/25 blend of
             2016 and 2012; 2022 = 2020 only (no 2016 on the 2022 lines)
  incumbent  +1 a Democratic incumbent on the ballot, -1 a Republican
             (the FEC's '(I)' flag), 0 open
  money      individual contributions, FEC final cycle totals (weball):
             includes some post-election money — a small leak, documented
  a_year     absorbs the national environment

The fit gives b, I, m and the residual sd (overall, incumbent-held, open),
which become the forecast's House parameters (`basis: fit`). It also runs
two out-of-sample checks — fit on one midterm, predict the other given the
national environment — and reports Brier scores and a reliability table,
so the district-level error the forecast assumes is the error history shows.
Uncontested and same-party races are excluded (nothing to predict).
"""

from __future__ import annotations

import csv
import io
import math
import zipfile
from collections import defaultdict

import numpy as np
import yaml

from midterms.paths import DATA, SOURCES
from midterms.pipeline.xlsx import sheet_names, xlsx_rows

H = SOURCES / "history"
NATIONAL_PRES = {2016: (65_853_514, 62_984_828), 2012: (65_915_795, 60_933_504),
                 2020: (81_283_501, 74_223_975)}


def _tp(d: float, r: float) -> float:
    return 100.0 * (d - r) / (d + r)


def _nat(year: int) -> float:
    return _tp(*NATIONAL_PRES[year])


def _num(x: str) -> float | None:
    x = (x or "").replace(",", "").replace("%", "").strip()
    try:
        return float(x)
    except ValueError:
        return None


def results(year: int) -> tuple[dict, float]:
    """district -> {'D': (votes, inc), 'R': (votes, inc), 'cands': n}; and
    the national two-party House margin from the same sheet."""
    path = H / f"federalelections{year}.xlsx"
    sheet = next(n for n in sheet_names(path) if "House Results" in n)
    rows = xlsx_rows(path, sheet)
    by = defaultdict(lambda: defaultdict(lambda: {"votes": 0.0, "inc": False, "party": None}))
    for r in rows[1:]:
        if len(r) < 17:
            continue
        st, dist, fec, inc, party = r[1].strip(), r[3].strip(), r[4].strip(), r[5].strip(), r[10].strip()
        if not st or not dist or not fec or fec.lower() == "n/a" or not dist[:2].isdigit():
            continue
        v = _num(r[15])
        if v is None:
            continue
        label = f"{st}-{'AL' if dist[:2] == '00' else dist[:2]}"
        c = by[label][fec]
        c["votes"] += v              # fusion: one candidate, several lines
        c["inc"] = c["inc"] or inc.startswith("(I)")
        if party in ("D", "R", "DFL", "DEM", "REP") and c["party"] is None:
            c["party"] = "D" if party in ("D", "DFL", "DEM") else "R"
        c.setdefault("fec", fec)
    out = {}
    nd = nr = 0.0
    for label, cands in by.items():
        ds = [c for c in cands.values() if c["party"] == "D"]
        rs = [c for c in cands.values() if c["party"] == "R"]
        for c in ds:
            nd += c["votes"]
        for c in rs:
            nr += c["votes"]
        if len(ds) == 1 and len(rs) == 1:
            out[label] = {"D": ds[0], "R": rs[0]}
    return out, _tp(nd, nr)


def lean_2018() -> dict:
    out = {}
    with open(H / "downballot-pres-2018-lines.csv", newline="") as f:
        for row in csv.reader(f):
            if not row or "-" not in row[0] or len(row[0]) > 6:
                continue
            c16, t16, o12, r12 = (_num(x) for x in row[3:7])
            if None in (c16, t16, o12, r12):
                continue
            rel16 = _tp(c16, t16) - _nat(2016)
            rel12 = _tp(o12, r12) - _nat(2012)
            out[row[0]] = 0.75 * rel16 + 0.25 * rel12
    return out


def lean_2022() -> dict:
    out = {}
    with open(H / "downballot-pres20-2022-lines.csv", newline="") as f:
        for row in csv.reader(f):
            if not row or "-" not in row[0] or len(row[0]) > 6:
                continue
            b, t = _num(row[3]), _num(row[4])
            if b is None or t is None:
                continue
            out[row[0]] = _tp(b, t) - _nat(2020)
    return out


def money(year: int) -> dict:
    yy = str(year)[2:]
    with zipfile.ZipFile(H / f"weball{yy}.zip") as z:
        name = next(n for n in z.namelist() if n.lower().endswith(".txt"))
        text = io.TextIOWrapper(z.open(name), encoding="latin-1").read()
    out = {}
    for line in text.splitlines():
        p = line.split("|")
        if len(p) > 17:
            try:
                out[p[0]] = float(p[17] or 0)      # TTL_INDIV_CONTRIB
            except ValueError:
                pass
    return out


def dataset() -> list[dict]:
    rows = []
    for year, leanfn in ((2018, lean_2018), (2022, lean_2022)):
        res, nat = results(year)
        lean = leanfn()
        cash = money(year)
        for label, rr in res.items():
            if label not in lean:
                continue
            d, r = rr["D"], rr["R"]
            if d["votes"] <= 0 or r["votes"] <= 0:
                continue
            if d["inc"] and r["inc"]:
                continue                     # member-vs-member
            inc = 1 if d["inc"] else (-1 if r["inc"] else 0)
            md, mr = cash.get(d["fec"], 0.0), cash.get(r["fec"], 0.0)
            rows.append({"year": year, "label": label, "margin": _tp(d["votes"], r["votes"]),
                         "lean": lean[label], "inc": inc,
                         "money": math.log2((md + 5000) / (mr + 5000)), "national": nat})
    return rows


def fit(rows: list[dict], years: list[int], cap: float = 4.0) -> dict:
    X, y = [], []
    for r in rows:
        if r["year"] not in years:
            continue
        X.append([1.0 if r["year"] == yr else 0.0 for yr in years]
                 + [r["lean"], r["inc"], r["money"]])
        y.append(r["margin"])
    X, y = np.array(X), np.array(y)
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    k = len(years)
    inc = X[:, k + 1]
    return {"a": {yr: float(beta[i]) for i, yr in enumerate(years)},
            "lean_coef": float(beta[k]), "incumbency": float(beta[k + 1]),
            "money_coef": float(beta[k + 2]),
            "sd": float(resid.std(ddof=X.shape[1])),
            "sd_incumbent": float(resid[inc != 0].std()), "sd_open": float(resid[inc == 0].std()),
            "n": int(len(y))}


def _phi(z: float) -> float:
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def oos(rows: list[dict], train: int, test: int) -> dict:
    """Fit on `train`; predict `test` given its actual national environment
    (the offset a_year - national estimated on the training year)."""
    f = fit(rows, [train])
    offset = f["a"][train] - next(r["national"] for r in rows if r["year"] == train)
    nat_test = next(r["national"] for r in rows if r["year"] == test)
    briers, losses, bins = [], [], defaultdict(lambda: [0, 0, 0.0])
    errs = []
    for r in rows:
        if r["year"] != test:
            continue
        mu = (nat_test + offset + f["lean_coef"] * r["lean"] + f["incumbency"] * r["inc"]
              + max(-4.0, min(4.0, f["money_coef"] * r["money"])))
        sd = f["sd_incumbent"] if r["inc"] else f["sd_open"]
        p = _phi(mu / sd)
        won = 1.0 if r["margin"] > 0 else 0.0
        briers.append((p - won) ** 2)
        pc = min(max(p, 1e-4), 1 - 1e-4)
        losses.append(-(won * math.log(pc) + (1 - won) * math.log(1 - pc)))
        errs.append(r["margin"] - mu)
        b = min(9, int(p * 10))
        bins[b][0] += 1
        bins[b][1] += won
        bins[b][2] += p
    e = np.array(errs)
    return {"train": train, "test": test, "n": len(briers),
            "brier": round(float(np.mean(briers)), 4),
            "log_loss": round(float(np.mean(losses)), 4),
            "rmse": round(float(np.sqrt((e ** 2).mean())), 2),
            "mean_error": round(float(e.mean()), 2),
            "reliability": [{"bin": f"{b / 10:.1f}-{(b + 1) / 10:.1f}", "n": v[0],
                             "forecast": round(v[2] / v[0], 3), "observed": round(v[1] / v[0], 3)}
                            for b, v in sorted(bins.items())]}


def main() -> dict:
    rows = dataset()
    both = fit(rows, [2018, 2022])
    nat = {yr: next(r["national"] for r in rows if r["year"] == yr) for yr in (2018, 2022)}
    offset = {yr: both["a"][yr] - nat[yr] for yr in (2018, 2022)}
    out = {
        "generated_by": "python3 -m midterms backtest",
        "sample": {yr: sum(1 for r in rows if r["year"] == yr) for yr in (2018, 2022)},
        "national_house_margin": {yr: round(v, 2) for yr, v in nat.items()},
        "fit": {"lean_coef": round(both["lean_coef"], 3), "incumbency": round(both["incumbency"], 2),
                "money_coef": round(both["money_coef"], 3), "sd": round(both["sd"], 2),
                "sd_incumbent": round(both["sd_incumbent"], 2), "sd_open": round(both["sd_open"], 2),
                "year_intercepts": {yr: round(v, 2) for yr, v in both["a"].items()},
                "intercept_minus_national": {yr: round(v, 2) for yr, v in offset.items()},
                "n": both["n"]},
        "per_year": {yr: {k: (round(v, 3) if isinstance(v, float) else v)
                          for k, v in fit(rows, [yr]).items() if k != "a"} for yr in (2018, 2022)},
        "out_of_sample": [oos(rows, 2018, 2022), oos(rows, 2022, 2018)],
    }
    from midterms.pipeline import fetch
    files = fetch.load_manifest().get("files", {})
    out["sources"] = {k: {"url": v["url"], "sha256": v["sha256"]} for k, v in sorted(files.items())
                      if k.startswith(("fec-results-", "fec-weball", "downballot-pres20-2022",
                                       "downballot-pres-2018"))}
    (DATA / "backtest.yaml").write_text(yaml.safe_dump(out, sort_keys=False))
    f = out["fit"]
    print(f"backtest: {f['n']} contested districts (2018 {out['sample'][2018]}, 2022 {out['sample'][2022]})")
    print(f"  lean coef {f['lean_coef']}  incumbency {f['incumbency']} pts  "
          f"money {f['money_coef']} pts/doubling  residual sd {f['sd']} "
          f"(incumbent {f['sd_incumbent']}, open {f['sd_open']})")
    print(f"  year intercept - national House margin: {f['intercept_minus_national']}")
    for o in out["out_of_sample"]:
        print(f"  fit {o['train']} -> predict {o['test']}: n={o['n']} Brier {o['brier']} "
              f"RMSE {o['rmse']} mean err {o['mean_error']}")
    return out
