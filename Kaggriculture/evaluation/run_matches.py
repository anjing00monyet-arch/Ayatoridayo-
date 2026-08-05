"""Runs an agent through N matches under fixed seeds and saves raw replays
to disk (`replays/<name>/seed_<n>.json`). This is step (5) evaluation in the
improvement loop, and also what a standalone "run 500-1000 games" batch job
(e.g. a GitHub Actions job) would call.
"""
from __future__ import annotations

import importlib.util
import json
from dataclasses import asdict
from pathlib import Path

from game.interface import AgentFn, MatchReplay, play_match

REPO_ROOT = Path(__file__).resolve().parent.parent


def load_agent(main_py_path: str | Path) -> AgentFn:
    """Loads the `agent(observation, configuration)` function from a
    submissions/<name>/main.py file without needing it importable as a
    package (handy for candidate files that get overwritten repeatedly).
    """
    path = Path(main_py_path)
    spec = importlib.util.spec_from_file_location(path.stem + "_" + path.parent.name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module.agent


def create_fixed_scenarios(n_games: int, seed_start: int = 0) -> list[int]:
    """Fixed seed list so baseline and candidate are compared on identical
    scenarios (evaluate_ab's `identical_scenarios=True`).
    """
    return list(range(seed_start, seed_start + n_games))


def run_matches(
    agent: AgentFn,
    seeds: list[int],
    out_dir: str | Path,
    max_days: int = 30,
    env_path: str | None = None,
) -> list[MatchReplay]:
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    replays = []
    for seed in seeds:
        replay = play_match(agent, seed=seed, max_days=max_days, env_path=env_path)
        replays.append(replay)
        (out_path / f"seed_{seed}.json").write_text(json.dumps(asdict(replay), indent=2))
    return replays


def run_matches_for_submission(
    submission_name: str,
    n_games: int = 1000,
    seed_start: int = 0,
    max_days: int = 30,
    env_path: str | None = None,
) -> list[MatchReplay]:
    """Convenience entry point: `run_matches_for_submission("baseline", 1000)`."""
    main_py = REPO_ROOT / "submissions" / submission_name / "main.py"
    agent = load_agent(main_py)
    seeds = create_fixed_scenarios(n_games, seed_start)
    out_dir = REPO_ROOT / "replays" / submission_name
    return run_matches(agent, seeds, out_dir, max_days=max_days, env_path=env_path)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("submission", choices=["baseline", "candidate"])
    parser.add_argument("--games", type=int, default=1000)
    parser.add_argument("--seed-start", type=int, default=0)
    parser.add_argument("--max-days", type=int, default=30)
    args = parser.parse_args()

    replays = run_matches_for_submission(
        args.submission, n_games=args.games, seed_start=args.seed_start, max_days=args.max_days
    )
    print(f"Ran {len(replays)} matches for '{args.submission}', saved to replays/{args.submission}/")
