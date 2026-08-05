"""Action-timing analysis: idle turns, watering/feeding lapses, blocked
PLANT actions, and sale timing. These are the "why did we lose money"
signals a raw profit number can't show.

Watering/feeding lapses are sampled once per day (`hour == 0`) rather than
every turn, since `consecutive_unwatered` / `consecutive_unfed` only change
at the end-of-day refresh -- scanning every turn would count the same daily
lapse ~24 times (`turnsPerDay` many).
"""
from __future__ import annotations

from typing import Any

from game.kaggriculture_env import decision_pairs


def _ops(action: dict[str, Any] | None) -> list[list[Any]]:
    action = action or {}
    farmer_op = action.get("farmer") or ["PASS"]
    hand_ops = action.get("hands") or []
    return [farmer_op, *hand_ops]


def analyze_actions(replay: dict[str, Any], player: int) -> dict[str, Any]:
    idle_turns = 0
    blocked_plant_actions = 0
    watering_lapses = 0
    feeding_lapses = 0
    sales: list[tuple[int, str, float | None]] = []

    for obs, action in decision_pairs(replay, player):
        farm = obs["farms"][player]
        private = obs.get("private", {}) or {}

        ops = _ops(action)
        idle_turns += sum(1 for op in ops if op and op[0] == "PASS")

        plant_demand: dict[str, int] = {}
        for op in ops:
            if op and op[0] == "PLANT" and len(op) > 1:
                plant_demand[op[1]] = plant_demand.get(op[1], 0) + 1
        seeds = private.get("seeds", {})
        blocked_plant_actions += sum(1 for crop, n in plant_demand.items() if n > seeds.get(crop, 0))

        for order in action.get("market", []) or []:
            if order and order[0] == "SELL" and len(order) >= 2:
                sales.append((obs["day"], order[1], obs["market"]["prices"].get(order[1])))

        if obs.get("hour") == 0:
            for row in farm["tiles"]:
                for tile in row:
                    if not isinstance(tile, dict):
                        continue
                    if tile.get("kind") == "PLANT" and tile.get("consecutive_unwatered", 0) >= 1:
                        watering_lapses += 1
                    elif tile.get("kind") in ("COOP", "PASTURE") and tile.get("animal"):
                        if tile.get("consecutive_unfed", 0) >= 1:
                            feeding_lapses += 1

    return {
        "idle_turns": idle_turns,
        "blocked_plant_actions": blocked_plant_actions,
        "watering_lapses": watering_lapses,
        "feeding_lapses": feeding_lapses,
        "sales": sales,
        "sale_count": len(sales),
    }


def analyze_matches(replays: list[dict[str, Any]], player: int) -> dict[str, Any]:
    per_match = [analyze_actions(r, player) for r in replays]
    n = max(len(per_match), 1)
    return {
        "avg_idle_turns": sum(m["idle_turns"] for m in per_match) / n,
        "avg_blocked_plant_actions": sum(m["blocked_plant_actions"] for m in per_match) / n,
        "avg_watering_lapses": sum(m["watering_lapses"] for m in per_match) / n,
        "avg_feeding_lapses": sum(m["feeding_lapses"] for m in per_match) / n,
        "avg_sale_count": sum(m["sale_count"] for m in per_match) / n,
    }
