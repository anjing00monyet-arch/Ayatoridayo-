# submissions/

- `baseline/main.py` -- current best-known agent. Only updated by
  `run_improvement_loop.py` after a candidate passes the acceptance gate.
- `candidate/main.py` -- working slot for the current improvement proposal,
  written by `agents/coder.py` and A/B tested by `evaluation/compare_agents.py`.

Both files must expose the official Kaggriculture entry point,
`agent(observation: dict) -> dict`, and return an action of the shape
`{"farmer": [...], "hands": [...], "market": [...]}`. Do not change that
signature or return shape as part of an "improvement" -- see
`evaluation/acceptance_gate.py` and `prompts/strategist.md`.

## Note on `from game.tables import CROPS`

Both files import cost constants from `game/tables.py` for convenience during
local development (`run_improvement_loop.py` runs with the repo root on
`PYTHONPATH`, so this resolves fine). **Kaggle's actual grading server only
sees whatever you submit** -- if a proposal needs `game/tables.py`, submit it
as a multi-file bundle (`tar -czf submission.tar.gz main.py game/tables.py
game/__init__.py -m "..."`, see `game/README.md` / the vendored
`AGENTS.md` in `kaggle_environments` for the exact submit command) or inline
the constants directly in `main.py` before submitting.
