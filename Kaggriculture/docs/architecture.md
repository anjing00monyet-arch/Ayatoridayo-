# Architecture: Kaggriculture Agent Lab

Reproduces the "AIエージェント型Kaggle開発環境" pattern from DeNA×AI Talks #6
(生成AI時代のKaggleの戦い方): split research / analysis / strategy /
implementation / evaluation into separate roles instead of asking one model
to "make it stronger" in one shot.

```
Kaggleのルール・ゲームコード
          |
          v
[1] researcher   agents/researcher.py   ルール・公開Notebook・Discussion・過去解法を整理 (docs/research/)
          |
          v
[2] run_matches  evaluation/run_matches.py   ベースラインで試合を実行し replays/ に保存
          |
          v
[3] analyst      agents/analyst.py      analysis/* で敗因・利益損失を集計 -> reports/latest_analysis.md
          |
          v
[4] strategist   agents/strategist.py   数式・戦略・パラメータ変更案を設計書として作成
          |
          v
[5] coder        agents/coder.py        submissions/candidate/main.py を自動修正
          |
          v
[6] reviewer     agents/reviewer.py     静的チェック + 設計書との整合性を事前レビュー
          |
          v
[7] compare_agents  evaluation/compare_agents.py   旧版と新版を同一シナリオで数百-数千試合比較
          |
          v
[8] acceptance_gate  evaluation/acceptance_gate.py   厳しい採用条件を全て満たした場合のみ
          |
          v
        採用 -> submissions/baseline/main.py を更新、reports/experiment_history.csv に記録
          |
          v
        繰り返し (run_improvement_loop.py)
```

## Why the acceptance gate is strict

An AI-written candidate that wins "on average" can still be a regression --
occasionally crashing, throwing invalid actions, or bombing one scenario
hard enough to erase the average gain. `evaluation/acceptance_gate.py`
requires *all* of:

- `mean_profit_delta >= 5000`
- `median_profit_delta > 0`
- `win_rate_delta >= 0.02`
- `crash_count == 0`
- `invalid_action_count == 0`
- `worst_scenario_delta >= -2000`

## Why replays are parsed into a stat table before reaching an LLM

Handing a whole replay to an LLM doesn't improve analysis quality. Every
match is compacted by `analysis/replay_parser.py` into the schema below
before any agent sees it, and `analysis/profit_breakdown.py` aggregates
hundreds of those into means/medians/worst-case:

```json
{
  "final_bank": 176420,
  "total_revenue": 291300,
  "worker_cost": 43200,
  "seed_cost": 18600,
  "animal_cost": 24500,
  "land_cost": 3000,
  "product_cost": 400,
  "idle_actions": 17,
  "dead_crops": 4,
  "escaped_animals": 1,
  "missed_harvests": 3,
  "late_investment_loss": 12800,
  "revenue_by_item": {"MELON": 74500, "STRAWBERRY": 48200, "MILK": 62100},
  "critical_failures": [
    "day 18: hired a farm hand late in the season",
    "day 25: planted melon with insufficient recovery window",
    "day 27: sold milk while price was falling"
  ]
}
```

`land_cost`/`product_cost` extend the original design sketch to cover two
Kaggriculture-specific spending categories that don't fit worker/seed/animal:
`BUY_LAND` (unlocking quadrants) and `BUY_PRODUCT` (buying back wheat/fertilizer).

## Current build status

- `game/` -- **wired to the real environment**. Kaggle publishes
  Kaggriculture as part of the open-source `kaggle_environments` framework
  (https://github.com/Kaggle/kaggle-environments); `game/kaggriculture_env.py`
  wraps `kaggle_environments.make("kaggriculture", ...)` directly, and
  `game/tables.py` re-exports the real cost constants from the installed
  package. See `game/README.md`.
- `analysis/`, `evaluation/` -- fully implemented against the real
  observation/action schema (`farms`, `private`, `market`, `town`; action
  shape `{"farmer": [...], "hands": [...], "market": [...]}`). Cost/revenue
  attribution is computed from each turn's submitted market orders against
  the real cost tables and that turn's market prices; `qty > 1` sell/buy
  orders are a close approximation (see replay_parser.py's docstring) since
  the real per-unit price can drift mid-order.
- `agents/`, `prompts/` -- fully implemented. Defaults to **manual mode**
  (see `agents/llm_client.py`): prompts are written to
  `reports/pending_prompts/` for you to run through a Claude Code session by
  hand, matching the semi-automatic first version recommended in the
  project notes. Set `ANTHROPIC_API_KEY` to run unattended instead.
- `run_improvement_loop.py` -- wires all of the above together. Never
  pushes to git on its own; promoted candidates land in
  `submissions/baseline/main.py` and `reports/experiment_history.csv` for
  you to review and commit.
- `submissions/baseline/main.py` -- starts as a vendored copy of
  `kaggle_environments`'s built-in `starter_agent` (a carrot loop). Real,
  legal, and intentionally simple -- the improvement loop's whole job is to
  find and validate something that beats it.

## Recommended first workflow (semi-automatic)

1. `python evaluation/run_matches.py baseline --games 1000` (against the
   built-in `"random"` opponent by default; full 720-turn episodes, so
   budget real wall-clock time -- try `--games 20 --episode-steps 96` first
   to sanity-check locally)
2. `python agents/analyst.py` (writes `reports/latest_analysis.md`)
3. `python agents/strategist.py` -- read the proposals, pick one
4. `python agents/coder.py` -- writes `submissions/candidate/main.py`
5. `python evaluation/compare_agents.py --games 1000` -- head-to-head A/B
   report + gate verdict (baseline vs. candidate directly, not vs. a third
   party)
6. If accepted, review the diff yourself, then commit
   `submissions/baseline/main.py` to a new branch and submit to Kaggle.

`run_improvement_loop.py` automates steps 1-5 end to end, pausing at any
step that needs a manual LLM reply.
