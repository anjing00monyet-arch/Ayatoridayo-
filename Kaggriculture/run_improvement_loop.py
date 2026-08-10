"""Orchestrates the full improvement loop:

    baseline --run_matches--> replays --analyst--> report --strategist--> proposals
        --(for each proposal)--> coder --reviewer(pre-check)--> compare_agents (A/B)
        --acceptance_gate--> promote candidate to new baseline, log to reports/

In manual mode (no ANTHROPIC_API_KEY, see agents/llm_client.py) this stops
at whichever agent step needs a human/Claude Code session to answer a
pending prompt in reports/pending_prompts/, and tells you exactly which
file to run through Claude Code and where to save the reply. Re-running
this script picks up where it left off.

This is the "should build first" semi-automatic version described in the
project notes: it does NOT auto-push to git. Promoted candidates land in
submissions/baseline/main.py and reports/experiment_history.csv; commit and
open a PR yourself (or extend `save_as_new_best` below) once you've reviewed
the results.
"""
from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path

from agents.analyst import run_analyst
from agents.coder import run_coder
from agents.llm_client import PendingManualReview
from agents.reviewer import run_reviewer
from agents.strategist import run_strategist
from analysis.replay_parser import parse_matches
from evaluation.acceptance_gate import gate_report, passes_acceptance_gate
from evaluation.compare_agents import evaluate_ab
from evaluation.run_matches import run_matches_for_submission

REPO_ROOT = Path(__file__).resolve().parent
BASELINE_MAIN = REPO_ROOT / "submissions" / "baseline" / "main.py"
CANDIDATE_MAIN = REPO_ROOT / "submissions" / "candidate" / "main.py"
HISTORY_CSV = REPO_ROOT / "reports" / "experiment_history.csv"

HISTORY_FIELDS = [
    "timestamp",
    "proposal_title",
    "accepted",
    "mean_profit_delta",
    "median_profit_delta",
    "win_rate_delta",
    "crash_count",
    "invalid_action_count",
    "worst_scenario_delta",
]


def log_experiment(proposal_title: str, accepted: bool, result) -> None:
    is_new = not HISTORY_CSV.exists()
    with HISTORY_CSV.open("a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=HISTORY_FIELDS)
        if is_new:
            writer.writeheader()
        writer.writerow(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "proposal_title": proposal_title,
                "accepted": accepted,
                "mean_profit_delta": result.mean_profit_delta,
                "median_profit_delta": result.median_profit_delta,
                "win_rate_delta": result.win_rate_delta,
                "crash_count": result.crash_count,
                "invalid_action_count": result.invalid_action_count,
                "worst_scenario_delta": result.worst_scenario_delta,
            }
        )


def save_as_new_best(candidate_src: str) -> None:
    BASELINE_MAIN.write_text(candidate_src)


def improvement_loop(games: int = 1000, max_proposals: int = 3) -> None:
    print(f"[1/6] Evaluating current baseline over {games} games...")
    baseline_replays = run_matches_for_submission("baseline", n_games=games)
    baseline_stats = parse_matches(baseline_replays, player=0)

    print("[2/6] Running analyst agent...")
    run_analyst(baseline_stats, baseline_replays)

    print("[3/6] Running strategist agent...")
    proposals = run_strategist()
    if not proposals:
        print("No proposals generated. Nothing to do.")
        return
    print(f"Got {len(proposals)} proposal(s): {[p.title for p in proposals]}")

    baseline_src = BASELINE_MAIN.read_text()
    for proposal in proposals[:max_proposals]:
        print(f"\n[4/6] Coding proposal: {proposal.title}")
        candidate_src = run_coder(proposal, baseline_src)

        print("[5/6] Reviewer pre-check...")
        approved, review_text = run_reviewer(proposal, baseline_src, candidate_src)
        if not approved:
            print(f"Reviewer rejected '{proposal.title}':\n{review_text}")
            continue

        print(f"[6/6] A/B evaluating over {games} games...")
        result = evaluate_ab(BASELINE_MAIN, CANDIDATE_MAIN, games=games)
        print(gate_report(result))

        accepted = passes_acceptance_gate(result)
        log_experiment(proposal.title, accepted, result)

        if accepted:
            print(f"ACCEPTED: promoting '{proposal.title}' to new baseline.")
            save_as_new_best(candidate_src)
            baseline_src = candidate_src
        else:
            print(f"REJECTED: '{proposal.title}' did not clear the acceptance gate.")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", type=int, default=1000)
    parser.add_argument("--max-proposals", type=int, default=3)
    args = parser.parse_args()

    try:
        improvement_loop(games=args.games, max_proposals=args.max_proposals)
    except PendingManualReview as e:
        print(f"\nLoop paused for manual review:\n{e}")
