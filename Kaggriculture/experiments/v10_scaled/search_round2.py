"""Round 2: ramp_per_day_3 was the only round-1 candidate with no
catastrophic-collapse seed (min=$8,075 vs $1-40 for everything else) --
a faster post-bootstrap ramp apparently spends less time in the fragile
low-hand-count zone. Combine it with reserve variations to see if the
worst case can be pushed higher still.
"""
from __future__ import annotations

import time

from experiments.v10_scaled.parametrized_agent import Params
from experiments.v10_scaled.search import evaluate

CANDIDATES: dict[str, Params] = {
    "ramp3_reserve150": Params(hire_ramp_per_day=3, ramp_reserve=150),
    "ramp3_reserve75": Params(hire_ramp_per_day=3, ramp_reserve=75),
    "ramp3_reserve400": Params(hire_ramp_per_day=3, ramp_reserve=400),
    "ramp3_cash500": Params(hire_ramp_per_day=3, cash_reserve=500),
    "ramp4_reserve150": Params(hire_ramp_per_day=4, ramp_reserve=150),
    "ramp3_phase1cap7": Params(hire_ramp_per_day=3, ramp_phase1_cap=7),
    "ramp3_cash500_phase1cap7": Params(hire_ramp_per_day=3, cash_reserve=500, ramp_phase1_cap=7),
}

if __name__ == "__main__":
    results = {}
    for name, params in CANDIDATES.items():
        t0 = time.time()
        stats = evaluate(params)
        dt = time.time() - t0
        results[name] = stats
        print(
            f"{name:28s} mean={stats['mean']:>10.0f}  median={stats['median']:>10.0f}  "
            f"min={stats['min']:>10.0f}  dead={stats['dead_crops_total']:>3d}  "
            f"escaped={stats['escaped_animals_total']:>3d}  ({dt:.0f}s)"
        )

    print("\nRanked by min (worst-case robustness):")
    for name, stats in sorted(results.items(), key=lambda kv: -kv[1]["min"]):
        print(f"  {name:28s} min={stats['min']:>10.0f}  mean={stats['mean']:>10.0f}")
