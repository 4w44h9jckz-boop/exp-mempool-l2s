#!/usr/bin/env python3
"""Experiment 06: in-mempool aggregation (EIP-8288). Prints results.md on standard output.

EIP-8288 lets a frame transaction declare a leanSTARK proof or a leanSPHINCS
signature as a dependency, carried beside it in a wrapper, and has every
mempool node send its peers one aggregate a second, with one recursive STARK
over all it holds. It also caps a wrapper at one leanSTARK and 16 leanSPHINCS
dependencies. This measures what that does to the time a transaction with a
dependency takes to reach a builder and a block, and how many such
transactions the aggregates carry, under the text's reading (the cap binds
aggregates, and only aggregates travel), without the cap (`cap_aggregates`
false), and with users' wrappers relayed at once (`forward_wrappers`); against
ordinary gossip of a transaction without a dependency.
"""

from __future__ import annotations

import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "ref" / "python"), str(ROOT / "sim")]

from emem import EIP_8141, EIP_8288, Head  # noqa: E402
from emem_sim import (ChainConfig, NetworkConfig, Scenario, Simulation, WalletLoad, backed_tx,  # noqa: E402
                      percentile, table, uniform)
from emem_sim.metrics import HASH_BYTES, TRIPLE_BYTES  # noqa: E402

SEED = 1
NODES = 30
DEGREE = 8
SLOT = 12
GAS_LIMIT = 6_300_000
BASE_FEE = 1_000_000_000
MIN_TIP = 1_000_000  # BB-1, go-ethereum's miner default
TIPS = (1_000_000, 3_000_000_000)  # what wallets tip, uniformly (the simulator's default)
EXEC_GAS = 50_000  # each transaction's sender frame
WALLETS = 6000
RUN = 1800
DEMAND = RUN - 300  # wallets send until then, so that the last of them can land
INTERVAL = EIP_8288.aggregation_interval
STARK_KB = 128  # EIP-8288, Motivation: STARKs "all take over 128 kB"


def variant(profile, name: str, **changes):
    return profile.with_(name=name, **changes)


GOSSIP = variant(EIP_8141, "gossip, no dependency")
TEXT = variant(EIP_8288, "eip-8288")
UNCAPPED = variant(EIP_8288, "eip-8288, uncapped", cap_aggregates=False)
FORWARD = variant(EIP_8288, "eip-8288, forwarded", forward_wrappers=True)


def tx_gas(scheme: str | None) -> tuple[int, int]:
    """A wallet's transaction: its max_gas, and what it takes of a block with AG-8's charge."""
    tx = backed_tx("self", "u0", None, max_fee=10**10, tip=10**9, label="x", exec_gas=EXEC_GAS, scheme=scheme)
    return tx.max_gas, tx.max_gas + 30000 * tx.declared


class Carried:
    """Per slot, the transactions listed in any node's aggregate (AG-7)."""

    def __init__(self, sim):
        self.by_slot: dict[int, set[str]] = defaultdict(set)
        for node in sim.net.nodes.values():
            if node.aggregator is not None:
                node.aggregator.aggregate = self._wrap(sim, node.aggregator.aggregate)

    def _wrap(self, sim, inner):
        def aggregate():
            w = inner()
            if w is not None:
                self.by_slot[int(sim.sched.now // SLOT)].update(e if isinstance(e, str) else e.hash for e in w.txs)
            return w
        return aggregate

    def per_slot(self, lo: float, hi: float) -> float | None:
        slots = range(int(lo // SLOT), int(hi // SLOT))
        return sum(len(self.by_slot.get(s, ())) for s in slots) / len(slots) if slots else None


def run(profile, scheme: str | None, per_slot: float, *, nodes: int = NODES, prove: float = 0.0,
        resend: bool = True) -> dict:
    senders = [f"u{i}" for i in range(WALLETS)]
    sim = Simulation(Scenario(
        seed=SEED, nodes=nodes,
        network=NetworkConfig(degree=DEGREE, latency=(0.02, 0.10), arrive_timeout=0.5, prove_delay=prove),
        chain=ChainConfig(slot_time=SLOT, proposer="rotate", block_delay=(0.1, 1.0), min_tip=MIN_TIP),
        frame_pool=profile,
        genesis=Head(timestamp=0, gas_limit=GAS_LIMIT, gas_used=GAS_LIMIT // 2, base_fee=BASE_FEE),
        accounts={s: 10**18 for s in senders}))
    wallets = WalletLoad("w", rate=per_slot / SLOT, senders=senders, tip=uniform(*TIPS), expiring=0.0,
                         exec_gas=EXEC_GAS, scheme=scheme, resend=resend, stop=DEMAND)
    sim.add_load(wallets)
    carried = Carried(sim)
    rec = sim.run(RUN)
    proposer = {b["number"]: b["proposer"] for b in rec.blocks}
    records = [rec.txs[tx.hash] for tx in wallets.txs]
    landed = [r for r in records if r.included_at is not None]
    route = Counter(r.via.get(proposer[r.block], "gossip") for r in landed)
    half = (nodes + 1) // 2
    reach = {}
    for name, need in (("half", half), ("all", nodes)):
        times = [sorted(r.first_seen.values())[need - 1] - r.submitted_at for r in records if len(r.first_seen) >= need]
        reach[name] = (len(times), percentile(times, 50))
    delays = [r.included_at - r.submitted_at for r in landed]
    return {"sent": len(records), "landed": len(landed), "p50": percentile(delays, 50),
            "p90": percentile(delays, 90), "reach": reach, "route": route, "rec": rec, "nodes": nodes,
            "carried": carried.per_slot(0, DEMAND), "spread": sum(len(r.first_seen) for r in records) / len(records)}


def label(profile, prove: float = 0.0, nodes: int = NODES) -> str:
    out = profile.name
    if prove:
        out += f", proving {prove:g} s"
    if nodes != NODES:
        out += f", {nodes} nodes"
    return out


# --- 1 ---------------------------------------------------------------------------------------------------------

def section_1() -> str:
    rows = []
    cases = [(GOSSIP, None, 0.0, NODES), (TEXT, "stark", 0.0, NODES), (TEXT, "stark", INTERVAL, NODES),
             (UNCAPPED, "stark", 0.0, NODES), (UNCAPPED, "stark", INTERVAL, NODES), (FORWARD, "stark", 0.0, NODES),
             (GOSSIP, None, 0.0, 100), (UNCAPPED, "stark", 0.0, 100)]
    for profile, scheme, prove, nodes in cases:
        r = run(profile, scheme, 2, nodes=nodes, prove=prove)
        rows.append([label(profile, prove, nodes), r["sent"], r["reach"]["half"][0], r["reach"]["half"][1],
                     r["reach"]["all"][0], r["reach"]["all"][1], r["landed"], r["p50"], r["p90"],
                     r["route"].get("gossip", 0), r["route"].get("user", 0), r["route"].get("aggregate", 0),
                     r["route"].get("forwarded", 0), r["carried"] if scheme else "n/a"])
    plain, stark = tx_gas(None), tx_gas("stark")
    return "\n".join([
        "## 1. Delay at low demand",
        "",
        f"A network of {NODES} nodes, {DEGREE} peers each, a block every {SLOT} s from a rotating proposer, gas limit "
        f"{GAS_LIMIT}. Wallets, each its own default-code sender, send 2 transactions a slot to random nodes for "
        f"{DEMAND // 60} minutes; a wallet with one in flight waits, and after every block that leaves it out sends "
        f"it again to a random node. Each transaction is `[dependency, self_verify, sender]` with one leanSTARK "
        f"triple, sent as a mode 0 wrapper with its proof: max_gas {stark[0]}, {stark[1]} of a block with AG-8's "
        f"charge. The gossip row sends the same transactions without the dependency frame (max_gas {plain[0]}) "
        f"under `eip-8141`, as ordinary transactions. Every node aggregates once every {INTERVAL:g} s at a phase "
        f"of its own and sends after the proving delay, if any, plus the link's latency. Reached is the number "
        f"of transactions that became pending at half the nodes and at all of them, with the median time from "
        f"first sending; delays are from first sending to inclusion, in seconds; and the last four columns say "
        f"how the block's proposer had first admitted each included transaction: by ordinary gossip, from a "
        f"user's wrapper sent to it, from a peer's aggregate, or from a forwarded user's wrapper. Carried is "
        f"the mean, over the slots of the demand, of the distinct transactions listed in any node's aggregate "
        f"during the slot.",
        "",
        table(["network", "sent", "reached half", "p50", "reached all", "p50", "landed", "delay p50", "p90",
               "gossip", "user", "aggregate", "forwarded", "carried"], rows),
    ])


# --- 2 ---------------------------------------------------------------------------------------------------------

def section_2() -> tuple[str, list]:
    rows, kept = [], []
    cases = [(p, "stark", d) for d in (2, 8, 32) for p in (TEXT, UNCAPPED, FORWARD)]
    cases += [(TEXT, "sphincs", 32), (UNCAPPED, "sphincs", 32)]
    for profile, scheme, per_slot in cases:
        r = run(profile, scheme, per_slot)
        kept.append((profile, scheme, per_slot, r))
        rows.append([profile.name, scheme, per_slot, r["sent"], r["landed"], r["p50"], r["p90"], r["spread"],
                     r["route"].get("user", 0), r["route"].get("aggregate", 0), r["route"].get("forwarded", 0),
                     r["carried"]])
    return "\n".join([
        "## 2. Against demand",
        "",
        "The network and wallets of section 1 at 2, 8 and 32 transactions a slot, each with one leanSTARK "
        "dependency, and at 32 with one leanSPHINCS dependency instead, under the text's reading, without the "
        "cap, and with users' wrappers forwarded; no proving delay. Spread is the mean number of nodes a "
        "transaction became pending at; user, aggregate and forwarded are as in section 1; carried is the mean, "
        "over the slots of the demand, of the distinct transactions listed in any node's aggregate during the "
        f"slot. A block holds {GAS_LIMIT // tx_gas('stark')[1]} of the leanSTARK transactions and "
        f"{GAS_LIMIT // tx_gas('sphincs')[1]} of the leanSPHINCS ones.",
        "",
        table(["network", "dependency", "a slot", "sent", "landed", "delay p50", "p90", "spread", "user",
               "aggregate", "forwarded", "carried"], rows),
    ]), kept


# --- 3 ---------------------------------------------------------------------------------------------------------

def section_3() -> str:
    rows = []
    for profile in (TEXT, UNCAPPED, FORWARD):
        r = run(profile, "stark", 8, resend=False)
        rows.append([profile.name, r["sent"], r["landed"], r["sent"] - r["landed"], r["p50"], r["p90"], r["spread"]])
    return "\n".join([
        "## 3. Wallets that send once",
        "",
        "Section 2's leanSTARK transactions at 8 a slot, from wallets that send each one once, to one random node, "
        "and wait. Not landed is by the end of the run, five minutes after the last was sent.",
        "",
        table(["network", "sent", "landed", "not landed", "delay p50", "p90", "spread"], rows),
    ])


# --- 4 ---------------------------------------------------------------------------------------------------------

def section_4(kept: list) -> str:
    rows = []
    for profile, scheme, per_slot, r in kept:
        if per_slot not in (8, 32):
            continue
        w, per = r["rec"].wrappers, RUN * r["nodes"]
        msgs = sum(w[(k, "messages")] for k in ("aggregate", "forwarded"))
        starks = sum(w[(k, "starks")] for k in ("aggregate", "forwarded"))
        proofs = sum(w[(k, "proofs")] for k in ("aggregate", "forwarded"))
        txb = sum(w[(k, "tx_bytes")] for k in ("aggregate", "forwarded"))
        hashb = sum(w[(k, "hash_bytes")] for k in ("aggregate", "forwarded"))
        depb = sum(w[(k, "dep_bytes")] for k in ("aggregate", "forwarded"))
        rows.append([profile.name, scheme, per_slot, msgs / per, starks / per, proofs / per, txb / per / 1000,
                     hashb / per / 1000, depb / per / 1000, starks / per * STARK_KB])
    return "\n".join([
        "## 4. What nodes send each other",
        "",
        "From section 2's runs at 8 and 32 a slot, per node and per second over the whole run: wrappers sent to "
        "peers, the recursive STARKs among them (one per aggregate), direct proofs (one per forwarded user's "
        f"wrapper), and kB of transactions sent in full, of {HASH_BYTES}-byte hashes in their place, and of "
        f"{TRIPLE_BYTES}-byte triples. The model does not size proofs (AG, Not modelled); the last column prices "
        f"each recursive STARK at the {STARK_KB} kB the EIP gives as the least a STARK takes, so it is a floor. "
        "A direct leanSTARK proof is the same size or more, and a leanSPHINCS signature is \"~2-3 kB\" (EIP-8288, "
        "Motivation).",
        "",
        table(["network", "dependency", "a slot", "wrappers", "STARKs", "direct proofs", "kB transactions",
               "kB hashes", "kB triples", "kB of STARKs, at least"], rows),
    ])


def main() -> None:
    print("# 06. In-mempool aggregation: results")
    print()
    print(f"Generated by `experiments/06-in-mempool-aggregation/run.py`, seed {SEED}, {NODES} nodes unless a row "
          f"says otherwise, {DEGREE} peers each, {SLOT} s slots, gas limit {GAS_LIMIT}, {RUN // 60} minutes a run. "
          "Do not edit by hand.")
    print()
    print(section_1())
    print()
    text, kept = section_2()
    print(text)
    print()
    print(section_3())
    print()
    print(section_4(kept))


if __name__ == "__main__":
    main()
