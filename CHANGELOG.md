# Changelog

The forecast of record is the last snapshot in `data/forecast/snapshots/`
generated before polls open (2026-11-03T10:00Z); everything below is the
model and pipeline that produced it. Automated six-hourly refreshes
(`refresh: …` commits) only re-pull data and re-run the model.

## Unreleased — final pre-election forecast

### 2026-11-01
- **Statewide polling backtest** (`midterms backtest`): this exact averaging
  code replayed on 323 Senate and governor races, 2014–2025, three days
  out. It refit the poll-error structure (a race-shared part plus a
  per-poll part that shrinks with the effective number of polls; t(6)
  likelihood) and sized the national error at 3.5 (was 2.8), carried fully
  by Senate and governor races and at 0.7 by the House. The direction of
  the next miss is deliberately not modeled — docs/method.md §8b.
- **Generic-ballot check** against 2018/2020/2022 (FiveThirtyEight's
  archived polls): the House shares the national polling error; its
  interval is, if anything, generous.
- **The website**: midterms.karazajac.io, built from `site/` and the new
  `data/site/*.json` contract (docs/site-data.md); `sim/simulator.mjs`
  reproduces the Python simulator in the browser for the what-if page (CI
  parity test).
- Every poll carries its own source URL (resolved from Wikipedia's
  reference lists); per-race polling-average trend lines with 80% bands.
- Fixes: incumbents matched from the race infobox (Lawler, NY-17, had lost
  his incumbency); Montana's D-side is the independent Bodnar, who outpolls
  the Democrat; Alaska's two Dan Sullivans; ranked-choice final rounds;
  hypothetical-matchup tables excluded; fusion lines merged; RCV "inactive
  ballots" rows dropped; Rothenberg recognized as Inside Elections.
- House fundamentals fit on 739 contested districts (2018, 2022), including
  the national-vote → district translation error.

### 2026-11-01 — first forecast
- Pipeline: 127 Wikipedia pages pinned by revision; partisan lean on the
  2026 lines from The Downballot and DRA block data; FEC individual
  contributions; Silver Bulletin pollster ratings.
- Model: Lite / Classic / Deluxe, 50,000 correlated simulations, the real
  control rules; ex-ante snapshots and the scorecard.

This repository supersedes a May 2026 prototype (a vanilla-JS Monte Carlo
in `KaraZajac/2026-midterms-forecast`, removed on Nov 1).
