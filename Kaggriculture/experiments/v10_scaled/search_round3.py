"""Round 3: ramp3_cash500_phase1cap7 was a breakthrough over round 2's
other candidates (mean $37,671, min $36,148, zero escaped animals, zero
dead crops across 10 seeds -- vs $7-20k means with frequent near-zero
collapses everywhere else). Push a bit further around that combination
to check whether it's a local optimum or more headroom remains.
"""
from __future__ import annotations

import time

from experiments.v10_scaled.parametrized_agent import Params
from experiments.v10_scaled.search import evaluate

CANDIDATES: dict[str, Params] = {
    "cash500_cap7": Params(hire_ramp_per_day=3, cash_reserve=500, ramp_phase1_cap=7),
    "cash700_cap7": Params(hire_ramp_per_day=3, cash_reserve=700, ramp_phase1_cap=7),
    "cash500_cap9": Params(hire_ramp_per_day=3, cash_reserve=500, ramp_phase1_cap=9),
    "cash500_cap7_ramp4": Params(hire_ramp_per_day=4, cash_reserve=500, ramp_phase1_cap=7),
    "cash500_cap7_reserve300": Params(hire_ramp_per_day=3, cash_reserve=500, ramp_phase1_cap=7, ramp_reserve=300),
    "cash500_cap7_landday5": Params(hire_ramp_per_day=3, cash_reserve=500, ramp_phase1_cap=7, land_day=5),
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
