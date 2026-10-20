#!/usr/bin/env python3
"""Experiment 20: a committee that clears every block. Prints results.md on standard output.

Per-block order matching, a private market maker or a batch auction that clears
every block must finish inside one slot, because the next batch arrives with the
next block. An earlier MPC study budgets it at 150 committee rounds for a 12 s
slot at an 80 ms round trip and 50 for a 4 s slot, and its protocols take 2,
17, 49 and 4,096 rounds, or 63 with a proof the chain checks. The budget
prices the computation and leaves out the network on either side of it. This puts the committee's three members in the gossip network and
measures the batches settled in the block they were meant for, the orders that
make the batch they were sent for, and the network's share of the slot, with
the orders taken from the chain or from the pool at a cutoff, against the round
count and slots of 12, 8 and 4 s. No clause changes; decision record 0029.
"""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "ref" / "python"), str(ROOT / "sim")]

from emem import EIP_8141, Head  # noqa: E402
from emem_sim import (ChainConfig, Clearing, NetworkConfig, Scenario, Simulation, TransferLoad,  # noqa: E402
                      fixed, percentile, run_all, table)

SEED = 1
NODES = 20
DEGREE = 8
MEMBERS = ("n17", "n18", "n19")  # the committee's nodes, which never propose
GAS_LIMIT = 60_000_000
BASE_FEE = 1_000_000_000
RUN = 1200.0
WINDOW = (120.0, 1080.0)  # orders sent and batches due in it are measured
ORDER_RATE = 0.5  # a second
ORDER_GAS = 100_000
ORDER_TIP = 3_000_000_000
ORDER_CAP = 100  # times the next base fee
SETTLE_GAS = 1_125_950  # Merces's settlement, a proof the chain checks
BACKGROUND_GAS = 1_000_000
SLOTS = (12, 8, 4)
ROUNDS = (2, 17, 49, 63, 150, 4096)
RTT = 0.080  # the MPC study's budget: cross-continent
RTTS = {"same region": 0.005, "cross-continent": 0.080, "intercontinental": 0.250}
MARGIN = 1.0
MARGINS = (0.25, 0.5, 2.0)
MARGIN_ROUNDS = 17


@dataclass(frozen=True)
class Run:
    channel: str
    slot: int
    rounds: int
    margin: float = MARGIN


def simulate(r: Run) -> dict:
    names = [f"n{i:02d}" for i in range(NODES)]
    users = [f"u{i}" for i in range(5000)]
    background = [f"b{i}" for i in range(3000)]
    proposers = tuple(n for n in names if n not in MEMBERS)
    if r.channel == "pool":  # orders reach the chain only through the settlement
        chain = ChainConfig(slot_time=r.slot, proposer=proposers, censored=lambda tx: tx.label.startswith("order"),
                            filtering=frozenset(names))
    else:
        chain = ChainConfig(slot_time=r.slot, proposer=proposers)
    sim = Simulation(Scenario(
        seed=SEED, nodes=NODES,
        network=NetworkConfig(degree=DEGREE, latency=(0.02, 0.10), arrive_timeout=0.5),
        chain=chain, frame_pool=EIP_8141,
        genesis=Head(timestamp=0, gas_limit=GAS_LIMIT, gas_used=GAS_LIMIT // 2, base_fee=BASE_FEE),
        accounts={**{a: 10**22 for a in users + background}, "mm": 10**24},
    ))
    on_chain = ORDER_RATE * r.slot * ORDER_GAS if r.channel == "chain" else 0
    target = GAS_LIMIT // 2 - SETTLE_GAS - on_chain
    sim.add_load(TransferLoad("bg", rate=target / BACKGROUND_GAS / r.slot, senders=background, gas=BACKGROUND_GAS))
    sim.add_load(TransferLoad("order", rate=ORDER_RATE, senders=users, gas=ORDER_GAS, tip=fixed(ORDER_TIP),
                              fee_multiplier=ORDER_CAP, stop=WINDOW[1]))
    c = Clearing("mm", address="mm", members=MEMBERS, orders="order", channel=r.channel, rounds=r.rounds, rtt=RTT,
                 margin=r.margin, gas=SETTLE_GAS)
    sim.add_load(c)
    rec = sim.run(RUN)
    return measure(rec, c, r)


def measure(rec, c: Clearing, r: Run) -> dict:
    proposer = {b["number"]: b["proposer"] for b in rec.blocks}
    due = [b for b in c.batches if WINDOW[0] <= b.target * r.slot < WINDOW[1]]
    in_time, late, inputs, outputs, room = 0, [], [], [], []
    for b in due:
        if r.channel == "chain":
            inputs.append(b.cut_at - (b.target - 1) * r.slot)
        t = rec.txs[b.tx.hash] if b.tx is not None else None
        if t is None or t.block is None:
            late.append(None)
            continue
        late.append(t.block - b.target)
        in_time += t.block == b.target
        seen = t.first_seen.get(proposer.get(b.target, ""))
        if seen is not None:
            outputs.append(seen - b.ended_at)
            if r.channel == "chain":
                room.append(b.target * r.slot - b.cut_at - (seen - b.ended_at))  # the time the rounds may take
    settled_by = {}
    sent_for = {}
    cuts = [b.cut_at for b in c.batches]
    for i, b in enumerate(c.batches):
        t = rec.txs[b.tx.hash] if b.tx is not None else None
        for h in b.orders:
            settled_by[h] = (i, t.included_at if t is not None else None)
    orders, made, delays, unsettled = 0, 0, [], 0
    for h, t in rec.txs.items():
        if not t.tx.label.startswith("order") or not WINDOW[0] <= t.submitted_at < WINDOW[1]:
            continue
        orders += 1
        if r.channel == "chain":
            made += t.block == math.ceil(t.submitted_at / r.slot)
        else:
            first = next((i for i, cut in enumerate(cuts) if cut >= t.submitted_at), None)
            made += h in settled_by and settled_by[h][0] == first
            reached = [t.first_seen.get(m) for m in c.members]
            if None not in reached:
                inputs.append(max(reached) - t.submitted_at)
        if h not in settled_by or settled_by[h][1] is None:
            unsettled += 1
            continue
        delays.append(settled_by[h][1] - t.submitted_at)
    known = [x for x in late if x is not None]
    return {"batches": len(due), "in time": in_time, "late max": max(known, default=None),
            "unsent": len(late) - len(known), "orders": orders, "made": made, "unsettled": unsettled,
            "delay p50": percentile(delays, 50), "delay p90": percentile(delays, 90),
            "input p50": percentile(inputs, 50), "input p99": percentile(inputs, 99),
            "output p50": percentile(outputs, 50), "output p99": percentile(outputs, 99),
            "room p1": percentile(room, 1)}


def runs() -> list[Run]:
    rs = [Run(ch, slot, n) for ch in ("chain", "pool") for slot in SLOTS for n in ROUNDS]
    rs += [Run("pool", slot, MARGIN_ROUNDS, m) for slot in SLOTS for m in MARGINS]
    return rs


def pct(part: int, whole: int) -> str:
    return f"{100 * part / whole:.2f}" if whole else "--"


def settle_rows(out: dict, channel: str, extra) -> list[list]:
    rows = []
    for r, o in out.items():
        if r.channel == channel and r.margin == MARGIN:
            rows.append([r.slot, r.rounds, f"{r.rounds * RTT:.2f}", o["batches"], pct(o["in time"], o["batches"]),
                         o["late max"], *extra(o), o["unsettled"], o["delay p50"], o["delay p90"]])
    return rows


def section_1(out: dict) -> str:
    return "\n".join([
        "## 1. Orders from the chain",
        "",
        f"{NODES} nodes, {DEGREE} peers each, a block every slot from a proposer in turn among the nodes that are not "
        f"the committee's, gas limit {GAS_LIMIT}, transfers of {BACKGROUND_GAS} gas filling the gas target beside the "
        f"orders and one settlement a block. Users send orders of {ORDER_GAS} gas at {ORDER_RATE} a second, from "
        f"accounts of their own, at a tip of {ORDER_TIP} wei and a fee cap of {ORDER_CAP} times the next base fee, "
        f"to random nodes, until second {WINDOW[1]:.0f}. The committee's members are nodes {', '.join(MEMBERS)}. "
        "Each batch takes the orders a block carried, starts once every member has imported that block and the "
        f"last batch has ended, takes the rounds in the table at a {RTT * 1000:.0f} ms round trip, and is settled "
        f"by {MEMBERS[0]} with a settlement of {SETTLE_GAS} gas from an account, at a tip of 2000000000 wei, meant "
        f"for the next block. Rows are the batches meant for a block from second {WINDOW[0]:.0f} to second "
        f"{WINDOW[1]:.0f} and the orders sent in it; the run lasts {RUN:.0f} s. In time is the percentage of batches "
        "settled in the block they were meant for, and late the most blocks after it; next block is the percentage "
        "of orders included in the first block after they were sent; delays are seconds from sending an order to "
        "the block that settled it.",
        "",
        table(["slot, s", "rounds", "rounds, s", "batches", "in time", "late, blocks", "next block", "unsettled",
               "delay p50", "p90"], settle_rows(out, "chain", lambda o: [pct(o["made"], o["orders"])])),
    ])


def section_2(out: dict) -> str:
    rows = []
    for r, o in out.items():
        if r.rounds == ROUNDS[0] and r.margin == MARGIN:
            fit = ["--"] * len(RTTS)
            if r.channel == "chain" and o["room p1"] is not None:
                fit = [math.floor(o["room p1"] / rtt) for rtt in RTTS.values()]
            rows.append([r.channel, r.slot, o["input p50"], o["input p99"], o["output p50"], o["output p99"], *fit,
                         *[math.floor(r.slot / rtt) for rtt in RTTS.values()]])
    names = list(RTTS)
    return "\n".join([
        "## 2. The network on either side",
        "",
        f"The {ROUNDS[0]}-round rows of sections 1 and 3. Before is, from the chain, seconds from a block to the "
        "last member's import of it, and from the pool, seconds from sending an order to the last member's holding "
        "it; after is seconds from sending a settlement to its arrival in the pool of the proposer it was meant for. "
        "Rounds that fit, from the chain, is the most rounds at each round trip that would have left 99 percent of "
        "the batches in time, from the slot less both sides as each batch met them; the slot alone is an earlier "
        "MPC study's budget, the slot divided by the round trip.",
        "",
        table(["orders", "slot, s", "before p50", "p99", "after p50", "p99",
               *[f"fit, {n}" for n in names], *[f"slot alone, {n}" for n in names]], rows),
    ])


def section_3(out: dict) -> str:
    return "\n".join([
        "## 3. Orders from the pool",
        "",
        "Section 1 with orders that travel the network as transactions and that no builder includes, so they reach "
        "the chain only through the settlement. Each batch takes the orders every member has held since before its "
        f"cutoff, {MARGIN:.0f} s and the rounds before the block it is meant for, and that no earlier batch took. "
        "Own batch is the percentage of orders in the first batch cut after they were sent.",
        "",
        table(["slot, s", "rounds", "rounds, s", "batches", "in time", "late, blocks", "own batch", "unsettled",
               "delay p50", "p90"], settle_rows(out, "pool", lambda o: [pct(o["made"], o["orders"])])),
    ])


def section_4(out: dict) -> str:
    rows = []
    for r, o in out.items():
        if r.channel == "pool" and r.rounds == MARGIN_ROUNDS:
            rows.append([r.slot, f"{r.margin:.2f}", o["batches"], pct(o["in time"], o["batches"]), o["late max"],
                         pct(o["made"], o["orders"]), o["delay p50"], o["delay p90"]])
    rows.sort(key=lambda row: (-row[0], float(row[1])))
    return "\n".join([
        "## 4. The pool's margin",
        "",
        f"Section 3 at {MARGIN_ROUNDS} rounds, with the cutoff the rounds and the margin in the table before the "
        "block a batch is meant for.",
        "",
        table(["slot, s", "margin, s", "batches", "in time", "late, blocks", "own batch", "delay p50", "p90"], rows),
    ])


def main() -> None:
    rs = runs()
    out = dict(zip(rs, run_all(simulate, rs)))
    print("# 20. A committee that clears every block: results")
    print()
    print(f"Generated by `experiments/20-per-block-clearing/run.py`, seed {SEED}, {NODES} nodes, {DEGREE} peers "
          f"each, gas limit {GAS_LIMIT}, {RUN:.0f} s a run, frame pool profile `eip-8141`. Do not edit by hand.")
    print()
    print(section_1(out))
    print()
    print(section_2(out))
    print()
    print(section_3(out))
    print()
    print(section_4(out))


if __name__ == "__main__":
    main()
