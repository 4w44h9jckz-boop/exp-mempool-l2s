#!/usr/bin/env python3
"""Experiment 03: what one block can make every node re-simulate. Prints results.md on standard output.

FP-15 re-simulates every pending frame transaction whose recorded dependencies
a block changed, and the payer's balance is one of them (FP-10). This counts,
per node and per block, how many prefixes are re-run and how much code they
run, when many pending transactions share one payer: an adversary's, moved by
a one-wei transfer every block, and an honest paymaster's, moved by its own
users' inclusions. Under `eip-8141`, `hegota-testnet`, and each with the
`reuse_balance` variant of FP-15.
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "ref" / "python"), str(ROOT / "sim")]

from emem import EIP_8141, HEGOTA_TESTNET, Head  # noqa: E402
from emem.framepool.prefix import analyse  # noqa: E402
from emem_sim import (ChainConfig, FanOutLoad, NetworkConfig, Scenario, Simulation, SponsoredLoad,  # noqa: E402
                      percentile, table)

SEED = 1
NODES = 20  # section 3
FAN_NODES = 10  # sections 1 and 2: every node holds and re-runs the same transactions, so fewer suffice
FAN = 1024  # section 1's transactions; section 2 goes to max_pending
SLOT = 12
GAS_LIMIT = 2_100_000
BASE_FEE = 1_000_000_000
TOUCH = 21_000
VERIFY_GAS = 80_000  # an adversary's sender code: within MAX_VERIFY_GAS with both signatures and the pay frame
PROFILES = [EIP_8141, HEGOTA_TESTNET,
            EIP_8141.with_(name="eip-8141, reuse", reuse_balance=True),
            HEGOTA_TESTNET.with_(name="hegota-testnet, reuse", reuse_balance=True)]
PAYER_CODE = {"sponsor": "", "paymaster": "canonical-paymaster", "noncanonical": "paymaster",
              "shared-sender": "account"}
STRUCTURES = [  # (label, shape, sender code gas)
    ("sponsor, default-code senders", "sponsor", 0),
    ("sponsor, senders with code", "sponsor", VERIFY_GAS),
    ("canonical paymaster, senders with code", "paymaster", VERIFY_GAS),
    ("non-canonical paymaster, senders with code", "noncanonical", VERIFY_GAS),
    ("shared sender, disjoint keys", "shared-sender", VERIFY_GAS),
]


def scenario(profile, accounts: dict, code: dict, nodes: int = NODES) -> Simulation:
    return Simulation(Scenario(
        seed=SEED,
        nodes=nodes,
        network=NetworkConfig(degree=8, latency=(0.02, 0.10), arrive_timeout=0.5),
        chain=ChainConfig(slot_time=SLOT, proposer="rotate", block_delay=(0.1, 1.0)),
        frame_pool=profile,
        genesis=Head(timestamp=0, gas_limit=GAS_LIMIT, gas_used=GAS_LIMIT // 2, base_fee=BASE_FEE),
        accounts=accounts,
        code={a: c for a, c in code.items() if c},
    ))


def code_gas(tx, state, cfg) -> int:
    """Gas of the prefix frames a node must execute: those whose target holds code the protocol does not define."""
    prefix = analyse(tx, cfg)
    total = 0
    for f in tx.frames[:prefix.length]:
        code = state.code(f.target if f.target is not None else tx.sender)
        if code and code not in (cfg.expiry_verifier_code, cfg.canonical_paymaster_code):
            total += f.exec_gas
    return total


def watch(sim) -> dict:
    """Per node and block: how many prefixes the import re-ran, and their code gas."""
    seen = {"blocks": []}

    def hook(node, block):
        f = node.pool.frame
        seen["blocks"].append((node.name, block, len(f.resimulated),
                               sum(code_gas(tx, f.state, f.config) for tx in f.resimulated)))

    for node in sim.net.nodes.values():
        node.import_hooks.append(hook)
    return seen


_fan: dict = {}


def fan_out(profile, shape: str, verify_gas: int, k: int) -> dict:
    """Once for each profile, shape and size."""
    key = (profile.name, shape, verify_gas, k)
    if key not in _fan:
        _fan[key] = run_fan_out(profile, shape, verify_gas, k)
    return _fan[key]


def run_fan_out(profile, shape: str, verify_gas: int, k: int, touches: int = 5) -> dict:
    """An adversary's `k` transactions on one payer, sent to every node at 30 s, and a touch a block from 60 s."""
    senders = FanOutLoad.sender_names("fan", shape, k, "payer")
    code = {"payer": PAYER_CODE[shape]}
    if shape != "shared-sender" and verify_gas:
        code.update({s: "account" for s in senders})
    sim = scenario(profile, {"payer": 10**18, "toucher": 10**20}, code, nodes=FAN_NODES)
    stop = 60 + SLOT * touches
    load = FanOutLoad("fan", shape=shape, k=k, payer="payer", node="n00", verify_gas=verify_gas, toucher="toucher",
                      targets=[f"n{i:02d}" for i in range(FAN_NODES)], start=30, touch_from=60, stop=stop)
    sim.add_load(load)
    marks = {}
    sim.sched.at(59, lambda: marks.update(held=[
        [e for e in n.pool.frame.entries.values() if e.tx.label.startswith("fan-")] for n in sim.net.nodes.values()]))
    seen = watch(sim)
    sim.run(stop + 2 * SLOT)
    touch_hashes = {t.hash for t in load.touches}
    hit = [(r, g) for _, block, r, g in seen["blocks"] if any(tx.hash in touch_hashes for tx in block.txs)]
    quiet = [r for _, block, r, g in seen["blocks"] if not any(tx.hash in touch_hashes for tx in block.txs)
             and block.head.timestamp > 60]
    held = marks["held"]
    return {
        "admitted": sum(1 for a in load.answers if "ok" in a),
        "held": sum(map(len, held)) / FAN_NODES,
        "capital": sum(e.tx.max_cost for e in held[0]),
        "max_gas": sum(e.tx.max_gas for e in held[0]),
        "refusals": Counter(a for answers in load.answers for a in answers if a != "ok").most_common(1),
        "touches": len(hit) / FAN_NODES,
        "resims": sum(r for r, _ in hit) / max(1, len(hit)),
        "code": sum(g for _, g in hit) / max(1, len(hit)),
        "quiet": sum(quiet) / max(1, len(quiet)),
    }


def honest(profile, shape: str, base: float = 1500, burst: float = 7500, hours: float = 1.0) -> dict:
    """A paymaster service's users: `base` an hour all run, and `burst` more an hour from minute 10 to 20."""
    users = [f"u{i}" for i in range(4000)]
    code = {u: "account" for u in users}
    code["payer"] = PAYER_CODE[shape]
    sim = scenario(profile, {"payer": 10**22}, code)
    loads = [SponsoredLoad("use", rate=base / 3600, senders=users[:2000], shape=shape, payer="payer"),
             SponsoredLoad("burst", rate=burst / 3600, senders=users[2000:], shape=shape, payer="payer",
                           start=600, stop=1200)]
    for load in loads:
        sim.add_load(load)
    held = []
    for node in sim.net.nodes.values():
        node.import_hooks.append(lambda node, block: held.append((block.head.timestamp,
                                                                  node.pool.frame.payer_count.get("payer", 0))))
    seen = watch(sim)
    rec = sim.run(hours * 3600)
    txs = [tx for load in loads for tx in load.txs]
    landed = [rec.txs[tx.hash] for tx in txs if rec.txs[tx.hash].included_at is not None]
    delays = [r.included_at - r.submitted_at for r in landed]
    blocks = seen["blocks"]
    late = [(r, g) for _, block, r, g in blocks if block.head.timestamp >= 1800]
    answers = Counter(a for load in loads for v in load.answers.values() for a in v)
    return {
        "max_gas": txs[0].max_gas, "asked": len(txs), "landed": len(landed) / hours, "p50": percentile(delays, 50), "p90": percentile(delays, 90),
        "resims": sum(r for _, _, r, _ in blocks) / len(blocks), "max": max(r for _, _, r, _ in blocks),
        "code": sum(g for _, _, _, g in blocks) / len(blocks), "late": sum(r for r, _ in late) / max(1, len(late)),
        "held": sum(h for _, h in held) / len(held), "held_max": max(h for _, h in held),
        "busy": answers["ErrFramePaymasterBusy"] / max(1, len(txs)),
        "waiting": len(txs) - len(landed),
    }


def main() -> None:
    out = ["# 03. Revalidation cost: results", "",
           f"Generated by `experiments/03-revalidation-cost/run.py`, seed {SEED}, {SLOT} s slots, gas limit "
           f"{GAS_LIMIT}, {FAN_NODES} nodes in sections 1 and 2 and {NODES} in section 3. Do not edit by hand.", ""]

    out += ["## The bound", "",
            "What FP-6, FP-14 and FP-15 allow one block to cost a node: every pending transaction re-simulated, each "
            "prefix at its whole verification budget. The adversary's gas is one transfer that changes the balance "
            "they all depend on.", ""]
    rows = []
    for p in (EIP_8141, HEGOTA_TESTNET):
        bound = p.max_pending * p.max_verify_gas
        rows.append([p.name, p.max_pending, p.max_verify_gas, bound, TOUCH, bound / TOUCH])
    out.append(table(["profile", "max_pending", "max_verify_gas", "gas re-run per node per block, at most",
                      "adversary's gas per block", "ratio"], rows))

    out += ["", "## 1. How many transactions one payer can make every node re-simulate", "",
            f"An adversary sends {FAN} transactions resting on one payer it controls to every node 30 s into the "
            "run, at a fee cap and tip of 1 wei, so that no builder includes them; from 60 s, after every block "
            "its node imports, an account it controls sends the payer 1 wei in a 21,000-gas transfer, which "
            "lands in the next block, five times. Held is the adversary's transactions per node when the "
            "touches begin; capital is the summed `max_cost` they reserve at one node, in wei, and what it would "
            "be at a fee cap of the genesis base fee, 1 gwei. Re-simulations and code gas are per node per block "
            "that carried a touch: code gas is the declared limits of the prefix frames whose target holds code "
            f"the protocol does not define, here {VERIFY_GAS} for each sender with code and 10000 for a "
            "non-canonical paymaster. Re-simulations in other blocks are per node per block after 60 s. The "
            "ratio is code gas per node against the touch's 21,000 gas.", ""]
    rows = []
    for label, shape, verify in STRUCTURES:
        for profile in PROFILES:
            r = fan_out(profile, shape, verify, FAN)
            refusal = r["refusals"][0][0] if r["refusals"] else "none"
            rows.append([label, profile.name, r["held"], refusal, r["capital"], r["max_gas"] * BASE_FEE,
                         r["touches"], r["resims"], r["code"], r["quiet"], r["code"] / TOUCH])
    out.append(table(["payer", "profile", "held", "refused as", "capital, wei", "capital at 1 gwei",
                      "touches landed", "re-simulations per touch", "code gas per touch", "re-simulations otherwise",
                      "ratio"], rows))

    out += ["", "## 2. As a function of how many share the payer", "",
            "Section 1's default-code sponsor with senders that hold code, under `eip-8141`, for fewer "
            "and more transactions, up to `max_pending`; columns as in section 1.", ""]
    rows = []
    for k in (1, 16, 256, FAN, EIP_8141.max_pending):
        r = fan_out(EIP_8141, "sponsor", VERIFY_GAS, k)
        rows.append([k, r["held"], r["capital"], r["resims"], r["code"], r["code"] / TOUCH])
    out.append(table(["transactions sent", "held", "capital, wei", "re-simulations per touch", "code gas per touch",
                      "ratio"], rows))

    out += ["", "## 3. An honest paymaster's users", "",
            "Users of one paymaster service, each a sender with code (30,000 gas of verification), send 1500 "
            "transactions an hour for an hour, and 7500 more an hour from minute 10 to minute 20: about half the "
            "base fee's target, then half again the block's capacity (the first table). Each user has one transaction in flight and sends it again to a "
            "random node after every block that does not include it; nobody raises a fee. The payer is a "
            "canonical paymaster, or under `hegota-testnet` a default-code sponsor, which that profile caps at "
            "one pending transaction. Landed is an hour's inclusions, delays are seconds from first submission. "
            "Re-simulations and code gas are per node per block, over the run and, for re-simulations, over its "
            "second half; held is the payer's pending transactions per node at a block. Busy is "
            "`ErrFramePaymasterBusy` answers per transaction asked.", ""]
    results = [(profile, shape, honest(profile, shape)) for profile, shape in (
        (EIP_8141, "paymaster"), (PROFILES[2], "paymaster"), (EIP_8141, "sponsor"), (HEGOTA_TESTNET, "sponsor"))]
    rows = []
    for shape in ("paymaster", "sponsor"):
        g = next(r["max_gas"] for _, s, r in results if s == shape)
        rows.append(["canonical paymaster" if shape == "paymaster" else "default-code sponsor", g,
                     GAS_LIMIT // 2 / g * 3600 / SLOT, GAS_LIMIT // g * 3600 / SLOT])
    out.append(table(["payer", "transaction gas", "target, an hour", "capacity, an hour"], rows))
    out.append("")
    rows = []
    for profile, shape, r in results:
        rows.append([profile.name, "canonical paymaster" if shape == "paymaster" else "default-code sponsor",
                     r["asked"], r["landed"], r["p50"], r["p90"], r["held"], r["held_max"], r["resims"], r["max"],
                     r["late"], r["code"], r["busy"], r["waiting"]])
    out.append(table(["profile", "payer", "asked", "landed", "delay p50", "p90", "held", "held, most",
                      "re-simulations", "most in a block", "second half", "code gas", "busy", "waiting at end"],
                     rows))
    print("\n".join(out))


if __name__ == "__main__":
    main()
