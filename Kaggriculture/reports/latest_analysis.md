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
`opponents/README.md`'s "Round 6" and "Round 7" sections have the full
writeup and the next levers (land expansion, ongoing crops, more
free-money checks like round 6's).
