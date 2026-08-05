# Kaggriculture Agent Lab

An AI-agent-driven improvement loop for the "Kaggriculture" Kaggle
competition: research, analysis, strategy, coding, and evaluation are split
into separate agent roles, each candidate is A/B tested against the current
best agent over hundreds/thousands of matches, and only candidates that
clear a strict acceptance gate get promoted. See `docs/architecture.md` for
the full design and current build status (short version: `game/` is a
placeholder until the official simulator is vendored in; everything else is
implemented and runnable today).

Structure:
- `submissions/baseline/`, `submissions/candidate/`: the current best agent
  and the working slot for the next proposal (`main.py` each)
- `game/`: seam to the actual Kaggriculture environment (`interface.py` +
  placeholder `stub_env.py`)
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
pip install -r requirements.txt   # only needed for unattended LLM API mode
python run_improvement_loop.py --games 200
```

Without `ANTHROPIC_API_KEY` set, the loop pauses at each agent step and
writes its prompt to `reports/pending_prompts/`; run that prompt through a
Claude Code session, save the reply next to it, and re-run the loop.
