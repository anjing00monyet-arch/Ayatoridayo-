"""Candidate v4: adds animal husbandry to the v3 multi-unit scale-up.

v3 (current baseline) stations the farmer and 9 hired hands on individual
crop tiles (melon/wheat). This version repurposes the 10th (last) hired
hand as a dedicated animal caretaker: it builds two pastures right next to
the shed, buys and places one COW and one SHEEP, and every day fetches
wheat from the shed to FEED both, plus CARE/HARVEST/COLLECT_FERTILIZER as
each becomes available. Unlike seeds (auto-available to any unit), FEED
consumes WHEAT from the *acting unit's own inventory* -- see
`_apply_unit_action`'s FEED handler in the installed `kaggle_environments`
package -- so the caretaker must physically carry it from the shed each
day. Milk/wool are the payoff: once fed, a cow/sheep produces indefinitely
from a single $400/$500 purchase, unlike crops which need a fresh seed
every harvest cycle (see opponents/README.md's analysis of why
opponents/submission_27 runs 8 cows + 2 sheep).

The caretaker's per-turn decision is entirely state-driven (derived fresh
from the current observation every call, no phase counter) so it's
self-correcting regardless of timing: build pasture -> fetch+place animal
-> daily feed/care/harvest/collect loop, re-evaluated from scratch each
turn.

Do not change the `agent(observation) -> action` signature or the action
return shape -- that is the official Kaggle submission API. See
submissions/README.md and game/README.md.
"""
from __future__ import annotations

from typing import Any

from game.tables import ANIMALS, CROPS, hire_cost

Observation = dict[str, Any]
Action = dict[str, Any]

TARGET_HANDS = 10
HIRE_RAMP_PER_DAY = 3  # stagger hiring so planting/harvest timing spreads out
CARETAKER_HAND_INDEX = TARGET_HANDS - 1  # last hired hand tends animals, not crops

SHED_TILE = (4, 4)  # only shed-adjacent tile guaranteed unlocked from turn 0

# Tiles in the starting NW quadrant, nearest-to-shed first; skip SHED_TILE
# itself. The first two (closest) are reserved for pastures so the
# caretaker's daily shed-to-pasture commute stays short; the rest are crop
# tiles for the farmer + other hands.
_NW_TILES = sorted(
    ((x, y) for x in range(5) for y in range(5) if (x, y) != SHED_TILE),
    key=lambda p: abs(p[0] - SHED_TILE[0]) + abs(p[1] - SHED_TILE[1]),
)
ANIMAL_TILES = _NW_TILES[:2]
ANIMAL_PLAN = ["COW", "SHEEP"]  # -> MILK, WOOL; two different animals avoids qty bookkeeping
CROP_TILES = _NW_TILES[2:]
# First few assigned crop units run wheat for early cash flow; the rest run melon.
CROP_PLAN = ["WHEAT"] * 3 + ["MELON"] * (len(CROP_TILES) - 3)
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


def _caretaker_action(farm, private, pos, unit_inventory):
    """State-driven: derives the caretaker's next move purely from current
    tile/inventory state, checked in priority order. Self-correcting --
    no memory of "where it was headed" needed.
    """
    tiles = farm["tiles"]
    wheat_held = unit_inventory.get("WHEAT", 0)

    # 1. Build any un-built pasture.
    for tx, ty in ANIMAL_TILES:
        if tiles[ty][tx] is None:
            if pos != (tx, ty):
                return [_move_toward(pos, (tx, ty))]
            return ["BUILD_PASTURE"]

    # 2. Place any animal that's been bought but isn't on its pasture yet.
    for (tx, ty), animal in zip(ANIMAL_TILES, ANIMAL_PLAN):
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
    for (tx, ty), animal in zip(ANIMAL_TILES, ANIMAL_PLAN):
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
            return ["PICKUP", "WHEAT", len(ANIMAL_PLAN)]
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
        if unit_id == CARETAKER_HAND_INDEX:
            inv = inventories[index] if index < len(inventories) else {}
            unit_ops.append(_caretaker_action(farm, private, pos, inv))
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

    # Reserve enough wheat in the shed to feed both animals today before
    # selling the rest; top up from the market if our own crop isn't enough.
    wheat_reserve = len(ANIMAL_PLAN)
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

    for (tx, ty), animal in zip(ANIMAL_TILES, ANIMAL_PLAN):
        tile = farm["tiles"][ty][tx]
        already_have = (isinstance(tile, dict) and tile.get("animal") == animal) or shed.get(
            animal, 0
        ) > 0 or any(inv.get(animal, 0) > 0 for inv in inventories)
        if not already_have:
            cost = ANIMALS[animal]["cost"]
            if remaining_money >= cost:
                buy_orders.append(["BUY_ANIMAL", animal, 1])
                remaining_money -= cost

    if wheat_in_shed < wheat_reserve:
        needed = wheat_reserve - wheat_in_shed
        cost_each = market_prices.get("WHEAT", CROPS["WHEAT"]["seed"])
        affordable = min(needed, int(remaining_money // max(1, cost_each)))
        if affordable > 0:
            buy_orders.append(["BUY_PRODUCT", "WHEAT", affordable])

    market = (hire_orders + sell_orders + buy_orders)[:10]

    return {"farmer": unit_ops[0], "hands": unit_ops[1:], "market": market}
