r"""The chain: one block per slot, built by a proposer from its own pool and delivered to every node.

Finality follows the beacon chain's happy path, read from ethereum/consensus-specs
at `c489a99077c16bad7d75053257c50633d12d314d`, `specs/phase0/beacon-chain.md`:
with every validator attesting, `weigh_justification_and_finalization` at the
end of epoch $E$ justifies $E$ and finalizes the checkpoint of $E - 1$, whose
block is the first of that epoch, and a node learns it when it imports the
first block of epoch $E + 1$. Block $n$ is at slot $n$ (no slot is missed), so a
node importing block $s$ knows every block up to slot $32(\lfloor s/32 \rfloor - 2)$
is final, and a block becomes final 64 to 95 slots after it was produced.
Each block carries the blocks it newly finalizes, with their frame gas by
sender, and a node hands them to its pool's `finalize` (MD-8) on import. Not
modelled: participation below two thirds, reorgs, and a missed slot, except
under an inclusion-list profile (below), where finality still counts blocks
rather than slots. A block is at the slot it was built for, so a slot without
a block leaves a gap in the slots of the heads (RR-2).

The proposer of each slot is the next in turn, through every node or through a
tuple of names, or with `draw` one drawn uniformly from the tuple from a random
stream of its own, so that a run of slots whose builders share a policy is as
long as chance makes it rather than as the order fixes it.

A transaction whose execution reverts is in its block and pays for the gas it
used (BB-5), and the block's record lists it under `reverted`; with
`drop_reverting`, every builder leaves such a transaction out instead (BB-7).

Under a sealed profile (EIP-8184) each block commits sealed transactions from
its proposer's pool and executes the previous block's commitments first
(LU-12, LU-13), whoever proposed it; the chain carries them from one slot to
the next. A key publisher in `key_publishers`, such as a `KeyCommittee`, is
asked once a block is built which of its commitments' keys will not be in
time, and the chain carries those to the next block as not `revealed`
(decision record 0032). A builder that filters leaves sealed transactions out
as well as the rest.

Under an inclusion-list profile (`07-focil.md`) a committee of nodes, drawn
each slot from a random stream of its own, builds its ILs from its pools at
`il_at` seconds into the slot, and the next block must satisfy them (IL-6) or
the slot has no block (IL-8). Builders and includers named in `filtering`
and `filtering_includers` leave out the transactions `censored` names. A
filtering builder whose block would leave a listed one out does one of four
things, its `strategy`:

- `stuff`: it buys the gas that excuses the omission (IL-6) with a
  transaction of its own, which burns the base fee and pays no tip;
- `miss`: it proposes the block anyway, and the slot has no block;
- `yield`: the slot goes to the next builder in turn that does not filter,
  which builds it honestly, as a proposer takes the best bid that satisfies
  the ILs; `miss` if every builder filters;
- `cheapest`: it stuffs if the stuffed block's priority fees cover the base
  fee it burns, and yields otherwise.

Each slot a filtering builder was due records what filtering cost it: the
priority fees of the block it would have built honestly from the same pool
and ILs, less those it was paid, plus the base fee it burned; and the gas its
filtered block left unused before it did anything about the ILs. Decision
record 0018.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, replace
from typing import Callable

from emem import FOCIL_PROFILES, Commitment, FocilConfig, Head, State, Tx, build_block, build_il, omission
from emem.focil import admitted, listed, valid_at_end

from .events import Scheduler
from .metrics import Recorder
from .network import Network


@dataclass(frozen=True)
class ChainConfig:
    slot_time: float = 12.0
    proposer: str | tuple[str, ...] = "rotate"  # "rotate" through the nodes or through a tuple of names, or one name
    draw: bool = False  # draw each slot's proposer from them, from a stream of its own, instead of in turn
    block_delay: tuple[float, float] = (0.1, 1.0)  # seconds until a non-proposer node imports the block
    min_tip: int = 1_000_000  # go-ethereum miner default, 0.001 gwei
    slots_per_epoch: int = 32  # SLOTS_PER_EPOCH
    focil: FocilConfig = FOCIL_PROFILES["off"]  # IL-1
    il_at: float = 8.0  # seconds into a slot at which its includers build their ILs
    censored: Callable[[object], bool] | None = None  # what filtering builders and includers leave out
    filtering: frozenset[str] = frozenset()  # builders that filter
    filtering_includers: frozenset[str] = frozenset()  # includers that filter
    strategy: str = "stuff"  # what a filtering builder does about a listed transaction (module docstring)
    dimensions: str = "one"  # BB-6: "two" counts EIP-8037's state gas apart from execution gas
    drop_reverting: bool = False  # BB-7: every builder leaves out what would revert


def tips(block) -> int:
    """The priority fees a block pays its proposer, a reverted transaction's at the gas it used (BB-5)."""
    base_fee = block.head.base_fee
    return sum(min(tx.reverted_used if tx in block.reverted else tx.used, tx.gas_limit) * tx.effective_tip(base_fee)
               for tx in block.txs)


class Chain:
    def __init__(self, sched: Scheduler, net: Network, recorder: Recorder, head: Head, state: State,
                 config: ChainConfig, rng: random.Random, committee_rng: random.Random | None = None,
                 proposer_rng: random.Random | None = None):
        self.sched = sched
        self.net = net
        self.recorder = recorder
        self.head = head
        self.state = state
        self.config = config
        self.rng = rng
        self._slot_index = 0
        self.frame_gas: dict[int, dict[str, int]] = {}  # by block number, until final
        self.final = 0  # the highest final block number; genesis is final
        self.commitments: tuple = ()  # the last block's sealed commitments, which the next one executes
        self.committee_rng = committee_rng or random.Random(0)
        self.proposer_rng = proposer_rng or random.Random(0)
        self.ils: tuple = ()  # the ILs the next block must satisfy
        self._missed = 0  # slots without a block since the last one
        # Each called with a block once it is built; returns the hashes of its commitments whose keys are withheld.
        self.key_publishers: list[Callable[[object], set[str]]] = []

    def start(self) -> None:
        self.sched.every(self.config.slot_time, self._slot)
        if self.config.focil.enabled:
            self.sched.every(self.config.slot_time, self._build_ils, start=self.sched.now + self.config.il_at)

    def _build_ils(self) -> None:
        """IL-2, by a committee drawn for this slot."""
        cfg = self.config
        names = self.committee_rng.sample(sorted(self.net.nodes), cfg.focil.committee_size)
        base_fee = self.head.next_base_fee()
        ils = []
        for name in names:
            leave_out = cfg.censored if name in cfg.filtering_includers else None
            il = build_il(self.net.nodes[name].pool, base_fee, cfg.focil, self.head, leave_out)
            ils.append(il)
            for tx in il:
                self.recorder.listed(tx, self.sched.now)
        self.ils = tuple(ils)

    def _builders(self) -> list[str]:
        if isinstance(self.config.proposer, tuple):
            return list(self.config.proposer)
        if self.config.proposer == "rotate":
            return list(self.net.nodes)
        return [self.config.proposer]

    def proposer(self):
        names = self._builders()
        if self.config.draw:
            return self.net.nodes[self.proposer_rng.choice(names)]
        return self.net.nodes[names[self._slot_index % len(names)]]

    def _next_honest(self, after: str):
        """The next builder in turn after `after` that does not filter, or None."""
        names = self._builders()
        i = names.index(after)
        for name in names[i + 1:] + names[:i]:
            if name not in self.config.filtering:
                return self.net.nodes[name]
        return None

    def _build(self, proposer, skip=None, own=()):
        cfg = self.config
        return build_block(proposer.pool, self.head, self.state, min_tip=cfg.min_tip, coinbase=proposer.name,
                           slot_time=int(cfg.slot_time) * (1 + self._missed), scheduled=self.commitments,
                           ils=self.ils, focil=cfg.focil, skip=skip, own=own,
                           slot=self.head.slot + 1 + self._missed, dimensions=cfg.dimensions,
                           drop_reverting=cfg.drop_reverting)

    def _omission(self, block, post):
        return omission(block.txs, post, block.head, block.gas, self.ils, self._frame_config, self.config.focil)

    def _filler(self, proposer, block, post) -> Tx:
        """A transaction of the builder's own that leaves too little gas for any listed one it left out."""
        head, focil = block.head, self.config.focil
        if self.config.dimensions != "one":
            raise NotImplementedError("a filler under BB-6's two dimensions")
        gas_left = head.gas_limit - head.gas_used
        present = {tx.hash for tx in block.txs}
        enforceable = set(admitted(self.ils, head, self._frame_config, focil)) if focil.frames else set()
        need = min(tx.gas_limit for tx in listed(self.ils) if tx.hash not in present and tx.gas_limit <= gas_left
                   and valid_at_end(tx, post, head, self._frame_config, focil, enforceable))
        gas = max(21000, gas_left - need + 1)
        return Tx(sender=proposer.name, nonce=self.state.nonce(proposer.name), gas=gas, max_fee=head.base_fee,
                  tip=0, to=proposer.name, label=f"filler-{head.number}")

    def _slot(self) -> None:
        cfg = self.config
        proposer = self.proposer()
        self._slot_index += 1
        self._frame_config = proposer.pool.frame.config
        filtering = cfg.censored is not None and proposer.name in cfg.filtering
        extra = {}
        if filtering:  # the counterfactual first, so the block the slot gets is its state's latest copy
            honest, _ = self._build(proposer)
            extra = {"filtering": True, "honest_tips": tips(honest), "burn": 0}
        block, post = self._build(proposer, skip=cfg.censored if filtering else None)
        if filtering:
            extra["left"] = block.head.gas_limit - block.head.gas_used  # before it does anything about the lists
            omits = cfg.focil.enabled and self._omission(block, post) is not None
            if omits and cfg.strategy in ("stuff", "cheapest"):
                filler = self._filler(proposer, block, post)
                stuffed, stuffed_post = self._build(proposer, skip=cfg.censored, own=(filler,))
                burn = filler.gas * stuffed.head.base_fee
                if cfg.strategy == "stuff" or tips(stuffed) >= burn:  # else losing the slot costs it less
                    block, post, omits = stuffed, stuffed_post, False
                    extra["burn"], extra["stuffed"] = burn, filler.gas
            if omits and cfg.strategy in ("yield", "cheapest") and (other := self._next_honest(proposer.name)):
                extra["yielded"] = proposer.name
                proposer = other
                self._frame_config = proposer.pool.frame.config
                block, post = self._build(proposer)
            extra["tips"] = 0 if "yielded" in extra else tips(block)
        if cfg.focil.enabled and self._omission(block, post) is not None:  # IL-8
            self._missed += 1
            self.ils = ()
            extra["tips"] = 0
            self.recorder.missed(self.sched.now, proposer.name, extra)
            return
        self._missed = 0
        self.ils = ()
        if cfg.dimensions == "two":  # BB-6's two sums
            extra["execution"], extra["state"] = block.gas.execution, block.gas.state
        if block.reverted:  # BB-5 and LU-13
            extra["reverted"] = tuple(t.hash for t in block.reverted)
        withheld = set().union(*(decide(block) for decide in self.key_publishers))
        self.head, self.state = block.head, post
        self.commitments = tuple(Commitment(replace(c.tx, revealed=False), c.tob) if c.tx.hash in withheld else c
                                 for c in block.commitments)
        self.recorder.block(block.head.number, self.sched.now, block.txs, block.head.base_fee,
                            block.head.gas_used, block.head.gas_limit, block.failed, proposer.name,
                            block.commitments, block.decrypted, extra)
        finalized = self._finalize(block)
        for node in self.net.nodes.values():
            delay = 0.0 if node is proposer else self.rng.uniform(*self.config.block_delay)
            self.sched.after(delay, lambda n=node: n.on_block(block, post, finalized))

    def _finalize(self, block) -> list[tuple[int, dict[str, int]]]:
        """The blocks that importing `block` finalizes, with each one's frame gas by sender."""
        gas: dict[str, int] = {}
        for tx in block.txs:
            if tx.type == 6:
                gas[tx.sender] = gas.get(tx.sender, 0) + tx.used
        number = block.head.number
        self.frame_gas[number] = gas
        epochs = self.config.slots_per_epoch
        upto = epochs * (number // epochs - 2)
        newly = [(n, self.frame_gas.pop(n)) for n in range(self.final + 1, upto + 1)]
        self.final = max(self.final, upto)
        return newly
