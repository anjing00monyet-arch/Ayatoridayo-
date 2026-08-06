from __future__ import annotations

import sys
import time
import traceback
from pathlib import Path
from typing import Any

from .agent_loader import LoadedAgent
from .bots import RandomLegalBot, load_bot, validate_action
from .engine import EngineAdapter, current_player, current_result
from .metrics import MechanismTracker
from .replay import ReplayRecorder
from .utils import canonical_hash, deck_hash, exact_weighted_schedule, read_deck, read_json, write_csv, write_json
from .validation import validate_replay_payload


def _resolve(base: Path, value: str | None) -> str | None:
    if value is None:
        return None
    p = Path(value)
    return str(p if p.is_absolute() else (base / p).resolve())


def _fallback_action(obs: dict[str, Any], seed: int) -> list[int]:
    return RandomLegalBot(seed).act(obs)


def run_game(
    *,
    engine: EngineAdapter,
    variant_name: str,
    agent: LoadedAgent,
    opponent_cfg: dict[str, Any],
    target_seat: int,
    game_index: int,
    output_dir: Path,
    save_replays: bool,
    max_decisions: int,
    bot_seed: int,
    error_policy: str = "fallback",
) -> dict[str, Any]:
    started = time.perf_counter()
    label = str(opponent_cfg["label"])
    expected_mill = bool(opponent_cfg.get("is_mill", False))
    opponent_deck = read_deck(opponent_cfg["deck"])
    opponent_bot = load_bot(str(opponent_cfg.get("bot", "greedy")), seed=bot_seed)
    opponent_bot.reset()
    reset_info = agent.reset()
    deck0, deck1 = (agent.deck, opponent_deck) if target_seat == 0 else (opponent_deck, agent.deck)
    recorder = ReplayRecorder(variant=variant_name, opponent=label, deck0=deck0, deck1=deck1)
    tracker = MechanismTracker(target_seat=target_seat, expected_mill=expected_mill)

    errors: list[str] = []
    crash_count = fallback_count = illegal_count = 0
    watched_ever: dict[str, bool] = {name: False for name in agent.watch_globals}
    winner = -1
    decisions = 0
    terminal_reason = "normal"
    replay_path = ""

    try:
        obs = engine.start(deck0, deck1)
        recorder.record_start(obs)
        tracker.observe(obs)
        while current_result(obs) == -1:
            if decisions >= max_decisions:
                terminal_reason = "max_decisions"
                raise RuntimeError(f"Exceeded max_decisions={max_decisions}")
            actor = current_player(obs)
            try:
                if actor == target_seat:
                    lethal_options = agent.lethal_attack_options(obs)
                    action = agent.act(obs)
                    watched = agent.watched_state(obs)
                    tracker.record_agent_decision(obs, action, watched, lethal_options)
                    for name, value in watched.items():
                        watched_ever[name] = watched_ever.get(name, False) or bool(value)
                else:
                    action = opponent_bot.act(obs)
            except Exception:
                crash_count += 1
                errors.append(traceback.format_exc())
                if error_policy == "fail_fast":
                    raise
                action = _fallback_action(obs, bot_seed + decisions + 1)
                fallback_count += 1

            valid, why = validate_action(obs, action)
            if not valid:
                illegal_count += 1
                errors.append(f"Illegal action by player {actor}: {action!r}: {why}")
                if error_policy == "fail_fast":
                    raise RuntimeError(errors[-1])
                action = _fallback_action(obs, bot_seed + decisions + 100_000)
                fallback_count += 1
                valid2, why2 = validate_action(obs, action)
                if not valid2:
                    raise RuntimeError(f"Fallback action also illegal: {action!r}: {why2}")

            next_obs = engine.select(action)
            decisions += 1
            result = current_result(next_obs)
            recorder.record_transition(actor, action, next_obs, result)
            obs = next_obs
            tracker.observe(obs)
        winner = current_result(obs)
    except Exception:
        if terminal_reason == "normal":
            terminal_reason = "exception"
        errors.append(traceback.format_exc())

    tracker.finalize()
    mill_seen = bool(
        watched_ever.get("_harness_policy_mill_seen", False)
        or watched_ever.get("_opp_mill_seen", False)
        or tracker.mill_seen
    )
    instrumentation = tracker.instrumentation()
    info = {
        "variant": variant_name,
        "opponent": label,
        "target_seat": target_seat,
        "game_index": game_index,
        "engine_module": engine.module_name,
        "deck_hashes": [deck_hash(deck0), deck_hash(deck1)],
        "reset": reset_info,
        "errors": errors,
        "terminal_reason": terminal_reason,
        **instrumentation,
    }
    replay_validation = {"ok": True, "errors": [], "warnings": ["replay saving disabled"]}
    if save_replays:
        replay_dir = output_dir / "replays"
        replay_dir.mkdir(parents=True, exist_ok=True)
        replay_file = replay_dir / f"game-{game_index:05d}-{variant_name}-vs-{label}-seat{target_seat}.json"
        payload = recorder.save(replay_file, winner, info)
        replay_validation = validate_replay_payload(payload)
        replay_path = str(replay_file)

    row: dict[str, Any] = {
        "variant": variant_name,
        "game_index": game_index,
        "opponent": label,
        "opponent_tier": str(opponent_cfg.get("bot", "greedy")),
        "target_seat": target_seat,
        "first_player": tracker.first_player,
        "first_player_known": int(tracker.first_player in (0, 1)),
        "target_went_first": int(tracker.first_player == target_seat) if tracker.first_player in (0, 1) else -1,
        "winner": winner,
        "won": int(winner == target_seat),
        "lost": int(winner in (0, 1) and winner != target_seat),
        "completed": int(winner in (0, 1)),
        "decisions": decisions,
        "duration_sec": round(time.perf_counter() - started, 6),
        "crash_count": crash_count,
        "illegal_action_count": illegal_count,
        "fallback_count": fallback_count,
        "mill_seen": int(mill_seen),
        "expected_mill": int(expected_mill),
        "mill_false_positive": int(mill_seen and not expected_mill),
        "terminal_reason": terminal_reason,
        "replay_path": replay_path,
        "replay_relative_path": str(Path(replay_path).relative_to(output_dir)) if replay_path else "",
        "replay_validation_ok": int(bool(replay_validation.get("ok"))),
        "replay_validation_error_count": len(replay_validation.get("errors") or []),
        "error_count": len(errors),
    }
    row.update(tracker.as_dict())

    trial_dir = output_dir / "trials"
    trial_dir.mkdir(parents=True, exist_ok=True)
    trial_file = trial_dir / f"trial-{game_index:05d}-{variant_name}-vs-{label}-seat{target_seat}.json"
    row["trial_relative_path"] = str(trial_file.relative_to(output_dir))
    write_json(trial_file, {
        "schema_version": 2,
        "trial": row,
        "instrumentation": instrumentation,
        "replay_validation": replay_validation,
        "errors": errors,
        "reset": reset_info,
        "deck_hashes": [deck_hash(deck0), deck_hash(deck1)],
    })
    return row


def summarize_rows(rows: list[dict[str, Any]], variant: str) -> dict[str, Any]:
    completed = [r for r in rows if r.get("completed") == 1]
    wins = sum(int(r.get("won", 0)) for r in completed)
    n = len(completed)
    by_opp: dict[str, dict[str, int | float]] = {}
    for row in completed:
        label = str(row["opponent"])
        d = by_opp.setdefault(label, {"games": 0, "wins": 0})
        d["games"] = int(d["games"]) + 1
        d["wins"] = int(d["wins"]) + int(row["won"])
    for d in by_opp.values():
        d["win_rate"] = float(d["wins"]) / int(d["games"]) if d["games"] else 0.0

    def rate(subset: list[dict[str, Any]]) -> float | None:
        return (sum(int(r.get("won", 0)) for r in subset) / len(subset)) if subset else None

    when_first = [r for r in completed if r.get("target_went_first") == 1]
    when_second = [r for r in completed if r.get("target_went_first") == 0]
    first_unknown = [r for r in completed if r.get("target_went_first") not in (0, 1)]
    seat0 = [r for r in completed if r.get("target_seat") == 0]
    seat1 = [r for r in completed if r.get("target_seat") == 1]
    total_duration = sum(float(r.get("duration_sec", 0)) for r in rows)
    return {
        "schema_version": 3,
        "variant": variant,
        "games_requested": len(rows),
        "games_completed": n,
        "wins": wins,
        "losses": n - wins,
        "win_rate": wins / n if n else 0.0,
        "win_rate_when_first": rate(when_first),
        "win_rate_when_second": rate(when_second),
        "games_when_first": len(when_first),
        "games_when_second": len(when_second),
        "games_first_player_unknown": len(first_unknown),
        "first_turn_imbalance": abs(len(when_first) - len(when_second)) / n if n else None,
        "win_rate_seat0": rate(seat0),
        "win_rate_seat1": rate(seat1),
        "attack_by_own_turn3_rate": sum(bool(r.get("attack_by_own_turn3")) for r in completed) / n if n else 0.0,
        "archaludon_by_own_turn3_rate": sum(bool(r.get("archaludon_by_own_turn3")) for r in completed) / n if n else 0.0,
        "mill_false_positives": sum(int(r.get("c0_1_mill_misdetection_occurred", 0)) for r in rows),
        "mill_detection_opportunities": sum(int(r.get("c0_1_mill_detection_opportunity", 0)) for r in rows),
        "mill_false_negatives": sum(int(r.get("c0_1_mill_false_negative", 0)) for r in rows),
        "mill_not_observable_games": sum(int(r.get("c0_1_mill_not_observable", 0)) for r in rows),
        "c0_2_promotion_events": sum(int(r.get("c0_2_promotion_event_count", 0)) for r in rows),
        "c0_2_promotion_violations": sum(int(r.get("c0_2_promotion_violation_count", 0)) for r in rows),
        "c0_2_self_inflicted_snipes": sum(int(r.get("c0_2_self_inflicted_snipe_count", 0)) for r in rows),
        "c0_2_true_self_snipes": sum(int(r.get("c0_2_true_self_snipe_count", 0)) for r in rows),
        "c0_2_voluntary_avoided_ready_duraludon": sum(int(r.get("c0_2_voluntary_avoided_ready_duraludon_count", 0)) for r in rows),
        "c0_3_lethal_opportunities": sum(int(r.get("c0_3_lethal_opportunity_count", 0)) for r in rows),
        "c0_3_lethal_opportunities_suppressed": sum(int(r.get("c0_3_lethal_suppression_count", 0)) for r in rows),
        "replay_validation_failures": sum(1 for r in rows if not bool(r.get("replay_validation_ok"))),
        "crashes": sum(int(r.get("crash_count", 0)) for r in rows),
        "illegal_actions": sum(int(r.get("illegal_action_count", 0)) for r in rows),
        "fallbacks": sum(int(r.get("fallback_count", 0)) for r in rows),
        "mean_duration_sec": total_duration / len(rows) if rows else 0.0,
        "throughput_games_per_min": (len(rows) * 60 / total_duration) if total_duration > 0 else None,
        "mean_decisions": sum(int(r.get("decisions", 0)) for r in rows) / len(rows) if rows else 0.0,
        "by_opponent": by_opp,
    }


def _validation_report(summary: dict[str, Any], games: int) -> dict[str, Any]:
    promotion_events = int(summary.get("c0_2_promotion_events", 0) or 0)
    suspected_snipes = int(summary.get("c0_2_self_inflicted_snipes", 0) or 0)
    true_snipes = int(summary.get("c0_2_true_self_snipes", 0) or 0)
    snipe_rate = true_snipes / promotion_events if promotion_events else 0.0
    lethal_opportunities = int(summary.get("c0_3_lethal_opportunities", 0) or 0)
    lethal_suppressions = int(summary.get("c0_3_lethal_opportunities_suppressed", 0) or 0)
    lethal_rate = lethal_suppressions / lethal_opportunities if lethal_opportunities else 0.0
    completed = int(summary.get("games_completed", 0) or 0)
    criteria = {
        "all_games_completed": completed == games,
        "crashes_zero": int(summary.get("crashes", 0) or 0) == 0,
        "illegal_actions_zero": int(summary.get("illegal_actions", 0) or 0) == 0,
        "replay_structure_valid": int(summary.get("replay_validation_failures", 0) or 0) == 0,
        "first_player_fully_captured": int(summary.get("games_first_player_unknown", 0) or 0) == 0,
        "c0_1_mill_false_positives_zero": int(summary.get("mill_false_positives", 0) or 0) == 0,
        "c0_1_mill_false_negatives_zero_when_observable": int(summary.get("mill_false_negatives", 0) or 0) == 0,
        "c0_2_true_self_snipe_rate_under_5pct": snipe_rate < 0.05,
        "c0_3_lethal_suppression_rate_at_most_1pct": lethal_rate <= 0.01,
    }
    return {
        "schema_version": 2,
        "mode": "smoke" if games <= 20 else "c0_validation",
        "passed": all(criteria.values()),
        "criteria": criteria,
        "observed": {
            "games_requested": games,
            "games_completed": completed,
            "mill_false_positives": int(summary.get("mill_false_positives", 0) or 0),
            "mill_detection_opportunities": int(summary.get("mill_detection_opportunities", 0) or 0),
            "mill_false_negatives": int(summary.get("mill_false_negatives", 0) or 0),
            "mill_not_observable_games": int(summary.get("mill_not_observable_games", 0) or 0),
            "promotion_events": promotion_events,
            "suspected_self_inflicted_snipes": suspected_snipes,
            "true_self_snipes": true_snipes,
            "true_self_snipe_rate": snipe_rate,
            "lethal_opportunities": lethal_opportunities,
            "lethal_suppressions": lethal_suppressions,
            "lethal_suppression_rate": lethal_rate,
            "replay_validation_failures": int(summary.get("replay_validation_failures", 0) or 0),
        },
    }


def run_batch_config(config_path: str) -> dict[str, Any]:
    config_file = Path(config_path).resolve()
    base = config_file.parent
    cfg = read_json(config_file)
    output_dir = Path(_resolve(base, cfg.get("output_dir", "out")) or "out")
    output_dir.mkdir(parents=True, exist_ok=True)

    cg_root = _resolve(base, cfg.get("cg_root"))
    if cg_root and cg_root not in sys.path:
        sys.path.insert(0, cg_root)

    variant = dict(cfg["variant"])
    variant_name = str(variant.get("name", "variant"))
    main_path = _resolve(base, variant["main"])
    deck_path = _resolve(base, variant["deck"])
    opponents = []
    for raw in cfg["opponents"]:
        entry = dict(raw)
        entry["deck"] = _resolve(base, entry["deck"])
        opponents.append(entry)

    games = int(cfg.get("games", 20))
    schedule_seed = int(cfg.get("schedule_seed", 0))
    base_schedule = exact_weighted_schedule(opponents, games, schedule_seed)
    write_json(output_dir / "schedule.json", base_schedule)
    write_json(output_dir / "resolved_config.json", cfg)
    error_policy = str(cfg.get("error_policy", "fallback")).strip().lower()
    if error_policy not in {"fallback", "fail_fast"}:
        raise ValueError("error_policy must be fallback or fail_fast")

    engine = EngineAdapter(str(cfg.get("game_module", "cg.game")))
    agent = LoadedAgent(
        main_path=main_path or "",
        deck_path=deck_path or "",
        cg_root=cg_root,
        watch_globals=list(variant.get("watch_globals", ["_opp_mill_seen"])),
    )
    expected_main_sha = str(variant.get("expected_main_sha256", "") or "").strip().lower()
    expected_deck_sha = str(variant.get("expected_deck_sha256", "") or "").strip().lower()
    if expected_main_sha and agent.main_sha256.lower() != expected_main_sha:
        raise RuntimeError(
            f"Variant {variant_name}: main.py SHA-256 mismatch. "
            f"expected={expected_main_sha} actual={agent.main_sha256} path={agent.main_path}"
        )
    if expected_deck_sha and agent.deck_sha256.lower() != expected_deck_sha:
        raise RuntimeError(
            f"Variant {variant_name}: deck.csv SHA-256 mismatch. "
            f"expected={expected_deck_sha} actual={agent.deck_sha256} path={agent.deck_path}"
        )

    config_fingerprint = canonical_hash({
        "game_module": cfg.get("game_module", "cg.game"),
        "cg_root": cg_root,
        "variant_name": variant_name,
        "main_sha256": agent.main_sha256,
        "deck_sha256": agent.deck_sha256,
        "opponents": opponents,
        "games": games,
        "schedule_seed": schedule_seed,
        "max_decisions": int(cfg.get("max_decisions", 2000)),
        "balance_first_second": bool(cfg.get("balance_first_second", True)),
    })
    write_json(output_dir / "run_manifest.json", {
        "harness_version": "7.0-submit-ready",
        "config_fingerprint": config_fingerprint,
        "variant": variant_name,
        "main_path": str(agent.main_path),
        "deck_path": str(agent.deck_path),
        "main_sha256": agent.main_sha256,
        "deck_sha256": agent.deck_sha256,
        "expected_main_sha256": expected_main_sha or None,
        "expected_deck_sha256": expected_deck_sha or None,
        "identity_verified": (not expected_main_sha or expected_main_sha == agent.main_sha256.lower()) and (not expected_deck_sha or expected_deck_sha == agent.deck_sha256.lower()),
        "games_requested": games,
        "schedule_seed": schedule_seed,
        "balance_first_second": bool(cfg.get("balance_first_second", True)),
        "resume_enabled": bool(cfg.get("resume", True)),
    })

    balance = bool(cfg.get("balance_first_second", True))
    max_multiplier = float(cfg.get("balance_max_attempt_multiplier", 8.0))
    save_replays = bool(cfg.get("save_replays", True))
    max_decisions = int(cfg.get("max_decisions", 2000))

    # Desired counts are derived from the exact weighted schedule.  For an odd
    # matchup count the two buckets may differ by one; v4's default C0 config
    # uses 104 games so all four matchup counts are even.
    desired: dict[str, dict[int, int]] = {}
    by_label: dict[str, dict[str, Any]] = {}
    for item in opponents:
        by_label[str(item["label"])] = item
    for entry in base_schedule:
        label = str(entry["label"])
        desired.setdefault(label, {0: 0, 1: 0})
    for label in desired:
        count = sum(1 for x in base_schedule if str(x["label"]) == label)
        desired[label][1] = count // 2
        desired[label][0] = count - desired[label][1]

    accepted: list[dict[str, Any]] = []
    all_rows: list[dict[str, Any]] = []
    attempts = 0
    max_attempts = max(games, int(round(games * max_multiplier)))
    resume_enabled = bool(cfg.get("resume", True))
    checkpoint_path = output_dir / "progress.json"
    if resume_enabled and checkpoint_path.exists():
        checkpoint = read_json(checkpoint_path)
        old_fingerprint = str(checkpoint.get("config_fingerprint", ""))
        if old_fingerprint != config_fingerprint:
            raise RuntimeError(
                "Existing progress.json belongs to a different configuration. "
                "Delete the output directory or use a new output_dir."
            )
        all_rows = list(checkpoint.get("all_rows", []))
        accepted = [r for r in all_rows if int(r.get("accepted_for_balanced_summary", 0) or 0) == 1]
        attempts = len(all_rows)
        for row in accepted:
            if balance:
                label = str(row.get("opponent"))
                first = int(row.get("target_went_first", -1) or -1)
                if label in desired and first in (0, 1):
                    desired[label][first] = max(0, desired[label][first] - 1)
        print(f"[RESUME] {variant_name}: accepted={len(accepted)}/{games}, attempts={attempts}", flush=True)

    def save_progress(*, completed: bool = False) -> None:
        write_json(checkpoint_path, {
            "schema_version": 1,
            "harness_version": "7.0-submit-ready",
            "config_fingerprint": config_fingerprint,
            "variant": variant_name,
            "games_requested": games,
            "accepted": len(accepted),
            "attempts": attempts,
            "completed": completed,
            "remaining_quotas": desired,
            "all_rows": all_rows,
        })
        write_csv(output_dir / "games.csv", accepted)
        write_csv(output_dir / "games_all_attempts.csv", all_rows)

    def remaining_total() -> int:
        return sum(max(0, n) for buckets in desired.values() for n in buckets.values())

    while len(accepted) < games:
        if not balance:
            opponent = base_schedule[len(accepted)]
        else:
            candidates = [
                label for label, buckets in desired.items()
                if buckets[0] > 0 or buckets[1] > 0
            ]
            if not candidates:
                break
            # Prefer the matchup with the largest unmet quota; stable tie-break
            # keeps A/B schedules reproducible even though cg.game itself is not seeded.
            label = max(candidates, key=lambda x: (desired[x][0] + desired[x][1], x))
            opponent = dict(by_label[label])

        if attempts >= max_attempts:
            raise RuntimeError(
                f"Could not fill first/second quotas: accepted={len(accepted)}/{games}, "
                f"attempts={attempts}/{max_attempts}, remaining={desired}"
            )

        target_seat = attempts % 2
        row = run_game(
            engine=engine,
            variant_name=variant_name,
            agent=agent,
            opponent_cfg=opponent,
            target_seat=target_seat,
            game_index=attempts,
            output_dir=output_dir,
            save_replays=save_replays,
            max_decisions=max_decisions,
            bot_seed=schedule_seed * 1_000_003 + attempts,
            error_policy=error_policy,
        )
        attempts += 1
        row["attempt_index"] = attempts - 1
        row["accepted_for_balanced_summary"] = 0

        accept = True
        if balance:
            first = row.get("target_went_first")
            label = str(row["opponent"])
            accept = first in (0, 1) and desired.get(label, {}).get(int(first), 0) > 0
            if accept:
                desired[label][int(first)] -= 1

        if accept:
            row["accepted_for_balanced_summary"] = 1
            accepted.append(row)

        all_rows.append(row)
        save_progress(completed=False)
        status = "ACCEPT" if accept else "EXTRA"
        print(
            f"[{len(accepted)}/{games}; attempt={attempts}] {status} {variant_name} vs {row['opponent']} "
            f"seat={row['target_seat']} first={row['target_went_first']} winner={row['winner']} "
            f"C0-1={row['c0_1_mill_misdetection_occurred']} "
            f"C0-2={row['c0_2_promotion_violation_count']} "
            f"C0-3={row['c0_3_lethal_suppression_count']} errors={row['error_count']}",
            flush=True,
        )

    write_csv(output_dir / "games.csv", accepted)
    write_csv(output_dir / "games_all_attempts.csv", all_rows)
    write_json(output_dir / "balance_quota_remaining.json", desired)
    summary = summarize_rows(accepted, variant_name)
    summary["harness_version"] = "7.0-submit-ready"
    summary["config_fingerprint"] = config_fingerprint
    summary["attempts_total"] = attempts
    summary["extra_unaccepted_attempts"] = attempts - len(accepted)
    summary["balance_first_second_enabled"] = balance
    summary["main_path"] = str(agent.main_path)
    summary["deck_path"] = str(agent.deck_path)
    summary["main_sha256"] = agent.main_sha256
    summary["deck_sha256"] = agent.deck_sha256
    write_json(output_dir / "summary.json", summary)
    validation = _validation_report(summary, games)
    validation.setdefault("criteria", {})["balanced_sample_completed"] = (
        len(accepted) == games and (not balance or remaining_total() == 0)
    )
    validation["passed"] = all(bool(v) for v in validation.get("criteria", {}).values())
    write_json(output_dir / "validation_report.json", validation)
    write_json(output_dir / "validation_summary.json", validation)
    save_progress(completed=True)
    return {"rows": accepted, "all_rows": all_rows, "summary": summary, "validation": validation, "output_dir": str(output_dir)}

