"""Seam between the improvement-loop tooling and the real Kaggriculture environment.

The official Kaggriculture simulator is not vendored in this repo yet. Every
other module (evaluation/, analysis/) is written against the small contract
below instead of against the simulator directly, so dropping in the real
environment later only means implementing `GameEnv` here and pointing
`load_env()` at it -- nothing in evaluation/ or analysis/ has to change.

Until the real environment lands, `RandomStubEnv` provides a runnable
stand-in with the same shape (bank, revenue_by_item, costs, events per step)
so the rest of the pipeline can be built and tested end-to-end today.
"""
from __future__ import annotations

import importlib
import random
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

Observation = dict[str, Any]
Action = dict[str, Any]
AgentFn = Callable[[Observation, dict[str, Any]], Action]

ITEMS = ("MELON", "STRAWBERRY", "MILK")


class GameEnv(Protocol):
    """Contract the real Kaggriculture environment must satisfy.

    Implement this against the official rules/API once available (see
    game/README.md), then point `load_env()` at the implementation.
    """

    def reset(self, seed: int) -> Observation: ...

    def step(self, action: Action) -> tuple[Observation, bool, dict[str, Any]]:
        """Advance one day. Returns (observation, done, step_record).

        `step_record` must contain at least the fields consumed by
        analysis/replay_parser.py: day, bank, revenue_by_item, costs,
        events, idle, dead_crops, escaped_animals, missed_harvest.
        """
        ...

    @property
    def invalid_action_count(self) -> int: ...

    @property
    def crashed(self) -> bool: ...


def load_env(env_path: str = "game.stub_env:RandomStubEnv") -> GameEnv:
    """Dynamically loads a concrete environment implementation.

    Example: once the official env is vendored, point this at it, e.g.
    `env_path="game.kaggriculture_env:KaggricultureEnv"`.
    """
    module_name, _, class_name = env_path.partition(":")
    module = importlib.import_module(module_name)
    env_cls = getattr(module, class_name)
    return env_cls()


@dataclass
class MatchReplay:
    """Normalized recording of one played match, ready for replay_parser.py."""

    seed: int
    steps: list[dict[str, Any]] = field(default_factory=list)
    final_bank: float = 0.0
    crashed: bool = False
    invalid_actions: int = 0


def play_match(agent: AgentFn, seed: int, max_days: int, env_path: str | None = None) -> MatchReplay:
    """Runs a single agent through one full match and records the replay."""
    env = load_env(env_path) if env_path else load_env()
    observation = env.reset(seed)
    replay = MatchReplay(seed=seed)
    for _day in range(max_days):
        action = agent(observation, {"day": _day, "seed": seed})
        observation, done, step_record = env.step(action)
        replay.steps.append(step_record)
        if done:
            break
    replay.final_bank = replay.steps[-1]["bank"] if replay.steps else 0.0
    replay.crashed = env.crashed
    replay.invalid_actions = env.invalid_action_count
    return replay
