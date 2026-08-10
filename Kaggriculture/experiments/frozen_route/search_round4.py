"""Round 4: reserve_500 beat reserve_1000 in round 3 (wheat_1: $62,416,
wheat_0: $62,411 -- essentially tied). Check whether an even smaller
reserve keeps helping or reserve_500 is the local optimum, and settle
the wheat_0 vs wheat_1 tie with a larger seed set.
"""
from __future__ import annotations

import time

from experiments.frozen_route.parametrized_agent import Params
from experiments.frozen_route.search import evaluate

MORE_SEEDS = list(range(12))

CANDIDATES: dict[str, Params] = {
    "wheat_1_reserve_250": Params(wheat_tiles=1, cash_reserve=250),
    "wheat_0_reserve_250": Params(wheat_tiles=0, cash_reserve=250),
    "wheat_1_reserve_0": Params(wheat_tiles=1, cash_reserve=0),
    "wheat_0_reserve_0": Params(wheat_tiles=0, cash_reserve=0),
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

    print("\nRanked by mean (5 seeds):")
    for name, stats in sorted(results.items(), key=lambda kv: -kv[1]["mean"]):
        print(f"  {name:24s} {stats['mean']:>10.0f}")

    print("\nTie-break wheat_0 vs wheat_1 @ reserve_500 with 12 seeds:")
    for name, params in {
        "wheat_1_reserve_500": Params(wheat_tiles=1, cash_reserve=500),
        "wheat_0_reserve_500": Params(wheat_tiles=0, cash_reserve=500),
    }.items():
        t0 = time.time()
        stats = evaluate(params, seeds=MORE_SEEDS)
        dt = time.time() - t0
        print(f"  {name:24s} mean={stats['mean']:>10.0f}  median={stats['median']:>10.0f}  "
              f"min={stats['min']:>10.0f}  max={stats['max']:>10.0f}  ({dt:.0f}s)")
