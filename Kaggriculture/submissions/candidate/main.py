"""Candidate Kaggriculture submission.

This file is the working slot for the current improvement proposal.
`agents/coder.py` overwrites it; `evaluation/compare_agents.py` A/B tests it
against `submissions/baseline/main.py`. Once it clears
`evaluation/acceptance_gate.py`, `run_improvement_loop.py` promotes it by
copying it over the baseline. Starts out identical to the baseline (a
vendored copy of `kaggle_environments`'s built-in `starter_agent`).

Do not change the `agent(observation) -> action` signature or the action
return shape -- that is the official Kaggle submission API. See
submissions/README.md and game/README.md.
"""
from __future__ import annotations

from typing import Any

from game.tables import CROPS

Observation = dict[str, Any]
Action = dict[str, Any]


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
    if seeds.get("CARROT", 0) == 0 and farm["money"] >= CROPS["CARROT"]["seed"]:
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
