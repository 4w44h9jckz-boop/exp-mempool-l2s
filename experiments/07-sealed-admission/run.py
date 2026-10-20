#!/usr/bin/env python3
"""Experiment 07: sealed admission (LUCID, EIP-8184). Prints results.md on standard output.

EIP-8184 leaves the sealed-transaction mempool's admission policy open: "there
are no fixed settings that can be established at this point for STs that
should or should not be propagated". `docs/spec/06-lucid.md` keeps three
readings as `policy` (LU-8) and two eviction orders as `evict_first` (LU-10).
This measures how long a cheap sealed payment, which bids no ToB fee and
tolerates every commitment before it, waits as demand approaches the 32
commitments a block takes; and what each reading admits of a flood of sealed
transactions that tolerate none before them, from one that bids a wei above
the payments to one that bids above everything.
"""

from __future__ import annotations

import random
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "ref" / "python"), str(ROOT / "sim")]

from emem import EIP_8184, Head, SealedTx, State, TxPool, build_block  # noqa: E402
from emem.sealed import fees  # noqa: E402
from emem_sim import (ChainConfig, NetworkConfig, Scenario, SealedFlood, SealedLoad, Simulation,  # noqa: E402
                      TransferLoad, percentile, table, uniform)

SEED = 1
NODES = 10
DEGREE = 8
SLOT = 12
GAS_LIMIT = 60_000_000  # a ToB segment of 7,500,000 (LU-1)
BASE_FEE = 1_000_000_000
MIN_TIP = 1_000_000  # BB-1, go-ethereum's miner default
RUN = 1200.0
WINDOW = (240.0, 960.0)  # honest demand that is measured; the flood, when there is one
PAY_GAS, PAY_SIZE = 100_000, 512
TRADE_GAS, TRADE_RATE = 300_000, 2  # a slot
TRADE_TOB = (10**12, 10**15)  # wei, uniformly
TRADE_PRECEDING = (1, 8)
BACKGROUND_GAS = 1_000_000
FLOOD_SIZE = 256  # bytes, so a gas limit of 16384 (LU-4)
ESCALATE_FROM = TRADE_TOB[1] + 1
NET_SLOTS = 256  # `st_slots` on the network under a flood, so that a fresh flood every block fits the model's budget
SURPLUS = 16
POLICY_RUNS = [("any", "last"), ("next-block", "last"), ("every-head", "last")]
EVICT_RUNS = [("any", "unplaced"), ("next-block", "unplaced")]


def profile(policy: str, evict: str, **changes):
    return EIP_8184.with_(policy=policy, evict_first=evict, **changes)


def name(policy: str, evict: str) -> str:
    return policy if evict == "last" else f"{policy}, {evict}"


def net_paid(st: SealedTx, base_fee: int, cfg) -> int:
    """What a committed, revealed sealed transaction costs its sender, in wei (LU-12, LU-13)."""
    f = fees(st, base_fee)
    refund = base_fee * (st.gas_limit - st.dual_gas_used) + f.tob * (cfg.tob_fee_fraction - 1) // cfg.tob_fee_fraction
    return f.ticket_fee - refund


# --- 1. One pool and the next block ---------------------------------------------

def one_pool(policy: str, evict: str, kind: str) -> list:
    """A sealed pool at the profile's size holding a slot's honest demand; then a flood; then a payment; a block."""
    cfg = profile(policy, evict)
    rng = random.Random(f"{SEED}/one-pool")
    head = Head(timestamp=12_000, gas_limit=GAS_LIMIT, gas_used=GAS_LIMIT // 2, base_fee=BASE_FEE)
    state = State()
    honest = []
    for i in range(16):
        honest.append(SealedTx(f"p{i}", max_fee=3 * BASE_FEE, tip=MIN_TIP, gas_limit=PAY_GAS, size=PAY_SIZE,
                               label=f"pay-{i}"))
    for i in range(TRADE_RATE):
        tob = rng.randint(*TRADE_TOB)
        honest.append(SealedTx(f"t{i}", max_fee=3 * BASE_FEE + -(-tob // TRADE_GAS), tip=MIN_TIP,
                               gas_limit=TRADE_GAS, max_tob_fee=tob, max_preceding=rng.randint(*TRADE_PRECEDING),
                               label=f"trade-{i}"))
    flood = SealedFlood("flood", kind=kind, k=cfg.st_slots + 64, tob=1 if kind == "cheap" else ESCALATE_FROM,
                        size=FLOOD_SIZE, surplus=64)
    flood.rng = random.Random(f"{SEED}/one-pool/flood")
    for tx in honest:
        state.edit(tx.sender).balance = 10**18
    for s in flood.senders:
        state.edit(s).balance = 10**18
    state.edit("late").balance = 10**18
    pool = TxPool(head, state, sealed_config=cfg)
    assert pool.add(honest) == ["ok"] * len(honest)
    sealed = pool.sealed
    budget = cfg.st_slots - len(sealed.entries) + flood.surplus
    admitted = 0
    for sender in flood.senders[:budget]:
        if pool.add([flood.sealed(sealed, sender)])[0] == "ok":
            admitted += 1
    capital = max(st.cost for st in flood._current.values())
    held = sum(1 for e in sealed.entries.values() if e.tx.sender.startswith("flood"))
    honest_held = len(sealed.entries) - held
    late = SealedTx("late", max_fee=3 * BASE_FEE, tip=MIN_TIP, gas_limit=PAY_GAS, size=PAY_SIZE, label="late")
    answer = pool.add([late])[0]
    block, post = build_block(pool, head, state, min_tip=MIN_TIP)
    theirs = [c.tx for c in block.commitments if c.tx.sender.startswith("flood")]
    pool.reset(block.head, post)
    after = sum(1 for e in sealed.entries.values() if e.tx.sender.startswith("flood"))
    paid = sum(net_paid(st, block.head.base_fee, cfg) for st in theirs)
    return [name(policy, evict), kind, budget, admitted, held, honest_held, answer,
            len(block.commitments) - len(theirs), len(theirs), paid, after, capital * len(flood.senders)]


def section_1() -> str:
    rows = [one_pool(p, e, k) for k in ("cheap", "escalating") for p, e in POLICY_RUNS + EVICT_RUNS]
    lines = [
        "## 1. One pool and the next block",
        "",
        f"A sealed pool of the profile's size, {EIP_8184.st_slots} slots, at a head with gas limit {GAS_LIMIT} and "
        f"base fee {BASE_FEE} wei, holds a slot's honest demand: 16 payments that bid no ToB fee and tolerate 31 "
        f"commitments before them, {PAY_GAS} gas each, and {TRADE_RATE} trades of {TRADE_GAS} gas that bid a ToB fee "
        f"drawn between {TRADE_TOB[0]} and {TRADE_TOB[1]} wei and tolerate between {TRADE_PRECEDING[0]} and "
        f"{TRADE_PRECEDING[1]}. A flood then sends enough of its sealed transactions to fill the pool and 64 more, "
        f"each from a sender of its own, tolerating no commitment before it, {FLOOD_SIZE} bytes and so "
        f"{64 * FLOOD_SIZE} gas: *cheap* ones that all bid 1 wei of ToB fee, or *escalating* ones that bid from "
        f"{ESCALATE_FROM} wei up, one more each. Then one more honest payment arrives, and the pool's node builds "
        "the next block and resets to it. Paid is what the flood's commitments cost it once revealed, in wei, and "
        "capital is the balance its senders must hold for the pool to admit them all (LU-5).",
        "",
        table(["pool", "flood", "sent", "admitted", "held", "honest held", "next payment", "honest committed",
               "flood committed", "paid, wei", "flood held after the head", "capital, wei"], rows),
    ]
    return "\n".join(lines)


# --- 2 and 3. The network --------------------------------------------------------

def simulation(cfg, pay_rate: float, flood: str | None = None, reseal: bool = False):
    pays = [f"p{i}" for i in range(4000)]
    trades = [f"t{i}" for i in range(400)]
    background = [f"b{i}" for i in range(600)]
    accounts = {a: 10**20 for a in pays + trades + background}
    adversary = None
    if flood:
        adversary = SealedFlood("flood", kind=flood, k=cfg.st_slots + 4 * SURPLUS,
                                tob=1 if flood == "cheap" else ESCALATE_FROM, size=FLOOD_SIZE, surplus=SURPLUS,
                                start=WINDOW[0], stop=WINDOW[1])
        accounts.update({s: 10**18 for s in adversary.senders})
    sim = Simulation(Scenario(
        seed=SEED,
        nodes=NODES,
        network=NetworkConfig(degree=DEGREE, latency=(0.02, 0.10), arrive_timeout=0.5),
        chain=ChainConfig(slot_time=SLOT, proposer="rotate", block_delay=(0.1, 1.0), min_tip=MIN_TIP),
        sealed_pool=cfg,
        genesis=Head(timestamp=0, gas_limit=GAS_LIMIT, gas_used=GAS_LIMIT // 2, base_fee=BASE_FEE),
        accounts=accounts,
    ))
    sealed_gas = pay_rate * PAY_GAS + TRADE_RATE * TRADE_GAS
    sim.add_load(TransferLoad("bg", rate=(GAS_LIMIT // 2 - sealed_gas) / BACKGROUND_GAS / SLOT, senders=background,
                              gas=BACKGROUND_GAS))
    payments = SealedLoad("pay", rate=pay_rate / SLOT, senders=pays, gas=PAY_GAS, size=PAY_SIZE, reseal=reseal,
                          stop=WINDOW[1])
    trading = SealedLoad("trade", rate=TRADE_RATE / SLOT, senders=trades, tob=uniform(*TRADE_TOB),
                         preceding=uniform(*TRADE_PRECEDING), gas=TRADE_GAS, size=PAY_SIZE, reseal=reseal,
                         stop=WINDOW[1])
    sim.add_load(payments)
    sim.add_load(trading)
    if adversary:
        sim.add_load(adversary)
    watch = Watch(sim)
    return sim, payments, trading, adversary, watch


class Watch:
    """Per node, mid-slot, how many sealed transactions the pool holds and how many are the flood's; and what
    every node admitted of the flood, relayed ones included."""

    def __init__(self, sim):
        self.sim = sim
        self.held: list[int] = []
        self.flood_held: list[int] = []
        self.admitted = 0
        self.evicted = Counter()  # honest sealed transactions LU-10 dropped, by load
        for node in sim.net.nodes.values():
            node.admit_hooks.append(self._admit)
        sim.sched.every(SLOT, self._sample, start=SLOT / 2)

    def _admit(self, node, tx, result) -> None:
        if result == "ok" and tx.label.startswith("flood"):
            self.admitted += 1

    def _sample(self) -> None:
        if not WINDOW[0] <= self.sim.sched.now < WINDOW[1]:
            return
        for node in self.sim.net.nodes.values():
            entries = node.pool.sealed.entries.values()
            self.held.append(len(entries))
            self.flood_held.append(sum(1 for e in entries if e.tx.label.startswith("flood")))


def outcome(rec, load) -> dict:
    """For the sealed transactions `load` first sent inside the window: delays to commitment, sends and refusals."""
    delays, missed, sends, answers = [], 0, [], Counter()
    by_quartile: dict[int, list[float]] = {q: [] for q in range(4)}
    for versions in load.sent:
        first = rec.txs[versions[0].hash]
        if not WINDOW[0] <= first.submitted_at < WINDOW[1]:
            continue
        got = load.answers[versions[0].hash]
        sends.append(len(got))
        answers.update(got)
        times = [rec.txs[v.hash].included_at for v in versions if rec.txs[v.hash].included_at is not None]
        if not times:
            missed += 1
            continue
        delay = min(times) - first.submitted_at
        delays.append(delay)
        by_quartile[int(versions[0].hash[2:10], 16) * 4 // 16**8].append(delay)
    n = len(sends)
    return {"sent": n, "committed": len(delays), "missed": missed, "p50": percentile(delays, 50),
            "p90": percentile(delays, 90), "p99": percentile(delays, 99), "max": max(delays, default=None),
            "mean": sum(delays) / len(delays) if delays else None, "sends": sum(sends) / max(1, n),
            "refused": {code: c / max(1, n) for code, c in answers.items() if code not in ("ok", "ErrAlreadyKnown")},
            "quartiles": by_quartile}


def mean(values) -> float | None:
    return sum(values) / len(values) if values else None


def run(policy: str, evict: str, pay_rate: float, flood: str | None = None, reseal: bool = False,
        slots: int | None = None) -> dict:
    cfg = profile(policy, evict, **({"st_slots": slots} if slots else {}))
    sim, payments, trading, adversary, watch = simulation(cfg, pay_rate, flood, reseal)
    rec = sim.run(RUN)
    committed = [(c.tx, b["base_fee"]) for b in rec.blocks for c in b["commitments"]]
    theirs = [(st, fee) for st, fee in committed if st.label.startswith("flood")]
    blocks = [b for b in rec.blocks if WINDOW[0] < b["at"] <= WINDOW[1]]
    evicted = Counter()
    for r in rec.txs.values():
        if isinstance(r.tx, SealedTx):
            evicted[r.tx.label.split("-")[0]] += r.dropped["evicted"]
    return {"pay": outcome(rec, payments), "trade": outcome(rec, trading), "adversary": adversary, "watch": watch,
            "flood committed": len(theirs), "flood paid": sum(net_paid(st, fee, cfg) for st, fee in theirs),
            "commitments": mean([len(b["commitments"]) for b in blocks]),
            "base fee": mean([b["base_fee"] for b in blocks]), "evicted": evicted,
            "capital": max((st.cost for st in adversary._current.values()), default=0) * adversary.k
            if adversary else 0}


RATES = (16, 28, 31, 34)
RESEAL_RATES = (28, 31)


def section_2() -> tuple[str, dict]:
    rows, kept = [], {}
    runs = [(p, e, rate, False) for rate in RATES for p, e in POLICY_RUNS]
    runs += [(p, e, rate, True) for rate in RESEAL_RATES for p, e in POLICY_RUNS[1:]]
    for policy, evict, rate, reseal in runs:
        r = run(policy, evict, rate, reseal=reseal)
        o = r["pay"]
        kept[(policy, rate, reseal)] = o["quartiles"]
        rows.append([name(policy, evict), "yes" if reseal else "no", rate, o["sent"], o["committed"], o["p50"],
                     o["p90"], o["p99"], o["max"], o["mean"], o["sends"],
                     o["refused"].get("ErrSTNotIncludable", 0.0), mean(r["watch"].held), r["commitments"],
                     sum(r["evicted"].values())])
    lines = [
        "## 2. Honest demand",
        "",
        f"A network of {NODES} nodes, {DEGREE} peers each, a block every {SLOT} s from a rotating proposer, gas limit "
        f"{GAS_LIMIT}, every pool at the profile's size. Payments arrive at the rate in the table, each from a "
        f"sender of its own with one in flight, bidding no ToB fee, tolerating 31 commitments before them, "
        f"{PAY_GAS} gas; trades arrive at {TRADE_RATE} a slot, as in section 1; both are sent to random nodes from "
        f"the start until second {WINDOW[1]:.0f}, and after every block that does not commit one its sender sends "
        f"it again to a random node, re-encrypted first where the table says resealed. Transfers of "
        f"{BACKGROUND_GAS} gas fill the rest of the gas target, so the base fee stays near {BASE_FEE} wei. Rows are "
        f"the payments first sent from second {WINDOW[0]:.0f} to second {WINDOW[1]:.0f}; the run lasts "
        f"{RUN:.0f} s. Delays are from first sending to the block that commits the payment, in seconds; its "
        "decrypted transaction runs one slot later (LU-13). Sends is the mean number of times a payment was sent, "
        "not-includable is `ErrSTNotIncludable` answers per payment, held is the mean number of sealed "
        "transactions a node's pool held mid-slot, commitments is the mean a block made, and evicted counts LU-10's "
        "drops of honest sealed transactions at any node.",
        "",
        table(["policy", "resealed", "a slot", "sent", "committed", "delay p50", "p90", "p99", "max", "mean",
               "sends", "not includable", "held", "commitments", "evicted"], rows),
    ]
    return "\n".join(lines), kept


def section_3(kept: dict) -> str:
    rows = []
    for rate in RESEAL_RATES:
        for policy, reseal in (("any", False), ("every-head", False), ("next-block", True), ("every-head", True)):
            row = [policy, "yes" if reseal else "no", rate]
            for q in range(4):
                d = kept[(policy, rate, reseal)][q]
                row += [percentile(d, 90), max(d, default=None)]
            rows.append(row)
    lines = [
        "## 3. Who waits",
        "",
        f"The payments of section 2 at {RESEAL_RATES[0]} and {RESEAL_RATES[1]} a slot, by the quartile of their "
        "first hash, lowest first: the 90th percentile and the longest of their delays, in seconds. Payments that "
        "bid no ToB fee and use the same gas are committed in the order of their hashes (LU-6), which "
        "re-encrypting draws again.",
        "",
        table(["policy", "resealed", "a slot", "q1 p90", "q1 max", "q2 p90", "q2 max", "q3 p90", "q3 max",
               "q4 p90", "q4 max"], rows),
    ]
    return "\n".join(lines)


FLOOD_RATE = 16


def section_4() -> str:
    rows, cost = [], []
    runs = [("any", "last", None)]
    runs += [(p, e, kind) for kind in ("cheap", "escalating") for p, e in POLICY_RUNS + EVICT_RUNS]
    for policy, evict, kind in runs:
        r = run(policy, evict, FLOOD_RATE, flood=kind, slots=NET_SLOTS)
        p, t, w = r["pay"], r["trade"], r["watch"]
        rows.append([name(policy, evict), kind or "none", p["sent"], p["committed"], p["p50"], p["p90"], t["sent"],
                     t["committed"], t["p50"], mean(w.held), mean(w.flood_held), r["evicted"]["pay"],
                     r["evicted"]["trade"]])
        if kind:
            a = r["adversary"]
            per = r["flood paid"] / r["flood committed"] if r["flood committed"] else None
            cost.append([name(policy, evict), kind, a.sent, w.admitted, r["flood committed"], r["flood paid"],
                         per, r["capital"], r["base fee"]])
    lines = [
        "## 4. A flood on the network",
        "",
        f"The network of section 2 with every pool at {NET_SLOTS} slots, payments at {FLOOD_RATE} a slot and trades "
        f"at {TRADE_RATE}, resent but not resealed. From second {WINDOW[0]:.0f} to second {WINDOW[1]:.0f} an "
        f"adversary with {NET_SLOTS + 4 * SURPLUS} senders sends each node directly, at the start and after every "
        f"block it imports, the flood's sealed transactions of section 1 from senders the node holds none from: "
        f"enough to fill its pool and {SURPLUS} more, stopping at the first the node refuses. Rows are the honest "
        "sealed transactions first sent during the flood, and committed is by the end of the run, "
        f"{RUN - WINDOW[1]:.0f} s after it; delays are from first sending to commitment, in seconds; "
        "held and flood held are the mean number of sealed transactions, and of the flood's, a node's pool held "
        "mid-slot; evicted counts LU-10's drops of payments and of trades at any node.",
        "",
        table(["pool", "flood", "payments", "committed", "delay p50", "p90", "trades", "committed", "delay p50",
               "held", "flood held", "payments evicted", "trades evicted"], rows),
        "",
        "What the flood cost: the sealed transactions it sent to nodes directly; their admissions at any node, "
        "relayed ones included; how many blocks committed; what those cost it once revealed, in all and per "
        "commitment, in wei; the balance its senders hold, in wei; and the mean base fee during the flood.",
        "",
        table(["pool", "flood", "sent", "admitted", "committed", "paid, wei", "per commitment, wei", "capital, wei",
               "base fee, wei"], cost),
    ]
    return "\n".join(lines)


def main() -> None:
    print("# 07. Sealed admission: results")
    print()
    print(f"Generated by `experiments/07-sealed-admission/run.py`, seed {SEED}, {NODES} nodes, {DEGREE} peers each, "
          f"{SLOT} s slots, gas limit {GAS_LIMIT}, {RUN:.0f} s a run, sealed pool profile `eip-8184` with the policy "
          "and eviction order each row names. Do not edit by hand.")
    print()
    print(section_1())
    print()
    text, kept = section_2()
    print(text)
    print()
    print(section_3(kept))
    print()
    print(section_4())


if __name__ == "__main__":
    main()
