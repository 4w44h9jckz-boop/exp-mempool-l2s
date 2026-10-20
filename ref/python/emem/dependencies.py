"""EIP-8288 dependency frames: `docs/spec/05-aggregation.md`, AG-2, AG-4 and AG-8.

Static rules over a transaction, kept apart from `aggregation.py` so that the
frame pool's static checks can use them without importing the pool.
"""

from __future__ import annotations

from typing import Iterable

from . import errors as E
from .errors import TxError
from .tx import LEANSPHINCS, LEANSTARK, Dependency, Frame, FrameTx

VERIFICATION_GAS = {LEANSPHINCS: 3000, LEANSTARK: 30000}  # LEANSPHINCS_ / LEANSTARK_VERIFICATION_GAS
RECURSIVE_STARK_GAS = 30000  # AG-8, per declared triple
TRIPLE_BYTES = 96


def check_frame(frame: Frame, max_dependencies: int) -> None:
    """AG-2, in place of FP-3's constraints on one frame."""
    k = len(frame.deps)
    if not 1 <= k <= max_dependencies or any(d.scheme not in VERIFICATION_GAS for d in frame.deps):
        raise TxError(E.ErrDepFrameMalformed)
    if frame.data_size != TRIPLE_BYTES * k or frame.target is not None or frame.value or frame.flags:
        raise TxError(E.ErrDepFrameMalformed)
    if frame.exec_gas != sum(VERIFICATION_GAS[d.scheme] for d in frame.deps) or frame.state_gas:
        raise TxError(E.ErrDepFrameMalformed)


def counts(deps: Iterable[Dependency]) -> tuple[int, int]:
    """How many leanSPHINCS and how many leanSTARK triples."""
    deps = list(deps)
    return sum(1 for d in deps if d.scheme == LEANSPHINCS), sum(1 for d in deps if d.scheme == LEANSTARK)


def check_limits(tx: FrameTx, max_sigs: int, max_starks: int) -> None:
    """AG-4, over the sorted, deduplicated list."""
    sigs, starks = counts(tx.dependencies)
    if sigs > max_sigs or starks > max_starks:
        raise TxError(E.ErrFrameTooManyDeps)


def union(txs: Iterable[FrameTx]) -> tuple[Dependency, ...]:
    """AG-5: the sorted, deduplicated union of the transactions' dependencies."""
    return tuple(sorted({d for tx in txs for d in tx.dependencies}))


def block_gas(tx: FrameTx) -> int:
    """AG-8: what a transaction's declarations add to its block's gas."""
    return RECURSIVE_STARK_GAS * tx.declared
