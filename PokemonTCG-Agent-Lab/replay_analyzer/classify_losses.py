"""Tag lost games with loss-reason categories, from games.csv and (optionally) replays.

Honesty note up front: only some of the requested categories have a directly
grounded signal in games.csv. Those are computed from scalar fields and are
reliable. The rest require inspecting the actual board state at the moment of
loss, which needs the replay JSON (only available if the run used
save_replays=true) -- those are computed too, but are heuristics over raw
observation dicts, not first-class harness metrics, so treat them as leads to
go read a handful of replays, not as ground truth to report a rate for
without spot-checking.

A game can carry more than one tag (e.g. missed_attack AND thin_board), and a
loss with no matching heuristic is tagged "unclassified" rather than forced
into the nearest bucket -- forcing single-label assignment on weak signal is
exactly the mistake analyze_snipes.py / board_metrics.py was written to catch
(see its module docstring).

Grounded in games.csv alone (always available):
    timeout            terminal_reason == "max_decisions"
    missed_attack      c0_3_lethal_suppression_count > 0
    bad_switch         c0_2_promotion_violation_count > 0 (includes true_self_snipe)
    mirror_misplay     opponent == archaludon_mirror and lost
    setup_failure      attack_by_own_turn3 == 0 (proxy: no attacker online by turn 3)
    deckout_signal     mill_seen and not expected_mill, OR opponent is_mill and long game
                        (games.csv doesn't record deck-out directly; see below)

Needs the replay JSON (best-effort, replay_path must exist and be readable):
    deckout            loser's final observation has deckCount == 0
    thin_board         loser's own bench was empty at the moment their Active was KO'd
    energy_shortage    loser's Active/bench had 0 energy attached when KO'd, 3+ turns in
    resource_overcommit hand held playable resources (energy/supporter) unused at loss
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

GROUNDED_ONLY = ("timeout", "missed_attack", "bad_switch", "mirror_misplay", "setup_failure")
REPLAY_ONLY = ("deckout", "thin_board", "energy_shortage", "resource_overcommit")


def _int(row: dict, key: str) -> int:
    raw = (row.get(key) or "").strip()
    try:
        return int(float(raw)) if raw not in ("", "None") else 0
    except ValueError:
        return 0


def classify_from_row(row: dict[str, Any]) -> set[str]:
    """The grounded, replay-free tags. Only meaningful for rows where lost == 1."""
    tags: set[str] = set()
    if row.get("terminal_reason") == "max_decisions":
        tags.add("timeout")
    if _int(row, "c0_3_lethal_suppression_count") > 0:
        tags.add("missed_attack")
    if _int(row, "c0_2_promotion_violation_count") > 0:
        tags.add("bad_switch")
    if row.get("opponent") == "archaludon_mirror":
        tags.add("mirror_misplay")
    if _int(row, "attack_by_own_turn3") == 0:
        tags.add("setup_failure")
    return tags


def _cards(area: Any) -> list[dict]:
    return [c for c in (area or []) if isinstance(c, dict)]


def classify_from_replay(replay_path: Path, loser_seat: int) -> set[str]:
    """Best-effort tags that need the actual observation. Never raises on a
    malformed/missing replay -- returns an empty set instead, since this is
    supplementary signal, not the primary classification."""
    tags: set[str] = set()
    try:
        replay = json.loads(replay_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return tags

    steps = replay.get("steps") or []
    if not steps:
        return tags

    final_obs = steps[-1][loser_seat].get("observation") or {}
    current = final_obs.get("current") or {}
    players = current.get("players") or []
    if loser_seat < len(players):
        loser_state = players[loser_seat] or {}
        if int(loser_state.get("deckCount", 1) or 1) <= 0:
            tags.add("deckout")

    for step in steps[1:]:
        entry = step[loser_seat] if loser_seat < len(step) else None
        if not entry:
            continue
        obs = entry.get("observation") or {}
        cur = obs.get("current") or {}
        turn = int(cur.get("turn", 0) or 0)
        own_players = cur.get("players") or []
        if loser_seat >= len(own_players):
            continue
        me = own_players[loser_seat] or {}
        active = _cards(me.get("active"))
        bench = _cards(me.get("bench"))
        if not active and turn >= 3:
            if not bench:
                tags.add("thin_board")
            else:
                energized = [c for c in bench if (c.get("energyCards") or c.get("energies"))]
                if not energized:
                    tags.add("energy_shortage")
    return tags


def classify_all(games_csv: Path, replay_root: Path | None = None) -> list[dict]:
    with games_csv.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    results = []
    for row in rows:
        if row.get("completed") != "1" or _int(row, "lost") != 1:
            continue
        tags = classify_from_row(row)
        if replay_root is not None:
            replay_rel = row.get("replay_relative_path") or ""
            if replay_rel:
                # This analyzer only classifies our own losses (filtered above),
                # so the loser is always our own target_seat.
                loser_seat = _int(row, "target_seat")
                tags |= classify_from_replay(replay_root / replay_rel, loser_seat)
        if not tags:
            tags = {"unclassified"}
        results.append({
            "game_index": row.get("game_index"), "opponent": row.get("opponent"),
            "decisions": row.get("decisions"), "tags": sorted(tags),
        })
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("games_csv", type=Path)
    parser.add_argument("--replay-root", type=Path,
                        help="output_dir the run used (parent of replays/); enables the replay-only tags")
    parser.add_argument("--out", type=Path, help="write full per-game tags JSON here")
    args = parser.parse_args()

    losses = classify_all(args.games_csv, args.replay_root)
    counts = Counter(tag for loss in losses for tag in loss["tags"])
    print(f"{len(losses)} losses classified"
          + ("" if args.replay_root else " (grounded tags only; pass --replay-root for deckout/thin_board/energy_shortage)"))
    for tag, count in counts.most_common():
        grounded = tag in GROUNDED_ONLY
        source = "games.csv" if grounded else ("replay" if tag in REPLAY_ONLY else "-")
        print(f"  {tag:<20}{count:>5}  ({source})")

    if args.out:
        args.out.write_text(json.dumps(losses, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nper-game tags written to {args.out}")


if __name__ == "__main__":
    main()
