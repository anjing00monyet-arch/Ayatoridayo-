from __future__ import annotations

import contextlib
import csv
import hashlib
import json
import math
import os
import random
import time
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence


def read_json(path: str | os.PathLike[str]) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return data


def write_json(path: str | os.PathLike[str], data: Any, *, indent: int | None = 2) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=indent, default=json_default)


def json_default(value: Any) -> Any:
    if hasattr(value, "value"):
        return value.value
    if hasattr(value, "__dict__"):
        return value.__dict__
    return str(value)


def read_deck(path: str | os.PathLike[str]) -> list[int]:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    values: list[int] = []
    for raw in text.replace(",", "\n").splitlines():
        raw = raw.strip()
        if raw:
            values.append(int(raw))
    if len(values) != 60:
        raise ValueError(f"Deck must contain exactly 60 cards, got {len(values)}: {p}")
    return values


def deck_hash(deck: Sequence[int]) -> str:
    payload = ",".join(map(str, sorted(deck))).encode("utf-8")
    return hashlib.sha1(payload).hexdigest()[:12]


def canonical_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, default=json_default).encode("utf-8")
    return hashlib.sha1(payload).hexdigest()


def now_id() -> str:
    return time.strftime("%Y%m%d-%H%M%S") + f"-{time.time_ns() % 1_000_000:06d}"


def exact_weighted_schedule(items: Sequence[dict[str, Any]], total: int, schedule_seed: int = 0) -> list[dict[str, Any]]:
    """Create an exact-size schedule using largest remainder allocation.

    schedule_seed controls only order and seat assignment. It does not seed cg.game.
    """
    if total <= 0:
        return []
    if not items:
        raise ValueError("At least one opponent is required")
    weights = [float(x.get("weight", 1.0)) for x in items]
    if any(w < 0 for w in weights) or sum(weights) <= 0:
        raise ValueError("Opponent weights must be non-negative and sum to > 0")
    scale = total / sum(weights)
    raw = [w * scale for w in weights]
    counts = [int(math.floor(x)) for x in raw]
    left = total - sum(counts)
    order = sorted(range(len(items)), key=lambda i: (raw[i] - counts[i], -i), reverse=True)
    for i in order[:left]:
        counts[i] += 1

    schedule: list[dict[str, Any]] = []
    for item, count in zip(items, counts):
        schedule.extend(dict(item) for _ in range(count))
    rng = random.Random(schedule_seed)
    rng.shuffle(schedule)
    for i, entry in enumerate(schedule):
        entry["target_seat"] = i % 2
        entry["schedule_index"] = i
    return schedule


def wilson_interval(wins: int, n: int, z: float = 1.959963984540054) -> tuple[float, float]:
    if n <= 0:
        return (0.0, 1.0)
    p = wins / n
    den = 1 + z * z / n
    center = (p + z * z / (2 * n)) / den
    half = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n) / den
    return max(0.0, center - half), min(1.0, center + half)


def fisher_exact_one_sided(k_cand: int, n_cand: int, k_base: int, n_base: int) -> float:
    """One-sided Fisher exact p-value for 'candidate event rate > baseline rate'.

    Used for low-count mechanism gates (self-snipes, lethal suppressions) where
    a raw count/rate comparison flags noise like 3/1587 -> 4/1192. Returns the
    probability, under the null of equal rates, of the candidate having at
    least k_cand events given the pooled margins (hypergeometric tail).
    p < 0.05 means the regression is unlikely to be chance.
    """
    if n_cand <= 0 or n_base <= 0:
        return 1.0
    total = n_cand + n_base
    successes = k_cand + k_base
    if successes <= 0:
        return 1.0
    lo = max(0, successes - n_base)
    hi = min(n_cand, successes)
    denom = math.comb(total, successes)
    if denom == 0:
        return 1.0
    tail = sum(
        math.comb(n_cand, k) * math.comb(n_base, successes - k)
        for k in range(max(k_cand, lo), hi + 1)
    )
    return min(1.0, tail / denom)


def difference_interval(w1: int, n1: int, w2: int, n2: int, z: float = 1.959963984540054) -> tuple[float, float, float]:
    if n1 <= 0 or n2 <= 0:
        return 0.0, -1.0, 1.0
    p1, p2 = w1 / n1, w2 / n2
    diff = p1 - p2
    se = math.sqrt(p1 * (1 - p1) / n1 + p2 * (1 - p2) / n2)
    return diff, diff - z * se, diff + z * se


def write_csv(path: str | os.PathLike[str], rows: Sequence[dict[str, Any]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        p.write_text("", encoding="utf-8")
        return
    fields: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                fields.append(key)
    with open(p, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


@contextlib.contextmanager
def pushd(path: str | os.PathLike[str]) -> Iterator[None]:
    old = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(old)
