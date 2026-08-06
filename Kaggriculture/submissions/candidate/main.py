"""Candidate v5: more animals per caretaker.

v4 (current baseline) ran exactly 1 cow + 1 sheep via a single caretaker.
opponents/submission_27 runs 8 cows + 2 sheep -- animal husbandry was the
single biggest lever identified in opponents/README.md.

Two earlier attempts at this got the economics wrong, in increasingly
specific ways (see the git log for the actual numbers from each):

1. Bumped TARGET_HANDS 10 -> 18 and added land purchases, assuming more
   hands + more animals would both help. HIRE cost is
   `mult * fib(n_already_hired_today)`, and hands must be re-hired from
   scratch every day (they disappear overnight) -- so the cost of a full
   day's hiring explodes with headcount: 10 hands costs $143/day, 12
   costs $376/day, 18 costs $6,764/day. That run never even reached the
   caretaker slots (15-17), and $3,000 was wasted on land for tiles we
   never needed.
2. Kept TARGET_HANDS at a seemingly-modest 12. Still wrong: $376/day in
   pure hire cost, sustained for the ~12 days before melon first matures
   (little income yet, just a few wheat tiles), burns through the $3,000
   starting bank on hiring *alone* -- before animal or seed costs are
   even considered. Hand count collapsed unpredictably once cash ran out,
   leaving some tiles/animals untended some days -> dead crops, escaped
   animals, a doom spiral.

This version keeps TARGET_HANDS at 10 -- the same headcount as v4, with
the same proven $143/day hire cost -- and instead *reallocates* 2 of
those 10 hands from crop tenants to caretakers (was 1 caretaker tending 2
animals; now 2 caretakers tending 3 animals each, 6 total: 4 cows + 2
sheep). Same hire bill as v4, one fewer melon tile, four more animals.
Also adds a cash reserve so a burst of animal purchases can never eat
into the money needed for tomorrow's hiring/feeding.

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
NUM_CARETAKERS = 2
ANIMALS_PER_CARETAKER = 3
CARETAKER_HAND_INDICES = list(range(TARGET_HANDS - NUM_CARETAKERS, TARGET_HANDS))  # last N hands
CASH_RESERVE = 1500  # never let discretionary spend (animals) risk tomorrow's hire/feed costs
CARETAKER_STAGGER_DAYS = 6  # extra days between successive caretaker groups going active

SHED_TILE = (4, 4)  # only shed-adjacent tile guaranteed unlocked from turn 0


def _by_distance(tiles):
    return sorted(tiles, key=lambda p: abs(p[0] - SHED_TILE[0]) + abs(p[1] - SHED_TILE[1]))


_NW_TILES = _by_distance((x, y) for x in range(5) for y in range(5) if (x, y) != SHED_TILE)

ANIMAL_TILES = _NW_TILES[: NUM_CARETAKERS * ANIMALS_PER_CARETAKER]
ANIMAL_PLAN = (["COW"] * 4 + ["SHEEP"] * 2)[: len(ANIMAL_TILES)]
# Groups: caretaker hand index -> its own slice of (tiles, animals).
CARETAKER_GROUPS = {
    hand_index: (
        ANIMAL_TILES[i * ANIMALS_PER_CARETAKER : (i + 1) * ANIMALS_PER_CARETAKER],
        ANIMAL_PLAN[i * ANIMALS_PER_CARETAKER : (i + 1) * ANIMALS_PER_CARETAKER],
    )
    for i, hand_index in enumerate(CARETAKER_HAND_INDICES)
}

# Crop tenants fill the remaining NW tiles (plenty -- 12 hands - 2
# caretakers + farmer = 11 crop tenders, vs. 18 leftover NW tiles).
CROP_TILES = _NW_TILES[len(ANIMAL_TILES) :]
# First few assigned crop units run wheat for early cash flow (also feeds
# the animals); the rest run melon.
CROP_PLAN = ["WHEAT"] * 4 + ["MELON"] * (len(CROP_TILES) - 4)
SELLABLE = ("WHEAT", "MELON", "CARROT", "STRAWBERRY", "TOMATO", "MILK", "WOOL")

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
    """State-driven: derives this caretaker's next move purely from current
    tile/inventory state for its own group of animals, checked in priority
    order. Self-correcting -- no memory of "where it was headed" needed.
    """
    tiles = farm["tiles"]
    wheat_held = unit_inventory.get("WHEAT", 0)

    # 1. Build any un-built pasture in my group.
    for tx, ty in my_tiles:
        if tiles[ty][tx] is None:
            if pos != (tx, ty):
                return [_move_toward(pos, (tx, ty))]
            return ["BUILD_PASTURE"]

    # 2. Place any animal that's been bought but isn't on its pasture yet.
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

    # 3. Daily loop: feed first (basic needs), then care, then collect.
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
        if unit_id in CARETAKER_GROUPS:
            my_tiles, my_plan = CARETAKER_GROUPS[unit_id]
            inv = inventories[index] if index < len(inventories) else {}
            unit_ops.append(_caretaker_action(farm, pos, inv, my_tiles, my_plan))
            continue
        target, crop = _assign_crop(game, unit_id)
        if target is None:
            unit_ops.append(["PASS"])
            continue
        unit_ops.append(_crop_tile_action(farm, day, pos, target, crop, available_seeds, seed_shortfall))

    hire_orders: list[list[Any]] = []
    # maxMarketOrdersPerTurn caps a single turn at 10 HIRE orders, so
    # replenishing TARGET_HANDS > 10 from the overnight reset to 0 takes
    # more than one turn -- spread it over the first few hours of the day
    # rather than losing the excess to the [:10] truncation below.
    if hour < 3 and len(hands) < game["ramp_target"]:
        wanted = min(10, game["ramp_target"] - len(hands))
        hires_today = farm.get("hires_today", 0)
        spend = 0.0
        for i in range(wanted):
            cost = hire_cost(hires_today + i)
            if money - spend < cost:
                break
            spend += cost
            hire_orders.append(["HIRE"])

    # Only spend on animals/feed for caretakers that actually exist today,
    # AND stagger the caretaker groups a further few days apart. Bringing
    # all of them online together piles up simultaneous purchase + daily
    # feed costs right as hiring finishes ramping (day ~3-4), well before
    # melon/wool/milk income exists to cover it -- an earlier version of
    # this file measured that cash crunch starving existing animals of
    # feed (2 consecutive unfed days -> escaped, a total loss of the
    # purchase) and losing head-to-head to v4 as a result.
    active_plan: list[str] = []
    for group_index, hand_index in enumerate(CARETAKER_HAND_INDICES):
        if hand_index < len(hands) and day >= group_index * CARETAKER_STAGGER_DAYS:
            active_plan.extend(CARETAKER_GROUPS[hand_index][1])

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

    # How many of each animal type are still needed (for active caretakers
    # only), counting ones already placed, in the shed, or carried by a unit.
    needed = Counter(active_plan)
    placed = Counter(
        tile["animal"]
        for (tx, ty) in ANIMAL_TILES
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
            # reserve that keeps tomorrow's hiring/feeding affordable. A
            # burst of simultaneous buys once new caretakers activate is
            # exactly what caused a cash-flow collapse (empty tiles going
            # unwatered, animals going unfed) in an earlier version of
            # this file -- see the git log for the numbers.
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
