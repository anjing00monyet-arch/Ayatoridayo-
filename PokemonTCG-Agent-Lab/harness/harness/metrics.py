from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .bots import RuntimeSymbols, option_card
from .utils import canonical_hash

DURALUDON = 169
ARCHALUDON_EX = 190
METAL_ENERGY = 8

# Card-class value hierarchy for the Archaludon deck. What makes a promotion a
# "self snipe" is not HP or attached energy but which card class is thrown away:
# the Duraludon/Archaludon line IS the win condition (precious), while walls
# like Relicanth/Cinderace exist to soak hits (expendable). An energy-less
# Duraludon is still precious; a 2-energy Relicanth is still expendable.
PRECIOUS_IDS = {DURALUDON, ARCHALUDON_EX}


def _player_state(obs: dict[str, Any], player: int) -> dict[str, Any]:
    current = obs.get("current") or {}
    players = current.get("players") or []
    if isinstance(players, list) and 0 <= player < len(players) and isinstance(players[player], dict):
        return players[player]
    return {}


def _cards(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [x for x in value if isinstance(x, dict)]


def _energy_count(card: dict[str, Any] | None) -> int:
    if not card:
        return 0
    energies = card.get("energies") or card.get("energyCards") or []
    return len(energies) if isinstance(energies, list) else 0


def _card_brief(card: dict[str, Any] | None) -> dict[str, Any] | None:
    if not card:
        return None
    return {
        "id": int(card.get("id", -1) or -1),
        "serial": int(card.get("serial", -1) or -1),
        "hp": int(card.get("hp", card.get("maxHp", 0)) or 0),
        "max_hp": int(card.get("maxHp", card.get("hp", 0)) or 0),
        "energy_count": _energy_count(card),
        "appear_this_turn": bool(card.get("appearThisTurn", False)),
    }


def _context_name(symbols: RuntimeSymbols, value: Any) -> str:
    for name, number in symbols.context.items():
        if number == value:
            return name
    return str(value)


def _option_brief(obs: dict[str, Any], idx: int, option: dict[str, Any], symbols: RuntimeSymbols) -> dict[str, Any]:
    card = option_card(obs, option, symbols)
    out: dict[str, Any] = {
        "option_index": idx,
        "type": option.get("type"),
        "player_index": option.get("playerIndex"),
        "area": option.get("area"),
        "index": option.get("index"),
        "attack_id": option.get("attackId"),
        "card": _card_brief(card),
    }
    return out


@dataclass
class MechanismTracker:
    target_seat: int
    expected_mill: bool = False
    archaludon_id: int = ARCHALUDON_EX
    symbols: RuntimeSymbols = field(default_factory=RuntimeSymbols)
    seen_log_hashes: set[str] = field(default_factory=set)
    first_attack_global_turn: int | None = None
    first_attack_own_turn: int | None = None
    first_archaludon_own_turn: int | None = None
    attack_by_own_turn3: bool = False
    archaludon_by_own_turn3: bool = False
    line_count_at_own_turn3: int | None = None
    own_turn_count: int = 0
    last_target_turn_marker: Any = None
    first_player: int = -1
    mill_seen: bool = False
    mill_signal_visible: bool = False
    mill_signal_first_seen_turn: int | None = None
    mill_first_seen_turn: int | None = None
    mill_first_seen_visible_opponent_ids: list[int] = field(default_factory=list)
    c0_1_mill_misdetection_occurred: bool = False
    c0_2_duraludon_promotion_events: list[dict[str, Any]] = field(default_factory=list)
    c0_3_lethal_suppression_events: list[dict[str, Any]] = field(default_factory=list)
    c0_3_lethal_opportunity_count: int = 0
    c0_3_pending_lethal: dict[str, Any] | None = None
    c0_3_pending_turn_marker: Any = None

    def observe(self, obs: dict[str, Any]) -> None:
        current = obs.get("current")
        if not isinstance(current, dict):
            return

        actor = current.get("yourIndex")
        turn_marker = current.get("turn")
        if self.c0_3_pending_lethal is not None:
            if actor != self.target_seat or turn_marker != self.c0_3_pending_turn_marker:
                self._finalize_pending_lethal(reason="turn_ended")

        fp = current.get("firstPlayer", -1)
        try:
            fp_int = int(fp)
        except (TypeError, ValueError):
            fp_int = -1
        if fp_int in (0, 1):
            self.first_player = fp_int

        if actor == self.target_seat and turn_marker != self.last_target_turn_marker:
            self.own_turn_count += 1
            self.last_target_turn_marker = turn_marker

        state = _player_state(obs, self.target_seat)
        cards = _cards(state.get("active")) + _cards(state.get("bench"))
        ids = [int(x.get("id", -1) or -1) for x in cards]
        if self.archaludon_id in ids and self.first_archaludon_own_turn is None:
            self.first_archaludon_own_turn = max(1, self.own_turn_count)
        if self.own_turn_count <= 3 and self.archaludon_id in ids:
            self.archaludon_by_own_turn3 = True
        if self.own_turn_count == 3 and self.line_count_at_own_turn3 is None:
            self.line_count_at_own_turn3 = sum(1 for cid in ids if cid in (DURALUDON, ARCHALUDON_EX))

        logs = obs.get("logs") or []
        if not isinstance(logs, list):
            return
        for event in logs:
            if not isinstance(event, dict):
                continue
            fingerprint = canonical_hash(event)
            if fingerprint in self.seen_log_hashes:
                continue
            self.seen_log_hashes.add(fingerprint)
            if "attackId" in event and event.get("playerIndex") == self.target_seat:
                if self.first_attack_global_turn is None:
                    try:
                        self.first_attack_global_turn = int(current.get("turn"))
                    except (TypeError, ValueError):
                        self.first_attack_global_turn = None
                    self.first_attack_own_turn = max(1, self.own_turn_count)
                if self.own_turn_count <= 3:
                    self.attack_by_own_turn3 = True

    def _visible_opponent_ids(self, obs: dict[str, Any]) -> list[int]:
        state = _player_state(obs, 1 - self.target_seat)
        visible = _cards(state.get("active")) + _cards(state.get("bench")) + _cards(state.get("discard"))
        return sorted({int(card.get("id", -1) or -1) for card in visible if int(card.get("id", -1) or -1) >= 0})

    def record_agent_decision(
        self,
        obs: dict[str, Any],
        action: list[int],
        watched_state: dict[str, Any],
        lethal_options: list[dict[str, Any]],
    ) -> None:
        current = obs.get("current") or {}
        if current.get("yourIndex") != self.target_seat:
            return

        signal_visible_now = bool(watched_state.get("_harness_mill_signal_visible", False))
        if signal_visible_now and not self.mill_signal_visible:
            self.mill_signal_visible = True
            try:
                self.mill_signal_first_seen_turn = int(current.get("turn"))
            except (TypeError, ValueError):
                self.mill_signal_first_seen_turn = None

        mill_now = bool(
            watched_state.get("_harness_policy_mill_seen", False)
            or watched_state.get("_opp_mill_seen", False)
        )
        if mill_now and not self.mill_seen:
            self.mill_seen = True
            try:
                self.mill_first_seen_turn = int(current.get("turn"))
            except (TypeError, ValueError):
                self.mill_first_seen_turn = None
            self.mill_first_seen_visible_opponent_ids = self._visible_opponent_ids(obs)
        if mill_now and not self.expected_mill:
            self.c0_1_mill_misdetection_occurred = True

        self._record_promotion(obs, action)
        self._record_lethal_suppression(obs, action, lethal_options)

    def _record_promotion(self, obs: dict[str, Any], action: list[int]) -> None:
        if not self.symbols.is_context(obs, "SWITCH", "TO_ACTIVE"):
            return
        current = obs.get("current") or {}
        if current.get("yourIndex") != self.target_seat:
            return
        select = obs.get("select") or {}
        options = select.get("option") or []
        if not isinstance(options, list):
            return

        candidates: list[dict[str, Any]] = []
        for idx, option in enumerate(options):
            if not isinstance(option, dict):
                continue
            pi = option.get("playerIndex", self.target_seat)
            try:
                pi = int(pi)
            except (TypeError, ValueError):
                pi = self.target_seat
            if pi != self.target_seat:
                continue
            card = option_card(obs, option, self.symbols)
            if not card:
                continue
            brief = _option_brief(obs, idx, option, self.symbols)
            brief["is_duraludon_line"] = int(card.get("id", -1) or -1) in (DURALUDON, ARCHALUDON_EX)
            brief["attack_ready"] = _energy_count(card) >= 3
            candidates.append(brief)
        if not candidates:
            return

        selected = [c for c in candidates if c["option_index"] in action]
        if not selected:
            return
        selected_card = selected[0].get("card") or {}
        selected_id = int(selected_card.get("id", -1) or -1)

        own_state = _player_state(obs, self.target_seat)
        active_cards = _cards(own_state.get("active"))
        forced = len(active_cards) == 0
        ready_duraludon = [
            c for c in candidates
            if c.get("is_duraludon_line") and c.get("attack_ready")
        ]
        alternatives = [c for c in candidates if c["option_index"] != selected[0]["option_index"]]
        selected_energy = int(selected_card.get("energy_count", 0) or 0)

        voluntary_avoided_ready = (
            not forced
            and bool(ready_duraludon)
            and not (selected_id in (DURALUDON, ARCHALUDON_EX) and selected_energy >= 3)
        )
        safer_alternatives = [
            c for c in alternatives
            if int((c.get("card") or {}).get("hp", 0) or 0) > int(selected_card.get("hp", 0) or 0)
            or int((c.get("card") or {}).get("id", -1) or -1) in (666, 57)
        ]
        forced_exposed_unready = (
            forced
            and selected_id == DURALUDON
            and selected_energy < 3
            and bool(safer_alternatives)
        )

        # --- Card-class based classification (v5 instrumentation) -----------
        # The legacy suspected_self_inflicted_snipe / safer_alternatives logic
        # keys on HP, which misreads two common shapes:
        #   * promoting a fresh Duraludon while an energized Relicanth sits on
        #     the bench looks "safe" by HP/energy but throws away the win
        #     condition (this IS the C0-2 bug shape), and
        #   * sacrificing an energy-less wall to protect a built Duraludon
        #     looks "bad" by HP but is exactly right.
        # Classify by card class instead. Legacy fields above are kept
        # unchanged for cross-run comparability.
        own_hand_ids = {
            int(c.get("id", -1) or -1) for c in _cards(own_state.get("hand"))
        }
        selected_appear = bool(selected_card.get("appear_this_turn", False))
        can_evolve_now = (
            selected_id == DURALUDON
            and ARCHALUDON_EX in own_hand_ids
            and not selected_appear
        )
        expendable_alternatives = [
            c for c in alternatives
            if int((c.get("card") or {}).get("id", -1) or -1) not in PRECIOUS_IDS
        ]
        precious_alternatives = [
            c for c in alternatives
            if int((c.get("card") or {}).get("id", -1) or -1) in PRECIOUS_IDS
        ]
        selected_ready = selected_id in PRECIOUS_IDS and selected_energy >= 3

        if selected_id in PRECIOUS_IDS:
            if selected_ready or can_evolve_now:
                classification = "precious_ready_or_completing"   # good: it can act
            elif not expendable_alternatives:
                classification = "precious_no_expendable_alternative"  # no real choice
            elif forced:
                classification = "true_self_snipe"  # threw the win condition to the wolves
            else:
                classification = "voluntary_precious_exposure"  # questionable, not gated
        else:
            if ready_duraludon:
                classification = "wall_out_over_ready_attacker"  # legacy voluntary-avoid shape
            elif precious_alternatives:
                classification = "resource_preserving_wall"  # good: wall soaks, line survives
            else:
                classification = "expendable_only_choice"

        true_self_snipe = classification == "true_self_snipe"
        # --------------------------------------------------------------------

        event = {
            "turn": current.get("turn"),
            "own_turn": self.own_turn_count,
            "context": select.get("context"),
            "context_name": _context_name(self.symbols, select.get("context")),
            "forced_promotion": forced,
            "selected": selected[0],
            "candidates": candidates,
            "attack_ready_duraludon_available": bool(ready_duraludon),
            "voluntary_avoided_ready_duraludon": voluntary_avoided_ready,
            "suspected_self_inflicted_snipe": forced_exposed_unready,
            "c0_2_violation": bool(voluntary_avoided_ready or forced_exposed_unready),
            "selected_can_evolve_now": can_evolve_now,
            "classification": classification,
            "true_self_snipe": true_self_snipe,
        }
        self.c0_2_duraludon_promotion_events.append(event)

    def _record_lethal_suppression(
        self,
        obs: dict[str, Any],
        action: list[int],
        lethal_options: list[dict[str, Any]],
    ) -> None:
        current = obs.get("current") or {}
        select = obs.get("select") or {}
        turn_marker = current.get("turn")

        if lethal_options and self.c0_3_pending_lethal is None:
            self.c0_3_lethal_opportunity_count += 1
            opp_state = _player_state(obs, 1 - self.target_seat)
            opp_active = _cards(opp_state.get("active"))
            self.c0_3_pending_lethal = {
                "turn": turn_marker,
                "own_turn": self.own_turn_count,
                "first_context": select.get("context"),
                "first_context_name": _context_name(self.symbols, select.get("context")),
                "opponent_active": _card_brief(opp_active[0] if opp_active else None),
                "lethal_options": lethal_options,
                "decision_trace": [],
            }
            self.c0_3_pending_turn_marker = turn_marker

        pending = self.c0_3_pending_lethal
        if pending is None:
            return

        options = select.get("option") or []
        selected: list[dict[str, Any]] = []
        if isinstance(options, list):
            for idx in action:
                if 0 <= idx < len(options) and isinstance(options[idx], dict):
                    selected.append(_option_brief(obs, idx, options[idx], self.symbols))
        pending["decision_trace"].append({
            "context": select.get("context"),
            "context_name": _context_name(self.symbols, select.get("context")),
            "selected_options": selected,
        })

        lethal_indices = {int(x["option_index"]) for x in lethal_options}
        if lethal_indices.intersection(action):
            pending["resolved_by_lethal_attack"] = True
            self.c0_3_pending_lethal = None
            self.c0_3_pending_turn_marker = None

    def _finalize_pending_lethal(self, reason: str) -> None:
        if self.c0_3_pending_lethal is None:
            return
        event = dict(self.c0_3_pending_lethal)
        event["reason"] = reason
        event["resolved_by_lethal_attack"] = False
        self.c0_3_lethal_suppression_events.append(event)
        self.c0_3_pending_lethal = None
        self.c0_3_pending_turn_marker = None

    def finalize(self) -> None:
        self._finalize_pending_lethal(reason="game_ended")

    def instrumentation(self) -> dict[str, Any]:
        promotion_violations = sum(bool(e.get("c0_2_violation")) for e in self.c0_2_duraludon_promotion_events)
        self_snipes = sum(bool(e.get("suspected_self_inflicted_snipe")) for e in self.c0_2_duraludon_promotion_events)
        voluntary_avoids = sum(bool(e.get("voluntary_avoided_ready_duraludon")) for e in self.c0_2_duraludon_promotion_events)
        true_snipes = sum(bool(e.get("true_self_snipe")) for e in self.c0_2_duraludon_promotion_events)
        classification_counts: dict[str, int] = {}
        for e in self.c0_2_duraludon_promotion_events:
            key = str(e.get("classification", "unclassified"))
            classification_counts[key] = classification_counts.get(key, 0) + 1
        return {
            "c0_2_true_self_snipe_count": true_snipes,
            "c0_2_classification_counts": classification_counts,
            "c0_1_mill_misdetection_occurred": self.c0_1_mill_misdetection_occurred,
            "c0_1_mill_detected": self.mill_seen,
            "c0_1_mill_signal_visible": self.mill_signal_visible,
            "c0_1_mill_detection_opportunity": bool(self.expected_mill and self.mill_signal_visible),
            "c0_1_mill_false_negative": bool(self.expected_mill and self.mill_signal_visible and not self.mill_seen),
            "c0_1_mill_not_observable": bool(self.expected_mill and not self.mill_signal_visible),
            "c0_1_mill_signal_first_seen_turn": self.mill_signal_first_seen_turn,
            "c0_1_mill_first_seen_turn": self.mill_first_seen_turn,
            "c0_1_mill_first_seen_visible_opponent_ids": self.mill_first_seen_visible_opponent_ids,
            "c0_2_duraludon_promotion_events": self.c0_2_duraludon_promotion_events,
            "c0_2_promotion_event_count": len(self.c0_2_duraludon_promotion_events),
            "c0_2_promotion_violation_count": promotion_violations,
            "c0_2_self_inflicted_snipe_count": self_snipes,
            "c0_2_voluntary_avoided_ready_duraludon_count": voluntary_avoids,
            "c0_3_lethal_suppression_events": self.c0_3_lethal_suppression_events,
            "c0_3_lethal_opportunity_count": self.c0_3_lethal_opportunity_count,
            "c0_3_lethal_suppression_count": len(self.c0_3_lethal_suppression_events),
        }

    def as_dict(self) -> dict[str, Any]:
        base = {
            "first_player": self.first_player,
            "first_attack_global_turn": self.first_attack_global_turn,
            "first_attack_own_turn": self.first_attack_own_turn,
            "first_archaludon_own_turn": self.first_archaludon_own_turn,
            "attack_by_own_turn3": self.attack_by_own_turn3,
            "archaludon_by_own_turn3": self.archaludon_by_own_turn3,
            "line_count_at_own_turn3": self.line_count_at_own_turn3,
        }
        inst = self.instrumentation()
        base.update({
            "c0_1_mill_misdetection_occurred": int(bool(inst["c0_1_mill_misdetection_occurred"])),
            "c0_1_mill_detected": int(bool(inst["c0_1_mill_detected"])),
            "c0_1_mill_signal_visible": int(bool(inst["c0_1_mill_signal_visible"])),
            "c0_1_mill_detection_opportunity": int(bool(inst["c0_1_mill_detection_opportunity"])),
            "c0_1_mill_false_negative": int(bool(inst["c0_1_mill_false_negative"])),
            "c0_1_mill_not_observable": int(bool(inst["c0_1_mill_not_observable"])),
            "c0_2_promotion_event_count": inst["c0_2_promotion_event_count"],
            "c0_2_promotion_violation_count": inst["c0_2_promotion_violation_count"],
            "c0_2_self_inflicted_snipe_count": inst["c0_2_self_inflicted_snipe_count"],
            "c0_2_true_self_snipe_count": inst["c0_2_true_self_snipe_count"],
            "c0_2_voluntary_avoided_ready_duraludon_count": inst["c0_2_voluntary_avoided_ready_duraludon_count"],
            "c0_3_lethal_opportunity_count": inst["c0_3_lethal_opportunity_count"],
            "c0_3_lethal_suppression_count": inst["c0_3_lethal_suppression_count"],
        })
        return base
