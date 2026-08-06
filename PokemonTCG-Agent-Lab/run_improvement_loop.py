"""Orchestrate one iteration of: run baseline+candidate -> analyze -> gate -> promote.

    current best (agents/baseline)
            |
    fixed opponents, fixed conditions (harness/run_arms.py)
            |
    classify losses from the replays (replay_analyzer/classify_losses.py)
            |
    [you / an assistant propose a patch here -- see propose_patch() below]
            |
    candidate main.py (agents/candidate)
            |
    baseline vs candidate, same conditions
            |
    per-matchup / per-seat / mirror-specific checks
            |
    harness/acceptance_gate.py
            |
    promote only if it passes

This script runs every mechanical step end to end EXCEPT the "propose a
patch" step, which is deliberately left as an explicit extension point
rather than something this script does unattended. Auto-generating and
auto-merging agent code changes without a human (or a supervised assistant
session) in the loop is a real risk for a competition submission -- a
silently-regressed agent is much worse than a slow one. Call this with
--dry-run to see the full pipeline (using the CURRENT candidate as-is) before
wiring up automatic patch generation.

    python run_improvement_loop.py --cg-root /path/to/cg/parent --games 500
    python run_improvement_loop.py --cg-root ... --games 900 --matchup tusk_mill
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parent
HARNESS = LAB_ROOT / "harness"
AGENTS = LAB_ROOT / "agents"


def propose_patch() -> bool:
    """Extension point: generate a candidate patch onto agents/candidate/main.py
    before this loop's comparison step. Returns True if a patch was written.

    Intentionally not implemented here -- see prompts/strategist.md and
    prompts/coder.md for how a human or an assistant session should approach
    this step, and experiments/experiment.yaml for how to record the
    hypothesis behind whatever patch gets proposed. The rest of this script
    works unmodified whether this returns True (a new candidate was staged)
    or False (compare the current candidate as-is, e.g. to validate a patch
    someone already wrote by hand)."""
    return False


def run_step(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    print(f"[run_improvement_loop] $ {' '.join(cmd)}", flush=True)
    return subprocess.run(cmd, check=True, **kwargs)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--cg-root", required=True)
    parser.add_argument("--games", type=int, default=500)
    parser.add_argument("--matchup", help="restrict to one opponent, e.g. tusk_mill")
    parser.add_argument("--schedule-seed", type=int, default=20260721)
    parser.add_argument("--dry-run", action="store_true",
                        help="skip propose_patch(); compare the current candidate as-is")
    parser.add_argument("--promote", action="store_true",
                        help="on a pass, overwrite agents/baseline with agents/candidate")
    args = parser.parse_args()

    if not args.dry_run:
        patched = propose_patch()
        if not patched:
            print("[run_improvement_loop] propose_patch() made no change "
                  "(not implemented -- see the module docstring); "
                  "comparing the current candidate as committed.")

    run_step([sys.executable, "tools/validate_agent.py", "baseline", "--expect-flags-off"], cwd=LAB_ROOT)
    run_step([sys.executable, "tools/validate_agent.py", "candidate"], cwd=LAB_ROOT)

    out_root = LAB_ROOT / "out" / "improvement_loop"
    arms_cmd = [
        sys.executable, "run_arms.py", "--arms", "baseline,base",
        "--games", str(args.games), "--schedule-seed", str(args.schedule_seed),
        "--cg-root", args.cg_root, "--out", str((out_root).relative_to(LAB_ROOT)),
    ]
    if args.matchup:
        arms_cmd += ["--matchup", args.matchup]
    run_step(arms_cmd, cwd=HARNESS)

    report_path = out_root / "run_arms_report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    baseline_summary = report["arms"]["baseline"]["summary"]
    candidate_summary = report["arms"]["base"]["summary"]

    baseline_summary_path = out_root / "baseline" / "summary.json"
    candidate_summary_path = out_root / "base" / "summary.json"
    gate = subprocess.run(
        [sys.executable, "harness/acceptance_gate.py", str(baseline_summary_path), str(candidate_summary_path),
         "--out", str(out_root / "gate_result.json")],
        cwd=LAB_ROOT, text=True, capture_output=True,
    )
    print(gate.stdout)
    passed = gate.returncode == 0

    for loss_side, summary_dir in (("baseline", out_root / "baseline"), ("candidate", out_root / "base")):
        games_csv = summary_dir / "games.csv"
        if games_csv.exists():
            run_step([sys.executable, "replay_analyzer/classify_losses.py", str(games_csv),
                     "--replay-root", str(summary_dir),
                     "--out", str(out_root / f"{loss_side}_loss_tags.json")], cwd=LAB_ROOT)

    run_step([sys.executable, "matchup_report.py", str(report_path),
             "--out-md", str(LAB_ROOT / "reports" / "latest_report.md"),
             "--out-csv", str(LAB_ROOT / "reports" / "matchup_matrix.csv")],
             cwd=LAB_ROOT / "replay_analyzer")

    verdict = "PASS" if passed else "FAIL"
    print(f"\n[run_improvement_loop] gate verdict: {verdict}")
    print(f"[run_improvement_loop] see reports/latest_report.md for the full breakdown")

    with (LAB_ROOT / "experiments" / "history.csv").open("a", encoding="utf-8") as handle:
        handle.write(
            f"{date.today().isoformat()},improvement_loop,baseline_vs_candidate,"
            f"{args.matchup or 'all'},{args.games},{baseline_summary.get('win_rate')},"
            f"candidate,{candidate_summary.get('win_rate')},"
            f"{candidate_summary.get('win_rate', 0) - baseline_summary.get('win_rate', 0):.4f},"
            f",{passed},{passed and args.promote},run_improvement_loop.py\n"
        )

    if not passed:
        print("[run_improvement_loop] candidate did NOT clear the acceptance gate; not promoting.")
        sys.exit(1)

    if args.promote:
        shutil.copy2(AGENTS / "candidate" / "main.py", AGENTS / "baseline" / "main.py")
        shutil.copy2(AGENTS / "candidate" / "deck.csv", AGENTS / "baseline" / "deck.csv")
        print("[run_improvement_loop] promoted: agents/candidate copied over agents/baseline. "
              "Remember to flip any newly-validated ENABLE_* flags' defaults before committing, "
              "and open a PR rather than pushing straight to main.")
    else:
        print("[run_improvement_loop] gate passed. Re-run with --promote to copy candidate -> baseline.")


if __name__ == "__main__":
    main()
