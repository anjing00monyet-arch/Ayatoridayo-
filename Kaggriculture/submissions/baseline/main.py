"""Baseline Kaggriculture submission.

This is the current best-known agent. `run_improvement_loop.py` only ever
overwrites this file by copying an *accepted*
`submissions/candidate/main.py` over it (see evaluation/acceptance_gate.py)
-- never edit it by hand as part of the improvement loop.

Starts out as a vendored copy of `kaggle_environments`'s built-in
`starter_agent` (a carrot loop: buy a carrot seed, plant it on the current
tile, water it daily, harvest at `max_yield_day`, sell whatever lands in the
shed). It is a real, legal Kaggriculture agent, just not a strategically
deep one -- exactly the kind of starting point this improvement loop is
meant to beat.

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
