#!/usr/bin/env python3
"""Experiment 16: batched admission. Prints results.md on standard output.

The one measured way to make a pairing proof cheap to verify is a batch
under one key, and a mempool decides one transaction at a time. This gives the nodes of `sim/emem_sim/network.py`
a window in which they hold proof-carrying transactions and verify them as one
batch, at the cost Commonware measured (`sim/emem_sim/batch.py`), and
measures the batches a node forms, what it saves, and the delay the window
adds to propagation and inclusion, against the window and the rate of proofs
under the key; then what a sender of invalid proofs, which spoil a batch and
make a node bisect it, costs a node that batches and one that does not.
Decision record 0025.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "ref" / "python"), str(ROOT / "sim")]

from emem import Head  # noqa: E402
from emem_sim import (InvalidProofLoad, NetworkConfig, ProofLoad, Scenario, Simulation, percentile,  # noqa: E402
                      run_all, table)
from emem_sim.batch import SINGLE_MS, batch_ms  # noqa: E402

SEEDS = (1, 2, 3)  # each draws its own topology, latencies and arrivals
NODES = 50
DEGREE = 8
SLOT = 12
GAS_LIMIT = 400_000_000  # room for every proof; blocks stay below the target
BASE_FEE = 1_000_000_000
RUN = 120.0
SEND = (12.0, 96.0)  # when proofs are sent
RATES = (1.0, 10.0, 100.0)  # proofs a second under the key, network-wide
WINDOWS = (0.0, 0.05, 0.1, 0.25, 0.5, 1.0)  # seconds
ATTACK_RATE = 100.0
ATTACK_WINDOWS = (0.0, 0.1)
INVALID = (0.0, 0.1, 1.0, 10.0, 50.0)  # invalid proofs a second, each handed to every node

# A one-nullifier private spend verified in the EVM, ethresear.ch topic 25889: "a BN254 pairing check at
# 181,000, and the protocol's own 20,000 per nullifier", 211,828 in all against a budget of 100,000.
PAIRING_GAS = 181_000
SPEND_GAS = 211_828
BUDGET = 100_000
BUSIEST = 8.96 / 3600  # spends a second: the four Tornado Cash ETH pools' busiest quarter, merged (experiment 01)


@dataclass(frozen=True)
class Run:
    seed: int
    rate: float
    window: float
    invalid: float = 0.0


def one(run: Run) -> dict:
    """One simulation, summarised."""
    senders = [f"u{i}" for i in range(int(run.rate * 200) + 50)]
    sim = Simulation(Scenario(
        seed=run.seed,
        nodes=NODES,
        network=NetworkConfig(degree=DEGREE, latency=(0.02, 0.10), arrive_timeout=0.5, batch_window=run.window),
        genesis=Head(timestamp=0, gas_limit=GAS_LIMIT, gas_used=GAS_LIMIT // 2, base_fee=BASE_FEE),
        accounts={s: 10**21 for s in senders},
    ))
    load = ProofLoad("proof", rate=run.rate, senders=senders, start=SEND[0], stop=SEND[1])
    sim.add_load(load)
    if run.invalid:
        sim.add_load(InvalidProofLoad("bad", rate=run.invalid, senders=["bad"], start=SEND[0], stop=SEND[1]))
    rec = sim.run(RUN)
    honest = [r for r in rec.txs.values() if sim.net.proofs.get(r.tx.hash)]
    reached = []
    for r in honest:
        seen = sorted(r.first_seen.values())
        if len(seen) >= 0.9 * NODES:
            reached.append(seen[int(0.9 * NODES) - 1] - r.submitted_at)
    nodes = list(sim.net.nodes.values())
    return {
        "sent": len(honest),
        "landed": sum(r.included_at is not None for r in honest),
        "delays": [r.included_at - r.submitted_at for r in honest if r.included_at is not None],
        "reached": reached,
        "batches": sum(len(n.batches) for n in nodes),
        "verified": sum(sum(n.batches) for n in nodes),
        "checks": sum(n.checks for n in nodes),
        "ms": sum(n.verify_ms for n in nodes),
        "busiest": max(n.verify_ms for n in nodes),
        "invalid": sum(1 for h, ok in sim.net.proofs.items() if not ok),
    }


def pooled(outs: list[dict]) -> dict:
    o = {k: sum(x[k] for x in outs) for k in ("sent", "landed", "batches", "verified", "checks", "ms", "invalid")}
    o["delays"] = [d for x in outs for d in x["delays"]]
    o["reached"] = [d for x in outs for d in x["reached"]]
    o["busiest"] = max(x["busiest"] for x in outs)
    honest = o["verified"] - o["invalid"] * NODES  # every invalid proof is verified once at every node
    o["per_proof"] = o["ms"] / honest * 1000  # microseconds of verification a valid proof, invalid ones' included
    o["share"] = o["ms"] / honest / SINGLE_MS
    o["per_second"] = o["ms"] / len(outs) / NODES / (SEND[1] - SEND[0])  # ms a node a second, while proofs arrive
    return o


def pct(xs, q):
    return percentile(xs, q) if xs else None


def setup() -> str:
    return (f"{NODES} nodes, {DEGREE} peers each, one-way link latency uniform in 20 to 100 ms, the arrive timeout "
            f"500 ms, {SLOT} s slots built by a proposer that rotates through the nodes, gas limit {GAS_LIMIT}, "
            f"profile `eip-8141`. From {SEND[0]:.0f} s to {SEND[1]:.0f} s users send self-paying frame transactions, "
            "each from a sender of its own, to random nodes, and each carries a proof under one key shared by all of "
            "them, which a node verifies before its pool sees the transaction: one at a time on arrival when the "
            "window is 0, and otherwise held from the first arrival of a batch until the window closes and verified "
            "as one batch, on one core whose time delays the admission. A proof costs "
            f"{SINGLE_MS * 1000:.1f} microseconds alone and a batch what Commonware measured for Pari proofs on one "
            "thread, interpolated between the sizes it measured (`sim/emem_sim/batch.py`). The run lasts "
            f"{RUN:.0f} s. Rows pool {len(SEEDS)} runs, seeds {', '.join(map(str, SEEDS))}, each with its own "
            "topology and arrivals.")


def section_1(out) -> str:
    rows = []
    for rate in RATES:
        for window in WINDOWS:
            o = pooled(out[(rate, window, 0.0)])
            rows.append([f"{rate:.0f}", window, o["sent"], o["landed"], f"{o['verified'] / o['batches']:.2f}",
                         f"{o['per_proof']:.1f}", f"{o['share']:.2f}", f"{o['per_second']:.2f}",
                         pct(o["reached"], 50), pct(o["reached"], 90), pct(o["delays"], 50), pct(o["delays"], 90)])
    return "\n".join([
        "## 1. The window against the rate of proofs",
        "",
        setup(),
        "",
        "Rate is proofs a second under the key, network-wide, as asked; a user whose last transaction has not "
        "landed does not send another, so slightly fewer are sent. Batch is the mean number of proofs a node "
        "verified together. Verification is in microseconds a proof, and as a share of verifying each alone; a "
        "node's load is the milliseconds of verification a node spends a second while proofs arrive. Reach is the "
        "time from sending until 45 of the 50 nodes hold the transaction, and delay until a block includes it, in "
        "seconds.",
        "",
        table(["rate", "window", "sent", "landed", "batch", "verification", "share", "node's load", "reach p50",
               "p90", "delay p50", "p90"], rows),
    ])


def fits(n: int) -> bool:
    return SPEND_GAS - PAIRING_GAS + PAIRING_GAS * batch_ms(n) / n / SINGLE_MS <= BUDGET


def section_2(out) -> str:
    rows = []
    for rate in RATES:
        for window in WINDOWS[1:]:
            o = pooled(out[(rate, window, 0.0)])
            pairing = PAIRING_GAS * o["share"]
            rows.append([f"{rate:.0f}", window, f"{o['verified'] / o['batches']:.2f}", f"{o['share']:.2f}",
                         round(pairing), round(SPEND_GAS - PAIRING_GAS + pairing)])
    least = next(n for n in range(1, 1000) if fits(n))
    windows = [["the busiest quarter of the four Tornado Cash ETH pools, merged", f"{BUSIEST * 3600:.2f} an hour",
                f"{least / BUSIEST / 60:.0f} minutes"]]
    windows += [[f"{rate:.0f} a second", f"{rate * 3600:.0f} an hour", f"{least / rate:.2f} s"] for rate in RATES]
    return "\n".join([
        "## 2. What a batch is worth against the validation budget",
        "",
        "Section 1's verification share applied to the gas of the pairing check in a one-nullifier private spend, "
        f"{PAIRING_GAS} of its {SPEND_GAS} (ethresear.ch topic 25889), as if the gas of a check scaled with its "
        "time; the rest of the spend's gas is unchanged. This is an interpretation, not a price any EIP sets "
        f"(decision record 0025). Against `MAX_VERIFY_GAS`, {BUDGET}.",
        "",
        table(["rate", "window", "batch", "share", "pairing check, gas", "spend, gas"], rows),
        "",
        f"The smallest batch that brings the spend within {BUDGET} under the same reading is {least} proofs, a "
        f"share of {batch_ms(least) / least / SINGLE_MS:.2f}. A node collects that many proofs under one key, on "
        "average, in the window below:",
        "",
        table(["proofs under the key", "rate", "window for a batch of " + str(least)], windows),
    ])


def section_3(out) -> str:
    rows = []
    for window in ATTACK_WINDOWS:
        for invalid in INVALID:
            o = pooled(out[(ATTACK_RATE, window, invalid)])
            rows.append([window, invalid, o["invalid"], f"{o['verified'] / o['batches']:.2f}",
                         f"{o['checks'] / o['batches']:.2f}", f"{o['per_proof']:.1f}", f"{o['share']:.2f}",
                         f"{o['per_second']:.2f}", f"{o['busiest'] / (SEND[1] - SEND[0]):.2f}",
                         pct(o["reached"], 50), pct(o["delays"], 50), o["landed"], o["sent"]])
    return "\n".join([
        "## 3. Proofs that fail",
        "",
        f"Section 1's network at {ATTACK_RATE:.0f} proofs a second, with a sender of invalid proofs that hands each "
        "one, from a fresh sender, to every node at once. A node refuses it after verifying its proof, so it is "
        "never relayed and pays nothing, and in a batch it fails the batch, which the node bisects down to the "
        "proofs that fail (`sim/emem_sim/batch.py`). Checks are batch verifications a batch, bisection included. "
        "Verification is per valid proof, the invalid proofs' cost included, and its share is against verifying "
        "every valid proof alone with no invalid ones; a node's load is the mean, and the busiest node's, in "
        "milliseconds a second while proofs arrive.",
        "",
        table(["window", "invalid a second", "invalid sent", "batch", "checks", "verification", "share",
               "node's load", "busiest", "reach p50", "delay p50", "landed", "sent"], rows),
    ])


def keys() -> list[tuple]:
    ks = [(rate, window, 0.0) for rate in RATES for window in WINDOWS]
    ks += [(ATTACK_RATE, window, invalid) for window in ATTACK_WINDOWS for invalid in INVALID]
    return list(dict.fromkeys(ks))


def main() -> None:
    ks = keys()
    runs = [Run(seed, rate=k[0], window=k[1], invalid=k[2]) for k in ks for seed in SEEDS]
    results = dict(zip(runs, run_all(one, runs)))
    out = {k: [results[r] for r in runs if (r.rate, r.window, r.invalid) == k] for k in ks}
    print("# 16. Batched admission: results")
    print()
    print(f"Generated by `experiments/16-batched-admission/run.py`, seeds {', '.join(map(str, SEEDS))}, {NODES} "
          f"nodes, {DEGREE} peers each, {SLOT} s slots, {RUN:.0f} s a run, frame pool profile `eip-8141`. Do not "
          "edit by hand.")
    for section in (section_1, section_2, section_3):
        print()
        print(section(out))


if __name__ == "__main__":
    main()
