from __future__ import annotations

from typing import Any

REQUIRED_OBS_KEYS = ("current", "logs", "select")
REQUIRED_ENTRY_KEYS = ("action", "info", "observation", "reward", "status")


def validate_replay_payload(data: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    steps = data.get("steps")
    if not isinstance(steps, list) or not steps:
        errors.append("steps must be a non-empty list")
        return {"ok": False, "errors": errors, "warnings": warnings}

    for step_index, step in enumerate(steps):
        if not isinstance(step, list) or len(step) != 2:
            errors.append(f"step {step_index}: expected exactly two player entries")
            continue
        for player, entry in enumerate(step):
            if not isinstance(entry, dict):
                errors.append(f"step {step_index} player {player}: entry is not an object")
                continue
            for key in REQUIRED_ENTRY_KEYS:
                if key not in entry:
                    errors.append(f"step {step_index} player {player}: missing entry.{key}")
            obs = entry.get("observation")
            if not isinstance(obs, dict):
                errors.append(f"step {step_index} player {player}: observation is not an object")
                continue
            for key in REQUIRED_OBS_KEYS:
                if key not in obs:
                    errors.append(f"step {step_index} player {player}: missing observation.{key}")

    info = data.get("info")
    if not isinstance(info, dict):
        errors.append("info must be an object")
    else:
        for key in (
            "c0_1_mill_misdetection_occurred",
            "c0_2_duraludon_promotion_events",
            "c0_3_lethal_suppression_events",
        ):
            if key not in info:
                errors.append(f"info missing instrumentation field: {key}")

    rewards = data.get("rewards")
    statuses = data.get("statuses")
    if not isinstance(rewards, list) or len(rewards) != 2:
        errors.append("rewards must contain two values")
    if not isinstance(statuses, list) or len(statuses) != 2:
        errors.append("statuses must contain two values")

    terminal = steps[-1] if steps else []
    if isinstance(terminal, list) and len(terminal) == 2:
        terminal_statuses = [entry.get("status") if isinstance(entry, dict) else None for entry in terminal]
        if data.get("statuses") == ["DONE", "DONE"] and terminal_statuses != ["DONE", "DONE"]:
            warnings.append("top-level statuses are DONE but final step entries are not both DONE")

    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "step_count": len(steps),
    }


def c0_success_checks(summary: dict[str, Any], *, minimum_games: int) -> dict[str, Any]:
    completed = int(summary.get("games_completed", 0) or 0)
    promotion_events = int(summary.get("c0_2_promotion_events", 0) or 0)
    suspected_snipes = int(summary.get("c0_2_self_inflicted_snipes", 0) or 0)
    true_snipes = int(summary.get("c0_2_true_self_snipes", 0) or 0)
    lethal_opportunities = int(summary.get("c0_3_lethal_opportunities", 0) or 0)
    lethal_suppressions = int(summary.get("c0_3_lethal_opportunities_suppressed", summary.get("c0_3_lethal_suppressions", 0)) or 0)
    snipe_rate = true_snipes / promotion_events if promotion_events else 0.0
    lethal_rate = lethal_suppressions / lethal_opportunities if lethal_opportunities else 0.0

    checks = {
        "trial_count": {
            "passed": completed >= minimum_games,
            "actual": completed,
            "required": minimum_games,
        },
        "no_crashes": {
            "passed": int(summary.get("crashes", 0) or 0) == 0,
            "actual": int(summary.get("crashes", 0) or 0),
            "required": 0,
        },
        "no_illegal_actions": {
            "passed": int(summary.get("illegal_actions", 0) or 0) == 0,
            "actual": int(summary.get("illegal_actions", 0) or 0),
            "required": 0,
        },
        "replay_structure_valid": {
            "passed": int(summary.get("replay_validation_failures", 0) or 0) == 0,
            "actual": int(summary.get("replay_validation_failures", 0) or 0),
            "required": 0,
        },
        "c0_1_no_mill_false_positives": {
            "passed": int(summary.get("c0_1_mill_misdetections", 0) or 0) == 0,
            "actual": int(summary.get("c0_1_mill_misdetections", 0) or 0),
            "required": 0,
        },
        "c0_2_true_self_snipes_under_5pct": {
            "passed": snipe_rate < 0.05,
            "actual_rate": snipe_rate,
            "numerator": true_snipes,
            "suspected_count_for_review": suspected_snipes,
            "denominator": promotion_events,
            "required": "<0.05",
        },
        "c0_3_lethal_suppressions_minimal": {
            "passed": lethal_rate <= 0.01,
            "actual_rate": lethal_rate,
            "numerator": lethal_suppressions,
            "denominator": lethal_opportunities,
            "required": "<=0.01",
        },
    }
    return {
        "passed": all(bool(item.get("passed")) for item in checks.values()),
        "checks": checks,
    }
