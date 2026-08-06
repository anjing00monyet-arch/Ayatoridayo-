"""Multi-seed search over v10_scaled's cash-flow knobs, replacing the
single-seed manual tuning that produced 7 rounds of one-collapse-at-a-time
fixes without ever converging on a stable configuration.

Evaluates each candidate against `"random"` over a fixed seed set,
reporting mean/median/min plus stability signals (dead crops, escaped
animals, crashes) that manual single-seed checks were missing.
"""
from __future__ import annotations

import statistics

from experiments.v10_scaled.parametrized_agent import Params, make_agent
from game.kaggriculture_env import play_match, final_money, crashed
from analysis.replay_parser import parse_match

SEEDS = list(range(10))


def evaluate(params: Params, seeds: list[int] = SEEDS) -> dict:
    agent = make_agent(params)
    banks, dead, escaped, crashes = [], [], [], 0
    for seed in seeds:
        replay = play_match(agent, "random", seed=seed, configuration={"episodeSteps": 720})
        banks.append(final_money(replay, player=0))
        parsed = parse_match(replay, player=0)
        dead.append(parsed["dead_crops"])
        escaped.append(parsed["escaped_animals"])
        if crashed(replay, player=0):
            crashes += 1
    return {
        "mean": statistics.mean(banks),
        "median": statistics.median(banks),
        "min": min(banks),
        "max": max(banks),
        "dead_crops_total": sum(dead),
        "escaped_animals_total": sum(escaped),
        "crashes": crashes,
        "banks": banks,
    }


if __name__ == "__main__":
    import time

    CANDIDATES: dict[str, Params] = {
        "baseline_150": Params(ramp_reserve=150),
        "reserve_75": Params(ramp_reserve=75),
        "reserve_250": Params(ramp_reserve=250),
        "reserve_400": Params(ramp_reserve=400),
        "phase1_cap_7": Params(ramp_reserve=150, ramp_phase1_cap=7),
        "phase1_cap_4": Params(ramp_reserve=150, ramp_phase1_cap=4),
        "ramp_per_day_1": Params(ramp_reserve=150, hire_ramp_per_day=1),
        "ramp_per_day_3": Params(ramp_reserve=150, hire_ramp_per_day=3),
        "cash_reserve_100": Params(ramp_reserve=150, cash_reserve=100),
        "cash_reserve_500": Params(ramp_reserve=150, cash_reserve=500),
    }

    results = {}
    for name, params in CANDIDATES.items():
        t0 = time.time()
        stats = evaluate(params)
        dt = time.time() - t0
        results[name] = stats
        print(
            f"{name:20s} mean={stats['mean']:>10.0f}  median={stats['median']:>10.0f}  "
            f"min={stats['min']:>10.0f}  dead={stats['dead_crops_total']:>3d}  "
            f"escaped={stats['escaped_animals_total']:>3d}  crashes={stats['crashes']}  ({dt:.0f}s)"
        )

    print("\nRanked by mean:")
    for name, stats in sorted(results.items(), key=lambda kv: -kv[1]["mean"]):
        print(f"  {name:20s} {stats['mean']:>10.0f}  min={stats['min']:>10.0f}")
