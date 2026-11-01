# Data rights and attribution

This repository is original code plus **derived research tables** built from
third-party election data. Rights are layered: the code is [MIT](LICENSE);
the derived data in `data/` is **CC BY-SA 4.0** — share-alike because it
incorporates Wikipedia content and Dave's Redistricting App data, both
licensed CC BY-SA 4.0 — and inherits the attribution requirements below.
Raw sources live only in the gitignored `sources/` directory (regenerable
with `midterms pull`) and are not redistributed here.

| layer | contents | provenance | terms (verified 2026-10-31) |
|---|---|---|---|
| Race pages | `data/races/` (nominees, incumbents), `data/polls/` (poll ledger, apart from the VoteHub rows below), `data/ratings.csv`, `data/averages.csv` | English Wikipedia: the 35 Senate, 36 governor and 51 House race pages, the generic-ballot polling template and the House overview — every page pinned by revision id in `data/meta.yaml` | **CC BY-SA 4.0**. Attribution: "Wikipedia contributors", with page titles and revision ids (`data/meta.yaml`) |
| District presidential results, 2026 lines | `lean` in `data/races/house.csv` and `data/lean/districts.csv` | The Downballot, *2024 and 2020 presidential results by congressional district* (2026 lines and 2024 lines), https://www.the-downballot.com/p/data | "We welcome (almost) any use of our data as long as you cite us and include a link… we ask that you please refrain from reproducing entire spreadsheets." Only the derived lean index is committed — not the per-year district results, which stay in `sources/` |
| 2020 results on redrawn lines | the 2020 component of `lean` for the 173 districts in AL, CA, FL, LA, NC, OH, TN, TX, UT | Dave's Redistricting App block-level election data (`dra2020/block_data`, v07): 2020 presidential votes from the Voting and Election Science Team (VEST); 2024 from the Redistricting Data Hub — aggregated to 2026 districts with the Census Bureau's 120th-Congress block equivalency files | DRA block data **CC BY-SA 4.0**, "you agree not to sell any of this data"; VEST **CC BY 4.0** (doi:10.7910/DVN/K7760H); Redistricting Data Hub: noncommercial, nonpartisan use, and **"This data was generated using data from the Redistricting Data Hub."** Only district aggregates are committed; block files are never redistributed. Census files are public domain |
| Campaign finance | `data/finance.csv` | Federal Election Commission bulk files (`webl26`; `weball18`/`weball22` for the backtest) | **Public domain** (U.S. government). Per the openFEC terms, the FEC is identified as the data source |
| Historical results | backtest inputs (not committed) and `data/backtest.yaml` (derived) | FEC *Federal Elections 2018*, *2020* and *2022*; The Downballot's 2018-lines and 2022-lines presidential sheets | FEC: public domain. The Downballot: as above |
| Historical race pages | `data/backtest_statewide.yaml` (derived: each race's polling average, result and rating, with page title and revision id) | English Wikipedia: every 2014–2024 Senate and governor race page plus the 2025 New Jersey and Virginia governorships (353 pages) | **CC BY-SA 4.0**; revision ids recorded per race |
| Historical generic-ballot polls | `sources/history/` only; derived averages in `data/backtest_statewide.yaml` | FiveThirtyEight's generic-ballot poll archive (2018–2024) as of the March 2025 shutdown, via the Internet Archive | **CC BY 4.0** (fivethirtyeight/data notice); credited to FiveThirtyEight / ABC News |
| Pollster quality | `data/pollster_quality.csv` (derived weights only) | Silver Bulletin pollster ratings, January 2026; FiveThirtyEight pollster ratings (final, 2024) for pollsters SB doesn't rate | Silver Bulletin: "You are welcome to use this data free of charge for any purpose, but please attribute it to Silver Bulletin." FiveThirtyEight: **CC BY 4.0** |
| VoteHub polls | rows of `data/polls/races.csv` whose `source` is `votehub:<id>` (polls Wikipedia's tables lack) | VoteHub public polls API (`api.votehub.com/polls`) | **CC BY 4.0**. Attribution: "Poll data from VoteHub (votehub.com)", with each poll's own source URL in the `url` column |
| Original contributions | the pipeline, model and journal code; adjustments, averages, forecasts, the backtest and scorecard | this project | code MIT; data outputs CC BY-SA 4.0 (attribution chains to the sources above) |

## Deliberately not used

| source | why |
|---|---|
| Cook Political Report (direct) | Terms forbid automated access and republication. Cook's ratings enter only as compiled, with attribution, on Wikipedia's pages |
| RealClearPolling | Bot-blocked; terms bar access other than by browser and redistribution |
| FiftyPlusOne, Decision Desk HQ | Paid / bot-blocked APIs whose terms forbid redistribution. Their *published averages* appear only as compiled on Wikipedia, as challengers |
| Silver Bulletin poll files | No license is stated for the poll CSVs (the ratings are explicitly free to use) |
| Kalshi, Polymarket, PredictIt | Developer/ToS terms bar storing or redistributing market data; markets may be compared locally, never committed |
| FRED | Terms prohibit use "in connection with the development or training of any software program or system"; no macroeconomic fundamentals are used |
| Cook PVI | Cook's own scores are proprietary; lean is computed here from presidential results |

## Required citations

- The Downballot, presidential results by congressional district
  (https://www.the-downballot.com/p/data).
- Dave's Redistricting App, block-level election data
  (https://github.com/dra2020/block_data); Voting and Election Science Team,
  *2020 Precinct-Level Election Results*, Harvard Dataverse,
  doi:10.7910/DVN/K7760H; and: *This data was generated using data from the
  Redistricting Data Hub.*
- Wikipedia contributors, the 2026 election pages listed in
  `data/meta.yaml` (CC BY-SA 4.0).
- Federal Election Commission (data source: openFEC / FEC bulk data).
- Silver Bulletin, pollster ratings (January 2026); FiveThirtyEight,
  pollster ratings (CC BY 4.0).
