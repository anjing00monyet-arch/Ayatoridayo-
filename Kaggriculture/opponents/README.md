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

## Benchmark results

vs. `opponents/submission_27/main.py`, 3 seeds, 720-turn games:

| version | our final bank | submission_27 final bank | deficit |
|---|---|---|---|
| single-tile carrot loop (pre-session baseline) | $3,504 | $186,169 | ~53x |
| v3: multi-unit crop scale-up (10 hands, melon/wheat) | ~$19,900-20,100 | ~$174,000-189,000 | ~9x |
| v4: v3 + cow/sheep husbandry | ~$27,600-29,700 | ~$163,000-196,000 | ~6x |
| v7: + farmer dual duty + sell fertilizer | ~$40,800-42,900 | ~$172,400-182,900 | ~4.0-4.5x |
| v8: + weed-blocks-pasture fix | ~$42,600-45,100 | ~$172,400-181,100 | ~4.0-4.1x |

Each round closed the gap further but none has won yet.

1. ~~**Animal husbandry** (cow/sheep -> milk/wool)~~ -- **done in v4**:
   compounding income from one $400-500 purchase instead of paying a
   fresh seed cost every harvest cycle. Required a dedicated caretaker
   unit to `PICKUP` the animal from the shed (animals bought via
   `BUY_ANIMAL` land in the shed, not directly on a tile) and physically
   carry `WHEAT` in inventory daily to `FEED` (unlike seeds, wheat for
   feeding is **not** auto-available -- see `_apply_unit_action`'s `FEED`
   handler in the installed `kaggle_environments` package).

## Round 4: scaling animals further (rejected, twice)

Tried to push from v4's 1 cow + 1 sheep toward submission_27's 8 cow + 2
sheep. Three attempts, each measured head-to-head against v4 over 10 real
720-turn games via `evaluation/compare_agents.py`:

1. **TARGET_HANDS 10 -> 18 + 3 caretakers (9 animals) + land purchases.**
   Catastrophic: `HIRE` cost is `mult * fib(n_already_hired_today)`, and
   hands must be re-hired from scratch every day (they disappear
   overnight). Reaching 18 hires in one day costs **$6,764**, vs. $143 for
   10 -- the fib curve, not tile space, is the real ceiling on headcount.
   The run never even reached the caretaker slots (indices 15-17), so
   `animal_cost` stayed exactly $0, and $3,000 got spent on land for
   tiles we never needed. This is also why submission_27 -- despite
   controlling far more land and 10 animals -- only issues ~9-10 HIRE
   calls/day on average (284 total / 30 days), not dozens: the same fib
   ceiling applies to it too.
2. **TARGET_HANDS 10 -> 12 (2 caretakers, 6 animals), no land.** Better,
   but $376/day in hire cost alone during the ~12-day window before melon
   first matures (little income yet) burns the $3,000 starting bank
   before any animal or seed spending is even considered. Hand count
   collapsed unpredictably once cash ran out, leaving tiles/animals
   untended some days -> dead crops, escaped animals, compounding losses.
3. **Kept TARGET_HANDS at 10 (v4's proven $143/day), reallocated 2 of
   those 10 hands from crop tiles to a second caretaker** (6 animals: 4
   cow + 2 sheep, one fewer melon tile) **+ a $1,500 cash reserve** so
   animal purchases can't eat into tomorrow's hire/feed money, **+
   staggering the second caretaker's animal purchases** by extra days.
   This got the hire economics right (hand count stayed flat at 10 all
   game, no more cash collapse) and genuinely raised revenue (milk+wool
   revenue: $23,133 vs. v4's $14,448; total revenue: ~$44,750 vs. v4's
   $40,575) -- but **still lost head-to-head, -$3,561 mean profit,
   REJECTED**. Root cause, found by diffing tile state turn-by-turn: 2 of
   the second caretaker's 3 animals escaped simultaneously on day 13,
   well after the cash-crunch window and well after the staggering delay
   -- i.e. not a money problem at all. The likely cause is the shared
   hand-spawn mechanic (hands respawn "at the least-crowded shed-adjacent
   slot" each day, which varies with how many *other* hands are also
   spawning that day): on a day where that caretaker spawned unusually
   far from its 3 pastures, it may not have had enough of its 24 turns
   left to reach and feed all three, missing 2 consecutive days for the
   same 2 animals. The one-time $400-500 purchase becomes a total loss on
   escape, which combined with 6 animals' recurring feed cost (~$150-270/
   day bought via `BUY_PRODUCT`, since growing enough wheat ourselves to
   self-supply would cost more melon tiles than it's worth) outweighed
   the extra revenue.

4. **Fixed the actual escape bug** (attempt 3's code, logic only, no
   economic changes): the caretaker checked "place a new animal" *before*
   "feed animals I already have". Whenever one slot's purchase was
   delayed for *any* reason (the cash reserve, purchase-order timing --
   nothing to do with spawn position, that theory in the previous version
   of this section was wrong), the caretaker got stuck retrying
   PICKUP/PLACE for the pending slot every single turn and never reached
   the daily feed loop for its other, already-placed animals -- which
   then starved. Confirmed via `_caretaker_action(farm, pos, inv, ...)`
   called directly against the exact game state at the turn in question.
   Reordered to feed-existing-first; **`escaped_animals` dropped to 0,
   `animal_cost` landed exactly at the expected $2,600 (no replacement
   purchases)** -- but mean profit vs. v4 got *worse*, -$4,870.

**Real net conclusion**, now isolated from both bugs: with animals never
escaping, milk+wool net profit (revenue minus feed minus purchase) was
**higher** in this version than in v4 ($13,808 vs. $11,492) -- animal
husbandry itself scales fine. The trade made to fund the second
caretaker -- one fewer melon tile -- was the actual loss: that tile was
worth ~$6,943 in melon revenue over the game, more than double what the
extra animals net. **Melon is worth more per hand than a second
caretaker's animals, given animals' recurring feed cost.** More animals
only pays if it doesn't cost a crop tile to get them.

`submissions/baseline/main.py` is still v4 (unchanged); round 4's
bug-fixed-but-still-rejected code was superseded by round 5 below.

## Round 5: farmer dual duty (close, still rejected)

Tested the "give the farmer dual duty" idea from the previous version of
this section: instead of a second *hand* caretaker (which costs a melon
tile), the farmer -- persistent, no daily re-hire/re-walk, idle 93% of
the time even with its own crop tile per the very first analysis in this
repo -- also tends 1-2 animals in its idle time. Priority per turn: crop
action if the crop tile needs something concrete right now (plant/water/
harvest), animal care otherwise. This costs neither a hire slot nor a
crop tile.

Tuning (each measured over 10-20 real games against v4):

- Farmer + 1 extra cow: **+$1,987 mean profit, 100% win rate** -- real,
  consistent, but nowhere near the $5,000 bar.
- Farmer + 2 animals (cow + sheep): **+$4,017 mean profit (10 games),
  +$4,453 (20 games), 100% win rate both times, zero crashes, zero
  escaped animals, zero dead crops.** Best result of the whole
  investigation -- still short of $5,000, correctly REJECTED.
- Farmer + 3 animals: made the farmer neglect its own crop (2 dead crops,
  melon revenue nearly halved) -- 2 is this design's ceiling.
- Hand caretaker + a 3rd animal instead (no crop to neglect, so seemed
  safer): shifted every crop tile 1 tile farther from the shed and lost
  head-to-head, -$4,482 mean profit. The 2 dedicated-hand-caretaker
  animals from v4 were also already near that role's ceiling.
- Loosening the $1,500 cash reserve to $1,000: worse, not better
  (+$3,538 over 15 games) -- $1,500 stands.

**Status**: farmer + 2 animals (cow + sheep) is a real, safe, consistently
positive improvement (100% win rate across every sample taken) but was
still short of the $5,000 bar on its own -- see round 6 for what closed
that gap.

## Round 6: free money already being collected, never sold (accepted)

Round 5's candidate already had both caretakers calling
`COLLECT_FERTILIZER` daily, but `SELLABLE` never included `"FERTILIZER"`
-- every unit collected sat dead in the shed for the rest of the game (74
units at game end in one test run). Adding it to `SELLABLE` was a
one-line, zero-risk change: **+$6,958 revenue** in that same test run.
Bundled with round 5's farmer-dual-duty change and measured together
against v4 over 15 real games: **+$17,150 mean profit, 100% win rate,
zero crashes -- ACCEPTED**, promoted to `submissions/baseline/main.py`
as **v7**.

vs. `opponents/submission_27`: deficit narrowed from ~6x to **~4.0-4.5x**
(~$40,800-42,900 vs. ~$172,400-182,900 across 3 seeds).

## Round 7: a rare but real bug (manually promoted, gate said reject)

Investigating a leftover un-placed sheep sitting in v7's shed at game end
found another instance of the round-4-class bug: weeds only spawn on
tiles that are still exactly `None` (`_spawn_weeds` in the installed
`kaggle_environments` package checks `is None`), but if one spawns on an
animal tile before its pasture gets built there, the tile becomes a WEED
dict -- not `None` -- so the "build pasture" check silently skips it
forever, stranding that animal slot (and whatever was bought for it) for
the rest of the game. Added a DIG step, placed below the daily feed loop
(not above -- the round-4 lesson about acquisition-before-upkeep applies
here too).

Measured over 15 real games against v7: **14 games showed exactly zero
difference** (weed spawn chance is only 0.005/tile/day across ~4 animal
tiles, so most games the bug never triggers) **and 1 game showed
+$8,858** (it did). Mean profit landed at +$591 -- correctly failing the
gate's $5,000 bar given how rare the triggering event is -- but every
single game was `>=` v7, never worse; `worst_scenario_delta` was exactly
$0.0. Presented this to the user as a judgment call (the numeric bar
exists to catch strategy changes that look good on average but can
backfire in some scenario; a fix that provably cannot make any game worse
isn't that kind of change), and **the user chose to promote it manually,
bypassing the gate** -- now **v8** in `submissions/baseline/main.py`.
`reports/experiment_history.csv` still records the gate's own verdict
(REJECTED) for this entry, since that CSV is a log of what the gate
actually said, not of promotion decisions.

vs. `opponents/submission_27`: ~4.0-4.1x deficit, consistent with v7
(the fix's benefit is real but rare, so it barely moves the 3-seed
average).

## Remaining levers (not yet tried)

1. **Land expansion**, once headcount is no longer the constraint it
   looks like it should be -- every version through v8 still fits inside
   the 24-tile NW quadrant, so this hasn't been the actual bottleneck yet.
2. **Ongoing crops (strawberry/tomato)** and **goose/egg** for further
   income diversification, matching submission_27's mix.
3. Look for more "free money already being collected" gaps like round
   6's -- cheap, safe wins are worth checking for before reaching for
   riskier strategy changes.
