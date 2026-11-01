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

**The VoteHub supplement.** Wikipedia's tables miss some polls, so
VoteHub's public poll feed (CC BY 4.0) fills the gaps. A VoteHub poll of a
race's two sides is added only if no Wikipedia poll of that race could be
the same poll: none from the same pollster or sponsor ending within 7
days, and none ending within 4 days with the same sample size or the same
topline (both shares within half a point). Doubt counts as a match:
counting a poll twice doubles its weight, while skipping one costs a
little information. On Nov 1 the feed had 860 matchup polls of 2026 races;
830 were already on Wikipedia, and 30 were added (21 inside the 150-day
window, the weightiest a late Remington poll of AL-02, a coin-flip race
whose only other polls were three summer Democratic internals). `make
verify` re-checks that no VoteHub poll duplicates a Wikipedia one.

**Fabricated polls** never enter: pollsters that admitted making up their
results are excluded from every source (`curated/excluded_pollsters.yaml`,
with the evidence). This cycle that means Wedgewood Polls (exposed by
FiftyPlusOne on Oct 20) and Median Strategies (August). Wikipedia's editors
and the major aggregators had already removed Wedgewood's polls, but
VoteHub's public feed still carried eleven on Nov 1, and one would have
been nearly half of Mississippi's Senate average. SoCal Strategies,
disputed but not shown to have fabricated anything, stays at the default
weight for an unrated pollster (its five polls carry under 0.4% of any
race's average).

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
anchors 0 → 0, 0.5 → 2.5, 1 → 5.5, 2 → 11, 3 → 22 points **× k = 1.25**,
with sd 5.5 (×1.3 when the race is polled, since raters read the same
polls). The rescale k is fit on 318 rated statewide races, 2014–2025: the
raters' Lean races were won by 8.1 points on average, not 5.5, and their
Solid races by 28 (k is 1.22–1.28 whichever cycle is held out; it improves
the ratings' and the blend's out-of-sample Brier). The rating sd is *not*
fit, on purpose: the leave-one-cycle-out loss keeps falling as it shrinks —
"trust the raters over the polls" — because the raters were more cautious
than polls that overstated Democrats in 2014–2024. That is the directional
correction §8b declines; 2025's misses ran the other way. Seven other
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
uncertainty and the rescaled rating map of §5): polls alone Brier 0.055 /
log loss 0.174 · ratings alone 0.050 / 0.160 · **polls + ratings 0.052 /
0.159**. Both rating-based scores beat polls alone. The raters' edge over
the blend on Brier is the same cautious-rater effect that §5 declines to
lean on; the blend has the best log loss, which punishes confident misses
hardest.

**The generic ballot, checked the same way** (FiveThirtyEight's archived
generic-ballot polls, CC BY, averaged by this code three days out):

| cycle | average | national House vote | miss | district baseline (§8) | miss |
|---|---:|---:|---:|---:|---:|
| 2018 | D+7.9 | D+8.8 | +0.9 | D+7.1 | −0.8 |
| 2020 | D+7.8 | D+2.6 | −5.2 | — | — |
| 2022 | D−0.2 | R+3.1 | −2.9 | R+0.6 | −0.4 |

Its misses against the vote ran ~0.8× the statewide misses, in the same
direction — so the House does share the national polling error. Against
the district baseline the House model actually uses, the generic ballot
missed by under a point in both midterms (the uncontested-seat distortions
in the raw vote cancel out). The House keeps its loading of 0.7 and its
2.1-point translation term anyway: two midterms are too few to fit, and
2020 shows a five-point miss is possible. If anything, the House interval
is wide.

Caveats: quality weights use Silver Bulletin's 2026 ratings, which were
themselves informed by these results (a mild leak); no trend-line
adjustment (it needs each year's generic-ballot series; negligible three
days out).

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
- **Wikipedia is the poll ledger; VoteHub only fills its gaps.** Wikipedia
  is the most complete open compilation (it already had 830 of the 860
  matchup polls in VoteHub's feed), but editors make typos; the pipeline
  drops impossible rows and pins revisions, and `make verify` checks every
  value's range, but a mis-keyed number can get through. A poll Wikipedia
  and VoteHub list under different names *and* different dates, sizes and
  numbers would be counted twice; the matching rule makes that unlikely,
  not impossible. And a fabricator not yet exposed is weighted like any
  unrated pollster.
- **Senate and governor fundamentals are priors** (they carry little
  weight next to the polls), and the rating-to-margin map is calibrated to
  published hit rates rather than fit here.
- **The national error is symmetric** — a choice, argued in §8b, not an
  oversight. Markets price Republicans higher than this model does in the
  close Senate races, consistent with expecting a 2016/2020-style miss.

## 10. Election night: the forecast, given the calls

`midterms live` (`model/live.py`) keeps the forecast of record exactly as
frozen and asks what it implies once some races are called. A race's
margin is `mu + A·θ + sd·ε` (§7), where θ holds the errors races share —
national, four regions, fifty states and the House-wide shift — and ε is
the race's own error. Given θ the races are independent, so a call changes
the rest of the map only through θ:

    p(θ | calls) ∝ p(θ) · Π_called P(the called side wins | θ)

and P(D-side wins | θ) is a Student-t CDF of `(mu + A·θ) / sd`. θ is drawn
by importance sampling — the national error from a t proposal with
heavier tails than its prior, the other 55 errors from a Gaussian fitted
to the posterior's mode and curvature (Newton's method), then refitted to
the weighted draws — and every draw is weighted exactly by
`p(θ)·Π P(y|θ) / q(θ)`. The uncalled races are simulated from the
weighted draws; `ess`, the effective number of draws, travels with every
number. With no calls the engine reproduces the forecast within
simulation error, and the site shows the forecast itself until the
first contested call.

Two choices keep it from overreacting:

- **Calls only, never partial counts.** Which counties and which kinds of
  ballots report first differs by state, and early margins swing on it;
  the model has no way to know what is still out. A call is the decision
  desk's statement that the count can no longer change the winner.
- **A call says who won, not by how much,** and a race not yet called is
  treated as saying nothing. Both throw information away, so the update
  is, if anything, too cautious early in the night.

Calls and counts come from civicAPI (counts from secretaries of state,
calls by its own decision desk; sources.md §7). The scorecard does not
use them: it resolves races from Wikipedia's results boxes, as before.
The two are cross-checked: a race they call differently is shown as
disputed and left out of the update; a race only Wikipedia has settled
counts as called; and if civicAPI is unreachable, the committed copy
carries on from Wikipedia's results boxes alone.

**Check** (`midterms live --check N`): N election nights drawn from the
forecast itself, each revealed the way a decision desk would — by poll
closing, lopsided races first, anything within a point only the next day —
with the live control probabilities scored at each hour against how the
night actually ended. On 500 such nights (2,000 weighted draws; Brier
score, lower is better):

| | pre-election | 8:30 PM ET | 9:30 PM | 10:30 PM | 1 AM |
|---|---|---|---|---|---|
| races called (of 489) | 0 | 265 | 356 | 394 | 476 |
| House control | 0.058 | 0.030 | 0.022 | 0.016 | 0.004 |
| Senate control | 0.198 | 0.113 | 0.091 | 0.059 | 0.049 |
| Governors (majority) | 0.177 | 0.104 | 0.081 | 0.069 | 0.036 |

The effective number of draws stays near 85% of the total all night.
Averaged over nights, a well-calibrated update must return the
pre-election probability; here the live probabilities average 0–1.4
points below it (House about 1 point, 1.5 standard errors; Senate and
governors within noise). That small lean toward Republicans is the price
of ignoring which races are still out, and the check's decision desk is
stylized, so read the live numbers as a careful update, not an exact one.
`midterms live --check 500` reproduces the table.
