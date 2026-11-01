# Changelog

The forecast of record is the last snapshot in `data/forecast/snapshots/`
generated before polls open (2026-11-03T10:00Z); everything below is the
model and pipeline that produced it. Automated six-hourly refreshes
(`refresh: …` commits) only re-pull data and re-run the model.

## Unreleased — final pre-election forecast

### 2026-11-01 — refresh fix: pollster ratings pinned in the repo (no model change)
- Silver Bulletin put its ratings file behind a login on Nov 1, and the
  22:05 UTC refresh failed on the download. The ratings the model has
  always used (Silver Bulletin, January 2026; FiveThirtyEight's 2024
  ratings as the fallback) are now committed in `data/pollster_ratings/`
  with each original file's sha256, and the refresh no longer downloads
  them. Every poll weight is unchanged (`data/pollster_quality.csv` is
  byte-identical).
- An FEC outage no longer stops a refresh either: the build keeps the
  committed filings.

### 2026-11-01 — VoteHub supplement, fabricated polls excluded, election-morning refreshes (data and schedule; no model change)
- **VoteHub's poll feed** (CC BY 4.0) now fills gaps in Wikipedia's poll
  tables. A VoteHub poll is added only when no Wikipedia poll of the same
  race could be the same poll: the same pollster or sponsor within 7 days,
  or the same sample size or topline within 4 days, counts as a match.
  `make verify` re-checks this. Of the 860 matchup polls of 2026 races in
  the feed, 830 were already on Wikipedia; 30 were added in 19 races (21
  inside the averaging window).
- **Fabricated polls excluded** (`curated/excluded_pollsters.yaml`, with
  evidence): Wedgewood Polls, which admitted on Oct 20 that its polls were
  made up, and Median Strategies (August). None were in Wikipedia's
  tables, but VoteHub's feed still carried 11 Wedgewood polls; one would
  have been 48% of Mississippi's Senate average.
- Races that moved, against the same day's Wikipedia-only data: AL-02
  49.0% → 45.8% D, NV-02 28.0% → 24.4%, FL-13 22.2% → 20.3%, WA-03
  87.8% → 85.8%. House control 94.9% (unchanged), Senate 75.4% → 75.5%,
  governors 78.4% → 78.2%.
- **Refresh schedule**: hourly on Nov 3 from 00:17 to 08:17 UTC, because
  GitHub ran the Nov 1 12:17 slot at 13:30 and skipped 06:17. A run that
  starts after 09:30 UTC stands down, so every snapshot that can be the
  record is committed before polls open.

### 2026-11-01 — data fix after the freeze (no model change)
- **FEC matching.** 50 nominee sides had failed to match an FEC filing —
  compound or accented surnames (Wasserman Schultz, Gluesenkamp Perez,
  Trone Garriott, Van Epps, De La Cruz, Luján), a record with swapped name
  fields ("NICK, LALOTA") and a legal-surname filing ("ARENHOLZ, ASHLEY
  HINSON") — and an unmatched side counted as $0 raised, pinning the
  money term at its ±4 cap. Matching now handles all of these (871/906
  matched; the rest are mostly unregistered minor candidates), and an
  unmatched side is *unknown* money, which skips the term rather than
  zeroing it. Races that moved: IA-03 68% → 84% D, WA-03 76% → 88%,
  TX-35 68% → 57%, CA-48 94% → 97%; House control 94.6% → 94.9%.

### 2026-11-01 — model frozen (05:08 UTC; first frozen snapshot 2026-11-01T050841Z)
From here to the deadline only the data changes; any later model change
would be recorded here with its reason.

- **Rating map rescaled** (×1.25, fit on 318 rated statewide races; stable
  whichever cycle is held out). The rating sd is deliberately left at its
  prior: fitting it would let the raters' caution about Democratic-leaning
  polls in 2014–2024 into the model by the back door (method.md §5).
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
