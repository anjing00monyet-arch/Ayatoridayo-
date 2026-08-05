"""Placeholder environment used until the official Kaggriculture simulator
is vendored into this folder.

It produces replay records with the exact shape the rest of the pipeline
(analysis/, evaluation/) expects, driven by simple random economics, so the
loop (run_matches -> analysis -> acceptance_gate) is runnable and testable
today. Swap it out by implementing game/interface.py's `GameEnv` against the
real rules and pointing evaluation calls at that module instead.
"""
from __future__ import annotations

import random

from game.interface import ITEMS, Action, Observation


class RandomStubEnv:
    def __init__(self, max_days: int = 30) -> None:
        self.max_days = max_days
        self._rng = random.Random()
        self._day = 0
        self._bank = 10_000.0
        self._invalid_action_count = 0
        self._crashed = False

    @property
    def invalid_action_count(self) -> int:
        return self._invalid_action_count

    @property
    def crashed(self) -> bool:
        return self._crashed

    def reset(self, seed: int) -> Observation:
        self._rng.seed(seed)
        self._day = 0
        self._bank = 10_000.0
        self._invalid_action_count = 0
        self._crashed = False
        return self._observation()

    def _observation(self) -> Observation:
        return {
            "day": self._day,
            "bank": self._bank,
            "prices": {item: round(self._rng.uniform(50, 150), 2) for item in ITEMS},
        }

    def step(self, action: Action) -> tuple[Observation, bool, dict]:
        self._day += 1
        kind = action.get("type", "idle")

        costs = {"worker": 0.0, "seed": 0.0, "animal": 0.0}
        revenue_by_item = {item: 0.0 for item in ITEMS}
        events: list[str] = []
        idle = kind == "idle"
        dead_crops = 0
        escaped_animals = 0
        missed_harvest = False

        if kind == "buy_seed":
            cost = self._rng.uniform(100, 400)
            costs["seed"] = cost
            self._bank -= cost
        elif kind == "buy_animal":
            cost = self._rng.uniform(300, 900)
            costs["animal"] = cost
            self._bank -= cost
        elif kind == "hire_worker":
            cost = self._rng.uniform(200, 500)
            costs["worker"] = cost
            self._bank -= cost
        elif kind == "sell":
            item = action.get("item", self._rng.choice(ITEMS))
            price = self._rng.uniform(50, 150)
            qty = action.get("qty", 1)
            revenue = price * qty
            revenue_by_item[item] += revenue
            self._bank += revenue
            events.append(f"day {self._day}: sold {item}")

        if self._rng.random() < 0.05:
            dead_crops = 1
            events.append(f"day {self._day}: crop died")
        if self._rng.random() < 0.02:
            escaped_animals = 1
            events.append(f"day {self._day}: animal escaped")

        done = self._day >= self.max_days
        step_record = {
            "day": self._day,
            "action": action,
            "bank": self._bank,
            "revenue_by_item": revenue_by_item,
            "costs": costs,
            "events": events,
            "idle": idle,
            "dead_crops": dead_crops,
            "escaped_animals": escaped_animals,
            "missed_harvest": missed_harvest,
        }
        return self._observation(), done, step_record
