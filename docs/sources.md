# Data sources

Every source was fetched and its terms read on 2026-10-31. Status:
**in use**, **pulled** (fetched, not yet a model input), or **not used**
(with the reason). Licensing detail: [../DATA-RIGHTS.md](../DATA-RIGHTS.md).

## In use

### 1. Wikipedia race pages — candidates, polls, ratings, outside averages
The most complete openly licensed compilation of 2026 race data (CC BY-SA
4.0), read through the MediaWiki action API (`action=parse`, rendered
HTML) and pinned by revision id.

- `2026 United States Senate election in <State>` (33) and
  `2026 United States Senate special election in Ohio` / `in Florida`
- `2026 <State> gubernatorial election` (36)
- `2026 United States House of Representatives elections in <State>`
  (at-large states: `…election in <State>`; California is split into
  `(districts 1–26)` and `(districts 27–52)`)
- `Template:2026 United States elections/polling` — the generic-ballot
  poll list (2024–2026)
- `2026 United States House of Representatives elections` — first-elected
  years, generic-ballot averages

Layout parsed by `midterms/pipeline/htmltable.py` + `racepage.py`: per race
(or per "District N" section), *General election › Predictions*
(Source / Ranking / As of), *› Polling* (poll tables and an aggregator
table), *› Fundraising*, *› Results* (the results box). Wikimedia's API
etiquette: serial requests (~1/s) with a user agent naming this repo; the
pipeline honors Retry-After.

### 2. The Downballot — presidential results by congressional district
Google Sheets fetched as CSV at build time (raw copies stay in `sources/`):

- 2026 lines: `1eZfaFI-c-PFOoKx1-zZA2MP0_dxRq_LVK0re3BOQqy0` (vote totals
  tab, gid 1491069057) — 2024 for all 435; 2020 blank in the nine redrawn
  states
- 2024 lines: `1ng1i_Dm_RMDnEvauH44pgE6JCUsapcuu8F2pCfeLWFo`
- backtest: 2022 lines (2020 results) `1CKngqOp8fzU22JOlypoxNsxL6KSAH920Whc-rd7ebuM`;
  2018 lines (2016/2012) `1zLNAuRqPauss00HDz4XbTH2HqsCzMe0pR8QmD1K8jk8`

### 3. Dave's Redistricting App block data + Census block equivalency files
2020 presidential results for the 173 districts on the nine redrawn maps:
`data.dra2020.net/file/dra-block-data/Election_Data_Block_<ST>.v07.zip`
aggregated with `www2.census.gov/…/120-congressional-district-befs/cd120.zip`
(per-state files `CD120_<fips>.txt`). 2024 aggregates match The Downballot
within 0.41 pts in eight states (Louisiana within 1.74, early-vote
allocation).

### 4. Federal Election Commission
- `fec.gov/files/bulk-downloads/2026/webl26.zip` — current House/Senate
  campaigns, pipe-delimited, no header (30 columns, `finance.py`); the model
  uses `TTL_INDIV_CONTRIB`, through the Oct 14 pre-general reports
- backtest: `federalelections2018.xlsx`, `federalelections2022.xlsx`
  (official results with the "(I)" incumbent flag) and `weball18/22.zip`

### 5. Pollster ratings
- Silver Bulletin, January 2026 (540 pollsters, Predictive Plus-Minus,
  grades, bans) — "free of charge for any purpose", with attribution
- FiveThirtyEight, final 2024 (`fivethirtyeight/data`, CC BY 4.0) — fallback

### 6. Backtest inputs (`midterms pull --only history`)
- Wikipedia's 2014–2024 Senate and governor race pages and the 2025 NJ/VA
  governorships (353 pages; fetched by `midterms backtest`, pinned by
  revision in `data/backtest_statewide.yaml`) — the same layout the 2026
  pages use, so the same parser reads polls, ratings and results boxes
- FiveThirtyEight's generic-ballot poll archive, 2018–2024
  (`web.archive.org/web/20250305204633id_/https://projects.fivethirtyeight.com/polls/data/generic_ballot_polls_historical.csv`,
  CC BY 4.0) — Wikipedia no longer carries past cycles' generic-ballot
  tables
- FEC *Federal Elections 2020* (national House vote for the generic check)

## Pulled, not yet used
- **VoteHub** public polls API (`api.votehub.com/polls`, CC BY 4.0): one JSON
  array, ~6,000 polls, no party field, likely/registered versions merged,
  public feed lags its own site. Planned as a de-duplicated supplement for
  races Wikipedia hasn't covered.

## Not used
- **FiveThirtyEight polls** — every live CSV redirects to ABC News since the
  March 2025 shutdown; only archives remain.
- **Cook Political Report, Sabato, Inside Elections (direct)** — Cook's
  terms forbid robots and republication; Sabato blocks automated requests.
  Ratings are read as compiled on Wikipedia. (Inside Elections' own JSON
  matched Wikipedia's IE column on all 214 races checked.)
- **RealClearPolling, FiftyPlusOne, DDHQ** — bot walls, paid APIs, terms
  against redistribution. Their averages appear only via Wikipedia, as
  challengers.
- **Silver Bulletin poll CSVs** — no license stated.
- **Prediction markets** (Kalshi, Polymarket, PredictIt) — terms bar storing
  or redistributing prices. On Oct 31 they had Democrats ~92–94.5% for the
  House and ~71–72% for the Senate.
- **FRED** — terms prohibit use in developing software models.
- **MEDSL House returns** — CC0, but the Dataverse file is behind a
  guestbook form; FEC official results serve the backtest instead.
- **Census ACS by district** — no ACS product covers the redrawn 2026
  districts (new-district tables due December 2026 or later).
