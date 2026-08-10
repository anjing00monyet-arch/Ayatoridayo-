"""Turns one raw Kaggriculture replay (game.kaggriculture_env.play_match
output, i.e. `env.toJSON()`) into the compact per-match stat table that AI
agents actually reason well over -- handing a whole 720-turn replay to an
LLM is exactly the "精度が上がらない" mistake this project is meant to avoid.

Money-delta attribution (seed/animal/worker/land/product cost, sale
revenue) is computed from each turn's submitted market orders using the
cost tables in game/tables.py and the market prices visible in that turn's
observation. SELL/BUY_PRODUCT revenue for orders with qty > 1 is an
approximation (the real per-unit price can drift mid-order -- see the
"Selling inventory to the market" section of the env's README) but is
accurate for qty == 1, which covers most agent behavior.
"""
from __future__ import annotations

from typing import Any

from analysis.failure_classifier import classify_failures
from game.kaggriculture_env import decision_pairs
from game.tables import ANIMALS, CROPS, hire_cost, land_cost

MatchStats = dict[str, Any]


def _ops(action: dict[str, Any] | None) -> list[list[Any]]:
    action = action or {}
    farmer_op = action.get("farmer") or ["PASS"]
    hand_ops = action.get("hands") or []
    return [farmer_op, *hand_ops]


def _diff_tile_events(steps: list[list[dict]], player: int) -> tuple[int, int, int]:
    """Counts crop deaths (PLANT -> WEED), animal escapes (animal -> None on
    a surviving structure), and missed harvests (a crop died while still
    holding unharvested yield_units) by diffing farm tiles turn to turn.
    """
    dead_crops = escaped_animals = missed_harvests = 0
    for t in range(len(steps) - 1):
        tiles_t = steps[t][player]["observation"]["farms"][player]["tiles"]
        tiles_t1 = steps[t + 1][player]["observation"]["farms"][player]["tiles"]
        for y, row in enumerate(tiles_t):
            for x, tile in enumerate(row):
                if not isinstance(tile, dict):
                    continue
                next_tile = tiles_t1[y][x]
                if tile.get("kind") == "PLANT":
                    if isinstance(next_tile, dict) and next_tile.get("kind") == "WEED":
                        dead_crops += 1
                        if tile.get("yield_units", 0) > 0:
                            missed_harvests += 1
                elif tile.get("kind") in ("COOP", "PASTURE") and tile.get("animal"):
                    still_there = isinstance(next_tile, dict) and next_tile.get("animal") == tile.get("animal")
                    if not still_there:
                        escaped_animals += 1
    return dead_crops, escaped_animals, missed_harvests


def parse_match(replay: dict[str, Any], player: int) -> MatchStats:
    steps = replay["steps"]
    final_agent_state = steps[-1][player]
    final_farm = final_agent_state["observation"]["farms"][player]

    revenue_by_item: dict[str, float] = {}
    worker_cost = seed_cost = animal_cost = land_cost_total = product_cost = 0.0
    idle_actions = 0

    for obs, action in decision_pairs(replay, player):
        farm = obs["farms"][player]
        market = obs["market"]
        prices = market.get("prices", {})

        ops = _ops(action)
        idle_actions += sum(1 for op in ops if op and op[0] == "PASS")

        hires_so_far = farm.get("hires_today", 0)
        quadrants_so_far = len(farm.get("unlocked_quadrants", ["NW"]))

        for order in action.get("market", []) or []:
            if not order:
                continue
            op = order[0]
            if op == "BUY_SEED" and len(order) >= 2:
                crop = order[1]
                qty = order[2] if len(order) > 2 else 1
                seed_cost += CROPS.get(crop, {}).get("seed", 0) * qty
            elif op == "BUY_ANIMAL" and len(order) >= 2:
                animal = order[1]
                qty = order[2] if len(order) > 2 else 1
                animal_cost += ANIMALS.get(animal, {}).get("cost", 0) * qty
            elif op == "HIRE":
                worker_cost += hire_cost(hires_so_far)
                hires_so_far += 1
            elif op == "BUY_LAND":
                land_cost_total += land_cost(quadrants_so_far)
                quadrants_so_far += 1
            elif op == "SELL" and len(order) >= 2:
                item = order[1]
                qty = order[2] if len(order) > 2 else 1
                revenue_by_item[item] = revenue_by_item.get(item, 0.0) + prices.get(item, 0) * qty
            elif op == "BUY_PRODUCT" and len(order) >= 2:
                item = order[1]
                qty = order[2] if len(order) > 2 else 1
                product_cost += prices.get(item, 0) * qty

    dead_crops, escaped_animals, missed_harvests = _diff_tile_events(steps, player)
    critical_failures, late_investment_loss = classify_failures(replay, player)

    return {
        "seed": replay.get("seed"),
        "final_bank": final_farm["money"],
        "final_status": final_agent_state["status"],
        "total_revenue": sum(revenue_by_item.values()),
        "worker_cost": worker_cost,
        "seed_cost": seed_cost,
        "animal_cost": animal_cost,
        "land_cost": land_cost_total,
        "product_cost": product_cost,
        "idle_actions": idle_actions,
        "dead_crops": dead_crops,
        "escaped_animals": escaped_animals,
        "missed_harvests": missed_harvests,
        "late_investment_loss": late_investment_loss,
        "revenue_by_item": revenue_by_item,
        "critical_failures": critical_failures,
        "crashed": final_agent_state["status"] in ("ERROR", "TIMEOUT", "INVALID"),
    }


def parse_matches(replays: list[dict[str, Any]], player: int) -> list[MatchStats]:
    return [parse_match(r, player) for r in replays]
