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

## Next proposal implemented and tested

"Stop buying a carrot seed once there isn't enough season left for it to
mature" (`submissions/candidate/main.py`). A/B tested head-to-head against
baseline over 30 full games (see `reports/experiment_history.csv`):
consistent +$20/game (100% win rate, zero variance) but **rejected** by
`evaluation/acceptance_gate.py` -- `mean_profit_delta` of $20 is nowhere
near the $5000 bar. Correctly rejected: real, but too small on its own.
The cost-structure finding above (never expanding beyond one tile) is the
much bigger opportunity for the next proposal.
