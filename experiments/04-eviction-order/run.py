#!/usr/bin/env python3
"""Experiment 04: eviction order as an attack surface. Prints results.md on standard output.

When a pool is full, a newcomer takes a slot only by pushing a held
transaction out, and the pool's eviction order decides which. FP-14 follows
EIP-8141: the nearest expiry deadline first, then the lowest effective tip.
NP-9 follows go-ethereum: by price. This measures what transactions that no
builder will ever include can push out of each, at one pool and on a network,
and what a burst of honest demand pushes out, under the EIP's order and under
the `evict_first` `tip` variant of FP-14.
"""

from __future__ import annotations

import random
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "ref" / "python"), str(ROOT / "sim")]

from emem import EIP_8141, GETH, HEGOTA_TESTNET, Account, Head, State, Tx, TxPool  # noqa: E402
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
TIP_FIRST = EIP_8141.with_(name="eip-8141, tip first", evict_first="tip")
JUNK_TIP = 10_000_000_000  # an expiring transaction's tip: above every honest one


# --- 1. One pool -------------------------------------------------------------

def fee_cap(tip: int) -> int:
    return 2 * BASE_FEE + tip


def one_pool(kind: str, profile):
    """A pool filled to capacity with honest transactions, a third of each class (half for the nonce pool)."""
    rng = random.Random(f"{SEED}/one-pool")
    head = Head(timestamp=12_000, gas_limit=GAS_LIMIT, gas_used=GAS_LIMIT // 2, base_fee=BASE_FEE)
    capacity = GETH.global_slots + GETH.global_queue if kind == "nonce" else profile.max_pending
    classes = ["pays", "stranded"] if kind == "nonce" else ["pays", "deadline", "stranded"]
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
    state = State(accounts)
    pool = TxPool(head, state, GETH, profile)
    by_hash = {}
    for cls, sender, cap, tip in honest:
        if kind == "nonce":
            tx = Tx(sender, nonce=0, gas=21_000, max_fee=cap, tip=tip, label=sender)
        else:
            deadline = head.timestamp + EXPIRY if cls == "deadline" else None
            tx = backed_tx("self", sender, None, max_fee=cap, tip=tip, label=sender, exec_gas=50_000,
                           deadline=deadline, expiry_verifier=profile.expiry_verifier)
        assert pool.add([tx], 0) == ["ok"], cls
        by_hash[tx.hash] = cls
    return pool, head, by_hash, capacity


def junk_tx(kind: str, pool_kind: str, i: int, head: Head, profile):
    """The adversary's i-th transaction of a kind; none is ever included (see the README)."""
    if kind == "free":
        cap, tip, deadline = 1, 1, None
    elif kind == "sub-minimum":
        tip, deadline = MIN_TIP - 1, None
        cap = fee_cap(tip)
    else:  # expiring
        tip, deadline = JUNK_TIP, head.timestamp
        cap = fee_cap(tip)
    if pool_kind == "nonce":
        return Tx(f"j{i}", nonce=0, gas=21_000, max_fee=cap, tip=tip, label=f"j{i}")
    return backed_tx("paymaster", f"j{i}", "pm", max_fee=cap, tip=tip, label=f"j{i}", deadline=deadline,
                     expiry_verifier=profile.expiry_verifier)


def section_1() -> str:
    pools = [("account-nonce pool, `geth` (NP-9)", "nonce", EIP_8141),
             ("frame pool, `eip-8141` (FP-14, expiry first)", "frame", EIP_8141),
             ("frame pool, `eip-8141` with `evict_first` `tip`", "frame", TIP_FIRST)]
    rows = []
    for label, pool_kind, profile in pools:
        kinds = ["free", "sub-minimum"] + ([] if pool_kind == "nonce" else ["expiring"])
        for kind in kinds:
            pool, head, by_hash, capacity = one_pool(pool_kind, profile)
            before = Counter(by_hash.values())
            answers = Counter(pool.add([junk_tx(kind, pool_kind, i, head, profile)], 0)[0] for i in range(capacity))
            held = Counter(by_hash[h] for h in by_hash if pool.get(h) is not None)

            def out(cls):
                return before[cls] - held[cls] if cls in before else "n/a"

            refused = Counter({a: n for a, n in answers.items() if a != "ok"})
            rows.append([label, kind, capacity, answers["ok"], out("pays"), out("deadline"), out("stranded"),
                         refused.most_common(1)[0][0] if refused else "none"])
    lines = [
        "## 1. What one pool lets a never-included transaction push out",
        "",
        "A pool at the pending base fee of 1 gwei is filled to capacity with honest transactions from distinct "
        "senders, priced as wallets price, a tip of 0.001 to 3 gwei and a fee cap of twice the base fee plus the tip: "
        "*pays*, without a deadline; *deadline*, the same with an expiry frame 600 s out (frame pool only); and "
        "*stranded*, a fee cap between half the base fee and just below it, as a backlog is after the base fee "
        "rises. They are in equal shares, a third each in the frame pool and half each in the account-nonce pool. "
        "Then as many again of the adversary's transactions arrive, one at a time, each from a sender of its own: "
        f"*free*, a fee cap and tip of 1 wei; *sub-minimum*, a tip of {MIN_TIP - 1} wei, one below the builders' "
        "minimum, and a fee cap of twice the base fee plus the tip; *expiring*, a deadline at the head's timestamp "
        "and a tip of 10 gwei, so that it is valid now and cannot be in the next block. No builder includes any of "
        "them. Out is how many of each honest class are no longer held; the last column is the commonest answer to "
        "the adversary's transactions that were refused.",
        "",
        table(["pool", "adversary", "capacity", "admitted", "out: pays", "out: deadline", "out: stranded",
               "refused as"], rows),
    ]
    return "\n".join(lines)


# --- 2 and 3. A network ------------------------------------------------------

def scenario(profile, users: int, nodes: int = NODES) -> Simulation:
    accounts = {f"u{i}": 10**18 for i in range(users)}
    accounts["pm"] = 10**24
    return Simulation(Scenario(
        seed=SEED,
        nodes=nodes,
        network=NetworkConfig(degree=8, latency=(0.02, 0.10), arrive_timeout=0.5),
        chain=ChainConfig(slot_time=SLOT, proposer="rotate", block_delay=(0.1, 1.0), min_tip=MIN_TIP),
        frame_pool=profile,
        genesis=Head(timestamp=0, gas_limit=GAS_LIMIT, gas_used=GAS_LIMIT // 2, base_fee=BASE_FEE),
        accounts=accounts,
        code={"pm": profile.canonical_paymaster_code, profile.expiry_verifier: profile.expiry_verifier_code},
    ))


def outcomes(sim, rec, loads, window: tuple[float, float]) -> dict:
    """Per class, for the honest transactions first sent inside `window`."""
    out = {}
    lo, hi = window
    for cls in ("pays", "deadline"):
        txs = [tx for w in loads for tx in w.txs
               if (tx.hash in w.deadlines) == (cls == "deadline") and lo <= rec.txs[tx.hash].submitted_at < hi]
        expired = {tx.hash for w in loads for tx in w.expired}
        answers = {h: a for w in loads for h, a in w.answers.items()}
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


FLOOD = (600.0, 1800.0)
FLOOD_HOURS = 1.0
RATE = 1500  # an hour


def run_flood(profile, flood: bool) -> dict:
    sim = scenario(profile, users=4000)
    wallets = WalletLoad("w", rate=RATE / 3600, senders=[f"u{i}" for i in range(4000)], tip=uniform(*TIPS),
                         expiring=0.5, expiry=EXPIRY)
    sim.add_load(wallets)
    adversary = None
    if flood:
        adversary = FloodLoad("flood", kind="free", k=profile.max_pending + SURPLUS, payer="pm", surplus=SURPLUS,
                              start=FLOOD[0], stop=FLOOD[1])
        sim.add_load(adversary)
    peak = {}
    sim.sched.at(FLOOD[1] - 1, lambda: peak.update(
        held=[sum(1 for e in n.pool.frame.entries.values() if e.tx.label.startswith("flood"))
              for n in sim.net.nodes.values()],
        reserved=[adversary.reserved(n) if adversary else 0 for n in sim.net.nodes.values()]))
    rec = sim.run(FLOOD_HOURS * 3600)
    included = sum(1 for s in adversary.senders if sim.chain.state.nonce(s) > 0) if adversary else 0
    peak["end"] = [sum(1 for e in n.pool.frame.entries.values() if e.tx.label.startswith("flood"))
                   for n in sim.net.nodes.values()]
    return {"sim": sim, "rec": rec, "wallets": wallets, "adversary": adversary, "peak": peak, "included": included,
            "during": outcomes(sim, rec, [wallets], FLOOD),
            "outside": outcomes(sim, rec, [wallets], (0, FLOOD[0]))}


def capacity() -> list[list]:
    """Gas of an honest transaction with and without a deadline, and what an hour of blocks holds and targets."""
    rows = []
    for cls, deadline in (("pays", None), ("deadline", EXPIRY)):
        tx = backed_tx("self", "u", None, max_fee=BASE_FEE, tip=1, label=cls, exec_gas=50_000, deadline=deadline)
        per_hour = 3600 / SLOT
        rows.append([cls, tx.used, GAS_LIMIT // tx.used * per_hour, GAS_LIMIT / 2 / tx.used * per_hour])
    return rows


def section_2() -> str:
    runs = [("eip-8141", EIP_8141, False), ("eip-8141", EIP_8141, True), ("hegota-testnet", HEGOTA_TESTNET, True),
            ("eip-8141, tip first", TIP_FIRST, True)]
    rows, cost = [], []
    for label, profile, flood in runs:
        r = run_flood(profile, flood)
        for cls in ("pays", "deadline"):
            o = r["during"][cls]
            rows.append([label, "free" if flood else "none", cls, o["asked"], o["landed in window"], o["landed"],
                         o["gave up"], o["p50"], o["p90"], o["overflow"], o["evicted"]])
        if flood:
            a, peak = r["adversary"], r["peak"]
            cost.append([label, a.k, a.sent, a.admitted, sum(peak["held"]) / len(peak["held"]),
                         sum(peak["end"]) / len(peak["end"]), max(peak["reserved"]),
                         max(peak["reserved"]) * BASE_FEE, r["included"]])
    lines = [
        "## 2. A flood on the network",
        "",
        f"Wallets that pay for themselves send {RATE} frame transactions an hour to random nodes, half of them with "
        f"a deadline {EXPIRY} s after first sending; each wallet has one in flight, sends it again to a random node "
        "after every block that leaves it out, and gives it up once its deadline has passed. From minute 10 to "
        "minute 30 an adversary keeps every node's frame pool full of *free* transactions, sent to each node "
        f"directly at the start and after every block it imports: enough to fill it and {SURPLUS} more. Rows are the "
        "transactions first sent during the flood. Landed in the flood is before minute 30; delays are of the "
        "landed ones, in seconds from first sending; overflow is `ErrTxPoolOverflow` answers per transaction, and "
        "evicted is FP-14 evictions per transaction across nodes. What a transaction costs in gas, and so what "
        "blocks hold and the base fee targets:",
        "",
        table(["class", "transaction gas", "capacity, an hour", "target, an hour"], capacity()),
        "",
        table(["profile", "flood", "class", "asked", "landed in the flood", "landed", "gave up", "delay p50",
               "p90", "overflow", "evicted"], rows),
        "",
        "What the flood cost: its transactions, what it sent over the twenty minutes, what nodes admitted, what "
        "each node held of it a second before it ended and when the run ended, half an hour later, what they "
        "reserved against the paymaster at the node that reserved most, in wei, and what the same transactions "
        "would reserve at a fee cap of 1 gwei, and how many were included, which is what it paid gas for.",
        "",
        table(["profile", "transactions", "sent", "admitted", "held per node", "held at the end",
               "reserved, wei", "at 1 gwei", "included"], cost),
    ]
    return "\n".join(lines)


BURST = (600.0, 1500.0)
BURST_RATE = 45_000  # an hour
BURST_USERS = 15_000
BURST_HOURS = 1.0


def run_burst(profile) -> dict:
    sim = scenario(profile, users=4000 + BURST_USERS)
    base = WalletLoad("w", rate=RATE / 3600, senders=[f"u{i}" for i in range(4000)], tip=uniform(*TIPS),
                      expiring=0.5, expiry=EXPIRY)
    burst = WalletLoad("b", rate=BURST_RATE / 3600, senders=[f"u{4000 + i}" for i in range(BURST_USERS)],
                       tip=uniform(*TIPS), expiring=0.5, expiry=EXPIRY, start=BURST[0], stop=BURST[1])
    sim.add_load(base)
    sim.add_load(burst)
    held = []
    sim.sched.every(SLOT, lambda: held.append(max(len(n.pool.frame.entries) for n in sim.net.nodes.values())))
    rec = sim.run(BURST_HOURS * 3600)
    return {"sim": sim, "rec": rec, "loads": [base, burst], "held": held,
            "during": outcomes(sim, rec, [base, burst], BURST)}


def section_3() -> str:
    rows, evicted, included = [], [], []
    for label, profile in [("eip-8141", EIP_8141), ("eip-8141, tip first", TIP_FIRST)]:
        r = run_burst(profile)
        most = max(r["held"])
        for cls in ("pays", "deadline"):
            o = r["during"][cls]
            rows.append([label, cls, o["asked"], o["landed in window"], o["landed"], o["gave up"], o["p50"],
                         o["p90"], o["overflow"], o["evicted"], most])
        rec = r["rec"]
        deadlines = {h for w in r["loads"] for h in w.deadlines}
        out = [x for x in rec.txs.values() if x.dropped["capacity"]]
        tips = [x.tx.tip for x in out]
        evicted.append([label, len(out), sum(1 for x in out if x.tx.hash in deadlines),
                        percentile(tips, 50) / 1e9 if tips else None, max(tips) / 1e9 if tips else None,
                        sum(1 for x in out if x.included_at is not None)])
        included.append({h for h, x in rec.txs.items() if x.included_at is not None})
    same = "the same" if included[0] == included[1] else "different"
    lines = [
        "## 3. An honest burst",
        "",
        f"The wallets of section 2, with no adversary, and from minute 10 to minute 25 {BURST_RATE} transactions an "
        f"hour more from {BURST_USERS} other wallets of the same kind, "
        f"{(RATE + BURST_RATE) / capacity()[0][2]:.2f} times what blocks hold without deadlines, so that the "
        "backlog fills every node's frame pool. Rows are the transactions first sent during the burst; columns "
        "as in section 2, and most held is the largest pool on any node at any block.",
        "",
        table(["profile", "class", "asked", "landed in the burst", "landed", "gave up", "delay p50", "p90",
               "overflow", "evicted", "most held"], rows),
        "",
        "What each order evicted, over the run: the transactions evicted at least once anywhere, how many of them "
        "carried a deadline, their median and highest tip in gwei, and how many of them were included later. The "
        f"two runs included {same} transactions ({len(included[0])} and {len(included[1])}).",
        "",
        table(["profile", "evicted", "with a deadline", "tip p50, gwei", "highest tip, gwei", "included later"],
              evicted),
    ]
    return "\n".join(lines)


def main() -> None:
    print("# 04. Eviction order: results")
    print()
    print(f"Generated by `experiments/04-eviction-order/run.py`, seed {SEED}, {SLOT} s slots, gas limit {GAS_LIMIT}, "
          f"{NODES} nodes in sections 2 and 3. Do not edit by hand.")
    print()
    print(section_1())
    print()
    print(section_2())
    print()
    print(section_3())


if __name__ == "__main__":
    main()
