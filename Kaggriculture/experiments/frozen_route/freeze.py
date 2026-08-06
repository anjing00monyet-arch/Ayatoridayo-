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


def _trace_actor_action(actions: list[dict[str, Any]], step: int, actor) -> list[Any]:
    trace = actions[min(max(int(step), 0), len(actions) - 1)] or {}
    if actor == "farmer":
        return list(trace.get("farmer") or ["PASS"])
    hands = trace.get("hands", []) or []
    return list(hands[actor] if actor < len(hands) else ["PASS"])


def make_frozen_agent(actions: list[dict[str, Any]]):
    """Returns an `agent(observation)` that replays `actions` by step
    index, digging out and retrying any PLANT/BUILD_PASTURE that lands on
    a weed the recording didn't have.

    A DIG-then-retry costs an actor one extra turn versus the recording,
    which -- if left uncorrected -- permanently shifts every later
    scripted move for that actor by one step for the rest of the game
    (movement is a sequence of relative NORTH/SOUTH/EAST/WEST commands,
    so a single dropped or duplicated turn desyncs position forever, not
    just for that one interaction). This cost a validated 15-seed run
    dearly (mean $62,971 -> $38,743, dead crops 1/15 -> 15/15) when an
    earlier fix here tried to patch the *symptom* (an unwatered crop
    under an actor's feet) instead of the *cause*: it clobbered movement
    commands for actors merely passing through a tile, with no way to
    resync afterward.

    The technique below -- lifted from decoding a real competitor
    submission's frozen route (submission_29) -- fixes the cause: after
    the single retry (age 1), it spends `WEED_REPLAY_STEPS` further turns
    replaying the action recorded one step *earlier* than the current
    step for that actor, i.e. catching up the whole one-step backlog the
    interruption created, before reverting to playing the script exactly
    on-index again. The actor loses exactly one of its originally
    recorded actions total (absorbed within the catch-up window), never
    an open-ended drift.
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

        # Retry any intent that's been waiting since a previous DIG, then
        # spend the rest of the catch-up window replaying the one-step-
        # earlier action so the actor re-syncs to the script's step index.
        for actor, pending in list(active.items()):
            index = 0 if actor == "farmer" else int(actor) + 1
            if index >= len(ops):
                active.pop(actor, None)
                continue
            age = step - pending["start"]
            if age == 1:
                ops[index] = list(pending["intended"])
            elif 2 <= age <= 1 + WEED_REPLAY_STEPS:
                ops[index] = _trace_actor_action(actions, step - 1, actor)
            else:
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
