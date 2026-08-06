from __future__ import annotations

import argparse
import json

from harness.extract import extract_decks


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract unique 60-card decks from Kaggle-compatible replay JSON/ZIP")
    parser.add_argument("replays", help="Replay JSON or ZIP")
    parser.add_argument("output_dir", help="Output directory")
    parser.add_argument("--own-deck", default=None, help="Exact own deck.csv to flag/exclude from opponent config")
    args = parser.parse_args()
    result = extract_decks(args.replays, args.output_dir, args.own_deck)
    print(json.dumps({"deck_count": len(result["rows"]), "opponent_entries": len(result["opponents"])}, indent=2))


if __name__ == "__main__":
    main()
