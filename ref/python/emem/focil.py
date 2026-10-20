"""Inclusion lists: `docs/spec/07-focil.md`, EIP-7805 with EIP-8369's eligibility profiles.

An includer builds a list from its pool (IL-2); a block satisfies the slot's
lists unless one of them names a transaction it left out that was valid at
the end of its payload and fitted the gas it left (IL-6); a builder appends
what it must (IL-7, in `block.build_block`).
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass, replace
from functools import lru_cache
from typing import Callable, Iterable

from .errors import TxError
from .framepool.config import FramePoolConfig
from .framepool.prefix import _check_static, analyse, simulate
from .model import Head, State
from .tx import AnyTx, FrameTx


@dataclass(frozen=True)
class FocilConfig:
    """IL-1."""

    name: str = "off"
    enabled: bool = False
    committee_size: int = 16  # IL_COMMITTEE_SIZE
    max_bytes: int = 8192  # MAX_BYTES_PER_INCLUSION_LIST
    frames: bool = False  # EIP-8369's Profile 2
    max_verify_gas_per_il: int = 1 << 20  # MAX_VERIFY_GAS_PER_IL
    max_verify_gas_per_tx: int = 1 << 20  # MAX_VERIFY_GAS_PER_TX; Interpretation, decision record 0018
    policy: str = "fee"  # Interpretation, decision record 0018; or "age"
    fill: str = "per-list"  # IL-4: a budget for each IL, or "per-payload", one over the delivered array

    def with_(self, **changes) -> "FocilConfig":
        return replace(self, **changes)


OFF = FocilConfig()
EIP_7805 = FocilConfig("eip-7805", enabled=True)
EIP_8369 = FocilConfig("eip-8369", enabled=True, frames=True)
ETHREX = FocilConfig("ethrex", enabled=True, frames=True, fill="per-payload")  # ethrex at 64b8fc09
FOCIL_PROFILES = {p.name: p for p in (OFF, EIP_7805, EIP_8369, ETHREX)}


def costs(tx: FrameTx, frame_cfg: FramePoolConfig) -> tuple[int, int]:
    """IL-3 and IL-4: a frame transaction's signature cost and its prefix's declared gas, or the whole
    transaction's when it has no prefix (IL-3 then refuses it)."""
    signatures = sum(s.verify_gas for s in tx.signatures)
    prefix = analyse(tx, frame_cfg)
    frames = prefix.frames if prefix is not None else tx.frames
    return signatures, sum(f.exec_gas for f in frames)


@lru_cache(maxsize=64)
def _candidate_config(frame_cfg: FramePoolConfig, per_tx: int) -> FramePoolConfig:
    """FP-3 to FP-6 with IL-3's bound in place of the pool's, and no pool policy."""
    return frame_cfg.with_(max_verify_gas=per_tx, max_verify_state_gas=None, price_limit=0)


def candidate(tx: FrameTx, head: Head, frame_cfg: FramePoolConfig, config: FocilConfig) -> bool:
    """IL-3: a Profile 2 candidate, from the transaction alone."""
    cfg = _candidate_config(frame_cfg, config.max_verify_gas_per_tx)
    return not isinstance(_check_static(tx, head.gas_limit, cfg), str)


def build_il(pool, base_fee: int, config: FocilConfig, head: Head | None = None,
             leave_out: Callable[[AnyTx], bool] | None = None) -> tuple[AnyTx, ...]:
    """IL-2: what an includer holding `pool` lists for a block at `base_fee`. `leave_out` is an
    includer's own choice not to list a transaction, which no clause makes; the simulator uses it."""
    head = head or pool.head
    chains: list[list[AnyTx]] = [list(txs) for _, txs in sorted(pool.nonce.pending_view(0, base_fee).items())]
    if config.frames:
        chains += [[tx] for tx in pool.frame.pending_view(0, base_fee)]

    def key(tx: AnyTx) -> tuple:
        arrival = pool.arrival(tx)
        if config.policy == "age":
            return (arrival,)
        return (-tx.effective_tip(base_fee), arrival)

    heap = [(key(chain[0]), i, 0) for i, chain in enumerate(chains)]
    heapq.heapify(heap)
    listed: list[AnyTx] = []
    size, budget = 0, config.max_verify_gas_per_il
    while heap:
        _, i, j = heapq.heappop(heap)
        tx = chains[i][j]
        if leave_out is not None and leave_out(tx):
            continue
        if size + tx.encoded_size > config.max_bytes:
            continue
        if isinstance(tx, FrameTx):
            if not candidate(tx, head, pool.frame.config, config):
                continue
            cost = sum(costs(tx, pool.frame.config))
            if cost > budget:
                continue
            budget -= cost
        listed.append(tx)
        size += tx.encoded_size
        if j + 1 < len(chains[i]):
            heapq.heappush(heap, (key(chains[i][j + 1]), i, j + 1))
    return tuple(listed)


def delivered_order(ils: Iterable[tuple[AnyTx, ...]], config: FocilConfig,
                    delivered: Iterable[AnyTx] | None = None) -> list[AnyTx]:
    """IL-4 and IL-6: the order the ILs are read in. Under `per-payload` it is the order delivered,
    which no text fixes, or else the ILs in committee order with each transaction once."""
    if config.fill == "per-payload" and delivered is not None:
        return list(delivered)
    return listed(ils)


def admitted(ils: Iterable[tuple[AnyTx, ...]], head: Head, frame_cfg: FramePoolConfig,
             config: FocilConfig, delivered: Iterable[AnyTx] | None = None) -> list[str]:
    """IL-4: the frame transactions the budget fill admitted, each once, in the order first admitted:
    by at least one IL's fill under `per-list`, by the one fill over the delivered array under
    `per-payload`."""
    ils = tuple(ils)
    runs = [delivered_order(ils, config, delivered)] if config.fill == "per-payload" else ils
    out: list[str] = []
    for run in runs:
        left = config.max_verify_gas_per_il
        for tx in run:
            if not isinstance(tx, FrameTx):
                continue
            signatures, prefix = costs(tx, frame_cfg)
            if signatures + prefix > config.max_verify_gas_per_tx or signatures + prefix > left:
                continue
            left -= signatures
            if any(not s.valid for s in tx.signatures):
                continue
            left -= prefix
            if candidate(tx, head, frame_cfg, config) and tx.hash not in out:
                out.append(tx.hash)
    return out


def fee_valid(tx: AnyTx, base_fee: int) -> bool:
    return tx.max_fee >= base_fee and tx.tip <= tx.max_fee


def valid_at_end(tx: AnyTx, state: State, block: Head, frame_cfg: FramePoolConfig, config: FocilConfig,
                 enforceable: set[str], verdicts: dict[str, bool] | None = None) -> bool:
    """IL-5, against the state after the block's last transaction, or, for a frame transaction, a
    client's verdict on it there when `verdicts` is given (IL-5's last reading)."""
    if verdicts is not None and isinstance(tx, FrameTx):
        return config.frames and tx.hash in enforceable and verdicts.get(tx.hash, False)
    if not fee_valid(tx, block.base_fee):
        return False
    if isinstance(tx, FrameTx):
        if not config.frames or tx.hash not in enforceable:
            return False
        prefix = analyse(tx, frame_cfg)
        if prefix is None:
            return False
        try:
            simulate(tx, prefix, block, state, frame_cfg)
        except TxError:
            return False
        return True
    return state.nonce(tx.sender) == tx.nonce and state.balance(tx.sender) >= tx.cost


def listed(ils: Iterable[tuple[AnyTx, ...]]) -> list[AnyTx]:
    """IL-6: every listed transaction once, in the order given."""
    seen: set[str] = set()
    out = []
    for il in ils:
        for tx in il:
            if tx.hash not in seen:
                seen.add(tx.hash)
                out.append(tx)
    return out


def omission(txs: Iterable[AnyTx], state: State, block: Head, gas_left, ils: tuple[tuple[AnyTx, ...], ...],
             frame_cfg: FramePoolConfig, config: FocilConfig, delivered: Iterable[AnyTx] | None = None,
             verdicts: dict[str, bool] | None = None) -> AnyTx | None:
    """IL-6: the listed transaction a block left out without excuse, or None if it satisfies its ILs.
    `gas_left` is the gas the block left, or the block's `GasPool`, whose fit BB-6 reads it as."""
    if not config.enabled:
        return None
    fits = gas_left.fits if hasattr(gas_left, "fits") else (lambda tx: tx.gas_limit <= gas_left)
    present = {tx.hash for tx in txs}
    order = delivered_order(ils, config, delivered)
    enforceable = set(admitted(ils, block, frame_cfg, config, order)) if config.frames else set()
    for tx in order:
        if tx.hash in present or not fits(tx):
            continue
        if valid_at_end(tx, state, block, frame_cfg, config, enforceable, verdicts):
            return tx
    return None


def canonical(block, post: State, ils: tuple[tuple[AnyTx, ...], ...], frame_cfg: FramePoolConfig,
              config: FocilConfig) -> bool:
    """IL-8: a block is canonical only if it satisfies the slot's ILs."""
    gas_left = block.gas if block.gas is not None else block.head.gas_limit - block.head.gas_used
    return omission(block.txs, post, block.head, gas_left, ils, frame_cfg, config) is None
