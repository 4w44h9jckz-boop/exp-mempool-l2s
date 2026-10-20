#!/usr/bin/env python3
"""Experiment 05: the expiry timestamp. Prints results.md on standard output.

EIP-8141 drops a frame transaction whose deadline "is less than the node's
view of the current block timestamp". FP-8 and FP-15 read that as the head's
timestamp, so a transaction whose deadline lies below the next block's is
admitted though no block can include it. This measures what a pool admits of
such transactions, from an adversary and from honest wallets, with the head's
timestamp and with the next slot's (`expiry_margin` set to the slot time),
under the EIP's eviction order and under experiment 04's tip-first variant;
and what the next slot's check leaves open: transactions a default-code
sponsor backs and then drains in the next block.
"""

from __future__ import annotations

import math
import random
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "ref" / "python"), str(ROOT / "sim")]

from emem import EIP_8141, GETH, HEGOTA_TESTNET, Account, Head, State, Tx, TxPool, build_block  # noqa: E402
from emem_sim import (ChainConfig, FloodLoad, NetworkConfig, Scenario, Simulation, WalletLoad,  # noqa: E402
                      backed_tx, percentile, table, uniform)

SEED = 1
NODES = 10
SLOT = 12
GAS_LIMIT = 2_100_000
BASE_FEE = 1_000_000_000
MIN_TIP = 1_000_000  # BB-1, go-ethereum's miner default
TIPS = (1_000_000, 3_000_000_000)  # what honest wallets tip, uniformly (the simulator's default)
EXPIRY = 600  # an honest deadline, seconds after first sending
SURPLUS = 16  # the adversary's transactions beyond the pool's room, after every block
JUNK_TIP = 10_000_000_000  # the adversary's tip: above every honest one


def variant(profile, name: str, **changes):
    return profile.with_(name=name, **changes)


EIP = variant(EIP_8141, "eip-8141")
NEXT = variant(EIP_8141, "eip-8141, next slot", expiry_margin=SLOT)
TIP = variant(EIP_8141, "eip-8141, tip first", evict_first="tip")
TIP_NEXT = variant(EIP_8141, "eip-8141, tip first, next slot", evict_first="tip", expiry_margin=SLOT)
HEGOTA = variant(HEGOTA_TESTNET, "hegota-testnet")
HEGOTA_TIP_NEXT = variant(HEGOTA_TESTNET, "hegota-testnet, tip first, next slot", evict_first="tip",
                          expiry_margin=SLOT)


def fee_cap(tip: int, base_fee: int = BASE_FEE) -> int:
    return 2 * base_fee + tip


def paid(txs, base_fee: int) -> int:
    """What the included `txs` paid in a block at `base_fee`, in wei (BB-5)."""
    return sum(min(tx.used, tx.gas_limit) * (base_fee + min(tx.tip, tx.max_fee - base_fee)) for tx in txs)


def deadline_of(tx) -> int | None:
    frames = getattr(tx, "frames", ())
    return frames[0].deadline if frames and frames[0].deadline is not None else None


# --- 1. One pool and the next block ---------------------------------------------

def one_pool(profile, kind: str):
    """A frame pool filled with honest transactions, a third of each class; then the adversary's; then a block."""
    rng = random.Random(f"{SEED}/one-pool")
    head = Head(timestamp=12_000, gas_limit=GAS_LIMIT, gas_used=GAS_LIMIT // 2, base_fee=BASE_FEE)
    capacity = profile.max_pending
    classes = ["pays", "deadline", "stranded"]
    honest = []
    for i in range(capacity):
        cls = classes[i % len(classes)]
        tip = rng.randint(*TIPS)
        cap = fee_cap(tip)
        if cls == "stranded":
            cap = rng.randint(BASE_FEE // 2, BASE_FEE - 1)
            tip = min(tip, cap)
        honest.append((cls, f"h{i}", cap, tip))
    accounts = {s: Account(balance=10**18) for _, s, _, _ in honest}
    accounts.update({f"j{i}": Account(balance=10**18) for i in range(capacity)})
    accounts["pm"] = Account(balance=10**24, code=profile.canonical_paymaster_code)
    accounts[profile.expiry_verifier] = Account(code=profile.expiry_verifier_code)
    junk, cap = [], fee_cap(JUNK_TIP)
    for i in range(capacity):
        if kind == "free":
            tx = backed_tx("paymaster", f"j{i}", "pm", max_fee=1, tip=1, label=f"j{i}",
                           expiry_verifier=profile.expiry_verifier)
        elif kind == "expiring":
            tx = backed_tx("paymaster", f"j{i}", "pm", max_fee=cap, tip=JUNK_TIP, label=f"j{i}",
                           deadline=head.timestamp + profile.expiry_margin, expiry_verifier=profile.expiry_verifier)
        else:  # drained
            tx = backed_tx("sponsor", f"j{i}", "dp", max_fee=cap, tip=JUNK_TIP, label=f"j{i}",
                           expiry_verifier=profile.expiry_verifier)
        junk.append(tx)
    drain_cap = fee_cap(2 * JUNK_TIP)
    if kind == "drained":
        accounts["dp"] = Account(balance=sum(tx.max_cost for tx in junk) + 21_000 * drain_cap)
    state = State(accounts)
    pool = TxPool(head, state, GETH, profile)
    by_hash = {}
    for cls, sender, cap, tip in honest:
        deadline = head.timestamp + EXPIRY if cls == "deadline" else None
        tx = backed_tx("self", sender, None, max_fee=cap, tip=tip, label=sender, exec_gas=50_000,
                       deadline=deadline, expiry_verifier=profile.expiry_verifier)
        assert pool.add([tx], 0) == ["ok"], cls
        by_hash[tx.hash] = cls
    answers = Counter(pool.add([tx], 0)[0] for tx in junk)
    theirs = {tx.hash for tx in junk}
    if kind == "drained":
        drain = Tx("dp", nonce=0, gas=21_000, max_fee=drain_cap, tip=2 * JUNK_TIP, label="drain",
                   value=state.balance("dp") - 21_000 * drain_cap, to="sink")
        assert pool.add([drain], 0) == ["ok"]
        theirs.add(drain.hash)
    before = Counter(by_hash.values())
    held = Counter(by_hash[h] for h in by_hash if pool.get(h) is not None)
    block, _ = build_block(pool, head, state, min_tip=MIN_TIP, coinbase="cb", slot_time=SLOT)
    included = [tx for tx in block.txs if tx.hash in theirs]
    skipped = Counter(err for tx, err in block.failed if tx.hash in theirs)
    return {"answers": answers, "out": {c: before[c] - held[c] for c in classes},
            "theirs": len(included), "honest": sum(1 for tx in block.txs if tx.hash in by_hash),
            "skipped": skipped, "paid": paid(included, block.head.base_fee)}


def section_1() -> str:
    rows = []
    for profile in (EIP, NEXT, TIP, TIP_NEXT, HEGOTA, HEGOTA_TIP_NEXT):
        for kind in ("free", "expiring", "drained"):
            r = one_pool(profile, kind)
            refused = Counter({a: n for a, n in r["answers"].items() if a != "ok"})
            skipped = r["skipped"].most_common(1)
            rows.append([profile.name, kind, r["answers"]["ok"], r["out"]["pays"], r["out"]["deadline"],
                         r["out"]["stranded"], refused.most_common(1)[0][0] if refused else "none",
                         r["theirs"], r["honest"], f"{skipped[0][1]} {skipped[0][0]}" if skipped else "none",
                         r["paid"]])
    lines = [
        "## 1. One pool and the next block",
        "",
        f"A frame pool of capacity {EIP.max_pending} at the pending base fee of 1 gwei and the head's timestamp is "
        "filled with honest transactions from distinct senders, a third each of three classes, as in experiment "
        "04: *pays*, a tip of 0.001 to 3 gwei and a fee cap of twice the base fee plus the tip; *deadline*, the "
        f"same with a deadline {EXPIRY} s out; *stranded*, a fee cap below the base fee. Then as many again of the "
        "adversary's transactions arrive, each from a sender of its own: *free*, a fee cap and tip of 1 wei, paid "
        "by a canonical paymaster instance; *expiring*, the earliest deadline the pool admits, the head's "
        "timestamp plus `expiry_margin`, at a tip of 10 gwei and a fee cap of twice the base fee plus the tip, "
        "paid by the same paymaster; *drained*, priced as *expiring* without a deadline, paid by one default-code "
        "sponsor, which then sends its whole balance away in a 21,000-gas transfer at 20 gwei. Then the pool "
        f"builds the next block, {SLOT} s later. Next block counts the adversary's transactions and the honest ones "
        "it includes, skipped is the adversary's that the builder skipped and why, and paid is what the "
        "adversary paid for its included ones, in wei.",
        "",
        table(["pool", "adversary", "admitted", "out: pays", "out: deadline", "out: stranded", "refused as",
               "next block: theirs", "next block: honest", "skipped", "paid, wei"], rows),
    ]
    return "\n".join(lines)


# --- 2. A flood on the network ---------------------------------------------------

NET_PENDING = 256  # `max_pending` on the network, so that a fresh flood every block fits the model's budget
FLOOD = (600.0, 1200.0)
RUN = 2700.0
RATE = 1500  # honest frame transactions an hour


def scenario(profile, users: int, extra: dict[str, int] | None = None) -> Simulation:
    accounts = {f"u{i}": 10**18 for i in range(users)}
    accounts["pm"] = 10**24
    accounts.update(extra or {})
    return Simulation(Scenario(
        seed=SEED,
        nodes=NODES,
        network=NetworkConfig(degree=8, latency=(0.02, 0.10), arrive_timeout=0.5),
        chain=ChainConfig(slot_time=SLOT, proposer="rotate", block_delay=(0.1, 1.0), min_tip=MIN_TIP),
        frame_pool=profile,
        genesis=Head(timestamp=0, gas_limit=GAS_LIMIT, gas_used=GAS_LIMIT // 2, base_fee=BASE_FEE),
        accounts=accounts,
        code={"pm": profile.canonical_paymaster_code, profile.expiry_verifier: profile.expiry_verifier_code},
    ))


def outcomes(rec, loads, window: tuple[float, float]) -> dict:
    """Per class, for the honest transactions first sent inside `window`."""
    out = {}
    lo, hi = window
    expired = {tx.hash for w in loads for tx in w.expired}
    answers = {h: a for w in loads for h, a in w.answers.items()}
    for cls in ("pays", "deadline"):
        txs = [tx for w in loads for tx in w.txs
               if (tx.hash in w.deadlines) == (cls == "deadline") and lo <= rec.txs[tx.hash].submitted_at < hi]
        landed = [rec.txs[tx.hash] for tx in txs if rec.txs[tx.hash].included_at is not None]
        delays = [r.included_at - r.submitted_at for r in landed]
        out[cls] = {
            "asked": len(txs),
            "landed": len(landed),
            "landed in window": sum(1 for r in landed if r.included_at < hi),
            "gave up": sum(1 for tx in txs if tx.hash in expired),
            "p50": percentile(delays, 50),
            "p90": percentile(delays, 90),
            "overflow": sum(answers[tx.hash].count("ErrTxPoolOverflow") for tx in txs) / max(1, len(txs)),
            "evicted": sum(rec.txs[tx.hash].dropped["capacity"] for tx in txs) / max(1, len(txs)),
        }
    return out


class Watch:
    """What a run's nodes admit that no block can include, and what the adversary's transactions paid."""

    def __init__(self, sim, adversary=None):
        self.admitted = Counter()  # admissions at any node, relayed ones included
        self.zombies = Counter()  # those of a transaction whose deadline is below the next block's timestamp
        self.expired_refusals = Counter()
        self.paid = 0
        self.included = Counter()
        self.adversary = adversary
        for node in sim.net.nodes.values():
            node.admit_hooks.append(self._admit)
        first = next(iter(sim.net.nodes.values()))
        first.import_hooks.append(self._block)

    def who(self, tx) -> str:
        return "adversary" if self.adversary and tx.label.startswith(self.adversary.name) else "honest"

    def _admit(self, node, tx, result) -> None:
        deadline = deadline_of(tx)
        if result == "ok":
            self.admitted[self.who(tx)] += 1
            if deadline is not None and deadline < SLOT * (math.floor(node.now / SLOT) + 1):
                self.zombies[self.who(tx)] += 1
        elif result == "ErrFrameExpired":
            self.expired_refusals[self.who(tx)] += 1

    def _block(self, node, block) -> None:
        theirs = [tx for tx in block.txs if self.who(tx) == "adversary"]
        self.included["adversary"] += len(theirs)
        self.paid += paid(theirs, block.head.base_fee)


def run_flood(profile, kind: str | None) -> dict:
    profile = profile.with_(max_pending=NET_PENDING)
    blocks = int(RUN // SLOT) + 2
    sponsors = {f"pm-{n}": 10**20 for n in range(blocks)} if kind == "drained" else {}
    sim = scenario(profile, users=4000, extra=sponsors)
    wallets = WalletLoad("w", rate=RATE / 3600, senders=[f"u{i}" for i in range(4000)], tip=uniform(*TIPS),
                         expiring=0.5, expiry=EXPIRY)
    sim.add_load(wallets)
    adversary = None
    if kind:
        adversary = FloodLoad("flood", kind=kind, k=NET_PENDING + SURPLUS, payer="pm", surplus=SURPLUS,
                              tip=JUNK_TIP, start=FLOOD[0], stop=FLOOD[1])
        sim.add_load(adversary)
    watch = Watch(sim, adversary)
    probe = {}
    sim.sched.at(FLOOD[1] - 1, lambda: probe.update(
        base_fee=sim.chain.head.next_base_fee(),
        reserved=max(adversary.reserved(n) for n in sim.net.nodes.values()) if adversary else 0))
    rec = sim.run(RUN)
    skipped = Counter()
    for b in rec.blocks:
        if FLOOD[0] < b["at"] <= FLOOD[1] + SLOT:
            skipped.update(b["failed"])
    return {"rec": rec, "wallets": wallets, "adversary": adversary, "watch": watch, "probe": probe,
            "skipped": skipped, "peak fee": max(b["base_fee"] for b in rec.blocks),
            "during": outcomes(rec, [wallets], FLOOD)}


def section_2() -> str:
    runs = [(EIP, None), (EIP, "expiring"), (NEXT, "expiring"), (TIP, "expiring"), (TIP_NEXT, "expiring"),
            (EIP, "drained"), (TIP_NEXT, "drained")]
    rows, cost = [], []
    for profile, kind in runs:
        r = run_flood(profile, kind)
        for cls in ("pays", "deadline"):
            o = r["during"][cls]
            rows.append([profile.name, kind or "none", cls, o["asked"], o["landed in window"], o["landed"],
                         o["gave up"], o["p50"], o["p90"], o["overflow"], o["evicted"]])
        if kind:
            a, w = r["adversary"], r["watch"]
            reason = r["skipped"].most_common(1)
            cost.append([profile.name, kind, a.sent, w.admitted["adversary"], w.zombies["adversary"],
                         w.included["adversary"], f"{reason[0][1]} {reason[0][0]}" if reason else "none", w.paid,
                         r["probe"]["reserved"], r["probe"]["base_fee"]])
    lines = [
        "## 2. A flood on the network",
        "",
        f"Wallets that pay for themselves send {RATE} frame transactions an hour to random nodes, half of them with "
        f"a deadline {EXPIRY} s after first sending; each has one in flight, sends it again to a random node after "
        "every block that leaves it out, and gives it up once its deadline has passed, as in experiment 04. Every "
        f"node's frame pool holds at most {NET_PENDING}. From minute 10 to minute 20 an adversary keeps every pool "
        f"full of its transactions, sent to each node directly at the start and after every block it imports: "
        f"enough to fill it and {SURPLUS} more, of the kinds of section 1, *expiring* or *drained*, made afresh "
        f"at every head. The run lasts {RUN / 60:.0f} minutes. Rows are the honest transactions first sent "
        "during the flood: landed in the flood is before minute 20, delays are of the landed ones in seconds from "
        "first sending, overflow is `ErrTxPoolOverflow` answers per transaction, and evicted is FP-14 evictions "
        "per transaction across nodes.",
        "",
        table(["profile", "flood", "class", "asked", "landed in the flood", "landed", "gave up", "delay p50",
               "p90", "overflow", "evicted"], rows),
        "",
        "What the flood cost: the transactions it sent to nodes directly; their admissions at any node, relayed "
        "ones included, and of those the admissions of a transaction whose deadline was below the next block's "
        "timestamp, so that no block could include it; how many of its transactions blocks included and the "
        "commonest reason builders skipped one; what the included ones paid, in wei; what its transactions "
        "reserved against their payers at the node that reserved most, a second before the flood ended; and the "
        "pending base fee then, in wei.",
        "",
        table(["profile", "flood", "sent", "admitted", "of them never includable", "included", "skipped",
               "paid, wei", "reserved, wei", "base fee, wei"], cost),
    ]
    return "\n".join(lines)


# --- 3. Honest deadlines ---------------------------------------------------------

BURST = (600.0, 1500.0)
BURST_RATE = 45_000  # an hour, as in experiment 04
BURST_USERS = 15_000
BURST_RUN = 3600.0


def run_burst(profile) -> dict:
    sim = scenario(profile, users=4000 + BURST_USERS)
    base = WalletLoad("w", rate=RATE / 3600, senders=[f"u{i}" for i in range(4000)], tip=uniform(*TIPS),
                      expiring=0.5, expiry=EXPIRY)
    burst = WalletLoad("b", rate=BURST_RATE / 3600, senders=[f"u{4000 + i}" for i in range(BURST_USERS)],
                       tip=uniform(*TIPS), expiring=0.5, expiry=EXPIRY, start=BURST[0], stop=BURST[1])
    sim.add_load(base)
    sim.add_load(burst)
    watch = Watch(sim)
    rec = sim.run(BURST_RUN)
    loads = [base, burst]
    expired = sum(len(w.expired) for w in loads)
    skipped = sum(b["failed"]["ErrFrameExpired"] for b in rec.blocks)
    return {"rec": rec, "loads": loads, "watch": watch, "expired": expired, "skipped": skipped,
            "landed": sum(1 for x in rec.txs.values() if x.included_at is not None),
            "evicted": sum(x.dropped["capacity"] for x in rec.txs.values()),
            "included": {h for h, x in rec.txs.items() if x.included_at is not None}}


def section_3() -> str:
    rows, included = [], {}
    for profile in (EIP, NEXT, TIP, TIP_NEXT):
        r = run_burst(profile)
        w = r["watch"]
        included[profile.name] = r["included"]
        rows.append([profile.name, len(r["rec"].txs), r["landed"], r["expired"], w.zombies["honest"],
                     w.zombies["honest"] / max(1, r["expired"]), r["skipped"], w.expired_refusals["honest"],
                     r["evicted"]])
    same = ["the same" if included[a.name] == included[b.name] else "different" for a, b in ((EIP, NEXT), (TIP, TIP_NEXT))]
    lines = [
        "## 3. Honest deadlines",
        "",
        f"The wallets of section 2, with no adversary and each node's frame pool at {EIP.max_pending}, and from "
        f"minute 10 to minute 25 {BURST_RATE} transactions an hour more from {BURST_USERS} other wallets of the "
        "same kind, the burst of experiment 04, so that thousands of transactions reach their deadline unincluded. "
        f"The run lasts {BURST_RUN / 60:.0f} minutes. Columns: the transactions sent and landed; given up, at "
        "their deadline; admissions of a transaction whose deadline was below the next block's timestamp, at any "
        "node, and the same per transaction given up; what builders skipped as `ErrFrameExpired`; what nodes "
        "refused as `ErrFrameExpired`; and FP-14 evictions.",
        "",
        table(["profile", "sent", "landed", "gave up", "admitted, never includable", "per one given up",
               "skipped by builders", "refused as expired", "evicted"], rows),
        "",
        f"With the EIP's order the two readings included {same[0]} transactions; with tip first, {same[1]}.",
    ]
    return "\n".join(lines)


def main() -> None:
    print("# 05. The expiry timestamp: results")
    print()
    print(f"Generated by `experiments/05-expiry-timestamp/run.py`, seed {SEED}, {SLOT} s slots, gas limit "
          f"{GAS_LIMIT}, {NODES} nodes in sections 2 and 3. Do not edit by hand.")
    print()
    print(section_1())
    print()
    print(section_2())
    print()
    print(section_3())


if __name__ == "__main__":
    main()
