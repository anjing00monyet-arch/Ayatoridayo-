# game/

This folder is the seam between the improvement-loop tooling and the actual
Kaggriculture competition environment.

- `interface.py` defines the `GameEnv` protocol every environment
  implementation must satisfy, plus `load_env()` / `play_match()` helpers
  used by `evaluation/run_matches.py`.
- `stub_env.py` is a placeholder (`RandomStubEnv`) that produces
  correctly-shaped replay records using simple random economics, so the rest
  of the pipeline can be built, run, and tested before the official rules
  are vendored here.

## Plugging in the real environment

1. Add the official Kaggriculture simulator (or a thin wrapper around the
   `kaggle_environments`-style API) as a new module in this folder, e.g.
   `game/kaggriculture_env.py`.
2. Implement the `GameEnv` protocol from `interface.py`:
   `reset(seed)`, `step(action)`, `invalid_action_count`, `crashed`.
   Keep the `step_record` fields (`day`, `bank`, `revenue_by_item`, `costs`,
   `events`, `idle`, `dead_crops`, `escaped_animals`, `missed_harvest`)
   because `analysis/replay_parser.py` depends on them.
3. Point evaluation calls at it, e.g.
   `run_matches(..., env_path="game.kaggriculture_env:KaggricultureEnv")`.
4. Do **not** change the official observation/action schema to make step 2
   easier -- adapt the wrapper instead. The acceptance gate and strategist
   prompt both explicitly forbid touching the official API.
