"""Baseline Kaggriculture submission.

This is the current best-known agent. `run_improvement_loop.py` only ever
overwrites this file by copying an *accepted* `submissions/candidate/main.py`
over it (see evaluation/acceptance_gate.py) -- never edit it by hand as part
of the improvement loop.

NOTE: the exact observation/action schema below is a placeholder until the
official Kaggriculture API is vendored into game/ (see game/README.md). Keep
the `agent(observation, configuration)` entry point and its return shape
stable -- that is the "official API" the acceptance gate and strategist
prompt forbid changing.
"""
from __future__ import annotations

from typing import Any

Observation = dict[str, Any]
Configuration = dict[str, Any]
Action = dict[str, Any]


def agent(observation: Observation, configuration: Configuration) -> Action:
    """Rule-based baseline: buy a seed early, otherwise sell whatever is
    priced above its running average, else idle.
    """
    day = observation.get("day", 0)
    bank = observation.get("bank", 0)
    prices: dict[str, float] = observation.get("prices", {})

    if day < 3 and bank > 500:
        return {"type": "buy_seed"}

    if prices:
        item, price = max(prices.items(), key=lambda kv: kv[1])
        if price > 100:
            return {"type": "sell", "item": item, "qty": 1}

    return {"type": "idle"}
