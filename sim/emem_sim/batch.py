"""What a node pays to verify proofs under one key, one at a time or in a batch (decision record 0025).

The costs are Commonware's single-threaded measurement of Pari proofs on an M5
MacBook Pro, in its blog post `/blogs/batch-pari`, read on 2026-09-15:
verifying N proofs one at a time and as one batch, in milliseconds. Between two
measured sizes the batch cost is interpolated on a log-log line; a batch of one
costs one individual verification. Nothing here verifies anything: a proof is a
flag.
"""

from __future__ import annotations

import math

# N: (individual, batch), milliseconds.
MEASURED = {
    2: (1.361, 0.882),
    32: (19.123, 2.007),
    512: (303.118, 9.934),
    8192: (4834.206, 100.030),
    65536: (38307.696, 644.543),
}
SIZES = sorted(MEASURED)
SINGLE_MS = MEASURED[SIZES[-1]][0] / SIZES[-1]  # one proof verified alone, at the largest run's rate


def batch_ms(n: int) -> float:
    """Milliseconds to verify `n` proofs under one key as one batch."""
    if n <= 0:
        return 0.0
    if n == 1:
        return SINGLE_MS
    if n <= SIZES[0]:
        lo, hi = 1, SIZES[0]
        a, b = SINGLE_MS, MEASURED[hi][1]
    elif n >= SIZES[-1]:
        lo, hi = SIZES[-2], SIZES[-1]
        a, b = MEASURED[lo][1], MEASURED[hi][1]
    else:
        hi = next(s for s in SIZES if s >= n)
        lo = SIZES[SIZES.index(hi) - 1]
        a, b = MEASURED[lo][1], MEASURED[hi][1]
    if n == hi:
        return b
    t = (math.log(n) - math.log(lo)) / (math.log(hi) - math.log(lo))
    return math.exp(math.log(a) + t * (math.log(b) - math.log(a)))


def verify(valid: list[bool]) -> tuple[float, int]:
    """Verify a batch whose proofs are `valid`, bisecting on failure: (milliseconds, checks run).

    A batch that holds an invalid proof fails as a whole, and is split in two
    halves that are checked in turn, down to single proofs; this is the
    bisection Commonware describes for a failed multi-signature.
    """
    n = len(valid)
    if n == 0:
        return 0.0, 0
    cost, checks = batch_ms(n), 1
    if n == 1 or all(valid):
        return cost, checks
    half = n // 2
    for part in (valid[:half], valid[half:]):
        c, k = verify(part)
        cost += c
        checks += k
    return cost, checks
