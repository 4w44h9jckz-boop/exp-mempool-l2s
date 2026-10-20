"""Wiring: a scenario is everything a run depends on, and a run is a function of it."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Callable

from emem import EIP_8141, GETH, Account, FramePoolConfig, Head, NoncePoolConfig, SealedPoolConfig, State, TxPool
from emem.sealed import OFF

from .chain import Chain, ChainConfig
from .events import Scheduler
from .metrics import Recorder
from .network import Network, NetworkConfig, Node
from .workload import Load, schedule


@dataclass
class Scenario:
    seed: int = 1
    nodes: int = 20
    network: NetworkConfig = field(default_factory=NetworkConfig)
    chain: ChainConfig = field(default_factory=ChainConfig)
    nonce_pool: NoncePoolConfig = GETH
    frame_pool: FramePoolConfig = EIP_8141
    sealed_pool: SealedPoolConfig = OFF
    genesis: Head = field(default_factory=lambda: Head(timestamp=0, gas_limit=30_000_000, gas_used=15_000_000,
                                                       base_fee=1_000_000_000))
    accounts: dict[str, int] = field(default_factory=dict)  # address -> balance
    code: dict[str, str] = field(default_factory=dict)  # address -> code; an address only here has no balance
    sample_interval: float = 12.0
    # Per-node frame pool profiles, chosen once the topology is drawn: a function of the simulation that
    # names the nodes whose profile is not `frame_pool`. It should draw from a random stream of its own.
    frame_pools: Callable[["Simulation"], dict[str, FramePoolConfig]] | None = None


class Simulation:
    def __init__(self, scenario: Scenario):
        self.scenario = scenario
        self.rng = random.Random(scenario.seed)
        self.sched = Scheduler()
        self.recorder = Recorder()
        self.net = Network(self.sched, self.rng, self.recorder, scenario.network)
        addresses = list(scenario.accounts) + [a for a in scenario.code if a not in scenario.accounts]
        state = State({a: Account(balance=scenario.accounts.get(a, 0), code=scenario.code.get(a, "")) for a in addresses})
        for i in range(scenario.nodes):
            pool = TxPool(scenario.genesis, state, scenario.nonce_pool, scenario.frame_pool, now=0,
                          sealed_config=scenario.sealed_pool)
            self.net.add(Node(f"n{i:02d}", pool, self.net))
        self.net.random_topology()
        if scenario.frame_pools is not None:
            for name, config in scenario.frame_pools(self).items():
                self.net.nodes[name].use_pool(TxPool(scenario.genesis, state, scenario.nonce_pool, config, now=0,
                                                     sealed_config=scenario.sealed_pool))
        self.chain = Chain(self.sched, self.net, self.recorder, scenario.genesis, state, scenario.chain, self.rng,
                           random.Random(f"{scenario.seed}/committee"), random.Random(f"{scenario.seed}/proposers"))
        self.loads: list[Load] = []
        self.nonces: dict[str, int] = {}

    def wallet_nonce(self, sender: str) -> int:
        """The next nonce a wallet uses: one past its last, or the chain's if that is ahead."""
        nonce = max(self.nonces.get(sender, 0), self.chain.state.nonce(sender))
        self.nonces[sender] = nonce + 1
        return nonce

    def add_load(self, load: Load) -> None:
        self.loads.append(load)

    def _sample(self) -> None:
        sizes = []
        for node in self.net.nodes.values():
            pending, queued = node.pool.nonce.content()
            sizes.append((sum(map(len, pending.values())) + len(node.pool.frame.entries),
                          sum(map(len, queued.values()))))
        extra = {}
        if self.scenario.sealed_pool.sealed:
            held = [len(node.pool.sealed.entries) for node in self.net.nodes.values()]
            extra = {"sealed_mean": sum(held) / len(held), "sealed_max": max(held)}
        self.recorder.sample(self.sched.now, pending_mean=sum(p for p, _ in sizes) / len(sizes),
                             pending_max=max(p for p, _ in sizes),
                             queued_mean=sum(q for _, q in sizes) / len(sizes),
                             base_fee=self.chain.head.next_base_fee(), **extra)

    def run(self, duration: float) -> Recorder:
        self.chain.start()
        for load in self.loads:
            schedule(self, load)
        self.sched.every(self.scenario.sample_interval, self._sample)
        interval = self.scenario.frame_pool.aggregation_interval
        phases = random.Random(f"{self.scenario.seed}/aggregation")  # so the chain's dice stay the same
        for node in self.net.nodes.values():  # AG-7, each node on a phase of its own
            if node.aggregator is not None:
                self.sched.every(interval, node.aggregate, start=self.sched.now + phases.uniform(0, interval))
        self.sched.run(duration)
        return self.recorder
