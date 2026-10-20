#!/usr/bin/env python3
"""Experiment 24: proving time in the aggregation interval (EIP-8288). Prints results.md on standard output.

EIP-8288 has every mempool node prove one recursive STARK over what it holds
every `AGGREGATION_INTERVAL` of 1000 ms, and gives a node that "will not have
enough proving time" an order to fill its aggregate in, the last step by
priority fee. Experiment 06 spent no time proving. This one counts it, by
AG-9 (`docs/spec/05-aggregation.md`, version 2), at costs fitted from leanVM's
own benchmark run on this repository's machine
(`bench/results/2026-10-13-leanvm.md`), and measures:

1. the delay and the reach of transactions with a dependency against demand,
   for nodes with no proving time, nodes that fill a budget of one interval
   in the EIP's order, nodes that prove everything and skip the ticks it
   takes, and nodes as fast as the implementers' laptop;
2. what happens when only some nodes can prove, the rest aggregating nothing
   and building no block;
3. a flood of transactions with a dependency, a high tip and a sponsor that
   is drained every block, so that none is ever included and none pays, under
   the budget and without one.
"""

from __future__ import annotations

import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "ref" / "python"), str(ROOT / "sim"), str(ROOT / "bench" / "leanvm")]

from emem import EIP_8288, Head  # noqa: E402
from emem_sim import (ChainConfig, FloodLoad, NetworkConfig, Scenario, Simulation, WalletLoad,  # noqa: E402
                      backed_tx, percentile, run_all, table, uniform)

import fit  # noqa: E402  bench/leanvm/fit.py, decision record 0033

SEED = 1
NODES = 30
DEGREE = 8
SLOT = 12
GAS_LIMIT = 30_000_000
BASE_FEE = 1_000_000_000
MIN_TIP = 1_000_000
TIPS = (1_000_000, 3_000_000_000)
EXEC_GAS = 50_000
WALLETS = 8000
RUN = 1200
DEMAND = RUN - 300
INTERVAL_MS = EIP_8288.aggregation_interval * 1000
JUNK_TIP = 10_000_000_000  # above every honest tip

COSTS = fit.costs()  # ms, this machine
FAST = fit.laptop_costs()  # ms, scaled to the README's machine by its time over ours, per kind of work
RATIOS = fit.ratios()
PROOF_KIB = fit.proof_kib()  # what one aggregate's proof weighs

UNCAPPED = EIP_8288.with_(cap_aggregates=False)
PROFILES = {
    "no proving time": UNCAPPED.with_(name="no proving time"),
    "this machine, budget": UNCAPPED.with_(name="this machine, budget", proving_budget=INTERVAL_MS, **COSTS),
    "this machine, no budget": UNCAPPED.with_(name="this machine, no budget", **COSTS),
    "laptop, budget": UNCAPPED.with_(name="laptop, budget", proving_budget=INTERVAL_MS, **FAST),
    "laptop, no budget": UNCAPPED.with_(name="laptop, no budget", **FAST),
    "capped, laptop, budget": EIP_8288.with_(name="capped, laptop, budget", proving_budget=INTERVAL_MS, **FAST),
}


def tx_gas(scheme: str) -> int:
    """What a wallet's transaction takes of a block, with AG-8's charge."""
    tx = backed_tx("self", "u0", None, max_fee=10**10, tip=10**9, label="x", exec_gas=EXEC_GAS, scheme=scheme)
    return tx.max_gas + 30000 * tx.declared


class Watch:
    """Every aggregate: its proving time, inputs and direct triples, what it listed, and the junk among it."""

    def __init__(self, sim, junk: str | None):
        self.junk = junk
        self.times: list[float] = []
        self.made = 0  # aggregates made during the demand
        self.inputs: list[int] = []
        self.direct: list[int] = []
        self.junk_share: list[float] = []
        self.by_slot: dict[int, set[str]] = defaultdict(set)
        for node in sim.net.nodes.values():
            if node.aggregator is not None:
                node.aggregator.aggregate = self._wrap(sim, node.aggregator)

    def _wrap(self, sim, agg):
        inner = agg.aggregate

        def aggregate():
            w = inner()
            if w is not None:
                self.made += sim.sched.now < DEMAND
                self.times.append(agg.proving_time)
                self.inputs.append(agg.inputs)
                self.direct.append(agg.verified)
                labels = [(e if isinstance(e, str) else e.hash) for e in w.txs]
                self.by_slot[int(sim.sched.now // SLOT)].update(labels)
                if self.junk is not None:
                    held = agg.pool.frame.entries
                    junk = sum(1 for h in labels if h in held and held[h].tx.label.startswith(self.junk))
                    self.junk_share.append(junk / len(labels))
            return w
        return aggregate

    def carried(self, lo: float, hi: float) -> float:
        slots = range(int(lo // SLOT), int(hi // SLOT))
        return sum(len(self.by_slot.get(s, ())) for s in slots) / len(slots)


def mean(xs) -> float | None:
    xs = list(xs)
    return sum(xs) / len(xs) if xs else None


def simulate(key: tuple) -> dict:
    """One run: (profile name, scheme, per slot, share of nodes that prove, junk a slot)."""
    name, scheme, per_slot, provers, junk = key
    profile = PROFILES[name]
    senders = [f"u{i}" for i in range(WALLETS)]
    accounts = {s: 10**18 for s in senders}
    blocks = RUN // SLOT + 2
    if junk:
        accounts.update({f"pm-{n}": 10**20 for n in range(blocks)})
    names = [f"n{i:02d}" for i in range(NODES)]
    proving = tuple(names[:round(provers * NODES)])

    def pools(sim) -> dict:
        idle = profile.with_(proving_budget=0)
        return {n: idle for n in sim.net.nodes if n not in proving}

    sim = Simulation(Scenario(
        seed=SEED, nodes=NODES,
        network=NetworkConfig(degree=DEGREE, latency=(0.02, 0.10), arrive_timeout=0.5),
        chain=ChainConfig(slot_time=SLOT, proposer=proving if provers < 1 else "rotate", block_delay=(0.1, 1.0),
                          min_tip=MIN_TIP),
        frame_pool=profile, frame_pools=pools if provers < 1 else None,
        genesis=Head(timestamp=0, gas_limit=GAS_LIMIT, gas_used=GAS_LIMIT // 2, base_fee=BASE_FEE),
        accounts=accounts))
    wallets = WalletLoad("w", rate=per_slot / SLOT, senders=senders, tip=uniform(*TIPS), expiring=0.0,
                         exec_gas=EXEC_GAS, scheme=scheme, stop=DEMAND)
    sim.add_load(wallets)
    adversary = None
    if junk:
        adversary = FloodLoad("junk", kind="drained", k=junk, payer="pm", surplus=0, tip=JUNK_TIP,
                              start=60, stop=DEMAND, scheme=scheme)
        sim.add_load(adversary)
    watch = Watch(sim, "junk" if junk else None)
    junk_in: set[str] = set()
    sim.net.nodes["n00"].import_hooks.append(lambda node, block: junk_in.update(
        tx.hash for tx in block.txs if tx.type == 6 and tx.label.startswith("junk")))
    busy: dict[str, int] = {}
    sim.sched.at(DEMAND, lambda: busy.update({n.name: n.busy for n in sim.net.nodes.values()}))
    rec = sim.run(RUN)
    records = [rec.txs[tx.hash] for tx in wallets.txs]
    landed = [r for r in records if r.included_at is not None]
    delays = [r.included_at - r.submitted_at for r in landed]
    nodes = [n for n in sim.net.nodes.values() if n.name in proving or provers >= 1]
    ticks = DEMAND / EIP_8288.aggregation_interval
    return {
        "sent": len(records), "landed": len(landed), "p50": percentile(delays, 50), "p90": percentile(delays, 90),
        "spread": mean(len(r.first_seen) for r in records), "carried": watch.carried(0, DEMAND),
        "time": mean(watch.times), "inputs": mean(watch.inputs), "direct": mean(watch.direct),
        "rate": watch.made / (len(nodes) * DEMAND),
        "busy": sum(busy[n.name] for n in nodes) / (len(nodes) * ticks),
        "junk share": mean(watch.junk_share) if junk else None,
        "junk sent": adversary.sent if adversary else 0,
        "junk included": len(junk_in),
        "via": Counter(v for r in landed for v in r.via.values()),
    }


MAIN = ("no proving time", "this machine, budget", "this machine, no budget", "laptop, budget", "laptop, no budget")
SECTION_1 = [(p, "stark", d, 1.0, 0) for d in (2, 8, 32) for p in MAIN]
SECTION_1 += [("capped, laptop, budget", "stark", 8, 1.0, 0)]
SECTION_1 += [(p, "sphincs", d, 1.0, 0) for d in (32, 128) for p in MAIN[:4]]
SECTION_2 = [("laptop, budget", "stark", 8, share, 0) for share in (1.0, 0.5, 0.2)]
SECTION_3 = [(p, "stark", 8, 1.0, k) for k in (0, 8, 32) for p in ("no proving time", "laptop, budget",
                                                                     "this machine, no budget")]


def costs_line() -> str:
    c, f, r = COSTS, FAST, RATIOS
    return (f"`prove_base` {c['prove_base']} ms, `prove_sig` {c['prove_sig']} ms a leanSPHINCS triple, "
            f"`prove_recursive` and `prove_stark` {c['prove_recursive']} ms a recursive input or leanSTARK "
            f"triple on this machine; on the laptop {f['prove_base']}, {f['prove_sig']} and "
            f"{f['prove_recursive']} ms, this machine's scaled by the README's time over ours, "
            f"{r['aggregation']} for its aggregation and {r['recursion']} for its recursion")


def section_1(out: dict) -> str:
    rows = []
    for key in SECTION_1:
        name, scheme, per_slot, _, _ = key
        r = out[key]
        rows.append([name, scheme, per_slot, r["sent"], r["landed"], r["p50"], r["p90"], r["spread"], r["carried"],
                     r["time"], r["inputs"], r["direct"], r["busy"], r["rate"], r["rate"] * DEGREE * PROOF_KIB])
    return "\n".join([
        "## 1. Against demand",
        "",
        f"A network of {NODES} nodes, {DEGREE} peers each, a block every {SLOT} s from a rotating proposer, gas "
        f"limit {GAS_LIMIT}. Wallets, each its own default-code sender, send transactions with one dependency to "
        f"random nodes for {DEMAND // 60} minutes of a {RUN // 60}-minute run, each as a mode 0 wrapper with its "
        f"proof; a wallet with one in flight waits, and after every block that leaves it out sends it again to a "
        f"random node. A leanSTARK transaction takes {tx_gas('stark')} gas of a block with AG-8's charge, a "
        f"leanSPHINCS one {tx_gas('sphincs')}. Every node aggregates once a second at a phase of its own, "
        f"`cap_aggregates` false except in the capped row, and sends its aggregate after its proving time (AG-9) "
        f"plus the link's latency. Costs: {costs_line()}. With a budget, a node lists in AG-7's order only what "
        f"it can prove in {INTERVAL_MS:g} ms; without one it lists everything and skips the ticks that come "
        f"while it is still proving. Spread is the mean number of nodes a transaction became pending at; carried "
        f"is the mean, over the slots of the demand, of the distinct transactions listed in any aggregate during "
        f"the slot; time, inputs and direct are the mean proving time of an aggregate in ms, the recursive "
        f"STARKs it took and the triples it verified directly; busy is the share of ticks skipped during the "
        f"demand; a s is the aggregates a node made a second during the demand, and KiB/s what it sent its "
        f"{DEGREE} peers at "
        f"{PROOF_KIB} KiB a proof, the benchmark's recursions, transactions not counted.",
        "",
        table(["nodes", "dependency", "a slot", "sent", "landed", "delay p50", "p90", "spread", "carried",
               "time ms", "inputs", "direct", "busy", "a s", "KiB/s"], rows),
    ])


def section_2(out: dict) -> str:
    rows = []
    for key in SECTION_2:
        _, _, _, share, _ = key
        r = out[key]
        rows.append([f"{share:.0%}", round(share * NODES), r["sent"], r["landed"], r["p50"], r["p90"],
                     r["spread"], r["carried"], r["time"]])
    return "\n".join([
        "## 2. When only some nodes can prove",
        "",
        "Section 1's leanSTARK transactions at 8 a slot under `laptop, budget`, with a share of the nodes "
        "able to prove. The others have a `proving_budget` of 0, so they admit users' wrappers and aggregates "
        "and send nothing (AG-9), and build no block: the proposer rotates through the provers alone, since a "
        "block needs its recursive STARK. Wallets still send to any node.",
        "",
        table(["provers", "nodes", "sent", "landed", "delay p50", "p90", "spread", "carried", "time ms"], rows),
    ])


def section_3(out: dict) -> str:
    rows = []
    for key in SECTION_3:
        name, _, _, _, k = key
        r = out[key]
        rows.append([name, k, r["sent"], r["landed"], r["p50"], r["p90"], r["spread"], r["time"],
                     r["junk share"] if k else "n/a", r["junk sent"], r["junk included"]])
    return "\n".join([
        "## 3. A flood that never pays",
        "",
        f"Section 1's leanSTARK transactions at 8 a slot, and from second 60 an adversary that, after every block "
        f"a node imports, hands that node directly k frame transactions with one leanSTARK dependency each, as "
        f"mode 0 wrappers, at a tip of {JUNK_TIP} wei, above every honest tip, each from a sender of its own "
        f"and all paid by one default-code sponsor of that block's own; with them it hands the node the "
        f"sponsor's transfer of its whole balance at twice that tip, which the next block includes first, so "
        f"that every one of the k fails there and leaves every pool at the next head (experiment 05's `drained` "
        f"flood). Junk share is the mean share of an aggregate's transactions that are the adversary's; sent "
        f"counts its transactions handed to a node; included counts those in a block.",
        "",
        table(["nodes", "k", "sent", "landed", "delay p50", "p90", "spread", "time ms", "junk share", "junk sent",
               "junk included"], rows),
    ])


def main() -> None:
    keys = list(dict.fromkeys(SECTION_1 + SECTION_2 + SECTION_3))
    out = dict(zip(keys, run_all(simulate, keys)))
    print("# Experiment 24: proving time in the aggregation interval")
    print()
    print(f"Generated by `experiments/24-proving-budget/run.py`, seed {SEED}. Costs from "
          "`bench/results/2026-10-13-leanvm.md` (decision records 0033 and 0034).")
    print()
    for section in (section_1(out), section_2(out), section_3(out)):
        print(section)
        print()


if __name__ == "__main__":
    main()
