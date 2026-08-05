# submissions/

- `baseline/main.py` -- current best-known agent. Only updated by
  `run_improvement_loop.py` after a candidate passes the acceptance gate.
- `candidate/main.py` -- working slot for the current improvement proposal,
  written by `agents/coder.py` and A/B tested by `evaluation/compare_agents.py`.

Both files must expose the same `agent(observation, configuration) -> action`
entry point, matching whatever the official Kaggriculture submission API
requires. Do not change that entry point's signature or return shape as part
of an "improvement" -- see `evaluation/acceptance_gate.py` and
`prompts/strategist.md`.
