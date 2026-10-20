"""Ticket issuers, and three defences a node might run against a self-issuer's junk proofs (decision records 0059
and 0062).

`docs/spec/10-claim-gated-admission.md` version 4 accepts as a ticket
paymaster any account whose code is the template, a key and a denomination
(CG-10), so anyone can issue tickets to themselves. Neither defence here is
a clause; each is modelled at a node, around the clauses, to price it:

- **Issuer memory.** A node counts, by issuer and epoch, the proofs that
  failed under its tickets (CG-4's record, kept by issuer), and once `k`
  have failed in an epoch it refuses that issuer's tickets for the rest of
  the epoch, with `ErrIssuerRefused`.
- **A node list.** A node accepts the tickets of the issuers it lists and
  refuses every other with `ErrIssuerUnlisted`.
- **A bond.** A node accepts the tickets of a paymaster that is staked, as
  `14-erc-8421.md` stakes an operator (AM-3), and refuses every other with
  `ErrIssuerUnbonded`; and it keeps ERC-8421's reputation for each ticket
  paymaster (AM-13): `seen` for each transaction under its tickets whose
  proof it checks or which it admits, `included` for each of those a block
  includes, both refreshed every `refresh_seconds`. A `BANNED` paymaster's
  tickets are refused with `ErrEntityBanned`, and a `THROTTLED` one's once
  it backs `throttled_entity_mempool_count` pending transactions here, with
  `ErrEntityThrottled`.

Each refuses in CG-2's place, before the ticket's signature is checked and
before the prefix runs, since a node reads a ticket's issuer from the
paymaster's code. A claim's issuer is not in the model's claim (MD-6): the
loads that make claims name it in `Issuers`, and the defences read it from
there. Each node counts, by load, the ticket checks, prefix simulations and
refusals it ran (`counts`).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace
from typing import Callable

from emem import Claim, FramePoolConfig, FrameTx, wrap
from emem import errors as E
from emem.errors import TxError

from .workload import Load, backed_tx, fixed

REFUSED = "ErrIssuerRefused"
UNLISTED = "ErrIssuerUnlisted"
UNBONDED = "ErrIssuerUnbonded"
ACTIVE, THROTTLED, BANNED = "ACTIVE", "THROTTLED", "BANNED"


class Issuers:
    """Which issuer signed each claim: named by the load that made it, or by its sender's issuer."""

    def __init__(self, by_sender: Callable[[str], str | None] = lambda sender: None):
        self.by_sender = by_sender
        self.named: dict[Claim, str] = {}

    def name(self, claim: Claim, issuer: str) -> None:
        self.named[claim] = issuer

    def of(self, claim: Claim) -> str | None:
        return self.named.get(claim) or self.by_sender(claim.sender)


@dataclass(frozen=True)
class Bond:
    """ERC-8421's stake and reputation for ticket paymasters (decision record 0062): the issuers whose paymasters
    are staked, and `config`, a profile carrying AM-1's parameters, as the `erc-8421` descriptor compiles to."""

    bonded: frozenset[str]
    config: FramePoolConfig


@dataclass(frozen=True)
class Defence:
    """What a node runs: `memory`, the failed proofs under one issuer that close it for the epoch, or None;
    `listed`, the issuers it accepts, or None for every one; `bond`, or None."""

    memory: int | None = None
    listed: frozenset[str] | None = None
    bond: Bond | None = None


def load_of(tx: FrameTx) -> str:
    """The load that made `tx`, the first word of its label."""
    return tx.label.split("-", 1)[0]


class Guard:
    """One node's defence, installed on its frame pool: CG-2's checks with the issuer's first, CG-4's record by
    issuer, and the counts. `closed` holds, by (issuer, epoch), the time it closed at this node; under a bond,
    `counters` holds each ticket paymaster's [seen, included] and `states` each change of its state, as (time,
    issuer, state)."""

    def __init__(self, node, defence: Defence, issuers: Issuers):
        self.node, self.defence, self.issuers = node, defence, issuers
        frame = node.pool.frame
        self.frame = frame
        self.failed: Counter = Counter()  # (issuer, epoch): proofs that failed under its tickets here
        self.closed: dict[tuple[str, int], float] = {}
        self.counts: Counter = Counter()  # (event, load): `ticket`, `prefix`, `refused`, `unlisted`, `unbonded`,
        # `banned`, `throttled`
        self.counters: dict[str, list[int]] = {}
        self.states: list[tuple[float, str, str]] = []
        self.refreshed = 0
        self._counted: set[str] = set()  # the transactions counted in `seen` here
        check, verified, simulate = frame._check_claim, frame.proof_verified, frame._simulate
        insert, remove = frame._insert, frame._remove
        bond = defence.bond

        def check_claim(tx: FrameTx) -> None:
            claim = tx.claim
            if claim is not None:
                issuer = self.issuers.of(claim)
                listed = self.defence.listed
                if listed is not None and issuer not in listed:
                    self.counts["unlisted", load_of(tx)] += 1
                    raise TxError(UNLISTED)
                if self.defence.memory is not None and (issuer, frame.epoch()) in self.closed:
                    self.counts["refused", load_of(tx)] += 1
                    raise TxError(REFUSED)
                if bond is not None:
                    self.refresh(node.now)
                    if issuer not in bond.bonded:
                        self.counts["unbonded", load_of(tx)] += 1
                        raise TxError(UNBONDED)
                    state = self.state(issuer)
                    if state == BANNED:  # REPUTATION-010
                        self.counts["banned", load_of(tx)] += 1
                        raise TxError(E.ErrEntityBanned)
                    if state == THROTTLED and self.pending(issuer) >= bond.config.throttled_entity_mempool_count:
                        self.counts["throttled", load_of(tx)] += 1  # REPUTATION-020
                        raise TxError(E.ErrEntityThrottled)
                self.counts["ticket", load_of(tx)] += 1
            check(tx)

        def proof_verified(tx: FrameTx, failed: bool) -> None:
            verified(tx, failed)
            self.see(tx)
            if failed and tx.claim is not None and self.defence.memory is not None:
                key = (self.issuers.of(tx.claim), frame.epoch())
                self.failed[key] += 1
                if self.failed[key] >= self.defence.memory and key not in self.closed:
                    self.closed[key] = node.now

        def simulated(tx, *args, **kwargs):
            self.counts["prefix", load_of(tx)] += 1
            return simulate(tx, *args, **kwargs)

        def inserted(e) -> None:
            insert(e)
            self.see(e.tx)

        def removed(tx_hash: str, reason: str, *args, **kwargs) -> None:
            tx = frame.entries[tx_hash].tx
            remove(tx_hash, reason, *args, **kwargs)
            if bond is not None and reason == "stale_nonce" and tx.hash in self._counted:  # included (AM-13)
                self.bump(self.issuers.of(tx.claim), included=1)

        frame._check_claim, frame.proof_verified, frame._simulate = check_claim, proof_verified, simulated
        if bond is not None:
            frame._insert, frame._remove = inserted, removed

    # --- under a bond: ERC-8421's reputation for ticket paymasters (AM-13) --------------------------

    def state(self, issuer: str) -> str:
        cfg = self.defence.bond.config
        seen, included = self.counters.get(issuer, (0, 0))
        m = seen // cfg.min_inclusion_rate_denominator
        if m > included + cfg.ban_slack:
            return BANNED
        if included + cfg.throttling_slack < m:
            return THROTTLED
        return ACTIVE

    def pending(self, issuer: str) -> int:
        """The pending transactions here whose tickets `issuer`'s paymaster backs."""
        return sum(1 for e in self.frame.entries.values()
                   if e.tx.claim is not None and self.issuers.of(e.tx.claim) == issuer)

    def bump(self, issuer: str | None, seen: int = 0, included: int = 0) -> None:
        if issuer is None or self.defence.bond is None:
            return
        self.refresh(self.node.now)
        before = self.state(issuer)
        c = self.counters.setdefault(issuer, [0, 0])
        c[0] += seen
        c[1] += included
        if self.state(issuer) != before:
            self.states.append((self.node.now, issuer, self.state(issuer)))

    def see(self, tx: FrameTx) -> None:
        """`seen`, once for each transaction under a ticket whose proof this node checked or which it admitted."""
        if tx.claim is not None and tx.hash not in self._counted and self.defence.bond is not None:
            self._counted.add(tx.hash)
            self.bump(self.issuers.of(tx.claim), seen=1)

    def refresh(self, now: float) -> None:
        """REPUTATION-010's refresh, every `refresh_seconds` of the run, counted from 0."""
        cfg = self.defence.bond.config
        while self.refreshed < int(now // cfg.refresh_seconds):
            self.refreshed += 1
            for issuer, c in self.counters.items():
                before = self.state(issuer)
                c[0], c[1] = c[0] * 23 // 24, c[1] * 23 // 24
                if self.state(issuer) != before:
                    self.states.append((self.refreshed * cfg.refresh_seconds, issuer, self.state(issuer)))

    def time_in(self, issuer: str, state: str, end: float) -> float:
        """Seconds of the run up to `end` that `issuer` spent in `state` here."""
        self.refresh(end)
        total, current, since = 0.0, ACTIVE, 0.0
        for t, who, s in self.states:
            if who != issuer or t > end:
                continue
            if current == state:
                total += t - since
            current, since = s, t
        return total + (end - since if current == state else 0.0)


def guard(sim, defences: Callable[[str], Defence], issuers: Issuers) -> dict[str, Guard]:
    """Install a guard on every node, its defence by node name."""
    return {name: Guard(node, defences(name), issuers) for name, node in sim.net.nodes.items()}


class JunkProofs(Load):
    """An adversary who hands every node mode 0 wrappers whose proofs do not verify, each carrying a valid ticket.

    Every `every` seconds from `start` until `stop`, offset by `offset`
    within the period, it makes `count` transactions, each from a fresh
    sender with one leanSTARK dependency and a valid claim for its slot in
    the epoch of the node's head (CG-2), paid by the issuer's paymaster
    (`sponsor` shape, the scenario funds it), and hands each node a wrapper
    of each whose proof fails. Its tickets come from `issuers` in order: a
    self-issuer deploys them, a holder of honest tickets buys them. With
    `rotate`, when a node answers that an issuer is refused there, it moves
    to its next issuer at that node and sends again, until it has none left
    in that epoch, and starts from its first again in the next, since
    issuer memory closes an issuer for an epoch and a bond's refresh may
    reopen one; it moves on from a banned paymaster the same way. Without
    `rotate`, it keeps to the first.

    `sent` counts the wrappers handed to nodes, `tickets` the claims it made,
    `used` the issuers it reached, and `answers` the answers by code.
    """

    def __init__(self, name: str, *, issuers: list[str], registry: Issuers, count: int, every: float,
                 offset: float = 0.0, rotate: bool = False, tip: int = 10_000_000_000, start: float = 0.0,
                 stop: float = float("inf")):
        super().__init__(name, rate=0.0, senders=[], tip=fixed(tip), start=start, stop=stop)
        self.issuers, self.registry = issuers, registry
        self.count, self.every, self.offset, self.rotate = count, every, offset, rotate
        self.sent = 0
        self.tickets = 0
        self.used: set[str] = set()
        self.answers: Counter = Counter()
        self._next = 0
        self._at: dict[tuple[str, int], int] = {}  # by node and epoch, the index of the issuer it uses there

    def attach(self, sim) -> None:
        super().attach(sim)
        first = self.start + (self.offset - self.start) % self.every
        sim.sched.at(first, lambda: self._round(sim))

    def _round(self, sim) -> None:
        if sim.sched.now >= self.stop:
            return
        for _ in range(self.count):
            self._one(sim)
        sim.sched.at(sim.sched.now + self.every, lambda: self._round(sim))

    def _one(self, sim) -> None:
        self._next += 1
        sender = f"{self.name}-s{self._next}"
        for node in sim.net.nodes.values():
            where = (node.name, node.pool.frame.epoch())
            while True:
                at = self._at.get(where, 0)
                if at >= len(self.issuers):
                    break
                answer = self._send(sim, node, sender, self.issuers[at])
                if answer not in (REFUSED, E.ErrEntityBanned) or not self.rotate:
                    break
                self._at[where] = at + 1

    def _send(self, sim, node, sender: str, issuer: str) -> str:
        pool = node.pool.frame
        head = pool.head
        claim = Claim(sender, 0, head.timestamp // pool.config.claim_epoch, salt=f"{self.name}-{self._next}-{issuer}")
        if claim not in self.registry.named:
            self.registry.name(claim, issuer)
            self.tickets += 1
        self.used.add(issuer)
        tip = self.tip(self.rng)
        tx = backed_tx("sponsor", sender, issuer, max_fee=2 * head.next_base_fee() + tip, tip=tip,
                       label=f"{self.name}-{self._next}-{issuer}", scheme="stark", claim=claim,
                       expiry_verifier=sim.scenario.frame_pool.expiry_verifier)
        wrapper = wrap([tx])
        wrapper = replace(wrapper, proofs=(False,) * len(wrapper.deps))
        self.sent += 1
        answer = node.submit_wrapper(wrapper, origin=self.name)
        answer = answer if isinstance(answer, str) else answer[0]
        self.answers[answer] += 1
        return answer
