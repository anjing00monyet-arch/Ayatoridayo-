"""Turns one raw match replay (game.interface.MatchReplay) into the compact
per-match stat table that AI agents actually reason well over -- feeding a
whole replay to an LLM is exactly the "精度が上がらない" mistake this
project is trying to avoid.

Output shape matches the example in the project design notes:

    {
      "final_bank": 176420,
      "total_revenue": 291300,
      "worker_cost": 43200,
      "seed_cost": 18600,
      "animal_cost": 24500,
      "idle_actions": 17,
      "dead_crops": 4,
      "escaped_animals": 1,
      "missed_harvests": 3,
      "late_investment_loss": 12800,
      "revenue_by_item": {"MELON": 74500, "STRAWBERRY": 48200, "MILK": 62100},
      "critical_failures": ["day 18: hired worker without profitable mission", ...]
    }
"""
from __future__ import annotations

from typing import Any

from analysis.failure_classifier import classify_failures
from game.interface import MatchReplay

MatchStats = dict[str, Any]


def parse_match(replay: MatchReplay) -> MatchStats:
    revenue_by_item: dict[str, float] = {}
    worker_cost = seed_cost = animal_cost = 0.0
    idle_actions = dead_crops = escaped_animals = missed_harvests = 0

    for step in replay.steps:
        for item, amount in step.get("revenue_by_item", {}).items():
            revenue_by_item[item] = revenue_by_item.get(item, 0.0) + amount
        costs = step.get("costs", {})
        worker_cost += costs.get("worker", 0.0)
        seed_cost += costs.get("seed", 0.0)
        animal_cost += costs.get("animal", 0.0)
        idle_actions += int(step.get("idle", False))
        dead_crops += step.get("dead_crops", 0)
        escaped_animals += step.get("escaped_animals", 0)
        missed_harvests += int(step.get("missed_harvest", False))

    critical_failures, late_investment_loss = classify_failures(replay)

    return {
        "seed": replay.seed,
        "final_bank": replay.final_bank,
        "total_revenue": sum(revenue_by_item.values()),
        "worker_cost": worker_cost,
        "seed_cost": seed_cost,
        "animal_cost": animal_cost,
        "idle_actions": idle_actions,
        "dead_crops": dead_crops,
        "escaped_animals": escaped_animals,
        "missed_harvests": missed_harvests,
        "late_investment_loss": late_investment_loss,
        "revenue_by_item": revenue_by_item,
        "critical_failures": critical_failures,
        "crashed": replay.crashed,
        "invalid_actions": replay.invalid_actions,
    }


def parse_matches(replays: list[MatchReplay]) -> list[MatchStats]:
    return [parse_match(r) for r in replays]
