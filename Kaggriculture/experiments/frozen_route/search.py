"""Evaluates hand-picked Params variants (informed by this session's prior
manual tuning rounds -- see opponents/README.md and
reports/latest_analysis.md for what's already known to help/hurt) against
a fixed set of seeds, to find the strongest configuration before freezing
its trajectory (see freeze.py).

Not a blind/random search: every axis here was chosen because we have a
specific open question about it from earlier rounds (e.g. "is TARGET_HANDS
10 really optimal, or just the first value that worked"), and pure
brute-force over the full parameter space is intractable given ~4-9s per
720-turn game.
"""
from __future__ import annotations

import statistics
import time

from experiments.frozen_route.parametrized_agent import Params, make_agent
from game.kaggriculture_env import play_match, final_money

SEEDS = list(range(5))  # same seeds reused for every candidate -> paired comparison
OPPONENT = "random"
EPISODE_STEPS = 720

CANDIDATES: dict[str, Params] = {
    "v8_baseline": Params(),
    "wheat_2": Params(wheat_tiles=2),
    "wheat_6": Params(wheat_tiles=6),
    "wheat_8": Params(wheat_tiles=8),
    "hands_9": Params(target_hands=9),
    "hands_11": Params(target_hands=11),
    "hands_12": Params(target_hands=12),
    "ramp_2": Params(hire_ramp_per_day=2),
    "ramp_4": Params(hire_ramp_per_day=4),
    "reserve_1000": Params(cash_reserve=1000),
    "reserve_2000": Params(cash_reserve=2000),
    "farmer_cow_only": Params(farmer_animals=("COW",)),
    "farmer_none": Params(farmer_animals=()),
    "secondary_strawberry": Params(secondary_crop="STRAWBERRY"),
    "secondary_tomato": Params(secondary_crop="TOMATO"),
    "hand_cow_only": Params(hand_animals=("COW",)),
}


def evaluate(params: Params, seeds: list[int] = SEEDS) -> dict:
    agent = make_agent(params)
    banks = []
    for seed in seeds:
        replay = play_match(agent, OPPONENT, seed=seed, configuration={"episodeSteps": EPISODE_STEPS})
        banks.append(final_money(replay, 0))
    return {
        "mean": statistics.mean(banks),
        "median": statistics.median(banks),
        "min": min(banks),
        "max": max(banks),
        "banks": banks,
    }


if __name__ == "__main__":
    results = {}
    for name, params in CANDIDATES.items():
        t0 = time.time()
        stats = evaluate(params)
        dt = time.time() - t0
        results[name] = stats
        print(f"{name:24s} mean={stats['mean']:>10.0f}  median={stats['median']:>10.0f}  "
              f"min={stats['min']:>10.0f}  max={stats['max']:>10.0f}  ({dt:.0f}s)")

    print("\nRanked by mean:")
    for name, stats in sorted(results.items(), key=lambda kv: -kv[1]["mean"]):
        print(f"  {name:24s} {stats['mean']:>10.0f}")
