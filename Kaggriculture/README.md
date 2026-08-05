# Kaggriculture Agent Lab

An AI-agent-driven improvement loop for the "Kaggriculture" Kaggle
competition: research, analysis, strategy, coding, and evaluation are split
into separate agent roles, each candidate is A/B tested against the current
best agent over hundreds/thousands of matches, and only candidates that
clear a strict acceptance gate get promoted. See `docs/architecture.md` for
the full design and current build status.

Runs on the real environment: Kaggle publishes Kaggriculture as part of its
open-source `kaggle_environments` framework
(https://github.com/Kaggle/kaggle-environments), and `game/` wraps that
directly -- not a placeholder.

Structure:
- `submissions/baseline/`, `submissions/candidate/`: the current best agent
  and the working slot for the next proposal (`main.py` each)
- `game/`: wrapper around the official `kaggle_environments` "kaggriculture"
  env (`kaggriculture_env.py`) plus shared cost constants (`tables.py`)
- `replays/`: raw per-match logs, one JSON file per seed
- `analysis/`: replay parsing, profit/cost aggregation, action-timing and
  failure-pattern analysis
- `evaluation/`: run matches, A/B compare baseline vs candidate, acceptance
  gate
- `agents/`: the five agent roles (researcher, analyst, strategist, coder,
  reviewer) plus the shared LLM-calling seam
- `reports/`: generated analysis reports and the experiment history log
- `prompts/`: markdown prompt templates for each agent role
- `docs/`: architecture notes and `docs/research/` for manually-collected
  Notebook/Discussion notes
- `tools/`: misc utility scripts
- `run_improvement_loop.py`: orchestrates the full loop end to end

## Quick start

```bash
cd Kaggriculture
pip install -r requirements.txt   # installs kaggle-environments (+ anthropic, optional)
python run_improvement_loop.py --games 20   # small smoke test; full runs default to 1000
```

Without `ANTHROPIC_API_KEY` set, the loop pauses at each agent step and
writes its prompt to `reports/pending_prompts/`; run that prompt through a
Claude Code session, save the reply next to it, and re-run the loop.

Full games are 720 turns (24 turns/day x 30 days) each, so 1000-game runs
take real wall-clock time -- `evaluation/run_matches.py` and
`evaluation/compare_agents.py` both accept `--episode-steps` to shorten
episodes for quick local iteration.
