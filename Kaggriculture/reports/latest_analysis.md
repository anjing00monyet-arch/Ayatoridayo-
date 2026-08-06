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
rejected) code for reference. `opponents/README.md`'s "Round 4" section
has the full writeup and the next lever: give the farmer dual duty
(crop + a couple of animals in its idle time, ~93% idle per the very
first analysis in this file) instead of dedicating a full hand to a
second caretaker, so animals stop costing a melon tile to acquire.
