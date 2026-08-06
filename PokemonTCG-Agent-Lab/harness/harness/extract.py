from __future__ import annotations

import collections
import hashlib
import json
import zipfile
from pathlib import Path
from typing import Any

from .utils import deck_hash, read_deck, write_csv, write_json


ARCHETYPE_SIGNALS: dict[str, set[int]] = {
    "archaludon": {169, 190, 666},
    "alakazam": {741, 742, 743},
    "lucario": {677, 678},
    "starmie": {1030, 1031},
    "tusk_mill": {58, 344, 345, 532, 756},
    "hop": {288, 289, 299, 304, 307, 308, 309, 310, 878, 879},
}


def classify_deck(deck: list[int]) -> str:
    ids = set(deck)
    scores = {name: len(signals & ids) for name, signals in ARCHETYPE_SIGNALS.items()}
    label = max(scores, key=scores.get)
    return label if scores[label] > 0 else "other"


def _decks_from_replay(data: dict[str, Any]) -> list[tuple[int, list[int]]]:
    found: dict[int, list[int]] = {}
    for step in data.get("steps", [])[:10]:
        if not isinstance(step, list):
            continue
        for player, entry in enumerate(step[:2]):
            if not isinstance(entry, dict):
                continue
            action = entry.get("action")
            if isinstance(action, list) and len(action) == 60 and all(isinstance(x, int) for x in action):
                found.setdefault(player, list(action))
    return sorted(found.items())


def extract_decks(replay_path: str, output_dir: str, own_deck_path: str | None = None) -> dict[str, Any]:
    source = Path(replay_path)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    own_hash = deck_hash(read_deck(own_deck_path)) if own_deck_path else None
    counts: collections.Counter[tuple[str, str, tuple[int, ...]]] = collections.Counter()

    def process(name: str, payload: bytes) -> None:
        data = json.loads(payload)
        for _, deck in _decks_from_replay(data):
            sorted_deck = tuple(sorted(deck))
            h = deck_hash(sorted_deck)
            label = classify_deck(list(sorted_deck))
            counts[(label, h, sorted_deck)] += 1

    if source.suffix.lower() == ".zip":
        with zipfile.ZipFile(source) as zf:
            for name in zf.namelist():
                if name.lower().endswith(".json"):
                    process(name, zf.read(name))
    else:
        process(source.name, source.read_bytes())

    rows: list[dict[str, Any]] = []
    config_entries: list[dict[str, Any]] = []
    for (label, h, deck), count in counts.most_common():
        deck_dir = out / label
        deck_dir.mkdir(parents=True, exist_ok=True)
        path = deck_dir / f"{label}-{h}.csv"
        path.write_text("\n".join(map(str, deck)) + "\n", encoding="utf-8")
        is_own = own_hash == h
        rows.append({
            "label": label,
            "deck_hash": h,
            "observations": count,
            "is_exact_own_deck": int(is_own),
            "path": str(path),
        })
        if not is_own:
            config_entries.append({
                "label": label,
                "deck": str(path),
                "bot": "tusk_mill" if label == "tusk_mill" else "greedy",
                "weight": count,
                "is_mill": label == "tusk_mill",
            })
    write_csv(out / "deck_index.csv", rows)
    write_json(out / "opponents_raw.json", {"opponents": config_entries})
    return {"rows": rows, "opponents": config_entries}
