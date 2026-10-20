#!/usr/bin/env python3
"""Experiment 19: a committee's settlement through the pool. Prints results.md on standard output.

Merces, an MPC confidential token (ePrint 2026/850), is two transactions: a
user's intent, 873,716 gas, and the committee's settlement of up to 50
intents, 1,125,950 gas whatever the batch holds, since a short batch is
padded.
The committee decides when to post, so it trades the users' latency against
their gas. This measures that trade on a network, with the rounds the
committee needs between blocks, and what a burst of demand does to a
committee that sends from an account, from one frame transaction at a time,
or from a nonce key for each batch. No clause changes; decision record 0028.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "ref" / "python"), str(ROOT / "sim")]

from emem import EIP_8141, Head  # noqa: E402
from emem_sim import (ChainConfig, Committee, NetworkConfig, Scenario, Simulation, TransferLoad,  # noqa: E402
                      fixed, percentile, run_all, table)

SEED = 1
NODES = 10
DEGREE = 8
SLOT = 12
GAS_LIMIT = 60_000_000
BASE_FEE = 1_000_000_000
RUN = 2400.0
WINDOW = (240.0, 1800.0)  # intents sent in it are measured
INTENT_GAS = 873_716  # Merces, two-hash, Table 4
SETTLE_GAS = 1_125_950  # 50 x 22,519; the same for a padded short batch
BATCH = 50
INTENT_TIP = 3_000_000_000
INTENT_CAP = 100  # times the next base fee
BACKGROUND_GAS = 1_000_000
ROUNDS = 63  # a batch's floor: witness extension and coGroth16
RTT = {"same region": 0.005, "cross-continent": 0.080, "intercontinental": 0.250}  # an earlier MPC study's round trips
BURST = (600.0, 900.0, 2 * GAS_LIMIT)  # from, to, gas a slot
SENDERS = {"account": "one", "frame": "one", "keys": "disjoint-keys"}  # the frame pool's per_sender


@dataclass(frozen=True)
class Run:
    section: int
    rate: float  # intents a slot
    rule: str = "every"
    wait: int = 5
    sender: str = "account"
    rtt: str = "same region"
    tip: int = 2_000_000_000
    burst: bool = False
    patience: int | None = None


def simulate(r: Run) -> dict:
    profile = replace(EIP_8141, per_sender=SENDERS[r.sender])
    users = [f"u{i}" for i in range(6000)]
    background = [f"b{i}" for i in range(3000)]
    accounts = {**{a: 10**22 for a in users + background}, "mpc": 10**24}
    sim = Simulation(Scenario(
        seed=SEED, nodes=NODES,
        network=NetworkConfig(degree=DEGREE, latency=(0.02, 0.10), arrive_timeout=0.5),
        chain=ChainConfig(slot_time=SLOT, proposer="rotate", block_delay=(0.1, 1.0)),
        frame_pool=profile,
        genesis=Head(timestamp=0, gas_limit=GAS_LIMIT, gas_used=GAS_LIMIT // 2, base_fee=BASE_FEE),
        accounts=accounts, code={} if r.sender == "account" else {"mpc": "committee"},
    ))
    target = GAS_LIMIT // 2 - r.rate * INTENT_GAS - SETTLE_GAS
    sim.add_load(TransferLoad("bg", rate=target / BACKGROUND_GAS / SLOT, senders=background, gas=BACKGROUND_GAS))
    if r.burst:
        sim.add_load(TransferLoad("burst", rate=BURST[2] / BACKGROUND_GAS / SLOT, senders=background,
                                  gas=BACKGROUND_GAS, start=BURST[0], stop=BURST[1]))
    sim.add_load(TransferLoad("intent", rate=r.rate / SLOT, senders=users, gas=INTENT_GAS, tip=fixed(INTENT_TIP),
                              fee_multiplier=INTENT_CAP, stop=WINDOW[1]))
    committee = Committee("settle", address="mpc", node="n00", intents="intent-", rule=r.rule, sender=r.sender,
                          batch=BATCH, wait=r.wait, compute=ROUNDS * RTT[r.rtt], gas=SETTLE_GAS, settle_tip=r.tip,
                          patience=r.patience)
    sim.add_load(committee)
    rec = sim.run(RUN)
    return measure(rec, committee)


def measure(rec, c: Committee) -> dict:
    base = {b["number"]: b["base_fee"] for b in rec.blocks}
    settled_at = {}
    for s in c.settlements:
        if s.included_at is not None and not s.reverted:
            for i in range(s.start, s.end):
                settled_at[i] = s.included_at
    from_inclusion, from_sending, measured, unsettled = [], [], 0, 0
    for i, h in enumerate(c.queue):
        t = rec.txs[h]
        if not WINDOW[0] <= t.submitted_at < WINDOW[1]:
            continue
        measured += 1
        if i not in settled_at:
            unsettled += 1
            continue
        from_inclusion.append(settled_at[i] - t.included_at)
        from_sending.append(settled_at[i] - t.submitted_at)
    landed = [s for s in c.settlements if s.included_at is not None]
    good = [s for s in landed if not s.reverted]
    gas = sum(c.gas for s in landed)
    wei = 0
    for s in landed:
        tx = next(v for v in s.versions if rec.txs[v.hash].included_at is not None)
        fee = base[s.block]
        wei += c.gas * (fee + min(tx.tip, tx.max_fee - fee))
    transfers = sum(s.size for s in good)
    before = [b["base_fee"] for b in rec.blocks if b["at"] < BURST[0]]
    after = [b["base_fee"] for b in rec.blocks if b["at"] >= BURST[1]]
    return {"base before": before[-1], "base max": max(b["base_fee"] for b in rec.blocks), "base after": min(after),
            "intents": measured, "unsettled": unsettled,
            "p50": percentile(from_inclusion, 50), "p90": percentile(from_inclusion, 90),
            "max": max(from_inclusion, default=None), "sent p50": percentile(from_sending, 50),
            "sent p90": percentile(from_sending, 90),
            "settlements": len(good), "size": transfers / len(good) if good else None,
            "reverted": len(landed) - len(good), "versions": sum(len(s.versions) for s in c.settlements),
            "gas": INTENT_GAS + gas / transfers if transfers else None,
            "settle wei": wei / transfers if transfers else None}


def runs() -> list[Run]:
    rs = []
    for rate in (1, 5, 20):
        rs.append(Run(1, rate))
        rs += [Run(1, rate, rule="full", wait=w) for w in (5, 25)]
    for rtt in RTT:
        rs += [Run(2, 5, sender=s, rtt=rtt) for s in ("account", "frame")]
    for patience in (None, 1):
        rs += [Run(3, 5, sender=s, tip=100_000_000, burst=True, patience=patience) for s in SENDERS]
    return rs


def rule(r: Run) -> str:
    return "every block" if r.rule == "every" else f"full, or {r.wait} blocks"


def section_1(out: dict) -> str:
    rows = []
    for r, o in out.items():
        if r.section == 1:
            rows.append([r.rate, rule(r), o["intents"], o["unsettled"], o["p50"], o["p90"], o["max"], o["sent p90"],
                         o["settlements"], o["size"], o["gas"]])
    return "\n".join([
        "## 1. The batching rule against demand",
        "",
        f"{NODES} nodes, {DEGREE} peers each, a block every {SLOT} s from a rotating proposer, gas limit {GAS_LIMIT}, "
        f"transfers of {BACKGROUND_GAS} gas filling the gas target beside the intents and one settlement a block. "
        f"Users send intents of {INTENT_GAS} gas at the rate in the table, from accounts of their own, at a tip of "
        f"{INTENT_TIP} wei and a fee cap of {INTENT_CAP} times the next base fee, to random nodes, until second "
        f"{WINDOW[1]:.0f}. The committee watches node n00. It settles at most {BATCH} intents at once, every block "
        f"or only when it has {BATCH} or the oldest has waited the blocks in the table; a batch takes {ROUNDS} "
        f"rounds at a {RTT['same region'] * 1000:.0f} ms round trip, and its settlement {SETTLE_GAS} gas, from an "
        f"account at a tip of 2000000000 wei. Rows are the intents first sent from second {WINDOW[0]:.0f}; the run "
        f"lasts {RUN:.0f} s. Delays are seconds from the block that included an intent to the block that settled it, "
        "and the 90th percentile from sending; gas is a transfer's, its intent and its share of the settlements.",
        "",
        table(["a slot", "rule", "intents", "unsettled", "delay p50", "p90", "max", "from sending p90",
               "settlements", "batch", "gas a transfer"], rows),
    ])


def section_2(out: dict) -> str:
    rows = []
    for r, o in out.items():
        if r.section == 2:
            rows.append([r.rtt, f"{ROUNDS * RTT[r.rtt]:.3f}", r.sender, o["intents"], o["unsettled"], o["p50"],
                         o["p90"], o["max"], o["settlements"], o["size"], o["gas"]])
    return "\n".join([
        "## 2. The committee's rounds",
        "",
        f"Section 1 at 5 intents a slot, every block, with a batch's {ROUNDS} rounds at an earlier MPC study's "
        "round trips, and "
        "the settlement sent from an account, at its next nonce, or as a frame transaction at the next sequence of "
        "one nonce key, which the pool holds only once the last has landed.",
        "",
        table(["network", "rounds, s", "sender", "intents", "unsettled", "delay p50", "p90", "max", "settlements",
               "batch", "gas a transfer"], rows),
    ])


def section_3(out: dict) -> str:
    rows = []
    for r, o in out.items():
        if r.section == 3:
            rows.append([r.sender, "every block" if r.patience else "no", o["intents"], o["unsettled"], o["p50"],
                         o["p90"], o["max"], o["settlements"], o["size"], o["reverted"], o["versions"],
                         o["settle wei"]])
    bases = []
    for r, o in out.items():
        if r.section == 3:
            bases.append([r.sender, "every block" if r.patience else "no", o["base before"], o["base max"],
                          o["base after"]])
    return "\n".join([
        "## 3. A burst",
        "",
        f"Section 1 at 5 intents a slot, every block, the same region, with a committee that bids a tip of "
        f"100000000 wei, and from second {BURST[0]:.0f} to second {BURST[1]:.0f} a burst of {BACKGROUND_GAS}-gas "
        f"transfers at {BURST[2]} gas a slot, twice the gas limit. The settlement is sent from an account; as a "
        "frame transaction under one nonce key; or as a frame transaction under a nonce key of its own, which "
        "`disjoint-keys` admits beside the others, so that one included before the settlement it follows reverts. "
        "A committee that re-prices replaces a settlement its node has imported a block without, raising tip and "
        "fee cap by 10 percent and the cap to twice the next base fee plus the tip. Reverted counts settlements a "
        "block included out of order; versions every settlement and replacement sent; wei is what the "
        "settlements cost a transfer settled, reverted ones included.",
        "",
        table(["sender", "re-prices", "intents", "unsettled", "delay p50", "p90", "max", "settlements", "batch",
               "reverted", "versions", "settlement wei a transfer"], rows),
        "",
        f"The base fee, in wei: in the last block before second {BURST[0]:.0f}, the highest in the run, and the "
        f"least from second {BURST[1]:.0f} to the end.",
        "",
        table(["sender", "re-prices", "before the burst", "highest", "least after the burst"], bases),
    ])


def main() -> None:
    rs = runs()
    out = dict(zip(rs, run_all(simulate, rs)))
    print("# 19. A committee's settlement: results")
    print()
    print(f"Generated by `experiments/19-committee-settlement/run.py`, seed {SEED}, {NODES} nodes, {DEGREE} peers "
          f"each, {SLOT} s slots, gas limit {GAS_LIMIT}, {RUN:.0f} s a run, frame pool profile `eip-8141` with "
          "`per_sender` `one`, or `disjoint-keys` for a committee with a key for each settlement. Do not edit by "
          "hand.")
    print()
    print(section_1(out))
    print()
    print(section_2(out))
    print()
    print(section_3(out))


if __name__ == "__main__":
    main()
