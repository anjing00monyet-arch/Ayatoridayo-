"""Multi-arm isolation runner: one flag (or deck change) per arm vs a shared baseline.

This is the repo-native version of the flag-isolation runner used during the
tusk_mill B1/A2/A3 investigation. That version embedded everything as
base64 gzip so it could be pasted into a single Kaggle notebook cell; here
the agent sources already live on disk (agents/baseline, agents/candidate),
so no embedding is needed.

Each arm runs as a real subprocess of run_batch.py -- never a
multiprocessing.Process with an in-notebook target -- because that is what
actually broke (see git history: "Can't get attribute '_arm_worker' on
<module '__main__' ...>" when the multiprocessing-based version was pasted
into a notebook cell). run_batch.py and harness/runner.py contain no
multiprocessing of their own, so shelling out to `python run_batch.py
config.json` can never hit that class of bug, in a notebook or not.

    python run_arms.py --preset isolate --games 500 --cg-root /path/to/cg/parent
    python run_arms.py --list-arms
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from harness.compare import mechanism_gates
from harness.utils import difference_interval, wilson_interval

LAB_ROOT = Path(__file__).resolve().parent.parent
CANDIDATE_MAIN = LAB_ROOT / "agents" / "candidate" / "main.py"
BASELINE_MAIN = LAB_ROOT / "agents" / "baseline" / "main.py"
DECK_CSV = (LAB_ROOT / "agents" / "candidate" / "deck.csv").read_text(encoding="utf-8")
OPPONENTS_DIR = LAB_ROOT / "agents" / "opponents_decks"

# See agents/candidate/main.py's own "v8 mechanism-regression fixes" comment
# block for what each flag does and why it exists.
KNOWN_FLAGS = (
    "ENABLE_B1_TWO_STEP_LETHAL", "ENABLE_A2_PRIZE_RACE", "ENABLE_A3_DRAW_STOP",
    "ENABLE_D1_FORCED_PROMOTION_GUARD", "ENABLE_B1_SAFE_RETREAT_GUARD",
    "ENABLE_A3_BENCH_AWARE", "ENABLE_C1_SWITCH", "ENABLE_C3_MILL_JUDGE",
)


@dataclass
class Arm:
    name: str
    description: str
    flags: tuple[str, ...] = ()
    use_baseline_source: bool = False


ARMS: dict[str, Arm] = {
    "baseline": Arm("baseline", "agents/baseline/main.py, untouched", use_baseline_source=True),
    "base": Arm("base", "agents/candidate/main.py, every new flag off"),
    "b1": Arm("b1", "B1 only: 2-step lethal retreat", flags=("ENABLE_B1_TWO_STEP_LETHAL",)),
    "a2": Arm("a2", "A2 only: prize-race survival", flags=("ENABLE_A2_PRIZE_RACE",)),
    "a3": Arm("a3", "A3 only: optional-draw stop", flags=("ENABLE_A3_DRAW_STOP",)),
    "a3_bench": Arm("a3_bench", "A3 + bench-aware exemption (Ultra/Dusk Ball stay live)",
                    flags=("ENABLE_A3_DRAW_STOP", "ENABLE_A3_BENCH_AWARE")),
    "d1": Arm("d1", "D1 only: forced-promotion guard (self-snipe fix)",
              flags=("ENABLE_D1_FORCED_PROMOTION_GUARD",)),
    "a3_d1": Arm("a3_d1", "A3 + D1", flags=("ENABLE_A3_DRAW_STOP", "ENABLE_D1_FORCED_PROMOTION_GUARD")),
    "b1_d1": Arm("b1_d1", "B1 + D1", flags=("ENABLE_B1_TWO_STEP_LETHAL", "ENABLE_D1_FORCED_PROMOTION_GUARD")),
    "all3": Arm("all3", "B1+A2+A3 (the originally-rejected v7 configuration)",
                flags=("ENABLE_B1_TWO_STEP_LETHAL", "ENABLE_A2_PRIZE_RACE", "ENABLE_A3_DRAW_STOP")),
    "full_fix": Arm("full_fix", "All patches plus all regression guards",
                    flags=("ENABLE_B1_TWO_STEP_LETHAL", "ENABLE_A2_PRIZE_RACE", "ENABLE_A3_DRAW_STOP",
                           "ENABLE_D1_FORCED_PROMOTION_GUARD", "ENABLE_B1_SAFE_RETREAT_GUARD",
                           "ENABLE_A3_BENCH_AWARE")),
}

PRESETS: dict[str, tuple[str, ...]] = {
    "isolate": ("base", "b1", "a2", "a3"),
    "a3fix": ("base", "a3", "a3_bench", "a3_d1"),
    "snipe": ("base", "b1", "d1", "b1_d1"),
    "fix": ("base", "all3", "d1", "full_fix"),
    "control": ("baseline", "base"),
}


def apply_flags(source: str, flags: tuple[str, ...]) -> str:
    out = source
    for flag in flags:
        out, n = re.subn(rf"^({re.escape(flag)}\s*=\s*)False\b", r"\1True", out, count=1, flags=re.M)
        if n != 1:
            raise RuntimeError(f"Could not flip {flag} in agents/candidate/main.py (matched {n} lines)")
    return out


def materialize_arm(arm: Arm, out_root: Path) -> tuple[Path, Path]:
    source = BASELINE_MAIN.read_text(encoding="utf-8") if arm.use_baseline_source \
        else apply_flags(CANDIDATE_MAIN.read_text(encoding="utf-8"), arm.flags)
    target_dir = out_root / "arms" / arm.name
    target_dir.mkdir(parents=True, exist_ok=True)
    main_path = target_dir / "main.py"
    deck_path = target_dir / "deck.csv"
    main_path.write_text(source, encoding="utf-8")
    deck_path.write_text(DECK_CSV, encoding="utf-8")
    return main_path, deck_path


def default_opponents(matchup: str | None) -> list[dict]:
    everyone = [
        {"label": "alakazam", "deck": str(OPPONENTS_DIR / "alakazam.csv"), "bot": "greedy", "weight": 35, "is_mill": False},
        {"label": "lucario", "deck": str(OPPONENTS_DIR / "lucario.csv"), "bot": "greedy", "weight": 25, "is_mill": False},
        {"label": "archaludon_mirror", "deck": str(OPPONENTS_DIR / "archaludon_mirror.csv"), "bot": "greedy", "weight": 25, "is_mill": False},
        {"label": "tusk_mill", "deck": str(OPPONENTS_DIR / "tusk_mill.csv"), "bot": "tusk_mill", "weight": 15, "is_mill": True},
    ]
    if not matchup:
        return everyone
    picked = [o for o in everyone if o["label"] == matchup]
    if not picked:
        raise SystemExit(f"--matchup must be one of {[o['label'] for o in everyone]}")
    return [dict(picked[0], weight=100)]


def run_arm(harness_root: Path, config_path: Path, output_dir: Path) -> dict:
    command = [sys.executable, str(harness_root / "run_batch.py"), str(config_path)]
    completed = subprocess.run(command, cwd=harness_root, text=True)
    if completed.returncode != 0:
        raise RuntimeError(f"Arm subprocess failed with exit code {completed.returncode}: {' '.join(command)}")
    summary_path = output_dir / "summary.json"
    if not summary_path.exists():
        raise RuntimeError(f"Arm subprocess exited 0 but wrote no summary.json in {output_dir}")
    return json.loads(summary_path.read_text(encoding="utf-8"))


def snipe_rate(summary: dict) -> float:
    events = int(summary.get("c0_2_promotion_events", 0) or 0)
    return (int(summary.get("c0_2_true_self_snipes", 0) or 0) / events) if events else 0.0


def compare_arm(baseline: dict, candidate: dict) -> dict:
    diff, low, high = difference_interval(
        int(candidate["wins"]), int(candidate["games_completed"]),
        int(baseline["wins"]), int(baseline["games_completed"]),
    )
    gates = mechanism_gates(baseline, candidate)
    return {
        "win_rate_minus_baseline": diff,
        "difference_normal95": [low, high],
        "significant_win_rate_change": not (low <= 0.0 <= high),
        "gates_passed": gates["passed"],
        "mechanism_gates": gates,
    }


def print_table(summaries: dict[str, dict], comparisons: dict[str, dict], baseline_name: str) -> None:
    print("\n" + "=" * 100)
    print(f"{'arm':<12}{'games':>7}{'win%':>8}{'Δwin':>8}{'sig':>6}{'snipe%':>9}{'gates':>8}  flags")
    print("-" * 100)
    for name, summary in summaries.items():
        comparison = comparisons.get(name)
        delta = f"{comparison['win_rate_minus_baseline'] * 100:+.2f}" if comparison else "  base"
        sig = ("YES" if comparison["significant_win_rate_change"] else "no") if comparison else "-"
        gates = ("PASS" if comparison["gates_passed"] else "FAIL") if comparison else "-"
        print(f"{name:<12}{summary.get('games_completed', 0):>7}"
              f"{float(summary.get('win_rate', 0)) * 100:>7.1f}%{delta:>8}{sig:>6}"
              f"{snipe_rate(summary) * 100:>8.2f}%{gates:>8}  {'+'.join(ARMS[name].flags) or '-'}")
    print("=" * 100)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--preset", default="isolate", choices=sorted(PRESETS))
    parser.add_argument("--arms", help="comma-separated arm names, overrides --preset")
    parser.add_argument("--games", type=int, default=500)
    parser.add_argument("--matchup", help="restrict every game to one opponent, e.g. tusk_mill")
    parser.add_argument("--schedule-seed", type=int, default=20260721)
    parser.add_argument("--cg-root", help="parent directory containing cg/game.py (required unless --list-arms)")
    parser.add_argument("--no-replays", action="store_true")
    parser.add_argument("--out", default="out/run_arms")
    parser.add_argument("--list-arms", action="store_true")
    args = parser.parse_args()

    if args.list_arms:
        for name, arm in ARMS.items():
            print(f"{name:<12} {arm.description}")
        print("\npresets:")
        for name, members in PRESETS.items():
            print(f"  {name:<9} {', '.join(members)}")
        return
    if not args.cg_root:
        parser.error("--cg-root is required unless --list-arms is given")

    selected = [a.strip() for a in args.arms.split(",")] if args.arms else list(PRESETS[args.preset])
    unknown = [a for a in selected if a not in ARMS]
    if unknown:
        raise SystemExit(f"unknown arm(s): {unknown}. Known: {sorted(ARMS)}")
    baseline_name = selected[0]

    harness_root = Path(__file__).resolve().parent
    output_root = LAB_ROOT / args.out
    output_root.mkdir(parents=True, exist_ok=True)
    opponents = default_opponents(args.matchup)

    print(f"arms: {', '.join(selected)} (baseline={baseline_name})")
    print(f"games/arm: {args.games}  total: {args.games * len(selected)}  cg_root: {args.cg_root}")

    summaries: dict[str, dict] = {}
    for index, name in enumerate(selected, start=1):
        arm = ARMS[name]
        main_path, deck_path = materialize_arm(arm, output_root)
        arm_out = output_root / name
        config = {
            "game_module": "cg.game",
            "cg_root": args.cg_root,
            "variant": {"name": name, "main": str(main_path), "deck": str(deck_path),
                       "watch_globals": ["_opp_mill_seen"]},
            "opponents": opponents,
            "games": args.games,
            "minimum_validation_games": args.games,
            "schedule_seed": args.schedule_seed,
            "max_decisions": 2000,
            "save_replays": not args.no_replays,
            "balance_first_second": True,
            "balance_max_attempt_multiplier": 10.0,
            "error_policy": "fallback",
            "resume": True,
            "output_dir": str(arm_out),
        }
        config_path = harness_root / "configs" / f"_run_arms_{name}_{args.games}.json"
        config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n--- [{index}/{len(selected)}] arm {name}: {arm.description}")
        summaries[name] = run_arm(harness_root, config_path, arm_out)

    baseline_summary = summaries[baseline_name]
    comparisons = {name: compare_arm(baseline_summary, summary)
                   for name, summary in summaries.items() if name != baseline_name}
    print_table(summaries, comparisons, baseline_name)

    report = {"baseline": baseline_name, "games_per_arm": args.games, "matchup": args.matchup or "all",
              "arms": {name: {"summary": s, "vs_baseline": comparisons.get(name)} for name, s in summaries.items()}}
    (output_root / "run_arms_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nReport: {output_root / 'run_arms_report.json'}")


if __name__ == "__main__":
    main()
