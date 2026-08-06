"""Run a single debuggable match instead of a full batch.

Reuses run_batch.py's config schema but overrides `games` to 1 and always
saves the replay + trial JSON, so you can point validate_replay.py or
replay_analyzer/ at exactly one game while iterating on an agent.

    python run_match.py configs/batch_example.json --opponent tusk_mill --seat 0
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from harness.agent_loader import LoadedAgent
from harness.engine import EngineAdapter
from harness.runner import run_game
from harness.utils import read_json


def _resolve(base: Path, value: str | None) -> str | None:
    if value is None:
        return None
    p = Path(value)
    return str(p if p.is_absolute() else (base / p).resolve())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("config", help="same schema as run_batch.py's config")
    parser.add_argument("--opponent", help="opponent label to play; default: first in config")
    parser.add_argument("--seat", type=int, choices=(0, 1), default=0, help="which seat the agent sits in")
    parser.add_argument("--seed", type=int, default=0, help="opponent bot RNG seed")
    parser.add_argument("--max-decisions", type=int, default=2000)
    args = parser.parse_args()

    config_file = Path(args.config).resolve()
    base = config_file.parent
    cfg = read_json(config_file)

    cg_root = _resolve(base, cfg.get("cg_root"))
    if cg_root and cg_root not in sys.path:
        sys.path.insert(0, cg_root)

    variant = cfg["variant"]
    agent = LoadedAgent(
        _resolve(base, variant["main"]),
        _resolve(base, variant["deck"]),
        cg_root=cg_root,
        watch_globals=variant.get("watch_globals"),
    )

    opponents = cfg["opponents"]
    if args.opponent:
        matches = [o for o in opponents if o["label"] == args.opponent]
        if not matches:
            raise SystemExit(f"no opponent labeled {args.opponent!r}; have {[o['label'] for o in opponents]}")
        opponent_cfg = dict(matches[0])
    else:
        opponent_cfg = dict(opponents[0])
    opponent_cfg["deck"] = _resolve(base, opponent_cfg["deck"])

    output_dir = Path(cfg.get("output_dir", "out_single_match"))
    if not output_dir.is_absolute():
        output_dir = (base / output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    engine = EngineAdapter(cfg.get("game_module", "cg.game"))
    row = run_game(
        engine=engine,
        variant_name=str(variant.get("name", "variant")),
        agent=agent,
        opponent_cfg=opponent_cfg,
        target_seat=args.seat,
        game_index=0,
        output_dir=output_dir,
        save_replays=True,
        max_decisions=args.max_decisions,
        bot_seed=args.seed,
        error_policy="fail_fast",
    )
    print(json.dumps(row, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
