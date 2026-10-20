"""EIP-8288 dependency frames: `docs/spec/05-aggregation.md`, AG-2, AG-4, AG-5's union and AG-8.

Static rules over a transaction, kept apart from `aggregation.py` so that the
frame pool's static checks can use them without importing the pool.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Iterable

from . import errors as E
from .errors import TxError
from .tx import LEANSPHINCS, LEANSTARK, Dependency, Frame, FrameTx

if TYPE_CHECKING:
    from .framepool.config import FramePoolConfig

VERIFICATION_GAS = {LEANSPHINCS: 3000, LEANSTARK: 30000}  # LEANSPHINCS_ / LEANSTARK_VERIFICATION_GAS
RECURSIVE_STARK_GAS = 30000  # AG-8, per declared triple
TRIPLE_BYTES = 96
ZERO_HASH = "0x" + "00" * 32


def check_frame(frame: Frame, cfg: FramePoolConfig) -> None:
    """AG-2, in place of FP-3's constraints on one frame; the frame before it is checked by the caller."""
    k = len(frame.deps)
    schemes = VERIFICATION_GAS if cfg.leanstark == "defined" else {LEANSPHINCS: VERIFICATION_GAS[LEANSPHINCS]}
    if not 1 <= k <= cfg.max_dependencies_per_frame or any(d.scheme not in schemes for d in frame.deps):
        raise TxError(E.ErrDepFrameMalformed)
    if frame.data_size != TRIPLE_BYTES * k or frame.target is not None or frame.value or frame.flags:
        raise TxError(E.ErrDepFrameMalformed)
    if frame.exec_gas != sum(VERIFICATION_GAS[d.scheme] for d in frame.deps) or frame.state_gas:
        raise TxError(E.ErrDepFrameMalformed)


def counts(deps: Iterable[Dependency]) -> tuple[int, int]:
    """How many leanSPHINCS and how many leanSTARK triples."""
    deps = list(deps)
    return sum(1 for d in deps if d.scheme == LEANSPHINCS), sum(1 for d in deps if d.scheme == LEANSTARK)


def dependencies(tx: FrameTx, cfg: FramePoolConfig | None = None) -> tuple[Dependency, ...]:
    """AG-4: the sorted, deduplicated triples of the transaction's dependency frames. Under `zero_data_hash`
    `sig_hash` a zero data_hash holds the transaction's signature hash, for which the model has MD-7's hash of the
    transaction (decision record 0063)."""
    if cfg is None or cfg.zero_data_hash != "sig_hash":
        return tx.dependencies
    return tuple(sorted({Dependency(d.scheme, tx.hash, d.vk_hash) if d.data_hash == ZERO_HASH else d
                         for d in tx.dependencies}))


def check_limits(tx: FrameTx, cfg: FramePoolConfig) -> None:
    """AG-4, over the sorted, deduplicated list."""
    sigs, starks = counts(dependencies(tx, cfg))
    if sigs > cfg.max_sigs_per_tx or starks > cfg.max_starks_per_tx:
        raise TxError(E.ErrFrameTooManyDeps)


def union(txs: Iterable[FrameTx], cfg: FramePoolConfig | None = None) -> tuple[Dependency, ...]:
    """AG-5: the sorted, deduplicated union of the transactions' dependencies."""
    return tuple(sorted({d for tx in txs for d in dependencies(tx, cfg)}))


def block_gas(tx: FrameTx) -> int:
    """AG-8: what a transaction's declarations add to its block's gas."""
    return RECURSIVE_STARK_GAS * tx.declared
