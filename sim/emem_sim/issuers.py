"""Ticket issuers, and two defences a node might run against a self-issuer's junk proofs (decision record 0059).

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

Both refuse in CG-2's place, before the ticket's signature is checked and
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

from emem import Claim, FrameTx, wrap
from emem.errors import TxError

from .workload import Load, backed_tx, fixed

REFUSED = "ErrIssuerRefused"
UNLISTED = "ErrIssuerUnlisted"


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
class Defence:
    """What a node runs: `memory`, the failed proofs under one issuer that close it for the epoch, or None;
    `listed`, the issuers it accepts, or None for every one."""

    memory: int | None = None
    listed: frozenset[str] | None = None


def load_of(tx: FrameTx) -> str:
    """The load that made `tx`, the first word of its label."""
    return tx.label.split("-", 1)[0]


class Guard:
    """One node's defence, installed on its frame pool: CG-2's checks with the issuer's first, CG-4's record by
    issuer, and the counts. `closed` holds, by (issuer, epoch), the time it closed at this node."""

    def __init__(self, node, defence: Defence, issuers: Issuers):
        self.node, self.defence, self.issuers = node, defence, issuers
        frame = node.pool.frame
        self.frame = frame
        self.failed: Counter = Counter()  # (issuer, epoch): proofs that failed under its tickets here
        self.closed: dict[tuple[str, int], float] = {}
        self.counts: Counter = Counter()  # (event, load): `ticket`, `prefix`, `refused`, `unlisted`
        check, verified, simulate = frame._check_claim, frame.proof_verified, frame._simulate

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
                self.counts["ticket", load_of(tx)] += 1
            check(tx)

        def proof_verified(tx: FrameTx, failed: bool) -> None:
            verified(tx, failed)
            if failed and tx.claim is not None and self.defence.memory is not None:
                key = (self.issuers.of(tx.claim), frame.epoch())
                self.failed[key] += 1
                if self.failed[key] >= self.defence.memory and key not in self.closed:
                    self.closed[key] = node.now

        def simulated(tx, *args, **kwargs):
            self.counts["prefix", load_of(tx)] += 1
            return simulate(tx, *args, **kwargs)

        frame._check_claim, frame.proof_verified, frame._simulate = check_claim, proof_verified, simulated


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
    issuer memory closes an issuer for an epoch; without, it keeps to the
    first.

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
                if answer != REFUSED or not self.rotate:
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
