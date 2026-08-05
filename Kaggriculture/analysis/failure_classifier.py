"""Heuristics that turn a raw replay into human/LLM-readable failure tags
and an estimate of capital sunk into investments that never paid back --
the two hardest things to spot by skimming a replay by eye.

These thresholds are starting points, not law -- tune them once real
Kaggriculture replays are available. Keep the *shape* of the output
(`list[str]`, `float`) stable since analysis/profit_breakdown.py and the
analyst prompt depend on it.
"""
from __future__ import annotations

from game.interface import MatchReplay

LATE_GAME_DAY_THRESHOLD = 25
RECOVERY_WINDOW_DAYS = 3


def classify_failures(replay: MatchReplay) -> tuple[list[str], float]:
    failures: list[str] = []
    late_investment_loss = 0.0

    total_days = len(replay.steps)
    pending_investments: list[tuple[int, float, str]] = []  # (day, cost, kind)

    for step in replay.steps:
        day = step.get("day", 0)
        action = step.get("action", {})
        costs = step.get("costs", {})
        kind = action.get("type")

        if kind == "hire_worker" and costs.get("worker", 0.0) > 0:
            pending_investments.append((day, costs["worker"], "worker"))
        elif kind == "buy_seed" and costs.get("seed", 0.0) > 0:
            pending_investments.append((day, costs["seed"], "seed"))
            if day > LATE_GAME_DAY_THRESHOLD and (total_days - day) < RECOVERY_WINDOW_DAYS:
                failures.append(
                    f"day {day}: planted with insufficient recovery window "
                    f"({total_days - day} days left)"
                )
        elif kind == "buy_animal" and costs.get("animal", 0.0) > 0:
            pending_investments.append((day, costs["animal"], "animal"))

        if kind == "sell":
            prices_before = step.get("prices_before")
            price = action.get("price")
            if prices_before is not None and price is not None and price < prices_before:
                failures.append(f"day {day}: sold despite falling price")

        if day > LATE_GAME_DAY_THRESHOLD and kind == "hire_worker":
            failures.append(f"day {day}: hired worker without profitable mission")

    total_revenue = sum(
        amt for step in replay.steps for amt in step.get("revenue_by_item", {}).values()
    )
    for day, cost, kind in pending_investments:
        if day > LATE_GAME_DAY_THRESHOLD and total_revenue < cost:
            late_investment_loss += cost

    return failures, late_investment_loss
