"""Candidate v3: multi-unit scale-up.

The single-tile carrot loop (previous candidate) never used hired hands,
land, or animals -- 93% of turns were idle (see reports/latest_analysis.md).
This version stations the farmer and a ramping roster of hired hands on
individual tiles across the starting NW quadrant, each running an
independent PLANT -> WATER -> HARVEST loop and replanting immediately.
Most tiles run MELON (high value, ~$250 base, best $/tile/day once
cycling); a few run WHEAT (cheap, fast 4-day cycle, glut-resistant price
curve) for early cash flow before melon pays off. Hands are re-hired every
day (they disappear overnight) and walk back to their assigned tile via
simple greedy movement; hiring ramps by a few hands/day rather than all at
once, so melon harvests -- and the eventual replant cycle -- land on
different days instead of glutting the market in one shot.

Does not yet buy land or raise animals -- the NW quadrant alone (24 usable
tiles) comfortably fits TARGET_HANDS=10 + the farmer. See
opponents/submission_27 for a far more sophisticated public solution
(scripted 719-step route + land expansion + animals + market-priority
logic) this was built and tested against.

Do not change the `agent(observation) -> action` signature or the action
return shape -- that is the official Kaggle submission API. See
submissions/README.md and game/README.md.
"""
from __future__ import annotations

from typing import Any

from game.tables import CROPS, hire_cost

Observation = dict[str, Any]
Action = dict[str, Any]

TARGET_HANDS = 10
HIRE_RAMP_PER_DAY = 3  # stagger hiring so planting/harvest timing spreads out

# Tiles in the starting NW quadrant, nearest-to-shed first; skip (4,4)
# (shed-adjacent, kept free to avoid any edge-case interaction).
NW_TILES = sorted(
    ((x, y) for x in range(5) for y in range(5) if (x, y) != (4, 4)),
    key=lambda p: abs(p[0] - 4) + abs(p[1] - 4),
)
# First few assigned units run wheat for early cash flow; the rest run melon.
CROP_PLAN = ["WHEAT"] * 3 + ["MELON"] * (len(NW_TILES) - 3)
SELLABLE = ("WHEAT", "MELON", "CARROT", "STRAWBERRY", "TOMATO")

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


def _assign(game: dict[str, Any], unit_id: Any) -> tuple[tuple[int, int] | None, str | None]:
    if unit_id not in game["unit_tile"]:
        index = len(game["unit_tile"])
        if index >= len(NW_TILES):
            return None, None
        game["unit_tile"][unit_id] = NW_TILES[index]
        game["unit_crop"][unit_id] = CROP_PLAN[index]
    return game["unit_tile"][unit_id], game["unit_crop"][unit_id]


def _move_toward(pos: tuple[int, int], target: tuple[int, int]) -> str:
    x, y = pos
    tx, ty = target
    if x != tx:
        return "EAST" if tx > x else "WEST"
    return "SOUTH" if ty > y else "NORTH"


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
    money = farm["money"]

    game = _game_state(player, step, day)

    hands = farm.get("hands", [])
    unit_ids: list[Any] = ["farmer", *range(len(hands))]
    unit_positions = [tuple(farm["farmer"]), *(tuple(p) for p in hands)]

    available_seeds = dict(seeds)
    seed_shortfall: dict[str, int] = {}
    unit_ops: list[list[Any]] = []

    for unit_id, pos in zip(unit_ids, unit_positions):
        target, crop = _assign(game, unit_id)
        if target is None:
            unit_ops.append(["PASS"])
            continue
        if pos != target:
            unit_ops.append([_move_toward(pos, target)])
            continue

        tile = farm["tiles"][target[1]][target[0]]
        if tile is None:
            if available_seeds.get(crop, 0) > 0:
                available_seeds[crop] -= 1
                unit_ops.append(["PLANT", crop])
            else:
                seed_shortfall[crop] = seed_shortfall.get(crop, 0) + 1
                unit_ops.append(["PASS"])
        elif isinstance(tile, dict) and tile.get("kind") == "PLANT" and tile.get("crop") == crop:
            age = day - tile["planted_day"]
            if age >= CROPS[crop]["max_yield_day"]:
                unit_ops.append(["HARVEST"])
            elif not tile.get("watered_today"):
                unit_ops.append(["WATER"])
            else:
                unit_ops.append(["PASS"])
        elif isinstance(tile, dict) and tile.get("kind") == "WEED":
            unit_ops.append(["DIG"])
        else:
            unit_ops.append(["PASS"])

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

    sell_orders = [["SELL", item, shed[item]] for item in SELLABLE if shed.get(item, 0) > 0]

    buy_orders: list[list[Any]] = []
    remaining_money = money
    for crop, shortfall in seed_shortfall.items():
        cost_each = CROPS[crop]["seed"]
        affordable = min(shortfall, int(remaining_money // cost_each))
        if affordable > 0:
            buy_orders.append(["BUY_SEED", crop, affordable])
            remaining_money -= affordable * cost_each

    market = (hire_orders + sell_orders + buy_orders)[:10]

    return {"farmer": unit_ops[0], "hands": unit_ops[1:], "market": market}
