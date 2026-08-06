"""Load a trial or replay JSON into a small normalized shape.

Two file kinds come out of harness/runner.py per game:
  * trials/trial-*.json   -- {trial, instrumentation, replay_validation, errors, ...}
                              trial is one row of games.csv; instrumentation carries
                              the full c0_2_duraludon_promotion_events list.
  * replays/game-*.json   -- Kaggle-replay-compatible: top-level "steps", each step
                              has both players' observation (see harness/replay.py).

Most analysis (classify_losses, board_metrics) only needs the trial JSON --
it's orders of magnitude smaller and already has every derived metric. Reach
for the replay JSON only when you need the turn-by-turn observation/action
sequence itself (e.g. to eyeball what a specific true_self_snipe actually did).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class Trial:
    path: Path
    row: dict[str, Any]            # == games.csv row for this game
    instrumentation: dict[str, Any]
    errors: list[str]

    @property
    def variant(self) -> str:
        return str(self.row.get("variant", ""))

    @property
    def opponent(self) -> str:
        return str(self.row.get("opponent", ""))

    @property
    def won(self) -> bool:
        return bool(int(self.row.get("won", 0) or 0))

    @property
    def promotion_events(self) -> list[dict[str, Any]]:
        return self.instrumentation.get("c0_2_duraludon_promotion_events") or []

    @property
    def true_self_snipe_events(self) -> list[dict[str, Any]]:
        return [e for e in self.promotion_events if e.get("true_self_snipe")]


def load_trial(path: Path) -> Trial:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return Trial(
        path=Path(path),
        row=data.get("trial", {}),
        instrumentation=data.get("instrumentation", {}),
        errors=data.get("errors", []),
    )


def iter_trials(trials_dir: Path, variant: str | None = None) -> list[Trial]:
    trials = []
    for path in sorted(Path(trials_dir).glob("trial-*.json")):
        if variant and variant not in path.name:
            continue
        trials.append(load_trial(path))
    return trials


def load_replay(path: Path) -> dict[str, Any]:
    """Return the raw Kaggle-compatible replay dict. steps[i][player]["observation"]
    gives that player's view after step i; steps[0] is the pre-game placeholder
    (see ReplayRecorder.__init__)."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def replay_actions(replay: dict[str, Any], seat: int) -> list[list[int]]:
    """The sequence of actions `seat` actually submitted, in order."""
    return [step[seat]["action"] for step in replay.get("steps", [])[1:] if step[seat]["action"]]
