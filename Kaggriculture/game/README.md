# game/

Wraps the official Kaggriculture environment, published by Kaggle as part of
the open-source `kaggle_environments` framework
(https://github.com/Kaggle/kaggle-environments). This is the real
competition environment -- not a placeholder.

- `kaggriculture_env.py` -- `play_match(agent_a, agent_b, seed, configuration)`
  runs one episode via `kaggle_environments.make("kaggriculture", ...)` and
  returns the full replay as a JSON-serializable dict, plus small helpers
  (`final_money`, `final_status`, `crashed`).
- `tables.py` -- crop/animal cost constants (imported straight from the
  installed `kaggle_environments` package so they can't drift) plus the
  hire-cost and land-cost formulas, used by `analysis/` to attribute money
  deltas to spending categories.

## Setup

```bash
pip install -r requirements.txt   # installs kaggle-environments
```

## Rules reference

Full game rules (crop/animal tables, market price function, turn processing
order, observation/action schema) live in the installed package:

```
<site-packages>/kaggle_environments/envs/kaggriculture/README.md
<site-packages>/kaggle_environments/envs/kaggriculture/AGENTS.md
```

Or read them online in the `kaggle_environments` GitHub repo. Three built-in
opponents are available by name for quick testing/evaluation: `"pass"`,
`"random"`, and `"starter"` (a deterministic carrot-loop baseline -- also
what `submissions/baseline/main.py` in this repo is a copy of).

## Agent contract (do not change)

```python
def agent(observation: dict) -> dict:
    ...  # returns {"farmer": [op, ...], "hands": [[op, ...], ...], "market": [[op, ...], ...]}
```

This is the official Kaggle submission signature. `evaluation/acceptance_gate.py`
and `prompts/strategist.md` both forbid changing it as part of an
"improvement" -- see `submissions/README.md`.
