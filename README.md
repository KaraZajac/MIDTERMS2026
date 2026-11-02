# MIDTERMS2026

[![validate](https://github.com/KaraZajac/MIDTERMS2026/actions/workflows/ci.yml/badge.svg)](https://github.com/KaraZajac/MIDTERMS2026/actions/workflows/ci.yml)
[![refresh](https://github.com/KaraZajac/MIDTERMS2026/actions/workflows/refresh.yml/badge.svg)](https://github.com/KaraZajac/MIDTERMS2026/actions/workflows/refresh.yml)
[![code: MIT](https://img.shields.io/badge/code-MIT-blue.svg)](LICENSE)
[![data: CC BY-SA 4.0](https://img.shields.io/badge/data-CC%20BY--SA%204.0-lightgrey.svg)](DATA-RIGHTS.md)

**An open, FiveThirtyEight-style forecast of the 2026 U.S. midterm elections:
every House district, every Senate seat and every governorship, simulated
50,000 times with correlated error, frozen in git before the polls open,
and scored against the results after they close.**

FiveThirtyEight went dark in March 2025. Its method didn't have to. This
repository rebuilds the core of it from public, openly licensed data and
publishes everything: the poll ledger, the adjustments, the parameters,
the backtests that set them, and the snapshot that gets graded.

**Live site: [midterms.karazajac.io](https://midterms.karazajac.io)** — every
race with its polls and inputs, chamber odds under each model version, and
an in-browser [what-if simulator](https://midterms.karazajac.io/simulator/)
(shift the national environment, call races, watch control move).

<!-- forecast:start -->
**Forecast as of 2026-11-02** (deluxe version, 50,000 simulations) · generic ballot D+9.1 (two-party)

| | Democrats win | Median D seats | 80% interval |
|---|---:|---:|---:|
| House (218 for control) | **94.9%** | 237 | 222–251 |
| Senate (51; VP breaks ties) | **78.1%** | 53 | 49–55 |
| Governorships (26 of 50) | 83.0% | 28 | 25–31 |

House tipping points: PA-07, NC-11, FL-25. Senate: Ohio (special), Texas, Kansas.
<!-- forecast:end -->

## What's here

<!-- counts:start -->
| | |
|---|---:|
| Races modeled (435 House, 35 Senate, 36 governor) | **506** |
| General-election head-to-head polls, in 179 races (39 of them from VoteHub) | **1,810** |
| Generic-ballot polls (Dec 2024 – latest) | **728** |
| Handicapper ratings (Cook, Sabato, Inside Elections and more) | **2,708** |
| Nominees matched to FEC filings | **871 / 906** |
| Contested House districts in the fundamentals backtest (2018 + 2022) | **739** |
| Senate and governor races in the polling backtest (2014–2025) | **323** |
| Latest poll in the data | **2026-11-02** |
<!-- counts:end -->

```
midterms/
├── pipeline/       pull (Wikipedia, VoteHub, FEC, The Downballot, DRA blocks)
│                     → build (races, polls, ratings, finance, lean) → validate;
│                     the refresh cadence; election-night results (civicAPI)
├── model/          poll averaging + adjustments, fundamentals, ratings map,
│                     correlated simulator, the House and statewide backtests,
│                     the forecast conditioned on election-night calls
└── journal/        the ex-ante scorecard
sim/simulator.mjs   the same simulator for the browser (CI-checked against Python)
site/               the Astro site at midterms.karazajac.io (builds from data/site/)
curated/            hand-maintained control math (seats not up, caucusing)
data/
├── races/          house.csv · senate.csv · governor.csv — nominees, D-side /
│                     R-side, incumbency, fixed outcomes, partisan lean
├── polls/          races.csv · generic.csv — every poll, with its source
│                     (Wikipedia page + revision, or a VoteHub id)
├── lean/           district and state partisan lean, 2026 lines
├── pollster_ratings/  the pollster ratings behind the poll weights, pinned
├── ratings.csv     every rating Wikipedia compiles, dated
├── averages.csv    outside polling averages (270toWin, DDHQ, RCP, Silver
│                     Bulletin…) — challengers, never inputs
├── finance.csv     FEC individual contributions per nominee
├── backtest.yaml   the fitted House parameters and their out-of-sample test
├── backtest_statewide.yaml   323 past races: how accurate this polling average is
├── meta.yaml       provenance: URLs, fetch times, sha256s, revision ids
├── forecast/       latest.json + snapshots/ (the timestamped record)
└── site/           the website's data contract (docs/site-data.md)
docs/               method (read the caveats), sources, site data, roadmap
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
The uncertainty of each average is fit too: a small error every poll of a
race shares plus a large one each poll carries alone, which averages away
as polls accumulate — so a race with two polls is far less certain than one
with thirty.

Each simulation draws one fat-tailed national error, Census-region and
state errors (a district shares its state's error with the Senate and
governor races), a House-wide translation error, and a fat-tailed
race-specific error. Seats roll up into control with the real rules: 218
for the House; 51 for Senate Democrats, 50 for Republicans with Vice
President Vance's tiebreak; an independent who hasn't picked a caucus
(Nebraska's Dan Osborn) counted as neither. Full method and its
limitations: [docs/method.md](docs/method.md).

## Accuracy

Two backtests set the parameters and are re-run by `make backtest`:

- **House fundamentals** — fit on 739 contested districts (2018, 2022);
  out of sample (fit one midterm, predict the other) Brier 0.041. The fit
  also exposed that the national-vote → district translation shifts by
  ±2 points between cycles, which the simulator now carries.
- **The polling average itself** — this exact averaging code replayed on
  323 Senate and governor races, 2014–2025, three days out. It refit the
  poll-error structure, sized the national error, and rescaled the
  rating map (raters' "Lean" races were won by 8 points, not 5.5).
  Rating-based forecasts beat polls alone (Brier 0.050–0.052 vs 0.055).
  Cycle-level misses ran −4.1, −2.6, +0.4, −7.2, −2.4, −5.0 and, in 2025's
  New Jersey and Virginia races, **+6.8 toward Democrats**: the national
  error is sized from them (sd 3.5) but not signed —
  [why](docs/method.md#8b-the-statewide-polling-backtest--how-accurate-is-this-average).
- **The generic ballot** — checked against 2018, 2020 and 2022: it shares
  the national polling miss, and the House interval is, if anything, wide.

The model was frozen at 2026-11-01 05:08 UTC (first frozen snapshot
`2026-11-01T050841Z`). From then until the polls open only the data
changes — including two matching fixes found in a later audit, recorded
with the races they moved in [CHANGELOG.md](CHANGELOG.md).

## The loop

```console
$ make pull        # Wikipedia (127 pages, pinned by revision), FEC, lean, ratings
$ make build       # sources/ -> data/ ; then `make verify`
$ make backtest    # refit: House fundamentals (2018/22) + statewide polls (2014-25)
$ make forecast    # -> data/forecast/latest.json (and this README's block)
$ make snapshot    # freeze a timestamped forecast into the record
$ python3 -m midterms show senate:ME     # one race, every input shown
$ make score       # after Election Day: the scorecard
$ make web-test    # the browser simulator must reproduce the Python forecast
```

## Honesty guarantees

- **Ex-ante only.** The scored forecast is the last snapshot generated
  before polls open (10:00 UTC, Nov 3). Snapshots are committed, so git
  timestamps them; nothing generated later can enter the record. The
  refresh runs every 30 minutes (each run starts the next, so GitHub's
  late or dropped cron slots don't matter) and stands down for the last
  half hour, so the final snapshot is committed before 10:00.
- **Election night never touches the record.** The live view
  (`midterms live`) conditions the frozen forecast on races as they are
  called — counts and calls from civicAPI — and the scorecard grades the
  forecast of record against Wikipedia's results boxes.
- **Every input is traceable.** Each Wikipedia page is pinned by revision
  id; each file by sha256 (`data/meta.yaml`). The build is deterministic:
  the same revisions and files reproduce `data/` exactly.
- **No hidden knobs.** Every parameter lives in `midterms/model/params.yaml`
  marked `fit` (estimated in this repo) or `prior` (from the literature,
  documented, and open to being overturned).
- **Challengers on the same races.** The scorecard grades Lite, Classic and
  Deluxe against the raters' consensus, a lean-only baseline and a coin
  flip, on identical resolved races — Brier score, log loss, calls.

## Data sources

Wikipedia's race pages (candidates, polls, ratings, outside averages;
CC BY-SA 4.0) · VoteHub's poll feed (CC BY 4.0) for the polls Wikipedia's
tables lack, de-duplicated, with admitted fabricators excluded · The
Downballot (2024/2020 presidential results by district, 2026 lines) ·
Dave's Redistricting App block data (2020 results on the nine
redrawn maps) with the Census Bureau's 120th-Congress block equivalency
files · the FEC (fundraising; 2018/2020/2022 official results) · Silver
Bulletin and FiveThirtyEight pollster ratings · for the backtests, 353
past Wikipedia race pages and FiveThirtyEight's archived generic-ballot
polls. Several obvious sources are
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
75% favorite loses about one time in four.*
