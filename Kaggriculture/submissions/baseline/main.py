"""Baseline v8: v7 + fix a rare weed-blocks-pasture-forever bug.

v7 (below) cleared evaluation/acceptance_gate.py against v4 normally
(+$17,150 mean profit, 100% win rate). This version adds one more fix
promoted *manually*, bypassing the gate's $5,000 mean-profit bar: if a
weed spawns on an animal tile before its pasture gets built there
(possible since `weedSpawnChance` checks any still-empty tile, and
pastures/animals can take a few turns to set up), the "build pasture"
check only matches tiles that are exactly `None`, so a WEED there is
silently skipped forever -- stranding that animal slot (and whatever was
bought for it) for the rest of the game. Added a DIG step, below the feed
loop so it can't repeat the earlier "acquisition blocks upkeep" mistake.

Measured over 15 real games: 14 showed exactly zero difference (the rare
weed event -- 0.005/tile/day across ~4 animal tiles -- simply didn't
occur that game) and 1 showed +$8,858 (it did). Mean profit landed at
only +$591 given how rare the event is, correctly failing the gate's
$5,000 bar -- but every single game was >= the old baseline, never worse.
The user opted to bypass the gate for this one on the reasoning that a
provably zero-downside bug fix isn't the kind of change the $5,000 bar
was designed to screen (it exists to catch strategy changes that might
look good on average but backfire in some scenarios; this fix cannot
backfire by construction).

Promoted from submissions/candidate/main.py after clearing
evaluation/acceptance_gate.py against v4: +$17,150 mean profit, 100% win
rate, zero crashes over 15 real 720-turn games (see
reports/experiment_history.csv). Two changes bundled together:

1. Farmer dual duty (round 5, see opponents/README.md): +$4,453 mean
   profit on its own, still short of the acceptance bar.
2. Selling collected FERTILIZER (round 6): both caretakers already
   called COLLECT_FERTILIZER, but `SELLABLE` never included it, so it sat
   dead in the shed all game (74 units at game end in one test run,
   completely wasted). Adding it to `SELLABLE` alone was worth +$6,958
   revenue in that same test run -- free money that was already being
   collected, just never sold.

Round 4 (see opponents/README.md and reports/latest_analysis.md) tried
scaling from v4's 1 cow + 1 sheep toward submission_27's 8 cow + 2 sheep
by reallocating 2 of the 10 hands into a second caretaker (6 animals
total). After fixing two real bugs (a cash-flow collapse, then a
feed-priority bug that caused animals to starve), the clean, bug-free
result was still a net loss vs. v4: the melon tile given up to free a
hand for the second caretaker was worth ~$6,943 over the game, more than
double the ~$2,316 the extra animals actually netted once feed cost is
counted. Animal husbandry itself was fine (its net profit was *higher*
than v4's) -- the problem was paying for it with a melon tile.

This version doesn't reallocate anything. It restores v4's exact
crop/hand-caretaker layout (farmer + 9 hands on crop tiles, 1 dedicated
hand caretaker tending 1 cow + 1 sheep) and adds one more cow tended by
the farmer itself, in the farmer's own idle time. The farmer is
persistent (never needs the daily re-hire + re-walk-back-to-position that
costs hands time) and, per the very first analysis in this repo, was idle
93% of the time even with a crop tile to tend -- so a second animal here
costs neither hire budget nor a crop tile. Each turn the farmer checks
its crop tile first (plant/water/harvest whenever something concrete
needs doing there) and only spends idle turns on animal care when the
crop needs nothing this instant -- it must never let animal-tending
travel cause it to miss its own crop's daily watering.

Do not change the `agent(observation) -> action` signature or the action
return shape -- that is the official Kaggle submission API. See
submissions/README.md and game/README.md.
"""
from __future__ import annotations

from collections import Counter
from typing import Any

from game.tables import ANIMALS, CROPS, hire_cost

Observation = dict[str, Any]
Action = dict[str, Any]

TARGET_HANDS = 10
HIRE_RAMP_PER_DAY = 3  # stagger hiring so planting/harvest timing spreads out
CARETAKER_HAND_INDEX = TARGET_HANDS - 1  # last hired hand tends animals, not crops
CASH_RESERVE = 1500  # never let discretionary spend (animals) risk tomorrow's hire/feed costs

SHED_TILE = (4, 4)  # only shed-adjacent tile guaranteed unlocked from turn 0


def _by_distance(tiles):
    return sorted(tiles, key=lambda p: abs(p[0] - SHED_TILE[0]) + abs(p[1] - SHED_TILE[1]))


_NW_TILES = _by_distance((x, y) for x in range(5) for y in range(5) if (x, y) != SHED_TILE)

HAND_ANIMAL_TILES = _NW_TILES[:2]
HAND_ANIMAL_PLAN = ["COW", "SHEEP"]  # tended by the dedicated hand caretaker
FARMER_ANIMAL_TILES = _NW_TILES[2:4]
FARMER_ANIMAL_PLAN = ["COW", "SHEEP"]  # tended by the farmer itself, in its idle time
# A 3rd animal on either the farmer (neglected its own crop -- 2 dead
# crops, melon revenue nearly halved) or the hand caretaker (shifted every
# crop tile 1 tile farther from the shed and lost head-to-head, -$4,482
# mean profit) was tried and made things worse. 2+2 is this design's peak.

ALL_ANIMAL_TILES = HAND_ANIMAL_TILES + FARMER_ANIMAL_TILES
ALL_ANIMAL_PLAN = HAND_ANIMAL_PLAN + FARMER_ANIMAL_PLAN

# Crop tenants fill the remaining NW tiles (plenty -- 10 crop tenders vs.
# 21 leftover NW tiles once 3 are reserved for animals).
CROP_TILES = _NW_TILES[len(ALL_ANIMAL_TILES) :]
# First few assigned crop units run wheat for early cash flow (also feeds
# the animals); the rest run melon.
CROP_PLAN = ["WHEAT"] * 4 + ["MELON"] * (len(CROP_TILES) - 4)
SELLABLE = ("WHEAT", "MELON", "CARROT", "STRAWBERRY", "TOMATO", "MILK", "WOOL", "FERTILIZER")

_STATE = {0: {}, 1: {}}


def _game_state(seat: int, step: int, day: int) -> dict[str, Any]:
    game = _STATE[seat]
    if step == 0 or step < game.get("last_step", -1):
        game = {"last_step": step, "unit_tile": {}, "unit_crop": {}, "ramp_day": -1, "ramp_target": 0}
        _STATE[seat] = game
    game["last_step"] = step
    # `hands` resets to 0 every day (must be re-hired daily), so the hiring
    # target has to be tracked here rather than derived from the current
    # (daily-reset) hand count -- otherwise it never grows past
    # HIRE_RAMP_PER_DAY.
    if day > game["ramp_day"]:
        game["ramp_day"] = day
        game["ramp_target"] = min(TARGET_HANDS, game["ramp_target"] + HIRE_RAMP_PER_DAY)
    return game


def _assign_crop(game: dict[str, Any], unit_id: Any) -> tuple[tuple[int, int] | None, str | None]:
    if unit_id not in game["unit_tile"]:
        index = len(game["unit_tile"])
        if index >= len(CROP_TILES):
            return None, None
        game["unit_tile"][unit_id] = CROP_TILES[index]
        game["unit_crop"][unit_id] = CROP_PLAN[index]
    return game["unit_tile"][unit_id], game["unit_crop"][unit_id]


def _move_toward(pos: tuple[int, int], target: tuple[int, int]) -> str:
    x, y = pos
    tx, ty = target
    if x != tx:
        return "EAST" if tx > x else "WEST"
    return "SOUTH" if ty > y else "NORTH"


def _crop_needs_attention(farm, day, target, crop) -> bool:
    """Whether the crop tile has something concrete to do right now --
    used by the farmer to decide crop duty vs. animal duty without first
    forcing a move back to the tile just to check.
    """
    tile = farm["tiles"][target[1]][target[0]]
    if tile is None:
        return True  # either plant now, or register the seed shortfall
    if isinstance(tile, dict) and tile.get("kind") == "PLANT" and tile.get("crop") == crop:
        age = day - tile["planted_day"]
        return age >= CROPS[crop]["max_yield_day"] or not tile.get("watered_today")
    if isinstance(tile, dict) and tile.get("kind") == "WEED":
        return True
    return False


def _crop_tile_action(farm, day, pos, target, crop, available_seeds, seed_shortfall):
    if pos != target:
        return [_move_toward(pos, target)]
    tile = farm["tiles"][target[1]][target[0]]
    if tile is None:
        if available_seeds.get(crop, 0) > 0:
            available_seeds[crop] -= 1
            return ["PLANT", crop]
        seed_shortfall[crop] = seed_shortfall.get(crop, 0) + 1
        return ["PASS"]
    if isinstance(tile, dict) and tile.get("kind") == "PLANT" and tile.get("crop") == crop:
        age = day - tile["planted_day"]
        if age >= CROPS[crop]["max_yield_day"]:
            return ["HARVEST"]
        if not tile.get("watered_today"):
            return ["WATER"]
        return ["PASS"]
    if isinstance(tile, dict) and tile.get("kind") == "WEED":
        return ["DIG"]
    return ["PASS"]


def _caretaker_action(farm, pos, unit_inventory, my_tiles, my_plan):
    """State-driven: derives the next move purely from current tile/
    inventory state for this group of animals, checked in priority order.
    Self-correcting -- no memory of "where it was headed" needed.

    Feeding animals *already* placed is checked before placing a *new*
    one -- an earlier version got this backwards and starved animals
    while stuck retrying a delayed purchase. See opponents/README.md's
    "Round 4" section.
    """
    tiles = farm["tiles"]
    wheat_held = unit_inventory.get("WHEAT", 0)

    # 1. Daily loop for animals I already have: feed first (basic needs),
    # then care, then collect. Takes priority over any setup work below --
    # an earlier version put "acquire a new animal" first and starved
    # existing animals while stuck retrying a delayed purchase. See
    # opponents/README.md's "Round 4" section.
    for (tx, ty), animal in zip(my_tiles, my_plan):
        tile = tiles[ty][tx]
        if not (isinstance(tile, dict) and tile.get("animal")):
            continue
        if not tile.get("fed_today"):
            if wheat_held > 0:
                if pos != (tx, ty):
                    return [_move_toward(pos, (tx, ty))]
                return ["FEED"]
            if pos != SHED_TILE:
                return [_move_toward(pos, SHED_TILE)]
            return ["PICKUP", "WHEAT", len(my_plan)]
        if not tile.get("cared_today"):
            if pos != (tx, ty):
                return [_move_toward(pos, (tx, ty))]
            return ["CARE"]
        if tile.get("yield_units", 0) > 0:
            if pos != (tx, ty):
                return [_move_toward(pos, (tx, ty))]
            return ["HARVEST"]
        if tile.get("fertilizer_available"):
            if pos != (tx, ty):
                return [_move_toward(pos, (tx, ty))]
            return ["COLLECT_FERTILIZER"]

    # 2. Clear any weed that spawned on one of my tiles before it got
    # built. Weeds only spawn on tiles that are still `None` (empty), and
    # once one lands here it isn't `None` anymore -- the "build pasture"
    # check below never matches a WEED dict, so without this the slot (and
    # whatever animal was bought for it) is stuck idle for the rest of the
    # game. Found by inspecting a leftover un-placed sheep sitting in the
    # shed at game end. Setup work, so it stays below the feed loop above.
    for tx, ty in my_tiles:
        tile = tiles[ty][tx]
        if isinstance(tile, dict) and tile.get("kind") == "WEED":
            if pos != (tx, ty):
                return [_move_toward(pos, (tx, ty))]
            return ["DIG"]

    # 3. Build any un-built pasture in my group.
    for tx, ty in my_tiles:
        if tiles[ty][tx] is None:
            if pos != (tx, ty):
                return [_move_toward(pos, (tx, ty))]
            return ["BUILD_PASTURE"]

    # 4. Only once every existing animal's daily needs are met: place any
    # animal that's been bought but isn't on its pasture yet.
    for (tx, ty), animal in zip(my_tiles, my_plan):
        tile = tiles[ty][tx]
        if isinstance(tile, dict) and tile.get("kind") == "PASTURE" and not tile.get("animal"):
            if unit_inventory.get(animal, 0) > 0:
                if pos != (tx, ty):
                    return [_move_toward(pos, (tx, ty))]
                return ["PLACE", animal]
            if pos != SHED_TILE:
                return [_move_toward(pos, SHED_TILE)]
            return ["PICKUP", animal, 1]

    return ["PASS"]


def agent(observation: Observation) -> Action:
    farms = observation.get("farms", [])
    player = observation.get("player", 0)
    if not farms or player >= len(farms):
        return {"farmer": ["PASS"], "hands": [], "market": []}

    farm = farms[player]
    private = observation.get("private", {}) or {}
    day = observation.get("day", 0)
    hour = observation.get("hour", 0)
    step = observation.get("step", 0)
    seeds = private.get("seeds", {})
    shed = private.get("shed", {})
    inventories = private.get("inventories", []) or []
    market_prices = (observation.get("market") or {}).get("prices", {}) or {}
    money = farm["money"]

    game = _game_state(player, step, day)

    hands = farm.get("hands", [])
    unit_ids: list[Any] = ["farmer", *range(len(hands))]
    unit_positions = [tuple(farm["farmer"]), *(tuple(p) for p in hands)]

    available_seeds = dict(seeds)
    seed_shortfall: dict[str, int] = {}
    unit_ops: list[list[Any]] = []

    for index, (unit_id, pos) in enumerate(zip(unit_ids, unit_positions)):
        inv = inventories[index] if index < len(inventories) else {}

        if unit_id == "farmer":
            target, crop = _assign_crop(game, unit_id)
            if target is not None and _crop_needs_attention(farm, day, target, crop):
                unit_ops.append(_crop_tile_action(farm, day, pos, target, crop, available_seeds, seed_shortfall))
            else:
                unit_ops.append(_caretaker_action(farm, pos, inv, FARMER_ANIMAL_TILES, FARMER_ANIMAL_PLAN))
            continue

        if unit_id == CARETAKER_HAND_INDEX:
            unit_ops.append(_caretaker_action(farm, pos, inv, HAND_ANIMAL_TILES, HAND_ANIMAL_PLAN))
            continue

        target, crop = _assign_crop(game, unit_id)
        if target is None:
            unit_ops.append(["PASS"])
            continue
        unit_ops.append(_crop_tile_action(farm, day, pos, target, crop, available_seeds, seed_shortfall))

    hire_orders: list[list[Any]] = []
    if hour == 0 and len(hands) < game["ramp_target"]:
        wanted = game["ramp_target"] - len(hands)
        hires_today = farm.get("hires_today", 0)
        spend = 0.0
        for i in range(wanted):
            cost = hire_cost(hires_today + i)
            if money - spend < cost:
                break
            spend += cost
            hire_orders.append(["HIRE"])

    # The hand caretaker only exists once hired; the farmer's animal is
    # always "active" since the farmer is always present.
    active_plan = list(FARMER_ANIMAL_PLAN)
    if CARETAKER_HAND_INDEX < len(hands):
        active_plan += HAND_ANIMAL_PLAN

    # Reserve enough wheat in the shed to feed every active animal today
    # before selling the rest; top up from the market if short.
    wheat_reserve = len(active_plan)
    wheat_in_shed = shed.get("WHEAT", 0)
    wheat_sellable = max(0, wheat_in_shed - wheat_reserve)
    sell_orders = [
        ["SELL", item, (wheat_sellable if item == "WHEAT" else shed.get(item, 0))]
        for item in SELLABLE
        if (wheat_sellable if item == "WHEAT" else shed.get(item, 0)) > 0
    ]

    buy_orders: list[list[Any]] = []
    remaining_money = money
    for crop, shortfall in seed_shortfall.items():
        cost_each = CROPS[crop]["seed"]
        affordable = min(shortfall, int(remaining_money // cost_each))
        if affordable > 0:
            buy_orders.append(["BUY_SEED", crop, affordable])
            remaining_money -= affordable * cost_each

    # How many of each animal type are still needed (for active groups
    # only), counting ones already placed, in the shed, or carried by a unit.
    needed = Counter(active_plan)
    placed = Counter(
        tile["animal"]
        for (tx, ty) in ALL_ANIMAL_TILES
        for tile in [farm["tiles"][ty][tx]]
        if isinstance(tile, dict) and tile.get("animal")
    )
    acquired = Counter({animal: shed.get(animal, 0) for animal in needed})
    for inv in inventories:
        for animal in needed:
            acquired[animal] += inv.get(animal, 0)
    for animal, want in needed.items():
        shortfall = want - placed[animal] - acquired[animal]
        if shortfall > 0:
            cost = ANIMALS[animal]["cost"]
            # Discretionary purchase -- never let it eat into the cash
            # reserve that keeps tomorrow's hiring/feeding affordable.
            spendable = max(0, remaining_money - CASH_RESERVE)
            affordable = min(shortfall, 1, int(spendable // cost))  # cap burst per turn
            if affordable > 0:
                buy_orders.append(["BUY_ANIMAL", animal, affordable])
                remaining_money -= affordable * cost

    if wheat_in_shed < wheat_reserve:
        shortfall = wheat_reserve - wheat_in_shed
        cost_each = market_prices.get("WHEAT", CROPS["WHEAT"]["seed"])
        affordable = min(shortfall, int(remaining_money // max(1, cost_each)))
        if affordable > 0:
            buy_orders.append(["BUY_PRODUCT", "WHEAT", affordable])
            remaining_money -= affordable * cost_each

    market = (hire_orders + sell_orders + buy_orders)[:10]

    return {"farmer": unit_ops[0], "hands": unit_ops[1:], "market": market}
