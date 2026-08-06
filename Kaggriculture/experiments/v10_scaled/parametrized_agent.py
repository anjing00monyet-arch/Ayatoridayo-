"""Parametrized version of experiments/v10_scaled/agent.py, so its
cash-flow knobs can be searched systematically across many seeds instead
of hand-tuned one value at a time against a single seed -- the same
methodology as experiments/frozen_route/parametrized_agent.py (round 8).

Manual single-seed tuning of this agent went through 7 rounds, each
fixing one specific collapse (ramp too fast, cash reserve deadlocking
hiring at zero hands, reserve trap at a low hand-count plateau, caretaker
hands unreliable at high indices, ramp-reserve threshold too conservative
then too aggressive) without ever reaching a configuration that's stable
across seeds -- the last one tried worked for 2 of 5 seeds and collapsed
on the other 3. That pattern (fixing one seed's failure mode at a time)
doesn't converge; a proper multi-seed search is needed instead.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any

from game.tables import ANIMALS, CROPS, hire_cost

Observation = dict[str, Any]
Action = dict[str, Any]

SHED_TILE = (4, 4)
NE_SHED_TILE = (5, 4)
SELLABLE = ("WHEAT", "MELON", "CARROT", "STRAWBERRY", "TOMATO", "MILK", "WOOL", "FERTILIZER")


@dataclass
class Params:
    target_hands: int = 14
    ramp_phase1_cap: int = 5
    ramp_phase2_day: int = 7
    ramp_reserve: float = 150
    hire_ramp_per_day: int = 2
    cash_reserve: float = 300  # discretionary-purchase-only (BUY_ANIMAL); never applied to hiring
    animal_caretaker_count: int = 4
    land_day: int = 7
    land_reserve: float = 1000


def _by_distance(tiles, origin):
    return sorted(tiles, key=lambda p: abs(p[0] - origin[0]) + abs(p[1] - origin[1]))


_NW_TILES = _by_distance([(x, y) for x in range(5) for y in range(5) if (x, y) != SHED_TILE], SHED_TILE)
_NE_TILES = _by_distance([(x, y) for x in range(5, 10) for y in range(5) if (x, y) != NE_SHED_TILE], NE_SHED_TILE)


def _move_toward(pos, target):
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
    crop_tender_hand_count = p.target_hands - p.animal_caretaker_count
    crop_tiles = _NW_TILES[: crop_tender_hand_count + 1]
    crop_plan = ["MELON"] * len(crop_tiles)

    animal_list = ["COW"] * 8 + ["SHEEP"] * 6
    animal_groups: list[list[str]] = [[] for _ in range(p.animal_caretaker_count)]
    for i, animal in enumerate(animal_list):
        animal_groups[i % p.animal_caretaker_count].append(animal)

    caretaker_tiles: list[list[tuple[int, int]]] = []
    cursor = 0
    for group in animal_groups:
        caretaker_tiles.append(_NE_TILES[cursor : cursor + len(group)])
        cursor += len(group)

    all_animal_tiles = [t for group in caretaker_tiles for t in group]
    caretaker_indices = list(range(p.animal_caretaker_count))

    state: dict[int, dict[str, Any]] = {0: {}, 1: {}}

    def game_state(seat, step, day, money):
        game = state[seat]
        if step == 0 or step < game.get("last_step", -1):
            game = {
                "last_step": step, "unit_tile": {}, "unit_crop": {}, "ramp_day": -1,
                "ramp_target": 0, "land_bought": False,
            }
            state[seat] = game
        game["last_step"] = step
        if day > game["ramp_day"]:
            game["ramp_day"] = day
            cap = p.target_hands if day >= p.ramp_phase2_day else p.ramp_phase1_cap
            if money > p.ramp_reserve:
                game["ramp_target"] = min(cap, game["ramp_target"] + p.hire_ramp_per_day)
        return game

    def assign_crop(game, unit_id):
        if unit_id not in game["unit_tile"]:
            index = len(game["unit_tile"])
            if index >= len(crop_tiles):
                return None, None
            game["unit_tile"][unit_id] = crop_tiles[index]
            game["unit_crop"][unit_id] = crop_plan[index]
        return game["unit_tile"][unit_id], game["unit_crop"][unit_id]

    def agent(observation: Observation) -> Action:
        farms = observation.get("farms", [])
        player = observation.get("player", 0)
        if not farms or player >= len(farms):
            return {"farmer": ["PASS"], "hands": [], "market": []}

        farm = farms[player]
        private = observation.get("private", {}) or {}
        day = observation.get("day", 0)
        hour = observation.get("hour", 0)
        seeds = private.get("seeds", {})
        shed = private.get("shed", {})
        inventories = private.get("inventories", []) or []
        market_prices = (observation.get("market") or {}).get("prices", {}) or {}
        money = farm["money"]

        game = game_state(player, observation.get("step", 0), day, money)

        hands = farm.get("hands", [])
        unit_ids: list[Any] = ["farmer", *range(len(hands))]
        unit_positions = [tuple(farm["farmer"]), *(tuple(pos) for pos in hands)]

        available_seeds = dict(seeds)
        seed_shortfall: dict[str, int] = {}
        unit_ops: list[list[Any]] = []

        for index, (unit_id, pos) in enumerate(zip(unit_ids, unit_positions)):
            inv = inventories[index] if index < len(inventories) else {}

            if unit_id == "farmer":
                target, crop = assign_crop(game, unit_id)
                unit_ops.append(
                    _crop_tile_action(farm, day, pos, target, crop, available_seeds, seed_shortfall)
                    if target is not None else ["PASS"]
                )
                continue

            if unit_id in caretaker_indices:
                unit_ops.append(
                    _caretaker_action(farm, pos, inv, caretaker_tiles[unit_id], animal_groups[unit_id])
                )
                continue

            target, crop = assign_crop(game, unit_id)
            unit_ops.append(
                _crop_tile_action(farm, day, pos, target, crop, available_seeds, seed_shortfall)
                if target is not None else ["PASS"]
            )

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
            elif day >= p.land_day and money >= p.land_reserve:
                land_orders.append(["BUY_LAND"])

        active_caretakers = sum(1 for idx in caretaker_indices if idx < len(hands))
        active_plan: list[str] = []
        for group_index in range(active_caretakers):
            active_plan += animal_groups[group_index]

        wheat_reserve_units = len(active_plan)
        wheat_in_shed = shed.get("WHEAT", 0)
        wheat_sellable = max(0, wheat_in_shed - wheat_reserve_units)
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

        if wheat_in_shed < wheat_reserve_units:
            shortfall = wheat_reserve_units - wheat_in_shed
            cost_each = market_prices.get("WHEAT", CROPS["WHEAT"]["seed"])
            affordable = min(shortfall, int(remaining_money // max(1, cost_each)))
            if affordable > 0:
                buy_orders.append(["BUY_PRODUCT", "WHEAT", affordable])
                remaining_money -= affordable * cost_each

        market = (hire_orders + land_orders + sell_orders + buy_orders)[:10]
        return {"farmer": unit_ops[0], "hands": unit_ops[1:], "market": market}

    return agent
