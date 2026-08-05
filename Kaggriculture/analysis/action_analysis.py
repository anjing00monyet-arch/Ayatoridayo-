"""Action-timing analysis: idle turns, watering/feeding delays, and whether
sells happened while prices were falling. These are the "why did we lose
money" signals that a raw profit number can't show.

`events` strings are matched by substring so this keeps working regardless
of the exact event vocabulary the real Kaggriculture env uses -- update the
keyword lists below once real event text is available.
"""
from __future__ import annotations

from typing import Any

from game.interface import MatchReplay

WATER_DELAY_KEYWORDS = ("delayed watering", "water delay", "missed watering")
FEED_DELAY_KEYWORDS = ("delayed feeding", "feed delay", "missed feeding")


def analyze_actions(replay: MatchReplay) -> dict[str, Any]:
    idle_turns = 0
    watering_delays = 0
    feeding_delays = 0
    sales = []  # (day, item, price)

    for step in replay.steps:
        if step.get("idle"):
            idle_turns += 1

        events = step.get("events", [])
        for event in events:
            lowered = event.lower()
            if any(k in lowered for k in WATER_DELAY_KEYWORDS):
                watering_delays += 1
            if any(k in lowered for k in FEED_DELAY_KEYWORDS):
                feeding_delays += 1

        action = step.get("action", {})
        if action.get("type") == "sell":
            sales.append(
                (step.get("day", 0), action.get("item"), action.get("price"))
            )

    return {
        "idle_turns": idle_turns,
        "watering_delays": watering_delays,
        "feeding_delays": feeding_delays,
        "sales": sales,
        "sale_count": len(sales),
    }


def analyze_matches(replays: list[MatchReplay]) -> dict[str, Any]:
    per_match = [analyze_actions(r) for r in replays]
    n = max(len(per_match), 1)
    return {
        "avg_idle_turns": sum(m["idle_turns"] for m in per_match) / n,
        "avg_watering_delays": sum(m["watering_delays"] for m in per_match) / n,
        "avg_feeding_delays": sum(m["feeding_delays"] for m in per_match) / n,
        "avg_sale_count": sum(m["sale_count"] for m in per_match) / n,
    }
