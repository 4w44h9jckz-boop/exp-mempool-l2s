"""The sealed transaction pool (EIP-8184, LUCID): `docs/spec/06-lucid.md`, LU-4, LU-5 and LU-8 to LU-11.

A third subpool behind the reservation tracker (MD-11). It holds at most one
sealed transaction per sender, at the sender's nonce, and nothing the next
block could not charge. Decision record 0014.

The pool keeps what it holds sorted in LU-6 order at the pending base fee,
which changes only at a new head, and remembers how far LU-7's walk over that
order has been carried. LU-8 asks whether the walk takes one more transaction
at its place, which depends only on what comes before it, so a flood that
ranks first is checked without walking what it outranks, and the walk is
redone only from where the pool last changed.
"""

from __future__ import annotations

import bisect
import itertools
from dataclasses import dataclass
from typing import Callable

from . import errors as E
from .errors import TxError
from .model import Head, State
from .reserver import Reserver
from .sealed import OFF, SealedPoolConfig, SealedTx, fees, is_candidate, order_key, select, takes
from .tx import replaces


@dataclass
class Entry:
    tx: SealedTx
    seq: int


class SealedPool:
    def __init__(self, head: Head, state: State, config: SealedPoolConfig = OFF,
                 reserver: Reserver | None = None, now: float = 0,
                 sequence: Callable[[], int] | None = None):
        self.config = config
        self.head = head
        self.state = state
        self.reserver = reserver or Reserver()
        self.entries: dict[str, Entry] = {}
        self.by_sender: dict[str, str] = {}
        self.log: list[tuple[str, SealedTx, str]] = []
        self._sequence = sequence or itertools.count().__next__
        self._index(head.next_base_fee())

    # --- the pool interface (MD-8, MD-9) -----------------------------------------

    def add(self, txs: list[SealedTx], now: float = 0) -> list[str]:
        results = []
        for tx in txs:
            try:
                self._add_one(tx)
                results.append(E.OK)
            except TxError as err:
                results.append(err.code)
        return results

    def reset(self, head: Head, state: State, now: float = 0) -> None:
        """LU-11."""
        self.head, self.state = head, state
        base_fee = head.next_base_fee()
        room = self.config.tob_gas_limit(head.gas_limit)
        for h, e in list(self.entries.items()):
            tx = e.tx
            if tx.nonce < state.nonce(tx.sender):
                self._remove(h, "included")
            elif state.balance(tx.sender) < tx.cost or fees(tx, base_fee) is None or tx.gas_limit > room:
                self._remove(h, "invalidated")
        self._index(base_fee)
        if self.config.policy == "every-head":
            keep = set(self._walk())
            for h in [h for h in self.entries if h not in keep]:
                self._remove(h, "not includable")

    def tick(self, now: float) -> None:
        pass

    def content(self) -> dict[str, list[SealedTx]]:
        return {s: [self.entries[h].tx] for s, h in self.by_sender.items()}

    def status(self, tx_hash: str) -> str:
        return "pending" if tx_hash in self.entries else "unknown"

    def get(self, tx_hash: str) -> SealedTx | None:
        e = self.entries.get(tx_hash)
        return e.tx if e is not None else None

    def arrival(self, tx_hash: str) -> int:
        return self.entries[tx_hash].seq

    def txs(self) -> list[SealedTx]:
        return [e.tx for e in self.entries.values()]

    def selection(self, base_fee: int, min_tip: int = 0) -> list[SealedTx]:
        """LU-7 over what the pool holds, against its state and the head's gas limit."""
        return select(self.txs(), self.state, base_fee, min_tip, self.head.gas_limit, self.config)

    # --- the order at the pending base fee ------------------------------------------

    def _index(self, base_fee: int) -> None:
        self._base_fee = base_fee
        self._keys = {h: order_key(e.tx, base_fee) for h, e in self.entries.items()}
        self._order = sorted(self._keys.values())
        self._candidate = {h: is_candidate(e.tx, self.state, base_fee, 0) for h, e in self.entries.items()}
        self._after: list[tuple[int, int]] = []  # LU-7's count and gas after each place in the order, so far

    def _walk(self, upto: int | None = None) -> list[str]:
        """Carry LU-7's walk at a minimum tip of 0 to place `upto` (the end by default); the hashes it takes there."""
        end = len(self._order) if upto is None else upto
        after = self._after
        count, gas = after[-1] if after else (0, 0)
        room = self.config.tob_gas_limit(self.head.gas_limit)
        for key in self._order[len(after):end]:
            h = key[-1]
            if self._candidate[h] and takes(count, gas, self.entries[h].tx, room, self.config):
                count, gas = count + 1, gas + self.entries[h].tx.gas_limit
            after.append((count, gas))
        if upto is not None:
            return []
        return [k[-1] for i, k in enumerate(self._order) if after[i] != (after[i - 1] if i else (0, 0))]

    def _takes(self, tx: SealedTx, without: str | None) -> bool:
        """LU-8's test: whether the selection over the pool and `tx`, less `without`, takes `tx`."""
        if not is_candidate(tx, self.state, self._base_fee, 0):
            return False
        place = bisect.bisect_left(self._order, order_key(tx, self._base_fee))
        skip = bisect.bisect_left(self._order, self._keys[without]) if without is not None else place
        if skip >= place:
            self._walk(place)
            count, gas = self._after[place - 1] if place else (0, 0)
        else:  # the one it replaces comes first: walk from there without it
            self._walk(skip)
            count, gas = self._after[skip - 1] if skip else (0, 0)
            room = self.config.tob_gas_limit(self.head.gas_limit)
            for key in self._order[skip + 1:place]:
                h = key[-1]
                if self._candidate[h] and takes(count, gas, self.entries[h].tx, room, self.config):
                    count, gas = count + 1, gas + self.entries[h].tx.gas_limit
        return takes(count, gas, tx, self.config.tob_gas_limit(self.head.gas_limit), self.config)

    def _victim(self, tx: SealedTx) -> tuple[str, bool]:
        """LU-10's victim for `tx`, and whether `tx` is admitted for it."""
        last = self._order[-1]
        before = order_key(tx, self._base_fee) < last
        if self.config.evict_first == "last":
            return last[-1], before
        place = bisect.bisect_left(self._order, order_key(tx, self._base_fee))
        took = self._takes(tx, None)
        self._walk(place)
        count, gas = self._after[place - 1] if place else (0, 0)
        if took:
            count, gas = count + 1, gas + tx.gas_limit
        room = self.config.tob_gas_limit(self.head.gas_limit)
        taken = []  # from `place` on, with `tx` before them
        for key in self._order[place:]:
            h = key[-1]
            t = self._candidate[h] and takes(count, gas, self.entries[h].tx, room, self.config)
            if t:
                count, gas = count + 1, gas + self.entries[h].tx.gas_limit
            taken.append(t)
        for i in range(len(self._order) - 1, -1, -1):
            t = taken[i - place] if i >= place else self._after[i] != (self._after[i - 1] if i else (0, 0))
            if not t:
                key = self._order[i]
                return key[-1], order_key(tx, self._base_fee) < key or took
        return last[-1], before

    # --- admission -------------------------------------------------------------

    def _add_one(self, tx: SealedTx) -> None:
        c = self.config
        if tx.hash in self.entries:  # LU-4
            raise TxError(E.ErrAlreadyKnown)
        if not c.sealed:
            raise TxError(E.ErrTxTypeNotSupported)
        if tx.signature_id != 1:
            raise TxError(E.ErrSTMalformed)
        if not tx.valid_signature:
            raise TxError(E.ErrInvalidSender)
        if not tx.ciphertext_ok:
            raise TxError(E.ErrSTMalformed)
        if tx.size > c.max_bytes_per_st:
            raise TxError(E.ErrOversizedData)
        if tx.gas_limit > c.max_tx_gas:
            raise TxError(E.ErrGasLimitTooHigh)
        if tx.gas_limit < c.calldata_gas_per_byte * tx.size:
            raise TxError(E.ErrFloorDataGas)
        base_fee = self.head.next_base_fee()  # LU-5
        if tx.gas_limit > c.tob_gas_limit(self.head.gas_limit):
            raise TxError(E.ErrSTExceedsToB)
        if self.reserver.held_by_other(tx.sender, self):
            raise TxError(E.ErrAlreadyReserved)
        nonce = self.state.nonce(tx.sender)
        if tx.nonce < nonce:
            raise TxError(E.ErrNonceTooLow)
        if tx.nonce > nonce:
            raise TxError(E.ErrNonceTooHigh)
        if self.state.balance(tx.sender) < tx.cost:
            raise TxError(E.ErrInsufficientFunds)
        if fees(tx, base_fee) is None:
            raise TxError(E.ErrFeeCapTooLow)
        old = self.by_sender.get(tx.sender)
        if old is not None:  # LU-9
            held = self.entries[old].tx
            bumped = (100 + c.price_bump) * held.max_tob_fee // 100
            if not replaces(held, tx, c.price_bump) or tx.max_tob_fee < bumped:
                raise TxError(E.ErrReplaceUnderpriced)
        if c.policy != "any" and not self._takes(tx, old):  # LU-8
            raise TxError(E.ErrSTNotIncludable)
        victim = None
        if old is None and len(self.entries) >= c.st_slots:  # LU-10
            victim, admitted = self._victim(tx)
            if not admitted:
                raise TxError(E.ErrUnderpriced)
        if victim is not None:
            self._remove(victim, "evicted")
        if old is not None:
            self._remove(old, "replaced", release=False)
        elif not self.reserver.hold(tx.sender, self):
            raise TxError(E.ErrAlreadyReserved)
        self.entries[tx.hash] = Entry(tx, self._sequence())
        self.by_sender[tx.sender] = tx.hash
        key = self._keys[tx.hash] = order_key(tx, self._base_fee)
        self._candidate[tx.hash] = is_candidate(tx, self.state, self._base_fee, 0)
        place = bisect.bisect_left(self._order, key)
        self._order.insert(place, key)
        del self._after[place:]
        self.log.append(("pending", tx, "admitted"))

    def _remove(self, tx_hash: str, reason: str, release: bool = True) -> None:
        e = self.entries.pop(tx_hash)
        del self.by_sender[e.tx.sender]
        place = bisect.bisect_left(self._order, self._keys.pop(tx_hash))
        del self._order[place]
        del self._after[place:]
        del self._candidate[tx_hash]
        if release:
            self.reserver.release(e.tx.sender, self)
        self.log.append(("dropped", e.tx, reason))
