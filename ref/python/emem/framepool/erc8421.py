"""ERC-8421's standard alternative mempool: `docs/spec/14-erc-8421.md`, AM-2 to AM-14.

A pool under the ruleset is the frame pool of `02-frame-pool.md` with FP-5,
FP-6, FP-7, FP-9, FP-11 and FP-12 replaced (AM-2): a prefix's frames are
attributed to entities (AM-3), which have their own budgets (AM-5), trace
rules (AM-8) and storage rules (AM-9), and stake and reputation decide how
much of the pool each may hold (AM-13). Nothing here runs the EVM; a frame
carries what a node's tracer would observe (MD-6). Decision record 0061.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache

from .. import errors as E
from ..errors import TxError
from ..model import Head, State
from ..tx import APPROVE_PAYMENT, APPROVE_SCOPE_MASK, ATOMIC_BATCH_FLAG, VERIFY_MODE, FrameTx, replaces
from .config import FramePoolConfig
from .matcha import admission_gas
from .pool import Entry, FramePool
from .prefix import (BANNED_OPCODES, DEPLOY, EXPIRY, ONLY_VERIFY, PAY, RECOGNIZED, SELF_VERIFY, Prefix, Simulation,
                     analyse, check_fp3, classify, classify_payer, default_code_approves)

PRE_VERIFY, STRAY = "pre_verify", "stray"  # AM-4
APPROVING = (SELF_VERIFY, ONLY_VERIFY, PAY)
CREATION = frozenset({"CREATE", "CREATE2", "SETDELEGATE"})
BANNED = BANNED_OPCODES - CREATION - {"SSTORE"}  # AM-8: OPCODES-020 and CREATION-010 take these
STAKED_ONLY = frozenset({"BALANCE", "SELFBALANCE"})  # OPCODES-010
ACTIVE, THROTTLED, BANNED_STATE = "ACTIVE", "THROTTLED", "BANNED"


class Refusal(TxError):
    """A refusal attributed to an entity (AM-14): the address of the frame, or the budget, that failed."""

    def __init__(self, code: str, entity: str | None):
        super().__init__(code)
        self.entity = entity


def _fail(code: str, entity: str | None = None):
    raise Refusal(code, entity)


# --- AM-4: structure -------------------------------------------------------------------------------------

def structure(tx: FrameTx, gas_limit: int, cfg: FramePoolConfig) -> Prefix:
    """FP-3 with SIGNATURE-010 (AM-6), then AM-4's steps 1 to 5: everything decidable without state."""
    result = _structure(tx, gas_limit, cfg)
    if isinstance(result, str):
        raise TxError(result)
    return result


@lru_cache(maxsize=1 << 12)
def _structure(tx: FrameTx, gas_limit: int, cfg: FramePoolConfig) -> Prefix | str:
    try:
        check_fp3(tx, gas_limit, cfg)
        return _classify(tx, cfg)
    except TxError as err:
        return err.code


def _resolved(frame, sender: str) -> str:
    return frame.target if frame.target is not None else sender


def _classify(tx: FrameTx, cfg: FramePoolConfig) -> Prefix:
    kinds = [classify(f, tx.sender, cfg) for f in tx.frames]
    if any(k == EXPIRY for k in kinds[1:]):  # PREFIX-010
        _fail(E.ErrFrameExpiryNotFirst)
    prefix = analyse(tx, cfg)
    if prefix is None:  # PREFIX-010
        _fail(E.ErrFrameNoPayer)
    if any(f.flags & ATOMIC_BATCH_FLAG for f in prefix.frames):  # PREFIX-040
        _fail(E.ErrFrameAtomicInPrefix)
    frames, kinds = prefix.frames, list(prefix.kinds)
    first = 1 if kinds[0] == EXPIRY else 0
    for i, kind in enumerate(kinds):
        if kind != DEPLOY:  # FP-5's DEFAULT frame with no approval scope
            continue
        if i + 1 < len(kinds) and kinds[i + 1] in APPROVING and \
                _resolved(frames[i], tx.sender) == _resolved(frames[i + 1], tx.sender):
            kinds[i] = PRE_VERIFY
        elif i != first:
            kinds[i] = STRAY
    if STRAY in kinds:  # PREFIX-120
        _fail(E.ErrFrameStrayDefault)
    shape = tuple(k for k in kinds[first:] if k != PRE_VERIFY)
    if shape not in RECOGNIZED:  # PREFIX-010
        _fail(E.ErrFrameUnrecognizedPrefix)
    if any(f.mode == VERIFY_MODE for f in prefix.rest):  # PREFIX-050
        _fail(E.ErrFrameVerifyAfterPrefix)
    return Prefix(prefix.length, tuple(kinds), frames, prefix.rest)


def check_pre_verify(tx: FrameTx, prefix: Prefix, state: State) -> None:
    """AM-4 step 6 [PREFIX-110]: a pre_verify frame's target has code at the head."""
    for frame, kind in zip(prefix.frames, prefix.kinds):
        target = _resolved(frame, tx.sender)
        if kind == PRE_VERIFY and state.code(target) == "":
            _fail(E.ErrFramePreVerifyNoCode, target)


# --- AM-3 and AM-5: entities, stake and budgets ---------------------------------------------------------

@dataclass(frozen=True)
class Entities:
    """AM-3: the roles, the entity each prefix frame is attributed to, and which entities are staked."""

    sender: str
    payer: str
    factory: str | None
    of_frame: tuple[str | None, ...]
    staked: frozenset[str]

    @property
    def addresses(self) -> tuple[str, ...]:
        """Each entity once, in the order sender, payer, factory."""
        out: list[str] = []
        for a in (self.sender, self.payer, self.factory):
            if a is not None and a not in out:
                out.append(a)
        return tuple(out)


def staked(addr: str, state: State, cfg: FramePoolConfig) -> bool:
    """AM-3 [STAKING-010]: never a default-code entity."""
    stake, delay, withdrawing = state.stake(addr)
    return state.code(addr) != "" and stake >= cfg.min_stake_value and delay >= cfg.min_unstake_delay \
        and not withdrawing


def entities(tx: FrameTx, prefix: Prefix, state: State, cfg: FramePoolConfig) -> Entities:
    """AM-3."""
    factory = None
    of_frame: list[str | None] = []
    for frame, kind in zip(prefix.frames, prefix.kinds):
        if kind == EXPIRY:
            of_frame.append(None)
            continue
        target = _resolved(frame, tx.sender)  # a pre_verify frame's is the next frame's (AM-4)
        if kind == DEPLOY:
            factory = target
        of_frame.append(target)
    payer = _resolved(prefix.frames[-1], tx.sender)
    addrs = {tx.sender, payer} | ({factory} if factory is not None else set())
    return Entities(tx.sender, payer, factory, tuple(of_frame),
                    frozenset(a for a in addrs if staked(a, state, cfg)))


def check_budgets(tx: FrameTx, prefix: Prefix, ent: Entities, cfg: FramePoolConfig) -> None:
    """AM-5 [BUDGET-010]: exec_gas by entity, the signatures with the sender, the expiry frame with none."""
    sums = {a: 0 for a in ent.addresses}
    for frame, who in zip(prefix.frames, ent.of_frame):
        if who is not None:
            sums[who] += frame.exec_gas
    sums[tx.sender] += sum(s.verify_gas for s in tx.signatures)
    for a in ent.addresses:
        limit = cfg.max_verify_gas_staked_entity if a in ent.staked else cfg.max_verify_gas_per_entity
        if sums[a] > limit:
            _fail(E.ErrEntityVerifyGas, a)


# --- AM-7 to AM-9: simulation, trace and storage -------------------------------------------------------

@dataclass
class ErcSimulation(Simulation):
    """FP-10's record, with the entities and every traced storage access as (address, associated)."""

    entities: Entities | None = None
    accesses: tuple[tuple[str, str | None], ...] = field(default=())


def _trace(frame, kind: str, who: str | None, tx: FrameTx, ent: Entities, state: State,
           cfg: FramePoolConfig) -> None:
    """AM-8, in its order."""
    ops = frame.opcodes
    if "UNASSIGNED" in ops:  # OPCODES-030
        _fail(E.ErrFrameUnassignedOpcode, who)
    if "OOG_REVERT" in ops:  # OPCODES-040
        _fail(E.ErrFrameOutOfGasRevert, who)
    banned = BANNED - STAKED_ONLY if who in ent.staked else BANNED
    if ops & banned:  # OPCODES-010, OPCODES-020
        _fail(E.ErrFrameBannedOpcode, who)
    if kind != DEPLOY and ops & CREATION:  # CREATION-010
        _fail(E.ErrFrameCreation, who)
    for addr in frame.calls:  # CALLING-010, CALLING-040
        if addr != tx.sender and addr not in cfg.precompiles and state.code(addr) == "":
            _fail(E.ErrFrameCallTarget, who)


def _allowed(access: tuple, write: bool, who: str | None, ent: Entities) -> bool:
    """AM-9: STORAGE-010 to STORAGE-033."""
    addr = access[0]
    assoc = access[3] if len(access) > 3 else None
    outside = addr not in ent.addresses
    if addr == ent.sender:  # STORAGE-010
        return True
    if assoc == ent.sender and outside and (ent.factory is None or ent.factory in ent.staked):  # STORAGE-021, -022
        return True
    if who in ent.staked:
        if addr == who:  # STORAGE-031
            return True
        if outside and (not write or assoc == who):  # STORAGE-032, STORAGE-033
            return True
    return False


def run(tx: FrameTx, prefix: Prefix, ent: Entities, head: Head, state: State, cfg: FramePoolConfig,
        expiry_margin: int = 0) -> ErcSimulation:
    """AM-7 to AM-9, frame by frame, recording AM-14's dependencies."""
    sender = tx.sender
    deps: dict[tuple, object] = {}
    for a in ent.addresses:
        deps[("code", a)] = state.code(a)
        deps[("balance", a)] = state.balance(a)
        deps[("stake", a)] = state.stake(a)
    sender_code = state.code(sender)
    written: dict[tuple[str, int], int] = {}  # what deploy and pre_verify frames wrote, read by later frames
    accesses: list[tuple[str, str | None]] = []
    deadline = payer = payer_code = None
    for frame, kind, who in zip(prefix.frames, prefix.kinds, ent.of_frame):
        if kind == EXPIRY:  # PREFIX-100, evaluated directly as FP-8 does
            code = state.code(cfg.expiry_verifier)
            deps[("code", cfg.expiry_verifier)] = code
            if code != cfg.expiry_verifier_code:
                _fail(E.ErrFramePrefixReverted)
            deadline = frame.deadline
            if frame.deadline < head.timestamp + expiry_margin:  # PREFIX-080
                _fail(E.ErrFrameExpired)
            continue
        target = _resolved(frame, sender)
        code = sender_code if target == sender else state.code(target)
        if code not in ("", cfg.canonical_paymaster_code):  # PREFIX-100 exempts the rest from AM-8 and AM-9
            _trace(frame, kind, who, tx, ent, state, cfg)
            if frame.mode == VERIFY_MODE and frame.writes:  # static mode: the write reverts
                _fail(E.ErrFramePrefixReverted, who)
            for access, write in [(r, False) for r in frame.reads] + [(w, True) for w in frame.writes]:
                if not _allowed(access, write, who, ent):  # STORAGE-000
                    _fail(E.ErrFrameStorageAccess, who)
                accesses.append((access[0], access[3] if len(access) > 3 else None))
        if code != "":  # FP-8's outcome; the default code reads nothing
            for addr, slot, expected, *_ in frame.reads:
                deps[("storage", addr, slot)] = state.storage(addr, slot)
                value = written.get((addr, slot), state.storage(addr, slot))
                if expected is not None and value != expected:
                    _fail(E.ErrFramePrefixReverted, who)
            if frame.reverts:  # PREFIX-060
                _fail(E.ErrFramePrefixReverted, who)
        if kind in (DEPLOY, PRE_VERIFY):
            if kind == DEPLOY:  # PREFIX-020
                if code == "" or frame.installs_code is None or sender_code != "":
                    _fail(E.ErrFrameDeployNoCode, who)
                sender_code = frame.installs_code
            written.update({(addr, slot): value for addr, slot, value, *_ in frame.writes})
            continue
        scope = frame.flags & APPROVE_SCOPE_MASK
        if code == "":
            if not default_code_approves(tx, scope, target):
                _fail(E.ErrFramePrefixReverted, who)
        elif frame.approves != scope:  # PREFIX-060
            _fail(E.ErrFrameMissingApprove, who)
        if scope & APPROVE_PAYMENT:
            if state.balance(target) < tx.max_cost:  # APPROVE reverts [PREFIX-060]
                _fail(E.ErrInsufficientFunds, who)
            payer, payer_code = target, code
    assert payer is not None  # the structure guarantees a payment frame
    payer_class = classify_payer(payer, payer_code, sender, cfg)
    if payer_class == "canonical":
        deps[("withdrawal", payer)] = state.withdrawal(payer)
    return ErcSimulation(payer, payer_class, deps, deadline, entities=ent, accesses=tuple(accesses))


def validate(tx: FrameTx, prefix: Prefix, head: Head, state: State, cfg: FramePoolConfig,
             expiry_margin: int = 0) -> ErcSimulation:
    """AM-14: what revalidation re-runs, PREFIX-110, AM-3, AM-5 and AM-7 to AM-9 against `state`."""
    check_pre_verify(tx, prefix, state)
    ent = entities(tx, prefix, state, cfg)
    check_budgets(tx, prefix, ent, cfg)
    return run(tx, prefix, ent, head, state, cfg, expiry_margin)


# --- the pool ---------------------------------------------------------------------------------------------

class StandardPool(FramePool):
    """A frame pool under ERC-8421's standard ruleset (`config.ruleset == "erc-8421"`)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.counters: dict[str, list[int]] = {}  # AM-13: by address, [seen, included]
        self.refreshed = 0  # how many refreshes the pool's time has passed

    # --- AM-13: reputation ----------------------------------------------------

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

    def ops_allowed(self, addr: str) -> int:
        """REPUTATION-220, in integers as written."""
        cfg = self.config
        seen, included = self.counters.get(addr, (0, 0))
        extra = included * min(included, cfg.max_txs_allowed_unstaked_entity) // seen if seen else 0
        return cfg.same_unstaked_entity_mempool_count + extra

    def _bump(self, addr: str, seen: int = 0, included: int = 0) -> None:
        c = self.counters.setdefault(addr, [0, 0])
        c[0], c[1] = max(0, c[0] + seen), max(0, c[1] + included)

    def _expire(self, now: float) -> None:
        """REPUTATION-010's refresh, every `refresh_seconds` of the pool's time."""
        super()._expire(now)
        due = int(now // self.config.refresh_seconds)
        while self.refreshed < due:
            for c in self.counters.values():
                c[0], c[1] = c[0] * 23 // 24, c[1] * 23 // 24
            self.refreshed += 1

    def _count(self, test, replaced: list[str]) -> int:
        return sum(1 for h, e in self.entries.items() if h not in replaced and test(e))

    def _check_reputation(self, tx: FrameTx, ent: Entities, replaced: list[str]) -> None:
        """AM-13, for each entity in the order sender, payer, factory."""
        cfg = self.config
        for a in ent.addresses:
            status = self.state_of(a)
            if a in ent.staked or (a == ent.payer and a != tx.sender):
                if status == BANNED_STATE:  # REPUTATION-010
                    raise TxError(E.ErrEntityBanned)
                if status == THROTTLED:  # REPUTATION-020
                    if self._count(lambda e: a in e.sim.entities.addresses, replaced) >= \
                            cfg.throttled_entity_mempool_count:
                        raise TxError(E.ErrEntityThrottled)
                elif a not in ent.staked:  # REPUTATION-220
                    if self._count(lambda e: e.sim.payer == a, replaced) >= self.ops_allowed(a):
                        raise TxError(E.ErrPayerOpsAllowed)
            elif a == tx.sender and status == THROTTLED:  # REPUTATION-210
                if self._count(lambda e: e.tx.sender == a, replaced) >= cfg.throttled_entity_mempool_count:
                    raise TxError(E.ErrSenderThrottled)

    # --- AM-10 to AM-12 -------------------------------------------------------

    def _conflicts(self, tx: FrameTx) -> list[str]:
        """LIFECYCLE-020: the sender's pending transactions with the same nonce_seq that share a key."""
        keys = set(tx.nonce_keys)
        return [h for h in self.by_sender.get(tx.sender, ())
                if self.entries[h].tx.nonce_seq == tx.nonce_seq and keys & set(self.entries[h].tx.nonce_keys)]

    def _contiguous(self, tx: FrameTx, pending: list[FrameTx]) -> str | None:
        """LIFECYCLE-010 against the chain and `pending`: None, or the code that refuses `tx`."""
        chain = [self.state.nonce_seq(tx.sender, k) for k in tx.nonce_keys]
        if any(tx.nonce_seq < c for c in chain):
            return E.ErrNonceTooLow
        for k, c in zip(tx.nonce_keys, chain):
            if tx.nonce_seq != c and not any(k in p.nonce_keys and p.nonce_seq + 1 == tx.nonce_seq for p in pending):
                return E.ErrNonceGap
        return None

    def _check_solvency(self, tx: FrameTx, sim: Simulation, replaced: list[str]) -> None:
        """AM-12 [SOLVENCY-010, SOLVENCY-020]: not counting the transactions it replaces."""
        payer = sim.payer
        reserved = self.reserved.get(payer, 0) - sum(self.entries[h].tx.max_cost for h in replaced
                                                     if self.entries[h].sim.payer == payer)
        withdrawal = self.state.withdrawal(payer) if sim.payer_class == "canonical" else 0
        if self.state.balance(payer) - reserved - withdrawal < tx.max_cost:
            raise TxError(E.ErrFramePayerExposure)

    def _check_payer(self, tx: FrameTx, payer: str, payer_class: str, old: Entry | None) -> None:
        """FP-15 step 4 under the ruleset: AM-12's exposure, with no cap of FP-11's kind."""
        reserved = self.reserved.get(payer, 0) - (old.tx.max_cost if old is not None and old.sim.payer == payer else 0)
        withdrawal = self.state.withdrawal(payer) if payer_class == "canonical" else 0
        if self.state.balance(payer) - reserved - withdrawal < tx.max_cost:
            raise TxError(E.ErrFramePayerExposure)

    def _check_local(self, tx: FrameTx, sim: ErcSimulation, replaced: list[str]) -> None:
        """AM-11 [LOCAL-010, LOCAL-020]."""
        ent = sim.entities
        senders = {e.tx.sender for h, e in self.entries.items() if h not in replaced}
        for a in (ent.factory, ent.payer):
            if a is not None and a != tx.sender and a in senders:
                raise TxError(E.ErrEntityIsSender)
        mine = {tx.sender} | ent.staked
        if any(assoc in mine and addr in senders for addr, assoc in sim.accesses):
            raise TxError(E.ErrLocalStorage)

    def _check_limits(self, tx: FrameTx, ent: Entities, replaced: list[str]) -> None:
        """AM-10 [LIFECYCLE-030]: not counting the transactions it replaces."""
        cfg = self.config
        pending = [self.entries[h].tx for h in self.by_sender.get(tx.sender, ()) if h not in replaced]
        for k in tx.nonce_keys:
            if sum(1 for p in pending if k in p.nonce_keys) >= cfg.same_nonce_key_mempool_count:
                raise TxError(E.ErrNonceKeyLimit)
        if tx.sender not in ent.staked and len(pending) >= cfg.same_sender_mempool_count:
            raise TxError(E.ErrSenderLimit)

    def _evict_gaps(self, senders) -> None:
        """LIFECYCLE-020 and AM-14: remove, in the order received, every pending transaction of `senders` that
        no longer meets LIFECYCLE-010, until none is left."""
        for sender in senders:
            changed = True
            while changed and sender in self.by_sender:
                changed = False
                for h in list(self.by_sender[sender]):
                    others = [self.entries[x].tx for x in self.by_sender[sender] if x != h]
                    if self._contiguous(self.entries[h].tx, others) is not None:
                        self._remove(h, "gap")
                        changed = True
                        break

    # --- admission (AM-2) -----------------------------------------------------

    def _add_one(self, tx: FrameTx, now: float = 0) -> str:
        cfg = self.config
        try:
            if tx.hash in self.entries:  # FP-2
                raise TxError(E.ErrAlreadyKnown)
            prefix = structure(tx, self.head.gas_limit, cfg)  # FP-3 with AM-6, AM-4 steps 1 to 5
            check_pre_verify(tx, prefix, self.state)  # AM-4 step 6
            replaced = self._conflicts(tx)
            ent = entities(tx, prefix, self.state, cfg)  # AM-3
            self._check_reputation(tx, ent, replaced)  # AM-13
            check_budgets(tx, prefix, ent, cfg)  # AM-5
            self.work[tx.sender] += admission_gas(tx, prefix)
            sim = run(tx, prefix, ent, self.head, self.state, cfg, cfg.expiry_margin)  # AM-7 to AM-9
            self._check_solvency(tx, sim, replaced)  # AM-12
            self._check_local(tx, sim, replaced)  # AM-11
            code = self._contiguous(tx, [self.entries[h].tx for h in self.by_sender.get(tx.sender, ())
                                         if h not in replaced])
            if code is not None:  # AM-10 [LIFECYCLE-010]
                raise TxError(code)
            self._check_limits(tx, ent, replaced)  # AM-10 [LIFECYCLE-030]
            if any(not replaces(self.entries[h].tx, tx, cfg.price_bump) for h in replaced):  # LIFECYCLE-020
                raise TxError(E.ErrReplaceUnderpriced)
            if self.reserver.held_by_other(tx.sender, self):  # FP-13
                raise TxError(E.ErrAlreadyReserved)
            seq = self._sequence()
            gapped = [tx.sender] if replaced else []
            if not replaced and len(self.entries) >= cfg.max_pending:  # FP-14
                victim = self._victim(tx, seq, sim.deadline)
                if victim is None:
                    raise TxError(E.ErrTxPoolOverflow)
                gapped.append(self.entries[victim].tx.sender)
                self._remove(victim, "capacity")
            before = {a for h in replaced for a in self.entries[h].sim.entities.addresses}
            for h in replaced:
                self._remove(h, "replaced", release=False)
            self._insert(Entry(tx, seq, prefix, sim, now))
            after = set(ent.addresses)
            for a in ent.addresses:  # AM-13 [REPUTATION-040]
                if a not in before:
                    self._bump(a, seen=+1)
            for a in sorted(before - after):
                self._bump(a, seen=-1)
            self._evict_gaps(gapped)  # AM-10
            return E.OK
        except TxError as err:
            return err.code

    # --- revalidation (AM-14) -------------------------------------------------

    def _simulate(self, tx: FrameTx, prefix: Prefix, head: Head, state: State) -> Simulation:
        return validate(tx, prefix, head, state, self.config, self.config.expiry_margin)

    def _invalidated(self, tx_hash: str, err: TxError) -> None:
        """AM-14: the blamed entity keeps its `seen`, every other loses one, except a staked factory when the
        sender is blamed [REPUTATION-320] and a staked sender [REPUTATION-330]."""
        ent = self.entries[tx_hash].sim.entities
        blamed = err.entity if isinstance(err, Refusal) else None
        for a in ent.addresses:
            if a == blamed or (a == ent.sender and a in ent.staked) or \
                    (a == ent.factory and a in ent.staked and blamed == ent.sender):
                continue
            self._bump(a, seen=-1)
        super()._invalidated(tx_hash, err)

    def _remove(self, tx_hash: str, reason: str, release: bool = True, account: bool = True) -> None:
        if reason == "stale_nonce":  # FP-15 step 1, read as inclusion (AM-13)
            for a in self.entries[tx_hash].sim.entities.addresses:
                self._bump(a, included=+1)
        super()._remove(tx_hash, reason, release, account)

    def reset(self, head: Head, state: State, now: float = 0, verdicts: dict[str, str] | None = None) -> None:
        """FP-15 with AM-14's dependencies and blame, then REPUTATION-010's removal of what refers to a banned
        entity, then LIFECYCLE-010's of what has a gap."""
        senders = {h: e.tx.sender for h, e in self.entries.items()}
        super().reset(head, state, now, verdicts)
        for h, e in list(self.entries.items()):
            ent = e.sim.entities
            if any(self.state_of(a) == BANNED_STATE for a in ent.addresses
                   if a in ent.staked or (a == ent.payer and a != ent.sender)):
                self._remove(h, "banned")
        self._evict_gaps(sorted({s for h, s in senders.items() if h not in self.entries}))
