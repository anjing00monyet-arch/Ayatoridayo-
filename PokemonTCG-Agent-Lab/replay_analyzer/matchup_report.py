"""Turn a run_arms.py report (or a bare summary.json/comparison.json pair) into
the two files reports/ actually wants: a markdown summary and a per-matchup CSV.

    python matchup_report.py out/run_arms/run_arms_report.json \
        --out-md ../reports/latest_report.md --out-csv ../reports/matchup_matrix.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from board_metrics import wilson_interval  # noqa: E402


def _fmt_pct(x: float | None) -> str:
    return "-" if x is None else f"{x * 100:.1f}%"


def build_markdown(report: dict) -> str:
    baseline = report["baseline"]
    lines = [
        f"# Run report: {report.get('matchup', 'all')} matchup, "
        f"{report['games_per_arm']} games/arm, baseline = `{baseline}`",
        "",
        "| arm | games | win% | Δwin vs baseline | 95% CI | gates | snipe% |",
        "|---|---:|---:|---:|---:|---|---:|",
    ]
    for name, entry in report["arms"].items():
        s = entry["summary"]
        vs = entry.get("vs_baseline")
        wr = float(s.get("win_rate", 0.0))
        lo, hi = wilson_interval(int(s.get("wins", 0)), int(s.get("games_completed", 0)))
        delta = f"{vs['win_rate_minus_baseline'] * 100:+.2f}pp" if vs else "base"
        gates = "-" if not vs else ("PASS" if vs["gates_passed"] else "**FAIL**")
        events = int(s.get("c0_2_promotion_events", 0) or 0)
        snipes = int(s.get("c0_2_true_self_snipes", 0) or 0)
        snipe_pct = _fmt_pct(snipes / events) if events else "-"
        lines.append(
            f"| {name} | {s.get('games_completed')} | {_fmt_pct(wr)} | {delta} | "
            f"[{lo*100:.1f}%, {hi*100:.1f}%] | {gates} | {snipe_pct} |"
        )

    lines += ["", "## Per-opponent win rate", "", "| arm | " +
             " | ".join(sorted({label for e in report["arms"].values()
                                for label in (e["summary"].get("by_opponent") or {})})) + " |"]
    labels = sorted({label for e in report["arms"].values() for label in (e["summary"].get("by_opponent") or {})})
    lines.append("|---|" + "---:|" * len(labels))
    for name, entry in report["arms"].items():
        by_opp = entry["summary"].get("by_opponent") or {}
        row = [f"{by_opp[label]['win_rate']*100:.1f}%" if label in by_opp else "-" for label in labels]
        lines.append(f"| {name} | " + " | ".join(row) + " |")

    lines += ["", "## Mechanism gates (candidate arms only)", ""]
    for name, entry in report["arms"].items():
        vs = entry.get("vs_baseline")
        if not vs:
            continue
        gates = vs["mechanism_gates"]
        status = "PASS" if gates["passed"] else "FAIL"
        lines.append(f"- **{name}**: {status}")
        for gate_name, ok in gates["hard_gates"].items():
            if not ok:
                lines.append(f"  - hard gate failed: `{gate_name}`")
        for soft in gates["soft_gates"]:
            if not soft["passed"]:
                lines.append(
                    f"  - soft gate failed: `{soft['gate']}` "
                    f"({soft['candidate']['events']}/{soft['candidate']['total']} = "
                    f"{soft['candidate']['rate']*100:.2f}%, ceiling "
                    f"{soft['absolute_rate_ceiling']*100:.1f}%, "
                    f"p={soft['fisher_one_sided_p']:.3f})")
    return "\n".join(lines) + "\n"


def build_csv_rows(report: dict) -> list[dict]:
    labels = sorted({label for e in report["arms"].values() for label in (e["summary"].get("by_opponent") or {})})
    rows = []
    for name, entry in report["arms"].items():
        by_opp = entry["summary"].get("by_opponent") or {}
        row = {"arm": name, "games": entry["summary"].get("games_completed"),
              "win_rate": entry["summary"].get("win_rate")}
        for label in labels:
            row[f"wr_{label}"] = by_opp.get(label, {}).get("win_rate")
        rows.append(row)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("report", type=Path, help="run_arms_report.json")
    parser.add_argument("--out-md", type=Path, default=Path("../reports/latest_report.md"))
    parser.add_argument("--out-csv", type=Path, default=Path("../reports/matchup_matrix.csv"))
    args = parser.parse_args()

    report = json.loads(args.report.read_text(encoding="utf-8"))
    args.out_md.parent.mkdir(parents=True, exist_ok=True)
    args.out_md.write_text(build_markdown(report), encoding="utf-8")

    rows = build_csv_rows(report)
    with args.out_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print(f"wrote {args.out_md}")
    print(f"wrote {args.out_csv}")


if __name__ == "__main__":
    main()
