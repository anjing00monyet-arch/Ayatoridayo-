from __future__ import annotations

import json
import hashlib
import multiprocessing as mp
import os
import tempfile
from pathlib import Path
from typing import Any

from .runner import run_batch_config
from .utils import (
    difference_interval,
    fisher_exact_one_sided,
    read_json,
    wilson_interval,
    write_csv,
    write_json,
)


def _soft_gate(
    name: str,
    k_cand: int,
    n_cand: int,
    k_base: int,
    n_base: int,
    *,
    absolute_rate_ceiling: float,
    alpha: float = 0.05,
) -> dict[str, Any]:
    """Statistical mechanism gate for low-count metrics.

    FAILs only when the candidate's regression is statistically significant
    (one-sided Fisher exact, p < alpha) OR the candidate's absolute rate
    exceeds the ceiling. A raw 3->4 count increase passes; 3->12 fails.
    """
    rate_cand = k_cand / n_cand if n_cand else 0.0
    rate_base = k_base / n_base if n_base else 0.0
    p = fisher_exact_one_sided(k_cand, n_cand, k_base, n_base)
    significant = p < alpha and rate_cand > rate_base
    over_ceiling = rate_cand > absolute_rate_ceiling
    return {
        "gate": name,
        "candidate": {"events": k_cand, "total": n_cand, "rate": rate_cand},
        "baseline": {"events": k_base, "total": n_base, "rate": rate_base},
        "fisher_one_sided_p": p,
        "alpha": alpha,
        "absolute_rate_ceiling": absolute_rate_ceiling,
        "significant_regression": significant,
        "over_absolute_ceiling": over_ceiling,
        "passed": not (significant or over_ceiling),
    }


def mechanism_gates(sa: dict[str, Any], sb: dict[str, Any]) -> dict[str, Any]:
    """Hard gates stay hard (expected-zero metrics); noisy low-count metrics
    use Fisher-based soft gates so single-event jitter cannot veto adoption."""

    def _i(summary: dict[str, Any], key: str) -> int:
        return int(summary.get(key, 0) or 0)

    hard = {
        "candidate_mill_false_positives_zero": _i(sb, "mill_false_positives") == 0,
        "candidate_mill_false_negatives_zero_when_observable": _i(sb, "mill_false_negatives") == 0,
        "candidate_crashes_zero": _i(sb, "crashes") == 0,
        "candidate_illegal_actions_zero": _i(sb, "illegal_actions") == 0,
        "candidate_replay_validation_clean": _i(sb, "replay_validation_failures") == 0,
    }
    # Prefer the card-class based true-snipe counter when both runs report it;
    # fall back to the legacy suspected-snipe counter for older result files.
    snipe_key = (
        "c0_2_true_self_snipes"
        if "c0_2_true_self_snipes" in sa and "c0_2_true_self_snipes" in sb
        else "c0_2_self_inflicted_snipes"
    )
    soft = [
        _soft_gate(
            f"{snipe_key}_not_significantly_worse",
            _i(sb, snipe_key), _i(sb, "c0_2_promotion_events"),
            _i(sa, snipe_key), _i(sa, "c0_2_promotion_events"),
            absolute_rate_ceiling=0.01,
        ),
        _soft_gate(
            "c0_2_ready_duraludon_avoidance_not_significantly_worse",
            _i(sb, "c0_2_voluntary_avoided_ready_duraludon"), _i(sb, "c0_2_promotion_events"),
            _i(sa, "c0_2_voluntary_avoided_ready_duraludon"), _i(sa, "c0_2_promotion_events"),
            absolute_rate_ceiling=0.02,
        ),
        _soft_gate(
            "c0_3_lethal_suppressions_not_significantly_worse",
            _i(sb, "c0_3_lethal_opportunities_suppressed"), _i(sb, "c0_3_lethal_opportunities"),
            _i(sa, "c0_3_lethal_opportunities_suppressed"), _i(sa, "c0_3_lethal_opportunities"),
            absolute_rate_ceiling=0.02,
        ),
    ]
    return {
        "hard_gates": hard,
        "soft_gates": soft,
        "self_snipe_metric_used": snipe_key,
        "passed": all(hard.values()) and all(g["passed"] for g in soft),
    }


def _worker(config_path: str, queue: Any) -> None:
    try:
        result = run_batch_config(config_path)
        queue.put({"ok": True, "result": result})
    except Exception as exc:
        import traceback
        queue.put({"ok": False, "error": repr(exc), "traceback": traceback.format_exc()})


def _build_variant_config(shared: dict[str, Any], variant: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    cfg = {
        "game_module": shared.get("game_module", "cg.game"),
        "cg_root": shared.get("cg_root"),
        "variant": variant,
        "opponents": shared["opponents"],
        "games": int(shared.get("games_per_variant", shared.get("games", 100))),
        "schedule_seed": int(shared.get("schedule_seed", 0)),
        "max_decisions": int(shared.get("max_decisions", 2000)),
        "save_replays": bool(shared.get("save_replays", True)),
        "balance_first_second": bool(shared.get("balance_first_second", True)),
        "balance_max_attempt_multiplier": float(shared.get("balance_max_attempt_multiplier", 8.0)),
        "error_policy": str(shared.get("error_policy", "fallback")),
        "output_dir": str(output_dir),
    }
    return cfg


def compare_config(config_path: str) -> dict[str, Any]:
    source = Path(config_path).resolve()
    base = source.parent
    shared = read_json(source)
    variants = list(shared.get("variants", []))
    if len(variants) != 2:
        raise ValueError("compare config must contain exactly two variants")
    output_root = Path(shared.get("output_dir", "ab_out"))
    if not output_root.is_absolute():
        output_root = (base / output_root).resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    # Resolve all paths before sending child configs.
    def resolve(value: str | None) -> str | None:
        if value is None:
            return None
        p = Path(value)
        return str(p if p.is_absolute() else (base / p).resolve())

    shared["cg_root"] = resolve(shared.get("cg_root"))
    for opp in shared["opponents"]:
        opp["deck"] = resolve(opp["deck"])
    identity_rows: list[dict[str, Any]] = []
    for variant in variants:
        variant["main"] = resolve(variant["main"])
        variant["deck"] = resolve(variant["deck"])
        main_bytes = Path(str(variant["main"])).read_bytes()
        deck_bytes = Path(str(variant["deck"])).read_bytes()
        actual_main = hashlib.sha256(main_bytes).hexdigest()
        actual_deck = hashlib.sha256(deck_bytes).hexdigest()
        expected_main = str(variant.get("expected_main_sha256", "") or "").lower()
        expected_deck = str(variant.get("expected_deck_sha256", "") or "").lower()
        identity_rows.append({
            "variant": str(variant.get("name", "variant")),
            "main_path": variant["main"],
            "deck_path": variant["deck"],
            "main_sha256": actual_main,
            "deck_sha256": actual_deck,
            "expected_main_sha256": expected_main or None,
            "expected_deck_sha256": expected_deck or None,
            "main_verified": not expected_main or actual_main == expected_main,
            "deck_verified": not expected_deck or actual_deck == expected_deck,
        })
    write_json(output_root / "identity_manifest.json", {
        "harness_version": "7.0-submit-ready",
        "variants": identity_rows,
        "all_verified": all(x["main_verified"] and x["deck_verified"] for x in identity_rows),
    })
    if not all(x["main_verified"] and x["deck_verified"] for x in identity_rows):
        raise RuntimeError("Variant identity verification failed; inspect identity_manifest.json")

    ctx = mp.get_context("spawn")
    queue = ctx.Queue()
    processes = []
    config_paths: list[str] = []
    for variant in variants:
        name = str(variant.get("name", "variant"))
        child_out = output_root / name
        child_cfg = _build_variant_config(shared, variant, child_out)
        child_cfg_path = output_root / f"resolved-{name}.json"
        write_json(child_cfg_path, child_cfg)
        config_paths.append(str(child_cfg_path))
        process = ctx.Process(target=_worker, args=(str(child_cfg_path), queue), name=f"harness-{name}")
        process.start()
        processes.append(process)

    messages = [queue.get() for _ in processes]
    for process in processes:
        process.join()
    failures = [m for m in messages if not m.get("ok")]
    if failures:
        raise RuntimeError("A/B worker failed:\n" + "\n".join(m.get("traceback", m.get("error", "")) for m in failures))

    result_by_name = {m["result"]["summary"]["variant"]: m["result"] for m in messages}
    ordered_names = [str(v.get("name", "variant")) for v in variants]
    try:
        a, b = (result_by_name[ordered_names[0]], result_by_name[ordered_names[1]])
    except KeyError as exc:
        raise RuntimeError(f"Missing worker result for {exc.args[0]!r}") from exc
    sa, sb = a["summary"], b["summary"]
    a_ci = wilson_interval(int(sa["wins"]), int(sa["games_completed"]))
    b_ci = wilson_interval(int(sb["wins"]), int(sb["games_completed"]))
    diff, low, high = difference_interval(
        int(sb["wins"]), int(sb["games_completed"]),
        int(sa["wins"]), int(sa["games_completed"]),
    )

    gates = mechanism_gates(sa, sb)
    comparison = {
        "baseline": sa["variant"],
        "candidate": sb["variant"],
        "baseline_summary": sa,
        "candidate_summary": sb,
        "baseline_wilson95": a_ci,
        "candidate_wilson95": b_ci,
        "candidate_minus_baseline": diff,
        "difference_normal95": [low, high],
        "mechanism_gates": gates,
        "important_note": (
            "This is an unpaired independent comparison. schedule_seed fixes only matchup composition/order/seat, "
            "not cg.game randomness. Low-count mechanism metrics use one-sided Fisher exact soft gates "
            "(fail only on statistically significant regression or absolute-ceiling breach); "
            "expected-zero metrics (mill false positives, crashes, illegal actions) remain hard gates."
        ),
    }
    write_json(output_root / "comparison.json", comparison)

    matchup_rows: list[dict[str, Any]] = []
    labels = sorted(set(sa.get("by_opponent", {})) | set(sb.get("by_opponent", {})))
    for label in labels:
        xa = sa.get("by_opponent", {}).get(label, {"games": 0, "wins": 0, "win_rate": 0})
        xb = sb.get("by_opponent", {}).get(label, {"games": 0, "wins": 0, "win_rate": 0})
        matchup_rows.append({
            "opponent": label,
            f"{sa['variant']}_games": xa["games"],
            f"{sa['variant']}_wins": xa["wins"],
            f"{sa['variant']}_win_rate": xa["win_rate"],
            f"{sb['variant']}_games": xb["games"],
            f"{sb['variant']}_wins": xb["wins"],
            f"{sb['variant']}_win_rate": xb["win_rate"],
            "candidate_minus_baseline": float(xb["win_rate"]) - float(xa["win_rate"]),
        })
    write_csv(output_root / "matchup_comparison.csv", matchup_rows)
    matchup_regressions = [
        row for row in matchup_rows
        if float(row.get("candidate_minus_baseline", 0.0)) < -0.05
    ]
    games_per_variant = min(int(sa.get("games_completed", 0) or 0), int(sb.get("games_completed", 0) or 0))
    if not gates.get("passed", False):
        verdict = "REJECT_CANDIDATE_MECHANISM_REGRESSION"
    elif matchup_regressions:
        verdict = "KEEP_BASELINE_MATCHUP_REGRESSION"
    elif high < 0:
        verdict = "KEEP_BASELINE_STATISTICALLY_SUPERIOR"
    elif low > 0 and games_per_variant >= 500:
        verdict = "ADOPT_CANDIDATE_FINAL_SUPERIOR"
    elif games_per_variant < 500 and diff > 0:
        verdict = "RUN_FULL_1000_CANDIDATE_PROMISING"
    else:
        verdict = "KEEP_BASELINE_INCONCLUSIVE"
    comparison["harness_version"] = "7.0-submit-ready"
    comparison["matchup_regressions_over_5pp"] = matchup_regressions
    comparison["verdict"] = verdict
    write_json(output_root / "comparison.json", comparison)
    return comparison
