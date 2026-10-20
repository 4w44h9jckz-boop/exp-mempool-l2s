r"""Nodes, each with its own pool, gossiping transactions the way go-ethereum's `eth` handler does.

Read from go-ethereum at the commit `docs/spec/README.md` pins: `eth/handler.go`
(`BroadcastTransactions`, `choosePeers`) and `eth/fetcher/tx_fetcher.go`
(`Notify`, `Enqueue`, `handleAddErrors`).

- **Broadcast.** A node that sees a transaction become executable sends it in
  full to a fixed set of $\lceil\sqrt{n}\rceil$ of its $n$ peers, chosen per
  sender by a keyed hash so that one sender's transactions always take the same
  first hops, and announces its hash to every other peer. A peer known to have
  the transaction is sent nothing, including one in the direct set. A
  transaction over 4096 bytes is only announced (EIP-5793; `txMaxBroadcastSize`).
- **Fetch.** A node that hears an announcement ignores it if its pool holds the
  transaction, if the transaction was in a block the node imported, or if the
  pool refused it as underpriced in the last five minutes (`ErrUnderpriced`,
  `ErrReplaceUnderpriced`, `ErrTxGasPriceTooLow`; `maxTxUnderpricedTimeout`).
  Otherwise it waits `arrive_timeout` for a push and then fetches from the
  first peer that announced it. A transaction refused for any other reason is
  not remembered: a later announcement from another peer fetches it again,
  and the pool decides again.
- **Local submission** (`eth_sendRawTransaction`) goes straight to the pool,
  whatever the node has seen before.

A node never sends a peer a transaction it knows the peer has: one the peer
sent or announced to it, or one it sent or announced to the peer. Not
modelled: bandwidth, message size limits, request batching windows, retries of
a failed fetch from another announcer, peer scoring, blob gossip. Decision
record 0004.

**Wrappers** (EIP-8288, `docs/spec/05-aggregation.md`), under a profile with
dependency frames. A transaction with dependencies travels only in wrappers
and is never broadcast or announced on its own. A user submits a mode 0
wrapper to a node, which checks it and admits its transactions (AG-5, AG-6).
Every `aggregation_interval`, at a phase drawn per node, a node builds its
aggregate (AG-7) and sends it to every peer `prove_delay` seconds later, plus
its proving time (AG-9), plus the link's latency. A node proves one aggregate
at a time: a tick that comes while it is still proving the last is skipped,
and counted in `busy`. With `forward_wrappers`, a node also sends every mode 0
wrapper it accepts to every peer but the one it came from, once. Decision
record 0013.

**Sealed transactions** (EIP-8184, `docs/spec/06-lucid.md`) are gossiped as
transactions of their `size`, which the EIP leaves to the client; a committed
one counts as on chain.

**Budget hints** (ethereum/EIPs pull request 12301, which leaves them to a
future eth wire protocol). With `announce_budget`, an announcement carries
each frame transaction's structural rule 6 budget, and a node does not fetch
one whose budget is above its own `max_verify_gas`; a push is unaffected.
With `remember_budget` above 0, the node also ignores later announcements of
that hash for that many seconds, as it does an underpriced one. A node in
`liars` relays nothing and includes nothing, and with hints announces every
hash it hears of to every peer as over any bound. Decision record 0016.

**Observers** (decision record 0021). With `record_heard`, every node
records, for each hash, when it first heard of it and from which peer, by a
push, a fetch's answer or an announcement, or that a local client submitted
it. A node in `spies` takes no part in the random topology; once it is
drawn, the spy is connected to every other node, and it relays nothing, so
it hears from every node and changes the paths of nothing but the pushes it
takes. Not modelled: a spy's own timing, such as reconnecting to learn more,
and what a node hears inside a wrapper.

**Proofs verified in batches** (decision record 0025). With `batch_window`
set, a transaction whose hash is in the network's `proofs` carries a proof
under one shared key, valid or not, that a node verifies before its pool
sees the transaction, on one core: each on arrival when the window is 0, or
else held from the first arrival of a batch until `batch_window` seconds
later, or until `batch_max` are held, and verified as one batch, which is
bisected when it fails (`sim/emem_sim/batch.py`). The verification's time
delays the admission. A transaction whose proof failed is refused and
remembered; one held or being verified is known, so a node does not fetch it
again, nor verifies one in a block it imported. Not modelled: a node that
drops or blocks the peer that sent an invalid proof, and a pool that admits
before the proof is verified.

**Work** (decision record 0037). Every node counts its aggregator's events
(`emem.aggregation.Aggregator._count`: checks, proofs, recursive STARKs, and
folds and covers) in `work`, by the origin of the message it was handling,
the load that handed it the wrapper, `peer` for one from a peer, or `self`
for its own aggregate, and by the load that made the transaction, the first
word of its label. `wrapper_hooks` are told of every wrapper a node checks and its answer,
and `aggregate_hooks` of every aggregate it makes. Every node also counts in
`inbound` the proofs that reach it in wrappers, a mode 1 wrapper's STARK as
one, by the wrapper's kind and its first transaction's maker, `aggregate`
for a mode 1 wrapper.

**Relays** (`docs/spec/10-claim-gated-admission.md`, CG-7, decision record
0038). A node whose pool's profile has `claims` and not `verifies` refuses
aggregates, verifies no proof, and sends every mode 0 wrapper it accepts to
every peer but the one it came from, once, whatever `forward_wrappers` says.
Which nodes may propose is the chain's `proposer`.
"""

from __future__ import annotations

import hashlib
import math
import random
from collections import Counter
from dataclasses import dataclass
from typing import Callable

from emem import Aggregator, FrameTx, TxPool
from emem.framepool.prefix import analyse

from .batch import verify
from .events import Scheduler
from .metrics import Recorder

MAX_BROADCAST_SIZE = 4096  # go-ethereum eth/handler.go, txMaxBroadcastSize
UNDERPRICED = frozenset({"ErrUnderpriced", "ErrReplaceUnderpriced", "ErrTxGasPriceTooLow"})
INFLATED = 2**63  # the budget a liar announces


def budget(tx, cfg) -> int | None:
    """Structural rule 6's budget of a frame transaction, FP-6's sum, which a budget hint carries."""
    prefix = analyse(tx, cfg) if isinstance(tx, FrameTx) else None
    if prefix is None:
        return None
    return sum(f.exec_gas for f in prefix.frames) + sum(s.verify_gas for s in tx.signatures)


@dataclass(frozen=True)
class NetworkConfig:
    degree: int = 8
    latency: tuple[float, float] = (0.02, 0.10)  # one-way, seconds, uniform per link
    arrive_timeout: float = 0.5  # txArriveTimeout
    underpriced_timeout: float = 300.0  # maxTxUnderpricedTimeout
    prove_delay: float = 0.0  # seconds from an aggregation tick until the aggregate is sent (EIP-8288)
    announce_budget: bool = False  # announcements carry a frame transaction's rule 6 budget (decision record 0016)
    remember_budget: float = 0.0  # seconds a node ignores a hash once announced above its bound; 0 forgets
    liars: tuple[str, ...] = ()  # nodes that relay nothing and, with hints, announce every hash as over any bound
    record_heard: bool = False  # every node records when, and from which peer, it first heard of each hash
    spies: tuple[str, ...] = ()  # nodes connected to every other node that relay nothing (decision record 0021)
    batch_window: float | None = None  # seconds a node holds proofs to verify them as a batch; None: not modelled
    batch_max: int = 0  # a batch is verified as soon as it holds this many; 0: no bound (decision record 0025)


class Node:
    def __init__(self, name: str, pool: TxPool, net: "Network"):
        self.name = name
        self.pool = pool
        self.net = net
        self.key = 0  # the broadcast key, drawn when the node joins the network
        self.peers: list[str] = []
        self.peer_known: dict[str, set[str]] = {}
        self.fetching: dict[str, list[str]] = {}
        self.on_chain: set[str] = set()
        self.underpriced: dict[str, float] = {}
        self.import_hooks: list[Callable[["Node", object], None]] = []
        self.admit_hooks: list[Callable[["Node", object, str], None]] = []  # every answer to a transaction
        self._direct: dict[str, set[str]] = {}
        self.aggregator = Aggregator(pool) if pool.frame.config.dependency_frames else None
        self.forwarded: set[tuple] = set()  # the mode 0 wrappers it has relayed
        self.liar = name in net.config.liars
        self.spy = name in net.config.spies
        self.heard: dict[str, tuple[float, str]] = {}  # with record_heard: hash -> when and from whom; "" is local
        self.heavy: dict[str, float] = {}  # hashes announced above its bound, when it remembers them
        self.lied: set[str] = set()
        self.held: list = []  # with batch_window: proof-carrying transactions waiting for their batch to close
        self.holding: set[str] = set()  # their hashes, and those of the batches being verified
        self.rejected: set[str] = set()  # transactions whose proof failed here
        self.window = 0  # the generation of the open batch; a timer closes only its own
        self.cpu_free = 0.0  # when the node's verifier is next idle
        self.verify_ms = 0.0
        self.checks = 0  # batch verifications, a bisection's included
        self.batches: list[int] = []  # the size of each batch verified
        self.proving_until = 0.0  # when the aggregate it is proving is done (AG-9)
        self.busy = 0  # aggregation ticks skipped because it was still proving
        self.work: Counter = Counter()  # by (origin, event, load): its aggregator's events (decision record 0037)
        self.inbound: Counter = Counter()  # by (kind, maker): the proofs that reached it in wrappers
        self._origin = ""  # the origin of the message being handled
        self.wrapper_hooks: list[Callable[["Node", object, object, str], None]] = []  # (node, wrapper, answer, origin)
        self.aggregate_hooks: list[Callable[["Node", object], None]] = []  # (node, aggregate)
        if self.aggregator is not None:
            self.aggregator.observe = self._observe

    @property
    def now(self) -> float:
        return self.net.sched.now

    def use_pool(self, pool: TxPool) -> None:
        """Replace the pool before the run starts, for a scenario whose nodes differ in profile."""
        self.pool = pool
        self.aggregator = Aggregator(pool) if pool.frame.config.dependency_frames else None
        if self.aggregator is not None:
            self.aggregator.observe = self._observe

    def _observe(self, event: str, tx) -> None:
        load = tx.label.split("-", 1)[0] if tx is not None else ""
        self.work[(self._origin, event, load)] += 1

    # --- inputs --------------------------------------------------------------

    def _hear(self, h: str, peer: str) -> None:
        if self.net.config.record_heard and h not in self.heard:
            self.heard[h] = (self.now, peer)

    def submit(self, tx) -> str:
        """A transaction from a local client (eth_sendRawTransaction)."""
        self._hear(tx.hash, "")
        if self.pool.get(tx.hash) is not None or tx.hash in self.holding:
            return "ErrAlreadyKnown"
        if tx.hash in self.rejected:
            return "ErrInvalidProof"
        if self._proof(tx):
            self._hold(tx)
            return "Held"
        return self._add([tx])[0]

    def receive(self, txs: list, from_peer: str) -> None:
        """Transactions pushed by a peer, or its answer to a fetch."""
        fresh = []
        for tx in txs:
            self.peer_known[from_peer].add(tx.hash)
            self._hear(tx.hash, from_peer)
            self.fetching.pop(tx.hash, None)
            if self.liar:
                self._lie(tx.hash)
            if self.pool.get(tx.hash) is None and tx.hash not in self.holding and tx.hash not in self.rejected \
                    and tx not in fresh:
                fresh.append(tx)
        rest = []
        for tx in fresh:
            if self._proof(tx):
                self._hold(tx)
            else:
                rest.append(tx)
        if rest:
            self._add(rest)

    def _add(self, txs: list) -> list[str]:
        results = self.pool.add(txs, self.now)
        for tx, result in zip(txs, results):
            self.net.recorder.admission(tx, self.name, result)
            if result in UNDERPRICED:
                self.underpriced[tx.hash] = self.now
            for hook in self.admit_hooks:
                hook(self, tx, result)
        self.drain()
        return results

    def _proof(self, tx) -> bool:
        """Whether `tx`'s proof is verified before the pool sees it; one in a block imported here is not, and the
        pool refuses it on its nonce."""
        return self.net.config.batch_window is not None and tx.hash in self.net.proofs and tx.hash not in self.on_chain

    def _hold(self, tx) -> None:
        """Hold a proof-carrying transaction for its batch, opening one if none is open."""
        cfg = self.net.config
        self.holding.add(tx.hash)
        self.held.append(tx)
        if cfg.batch_window == 0 or (cfg.batch_max and len(self.held) >= cfg.batch_max):
            self._close()
        elif len(self.held) == 1:
            self.window += 1
            self.net.sched.after(cfg.batch_window, lambda w=self.window: self._close(w))

    def _close(self, window: int | None = None) -> None:
        """Verify the held batch on the node's one verifier, then admit what passed."""
        if window is not None and window != self.window or not self.held:
            return
        batch, self.held = self.held, []
        self.window += 1
        cost, checks = verify([self.net.proofs[tx.hash] for tx in batch])
        self.verify_ms += cost
        self.checks += checks
        self.batches.append(len(batch))
        self.cpu_free = max(self.now, self.cpu_free) + cost / 1000
        self.net.sched.at(self.cpu_free, lambda: self._verified(batch))

    def _verified(self, batch: list) -> None:
        good = []
        for tx in batch:
            self.holding.discard(tx.hash)
            if not self.net.proofs[tx.hash]:
                self.rejected.add(tx.hash)
                self.net.recorder.admission(tx, self.name, "ErrInvalidProof")
            elif self.pool.get(tx.hash) is None and tx.hash not in self.on_chain:
                good.append(tx)
        if good:
            self._add(good)

    def submit_wrapper(self, wrapper, origin: str = "client") -> str | list[str]:
        """A user's wrapper, from a local client; `origin` names the load that sent it."""
        return self._wrapper(wrapper, None, origin)

    def on_wrapper(self, wrapper, from_peer: str) -> None:
        self._wrapper(wrapper, from_peer, "peer")

    def _wrapper(self, wrapper, source: str | None, origin: str) -> str | list[str]:
        """AG-5 and AG-6, then relaying under `forward_wrappers` (AG-7)."""
        previous, self._origin = self._origin, origin
        try:
            results = self.aggregator.receive(wrapper, self.now)
        finally:
            self._origin = previous
        for hook in self.wrapper_hooks:
            hook(self, wrapper, results, origin)
        kind = "user" if source is None else ("aggregate" if wrapper.mode == 1 else "forwarded")
        self.net.recorder.wrapper_received(wrapper, self.name, results, kind)
        if isinstance(results, str):
            return results
        for entry, result in zip(wrapper.txs, results):
            if isinstance(entry, FrameTx) and result != "ErrAlreadyKnown":
                self.net.recorder.admission(entry, self.name, result)
                for hook in self.admit_hooks:
                    hook(self, entry, result)
        self.drain()
        cfg = self.pool.frame.config
        if wrapper.mode == 0 and (cfg.forward_wrappers or (cfg.claims and not cfg.verifies)):  # CG-7 step 4
            key = tuple(e if isinstance(e, str) else e.hash for e in wrapper.txs)
            if key not in self.forwarded:
                self.forwarded.add(key)
                for p in self.peers:
                    if p != source:
                        self.net.send_wrapper(self, p, wrapper, "forwarded")
        return results

    def aggregate(self) -> None:
        """One aggregation tick (AG-7), skipped while the last aggregate is still being proven (AG-9)."""
        if self.now < self.proving_until - 1e-9:  # done at the tick itself is not busy
            self.busy += 1
            return
        previous, self._origin = self._origin, "self"
        try:
            wrapper = self.aggregator.aggregate()
        finally:
            self._origin = previous
        if wrapper is None:
            return
        for hook in self.aggregate_hooks:
            hook(self, wrapper)
        proving = self.aggregator.proving_time / 1000
        self.proving_until = self.now + proving
        delay = self.net.config.prove_delay + proving
        for p in self.peers:
            self.net.send_wrapper(self, p, wrapper, "aggregate", delay)

    def on_announce(self, hashes: list[str], from_peer: str, budgets: list[int | None] | None = None) -> None:
        for i, h in enumerate(hashes):
            self.peer_known[from_peer].add(h)
            self._hear(h, from_peer)
            if self.liar:
                self._lie(h)
            if self.pool.get(h) is not None or h in self.on_chain or h in self.holding or h in self.rejected:
                continue
            refused = self.underpriced.get(h)
            if refused is not None:
                if self.now - refused <= self.net.config.underpriced_timeout:
                    continue
                del self.underpriced[h]
            heavy = self.heavy.get(h)
            if heavy is not None:
                if self.now - heavy <= self.net.config.remember_budget:
                    continue
                del self.heavy[h]
            if budgets is not None and budgets[i] is not None and budgets[i] > self.pool.frame.config.max_verify_gas:
                self.net.recorder.skipped(h)
                if self.net.config.remember_budget > 0:
                    self.heavy[h] = self.now
                continue
            if h in self.fetching:
                self.fetching[h].append(from_peer)
                continue
            self.fetching[h] = [from_peer]
            self.net.sched.after(self.net.config.arrive_timeout, lambda h=h: self._fetch(h))

    def _lie(self, h: str) -> None:
        """A liar's announcement of `h`, once, to every peer not known to have it, as over any bound."""
        if h in self.lied or not self.net.config.announce_budget:
            return
        self.lied.add(h)
        for p in self.peers:
            if h not in self.peer_known[p]:
                self.peer_known[p].add(h)
                self.net.announce(self, p, [h], [INFLATED])

    def _fetch(self, h: str) -> None:
        announcers = self.fetching.pop(h, None)
        if announcers:
            self.net.request(self, announcers[0], h)

    def on_block(self, block, state, finalized=()) -> None:
        self.on_chain.update(tx.hash for tx in block.txs)
        self.on_chain.update(c.tx.hash for c in block.commitments)
        self.pool.reset(block.head, state, self.now)
        if finalized:
            self.pool.finalize(list(finalized), self.now)
        self.drain()
        for hook in self.import_hooks:
            hook(self, block)

    def tick(self) -> None:
        self.pool.tick(self.now)
        self.drain()

    # --- outputs -------------------------------------------------------------

    def drain(self) -> None:
        """Read what the pools logged; gossip what became executable."""
        executable = []
        for log in (self.pool.nonce.log, self.pool.frame.log, self.pool.sealed.log):
            for kind, tx, detail in log:
                if kind == "pending":
                    executable.append(tx)
                    self.net.recorder.pending(tx, self.name, self.now)
                elif kind == "dropped":
                    self.net.recorder.dropped(tx, self.name, detail)
            log.clear()
        if executable:
            self.broadcast(executable)

    def direct_peers(self, sender: str) -> set[str]:
        """go-ethereum `choosePeers`: the ceil(sqrt(n)) peers with the lowest keyed hash of (node, peer, sender)."""
        chosen = self._direct.get(sender)
        if chosen is None:
            def score(peer: str) -> bytes:
                return hashlib.blake2b(f"{self.name}|{peer}|{sender}".encode(), digest_size=8,
                                       key=self.key.to_bytes(8, "big")).digest()
            ranked = sorted(self.peers, key=score)
            chosen = set(ranked[:math.ceil(math.sqrt(len(ranked)))])
            self._direct[sender] = chosen
        return chosen

    def broadcast(self, txs: list) -> None:
        if self.liar or self.spy:
            return
        direct: dict[str, list] = {}
        announce: dict[str, list] = {}
        for tx in txs:
            if self.pool.status(tx.hash) == "unknown":
                continue
            if self.aggregator is not None and getattr(tx, "dependencies", ()):
                continue  # it travels in wrappers
            pushed = self.direct_peers(tx.sender) if tx.encoded_size <= MAX_BROADCAST_SIZE else set()
            for p in self.peers:
                if tx.hash in self.peer_known[p]:
                    continue
                self.peer_known[p].add(tx.hash)
                if p in pushed:
                    direct.setdefault(p, []).append(tx)
                else:
                    announce.setdefault(p, []).append(tx)
        for p, batch in direct.items():
            self.net.send_txs(self, p, batch)
        hints = self.net.config.announce_budget
        for p, batch in announce.items():
            self.net.announce(self, p, [tx.hash for tx in batch],
                              [budget(tx, self.pool.frame.config) for tx in batch] if hints else None)


class Network:
    def __init__(self, sched: Scheduler, rng: random.Random, recorder: Recorder, config: NetworkConfig):
        self.sched = sched
        self.rng = rng
        self.recorder = recorder
        self.config = config
        self.nodes: dict[str, Node] = {}
        self.proofs: dict[str, bool] = {}  # with batch_window: hash -> whether its proof is valid
        self.latency: dict[tuple[str, str], float] = {}

    def add(self, node: Node) -> None:
        node.key = self.rng.getrandbits(64)
        self.nodes[node.name] = node

    def connect(self, a: str, b: str) -> None:
        if a == b or b in self.nodes[a].peers:
            return
        lat = self.rng.uniform(*self.config.latency)
        for x, y in ((a, b), (b, a)):
            self.nodes[x].peers.append(y)
            self.nodes[x].peer_known[y] = set()
            self.latency[(x, y)] = lat

    def random_topology(self) -> None:
        """Each node dials random peers until it has `degree` of them (inbound links count); then each spy is
        connected to every other node."""
        names = [n for n in self.nodes if n not in self.config.spies]
        for a in names:
            attempts = 0
            while len(self.nodes[a].peers) < min(self.config.degree, len(names) - 1) and attempts < 50 * len(names):
                attempts += 1
                b = self.rng.choice(names)
                if len(self.nodes[b].peers) < 2 * self.config.degree:
                    self.connect(a, b)
        for spy in self.config.spies:
            for b in self.nodes:
                self.connect(spy, b)

    def send_txs(self, src: Node, dst: str, txs: list) -> None:
        self.sched.after(self.latency[(src.name, dst)], lambda: self.nodes[dst].receive(txs, src.name))

    def send_wrapper(self, src: Node, dst: str, wrapper, kind: str, delay: float = 0.0) -> None:
        self.recorder.wrapper_sent(wrapper, src.name, kind)
        first = next((e for e in wrapper.txs if isinstance(e, FrameTx)), None)
        maker = "aggregate" if wrapper.mode == 1 else (first.label.split("-", 1)[0] if first is not None else "")
        self.nodes[dst].inbound[(kind, maker)] += 1 if wrapper.mode == 1 else len(wrapper.proofs)
        self.sched.after(delay + self.latency[(src.name, dst)], lambda: self.nodes[dst].on_wrapper(wrapper, src.name))

    def announce(self, src: Node, dst: str, hashes: list[str], budgets: list[int | None] | None = None) -> None:
        self.sched.after(self.latency[(src.name, dst)], lambda: self.nodes[dst].on_announce(hashes, src.name, budgets))

    def request(self, src: Node, dst: str, h: str) -> None:
        lat = self.latency[(src.name, dst)]

        def respond():
            tx = self.nodes[dst].pool.get(h)
            if tx is not None:
                self.sched.after(lat, lambda: src.receive([tx], dst))

        self.sched.after(lat, respond)
