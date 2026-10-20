#!/usr/bin/env python3
"""Experiment 10: wasted validation work against network size. Prints results.md on standard output.

ethresear.ch topic 25995 proves that a public-mempool rule that charges nothing
per attempt wastes work in proportion to the number of nodes, because every
forwarding node checks each sponsored transaction with a fresh empty payer.
EIP-8141's pool runs a frame
transaction's validation prefix before it can tell whether the payer can pay
(FP-8 before FP-11), and refuses the transaction if the payer cannot. This
counts the prefixes the whole network runs per adversary transaction, against
the number of nodes and under both frame pool profiles: for sponsors that hold
nothing, and for one sponsor a block that holds enough and moves its balance
on before the transactions it backs can land. Decision record 0019.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "ref" / "python"), str(ROOT / "sim")]

from emem import EIP_8141, HEGOTA_TESTNET, Head  # noqa: E402
from emem import errors as E  # noqa: E402
from emem_sim import (ChainConfig, NetworkConfig, Scenario, Simulation, SybilLoad, WalletLoad,  # noqa: E402
                      run_all, table)

SEEDS = (1, 2, 3)  # each draws its own topology, latencies and arrivals
SIZES = (25, 50, 100, 200)
DEGREE = 8
SLOT = 12
GAS_LIMIT = 30_000_000
BASE_FEE = 1_000_000_000
RUN = 360.0
ATTACK = (36.0, 324.0)  # when the adversary sends
HONEST_RATE = 0.5  # self-paying frame transactions a second, the yardstick
EMPTY_RATE = 1.0  # adversary transactions a second, each with a sponsor of its own that holds nothing
K = 32  # transactions one drained sponsor backs a round
SMALL_K = 4
TIP = 1_000_000_000
PROFILES = {"eip-8141": EIP_8141, "hegota-testnet": HEGOTA_TESTNET}
WEI_PER_GWEI = 10**9
WEI_PER_ETH = 10**18

# Answers a pool gives before it runs the prefix (FP-2 to FP-7); every other answer cost it a run.
BEFORE_RUN = {E.ErrAlreadyKnown, E.ErrFrameMalformed, E.ErrGasLimitTooHigh, E.ErrInvalidSender, E.ErrTipAboveFeeCap,
              E.ErrTxGasPriceTooLow, E.ErrGasLimit, E.ErrFrameExpiryNotFirst, E.ErrFrameNoPayer,
              E.ErrFrameAtomicInPrefix, E.ErrFrameUnrecognizedPrefix, E.ErrFrameVerifyAfterPrefix, E.ErrFrameVerifyGas,
              E.ErrFrameVerifyStateGas, E.ErrNonceTooLow, E.ErrNonceTooHigh}


@dataclass(frozen=True)
class Run:
    seed: int
    nodes: int
    profile: str
    kind: str  # "empty" or "drained"
    copies: int = 1  # empty: how many nodes the adversary hands each transaction; 0 for every node
    k: int = K  # drained: transactions a round


def one(run: Run) -> dict:
    honest = [f"u{i}" for i in range(int(HONEST_RATE * RUN * 2))]
    adversary = SybilLoad("a", kind=run.kind, rate=EMPTY_RATE, k=run.k, copies=run.copies or run.nodes, tip=TIP,
                          start=ATTACK[0], stop=ATTACK[1])
    accounts = {u: 10**20 for u in honest}
    rounds = int((ATTACK[1] - ATTACK[0]) // SLOT) + 1
    capital = adversary.funding(4 * BASE_FEE, rounds) if run.kind == "drained" else 0
    if capital:
        accounts[adversary.payer(0)] = capital
    sim = Simulation(Scenario(
        seed=run.seed,
        nodes=run.nodes,
        network=NetworkConfig(degree=DEGREE, latency=(0.02, 0.10), arrive_timeout=0.5),
        chain=ChainConfig(slot_time=SLOT, block_delay=(0.1, 1.0)),
        frame_pool=PROFILES[run.profile],
        genesis=Head(timestamp=0, gas_limit=GAS_LIMIT, gas_used=GAS_LIMIT // 2, base_fee=BASE_FEE),
        accounts=accounts,
    ))
    sim.add_load(WalletLoad("w", rate=HONEST_RATE, senders=honest, expiring=0.0, fresh=True, stop=RUN))
    sim.add_load(adversary)
    rerun = {"a": 0, "w": 0}
    failed = {"a": 0}
    seen: set[int] = set()

    def count(node, block) -> None:
        for tx in node.pool.frame.resimulated:
            rerun["a" if tx.sender.startswith("a-") else "w"] += 1
        if block.head.number not in seen:  # the builder's own attempts, once a block
            seen.add(block.head.number)
            failed["a"] += sum(1 for tx, _ in block.failed if tx.sender.startswith("a-"))
    for node in sim.net.nodes.values():
        node.import_hooks.append(count)
    rec = sim.run(RUN)

    def runs(prefix: str) -> tuple[int, int, int]:
        txs = [r for r in rec.txs.values() if getattr(r.tx, "frames", None) and r.tx.sender.startswith(prefix)]
        admitted = sum(n for r in txs for code, n in r.results.items() if code not in BEFORE_RUN)
        held = sum(len(r.first_seen) for r in txs)
        return len(txs), admitted, held
    base_fees = {b["number"]: b["base_fee"] for b in rec.blocks}
    paid = 0
    for t in adversary.transfers:
        r = rec.txs[t.hash]
        if r.block is not None:
            fee = base_fees[r.block]
            paid += t.gas * (fee + t.effective_tip(fee))
    a_txs, a_runs, a_held = runs("a-")
    w_txs, w_runs, _ = runs("u")
    landed = sum(1 for tx in adversary.txs if rec.txs[tx.hash].included_at is not None)
    return {"txs": a_txs, "sent": adversary.sent, "runs": a_runs, "rerun": rerun["a"], "held": a_held,
            "failed": failed["a"], "landed": landed, "paid": paid, "capital": capital,
            "rounds": len(adversary.transfers), "honest": w_txs, "honest_runs": w_runs + rerun["w"]}


def pooled(outs: list[dict]) -> dict:
    return {k: sum(o[k] for o in outs) for k in outs[0]}


def cells(o: dict, nodes: int) -> list:
    work = o["runs"] + o["rerun"]
    return [o["txs"], o["sent"], o["runs"] / o["txs"], o["rerun"] / o["txs"], work / o["sent"],
            work / o["txs"] / nodes, o["held"] / o["txs"], o["landed"], o["honest_runs"] / o["honest"] / nodes]


HEADERS = ["transactions", "handed", "runs per transaction", "re-runs per transaction", "work per hand-over",
           "work per transaction per node", "pools reached", "landed", "honest work per node"]


def section_1(out) -> str:
    rows = []
    for profile in PROFILES:
        for copies in (1, 0):
            for n in SIZES:
                o = out[(n, profile, "empty", copies, K)]
                rows.append([profile, "every node" if copies == 0 else copies, n] + cells(o, n))
    lines = [
        "## 1. Sponsors that hold nothing",
        "",
        f"Networks of the size in the table, {DEGREE} peers each, a block every {SLOT} s from a proposer that "
        f"rotates through every node, gas limit {GAS_LIMIT}. Honest wallets send self-paying frame transactions at "
        f"{HONEST_RATE * SLOT:.0f} a slot for the whole {RUN:.0f} s run, as the yardstick. From {ATTACK[0]:.0f} s to "
        f"{ATTACK[1]:.0f} s the adversary sends {EMPTY_RATE * SLOT:.0f} sponsored transactions a slot, each from a "
        "default-code sender of its own and backed by a default-code sponsor of its own that holds nothing, at a fee "
        f"cap of twice the next base fee plus a {TIP / WEI_PER_GWEI:.0f} gwei tip, and hands each to one random node "
        f"or to every node. Rows pool {len(SEEDS)} runs, seeds {', '.join(map(str, SEEDS))}, each with its own "
        "topology.",
        "",
        "Handed counts what the adversary handed a node, a transaction handed to every node once for each. Runs are "
        "the prefixes nodes ran to admit or refuse a transaction (FP-8, before FP-11), re-runs those they ran again "
        "at a new head (FP-15), and work the two together: per hand-over, per transaction and node, and for an "
        "honest transaction per node. Pools reached is how many nodes held a transaction pending; landed how many "
        "a block included.",
        "",
        table(["profile", "handed to", "nodes"] + HEADERS, rows),
    ]
    return "\n".join(lines)


def section_2(out) -> str:
    rows, money = [], []
    for profile in PROFILES:
        for k in (SMALL_K, K):
            for n in SIZES:
                o = out[(n, profile, "drained", 1, k)]
                rows.append([profile, k, n] + cells(o, n) + [o["failed"] / o["txs"]])
                work = o["runs"] + o["rerun"]
                money.append([profile, k, n, o["rounds"] // len(SEEDS),
                              f"{o['capital'] / len(SEEDS) / WEI_PER_ETH:.3g}",
                              f"{o['paid'] / o['rounds'] / WEI_PER_GWEI:.4g}",
                              f"{work / o['rounds'] / n:.2f}", f"{work * WEI_PER_GWEI / o['paid']:.4g}"])
    lines = [
        "## 2. A sponsor drained every block",
        "",
        "Section 1's networks and honest wallets. From the first block after "
        f"{ATTACK[0]:.0f} s until {ATTACK[1]:.0f} s, after every block, the adversary hands each of k sponsored "
        "transactions to a random node, all backed by one default-code sponsor that holds enough to pay for them "
        "at the fee cap, and hands every node that sponsor's transfer of its whole balance to the next round's "
        "sponsor, at twice the tip, so that the next block includes it first and every transaction it backed "
        "fails. The same money backs every round. Failed in block is how many times a builder tried a "
        "transaction and failed it, per transaction.",
        "",
        table(["profile", "k", "nodes"] + HEADERS + ["failed in block"], rows),
        "",
        "What it cost the adversary, per run: the rounds it sent; the balance it moves from sponsor to sponsor, "
        "which it keeps, enough for k transactions at 4 gwei a gas and every round's transfer; what each round's "
        "transfer paid in base fee and tip; and the prefixes the network ran, admitting and re-running, per node "
        "and round and per gwei it paid.",
        "",
        table(["profile", "k", "nodes", "rounds", "capital, ETH", "paid a round, gwei", "work per node a round",
                "work per gwei paid"], money),
    ]
    return "\n".join(lines)


def main() -> None:
    keys = [(n, p, "empty", c, K) for p in PROFILES for c in (1, 0) for n in SIZES]
    keys += [(n, p, "drained", 1, k) for p in PROFILES for k in (SMALL_K, K) for n in SIZES]
    runs = [Run(seed, n, p, kind, c, k) for (n, p, kind, c, k) in keys for seed in SEEDS]
    results = dict(zip(runs, run_all(one, runs)))
    out = {key: pooled([results[Run(seed, *key)] for seed in SEEDS]) for key in keys}
    print("# 10. Wasted validation work against network size: results")
    print()
    print(f"Generated by `experiments/10-wasted-work/run.py`, seeds {', '.join(map(str, SEEDS))}, "
          f"{', '.join(map(str, SIZES))} nodes, {DEGREE} peers each, {SLOT} s slots, {RUN:.0f} s a run, frame pool "
          "profiles `eip-8141` and `hegota-testnet`. Do not edit by hand.")
    print()
    print(section_1(out))
    print()
    print(section_2(out))


if __name__ == "__main__":
    main()
