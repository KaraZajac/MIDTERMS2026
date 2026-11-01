# MIDTERMS2026

**An open, FiveThirtyEight-style forecast of the 2026 U.S. midterm elections:
every House district, every Senate seat and every governorship, simulated
50,000 times with correlated error, frozen in git before the polls open,
and scored against the results after they close.**

FiveThirtyEight went dark in March 2025. Its method didn't have to. This
repository rebuilds the core of it from public, openly licensed data and
publishes everything: the poll ledger, the adjustments, the parameters,
the backtest that set them, and the snapshot that gets graded.

<!-- forecast:start -->
**Forecast as of 2026-11-01** (deluxe version, 50,000 simulations) · generic ballot D+9.1 (two-party)

| | Democrats win | Median D seats | 80% interval |
|---|---:|---:|---:|
| House (218 for control) | **92.8%** | 238 | 220–254 |
| Senate (51; VP breaks ties) | **78.3%** | 52 | 49–55 |
| Governorships (26 of 50) | 84.9% | 27 | 25–30 |

House tipping points: PA-07, AZ-01, VA-02. Senate: Ohio (special), Kansas, Texas.
<!-- forecast:end -->

## What's here

| | |
|---|---:|
| Races modeled (435 House, 35 Senate, 36 governor) | **506** |
| General-election head-to-head polls, in 176 races | **1,640** |
| Generic-ballot polls (Dec 2024 – Oct 2026) | **724** |
| Handicapper ratings (Cook, Sabato, Inside Elections and 7 more) | **2,687** |
| Nominees matched to FEC filings | **856 / 906** |
| Contested districts in the backtest (2018 + 2022) | **739** |

```
midterms/
├── pipeline/       pull (Wikipedia, FEC, The Downballot, DRA blocks, pollster
│                     ratings) → build (races, polls, ratings, finance, lean)
│                     → validate; a stdlib HTML-table parser for Wikipedia
├── model/          poll averaging + adjustments, fundamentals, ratings map,
│                     correlated simulator, the 2018/2022 backtest
└── journal/        the ex-ante scorecard
curated/            hand-maintained control math (seats not up, caucusing)
data/
├── races/          house.csv · senate.csv · governor.csv — nominees, D-side /
│                     R-side, incumbency, fixed outcomes, partisan lean
├── polls/          races.csv · generic.csv — every poll, with page + revision
├── lean/           district and state partisan lean, 2026 lines
├── ratings.csv     every rating Wikipedia compiles, dated
├── averages.csv    outside polling averages (270toWin, DDHQ, RCP, Silver
│                     Bulletin…) — challengers, never inputs
├── finance.csv     FEC individual contributions per nominee
├── backtest.yaml   the fitted House parameters and their out-of-sample test
├── meta.yaml       provenance: URLs, fetch times, sha256s, revision ids
└── forecast/       latest.json + snapshots/ (the timestamped record)
docs/               method (read the caveats), sources, roadmap
tests/              stdlib unittest; `make verify` gates every commit
```

## The model, briefly

Three versions, as 538 published them, each a precision-weighted blend of
independent estimates of a race's two-party margin:

- **Lite** — the polling average; for unpolled races, partisan lean plus
  the national environment (the generic-ballot average), nothing else.
- **Classic** — Lite plus fundamentals: lean, incumbency and fundraising,
  with coefficients **fit on 739 contested districts from the 2018 and 2022
  midterms** (lean ×0.875, incumbency 2.9 pts, 0.8 pts per doubling of the
  money ratio, residual sd 5.6–6.0).
- **Deluxe** (the headline) — Classic plus the Cook / Sabato / Inside
  Elections consensus.

Polls are weighted by recency, sample size and Silver Bulletin's January
2026 pollster ratings, and adjusted for house effects, likely-vs-registered
voter gaps and partisan sponsorship — each adjustment *measured from the
poll set itself* (this cycle: RV polls run 0.5 pts more Democratic than LV
versions of the same poll; D-sponsored polls lean 2.1 pts D, R-sponsored
1.9 pts R). Older state polls are moved along the national trend line.

Each simulation draws one fat-tailed national error, Census-region and
state errors (a district shares its state's error with the Senate and
governor races), a House-wide translation error, and a fat-tailed
race-specific error. Seats roll up into control with the real rules: 218
for the House; 51 for Senate Democrats, 50 for Republicans with Vice
President Vance's tiebreak; an independent who hasn't picked a caucus
(Nebraska's Dan Osborn) counted as neither. Full method and its
limitations: [docs/method.md](docs/method.md).

## The loop

```console
$ make pull        # Wikipedia (127 pages, pinned by revision), FEC, lean, ratings
$ make build       # sources/ -> data/ ; then `make verify`
$ make backtest    # refit the House fundamentals on 2018 + 2022
$ make forecast    # -> data/forecast/latest.json (and this README's block)
$ make snapshot    # freeze a timestamped forecast into the record
$ python3 -m midterms show senate:ME     # one race, every input shown
$ make score       # after Election Day: the scorecard
```

## Honesty guarantees

- **Ex-ante only.** The scored forecast is the last snapshot generated
  before polls open (10:00 UTC, Nov 3). Snapshots are committed, so git
  timestamps them; nothing generated later can enter the record.
- **Every input is traceable.** Each Wikipedia page is pinned by revision
  id; each file by sha256 (`data/meta.yaml`). Rebuilding from those
  revisions reproduces `data/` exactly.
- **No hidden knobs.** Every parameter lives in `midterms/model/params.yaml`
  marked `fit` (estimated in this repo) or `prior` (from the literature,
  documented, and open to being overturned).
- **Challengers on the same races.** The scorecard grades Lite, Classic and
  Deluxe against the raters' consensus, a lean-only baseline and a coin
  flip, on identical resolved races — Brier score, log loss, calls.

## Data sources

Wikipedia's race pages (candidates, polls, ratings, outside averages;
CC BY-SA 4.0) · The Downballot (2024/2020 presidential results by district,
2026 lines) · Dave's Redistricting App block data (2020 results on the nine
redrawn maps) with the Census Bureau's 120th-Congress block equivalency
files · the FEC (fundraising; 2018/2022 official results) · Silver Bulletin
and FiveThirtyEight pollster ratings. Several obvious sources are
deliberately *not* used — Cook (terms forbid scraping), RealClearPolling,
prediction markets, FRED — see [docs/sources.md](docs/sources.md) for why,
and [DATA-RIGHTS.md](DATA-RIGHTS.md) for the layered licensing.

## Setup

Python ≥ 3.11 with PyYAML and NumPy. `pip install -e .` for the `midterms`
entry point (or `python3 -m midterms …`). `make install-hooks` turns on
the pre-commit gate. The first `make pull` downloads ~150 MB (most of it
block-level election data for the redrawn states); later pulls refresh
only what changes.

## Licensing

Code: [MIT](LICENSE). Derived data in `data/`: **CC BY-SA 4.0**, because it
builds on Wikipedia and Dave's Redistricting App, both share-alike — with
the attribution chain in [DATA-RIGHTS.md](DATA-RIGHTS.md).

*An analytical exercise in public forecasting. Not affiliated with
FiveThirtyEight, ABC News, Wikipedia, or any campaign or party; not a
prediction service and not advice. Probabilities are not certainties: a
78% favorite loses about one time in five.*
