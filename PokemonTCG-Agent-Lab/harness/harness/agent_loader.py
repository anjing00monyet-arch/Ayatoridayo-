from __future__ import annotations

import importlib.util
import hashlib
import os
import sys
import types
import uuid
from pathlib import Path
from typing import Any, Callable

from .utils import pushd, read_deck


RESET_OBS: dict[str, Any] = {
    "current": None,
    "logs": [],
    "remainingOverageTime": 600,
    "search_begin_input": False,
    "select": None,
    "step": 0,
}


class AgentLoadError(RuntimeError):
    pass


class LoadedAgent:
    def __init__(
        self,
        main_path: str,
        deck_path: str,
        *,
        cg_root: str | None = None,
        watch_globals: list[str] | None = None,
    ) -> None:
        self.main_path = Path(main_path).resolve()
        self.deck_path = Path(deck_path).resolve()
        self.agent_dir = self.main_path.parent
        self.watch_globals = watch_globals or ["_opp_mill_seen"]
        if cg_root:
            cg_path = str(Path(cg_root).resolve())
            if cg_path not in sys.path:
                sys.path.insert(0, cg_path)
        if str(self.agent_dir) not in sys.path:
            sys.path.insert(0, str(self.agent_dir))
        if self.deck_path.name != "deck.csv":
            raise AgentLoadError(
                f"The agent reset branch expects a file named deck.csv; got {self.deck_path.name!r}"
            )
        self.deck = read_deck(self.deck_path)
        self.main_sha256 = hashlib.sha256(self.main_path.read_bytes()).hexdigest()
        self.deck_sha256 = hashlib.sha256(self.deck_path.read_bytes()).hexdigest()
        self.module = self._load_module()
        self.agent_fn: Callable[[dict[str, Any]], Any] = getattr(self.module, "agent", None)
        if not callable(self.agent_fn):
            raise AgentLoadError(f"No callable agent(obs) in {self.main_path}")

    def _load_module(self) -> types.ModuleType:
        name = f"harness_variant_{uuid.uuid4().hex}"
        spec = importlib.util.spec_from_file_location(name, self.main_path)
        if spec is None or spec.loader is None:
            raise AgentLoadError(f"Could not import {self.main_path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        with pushd(self.agent_dir):
            spec.loader.exec_module(module)
        return module

    def reset(self) -> dict[str, Any]:
        """Reset through the agent's own select=None branch; never duplicate global reset logic."""
        # read_deck_csv() in submitted agents normally reads ./deck.csv.
        with pushd(self.deck_path.parent):
            returned = self.agent_fn(dict(RESET_OBS))
        info: dict[str, Any] = {"reset_return_type": type(returned).__name__}
        if isinstance(returned, (list, tuple)) and len(returned) == 60:
            try:
                returned_deck = [int(x) for x in returned]
                info["reset_deck_matches"] = sorted(returned_deck) == sorted(self.deck)
            except Exception:
                info["reset_deck_matches"] = False
        return info

    def act(self, obs: dict[str, Any]) -> list[int]:
        with pushd(self.agent_dir):
            raw = self.agent_fn(obs)
        if raw is None:
            return []
        if isinstance(raw, tuple):
            raw = list(raw)
        if not isinstance(raw, list):
            try:
                raw = list(raw)
            except TypeError as exc:
                raise TypeError(f"agent returned non-iterable action: {raw!r}") from exc
        return [int(x) for x in raw]


    def lethal_attack_options(self, obs_dict: dict[str, Any]) -> list[dict[str, Any]]:
        """Return legal attack options that KO the current opposing Active.

        Prefer the loaded agent's own damage helpers so instrumentation measures
        the same mechanics the policy reasons about. Fall back to a conservative
        map for the bundled Archaludon deck.
        """
        select = obs_dict.get("select") or {}
        options = select.get("option") or []
        if not isinstance(options, list):
            return []
        current = obs_dict.get("current") or {}
        yi = current.get("yourIndex")
        if yi not in (0, 1):
            return []
        players = current.get("players") or []
        if not isinstance(players, list) or len(players) < 2:
            return []
        opp = players[1 - int(yi)] if isinstance(players[1 - int(yi)], dict) else {}
        active = opp.get("active") or []
        target_dict = next((x for x in active if isinstance(x, dict)), None) if isinstance(active, list) else None
        if not target_dict:
            return []
        target_hp = int(target_dict.get("hp", target_dict.get("maxHp", 0)) or 0)
        if target_hp <= 0:
            return []

        converted = None
        converter = getattr(self.module, "to_observation_class", None)
        if callable(converter):
            try:
                converted = converter(obs_dict)
            except Exception:
                converted = None

        target_obj = None
        if converted is not None:
            getter = getattr(self.module, "opp_active_pokemon", None)
            if callable(getter):
                try:
                    target_obj = getter(converted)
                except Exception:
                    target_obj = None

        known_base = {253: 220, 224: None, 223: 30, 965: 50, 61: 30}
        output: list[dict[str, Any]] = []
        for idx, option in enumerate(options):
            if not isinstance(option, dict) or "attackId" not in option:
                continue
            try:
                attack_id = int(option.get("attackId"))
            except (TypeError, ValueError):
                continue
            damage = None
            best_damage = getattr(self.module, "best_attack_damage", None)
            if converted is not None and callable(best_damage):
                try:
                    damage = int(best_damage(converted, attack_id))
                except Exception:
                    damage = None
            if damage is None:
                if attack_id == 224:
                    own = players[int(yi)] if isinstance(players[int(yi)], dict) else {}
                    own_active = own.get("active") or []
                    own_card = next((x for x in own_active if isinstance(x, dict)), None) if isinstance(own_active, list) else None
                    if own_card:
                        max_hp = int(own_card.get("maxHp", own_card.get("hp", 0)) or 0)
                        hp = int(own_card.get("hp", max_hp) or 0)
                        damage = 80 + max(0, max_hp - hp)
                else:
                    damage = known_base.get(attack_id)
            if damage is None:
                continue
            effective = int(damage)
            eff_fn = getattr(self.module, "effective_damage", None)
            if target_obj is not None and callable(eff_fn):
                try:
                    effective = int(eff_fn(int(damage), target_obj))
                except Exception:
                    effective = int(damage)
            if effective >= target_hp:
                output.append({
                    "option_index": idx,
                    "attack_id": attack_id,
                    "estimated_damage": effective,
                    "target_hp": target_hp,
                    "target_id": int(target_dict.get("id", -1) or -1),
                })
        return output

    def watched_state(self, obs: dict[str, Any] | None = None) -> dict[str, Any]:
        """Return watched globals plus a side-effect-free mill-policy signal.

        Some agents recognize a currently visible Crustle line directly inside
        detect_matchup(), while the sticky `_opp_mill_seen` global is only set
        for a narrower signal card. Watching the global alone therefore creates
        false negatives even though the policy is actively treating the matchup
        as mill. The synthetic signal mirrors the agent's exported constants
        without calling policy functions or mutating agent state.
        """
        state = {name: getattr(self.module, name, None) for name in self.watch_globals}
        sticky = bool(state.get("_opp_mill_seen", False))
        visible_match = False
        visible_ids: set[int] = set()
        if isinstance(obs, dict):
            current = obs.get("current") or {}
            yi = current.get("yourIndex")
            players = current.get("players") or []
            if yi in (0, 1) and isinstance(players, list) and len(players) >= 2:
                opp = players[1 - int(yi)] if isinstance(players[1 - int(yi)], dict) else {}
                for area in ("active", "bench", "discard"):
                    cards = opp.get(area) or []
                    if isinstance(cards, list):
                        for card in cards:
                            if isinstance(card, dict):
                                try:
                                    visible_ids.add(int(card.get("id", -1)))
                                except (TypeError, ValueError):
                                    pass
        signal_ids: set[int] = set()
        for attr in ("MILL_SIGNAL_IDS", "CRUSTLE_LINE"):
            raw = getattr(self.module, attr, set())
            try:
                signal_ids.update(int(x) for x in raw)
            except Exception:
                pass
        if visible_ids and signal_ids:
            visible_match = bool(visible_ids & signal_ids)
        state["_harness_policy_mill_seen"] = sticky or visible_match
        state["_harness_mill_signal_visible"] = visible_match
        state["_harness_visible_opponent_ids"] = sorted(x for x in visible_ids if x >= 0)
        state["_harness_mill_signal_ids"] = sorted(signal_ids)
        return state
