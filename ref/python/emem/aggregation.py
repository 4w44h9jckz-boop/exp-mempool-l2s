"""In-mempool aggregation (EIP-8288) at one node: `docs/spec/05-aggregation.md`, AG-5 to AG-7, AG-9 and AG-10, and
CG-3 to CG-5 and CG-7 of `10-claim-gated-admission.md` under `claims`.

Nothing here proves anything. A proof is a flag, and a recursive STARK is the
list of dependencies whose hash is its public input, with a flag; a node can
aggregate any subset of what it has proven, because the EIP's circuit takes
recursive proofs and removes discards. Decision record 0012. Proving time is
counted, not spent: AG-9's linear count of the circuit's inputs, which bounds
what an aggregate lists when the profile sets a budget. Decision record 0034. Memory is counted the same
way over the same inputs, AG-10, and bounds what it lists under a budget of its own. Decision record 0042.
Verification is counted too, by event, for the simulator to price (decision
record 0037).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Callable

from . import errors as E
from .dependencies import counts, union
from .errors import TxError
from .tx import LEANSPHINCS, Dependency, FrameTx
from .txpool import TxPool


@dataclass(frozen=True)
class Stark:
    """A recursive STARK: the triples its public input is the hash of, and whether it verifies."""

    covers: tuple[Dependency, ...]
    valid: bool = True


@dataclass(frozen=True)
class Wrapper:
    """AG-5. `txs` holds frame transactions, and the hashes of those sent before."""

    txs: tuple[FrameTx | str, ...]
    mode: int
    deps: tuple[Dependency, ...]
    proofs: tuple[bool, ...] = ()  # mode 0: whether each triple's proof verifies
    stark: Stark | None = None  # mode 1
    signed: tuple[bool, ...] = ()  # mode 0, CG-3: whether each proof is the one its sender signed; () if all are


def wrap(txs: list[FrameTx], mode: int = 0) -> Wrapper:
    """An honest wrapper: its transactions' dependencies, and proofs that verify."""
    deps = union(txs)
    if mode == 0:
        return Wrapper(tuple(txs), 0, deps, (True,) * len(deps))
    return Wrapper(tuple(txs), 1, deps, stark=Stark(deps))


class Aggregator:
    """AG-5 to AG-7 and AG-9 for the node whose pool this is; the proven triples live on its frame pool (AG-6)."""

    def __init__(self, pool: TxPool):
        self.pool = pool
        self.previous: list[str] = []  # AG-7 step 1: its last aggregate, in order
        self.previous_deps: tuple[Dependency, ...] = ()  # AG-9 rule 1: what that aggregate's STARK covers
        self.sent: set[str] = set()  # the transactions it has sent in an aggregate
        self.received: list[tuple[Wrapper, list[str]]] = []  # AG-7 step 2: each aggregate received since, and its list
        self.direct: set[Dependency] = set()  # AG-9 rule 3: triples whose proofs it verified in a mode 0 wrapper
        self.first_cover: dict[Dependency, Wrapper] = {}  # AG-9 rule 4: the first aggregate that covered each triple
        self.proving_time: float = 0  # AG-9: the last aggregate's, in ms, 0 when it listed nothing
        self.memory: float = 0  # AG-10: the last aggregate's, in MiB, 0 when it listed nothing
        self.inputs = 0  # recursive STARKs the last aggregate took
        self.verified = 0  # triples the last aggregate verified directly
        self.folded: set[Dependency] = set()  # every triple its aggregates have listed
        self.work: Counter = Counter()  # by event, as `_count` names them (decision record 0037)
        self.observe: Callable[[str, FrameTx | None], None] | None = None  # told of each event and its transaction

    def _count(self, event: str, tx: FrameTx | None = None) -> None:
        """Decision record 0037: `check`, a transaction's admission checks run, its signature and claim among
        them; `proof`, a proof verified in a mode 0 wrapper; `stark`, a recursive STARK verified; for a triple
        listed in one of its aggregates for the first time, `fold` if the aggregate verified it directly
        (AG-9 rule 3) and `cover` if a recursive input it took covers it."""
        self.work[event] += 1
        if self.observe is not None:
            self.observe(event, tx)

    def receive(self, wrapper: Wrapper, now: float = 0) -> str | list[str]:
        """AG-5 and AG-6: a code refusing the whole wrapper, or one answer per transaction."""
        frame = self.pool.frame
        cfg = frame.config
        resolved = [entry if isinstance(entry, FrameTx) else
                    (frame.entries[entry].tx if entry in frame.entries else None) for entry in wrapper.txs]
        relay = cfg.claims and not cfg.verifies  # CG-7
        try:
            if relay and wrapper.mode == 1:  # CG-7 step 1
                raise TxError(E.ErrRelayAggregate)
            if wrapper.mode not in (0, 1) or (wrapper.mode == 0 and len(wrapper.proofs) != len(wrapper.deps)) \
                    or (wrapper.mode == 1 and wrapper.stark is None):
                raise TxError(E.ErrWrapperMalformed)
            if wrapper.mode == 0:
                if any(tx is None for tx in resolved):
                    raise TxError(E.ErrWrapperUnknownTx)
                if tuple(wrapper.deps) != union(resolved):
                    raise TxError(E.ErrWrapperDeps)
            elif tuple(wrapper.stark.covers) != tuple(wrapper.deps):
                raise TxError(E.ErrWrapperDeps)
            if wrapper.mode == 0 or cfg.cap_aggregates:
                sigs, starks = counts(wrapper.deps)
                if sigs > cfg.max_sig_deps_per_wrapper or starks > cfg.max_stark_deps_per_wrapper:
                    raise TxError(E.ErrWrapperTooManyDeps)
            gated = wrapper.mode == 0 and cfg.claims
            if gated:  # CG-3
                if cfg.signed_proofs and not all(wrapper.signed):
                    raise TxError(E.ErrProofUnsigned)
                for tx in resolved:
                    self._count("check", tx)
                    frame.precheck(tx)
            if relay:  # CG-7 step 2: no proof verified, and CG-5's record made
                for tx in resolved:
                    frame.proof_verified(tx, False)
            elif wrapper.mode == 0:  # step 5, in the order of the triples, as far as the first that fails
                owner: dict[Dependency, FrameTx] = {}
                for tx in resolved:
                    for d in tx.dependencies:
                        owner.setdefault(d, tx)
                for d, ok in zip(wrapper.deps, wrapper.proofs):
                    self._count("proof", owner.get(d))
                    if not ok:
                        break
                if gated:  # CG-4, CG-5
                    bad = {d for d, ok in zip(wrapper.deps, wrapper.proofs) if not ok}
                    for tx in resolved:
                        frame.proof_verified(tx, any(d in bad for d in tx.dependencies))
                if not all(wrapper.proofs):
                    raise TxError(E.ErrWrapperProof)
            else:
                self._count("stark")
                if not wrapper.stark.valid:
                    raise TxError(E.ErrWrapperProof)
        except TxError as err:
            return err.code
        if relay:  # CG-7 steps 2 and 3
            frame.relayed.update(wrapper.deps)
        else:
            frame.proven.update(wrapper.deps)
            if wrapper.mode == 0:
                self.direct.update(wrapper.deps)
            else:
                for d in wrapper.deps:
                    self.first_cover.setdefault(d, wrapper)
        fresh, seen = [], set()
        for tx in resolved:  # what the node holds is answered without asking the pool again
            if tx is not None and tx.hash not in frame.entries and tx.hash not in seen:
                fresh.append(tx)
                seen.add(tx.hash)
        if not (wrapper.mode == 0 and cfg.claims):  # checked here, after the proof; CG-3 checked them before
            for tx in fresh:
                self._count("check", tx)
        answers = dict(zip((tx.hash for tx in fresh), self.pool.add(fresh, now))) if fresh else {}
        results = []
        for tx in resolved:
            if tx is None:
                results.append(E.ErrWrapperUnknownTx)
            else:
                results.append(answers.pop(tx.hash, E.ErrAlreadyKnown))
        if wrapper.mode == 1:
            self.received.append((wrapper, [tx.hash for tx in resolved if tx is not None]))
        return results

    def aggregate(self) -> Wrapper | None:
        """AG-7: this interval's aggregate, or None for a node that lists nothing; AG-9 and AG-10 count and bound
        its time and its memory."""
        frame = self.pool.frame
        cfg = frame.config
        held = {h: e for h, e in frame.entries.items() if e.tx.dependencies}
        received, self.received = self.received, []
        self.proving_time, self.memory, self.inputs, self.verified = 0, 0, 0, 0
        if not held or (cfg.claims and not cfg.verifies):  # CG-7 step 5: a relay builds none
            self.previous, self.previous_deps = [], ()
            return None
        listed: list[str] = []
        chosen: set[str] = set()
        deps: set[Dependency] = set()
        covered: set[Dependency] = set()  # AG-9: what the inputs taken and the direct proofs cover
        taken: set[int] = set()  # the inputs taken, by identity; 0 is its own previous aggregate
        direct = 0
        verified: set[Dependency] = set()  # the triples it verifies directly
        time = memory = 0.0
        previous_cover = set(self.previous_deps)
        unit = {LEANSPHINCS: cfg.prove_sig}
        held_unit = {LEANSPHINCS: cfg.memory_sig}  # AG-10

        def consider(h: str, source: Wrapper | None = None, source_cover: frozenset = frozenset()) -> None:
            nonlocal direct, time, memory
            if h in chosen or h not in held:
                return
            tx = held[h].tx
            more = deps.union(tx.dependencies)
            if cfg.cap_aggregates:
                sigs, starks = counts(more)
                if sigs > cfg.max_sig_deps_per_wrapper or starks > cfg.max_stark_deps_per_wrapper:
                    return
            inputs: dict[int, tuple[Dependency, ...]] = {}  # AG-9: the inputs this transaction adds
            verify: set[Dependency] = set()
            for d in tx.dependencies:
                if d in covered or d in verify or any(d in c for c in inputs.values()):
                    continue
                if d in previous_cover:  # 1
                    key, cover = 0, self.previous_deps
                elif source is not None and d in source_cover:  # 2
                    key, cover = id(source), source.deps
                elif d in self.direct or d not in self.first_cover:  # 3
                    verify.add(d)
                    continue
                else:  # 4
                    first = self.first_cover[d]
                    key, cover = id(first), first.deps
                if key not in taken:
                    inputs[key] = cover
            extra = (0 if listed else cfg.prove_base) + cfg.prove_recursive * len(inputs) \
                + sum(unit.get(d.scheme, cfg.prove_stark) for d in verify)
            if cfg.proving_budget is not None and time + extra > cfg.proving_budget:
                return
            more_memory = (0 if listed else cfg.memory_base) + cfg.memory_recursive * len(inputs) \
                + sum(held_unit.get(d.scheme, cfg.memory_stark) for d in verify)  # AG-10, over AG-9's inputs
            if cfg.memory_budget is not None and memory + more_memory > cfg.memory_budget:
                return
            for key, cover in inputs.items():
                taken.add(key)
                covered.update(cover)
            covered.update(verify)
            verified.update(verify)
            direct += len(verify)
            time += extra
            memory += more_memory
            deps.update(more)
            chosen.add(h)
            listed.append(h)

        for h in self.previous:  # 1
            consider(h)
        while received:  # 2
            best = max(range(len(received)),
                       key=lambda i: (sum(1 for h in received[i][1] if h in held and h not in chosen), -i))
            wrapper, hashes = received.pop(best)
            cover = frozenset(wrapper.deps)
            for h in hashes:
                consider(h, wrapper, cover)
        base_fee = frame.head.next_base_fee()  # 3
        for e in sorted((e for h, e in held.items() if h not in chosen),
                        key=lambda e: (-e.tx.effective_tip(base_fee), e.seq)):
            consider(e.tx.hash)
        if not listed:
            self.previous, self.previous_deps = [], ()
            return None
        for h in listed:
            for d in held[h].tx.dependencies:
                if d not in self.folded:
                    self.folded.add(d)
                    self._count("fold" if d in verified else "cover", held[h].tx)
        entries = tuple(h if h in self.sent else held[h].tx for h in listed)
        self.sent.update(listed)
        self.previous = listed
        covered_deps = tuple(sorted(deps))
        self.previous_deps = covered_deps
        self.proving_time, self.memory, self.inputs, self.verified = time, memory, len(taken), direct
        return Wrapper(entries, 1, covered_deps, stark=Stark(covered_deps))
