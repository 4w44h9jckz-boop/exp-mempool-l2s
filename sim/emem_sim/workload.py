"""Who sends what, and when.

A load is a Poisson process of submissions to random nodes. Wallets price as
most do: a tip drawn from the load's distribution and a fee cap of twice the
next base fee plus the tip. A wallet uses the higher of its own next nonce and
the chain's (`Simulation.wallet_nonce`, shared by every load), so a transaction
the network loses leaves a gap behind it, as it would for a real wallet that
does not resubmit. Wallets never bump the fee of a stuck transaction, except
`BumpLoad`'s and the users of a `SharedSenderLoad` with `patience`.

Each load draws from two random streams of its own, seeded from the scenario's
seed and the load's name: `rng` for what is asked (arrival times, senders,
tips) and `routing` for where it is sent. The network and the chain draw from
the simulation's stream. So two runs that differ only in a pool profile or a
submission rule are offered the same demand, and a difference between them is
the rule's and not the dice's.
"""

from __future__ import annotations

import bisect
import hashlib
import math
import random
from collections import Counter
from dataclasses import dataclass, field, replace
from typing import Callable

from emem import EIP_8141, GETH, Claim, Dependency, Frame, FrameTx, SealedTx, Signature, Tx, Wrapper, wrap
from emem.dependencies import union
from emem.framepool.matcha import charge
from emem.framepool.prefix import analyse
from emem.recentroots import TUPLE_BYTES, source_id
from emem.sealed import fees
from emem.tx import LEANSPHINCS, LEANSTARK, SET_CODE, intrinsic_gas

SCHEMES = {"sphincs": (LEANSPHINCS, 3000), "stark": (LEANSTARK, 30000)}  # EIP-8288 verification gas


def fixed(value: int) -> Callable[[random.Random], int]:
    return lambda rng: value


def uniform(lo: int, hi: int) -> Callable[[random.Random], int]:
    return lambda rng: rng.randint(lo, hi)


def one_of(*values: int) -> Callable[[random.Random], int]:
    return lambda rng: rng.choice(values)


@dataclass
class Load:
    name: str
    rate: float  # submissions per second
    senders: list[str]
    tip: Callable[[random.Random], int] = field(default=uniform(1_000_000, 3_000_000_000))
    start: float = 0.0
    stop: float = float("inf")
    fee_multiplier: int = 2

    def make(self, sim, sender: str):
        raise NotImplementedError

    def attach(self, sim) -> None:
        """Called once, when the load is scheduled."""
        self.rng = random.Random(f"{sim.scenario.seed}/{self.name}/arrivals")
        self.routing = random.Random(f"{sim.scenario.seed}/{self.name}/routing")

    def arrive(self, sim) -> None:
        """One Poisson arrival: a random sender's next transaction, to a random node."""
        sender = self.rng.choice(self.senders)
        tx = self.make(sim, sender)
        if tx is not None:
            node = self.routing.choice(list(sim.net.nodes.values()))
            sim.recorder.submitted(tx, sim.sched.now, node.name)
            node.submit(tx)

    def fee_cap(self, sim, tip: int) -> int:
        return self.fee_multiplier * sim.chain.head.next_base_fee() + tip


class TransferLoad(Load):
    """Plain type 2 transfers. `gas` is each one's execution gas, or draws it after the tip, and `state` is
    EIP-8037 state gas it adds to the limit and uses, or draws it after the gas (MD-5, decision record 0043)."""

    def __init__(self, *args, gas: int | Callable[[random.Random], int] = 21000,
                 state: int | Callable[[random.Random], int] = 0, **kwargs):
        super().__init__(*args, **kwargs)
        self.gas = gas
        self.state = state

    def make(self, sim, sender: str):
        nonce = sim.wallet_nonce(sender)
        tip = self.tip(self.rng)
        gas = self.gas(self.rng) if callable(self.gas) else self.gas
        state = self.state(self.rng) if callable(self.state) else self.state
        return Tx(sender, nonce=nonce, gas=gas + state, max_fee=self.fee_cap(sim, tip), tip=tip,
                  label=f"{self.name}-{sender}-{nonce}", state_gas_used=state or None)


def bump_fees(tip: int, cap: int, bump: int, base: int = 0, limit: int | None = None) -> tuple[int, int] | None:
    """A replacement's tip and fee cap: each raised by `bump` percent, rounded up, the cap to at least `base`
    plus the new tip and to at most `limit`. None if that cap is not `bump` percent above `cap`, or is below the
    tip, so that NP-11 would refuse it."""
    new_tip = -(-tip * (100 + bump) // 100)
    least = -(-cap * (100 + bump) // 100)
    new_cap = max(least, base + new_tip)
    if limit is not None:
        new_cap = min(new_cap, limit)
    if new_cap < least or new_tip > new_cap:
        return None
    return new_tip, new_cap


class Transfer:
    """One user's transfer from a `BumpLoad`, and every version its wallet sent."""

    def __init__(self, sender: str, nonce: int, requested_at: float, limit: int | None):
        self.sender = sender
        self.nonce = nonce
        self.requested_at = requested_at
        self.limit = limit
        self.versions: list[Tx] = []
        self.blocks = 0  # blocks its wallet's node imported without it since its last version was sent


class BumpLoad(TransferLoad):
    """Plain transfers from wallets that re-price, and from users who do not pay above a price.

    Each sender's wallet sends to one node, drawn when it first sends, and
    watches it. With `patience`, once that node has imported `patience` blocks
    without the wallet's oldest unincluded transaction, the wallet replaces it
    at the same nonce, sends the replacement to the same node, and counts
    again; with `every`, it does so for each unincluded transaction, each
    counted from its own last version. The replacement raises the tip and the fee cap by `bump` percent
    each, rounded up, and with `reprice` raises the fee cap further, to
    `fee_multiplier` times the next base fee plus the new tip, as a wallet's
    speed-up does. NP-11 admits a replacement only if both fields rise by
    `price_bump` percent. With `limit`, a draw in wei a gas from a stream of
    the load's own, a user pays at most that much a gas, base fee and tip
    together: it does not send while the next base fee plus its tip is above
    it, its fee cap is at most it, and its wallet does not bump past it.
    Without `patience` and `limit` the demand is `TransferLoad`'s, sent to one
    node a sender.
    """

    def __init__(self, *args, patience: int | None = None, bump: int = 10, reprice: bool = False,
                 every: bool = False, limit: Callable[[random.Random], int] | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.patience = patience
        self.bump = bump
        self.every = every
        self.reprice = reprice
        self.limit = limit
        self.transfers: list[Transfer] = []
        self.priced_out = 0  # arrivals whose user did not send
        self.answers: Counter = Counter()  # what the wallet's node said to each replacement

    def attach(self, sim) -> None:
        super().attach(sim)
        self.limits = random.Random(f"{sim.scenario.seed}/{self.name}/limits")
        self.home: dict[str, str] = {}
        self.watched: dict[str, list[str]] = {}
        self.open: dict[str, list[Transfer]] = {}
        for node in sim.net.nodes.values():
            node.import_hooks.append(lambda node, block: self._import(sim, node))

    def arrive(self, sim) -> None:
        sender = self.rng.choice(self.senders)
        tip = self.tip(self.rng)
        limit = self.limit(self.limits) if self.limit is not None else None
        if limit is not None and sim.chain.head.next_base_fee() + tip > limit:
            self.priced_out += 1
            return
        cap = self.fee_cap(sim, tip) if limit is None else min(self.fee_cap(sim, tip), limit)
        nonce = sim.wallet_nonce(sender)
        tx = Tx(sender, nonce=nonce, gas=self.gas, max_fee=cap, tip=tip, label=f"{self.name}-{sender}-{nonce}")
        transfer = Transfer(sender, nonce, sim.sched.now, limit)
        transfer.versions.append(tx)
        self.transfers.append(transfer)
        self.open.setdefault(sender, []).append(transfer)
        if sender not in self.home:
            self.home[sender] = self.routing.choice(list(sim.net.nodes))
            self.watched.setdefault(self.home[sender], []).append(sender)
        node = sim.net.nodes[self.home[sender]]
        sim.recorder.submitted(tx, sim.sched.now, node.name)
        node.submit(tx)

    def _import(self, sim, node) -> None:
        for sender in self.watched.get(node.name, ()):
            chain_nonce = node.pool.state.nonce(sender)
            waiting = [t for t in self.open[sender] if t.nonce >= chain_nonce]
            self.open[sender] = waiting
            for t in waiting:
                t.blocks += 1
            if self.patience is None:
                continue
            base = self.fee_multiplier * sim.chain.head.next_base_fee() if self.reprice else 0
            for t in waiting if self.every else waiting[:1]:
                if t.blocks < self.patience:
                    continue
                last = t.versions[-1]
                fees = bump_fees(last.tip, last.max_fee, self.bump, base, t.limit)
                if fees is None:
                    continue
                tx = replace(last, tip=fees[0], max_fee=fees[1],
                             label=f"{self.name}-{sender}-{t.nonce}.{len(t.versions)}")
                t.versions.append(tx)
                t.blocks = 0
                sim.recorder.submitted(tx, sim.sched.now, node.name)
                self.answers[node.submit(tx)] += 1

    def stuck(self, sim) -> int:
        """Senders with a transfer the chain has not included."""
        return sum(any(t.nonce >= sim.chain.state.nonce(s) for t in ts) for s, ts in self.open.items())


class HotWallet(TransferLoad):
    """Plain transfers from senders that each send many, such as an exchange's hot wallet (NP-6).

    Each sender's wallet sends every transfer it is asked for to one node,
    drawn when the load is attached, and watches it. `rule` says how it sends
    while that node's head shows the sender without code, and `delegated` (by
    default `rule`) once it shows a delegation:

    - `at once`: each transfer when it is asked for, at the next nonce;
    - `serial`: one transaction in flight, the next when its node imports the
      block that includes the last, which is all NP-6 lets a delegated sender
      keep;
    - `batch`: as `serial`, but each transaction carries every transfer
      waiting, up to as many as the EIP-7825 cap allows, as a delegated
      account's code can make several calls; it is priced at `gas` a transfer,
      as if each were sent alone, and at the highest tip among them.

    A transaction its node refuses waits, with every later transfer, and is
    sent again after the node's next import; so is a transfer whose nonce a
    block used for something else, as an EIP-7702 authorization does when it
    bumps its authority's nonce. The fee cap is set when a transaction is
    sent. `authorize` signs a sender's authorization for a sponsor (`Upgrade`)
    at the sender's next nonce, and `sign` says what the wallet does around it:

    - `next`: it signs at once and keeps sending;
    - `pause`: it signs at once and sends nothing more for that sender until
      its node's head shows the delegation or the sponsor reports the
      authorization skipped (`resume`);
    - `drain`: as `pause`, but it signs only once nothing it sent for that
      sender is waiting for a block its node has imported, so that no
      transaction of its own can take the authorization's nonce.

    `answers` counts what the
    wallet's node said to every send, `lost` the transfers sent again because
    their nonce was used, and `txs` the transactions sent.
    """

    RULES = ("at once", "serial", "batch")
    SIGNING = ("next", "pause", "drain")

    def __init__(self, *args, rule: str = "at once", delegated: str | None = None, sign: str = "next", **kwargs):
        super().__init__(*args, **kwargs)
        if rule not in self.RULES or (delegated or rule) not in self.RULES or sign not in self.SIGNING:
            raise ValueError((rule, delegated, sign))
        self.rule = rule
        self.delegated = delegated or rule
        self.sign = sign
        self.max_batch = GETH.max_tx_gas // self.gas
        self.transfers: list[Transfer] = []
        self.answers: Counter = Counter()
        self.lost = 0
        self.txs = 0

    def attach(self, sim) -> None:
        super().attach(sim)
        self.home = {s: self.routing.choice(list(sim.net.nodes)) for s in self.senders}
        self.watched: dict[str, list[str]] = {}
        for sender, name in self.home.items():
            self.watched.setdefault(name, []).append(sender)
        self.sent: dict[str, list[Transfer]] = {}  # by sender: sent, and not in a block its node imported
        self.queue: dict[str, list[Transfer]] = {s: [] for s in self.senders}
        self.inflight: dict[str, int] = {}  # by sender: the nonce of the last transaction sent
        self.next_nonce: dict[str, int] = {}
        self.paused: set[str] = set()
        for node in sim.net.nodes.values():
            node.import_hooks.append(lambda node, block: self._import(sim, node, block))

    def arrive(self, sim) -> None:
        sender = self.rng.choice(self.senders)
        transfer = Transfer(sender, -1, sim.sched.now, None)
        transfer.tip = self.tip(self.rng)
        self.transfers.append(transfer)
        self.queue[sender].append(transfer)
        self._send(sim, sender)

    def sending(self, node, sender: str) -> str:
        """The rule the wallet sends `sender`'s transfers by, from its node's head."""
        return self.delegated if node.pool.state.code(sender) != "" else self.rule

    def authorize(self, sim, sender: str) -> int | None:
        """The nonce `sender`'s authorization for a sponsor carries, its next, or None while `drain` waits."""
        if self.sign != "next":
            self.paused.add(sender)
        if self.sign == "drain" and self.sent.get(sender):
            return None
        return max(self.next_nonce.get(sender, 0), sim.net.nodes[self.home[sender]].pool.state.nonce(sender))

    def resume(self, sim, sender: str) -> None:
        self.paused.discard(sender)
        self._send(sim, sender)

    def _send(self, sim, sender: str) -> None:
        if sender in self.paused:
            return
        node = sim.net.nodes[self.home[sender]]
        chain = node.pool.state.nonce(sender)
        if self.inflight.get(sender, chain) < chain:
            del self.inflight[sender]
        queue = self.queue[sender]
        rule = self.sending(node, sender)
        while queue:
            if sender in self.inflight and rule != "at once":
                return
            n = min(len(queue), self.max_batch) if rule == "batch" else 1
            group = queue[:n]
            nonce = max(self.next_nonce.get(sender, 0), chain)
            tip = max(t.tip for t in group)
            tx = Tx(sender, nonce=nonce, gas=self.gas * n, max_fee=self.fee_cap(sim, tip), tip=tip,
                    label=f"{self.name}-{sender}-{nonce}.{self.txs}")
            self.txs += 1
            sim.recorder.submitted(tx, sim.sched.now, node.name)
            answer = node.submit(tx)
            self.answers[answer] += 1
            if answer != "ok":
                return
            del queue[:n]
            for t in group:
                t.nonce = nonce
                t.versions.append(tx)
            self.sent.setdefault(sender, []).extend(group)
            self.next_nonce[sender] = nonce + 1
            self.inflight[sender] = nonce

    def _import(self, sim, node, block) -> None:
        senders = self.watched.get(node.name, ())
        if not senders:
            return
        included = {tx.hash for tx in block.txs}
        for sender in senders:
            chain = node.pool.state.nonce(sender)
            sent = [t for t in self.sent.get(sender, ()) if t.versions[-1].hash not in included]
            lost = [t for t in sent if t.nonce < chain]
            self.sent[sender] = [t for t in sent if t not in lost]
            if lost:  # sent again after the transfers still pending, whose nonces are still good
                self.lost += len(lost)
                self.queue[sender] = sorted(lost + self.queue[sender], key=lambda t: t.requested_at)
                self.next_nonce[sender] = max([chain] + [t.nonce + 1 for t in self.sent[sender]])
                if not self.sent[sender]:
                    self.inflight.pop(sender, None)
            if sender in self.paused and node.pool.state.code(sender) != "":
                self.paused.discard(sender)
            self._send(sim, sender)


class Upgrade(Load):
    """A sponsor's EIP-7702 authorizations for a `HotWallet`'s senders, `batch` of them a type 4 transaction.

    From `start`, the sponsor asks the wallet for the authorizations of the
    next `batch` of its senders not yet delegated, each at its sender's next
    nonce (`HotWallet.authorize`), and sends a type 4 transaction carrying
    them, to `delegate`, from `sponsor`, at a tip of `upgrade_tip` and a gas
    limit of its intrinsic gas (FEE-3) and `exec_gas`, to a node drawn once.
    After every block that node imports: if the block includes the
    transaction, each authority its head shows delegated is done, and each
    other, whose authorization was skipped (BB-5), keeps its place at the
    front of the line and its wallet resumes; then the next batch is asked
    for. If the block does not include it and the node does not hold it, as
    when it refused it (NP-7 refuses an authority with more than one
    transaction in the pool), the sponsor asks the same senders again and
    sends it again; while any of them will not sign yet, it sends nothing and
    asks again after the next import. `batches` holds, for each batch, its authorities, when it
    was first sent, every transaction and answer, when it was first admitted
    and included, and the authorities applied and skipped; `done_at` when the
    sponsor's node first showed each sender delegated.
    """

    def __init__(self, name: str, *, sponsor: str, wallet: HotWallet, batch: int = 1, delegate: str = "wallet-v1",
                 upgrade_tip: int = 2_000_000_000, exec_gas: int = 0, start: float = 0.0,
                 stop: float = float("inf"), fee_multiplier: int = 2):
        super().__init__(name, rate=0.0, senders=[sponsor], tip=fixed(upgrade_tip), start=start, stop=stop,
                         fee_multiplier=fee_multiplier)
        self.sponsor = sponsor
        self.wallet = wallet
        self.line = list(wallet.senders)
        self.batch = batch
        self.delegate = delegate
        self.upgrade_tip = upgrade_tip
        self.exec_gas = exec_gas
        self.batches: list[dict] = []
        self.done_at: dict[str, float] = {}

    def attach(self, sim) -> None:
        super().attach(sim)
        self.node = self.routing.choice(list(sim.net.nodes))
        sim.net.nodes[self.node].import_hooks.append(lambda node, block: self._import(sim, node, block))
        sim.sched.at(self.start, lambda: self._next(sim))

    def _next(self, sim) -> None:
        if not self.line or sim.sched.now >= self.stop:
            return
        self.batches.append({"authorities": tuple(self.line[:self.batch]), "sent_at": sim.sched.now, "txs": [],
                             "answers": [], "admitted_at": None, "included_at": None, "applied": (), "skipped": ()})
        self._send(sim)

    def _send(self, sim) -> None:
        b = self.batches[-1]
        node = sim.net.nodes[self.node]
        nonces = [self.wallet.authorize(sim, a) for a in b["authorities"]]
        if None in nonces:
            return
        auths = tuple(zip(b["authorities"], nonces))
        gas = intrinsic_gas(Tx(self.sponsor, authorities=auths)) + self.exec_gas
        tx = Tx(self.sponsor, nonce=node.pool.state.nonce(self.sponsor), gas=gas,
                max_fee=self.fee_cap(sim, self.upgrade_tip), tip=self.upgrade_tip, type=SET_CODE,
                authorities=auths, delegate=self.delegate, label=f"{self.name}-{len(self.batches)}.{len(b['txs'])}")
        sim.recorder.submitted(tx, sim.sched.now, node.name)
        answer = node.submit(tx)
        b["txs"].append(tx)
        b["answers"].append(answer)
        if answer == "ok" and b["admitted_at"] is None:
            b["admitted_at"] = sim.sched.now

    def _import(self, sim, node, block) -> None:
        if not self.batches or self.batches[-1]["included_at"] is not None:
            return
        b = self.batches[-1]
        last = b["txs"][-1] if b["txs"] else None
        if last is not None and any(tx.hash == last.hash for tx in block.txs):
            b["included_at"] = sim.sched.now
            b["applied"] = tuple(a for a in b["authorities"] if node.pool.state.code(a) != "")
            b["skipped"] = tuple(a for a in b["authorities"] if a not in b["applied"])
            for a in b["applied"]:
                self.done_at[a] = sim.sched.now
                self.line.remove(a)
            for a in b["skipped"]:
                self.wallet.resume(sim, a)
            self._next(sim)
        elif last is None or node.pool.get(last.hash) is None:
            self._send(sim)


class FrameLoad(Load):
    """Self-paying EIP-8141 frame transactions, `[self_verify, sender]`, from default-code senders.

    A wallet with an unincluded frame transaction waits for it rather than send
    another, because the public mempool would refuse a second one (FP-12).
    `sponsor` makes them `[only_verify, pay, sender]` paid by a default-code
    sponsor instead.
    """

    def __init__(self, *args, exec_gas: int = 50000, sponsor: str | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.exec_gas = exec_gas
        self.sponsor = sponsor
        self.outstanding: dict[str, int] = {}
        self.skipped = 0

    def make(self, sim, sender: str):
        seq = sim.chain.state.nonce(sender)
        if self.outstanding.get(sender, -1) >= seq:
            self.skipped += 1
            return None
        self.outstanding[sender] = seq
        tip = self.tip(self.rng)
        if self.sponsor is None:
            frames = (Frame(mode=1, flags=3, exec_gas=30000), Frame(mode=2, exec_gas=self.exec_gas))
            sigs = (Signature(),)
        else:
            frames = (Frame(mode=1, flags=2, exec_gas=30000), Frame(mode=1, flags=1, target=self.sponsor, exec_gas=30000),
                      Frame(mode=2, exec_gas=self.exec_gas))
            sigs = (Signature(), Signature(signer=self.sponsor))
        return FrameTx(sender, frames, nonce_seq=seq, signatures=sigs, max_fee=self.fee_cap(sim, tip), tip=tip,
                       label=f"{self.name}-{sender}-{seq}")


class ProofLoad(FrameLoad):
    """`FrameLoad`'s transactions, each carrying a valid proof under one shared key, which a node with
    `batch_window` verifies before admitting it (decision record 0025)."""

    def make(self, sim, sender: str):
        tx = super().make(sim, sender)
        if tx is not None:
            sim.net.proofs[tx.hash] = True
        return tx


class InvalidProofLoad(FrameLoad):
    """Frame transactions whose proof fails, each from a fresh sender and handed to every target node at once.

    Every node refuses each one after verifying it, so each spoils one batch at every node it reaches, and
    none is relayed or pays anything (decision record 0025)."""

    def __init__(self, *args, targets: list[str] | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.targets = targets
        self.sent = 0

    def arrive(self, sim) -> None:
        self.sent += 1
        tx = FrameLoad.make(self, sim, f"{self.name}{self.sent}")
        sim.net.proofs[tx.hash] = False
        names = self.targets if self.targets is not None else list(sim.net.nodes)
        sim.recorder.submitted(tx, sim.sched.now, names[0])
        for name in names:
            sim.net.nodes[name].submit(tx)


def load_floor(pool, tx: FrameTx) -> int:
    """The least effective tip MA-13 asks of `tx` at `pool` now: 0 for a baseline or with no `load_price`."""
    frame = pool.frame
    price = frame.config.load_price
    if not frame.matcha or not price or tx.sender not in frame.by_sender:
        return 0
    c = charge(tx, analyse(tx, frame.config), frame.config.safety_factor)
    return -(-price * (c + frame.load(tx.sender)) // c)


class Spend:
    """One user's request for a spend from a shared sender, and what became of it."""

    def __init__(self, index: int, label: str, sender: str, requested_at: float, tip: int):
        self.index = index
        self.label = label
        self.sender = sender
        self.requested_at = requested_at
        self.tip = tip  # what the user offers
        self.drawn = tip  # what the user drew, before any floor
        self.tx: FrameTx | None = None
        self.home: str | None = None  # the node whose blocks the submitter watches
        self.answers: list[str] = []  # what the node it was submitted to said, each time
        self.copies: list[FrameTx] = []  # CopiesLoad: every copy handed out, in order
        self.versions: list[FrameTx] = []  # with `patience`: every version sent, re-priced by its user
        self.blocks = 0  # with `patience`: blocks its watched node imported without it since its last version


class SharedSenderLoad(Load):
    """Spends from shared senders: a privacy pool that is the sender of every user's withdrawal.

    The pool contract is the sender, verifies the spend in a
    `self_verify` frame and pays for it, a `SENDER` frame makes the transfer,
    and one signature entry by the user commits the fees. With `expiry` set, an
    expiry frame comes first, with a deadline `expiry` seconds after the spend
    is first sent and a limit of 100 gas, which covers the 51 that the
    canonical expiry verifier's success path costs at ordinary opcode prices
    (EIP-8141, Expiry Verifier Frame); the scenario must then give the expiry
    verifier its code. The spend's nullifier is its EIP-8250 nonce key, fresh
    for every spend and used at sequence 0, so FP-7 always passes and the
    per-sender rule decides admission. The key is the spend's index plus one,
    or with `key_bytes` 32 a 256-bit hash of its label, as a nullifier would
    be. Each arrival is one user asking for a spend from one of `senders`,
    which must hold code (`Scenario.code`) and a balance.

    `reads` says what the pool's `self_verify` frame reads of the pool's
    storage (`04-matcha.md`, MA-14): `none`; `own`, the slot named by the
    spend's nullifier, expecting 0, as a pool that records its nullifiers in
    storage reads whether one is spent; or `root`, the slot `root_slot`,
    accepting any value, as a pool reads a root that every deposit rewrites
    (`SlotWriter`).

    `rule` says who submits:

    - `relayer`: one relayer per sender, at a fixed node, sends spends in the
      order they were asked for. With `serial` it keeps one spend outstanding
      and sends the next `wait` seconds after its node imports the block that
      includes it, which with `wait` 0 is `FrameLoad`'s waiting rule; without,
      it sends each spend at once, and when its node refuses one, stops and
      tries again after the next block. With `resend`, after every block it
      also takes back every spend it sent that is neither included nor held
      by its node, and sends it again in order; a pool under `matcha` drops
      spends that a sender's width cannot pay to re-run (MA-9) or that outlive
      the lifetime (MA-8).
    - `direct`: each user submits their own spend to a random node, of
      `targets` if given, and after every block that node imports without
      including it, submits it again to a random node. With `floor`, a user
      first reads the node's MA-13 load floor and offers the higher of its
      own tip and the floor (`04-matcha.md`).

    The fee cap is set when the spend is first sent, from the tip drawn when it
    was asked for. With `patience`, a spend's user re-prices it, since the
    fees are committed by the user's signature entry and not the submitter's:
    once the node that watches the spend (the relayer's, or the user's own)
    has imported `patience` blocks without it, the user signs a version with
    `BumpLoad`'s fees, which the relayer sends to its node in place of the old
    one, or the user sends to a random node. Without `patience` nobody bumps a
    fee.

    With `expiring`, a number of seconds, spends are in EIP-8266's
    expiring-nonce mode (`docs/spec/09-expiring-nonces.md`), which the
    scenario's frame pool profile must enable: the nonce key is the reserved
    `expiring_key` at sequence 0, an expiry frame comes first with a deadline
    `expiring` seconds after the timestamp of the head of the node the version
    is made for (the relayer's, or the one its user sends it to), and the
    nullifier lives in the pool's storage: the `self_verify` frame reads its
    slot, expecting 0, as with `reads` `own`, the spend writes it, and the
    frame's gas carries the mode's `expiring_nonce_gas` (EN-5). A spend is
    included once its slot is set. When a version can no longer make the next
    block, its deadline being below the watching node's head timestamp plus
    the slot time, its user signs a new one with a new deadline (decision
    record 0030); a relayer then sends that in order, and one that is not
    `serial` also takes back every spend its node has dropped, as `resend`
    does.
    """

    def __init__(self, *args, rule: str = "relayer", serial: bool = True, verify_gas: int = 15000,
                 verify_bytes: int = 160, exec_gas: int = 30000, exec_bytes: int = 292,
                 relayers: dict[str, str] | None = None, wait: float = 0.0, expiry: float | None = None,
                 key_bytes: int | None = None, resend: bool = False, targets: list[str] | None = None,
                 floor: bool = False, patience: int | None = None, bump: int = 10, reprice: bool = False,
                 reads: str = "none", root_slot: int = 0, expiring: int | None = None, state_gas: int = 0,
                 **kwargs):
        super().__init__(*args, **kwargs)
        self.state_gas = state_gas
        if reads not in ("none", "own", "root"):
            raise ValueError(reads)
        if expiring is not None and reads == "root":
            raise ValueError("an expiring spend reads its own nullifier")
        self.expiring = expiring
        self.reads = "own" if expiring is not None else reads
        self.root_slot = root_slot
        self.targets = targets
        self.floor = floor
        self.patience = patience
        self.bump = bump
        self.reprice = reprice
        if key_bytes not in (None, 32):
            raise ValueError(key_bytes)
        self.expiry = expiry
        self.key_bytes = key_bytes
        self.resend = resend or expiring is not None
        if rule not in ("relayer", "direct"):
            raise ValueError(rule)
        self.rule = rule
        self.serial = serial
        self.wait = wait
        self.verify_gas = verify_gas
        self.verify_bytes = verify_bytes
        self.exec_gas = exec_gas
        self.exec_bytes = exec_bytes
        self.relayer_nodes = relayers
        self.spends: list[Spend] = []
        self._queue: dict[str, list[Spend]] = {s: [] for s in self.senders}
        self._outstanding: dict[str, Spend | None] = {s: None for s in self.senders}
        self._ready_at: dict[str, float] = {s: 0.0 for s in self.senders}
        self._waiting: dict[str, list[Spend]] = {}  # direct: by the node watched
        self._sent: dict[str, list[Spend]] = {s: [] for s in self.senders}  # relayer, with resend

    def nullifier(self, spend: Spend) -> int:
        """The spend's nonce key, never key 0."""
        if self.key_bytes is None:
            return spend.index + 1
        digest = hashlib.blake2b(spend.label.encode(), digest_size=32).digest()
        return int.from_bytes(digest, "big") | 1 << 255

    def prefix_reads(self, spend: Spend) -> tuple:
        """What the spend's `self_verify` frame reads, by `reads`."""
        if self.reads == "own":
            return ((spend.sender, self.nullifier(spend), 0),)
        if self.reads == "root":
            return ((spend.sender, self.root_slot, None),)
        return ()

    def spend_tx(self, sim, spend: Spend, reads: tuple | None = None, node=None) -> FrameTx:
        """The spend as first sent; its prefix reads `reads`, or by default what `reads` names. With
        `expiring`, a version in the mode, its deadline from `node`'s head."""
        if reads is None:
            reads = self.prefix_reads(spend)
        cfg = sim.scenario.frame_pool
        verify_gas = self.verify_gas + (cfg.expiring_nonce_gas if self.expiring is not None else 0)
        # `state_gas` is the nullifier's: EIP-8250 charges a nonce key's first use to the payment-scoped
        # APPROVE, and a nullifier in storage is the SENDER frame's write (decision record 0043)
        in_storage = self.expiring is not None
        frames = (Frame(mode=1, flags=3, exec_gas=verify_gas, data_size=self.verify_bytes, approves=3,
                        reads=reads, state_gas=0 if in_storage else self.state_gas),
                  Frame(mode=2, target="token", exec_gas=self.exec_gas, data_size=self.exec_bytes,
                        state_gas=self.state_gas if in_storage else 0))
        if self.expiring is not None:
            deadline = node.pool.head.timestamp + self.expiring
            frames = (Frame(mode=1, target=cfg.expiry_verifier, exec_gas=100, data_size=8, deadline=deadline),) + frames
            n = len(spend.versions)
            return FrameTx(spend.sender, frames, nonce_keys=(cfg.expiring_key,), nonce_seq=0,
                           signatures=(Signature(signer=f"user-{spend.label}"),),
                           max_fee=self.fee_cap(sim, spend.tip), tip=spend.tip,
                           writes=((spend.sender, self.nullifier(spend), 1),),
                           label=spend.label if n == 0 else f"{spend.label}.{n}")
        if self.expiry is not None:
            deadline = int(sim.sched.now + self.expiry)
            frames = (Frame(mode=1, target=sim.scenario.frame_pool.expiry_verifier, exec_gas=100, data_size=8,
                            deadline=deadline),) + frames
        return FrameTx(spend.sender, frames, nonce_keys=(self.nullifier(spend),), nonce_seq=0,
                       signatures=(Signature(signer=f"user-{spend.label}"),),
                       max_fee=self.fee_cap(sim, spend.tip), tip=spend.tip, label=spend.label)

    def attach(self, sim) -> None:
        super().attach(sim)
        names = list(sim.net.nodes)
        if self.relayer_nodes is None:
            self.relayer_nodes = {s: names[i % len(names)] for i, s in enumerate(self.senders)}
        hook = self._relayer_import if self.rule == "relayer" else self._direct_import
        for node in sim.net.nodes.values():
            node.import_hooks.append(lambda node, block: hook(sim, node))

    def arrive(self, sim, node=None) -> Spend:
        """One user asks for a spend; under `direct`, it goes to `node` if given, else to a random node."""
        sender = self.rng.choice(self.senders)
        index = len(self.spends)
        spend = Spend(index, f"{self.name}-{index}", sender, sim.sched.now, self.tip(self.rng))
        self.spends.append(spend)
        if self.rule == "relayer":
            self._queue[sender].append(spend)
            self._relay(sim, sender)
        else:
            node = node if node is not None else self._random_node(sim)
            if self.floor:
                spend.tip = max(spend.tip, load_floor(node.pool, self.spend_tx(sim, spend, node=node)))
            spend.tx = self.spend_tx(sim, spend, node=node)
            spend.versions.append(spend.tx)
            spend.home = node.name
            self._waiting.setdefault(node.name, []).append(spend)
            self._submit(sim, spend, node)
        return spend

    def _random_node(self, sim):
        """A random node, of `targets` if given."""
        return sim.net.nodes[self.routing.choice(self.targets if self.targets is not None else list(sim.net.nodes))]

    def _submit(self, sim, spend: Spend, node) -> str:
        sim.recorder.submitted(spend.tx, sim.sched.now, node.name)
        answer = node.submit(spend.tx)
        spend.answers.append(answer)
        return answer

    def _included(self, node, spend: Spend) -> bool:
        if self.expiring is not None:
            return node.pool.state.storage(spend.sender, self.nullifier(spend)) != 0
        return node.pool.state.nonce_seq(spend.sender, spend.tx.nonce_keys[0]) > 0

    def _stale(self, sim, spend: Spend, node) -> bool:
        """With `expiring`: whether the spend's version can no longer make the next block on `node`'s head."""
        return self.expiring is not None and \
            spend.tx.frames[0].deadline < node.pool.head.timestamp + sim.scenario.chain.slot_time

    def _resign(self, sim, spend: Spend, node) -> None:
        """With `expiring`: the user signs a new version, its deadline from `node`'s head."""
        spend.tx = self.spend_tx(sim, spend, node=node)
        spend.versions.append(spend.tx)

    def _relay(self, sim, sender: str) -> None:
        node = sim.net.nodes[self.relayer_nodes[sender]]
        queue = self._queue[sender]
        if sim.sched.now < self._ready_at[sender]:
            return
        while queue and not (self.serial and self._outstanding[sender] is not None):
            spend = queue[0]
            if spend.tx is not None and self._included(node, spend):
                queue.pop(0)  # taken back, but another node's block has included it since
                continue
            if spend.tx is None:
                spend.tx = self.spend_tx(sim, spend, node=node)
                spend.versions.append(spend.tx)
                spend.home = node.name
            elif self._stale(sim, spend, node):
                self._resign(sim, spend, node)
            if self._submit(sim, spend, node) != "ok":
                return  # try again at the next block
            queue.pop(0)
            if self.serial:
                self._outstanding[sender] = spend
            elif self.resend:
                self._sent[sender].append(spend)

    def _relayer_import(self, sim, node) -> None:
        for sender, name in self.relayer_nodes.items():
            if name != node.name:
                continue
            if self.resend:
                sent = [sp for sp in self._sent[sender] if not self._included(node, sp)]
                lost = [sp for sp in sent if node.pool.get(sp.tx.hash) is None or self._stale(sim, sp, node)]
                self._sent[sender] = [sp for sp in sent if sp not in lost]
                if lost:
                    self._queue[sender] = sorted(lost + self._queue[sender], key=lambda sp: sp.index)
            spend = self._outstanding[sender]
            if spend is not None and self._included(node, spend):
                self._outstanding[sender] = None
                if self.wait > 0:
                    self._ready_at[sender] = sim.sched.now + self.wait
                    sim.sched.after(self.wait, lambda sender=sender: self._relay(sim, sender))
                    continue
            elif spend is not None and self._reprice(sim, spend):
                self._submit(sim, spend, node)
            elif spend is not None and self.expiring is not None:
                if self._stale(sim, spend, node):
                    self._resign(sim, spend, node)
                if node.pool.get(spend.tx.hash) is None:
                    self._submit(sim, spend, node)
            self._relay(sim, sender)

    def _direct_import(self, sim, node) -> None:
        watching = self._waiting.get(node.name)
        if not watching:
            return
        still = []
        for spend in watching:
            if not self._included(node, spend):
                still.append(spend)
                self._reprice(sim, spend)
                if self._stale(sim, spend, node):
                    self._resign(sim, spend, node)
                self._submit(sim, spend, self._random_node(sim))
        self._waiting[node.name] = still

    def _reprice(self, sim, spend: Spend) -> bool:
        """With `patience`, count a block without `spend` and, at `patience`, make its next version."""
        if self.patience is None:
            return False
        spend.blocks += 1
        if spend.blocks < self.patience:
            return False
        base = self.fee_multiplier * sim.chain.head.next_base_fee() if self.reprice else 0
        fees = bump_fees(spend.tx.tip, spend.tx.max_fee, self.bump, base)
        if fees is None:
            return False
        spend.tx = replace(spend.tx, tip=fees[0], max_fee=fees[1], label=f"{spend.label}.{len(spend.versions)}")
        spend.versions.append(spend.tx)
        spend.blocks = 0
        return True

    def backlog(self) -> int:
        """Spends asked for and not yet sent (relayer) or not yet included (direct)."""
        return sum(map(len, self._queue.values())) + sum(map(len, self._waiting.values()))


class JunkLoad(SharedSenderLoad):
    """An adversary at one node that, after every block its node imports, sends spends meant never to land.

    Each is a valid spend from `senders[0]` in `SharedSenderLoad`'s shape, with
    a fee cap that covers the next base fee and a tip of `tip`, below the
    builders' minimum, so that no builder includes it. After each block its
    own node imports, it sends up to `burst` to each node in `targets` (its own
    node by default; an adversary can peer with every node) and stops when
    every target refuses one. Two uses:

    - **Mass invalidation** (`setting` and `flipper` given): the sender is the
      adversary's own application, every junk prefix reads the setting slot
      `(address, slot)` expecting its value at the head, and an account the
      adversary controls, `flipper`, sends a transaction that writes the next
      value, at a tip that lands it in the next block, whenever its last one
      has landed. Every junk spend pending anywhere is then invalidated by one
      write, which is the first attack of ethresear.ch topic 25949.
    - **Width draining** (neither given): the sender is an honest shared
      sender, and the junk occupies its width (MATCHA) or its one pending slot
      (`one`). This is the post's second attack, without the FOCIL deterrent
      the post relies on, which the model does not have.

    The flip is 26,000 gas: 21,000 for the transaction and 5,000 for a cold
    `SSTORE` that changes a non-zero slot (EIP-2929's 2,100 cold access and
    2,900 for the write). The load draws no arrivals; `start` and `stop`
    bound when it acts.

    For mass invalidation two more shapes (`04-matcha.md`, MA-14): with
    `slots` above 1, junk spend $i$ reads slot `setting[1]` plus $i$ modulo
    `slots`; with several `senders`, junk spend $i$ comes from sender $i$
    modulo their number, an application of its own, and reads that slot of
    its own storage. With `flip_held` the flip writes, instead of the one
    setting, every setting that a junk spend its node holds reads, and none
    when it holds none, for 21,000 gas, 5,000 a slot, and 2,600 for each
    account after the first, EIP-2929's cold account access for the call
    that writes there.
    """

    def __init__(self, *args, node: str, burst: int = 100, targets: list[str] | None = None,
                 setting: tuple[str, int] | None = None, flipper: str | None = None,
                 flip_tip: int = 2_000_000_000, flip_gas: int = 26_000, slots: int = 1, flip_held: bool = False,
                 **kwargs):
        kwargs.setdefault("rate", 0.0)
        kwargs.setdefault("tip", fixed(1))
        super().__init__(*args, **kwargs)
        self.node = node
        self.targets = targets or [node]
        self.burst = burst
        self.setting = setting
        self.flipper = flipper
        self.flip_tip = flip_tip
        self.flip_gas = flip_gas
        self.slots = slots
        self.flip_held = flip_held
        self.flips: list[Tx] = []

    def attach(self, sim) -> None:
        Load.attach(self, sim)
        sim.net.nodes[self.node].import_hooks.append(lambda node, block: self._act(sim, node))

    def _setting(self, index: int) -> tuple[str, int]:
        """The sender and the setting slot that junk spend `index` reads."""
        sender = self.senders[index % len(self.senders)]
        return sender, self.setting[1] + index % self.slots

    def _act(self, sim, node) -> None:
        now = sim.sched.now
        if not self.start <= now < self.stop:
            return
        for _ in range(self.burst):
            index = len(self.spends)
            sender = self.senders[index % len(self.senders)]
            reads = None
            if self.setting is not None:
                address, slot = self._setting(index) if self.flip_held else self.setting
                reads = ((address, slot, node.pool.state.storage(address, slot)),)
            spend = Spend(index, f"{self.name}-{index}", sender, now, self.tip(self.rng))
            spend.tx = self.spend_tx(sim, spend, reads)
            spend.home = node.name
            self.spends.append(spend)
            answers = [self._submit(sim, spend, sim.net.nodes[t]) for t in self.targets]
            if "ok" not in answers:
                break
        if self.flipper is not None and (not self.flips or node.pool.state.nonce(self.flipper) > self.flips[-1].nonce):
            if self.flip_held:
                held = sorted({self._setting(sp.index) for sp in self.spends
                               if sp.home == node.name and node.pool.get(sp.tx.hash) is not None})
                if not held:
                    return
                gas = 21_000 + 5_000 * len(held) + 2_600 * (len({a for a, _ in held}) - 1)
            else:
                held, gas = [self.setting], self.flip_gas
            state = node.pool.state
            nonce = state.nonce(self.flipper)
            flip = Tx(self.flipper, nonce=nonce, gas=gas, tip=self.flip_tip, max_fee=self.fee_cap(sim, self.flip_tip),
                      writes=tuple((a, k, state.storage(a, k) + 1) for a, k in held), label=f"{self.name}-flip-{nonce}")
            self.flips.append(flip)
            sim.recorder.submitted(flip, now, node.name)
            node.submit(flip)


class SlotWriter(Load):
    """Deposits into a shared sender: one transaction a block that rewrites a slot of its storage.

    After every block `node` imports, from `start` until `stop`, once its last
    write has landed, `senders[0]` sends to `node` a transaction of `gas` that
    writes the next value to `slot` of `address`, at a tip of `write_tip`,
    which lands it in the next block. A privacy pool's deposit rewrites its
    root in this way; 26,000 gas is `JunkLoad`'s flip, and a deposit's other
    work is left out. The load draws no arrivals.
    """

    def __init__(self, *args, node: str, address: str, slot: int = 0, gas: int = 26_000,
                 write_tip: int = 2_000_000_000, **kwargs):
        kwargs.setdefault("rate", 0.0)
        super().__init__(*args, **kwargs)
        self.node = node
        self.address = address
        self.slot = slot
        self.gas = gas
        self.write_tip = write_tip
        self.writes: list[Tx] = []

    def attach(self, sim) -> None:
        super().attach(sim)
        sim.net.nodes[self.node].import_hooks.append(lambda node, block: self._write(sim, node))

    def _write(self, sim, node) -> None:
        if not self.start <= sim.sched.now < self.stop:
            return
        state = node.pool.state
        sender = self.senders[0]
        if self.writes and state.nonce(sender) <= self.writes[-1].nonce:
            return
        nonce = state.nonce(sender)
        tx = Tx(sender, nonce=nonce, gas=self.gas, tip=self.write_tip, max_fee=self.fee_cap(sim, self.write_tip),
                writes=((self.address, self.slot, state.storage(self.address, self.slot) + 1),),
                label=f"{self.name}-{nonce}")
        self.writes.append(tx)
        sim.recorder.submitted(tx, sim.sched.now, node.name)
        node.submit(tx)


class Settlement:
    """One batch a `Committee` settles: the intents at queue positions `start` to `end`, and its versions."""

    def __init__(self, index: int, start: int, end: int, cut_at: float):
        self.index = index
        self.start = start
        self.end = end
        self.cut_at = cut_at
        self.sent_at: float | None = None
        self.versions: list = []
        self.blocks = 0  # blocks its node imported without it since its last version
        self.included_at: float | None = None
        self.block: int | None = None
        self.doomed = False  # proved after a settlement that reverted, so it reverts too
        self.reverted = False

    @property
    def size(self) -> int:
        return self.end - self.start


class Committee(Load):
    """An MPC committee that settles users' intents in batches, as Merces's does (decision record 0028).

    Intents are transactions whose label starts with `intents`. After every
    block `node` imports, the committee appends the block's intents to its
    queue in block order, as Merces's action queue holds them, and cuts
    batches from the queue's head: under `rule` "every" whenever it has any,
    up to `batch`; under "full" only `batch` at a time, or what it has once
    the oldest has waited `wait` blocks. A batch is ready `compute` seconds
    after its cut, the committee's rounds, and its settlement takes `gas`
    whatever its size, since a short batch is padded. Each settlement is
    proved against the queue position the last one ends at; one included
    before that position is reached reverts, pays its gas and settles
    nothing, and the committee cuts its intents again.

    `sender` says how a settlement is sent from `address`, to `node`, at a
    tip of `settle_tip` and a fee cap of `fee_multiplier` times the next base
    fee plus the tip:

    - "account": a type 2 transaction at the next nonce, sent when ready; the
      account-nonce pool holds it behind the last (NP-12), so the committee
      cuts every block.
    - "frame": a frame transaction, a `VERIFY` frame that checks the
      committee's key and a `SENDER` frame that settles, at the next sequence
      of nonce key 1. FP-7 queues no frame transaction, so the committee cuts
      only when it has no settlement pending or computing, and the cut takes
      what the queue holds, up to `batch`.
    - "keys": a frame transaction under a nonce key of its own for each
      settlement, sent when ready, which `disjoint-keys` admits beside the
      others; the committee cuts every block, and a settlement that a block
      includes out of order reverts.

    With `patience`, once its node has imported that many blocks without a
    pending settlement, the committee re-prices it as `BumpLoad` does with
    `reprice`, by `bump` percent and to the market, and sends the new version
    to its node. `queue` holds the intents' hashes in order and
    `settlements` every batch.
    """

    RULES = ("every", "full")
    SENDERS = ("account", "frame", "keys")

    def __init__(self, name: str, *, address: str, node: str, intents: str, rule: str = "every",
                 sender: str = "account", batch: int = 50, wait: int = 5, compute: float = 0.315,
                 gas: int = 1_125_950, verify_gas: int = 15_000, settle_tip: int = 2_000_000_000,
                 patience: int | None = None, bump: int = 10, start: float = 0.0, stop: float = float("inf"),
                 fee_multiplier: int = 2):
        if rule not in self.RULES or sender not in self.SENDERS:
            raise ValueError((rule, sender))
        super().__init__(name, rate=0.0, senders=[address], tip=fixed(settle_tip), start=start, stop=stop,
                         fee_multiplier=fee_multiplier)
        self.address = address
        self.node = node
        self.intents = intents
        self.rule = rule
        self.sender = sender
        self.batch = batch
        self.wait = wait
        self.compute = compute
        self.gas = gas
        self.verify_gas = verify_gas
        self.settle_tip = settle_tip
        self.patience = patience
        self.bump = bump
        self.queue: list[str] = []
        self.queued_in: list[int] = []  # the block number that included each intent
        self.settlements: list[Settlement] = []
        self.cut_to = 0  # queue position the last cut batch ends at
        self.applied = 0  # queue position the last settlement that succeeded ends at
        self._busy = 0  # batches cut and not yet included, sent or computing
        self._by_hash: dict[str, Settlement] = {}
        self._nonce = 0
        self._sequence = 0

    def attach(self, sim) -> None:
        super().attach(sim)
        sim.net.nodes[self.node].import_hooks.append(lambda node, block: self._import(sim, node, block))

    def _import(self, sim, node, block) -> None:
        for tx in block.txs:
            if tx.label.startswith(self.intents):
                self.queue.append(tx.hash)
                self.queued_in.append(block.head.number)
                continue
            s = self._by_hash.get(tx.hash)
            if s is None or s.included_at is not None:
                continue
            s.included_at, s.block = sim.sched.now, block.head.number
            self._busy -= 1
            if s.start == self.applied and not s.doomed:
                self.applied = s.end
            else:
                s.reverted = True
                self._rewind()
        if self.patience is not None:
            self._reprice(sim, node)
        if self.start <= sim.sched.now < self.stop:
            self._cut(sim, block.head.number)

    def _rewind(self) -> None:
        """After a revert: keep the pending settlements that still follow on from the last good one, doom the
        rest, and cut again from where the kept ones end."""
        self.cut_to = self.applied
        for s in sorted(self.settlements, key=lambda s: s.start):
            if s.included_at is not None or s.doomed:
                continue
            if s.start == self.cut_to:
                self.cut_to = s.end
            else:
                s.doomed = True

    def _cut(self, sim, number: int) -> None:
        while self.cut_to < len(self.queue):
            if self.sender == "frame" and self._busy:
                return
            n = min(self.batch, len(self.queue) - self.cut_to)
            if self.rule == "full" and n < self.batch and number - self.queued_in[self.cut_to] < self.wait:
                return
            s = Settlement(len(self.settlements), self.cut_to, self.cut_to + n, sim.sched.now)
            self.settlements.append(s)
            self.cut_to = s.end
            self._busy += 1
            sim.sched.after(self.compute, lambda s=s: self._send(sim, s))

    def _send(self, sim, s: Settlement) -> None:
        tip = self.settle_tip
        tx = self._tx(sim, s, tip, self.fee_cap(sim, tip))
        s.sent_at = sim.sched.now
        self._submit(sim, s, tx)

    def _tx(self, sim, s: Settlement, tip: int, cap: int):
        label = f"{self.name}-{s.index}"
        if self.sender == "account":
            nonce, self._nonce = self._nonce, self._nonce + 1
            return Tx(self.address, nonce=nonce, gas=self.gas, max_fee=cap, tip=tip, label=label)
        if self.sender == "frame":
            keys, seq = (1,), self._sequence
            self._sequence += 1
        else:
            keys, seq = (s.index + 1,), 0
        verify = Frame(mode=1, flags=3, exec_gas=self.verify_gas, data_size=96, approves=3)
        settle = Frame(mode=2, target=f"{self.address}-contract", exec_gas=0, data_size=0)
        tx = FrameTx(self.address, (verify, settle), nonce_keys=keys, nonce_seq=seq,
                     signatures=(Signature(signer=self.name),), max_fee=cap, tip=tip, label=label)
        settle = replace(settle, exec_gas=self.gas - tx.max_gas)
        return replace(tx, frames=(verify, settle))

    def _submit(self, sim, s: Settlement, tx) -> None:
        s.versions.append(tx)
        s.blocks = 0
        self._by_hash[tx.hash] = s
        node = sim.net.nodes[self.node]
        sim.recorder.submitted(tx, sim.sched.now, node.name)
        node.submit(tx)

    def _reprice(self, sim, node) -> None:
        base = self.fee_multiplier * sim.chain.head.next_base_fee()
        for s in self.settlements:
            if s.sent_at is None or s.included_at is not None:
                continue
            s.blocks += 1
            if s.blocks < self.patience:
                continue
            last = s.versions[-1]
            fees = bump_fees(last.tip, last.max_fee, self.bump, base)
            if fees is not None:
                self._submit(sim, s, replace(last, tip=fees[0], max_fee=fees[1],
                                             label=f"{self.name}-{s.index}.{len(s.versions)}"))


class Batch:
    """One batch a `Clearing` committee clears, aimed at block `target`: the orders it took, and its settlement."""

    def __init__(self, target: int, orders: list[str], cut_at: float, started_at: float, ended_at: float):
        self.target = target
        self.orders = orders
        self.cut_at = cut_at
        self.started_at = started_at
        self.ended_at = ended_at
        self.tx = None  # the settlement, once sent


class Clearing(Load):
    """A committee that clears a batch of orders every block, as per-block matching must (decision record 0029).

    `members` are nodes of the network. A batch takes `rounds` rounds at a
    round trip of `rtt` between them, and starts no earlier than the last
    batch's end, since each clears the book the last one left. Batch `b` is
    meant for block `b`:

    - `channel` "chain": its orders are the transactions labelled `orders`
      that block `b - 1` carried, as Merces takes its intents; it starts once
      every member has imported that block.
    - `channel` "pool": its orders are the ones every member has held pending
      since before the cutoff, `margin` seconds and the rounds before block
      `b` is due, that no earlier batch took. They travel the network as
      transactions, and reach the chain only through the settlement, so the
      scenario's builders must leave them out (`ChainConfig.censored`).

    The first member sends each batch's settlement when it ends, from
    `address`, an account, at its next nonce, to its own node, at a tip of
    `settle_tip`, whether or not the batch holds an order. `batches` holds
    them in order.
    """

    CHANNELS = ("chain", "pool")

    def __init__(self, name: str, *, address: str, members: tuple[str, ...], orders: str, channel: str = "chain",
                 rounds: int = 49, rtt: float = 0.08, margin: float = 1.0, gas: int = 1_125_950,
                 settle_tip: int = 2_000_000_000, start: float = 0.0, stop: float = float("inf"),
                 fee_multiplier: int = 2):
        if channel not in self.CHANNELS or not members:
            raise ValueError((channel, members))
        super().__init__(name, rate=0.0, senders=[address], tip=fixed(settle_tip), start=start, stop=stop,
                         fee_multiplier=fee_multiplier)
        self.address = address
        self.members = tuple(members)
        self.orders = orders
        self.channel = channel
        self.rounds = rounds
        self.rtt = rtt
        self.margin = margin
        self.gas = gas
        self.settle_tip = settle_tip
        self.batches: list[Batch] = []
        self._imported: dict[int, set[str]] = {}  # block number -> members that have imported it
        self._free_at = 0.0  # when the last batch's rounds end
        self._taken: set[str] = set()
        self._nonce = 0

    @property
    def compute(self) -> float:
        return self.rounds * self.rtt

    def attach(self, sim) -> None:
        super().attach(sim)
        if self.channel == "chain":
            for m in self.members:
                sim.net.nodes[m].import_hooks.append(lambda node, block, m=m: self._import(sim, m, block))
            return
        slot = sim.scenario.chain.slot_time
        lead = self.compute + self.margin
        target = max(1, math.ceil((max(self.start, sim.sched.now) + lead) / slot))
        sim.sched.at(target * slot - lead, lambda: self._cutoff(sim, target))

    def _import(self, sim, member: str, block) -> None:
        number = block.head.number
        seen = self._imported.setdefault(number, set())
        seen.add(member)
        if len(seen) < len(self.members):
            return
        del self._imported[number]
        if self.start <= sim.sched.now < self.stop:
            self._clear(sim, number + 1, [tx.hash for tx in block.txs if tx.label.startswith(self.orders)])

    def _cutoff(self, sim, target: int) -> None:
        if sim.sched.now >= self.stop:
            return
        now = sim.sched.now
        orders = []
        for h, rec in sim.recorder.txs.items():
            if h in self._taken or not rec.tx.label.startswith(self.orders):
                continue
            if all(rec.first_seen.get(m, float("inf")) <= now for m in self.members):
                orders.append(h)
                self._taken.add(h)
        self._clear(sim, target, orders)
        slot = sim.scenario.chain.slot_time
        sim.sched.at((target + 1) * slot - self.compute - self.margin, lambda: self._cutoff(sim, target + 1))

    def _clear(self, sim, target: int, orders: list[str]) -> None:
        now = sim.sched.now
        started = max(now, self._free_at)
        b = Batch(target, orders, now, started, started + self.compute)
        self._free_at = b.ended_at
        self.batches.append(b)
        sim.sched.at(b.ended_at, lambda: self._send(sim, b))

    def _send(self, sim, b: Batch) -> None:
        nonce, self._nonce = self._nonce, self._nonce + 1
        b.tx = Tx(self.address, nonce=nonce, gas=self.gas, max_fee=self.fee_cap(sim, self.settle_tip),
                  tip=self.settle_tip, label=f"{self.name}-{b.target}")
        node = sim.net.nodes[self.members[0]]
        sim.recorder.submitted(b.tx, sim.sched.now, node.name)
        node.submit(b.tx)


SHAPES = ("sponsor", "paymaster", "noncanonical", "shared-sender", "self")
DIRECT_GAS = 5000  # the limit of a frame the protocol defines: default code, or the canonical paymaster


def backed_tx(shape: str, sender: str, payer: str | None, *, max_fee: int, tip: int, label: str, key: int = 0,
              seq: int = 0, verify_gas: int = 0, pay_gas: int = 10_000, exec_gas: int = 21_000,
              deadline: int | None = None, expiry_verifier: str = EIP_8141.expiry_verifier,
              scheme: str | None = None, signature: Signature = Signature(), claim: Claim | None = None) -> FrameTx:
    """A frame transaction whose payment rests on `payer`, in one of `SHAPES`.

    - `sponsor`, `paymaster`, `noncanonical`: `[only_verify, pay, sender]`. The
      pay frame targets `payer`, which runs its default code and needs the
      second signature entry (`sponsor`), holds the canonical paymaster's code
      (`paymaster`), or holds other code (`noncanonical`, which runs for
      `pay_gas`). The sender holds code and its verify frame runs it for
      `verify_gas`, or with `verify_gas` 0 has default code.
    - `shared-sender`: `payer` is the sender, holds code, and verifies and pays
      in one `self_verify` frame of `verify_gas`, on nonce key `key`.
    - `self`: the sender pays for itself in one `self_verify` frame, with code
      for `verify_gas` or with `verify_gas` 0 default code; `payer` is unused.

    With `deadline`, an expiry frame at `expiry_verifier` comes first, with a
    limit of 100 gas, which covers the 51 the canonical expiry verifier's
    success path costs (EIP-8141, Expiry Verifier Frame). A frame the protocol
    defines, which a node evaluates without running code (EIP-8141, "Direct
    Evaluation of Protocol-Defined Frames"), gets a limit of `DIRECT_GAS`. The
    scenario must give every account its code.

    With `scheme`, `sphincs` or `stark`, an EIP-8288 dependency frame with one
    triple of that scheme, unique to `label`, comes before everything else
    (AG-2), as EIP-8288's Test Case 1 has it.

    `signature` is the sender's entry, a secp256k1 signature unless another is
    given, such as an `arbitrary` entry that carries a proof. `claim` is an
    admission claim (CG-2), which only the `claim-gated` profile reads.
    """
    if shape not in SHAPES:
        raise ValueError(shape)
    sender_frame = Frame(mode=2, exec_gas=exec_gas)
    expiry = () if deadline is None else (Frame(mode=1, target=expiry_verifier, exec_gas=100, data_size=8,
                                                 deadline=deadline),)
    if scheme is not None:
        code, gas = SCHEMES[scheme]
        expiry = (Frame(mode=3, deps=(Dependency(code, label, "vk"),), exec_gas=gas, data_size=96),) + expiry
    if shape in ("shared-sender", "self"):
        verify = (Frame(mode=1, flags=3, exec_gas=verify_gas, approves=3) if shape == "shared-sender" or verify_gas
                  else Frame(mode=1, flags=3, exec_gas=DIRECT_GAS))
        return FrameTx(payer if shape == "shared-sender" else sender, expiry + (verify, sender_frame),
                       nonce_keys=(key,), nonce_seq=seq, signatures=(signature,), max_fee=max_fee, tip=tip,
                       label=label, claim=claim)
    verify = (Frame(mode=1, flags=2, exec_gas=verify_gas, approves=2) if verify_gas
              else Frame(mode=1, flags=2, exec_gas=DIRECT_GAS))
    signatures = (signature,)
    if shape == "sponsor":
        pay = Frame(mode=1, flags=1, target=payer, exec_gas=DIRECT_GAS)
        signatures += (Signature(signer=payer),)
    else:
        pay = Frame(mode=1, flags=1, target=payer, approves=1,
                    exec_gas=DIRECT_GAS if shape == "paymaster" else pay_gas)
    return FrameTx(sender, expiry + (verify, pay, sender_frame), nonce_keys=(key,), nonce_seq=seq,
                   signatures=signatures, max_fee=max_fee, tip=tip, label=label, claim=claim)


class CopiesLoad(SharedSenderLoad):
    """Spends from a shared sender, each handed out as copies that only one of can land (decision record 0020).

    Each arrival is one user's spend from one of `senders`, which the user
    hands out at once as `copies` transactions, or as one for every node with
    `copies` 0, each to a different random node, and never again. The copies
    carry the same frames and fees and differ only in their label, as copies
    naming different relayers would. `record` says where the spend's
    nullifier, the spend's index plus one, is kept:

    - `nonce`: the EIP-8250 nonce key, as in `SharedSenderLoad`, so every
      copy has the same identity and a pool holds one of them (FP-12);
    - `slot`: a slot of the sender's storage, which the prefix reads and
      approves only while it holds 0 and the execution sets to 1. Each copy
      then has a nonce key of its own, and a pool can hold every copy.

    `spends[i].copies` lists what was handed out, in order.
    """

    RECORDS = ("nonce", "slot")

    def __init__(self, *args, copies: int = 2, record: str = "nonce", **kwargs):
        super().__init__(*args, rule="direct", **kwargs)
        if record not in self.RECORDS:
            raise ValueError(record)
        self.copies = copies
        self.record = record

    def attach(self, sim) -> None:
        Load.attach(self, sim)  # nobody resends a copy

    def copy_tx(self, sim, spend: Spend, j: int) -> FrameTx:
        """The `j`-th copy of `spend`."""
        nullifier = self.nullifier(spend)
        if self.record == "nonce":
            tx = self.spend_tx(sim, spend)
            return replace(tx, label=f"{spend.label}/{j}")
        tx = self.spend_tx(sim, spend, reads=((spend.sender, nullifier, 0),))
        return replace(tx, label=f"{spend.label}/{j}", nonce_keys=(nullifier << 16 | j,),
                       writes=((spend.sender, nullifier, 1),))

    def arrive(self, sim) -> None:
        sender = self.rng.choice(self.senders)
        index = len(self.spends)
        spend = Spend(index, f"{self.name}-{index}", sender, sim.sched.now, self.tip(self.rng))
        self.spends.append(spend)
        nodes = list(sim.net.nodes.values())
        targets = self.routing.sample(nodes, self.copies or len(nodes))
        spend.copies = [self.copy_tx(sim, spend, j) for j in range(len(targets))]
        spend.tx = spend.copies[0]
        spend.home = targets[0].name
        for tx, node in zip(spend.copies, targets):
            sim.recorder.submitted(tx, sim.sched.now, node.name)
            spend.answers.append(node.submit(tx))


class RootWriter(Load):
    """A root source's writer (`08-recent-roots.md`, RR-3).

    From `start` until `stop`, every `every` seconds, `senders[0]` sends to a
    random node a transaction of `gas` that writes a fresh root for the source
    `(address, salt)`, at a tip drawn as every load's. As each block is first
    imported it learns which slots hold one of its roots, so that a wallet can
    ask for the latest at or before a node's head (`latest`). A write a block
    leaves out stays in the pools, and the next ones queue behind it on its
    nonce. The load draws no arrivals.
    """

    def __init__(self, *args, address: str, salt: str = "0", every: float = 12.0, gas: int = 60_000, **kwargs):
        kwargs.setdefault("rate", 0.0)
        super().__init__(*args, **kwargs)
        self.address = address
        self.salt = salt
        self.source = source_id(address, salt)
        self.every = every
        self.gas = gas
        self.writes: list[Tx] = []
        self.slots: list[int] = []  # the slots that hold one of its roots, in order
        self.roots: list[str] = []

    def attach(self, sim) -> None:
        super().attach(sim)
        sim.sched.every(self.every, lambda: self._write(sim), start=max(self.start, sim.sched.now))
        for node in sim.net.nodes.values():
            node.import_hooks.append(lambda node, block: self._learn(block))

    def _write(self, sim) -> None:
        if sim.sched.now >= self.stop:
            return
        sender = self.senders[0]
        nonce = sim.wallet_nonce(sender)
        tip = self.tip(self.rng)
        root = f"{self.name}-{len(self.writes)}"
        tx = Tx(sender, nonce=nonce, gas=self.gas, max_fee=self.fee_cap(sim, tip), tip=tip,
                root_writes=((self.address, self.salt, root),), label=f"{self.name}-{nonce}")
        self.writes.append(tx)
        node = self.routing.choice(list(sim.net.nodes.values()))
        sim.recorder.submitted(tx, sim.sched.now, node.name)
        node.submit(tx)

    def _learn(self, block) -> None:
        slot = block.head.slot
        if self.slots and slot <= self.slots[-1]:
            return  # another node imported it first; blocks are first imported in order, by their proposer
        mine = [w for tx in block.txs for w in getattr(tx, "root_writes", ()) if w[:2] == (self.address, self.salt)]
        if mine:
            self.slots.append(slot)
            self.roots.append(mine[-1][2])

    def latest(self, slot: int) -> tuple[int, str] | None:
        """The latest `(slot, root)` written at or before `slot`, or None."""
        i = bisect.bisect_right(self.slots, slot)
        return (self.slots[i - 1], self.roots[i - 1]) if i else None


REPROVE = ("ErrFrameRootExpired", "ErrFrameRootUnknown")


class RootSpendLoad(SharedSenderLoad):
    """Spends proved against a recent root (`08-recent-roots.md`), each from a sender of its own.

    The spend is `SharedSenderLoad`'s, under its `direct` rule, with a
    `recent_root_verify` frame first, of `root_gas`, naming one root of
    `writer`'s source. Each arrival takes the next of `senders`, which must
    hold code and a balance and must not run out, and picks a random node, of
    `targets` if given, which it watches. A user reads the latest root written
    at or before that node's head, proves for `prove` seconds, and sends the
    spend to a random node. After every block its node imports without
    including it, it sends the spend again to a random node; when a node
    refuses it for its root (`REPROVE`), the user reads the latest root at its
    node's head again, proves again, and sends the new version, a transaction
    with the same nullifier and tip and a fee cap from the base fee of the
    time. A user that finds no root yet tries again at the next block.

    Each spend records its versions as `(transaction, root slot)`, the age of
    each version's root when it was sent, in slots as the node it watches
    counts them (RR-2), how many proofs it took, and, when it lands, the slot
    of the block and the root slot of the version that landed.
    """

    def __init__(self, *args, writer: RootWriter, prove: float = 12.0, root_gas: int = 10_000, **kwargs):
        kwargs["rule"] = "direct"
        super().__init__(*args, **kwargs)
        self.writer = writer
        self.prove = prove
        self.root_gas = root_gas

    def root_tx(self, sim, spend: Spend, root: tuple[int, str]) -> FrameTx:
        tx = self.spend_tx(sim, spend)
        frame = Frame(mode=1, target=sim.scenario.frame_pool.recent_root_address, exec_gas=self.root_gas,
                      data_size=TUPLE_BYTES, roots=((self.writer.source, root[0], root[1]),))
        label = spend.label if not spend.versions else f"{spend.label}.{len(spend.versions)}"
        return replace(tx, frames=(frame,) + tx.frames, label=label)

    def arrive(self, sim) -> None:
        index = len(self.spends)
        if index == len(self.senders):
            raise ValueError(f"{self.name}: more arrivals than senders")
        spend = Spend(index, f"{self.name}-{index}", self.senders[index], sim.sched.now, self.tip(self.rng))
        spend.versions, spend.ages, spend.proofs, spend.proving = [], [], 0, False
        spend.landed_slot = spend.landed_root = None
        self.spends.append(spend)
        node = self._random_node(sim)
        spend.home = node.name
        self._waiting.setdefault(node.name, []).append(spend)
        self._prove(sim, spend, node)

    def _prove(self, sim, spend: Spend, node) -> None:
        """Read the latest root at `node`'s head and send a spend against it `prove` seconds later."""
        root = self.writer.latest(node.pool.head.slot)
        if root is None:
            return  # tried again at the next block
        spend.proving = True
        spend.proofs += 1

        def send() -> None:
            spend.proving = False
            spend.tx = self.root_tx(sim, spend, root)
            spend.versions.append((spend.tx, root[0]))
            spend.ages.append(sim.net.nodes[spend.home].pool.head.slot + 1 - root[0])
            self._submit(sim, spend, self._random_node(sim))
        sim.sched.after(self.prove, send)

    def _direct_import(self, sim, node) -> None:
        watching = self._waiting.get(node.name)
        if not watching:
            return
        still = []
        for spend in watching:
            if spend.tx is not None and self._included(node, spend):
                spend.landed_slot = node.pool.head.slot
                spend.landed_root = next(slot for tx, slot in spend.versions
                                         if sim.recorder.txs[tx.hash].included_at is not None)
                continue
            still.append(spend)
            if spend.proving:
                continue
            if spend.tx is None:
                self._prove(sim, spend, node)
            elif self._submit(sim, spend, self._random_node(sim)) in REPROVE:
                self._prove(sim, spend, node)
        self._waiting[node.name] = still


class FanOutLoad(Load):
    """An adversary who backs `k` pending frame transactions with one dependency and moves it every block.

    The dependency is the balance of `payer`, which every one of the
    transactions records (FP-10): a sponsor, a paymaster or a shared sender,
    as `backed_tx`'s `shape` says. With every shape but `shared-sender` each
    transaction has a sender of its own, `sender_names` gives their names, and
    they hold code when `verify_gas` is above 0. At `start` the adversary
    sends all `k` to every node in `targets` (`node` by default), at a fee cap
    and tip of `max_fee` wei each, 1 by default: FP-3 asks for nothing more,
    no builder includes them, and each reserves only its `max_gas` times
    `max_fee` against the payer (FP-11). From `touch_from` until `stop`, after
    every block its node imports, an account it controls, `toucher`, sends
    `touch_value` wei to `touched` (the payer by default) in a 21,000-gas
    transfer at a tip that lands it in the next block, whenever its last one
    has landed. The transfer changes nothing a prefix can observe except the
    balance, and FP-15 re-simulates every transaction that recorded it.
    """

    def __init__(self, name: str, *, shape: str, k: int, payer: str, node: str, targets: list[str] | None = None,
                 verify_gas: int = 0, pay_gas: int = 10_000, max_fee: int = 1, toucher: str | None = None,
                 touched: str | None = None, touch_value: int = 1, touch_tip: int = 2_000_000_000,
                 touch_from: float = 0.0, start: float = 0.0, stop: float = float("inf")):
        super().__init__(name, rate=0.0, senders=self.sender_names(name, shape, k, payer), tip=fixed(max_fee),
                         start=start, stop=stop)
        self.shape = shape
        self.k = k
        self.payer = payer
        self.node = node
        self.targets = targets or [node]
        self.verify_gas = verify_gas
        self.pay_gas = pay_gas
        self.max_fee = max_fee
        self.toucher = toucher
        self.touched = touched or payer
        self.touch_value = touch_value
        self.touch_tip = touch_tip
        self.touch_from = touch_from
        self.txs: list[FrameTx] = []
        self.answers: list[list[str]] = []
        self.touches: list[Tx] = []

    @staticmethod
    def sender_names(name: str, shape: str, k: int, payer: str) -> list[str]:
        return [payer] if shape == "shared-sender" else [f"{name}-s{i}" for i in range(k)]

    def attach(self, sim) -> None:
        super().attach(sim)
        sim.sched.at(max(self.start, sim.sched.now), lambda: self._send(sim))
        sim.net.nodes[self.node].import_hooks.append(lambda node, block: self._touch(sim, node))

    def _send(self, sim) -> None:
        now = sim.sched.now
        for i in range(self.k):
            shared = self.shape == "shared-sender"
            tx = backed_tx(self.shape, self.payer if shared else self.senders[i], self.payer, max_fee=self.max_fee,
                           tip=self.max_fee, label=f"{self.name}-{i}", key=i + 1 if shared else 0,
                           verify_gas=self.verify_gas, pay_gas=self.pay_gas)
            self.txs.append(tx)
            answers = []
            for t in self.targets:
                sim.recorder.submitted(tx, now, t)
                answers.append(sim.net.nodes[t].submit(tx))
            self.answers.append(answers)

    def _touch(self, sim, node) -> None:
        now = sim.sched.now
        if self.toucher is None or not self.touch_from <= now < self.stop:
            return
        nonce = node.pool.state.nonce(self.toucher)
        if self.touches and nonce <= self.touches[-1].nonce:
            return
        tx = Tx(self.toucher, nonce=nonce, gas=21_000, to=self.touched, value=self.touch_value,
                max_fee=self.fee_cap(sim, self.touch_tip), tip=self.touch_tip, label=f"{self.name}-touch-{nonce}")
        self.touches.append(tx)
        sim.recorder.submitted(tx, now, node.name)
        node.submit(tx)


class SponsoredLoad(Load):
    """Users of a paymaster service: each a sender with code, whose frame transactions one payer sponsors.

    Each arrival is a user's next transaction, in `backed_tx`'s `shape` with
    `payer`, sent to a random node; a user with one in flight is skipped, as
    `FrameLoad`'s wallets are. After every block that node imports without
    including it, the user sends it again to a random node, so a refusal
    costs a block rather than the transaction.

    With `expiring` above 0, that share of transactions, drawn per arrival,
    carry an expiry frame with a deadline `expiry` seconds after they are
    first sent, and a user whose transaction can no longer be included, its
    deadline below the timestamp of the block it watched, gives it up
    (`expired`) and is free to send the next.

    With `scheme`, every transaction carries one EIP-8288 dependency of that
    scheme (`backed_tx`), and is sent, and sent again, as a mode 0 wrapper
    with its proof (AG-5). With `resend` false, a user sends each transaction
    once and only watches the node it sent it to. With `targets`, users send
    only to those nodes; `signature` is passed to `backed_tx`. With `fresh`,
    each arrival is the next sender in `senders`, which must not run out, so
    that no arrival is skipped or draws a sender and two runs that differ
    only in the network are offered the same senders at the same times.

    With `claims`, every transaction carries a valid claim for its slot in the
    epoch of the chain's head (CG-2), and a user about to send it again buys a
    fresh one, making a new version of the transaction with the same fees, if
    the epoch has moved on or if the last node it was sent to answered that
    its claim is of another epoch, used, refused or expired (`RENEW`).
    `versions` lists, by the hash of each transaction's first version, every
    version made; `claims_bought` counts the claims.
    """

    RENEW = frozenset({"ErrClaimEpoch", "ErrClaimUsed", "ErrClaimRefused", "ErrClaimExpired"})

    def __init__(self, *args, shape: str, payer: str | None, verify_gas: int = 30_000, pay_gas: int = 10_000,
                 exec_gas: int = 50_000, expiring: float = 0.0, expiry: float = 600.0, scheme: str | None = None,
                 resend: bool = True, targets: list[str] | None = None, signature: Signature = Signature(),
                 fresh: bool = False, claims: bool = False, **kwargs):
        super().__init__(*args, **kwargs)
        self.shape = shape
        self.payer = payer
        self.verify_gas = verify_gas
        self.pay_gas = pay_gas
        self.exec_gas = exec_gas
        self.expiring = expiring
        self.expiry = expiry
        self.scheme = scheme
        self.resend = resend
        self.targets = targets
        self.signature = signature
        self.fresh = fresh
        self.claims = claims
        self.claims_bought = 0
        self.versions: dict[str, list[FrameTx]] = {}
        self._first: dict[str, str] = {}  # by sender, the first version of its transaction in flight
        self._last: dict[str, str] = {}  # by hash, the last answer to it
        self._arrivals = 0
        self.txs: list[FrameTx] = []
        self.answers: dict[str, list[str]] = {}
        self.deadlines: dict[str, int] = {}  # by hash, for the transactions that carry one
        self.expired: list[FrameTx] = []
        self.skipped = 0
        self._busy: set[str] = set()
        self._waiting: dict[str, list[FrameTx]] = {}

    def attach(self, sim) -> None:
        super().attach(sim)
        for node in sim.net.nodes.values():
            node.import_hooks.append(lambda node, block: self._import(sim, node))

    def arrive(self, sim) -> None:
        if self.fresh:
            if self._arrivals == len(self.senders):
                raise ValueError(f"{self.name}: more arrivals than senders")
            sender = self.senders[self._arrivals]
            self._arrivals += 1
        else:
            sender = self.rng.choice(self.senders)
        if sender in self._busy:
            self.skipped += 1
            return
        tip = self.tip(self.rng)
        seq = sim.chain.state.nonce(sender)
        deadline = None
        if self.expiring and self.rng.random() < self.expiring:
            deadline = int(sim.sched.now + self.expiry)
        tx = backed_tx(self.shape, sender, self.payer, max_fee=self.fee_cap(sim, tip), tip=tip, seq=seq,
                       label=f"{self.name}-{sender}-{seq}", verify_gas=self.verify_gas, pay_gas=self.pay_gas,
                       exec_gas=self.exec_gas, deadline=deadline,
                       expiry_verifier=sim.scenario.frame_pool.expiry_verifier, scheme=self.scheme,
                       signature=self.signature, claim=self._claim(sim, sender, seq) if self.claims else None)
        if deadline is not None:
            self.deadlines[tx.hash] = deadline
        if self.claims:
            self.versions[tx.hash] = [tx]
            self._first[sender] = tx.hash
        self._busy.add(sender)
        self.txs.append(tx)
        self._submit(sim, tx)

    def _submit(self, sim, tx: FrameTx) -> None:
        names = self.targets if self.targets is not None else list(sim.net.nodes)
        node = sim.net.nodes[self.routing.choice(names)]
        sim.recorder.submitted(tx, sim.sched.now, node.name)
        if self.scheme is None:
            answer = node.submit(tx)
        else:
            answer = node.submit_wrapper(wrap([tx]), origin=self.name)
            answer = answer if isinstance(answer, str) else answer[0]
        self.answers.setdefault(tx.hash, []).append(answer)
        self._last[tx.hash] = answer
        self._waiting.setdefault(node.name, []).append(tx)

    def _claim(self, sim, sender: str, seq: int) -> Claim:
        """A fresh claim for the sender's slot in the epoch of the chain's head."""
        self.claims_bought += 1
        epoch = sim.chain.head.timestamp // sim.scenario.frame_pool.claim_epoch
        return Claim(sender, seq, epoch, salt=f"{self.name}-{self.claims_bought}")

    def _renew(self, sim, tx: FrameTx) -> FrameTx:
        """The version to send again: `tx`, or one with a fresh claim (`RENEW`)."""
        epoch = sim.chain.head.timestamp // sim.scenario.frame_pool.claim_epoch
        if tx.claim is None or (tx.claim.epoch == epoch and self._last.get(tx.hash) not in self.RENEW):
            return tx
        new = replace(tx, claim=self._claim(sim, tx.sender, tx.nonce_seq))
        if tx.hash in self.deadlines:
            self.deadlines[new.hash] = self.deadlines[tx.hash]
        self.versions[self._first[tx.sender]].append(new)
        return new

    def _import(self, sim, node) -> None:
        watching = self._waiting.pop(node.name, [])
        for tx in watching:
            if node.pool.state.nonce(tx.sender) > tx.nonce_seq:
                self._busy.discard(tx.sender)
            elif self.deadlines.get(tx.hash, node.pool.head.timestamp) < node.pool.head.timestamp:
                self.expired.append(tx)
                self._busy.discard(tx.sender)
            elif self.resend:
                self._submit(sim, self._renew(sim, tx) if self.claims else tx)
            else:
                self._waiting.setdefault(node.name, []).append(tx)


class WalletLoad(SponsoredLoad):
    """Wallets that pay for themselves: `SponsoredLoad` with `backed_tx`'s shape `self`.

    Senders have default code unless `verify_gas` is above 0; half of the
    transactions carry a deadline ten minutes out unless `expiring` and
    `expiry` say otherwise.
    """

    def __init__(self, *args, verify_gas: int = 0, expiring: float = 0.5, expiry: float = 600.0, **kwargs):
        super().__init__(*args, shape="self", payer=None, verify_gas=verify_gas, expiring=expiring, expiry=expiry,
                         **kwargs)


class FloodLoad(Load):
    """An adversary who keeps every node's frame pool full of transactions that no builder includes, or pays.

    Each of its `k` transactions has a default-code sender of its own. `kind`
    says what they are:

    - `free`: no deadline, a fee cap and tip of 1 wei, paid by `payer`, a
      canonical paymaster instance, which no profile caps (experiment 03).
      FP-3 admits it, no builder includes it, and each reserves its `max_gas`
      in wei.
    - `expiring`: paid by `payer` as above, with the earliest deadline the
      node admits, the timestamp of the head it is sent on plus the pool's
      `expiry_margin` (FP-8), at a tip of `tip` and a fee cap of twice the next
      base fee plus the tip. With a margin of 0 the next block cannot include
      it and FP-15 drops it at the next head; with a margin of the slot time
      the next block can, and the adversary pays for what it includes. Either
      way the adversary sends a fresh one, with a new deadline, every block.
    - `drained`: no deadline, priced as `expiring`, and paid by a default-code
      sponsor of the head's own, `payer-<number>`, which the scenario funds.
      With them the adversary sends the sponsor's transfer of its whole
      balance at twice the tip, which the next block includes first, so that
      every transaction the sponsor backs fails there and FP-15 removes them
      all at the next head. A profile that caps codeless payers (FP-11)
      admits one transaction per sponsor.
    - `empty`: as `drained`, with a sponsor that the scenario does not fund
      and no transfer, so that FP-11 refuses every one (experiment 10's
      sponsors that hold nothing).

    With `revealed` false every key is withheld, so a commitment runs nothing
    and refunds nothing (LU-13, decision record 0027).

    With `scheme`, `sphincs` or `stark`, every one of its frame transactions
    carries one EIP-8288 dependency of that scheme (`backed_tx`), and is
    handed to a node as a mode 0 wrapper with its proof (AG-5), so that it
    takes a place in every aggregate that lists it (decision record 0034).

    With `claims` a number $T$, every transaction carries a claim for its slot
    in the epoch of the head it is made at (CG-2): the first $T$ it makes, a
    valid one, and the rest one whose issuer's signature does not verify; not
    with `free`, whose transactions are made once. `claimed` counts the valid
    claims it used. With `proofs` false, its wrappers carry proofs that do not
    verify, which it signs, since the transactions are its own (CG-3). With
    `rotate`, a batch made at head `number` comes from senders of that head's
    own, `<name>-s<i>-<number>`, so that no two batches share a slot.

    At `start`, and after every block a node in `targets` (every node by
    default) imports until `stop`, it sends that node, directly, the
    transactions of its own the node does not hold: as many as the pool has
    room for and `surplus` more, which FP-14 admits only by evicting
    something. A node relays what it admits, as it would any transaction. The
    adversary records nothing in the recorder, so that its transactions do
    not count as demand.
    """

    KINDS = ("free", "expiring", "drained", "empty")

    def __init__(self, name: str, *, kind: str, k: int, payer: str, targets: list[str] | None = None,
                 surplus: int = 64, tip: int = 10_000_000_000, start: float = 0.0, stop: float = float("inf"),
                 scheme: str | None = None, claims: int | None = None, proofs: bool = True, rotate: bool = False):
        if kind not in self.KINDS or (claims is not None and kind == "free"):
            raise ValueError(kind)
        self.scheme = scheme
        self.claims = claims
        self.proofs = proofs
        self.rotate = rotate
        self.claimed = 0
        super().__init__(name, rate=0.0, senders=[f"{name}-s{i}" for i in range(k)], tip=fixed(tip),
                         start=start, stop=stop)
        self.kind = kind
        self.k = k
        self.payer = payer
        self.targets = targets
        self.surplus = surplus
        self.sent = 0
        self.admitted = 0
        self.drains: list[Tx] = []
        self._batch: tuple[int, list[FrameTx], Tx | None] | None = None  # the head number it was made for

    def attach(self, sim) -> None:
        super().attach(sim)
        self.targets = self.targets or list(sim.net.nodes)
        for name in self.targets:
            sim.net.nodes[name].import_hooks.append(lambda node, block: self._fill(sim, node))
        sim.sched.at(max(self.start, sim.sched.now), lambda: [self._fill(sim, sim.net.nodes[t]) for t in self.targets])

    def sponsor(self, number: int) -> str:
        """The default-code sponsor of a `drained` batch made at head `number`."""
        return f"{self.payer}-{number}"

    def batch(self, sim, pool) -> tuple[list[FrameTx], Tx | None]:
        """The transactions for a node whose frame pool is `pool`, and a `drained` batch's transfer.

        The same ones throughout for `free`, fresh ones at each head otherwise.
        """
        head, verifier = pool.head, sim.scenario.frame_pool.expiry_verifier
        number = 0 if self.kind == "free" else head.number
        if self._batch is None or self._batch[0] != number:
            drain = None
            if self.kind == "free":
                txs = [backed_tx("paymaster", s, self.payer, max_fee=1, tip=1, label=f"{self.name}-{i}-0",
                                 expiry_verifier=verifier, scheme=self.scheme) for i, s in enumerate(self.senders)]
            else:
                tip = self.tip(self.rng)
                fee = 2 * head.next_base_fee() + tip
                senders = [f"{s}-{number}" for s in self.senders] if self.rotate else self.senders
                if self.kind == "expiring":
                    deadline = head.timestamp + pool.config.expiry_margin
                    txs = [backed_tx("paymaster", s, self.payer, max_fee=fee, tip=tip, seq=pool.state.nonce(s),
                                     label=f"{self.name}-{i}-{number}", deadline=deadline, expiry_verifier=verifier,
                                     scheme=self.scheme, claim=self._claim(s, pool, f"{self.name}-{i}-{number}"))
                           for i, s in enumerate(senders)]
                else:
                    sponsor = self.sponsor(number)
                    txs = [backed_tx("sponsor", s, sponsor, max_fee=fee, tip=tip, seq=pool.state.nonce(s),
                                     label=f"{self.name}-{i}-{number}", expiry_verifier=verifier, scheme=self.scheme,
                                     claim=self._claim(s, pool, f"{self.name}-{i}-{number}"))
                           for i, s in enumerate(senders)]
                if self.kind == "drained":
                    cap = 2 * head.next_base_fee() + 2 * tip
                    drain = Tx(sponsor, nonce=pool.state.nonce(sponsor), gas=21_000, max_fee=cap, tip=2 * tip,
                               value=max(0, pool.state.balance(sponsor) - 21_000 * cap), to=f"{self.name}-sink",
                               label=f"{self.name}-drain-{number}")
                    self.drains.append(drain)
            self._batch = (number, txs, drain)
        return self._batch[1], self._batch[2]

    def _claim(self, sender: str, pool, salt: str) -> Claim | None:
        if self.claims is None:
            return None
        valid = self.claimed < self.claims
        self.claimed += valid
        return Claim(sender, pool.state.nonce(sender), pool.head.timestamp // pool.config.claim_epoch, valid=valid,
                     salt=salt)

    def _fill(self, sim, node) -> None:
        if not self.start <= sim.sched.now < self.stop:
            return
        pool = node.pool.frame
        budget = max(0, pool.config.max_pending - len(pool.entries)) + self.surplus
        txs, drain = self.batch(sim, pool)
        for tx in txs:
            if budget <= 0:
                break
            if tx.hash in pool.entries:
                continue
            budget -= 1
            self.sent += 1
            if self.scheme is None:
                answer = node.submit(tx)
            else:
                wrapper = wrap([tx])
                if not self.proofs:
                    wrapper = replace(wrapper, proofs=(False,) * len(wrapper.deps))
                answer = node.submit_wrapper(wrapper, origin=self.name)
                answer = answer if isinstance(answer, str) else answer[0]
            if answer == "ok":
                self.admitted += 1
        if drain is not None:
            node.submit(drain)

    def reserved(self, node) -> int:
        """What its transactions held at `node` reserve against its payers (FP-11), in wei."""
        return sum(v for p, v in node.pool.frame.reserved.items()
                   if p == self.payer or p.startswith(self.payer + "-"))


class FramingLoad(Load):
    """An adversary who sees honest transactions and tries to get them refused (decision record 0037).

    It watches every node, and the first time a node admits a frame
    transaction of the load named `target`, it hands every node, `delay`
    seconds later and from `start` until `stop`, a mode 0 wrapper (AG-5) whose
    proofs do not verify. It holds no key but its own and no claim. `kind`
    says what the wrapper carries:

    - `copy`: a transaction of its own, the honest one with a sender of the
      adversary's and the honest one's claim and dependencies; it signs its
      own proofs.
    - `rewrap`: the honest transaction itself. EIP-8288's wrapper carries its
      proofs beside the signed transaction, so anyone who holds one can send
      it again with proofs of their own; these are marked as not the ones the
      sender signed (CG-3).

    `sent` counts the wrappers it hands a node, and `answers` the answers.
    """

    KINDS = ("copy", "rewrap")

    def __init__(self, name: str, *, kind: str, target: str, delay: float = 0.1, start: float = 0.0,
                 stop: float = float("inf")):
        if kind not in self.KINDS:
            raise ValueError(kind)
        super().__init__(name, rate=0.0, senders=[], tip=fixed(0), start=start, stop=stop)
        self.kind = kind
        self.target = target
        self.delay = delay
        self.seen: set[str] = set()
        self.sent = 0
        self.answers: Counter = Counter()

    def attach(self, sim) -> None:
        super().attach(sim)
        for node in sim.net.nodes.values():
            node.admit_hooks.append(lambda node, tx, result: self._see(sim, tx, result))

    def _see(self, sim, tx, result: str) -> None:
        if result != "ok" or not isinstance(tx, FrameTx) or not tx.label.startswith(self.target + "-") \
                or tx.hash in self.seen or not self.start <= sim.sched.now < self.stop:
            return
        self.seen.add(tx.hash)
        sim.sched.after(self.delay, lambda: self._frame(sim, tx))

    def _frame(self, sim, tx: FrameTx) -> None:
        if self.kind == "copy":
            n = len(self.seen)
            tx = replace(tx, sender=f"{self.name}-s{n}", label=f"{self.name}-{n}")
        deps = union([tx])
        wrapper = Wrapper((tx,), 0, deps, (False,) * len(deps), signed=(self.kind == "copy",) * len(deps))
        for node in sim.net.nodes.values():
            self.sent += 1
            answer = node.submit_wrapper(wrapper, origin=self.name)
            self.answers[answer if isinstance(answer, str) else answer[0]] += 1


class SybilLoad(Load):
    """An adversary that backs sponsored frame transactions with payers of its own making (decision record 0019).

    Every transaction has `backed_tx`'s `sponsor` shape, from a default-code
    sender of its own, and owes nothing unless a block includes it. `kind`
    says what backs it:

    - `empty`: a default-code sponsor of its own that holds nothing, which
      costs nothing to make. Each arrival is handed to `copies` random nodes,
      one by default.
    - `drained`: one default-code sponsor a round, `payer(r)`; the scenario
      funds the first with `funding(max_fee)`. `wait` seconds after every
      block the node `node` imports, from `start` until `stop`, so that every
      node holds the block whose transfer funded the round's sponsor, the
      adversary hands that round's `k` transactions each to a random node,
      and hands every node
      the sponsor's transfer of its whole balance, less the transfer's fee,
      to the next round's sponsor at twice the tip. The next block includes
      the transfer first, so every transaction the sponsor backed fails there
      and FP-15 removes it everywhere at the next head, and the same money
      backs every round.

    `sent` counts the transactions the adversary handed a node, a transaction
    handed to two nodes counting twice. The recorder sees every transaction
    and every transfer.
    """

    KINDS = ("empty", "drained")

    def __init__(self, name: str, *, kind: str, rate: float = 0.0, k: int = 0, copies: int = 1, node: str = "n00",
                 wait: float = 2.0, tip: int = 1_000_000_000, start: float = 0.0, stop: float = float("inf"),
                 senders: int = 100_000):
        if kind not in self.KINDS:
            raise ValueError(kind)
        super().__init__(name, rate=rate if kind == "empty" else 0.0,
                         senders=[f"{name}-s{i}" for i in range(senders)], tip=fixed(tip), start=start, stop=stop)
        self.kind = kind
        self.k = k
        self.copies = copies
        self.node = node
        self.wait = wait
        self.sent = 0
        self.txs: list[FrameTx] = []
        self.transfers: list[Tx] = []
        self._next = 0
        self._round = 0

    def payer(self, r: int) -> str:
        return f"{self.name}-payer-{r}"

    def funding(self, max_fee: int, rounds: int = 1) -> int:
        """What the first sponsor must hold to back `k` transactions at `max_fee` in each of `rounds` rounds,
        since each round's transfer pays its fee out of the balance it moves on."""
        one = backed_tx("sponsor", "x", "y", max_fee=max_fee, tip=0, label="x").max_cost
        return self.k * one + rounds * 21_000 * 2 * max_fee

    def _sender(self) -> str:
        sender = self.senders[self._next]
        self._next += 1
        return sender

    def attach(self, sim) -> None:
        super().attach(sim)
        if self.kind == "drained":
            sim.net.nodes[self.node].import_hooks.append(
                lambda node, block: sim.sched.after(self.wait, lambda: self._round_start(sim)))
            sim.sched.at(max(self.start, sim.sched.now), lambda: self._round_start(sim))

    def _hand(self, sim, tx, nodes) -> None:
        sim.recorder.submitted(tx, sim.sched.now, nodes[0].name)
        for node in nodes:
            if isinstance(tx, FrameTx):
                self.sent += 1
            node.submit(tx)

    def arrive(self, sim) -> None:  # `empty`
        sender = self._sender()
        tip = self.tip(self.rng)
        tx = backed_tx("sponsor", sender, f"{sender}-payer", max_fee=self.fee_cap(sim, tip), tip=tip,
                       label=f"{self.name}-{sender}")
        self.txs.append(tx)
        self._hand(sim, tx, self.routing.sample(list(sim.net.nodes.values()), self.copies))

    def _round_start(self, sim) -> None:
        if not self.start <= sim.sched.now < self.stop:
            return
        head, state = sim.chain.head, sim.chain.state
        sponsor, after = self.payer(self._round), self.payer(self._round + 1)
        self._round += 1
        tip = self.tip(self.rng)
        fee = self.fee_cap(sim, tip)
        nodes = list(sim.net.nodes.values())
        for i in range(self.k):
            tx = backed_tx("sponsor", self._sender(), sponsor, max_fee=fee, tip=tip,
                           label=f"{self.name}-{sponsor}-{i}")
            self.txs.append(tx)
            self._hand(sim, tx, [self.routing.choice(nodes)])
        cap = 2 * head.next_base_fee() + 2 * tip
        transfer = Tx(sponsor, nonce=state.nonce(sponsor), gas=21_000, max_fee=cap, tip=2 * tip,
                      value=max(0, state.balance(sponsor) - 21_000 * cap), to=after,
                      label=f"{self.name}-transfer-{sponsor}")
        self.transfers.append(transfer)
        self._hand(sim, transfer, nodes)


class SealedLoad(Load):
    """Senders of EIP-8184 sealed transactions (`docs/spec/06-lucid.md`), each with one in flight.

    Each arrival is a sender's next sealed transaction, sent to a random node;
    a sender with one in flight is skipped, since a pool holds one per sender
    and only at its nonce (LU-5). The ticket asks for a ToB fee of `tob` wei
    and tolerates `preceding` commitments before it, both drawn per arrival,
    with a gas limit of `gas` that the decrypted transaction uses in full,
    `size` bytes and no key fee; every key is released. Its fee cap per gas is
    twice the next base fee plus the tip plus the ToB fee per gas, rounded up,
    so that it pays the ToB fee it asks for while the base fee stays below
    twice what it was (LU-3). After every block the node it was sent to
    imports without committing it, the sender sends it again to a random node;
    with `reseal`, re-encrypted first, which makes a new sealed transaction
    with the same fees and a hash of its own. `sent` holds every version of
    each, in order, and `answers` every answer to each, by its first
    version's hash.

    With `publishers` above 1, each attempt names one of that many key
    publishers, at random among those that have not withheld a key from its
    sender, and the first `withholding` of them withhold every key they are
    named for: the ticket is committed and charged and nothing runs (LU-13,
    decision record 0027). When the block that committed a withheld ticket
    reaches the node the sender sent it to, the sender sends the payment
    again at its next nonce to that node: as a new sealed transaction, which
    `sent` holds as the next version, under `response` "sealed", or as a
    regular transaction with the same gas and tip under "public", which
    `public` holds by the first version's hash and which the sender sends
    again to the node after every block that does not include it. `withheld` counts each payment's
    withheld attempts by the same hash.

    With a `committee` (decision record 0032), a share `committee_share` of
    payments, drawn when each is first sent, name the committee, every attempt
    of theirs too, and the rest name `kp`, which releases every key. The
    committee decides once a block is built whether a commitment's key is in
    time; the sender learns the committee's `deadline` after the block that
    committed it was built, having seen no key, and only then sends the
    payment again, as above. At a rotation the sender `keep`s a pending sealed
    transaction sealed to the old key, or, with `rotation` "reseal", replaces
    it at its node with one sealed to the new key at fees raised by
    `price_bump` percent (LU-9), at the first import of a block after which
    the next slot is in a new epoch.
    """

    RESPONSES = ("sealed", "public")
    ROTATIONS = ("keep", "reseal")

    def __init__(self, *args, tob: Callable[[random.Random], int] = fixed(0),
                 preceding: Callable[[random.Random], int] = fixed(31), gas: int = 100_000, size: int = 512,
                 reseal: bool = False, publishers: int = 1, withholding: int = 0, response: str = "sealed",
                 committee: "KeyCommittee | None" = None, committee_share: float = 1.0, rotation: str = "keep",
                 price_bump: int = 10, **kwargs):
        super().__init__(*args, **kwargs)
        if response not in self.RESPONSES or not 0 <= withholding <= publishers or rotation not in self.ROTATIONS:
            raise ValueError((response, withholding, publishers, rotation))
        self.committee = committee
        self.committee_share = committee_share
        self.rotation = rotation
        self.price_bump = price_bump
        self.tob = tob
        self.preceding = preceding
        self.gas = gas
        self.size = size
        self.reseal = reseal
        self.publishers = ["kp"] + [f"kp{i}" for i in range(1, publishers)]
        self.withholders = set(self.publishers[:withholding])
        self.response = response
        self.sent: list[list[SealedTx]] = []
        self.answers: dict[str, list[str]] = {}
        self.withheld: Counter = Counter()
        self.public: dict[str, Tx] = {}
        self.skipped = 0
        self._busy: set[str] = set()
        self._waiting: dict[str, list[list[SealedTx]]] = {}
        self._public_waiting: dict[str, list[Tx]] = {}
        self._avoid: dict[str, set[str]] = {}

    def attach(self, sim) -> None:
        super().attach(sim)
        self.choosing = random.Random(f"{sim.scenario.seed}/{self.name}/publishers")
        if self.committee is not None:
            self.committee.attach(sim)
        for node in sim.net.nodes.values():
            node.import_hooks.append(lambda node, block: self._import(sim, node, block))

    def arrive(self, sim) -> None:
        sender = self.rng.choice(self.senders)
        if sender in self._busy:
            self.skipped += 1
            return
        self._busy.add(sender)
        tip, tob, preceding = self.tip(self.rng), self.tob(self.rng), self.preceding(self.rng)
        nonce = sim.chain.state.nonce(sender)
        publisher = None
        if self.committee is not None:
            publisher = self.committee.name if self.choosing.random() < self.committee_share else self.publishers[0]
        st = self._sealed(sim, sender, nonce, self.fee_cap(sim, tip) + -(-tob // self.gas), tip, tob, preceding,
                          f"{self.name}-{sender}-{nonce}", publisher)
        versions = [st]
        self.sent.append(versions)
        self._submit(sim, versions)

    def _sealed(self, sim, sender: str, nonce: int, max_fee: int, tip: int, tob: int, preceding: int,
                label: str, publisher: str | None = None) -> SealedTx:
        if publisher is None:
            publisher = self.publishers[0]
            if len(self.publishers) > 1:
                avoid = self._avoid.get(sender, set())
                publisher = self.choosing.choice([p for p in self.publishers if p not in avoid] or self.publishers)
        st = SealedTx(sender, nonce=nonce, max_fee=max_fee, tip=tip, gas_limit=self.gas, max_tob_fee=tob,
                      max_preceding=preceding, key_publisher=publisher, fee_recipient=publisher,
                      size=self.size, revealed=publisher not in self.withholders, label=label)
        if self.committee is not None and publisher == self.committee.name:
            self.committee.seal(sim, st)
        return st

    def _submit(self, sim, versions: list[SealedTx], node=None) -> None:
        node = node or self.routing.choice(list(sim.net.nodes.values()))
        sim.recorder.submitted(versions[-1], sim.sched.now, node.name)
        self.answers.setdefault(versions[0].hash, []).append(node.submit(versions[-1]))
        self._waiting.setdefault(node.name, []).append(versions)

    def _import(self, sim, node, block) -> None:
        for tx in self._public_waiting.pop(node.name, []):
            if node.pool.state.nonce(tx.sender) > tx.nonce:
                self._busy.discard(tx.sender)
            else:
                node.submit(tx)
                self._public_waiting.setdefault(node.name, []).append(tx)
        for versions in self._waiting.pop(node.name, []):
            st = versions[-1]
            if node.pool.state.nonce(st.sender) > st.nonce:
                if self.committee is not None and st.key_publisher == self.committee.name:
                    self._learn(sim, versions, node, block)
                elif st.revealed:
                    self._busy.discard(st.sender)
                else:
                    self._withheld(sim, versions, node)
                continue
            if self.reseal:
                versions.append(replace(st, label=f"{versions[0].label}/{len(versions)}"))
            elif self._stale(sim, st):
                bump = lambda v: -(-v * (100 + self.price_bump) // 100)  # noqa: E731
                versions.append(self._sealed(sim, st.sender, st.nonce, bump(st.max_fee), bump(st.tip),
                                             bump(st.max_tob_fee), st.max_preceding,
                                             f"{versions[0].label}/{len(versions)}", st.key_publisher))
                self._submit(sim, versions, node)
                continue
            self._submit(sim, versions)

    def _stale(self, sim, st: SealedTx) -> bool:
        """Whether a sender that reseals at a rotation replaces `st`, sealed to a key the committee no longer
        seals to."""
        c = self.committee
        return (self.rotation == "reseal" and c is not None and st.key_publisher == c.name
                and c.sealed_to.get(st.hash) != c.sealing_epoch(sim))

    def _learn(self, sim, versions: list[SealedTx], node, block) -> None:
        """A commitment that names the committee is in `block`: the committee's `deadline` after the block
        was built, the sender knows whether its key came."""
        st = versions[-1]
        mine = next((c.tx for c in block.commitments if c.tx.sender == st.sender and c.tx.nonce == st.nonce), st)

        def check() -> None:
            if self.committee.outcome.get(mine.hash) in self.committee.RELEASED:
                self._busy.discard(st.sender)
            else:
                self._withheld(sim, versions, node)
        sim.sched.at(max(sim.sched.now, self.committee.started[block.head.number] + self.committee.deadline), check)

    def _withheld(self, sim, versions: list[SealedTx], node) -> None:
        """The key of `versions[-1]`, committed, was withheld: the payment goes again at the next nonce, to
        `node`, which has the block that committed it."""
        st, first = versions[-1], versions[0].hash
        self.withheld[first] += 1
        self._avoid.setdefault(st.sender, set()).add(st.key_publisher)
        if self.response == "sealed":
            max_fee = self.fee_cap(sim, st.tip) + -(-st.max_tob_fee // self.gas)
            again = st.key_publisher if self.committee is not None else None
            versions.append(self._sealed(sim, st.sender, st.nonce + 1, max_fee, st.tip, st.max_tob_fee,
                                         st.max_preceding, f"{versions[0].label}/{len(versions)}", again))
            self._submit(sim, versions, node)
            return
        tx = Tx(st.sender, nonce=st.nonce + 1, gas=self.gas, max_fee=self.fee_cap(sim, st.tip), tip=st.tip,
                label=f"{versions[0].label}/public")
        self.public[first] = tx
        sim.recorder.submitted(tx, sim.sched.now, node.name)
        node.submit(tx)
        self._public_waiting.setdefault(node.name, []).append(tx)


class KeyCommittee:
    """A threshold committee that is an EIP-8184 key publisher for the sealed transactions naming `name`
    (decision record 0032).

    Of its `members`, `withholding` never send a share, and each other one
    misses each slot on its own with probability `late`. Once a block is
    built, the committee draws how many members are in time in that slot, and
    the key of each of its commitments in the block is released if at least
    `threshold` are; with `per` "commitment", it draws afresh for each
    commitment instead, the same probability per key without the
    correlation. A commitment's sender is online in its slot with probability
    `online`, drawn per commitment, and then releases its own key whatever
    the committee does. Nothing within the slot is timed: a member
    late for the deadline is, to the key, one that withheld.

    With `epoch` above 0 the committee changes every `epoch` slots. Under
    `handover` "reshare" it keeps its public key, and the committee serving a
    commitment's slot releases its key. Under "rotate" each epoch's committee
    has a key of its own: a sender seals to the key of the epoch of the next
    slot (`seal`), and only that epoch's committee can release the key, in
    its own epoch and the first `serving` slots of the next. Both the serving
    committee and the one before it are drawn every slot, so runs that differ
    only in `serving` or in their senders see the same members.

    `outcome` holds, by hash, what became of each commitment's key:
    "released", "self" (its sender's), "quorum" (too few shares) or "gone"
    (no committee holds it). `slots` holds, by block, its commitments, the
    members in time of the serving committee and of the one before, and the
    shares sent: one per member in time for each commitment, and one per
    member in time of each committee that had a commitment, as a batch would.
    `started` holds when each block was built; a sender learns of a withheld
    key `deadline` seconds after that.
    """

    PER = ("slot", "commitment")
    HANDOVERS = ("reshare", "rotate")
    RELEASED = ("released", "self")

    def __init__(self, name: str, *, members: int, threshold: int, withholding: int = 0, late: float = 0.0,
                 online: float = 0.0, per: str = "slot", epoch: int = 0, handover: str = "reshare",
                 serving: int = 0, deadline: float = 9.0):
        if per not in self.PER or handover not in self.HANDOVERS or not 0 < threshold <= members:
            raise ValueError((per, handover, threshold, members))
        if not 0 <= withholding <= members or (epoch and not 0 <= serving < epoch):
            raise ValueError((withholding, serving, epoch))
        self.name = name
        self.members = members
        self.threshold = threshold
        self.withholding = withholding
        self.late = late
        self.online = online
        self.per = per
        self.epoch = epoch
        self.handover = handover
        self.serving = serving
        self.deadline = deadline
        self.sealed_to: dict[str, int] = {}
        self.outcome: dict[str, str] = {}
        self.slots: dict[int, dict] = {}
        self.started: dict[int, float] = {}
        self.sim = None

    def attach(self, sim) -> None:
        """Called once, by the first `SealedLoad` that names the committee."""
        if self.sim is not None:
            return
        self.sim = sim
        self.rng = random.Random(f"{sim.scenario.seed}/{self.name}/members")
        self.fresh = random.Random(f"{sim.scenario.seed}/{self.name}/each")
        self.senders = random.Random(f"{sim.scenario.seed}/{self.name}/online")
        sim.chain.key_publishers.append(self.decide)

    def key_epoch(self, slot: int) -> int:
        return slot // self.epoch if self.epoch else 0

    def sealing_epoch(self, sim) -> int:
        """The epoch of the key a sender seals to now: that of the next slot."""
        return self.key_epoch(sim.chain.head.slot + 1)

    def seal(self, sim, st: SealedTx) -> None:
        self.sealed_to[st.hash] = self.sealing_epoch(sim)

    def _in_time(self, rng: random.Random) -> int:
        return sum(1 for _ in range(self.members - self.withholding) if rng.random() >= self.late)

    def decide(self, block) -> set[str]:
        slot, number = block.head.slot, block.head.number
        self.started[number] = self.sim.sched.now
        serving, before = self._in_time(self.rng), self._in_time(self.rng)
        e = self.key_epoch(slot)
        withheld: set[str] = set()
        each = batched = 0
        used: dict[int, int] = {}
        mine = [c.tx for c in block.commitments if c.tx.key_publisher == self.name]
        for st in mine:
            sealed = self.sealed_to.get(st.hash, e)
            if self.handover == "reshare" or sealed == e:
                held, which = serving, e
            elif sealed == e - 1 and slot - e * self.epoch < self.serving:
                held, which = before, e - 1
            else:
                held, which = None, None
            if held is not None and self.per == "commitment":
                held = self._in_time(self.fresh)
            online = self.senders.random() < self.online
            if held is not None:
                each += held
                used[which] = held
            if held is not None and held >= self.threshold:
                self.outcome[st.hash] = "released"
            elif online:
                self.outcome[st.hash] = "self"
            else:
                self.outcome[st.hash] = "quorum" if held is not None else "gone"
                withheld.add(st.hash)
        batched = sum(used.values())
        self.slots[number] = {"slot": slot, "commitments": len(mine), "serving": serving, "before": before,
                              "shares": each, "batched": batched, "withheld": len(withheld)}
        return withheld


class SealedFlood(Load):
    """An adversary who keeps every node's sealed pool full of sealed transactions that outrank the honest.

    Each of its `k` senders, which the scenario funds, has one sealed
    transaction at a time. Each tolerates no commitment before it
    (`max_preceding_commitments` 0), so a block commits at most one of them,
    and only first; it has `size` bytes, the least gas limit LU-4 allows and a
    tip of `tip`, its key is released, and it does nothing. `kind` says what
    ToB fee each asks for:

    - `cheap`: `tob` wei, the same for all. With `tob` above what payments bid
      and below what some honest sealed transaction bids, a block commits one
      only when its builder holds no honest one that bids more, and the rest
      cost the adversary nothing. Under `next-block` and `every-head` all but
      one have no place in the next block (LU-8).
    - `escalating`: from `tob` up, each one made 1 wei above the last. With
      `tob` above every honest bid, each comes first when it is sent, which
      every policy admits, and a block commits the highest; the adversary pays
      its ticket less what the reveal refunds (LU-13).

    With `revealed` false every key is withheld, so a commitment runs nothing
    and refunds nothing (LU-13, decision record 0027).

    At `start`, and after every block a node in `targets` (every node by
    default) imports until `stop`, it sends that node, directly, sealed
    transactions from senders the node holds none from: as many as the pool
    has room for and `surplus` more, which LU-10 admits only by evicting the
    last in commitment order, stopping at the first the node refuses. A
    `cheap` sender sends the same one until it is committed, an `escalating`
    one a fresh one every time. A node relays what it admits, as it would any
    transaction. The adversary records nothing in the recorder, so that its
    transactions do not count as demand.
    """

    KINDS = ("cheap", "escalating")

    def __init__(self, name: str, *, kind: str, k: int, tob: int = 1, size: int = 256, tip: int = 1_000_000,
                 surplus: int = 16, targets: list[str] | None = None, start: float = 0.0,
                 stop: float = float("inf"), revealed: bool = True):
        if kind not in self.KINDS:
            raise ValueError(kind)
        super().__init__(name, rate=0.0, senders=[f"{name}-s{i}" for i in range(k)], tip=fixed(tip),
                         start=start, stop=stop)
        self.kind = kind
        self.k = k
        self.base_tob = tob
        self.size = size
        self.surplus = surplus
        self.targets = targets
        self.revealed = revealed
        self.made = 0
        self.sent = 0
        self.admitted = 0
        self._current: dict[str, SealedTx] = {}

    def attach(self, sim) -> None:
        super().attach(sim)
        self.targets = self.targets or list(sim.net.nodes)
        for name in self.targets:
            sim.net.nodes[name].import_hooks.append(lambda node, block: self._fill(sim, node))
        sim.sched.at(max(self.start, sim.sched.now), lambda: [self._fill(sim, sim.net.nodes[t]) for t in self.targets])

    def sealed(self, pool, sender: str) -> SealedTx:
        """The sealed transaction `sender` sends to a node whose sealed pool is `pool`."""
        nonce = pool.state.nonce(sender)
        st = self._current.get(sender)
        if self.kind == "cheap" and st is not None and st.nonce == nonce and fees(st, pool.head.next_base_fee()):
            return st
        tob = self.base_tob if self.kind == "cheap" else self.base_tob + self.made
        gas = pool.config.calldata_gas_per_byte * self.size
        tip = self.tip(self.rng)
        st = SealedTx(sender, nonce=nonce, max_fee=2 * pool.head.next_base_fee() + tip + -(-tob // gas), tip=tip,
                      gas_limit=gas, max_tob_fee=tob, max_preceding=0, size=self.size, revealed=self.revealed,
                      label=f"{self.name}-{self.made}")
        self.made += 1
        self._current[sender] = st
        return st

    def _fill(self, sim, node) -> None:
        if not self.start <= sim.sched.now < self.stop:
            return
        pool = node.pool.sealed
        budget = max(0, pool.config.st_slots - len(pool.entries)) + self.surplus
        for sender in self.senders:
            if budget <= 0:
                break
            if sender in pool.by_sender:
                continue
            budget -= 1
            self.sent += 1
            if node.submit(self.sealed(pool, sender)) != "ok":
                break
            self.admitted += 1


def schedule(sim, load: Load) -> None:
    """Start `load`'s Poisson arrivals on `sim`; a load with no rate only attaches."""
    load.attach(sim)
    if load.rate <= 0:
        return

    def arrive():
        if sim.sched.now >= load.stop:
            return
        load.arrive(sim)
        sim.sched.after(load.rng.expovariate(load.rate), arrive)

    sim.sched.at(max(load.start, sim.sched.now) + load.rng.expovariate(load.rate), arrive)


@dataclass
class Update:
    """One update an `Updater` holder sent: the chain it covers, `start` to `end`, and what became of it."""

    tx: FrameTx
    holder: str
    start: int
    end: int
    began: float  # when proving began
    sent: float
    slot: int | None = None  # of the block that carried it
    effect: bool | None = None  # whether it took effect there, or reverted


class Updater(Load):
    """The open role that proves a privacy pool's root from its chained outputs (the plan's item 31, decision record 0039).

    The pool appends each output to a hash chain as the block that carries it
    executes; the transactions of `outputs`, a load whose labels begin with its
    name, carry `per_tx` each. The role is held by the nodes `holders`, the
    i-th sending from `senders[i]`, an account that pays for itself. After each
    block a holder imports, it reads at its head the chain's length and its
    coverage, the length the latest update in effect covers; if at least
    `every` outputs lie between them and it has no update of its own in
    flight, it proves an update of all of them, for `prove(k)` seconds with $k$
    the outputs, and sends it to its own node: a frame transaction of
    `backed_tx`'s shape `self` with one leanSTARK dependency, in a mode 0
    wrapper (AG-5). With `backoff` above 0, a holder about to prove first
    waits a time drawn uniformly below it, reads its head again, and proves
    nothing if its pool now holds another holder's update of the coverage it
    read.

    Blocks are read as each is first imported, in order. An update whose start
    is the coverage when it executes takes effect, and the outputs it covers
    can be spent from the next slot: its root is written in its block's slot
    $S$ and is referenceable from $S + 1$ (`08-recent-roots.md`, RR-2 and
    RR-3). Any other update reverts in execution, which is where the pool's
    contract compares the update's old root with its own; it is included, and
    pays, all the same. A holder's update is in flight until a block carries
    it; after each block that does not, the holder sends it again to its own
    node. The root itself is not written: nothing in the run cites it.

    `carried[i]` is the slot of the block that carried output i, and
    `spendable[i]` the slot from which it can be spent, once an update covers
    it. `updates` lists every update, in the order sent, and `proving` the
    seconds each holder spent proving.
    """

    def __init__(self, *args, outputs: Load, holders: list[str], prove: Callable[[int], float], per_tx: int = 2,
                 every: int = 1, backoff: float = 0.0, exec_gas: int = 50_000, **kwargs):
        kwargs.setdefault("rate", 0.0)
        super().__init__(*args, **kwargs)
        if len(self.senders) < len(holders):
            raise ValueError(f"{self.name}: a sender for each holder")
        self.outputs = outputs
        self.holders = {name: self.senders[i] for i, name in enumerate(holders)}
        self.prove = prove
        self.per_tx = per_tx
        self.every = max(1, every)
        self.backoff = backoff
        self.deferred = 0  # times a holder stood down for another's update
        self.exec_gas = exec_gas
        self.carried: list[int] = []
        self.spendable: dict[int, int] = {}
        self.coverage = 0
        self.history: list[tuple[int, int, int]] = []  # (slot, chain length, coverage) after each block read
        self.updates: list[Update] = []
        self.proving: Counter = Counter()
        self._by_hash: dict[str, Update] = {}
        self._flight: dict[str, Update] = {}
        self._busy: set[str] = set()  # holders waiting to decide, or proving

    def attach(self, sim) -> None:
        super().attach(sim)
        for node in sim.net.nodes.values():
            node.import_hooks.append(lambda node, block: self._import(sim, node, block))

    def _read(self, block) -> None:
        slot = block.head.slot
        if self.history and slot <= self.history[-1][0]:
            return  # another node imported it first
        prefix = f"{self.outputs.name}-"
        for tx in block.txs:
            u = self._by_hash.get(tx.hash)
            if u is not None:
                u.slot = slot
                u.effect = u.start == self.coverage
                if u.effect:
                    for i in range(u.start, u.end):
                        self.spendable[i] = slot + 1
                    self.coverage = u.end
            elif getattr(tx, "label", "").startswith(prefix):
                self.carried.extend([slot] * self.per_tx)
        self.history.append((slot, len(self.carried), self.coverage))

    def view(self, slot: int) -> tuple[int, int]:
        """The chain's length and the coverage after the block at `slot`, or the latest before it."""
        i = bisect.bisect_right(self.history, (slot, math.inf, math.inf))
        return self.history[i - 1][1:] if i else (0, 0)

    def _import(self, sim, node, block) -> None:
        self._read(block)
        if node.name not in self.holders or node.name in self._busy:
            return
        flight = self._flight.get(node.name)
        if flight is not None:
            if flight.slot is None or flight.slot > node.pool.head.slot:  # not yet in a block at its head
                if flight.slot is None:
                    node.submit_wrapper(wrap([flight.tx]), origin=self.name)
                return
            del self._flight[node.name]
        length, coverage = self.view(node.pool.head.slot)
        if length - coverage < self.every:
            return
        if not self.backoff:
            self._prove(sim, node, length, coverage)
            return
        self._busy.add(node.name)

        def decide() -> None:
            self._busy.discard(node.name)
            length, coverage = self.view(node.pool.head.slot)
            if length - coverage < self.every:
                return
            if any(u.start == coverage and u.holder != node.name and u.tx.hash in node.pool.frame.entries
                   for u in self._flight.values()):
                self.deferred += 1
                return
            self._prove(sim, node, length, coverage)
        sim.sched.after(self.rng.uniform(0, self.backoff), decide)

    def _prove(self, sim, node, length: int, coverage: int) -> None:
        """Prove an update of the chain from `coverage` to `length`, then send it to `node`."""
        self._busy.add(node.name)
        began = sim.sched.now
        seconds = self.prove(length - coverage)
        self.proving[node.name] += seconds

        def send() -> None:
            self._busy.discard(node.name)
            sender = self.holders[node.name]
            seq = node.pool.state.nonce(sender)
            tip = self.tip(self.rng)
            tx = backed_tx("self", sender, None, max_fee=self.fee_cap(sim, tip), tip=tip, seq=seq,
                           label=f"{self.name}-{node.name}-{seq}", exec_gas=self.exec_gas, scheme="stark")
            u = Update(tx, node.name, coverage, length, began, sim.sched.now)
            self.updates.append(u)
            self._by_hash[tx.hash] = u
            self._flight[node.name] = u
            sim.recorder.submitted(tx, sim.sched.now, node.name)
            node.submit_wrapper(wrap([tx]), origin=self.name)
        sim.sched.after(seconds, send)


@dataclass
class Purchase:
    """One ticket a `Tickets` wallet bought under a key, and the spend that redeemed it."""

    index: int
    key: int
    tx: Tx
    home: str  # the node the wallet sent the purchase to, whose blocks it watches
    hold: float  # the holding time the wallet drew, in seconds
    slot: int | None = None  # of the block that carried the purchase
    seen: float | None = None  # when the wallet's node imported that block
    spend: Spend | None = None


class Tickets(Load):
    """Blind tickets bought in public and spent from a shared sender (the plan's item 30, decision record 0040).

    Each arrival is a wallet buying a ticket under one of `keys` issuing keys,
    drawn uniformly, so the purchases under each key are a Poisson stream of
    rate `rate / keys`, independent of the others'. A purchase is a plain
    transaction of `gas` from one of `senders`, sent to a random node of
    `targets` (of every node if None). The ticket exists once a block carries
    the purchase: the wallet watches the node it sent the purchase to, and
    when that node imports the block, holds the ticket for a time drawn from
    `hold` and then spends it. The spend is an arrival of `spender`, a
    `SharedSenderLoad` with rule `direct` and no rate of its own, sent to the
    purchase's node with `entry` `same` and to a random node of `targets`
    with `entry` `random`; from there it is `spender`'s, which sends it again
    after every block its node imports without it. A purchase is sent once.
    """

    def __init__(self, *args, keys: int, hold: Callable[[random.Random], float], spender: SharedSenderLoad,
                 entry: str = "random", gas: int = 50_000, targets: list[str] | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        if entry not in ("same", "random"):
            raise ValueError(entry)
        if spender.rule != "direct" or spender.rate > 0:
            raise ValueError(f"{self.name}: the spender is direct and has no rate of its own")
        self.keys = keys
        self.hold = hold
        self.spender = spender
        self.entry = entry
        self.gas = gas
        self.targets = targets
        self.purchases: list[Purchase] = []
        self._waiting: dict[str, dict[str, Purchase]] = {}  # by the node watched: purchase hash -> purchase

    def attach(self, sim) -> None:
        super().attach(sim)
        schedule(sim, self.spender)
        for node in sim.net.nodes.values():
            node.import_hooks.append(lambda node, block: self._import(sim, node, block))

    def _node(self, sim):
        return sim.net.nodes[self.routing.choice(self.targets if self.targets is not None else list(sim.net.nodes))]

    def arrive(self, sim) -> None:
        key = self.rng.randrange(self.keys)
        sender = self.rng.choice(self.senders)
        hold = self.hold(self.rng)
        tip = self.tip(self.rng)
        index = len(self.purchases)
        tx = Tx(sender, nonce=sim.wallet_nonce(sender), gas=self.gas, max_fee=self.fee_cap(sim, tip), tip=tip,
                label=f"{self.name}-{index}")
        node = self._node(sim)
        p = Purchase(index, key, tx, node.name, hold)
        self.purchases.append(p)
        self._waiting.setdefault(node.name, {})[tx.hash] = p
        sim.recorder.submitted(tx, sim.sched.now, node.name)
        node.submit(tx)

    def _import(self, sim, node, block) -> None:
        waiting = self._waiting.get(node.name)
        if not waiting:
            return
        for tx in block.txs:
            p = waiting.pop(tx.hash, None)
            if p is not None:
                p.slot, p.seen = block.head.slot, sim.sched.now
                sim.sched.after(p.hold, lambda p=p: self._spend(sim, p))

    def _spend(self, sim, p: Purchase) -> None:
        node = sim.net.nodes[p.home] if self.entry == "same" else self._node(sim)
        p.spend = self.spender.arrive(sim, node)



@dataclass
class Attempt:
    """One signing of a round's output list, and what became of it."""

    size: int
    tx: Tx | SealedTx | None = None  # the round; under "lock" its settlement, once sent
    lock: Tx | None = None  # under "lock", the transaction that locks the units
    rest: float = 0.0  # under "lock", the coordination left once the lock is in a block
    sent: float | None = None
    locked: float | None = None  # under "lock", when a block carried the lock
    end: float | None = None
    outcome: str = ""  # settled, reverted, dropped, caught, short or refused; empty while it waits
    gas_lost: int = 0  # what its round used when it reverted, which its submitter paid for


@dataclass
class Round:
    """One shuffle round, its inputs and its attempts."""

    index: int
    start: float
    inputs: list[str]
    griefer: str | None = None
    griefer_node: str | None = None
    attempts: list[Attempt] = field(default_factory=list)
    end: float | None = None
    outcome: str = ""  # settled, abandoned or refused; empty while it runs
    grief: Tx | None = None  # the griefer's transfer, once sent


class ShuffleRounds(Load):
    """Shuffle rounds, one after another from a publisher at `node` (decision record 0046).

    Round $k$ has `size` inputs, the accounts `{name}-{k}-i{j}`, each holding
    `unit` and `spare` wei, and as many fresh outputs. Each attempt takes
    `coordination(rng)` seconds off chain, its inputs registering and signing
    the output list, and is then sent from `address` to `node` in one of
    three ways, its `mode`:

    - "public": a type 2 transaction that pulls `unit` from every input, in
      order, into `{name}-{k}-round` and pays it to every output (MD-5), with
      gas `gas(n)` for $n$ inputs and, if it reverts at its $m$-th pull,
      `revert_gas(m)` (BB-5), at a tip of `round_tip`;
    - "sealed": the same as an EIP-8184 sealed transaction (LU-2), which runs
      at the top of the block after the one that commits it (LU-13);
    - "lock": after half the coordination, a type 2 transaction that pulls
      the units into `{name}-{k}-escrow` and skips an input that cannot pay
      (`atomic` false), with gas `lock_gas(n)`; once a block carries it, the
      other half of the coordination among the inputs it locked; and then a
      type 2 transaction that pays every output from the escrow, with gas
      `settle_gas(n)`.

    The publisher sends nothing it can see will fail: before sending, an
    input whose balance at its node's head is below `unit`, or that has a
    transaction pending in its node's pool, is left out, and the attempt is
    *caught* and starts again without it, as a submitter that simulates a
    round before sending it would. A sent attempt fails when the block that
    includes, or executes, its round reverts it; or, while its round is still
    pending and uncommitted, once an input's balance at the publisher's head
    is below `unit`, when the publisher gives up on it as *dropped*, which is
    how a round that builders drop (BB-7) ends. A dropped round stays in the
    pools until the next attempt replaces it at its nonce, its fees raised by
    `price_bump` percent (NP-11, LU-9); if a builder includes it first, it
    reverts and counts as reverted, and an attempt sent at the nonce it took
    is sent again at the next. After a failure the publisher leaves out every
    input whose balance is below `unit` and starts the next attempt among the
    inputs left. A lock that leaves fewer than `min_size` inputs is *short*.
    A round left with fewer than `min_size` inputs is abandoned, and one the
    publisher's pool refuses is refused. The next round starts when one ends,
    `count` rounds in all.

    With `griefer`, one input of every round, at a position drawn per round,
    is an adversary's, at a node drawn per round. It signs last, and as the
    round, or under "lock" the lock, is sent, it sends a transfer of its unit
    to a fresh address at a tip `grief_tip` above the round's, from that
    node: one transaction a round. Once it has spent, it is left out.

    `rounds` holds every round.
    """

    MODES = ("public", "sealed", "lock")

    def __init__(self, name: str, *, address: str, node: str, size: int, mode: str = "public",
                 gas: Callable[[int], int], revert_gas: Callable[[int], int], data_size: Callable[[int], int],
                 lock_gas: Callable[[int], int] | None = None, settle_gas: Callable[[int], int] | None = None,
                 coordination: Callable[[random.Random], float], unit: int, spare: int,
                 round_tip: int = 2_000_000_000, griefer: bool = False, grief_tip: int = 1_000_000_000,
                 min_size: int = 8, count: int = 20, price_bump: int = 10, start: float = 0.0,
                 fee_multiplier: int = 2):
        if mode not in self.MODES:
            raise ValueError(mode)
        super().__init__(name, rate=0.0, senders=[address], tip=fixed(round_tip), start=start,
                         fee_multiplier=fee_multiplier)
        self.address = address
        self.node = node
        self.size = size
        self.mode = mode
        self.gas = gas
        self.revert_gas = revert_gas
        self.data_size = data_size
        self.lock_gas = lock_gas or (lambda n: gas(n) // 2)
        self.settle_gas = settle_gas or (lambda n: gas(n) - gas(n) // 2)
        self.coordination = coordination
        self.unit = unit
        self.spare = spare
        self.round_tip = round_tip
        self.griefer = griefer
        self.grief_tip = grief_tip
        self.min_size = min_size
        self.count = count
        self.price_bump = price_bump
        self.rounds: list[Round] = []
        self._sent: dict[str, tuple[Round, Attempt]] = {}  # every round, lock or settlement sent, by hash
        self._committed: set[str] = set()  # under "sealed", what a block has committed
        self._pending: Tx | SealedTx | None = None  # the last sent at the publisher's next nonce

    def accounts(self) -> dict[str, int]:
        """The inputs' genesis balances."""
        return {f"{self.name}-{k}-i{j}": self.unit + self.spare for k in range(self.count) for j in range(self.size)}

    def attach(self, sim) -> None:
        super().attach(sim)
        self.sim = sim
        self.timing = random.Random(f"{sim.scenario.seed}/{self.name}/coordination")
        sim.net.nodes[self.node].import_hooks.append(self._import)
        sim.sched.at(max(self.start, sim.sched.now), self._next)

    @property
    def current(self) -> Round | None:
        return self.rounds[-1] if self.rounds and not self.rounds[-1].outcome else None

    def _next(self) -> None:
        if len(self.rounds) >= self.count:
            return
        k = len(self.rounds)
        inputs = [f"{self.name}-{k}-i{j}" for j in range(self.size)]
        r = Round(k, self.sim.sched.now, inputs)
        if self.griefer:
            r.griefer = inputs[self.rng.randrange(self.size)]
            r.griefer_node = self.routing.choice(sorted(self.sim.net.nodes))
        self.rounds.append(r)
        self._coordinate(r)

    def _coordinate(self, r: Round) -> None:
        t = self.coordination(self.timing)
        if self.mode == "lock":
            self.sim.sched.after(t / 2, lambda: self._send(r, t / 2))
        else:
            self.sim.sched.after(t, lambda: self._send(r))

    def _end(self, r: Round, outcome: str) -> None:
        r.outcome, r.end = outcome, self.sim.sched.now
        self._next()

    def _again(self, r: Round) -> None:
        """The next attempt, among the inputs that can still pay."""
        r.inputs = [i for i in r.inputs if not self._short(i)]
        if len(r.inputs) < self.min_size:
            self._end(r, "abandoned")
            return
        self._coordinate(r)

    def _view(self):
        return self.sim.net.nodes[self.node].pool

    def _short(self, i: str) -> bool:
        return self._view().state.balance(i) < self.unit

    def _busy(self, i: str) -> bool:
        lst = self._view().nonce.pending.get(i)
        return bool(lst) and not lst.empty()

    def _nonce(self) -> int:
        return self._pending.nonce if self._pending is not None else self._view().state.nonce(self.address)

    def _fees(self) -> tuple[int, int]:
        """A fresh tip and fee cap, raised to replace what waits at the publisher's next nonce (NP-11, LU-9)."""
        tip, max_fee = self.round_tip, self.fee_cap(self.sim, self.round_tip)
        old = self._pending
        if old is not None:
            bump = lambda v: -(-v * (100 + self.price_bump) // 100) + 1  # noqa: E731
            tip, max_fee = max(tip, bump(old.tip)), max(max_fee, bump(old.max_fee))
        return tip, max_fee

    def _round(self, r: Round, label: str, nonce: int, tip: int, max_fee: int) -> Tx | SealedTx:
        n, k = len(r.inputs), r.index
        pulls = tuple((i, self.unit) for i in r.inputs)
        if self.mode == "lock":
            return Tx(self.address, nonce=nonce, gas=self.lock_gas(n), max_fee=max_fee, tip=tip,
                      to=f"{self.name}-{k}-escrow", data_size=self.data_size(n) // 2, pulls=pulls, atomic=False,
                      label=f"{label}-lock")
        # where it would revert: at the griefer's pull if it is in this attempt, else at the last
        m = r.inputs.index(r.griefer) + 1 if r.griefer in r.inputs else n
        pays = tuple((f"{label}-o{j}", self.unit) for j in range(n))
        if self.mode == "sealed":
            return SealedTx(self.address, nonce=nonce, max_fee=max_fee, tip=tip, gas_limit=self.gas(n),
                            size=110 + self.data_size(n), to=f"{self.name}-{k}-round", pulls=pulls, pays=pays,
                            revert_used=self.revert_gas(m), label=label)
        return Tx(self.address, nonce=nonce, gas=self.gas(n), max_fee=max_fee, tip=tip,
                  to=f"{self.name}-{k}-round", data_size=self.data_size(n), pulls=pulls, pays=pays,
                  revert_gas_used=self.revert_gas(m), label=label)

    def _submit(self, r: Round, a: Attempt, tx: Tx | SealedTx) -> bool:
        now = self.sim.sched.now
        self.sim.recorder.submitted(tx, now, self.node)
        if self.sim.net.nodes[self.node].submit(tx) != "ok":
            a.outcome, a.end = "refused", now
            self._end(r, "refused")
            return False
        self._sent[tx.hash] = (r, a)
        self._pending = tx
        return True

    def _send(self, r: Round, rest: float = 0.0) -> None:
        """An attempt among `r.inputs`: under "lock" its lock, with `rest` seconds of coordination left."""
        if r.outcome:
            return
        a = Attempt(len(r.inputs), rest=rest)
        r.attempts.append(a)
        now = self.sim.sched.now
        if any(self._short(i) or self._busy(i) for i in r.inputs):
            a.outcome, a.end = "caught", now
            r.inputs = [i for i in r.inputs if not self._busy(i)]
            self._again(r)
            return
        tip, max_fee = self._fees()
        tx = self._round(r, f"{self.name}-{r.index}-{len(r.attempts)}", self._nonce(), tip, max_fee)
        self._grieve(r, tip)
        a.sent = now
        if self.mode == "lock":
            a.lock = tx
        else:
            a.tx = tx
        self._submit(r, a, tx)

    def _resend(self, r: Round, a: Attempt) -> None:
        """`a`'s round again, at the publisher's next nonce, since an earlier version took the one it had."""
        self._pending = None
        tip, max_fee = self._fees()
        tx = self._round(r, a.tx.label, self._nonce(), tip, max_fee)
        a.tx = tx
        self._submit(r, a, tx)

    def _grieve(self, r: Round, tip: int) -> None:
        """The griefer, if its seat is in this attempt, sends its unit away as it signs."""
        if r.griefer is None or r.griefer not in r.inputs or r.grief is not None:
            return
        grief_tip = tip + self.grief_tip
        r.grief = Tx(r.griefer, nonce=0, gas=21000, max_fee=self.fee_cap(self.sim, grief_tip), tip=grief_tip,
                     value=self.unit, to=f"{r.griefer}-fresh", label=f"{r.griefer}-grief")
        self.sim.recorder.submitted(r.grief, self.sim.sched.now, r.griefer_node)
        self.sim.net.nodes[r.griefer_node].submit(r.grief)

    def _import(self, node, block) -> None:
        now = self.sim.sched.now
        if self._pending is not None and self._view().state.nonce(self.address) > self._pending.nonce:
            self._pending = None
        self._committed.update(c.tx.hash for c in block.commitments if c.tx.hash in self._sent)
        reverted = {tx.hash for tx in block.reverted}
        for tx in (block.decrypted if self.mode == "sealed" else block.txs):
            hit = self._sent.get(tx.hash)
            if hit is None:
                continue
            r, a = hit
            if tx == a.lock:
                self._locked(r, a)
                continue
            live = r.outcome == "" and a.end is None  # not given up as dropped
            if tx.hash in reverted:
                a.outcome, a.gas_lost = "reverted", tx.reverted_used
                a.end = a.end if a.end is not None else now
                if live:
                    self._again(r)
            else:
                a.outcome, a.end = "settled", now
                if r.outcome == "":
                    self._end(r, "settled")
        r = self.current
        if r is None or not r.attempts:
            return
        a = r.attempts[-1]
        if a.end is not None or a.tx is None:
            return
        if self.mode == "sealed" and a.tx.hash in self._committed:
            return
        if self._view().state.nonce(self.address) > a.tx.nonce:  # an earlier version took its nonce
            self._resend(r, a)
            return
        if self.mode != "lock" and any(self._short(i) for i in r.inputs):
            a.outcome, a.end = "dropped", now  # it waits on a pull it cannot make, and BB-7's builders drop it
            self._again(r)

    def _locked(self, r: Round, a: Attempt) -> None:
        """A block carried `a`'s lock: the inputs it locked, and the settlement once they have signed."""
        a.locked = self.sim.sched.now
        escrow = self._view().state.balance(f"{self.name}-{r.index}-escrow")
        r.inputs = [i for i in r.inputs if self._view().state.nonce(i) == 0]  # an input that spent was skipped
        assert len(r.inputs) == escrow // self.unit, (r.index, len(r.inputs), escrow)
        if len(r.inputs) < self.min_size:
            a.outcome, a.end = "short", self.sim.sched.now
            self._end(r, "abandoned")
            return
        self.sim.sched.after(a.rest, lambda: self._settle(r, a))

    def _settle(self, r: Round, a: Attempt) -> None:
        n, k = len(r.inputs), r.index
        tip, max_fee = self._fees()
        label = f"{self.name}-{k}-{len(r.attempts)}"
        a.tx = Tx(self.address, nonce=self._nonce(), gas=self.settle_gas(n), max_fee=max_fee, tip=tip,
                  to=f"{self.name}-{k}-escrow", data_size=self.data_size(n) - self.data_size(n) // 2,
                  pays=tuple((f"{label}-o{j}", self.unit) for j in range(n)), label=f"{label}-settle")
        self._submit(r, a, a.tx)
