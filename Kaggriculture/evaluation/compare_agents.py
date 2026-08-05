"""A/B compares baseline vs candidate head-to-head under identical seeds and
produces the ValidationResult that evaluation/acceptance_gate.py judges.

Player order is alternated by seed parity so neither agent gets a
systematic first-mover advantage across the sample.
"""
from __future__ import annotations

import json
import statistics
from pathlib import Path

from analysis.action_analysis import analyze_actions
from evaluation.acceptance_gate import ValidationResult
from evaluation.run_matches import create_fixed_scenarios, load_agent
from game.kaggriculture_env import play_match

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_EPISODE_STEPS = 720


def evaluate_ab(
    baseline_main_py: str | Path,
    candidate_main_py: str | Path,
    games: int = 1000,
    seed_start: int = 0,
    episode_steps: int = DEFAULT_EPISODE_STEPS,
    replay_dir: str | Path = REPO_ROOT / "replays" / "ab_test",
) -> ValidationResult:
    seeds = create_fixed_scenarios(games, seed_start)  # identical_scenarios=True

    baseline_agent = load_agent(baseline_main_py)
    candidate_agent = load_agent(candidate_main_py)

    replay_path = Path(replay_dir)
    replay_path.mkdir(parents=True, exist_ok=True)

    deltas = []
    crash_count = 0
    invalid_action_count = 0

    for seed in seeds:
        candidate_first = seed % 2 == 0
        if candidate_first:
            replay = play_match(
                candidate_agent, baseline_agent, seed=seed, configuration={"episodeSteps": episode_steps}
            )
            candidate_idx, baseline_idx = 0, 1
        else:
            replay = play_match(
                baseline_agent, candidate_agent, seed=seed, configuration={"episodeSteps": episode_steps}
            )
            candidate_idx, baseline_idx = 1, 0

        (replay_path / f"seed_{seed}.json").write_text(json.dumps(replay))

        final_states = replay["steps"][-1]
        candidate_money = float(final_states[candidate_idx]["reward"] or 0.0)
        baseline_money = float(final_states[baseline_idx]["reward"] or 0.0)
        deltas.append(candidate_money - baseline_money)

        if any(step[candidate_idx]["status"] in ("ERROR", "TIMEOUT", "INVALID") for step in replay["steps"]):
            crash_count += 1
        invalid_action_count += analyze_actions(replay, candidate_idx)["blocked_plant_actions"]

    wins = sum(1 for d in deltas if d > 0)

    return ValidationResult(
        mean_profit_delta=statistics.mean(deltas),
        median_profit_delta=statistics.median(deltas),
        win_rate_delta=(wins / len(deltas)) - 0.5,
        crash_count=crash_count,
        invalid_action_count=invalid_action_count,
        worst_scenario_delta=min(deltas),
    )


if __name__ == "__main__":
    import argparse

    from evaluation.acceptance_gate import gate_report, passes_acceptance_gate

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", type=int, default=1000)
    parser.add_argument("--seed-start", type=int, default=0)
    parser.add_argument("--episode-steps", type=int, default=DEFAULT_EPISODE_STEPS)
    args = parser.parse_args()

    result = evaluate_ab(
        REPO_ROOT / "submissions" / "baseline" / "main.py",
        REPO_ROOT / "submissions" / "candidate" / "main.py",
        games=args.games,
        seed_start=args.seed_start,
        episode_steps=args.episode_steps,
    )
    print(gate_report(result))
    print("PASSES GATE:", passes_acceptance_gate(result))
