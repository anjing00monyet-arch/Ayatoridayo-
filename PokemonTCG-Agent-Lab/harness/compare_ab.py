from __future__ import annotations

import argparse
import json

from harness.compare import compare_config


def main() -> None:
    parser = argparse.ArgumentParser(description="Run A/B in isolated processes and compare independent results")
    parser.add_argument("config", help="Path to A/B config JSON")
    args = parser.parse_args()
    result = compare_config(args.config)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
