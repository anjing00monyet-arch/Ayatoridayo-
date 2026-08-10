"""Thin wrapper around the official `kaggle_environments` "kaggriculture"
environment (https://github.com/Kaggle/kaggle-environments). This is the
real competition environment, not a stand-in -- `pip install
kaggle-environments` provides both the simulator and the exact rules
documented in its `envs/kaggriculture/README.md` / `AGENTS.md`.
"""
from __future__ import annotations

from typing import Any, Callable

try:
    from kaggle_environments import make
except ImportError as e:
    raise ImportError(
        "kaggle-environments is required to run Kaggriculture matches. "
        "Install it with: pip install kaggle-environments"
    ) from e

Agent = Callable[[dict[str, Any]], dict[str, Any]] | str

DEFAULT_CONFIGURATION = {"episodeSteps": 720}


def play_match(
    agent_a: Agent,
    agent_b: Agent,
    seed: int | None = None,
    configuration: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Runs one match, `agent_a` as player 0 and `agent_b` as player 1, and
    returns the full episode as a JSON-serializable dict (`env.toJSON()`)
    with `seed` attached for bookkeeping.

    `agent_a` / `agent_b` may be a `def agent(observation) -> action`
    callable, a path to a `main.py`-style file, or one of the built-in
    names `"pass"`, `"random"`, `"starter"`.
    """
    cfg = dict(DEFAULT_CONFIGURATION)
    if configuration:
        cfg.update(configuration)
    if seed is not None:
        cfg["seed"] = seed

    env = make("kaggriculture", configuration=cfg)
    env.run([agent_a, agent_b])

    replay = env.toJSON()
    replay["seed"] = seed
    return replay


def final_money(replay: dict[str, Any], player: int) -> float:
    return float(replay["steps"][-1][player]["reward"] or 0.0)


def final_status(replay: dict[str, Any], player: int) -> str:
    return replay["steps"][-1][player]["status"]


def crashed(replay: dict[str, Any], player: int) -> bool:
    return any(step[player]["status"] in ("ERROR", "TIMEOUT", "INVALID") for step in replay["steps"])


def decision_pairs(replay: dict[str, Any], player: int) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """Returns (observation, action) pairs where `action` is what the agent
    actually chose *in response to* `observation`.

    `kaggle_environments` stores `steps[i]["observation"]` as the state
    *after* `steps[i]["action"]` was applied -- i.e. the action recorded
    at index i was decided from `steps[i-1]`'s observation, not its own.
    Naively zipping `steps[t]["observation"]` with `steps[t]["action"]`
    pairs each action with the observation it produced instead of the one
    that caused it (confirmed empirically: a BUY_SEED order shows up at
    the same index where `seeds` already reads 1, i.e. post-purchase).
    Use this helper instead of indexing `steps` directly when attributing
    an action to "what the agent saw at decision time".
    """
    steps = replay["steps"]
    return [
        (steps[t][player]["observation"], steps[t + 1][player].get("action") or {})
        for t in range(len(steps) - 1)
    ]
