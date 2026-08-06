"""Kaggriculture submission -- self-contained copy of
submissions/baseline/main.py (v8), for uploading to Kaggle directly.

Kaggle's grading server only sees whatever file is submitted, so this
inlines the two constants (`CROPS`, `ANIMALS`) and the `hire_cost`
formula that the dev copy imports from `game/tables.py` (which itself
just re-exports them from the installed `kaggle_environments` package --
see that file's docstring). Everything else is unchanged. Do not edit
this file directly; regenerate it from submissions/baseline/main.py if
that changes (see submissions/README.md).
"""
from __future__ import annotations

from collections import Counter
from typing import Any

Observation = dict[str, Any]
Action = dict[str, Any]

# Inlined from kaggle_environments.envs.kaggriculture.kaggriculture.CROPS
CROPS = {
    "WHEAT": {"seed": 10, "first_yield_day": 2, "max_yield_day": 4, "interval": 0, "max_yield": 6, "ongoing": False},
    "CARROT": {"seed": 20, "first_yield_day": 2, "max_yield_day": 3, "interval": 0, "max_yield": 4, "ongoing": False},
    "TOMATO": {"seed": 50, "first_yield_day": 8, "max_yield_day": 8, "interval": 1, "max_yield": 4, "ongoing": True},
    "STRAWBERRY": {"seed": 100, "first_yield_day": 10, "max_yield_day": 10, "interval": 2, "max_yield": 4, "ongoing": True},
    "MELON": {"seed": 80, "first_yield_day": 10, "max_yield_day": 12, "interval": 0, "max_yield": 6, "ongoing": False},
}
# Inlined from kaggle_environments.envs.kaggriculture.kaggriculture.ANIMALS
ANIMALS = {
    "GOOSE": {"cost": 300, "structure": "COOP", "first_yield_day": 4, "interval": 1, "max_held": 4, "product": "EGG"},
    "COW": {"cost": 400, "structure": "PASTURE", "first_yield_day": 8, "interval": 2, "max_held": 6, "product": "MILK"},
    "SHEEP": {"cost": 500, "structure": "PASTURE", "first_yield_day": 6, "interval": 3, "max_held": 6, "product": "WOOL"},
}
FARM_HAND_COST_MULT = 1


def _fib(n: int) -> int:
    """_fib(0)=1, _fib(1)=1, _fib(2)=2, _fib(3)=3, _fib(4)=5, ..."""
    a, b = 1, 1
    for _ in range(n):
        a, b = b, a + b
    return a


def hire_cost(n_already_hired_today: int, mult: int = FARM_HAND_COST_MULT) -> int:
    return mult * _fib(n_already_hired_today)


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
    tiles = farm["tiles"]
    wheat_held = unit_inventory.get("WHEAT", 0)

    # 1. Daily loop for animals I already have: feed first (basic needs),
    # then care, then collect. Takes priority over any setup work below.
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

    # 2. Clear any weed that spawned on one of my tiles before it got built.
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

    active_plan = list(FARMER_ANIMAL_PLAN)
    if CARETAKER_HAND_INDEX < len(hands):
        active_plan += HAND_ANIMAL_PLAN

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

    market = (hire_orders + sell_orders + buy_orders)[:10]

    return {"farmer": unit_ops[0], "hands": unit_ops[1:], "market": market}
