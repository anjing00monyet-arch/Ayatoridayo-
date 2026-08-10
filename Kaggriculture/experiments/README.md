# experiments/

Working area for larger, multi-step investigations that don't fit
cleanly into the analysis/evaluation/agents pipeline -- e.g. an offline
search for a frozen action-sequence submission (see `frozen_route/`).
Not part of the improvement loop itself.

## frozen_route/

Building a submission_27-style "frozen 720-step scripted route" (see
`opponents/README.md`), but via actual offline search rather than
freezing our existing reactive agent's trajectory (which would only lose
robustness for no performance gain -- see the chat history for why).

- `parametrized_agent.py`: generalizes `submissions/baseline/main.py`
  (v8) into a `Params` dataclass + `make_agent(params)` factory, so a
  search harness can construct and evaluate many variants. Verified
  byte-identical to v8 when constructed with default params.
- `search.py`: evaluates hand-picked `Params` variants (informed by this
  session's prior manual-tuning rounds, not blind search) over a fixed
  seed set, to find the strongest configuration.
- `freeze.py` / `build_main.py`: record the winning configuration's
  actual turn-by-turn decisions into a fixed action list, wrap replay
  with a weed-repair layer (dig-and-retry, like submission_27) for
  robustness to a different game's random weed spawns, and emit a
  self-contained, submittable `main.py`.
