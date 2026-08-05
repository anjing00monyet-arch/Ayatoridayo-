"""Candidate Kaggriculture submission.

This file is the working slot for the current improvement proposal.
`agents/coder.py` overwrites it; `evaluation/compare_agents.py` A/B tests it
against `submissions/baseline/main.py`. Once it clears
`evaluation/acceptance_gate.py`, `run_improvement_loop.py` promotes it by
copying it over the baseline.

Current proposal: stop buying a carrot seed once there's not enough season
left for it to mature (`agents/analyst.py` flagged this as the single most
common critical failure across 30 baseline games -- see
reports/latest_analysis.md).

Do not change the `agent(observation) -> action` signature or the action
return shape -- that is the official Kaggle submission API. See
submissions/README.md and game/README.md.
"""
from __future__ import annotations

from typing import Any

from game.tables import CROPS

Observation = dict[str, Any]
Action = dict[str, Any]

# agent() receives no `configuration`, so the season length can't be read
# from the observation -- this hardcodes the documented default (30 days).
SEASON_DAYS = 30


def agent(observation: Observation) -> Action:
    farms = observation.get("farms", [])
    player = observation.get("player", 0)
    private = observation.get("private", {}) or {}
    if not farms or player >= len(farms):
        return {"farmer": ["PASS"], "hands": [], "market": []}

    farm = farms[player]
    fx, fy = farm["farmer"]
    tile = farm["tiles"][fy][fx]
    day = observation.get("day", 0)
    seeds = private.get("seeds", {})
    shed = private.get("shed", {})

    market = []
    if shed.get("CARROT", 0) > 0:
        market.append(["SELL", "CARROT", shed["CARROT"]])
    # Analyst finding: every baseline game bought a doomed carrot seed around
    # day 28 (2 days left, needs 3 to reach max_yield_day) -- last day a new
    # planting can still mature before season end.
    last_plantable_day = SEASON_DAYS - 1 - CROPS["CARROT"]["max_yield_day"]
    if (
        seeds.get("CARROT", 0) == 0
        and farm["money"] >= CROPS["CARROT"]["seed"]
        and day <= last_plantable_day
    ):
        market.append(["BUY_SEED", "CARROT", 1])

    farmer = ["PASS"]
    if tile is None and seeds.get("CARROT", 0) > 0:
        farmer = ["PLANT", "CARROT"]
    elif isinstance(tile, dict) and tile.get("kind") == "PLANT" and tile["crop"] == "CARROT":
        age = day - tile["planted_day"]
        if age >= CROPS["CARROT"]["max_yield_day"]:
            farmer = ["HARVEST"]
        elif not tile["watered_today"]:
            farmer = ["WATER"]

    return {"farmer": farmer, "hands": [], "market": market}
