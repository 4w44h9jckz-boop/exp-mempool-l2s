#!/usr/bin/env python3
"""Experiment 22: delegated accounts. Prints results.md on standard output.

A hot wallet's plain transfers from an account without code against the same
account delegated under EIP-7702, which NP-6 gives one transaction in flight,
sent at once, one at a time, or batched; and a sponsor that upgrades sixteen
busy accounts with type 4 transactions, whose authorizations race their
authorities' own transfers (NP-7, BB-5 version 2, decision record 0031).
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path
from typing import NamedTuple

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "ref" / "python"), str(ROOT / "sim")]

from emem import Head  # noqa: E402
from emem.tx import PER_AUTHORIZATION  # noqa: E402
from emem_sim import (ChainConfig, HotWallet, NetworkConfig, Scenario, Simulation, Upgrade,  # noqa: E402
                      percentile, run_all, table)

SEED = 1
NODES = 20
SLOT = 12
GAS_LIMIT = 30_000_000
DELEGATION = "0xef0100wallet-v1"
VARIANTS = {  # name: (accounts, delegated, rule)
    "EOA": (1, False, "at once"),
    "delegated, at once": (1, True, "at once"),
    "delegated, serial": (1, True, "serial"),
    "delegated, serial, 4 accounts": (4, True, "serial"),
    "delegated, batch": (1, True, "batch"),
}
DEMANDS = (60, 150, 300, 600, 1200, 3600)
HOURS_1 = 2
ACCOUNTS_2 = 16
START_2 = 1800
WINDOW = 600
HOURS_2 = 2
SIGNING = {"next": "keeps sending", "pause": "pauses", "drain": "drains"}


class Wallet(NamedTuple):
    variant: str
    demand: int


class Upgrading(NamedTuple):
    rate: int  # transfers an hour from each account
    batch: int
    sign: str  # HotWallet.SIGNING


def scenario(senders: list[str], delegated: bool) -> Scenario:
    accounts = {s: 10**24 for s in senders} | {"sponsor": 10**24}
    return Scenario(
        seed=SEED,
        nodes=NODES,
        network=NetworkConfig(degree=8, latency=(0.02, 0.10), arrive_timeout=0.5),
        chain=ChainConfig(slot_time=SLOT, proposer="rotate", block_delay=(0.1, 1.0)),
        genesis=Head(timestamp=0, gas_limit=GAS_LIMIT, gas_used=GAS_LIMIT // 2, base_fee=1_000_000_000),
        accounts=accounts,
        code={s: DELEGATION for s in senders} if delegated else {},
    )


def landed(rec, transfers) -> dict:
    """Each landed transfer's inclusion time, by its index."""
    out = {}
    for i, t in enumerate(transfers):
        if t.versions and rec.txs[t.versions[-1].hash].included_at is not None:
            out[i] = rec.txs[t.versions[-1].hash].included_at
    return out


def wallet(r: Wallet) -> dict:
    n, delegated, rule = VARIANTS[r.variant]
    senders = [f"hot{i}" for i in range(n)]
    sim = Simulation(scenario(senders, delegated))
    load = HotWallet("hot", rate=r.demand / 3600, senders=senders, rule=rule)
    sim.add_load(load)
    rec = sim.run(HOURS_1 * 3600)
    done = landed(rec, load.transfers)
    delays = [done[i] - t.requested_at for i, t in enumerate(load.transfers) if i in done]
    txs = {load.transfers[i].versions[-1].hash for i in done}
    per_block = Counter((load.transfers[i].sender, rec.txs[load.transfers[i].versions[-1].hash].block) for i in done)
    asked = max(1, len(load.transfers))
    np6 = load.answers["ErrInflightTxLimitReached"] + load.answers["ErrOutOfOrderTxFromDelegated"]
    return {"asked": len(load.transfers), "per_hour": len(done) / HOURS_1, "waiting": len(load.transfers) - len(done),
            "mean": sum(delays) / len(delays) if delays else None, "p50": percentile(delays, 50),
            "p99": percentile(delays, 99), "per_tx": len(done) / max(1, len(txs)),
            "most": max(per_block.values(), default=0), "refused": np6 / asked}


def upgrading(r: Upgrading) -> dict:
    senders = [f"hot{i}" for i in range(ACCOUNTS_2)]
    sim = Simulation(scenario(senders, False))
    load = HotWallet("hot", rate=ACCOUNTS_2 * r.rate / 3600, senders=senders, rule="at once", delegated="batch",
                     sign=r.sign)
    up = Upgrade("up", sponsor="sponsor", wallet=load, batch=r.batch, start=START_2)
    sim.add_load(load)
    sim.add_load(up)
    duration = HOURS_2 * 3600
    rec = sim.run(duration)
    finished = max(up.done_at.values()) if len(up.done_at) == ACCOUNTS_2 else None
    answers = Counter(a for b in up.batches for a in b["answers"])
    later = sum(a == "ErrAuthorityReserved" for i, b in enumerate(up.batches) for j, a in enumerate(b["answers"])
                if (i, j) != (0, 0))
    sent = sum(answers.values())
    skipped = sum(len(b["skipped"]) for b in up.batches)
    applied = sum(len(b["applied"]) for b in up.batches)
    peers = Counter()
    for b in up.batches:
        for tx in b["txs"]:
            peers.update(rec.txs[tx.hash].results)
    included = sum(b["included_at"] is not None for b in up.batches)
    done = landed(rec, load.transfers)
    during = [done[i] - t.requested_at for i, t in enumerate(load.transfers)
              if i in done and START_2 <= t.requested_at < START_2 + WINDOW]
    before = [done[i] - t.requested_at for i, t in enumerate(load.transfers)
              if i in done and 600 <= t.requested_at < START_2]
    np6 = load.answers["ErrInflightTxLimitReached"] + load.answers["ErrOutOfOrderTxFromDelegated"]
    return {"delegated": len(up.done_at), "time": finished - START_2 if finished is not None else None,
            "sent": sent, "refused": answers["ErrAuthorityReserved"], "later": later, "included": included,
            "applied": applied,
            "skipped": skipped, "wasted": skipped * PER_AUTHORIZATION,
            "peers": peers["ErrAuthorityReserved"] / max(1, sent), "lost": load.lost, "np6": np6,
            "before": (percentile(before, 50), percentile(before, 99)),
            "during": (percentile(during, 50), percentile(during, 99)),
            "unlanded": sum(1 for i, t in enumerate(load.transfers) if i not in done and t.requested_at < duration - 60)}


def run(r):
    return wallet(r) if isinstance(r, Wallet) else upgrading(r)


def main() -> None:
    s1 = [Wallet(v, d) for v in VARIANTS for d in DEMANDS]
    s2 = [Upgrading(rate, b, sign) for rate in (60, 300, 1200) for b in (1, 4, 16) for sign in SIGNING]
    runs = s1 + s2
    res = dict(zip(runs, run_all(run, runs)))

    out = ["# 22. Delegated accounts: results", "",
           f"Generated by `experiments/22-delegated-accounts/run.py`, seed {SEED}, {NODES} nodes, a {SLOT} s slot, "
           f"gas limit {GAS_LIMIT:,}. Do not edit by hand.", ""]

    out += ["## 1. A hot wallet's throughput", "",
            f"One account (four in one row) sending plain transfers of 21,000 gas at the demand below, for "
            f"{HOURS_1} hours, from a wallet that sends each to one node. EOA: the account has no code, and the "
            "wallet sends each transfer at once. Delegated: the account's code is a delegation indicator, so NP-6 "
            "gives it one transaction in flight; at once, the wallet sends each transfer at once and, when its node "
            "refuses one, tries again after the node's next import; serial, it sends the next when its node imports "
            "the block that includes the last; batch, as serial, but each transaction carries every transfer "
            "waiting. Demand and landed are transfers an hour; delays are seconds from the request to the block "
            "that included the transfer; transfers a transaction are landed transfers over the transactions that "
            "carried them; most in a block is the most landed transfers one account had in one block; NP-6 "
            "refusals are the wallet's node's `ErrInflightTxLimitReached` and `ErrOutOfOrderTxFromDelegated`, per "
            "transfer asked.", ""]
    rows = []
    for v in VARIANTS:
        for d in DEMANDS:
            x = res[Wallet(v, d)]
            rows.append([v, d, x["asked"], x["per_hour"], x["mean"], x["p50"], x["p99"], x["waiting"], x["per_tx"],
                         x["most"], x["refused"]])
    out.append(table(["variant", "demand", "asked", "landed", "delay mean", "p50", "p99", "waiting at end",
                      "transfers a transaction", "most in a block", "NP-6 refusals"], rows))

    out += ["", f"## 2. Upgrading {ACCOUNTS_2} busy accounts", "",
            f"{ACCOUNTS_2} accounts without code, each sending plain transfers at the rate below, at once, from a "
            "wallet that sends each account's transfers to one node, and batches them, as section 1's batch, once "
            f"its node's head shows the account delegated. From second {START_2} a sponsor upgrades them in type 4 "
            "transactions of the batch size below, at a tip of 2 gwei, sent to one node. Each authorization is "
            "signed at its account's next nonce by a wallet that keeps sending; that pauses, sending nothing more "
            "for the account until its node shows the delegation or the sponsor reports the authorization "
            "skipped; or that drains, pausing as well but signing only once nothing it sent for the account is "
            "waiting for a block. The sponsor sends a batch again after its node's next import when the node "
            "refused it or a wallet had not signed, and moves on once a block includes it, keeping in line any "
            "account whose authorization the block skipped (BB-5). Delegated is accounts "
            f"delegated by the end, {HOURS_2} hours, and time the seconds from second {START_2} to the last. Sends "
            "are type 4 transactions sent; reserved the sponsor's node's `ErrAuthorityReserved`, and later those "
            "after its first send; peers the other "
            "nodes' `ErrAuthorityReserved` to them, per send; skipped the authorizations a block skipped, and their "
            "gas, 25,000 each, which the sponsor paid; lost the transfers sent again because an authorization used "
            "their nonce; NP-6 the wallet's node's refusals. Delays are seconds from the request to inclusion, "
            f"before for transfers asked from second 600 to the start, and during for those asked in the {WINDOW} s "
            "after it. Unlanded is transfers asked more than a minute before the end and not included.", ""]
    rows = []
    for rate in (60, 300, 1200):
        for b in (1, 4, 16):
            for sign in SIGNING:
                x = res[Upgrading(rate, b, sign)]
                rows.append([rate, b, SIGNING[sign], x["delegated"], x["time"], x["sent"], x["refused"],
                             x["later"], x["peers"], x["included"], x["skipped"], x["wasted"], x["lost"], x["np6"],
                             x["before"][0], x["before"][1], x["during"][0], x["during"][1], x["unlanded"]])
    out.append(table(["rate", "batch", "wallet", "delegated", "time", "sends", "reserved", "later", "peers",
                      "included",
                      "skipped", "skipped gas", "lost", "NP-6", "before p50", "p99", "during p50", "p99",
                      "unlanded"], rows))
    print("\n".join(out))


if __name__ == "__main__":
    main()
