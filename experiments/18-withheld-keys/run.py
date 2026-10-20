#!/usr/bin/env python3
"""Experiment 18: withheld LUCID keys (EIP-8184). Prints results.md on standard output.

A key publisher that does not release a key leaves its sealed transaction
committed and charged, and nothing runs (LU-12, LU-13). This measures what
that does to cheap sealed payments on experiment 07's network, against the
share of key publishers that withhold, when the sender sends the payment
again sealed or in public, under each admission policy (LU-8); and what
experiment 07's escalating flood costs its adversary when it withholds every
key. Decision record 0027.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "ref" / "python"), str(ROOT / "sim")]

from emem import EIP_8184, Head, SealedTx  # noqa: E402
from emem.sealed import fees  # noqa: E402
from emem_sim import (ChainConfig, NetworkConfig, Scenario, SealedFlood, SealedLoad, Simulation,  # noqa: E402
                      TransferLoad, percentile, run_all, table, uniform)

SEED = 1
NODES = 10
DEGREE = 8
SLOT = 12
GAS_LIMIT = 60_000_000  # a ToB segment of 7,500,000 (LU-1)
BASE_FEE = 1_000_000_000
MIN_TIP = 1_000_000  # BB-1, go-ethereum's miner default
RUN = 1200.0
WINDOW = (240.0, 960.0)  # payments that are measured; the flood, when there is one
PAY_GAS, PAY_SIZE = 100_000, 512
TRADE_GAS, TRADE_RATE = 300_000, 2  # a slot
TRADE_TOB = (10**12, 10**15)  # wei, uniformly
TRADE_PRECEDING = (1, 8)
BACKGROUND_GAS = 1_000_000
PUBLISHERS = 10
WITHHOLDING = (0, 1, 3, 5)  # of the PUBLISHERS
RATES = (16, 28)  # payments a slot
POLICIES = ("any", "next-block", "every-head")
RESPONSES = ("sealed", "public")
FLOOD_SIZE = 256  # bytes, so a gas limit of 16384 (LU-4)
ESCALATE_FROM = TRADE_TOB[1] + 1
NET_SLOTS = 256  # experiment 07's section 4
SURPLUS = 16
FLOOD_RATE = 16
FLOOD_POOLS = (("any", "last"), ("every-head", "last"), ("any", "unplaced"))


@dataclass(frozen=True)
class Run:
    policy: str
    evict: str
    rate: int
    withholding: int = 0
    response: str = "sealed"
    flood: bool = False
    flood_revealed: bool = True


def name(policy: str, evict: str) -> str:
    return policy if evict == "last" else f"{policy}, {evict}"


def net_paid(st: SealedTx, base_fee: int, cfg) -> int:
    """What a committed sealed transaction costs its sender, in wei (LU-12, LU-13): the ticket, less the
    refund if it is revealed."""
    f = fees(st, base_fee)
    if not st.revealed:
        return f.ticket_fee
    refund = base_fee * (st.gas_limit - st.dual_gas_used) + f.tob * (cfg.tob_fee_fraction - 1) // cfg.tob_fee_fraction
    return f.ticket_fee - refund


def simulate(r: Run) -> dict:
    cfg = EIP_8184.with_(policy=r.policy, evict_first=r.evict, **({"st_slots": NET_SLOTS} if r.flood else {}))
    pays = [f"p{i}" for i in range(4000)]
    trades = [f"t{i}" for i in range(400)]
    background = [f"b{i}" for i in range(600)]
    accounts = {a: 10**20 for a in pays + trades + background}
    adversary = None
    if r.flood:
        adversary = SealedFlood("flood", kind="escalating", k=cfg.st_slots + 4 * SURPLUS, tob=ESCALATE_FROM,
                                size=FLOOD_SIZE, surplus=SURPLUS, start=WINDOW[0], stop=WINDOW[1],
                                revealed=r.flood_revealed)
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
    sealed_gas = r.rate * PAY_GAS + TRADE_RATE * TRADE_GAS
    sim.add_load(TransferLoad("bg", rate=(GAS_LIMIT // 2 - sealed_gas) / BACKGROUND_GAS / SLOT, senders=background,
                              gas=BACKGROUND_GAS))
    payments = SealedLoad("pay", rate=r.rate / SLOT, senders=pays, gas=PAY_GAS, size=PAY_SIZE, stop=WINDOW[1],
                          publishers=PUBLISHERS, withholding=r.withholding, response=r.response)
    trading = SealedLoad("trade", rate=TRADE_RATE / SLOT, senders=trades, tob=uniform(*TRADE_TOB),
                         preceding=uniform(*TRADE_PRECEDING), gas=TRADE_GAS, size=PAY_SIZE, stop=WINDOW[1])
    sim.add_load(payments)
    sim.add_load(trading)
    if adversary:
        sim.add_load(adversary)
    rec = sim.run(RUN)
    return measure(r, cfg, rec, payments, adversary)


def measure(r: Run, cfg, rec, payments: SealedLoad, adversary) -> dict:
    at = {b["number"]: b["at"] for b in rec.blocks}
    base = {b["number"]: b["base_fee"] for b in rec.blocks}
    delays, attempts, lost, public, sealed = [], [], [], 0, 0
    sent = 0
    for versions in payments.sent:
        first = rec.txs[versions[0].hash]
        if not WINDOW[0] <= first.submitted_at < WINDOW[1]:
            continue
        sent += 1
        done, paid_for, tries = None, 0, 0
        for v in dict.fromkeys(versions):  # a version once, though it was sent several times
            t = rec.txs[v.hash]
            if t.block is None:
                continue
            tries += 1
            if v.revealed:
                done = at.get(t.block + 1)  # LU-13: it runs in the next block
                sealed += done is not None
            else:
                paid_for += fees(v, base[t.block]).ticket_fee
        tx = payments.public.get(versions[0].hash)
        if tx is not None and rec.txs[tx.hash].included_at is not None:
            done = rec.txs[tx.hash].included_at
            public += 1
        attempts.append(tries)
        lost.append(paid_for)
        if done is not None:
            delays.append(done - first.submitted_at)
    blocks = [b for b in rec.blocks if WINDOW[0] < b["at"] <= WINDOW[1]]
    commits = [c.tx for b in blocks for c in b["commitments"]]
    out = {"sent": sent, "executed": len(delays), "sealed": sealed, "public": public,
           "p50": percentile(delays, 50), "p90": percentile(delays, 90), "p99": percentile(delays, 99),
           "max": max(delays, default=None), "attempts": sum(attempts) / max(1, sent),
           "lost": sum(lost) / max(1, sent), "lost max": max(lost, default=0),
           "commitments": len(commits) / max(1, len(blocks)),
           "withheld": sum(1 for st in commits if not st.revealed) / max(1, len(blocks)),
           "base fee": sum(b["base_fee"] for b in blocks) / max(1, len(blocks))}
    if adversary:
        theirs = [(c.tx, b["base_fee"]) for b in rec.blocks for c in b["commitments"] if c.tx.label.startswith("flood")]
        out["flood committed"] = len(theirs)
        out["flood paid"] = sum(net_paid(st, fee, cfg) for st, fee in theirs)
    return out


def runs() -> list[Run]:
    rs = []
    for rate in RATES:
        for policy in POLICIES:
            rs.append(Run(policy, "last", rate))
            rs += [Run(policy, "last", rate, w, resp) for w in WITHHOLDING[1:] for resp in RESPONSES]
    for revealed in (True, False):
        rs += [Run(p, e, FLOOD_RATE, flood=True, flood_revealed=revealed) for p, e in FLOOD_POOLS]
    return rs


def share(w: int) -> str:
    return f"{w} of {PUBLISHERS}"


def section_1(out: dict) -> str:
    rows = []
    for rate in RATES:
        for policy in POLICIES:
            for w in WITHHOLDING:
                for resp in (RESPONSES[:1] if w == 0 else RESPONSES):
                    o = out[Run(policy, "last", rate, w, resp if w else "sealed")]
                    rows.append([rate, policy, share(w), resp if w else "", o["sent"], o["executed"], o["sealed"],
                                 o["public"], o["p50"], o["p90"], o["p99"], o["max"], o["attempts"],
                                 o["lost"], o["lost max"], o["commitments"], o["withheld"]])
    return "\n".join([
        "## 1. Payments against withholding publishers",
        "",
        f"Experiment 07's network: {NODES} nodes, {DEGREE} peers each, a block every {SLOT} s from a rotating "
        f"proposer, gas limit {GAS_LIMIT}, every pool at the profile's {EIP_8184.st_slots} slots under the policy in "
        f"the table. Payments arrive at the rate in the table, each from a sender of its own with one in flight, "
        f"bidding no ToB fee, tolerating 31 commitments before them, {PAY_GAS} gas, sent to random nodes from the "
        f"start until second {WINDOW[1]:.0f}, and sent again to a random node after every block that does not "
        f"commit them; trades arrive at {TRADE_RATE} a slot as in experiment 07, and transfers of {BACKGROUND_GAS} "
        f"gas fill the rest of the gas target. Each payment's attempt names one of {PUBLISHERS} key publishers at "
        "random, among those that have not withheld from its sender before; the share in the table withhold every "
        "key. When the block that committed a withheld ticket reaches the node the sender sent it to, the sender "
        "sends the payment again at its next nonce: sealed, re-encrypted to a new publisher, or public, as a "
        f"regular transaction with the same gas and tip. Rows are the payments first sent from second "
        f"{WINDOW[0]:.0f} to second {WINDOW[1]:.0f}; the run lasts {RUN:.0f} s. Executed is by the end of the run, "
        "sealed or public; delays are from first sending to the block that runs the payment, its decrypted "
        "transaction one block after its commitment or its regular transaction, in seconds. Attempts is the mean "
        "number of the payment's tickets committed; lost is the mean, and the largest, wei a payment paid for "
        "tickets whose key was withheld; commitments and withheld are the mean a block made, and of them the "
        "withheld, during the window.",
        "",
        table(["a slot", "policy", "withholding", "response", "sent", "executed", "sealed", "public", "delay p50",
               "p90", "p99", "max", "attempts", "lost, wei", "lost max, wei", "commitments", "withheld"], rows),
    ])


def section_2(out: dict) -> str:
    rows = []
    for p, e in FLOOD_POOLS:
        for revealed in (True, False):
            o = out[Run(p, e, FLOOD_RATE, flood=True, flood_revealed=revealed)]
            per = o["flood paid"] / o["flood committed"] if o["flood committed"] else None
            rows.append([name(p, e), "released" if revealed else "withheld", o["sent"], o["executed"], o["p90"],
                         o["flood committed"], o["flood paid"], per])
    return "\n".join([
        "## 2. A flood that withholds",
        "",
        f"Experiment 07's section 4: every pool at {NET_SLOTS} slots, payments at {FLOOD_RATE} a slot with no "
        f"publisher withholding, and from second {WINDOW[0]:.0f} to second {WINDOW[1]:.0f} its escalating flood, "
        f"sealed transactions that tolerate no commitment before them and bid from {ESCALATE_FROM} wei of ToB fee "
        "up, sent to every node after every block it imports; its keys released, as in experiment 07, or all "
        "withheld. Rows are the payments first sent during the flood, executed by the end of the run, the 90th "
        "percentile of their delay to execution in seconds, the flood's commitments, and what they cost it in "
        "all and per commitment, in wei.",
        "",
        table(["pool", "flood keys", "payments", "executed", "delay p90", "flood committed", "paid, wei",
               "per commitment, wei"], rows),
    ])


def main() -> None:
    rs = runs()
    out = dict(zip(rs, run_all(simulate, rs)))
    print("# 18. Withheld keys: results")
    print()
    print(f"Generated by `experiments/18-withheld-keys/run.py`, seed {SEED}, {NODES} nodes, {DEGREE} peers each, "
          f"{SLOT} s slots, gas limit {GAS_LIMIT}, {RUN:.0f} s a run, sealed pool profile `eip-8184` with the policy "
          "and eviction order each row names. Do not edit by hand.")
    print()
    print(section_1(out))
    print()
    print(section_2(out))


if __name__ == "__main__":
    main()
