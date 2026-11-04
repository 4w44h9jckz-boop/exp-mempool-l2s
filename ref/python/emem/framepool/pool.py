"""The frame transaction pool: `docs/spec/02-frame-pool.md`, the MATCHA proposal of `04-matcha.md`, the
recent roots of `08-recent-roots.md`, the expiring nonces of `09-expiring-nonces.md`, the claim-gated
admission of `10-claim-gated-admission.md`, and the relaxed alternative mempool of `15-relaxed-mempool.md`."""

from __future__ import annotations

import heapq
import itertools
import math
from collections import Counter
from dataclasses import dataclass, replace
from typing import Callable

from .. import errors as E
from ..dependencies import dependencies
from ..errors import TxError
from ..model import Head, State, is_delegation
from ..reserver import Reserver
from ..tx import FrameTx, replaces
from .config import EIP_8141, FramePoolConfig
from .matcha import admission_gas, charge
from .prefix import (EXPIRY, PAY, ROOT, Prefix, Simulation, analyse, check_expiring, check_nonce, check_static,
                     dep_value, expiring, seen_slot, simulate, static_payer)
from .relaxed import BANNED, RELAXABLE, declaration, declares, state_of

ACTIVE, THROTTLED, BANNED_STATE = "ACTIVE", "THROTTLED", "BANNED"  # AM-13's states


def staked(addr: str, state: State, cfg: FramePoolConfig) -> bool:
    """AM-3 [STAKING-010], and CG-11's bonded: never a default-code account."""
    stake, delay, withdrawing = state.stake(addr)
    return state.code(addr) != "" and stake >= cfg.min_stake_value and delay >= cfg.min_unstake_delay \
        and not withdrawing


@dataclass
class Entry:
    tx: FrameTx
    seq: int
    prefix: Prefix
    sim: Simulation
    admitted: float = 0
    charge: int = 0  # MA-2, kept for the re-runs of MA-9
    reads: frozenset[str] = frozenset()  # the addresses it is indexed under (FP-15)
    cls: frozenset = frozenset()  # MA-14, fixed at admission
    relaxed: frozenset = frozenset()  # RM-2: the relaxations that admitted it, of `reads`, `sender` and `payer`
    declared: tuple = ()  # RM-3: the declared slots it reads, as (address, slot)
    relies: frozenset = frozenset()  # RM-6: the declared codes it relies on


class FramePool:
    def __init__(self, head: Head, state: State, config: FramePoolConfig = EIP_8141,
                 reserver: Reserver | None = None, now: float = 0,
                 sequence: Callable[[], int] | None = None):
        self.config = config
        self.head = head
        self.state = state
        self.reserver = reserver or Reserver()
        self.entries: dict[str, Entry] = {}
        self.by_identity: dict[tuple, str] = {}
        self.by_sender: dict[str, list[str]] = {}
        self.keys: dict[str, dict[int, int]] = {}  # by sender: how many pending transactions use each nonce key
        self.reserved: dict[str, int] = {}
        self.readers: dict[str, set[str]] = {}  # FP-15: by address, the transactions whose sender, payer or dependencies name it
        self.payer_count: dict[str, int] = {}
        self.resimulated: list[FrameTx] = []
        self.resimulations = 0
        self.dropped: Counter = Counter()  # by reason, every transaction the pool has removed
        self.work: Counter = Counter()  # by sender: admission gas (MA-2) of every prefix run, admitted or not
        self.log: list[tuple[str, FrameTx, str]] = []
        self._sequence = sequence or itertools.count().__next__
        self.matcha = config.per_sender == "matcha"
        self.widths: dict[str, int] = {}  # MA-3
        self.bases: set[str] = set()  # MA-5: the hashes of pending baselines
        self.claims: dict[str, Counter] = {}  # MA-14: by sender, how many pending classes hold each element
        self._ages: list[tuple[float, int, str]] = []  # MA-8: a heap of (admitted, seq, hash), stale ones included
        self.credited: int | None = None  # MA-4: the highest block number credited
        self._evictable: list[tuple[tuple, str]] = []  # FP-14: a heap of (key, hash), stale entries included
        self._evict_fee: int | None = None  # the pending base fee its keys were computed at; None to rebuild
        self.proven: set = set()  # AG-6: the dependency triples this node holds proofs for
        self.relayed: set = set()  # CG-7: the triples a relay has passed on unverified, which AG-6 counts as proven
        # CG-4 to CG-6, under `claims`. CG-2 makes a claim name its transaction's slot, so a claim stands
        # for the clauses' slot and claim.
        self.refused_slots: dict[tuple, int] = {}  # CG-4 under `slot`: by slot, the last epoch it is refused in
        self.refused_claims: dict = {}  # CG-4 under `claim`: by claim, the same
        self.used_claims: set = set()  # CG-5: the claims a node has verified a proof under
        self.expired_claims: dict = {}  # CG-6: by claim, the last epoch it is refused in
        # AM-13's counters, kept for ERC-8421's entities and, under `bond`, for ticket paymasters (CG-11)
        self.counters: dict[str, list[int]] = {}  # by address, [seen, included]
        self.refreshed = 0  # how many refreshes the pool's time has passed
        self._counted: set[str] = set()  # CG-11: the transactions counted in a ticket paymaster's `seen`
        # 15-relaxed-mempool.md, under `relaxed`
        self._canon = config.with_(relaxed=False, dependency_frames=False, claims=False, bond=False, binding=False)
        self._full = config  # the descriptor's whole configuration, while RM-2's first judgement runs canonically
        self.slot_readers: dict[tuple, set[str]] = {}  # RM-3: by declared slot, the pending transactions reading it
        self.violations: dict[str, int] = {}  # RM-6: by declared code
        self.declarations_refreshed = 0  # RM-6: how many refreshes the pool's time has passed
        self.forwarded: set = set()  # RM-8: the claims a relay has forwarded
        self._relaxing = False  # RM-2: the second judgement is running
        self._marks: set[str] = set()  # RM-2: the relaxations the running judgement has used
        self._relies: set[str] = set()  # RM-6: the declared codes it has relied on
        self._sim: Simulation | None = None  # the running judgement's simulation, for RM-4
    # --- the pool interface (MD-8) --------------------------------------------

    def add(self, txs: list[FrameTx], now: float = 0) -> list[str]:
        results = []
        for tx in txs:
            self._expire(now)
            results.append(self._add_one(tx, now))
        return results

    def reset(self, head: Head, state: State, now: float = 0, verdicts: dict[str, str] | None = None,
              access_lists: list | None = None) -> None:
        """FP-15, with MA-8 to MA-10 under `matcha`, and RM-6's reading of the blocks' access lists under
        `relaxed`.

        Only a transaction indexed under an address the new state may have
        changed can fail step 1, 3 or 4, so only those are looked at, in the
        order received; the EIP's "Nodes SHOULD index pending transactions by
        this set" is the same idea.
        """
        self._expire(now)
        if self.config.relaxed and access_lists:
            self._violations(access_lists)
        touched = state.changed_since(self.state)
        self.head, self.state = head, state
        self.resimulated = []
        self._evictable, self._evict_fee = [], None
        verdicts = {h: v for h, v in (verdicts or {}).items() if h in self.entries}  # MD-8
        renewed = {h for h, v in verdicts.items() if self.entries[h].sim.verdict not in (None, v)}  # FP-10, FP-15 step 3
        affected = sorted({h for a in touched for h in self.readers.get(a, ())} | renewed,
                          key=lambda h: self.entries[h].seq)
        cfg = self.config
        for h in affected:
            tx = self.entries[h].tx
            if expiring(tx, cfg):  # EN-6 in place of step 1
                if cfg.nonce_ring in touched and \
                        state.storage(cfg.nonce_ring, seen_slot(h)) >= head.timestamp + cfg.expiry_margin:
                    self._remove(h, "stale_nonce")
            elif tx.sender in touched and any(state.nonce_seq(tx.sender, k) > tx.nonce_seq for k in tx.nonce_keys):
                self._remove(h, "stale_nonce")
        for h, e in list(self.entries.items()):
            if e.sim.deadline is not None and e.sim.deadline < head.timestamp + self.config.expiry_margin:
                self._remove(h, "expired")
        if self.config.recent_roots:  # RR-7
            current, length = head.slot + 1, self.config.recent_root_length
            for h, e in list(self.entries.items()):
                if e.sim.roots is None:
                    continue
                if e.sim.roots[1] >= current:
                    self._remove(h, "root_future")
                elif e.sim.roots[0] + length <= current:
                    self._remove(h, "root_expired")
        values: dict[tuple, object] = {}  # each dependency's value at the new head, read once

        def value(key: tuple) -> object:
            if key not in values:
                values[key] = dep_value(state, key)
            return values[key]

        for h in affected:
            e = self.entries.get(h)
            if e is None:
                continue
            changed = [k for k, v in e.sim.deps.items() if value(k) != v]
            if h in verdicts and e.tx.verdict is not None:  # the newest verdict is the one any re-run uses
                e.tx = replace(e.tx, verdict=verdicts[h])
            if h in renewed:
                changed.append(("verdict",))
            if not changed:
                continue
            if self._reuse(e, changed, state):
                continue
            if self.matcha and h not in self.bases:  # MA-9
                if self.widths.get(e.tx.sender, 0) < e.charge:
                    self._remove(h, "width")
                    continue
                self.widths[e.tx.sender] -= e.charge
            self.resimulated.append(e.tx)
            self.resimulations += 1
            self.work[e.tx.sender] += admission_gas(e.tx, e.prefix)
            try:
                sim = self._simulate(e.tx, e.prefix, head, state, relax=bool(e.relaxed))
            except TxError as err:
                self._invalidated(h, err)
                continue
            self._index(e, -1)
            e.sim = sim
            self._index(e, +1)
        if self.matcha:  # MA-10: recount, remove nothing
            self.reserved, self.payer_count = {}, {}
            for e in self.entries.values():
                self._account(e, +1)
            return
        # Step 4. A payer whose account did not change passes again, because removals only lower what
        # precedes each of its transactions; the others are counted again from nothing.
        payers = touched & self.reserved.keys()
        again = sorted((h for p in payers for h in self.readers.get(p, ()) if self.entries[h].sim.payer == p),
                       key=lambda h: self.entries[h].seq)
        for p in payers:
            del self.reserved[p], self.payer_count[p]
        for h in again:
            e = self.entries[h]
            try:
                self._check_payer(e.tx, e.sim.payer, e.sim.payer_class, None, lifted="payer" in e.relaxed)
            except TxError as err:
                self._remove(h, "payer:" + err.code, account=False)
                continue
            self._account(e, +1)

    def _invalidated(self, tx_hash: str, err: TxError) -> None:
        """FP-15 step 3: a re-run that fails removes the transaction."""
        self._remove(tx_hash, "invalidated:" + err.code)

    def _reuse(self, e: Entry, changed: list[tuple], state: State) -> bool:
        """FP-15 step 3 under `reuse_balance`, or MA-9 step 1: whether a change to balances alone re-runs nothing."""
        if not self.config.reuse_balance or any(k[0] != "balance" for k in changed):
            return False
        if self.matcha:
            return True
        if any(not e.sim.deps[k] or not dep_value(state, k) for k in changed):
            return False  # a balance from or to zero can change the sender-existence check
        for k in changed:
            e.sim.deps[k] = dep_value(state, k)
        return True

    def tick(self, now: float) -> None:
        self._expire(now)

    def finalize(self, blocks: list[tuple[int, dict[str, int]]], now: float = 0) -> None:
        """MD-8; MA-4 under `matcha`, ignored otherwise."""
        self._expire(now)
        if not self.matcha:
            return
        for number, gas in sorted(blocks, key=lambda b: b[0]):
            if self.credited is not None and number <= self.credited:
                continue
            for sender, g in gas.items():
                self.widths[sender] = min(self.config.width_cap, self.widths.get(sender, 0) + g)
            self.credited = number

    def width(self, sender: str) -> int:
        """MA-12."""
        return self.widths.get(sender, 0)

    def baselines(self, sender: str) -> list[str]:
        """MA-12: the hashes of the sender's pending baselines, in the order admitted."""
        return [h for h in self.by_sender.get(sender, ()) if h in self.bases]

    def baseline(self, sender: str) -> str | None:
        """MA-12: the first of the sender's baselines, or None."""
        hashes = self.baselines(sender)
        return hashes[0] if hashes else None

    def load(self, sender: str, leave_out: str | None = None) -> int:
        """MA-12, MA-13: the charges of the sender's pending additional transactions, without `leave_out`."""
        return sum(self.entries[h].charge for h in self.by_sender.get(sender, ())
                   if h not in self.bases and h != leave_out)

    def over_reserved(self) -> set[str]:
        """MA-10: the payers whose balance at the head is below their reservations."""
        canonical = {e.sim.payer for e in self.entries.values() if e.sim.payer_class == "canonical"}
        return {payer for payer, r in self.reserved.items()
                if self.state.balance(payer) - r - (self.state.withdrawal(payer) if payer in canonical else 0) < 0}

    def content(self) -> dict[str, list[FrameTx]]:
        return {s: [self.entries[h].tx for h in hs] for s, hs in self.by_sender.items()}

    def status(self, tx_hash: str) -> str:
        return "pending" if tx_hash in self.entries else "unknown"

    def pending_view(self, min_tip: int, base_fee: int) -> list[FrameTx]:
        """FP-16, and MA-11 under `matcha`."""
        live = [e for e in self.entries.values() if e.tx.effective_tip(base_fee) >= min_tip]
        if self.matcha:
            unavailable = self.over_reserved()
            live = [e for e in live if e.sim.payer not in unavailable]
        live.sort(key=lambda e: (-e.tx.effective_tip(base_fee), e.seq))
        return [e.tx for e in live]

    def arrival(self, tx_hash: str) -> int:
        return self.entries[tx_hash].seq

    def before_prefix(self, tx: FrameTx) -> None:
        """SF-4: FP-2 to FP-7, and CG-2, CG-4 and CG-6 under `claims`, the checks a node runs before it asks a
        client about the prefix. Raises the first failure and changes nothing."""
        if tx.hash in self.entries:  # FP-2
            raise TxError(E.ErrAlreadyKnown)
        prefix = check_static(tx, self.head, self.config)  # FP-3 to FP-6
        if self.config.claims:  # CG-2, CG-4, CG-6
            self._check_claim(tx)
        if expiring(tx, self.config):  # EN-4 in place of FP-7
            check_expiring(tx, prefix, self.state, self.config, self.head.timestamp + self.config.expiry_margin)
        else:
            check_nonce(tx, self.state)  # FP-7

    # --- claim-gated admission (CG-2 to CG-6) ---------------------------------

    def epoch(self) -> int:
        """CG-1: the epoch of the head."""
        return self.head.timestamp // self.config.claim_epoch

    def precheck(self, tx: FrameTx) -> None:
        """CG-3 step 2 for one transaction: FP-2 to FP-10 with CG-2, CG-4 and CG-6, without AG-6, then CG-5.
        Raises the first failure and changes nothing but the work counted. A relay of RM-8 runs no prefix."""
        if tx.hash in self.entries:  # FP-2
            raise TxError(E.ErrAlreadyKnown)
        prefix = check_static(tx, self.head, self.config)  # FP-3 to FP-6, AG-2 to AG-4
        self._check_claim(tx)
        self.work[tx.sender] += admission_gas(tx, prefix)
        if self.config.relaxed and self.config.tier == "relay":
            check_nonce(tx, self.state)  # FP-7, the relay's state
        else:
            self._simulate(tx, prefix, self.head, self.state, relax=self.config.relaxed)  # FP-7 to FP-10
        if tx.claim is not None and tx.claim in self.used_claims:  # CG-5
            raise TxError(E.ErrClaimUsed)

    def proof_verified(self, tx: FrameTx, failed: bool) -> None:
        """CG-5, and CG-4 and CG-11's count when `failed`: a mode 0 wrapper that passed CG-3 reached AG-5's step
        5, and a proof of a triple `tx` declares did not verify."""
        claim = tx.claim
        if claim is None:
            return
        if failed:
            self._see(tx)  # CG-11
        self.used_claims.add(claim)
        memory = self.config.claim_memory
        if failed and memory == "slot":
            self.refused_slots[tx.slot] = max(self.refused_slots.get(tx.slot, claim.epoch), claim.epoch)
        elif failed and memory == "claim":
            self.refused_claims[claim] = claim.epoch

    def _check_claim(self, tx: FrameTx) -> None:
        """CG-11 under `bond`, then CG-2 with CG-12 under `binding` after its step 1, then CG-4, then CG-6, as the
        pool runs them after FP-6."""
        claim = tx.claim
        if claim is None:
            if dependencies(tx, self.config):
                raise TxError(E.ErrClaimMissing)
            return
        self._check_bond(tx)
        if self.config.binding and not claim.bound:
            raise TxError(E.ErrClaimUnbound)
        if not claim.valid:
            raise TxError(E.ErrClaimInvalid)
        if claim.slot != tx.slot:
            raise TxError(E.ErrClaimWrongSlot)
        epoch = self.epoch()
        if claim.epoch != epoch:
            raise TxError(E.ErrClaimEpoch)
        if self.refused_slots.get(tx.slot, -1) >= epoch:
            raise TxError(E.ErrSlotRefused)
        if self.refused_claims.get(claim, -1) >= epoch:
            raise TxError(E.ErrClaimRefused)
        if self.expired_claims.get(claim, -1) >= epoch:
            raise TxError(E.ErrClaimExpired)

    # --- AM-13's reputation, and CG-11's bond on the ticket paymaster ----------

    def give(self, addr: str, seen: int, included: int) -> None:
        """AM-13: the counters a node was given for `addr`."""
        self.counters[addr] = [seen, included]

    def reputation(self, addr: str) -> dict:
        """AM-13: an entity's counters and state (MD-9)."""
        seen, included = self.counters.get(addr, (0, 0))
        return {"seen": seen, "included": included, "status": self.state_of(addr)}

    def state_of(self, addr: str) -> str:
        cfg = self.config
        seen, included = self.counters.get(addr, (0, 0))
        m = seen // cfg.min_inclusion_rate_denominator
        if m > included + cfg.ban_slack:
            return BANNED_STATE
        if included + cfg.throttling_slack < m:
            return THROTTLED
        return ACTIVE

    def _bump(self, addr: str, seen: int = 0, included: int = 0) -> None:
        c = self.counters.setdefault(addr, [0, 0])
        c[0], c[1] = max(0, c[0] + seen), max(0, c[1] + included)

    def _refresh(self, now: float) -> None:
        """AM-13 [REPUTATION-010]: every `refresh_seconds` of the pool's time, counted from 0."""
        due = int(now // self.config.refresh_seconds)
        while self.refreshed < due:
            for c in self.counters.values():
                c[0], c[1] = c[0] * 23 // 24, c[1] * 23 // 24
            self.refreshed += 1

    def ticket_paymaster(self, tx: FrameTx) -> str | None:
        """CG-11: the payer of a transaction that carries a claim, when that is not its sender."""
        if not self.config.bond or tx.claim is None:
            return None
        prefix = analyse(tx, self.config)
        if prefix is None:
            return None
        last = prefix.frames[-1]
        payer = last.target if last.target is not None else tx.sender
        return None if payer == tx.sender else payer

    def _check_bond(self, tx: FrameTx) -> None:
        """CG-11's three refusals, in order."""
        paymaster = self.ticket_paymaster(tx)
        if paymaster is None:
            return
        cfg = self.config
        if not staked(paymaster, self.state, cfg):
            raise TxError(E.ErrIssuerUnbonded)
        status = self.state_of(paymaster)
        if status == BANNED_STATE:
            raise TxError(E.ErrEntityBanned)
        if status == THROTTLED and sum(1 for e in self.entries.values()
                                       if self.ticket_paymaster(e.tx) == paymaster) >= \
                cfg.throttled_entity_mempool_count:
            raise TxError(E.ErrEntityThrottled)

    def _see(self, tx: FrameTx) -> None:
        """CG-11: `seen`, once for each transaction, when its proof fails or when it is admitted."""
        paymaster = self.ticket_paymaster(tx)
        if paymaster is not None and tx.hash not in self._counted:
            self._counted.add(tx.hash)
            self._bump(paymaster, seen=+1)

    # --- admission ------------------------------------------------------------

    def _add_one(self, tx: FrameTx, now: float = 0) -> str:
        """RM-2 under `relaxed`: the canonical modules first, and the whole descriptor only for a transaction they
        refuse with a code a relaxation answers, or one with a dependency; RM-8's relay apart."""
        if not self.config.relaxed:
            return self._admit(tx, now)
        if self.config.tier == "relay":
            return self._relay(tx, now)
        if not any(f.mode == self.config.dep_frame_mode for f in tx.frames):
            self.config = self._canon
            try:
                code = self._admit(tx, now)
            finally:
                self.config = self._full
            if code not in RELAXABLE:
                return code
        self._relaxing = True
        try:
            return self._admit(tx, now)
        finally:
            self._relaxing = False

    def _admit(self, tx: FrameTx, now: float = 0) -> str:
        self._marks, self._relies, self._sim = set(), set(), None
        try:
            if tx.hash in self.entries:  # FP-2
                raise TxError(E.ErrAlreadyKnown)
            prefix = check_static(tx, self.head, self.config)  # FP-3 to FP-6, AG-2 to AG-4
            if self.config.claims:  # CG-2, CG-4, CG-6
                self._check_claim(tx)
            if self.config.dependency_frames and not all(d in self.proven or d in self.relayed
                                                          for d in dependencies(tx, self.config)):  # AG-6, CG-7 step 3
                raise TxError(E.ErrFrameDepsUnproven)
            if not self._relaxing:  # RM-2's second judgement runs no prefix that was not counted
                self.work[tx.sender] += admission_gas(tx, prefix)
            old_hash = None if self._many(tx) else self.by_identity.get((tx.sender, tx.nonce_keys, tx.nonce_seq))
            old = self.entries[old_hash] if old_hash is not None else None
            early = self.config.static_first and not self.matcha
            if early:  # Admission under `static_first`: FP-7, then FP-11 and FP-12, before the prefix runs
                if expiring(tx, self.config):  # EN-4
                    check_expiring(tx, prefix, self.state, self.config, self.head.timestamp + self.config.expiry_margin)
                else:
                    check_nonce(tx, self.state)
                self._check_payer(tx, *static_payer(tx, prefix, self.state, self.config), old)
                self._check_identity(tx, old)
            sim = self._simulate(tx, prefix, self.head, self.state, relax=self._relaxing)  # FP-7 to FP-10
            self._sim = sim
            if not early:
                self._check_payer(tx, sim.payer, sim.payer_class, old)  # FP-11
            tx_charge = charge(tx, prefix, self.config.safety_factor) if self.matcha else 0
            cls = self._class(tx, sim) if self.matcha else frozenset()
            if old is not None:  # FP-12, MA-7
                if not early and not replaces(old.tx, tx, self.config.price_bump):
                    raise TxError(E.ErrReplaceUnderpriced)
                baseline = self.matcha and old_hash in self.bases and self._keeps(cls, tx.sender, old_hash)
                if self.matcha and not baseline:
                    self._check_additional(tx, sim, tx_charge, old_hash)
            elif self.matcha:  # MA-5, MA-6
                if tx.sender in self.by_sender:
                    self._check_keys(tx)
                baseline = not self._shares(cls, tx.sender)
                if not baseline:
                    self._check_additional(tx, sim, tx_charge)
            elif not early:
                self._check_sender(tx)
            declared = self._declared(tx, sim)
            if self._relaxing:  # RM-3's unset slots, then RM-6
                self._check_relaxed(tx, sim, declared, old_hash)
            if self.reserver.held_by_other(tx.sender, self):  # FP-13
                raise TxError(E.ErrAlreadyReserved)
            seq = self._sequence()
            if old is None and len(self.entries) >= self.config.max_pending:  # FP-14
                victim = self._victim(tx, seq, sim.deadline)
                if victim is None:
                    raise TxError(E.ErrTxPoolOverflow)
                self._remove(victim, "capacity")
            if old_hash is not None:  # CG-6 under `binding`: the holder's re-pricing is no removal
                same = self.config.binding and tx.claim is not None and tx.claim == self.entries[old_hash].tx.claim
                self._remove(old_hash, "replaced", release=False, keep_claim=same)
            if self.matcha:
                if baseline:
                    self.bases.add(tx.hash)
                else:
                    self.widths[tx.sender] -= tx_charge
            self._insert(Entry(tx, seq, prefix, sim, now, tx_charge, cls=cls, relaxed=frozenset(self._marks),
                               declared=declared, relies=frozenset(self._relies)))
            return E.OK
        except TxError as err:
            return err.code

    def _simulate(self, tx: FrameTx, prefix: Prefix, head: Head, state: State, relax: bool = False) -> Simulation:
        """FP-7 to FP-10 as a pool runs them: with its `expiry_margin`, and its head's slot plus one and its
        `root_margin` (RR-2, RR-5); with `relax`, RM-3's declared reads."""
        cfg = self.config
        return simulate(tx, prefix, head, state, cfg, cfg.expiry_margin, head.slot + 1, cfg.root_margin, relax)

    def _check_payer(self, tx: FrameTx, payer: str, payer_class: str, old: Entry | None,
                     lifted: bool = False) -> None:
        """FP-11, with RM-5 in the second judgement of RM-2; `lifted` for a transaction RM-5 admitted, which FP-15
        step 4 counts again without the count."""
        cfg = self.config
        reserved = self.reserved.get(payer, 0)
        count = self.payer_count.get(payer, 0)
        if old is not None and old.sim.payer == payer:
            reserved -= old.tx.max_cost
            count -= 1
        withdrawal = self.state.withdrawal(payer) if payer_class == "canonical" else 0
        if self.state.balance(payer) - reserved - withdrawal < tx.max_cost:
            raise TxError(E.ErrFramePayerExposure)
        capped = payer_class == "noncanonical" or (payer_class == "default" and cfg.cap_codeless_payers)
        if capped and count >= cfg.max_pending_noncanonical and not lifted:
            if self._relaxing and self._rm5(tx, payer):  # RM-5
                self._marks.add("payer")
                return
            raise TxError(E.ErrFramePaymasterBusy)

    def _check_identity(self, tx: FrameTx, old: Entry | None) -> None:
        """FP-12 as a whole: the price bump over the pending transaction with the same identity, else the sender."""
        if old is not None:
            if not replaces(old.tx, tx, self.config.price_bump):
                raise TxError(E.ErrReplaceUnderpriced)
        else:
            self._check_sender(tx)

    def _check_sender(self, tx: FrameTx) -> None:
        """FP-12, for a transaction that replaces nothing; under EN-6, not for one in the mode, and counting none."""
        if self._many(tx):
            return
        pending = len(self.by_sender.get(tx.sender, ()))
        if self.config.expiring and self.config.expiring_per_sender == "many":
            pending -= self.keys.get(tx.sender, {}).get(self.config.expiring_key, 0)
        if pending and not (self.config.per_sender == "disjoint-keys" and self._disjoint(tx)):
            if self._relaxing and self._rm4(tx):  # RM-4
                self._marks.add("sender")
                return
            raise TxError(E.ErrFrameSenderBusy)

    def _many(self, tx: FrameTx) -> bool:
        """EN-6: whether `tx` is in the mode and exempt from FP-12, identified by its hash alone."""
        return expiring(tx, self.config) and self.config.expiring_per_sender == "many"

    def _disjoint(self, tx: FrameTx) -> bool:
        """Neither `tx` nor any pending transaction from its sender uses key 0, and they share no key."""
        used = self.keys.get(tx.sender, {})
        return 0 not in tx.nonce_keys and 0 not in used and not any(k in used for k in tx.nonce_keys)

    def _class(self, tx: FrameTx, sim: Simulation) -> frozenset:
        """MA-14: the sender alone, or what FP-10 recorded that can make the pool re-run the prefix."""
        cfg = self.config
        if cfg.contention == "sender":
            return frozenset([("sender", tx.sender)])
        cls = set()
        for key, value in sim.deps.items():
            kind = key[0]
            if kind == "nonce_seq" or (kind == "balance" and cfg.reuse_balance):
                continue
            if kind == "code" and value != "" and not is_delegation(value):
                continue
            if kind == "storage" and cfg.recent_roots and key[1] == cfg.recent_root_address:
                continue
            cls.add(key[:2] if kind == "storage" and cfg.contention == "storage" else key)
        return frozenset(cls)

    def _shares(self, cls: frozenset, sender: str) -> bool:
        """MA-5: whether a pending transaction from `sender` shares the class `cls`."""
        claims = self.claims.get(sender, {})
        return any(x in claims for x in cls)

    def _keeps(self, cls: frozenset, sender: str, old_hash: str) -> bool:
        """MA-7: whether a replacement of the baseline `old_hash` with class `cls` is a baseline: every element
        is the old one's or no pending transaction's."""
        old = self.entries[old_hash].cls
        claims = self.claims.get(sender, {})
        return all(x in old or x not in claims for x in cls)

    def _check_keys(self, tx: FrameTx) -> None:
        """MA-6, check 1: non-zero keys on both sides, and none shared."""
        if not self._disjoint(tx):
            raise TxError(E.ErrFrameSenderBusy)

    def _check_additional(self, tx: FrameTx, sim: Simulation, tx_charge: int, replaced: str | None = None) -> None:
        """MA-6, checks 2 to 5: valid for a child of the head, the width to pay for it, and MA-13's floor."""
        if tx.max_fee < self.head.next_base_fee():
            raise TxError(E.ErrFeeCapTooLow)
        if sim.deadline is not None and sim.deadline <= self.head.timestamp:
            raise TxError(E.ErrFrameExpired)
        if self.widths.get(tx.sender, 0) < tx_charge:
            raise TxError(E.ErrFrameInsufficientWidth)
        price = self.config.load_price  # MA-13, compared exactly: tip * c >= price * (c + L)
        if price and tx.effective_tip(self.head.next_base_fee()) * tx_charge < \
                price * (tx_charge + self.load(tx.sender, replaced)):
            raise TxError(E.ErrFrameLoadUnderpriced)

    def _expire(self, now: float) -> None:
        """AM-13's refresh and RM-6's, then MA-8, oldest first."""
        self._refresh(now)
        if self._full.relaxed:
            self._refresh_declarations(now)
        if not self.matcha:
            return
        ages = self._ages
        while ages and now - ages[0][0] > self.config.lifetime:
            _, seq, h = heapq.heappop(ages)
            e = self.entries.get(h)
            if e is not None and e.seq == seq:
                self._remove(h, "lifetime")

    def _evict_key(self, deadline: int | None, tx: FrameTx, seq: int, base_fee: int) -> tuple:
        """FP-14: the smallest key is the victim. The latest received has the smallest `-seq`."""
        nearest = math.inf if deadline is None else deadline
        tip = tx.effective_tip(base_fee)
        return (nearest, tip, -seq) if self.config.evict_first == "expiry" else (tip, nearest, -seq)

    def _victim(self, tx: FrameTx, seq: int, deadline: int | None) -> str | None:
        """FP-14: the held transaction to evict for `tx`, or None when `tx` itself is the victim.

        The held keys live in a heap, built at the pending base fee on first use
        after a reset; a removed transaction leaves its entry behind until it
        reaches the top.
        """
        base_fee = self.head.next_base_fee()
        if self._evict_fee != base_fee:
            self._evictable = [(self._evict_key(e.sim.deadline, e.tx, e.seq, base_fee), h)
                               for h, e in self.entries.items()]
            heapq.heapify(self._evictable)
            self._evict_fee = base_fee
        heap = self._evictable
        while heap and (heap[0][1] not in self.entries or self.entries[heap[0][1]].seq != -heap[0][0][-1]):
            heapq.heappop(heap)
        if heap and heap[0][0] < self._evict_key(deadline, tx, seq, base_fee):
            return heap[0][1]
        return None

    # --- 15-relaxed-mempool.md ------------------------------------------------

    def _declared(self, tx: FrameTx, sim: Simulation) -> tuple:
        """RM-3: the declared slots a prefix reads, its sender's included, as (address, slot), in a fixed order."""
        cfg = self._full
        if not cfg.relaxed:
            return ()
        return tuple(sorted((k[1], k[2]) for k in sim.deps
                            if k[0] == "storage" and declares(cfg, self.state.code(k[1]), k[2])))

    def _check_relaxed(self, tx: FrameTx, sim: Simulation, declared: tuple, old_hash: str | None) -> None:
        """RM-3's unset slots, then RM-6, for a transaction RM-2's second judgement admits."""
        cfg = self._full
        if any(a != tx.sender for a, _ in declared):
            self._marks.add("reads")
        for a, slot in declared:
            if a != tx.sender or "sender" in self._marks:
                self._relies.add(self.state.code(a))
            if self.state.storage(a, slot) == 0 and self.slot_readers.get((a, slot), set()) - {old_hash}:
                raise TxError(E.ErrWriteOnceBusy)
        for code in sorted(self._relies):
            state = state_of(self.violations.get(code, 0), cfg)
            if state == BANNED:
                raise TxError(E.ErrDeclarationBanned)
            if state != "ACTIVE" and sum(1 for h, e in self.entries.items()
                                         if code in e.relies and h != old_hash) >= cfg.throttled_count:
                raise TxError(E.ErrDeclarationThrottled)

    def _rm4(self, tx: FrameTx) -> bool:
        """RM-4: items 1 to 3, for a transaction FP-12 refuses under `one`."""
        cfg, sim = self._full, self._sim
        if not self._disjoint(tx):
            return False
        if cfg.sender_bound:
            code = self.state.code(tx.sender)
            if declaration(cfg, code) is None:
                return False
            if any(k[0] == "storage" and k[1] == tx.sender and not declares(cfg, code, k[2]) for k in sim.deps):
                return False
            self._relies.add(code)
        if cfg.outflow_bound and sim.payer_class != "canonical":
            return self._reserve(tx, sim.payer)
        return True

    def _rm5(self, tx: FrameTx, payer: str) -> bool:
        """RM-5: the count lifted, under `outflow_bound` for a payer that passes the reserve."""
        return not self._full.outflow_bound or self._reserve(tx, payer)

    def _reserve(self, tx: FrameTx, payer: str) -> bool:
        """RM-5's reserve: a declared payer with a bound X, and a max_cost of at least X."""
        code = self.state.code(payer)
        d = declaration(self._full, code)
        if d is None or d[2] is None:
            return False
        if tx.max_cost < d[2]:
            raise TxError(E.ErrRelaxedReserve)
        self._relies.add(code)
        return True

    def _violations(self, access_lists: list) -> None:
        """RM-6: each block's access list, read against the old head's codes and values, oldest block first."""
        cfg, state = self._full, self.state
        storage: dict[tuple, int] = {}
        balance: dict[str, int] = {}
        for block in access_lists:
            for addr, changes in block.items():
                code = state.code(addr)
                d = declaration(cfg, code)
                if d is None:
                    continue
                for slot, writes in changes.get("storage_changes", {}).items():
                    for _, post in sorted(writes):
                        pre = storage.get((addr, slot), state.storage(addr, slot))
                        if pre != 0 and declares(cfg, code, slot):
                            self.violations[code] = self.violations.get(code, 0) + 1
                        storage[(addr, slot)] = post
                for _, post in sorted(changes.get("balance_changes", [])):
                    pre = balance.get(addr, state.balance(addr))
                    if d[2] is not None and pre - post > d[2]:
                        self.violations[code] = self.violations.get(code, 0) + 1
                    balance[addr] = post

    def _refresh_declarations(self, now: float) -> None:
        """RM-6: violations decay every `declaration_refresh_seconds` of the pool's time, counted from 0."""
        due = int(now // self._full.declaration_refresh_seconds)
        while self.declarations_refreshed < due:
            for code in list(self.violations):
                self.violations[code] = self.violations[code] * 23 // 24
            self.declarations_refreshed += 1

    def declaration_status(self, code: str) -> dict:
        """RM-6: a declared code's count of violations and its state (MD-9)."""
        v = self.violations.get(code, 0)
        return {"violations": v, "state": state_of(v, self._full)}

    def groups(self) -> list[list[FrameTx]]:
        """RM-7: the pending transactions joined by shared keys, listed by their earliest received."""
        order = sorted(self.entries.values(), key=lambda e: e.seq)
        parent = {e.tx.hash: e.tx.hash for e in order}

        def find(h: str) -> str:
            while parent[h] != h:
                parent[h] = parent[parent[h]]
                h = parent[h]
            return h

        owner: dict[tuple, str] = {}
        for e in order:
            keys = [("nonce", e.tx.sender, k) for k in e.tx.nonce_keys] + [("payer", e.sim.payer)] + \
                   [("slot", a, slot) for a, slot in e.declared]
            for key in keys:
                if key in owner:
                    a, b = find(owner[key]), find(e.tx.hash)
                    if a != b:
                        first, second = sorted((a, b), key=lambda h: self.entries[h].seq)
                        parent[second] = first
                else:
                    owner[key] = e.tx.hash
        groups: dict[str, list[FrameTx]] = {}
        for e in order:
            groups.setdefault(find(e.tx.hash), []).append(e.tx)
        return list(groups.values())

    def _protocol_defined(self, tx: FrameTx, prefix: Prefix) -> bool:
        """RM-8 item 1: every prefix frame is one the EIP evaluates directly."""
        for frame, kind in zip(prefix.frames, prefix.kinds):
            if kind in (ROOT, EXPIRY):
                continue
            target = frame.target if frame.target is not None else tx.sender
            code = self.state.code(target)
            if code == "" or (kind == PAY and code == self.config.canonical_paymaster_code):
                continue
            return False
        return True

    def _relay(self, tx: FrameTx, now: float = 0) -> str:
        """RM-8: a relay's admission. It runs no prefix and checks no proof."""
        cfg = self.config
        try:
            if tx.hash in self.entries:  # FP-2
                raise TxError(E.ErrAlreadyKnown)
            prefix = check_static(tx, self.head, cfg)  # FP-3 to FP-6, AG-2 to AG-4
            if cfg.dependency_frames and not all(d in self.proven or d in self.relayed
                                                  for d in dependencies(tx, cfg)):  # AG-6, CG-7 step 3
                raise TxError(E.ErrFrameDepsUnproven)
            old_hash = self.by_identity.get((tx.sender, tx.nonce_keys, tx.nonce_seq))
            old = self.entries[old_hash] if old_hash is not None else None
            if self._protocol_defined(tx, prefix):  # item 1, evaluated as FP-8 does
                sim = self._simulate(tx, prefix, self.head, self.state)
            elif tx.claim is not None:  # item 2: the claim, and not the prefix
                seqs = check_nonce(tx, self.state)  # FP-7
                self._check_claim(tx)
                if tx.claim in self.forwarded and (old is None or old.tx.claim != tx.claim):
                    raise TxError(E.ErrClaimUsed)
                payer, payer_class = static_payer(tx, prefix, self.state, cfg)
                deps = {("nonce_seq", tx.sender, k): s for k, s in zip(tx.nonce_keys, seqs)}
                deps[("balance", payer)] = self.state.balance(payer)
                sim = Simulation(payer, payer_class, deps, None)
            else:
                raise TxError(E.ErrRelayUnchecked)
            reserved = self.reserved.get(sim.payer, 0) - (old.tx.max_cost if old and old.sim.payer == sim.payer else 0)
            withdrawal = self.state.withdrawal(sim.payer) if sim.payer_class == "canonical" else 0
            if self.state.balance(sim.payer) - reserved - withdrawal < tx.max_cost:  # FP-11's exposure check
                raise TxError(E.ErrFramePayerExposure)
            if old is not None:  # FP-12
                if not replaces(old.tx, tx, cfg.price_bump):
                    raise TxError(E.ErrReplaceUnderpriced)
            elif tx.sender in self.by_sender and not self._disjoint(tx):  # RM-4 item 1
                raise TxError(E.ErrFrameSenderBusy)
            if self.reserver.held_by_other(tx.sender, self):  # FP-13
                raise TxError(E.ErrAlreadyReserved)
            seq = self._sequence()
            if old is None and len(self.entries) >= cfg.max_pending:  # FP-14
                victim = self._victim(tx, seq, sim.deadline)
                if victim is None:
                    raise TxError(E.ErrTxPoolOverflow)
                self._remove(victim, "capacity")
            if old_hash is not None:
                self._remove(old_hash, "replaced", release=False, keep_claim=True)
            self._insert(Entry(tx, seq, prefix, sim, now))
            if tx.claim is not None:
                self.forwarded.add(tx.claim)
            return E.OK
        except TxError as err:
            return err.code

    # --- bookkeeping ----------------------------------------------------------

    def _index(self, e: Entry, sign: int) -> None:
        """Add `e` to `readers` under its sender, payer and dependencies, or take it out."""
        if sign > 0:
            e.reads = frozenset((e.tx.sender, e.sim.payer, *(k[1] for k in e.sim.deps)))
        for a in e.reads:
            if sign > 0:
                self.readers.setdefault(a, set()).add(e.tx.hash)
            else:
                hashes = self.readers[a]
                hashes.discard(e.tx.hash)
                if not hashes:
                    del self.readers[a]

    def _account(self, e: Entry, sign: int) -> None:
        payer = e.sim.payer
        self.reserved[payer] = self.reserved.get(payer, 0) + sign * e.tx.max_cost
        self.payer_count[payer] = self.payer_count.get(payer, 0) + sign
        if self.payer_count[payer] == 0:
            del self.reserved[payer], self.payer_count[payer]

    def _insert(self, e: Entry) -> None:
        tx = e.tx
        self.entries[tx.hash] = e
        if not self._many(tx):
            self.by_identity[(tx.sender, tx.nonce_keys, tx.nonce_seq)] = tx.hash
        self.by_sender.setdefault(tx.sender, []).append(tx.hash)
        used = self.keys.setdefault(tx.sender, {})
        for k in tx.nonce_keys:
            used[k] = used.get(k, 0) + 1
        self._account(e, +1)
        self._index(e, +1)
        for key in e.declared:  # RM-3
            self.slot_readers.setdefault(key, set()).add(tx.hash)
        if self._evict_fee is not None:
            heapq.heappush(self._evictable, (self._evict_key(e.sim.deadline, tx, e.seq, self._evict_fee), tx.hash))
        if self.matcha:
            if e.cls:
                self.claims.setdefault(tx.sender, Counter()).update(e.cls)
            heapq.heappush(self._ages, (e.admitted, e.seq, tx.hash))
        self.reserver.hold(tx.sender, self)
        self._see(tx)  # CG-11
        self.log.append(("pending", tx, "admitted"))

    def _remove(self, tx_hash: str, reason: str, release: bool = True, account: bool = True,
                keep_claim: bool = False) -> None:
        e = self.entries.pop(tx_hash)
        tx = e.tx
        self.dropped[reason] += 1
        self.bases.discard(tx_hash)
        if e.cls:
            claims = self.claims[tx.sender]
            claims.subtract(e.cls)
            for x in e.cls:
                if not claims[x]:
                    del claims[x]
            if not claims:
                del self.claims[tx.sender]
        identity = (tx.sender, tx.nonce_keys, tx.nonce_seq)
        if self.by_identity.get(identity) == tx_hash:
            del self.by_identity[identity]
        hashes = self.by_sender[tx.sender]
        hashes.remove(tx_hash)
        used = self.keys[tx.sender]
        for k in tx.nonce_keys:
            used[k] -= 1
            if not used[k]:
                del used[k]
        if not hashes:
            del self.by_sender[tx.sender]
            del self.keys[tx.sender]
            if release:
                self.reserver.release(tx.sender, self)
        if account:
            self._account(e, -1)
        self._index(e, -1)
        for key in e.declared:  # RM-3
            readers = self.slot_readers[key]
            readers.discard(tx_hash)
            if not readers:
                del self.slot_readers[key]
        if reason == "stale_nonce" and tx.hash in self._counted:  # CG-11: included
            self._bump(self.ticket_paymaster(tx), included=+1)
        canonical = self.config.relaxed and not e.relaxed and not dependencies(tx, self.config)  # RM-2
        if self.config.claims and tx.claim is not None and reason != "stale_nonce" and not keep_claim \
                and not canonical:  # CG-6
            self.expired_claims[tx.claim] = max(self.expired_claims.get(tx.claim, tx.claim.epoch), tx.claim.epoch)
        self.log.append(("dropped", tx, reason))
