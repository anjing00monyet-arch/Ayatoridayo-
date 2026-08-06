"""Experimental v10: v9's reactive architecture, rescaled to match what
two independently-converged strong strategies actually use.

v9 (rejected in round 10 in favor of building on the real submission_29)
ran 10 hands and only 2 cow + 2 sheep (4 animals total). Decoding
submission_29 and analyzing 5 real match logs from the actual #1
leaderboard player (Konstantin03) both show 14 hands and 8 cow + 6 sheep
(14 animals) -- a much larger scale on both counts, from two genuinely
different architectures (submission_29 is a frozen 719-step script;
Konstantin03's own logs are byte-identical to each other only through
step ~169, then diverge across ~94% of the remaining turns depending on
the opponent -- confirming a reactive, money/state-driven design much
closer to this project's own v3-v9 lineage than to a frozen script).

This is a first cut at closing that scale gap reactively (not by grafting
foreign moves onto a fragile frozen script, which this project's own
round 9/11/12 investigations found breaks easily under small
perturbations): same crop-tile-tending pattern as v9, plus land expansion
into NE for room, plus 4 dedicated animal caretaker hands instead of 1,
covering all 14 animals instead of 4. Not yet validated -- see
experiments/v10_scaled/bench.py.

Do not change the `agent(observation) -> action` signature or the action
return shape -- that is the official Kaggle submission API.
"""
from __future__ import annotations

from collections import Counter
from typing import Any

from game.tables import ANIMALS, CROPS, hire_cost

Observation = dict[str, Any]
Action = dict[str, Any]

TARGET_HANDS = 14
# Two-phase ramp, calibrated against Konstantin03's real match logs (noon
# hand counts sampled directly): they hover around 5 hands through day 6
# (money as low as $2-30 some days -- clearly deliberately lean before
# crops/animals mature enough to pay for a bigger roster), then scale up
# to 14 over days 7-11 once real revenue exists. A first version ramped
# straight to 14 by day 2 (misreading "5 immediate hires on day 1" as "+5
# hands every day") -- 14 hands costs $986/day in HIRE fees alone (fib-cost
# scales steeply), which no crop or animal here can possibly repay before
# its first harvest (melon: 12 days; cow/sheep: 6-8 days), so the economy
# never recovered: money crashed to ~$0 by day 3 and stayed there for the
# rest of the game, killing all 10 crop tiles and 2 animals from neglect.
_RAMP_PHASE1_CAP = 5
_RAMP_PHASE2_DAY = 7
HIRE_RAMP_PER_DAY = 2
ANIMAL_CARETAKER_COUNT = 4
CROP_TENDER_HAND_COUNT = TARGET_HANDS - ANIMAL_CARETAKER_COUNT  # 10 hands + farmer = 11 crop tenders
CASH_RESERVE = 0

SHED_TILE = (4, 4)
NE_SHED_TILE = (5, 4)


def _by_distance(tiles, origin):
    return sorted(tiles, key=lambda p: abs(p[0] - origin[0]) + abs(p[1] - origin[1]))


_NW_TILES = _by_distance([(x, y) for x in range(5) for y in range(5) if (x, y) != SHED_TILE], SHED_TILE)
_NE_TILES = _by_distance([(x, y) for x in range(5, 10) for y in range(5) if (x, y) != NE_SHED_TILE], NE_SHED_TILE)

CROP_TILES = _NW_TILES[:CROP_TENDER_HAND_COUNT + 1]  # +1 for the farmer's own tile
CROP_PLAN = ["MELON"] * len(CROP_TILES)

# 8 cow + 6 sheep (matches both submission_29's decode and Konstantin03's
# real logs), split across 4 caretaker hands so no one caretaker has to
# cover more animals than it can realistically feed/care/harvest in a day.
_ANIMAL_LIST = ["COW"] * 8 + ["SHEEP"] * 6
_ANIMAL_GROUPS: list[list[str]] = [[], [], [], []]
for _i, _animal in enumerate(_ANIMAL_LIST):
    _ANIMAL_GROUPS[_i % ANIMAL_CARETAKER_COUNT].append(_animal)

_animal_tile_cursor = 0
CARETAKER_ANIMAL_TILES: list[list[tuple[int, int]]] = []
CARETAKER_ANIMAL_PLANS: list[list[str]] = _ANIMAL_GROUPS
for _group in _ANIMAL_GROUPS:
    CARETAKER_ANIMAL_TILES.append(_NE_TILES[_animal_tile_cursor : _animal_tile_cursor + len(_group)])
    _animal_tile_cursor += len(_group)

ALL_ANIMAL_TILES = [t for group in CARETAKER_ANIMAL_TILES for t in group]
ALL_ANIMAL_PLAN = [a for group in CARETAKER_ANIMAL_PLANS for a in group]
CARETAKER_HAND_INDICES = list(range(CROP_TENDER_HAND_COUNT, TARGET_HANDS))  # last 4 hired hands

SELLABLE = ("WHEAT", "MELON", "CARROT", "STRAWBERRY", "TOMATO", "MILK", "WOOL", "FERTILIZER")

_STATE = {0: {}, 1: {}}


def _game_state(seat: int, step: int, day: int) -> dict[str, Any]:
    game = _STATE[seat]
    if step == 0 or step < game.get("last_step", -1):
        game = {
            "last_step": step, "unit_tile": {}, "unit_crop": {}, "ramp_day": -1,
            "ramp_target": 0, "land_bought": False,
        }
        _STATE[seat] = game
    game["last_step"] = step
    if day > game["ramp_day"]:
        game["ramp_day"] = day
        cap = TARGET_HANDS if day >= _RAMP_PHASE2_DAY else _RAMP_PHASE1_CAP
        game["ramp_target"] = min(cap, game["ramp_target"] + HIRE_RAMP_PER_DAY)
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
    tile = farm["tiles"][target[1]][target[0]]
    if tile is None:
        return True
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
    """Same priority order as v9: feed/care/harvest for animals already
    placed always comes before acquiring a new one -- see
    opponents/README.md's "Round 4" section for why that order matters.
    """
    tiles = farm["tiles"]
    wheat_held = unit_inventory.get("WHEAT", 0)

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

    for tx, ty in my_tiles:
        tile = tiles[ty][tx]
        if isinstance(tile, dict) and tile.get("kind") == "WEED":
            if pos != (tx, ty):
                return [_move_toward(pos, (tx, ty))]
            return ["DIG"]

    for tx, ty in my_tiles:
        if tiles[ty][tx] is None:
            if pos != (tx, ty):
                return [_move_toward(pos, (tx, ty))]
            return ["BUILD_PASTURE"]

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
            if target is not None:
                unit_ops.append(_crop_tile_action(farm, day, pos, target, crop, available_seeds, seed_shortfall))
            else:
                unit_ops.append(["PASS"])
            continue

        if unit_id in CARETAKER_HAND_INDICES:
            group = unit_id - CROP_TENDER_HAND_COUNT
            unit_ops.append(
                _caretaker_action(farm, pos, inv, CARETAKER_ANIMAL_TILES[group], CARETAKER_ANIMAL_PLANS[group])
            )
            continue

        target, crop = _assign_crop(game, unit_id)
        if target is None:
            unit_ops.append(["PASS"])
            continue
        unit_ops.append(_crop_tile_action(farm, day, pos, target, crop, available_seeds, seed_shortfall))

    hire_orders: list[list[Any]] = []
    if hour < 3 and len(hands) < game["ramp_target"]:
        wanted = game["ramp_target"] - len(hands)
        hires_today = farm.get("hires_today", 0)
        spend = 0.0
        for i in range(wanted):
            cost = hire_cost(hires_today + i)
            if money - spend < cost:
                break
            spend += cost
            hire_orders.append(["HIRE"])

    land_orders: list[list[Any]] = []
    if not game["land_bought"]:
        if "NE" in farm.get("unlocked_quadrants", []):
            game["land_bought"] = True
        # Match Konstantin03's real timing (~day 7) rather than spending
        # $1,000 during the lean bootstrap phase, before crops/animals
        # have started paying for themselves.
        elif day >= _RAMP_PHASE2_DAY and money >= 1000:
            land_orders.append(["BUY_LAND"])

    active_caretakers = sum(1 for idx in CARETAKER_HAND_INDICES if idx < len(hands))
    active_plan: list[str] = []
    for group_index in range(active_caretakers):
        active_plan += CARETAKER_ANIMAL_PLANS[group_index]

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
            spendable = max(0, remaining_money - CASH_RESERVE)
            affordable = min(shortfall, 1, int(spendable // cost))
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

    market = (hire_orders + land_orders + sell_orders + buy_orders)[:10]

    return {"farmer": unit_ops[0], "hands": unit_ops[1:], "market": market}
