"""Multi-criteria adoption gate for a candidate agent vs. the current baseline.

harness/compare.py's mechanism_gates() already checks mechanism regressions
(mill false positives, crashes, illegal actions, self-snipe rate) against a
hard-coded absolute ceiling. This module adds the outcome-level criteria on
top: overall win rate, mirror win rate, worst single matchup, first-attack
tempo, and deck-out rate -- the checklist from the lab's design doc.

Usage:
    python -m harness.acceptance_gate baseline/summary.json candidate/summary.json
or import evaluate_gate(baseline_summary, candidate_summary) directly.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness.compare import mechanism_gates  # noqa: E402


@dataclass
class GateThresholds:
    min_total_win_rate_delta: float = 0.02
    min_mirror_win_rate_delta: float = 0.01
    max_worst_matchup_regression: float = 0.03  # matchup win rate may drop at most this much
    max_first_attack_turn_delta: float = 0.25   # own-turn count; lower is better, so delta must be <= this
    max_deckout_rate_delta: float = 0.005
    mirror_opponent_label: str = "archaludon_mirror"


@dataclass
class GateResult:
    passed: bool
    reasons_failed: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    mechanism: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "reasons_failed": self.reasons_failed,
            "metrics": self.metrics,
            "mechanism_gates": self.mechanism,
        }


def _matchup_win_rate(summary: dict[str, Any], label: str) -> float | None:
    row = (summary.get("by_opponent") or {}).get(label)
    if not row or not row.get("games"):
        return None
    return float(row["win_rate"])


def _deckout_rate(summary: dict[str, Any]) -> float:
    """Approximated from terminal reasons is not in summary.json; the closest
    proxy the harness records at summary level is mill-related fields plus
    games lost with a full deck-out signature aren't separately counted here.
    Until per-terminal-reason counts are added to summarize_rows(), this reads
    zero unless the caller supplies deckout_games/games_completed explicitly
    via the optional summary keys below (see replay_analyzer/classify_losses.py,
    which DOES compute this per game from games.csv and can inject it)."""
    games = int(summary.get("games_completed", 0) or 0)
    deckouts = summary.get("deckout_games")
    if deckouts is None or not games:
        return 0.0
    return float(deckouts) / games


def evaluate_gate(
    baseline_summary: dict[str, Any],
    candidate_summary: dict[str, Any],
    thresholds: GateThresholds | None = None,
) -> GateResult:
    t = thresholds or GateThresholds()
    reasons: list[str] = []

    base_wr = float(baseline_summary.get("win_rate", 0.0) or 0.0)
    cand_wr = float(candidate_summary.get("win_rate", 0.0) or 0.0)
    total_delta = cand_wr - base_wr
    if total_delta < t.min_total_win_rate_delta:
        reasons.append(
            f"total win rate delta {total_delta:+.4f} < required {t.min_total_win_rate_delta:+.4f}")

    base_mirror = _matchup_win_rate(baseline_summary, t.mirror_opponent_label)
    cand_mirror = _matchup_win_rate(candidate_summary, t.mirror_opponent_label)
    mirror_delta = None
    if base_mirror is not None and cand_mirror is not None:
        mirror_delta = cand_mirror - base_mirror
        if mirror_delta < t.min_mirror_win_rate_delta:
            reasons.append(
                f"mirror win rate delta {mirror_delta:+.4f} < required {t.min_mirror_win_rate_delta:+.4f}")
    else:
        reasons.append(f"mirror matchup '{t.mirror_opponent_label}' missing from one summary; cannot gate on it")

    worst_matchup, worst_delta = None, 0.0
    base_by_opp = baseline_summary.get("by_opponent") or {}
    cand_by_opp = candidate_summary.get("by_opponent") or {}
    for label in sorted(set(base_by_opp) | set(cand_by_opp)):
        b = _matchup_win_rate(baseline_summary, label)
        c = _matchup_win_rate(candidate_summary, label)
        if b is None or c is None:
            continue
        delta = c - b
        if worst_matchup is None or delta < worst_delta:
            worst_matchup, worst_delta = label, delta
    if worst_matchup is not None and worst_delta < -t.max_worst_matchup_regression:
        reasons.append(
            f"worst matchup '{worst_matchup}' regressed {worst_delta:+.4f}, "
            f"exceeds allowed -{t.max_worst_matchup_regression:.4f}")

    base_first_attack = baseline_summary.get("mean_first_attack_own_turn")
    cand_first_attack = candidate_summary.get("mean_first_attack_own_turn")
    first_attack_delta = None
    if base_first_attack is not None and cand_first_attack is not None:
        first_attack_delta = float(cand_first_attack) - float(base_first_attack)
        if first_attack_delta > t.max_first_attack_turn_delta:
            reasons.append(
                f"first-attack turn got {first_attack_delta:+.3f} slower, "
                f"exceeds allowed {t.max_first_attack_turn_delta:+.3f}")
    # else: summarize_rows() doesn't emit this field today; a caller that has
    # per-game games.csv should compute it (see board_metrics.py) and pass it
    # in via summary["mean_first_attack_own_turn"] before calling this gate.

    base_deckout = _deckout_rate(baseline_summary)
    cand_deckout = _deckout_rate(candidate_summary)
    deckout_delta = cand_deckout - base_deckout
    if deckout_delta > t.max_deckout_rate_delta:
        reasons.append(
            f"deck-out rate delta {deckout_delta:+.4f} exceeds allowed {t.max_deckout_rate_delta:+.4f}")

    mechanism = mechanism_gates(baseline_summary, candidate_summary)
    if not mechanism["passed"]:
        failed_hard = [k for k, v in mechanism["hard_gates"].items() if not v]
        failed_soft = [g["gate"] for g in mechanism["soft_gates"] if not g["passed"]]
        if failed_hard:
            reasons.append(f"mechanism hard gate(s) failed: {', '.join(failed_hard)}")
        if failed_soft:
            reasons.append(f"mechanism soft gate(s) failed: {', '.join(failed_soft)}")

    if int(candidate_summary.get("crashes", 0) or 0) != 0:
        reasons.append(f"candidate crashes = {candidate_summary.get('crashes')}, must be 0")
    if int(candidate_summary.get("illegal_actions", 0) or 0) != 0:
        reasons.append(f"candidate illegal_actions = {candidate_summary.get('illegal_actions')}, must be 0")

    return GateResult(
        passed=not reasons,
        reasons_failed=reasons,
        metrics={
            "total_win_rate_delta": total_delta,
            "mirror_win_rate_delta": mirror_delta,
            "worst_matchup": worst_matchup,
            "worst_matchup_delta": worst_delta if worst_matchup is not None else None,
            "first_attack_turn_delta": first_attack_delta,
            "deckout_rate_delta": deckout_delta,
            "crashes": candidate_summary.get("crashes"),
            "illegal_actions": candidate_summary.get("illegal_actions"),
        },
        mechanism=mechanism,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("baseline_summary", type=Path)
    parser.add_argument("candidate_summary", type=Path)
    parser.add_argument("--out", type=Path, help="write the gate result JSON here")
    args = parser.parse_args()

    baseline = json.loads(args.baseline_summary.read_text(encoding="utf-8"))
    candidate = json.loads(args.candidate_summary.read_text(encoding="utf-8"))
    result = evaluate_gate(baseline, candidate)
    payload = result.to_dict()
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if args.out:
        args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    sys.exit(0 if result.passed else 1)


if __name__ == "__main__":
    main()
