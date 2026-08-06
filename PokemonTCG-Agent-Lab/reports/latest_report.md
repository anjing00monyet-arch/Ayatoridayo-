# Latest report

No run has been generated in this repository yet.

Generate this file with:

```bash
cd harness
python run_arms.py --preset isolate --games 500 --cg-root /path/to/cg/parent
cd ../replay_analyzer
python matchup_report.py ../harness/out/run_arms/run_arms_report.json
```

The last real run of this kind (from the notebook-based predecessor of
`run_arms.py`, before this repo existed) is recorded in
`experiments/history.csv` for reference: the `isolate` preset at 500
games/arm, all matchups, `2026-08-05`, which found `a3` alone breaching the
`true_self_snipe` gate ceiling.
