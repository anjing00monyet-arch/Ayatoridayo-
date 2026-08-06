# engine/

This directory intentionally does **not** contain the `cg` package (the
competition's game engine). It's Kaggle-competition-provided code with an
unclear redistribution license, and this repo is public -- committing it
here would be a real licensing risk, not a hypothetical one.

## What to do instead

Every harness entry point (`harness/run_batch.py`, `harness/compare_ab.py`,
`harness/run_arms.py`, `harness/run_match.py`) takes a `cg_root` (config key
or `--cg-root` flag): the **parent directory** that contains `cg/game.py`.
Point it at wherever you already have the competition's engine installed
locally or as a Kaggle input, e.g.:

```bash
python run_arms.py --cg-root /kaggle/input/competitions/pokemon-tcg-ai-battle/... --preset isolate
```

`cg/` is listed in `.gitignore` at the repo root so that if you *do* drop a
local copy in `engine/cg/` for convenience, it won't get committed by
accident.
