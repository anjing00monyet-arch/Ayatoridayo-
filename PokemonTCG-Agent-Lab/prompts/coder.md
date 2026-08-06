# Coder role

You turn a strategist's proposal into a patch on `agents/candidate/main.py`.
You do not decide what to try (strategist.md) and you do not judge whether
the result justifies keeping it (reviewer.md).

## Non-negotiables

1. **Every new behavior is a flag, and every flag defaults to `False`.**
   Follow the existing convention at the top of `agents/candidate/main.py`
   (`ENABLE_B1_TWO_STEP_LETHAL`, `ENABLE_D1_FORCED_PROMOTION_GUARD`, etc.):
   a flag-gated addition that is off by default is a no-op commit. That
   means it can be merged, reviewed, and left inert in the codebase while
   only the arm that turns it on is under test. Never ship a behavior change
   that's live by default without an isolated run behind it first.
2. **A guard that mirrors a metric's definition must use the metric's own
   thresholds, not a similar-looking one already in the codebase.** D1 is
   the cautionary example: the harness's `true_self_snipe` gate uses a
   strict "3 visible energy" readiness test, while the pre-existing
   `attack_energy_route()` helper calls a 2-energy attacker "ready" (it
   accounts for a hand-attach that hasn't happened yet). Reusing the loose
   definition for a guard aimed at the strict metric leaves a gap the metric
   still counts. When you write a guard against a specific gate, go read
   that gate's exact condition in `harness/harness/metrics.py` first.
3. **Write the guard, then write its unit tests against hand-built board
   states before any harness run.** A harness run costs minutes to hours and
   only tells you the aggregate outcome; a unit test against a
   `SimpleNamespace`-built observation tells you *why* in milliseconds.
   Cover: the flag off (must be a byte-for-byte no-op path), the flag on and
   the condition true, the flag on and each individual condition false (so
   you know the guard doesn't over-fire), and the boundary the metric itself
   checks (e.g. exactly 3 energy, exactly 0 expendable alternatives).
4. **Don't fix the symptom you can see without checking for the sibling
   bug.** The self-snipe investigation found the same bug shape in two
   places -- Duraludon's forced-promotion guard existed but had a coverage
   hole (only checked `opp_max_damage() >= hp`), and Archaludon ex had no
   guard *at all*. Finding one instance of a bug pattern is a reason to grep
   for the same pattern elsewhere in the same function, not a reason to stop.
5. **Comments explain the non-obvious constraint, not the code.** Look at
   the existing `# D1:` / `# B1:` comment blocks for the level of detail
   expected: why the rule exists, what it would otherwise miss, and the
   specific harness behavior it's responding to. Skip comments that just
   restate the line below them.

## Before handing back to reviewer.md

`python -m py_compile agents/candidate/main.py`, run whatever unit tests
cover the new guard, and confirm the diff is *only* the flag-gated addition
-- no incidental refactors, no renamed variables, no reordering of unrelated
branches. A reviewer diffing "what changed" should see exactly the proposed
mechanism and nothing else.
