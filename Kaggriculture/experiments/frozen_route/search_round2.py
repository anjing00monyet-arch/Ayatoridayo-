"""Round 2: combine the individually-winning axes from search.py's round 1
(wheat_2 clearly best so far: fewer wheat tiles, more melon) rather than
assuming single-axis winners simply stack -- interactions are common
(e.g. more hands only helps if there's enough melon-tile-days to use
them, animal counts trade off against crop tiles).
"""
from __future__ import annotations

import time

from experiments.frozen_route.parametrized_agent import Params
from experiments.frozen_route.search import evaluate

CANDIDATES: dict[str, Params] = {
    "wheat_2_only": Params(wheat_tiles=2),
    "wheat_2_hands_11": Params(wheat_tiles=2, target_hands=11),
    "wheat_1": Params(wheat_tiles=1),
    "wheat_3": Params(wheat_tiles=3),
    "wheat_2_reserve_2000": Params(wheat_tiles=2, cash_reserve=2000),
    "wheat_2_ramp_4": Params(wheat_tiles=2, hire_ramp_per_day=4),
    "wheat_2_farmer_cow_only": Params(wheat_tiles=2, farmer_animals=("COW",)),
    "wheat_2_hand_cow_only": Params(wheat_tiles=2, hand_animals=("COW",)),
    "wheat_2_strawberry": Params(wheat_tiles=2, secondary_crop="STRAWBERRY"),
}

if __name__ == "__main__":
    results = {}
    for name, params in CANDIDATES.items():
        t0 = time.time()
        stats = evaluate(params)
        dt = time.time() - t0
        results[name] = stats
        print(f"{name:28s} mean={stats['mean']:>10.0f}  median={stats['median']:>10.0f}  "
              f"min={stats['min']:>10.0f}  max={stats['max']:>10.0f}  ({dt:.0f}s)")

    print("\nRanked by mean:")
    for name, stats in sorted(results.items(), key=lambda kv: -kv[1]["mean"]):
        print(f"  {name:28s} {stats['mean']:>10.0f}")
