from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Any, Callable


class EngineContractError(RuntimeError):
    pass


def _looks_like_obs(value: Any) -> bool:
    return isinstance(value, dict) and "current" in value and "select" in value


def normalize_engine_return(value: Any) -> dict[str, Any]:
    """Accept the known cg.game return shape plus a few defensive wrappers."""
    if _looks_like_obs(value):
        return value
    if isinstance(value, dict):
        for key in ("observation", "obs"):
            candidate = value.get(key)
            if _looks_like_obs(candidate):
                return candidate
    if isinstance(value, (tuple, list)):
        candidates = [x for x in value if _looks_like_obs(x)]
        if len(candidates) == 1:
            return candidates[0]
        if len(candidates) > 1:
            active = [x for x in candidates if x.get("select") is not None]
            if len(active) == 1:
                return active[0]
    raise EngineContractError(
        "cg.game returned an unsupported value. Expected an obs dict containing "
        "'current' and 'select'."
    )


@dataclass
class EngineAdapter:
    module_name: str = "cg.game"

    def __post_init__(self) -> None:
        module = importlib.import_module(self.module_name)
        try:
            self._battle_start: Callable[[list[int], list[int]], Any] = module.battle_start
            self._battle_select: Callable[[list[int]], Any] = module.battle_select
        except AttributeError as exc:
            raise EngineContractError(
                f"{self.module_name} must expose battle_start(deck0, deck1) and battle_select(select_list)"
            ) from exc

    def start(self, deck0: list[int], deck1: list[int]) -> dict[str, Any]:
        return normalize_engine_return(self._battle_start(deck0, deck1))

    def select(self, action: list[int]) -> dict[str, Any]:
        return normalize_engine_return(self._battle_select(action))


def current_result(obs: dict[str, Any]) -> int:
    current = obs.get("current")
    if not isinstance(current, dict):
        return -1
    value = current.get("result", -1)
    try:
        return int(value)
    except (TypeError, ValueError):
        return -1


def current_player(obs: dict[str, Any]) -> int:
    current = obs.get("current")
    if not isinstance(current, dict):
        raise EngineContractError("Observation has no current state")
    value = current.get("yourIndex")
    if value not in (0, 1):
        raise EngineContractError(f"current.yourIndex must be 0 or 1, got {value!r}")
    return int(value)
