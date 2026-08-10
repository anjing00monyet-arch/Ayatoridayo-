"""The acceptance gate: a candidate only gets promoted to baseline if it
clears *all* of these, not just "wins on average". A candidate that's
great in most games but occasionally crashes or tanks in one scenario is
rejected -- that's the whole point of the gate.

Thresholds are the ones from the project design notes; tune per-competition
but keep them explicit and reviewed, never silently loosened to make a
candidate pass.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ValidationResult:
    mean_profit_delta: float
    median_profit_delta: float
    win_rate_delta: float
    crash_count: int
    invalid_action_count: int
    worst_scenario_delta: float


def passes_acceptance_gate(result: ValidationResult) -> bool:
    return (
        result.mean_profit_delta >= 5000
        and result.median_profit_delta > 0
        and result.win_rate_delta >= 0.02
        and result.crash_count == 0
        and result.invalid_action_count == 0
        and result.worst_scenario_delta >= -2000
    )


def gate_report(result: ValidationResult) -> str:
    """Human-readable pass/fail breakdown, one line per criterion."""
    checks = [
        ("mean_profit_delta >= 5000", result.mean_profit_delta >= 5000, result.mean_profit_delta),
        ("median_profit_delta > 0", result.median_profit_delta > 0, result.median_profit_delta),
        ("win_rate_delta >= 0.02", result.win_rate_delta >= 0.02, result.win_rate_delta),
        ("crash_count == 0", result.crash_count == 0, result.crash_count),
        ("invalid_action_count == 0", result.invalid_action_count == 0, result.invalid_action_count),
        ("worst_scenario_delta >= -2000", result.worst_scenario_delta >= -2000, result.worst_scenario_delta),
    ]
    lines = [f"{'PASS' if ok else 'FAIL'}  {label}  (actual: {actual})" for label, ok, actual in checks]
    overall = "ACCEPTED" if all(ok for _, ok, _ in checks) else "REJECTED"
    return f"{overall}\n" + "\n".join(lines)
