"""A/B compares baseline vs candidate under identical seeds and produces the
ValidationResult that evaluation/acceptance_gate.py judges.
"""
from __future__ import annotations

import statistics
from pathlib import Path

from analysis.replay_parser import parse_match
from evaluation.acceptance_gate import ValidationResult
from evaluation.run_matches import create_fixed_scenarios, load_agent, run_matches

REPO_ROOT = Path(__file__).resolve().parent.parent


def evaluate_ab(
    baseline_main_py: str | Path,
    candidate_main_py: str | Path,
    games: int = 1000,
    seed_start: int = 0,
    max_days: int = 30,
    env_path: str | None = None,
    baseline_replay_dir: str | Path = REPO_ROOT / "replays" / "baseline",
    candidate_replay_dir: str | Path = REPO_ROOT / "replays" / "candidate",
) -> ValidationResult:
    seeds = create_fixed_scenarios(games, seed_start)  # identical_scenarios=True

    baseline_agent = load_agent(baseline_main_py)
    candidate_agent = load_agent(candidate_main_py)

    baseline_replays = run_matches(baseline_agent, seeds, baseline_replay_dir, max_days, env_path)
    candidate_replays = run_matches(candidate_agent, seeds, candidate_replay_dir, max_days, env_path)

    baseline_stats = [parse_match(r) for r in baseline_replays]
    candidate_stats = [parse_match(r) for r in candidate_replays]

    deltas = [
        c["final_bank"] - b["final_bank"] for b, c in zip(baseline_stats, candidate_stats)
    ]
    wins = sum(1 for d in deltas if d > 0)

    return ValidationResult(
        mean_profit_delta=statistics.mean(deltas),
        median_profit_delta=statistics.median(deltas),
        win_rate_delta=(wins / len(deltas)) - 0.5,
        crash_count=sum(1 for c in candidate_stats if c["crashed"]),
        invalid_action_count=sum(c["invalid_actions"] for c in candidate_stats),
        worst_scenario_delta=min(deltas),
    )


if __name__ == "__main__":
    import argparse

    from evaluation.acceptance_gate import gate_report, passes_acceptance_gate

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", type=int, default=1000)
    parser.add_argument("--seed-start", type=int, default=0)
    args = parser.parse_args()

    result = evaluate_ab(
        REPO_ROOT / "submissions" / "baseline" / "main.py",
        REPO_ROOT / "submissions" / "candidate" / "main.py",
        games=args.games,
        seed_start=args.seed_start,
    )
    print(gate_report(result))
    print("PASSES GATE:", passes_acceptance_gate(result))
