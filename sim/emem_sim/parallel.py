"""Running independent simulations at once, with their results in the order they were asked for.

A run's randomness comes from its own scenario and seed, and nothing in
`emem` or `emem_sim` keeps state between runs, so a run gives the same result
whichever process runs it and whatever runs beside it. `EMEM_JOBS` sets how
many processes run at once; it defaults to the number of processors, and 1
runs everything in this process. Decision record 0018.
"""

from __future__ import annotations

import os
from concurrent.futures import ProcessPoolExecutor
from typing import Callable, Iterable, TypeVar

A = TypeVar("A")
R = TypeVar("R")


def jobs() -> int:
    return max(1, int(os.environ.get("EMEM_JOBS") or os.cpu_count() or 1))


def run_all(fn: Callable[[A], R], args: Iterable[A]) -> list[R]:
    """`[fn(a) for a in args]`, in as many processes as `jobs()`. `fn` must be a module's own function."""
    args = list(args)
    n = min(jobs(), len(args))
    if n <= 1:
        return [fn(a) for a in args]
    with ProcessPoolExecutor(n) as pool:
        return list(pool.map(fn, args))
