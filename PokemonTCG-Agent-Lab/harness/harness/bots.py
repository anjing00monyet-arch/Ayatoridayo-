from __future__ import annotations

import importlib
import random
from dataclasses import dataclass
from typing import Any, Protocol


class Bot(Protocol):
    def reset(self) -> None: ...
    def act(self, obs: dict[str, Any]) -> list[int]: ...


def _select(obs: dict[str, Any]) -> dict[str, Any]:
    value = obs.get("select")
    return value if isinstance(value, dict) else {}


def _options(obs: dict[str, Any]) -> list[dict[str, Any]]:
    value = _select(obs).get("option")
    return [x for x in value if isinstance(x, dict)] if isinstance(value, list) else []


def selection_bounds(obs: dict[str, Any]) -> tuple[int, int]:
    sel = _select(obs)
    options = _options(obs)
    minimum = int(sel.get("minCount", 0) or 0)
    maximum = int(sel.get("maxCount", minimum) or minimum)
    maximum = min(maximum, len(options))
    minimum = min(minimum, maximum)
    return minimum, maximum


def validate_action(obs: dict[str, Any], action: list[int]) -> tuple[bool, str]:
    options = _options(obs)
    minimum, maximum = selection_bounds(obs)
    if len(action) < minimum or len(action) > maximum:
        return False, f"count {len(action)} outside [{minimum}, {maximum}]"
    if len(set(action)) != len(action):
        return False, "duplicate option index"
    if any(i < 0 or i >= len(options) for i in action):
        return False, f"index outside [0, {len(options) - 1}]"
    return True, "ok"


@dataclass
class RandomLegalBot:
    rng_seed: int | None = None

    def __post_init__(self) -> None:
        self.rng = random.Random(self.rng_seed)

    def reset(self) -> None:
        return None

    def act(self, obs: dict[str, Any]) -> list[int]:
        options = _options(obs)
        minimum, maximum = selection_bounds(obs)
        if not options or maximum == 0:
            return []
        count = self.rng.randint(minimum, maximum)
        return sorted(self.rng.sample(range(len(options)), count))


class RuntimeSymbols:
    """Resolve cg.api enums/card DB at runtime, with safe fallbacks."""

    def __init__(self) -> None:
        self.option_type: dict[str, int] = {}
        self.context: dict[str, int] = {}
        self.area: dict[str, int] = {}
        self.card_db: dict[int, Any] = {}
        try:
            api = importlib.import_module("cg.api")
            self.option_type = self._enum_map(getattr(api, "OptionType", None))
            self.context = self._enum_map(getattr(api, "SelectContext", None))
            self.area = self._enum_map(getattr(api, "AreaType", None))
            all_cards = getattr(api, "all_card_data", None)
            if callable(all_cards):
                self.card_db = {int(getattr(c, "cardId")): c for c in all_cards()}
        except Exception:
            pass

    @staticmethod
    def _enum_map(enum_cls: Any) -> dict[str, int]:
        if enum_cls is None:
            return {}
        out: dict[str, int] = {}
        for name in dir(enum_cls):
            if name.startswith("_"):
                continue
            value = getattr(enum_cls, name)
            try:
                out[name] = int(value)
            except Exception:
                try:
                    out[name] = int(value.value)
                except Exception:
                    continue
        return out

    def is_option(self, option: dict[str, Any], *names: str) -> bool:
        value = option.get("type")
        return any(name in self.option_type and value == self.option_type[name] for name in names)

    def is_context(self, obs: dict[str, Any], *names: str) -> bool:
        value = _select(obs).get("context")
        return any(name in self.context and value == self.context[name] for name in names)


def _player_state(obs: dict[str, Any], player: int) -> dict[str, Any]:
    current = obs.get("current") or {}
    players = current.get("players") or []
    if isinstance(players, list) and 0 <= player < len(players) and isinstance(players[player], dict):
        return players[player]
    return {}


def _card_from_area(obs: dict[str, Any], area: Any, index: Any, player: int, symbols: RuntimeSymbols) -> dict[str, Any] | None:
    try:
        index = int(index)
    except (TypeError, ValueError):
        return None
    state = _player_state(obs, player)
    area_names = {
        symbols.area.get("DECK"): "deck",
        symbols.area.get("HAND"): "hand",
        symbols.area.get("DISCARD"): "discard",
        symbols.area.get("ACTIVE"): "active",
        symbols.area.get("BENCH"): "bench",
        symbols.area.get("PRIZE"): "prize",
    }
    key = area_names.get(area)
    if key == "deck":
        deck = _select(obs).get("deck")
        cards = deck if isinstance(deck, list) else []
    else:
        cards = state.get(key, []) if key else []
    if isinstance(cards, list) and 0 <= index < len(cards) and isinstance(cards[index], dict):
        return cards[index]
    return None


def option_card(obs: dict[str, Any], option: dict[str, Any], symbols: RuntimeSymbols) -> dict[str, Any] | None:
    current = obs.get("current") or {}
    player = option.get("playerIndex", current.get("yourIndex", 0))
    if symbols.is_option(option, "PLAY"):
        return _card_from_area(obs, symbols.area.get("HAND"), option.get("index"), int(player), symbols)
    return _card_from_area(obs, option.get("area"), option.get("index"), int(player), symbols)


def _energy_count(card: dict[str, Any] | None) -> int:
    if not card:
        return 0
    energies = card.get("energies") or card.get("energyCards") or []
    return len(energies) if isinstance(energies, list) else 0


def _hp(card: dict[str, Any] | None) -> int:
    if not card:
        return 0
    try:
        return int(card.get("hp", card.get("maxHp", 0)) or 0)
    except (TypeError, ValueError):
        return 0


@dataclass
class GreedyBot:
    """Tier2: generic legal greedy pilot.

    It is intentionally simple. Its role is stable differential testing, not ladder replication.
    """

    rng_seed: int | None = None

    def __post_init__(self) -> None:
        self.rng = random.Random(self.rng_seed)
        self.symbols = RuntimeSymbols()

    def reset(self) -> None:
        return None

    def _score(self, obs: dict[str, Any], idx: int, option: dict[str, Any]) -> float:
        s = self.symbols
        card = option_card(obs, option, s)
        cid = int((card or {}).get("id", option.get("cardId", -1)) or -1)
        current = obs.get("current") or {}
        yi = int(current.get("yourIndex", 0) or 0)
        pi = int(option.get("playerIndex", yi) or yi)

        if s.is_option(option, "END_TURN", "END"):
            return -10000
        if s.is_option(option, "ATTACK"):
            return 5000 + float(option.get("damage", 0) or 0)
        if s.is_option(option, "ABILITY"):
            return 9500
        if s.is_option(option, "EVOLVE"):
            return 9000 + _hp(card)
        if s.is_option(option, "ATTACH", "ATTACH_ENERGY"):
            return 8500
        if s.is_option(option, "PLAY"):
            # Prefer setup/draw cards, but attacks still terminate the turn reliably.
            strategic = {
                1121: 8800,  # Ultra Ball
                1152: 8600,  # Poke Pad
                1122: 8300,  # Pokegear
                1227: 8200,  # Lillie
                1185: 8100,  # Explorer
                1213: 8000,  # Judge
                1197: 8050,  # Xerosic
            }
            return strategic.get(cid, 7200) + min(_hp(card), 400) / 1000
        if s.is_option(option, "RETREAT"):
            return 1000

        # Selection/target contexts.
        if pi != yi:
            # Opponent target: lowest remaining HP first.
            return 5000 - _hp(card) + _energy_count(card) * 30
        if s.is_context(obs, "ATTACH_TO", "ATTACH_FROM"):
            return 4000 + max(0, 3 - _energy_count(card)) * 300 + _hp(card) / 10
        if s.is_context(obs, "SWITCH", "TO_ACTIVE"):
            return 4000 + _energy_count(card) * 500 + _hp(card) / 10
        if s.is_context(obs, "DISCARD"):
            return 2000 - _hp(card) - _energy_count(card) * 100
        if s.is_context(obs, "DAMAGE"):
            return 3000 - _hp(card)
        return 1000 + _hp(card) / 100 + self.rng.random() * 0.001 - idx * 1e-6

    def act(self, obs: dict[str, Any]) -> list[int]:
        options = _options(obs)
        minimum, maximum = selection_bounds(obs)
        if not options or maximum == 0:
            return []
        scored = sorted(
            ((self._score(obs, i, opt), i) for i, opt in enumerate(options)),
            reverse=True,
        )
        selected: list[int] = []
        for score, idx in scored:
            if len(selected) >= maximum:
                break
            if len(selected) >= minimum and score < 0:
                break
            selected.append(idx)
        if len(selected) < minimum:
            selected = [idx for _, idx in scored[:minimum]]
        return sorted(selected)


@dataclass
class TuskMillBot(GreedyBot):
    """Tier3 starter for Great Tusk/Crustle mill; refine against real replays."""

    MILL_IDS = {58, 344, 345, 532, 756, 1197, 1212, 1235}

    def _score(self, obs: dict[str, Any], idx: int, option: dict[str, Any]) -> float:
        score = super()._score(obs, idx, option)
        card = option_card(obs, option, self.symbols)
        cid = int((card or {}).get("id", option.get("cardId", -1)) or -1)
        if cid in self.MILL_IDS:
            score += 3500
        if self.symbols.is_option(option, "ATTACK"):
            score += 2500
        return score


def load_bot(spec: str, *, seed: int | None = None) -> Bot:
    normalized = spec.strip().lower()
    if normalized in {"random", "tier1", "random_legal"}:
        return RandomLegalBot(seed)
    if normalized in {"greedy", "tier2"}:
        return GreedyBot(seed)
    if normalized in {"tusk_mill", "mill", "tier3_mill"}:
        return TuskMillBot(seed)
    if ":" in spec:
        module_name, attr = spec.split(":", 1)
        factory = getattr(importlib.import_module(module_name), attr)
        bot = factory(seed=seed)
        if not hasattr(bot, "act"):
            raise TypeError(f"Custom bot {spec} has no act(obs) method")
        return bot
    raise ValueError(f"Unknown bot specification: {spec}")
