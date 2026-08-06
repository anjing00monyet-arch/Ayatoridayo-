"""Freezes a policy's actual turn-by-turn decisions into a fixed action
list, then wraps replay of that list with a weed-repair layer so it
survives being replayed against a *different* random weed-spawn sequence
than the one recorded against (weeds spawn at
`weedSpawnChance`/tile/day -- see game/README.md -- so a different game
will not spawn them in the same places/times).

This mirrors the technique found by decoding opponents/submission_27:
a precomputed action-per-step script, patched at replay time so a
PLANT/BUILD_PASTURE landing on an unexpected WEED digs it first and
retries the original intent a few turns later, instead of silently
failing forever.
"""
from __future__ import annotations

import copy
import json
from typing import Any

from game.kaggriculture_env import decision_pairs, play_match

WEED_REPLAY_STEPS = 8  # how many turns later to retry an intent that got weed-blocked


def record_trajectory(agent, opponent: str, seed: int, episode_steps: int = 720) -> list[dict[str, Any]]:
    """Plays one match and returns the list of actions the agent actually
    took, indexed by step (0..episode_steps-2), via decision_pairs so each
    action is correctly paired with the observation that produced it.
    """
    replay = play_match(agent, opponent, seed=seed, configuration={"episodeSteps": episode_steps})
    return [action for _obs, action in decision_pairs(replay, player=0)]


def _copy_action(action: dict[str, Any] | None) -> dict[str, Any]:
    action = copy.deepcopy(action or {})
    return {
        "farmer": list(action.get("farmer") or ["PASS"]),
        "hands": [list(op or ["PASS"]) for op in (action.get("hands") or [])],
        "market": [list(order) for order in (action.get("market") or [])],
    }


def _align_hands(action: dict[str, Any], expected: int) -> dict[str, Any]:
    """Pads/truncates the recorded `hands` list to however many hands
    actually exist this turn during replay (can differ from the recorded
    game if a hire lands a turn earlier/later due to a money difference).
    """
    hands = list(action.get("hands") or [])
    if len(hands) < expected:
        hands = hands + [["PASS"] for _ in range(expected - len(hands))]
    action["hands"] = [list(op or ["PASS"]) for op in hands[:expected]]
    return action


def _tile_at(farm: dict[str, Any], pos) -> Any:
    try:
        x, y = int(pos[0]), int(pos[1])
        return farm["tiles"][y][x]
    except (IndexError, TypeError, ValueError):
        return "LOCKED"


def _needs_water(tile: Any) -> bool:
    """True if standing on a live crop that hasn't been watered today --
    missing water twice in a row kills the crop (turns it into a WEED),
    and a different game's random weed spawns elsewhere on the board can
    shift an actor's movement enough that the recorded script waters the
    wrong tile at the wrong time. Watering an already-watered tile is a
    guaranteed no-op in the real env, so this check is safe to run every
    turn regardless of what the recording intended here.
    """
    return isinstance(tile, dict) and tile.get("kind") == "PLANT" and not tile.get("watered_today", False)


def _needs_urgent_harvest(tile: Any, step: int) -> bool:
    """True if standing on a crop past its harvest deadline that still
    holds yield -- past `max_lifespan_step` the crop decays by 1 unit
    every 2 turns until it dies (becomes a WEED), so a script that
    arrives late (due to any earlier desync) needs to harvest immediately
    rather than follow whatever it originally had scheduled for this turn.
    """
    if not (isinstance(tile, dict) and tile.get("kind") == "PLANT"):
        return False
    mls = tile.get("max_lifespan_step", -1)
    return tile.get("yield_units", 0) > 0 and mls >= 0 and step >= mls


def make_frozen_agent(actions: list[dict[str, Any]]):
    """Returns an `agent(observation)` that replays `actions` by step
    index, digging out and retrying any PLANT/BUILD_PASTURE that lands on
    a weed the recording didn't have.
    """
    weed_state: dict[int, dict[str, Any]] = {0: {}, 1: {}}

    def repair(observation, action, step) -> dict[str, Any]:
        seat = 1 if int(observation.get("player", 0) or 0) == 1 else 0
        game = weed_state[seat]
        if step == 0 or step < game.get("last_step", -1):
            game = {"last_step": step, "active": {}}
            weed_state[seat] = game
        game["last_step"] = step

        farms = observation.get("farms", []) or []
        farm = farms[seat] if seat < len(farms) else {}
        positions = [farm.get("farmer"), *(farm.get("hands") or [])]
        ops = [action.get("farmer", ["PASS"]), *(action.get("hands") or [])]
        active = game["active"]

        # Retry any intent that's been waiting since a previous DIG.
        for actor, pending in list(active.items()):
            index = 0 if actor == "farmer" else int(actor) + 1
            if index >= len(ops):
                active.pop(actor, None)
                continue
            age = step - pending["start"]
            if age == 1:
                ops[index] = list(pending["intended"])
            elif age > WEED_REPLAY_STEPS:
                active.pop(actor, None)

        # Detect new weed-blocked intents.
        for index, (pos, op) in enumerate(zip(positions, ops)):
            actor = "farmer" if index == 0 else index - 1
            if actor in active or not isinstance(op, list) or not op:
                continue
            if op[0] not in ("PLANT", "BUILD_PASTURE"):
                continue
            tile = _tile_at(farm, pos)
            if not (isinstance(tile, dict) and tile.get("kind") == "WEED"):
                continue
            active[actor] = {"start": step, "intended": list(op)}
            ops[index] = ["DIG"]

        # Crop-safety net: react to the *real* board state under each actor's
        # feet, not just the recorded intent -- catches watering/harvest
        # timing drift that a scripted PLANT/BUILD weed-dodge alone can't,
        # e.g. an already-planted crop the script assumed was watered on a
        # different turn than it actually needs to be in this game's replay.
        # A WEED tile (mid weed-repair above) never matches either check, so
        # this never fights the retry logic for the same actor+turn.
        for index, pos in enumerate(positions):
            if index >= len(ops):
                break
            tile = _tile_at(farm, pos)
            if _needs_water(tile):
                ops[index] = ["WATER"]
            elif _needs_urgent_harvest(tile, step):
                ops[index] = ["HARVEST"]

        action["farmer"] = ops[0] if ops else ["PASS"]
        action["hands"] = ops[1:]
        return action

    def agent(observation: dict[str, Any]) -> dict[str, Any]:
        try:
            step = min(max(0, int(observation.get("step", 0) or 0)), len(actions) - 1)
            action = _copy_action(actions[step])
            farms = observation.get("farms", []) or []
            player = int(observation.get("player", 0) or 0)
            farm = farms[player] if player < len(farms) else {}
            action = _align_hands(action, len(farm.get("hands", []) or []))
            return repair(observation, action, step)
        except Exception:
            farms = observation.get("farms", []) or []
            player = int(observation.get("player", 0) or 0)
            farm = farms[player] if player < len(farms) else {}
            return {
                "farmer": ["PASS"],
                "hands": [["PASS"] for _ in (farm.get("hands") or [])],
                "market": [],
            }

    return agent


def freeze_to_file(actions: list[dict[str, Any]], out_path: str) -> None:
    with open(out_path, "w") as f:
        json.dump(actions, f)


def load_frozen(path: str) -> list[dict[str, Any]]:
    with open(path) as f:
        return json.load(f)
