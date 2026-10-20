#!/usr/bin/env python3
"""Experiment 23: a threshold committee as LUCID's key publisher (EIP-8184). Prints results.md on standard output.

Experiment 18's payments, with a committee of n members and threshold t as
their key publisher: a key is in time in a slot when at least t members'
shares are. This measures the payments against the members that withhold and
those late in a slot, with senders that seal again or go public, against a
baseline whose keys fail one at a time at the same rate, and with senders that
release their own key; the shares a slot carries; a rotation of the committee
with sealed transactions in flight; and builders that leave the committee's
sealed transactions out. Decision record 0032.
"""

from __future__ import annotations

import random
import sys
from dataclasses import dataclass
from fractions import Fraction
from math import comb, log2
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "ref" / "python"), str(ROOT / "sim")]

from emem import EIP_8184, Head  # noqa: E402
from emem.sealed import fees  # noqa: E402
from emem_sim import (ChainConfig, KeyCommittee, NetworkConfig, Scenario, SealedLoad, Simulation,  # noqa: E402
                      TransferLoad, percentile, run_all, table, uniform)

SEED = 1
NODES = 10
DEGREE = 8
SLOT = 12
GAS_LIMIT = 60_000_000  # a ToB segment of 7,500,000 (LU-1)
BASE_FEE = 1_000_000_000
MIN_TIP = 1_000_000  # BB-1, go-ethereum's miner default
RUN = 1200.0
WINDOW = (240.0, 960.0)  # payments that are measured
PAY_GAS, PAY_SIZE = 100_000, 512
TRADE_GAS, TRADE_RATE = 300_000, 2  # a slot
TRADE_TOB = (10**12, 10**15)  # wei, uniformly
TRADE_PRECEDING = (1, 8)
BACKGROUND_GAS = 1_000_000
RATES = (16, 28)  # payments a slot
NAME = "committee"
T3, T4 = 3.0, 9.0  # seconds into the slot: ATTESTATION_DUE_BPS_GLOAS and PAYLOAD_ATTESTATION_DUE_BPS of 12 s
COMMITTEES = ((16, 11), (16, 9), (64, 43), (64, 33), (423, 212))  # (n, t): two thirds and a majority
CORRUPT = Fraction(1, 3)  # the share of validators corrupt, and of members that withhold in the rows that have any
LATE = (0.1, 0.2, 0.3)  # the chance each other member misses a slot
PUBLIC = (64, 43)  # the committee whose senders also go public
PARTIAL = (0.05, 0.95)  # a row whose key is in time with a chance in this range is run against its baseline
ONLINE = 0.5
SHARE_BYTES = 32  # ASSUMPTION: one element of a 256-bit group, without its proof
EPOCH = 32  # SLOTS_PER_EPOCH
SERVING = (0, 1, 2, 4)  # slots the old committee keeps serving after a rotation
BUILDERS = 10
FILTERING = (0, 1, 3, 5)  # of the BUILDERS
FILTERED_SHARE = 0.5  # of payments that name the committee, in the filtering runs


@dataclass(frozen=True)
class Run:
    rate: int
    n: int = 64
    t: int = 43
    withholding: int = 0
    late: float = 0.0
    response: str = "sealed"
    per: str = "slot"
    online: float = 0.0
    handover: str = "reshare"
    serving: int = 0
    rotation: str = "keep"
    epoch: int = 0
    filtering: int = 0
    share: float = 1.0  # of payments that name the committee


def third(n: int) -> int:
    return int(n * CORRUPT)


def in_time(r: Run) -> float:
    """The chance a slot's key is in time: at least t of the n - w members that may send are, each with 1 - q."""
    m, p = r.n - r.withholding, 1 - r.late
    return sum(comb(m, k) * p**k * (1 - p) ** (m - k) for k in range(r.t, m + 1))


def no_majority(n: int) -> Fraction:
    """The chance a committee of n drawn from validators of which CORRUPT are corrupt has no honest majority."""
    return sum(comb(n, k) * CORRUPT**k * (1 - CORRUPT) ** (n - k) for k in range((n + 1) // 2, n + 1))


def smallest(bits: int) -> int:
    n = 1
    while no_majority(n) >= Fraction(1, 2**bits):
        n += 1
    return n


def simulate(r: Run) -> dict:
    cfg = EIP_8184.with_(policy="any")
    pays = [f"p{i}" for i in range(4000)]
    trades = [f"t{i}" for i in range(400)]
    background = [f"b{i}" for i in range(600)]
    accounts = {a: 10**20 for a in pays + trades + background}
    names = [f"n{i:02d}" for i in range(NODES)]
    filtering = frozenset(random.Random(f"{SEED}/filtering").sample(names, r.filtering))
    leave_out = {"censored": lambda tx: getattr(tx, "key_publisher", None) == NAME,
                 "filtering": filtering} if filtering else {}
    sim = Simulation(Scenario(
        seed=SEED,
        nodes=NODES,
        network=NetworkConfig(degree=DEGREE, latency=(0.02, 0.10), arrive_timeout=0.5),
        chain=ChainConfig(slot_time=SLOT, proposer="rotate", block_delay=(0.1, 1.0), min_tip=MIN_TIP, **leave_out),
        sealed_pool=cfg,
        genesis=Head(timestamp=0, gas_limit=GAS_LIMIT, gas_used=GAS_LIMIT // 2, base_fee=BASE_FEE),
        accounts=accounts,
    ))
    committee = KeyCommittee(NAME, members=r.n, threshold=r.t, withholding=r.withholding, late=r.late,
                             online=r.online, per=r.per, epoch=r.epoch, handover=r.handover, serving=r.serving,
                             deadline=T4)
    sealed_gas = r.rate * PAY_GAS + TRADE_RATE * TRADE_GAS
    sim.add_load(TransferLoad("bg", rate=(GAS_LIMIT // 2 - sealed_gas) / BACKGROUND_GAS / SLOT, senders=background,
                              gas=BACKGROUND_GAS))
    payments = SealedLoad("pay", rate=r.rate / SLOT, senders=pays, gas=PAY_GAS, size=PAY_SIZE, stop=WINDOW[1],
                          committee=committee, committee_share=r.share, response=r.response, rotation=r.rotation)
    sim.add_load(payments)
    sim.add_load(SealedLoad("trade", rate=TRADE_RATE / SLOT, senders=trades, tob=uniform(*TRADE_TOB),
                            preceding=uniform(*TRADE_PRECEDING), gas=TRADE_GAS, size=PAY_SIZE, stop=WINDOW[1]))
    rec = sim.run(RUN)
    return measure(rec, payments, committee)


def measure(rec, payments: SealedLoad, committee: KeyCommittee) -> dict:
    at = {b["number"]: b["at"] for b in rec.blocks}
    base = {b["number"]: b["base_fee"] for b in rec.blocks}
    groups: dict[str, dict] = {}
    for versions in payments.sent:
        first = rec.txs[versions[0].hash]
        if not WINDOW[0] <= first.submitted_at < WINDOW[1]:
            continue
        g = groups.setdefault(versions[0].key_publisher, {"sent": 0, "delays": [], "attempts": 0, "lost": [],
                                                          "sealed": 0, "public": 0, "gone": 0})
        g["sent"] += 1
        done, paid_for = None, 0
        for v in dict.fromkeys(versions):  # a version once, though it was sent several times
            t = rec.txs[v.hash]
            if t.block is None:
                continue
            g["attempts"] += 1
            outcome = committee.outcome.get(v.hash, "released") if v.key_publisher == NAME else "released"
            if outcome in committee.RELEASED:
                done = at.get(t.block + 1)  # LU-13: it runs in the next block
                g["sealed"] += done is not None
            else:
                paid_for += fees(v, base[t.block]).ticket_fee
                g["gone"] += outcome == "gone"
        tx = payments.public.get(versions[0].hash)
        if tx is not None and rec.txs[tx.hash].included_at is not None:
            done = rec.txs[tx.hash].included_at
            g["public"] += 1
        g["lost"].append(paid_for)
        if done is not None:
            g["delays"].append(done - first.submitted_at)
    blocks = [b for b in rec.blocks if WINDOW[0] < b["at"] <= WINDOW[1]]
    commits = [c.tx for b in blocks for c in b["commitments"]]
    mine = [st for st in commits if st.key_publisher == NAME]
    slots = [committee.slots[b["number"]] for b in blocks]
    used = [s for s in slots if s["commitments"]]
    out = {"commitments": len(commits) / max(1, len(blocks)),
           "withheld": sum(1 for st in commits if committee.outcome.get(st.hash) not in (None, *committee.RELEASED))
           / max(1, len(blocks)),
           "released": sum(1 for st in mine if committee.outcome[st.hash] == "released") / max(1, len(mine)),
           "mine": [s["commitments"] for s in slots], "shares": [s["shares"] for s in slots],
           "batched": [s["batched"] for s in slots], "used": len(used), "blocks": len(blocks)}
    for name, g in groups.items():
        d, n = g["delays"], max(1, g["sent"])
        out[name] = {"sent": g["sent"], "executed": len(d), "sealed": g["sealed"], "public": g["public"],
                     "p50": percentile(d, 50), "p90": percentile(d, 90), "p99": percentile(d, 99),
                     "max": max(d, default=None), "attempts": g["attempts"] / n, "lost": sum(g["lost"]) / n,
                     "lost max": max(g["lost"], default=0), "gone": g["gone"]}
    return out


def members(withholding: bool) -> list[Run]:
    return [Run(rate, n, t, third(n) if withholding else 0, q) for rate in RATES for n, t in COMMITTEES
            for q in LATE]


def section_1_runs() -> list[Run]:
    return [Run(rate) for rate in RATES] + members(False) + members(True)


def public_runs() -> list[Run]:
    return [Run(r.rate, r.n, r.t, r.withholding, r.late, "public") for r in section_1_runs()[len(RATES):]
            if (r.n, r.t) == PUBLIC]


def partial() -> list[Run]:
    return [r for r in section_1_runs()[len(RATES):] if PARTIAL[0] <= in_time(r) <= PARTIAL[1]]


def baseline_runs() -> list[Run]:
    return [Run(r.rate, r.n, r.t, r.withholding, r.late, per="commitment") for r in partial()]


def online_runs() -> list[Run]:
    return [Run(r.rate, r.n, r.t, r.withholding, r.late, online=ONLINE) for r in partial()]


def handover_runs() -> list[Run]:
    rs = []
    for rate in RATES:
        rs.append(Run(rate, epoch=EPOCH))
        rs += [Run(rate, epoch=EPOCH, handover="rotate", serving=g, rotation=k) for g in SERVING
               for k in ("keep", "reseal")]
    return rs


def filtering_runs() -> list[Run]:
    return [Run(rate, filtering=f, share=FILTERED_SHARE) for rate in RATES for f in FILTERING]


def runs() -> list[Run]:
    rs = (section_1_runs() + public_runs() + baseline_runs() + online_runs() + handover_runs()
          + filtering_runs())
    return list(dict.fromkeys(rs))


def committee_name(r: Run) -> str:
    return f"{r.t} of {r.n}"


def fixed(x, places=2) -> str:
    return f"{x:.{places}f}"


def payment_cells(o: dict) -> list:
    return [o["sent"], o["executed"], o["sealed"], o["public"], o["p50"], o["p90"], o["p99"], o["max"],
            o["attempts"], o["lost"], o["lost max"]]


PAYMENT_HEADER = ["sent", "executed", "sealed", "public", "delay p50", "p90", "p99", "max", "attempts", "lost, wei",
                  "lost max, wei"]


def section_0() -> str:
    n40, il = smallest(40), 16
    return "\n".join([
        "## 0. Committee sizes",
        "",
        f"A committee of $n$ drawn from validators of which {CORRUPT} are corrupt has no honest majority when at "
        "least half its members are corrupt; the chance, from the binomial distribution, exactly:",
        "",
        table(["n", "chance of no honest majority", "log2"],
              [[n, f"{float(no_majority(n)):.3e}", fixed(log2(no_majority(n)))] for n in (il, 64, n40)]),
        "",
        f"The smallest $n$ whose chance is below $2^{{-40}}$ is {n40}. 16 is EIP-7805's `IL_COMMITTEE_SIZE`.",
    ])


def section_1(out: dict) -> str:
    rows = []
    for r in section_1_runs():
        o = out[r]
        rows.append([r.rate, committee_name(r), r.withholding, r.late, fixed(in_time(r), 4), fixed(o["released"], 4)]
                    + payment_cells(o[NAME]) + [o["commitments"], o["withheld"]])
    return "\n".join([
        "## 1. Payments against members that withhold or are late",
        "",
        f"Experiment 18's network: {NODES} nodes, {DEGREE} peers each, a block every {SLOT} s from a rotating "
        f"proposer, gas limit {GAS_LIMIT}, every pool at the profile's {EIP_8184.st_slots} slots under `any`. "
        f"Payments arrive at the rate in the table, each from a sender of its own with one in flight, bidding no "
        f"ToB fee, tolerating 31 commitments before them, {PAY_GAS} gas, sent to random nodes until second "
        f"{WINDOW[1]:.0f} and again after every block that does not commit them; trades arrive at {TRADE_RATE} a "
        f"slot, naming a publisher that releases every key, and transfers of {BACKGROUND_GAS} gas fill the rest of "
        "the gas target. Every payment names the committee in the table, $t$ of $n$: of its members, the number "
        "in the table withhold every share, and each other member misses each slot with the chance in the table. "
        "A key is in time in a slot when at least $t$ shares are, one draw a slot for all the committee's "
        f"commitments in it. A sender that has seen no key {T4:.0f} s after the block that committed its payment "
        "sends it again, sealed to the committee at its next nonce, to the node it sent it to. The first two rows "
        "are the committee of 64 with nothing withheld. P(key) is the chance a slot's key is in time, exactly; "
        "released is the share of the committee's commitments in the window whose key it released. Rows are the "
        f"payments first sent from second {WINDOW[0]:.0f} to second {WINDOW[1]:.0f}; the run lasts {RUN:.0f} s. "
        "Executed is by the end of the run; delays are from first sending to the block that runs the payment, in "
        "seconds. Attempts is the mean number of the payment's tickets committed; lost is the mean, and the "
        "largest, wei a payment paid for tickets whose key was withheld; commitments and withheld are the mean a "
        "block made, and of them the withheld, during the window.",
        "",
        table(["a slot", "committee", "withholding", "late", "P(key)", "released"] + PAYMENT_HEADER
              + ["commitments", "withheld"], rows),
    ])


def section_2(out: dict) -> str:
    rows = []
    for r in public_runs():
        o = out[r]
        rows.append([r.rate, committee_name(r), r.withholding, r.late, fixed(in_time(r), 4)]
                    + payment_cells(o[NAME]) + [o["commitments"], o["withheld"]])
    return "\n".join([
        "## 2. Senders that go public",
        "",
        f"Section 1's rows for the committee of {PUBLIC[1]} of {PUBLIC[0]}, with every sender whose key is "
        "withheld sending the payment again as a regular transaction with the same gas and tip, at its next "
        "nonce, to the node it sent it to, and again after every block that does not include it.",
        "",
        table(["a slot", "committee", "withholding", "late", "P(key)"] + PAYMENT_HEADER
              + ["commitments", "withheld"], rows),
    ])


def section_3(out: dict) -> str:
    rows = []
    for r in partial():
        for label, run in (("slot", r), ("commitment", Run(r.rate, r.n, r.t, r.withholding, r.late,
                                                             per="commitment")),
                           (f"slot, {ONLINE} online", Run(r.rate, r.n, r.t, r.withholding, r.late, online=ONLINE))):
            o = out[run]
            rows.append([r.rate, committee_name(r), r.withholding, r.late, fixed(in_time(r), 4), label,
                         fixed(o["released"], 4)] + payment_cells(o[NAME]) + [o["commitments"], o["withheld"]])
    return "\n".join([
        "## 3. Keys that fail together, keys that fail alone, and senders that release their own",
        "",
        f"Section 1's rows whose P(key) is between {PARTIAL[0]} and {PARTIAL[1]}, each three ways: as in "
        "section 1, one draw of the members a slot (`slot`); with the members drawn afresh for each commitment, "
        "so that each key is in time with the same chance and alone (`commitment`); and one draw a slot with "
        f"each commitment's sender online with chance {ONLINE}, drawn per commitment, releasing its own key when "
        "the committee does not.",
        "",
        table(["a slot", "committee", "withholding", "late", "P(key)", "draw", "released"] + PAYMENT_HEADER
              + ["commitments", "withheld"], rows),
    ])


def section_4(out: dict) -> str:
    rows = []
    for rate in RATES:
        for n, t in COMMITTEES:
            o = out[Run(rate, n, t, 0, LATE[0])]
            mine, shares, batched = o["mine"], o["shares"], o["batched"]
            rows.append([rate, f"{t} of {n}", sum(mine) / len(mine), max(mine), sum(shares) / len(shares),
                         max(shares), sum(batched) / len(batched), SHARE_BYTES * sum(shares) / len(shares),
                         SHARE_BYTES * max(shares), PAY_SIZE * sum(mine) / len(mine)])
    return "\n".join([
        "## 4. Shares a slot",
        "",
        f"Section 1's rows with no member withholding and each late with chance {LATE[0]}, over the blocks of "
        "the window. Each member in time sends one share for each of its committee's commitments in the block "
        "(each), or one for the block as batched threshold encryption would (batched). Bytes are at "
        f"{SHARE_BYTES} bytes a share, an ASSUMPTION (decision record 0032); sealed bytes are the committee's "
        f"sealed transactions committed in the block, at {PAY_SIZE} bytes each.",
        "",
        table(["a slot", "committee", "commitments, mean", "max", "shares each, mean", "max", "batched, mean",
               "bytes each, mean", "max", "sealed bytes, mean"], rows),
    ])


def section_5(out: dict) -> str:
    rows = []
    for r in handover_runs():
        o = out[r]
        rows.append([r.rate, r.handover, r.serving if r.handover == "rotate" else "",
                     r.rotation if r.handover == "rotate" else "", o[NAME]["gone"]] + payment_cells(o[NAME])
                    + [o["commitments"], o["withheld"]])
    return "\n".join([
        "## 5. A rotation with sealed transactions in flight",
        "",
        f"Section 1's network with the committee of {PUBLIC[1]} of {PUBLIC[0]}, no member withholding or late, "
        f"changed every {EPOCH} slots, at slots {EPOCH}, {2 * EPOCH} and {3 * EPOCH}. Under `reshare` the public "
        "key is kept. Under `rotate` each epoch's committee has a key of its own, a sender seals to the key of "
        "the epoch of the next slot, and the old committee releases keys sealed to it for the first slots of the "
        "next epoch in the table, after which they are gone. A sender `keep`s a pending sealed transaction, or "
        "`reseal`s it to the new key at fees raised by 10% (LU-9) once its node imports the last block of an "
        "epoch. Gone is the number of the payments' commitments whose key no committee held.",
        "",
        table(["a slot", "handover", "serving", "sender", "gone"] + PAYMENT_HEADER + ["commitments", "withheld"],
              rows),
    ])


def section_6(out: dict) -> str:
    rows = []
    for r in filtering_runs():
        o = out[r]
        c, k = o[NAME], o["kp"]
        rows.append([r.rate, f"{r.filtering} of {BUILDERS}", c["sent"], c["executed"], c["p50"], c["p90"],
                     c["p99"], c["max"], k["sent"], k["executed"], k["p50"], k["p99"], o["commitments"]])
    return "\n".join([
        "## 6. Builders that leave the committee out",
        "",
        f"Section 1's network with the committee of {PUBLIC[1]} of {PUBLIC[0]}, no member withholding or late. "
        f"Each payment names the committee with chance {FILTERED_SHARE} and otherwise a publisher that releases "
        "every key. The builders in the table, drawn once from a stream of their own, commit none of the sealed "
        "transactions that name the committee; there are no inclusion lists. Delays are in seconds, for the "
        "payments that name the committee and for the others.",
        "",
        table(["a slot", "filtering", "committee's sent", "executed", "delay p50", "p90", "p99", "max",
               "others' sent", "executed", "delay p50", "p99", "commitments"], rows),
    ])


def main() -> None:
    rs = runs()
    out = dict(zip(rs, run_all(simulate, rs)))
    print("# 23. A committee's keys: results")
    print()
    print(f"Generated by `experiments/23-committee-keys/run.py`, seed {SEED}, {NODES} nodes, {DEGREE} peers each, "
          f"{SLOT} s slots, gas limit {GAS_LIMIT}, {RUN:.0f} s a run, sealed pool profile `eip-8184` under `any`, "
          f"a sender learning of a withheld key {T4:.0f} s after the block that committed it. Do not edit by hand.")
    for section in (section_0(), section_1(out), section_2(out), section_3(out), section_4(out), section_5(out),
                    section_6(out)):
        print()
        print(section)


if __name__ == "__main__":
    main()
