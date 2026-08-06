from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from .utils import now_id, write_json


def _dummy_obs(player: int | None = None) -> dict[str, Any]:
    obs: dict[str, Any] = {
        "current": None,
        "logs": [],
        "remainingOverageTime": 600,
        "search_begin_input": False,
        "select": None,
        "step": 0,
    }
    return obs


class ReplayRecorder:
    def __init__(self, *, variant: str, opponent: str, deck0: list[int], deck1: list[int]) -> None:
        self.variant = variant
        self.opponent = opponent
        self.deck0 = list(deck0)
        self.deck1 = list(deck1)
        self.id = now_id()
        self.steps: list[list[dict[str, Any]]] = []
        self.last_obs: list[dict[str, Any]] = [_dummy_obs(0), _dummy_obs(1)]
        self.steps.append([
            self._entry([], self.last_obs[0], "ACTIVE", 0),
            self._entry([], self.last_obs[1], "ACTIVE", 0),
        ])

    @staticmethod
    def _entry(action: list[int], observation: dict[str, Any], status: str, reward: int) -> dict[str, Any]:
        return {
            "action": list(action),
            "info": {},
            "observation": copy.deepcopy(observation),
            "reward": reward,
            "status": status,
        }

    def record_start(self, obs: dict[str, Any]) -> None:
        actor = int((obs.get("current") or {}).get("yourIndex", 0))
        self.last_obs[actor] = copy.deepcopy(obs)
        entries = []
        for p in (0, 1):
            status = "ACTIVE" if p == actor else "INACTIVE"
            entries.append(self._entry(self.deck0 if p == 0 else self.deck1, self.last_obs[p], status, 0))
        self.steps.append(entries)

    def record_transition(self, actor: int, action: list[int], next_obs: dict[str, Any], result: int) -> None:
        next_actor = int((next_obs.get("current") or {}).get("yourIndex", 1 - actor))
        self.last_obs[next_actor] = copy.deepcopy(next_obs)
        terminal = result in (0, 1)
        if terminal:
            # Propagate only the public terminal marker to the stale perspective.
            for p in (0, 1):
                current = self.last_obs[p].get("current")
                if isinstance(current, dict):
                    current["result"] = result
        entries: list[dict[str, Any]] = []
        for p in (0, 1):
            reward = 0 if not terminal else (1 if p == result else -1)
            status = "DONE" if terminal else ("ACTIVE" if p == next_actor else "INACTIVE")
            entries.append(self._entry(action if p == actor else [], self.last_obs[p], status, reward))
        self.steps.append(entries)

    def payload(self, winner: int, info: dict[str, Any]) -> dict[str, Any]:
        rewards = [0, 0] if winner not in (0, 1) else [1 if i == winner else -1 for i in (0, 1)]
        statuses = ["DONE", "DONE"] if winner in (0, 1) else ["ERROR", "ERROR"]
        return {
            "configuration": {"episodeSteps": len(self.steps)},
            "description": "Local cg.game differential harness replay",
            "id": self.id,
            "info": info,
            "module_version": "local",
            "name": "pokemon-card-game",
            "rewards": rewards,
            "schema_version": 1,
            "specification": {},
            "statuses": statuses,
            "steps": self.steps,
            "title": f"{self.variant} vs {self.opponent}",
            "version": "harness-0.2-c0",
        }

    def save(self, path: str | Path, winner: int, info: dict[str, Any]) -> dict[str, Any]:
        payload = self.payload(winner, info)
        write_json(path, payload, indent=None)
        return payload
