"""The account-nonce pool: `docs/spec/01-nonce-pool.md`.

A transcription of go-ethereum's `legacypool` at commit 93d78a01, written for a
reader rather than for speed. Method names follow the Go functions they mirror,
and each carries the clause it implements.
"""

from __future__ import annotations

import itertools
from typing import Callable

from .. import errors as E
from ..errors import TxError
from ..model import Head, State
from ..reserver import Reserver
from ..tx import SET_CODE, Tx, authority_addresses, floor_data_gas, intrinsic_gas
from .config import GETH, NoncePoolConfig
from .priced import PricedList
from .txlist import NonceList

ACCEPTED_TYPES = (0, 1, 2, SET_CODE)


class NoncePool:
    def __init__(self, head: Head, state: State, config: NoncePoolConfig = GETH,
                 reserver: Reserver | None = None, now: float = 0,
                 sequence: Callable[[], int] | None = None):
        self.config = config
        self.head = head
        self.state = state
        self.reserver = reserver or Reserver()
        self.pending: dict[str, NonceList] = {}
        self.queue: dict[str, NonceList] = {}
        self.beats: dict[str, float] = {}
        self.all: dict[str, Tx] = {}
        self.slots = 0
        self.auths: dict[str, set[str]] = {}
        self.pending_nonces: dict[str, int] = {}
        self.changes_since_reorg = 0
        self.arrival: dict[str, int] = {}
        self._sequence = sequence or itertools.count().__next__
        self._last_eviction = now
        self._now = now
        # (kind, tx, detail), for experiments to read and clear: "pending" when a
        # transaction becomes executable (go-ethereum announces these to peers), and
        # "dropped" with a reason. Not part of the specification.
        self.log: list[tuple[str, Tx, str]] = []
        self.priced = PricedList(lambda h: h in self.all, lambda: list(self.all.values()),
                                 lambda tx: self.arrival.get(tx.hash, 0), self.num_slots)
        self.priced.set_base_fee(head.next_base_fee())

    # --- bookkeeping ----------------------------------------------------------

    def num_slots(self, tx: Tx) -> int:
        return -(-tx.encoded_size // self.config.slot_size)

    def _all_add(self, tx: Tx) -> None:
        self.all[tx.hash] = tx
        self.slots += self.num_slots(tx)
        for auth in authority_addresses(tx):
            self.auths.setdefault(auth, set()).add(tx.hash)

    def _all_remove(self, tx: Tx) -> None:
        if self.all.pop(tx.hash, None) is None:
            return
        self.arrival.pop(tx.hash, None)
        self.slots -= self.num_slots(tx)
        for auth in authority_addresses(tx):
            hashes = self.auths.get(auth)
            if hashes is not None:
                hashes.discard(tx.hash)
                if not hashes:
                    del self.auths[auth]

    def _dropped(self, tx: Tx, reason: str) -> None:
        self.log.append(("dropped", tx, reason))

    def _pending_nonce(self, addr: str) -> int:
        """NP-15."""
        return self.pending_nonces.get(addr, self.state.nonce(addr))

    def _set_if_lower(self, addr: str, nonce: int) -> None:
        if self._pending_nonce(addr) > nonce:
            self.pending_nonces[addr] = nonce

    def _bump(self, addr: str) -> None:
        """NP-18: refresh a heartbeat only if the sender has one."""
        if addr in self.beats:
            self.beats[addr] = self._now

    def _release_if_empty(self, addr: str) -> None:
        if addr not in self.pending and addr not in self.queue:
            self.reserver.release(addr, self)

    # --- the pool interface (MD-8) --------------------------------------------

    def add(self, txs: list[Tx], now: float = 0) -> list[str]:
        """NP-2, go-ethereum `Add` with sync set."""
        self._run_evictions(now)
        results: list[str | None] = [None] * len(txs)
        for i, tx in enumerate(txs):
            if tx.hash in self.all:
                results[i] = E.ErrAlreadyKnown
                continue
            err = self.validate_basics(tx)
            if err is not None:
                results[i] = err
        if all(r is not None for r in results):
            return results  # type: ignore[return-value]
        dirty: list[str] = []
        for i, tx in enumerate(txs):
            if results[i] is not None:
                continue
            try:
                replaced = self._add(tx)
            except TxError as err:
                results[i] = err.code
                continue
            results[i] = E.OK
            if not replaced and tx.sender not in dirty:
                dirty.append(tx.sender)
        self._run_reorg(dirty, reset=False)
        return results  # type: ignore[return-value]

    def reset(self, head: Head, state: State, now: float = 0) -> None:
        """NP-19."""
        self._run_evictions(now)
        self.head = head
        self.state = state
        self.pending_nonces = {}
        self._run_reorg(list(self.queue), reset=True)

    def tick(self, now: float) -> None:
        """NP-18."""
        self._run_evictions(now)

    def content(self) -> tuple[dict[str, list[Tx]], dict[str, list[Tx]]]:
        pending = {a: l.flatten() for a, l in self.pending.items() if not l.empty()}
        queued = {a: l.flatten() for a, l in self.queue.items() if not l.empty()}
        return pending, queued

    def status(self, tx_hash: str) -> str:
        tx = self.all.get(tx_hash)
        if tx is None:
            return "unknown"
        plist = self.pending.get(tx.sender)
        if plist is not None and plist.get(tx.nonce) is tx:
            return "pending"
        return "queued"

    def pending_view(self, min_tip: int, base_fee: int) -> dict[str, list[Tx]]:
        """NP-20, go-ethereum `Pending` with `MinTip` and `BaseFee`."""
        view = {}
        for addr, plist in self.pending.items():
            txs = []
            for tx in plist.flatten():
                if tx.effective_tip(base_fee) < min_tip:
                    break
                txs.append(tx)
            if txs:
                view[addr] = txs
        return view

    # --- admission ------------------------------------------------------------

    def validate_basics(self, tx: Tx) -> str | None:
        """NP-3, go-ethereum `ValidateTransaction`. Returns the first failure."""
        c = self.config
        if getattr(tx, "type", None) not in ACCEPTED_TYPES:
            return E.ErrTxTypeNotSupported
        if tx.encoded_size > c.max_size:
            return E.ErrOversizedData
        if tx.to is None and tx.data_size > c.max_initcode_size:
            return E.ErrMaxInitCodeSizeExceeded
        if c.max_tx_gas is not None and tx.gas > c.max_tx_gas:
            return E.ErrGasLimitTooHigh
        if tx.value < 0:
            return E.ErrNegativeValue
        if tx.gas > self.head.gas_limit:
            return E.ErrGasLimit
        if tx.max_fee < tx.tip:
            return E.ErrTipAboveFeeCap
        if not tx.valid_signature:
            return E.ErrInvalidSender
        if tx.nonce + 1 >= 2**64:
            return E.ErrNonceMax
        if tx.gas < intrinsic_gas(tx):
            return E.ErrIntrinsicGas
        if tx.gas < floor_data_gas(tx, c.floor_cost_per_token):
            return E.ErrFloorDataGas
        if tx.tip < c.price_limit:
            return E.ErrTxGasPriceTooLow
        if tx.type == SET_CODE and not tx.authorities:
            return E.ErrEmptyAuthList
        return None

    def _validate_tx(self, tx: Tx) -> None:
        """NP-4 to NP-7, go-ethereum `validateTx` and `validateAuth`."""
        sender = tx.sender
        if self.state.nonce(sender) > tx.nonce:
            raise TxError(E.ErrNonceTooLow)
        balance = self.state.balance(sender)
        if balance < tx.cost:
            raise TxError(E.ErrInsufficientFunds)
        plist = self.pending.get(sender)
        spent = plist.total_cost if plist is not None else 0
        prev = plist.get(tx.nonce) if plist is not None else None
        need = spent + tx.cost - (prev.cost if prev is not None else 0)
        if balance < need:
            raise TxError(E.ErrInsufficientFunds)
        # NP-6, checkDelegationLimit
        if self.state.code(sender) != "" or sender in self.auths:
            if plist is None:
                if self._pending_nonce(sender) != tx.nonce:
                    raise TxError(E.ErrOutOfOrderTxFromDelegated)
            elif not plist.contains(tx.nonce):
                raise TxError(E.ErrInflightTxLimitReached)
        # NP-7
        for auth in authority_addresses(tx):
            count = len(self.pending.get(auth, ())) + len(self.queue.get(auth, ()))
            if count > 1 or self.reserver.held_by_other(auth, self):
                raise TxError(E.ErrAuthorityReserved)

    def _add(self, tx: Tx) -> bool:
        """go-ethereum `add`. Returns whether it replaced a transaction."""
        if tx.hash in self.all:
            raise TxError(E.ErrAlreadyKnown)
        self._validate_tx(tx)
        sender = tx.sender
        took = False
        if sender not in self.pending and sender not in self.queue:  # NP-8
            if not self.reserver.hold(sender, self):
                raise TxError(E.ErrAlreadyReserved)
            took = True
        try:
            self._make_room(tx)
            self.arrival[tx.hash] = self._sequence()
            plist = self.pending.get(sender)
            if plist is not None and plist.contains(tx.nonce):  # NP-11
                inserted, old = plist.add(tx, self.config.price_bump)
                if not inserted:
                    raise TxError(E.ErrReplaceUnderpriced)
                if old is not None:
                    self._all_remove(old)
                    self.priced.removed(1)
                    self._dropped(old, "replaced")
                self._all_add(tx)
                self.priced.put(tx)
                self._bump(sender)
                self.log.append(("pending", tx, "replacement"))
                return old is not None
            return self._enqueue(tx, add_all=True)  # NP-12
        except TxError:
            self.arrival.pop(tx.hash, None)
            if took:
                self._release_if_empty(sender)
            raise

    def _make_room(self, tx: Tx) -> None:
        """NP-9."""
        c = self.config
        capacity = c.global_slots + c.global_queue
        if self.slots + self.num_slots(tx) <= capacity:
            return
        if self.priced.underpriced(tx):
            raise TxError(E.ErrUnderpriced)
        if self.changes_since_reorg > c.global_slots // 4:
            raise TxError(E.ErrTxPoolOverflow)
        drop, ok = self.priced.discard(self.slots - capacity + self.num_slots(tx))
        if not ok:
            raise TxError(E.ErrTxPoolOverflow)
        if self._is_gapped(tx.sender, tx):
            if any((p := self.pending.get(d.sender)) is not None and p.contains(d.nonce) for d in drop):
                for d in drop:
                    self.priced.put(d)
                raise TxError(E.ErrFutureReplacePending)
        for d in drop:
            self._dropped(d, "underpriced")
            self.changes_since_reorg += self._remove_tx(d, outofbound=False, unreserve=d.sender != tx.sender)

    def _is_gapped(self, sender: str, tx: Tx) -> bool:
        nxt = self._pending_nonce(sender)
        if tx.nonce <= nxt:
            return False
        q = self.queue.get(sender)
        if q is None:
            return True
        return any(not q.contains(n) for n in range(nxt, tx.nonce))

    def _enqueue(self, tx: Tx, add_all: bool) -> bool:
        """go-ethereum `enqueueTx` and `queue.add`."""
        sender = tx.sender
        q = self.queue.get(sender)
        if q is None:
            q = self.queue[sender] = NonceList(strict=False)
        inserted, old = q.add(tx, self.config.price_bump)
        if not inserted:
            if q.empty():
                del self.queue[sender]
            raise TxError(E.ErrReplaceUnderpriced)
        if sender not in self.beats:
            self.beats[sender] = self._now
        if old is not None:
            self._dropped(old, "replaced")
            self._remove_tx(old, outofbound=True, unreserve=True)
        if add_all:
            self._all_add(tx)
            self.priced.put(tx)
        return old is not None

    def _queue_remove(self, addr: str, tx: Tx) -> None:
        q = self.queue.get(addr)
        if q is None:
            return
        held = q.get(tx.nonce)
        if held is not None and held.hash != tx.hash:
            return
        q.remove(tx)
        if q.empty():
            del self.queue[addr]
            self.beats.pop(addr, None)

    def _remove_tx(self, tx: Tx, outofbound: bool, unreserve: bool) -> int:
        """NP-17, go-ethereum `removeTx`. Returns the pending transactions it removed or demoted."""
        if tx.hash not in self.all:
            return 0
        addr = tx.sender
        self._all_remove(tx)
        if outofbound:
            self.priced.removed(1)
        try:
            plist = self.pending.get(addr)
            if plist is not None:
                removed, invalids = plist.remove(tx)
                if removed:
                    if plist.empty():
                        del self.pending[addr]
                    for inv in invalids:
                        self._demote(inv)
                    self._set_if_lower(addr, tx.nonce)
                    return 1 + len(invalids)
            self._queue_remove(addr, tx)
            return 0
        finally:
            if unreserve:
                self._release_if_empty(addr)

    def _demote(self, tx: Tx) -> None:
        """Move a transaction from pending to the queue without touching the lookup."""
        try:
            self._enqueue(tx, add_all=False)
        except TxError:
            # go-ethereum ignores this error and leaks the transaction in its lookup;
            # the model drops it instead. It needs a queued transaction at a nonce
            # that is also pending, which the other rules prevent.
            self._all_remove(tx)
            self._dropped(tx, "lost")

    # --- promotion, demotion and truncation ------------------------------------

    def _run_reorg(self, addrs: list[str], reset: bool) -> None:
        """go-ethereum `runReorg`, NP-14, NP-16 and NP-19."""
        self._promote_executables(addrs)
        if reset:
            self._demote_unexecutables()
            self.priced.set_base_fee(self.head.next_base_fee())
            self.pending_nonces = {a: l.last().nonce + 1 for a, l in self.pending.items() if not l.empty()}
        self._truncate_pending()
        self._truncate_queue()
        self.changes_since_reorg = 0

    def _promote_executables(self, addrs: list[str]) -> list[Tx]:
        """NP-14, go-ethereum `promoteExecutables` and `queue.promoteExecutables`."""
        gas_limit = self.head.gas_limit
        promotable: list[Tx] = []
        dropped: list[Tx] = []
        emptied: list[str] = []
        for addr in addrs:
            q = self.queue.get(addr)
            if q is None:
                continue
            for tx in q.forward(self.state.nonce(addr)):
                dropped.append(tx)
                self._dropped(tx, "stale_nonce")
            unpayable, _ = q.filter(self.state.balance(addr), gas_limit)
            for tx in unpayable:
                dropped.append(tx)
                self._dropped(tx, "unpayable")
            promotable.extend(q.ready(self._pending_nonce(addr)))
            for tx in q.cap(self.config.account_queue):
                dropped.append(tx)
                self._dropped(tx, "account_queue")
            if q.empty():
                del self.queue[addr]
                self.beats.pop(addr, None)
                emptied.append(addr)
        promoted = [tx for tx in promotable if self._promote_tx(tx)]
        for tx in dropped:
            self._all_remove(tx)
        self.priced.removed(len(dropped))
        for addr in emptied:
            if addr not in self.pending:
                self.reserver.release(addr, self)
        return promoted

    def _promote_tx(self, tx: Tx) -> bool:
        addr = tx.sender
        plist = self.pending.get(addr)
        if plist is None:
            plist = self.pending[addr] = NonceList(strict=True)
        inserted, old = plist.add(tx, self.config.price_bump)
        if not inserted:
            self._all_remove(tx)
            self.priced.removed(1)
            self._dropped(tx, "replaced")
            return False
        if old is not None:
            self._all_remove(old)
            self.priced.removed(1)
            self._dropped(old, "replaced")
        self.pending_nonces[addr] = tx.nonce + 1
        self._bump(addr)
        self.log.append(("pending", tx, "promoted"))
        return True

    def _demote_unexecutables(self) -> None:
        """NP-19 step 3, go-ethereum `demoteUnexecutables`."""
        gas_limit = self.head.gas_limit
        for addr in list(self.pending):
            plist = self.pending[addr]
            nonce = self.state.nonce(addr)
            olds = plist.forward(nonce)
            for tx in olds:
                self._all_remove(tx)
                self._dropped(tx, "stale_nonce")
            drops, invalids = plist.filter(self.state.balance(addr), gas_limit)
            for tx in drops:
                self._all_remove(tx)
                self._dropped(tx, "unpayable")
            for tx in invalids:
                self._demote(tx)
            self.priced.removed(len(olds) + len(drops))
            if not plist.empty() and plist.get(nonce) is None:
                for tx in plist.cap(0):
                    self._demote(tx)
            if plist.empty():
                del self.pending[addr]
                if addr not in self.queue:
                    self.reserver.release(addr, self)

    def _truncate_pending(self) -> None:
        """NP-16, go-ethereum `truncatePending`. Ties between senders go by address (MD-10)."""
        c = self.config
        pending = len(self.all) - sum(len(q) for q in self.queue.values())
        if pending <= c.global_slots:
            return
        spammers = sorted((a for a, l in self.pending.items() if len(l.txs) > c.account_slots),
                          key=lambda a: (-len(self.pending[a]), a))

        def cut(addr: str) -> None:
            plist = self.pending[addr]
            caps = plist.cap(len(plist) - 1)
            for tx in caps:
                self._all_remove(tx)
                self._set_if_lower(addr, tx.nonce)
                self._dropped(tx, "pending_truncated")
            self.priced.removed(len(caps))

        offenders: list[str] = []
        for offender in spammers:
            if pending <= c.global_slots:
                break
            offenders.append(offender)
            if len(offenders) > 1:
                threshold = len(self.pending[offender])
                while pending > c.global_slots and len(self.pending[offenders[-2]]) > threshold:
                    for addr in offenders[:-1]:
                        cut(addr)
                        pending -= 1
        if pending > c.global_slots and offenders:
            while pending > c.global_slots and len(self.pending[offenders[-1]]) > c.account_slots:
                for addr in offenders:
                    cut(addr)
                    pending -= 1

    def _truncate_queue(self) -> None:
        """NP-16, go-ethereum `queue.truncate`: oldest heartbeat first, ties by address."""
        c = self.config
        queued = sum(len(q) for q in self.queue.values())
        if queued <= c.global_queue:
            return
        drop = queued - c.global_queue
        removed: list[Tx] = []
        emptied: list[str] = []
        for addr in sorted(self.queue, key=lambda a: (self.beats.get(a, 0), a)):
            if drop <= 0:
                break
            txs = self.queue[addr].flatten()
            if len(txs) <= drop:
                for tx in txs:
                    self._queue_remove(addr, tx)
                    removed.append(tx)
                drop -= len(txs)
                emptied.append(addr)
                continue
            for tx in reversed(txs):
                if drop <= 0:
                    break
                self._queue_remove(addr, tx)
                removed.append(tx)
                drop -= 1
        for tx in removed:
            self._all_remove(tx)
            self._dropped(tx, "queue_truncated")
        self.priced.removed(len(removed))
        for addr in emptied:
            if addr not in self.pending:
                self.reserver.release(addr, self)

    # --- lifetime --------------------------------------------------------------

    def _run_evictions(self, now: float) -> None:
        """NP-18: run, each at its own time, every pass due at or before `now`."""
        interval = self.config.eviction_interval
        due = self._last_eviction + interval
        while due <= now:
            self._now = due
            if self.queue:
                self._evict_pass(due)
            self._last_eviction = due
            due += interval
        self._now = now

    def _evict_pass(self, t: float) -> None:
        stale = [tx for addr, q in self.queue.items()
                 if t - self.beats.get(addr, t) > self.config.lifetime for tx in q.flatten()]
        for tx in stale:
            self._dropped(tx, "lifetime")
            self._remove_tx(tx, outofbound=True, unreserve=True)
