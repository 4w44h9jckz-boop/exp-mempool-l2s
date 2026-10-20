#!/usr/bin/env python3
r"""Experiment 25: what a self-issuer's junk proofs cost, and two defences against them. Prints results.md.

`docs/spec/10-claim-gated-admission.md` version 4 accepts as a ticket
paymaster any account whose code is the template, a key and a denomination
(CG-10), so anyone can issue tickets to themselves; under CG-3 a wrapper
refused at its proof leaves no pending transaction. This prices, in node
work and in what the attacker spends:

1. a self-issuer's junk proofs under version 4 as written, under issuer
   memory for two values of $k$, and under a node list;
2. a holder of honest tickets who attaches junk proofs to them, which issuer
   memory turns against the honest issuer's other users;
3. node lists that differ, and how many senders a node then carries.

Neither defence is a clause: both are modelled in the simulator, around the
clauses (`sim/emem_sim/issuers.py`, decision record 0059).
"""

from __future__ import annotations

import importlib.util
import random
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "ref" / "python"), str(ROOT / "sim")]

from emem import EIP_8288, Head  # noqa: E402
from emem_sim import (ChainConfig, Defence, Issuers, JunkProofs, NetworkConfig, Scenario, Simulation,  # noqa: E402
                      WalletLoad, guard, percentile, run_all, table, uniform)


def _module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


leanvm = _module("leanvm_fit", ROOT / "bench" / "leanvm" / "fit.py")  # decision record 0033

SEED = 1
NODES = 30
DEGREE = 8
SLOT = 12
EPOCH = EIP_8288.claim_epoch  # 384 s
RUN = 4 * EPOCH
DEMAND = RUN - 300  # honest spends stop here, and the run drains
START = 60
END = 3 * EPOCH  # every attacker stops at the start of the last epoch, so that what it closed reopens in the run
DAY = 86_400 // EPOCH  # epochs a day
GAS_LIMIT = 30_000_000
BASE_FEE = 1_000_000_000
MIN_TIP = 1_000_000
TIPS = (1_000_000, 3_000_000_000)
EXEC_GAS = 50_000
WALLETS = 8000
PER_SLOT = 8
HONEST = [f"h{i}" for i in range(4)]  # the honest issuers; wallet u<i> holds tickets of h<i mod 4>
JUNK_PER_SLOT = 4  # a self-issuer's wrappers to every node, every slot
OFFSET = 5  # seconds into an epoch at which a holder of honest tickets sends
FULL_EPOCHS = (1, 2)  # the epochs an attacker covers from start to end

# Measured, and cited in the README: the Hegota testnet and a wallet's run on it
VERIFY_GAS = 122_006  # the ticket paymaster's VERIFY frame, a ticket's check on chain
DEPLOY_GAS = 2_443_085  # eth_estimateGas of a ticket paymaster's deployment
TICKET_WEI = 10**15  # the denomination: what one honest ticket costs its buyer
FLOAT_WEI = 383_893_005_374_502  # FEE-4's max cost of the wallet's spend, the least float FP-8 lets one pass
VERIFY_MS = 11.442  # verifying one leanVM proof on this machine (bench/results/2026-10-13-leanvm.md)

INTERVAL_MS = EIP_8288.aggregation_interval * 1000
FAST = leanvm.laptop_costs()  # experiment 24's `laptop, budget` nodes
GATED = EIP_8288.with_(cap_aggregates=False, proving_budget=INTERVAL_MS, claims=True, **FAST)


def issuer_of(sender: str) -> str | None:
    return HONEST[int(sender[1:]) % len(HONEST)] if sender.startswith("u") else None


def defence(name: str, listed: int = len(HONEST)):
    """A function of a node's name to its `Defence`, by the row's name."""
    if name == "none":
        return lambda node: Defence()
    if name.startswith("memory"):
        k = int(name.split("=")[-1])
        return lambda node: Defence(memory=k)
    if listed == len(HONEST):
        return lambda node: Defence(listed=frozenset(HONEST))
    return lambda node: Defence(listed=frozenset(random.Random(f"{SEED}/lists/{node}").sample(HONEST, listed)))


def simulate(key: tuple) -> dict:
    """One run: (section, defence, paymasters or tickets an epoch, issuers a node lists)."""
    section, name, n, listed = key
    senders = [f"u{i}" for i in range(WALLETS)]
    junk = [f"x{i}" for i in range(n)] if section in (1, 3) else []
    accounts = {s: 10**18 for s in senders} | {p: 10**20 for p in HONEST + junk}
    sim = Simulation(Scenario(
        seed=SEED, nodes=NODES,
        network=NetworkConfig(degree=DEGREE, latency=(0.02, 0.10), arrive_timeout=0.5),
        chain=ChainConfig(slot_time=SLOT, proposer="rotate", block_delay=(0.1, 1.0), min_tip=MIN_TIP),
        frame_pool=GATED,
        genesis=Head(timestamp=0, gas_limit=GAS_LIMIT, gas_used=GAS_LIMIT // 2, base_fee=BASE_FEE),
        accounts=accounts))
    registry = Issuers(issuer_of)
    wallets = WalletLoad("u", rate=PER_SLOT / SLOT, senders=senders, tip=uniform(*TIPS), expiring=0.0,
                         exec_gas=EXEC_GAS, scheme="stark", stop=DEMAND, claims=True)
    sim.add_load(wallets)
    guards = guard(sim, defence(name, listed), registry)
    attacker = None
    if section in (1, 3):  # a self-issuer, its paymasters in the order it deploys them
        attacker = JunkProofs("x", issuers=junk, registry=registry, count=JUNK_PER_SLOT, every=SLOT,
                              rotate=True, start=START, stop=END)
    elif section == 2:  # a holder of h0's tickets, n of them an epoch
        attacker = JunkProofs("g", issuers=["h0"], registry=registry, count=n, every=EPOCH, offset=OFFSET,
                              start=START, stop=END)
    if attacker is not None:
        sim.add_load(attacker)
    failed: Counter = Counter()  # (node, epoch): the attacker's proofs that failed there

    def seen(node, wrapper, results, origin) -> None:
        if attacker is not None and origin == attacker.name and results == "ErrWrapperProof":
            failed[node.name, int(node.now // EPOCH)] += 1

    for node in sim.net.nodes.values():
        node.wrapper_hooks.append(seen)
    rec = sim.run(RUN)

    counts: Counter = Counter()
    for g in guards.values():
        counts.update(g.counts)
    proofs = Counter()
    for node in sim.net.nodes.values():
        for (origin, event, _), c in node.work.items():
            if event == "proof":
                proofs[origin] += c

    def landed(issuers: set[str]) -> tuple[int, int, list[float]]:
        sent, done, delays = 0, 0, []
        for first in wallets.txs:
            if issuer_of(first.sender) not in issuers:
                continue
            sent += 1
            times = [rec.txs[v.hash].included_at for v in wallets.versions.get(first.hash, [first])
                     if v.hash in rec.txs and rec.txs[v.hash].included_at is not None]
            if times:
                done += 1
                delays.append(min(times) - rec.txs[first.hash].submitted_at)
        return sent, done, delays

    carried = []  # by node, the share of honest spends that were pending there at some point
    for node in sim.net.nodes:
        held = sum(1 for first in wallets.txs
                   if any(node in rec.txs[v.hash].first_seen for v in wallets.versions.get(first.hash, [first])
                          if v.hash in rec.txs))
        carried.append(held / len(wallets.txs))
    lists = [g.defence.listed for g in guards.values()]
    closed = [(issuer, epoch, at) for g in guards.values() for (issuer, epoch), at in g.closed.items()]
    a = attacker.name if attacker is not None else ""
    full = [failed[node, e] for node in sim.net.nodes for e in FULL_EPOCHS]
    out = {
        "all": landed(set(HONEST)), "h0": landed({"h0"}), "others": landed(set(HONEST) - {"h0"}),
        "sent": attacker.sent if attacker else 0, "tickets": attacker.tickets if attacker else 0,
        "used": len(attacker.used) if attacker else 0,
        "ticket checks": counts["ticket", a], "prefixes": counts["prefix", a], "proofs": proofs[a],
        "refused": counts["refused", a], "unlisted": counts["unlisted", a],
        "a node an epoch": sum(full) / len(full),
        "honest refused": counts["refused", "u"], "honest unlisted": counts["unlisted", "u"],
        "honest tickets": wallets.claims_bought,
        "closed nodes": [sum(1 for i, e, _ in closed if i == "h0" and e == epoch) for epoch in FULL_EPOCHS],
        "closed s": [(epoch + 1) * EPOCH - at for i, epoch, at in closed if i == "h0" and epoch in FULL_EPOCHS],
        "carried": carried,
        "lists": [len(x) if x is not None else len(HONEST) for x in lists],
    }
    return out


def mean(xs: list[float]) -> float | None:
    return sum(xs) / len(xs) if xs else None


S1 = [(1, "none", 1, 4), (1, "memory k=1", 1, 4), (1, "memory k=1", 8, 4), (1, "memory k=8", 1, 4),
      (1, "memory k=8", 8, 4), (1, "list", 1, 4)]
S2 = [(2, "none", 1, 4), (2, "memory k=1", 1, 4), (2, "memory k=8", 8, 4), (2, "list", 1, 4)]
S3 = [(3, "list", 1, n) for n in (4, 3, 2, 1)]


def honest(r: dict, part: str = "all") -> list:
    sent, done, delays = r[part]
    return [done, sent, percentile(delays, 50), percentile(delays, 90)]


def section_1(out: dict) -> str:
    rows = []
    for key in S1:
        _, name, n, _ = key
        r = out[key]
        deploy = r["used"] * DEPLOY_GAS
        a_day = r["a node an epoch"] * NODES * DAY
        rows.append([name, n, r["used"], r["sent"], r["ticket checks"], r["prefixes"], r["proofs"],
                     r["a node an epoch"], r["refused"] + r["unlisted"], deploy,
                     deploy / r["proofs"] if r["proofs"] else None, deploy / a_day if a_day else None,
                     r["used"] * FLOAT_WEI, r["proofs"] * VERIFY_MS / 1000, r["honest refused"]] + honest(r))
    return "\n".join([
        "## 1. A self-issuer's junk proofs",
        "",
        f"{NODES} nodes, {DEGREE} peers each, a block every {SLOT} s from a rotating proposer, under EIP-8288 "
        f"with claims (CG-1), experiment 24's `laptop, budget` nodes. Wallets send {PER_SLOT} spends a slot, "
        f"each with one leanSTARK dependency, as mode 0 wrappers, for {DEMAND} s of a {RUN} s run, epochs of "
        f"{EPOCH} s. Each spend carries a valid ticket of one of {len(HONEST)} honest issuers and pays for "
        f"itself, which sets aside FP-11's cap of one pending transaction for a ticket paymaster. From second "
        f"{START} until second {END} a self-issuer hands every node {JUNK_PER_SLOT} wrappers a slot, each from a fresh sender "
        f"with a valid ticket it signed, whose proof fails. With more than one paymaster it moves to the next "
        f"at a node that refuses the current one. Each prefix runs the paymaster's `VERIFY` frame, which spent "
        f"{VERIFY_GAS} gas on the testnet, and a ticket check is the same pairing outside the EVM. `none` is "
        f"version 4 as written; `memory k=n` closes an issuer "
        f"at a node, for the rest of the epoch, at its n-th failed proof there; `list` accepts only the honest "
        f"issuers. Ticket checks, prefixes and proofs count what nodes ran on its wrappers; a node an epoch is "
        f"the mean of the proofs one node verified in each of epochs {FULL_EPOCHS[0]} and {FULL_EPOCHS[-1]}, "
        f"which the attack covers whole. Deployment gas is {DEPLOY_GAS} a paymaster it used; a proof is that over "
        f"the proofs nodes verified in the run, and over a day that over {DAY} epochs at a node an epoch's rate "
        f"on every node, with the same paymasters. Float is the least each must hold, {FLOAT_WEI} wei; it has "
        f"no withdrawal and leaves only as gas the paymaster approves. Proof s prices the proofs at "
        f"{VERIFY_MS} ms each. Honest refused counts the times a node refused an honest spend's issuer.",
        "",
        table(["defence", "paymasters", "used", "wrappers", "ticket checks", "prefixes", "proofs",
               "proofs a node an epoch", "refused before the ticket", "deployment gas", "deployment gas a proof",
               "a proof over a day", "float wei", "proof s", "honest refused", "landed", "sent", "delay p50",
               "p90"], rows),
    ])


def section_2(out: dict) -> str:
    rows = []
    base = out[S2[0]]["honest tickets"]
    for key in S2:
        _, name, n, _ = key
        r = out[key]
        rows.append([name, n, r["tickets"], r["tickets"] * TICKET_WEI, r["proofs"], mean(r["closed nodes"]),
                     mean(r["closed s"]), r["honest refused"], r["honest tickets"] - base]
                    + honest(r, "h0") + honest(r, "others")[2:])
    return "\n".join([
        "## 2. A holder of honest tickets",
        "",
        f"Section 1's network and wallets, and no self-issuer. A holder of h0's tickets, bought at "
        f"{TICKET_WEI} wei each, hands every node, {OFFSET} s into each epoch from second {START} until second "
        f"{END}, wrappers of "
        f"its own whose proofs fail, one for each ticket, n tickets an epoch. Nodes closed is the mean, over "
        f"epochs {FULL_EPOCHS[0]} and {FULL_EPOCHS[-1]}, of the nodes that closed h0; seconds closed the mean "
        f"time from a node's closing to the epoch's end. Honest refused counts the times a node refused an "
        f"honest spend because its issuer was closed, and honest tickets the tickets wallets bought beyond those "
        f"of `none`, a fresh one whenever the epoch moved on before their spend landed. The last two columns are "
        f"the delays of the other issuers' spends.",
        "",
        table(["defence", "tickets an epoch", "tickets", "wei", "proofs", "nodes closed", "seconds closed",
               "honest refused", "honest tickets over none", "h0 landed", "h0 sent", "h0 delay p50", "p90",
               "others p50", "others p90"], rows),
    ])


def section_3(out: dict) -> str:
    rows = []
    for key in S3:
        _, _, _, listed = key
        r = out[key]
        rows.append([listed, mean(r["carried"]), min(r["carried"]), max(r["carried"]), r["honest unlisted"],
                     r["ticket checks"] + r["prefixes"] + r["proofs"], r["unlisted"]] + honest(r))
    return "\n".join([
        "## 3. Node lists that differ",
        "",
        f"Section 1's network, wallets and self-issuer, with one paymaster. Each node lists n of the "
        f"{len(HONEST)} honest issuers, drawn at random for each node, and never the self-issuer. Carried is "
        f"the share of honest spends that were pending at a node at some point, its mean, least and most over "
        f"nodes; honest unlisted counts the times a node refused an honest spend's issuer. A wallet refused "
        f"sends again to a random node after the next block, as it does after any refusal.",
        "",
        table(["issuers listed", "carried mean", "least", "most", "honest unlisted", "junk checks, prefixes, proofs",
               "junk refused", "landed", "sent", "delay p50", "p90"], rows),
    ])


def main() -> None:
    keys = S1 + S2 + S3
    out = dict(zip(keys, run_all(simulate, keys)))
    print("# Experiment 25: a self-issuer's junk proofs, and two defences")
    print()
    print(f"Generated by `experiments/25-ticket-defences/run.py`, seed {SEED}. Clauses in "
          "`docs/spec/10-claim-gated-admission.md` version 4; the defences are modelled in the simulator, not "
          "specified (decision record 0059).")
    print()
    for section in (section_1(out), section_2(out), section_3(out)):
        print(section)
        print()


if __name__ == "__main__":
    main()
