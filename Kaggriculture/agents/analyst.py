"""Analyst agent: turns aggregated replay stats into a failure-cause report
saved to reports/latest_analysis.md, which the strategist agent then reads.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agents.llm_client import call
from analysis.action_analysis import analyze_matches
from analysis.profit_breakdown import aggregate, top_failures
from game.interface import MatchReplay

REPO_ROOT = Path(__file__).resolve().parent.parent
PROMPT_TEMPLATE = (REPO_ROOT / "prompts" / "analyst.md").read_text()
OUTPUT_PATH = REPO_ROOT / "reports" / "latest_analysis.md"


def run_analyst(match_stats: list[dict[str, Any]], replays: list[MatchReplay]) -> str:
    agg = aggregate(match_stats)
    action_stats = analyze_matches(replays)
    failures = top_failures(match_stats)

    prompt = (
        PROMPT_TEMPLATE.replace("{{ n_matches }}", str(len(match_stats)))
        .replace("{{ aggregate_json }}", json.dumps(agg, indent=2, ensure_ascii=False))
        .replace("{{ top_failures }}", "\n".join(f"- {f}" for f in failures) or "(なし)")
        .replace("{{ action_stats }}", json.dumps(action_stats, indent=2, ensure_ascii=False))
    )
    report = call(prompt, role="analyst")
    OUTPUT_PATH.write_text(report)
    return report


if __name__ == "__main__":
    from analysis.replay_parser import parse_matches
    from evaluation.run_matches import run_matches_for_submission

    replays = run_matches_for_submission("baseline", n_games=100)
    stats = parse_matches(replays)
    print(run_analyst(stats, replays))
