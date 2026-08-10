"""Game constants shared by analysis tooling, delegated to the installed
`kaggle_environments` package rather than hand-copied, so they can't drift
from the real values. See the Object Types table in the official env README
for the human-readable version:
https://github.com/Kaggle/kaggle-environments (envs/kaggriculture).

`hire_cost` / `land_cost` mirror `_hire_cost` / `_do_buy_land` in
`kaggle_environments.envs.kaggriculture.kaggriculture` (private helpers, so
reimplemented here rather than imported) -- keep in sync if that module's
formulas change.
"""
from __future__ import annotations

try:
    from kaggle_environments.envs.kaggriculture.kaggriculture import ANIMALS, CROPS
except ImportError as e:
    raise ImportError(
        "kaggle-environments is required for Kaggriculture tooling. "
        "Install it with: pip install kaggle-environments"
    ) from e

LAND_COST_SCHEDULE = [1000, 2000, 4000]  # cost to unlock the 2nd, 3rd, 4th quadrant
FARM_HAND_COST_MULT = 1


def _fib(n: int) -> int:
    """_fib(0)=1, _fib(1)=1, _fib(2)=2, _fib(3)=3, _fib(4)=5, ..."""
    a, b = 1, 1
    for _ in range(n):
        a, b = b, a + b
    return a


def hire_cost(n_already_hired_today: int, mult: int = FARM_HAND_COST_MULT) -> int:
    return mult * _fib(n_already_hired_today)


def land_cost(n_unlocked_quadrants_before: int) -> int:
    """Cost to buy the next quadrant, given how many are unlocked already
    (including the starting NW quadrant, so this is `len(unlocked_quadrants)`
    before the purchase).
    """
    idx = n_unlocked_quadrants_before - 1
    if idx < 0 or idx >= len(LAND_COST_SCHEDULE):
        return 0
    return LAND_COST_SCHEDULE[idx]
