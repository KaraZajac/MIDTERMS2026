# Roadmap

## Before Election Day (Nov 3)
- [x] Pipeline: Wikipedia race pages, generic ballot, lean on 2026 lines,
      FEC, pollster ratings
- [x] Model: Lite / Classic / Deluxe, correlated simulation, control rules
- [x] House fundamentals fit on 2018 + 2022
- [x] Ex-ante snapshots + scorer (resolves only called races; majority
      rules for GA, LA House, ranked-choice ME/AK)
- [x] Statewide polling backtest (323 races, 2014–2025): poll-error
      structure fit, national error sized, rating map rescaled
- [x] Generic-ballot check (2018/2020/2022)
- [x] Refresh every 6 hours through Election Day; the last snapshot before
      10:00 UTC Nov 3 is the record, published as the `forecast-of-record`
      release on the first run after
- [x] Site: midterms.karazajac.io (`site/`), with the in-browser simulator
- [x] Model frozen (2026-11-01 05:08 UTC)

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
- [ ] Fit the Senate and governor *fundamentals* (lean, incumbency) on the
      statewide backtest races (they're priors; they carry ~10–25% weight)
- [ ] Fit the House rating map and rating sd on district ratings (the
      statewide fit sets the map now)
- [ ] A House national-loading fit once more generic-ballot cycles are in hand
- [ ] VoteHub as a de-duplicated poll supplement
- [ ] Candidate quality (prior office) for open seats
