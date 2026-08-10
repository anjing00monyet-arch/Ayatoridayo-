"""Runs an agent through N Kaggriculture matches under fixed seeds against a
fixed opponent, and saves raw replays to disk
(`replays/<name>/seed_<n>.json`). This is the "run 500-1000 games" batch job
(e.g. a scheduled GitHub Actions job) and step 1 of the improvement loop.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from game.kaggriculture_env import play_match

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_EPISODE_STEPS = 720


def load_agent(main_py_path: str | Path):
    """Loads the `agent(observation)` function from a submissions/<name>/main.py
    file without needing it importable as a package (handy for candidate
    files that get overwritten repeatedly).
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
    agent,
    seeds: list[int],
    out_dir: str | Path,
    opponent="random",
    episode_steps: int = DEFAULT_EPISODE_STEPS,
) -> list[dict]:
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    replays = []
    for seed in seeds:
        replay = play_match(agent, opponent, seed=seed, configuration={"episodeSteps": episode_steps})
        replays.append(replay)
        (out_path / f"seed_{seed}.json").write_text(json.dumps(replay))
    return replays


def run_matches_for_submission(
    submission_name: str,
    n_games: int = 1000,
    seed_start: int = 0,
    opponent="random",
    episode_steps: int = DEFAULT_EPISODE_STEPS,
) -> list[dict]:
    """Convenience entry point: `run_matches_for_submission("baseline", 1000)`."""
    main_py = REPO_ROOT / "submissions" / submission_name / "main.py"
    agent = load_agent(main_py)
    seeds = create_fixed_scenarios(n_games, seed_start)
    out_dir = REPO_ROOT / "replays" / submission_name
    return run_matches(agent, seeds, out_dir, opponent=opponent, episode_steps=episode_steps)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("submission", choices=["baseline", "candidate"])
    parser.add_argument("--games", type=int, default=1000)
    parser.add_argument("--seed-start", type=int, default=0)
    parser.add_argument("--opponent", default="random")
    parser.add_argument("--episode-steps", type=int, default=DEFAULT_EPISODE_STEPS)
    args = parser.parse_args()

    replays = run_matches_for_submission(
        args.submission,
        n_games=args.games,
        seed_start=args.seed_start,
        opponent=args.opponent,
        episode_steps=args.episode_steps,
    )
    print(f"Ran {len(replays)} matches for '{args.submission}', saved to replays/{args.submission}/")
