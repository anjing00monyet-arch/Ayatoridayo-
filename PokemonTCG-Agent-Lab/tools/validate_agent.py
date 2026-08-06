"""Static checks on an agents/<name>/ directory, with no cg engine required.

Catches the class of mistake that would otherwise only surface after a full
harness run: syntax errors, a missing agent()/read_deck_csv(), an illegal
deck.csv, or a flag left on/off by accident before packaging a submission.

    python validate_agent.py candidate
    python validate_agent.py candidate --expect-flags-off   # CI: fail if any ENABLE_* is True
"""
from __future__ import annotations

import argparse
import ast
import re
import sys
from collections import Counter
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parent.parent
BASIC_ENERGY_IDS = {8}      # Basic Metal Energy; extend if the deck runs other basic energy
KNOWN_ACE_SPECS = {1159}    # Hero's Cape. This list is only as complete as what this repo has
                            # seen -- it is NOT derived from the real card database (no cg here).


def check_syntax(main_py: Path) -> list[str]:
    problems = []
    try:
        source = main_py.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(main_py))
    except SyntaxError as exc:
        return [f"SyntaxError: {exc}"]

    defined = {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
    for required in ("agent", "read_deck_csv"):
        if required not in defined:
            problems.append(f"no top-level def {required}(...) found")
    return problems


def check_flags(main_py: Path, expect_off: bool) -> tuple[list[str], dict[str, bool]]:
    source = main_py.read_text(encoding="utf-8")
    flags = {m.group(1): m.group(2) == "True"
            for m in re.finditer(r"^(ENABLE_\w+)\s*=\s*(True|False)\b", source, re.M)}
    problems = []
    if expect_off:
        on = [name for name, value in flags.items() if value]
        if on:
            problems.append(f"expected all ENABLE_* flags off, but these are True: {on}")
    return problems, flags


def check_deck(deck_csv: Path) -> list[str]:
    problems = []
    try:
        ids = [int(line) for line in deck_csv.read_text(encoding="utf-8").split() if line.strip()]
    except ValueError as exc:
        return [f"deck.csv contains a non-integer line: {exc}"]

    if len(ids) != 60:
        problems.append(f"deck must be exactly 60 cards, got {len(ids)}")
    counts = Counter(ids)
    for card_id, count in counts.items():
        if card_id not in BASIC_ENERGY_IDS and count > 4:
            problems.append(f"card {card_id} appears {count} times (limit 4)")
        if card_id in KNOWN_ACE_SPECS and count > 1:
            problems.append(f"card {card_id} is a known ACE SPEC but appears {count} times")
    return problems


def validate(agent_dir: Path, expect_flags_off: bool) -> list[str]:
    problems = []
    main_py = agent_dir / "main.py"
    deck_csv = agent_dir / "deck.csv"

    if not main_py.exists():
        return [f"{main_py} does not exist"]
    problems += [f"main.py: {p}" for p in check_syntax(main_py)]
    flag_problems, flags = check_flags(main_py, expect_flags_off)
    problems += [f"main.py: {p}" for p in flag_problems]

    if not deck_csv.exists():
        problems.append(f"{deck_csv} does not exist")
    else:
        problems += [f"deck.csv: {p}" for p in check_deck(deck_csv)]

    if flags:
        print("flags found:")
        for name, value in sorted(flags.items()):
            print(f"  {name} = {value}")
    return problems


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("agent", help="name of the agents/<agent>/ directory, e.g. candidate")
    parser.add_argument("--expect-flags-off", action="store_true",
                        help="fail if any ENABLE_* flag is True (use before packaging a plain submission)")
    args = parser.parse_args()

    agent_dir = LAB_ROOT / "agents" / args.agent
    if not agent_dir.is_dir():
        sys.exit(f"no such agent directory: {agent_dir}")

    problems = validate(agent_dir, args.expect_flags_off)
    if problems:
        print(f"\n{len(problems)} problem(s) in {agent_dir}:")
        for p in problems:
            print(f"  - {p}")
        sys.exit(1)
    print(f"\n{agent_dir}: OK")


if __name__ == "__main__":
    main()
