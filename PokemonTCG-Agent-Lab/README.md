# PokemonTCG-Agent-Lab

Analysis and improvement environment for the Archaludon ex + Cinderace
rule-based agent. Not utility-maximization scoring like Kaggriculture --
this lab is built around win rate, per-matchup breakdowns, and the specific
mechanism metrics (self-snipe rate, lethal suppression, mill detection) that
have driven every real finding so far, ahead of raw win rate.

## What needs the `cg` engine, and what doesn't

The competition's game engine (`cg`) is **not** committed here (see
[`engine/README.md`](engine/README.md) for why) and is not available on
GitHub-hosted CI runners. That splits every tool in this repo into two
tiers:

| Needs `cg` (pass `--cg-root`) | Pure Python, runs anywhere |
|---|---|
| `harness/run_batch.py`, `harness/compare_ab.py` | `tools/validate_agent.py` |
| `harness/run_match.py`, `harness/run_arms.py` | `tools/package_submission.py` |
| `run_improvement_loop.py` | `harness/seed_schedule.py` |
| | `harness/acceptance_gate.py` (reads existing `summary.json`) |
| | `replay_analyzer/*.py` (reads existing `games.csv`/replays) |

`.github/workflows/pokemon-tcg-smoke-test.yml` runs the right-hand column on
every push. The left-hand column has template workflows
(`pokemon-tcg-ab-evaluation.yml`, `pokemon-tcg-nightly-gauntlet.yml`) that
need a self-hosted runner with `cg` installed before they'll do anything
real -- see the comments at the top of each file.

## Layout

```
agents/
  baseline/          the current known-good main.py + deck.csv (flags off)
  candidate/          the version under test
  opponents_decks/    fixed opponent deck.csv files (alakazam/lucario/archaludon_mirror/tusk_mill)
engine/                cg goes here locally; not committed (see engine/README.md)
harness/
  harness/             the actual runner package (agent_loader, bots, compare, engine,
                       metrics, replay, runner, utils, validation)
  run_batch.py          run one variant against the configured opponent mixture
  run_match.py          run exactly one game, for debugging (new)
  compare_ab.py          A/B exactly two variants, isolated subprocesses
  run_arms.py            N arms (flag or deck changes) vs one baseline (new; repo-native
                         version of the notebook-embedded multi-arm runner used during
                         the tusk_mill investigation)
  acceptance_gate.py      multi-criteria promote/reject decision (new)
  seed_schedule.py        preview a config's game schedule without running anything (new)
  configs/                config JSON schema examples for run_batch.py / compare_ab.py
replay_analyzer/
  parse_replay.py         load trial/replay JSON into a normalized shape (new)
  classify_losses.py      tag lost games with loss-reason categories (new)
  board_metrics.py        the snipe-rate / confounder analysis with proper CIs
                          (moved from the standalone analyze_snipes.py script)
  matchup_report.py       turn a run_arms report into reports/latest_report.md (new)
  extract_true_snipes.py  pull true_self_snipe events out of trials/ for manual review
experiments/
  opponents.json          the opponent mixture used across the tusk_mill investigation
  experiment.yaml          template: record a hypothesis before you run it
  history.csv             append-only log of what was tried and whether it was promoted
prompts/
  analyst.md / strategist.md / coder.md / reviewer.md
                          role instructions for whoever (human or assistant) is driving
                          a given step of the improvement loop -- see run_improvement_loop.py
reports/                 generated output (latest_report.md, matchup_matrix.csv, regressions.json)
tools/
  package_submission.py    zip an agents/<name>/ into a submission (moved from make_submission.py)
  validate_agent.py        syntax/deck-legality/flag-default checks, no cg needed (new)
  download_replays.py      fetch Kaggle episode replays by ID (new, untested against this
                           competition -- see its docstring)
run_improvement_loop.py   orchestrates the whole cycle end to end except patch authorship
                          (see the file's docstring for why that step is deliberately manual)
```

## Quickstart

```bash
# Everything that doesn't need cg:
python tools/validate_agent.py candidate
python tools/package_submission.py candidate
python harness/seed_schedule.py harness/configs/full_1000.json --games 1000

# Everything that does (point --cg-root at the parent of your local cg/):
cd harness
python run_arms.py --list-arms
python run_arms.py --preset isolate --games 500 --cg-root /path/to/cg/parent
```

## The improvement loop

```
agents/baseline (current best)
        |
harness/run_arms.py, fixed opponents/seed
        |
replay_analyzer/classify_losses.py
        |
[patch proposed here -- see prompts/strategist.md + prompts/coder.md,
 or run_improvement_loop.py's propose_patch() as the wiring point]
        |
agents/candidate
        |
run_arms.py again, baseline vs candidate, same conditions
        |
harness/acceptance_gate.py
        |
promote (agents/candidate -> agents/baseline) only on a pass
```

`run_improvement_loop.py` runs every mechanical step above end to end. Patch
authorship is deliberately left as an explicit extension point rather than
fully automated -- see that file's docstring for why, and `prompts/` for how
a human or an assistant session should approach each step.

## Known real findings so far (see `experiments/history.csv`)

The `isolate` preset (base/b1/a2/a3, 500 games/arm, all matchups) found that
**A3 alone** breaches the `true_self_snipe` mechanism gate's absolute
ceiling (1.47% vs a 1.0% ceiling), not B1 as first suspected when a bundled
B1+A2+A3 candidate was originally rejected. `a3fix` (base/a3/a3_bench/a3_d1)
is the follow-up test isolating which of the two proposed fixes -- exempting
Pokemon search cards from A3's draw-stop, or mirroring the gate's own
readiness definition back into the promotion guard -- actually closes the
gap; see `experiments/experiment.yaml` for the recorded hypothesis.
