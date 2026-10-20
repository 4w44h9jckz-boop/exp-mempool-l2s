#!/usr/bin/env python3
"""Experiment 21: expiring nonces for a shared sender. Prints results.md on standard output.

Experiment 01's shared sender, its nullifier a 256-bit EIP-8250 nonce key under
FP-12's `one` and `disjoint-keys`, against the same sender in EIP-8266's
expiring-nonce mode, composed with EIP-8250 as a reserved key, its nullifier in
its own storage (`docs/spec/09-expiring-nonces.md`, decision record 0030), with
nodes that take the EIP's MAY and admit several pending (`many`) and nodes that
do not (`one`).
"""

from __future__ import annotations

import bisect
import sys
from collections import Counter
from dataclasses import replace
from pathlib import Path
from typing import NamedTuple

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "ref" / "python"), str(ROOT / "sim")]

from emem import EIP_8141, EIP_8266, Head  # noqa: E402
from emem_sim import (ChainConfig, NetworkConfig, Scenario, SharedSenderLoad, Simulation,  # noqa: E402
                      percentile, run_all, table)

SEED = 1
NODES = 20
HOURS = 4
SLOT = 12
GAS_LIMIT = 2_100_000
LEAD = 48
VARIANTS = {
    "one": (EIP_8141, True),
    "disjoint-keys": (replace(EIP_8141, per_sender="disjoint-keys"), False),
    "expiring, many": (EIP_8266, False),
    "expiring, one": (replace(EIP_8266, expiring_per_sender="one"), True),
}


class Run(NamedTuple):
    variant: str
    demand: int
    rule: str = "relayer"
    lead: int = LEAD
    hours: float = HOURS
    forget: bool = False  # the fetcher keeps no memory of a refusal as underpriced


def mean(values):
    return sum(values) / len(values) if values else None


def simulate(r: Run) -> dict:
    profile, serial = VARIANTS[r.variant]
    expiring = r.lead if profile.expiring else None
    scenario = Scenario(
        seed=SEED,
        nodes=NODES,
        network=NetworkConfig(degree=8, latency=(0.02, 0.10), arrive_timeout=0.5,
                              underpriced_timeout=0.0 if r.forget else 300.0),
        chain=ChainConfig(slot_time=SLOT, proposer="rotate", block_delay=(0.1, 1.0)),
        frame_pool=profile,
        genesis=Head(timestamp=0, gas_limit=GAS_LIMIT, gas_used=GAS_LIMIT // 2, base_fee=1_000_000_000),
        accounts={"pool": 10**24, profile.expiry_verifier: 0},
        code={"pool": "privacy-pool", profile.expiry_verifier: "expiry-verifier"},
    )
    sim = Simulation(scenario)
    load = SharedSenderLoad("spend", rate=r.demand / 3600, senders=["pool"], rule=r.rule,
                            serial=serial and r.rule == "relayer", key_bytes=32, expiring=expiring)
    sim.add_load(load)
    duration = r.hours * 3600
    rec = sim.run(duration)

    landed = {}
    for sp in load.spends:
        for v in sp.versions:
            if rec.txs[v.hash].included_at is not None:
                landed[sp.label] = rec.txs[v.hash].included_at
    delays = [landed[sp.label] - sp.requested_at for sp in load.spends if sp.label in landed]
    exposure = [landed[sp.label] - rec.txs[sp.versions[0].hash].submitted_at
                for sp in load.spends if sp.label in landed]
    queued = [rec.txs[sp.versions[0].hash].submitted_at - sp.requested_at > r.lead
              for sp in load.spends if sp.label in landed]
    tips = sorted(sp.tip for sp in load.spends)
    median_tip = tips[len(tips) // 2] if tips else 0
    high = [landed[sp.label] - sp.requested_at for sp in load.spends if sp.label in landed and sp.tip >= median_tip]
    low = [landed[sp.label] - sp.requested_at for sp in load.spends if sp.label in landed and sp.tip < median_tip]
    times = [b["at"] for b in rec.blocks]
    carrying = Counter(landed.values())
    waiting = [0] * (len(times) + 1)  # spends waiting since before the previous slot, by block, as differences
    for sp in load.spends:
        first = bisect.bisect_right(times, sp.requested_at + SLOT)
        last = bisect.bisect_left(times, landed.get(sp.label, duration + 1))
        if first < last:
            waiting[first] += 1
            waiting[last] -= 1
    missed, open_ = 0, 0
    for i, t in enumerate(times):
        open_ += waiting[i]
        missed += open_ > 0 and not carrying[t]
    results, dropped = Counter(), Counter()
    for sp in load.spends:
        for v in sp.versions:
            results.update(rec.txs[v.hash].results)
            dropped.update(rec.txs[v.hash].dropped)
    answers = Counter(a for sp in load.spends for a in sp.answers)
    asked = max(1, len(load.spends))
    n = max(1, len(landed))
    tx = load.spends[0].versions[0]
    return {
        "asked": len(load.spends), "landed": len(landed), "per_hour": len(landed) / r.hours,
        "waiting": len(load.spends) - len(landed), "delays": delays, "exposure": exposure,
        "per_block": max(carrying.values(), default=0), "missed": missed,
        "queued": 100 * sum(queued) / n, "high": high, "low": low,
        "versions": mean([len(sp.versions) for sp in load.spends if sp.label in landed]),
        "versions_max": max((len(sp.versions) for sp in load.spends), default=0),
        "submissions": sum(answers.values()) / asked,
        "refused": (sum(answers.values()) - answers["ok"]) / asked,
        "busy": (results["ErrFrameSenderBusy"] + results["ErrReplaceUnderpriced"]) / n,
        "far": results["ErrFrameExpiryTooFar"] / n, "expired": results["ErrFrameExpired"] / n,
        "replaced": dropped["replaced"] / asked,
        "tx": (len(tx.frames), tx.data_bytes, tx.gas.intrinsic, tx.max_gas, tx.frames[-2].exec_gas,
               GAS_LIMIT // tx.max_gas),
    }


def main() -> None:
    s1 = [Run(v, d) for v in VARIANTS for d in (60, 150, 300, 600, 1200, 3600)]
    s2 = [Run(v, d, rule) for d in (150, 300) for v in VARIANTS for rule in ("relayer", "direct")]
    s3 = [Run("expiring, many", d, lead=lead) for d in (300, 3600) for lead in (12, 24, 36, 48, 60)]
    s4 = [Run(v, d, forget=f) for v in ("one", "expiring, one") for d in (300, 3600) for f in (False, True)]
    runs = list(dict.fromkeys(s1 + s2 + s3 + s4))
    res = dict(zip(runs, run_all(simulate, runs)))

    out = ["# 21. Expiring nonces for a shared sender: results", "",
           f"Generated by `experiments/21-expiring-nonces/run.py`, seed {SEED}, {NODES} nodes, a {SLOT} s slot, "
           f"{HOURS} simulated hours a run, a deadline {LEAD} s after the head's timestamp unless a section says "
           "otherwise. Do not edit by hand.", ""]

    out += ["## The spend", "",
            "The first spend of each variant. The keyed variants carry the nullifier as a 32-byte nonce key; "
            "the expiring ones carry the reserved key and an expiry frame, and their `self_verify` frame, which "
            "approves payment, carries the 13,000 gas of EN-5. Prefix gas is that frame's.", ""]
    out.append(table(["variant", "frames", "data bytes", "intrinsic gas", "max gas", "prefix gas",
                      "spends per block at the limit"],
                     [[v, *res[Run(v, 60)]["tx"]] for v in VARIANTS]))

    out += ["", "## 1. Spends an hour against demand", "",
            "One shared sender, its spends sent by a relayer: under `one` and `expiring, one` it waits for each "
            "spend's inclusion before sending the next; under `disjoint-keys` and `expiring, many` it sends each "
            "at once. Demand and landed spends are per hour; $\\rho$ is demand over the one-a-slot ceiling. Delays "
            "are seconds from the user's request to the block that included the spend. Versions are the versions "
            "of a landed spend its user signed, 1 when it was never signed again. Queued past the lead is the percentage "
            f"of landed spends the relayer first sent more than {LEAD} s after they were asked for: in the expiring "
            "variants the relayer makes a spend's version when it sends it, so each of these is a spend whose user "
            "signed when the relayer sent it, rather than when they asked. Refusals are every node's "
            "answers to the spend's versions, received from the relayer or a peer, per spend landed: busy is "
            "`ErrFrameSenderBusy` and `ErrReplaceUnderpriced`, too far `ErrFrameExpiryTooFar`.", ""]
    rows = []
    for v in VARIANTS:
        for d in (60, 150, 300, 600, 1200, 3600):
            x = res[Run(v, d)]
            rows.append([v, d, d * SLOT / 3600, x["asked"], x["per_hour"], x["per_block"], mean(x["delays"]),
                         percentile(x["delays"], 50), percentile(x["delays"], 99), x["waiting"], x["queued"],
                         x["versions"], x["busy"], x["far"]])
    out.append(table(["variant", "demand", "rho", "asked", "landed", "most in a block", "delay mean", "p50", "p99",
                      "waiting at end", "queued past the lead", "versions", "busy", "too far"], rows))

    out += ["", "## 2. Who submits", "",
            "Section 1's relayer against `direct` users, who submit their own spend to a random node and, after "
            "every block that node imports without including it, submit it again to a random node; in the "
            "expiring variants a user whose version can no longer make the next block signs a new one first. "
            "Exposure is seconds from the spend's first submission to any node until its inclusion. Submissions, "
            "and the refusals among them, are per spend asked, from the node each submission went to. Replaced "
            "is the number of times, per spend asked, that a node dropped one of its versions for another "
            "transaction that replaced it. Upper and lower tips split the spends asked at the median tip.", ""]
    rows = []
    for d in (150, 300):
        for v in VARIANTS:
            for rule in ("relayer", "direct"):
                x = res[Run(v, d, rule)]
                rows.append([v, rule, d, x["per_hour"], percentile(x["delays"], 50), percentile(x["delays"], 90),
                             percentile(x["high"], 50), percentile(x["low"], 50),
                             percentile(x["exposure"], 50), percentile(x["exposure"], 90), x["submissions"],
                             x["refused"], x["replaced"], x["versions"]])
    out.append(table(["variant", "rule", "demand", "landed", "delay p50", "p90", "p50, upper tips", "lower tips",
                      "exposure p50", "p90", "submissions", "refused", "replaced", "versions"], rows))

    out += ["", "## 3. The deadline", "",
            "`expiring, many` with a relayer, its user setting the deadline the lead below after the timestamp "
            "of the relayer's node's head. A node refuses a version as too far when its own head is older than "
            "the relayer's by more than 60 s less the lead, and a version whose deadline is below the next "
            "block's timestamp can no longer be included. Columns as in section 1, with expired "
            "`ErrFrameExpired`, per spend landed, and the most versions any spend needed.", ""]
    rows = []
    for d in (300, 3600):
        for lead in (12, 24, 36, 48, 60):
            x = res[Run("expiring, many", d, lead=lead)]
            rows.append([d, lead, x["per_hour"], mean(x["delays"]), percentile(x["delays"], 99), x["waiting"],
                         x["versions"], x["versions_max"], x["far"], x["expired"]])
    out.append(table(["demand", "lead", "landed", "delay mean", "p99", "waiting at end", "versions", "most",
                      "too far", "expired"], rows))

    out += ["", "## 4. The fetcher's memory", "",
            "The two variants under which a node holds one pending spend from the sender, with a relayer, as in "
            "section 1, and again with a fetcher that keeps no memory of a refusal as underpriced "
            "(`underpriced_timeout` 0 rather than go-ethereum's 300 s). A slot is missed when no spend was "
            "included though one had been waiting since before the previous slot. Busy as in section 1.", ""]
    rows = []
    for v in ("one", "expiring, one"):
        for d in (300, 3600):
            for f in (False, True):
                x = res[Run(v, d, forget=f)]
                rows.append([v, d, 0 if f else 300, x["per_hour"], x["missed"], x["busy"]])
    out.append(table(["variant", "demand", "memory, s", "landed", "slots missed", "busy"], rows))
    print("\n".join(out))


if __name__ == "__main__":
    main()
