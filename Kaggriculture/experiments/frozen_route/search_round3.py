"""Round 3: fine-tune around round 2's winner (wheat_tiles=1,
cash_reserve=1000, mean=$60,203) -- check whether even less wheat or an
even smaller reserve helps further, or whether 1/1000 is the local
optimum.
"""
from __future__ import annotations

import time

from experiments.frozen_route.parametrized_agent import Params
from experiments.frozen_route.search import evaluate

CANDIDATES: dict[str, Params] = {
    "wheat_1_reserve_1000": Params(wheat_tiles=1, cash_reserve=1000),  # round 2 winner, re-confirm
    "wheat_0_reserve_1000": Params(wheat_tiles=0, cash_reserve=1000),
    "wheat_1_reserve_500": Params(wheat_tiles=1, cash_reserve=500),
    "wheat_0_reserve_500": Params(wheat_tiles=0, cash_reserve=500),
    "wheat_1_reserve_750": Params(wheat_tiles=1, cash_reserve=750),
    "wheat_1_reserve_1250": Params(wheat_tiles=1, cash_reserve=1250),
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
