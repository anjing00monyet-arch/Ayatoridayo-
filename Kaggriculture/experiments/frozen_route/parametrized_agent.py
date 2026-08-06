"""Parameterized generalization of submissions/baseline/main.py (v8), used
to search for a stronger configuration before freezing its trajectory
into a fixed 720-step action list (see freeze.py).

`make_agent(params)` returns an `agent(observation)` closure built from a
`Params` dataclass instead of hard-coded module-level constants, so a
search harness can construct many variants and evaluate them by actually
playing real games (see search.py).
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from game.tables import ANIMALS, CROPS, hire_cost

SHED_TILE = (4, 4)


@dataclass
class Params:
    target_hands: int = 10
    hire_ramp_per_day: int = 3
    cash_reserve: float = 1500
    wheat_tiles: int = 4  # first N crop-tenders run wheat; rest run `secondary_crop`
    secondary_crop: str = "MELON"
    farmer_animals: tuple[str, ...] = ("COW", "SHEEP")
    hand_animals: tuple[str, ...] = ("COW", "SHEEP")  # empty tuple = no hand caretaker


def _by_distance(tiles):
    return sorted(tiles, key=lambda p: abs(p[0] - SHED_TILE[0]) + abs(p[1] - SHED_TILE[1]))


_NW_TILES = _by_distance((x, y) for x in range(5) for y in range(5) if (x, y) != SHED_TILE)


def _move_toward(pos, target):
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


def make_agent(p: Params):
    hand_animal_tiles = _NW_TILES[: len(p.hand_animals)]
    farmer_animal_tiles = _NW_TILES[len(p.hand_animals) : len(p.hand_animals) + len(p.farmer_animals)]
    all_animal_tiles = hand_animal_tiles + farmer_animal_tiles
    all_animal_plan = list(p.hand_animals) + list(p.farmer_animals)

    crop_tiles = _NW_TILES[len(all_animal_tiles) :]
    crop_plan = ["WHEAT"] * p.wheat_tiles + [p.secondary_crop] * max(0, len(crop_tiles) - p.wheat_tiles)

    caretaker_hand_index = p.target_hands - 1 if p.hand_animals else None

    sellable = ("WHEAT", "MELON", "CARROT", "STRAWBERRY", "TOMATO", "MILK", "WOOL", "EGG", "FERTILIZER")

    state: dict[int, dict[str, Any]] = {0: {}, 1: {}}

    def game_state(seat, step, day):
        game = state[seat]
        if step == 0 or step < game.get("last_step", -1):
            game = {"last_step": step, "unit_tile": {}, "unit_crop": {}, "ramp_day": -1, "ramp_target": 0}
            state[seat] = game
        game["last_step"] = step
        if day > game["ramp_day"]:
            game["ramp_day"] = day
            game["ramp_target"] = min(p.target_hands, game["ramp_target"] + p.hire_ramp_per_day)
        return game

    def assign_crop(game, unit_id):
        if unit_id not in game["unit_tile"]:
            index = len(game["unit_tile"])
            if index >= len(crop_tiles):
                return None, None
            game["unit_tile"][unit_id] = crop_tiles[index]
            game["unit_crop"][unit_id] = crop_plan[index]
        return game["unit_tile"][unit_id], game["unit_crop"][unit_id]

    def agent(observation):
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

        game = game_state(player, step, day)

        hands = farm.get("hands", [])
        unit_ids: list[Any] = ["farmer", *range(len(hands))]
        unit_positions = [tuple(farm["farmer"]), *(tuple(hp) for hp in hands)]

        available_seeds = dict(seeds)
        seed_shortfall: dict[str, int] = {}
        unit_ops: list[list[Any]] = []

        for index, (unit_id, pos) in enumerate(zip(unit_ids, unit_positions)):
            inv = inventories[index] if index < len(inventories) else {}

            if unit_id == "farmer":
                if p.farmer_animals:
                    target, crop = assign_crop(game, unit_id)
                    if target is not None and _crop_needs_attention(farm, day, target, crop):
                        unit_ops.append(_crop_tile_action(farm, day, pos, target, crop, available_seeds, seed_shortfall))
                    else:
                        unit_ops.append(_caretaker_action(farm, pos, inv, farmer_animal_tiles, list(p.farmer_animals)))
                else:
                    target, crop = assign_crop(game, unit_id)
                    if target is None:
                        unit_ops.append(["PASS"])
                    else:
                        unit_ops.append(_crop_tile_action(farm, day, pos, target, crop, available_seeds, seed_shortfall))
                continue

            if caretaker_hand_index is not None and unit_id == caretaker_hand_index:
                unit_ops.append(_caretaker_action(farm, pos, inv, hand_animal_tiles, list(p.hand_animals)))
                continue

            target, crop = assign_crop(game, unit_id)
            if target is None:
                unit_ops.append(["PASS"])
                continue
            unit_ops.append(_crop_tile_action(farm, day, pos, target, crop, available_seeds, seed_shortfall))

        hire_orders: list[list[Any]] = []
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

        active_plan = list(p.farmer_animals)
        if caretaker_hand_index is not None and caretaker_hand_index < len(hands):
            active_plan += list(p.hand_animals)

        wheat_reserve = len(active_plan)
        wheat_in_shed = shed.get("WHEAT", 0)
        wheat_sellable = max(0, wheat_in_shed - wheat_reserve)
        sell_orders = [
            ["SELL", item, (wheat_sellable if item == "WHEAT" else shed.get(item, 0))]
            for item in sellable
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

        if active_plan:
            needed = Counter(active_plan)
            placed = Counter(
                tile["animal"]
                for (tx, ty) in all_animal_tiles
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
                    spendable = max(0, remaining_money - p.cash_reserve)
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

    return agent
