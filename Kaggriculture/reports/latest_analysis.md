# Latest Analysis

Real smoke-test run (not LLM-generated -- `ANTHROPIC_API_KEY` wasn't set, this
is the raw `analysis/profit_breakdown.aggregate()` output written up by hand
to confirm the pipeline produces sane numbers against the actual
`kaggle_environments` "kaggriculture" env). 30 full 720-turn games,
baseline (`starter_agent` carrot loop) vs. the built-in `"random"` opponent.

## Summary

Baseline nets ~$499 average profit on a $3000 starting bank (mean final
bank $3498.7, stdev $8.4 -- almost no variance, since a single-tile carrot
loop against a random opponent has little exposure to opponent behavior).

## Top failure

Every single one of the 30 games (`30x`) bought a new carrot seed around
day 28 that could never mature before the season ends on day 29
(`max_yield_day` for carrot is 3, so planting needs `days_left >= 3`; the
baseline's only gate is "do I have $20", not "is there time left"). That
wasted seed cost ($20/game) is the entirety of `avg_late_investment_loss`.

## Cost structure

100% of spend is seed cost ($6600 total / 30 games = $220/game, i.e. 11
carrot seeds bought per game) -- no worker, animal, or land spend at all,
since the baseline never hires, never raises animals, and never buys land.
That's a much bigger strategic gap than the late-buy issue above: a
single-tile, single-crop, single-farmer strategy leaves almost the entire
game (both land and diversification) untouched.

## Action patterns

670 of 720 turns (93%) are idle (`PASS`) -- expected for a one-tile
strategy with no hired hands, but a strong signal that hiring farm hands
or buying land (currently completely unused) would let the agent act more
often per turn instead of just watching one carrot grow.

## Next proposal implemented and tested (round 1, rejected)

"Stop buying a carrot seed once there isn't enough season left for it to
mature" (`submissions/candidate/main.py`). A/B tested head-to-head against
baseline over 30 full games (see `reports/experiment_history.csv`):
consistent +$20/game (100% win rate, zero variance) but **rejected** by
`evaluation/acceptance_gate.py` -- `mean_profit_delta` of $20 is nowhere
near the $5000 bar. Correctly rejected: real, but too small on its own.
The cost-structure finding above (never expanding beyond one tile) is the
much bigger opportunity for the next proposal.

## Round 2 (accepted, promoted to baseline)

Acted on the cost-structure finding: multi-unit scale-up (farmer + 10
hired hands, each tending its own melon/wheat tile in the starting
quadrant instead of one carrot tile idling 93% of turns). A/B tested over
10 real 720-turn games against the old single-tile baseline: **+$22,433
mean profit, 100% win rate, zero crashes/invalid actions -- ACCEPTED**,
promoted to `submissions/baseline/main.py`.

Also benchmarked (outside the acceptance gate, which only compares our own
baseline vs. candidate) against a real, much stronger public solution
(`opponents/submission_27`, decoded and analyzed -- see
`opponents/README.md`): went from a ~53x deficit ($3,504 vs. $186,169) to
a ~9x deficit (~$20,000 vs. ~$180,000). Real progress, still losing.

## Round 3 (accepted, promoted to baseline)

Added animal husbandry: a dedicated caretaker (the 10th hired hand) builds
2 pastures next to the shed, buys/places 1 cow + 1 sheep, and runs a
daily fetch-wheat -> feed -> care -> harvest -> collect-fertilizer loop.
A/B tested over 10 real games against the v3 (crop-only) baseline:
**+$9,935 mean profit, 100% win rate, zero crashes -- ACCEPTED**, promoted.

vs. `opponents/submission_27`: deficit narrowed further, from ~9x to ~6x
(~$28,000 vs. ~$175,000 average across 3 seeds). `opponents/README.md`
has the full table and the next levers (more animals, land expansion,
ongoing crops).

## Round 4 (rejected, twice -- baseline unchanged)

Tried scaling from 1 cow + 1 sheep to submission_27's scale (aimed for 6
animals: 4 cow + 2 sheep). Two tuned attempts, both A/B tested over 10
real games against the v4 baseline and both **REJECTED**:

- Attempt 1: -$3,557 mean profit. Attempt 2 (added a $1,500 cash reserve
  + staggered the second caretaker's purchases): -$3,561 mean profit,
  essentially unchanged.

Revenue actually went *up* both times (total revenue ~$44,750 vs. v4's
$40,575, milk+wool alone $23,133 vs. $14,448) but costs rose more:
2 of the second caretaker's 3 animals escaped on day 13 in both attempts,
each escape a total loss of the $400-500 purchase.

**Attempt 3** fixed the actual bug (found by calling `_caretaker_action`
directly against the exact game state, not by theorizing): the caretaker
checked "place a new animal" *before* "feed animals I already have", so
whenever one slot's purchase was delayed it got stuck retrying every turn
and never got to feed the ones it already had. Reordered to
feed-existing-first: `escaped_animals` dropped to 0 and `animal_cost`
landed exactly at $2,600 (no replacement buys) -- but mean profit vs. v4
got *worse* (-$4,870). With the bug gone, the real cause is now clear:
milk+wool net profit (revenue minus feed minus purchase) was actually
*higher* than v4's ($13,808 vs. $11,492) -- animal husbandry itself
scales fine. The one melon tile given up to fund the second caretaker
was worth ~$6,943 in revenue over the game, more than double what the
extra animals net. **Melon is worth more per hand than a second
caretaker, given animals' recurring feed cost** -- more animals only pays
if it doesn't cost a crop tile to get them.

`submissions/baseline/main.py` is unchanged (still v4);
`submissions/candidate/main.py` holds attempt 3's (bug-fixed but still
rejected) code for reference.

## Round 5 (close, still rejected -- baseline unchanged)

Acted on round 4's lever: gave the farmer dual duty (crop + animals in
its idle time) instead of dedicating a full hand to a second caretaker,
so animals stop costing a melon tile. Best tuning -- farmer tends 1 extra
cow + 1 extra sheep, on top of its own crop tile and the existing hand
caretaker's 1 cow + 1 sheep -- scored **+$4,453 mean profit, 100% win
rate, zero crashes, zero escaped animals, zero dead crops over 20 real
games**. The best and safest result of this entire investigation, but
still short of the $5,000 acceptance bar -- correctly REJECTED. Adding a
3rd animal to either the farmer (neglected its own crop, 2 dead crops) or
the hand caretaker (pushed every crop tile 1 tile farther from the shed,
-$4,482) made things worse, so 2+2 is this design's ceiling.

vs. `opponents/submission_27`: deficit narrowed slightly further to
~5.3-5.5x. Full numbers in `opponents/README.md`'s "Round 5" section.

## Round 6 (accepted, promoted to baseline as v7)

Round 5's candidate already had both caretakers calling
`COLLECT_FERTILIZER`, but `FERTILIZER` was never in `SELLABLE` -- it sat
dead in the shed all game (74 units at game end in one test). Adding it
was a one-line, zero-risk fix worth +$6,958 revenue on its own. Bundled
with round 5's farmer dual duty and measured together against v4 over 15
real games: **+$17,150 mean profit, 100% win rate, zero crashes --
ACCEPTED**, promoted as v7.

vs. `opponents/submission_27`: deficit narrowed from ~6x to **~4.0-4.5x**.

## Round 7 (manually promoted to baseline as v8 -- gate said reject)

Investigating a leftover un-placed sheep in v7's shed found the same bug
class as round 4, in a new spot: a weed can spawn on an animal tile
before its pasture is built there (weeds only check `is None`, and a
WEED dict isn't `None`), permanently blocking that slot since "build
pasture" never matches a WEED. Added a DIG step below the feed loop.

Measured over 15 real games against v7: 14 showed exactly zero
difference (the weed-on-pasture event is rare -- 0.005/tile/day across
~4 tiles) and 1 showed +$8,858. Mean profit landed at only +$591,
correctly failing the gate's $5,000 bar -- but no game was ever worse
than v7 (`worst_scenario_delta` was exactly $0.0). Asked the user how to
treat a fix that provably cannot backfire but averages below the bar;
**they chose to promote it manually**, reasoning that the $5,000 bar
exists to catch risky strategy changes, not to block strictly
non-negative bug fixes. `reports/experiment_history.csv` still shows the
gate's actual verdict (REJECTED) for this entry -- it's a log of what the
gate said, not of promotion decisions.

vs. `opponents/submission_27`: ~4.0-4.1x deficit, essentially unchanged
from v7 since the fix's benefit is real but rare.

## Round 8 (accepted, promoted to baseline as v9)

User asked for a submission_27-style frozen action script, built via
actual offline search rather than freezing v8's existing trajectory.
Generalized v8 into a `Params`-driven agent
(`experiments/frozen_route/parametrized_agent.py`, verified
byte-identical to v8 at defaults) and ran 4 rounds of search over wheat
tile count, cash reserve, hire ramp, target hand count, and secondary
crop. Winner: `wheat_tiles=0` (all-melon crop tiles) + `cash_reserve=0`,
$64,595 mean over 5 seeds vs. v8's $53,221 -- validated over 15 solo
seeds (mean $64,749, zero crashes/dead-crops/escapes) and head-to-head
against v8 (**+$12,311 mean profit, 100% win rate, zero crashes --
ACCEPTED**), promoted as v9.

Then froze the winning policy's actual decisions into a fixed action
list with a submission_27-style weed-repair layer, as originally
requested -- and it measured *worse*: mean $62,949 vs. the same policy
run reactively at $64,749, with one seed in 15 cratering to $43,099 (3
dead crops) because weed-repair only covers a scripted PLANT/BUILD
landing on a weed, not the other ways a different game's random weed
spawns can desync an already-planted crop's watering from what the
recording assumed. Deployed the winning parameters reactively as v9
instead of the frozen script, which is kept for the record
(`submission_ready/main_frozen.py`) but is not the baseline.

vs. `opponents/submission_27`: deficit narrowed from ~4.0-4.1x to
**~3.5x** (~$47,700-50,600 vs. ~$166,700-176,200 across 3 seeds).
`opponents/README.md`'s "Round 8" section has the full search numbers,
the frozen-vs-reactive comparison table, and the next levers (land
expansion, adding a third crop alongside all-melon, more free-money
checks like round 6's).

## Round 9 (frozen-route fragility fixed; baseline unchanged)

A first attempt at closing round 8's frozen-vs-reactive gap (a
"crop-safety" pass forcing WATER/HARVEST off live board state) was a
**regression**: re-validating over 15 seeds showed it clobbered scripted
movement whenever an actor merely passed through an unwatered crop
tile, with no way to resync -- mean crashed from $62,971 to $38,743 and
every single game lost a crop (was 1-in-15). Caught before reaching
baseline; reverted.

The user then supplied a second real competitor submission
(`opponents/submission_29`, decoded same as submission_27). Its
weed-repair uses a bounded catch-up window (replay each one-step-earlier
recorded action for a few turns after any DIG-and-retry) instead of a
single retry or a board-reactive override, correctly absorbing the
one-turn cost without permanent drift. Adopted it verbatim in
`experiments/frozen_route/` and regenerated
`submission_ready/main_frozen.py`: re-validated over the same 15 seeds,
frozen now lands at $64,221 mean / $62,648 min / 0 dead crops, within
noise of reactive v9's $64,472 / $62,089 / 0 -- the fragility is gone.
`submissions/baseline/main.py` stays on reactive v9 regardless (no
upside to switching); the frozen artifact is now just a correctly-working
record instead of a known-fragile one.

Also benchmarked v9 against submission_29 (3 seeds): $48,795 vs.
$171,436, ~3.5x deficit -- essentially tied with submission_27 despite
submission_29's more elaborate market-timing logic, reinforcing that
land expansion (not market tricks) is likely the biggest unclaimed lever.
`opponents/README.md`'s "Round 9" and "submission_29" sections have the
full decode, the before/after fix numbers, and updated next levers.

## Round 10 (v9 rejected; submission_29 adopted as the new base)

User rejected continuing the v9 lineage given round 9's benchmark result
and asked to build directly on submission_29 instead, with a specific ask
to find a way to still profit against a mirror opponent (common on the
real leaderboard, since many entries converge on the same strong public
notebooks). `submissions/baseline/main.py` and
`submissions/candidate/main.py` were both replaced with submission_29
verbatim as the new starting point.

## Round 11 (mirror-defense investigated; one safe fix kept, three ideas dropped -- REJECTED by the gate, promotion is the user's call)

Three ideas for beating a mirror opponent, tried and measured in order:

1. Endgame liquidation (spread the final sell-off over ~30 turns instead
   of one terminal dump) -- no edge; a real mirror match showed the shed
   is already empty by the terminal turn, since submission_29 sells
   continuously all game rather than hoarding.
2. Per-item sell-timing shift, delay direction -- first attempt regressed
   badly (mirror match: $54,625 vs. baseline's $151,550) from two bugs
   (selling before the harvest that produces the item; a shifted sell
   landing on a turn already at the engine's 10-order cap and getting
   silently truncated), and even after fixing both plus adding retry logic
   for HIRE/BUY_ANIMAL/BUY_SEED/BUY_LAND (`_purchase_retry` -- found
   necessary after tracing a real game to a missed BUY_ANIMAL costing 2
   sheep), the mirror match was still down ~24%: delaying our sell handed
   the *unshifted* mirror the fresher price on every shared item, exactly
   backwards from the intent.
3. Per-item sell-timing shift, early direction (additive, not
   move-and-replace) -- closed most of the gap (mirror match mean delta
   improved from -$33,424 to **-$7,477**, ~78% better) by adding an early
   sell attempt on top of the untouched original order, letting
   `_safe_market`'s existing live-shed clamp handle safety with no
   separate backlog. Doubling every offset's magnitude produced no further
   improvement (-$7,551, within noise) -- a real plateau. **No version of
   this shift ever reached parity or a positive edge against a true
   mirror**; this game's per-unit lockstep pricing and slow price recovery
   (`_town_consume` pulls back only 1-2 units per interval) apparently
   don't leave room for a within-script timing trick to beat a genuine
   clone.

**Kept: `_purchase_retry` alone**, sell-timing shift removed entirely.
Isolated test against a real mirror (shift neutralized): an exact tie,
mean delta **+$10 over 10 seeds** (sign flipping), plus a healthy
$188,099 mean solo vs. "random" -- a strict, zero-downside hardening fix
against any future cash-flow disruption, kept on that basis alone.
`submissions/candidate/main.py` is now submission_29 + `_purchase_retry`.

The acceptance gate formally **REJECTS** this (mean delta $10, nowhere
near the $5,000 bar) exactly as designed. Unlike round 7's non-negative
bug fix, whether to manually promote a zero-average, zero-downside
hardening fix is left to the user -- `opponents/README.md`'s "Round 11"
section has the full trace and the updated "Remaining levers" (land
expansion is still the best-supported unclaimed lever).

## Round 12 (real #1-player logs analyzed; scaled reactive rebuild stabilized but not competitive; baseline unchanged)

User supplied 5 real Kaggle episode replays featuring "Konstantin03" (the
account in all 5, taken as the current #1 leaderboard player). Both
submission_29 and Konstantin03 independently converge on the same scale
(14 hands, 8 cow + 6 sheep, exactly 2 land purchases, never the 3rd/
priciest quadrant) -- fib-cost math confirms staffing that unclaimed
quadrant would cost $334,480/20 days for 6 more hands, far more than a
few melon tiles could earn back, so round 9's "unclaimed land" lever was
likely a correct non-choice all along, not an oversight. Konstantin03's
own 5 logs are also byte-identical only through day ~7, then diverge on
~94% of remaining turns depending on the opponent -- a genuinely
reactive, state-driven design (this project's own v3-v9 lineage) grafted
onto a frozen bootstrap, not a pure frozen script like submission_29.

Rebuilt v9's reactive architecture at this validated scale in
`experiments/v10_scaled/`. Manual single-seed tuning of the cash-flow
knobs took 7 rounds (each fixing one collapse: ramp too fast, a cash
reserve deadlocking at zero hands, the same trap at a low plateau,
unreliable caretaker hand indices, a ramp threshold too conservative then
too aggressive) without ever converging -- switched to round 8's
multi-seed search methodology instead and found a stable combination
(10 seeds: zero escaped animals, zero dead crops, mean $38,278, worst
case $36,807, vs. the best single-seed guess's mean $20,236/worst case $1).

**Matching scale wasn't enough**: head-to-head vs. submission_29, v10
scores $25,471 vs. $173,622 (~6.8x deficit) -- stable now, but v10 only
grows melon while both strong strategies run melon+wheat+strawberry
together. `submissions/candidate/main.py` stays unchanged
(submission_29 + `_purchase_retry`); `experiments/v10_scaled/` is kept as
a validated research artifact. `opponents/README.md`'s "Round 12" section
has the full trace and adds crop diversification to "Remaining levers"
as the most likely next step for that agent, if revisited.
