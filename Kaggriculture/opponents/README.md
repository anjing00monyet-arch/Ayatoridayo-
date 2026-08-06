# opponents/

Real third-party Kaggriculture agents kept around as fixed benchmarks --
not part of the improvement loop itself (`evaluation/acceptance_gate.py`
only judges baseline-vs-candidate), but useful as an external strength
check via `game.kaggriculture_env.play_match(our_agent, "opponents/X/main.py", ...)`.

## submission_27

A public solution (docstring credits a "public v20 Notebook" and
prvsiyan's "The Moon Counts Melons" Notebook). Decompiled for analysis
(the `_ACTIONS` blob is base85 + zlib + JSON, not encrypted -- fully
reversible with the standard library) to understand its strategy:

- **Frozen 719-step scripted route**: a precomputed sequence of
  farmer/hand/market actions per turn, presumably produced by offline
  search/optimization. Farm operations (movement, planting, buying,
  hiring, building) do **not** react to the opponent or live game state at
  all -- only the step index.
- **Weed repair**: if the script's next PLANT/BUILD_PASTURE would land on
  a weed tile, DIG first and replay the intended action a few turns later.
- **Mirror detection + market front-running**: a small logistic-regression
  model estimates whether the opponent's farm looks like a mirror of its
  own, then reorders (not resizes) its scripted SELL orders by live price
  x opponent-exposure so the highest-value items go first when a turn's
  orders exceed `maxMarketOrdersPerTurn`.
- **Terminal dump-sell**: sells everything left in the shed on the last
  turn (unsold inventory doesn't count toward the final score).
- Decoded schedule: 719 total actions, 62 BUY_SEED (mostly wheat, then
  melon and strawberry from day ~4), 10 BUY_ANIMAL (8 cow, 2 sheep -- milk
  and wool are steady, low-marginal-cost income once placed and fed,
  unlike crops which need a fresh seed + full grow cycle every harvest),
  284 HIRE calls (a large, sustained hand roster), and 2 BUY_LAND buys
  (day ~7 and ~11, expanding to 3 of the 4 quadrants).

## Benchmark result

`submissions/baseline/main.py` (v3: 10 hired hands + farmer, each
permanently tending one melon/wheat tile in the starting quadrant, no
land purchase or animals) vs. `opponents/submission_27/main.py`, 3 seeds,
720-turn games:

| seed | our final bank | submission_27 final bank |
|---|---|---|
| 0 | $19,892 | $174,326 |
| 1 | $20,073 | $188,359 |
| 2 | $19,950 | $188,848 |

For comparison, the single-tile carrot loop (the baseline before this
session) scored ~$3,504 against the same opponent -- so the multi-unit
scale-up closed the gap from a ~53x deficit to a ~9x deficit, but does not
win. The decoded schedule above points at the two biggest remaining
levers, in rough order of expected impact:

1. **Animal husbandry** (cow/sheep -> milk/wool): compounding income from
   one $400-500 purchase instead of paying a fresh seed cost every
   harvest cycle. Not yet implemented here -- it requires a unit to
   `PICKUP` the animal from the shed (animals bought via `BUY_ANIMAL`
   land in the shed, not directly on a tile) and carry `WHEAT` in
   inventory daily to `FEED` (unlike seeds, wheat for feeding is **not**
   auto-available -- see `_apply_unit_action`'s `FEED` handler in the
   installed `kaggle_environments` package), i.e. a genuine daily
   shed-commute loop per animal, not a simple PLANT/WATER/HARVEST cycle.
2. **Land expansion**: more tiles support more hands productively; we
   have headroom in the current 24-tile NW quadrant before this matters.

Neither was implemented in this pass to avoid shipping unvalidated,
half-tested logic under time pressure -- see the task history / git log
for the reasoning. They're the natural next candidate proposals.
