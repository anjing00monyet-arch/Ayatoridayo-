from __future__ import annotations

import argparse
import json
from pathlib import Path

from harness.validation import validate_replay_payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate a harness replay and C0 instrumentation")
    parser.add_argument("replay")
    args = parser.parse_args()
    path = Path(args.replay)
    data = json.loads(path.read_text(encoding="utf-8"))
    result = validate_replay_payload(data)
    if not result["ok"]:
        for error in result["errors"]:
            print("ERROR:", error)
        raise SystemExit(1)
    print(f"OK: {path}")
    print(f"steps={result.get('step_count')}")
    info = data.get("info") or {}
    print("c0_1_mill_misdetection_occurred=", info.get("c0_1_mill_misdetection_occurred"))
    print("c0_2_duraludon_promotion_events=", len(info.get("c0_2_duraludon_promotion_events") or []))
    print("c0_3_lethal_suppression_events=", len(info.get("c0_3_lethal_suppression_events") or []))


if __name__ == "__main__":
    main()
