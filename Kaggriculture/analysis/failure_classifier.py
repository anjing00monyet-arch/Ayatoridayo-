"""Heuristics that turn a raw replay into human/LLM-readable failure tags
and an estimate of capital sunk into late-season investments that couldn't
pay back in time -- the two hardest things to spot by skimming a replay by
eye.

Thresholds and the "insufficient recovery window" check are starting
points, not law -- tune once real experiment data is available. Keep the
*shape* of the output (`list[str]`, `float`) stable since
analysis/profit_breakdown.py and prompts/analyst.md depend on it.
"""
from __future__ import annotations

from typing import Any

from game.tables import ANIMALS, CROPS

LATE_GAME_DAY_FRACTION = 0.8  # last 20% of the season counts as "late"


def classify_failures(steps: list[list[dict[str, Any]]], player: int) -> tuple[list[str], float]:
    last_day = steps[-1][player]["observation"]["day"]
    late_day_threshold = int(last_day * LATE_GAME_DAY_FRACTION)

    failures: list[str] = []
    late_investment_loss = 0.0

    for t in range(len(steps) - 1):
        agent_state = steps[t][player]
        obs = agent_state["observation"]
        day = obs["day"]
        if day < late_day_threshold:
            continue

        action = agent_state.get("action") or {}
        for order in action.get("market", []) or []:
            if not order:
                continue
            op = order[0]
            days_left = last_day - day

            if op == "HIRE":
                failures.append(f"day {day}: hired a farm hand late in the season")

            elif op == "BUY_SEED" and len(order) >= 2:
                crop = order[1]
                max_yield_day = CROPS.get(crop, {}).get("max_yield_day", 0)
                if days_left < max_yield_day:
                    failures.append(
                        f"day {day}: planted {crop} with insufficient recovery window "
                        f"({days_left} days left, needs {max_yield_day})"
                    )
                    late_investment_loss += CROPS.get(crop, {}).get("seed", 0)

            elif op == "BUY_ANIMAL" and len(order) >= 2:
                animal = order[1]
                first_yield = ANIMALS.get(animal, {}).get("first_yield_day", 0)
                if days_left < first_yield:
                    failures.append(
                        f"day {day}: bought {animal} too late to reach first yield "
                        f"({days_left} days left, needs {first_yield})"
                    )
                    late_investment_loss += ANIMALS.get(animal, {}).get("cost", 0)

            elif op == "SELL" and len(order) >= 2 and t > 0:
                item = order[1]
                prev_price = steps[t - 1][player]["observation"]["market"]["prices"].get(item)
                cur_price = obs["market"]["prices"].get(item)
                if prev_price is not None and cur_price is not None and cur_price < prev_price:
                    failures.append(
                        f"day {day}: sold {item} while price was falling ({prev_price} -> {cur_price})"
                    )

    return failures, late_investment_loss
