# Changelog

The forecast of record is the last snapshot in `data/forecast/snapshots/`
generated before polls open (2026-11-03T10:00Z); everything below is the
model and pipeline that produced it. Automated six-hourly refreshes
(`refresh: …` commits) only re-pull data and re-run the model.

## Unreleased — final pre-election forecast

### 2026-11-03, night — the committed copy never drops calls (no model change)
- When civicAPI doesn't answer the refresh's run, the committed
  `live.json` used to fall back to Wikipedia's settled races alone. Once
  Wikipedia settles a few races, such a copy would be newer than the web
  server's last good one but hold far fewer calls, and the page, which
  shows the newer file, would retract calls civicAPI had made. The
  fallback now applies only while civicAPI hasn't answered at all;
  otherwise the run writes nothing and the last good copy stays.

### 2026-11-03, night — the chances through the night (no model change)
- `live.json` keeps `history`: each chamber's chance of Democratic
  control given the calls, and the number of races called, whenever
  either changed, from the forecast of record on, for a chart of the
  night. Each file carries the previous file's history on; the web
  server's first one started it from the calls still in `events` (back
  to 00:41 UTC). Chances are kept to 4 decimals, as `p_control` is: at 3
  the Senate's forecast (0.7675) read 76.7% on the chart and 76.8% on the
  gauge beside it.

### 2026-11-03, night — county results of the statewide races (no model change)
- `midterms counties` writes each Senate and governor race's results by
  county (civicAPI's `race/{id}`), one file per race, for county maps on
  the race pages. The web server runs it every 5 minutes beside
  `live.json`. It reuses the race ids the live job already has (no extra
  searches), fetches only races with votes, three at a time with one try
  each, and stops a cycle after three failures in a row, so it never adds
  to an outage. Counties that don't add up to the race's total (towns
  without FIPS) give no map. Contract: docs/site-data.md.
- civicAPI sends independent cities, which are county equivalents, without
  a FIPS: Virginia's 38 held a quarter of its Senate votes, so its
  counties fell short of the total and it had no map. They are now found
  by name (Virginia's 38, Baltimore, Carson City; codes checked against
  the site's county shapes), and each file lists the regions it left out.
- By 03:05 UTC civicAPI had answered none of the county requests for 30
  minutes, and 41 races with votes (Iowa's Senate race among them) had no
  map. Each cycle now tries the races without a map first, the closest
  races first (by the forecast), and stops after five failures in a row
  instead of three. Empty files from before the city lookup count as no map.

### 2026-11-03, evening — a slow civicAPI answer is waited for (no model change)
- At 22:58 UTC, as the first polls closed, civicAPI left three 25-second
  reads of the governors' search in a row unanswered, and that run of the
  web server's live job failed (`/live.json` went 3 minutes without an
  update before the next runs caught up). Giving up on a slow read only
  asked the same slow search again. Now the first read waits up to 50
  seconds; a second gets what is left of the same 80-second budget, so a
  run still ends well inside the server's 110-second limit.
- Then civicAPI's two searches failed by turns: five of the server's 74
  runs between 23:07 and 00:23 UTC failed, each on one search while the
  other answered, two of them in a row (`/live.json` went 4 minutes
  without an update). The web server now keeps each search's last answer
  beside its `live.json`. When one search still fails after its retries,
  its last answer stands in if it is at most 5 minutes old, and the page
  says so ("governors' results as of 7:19 p.m. ET"; `source.fetched` is
  then that older answer's time). If both searches fail, nothing stands
  in: the run fails and the last good file stays up, as before. The
  committed copy is unchanged.
- From 01:00 UTC civicAPI answered most House-and-Senate searches with a
  502 in a fifth of a second, asking the client to wait 30 seconds or
  more before trying again. Honoring that left a run two or three tries,
  and the search went unanswered for minutes at a time. A 5xx's
  Retry-After is now honored only up to 10 seconds (a 429's still up to
  30), so a run gets about seven tries.
- Cloudflare's own origin errors in front of civicAPI (520–524) are
  retried like a 502. The log names every search that failed and, for an
  HTTP error, the Retry-After it carried. The page's credit line reads
  "…; counts from secretaries of state; …" (lowercase after the
  semicolon), and a stood-in search's time is written "8:09 p.m. ET", as
  the rest of the site writes times.

### 2026-11-03, morning — civicAPI's searches (no model change)
- From 14:00 UTC civicAPI answered the governors' text search
  (`query=Governor`) with 503 DATABASE_TIMEOUT ("Public database request
  exceeded its time budget"), and every run of the web server's live job
  failed. The governors' search now filters by office
  (`election_type=Statewide&type=Governor`). That returns the same races
  (all 506 still map) and doesn't time out.
- A failed civicAPI read (429, 5xx, a network error or a timeout) used to
  get two quick tries. Now it is tried again after 2, 4, 8, then every 10
  seconds, or the server's Retry-After, while the fetch's 80-second budget
  lasts. That is inside the web server's 110-second limit on the job.
  Downloads now say why they failed (`fetch.DownloadFailed`: the HTTP
  status and Retry-After). A reset connection or a cut-off gzip body
  counts as a network error to retry, not a crash.

### 2026-11-03, after the seal — reused inputs keep their provenance (no model change)
- After the deadline the refresh pulls only Wikipedia (for the results),
  so every build reuses the committed VoteHub polls and FEC filings. The
  first of these builds (10:10 UTC) wrote `data/meta.yaml` as though they
  had no source. It dropped the `fec-webl26` and `votehub-polls` file
  entries and counted 0 fabricated VoteHub polls excluded instead of 11,
  so the /data/ page lost its "Polls excluded as fabricated" line. Now a
  build that reuses data keeps those file entries and that count from the
  meta.yaml committed before it (`build.keep_provenance`). The 10:10
  entries were restored from the forecast of record's commit (0ab1b66).
  The data and the forecast of record are unchanged.
- A build that reuses the FEC filings no longer fails when Wikipedia
  respells a nominee's name (a Nov 1 page had "Gordan Heslop" for LA-04's
  "Gordon Heslop"). That nominee's row is left without a filing, as
  intended, instead of breaking the build, which would have stopped the
  scoring after the deadline until the names matched again.

### 2026-11-03 — election night for viewers: seats changing hands, poll closings (no model change)
- `live.json` marks the seats that change hands: `held` (the party holding
  each seat now), the winner's `party`, `flip`, and per chamber `gains`,
  `losses` and the list of `flips`. House seats count by district number
  from the Clerk of the House's member list (published Oct 1, 2026; a
  vacant seat counts for its last member's party), as AP and Wikipedia
  count gains; Senate seats and governorships by incumbent.
  `data/holders/` pins the table.
- `live.json` carries every state's poll closing times (`polls_close`,
  from `curated/poll_closing.yaml`, after 270toWin's table): first and
  last closing, with a note for states split across time zones. The
  simulated nights in `tests/fixtures/live/` (regenerated) call races by
  these times.
- Overnight the refresh re-reads Wikipedia's results boxes, the
  cross-check on civicAPI's calls, every 10 minutes instead of every 30.
- civicAPI's searches take 6–10 s to a first byte when its cache is cold,
  as a once-a-minute poll always finds it, and the web server's first real
  run (05:25 UTC) failed on the 12-second read timeout with no retry. Now
  each read may wait 25 s, twice; the two searches run side by side; and
  the response comes gzipped (47 KB instead of 414).

### 2026-11-01 — election night: live results and the forecast given the calls (no model change)
- `midterms live` fetches every race's count and call from civicAPI
  (civicapi.org; counts from secretaries of state, calls by its decision
  desk) and writes `live.json`: each race's state of play, and each
  chamber's chances *given the races called so far* — the frozen forecast
  of record conditioned on the calls, never on partial counts (method
  §10). The forecast of record itself is untouched, and the scorecard
  still resolves races from Wikipedia.
- The web server runs it every minute through the night; the refresh
  workflow commits `data/site/live.json` as the record (every 10 minutes
  overnight). Contract: docs/site-data.md.
- `summary.json` gains `next_refresh`, when the next refresh starts; and
  a new `changes.json` lists what each refresh changed — the polls that
  entered an average, the races that moved two points or more, the
  chambers (backfilled from today's refresh commits).

### 2026-11-01 — refresh fixes: ratings pinned, a 30-minute chain (no model change)
- Silver Bulletin put its ratings file behind a login on Nov 1, and the
  22:05 UTC refresh failed on the download. The ratings the model has
  always used (Silver Bulletin, January 2026; FiveThirtyEight's 2024
  ratings as the fallback) are now committed in `data/pollster_ratings/`
  with each original file's sha256, and the refresh no longer downloads
  them. Every poll weight is unchanged (`data/pollster_quality.csv` is
  byte-identical).
- An FEC outage no longer stops a refresh either: the build keeps the
  committed filings.
- **Refresh every 30 minutes**, as a chain: each run waits for the next
  slot and dispatches it (`midterms/pipeline/cadence.py`), because GitHub
  ran the 18:17 UTC cron slot at 22:05. Hourly cron runs are only a
  watchdog that restarts the chain. The last half hour before polls open
  still stands down. After the deadline: hourly scoring, then results
  every 10 minutes from 23:00 UTC on election night.

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
