"""Preview the exact game schedule a config would produce, without running any games.

The actual scheduling logic lives in harness/utils.py's exact_weighted_schedule()
-- run_batch.py and compare_ab.py already call it internally. This is a
standalone CLI over the same function, for sanity-checking opponent weights
and game counts (e.g. "does tusk_mill really get 75 games out of 500?")
before spending an hour running them.

    python seed_schedule.py configs/batch_example.json --games 500
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from harness.utils import exact_weighted_schedule, read_json


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("config", type=Path)
    parser.add_argument("--games", type=int, help="override the config's games/games_per_variant")
    parser.add_argument("--schedule-seed", type=int, help="override the config's schedule_seed")
    args = parser.parse_args()

    cfg = read_json(args.config)
    games = args.games or int(cfg.get("games", cfg.get("games_per_variant", 100)))
    seed = args.schedule_seed if args.schedule_seed is not None else int(cfg.get("schedule_seed", 0))
    schedule = exact_weighted_schedule(cfg["opponents"], games, seed)

    counts = Counter(entry["label"] for entry in schedule)
    print(json.dumps({"games": games, "schedule_seed": seed, "by_opponent": dict(counts)},
                     ensure_ascii=False, indent=2))
    total_weight = sum(float(o.get("weight", 1.0)) for o in cfg["opponents"])
    for opp in cfg["opponents"]:
        label = opp["label"]
        expected = games * float(opp.get("weight", 1.0)) / total_weight
        print(f"  {label:<20} expected={expected:7.2f}  actual={counts.get(label, 0)}")


if __name__ == "__main__":
    main()
