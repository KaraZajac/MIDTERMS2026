# Method

How MIDTERMS2026 turns polls, fundamentals and ratings into probabilities —
and, at the end, everything it gets wrong or leaves out. The design follows
FiveThirtyEight's 2018–2024 House, Senate and governor models as described
in their published methodology; where this model differs, it says so.

## 1. The unit: a two-party margin between two sides

Every race is reduced to a head-to-head between a **D-side** and an
**R-side** candidate, and every quantity is the D-side's **two-party
margin** in points: 100 × (D − R) / (D + R).

- Normally the sides are the Democratic and Republican nominees.
- Where a party fields nobody, the strongest other candidate takes that
  side: Dan Osborn (I) is Nebraska's D-side; Todd Achilles (I) Idaho's;
  Brian Bengs (I) South Dakota's.
- In multi-candidate races the sides are chosen **by poll share**: the
  best-polling Republican is the R-side (Alaska's top-four general has
  three) and the best-polling non-Republican the D-side (in Montana the
  independent Seth Bodnar outpolls the Democratic nominee four to one).
- A race is **fixed** — decided before Election Day — when only one party
  can win: one candidate on the ballot, two of the same party (California
  top-two), or a nominee facing only minor candidates in a race every core
  rater calls Safe and nobody has polled. In 2026: 16 House seats fixed D,
  1 fixed R.

Candidates come from each race's Wikipedia results box (or, where editors
haven't added one yet, the race infobox). Incumbency is taken from the
infobox's "Incumbent U.S. Representative/Senator/Governor" row and matched
against the nominees, because the "(incumbent)" tag is applied
inconsistently.

## 2. Polls

**Source and selection.** Every general-election poll table on every race
page whose answer columns name *both* sides — the actual matchup.
Hypothetical-matchup tables (Wikipedia's collapsed "Hypothetical polling"
blocks) and primary tables are excluded. Ranked-choice tables keep each
poll's final round. One version per underlying poll: likely voters over
registered voters over adults, then the first-listed question.

**Weights** (FiveThirtyEight's structure):

| factor | form |
|---|---|
| recency | 0.5 ^ (age / 14 days) — 10 days for the generic ballot |
| sample size | √(clamp(n, 200, 3000) / 600) |
| pollster quality | exp(−0.35 × Silver Bulletin Predictive Plus-Minus), clamped to [0.35, 1.6]; unrated 0.7; banned 0 |
| sponsorship | ½ for D- or R-affiliated polls |
| crowding | 1/√k for a pollster's k polls of the race in the window |

**Adjustments, each measured from the polls themselves** (with shrinkage
toward zero so thin evidence moves little):

| adjustment | how it is measured | 2026 value |
|---|---|---|
| population | mean LV − RV margin across polls that published both | RV: −0.48 pts (127 pairs) |
| sponsor lean | mean residual of D-/R-affiliated polls vs. other pollsters' polls of the same race within ±21 days | D +2.07 (169 polls), R −1.94 (331) |
| house effects | the same residual by pollster, after sponsor lean, iterated, shrunk with 6 pseudo-polls | per pollster, in `forecast/latest.json` |
| trend line | a state or district poll fielded weeks ago is moved by the change in the national generic-ballot average since its field date | — |

**Uncertainty of a race's average** (race-level, excluding the error all
races share, which the simulator adds):

  sd² = shared² + per_poll² / n_eff + Σ(wᵢ/Σw)² · sampling_sdᵢ²
        + 1.5² · (days since last poll / 30) + 3.5² · (share of weight from sponsored polls)

Nonsampling error has two parts: a piece every poll of the race shares,
and a piece each poll carries alone (mode, frame, a house effect that
doesn't fit this race) that averages out as polls accumulate — hence
÷ n_eff, the effective number of polls. Both are **fit** on 323 Senate and
governor races, 2014–2025 (§8b): **shared 1.2, per-poll 8.75** for
statewide races. A race with 30 polls is thus about as certain as one
with 10 by sampling error alone, but a race with two polls is far less
certain than either. House districts use a larger shared part (3.0, prior):
district polls miss by more, and 64% of 2026 district polls are campaign-
or party-sponsored, against 47% statewide. An average built entirely of
one campaign's internals is far less certain than one with independent
polls.

## 3. The national environment

The generic-ballot average (same machinery, 724 polls) is the national
environment *N*: D+9.1 two-party as of Nov 1. The outside averages
Wikipedia compiles (DDHQ, FiftyPlusOne, NBC, RCP, Silver Bulletin; raw
D+8.0 to D+8.9) are recorded as challengers, not inputs. No macroeconomic
or approval-based prior is blended in: three days out, the final generic
ballot dominates every published fundamentals model, and FRED's terms rule
out its use here.

## 4. Fundamentals

**Partisan lean** of a district or state, on the lines used in 2026:

  lean = 0.75 × (2024 margin − national 2024) + 0.25 × (2020 margin − national 2020)

(two-party margins; the 75/25 weighting Cook uses). 2024 results on 2026
lines for all 435 districts come from The Downballot; 2020 from the same
sheet where lines are unchanged, and — for the 173 districts in the nine
states that redrew (AL, CA, FL, LA, NC, OH, TN, TX, UT) — from Dave's
Redistricting App block-level results aggregated to the new districts
with the Census Bureau's 120th-Congress block files. (Spot checks: TX-28
2020 two-party D+9.7, matching the Texas Legislative Council; 2024 block
aggregates match The Downballot within 0.4 pts.) State leans sum their
districts.

**House** (fit on 2018 + 2022; `data/backtest.yaml`):

  μ_F = 0.875 · lean + N + 2.88 · inc + 0.81 · log₂(D money / R money)  (money term capped at ±4)

where *inc* is +1/−1 for a running D/R incumbent and money is FEC
individual contributions. Residual sd: 5.58 (incumbent-held), 6.02 (open).
A first-term incumbent gets a further +1.0 (prior; the sophomore surge).

**Senate**: 0.85 · lean + N + 2.5 · inc, sd 8.5 (priors).
**Governor**: 0.55 · lean + 0.6 · N + 4.0 · inc, sd 11 (priors —
governorships are the least nationalized offices; Vermont's Phil Scott
wins in a D+30 state).

## 5. Expert ratings

The latest Cook, Sabato and Inside Elections ratings (as compiled on
Wikipedia, dated) are mapped to a scale (Solid ±3, Likely ±2, Lean ±1,
Tilt ±0.5, Toss-up 0), averaged, and converted to a margin through the
anchors 0 → 0, 0.5 → 2.5, 1 → 5.5, 2 → 11, 3 → 22 points, with sd 5.5
(×1.3 when the race is polled, since raters read the same polls). With the
shared error added, those anchors reproduce the raters' long-run hit rates
(Tilt ≈ 65%, Lean ≈ 80%, Likely ≈ 95%, Solid > 99.9%). Seven other
handicappers Wikipedia tracks are recorded but not blended.

## 6. Versions and the blend

| version | components (precision-weighted) |
|---|---|
| Lite | polling average; if none: lean-based estimate (lean + N), sd + 0.5 |
| Classic | fundamentals + polling average |
| Deluxe | fundamentals + polling average + ratings — **the headline** |

Each component is treated as an independent measurement of the margin:
μ = Σ μₖ/σₖ² / Σ 1/σₖ², σ = (Σ 1/σₖ²)^−½.

## 7. Simulation

50,000 draws (seeded; reproducible). For race r in draw s:

  margin = μ_r + λ_r · national_s + region_s + state_s + house_s + idio_{s,r}

| term | distribution | sd |
|---|---|---|
| national | Student t, 5 df | 3.5, on the statewide-poll scale (fit-informed, §8b); loading λ = 1 for Senate and governor races, 0.7 for the House (whose national error rides on the generic ballot) |
| Census region | normal | 1.5 |
| state (shared by a state's House, Senate and governor races) | normal | 1.8 |
| House-wide translation | normal | 2.1 (fit: the instability of the national-vote → district-baseline offset between 2018 and 2022) |
| race | Student t, 6 df | the race's blended σ |

Seats roll up with the real rules: House 218; Senate Democrats need 51
(34 of their seats are not up), Republicans 50 (31 not up) with Vice
President Vance's tiebreak; Sanders and King caucus with Democrats;
an independent who hasn't committed to a caucus is counted as neither
(a headline "unclear" outcome), with an alternate tally if they sided with
Democrats. Governors: 26 of 50 (14 not up: 6 D, 8 R).

(The governor *mean* moves only 0.6× with the national environment — §4 —
but governor polls share the national polling *error* fully; the backtest
found their cycle-level misses as large as the Senate's.)

Reported per race: P(win), margin mean, sd and 1–99% quantiles, and the
**tipping-point** frequency — how often the race is the one that delivers
the decisive seat (the 218th House seat; the 17th Democratic / 19th
Republican Senate win). Chamber seat distributions and the joint
House × Senate outcome table come from the same draws.

## 8. The backtest

`midterms backtest` regresses the two-party margin of every contested
district in 2018 (355) and 2022 (384) on lean, incumbency and fundraising,
with a year intercept absorbing the national environment:

| | 2018 | 2022 | pooled |
|---|---:|---:|---:|
| lean coefficient | 0.85 | 0.91 | **0.875** |
| incumbency (pts) | 2.96 | 2.81 | **2.88** |
| money (pts / doubling) | 1.06 | 0.60 | **0.81** |
| residual sd | 6.08 | 5.25 | **5.69** |

Out of sample (fit one year, predict the other given the actual national
House vote): Brier 0.041 both ways; RMSE 7.1–7.2; but a **mean error of
+4.6 / −3.8 points** — the year intercept sat 1.7 points below the national
margin in 2018 and 2.5 above it in 2022. That instability is real
(composition of uncontested seats, where each party over- or
under-performs) and is why the simulator carries a House-wide translation
error. The pooled fit, not either single year, sets the parameters.

Caveats: lean in 2022 uses 2020 only (no 2016 results exist on the 2022
lines); fundraising uses final cycle totals, which include some
post-election money; two midterms are a small sample for the translation
error.

## 8b. The statewide polling backtest — how accurate is this average?

The Senate and governor forecasts are mostly polls, so `midterms
backtest` also replays this exact averaging code on every Senate and
governor race of 2014–2024 plus the 2025 New Jersey and Virginia
governorships — 323 races with polls and a Republican vs non-Republican
result — as of three days before each election, with every adjustment fit
on that year's polls only, and compares with the results
(`data/backtest_statewide.yaml`).

| cycle | races | mean miss (D-side minus average) | RMSE |
|---|---:|---:|---:|
| 2014 | 68 | −4.14 | 6.90 |
| 2016 | 42 | −2.64 | 7.62 |
| 2018 | 65 | +0.36 | 5.27 |
| 2020 | 42 | −7.17 | 9.23 |
| 2022 | 62 | −2.43 | 6.60 |
| 2024 | 42 | −5.00 | 6.53 |
| 2025 (NJ, VA) | 2 | +6.80 | 7.10 |

What it changed:

1. **Race-level error, fit.** Net of each cycle's shared miss, the spread
   is 5.8 points. The old fixed race-level term was right for well-polled
   races and badly overconfident for thinly polled ones (errors 1.5× the
   stated sd with fewer than six polls). The shared + per-poll structure in
   §2, fit by maximum likelihood under the simulator's own t(6) error, is
   calibrated across poll counts (standardized error 0.8–1.1 in every
   bucket) and raises the log-likelihood by 16 units.
2. **The national error, sized.** Net of race-level noise, the cycle-level
   miss has an sd of ~3.6 across the midterm-like cycles (2014, 2018, 2022,
   2025) and ~4.3 across all; the national sd is 3.5 (it was 2.8).
3. **The national error, *not* signed.** Polls overstated the D-side in
   five of six cycles from 2014 to 2024, and a leave-one-cycle-out test
   shows that shading every average halfway toward Republicans would have
   scored better in those years (Brier 0.048 vs 0.055) — even in 2018.
   But the misses track context, not party: the large ones came with Trump
   on the ballot (2016, 2020, 2024); midterms ran −4.1, +0.4, −2.4; and the
   two contests polled under the current administration, the 2025 New
   Jersey and Virginia governorships, *under*stated Democrats by 8.8 and
   4.8 points. A correction fit to 2014–2024 would have made 2025 worse.
   The model therefore assumes no direction and widens instead; the
   scorecard will show whether that was right.

Scores on the same races (probabilities from the forecast's own
uncertainty): polls alone Brier 0.0550 · ratings alone 0.0535 · **polls +
ratings 0.0524** (log loss 0.163, calls 92%) — the blend beats either
input, which is the case for Deluxe.

Caveats: quality weights use Silver Bulletin's 2026 ratings, which were
themselves informed by these results (a mild leak); no trend-line
adjustment (it needs each year's generic-ballot series; negligible three
days out); and the national loading for the House (0.7) is a prior — no
generic-ballot backtest yet.

## 9. Known limitations

- **Louisiana's House races** are a majority-vote first round on Nov 3 with
  a Dec 12 runoff; the model forecasts the eventual party winner and treats
  the race as D-side vs. R-side. **Georgia** requires a majority (runoff
  Dec 1). **Maine and Alaska** use ranked-choice voting; the model uses
  final-round polls where published.
- **Three-way races** (Montana Senate, Maine governor) are compressed into
  two sides; two-party normalization exaggerates margins when a third
  candidate is large.
- **No demographic correlation.** FiveThirtyEight correlated errors across
  demographically similar districts; here errors are shared only by region
  and state. No ACS product yet covers the redrawn districts.
- **No candidate-quality, scandal or ideology terms** — only lean,
  incumbency and money.
- **Wikipedia is the poll ledger.** It is the most complete open compilation
  (more complete than VoteHub's public API), but editors make typos; the
  pipeline drops impossible rows and pins revisions, and `make verify`
  checks every value's range, but a mis-keyed number can get through.
- **Senate and governor fundamentals are priors** (they carry little
  weight next to the polls), and the rating-to-margin map is calibrated to
  published hit rates rather than fit here.
- **The national error is symmetric** — a choice, argued in §8b, not an
  oversight. Markets price Republicans higher than this model does in the
  close Senate races, consistent with expecting a 2016/2020-style miss.
