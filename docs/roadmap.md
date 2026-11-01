# Roadmap

## Before Election Day (Nov 3)
- [x] Pipeline: Wikipedia race pages, generic ballot, lean on 2026 lines,
      FEC, pollster ratings
- [x] Model: Lite / Classic / Deluxe, correlated simulation, control rules
- [x] House fundamentals fit on 2018 + 2022
- [x] Ex-ante snapshots + scorer
- [ ] Refresh every 6 hours through Election Day; the last snapshot before
      10:00 UTC Nov 3 is the record
- [ ] Site: a TOCSIN/JUDGMENT-style Astro board on a karazajac.io subdomain
      (e.g. `midterms.karazajac.io`)
      (national topline, seat histograms, race pages, the poll ledger)

## After Election Day
- [ ] `midterms pull --only wiki --force` → `midterms score` as results
      boxes fill in; re-score as runoffs (GA Dec 1, LA Dec 12) and recounts
      resolve
- [ ] Publish the scorecard (model versions vs. raters' consensus vs.
      baselines; markets compared locally only)
- [ ] Postmortem: which adjustments helped (population, sponsor, house
      effects, trend line), measured by refitting with each turned off

## Model
- [ ] Demographic error correlation (538's approach) once district
      demographics exist for the 2026 lines (education/race from block data)
- [ ] Backtest Senate and governor parameters (2018, 2022 Senate polls and
      results; Wikipedia's 2018/2022 pages carry the same tables)
- [ ] Fit the rating → margin map on historical ratings (Wikipedia's 2018,
      2020, 2022, 2024 House pages) instead of published hit rates
- [ ] VoteHub as a de-duplicated poll supplement
- [ ] Candidate quality (prior office) for open seats
