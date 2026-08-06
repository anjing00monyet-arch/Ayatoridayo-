"""Build submission.zip from an agents/<name>/ directory (main.py + deck.csv).

    python package_submission.py candidate
    python package_submission.py baseline --out /tmp/baseline_submission.zip

Why zip instead of running main.py directly: main.py's top-level
`from cg.api import (...)` only resolves inside the actual evaluation
harness (competition input on sys.path). Outside that harness -- e.g. a
plain notebook commit run, or this repo's CI -- the import fails with
ModuleNotFoundError: No module named 'cg'. Zipping the source instead of
executing it sidesteps that entirely: the zip's contents are never imported
by whatever process builds the submission, only unpacked by the harness at
episode start.
"""
from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parent.parent
FILES = ["main.py", "deck.csv"]


def package(agent_dir: Path, out_path: Path) -> Path:
    present = [f for f in FILES if (agent_dir / f).exists()]
    missing = [f for f in FILES if f not in present]
    if "main.py" not in present:
        sys.exit(f"{agent_dir}/main.py not found -- nothing to package")
    if missing:
        print(f"[package_submission] warning: missing {missing} in {agent_dir}, excluding from zip",
              file=sys.stderr)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in present:
            zf.write(agent_dir / name, arcname=name)
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("agent", help="name of the agents/<agent>/ directory, e.g. candidate")
    parser.add_argument("--out", type=Path, help="output zip path (default: <agent>_submission.zip)")
    args = parser.parse_args()

    agent_dir = LAB_ROOT / "agents" / args.agent
    if not agent_dir.is_dir():
        sys.exit(f"no such agent directory: {agent_dir}")
    out_path = args.out or (LAB_ROOT / f"{args.agent}_submission.zip")
    result = package(agent_dir, out_path)
    print(f"[package_submission] wrote {result}")


if __name__ == "__main__":
    main()
