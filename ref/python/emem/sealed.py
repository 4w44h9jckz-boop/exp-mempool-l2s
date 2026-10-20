"""Sealed transactions (EIP-8184, LUCID): `docs/spec/06-lucid.md`, LU-1 to LU-3, LU-6 and LU-7.

The object, its ticket's fees, the order of commitments and what a builder
selects. The pool that holds sealed transactions is `sealedpool.py`, and the
block that commits and decrypts them is `block.py`. Decision record 0014.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from functools import cached_property
from typing import Iterable

from .model import State
from .tx import _hash


@dataclass(frozen=True)
class SealedPoolConfig:
    """LU-1."""

    name: str = "off"
    sealed: bool = False
    tob_gas_fraction_denominator: int = 8
    tob_fee_fraction: int = 128
    max_st_commits: int = 32  # MAX_ST_COMMITS_PER_IL * IL_COMMITTEE_SIZE
    max_bytes_per_st: int = 2**24 // 64
    max_tx_gas: int = 2**24  # EIP-7825
    calldata_gas_per_byte: int = 64
    st_slots: int = 4096
    price_bump: int = 10
    policy: str = "any"  # "any", "next-block" or "every-head"
    evict_first: str = "last"  # "last" or "unplaced"

    def with_(self, **changes) -> SealedPoolConfig:
        return replace(self, **changes)

    def tob_gas_limit(self, gas_limit: int) -> int:
        return gas_limit // self.tob_gas_fraction_denominator


OFF = SealedPoolConfig()
EIP_8184 = SealedPoolConfig(name="eip-8184", sealed=True)
SEALED_PROFILES = {c.name: c for c in (OFF, EIP_8184)}
POLICIES = ("any", "next-block", "every-head")
EVICTIONS = ("last", "unplaced")


@dataclass(frozen=True, eq=False)
class SealedTx:
    """LU-2. Defaults match `conformance/README.md`."""

    sender: str
    nonce: int = 0
    max_fee: int = 100
    tip: int = 10
    gas_limit: int = 100_000
    max_tob_fee: int = 0
    max_preceding: int = 31
    key_publisher: str = "kp"
    fee_recipient: str = "kp"
    key_fee: int = 0
    size: int = 512
    signature_id: int = 1
    valid_signature: bool = True
    ciphertext_ok: bool = True
    revealed: bool = True
    used: int | None = None  # dual_gas_used; None for gas_limit
    label: str = ""
    # LU-2 version 2: the plaintext's recipient, pulls and pays (MD-5), and its gas if it reverts (LU-13);
    # absent, the hash is as it was under version 1
    to: str | None = field(default=None, metadata={"omit_none": True})
    pulls: tuple[tuple[str, int], ...] | None = field(default=None, metadata={"omit_none": True})
    pays: tuple[tuple[str, int], ...] | None = field(default=None, metadata={"omit_none": True})
    atomic: bool | None = field(default=None, metadata={"omit_none": True})  # None is true
    revert_used: int | None = field(default=None, metadata={"omit_none": True})

    @cached_property
    def hash(self) -> str:
        return _hash(self)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, SealedTx) and other.hash == self.hash

    def __hash__(self) -> int:
        return hash(self.hash)

    @property
    def encoded_size(self) -> int:
        return self.size

    @property
    def cost(self) -> int:
        """LU-3: the most its ticket can be charged."""
        return self.max_fee * self.gas_limit

    @property
    def dual_gas_used(self) -> int:
        return self.gas_limit if self.used is None else self.used

    @property
    def reverted_used(self) -> int:
        """LU-2: the plaintext's dual_gas_used if its execution reverts."""
        return self.dual_gas_used if self.revert_used is None else self.revert_used

    def name(self) -> str:
        return self.label or self.hash[:10]


@dataclass(frozen=True)
class Fees:
    """LU-3, in wei for the whole ticket."""

    priority: int
    tob: int
    ticket_fee: int


def fees(st: SealedTx, base_fee: int) -> Fees | None:
    """LU-3: the ticket's fees at `base_fee`, or None if it cannot pay."""
    g = st.gas_limit
    left = st.max_fee * g - base_fee * g - st.key_fee
    if left < 0:
        return None
    priority = min(st.tip * g, left)
    tob = min(st.max_tob_fee, left - priority)
    return Fees(priority, tob, base_fee * g + st.key_fee + priority + tob)


def order_key(st: SealedTx, base_fee: int) -> tuple:
    """LU-6, for one that can pay: smaller comes first."""
    f = fees(st, base_fee)
    return (-(f.tob if f is not None else -1), -st.gas_limit, st.hash)


def is_candidate(st: SealedTx, state: State, base_fee: int, min_tip: int) -> bool:
    """LU-7, step 1."""
    f = fees(st, base_fee)
    return (f is not None and st.nonce == state.nonce(st.sender) and state.balance(st.sender) >= f.ticket_fee
            and f.priority >= min_tip * st.gas_limit)


def takes(count: int, gas: int, st: SealedTx, room: int, cfg: SealedPoolConfig) -> bool:
    """LU-7, step 2: whether a candidate is selected when `count` with `gas` in all are selected before it."""
    return count < cfg.max_st_commits and gas + st.gas_limit <= room and count <= st.max_preceding


def select(sts: Iterable[SealedTx], state: State, base_fee: int, min_tip: int, gas_limit: int,
           cfg: SealedPoolConfig) -> list[SealedTx]:
    """LU-7: the selection, in commitment order."""
    candidates = sorted((st for st in sts if is_candidate(st, state, base_fee, min_tip)),
                        key=lambda st: order_key(st, base_fee))
    room = cfg.tob_gas_limit(gas_limit)
    selected: list[SealedTx] = []
    gas = 0
    for st in candidates:
        if takes(len(selected), gas, st, room, cfg):
            selected.append(st)
            gas += st.gas_limit
    return selected
