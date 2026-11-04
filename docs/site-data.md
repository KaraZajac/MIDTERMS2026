# Site data contract — `data/site/*.json`

The website (midterms.karazajac.io, built from `site/`) reads only these
files. They are written by `midterms export`, which runs at the end of every
`midterms forecast` (and after `midterms score` once results arrive); the
refresh workflow commits them every 30 minutes until polls open, then as
results and scores change (`midterms/pipeline/cadence.py`). `midterms verify` checks the
envelope, ids/slugs and probabilities on every commit.

Conventions:

- **Envelope.** Every file is a JSON object with `generated` (UTC ISO — when
  the forecast ran) and `asof` (the date it is a forecast *as of*).
- **Margins** are two-party margins in points, **D-side minus R-side**:
  100 × (D − R) / (D + R). Positive = the D-side candidate leads.
- **Sides.** Every race is D-side vs R-side. Usually Democrat vs Republican;
  where a party has no nominee, an independent fills its side (party code
  `IND`): Osborn (NE), Achilles (ID), Bengs (SD) and Bodnar (MT; he outpolls
  the Democrat) are D-sides; Kiley (CA-06) is an R-side.
- **Ids and slugs.** `house:PA-07`, `house:AK-AL` (at-large),
  `senate:ME`, `senate:OH-special`, `senate:FL-special`, `governor:OH`.
  `slug` is `chamber/rest-lowercased` (`senate/oh-special`); route = `/` +
  slug + `/`.
- **Versions.** `lite`, `classic`, `deluxe`; `summary.headline` (= `deluxe`)
  is the one to lead with.
- **Phase.** `meta.phase` / `summary.phase`: `forecast` before
  2026-11-03T10:00Z, then `frozen` until a race resolves, then `results`.

## summary.json

```jsonc
{
  "phase": "forecast", "election_day": "2026-11-03", "deadline": "2026-11-03T10:00:00Z",
  "n_sims": 50000, "headline": "deluxe", "versions": ["lite","classic","deluxe"],
  "national": {
    "generic": {"margin": 9.11, "n_polls": 150, "pollsters": 61, "latest": "2026-10-30"},
    "environment_sd": 2.8,                       // sd of the national error at E-3
    "popular_vote": {"mu": 9.11, "p10": 5.96, "p90": 12.35},
    "outside_averages": [{"source": "Silver Bulletin", "d": 51.3, "r": 42.4,
                          "margin_raw": 8.9, "updated": "2026-10-30", "url": "…"}]
  },
  "chambers": {
    "house" | "senate" | "governor": {
      "versions": {"deluxe": {
        "p_control": {"D": 0.928, "R": 0.072, "unclear": 0.0},
        "p_control_alt": null,                    // senate: uncommitted independents counted with D
        "seats": {"mean": 237.4, "p10": 220, "p50": 238, "p90": 254},   // D-bloc seats
        "hist": {"min": 168, "p": [0.00002, …]}    // p[i] = P(D-bloc seats = min + i)
      }, "lite": {…}, "classic": {…}},
      "tipping": [{"id": "house:PA-07", "slug": "house/pa-07", "label": "PA-07", "p": 0.03}],
      "n_races": 435, "competitive": 49, "fixed": 17,
      "seats": 435, "majority": 218, "seats_not_up": {},          // senate: {R:31, D:32, I:2}
      "tie_breaker": "R", "caucus": {"I": "D"}, "note": "…"        // senate only
    }
  },
  "joint": {"grid": {"house_D": {"senate_D": 0.765, "senate_R": 0.157},
                     "house_R": {"senate_D": 0.016, "senate_R": 0.055}}, "unclear": 0.007},
  "adjustments": {"population_shift": {"RV": -0.48}, "sponsor_lean": {"D": 2.07, "R": -1.94},
                  "house_effects": [{"pollster": "activote", "points": -1.3, "polls": 25}]},
  "counts": {…}                                   // races, polls, ratings, FEC matches
}
```

## races.json — `{generated, asof, races: [...]}` (506 races)

```jsonc
{
  "id": "senate:ME", "slug": "senate/me", "chamber": "senate", "state": "ME",
  "state_name": "Maine", "label": "Maine", "district": null, "special": false,
  "d": {"name": "Troy Jackson", "party": "D"}, "r": {"name": "Susan Collins", "party": "R"},
  "others": ["Name (L)"],
  "incumbent": {"name": "Susan Collins", "party": "R", "running": true, "first_elected": null},
  "fixed": null,              // "D"/"R" when decided before Election Day (no distribution)
  "lean": 7.64,               // partisan lean, D minus R, vs the nation
  "rules": "Ranked-choice voting",
  "ratings": {"Cook": {"rating": "Tossup", "asof": "2026-10-20", "scale": 0, "url": "…"}, …},
  "inputs": {
    "fundamentals": {"mu": 13.1, "sd": 8.5,
                     "parts": {"lean": 6.49, "national": 9.11, "incumbency": -2.5, "fundraising": 0}},
    "polls": {"mu": 2.47, "sd": 3.72, "n_polls": 30, "n_eff": 17.0, "pollsters": 23,
              "latest": "2026-10-27", "partisan_share": 0.3},
    "ratings": {"mu": 0.0, "sd": 7.15, "scale": 0.0, "raters": {"Cook": "Tossup", …}}
  },
  "forecast": {"deluxe": {
    "p_d_side": 0.776, "p_party": {"D": 0.776, "R": 0.224},
    "estimate": {"mu": 3.40, "sd": 3.08,                      // the blend, before shared error
                 "weights": {"fundamentals": 0.131, "polls": 0.684, "ratings": 0.185}},
    "margin": {"mean": 3.47, "sd": 4.75, "q01": -7.8, "q05": -4.2, "q10": -2.4, "q25": 0.4,
               "q50": 3.5, "q75": 6.5, "q90": 9.4, "q95": 11.1, "q99": 15.3},
    "tipping": 0.118
  }, "classic": {…}, "lite": {…}},
  "favorite": "D", "flip": true,             // favorite differs from the incumbent party
  "outside_averages": [{"source": "270toWin", "d": 49.2, "r": 45.6, "margin_raw": 3.6,
                        "end": "2026-10-27", "updated": "2026-10-31", "url": "…"}],
  "finance": {"D": {"name": "…", "receipts": 23977118, "fec_id": "S6ME…", "url": "…"}, "R": {…}},
  "source": {"title": "2026 United States Senate election in Maine", "revid": 1383115522,
             "url": "https://en.wikipedia.org/w/index.php?oldid=1383115522"}
}
```

`inputs.*` is null when a component is absent (no polls; no rating).
`estimate.weights` keys are the components actually blended
(`lean` appears in Lite for unpolled races).

## polls.json — `{generated, asof, basis, races: {id: {polls, trend}}}`

```jsonc
"senate:ME": {
  "polls": [{"pollster": "Data for Progress", "sponsor": "D", "start": "2026-10-23",
             "end": "2026-10-27", "n": 652, "population": "LV", "d": 50.0, "r": 45.0,
             "margin": 5.26,        // raw two-party
             "adjusted": 4.29,      // after house effect, population, sponsor, trend line
             "weight": 0.0588,      // share of the race's average (weights sum to 1)
             "url": "https://www.dataforprogress.org/…",   // the poll's own source
             "via": "wikipedia",    // or "votehub": a poll Wikipedia's tables lack
             "wikipedia": "https://en.wikipedia.org/w/index.php?oldid=…"}],   // null when via votehub
  "trend": [["2026-07-04", 1.8, 0.4, 3.2], …]   // [date, average, lo80, hi80], daily
}
```

Only polls inside the averaging window (150 days) appear; the full ledger is
`data/polls/races.csv`.

## generic.json

`{generated, asof, basis, average: [[date, avg, lo80, hi80], …] (150 days),
polls: [… same poll fields …], outside_averages: [...]}`

## history.json

`{generated, asof, snapshots: [{generated, asof, snapshot, ex_ante, generic,
house|senate|governor: {p, p50, p10, p90}}]}` — one row per frozen snapshot;
`ex_ante` false for anything generated after the deadline.

## changes.json — what each refresh changed

`{generated, asof, basis, entries: [{t, previous, chambers: {house|senate|governor:
{from, to}}, polls: [{race, pollster, end, margin, partisan, via, weight}],
polls_total, moved: [{race, from, to}], moved_total}]}` — newest first, the
last 96 refreshes that changed anything (`model/changes.py`). `polls` are the
polls that entered an average since the previous forecast (`margin`: raw
two-party, D-side minus R-side; `weight`: share of that race's average);
`moved` are the races whose P(D-side wins) moved two points or more; the
chamber values are P(Democratic control). Headline version throughout.
Frozen after the deadline, when the forecast stops rerunning.

## sim.json — input for `sim/simulator.mjs`

`{national_mu, shared: {sd_national, nu_national, sd_region, sd_state,
nu_race, sd_chamber: {house}, floor_idio}, regions: {name: [states]},
chambers: {house|senate|governor: {majority, seats_not_up, tie_breaker,
caucus, alt_caucus}}, reference: {version: {chamber: p_control}}, races:
[{id, chamber, state, lam, d_side, r_side, fixed, mu: {version}, sd: {version}}]}`

```js
import { simulate, createEngine } from "../../sim/simulator.mjs";
const out = simulate({ params: sim, n: 5000, seed: 1, version: "deluxe",
                       shift: 0, natScale: 1, forced: { "senate:TX": "D" } });
// out.accepted, out.chambers.senate.p.D, out.chambers.house.hist, out.races["senate:ME"]
const engine = createEngine(sim, { nSims: 5000 });   // for sliders: draws once
engine.run({ shift: -2 });                            // ~25 ms
```

`shift` moves every race toward Democrats by that many points (λ-loaded,
so governors move 0.6×); `natScale` scales the national error;
`forced` conditions on outcomes (`'D'` = the D-side wins). CI checks the JS
engine against the Python forecast (`make web-test`).

## backtest.json

`{house_fundamentals: {what, fit, per_year, sample, out_of_sample: [{train,
test, n, brier, log_loss, rmse, mean_error, calibration: [{bin, n,
forecast, observed}]}]}, senate_polls?: {…}}`

## meta.json

`{phase, exported, deadline, election_day, counts, sources_digest,
quantiles, wikipedia: [{title, revid, url}], states: {ST: {name, tile: [col,
row], region}}, license, repo, site, attribution: [...]}` — `tile` is a
standard state tile-grid position for cartograms.

## scorecard.json (after Election Day)

`{forecast, forecast_generated, deadline, resolved, open_count, open,
scoreboard: {lite|classic|deluxe|ratings|lean-only|coin-flip: {n, brier,
log_loss, calls}}}` — written by `midterms score`.

`provisional` (election night on, when a live.json exists): `{basis, asof,
called, scoreboard: {… as above}, races: [[race id, winning side "D"|"R",
headline P(winner)]]}` — the same contenders scored on the races *called*
so far (civicAPI's decision desk, or Wikipedia where it called first), from
the newest live.json (the web server's, else the committed copy), as of
`asof`. Calls are not final results: show it apart from the scorecard of
record (`resolved`, `scoreboard`, `races`), which resolves races from
Wikipedia's results boxes alone. Updated with every scoring run (every 10
minutes on election night, then with each refresh).

## live.json (election night) — written by `midterms live`

Two copies, one shape. The web server runs `midterms live --out …` every
minute from Nov 3 22:30 UTC and serves `/live.json`; the refresh workflow
commits `data/site/live.json` (every 10 minutes overnight, then less
often) as the record and the build-time fallback. Show whichever copy has
the newer `generated`. Every string is plain text.

```
{
  generated, asof,            // when this file was computed (UTC)
  fixture: false,             // true only for simulated nights (tests/fixtures/live/)
  status,                     // "awaiting" (no votes yet) | "counting" | "complete"
  source: {name: "civicAPI", url, fetched, credit, note},
                              // fetched: when civicAPI was read; on the web server, when
                              // one search failed and its last answer (≤ 5 min old for the
                              // House and Senate, 30 for governors)
                              // stood in, that answer's time, and note says which
  forecast: {snapshot, generated, of_record, version},
                              // the forecast conditioned: after the deadline, the
                              // forecast of record (of_record true)
  method,                     // one sentence for the page
  held_note,                  // one sentence: what "changes hands" means (below)
  polls_close: {              // when the polls close (curated/poll_closing.yaml)
    source: {name, url, fetched, note},
    states: {ST: {first, last, note?}},
                              // UTC; first and last differ in states split across
                              // time zones (and New Hampshire's towns), with a
                              // one-line note; a statewide race is called only
                              // after `last`
    races: {race id: {first, last}}
                              // districts with their own window (Florida's: the
                              // 1st and 2nd close at 8 p.m. ET, the rest at 7);
                              // every other race: its state's
  },
  counts: {awaiting, counting, called, runoff, uncontested},
  chambers: {house|senate|governor: {
    seats, majority,
    not_up: {party: n},       // Senate and governor seats not on the ballot
    fixed: {party: n},        // decided before Election Day (uncontested)
    called: {party: n},       // called tonight, by the winner's party label
    uncalled,                 // contested races without a call
    bloc: {D, R, other},      // not_up + fixed + called, under the caucus rule
    pre:  {p_control: {D, R, unclear}, seats: {mean, p10, p50, p90}},
                              // the forecast of record, unchanged
    live: {p_control, p_control_alt?, seats, hist: {min, p: [...]},
           ess, draws, reliable},
                              // given the calls so far; `ess` is the effective
                              // number of simulations behind it, and when
                              // `reliable` is false (ess < 400) say so instead
                              // of showing a noisy number
    favorites: {called, won}, // called contested races the forecast favored
    upsets: [race id],        // called against the forecast, biggest first
    gains: {party: n},        // seats won from another party, by the winner's party
    losses: {party: n},       // ... by the party that held them
    flips: [race id]          // the seats that changed hands, newest call first
  }},
  races: {race id: {          // every race in races.json, same ids
    status,                   // awaiting | counting | called | runoff | uncontested
    winner?,                  // "D" | "R" (the D-side / R-side) | "other"
    winner_name?,             // only when the winner is neither nominee
    called_at?,               // when a call was first seen
    upset?,                   // the winner had under 50% in the forecast
    called_by?,               // "wikipedia" when only Wikipedia's results box
                              // has settled it (civicAPI otherwise)
    held?,                    // the party holding the seat now ("D", "R", "IND")
    party?,                   // the winner's party, when the winner is a nominee
    flip?,                    // true: the seat changes hands (party != held)
    disputed?,                // civicAPI and Wikipedia call it differently:
                              // shown as counting, not used
    pct_reporting?, votes?: {D, R, other}, margin?,
                              // the current count; margin is two-party,
                              // D-side minus R-side, points
    p_pre,                    // P(D-side wins), forecast of record
    p_live                    // P(D-side wins | calls so far); 1 or 0 once called
  }},
  events: [{t, race, type: "call"|"changed"|"retracted", winner,
            p_winner_pre?, upset?, party?, flip?, after: {house, senate, governor}}]
                              // newest first (120 kept); `after` is
                              // P(D control) once that call was in
  history: [[t, house, senate, governor, called]]
                              // oldest first: P(D control) given the calls
                              // (4 decimals, as p_control) and the races called,
                              // whenever either changed, from the forecast of
                              // record at the deadline on (1,500 kept)
}
```

Before any contested race is called, `live` equals `pre` exactly. The
counts are display only: the live probabilities use calls, never partial
counts (method §10).

Every call is in `races` (status, winner, called_at); `events` keeps only
the newest 120, so a full list of calls is built from `races`.

**Changing hands.** `held` is the party holding each seat now: House seats
by district number from the Clerk of the House's member list (a vacant seat
counts for its last member's party), Senate seats and governorships by
incumbent (data/holders/). That is the convention AP and Wikipedia use for
gains, so a redrawn district can change hands. `flip` marks a called (or
uncontested) race whose winner's party differs; a winner who is neither
nominee (`winner: "other"`) has no `party` and is never marked.

## counties/&lt;chamber&gt;/&lt;slug&gt;.json (election night, web server only) — written by `midterms counties`

County results of one statewide race (Senate or governor), from civicAPI's
`race/{id}`. The web server writes them every 5 minutes beside `/live.json`
and serves them at `/counties/senate/ga.json`, `/counties/governor/ga.json`,
`/counties/senate/oh-special.json` (the race page's path). They are not
committed. A race with no votes yet has no file (404); a race whose fetch
failed keeps its last file.

```
{
  generated, fetched,          // when written; when civicAPI answered for this race
  race: "senate:GA", civic_id,
  source: {name: "civicAPI", url, credit},
  total,                       // the race's votes in the same answer
  coverage,                    // the regions' votes / total (null before votes)
  regions: [{                  // by 5-digit county FIPS, sorted
    fips, name,                // name null for a county added up from towns
    pct_reporting,             // null for a county added up from towns
    votes: {D, R, other},      // by our sides, as in live.json
    margin                     // two-party, D-side minus R-side, points; null if a
  }],                          // side didn't match or no two-party votes yet
  dropped, dropped_names,      // civicAPI regions without a usable FIPS (independent
                              // cities are found by name: VA's 38, Baltimore, Carson City)
  note?                        // why regions is empty
}
```

When the counties don't add up to the race's total (coverage outside
0.97–1.03: Massachusetts' towns come without FIPS), `regions` is `[]` and
`note` says why: show no map. Shade a county by the side `margin` favors;
no votes yet (`votes` all 0) is no shade.
