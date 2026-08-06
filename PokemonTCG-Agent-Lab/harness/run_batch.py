from __future__ import annotations

import argparse
import json

from harness.runner import run_batch_config


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one Pokémon TCG agent variant against a fixed opponent mixture")
    parser.add_argument("config", help="Path to batch config JSON")
    args = parser.parse_args()
    result = run_batch_config(args.config)
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
