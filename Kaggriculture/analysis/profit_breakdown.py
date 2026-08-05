"""Aggregates many parsed match stats (analysis.replay_parser.MatchStats)
into the summary numbers the analyst/strategist agents and the acceptance
gate actually consume. A single match is noise; hundreds aggregated is
signal.
"""
from __future__ import annotations

import statistics
from typing import Any

MatchStats = dict[str, Any]


def aggregate(matches: list[MatchStats]) -> dict[str, Any]:
    if not matches:
        raise ValueError("aggregate() requires at least one match")

    banks = [m["final_bank"] for m in matches]
    revenue_totals: dict[str, float] = {}
    for m in matches:
        for item, amount in m["revenue_by_item"].items():
            revenue_totals[item] = revenue_totals.get(item, 0.0) + amount

    total_cost = sum(
        m["worker_cost"] + m["seed_cost"] + m["animal_cost"] + m["land_cost"] + m["product_cost"]
        for m in matches
    )
    cost_breakdown = {
        "worker": sum(m["worker_cost"] for m in matches),
        "seed": sum(m["seed_cost"] for m in matches),
        "animal": sum(m["animal_cost"] for m in matches),
        "land": sum(m["land_cost"] for m in matches),
        "product": sum(m["product_cost"] for m in matches),
    }
    cost_share = (
        {k: v / total_cost for k, v in cost_breakdown.items()} if total_cost else cost_breakdown
    )

    return {
        "n_matches": len(matches),
        "mean_bank": statistics.mean(banks),
        "median_bank": statistics.median(banks),
        "stdev_bank": statistics.pstdev(banks) if len(banks) > 1 else 0.0,
        "worst_bank": min(banks),
        "best_bank": max(banks),
        "revenue_by_item": revenue_totals,
        "cost_breakdown": cost_breakdown,
        "cost_share": cost_share,
        "avg_idle_actions": statistics.mean(m["idle_actions"] for m in matches),
        "avg_dead_crops": statistics.mean(m["dead_crops"] for m in matches),
        "avg_escaped_animals": statistics.mean(m["escaped_animals"] for m in matches),
        "avg_missed_harvests": statistics.mean(m["missed_harvests"] for m in matches),
        "avg_late_investment_loss": statistics.mean(m["late_investment_loss"] for m in matches),
        "crash_count": sum(1 for m in matches if m["crashed"]),
        "top_critical_failures": top_failures(matches),
    }


def top_failures(matches: list[MatchStats], limit: int = 10) -> list[str]:
    seen: dict[str, int] = {}
    for m in matches:
        for failure in m["critical_failures"]:
            # collapse "day N: X" into "X" so repeated patterns count together
            key = failure.split(": ", 1)[-1] if ": " in failure else failure
            seen[key] = seen.get(key, 0) + 1
    return [f"{count}x: {key}" for key, count in sorted(seen.items(), key=lambda kv: -kv[1])[:limit]]
