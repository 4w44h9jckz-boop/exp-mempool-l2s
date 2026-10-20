#!/usr/bin/env python3
"""Experiment 11: one spend, many copies. Prints results.md on standard output.

An earlier design study built a blind ticket that its holder can put into
many operations at once, of which one lands, and reads the copies as ERC-7562's mass
invalidation attack in its cheapest form; it proposes duplicate suppression,
one pending operation per paymaster and ticket. In the frame pool the ticket
is a spend from a shared sender, and its nullifier is either an EIP-8250
nonce key, which gives every copy one identity, or a slot of the sender's
storage, which does not. This hands each spend out as copies to different
nodes and counts how many pools hold a copy that has lost and for how long,
and what the copies cost the network in prefix runs, re-runs and failed
attempts in blocks; under the nonce key also with FP-11 and FP-12 checked
before the prefix (`static_first`). Decision record 0020.
"""

from __future__ import annotations

import statistics
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "ref" / "python"), str(ROOT / "sim")]

from emem import HEGOTA_TESTNET, Head  # noqa: E402
from emem import errors as E  # noqa: E402
from emem_sim import (ChainConfig, CopiesLoad, NetworkConfig, Scenario, Simulation, fixed, percentile,  # noqa: E402
                      run_all, table)

SEEDS = (1, 2, 3)  # each draws its own topology, latencies and arrivals
NODES = 50
SIZES = (25, 50, 100, 200)  # section 2: one copy for every node
DEGREE = 8
SLOT = 12
GAS_LIMIT = 30_000_000
BASE_FEE = 1_000_000_000
RUN = 480.0
SEND = (12.0, 420.0)  # when users hand out spends
RATE = 1 / SLOT  # spends a second, one a slot
TIP = 1_000_000_000
COPIES = (1, 2, 4, 8, 0)  # 0: one for every node
VARIANTS = (("nonce", False), ("nonce", True), ("slot", False))
SENDER = "pool"

# Answers a pool gives before it runs the prefix: FP-2 to FP-7, and under `static_first` FP-11 and FP-12.
BEFORE_RUN = {E.ErrAlreadyKnown, E.ErrFrameMalformed, E.ErrGasLimitTooHigh, E.ErrInvalidSender, E.ErrTipAboveFeeCap,
              E.ErrTxGasPriceTooLow, E.ErrGasLimit, E.ErrFrameExpiryNotFirst, E.ErrFrameNoPayer,
              E.ErrFrameAtomicInPrefix, E.ErrFrameUnrecognizedPrefix, E.ErrFrameVerifyAfterPrefix, E.ErrFrameVerifyGas,
              E.ErrFrameVerifyStateGas, E.ErrNonceTooLow, E.ErrNonceTooHigh}
STATIC = {E.ErrFramePayerExposure, E.ErrFramePaymasterBusy, E.ErrReplaceUnderpriced, E.ErrFrameSenderBusy}


@dataclass(frozen=True)
class Run:
    seed: int
    record: str
    copies: int
    static_first: bool
    nodes: int = NODES


def one(run: Run) -> dict:
    sim = Simulation(Scenario(
        seed=run.seed,
        nodes=run.nodes,
        network=NetworkConfig(degree=DEGREE, latency=(0.02, 0.10), arrive_timeout=0.5),
        chain=ChainConfig(slot_time=SLOT, block_delay=(0.1, 1.0)),
        frame_pool=HEGOTA_TESTNET.with_(static_first=run.static_first),
        genesis=Head(timestamp=0, gas_limit=GAS_LIMIT, gas_used=GAS_LIMIT // 2, base_fee=BASE_FEE),
        accounts={SENDER: 10**24},
        code={SENDER: "privacy-pool"},
    ))
    load = CopiesLoad("t", rate=RATE, senders=[SENDER], copies=run.copies, record=run.record, tip=fixed(TIP),
                      start=SEND[0], stop=SEND[1])
    sim.add_load(load)
    spend_of: dict[str, int] = {}  # copy -> spend
    landed: dict[int, tuple[str, int]] = {}  # spend -> (the copy that landed, its block)
    imports: dict[tuple[str, int], float] = {}  # (node, block) -> when the node imported it
    rerun = {"lost": 0, "other": 0}
    failed = [0]
    seen: set[int] = set()
    indexed: list[int] = []

    def count(node, block) -> None:
        for spend in load.spends[len(indexed):]:
            spend_of.update((tx.hash, spend.index) for tx in spend.copies)
            indexed.append(spend.index)
        number = block.head.number
        imports[(node.name, number)] = node.now
        if number not in seen:  # the first import of a block: what it included, and its builder's failures
            seen.add(number)
            for tx in block.txs:
                i = spend_of.get(tx.hash)
                if i is not None:
                    landed.setdefault(i, (tx.hash, number))
            failed[0] += sum(1 for tx, _ in block.failed if tx.hash in spend_of)
        for tx in node.pool.frame.resimulated:
            i = spend_of.get(tx.hash)
            if i is not None:
                rerun["lost" if i in landed else "other"] += 1
    for node in sim.net.nodes.values():
        node.import_hooks.append(count)
    rec = sim.run(RUN)
    block_time = {b["number"]: b["at"] for b in rec.blocks}

    copies = runs = refused = 0
    pools, lost_pools, holds, delays = [], [], [], []
    for sp in load.spends:
        copies += len(sp.copies)
        reached: set[str] = set()
        for tx in sp.copies:
            r = rec.txs[tx.hash]
            reached.update(r.first_seen)
            for code, n in r.results.items():
                before = code in BEFORE_RUN or (run.static_first and code in STATIC)
                runs += 0 if before else n
                refused += n if code != E.OK else 0
        pools.append(len(reached))
        win = landed.get(sp.index)
        if win is None:
            continue
        h, number = win
        at = block_time[number]
        delays.append(at - sp.requested_at)
        losers: set[str] = set()
        for tx in sp.copies:
            if tx.hash == h:
                continue
            for node, first in rec.txs[tx.hash].first_seen.items():
                gone = imports.get((node, number))
                if gone is not None and first < gone:
                    losers.add(node)
                    holds.append(gone - max(at, first))
        lost_pools.append(len(losers))
    blocks = len(rec.blocks)
    return {"spends": len(load.spends), "landed": len(landed), "copies": copies, "runs": runs, "refused": refused,
            "pools": pools, "lost_pools": lost_pools, "holds": holds, "delays": delays,
            "rerun_lost": rerun["lost"], "rerun_other": rerun["other"], "failed": failed[0],
            "node_blocks": blocks * run.nodes}


def pooled(outs: list[dict]) -> dict:
    return {k: (sum((o[k] for o in outs), []) if isinstance(outs[0][k], list) else sum(o[k] for o in outs))
            for k in outs[0]}


def fmt(x, digits: int = 2) -> str:
    return "n/a" if x is None else f"{x:.{digits}f}"


def section_1(out) -> str:
    rows = []
    for record, static in VARIANTS:
        for c in COPIES:
            o = out[(record, c, static, NODES)]
            s = o["spends"]
            rows.append([record, "yes" if static else "no", "every node" if c == 0 else c, s, o["landed"],
                         fmt(o["copies"] / s), fmt(statistics.fmean(o["pools"])), fmt(statistics.fmean(o["lost_pools"])),
                         fmt(percentile(o["holds"], 50)), fmt(max(o["holds"], default=None)),
                         fmt(o["runs"] / s), fmt(o["refused"] / s), fmt(o["rerun_lost"] / s), fmt(o["failed"] / s),
                         fmt(o["rerun_other"] / o["node_blocks"]), fmt(percentile(o["delays"], 50))])
    lines = [
        "## 1. Copies of one spend",
        "",
        f"{NODES} nodes, {DEGREE} peers each, a block every {SLOT} s from a proposer that rotates through every "
        f"node, gas limit {GAS_LIMIT}, frame pool profile `hegota-testnet`. From {SEND[0]:.0f} s to {SEND[1]:.0f} s "
        f"users ask for spends from one shared sender at one a slot, each with a {TIP // 10**9} gwei tip and a fee "
        "cap of twice the next base fee plus the tip, and hand each out at once as copies, each to a different "
        f"random node, or one to every node. The run lasts {RUN:.0f} s. Rows pool {len(SEEDS)} runs, seeds "
        f"{', '.join(map(str, SEEDS))}, each with its own topology.",
        "",
        "Nullifier says where the spend's nullifier is: its nonce key, or a slot of the sender's storage. Static "
        "first is FP-1's `static_first`. Per spend: copies handed out; pools that held a copy; pools that held a "
        "copy after another copy's block was built, which has lost; prefix runs at admission, admitting or "
        "refusing, across all nodes and copies; refusals; re-runs of a lost copy at a new head (FP-15); and "
        "attempts by builders that failed (BB-3). Held after loss is, for each pool and lost copy, from the "
        "winning block's building until the pool dropped the copy, in seconds. Other re-runs are those of "
        "spends not yet included, per node and block. Delay is from asking to the winning block.",
        "",
        table(["nullifier", "static first", "copies", "spends", "landed", "copies per spend", "pools reached",
               "pools with a lost copy", "held after loss p50", "max", "runs per spend", "refused per spend",
               "re-runs of lost copies per spend", "failed in block per spend", "other re-runs per node a block",
               "delay p50"], rows),
    ]
    return "\n".join(lines)


def section_2(out) -> str:
    rows = []
    for record, static in VARIANTS:
        for n in SIZES:
            o = out[(record, 0, static, n)]
            s = o["spends"]
            rows.append([record, "yes" if static else "no", n, s, o["landed"], fmt(statistics.fmean(o["lost_pools"])),
                         fmt(o["runs"] / s), fmt(o["runs"] / s / n), fmt(o["rerun_lost"] / s),
                         fmt(o["rerun_lost"] / s / n), fmt(o["failed"] / s)])
    lines = [
        "## 2. One copy for every node, against the network's size",
        "",
        f"Section 1's chain, spends and pools, with every spend handed out as one copy to each of {', '.join(map(str, SIZES))} "
        f"nodes, {DEGREE} peers each. Per spend, as in section 1, and per spend and node.",
        "",
        table(["nullifier", "static first", "nodes", "spends", "landed", "pools with a lost copy", "runs per spend",
               "runs per spend per node", "re-runs of lost copies per spend", "per node", "failed in block per spend"],
              rows),
    ]
    return "\n".join(lines)


def main() -> None:
    keys = [(record, c, static, NODES) for record, static in VARIANTS for c in COPIES]
    keys += [(record, 0, static, n) for record, static in VARIANTS for n in SIZES if n != NODES]
    runs = [Run(seed, *key) for key in keys for seed in SEEDS]
    results = dict(zip(runs, run_all(one, runs)))
    out = {key: pooled([results[Run(seed, *key)] for seed in SEEDS]) for key in keys}
    print("# 11. One spend, many copies: results")
    print()
    print(f"Generated by `experiments/11-spend-copies/run.py`, seeds {', '.join(map(str, SEEDS))}, {NODES} nodes "
          f"and in section 2 {', '.join(map(str, SIZES))}, {DEGREE} peers each, {SLOT} s slots, {RUN:.0f} s a run, "
          "frame pool profile `hegota-testnet`. Do not edit by hand.")
    print()
    print(section_1(out))
    print()
    print(section_2(out))


if __name__ == "__main__":
    main()
