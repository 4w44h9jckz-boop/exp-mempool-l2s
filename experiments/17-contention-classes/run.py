#!/usr/bin/env python3
"""Experiment 17: width by contention class. Prints results.md on standard output.

MATCHA (`docs/spec/04-matcha.md`) gives a sender one pending transaction that
spends no width, its baseline, and charges every other. Reply #2 on its thread
asks whether width should be indexed instead by the contention class of what
a prefix reads; MA-14 specifies the post's reading, `sender`, and two others,
`storage` and `slot`, under which a transaction that shares a class with no
pending one is a baseline. This runs experiment 02's honest pool, its
malicious application and its draining adversary under each, with spends that
read nothing of the pool's storage, a slot of their own, or a root that every
deposit rewrites. Decision record 0026.
"""

from __future__ import annotations

import sys
from collections import Counter
from dataclasses import dataclass, replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "ref" / "python"), str(ROOT / "sim")]

from emem import EIP_8141, MATCHA, Head  # noqa: E402
from emem_sim import (ChainConfig, JunkLoad, NetworkConfig, Scenario, SharedSenderLoad, Simulation,  # noqa: E402
                      SlotWriter, percentile, run_all, table)

SEED = 1
NODES = 20
HOURS = 4
GAS_LIMIT = 2_100_000
SLOT = 12
POLICIES = {
    "one": EIP_8141,
    "disjoint-keys": replace(EIP_8141, name="eip-8141, disjoint-keys", per_sender="disjoint-keys"),
    "matcha, sender": MATCHA,
    "matcha, storage": MATCHA.with_(contention="storage"),
    "matcha, slot": MATCHA.with_(contention="slot"),
}
CLASSES = ("matcha, sender", "matcha, storage", "matcha, slot")
# Experiment 02's spend: the voucher-pool spend, with a 256-bit nullifier as its nonce key.
SHAPE = dict(verify_gas=5000, verify_bytes=260, exec_gas=41000, exec_bytes=68, expiry=86400, key_bytes=32)
EXPIRY = EIP_8141.expiry_verifier
READS = ("none", "own", "root")
DEMANDS = (1200, 2400)
ATTACK = 2 * 3600  # section 3's adversary starts here, and its delays count spends asked from here
APPS = 100  # section 2: the applications of an adversary that uses one each
STRATEGIES = ("one setting", "a setting each", "an application each")


@dataclass(frozen=True)
class Run:
    section: int
    policy: str
    reads: str = "none"
    demand: float = 1200
    strategy: str = ""
    adversary: bool = False


def simulation(profile, senders: list[str], code: str) -> Simulation:
    return Simulation(Scenario(
        seed=SEED,
        nodes=NODES,
        network=NetworkConfig(degree=8, latency=(0.02, 0.10), arrive_timeout=0.5),
        chain=ChainConfig(slot_time=SLOT, proposer="rotate", block_delay=(0.1, 1.0)),
        frame_pool=profile,
        genesis=Head(timestamp=0, gas_limit=GAS_LIMIT, gas_used=GAS_LIMIT // 2, base_fee=1_000_000_000),
        accounts={**{s: 10**24 for s in senders}, EXPIRY: 0, "depositor": 10**24},
        code={**{s: code for s in senders}, EXPIRY: "expiry-verifier"},
    ))


def relayer(name: str, profile, demand: float, sender: str, **kwargs) -> SharedSenderLoad:
    """Experiment 02's relayer: serial under `one`, otherwise at once, taking back what is dropped."""
    serial = profile.per_sender == "one"
    return SharedSenderLoad(name, rate=demand / 3600, senders=[sender], serial=serial, resend=not serial,
                            **SHAPE, **kwargs)


def landed(rec, spends) -> dict[int, float]:
    return {sp.index: rec.txs[sp.tx.hash].included_at for sp in spends
            if sp.tx is not None and rec.txs[sp.tx.hash].included_at is not None}


def honest(run: Run) -> dict:
    """One shared sender, `pool0`, its relayer at n00; a depositor when spends read the root; and in
    section 3 an adversary sending junk spends from it to every node from hour 2."""
    profile = POLICIES[run.policy]
    sim = simulation(profile, ["pool0"], "privacy-pool")
    load = relayer("spend", profile, run.demand, "pool0", reads=run.reads)
    sim.add_load(load)
    if run.reads == "root":
        sim.add_load(SlotWriter("deposit", senders=["depositor"], node="n00", address="pool0", slot=0))
    adversary = None
    if run.adversary:
        adversary = JunkLoad("junk", senders=["pool0"], node="n05", burst=20, start=ATTACK,
                             targets=[f"n{i:02d}" for i in range(NODES)], reads=run.reads, **SHAPE)
        sim.add_load(adversary)
    first_width = []
    home = sim.net.nodes["n00"]
    home.import_hooks.append(lambda node, block: first_width or node.pool.frame.width("pool0") == 0
                             or first_width.append(sim.sched.now))
    rec = sim.run(HOURS * 3600)
    times = landed(rec, load.spends)
    delays = [times[sp.index] - sp.requested_at for sp in load.spends if sp.index in times]
    per_block = Counter(times.values())
    multi = [b["at"] for b in rec.blocks if per_block[b["at"]] > 1]
    answers = Counter(a for sp in load.spends for a in sp.answers)
    nodes = list(sim.net.nodes.values())
    blocks = len(rec.blocks)
    out = {
        "per_hour": len(times) / HOURS,
        "by_hour": [sum(1 for t in times.values() if h * 3600 <= t < (h + 1) * 3600) for h in range(HOURS)],
        "delays": delays, "multi": multi[0] / 60 if multi else None,
        "late": [times[sp.index] - sp.requested_at for sp in load.spends
                 if sp.requested_at >= ATTACK and sp.index in times],
        "first_width": first_width[0] / 60 if first_width else None,
        "resims": sum(n.pool.frame.resimulations for n in nodes) / NODES / blocks,
        "work": sum(n.pool.frame.work["pool0"] for n in nodes) / NODES / blocks,
        "width_refused": answers["ErrFrameInsufficientWidth"] / max(1, len(load.spends)),
        "waiting": len(load.spends) - len(times),
        "pending": sum(len(n.pool.frame.entries) for n in nodes) / NODES,
        "evicted": sum(n.pool.frame.dropped["capacity"] for n in nodes) / NODES,
    }
    if adversary is not None:
        out["junk_admitted"] = sum(1 for sp in adversary.spends if "ok" in sp.answers)
        out["junk_held"] = sum(1 for n in nodes for tx in n.pool.frame.content().get("pool0", [])
                               if tx.label.startswith("junk")) / NODES
    return out


def invalidation(run: Run, earn: float = 600, earn_until: float = 2700, start: float = 3600,
                 stop: float = 4800) -> dict:
    """Experiment 02's first attack: an application whose junk spends read a setting that a flip changes
    in the next block, with one setting, a setting for each junk spend, or an application for each."""
    profile = POLICIES[run.policy]
    senders = [f"evil{i}" for i in range(APPS)] if run.strategy == "an application each" else ["evil"]
    sim = simulation(profile, senders + ["admin"], "evil-app")
    paid = relayer("paid", profile, earn, senders[0], stop=earn_until)
    held = run.strategy != "one setting"
    junk = JunkLoad("junk", senders=senders, node="n05", burst=100, setting=(senders[0], 1), flipper="admin",
                    start=start, stop=stop, slots=APPS if run.strategy == "a setting each" else 1, flip_held=held,
                    **SHAPE)
    sim.add_load(paid)
    sim.add_load(junk)
    marks = {}

    def mark(name):
        marks[name] = {n.name: (sum(n.pool.frame.work[s] for s in senders), n.pool.frame.resimulations)
                       for n in sim.net.nodes.values()}
        marks[name + " width"] = sim.net.nodes["n05"].pool.frame.width(senders[0])

    sim.sched.at(start - 0.001, lambda: mark("start"))
    sim.sched.at(stop + SLOT - 0.001, lambda: mark("stop"))
    rec = sim.run(stop + 2 * SLOT)
    blocks = sum(1 for b in rec.blocks if start < b["at"] <= stop + SLOT)
    work = sum(marks["stop"][n][0] - marks["start"][n][0] for n in marks["stop"]) / NODES
    resims = sum(marks["stop"][n][1] - marks["start"][n][1] for n in marks["stop"]) / NODES
    flips = [f for f in junk.flips if rec.txs[f.hash].included_at is not None]
    flip_gas = sum(f.used for f in flips)
    admitted = sum(1 for sp in junk.spends if sp.answers and sp.answers[0] == "ok")
    return {"blocks": blocks, "admitted": admitted / blocks, "work": work / blocks, "resims": resims / blocks,
            "flips": len(flips), "flip_gas": flip_gas / blocks, "ratio": work / flip_gas if flip_gas else None,
            "width_start": marks["start width"], "width_stop": marks["stop width"]}


def one(run: Run) -> dict:
    return invalidation(run) if run.section == 2 else honest(run)


def runs() -> list[Run]:
    out = [Run(1, policy, reads, demand) for demand in DEMANDS for reads in READS
           for policy in ("disjoint-keys",) + CLASSES]
    out += [Run(2, "one", strategy="one setting"), Run(2, "one", strategy="an application each"),
            Run(2, "disjoint-keys", strategy="one setting")]
    out += [Run(2, policy, strategy=s) for policy in CLASSES for s in ("one setting", "a setting each")]
    out += [Run(3, policy, reads, adversary=True) for reads in ("none", "own") for policy in CLASSES]
    return out


def section_1(out) -> str:
    rows = []
    for demand in DEMANDS:
        for reads in READS:
            for policy in ("disjoint-keys",) + CLASSES:
                r = out[Run(1, policy, reads, demand)]
                rows.append([policy, reads, demand, r["per_hour"], sum(r["by_hour"][-2:]) / 2,
                             percentile(r["delays"], 50), percentile(r["delays"], 90), r["multi"], r["first_width"],
                             r["resims"], r["work"], r["width_refused"], r["waiting"]])
    return "\n".join([
        "## 1. Honest throughput",
        "",
        "One shared sender, `pool0`, and its relayer at node n00, which sends each spend at once and after every "
        "block takes back and sends again any spend its node refused or no longer holds (experiment 02). The "
        "spend's `self_verify` frame reads nothing of the pool's storage (`none`, experiment 02's spend), a slot "
        "named by its nullifier, expecting 0 (`own`), or slot 0, accepting any value, which a depositor at n00 "
        "rewrites in every block (`root`). Landed and demand are spends an hour, over the run and over its last "
        "two hours; delays are seconds from request to inclusion; the first multi-spend block and first width "
        "are minutes from the start; re-simulations and work, the admission gas of every prefix run for the "
        "pool, are per node per block; width refusals are per spend asked, at n00.",
        "",
        table(["policy", "reads", "demand", "landed", "last 2 h", "delay p50", "p90", "first multi-spend block",
               "first width", "re-simulations", "work", "width refusals", "waiting at end"], rows),
    ])


def section_2(out) -> str:
    rows = []
    for run in [r for r in out if r.section == 2]:
        r = out[run]
        rows.append([run.policy, run.strategy, r["blocks"], r["admitted"], r["resims"], r["work"], r["flips"],
                     r["flip_gas"], r["ratio"], r["width_start"], r["width_stop"]])
    return "\n".join([
        "## 2. Mass invalidation",
        "",
        "Experiment 02's malicious application: it earns width with 600 paid spends an hour for the first 45 "
        "minutes, and from minute 60 to minute 80, after every block its node n05 imports, sends up to 100 junk "
        "spends at a tip of 1 wei, which no builder includes, while an account it controls sends a transaction "
        "that changes, in the next block, what the junk read. With one setting every junk spend reads slot 1 of "
        "the application and the flip is experiment 02's, 26,000 gas. With a setting each, junk spend $i$ reads "
        f"slot $1 + (i \\bmod {APPS})$; with an application each, junk spend $i$ comes from application "
        f"$i \\bmod {APPS}$ and reads slot 1 of its own storage. In both the flip writes every setting a junk "
        "spend held at n05 reads, for 21,000 gas, 5,000 a slot and 2,600 for each further application "
        "(`sim/emem_sim/workload.py`). Per block of the attack: junk admitted at n05, and per node the "
        "re-simulations and the work for the adversary's senders, in gas; the attacker's gas is what its flips "
        "used, per block; the ratio is work per node against it; width is n05's for the first sender.",
        "",
        table(["policy", "junk reads", "blocks", "junk admitted", "re-simulations", "work", "flips landed",
               "attacker gas", "work per attacker gas", "width at start", "width at end"], rows),
    ])


def section_3(out) -> str:
    rows = []
    for reads in ("none", "own"):
        for policy in CLASSES:
            for adversary in (False, True):
                r = out[Run(3, policy, reads, adversary=True)] if adversary else out[Run(1, policy, reads, 1200)]
                rows.append([policy, reads, "every node" if adversary else "no adversary"] + r["by_hour"] + [
                    percentile(r["late"], 50), percentile(r["late"], 90), r.get("junk_admitted"),
                    r.get("junk_held"), r["pending"], r["evicted"], r["width_refused"]])
    return "\n".join([
        "## 3. Width draining",
        "",
        "Section 1's pool at 1200 spends an hour and, for the last two hours, experiment 02's adversary holding "
        "vouchers for it: after every block n05 imports it sends up to 20 junk spends from the pool, valid and "
        "read like the honest ones, at a tip of 1 wei, to every node. The rows with no adversary are section 1's "
        "runs. Landed is honest spends by hour, so the adversary acts in hours 3 and 4; delay is over spends "
        "asked in those hours. Junk admitted counts the junk spends some node took; junk held and pending are "
        "the mean numbers a node holds at the end, junk and all; evicted is the mean number a node removed for "
        "room (FP-14) over the run.",
        "",
        table(["policy", "reads", "junk sent to", "hour 1", "hour 2", "hour 3", "hour 4", "delay p50 from hour 2",
               "p90", "junk admitted", "junk held", "pending", "evicted", "width refusals"], rows),
    ])


def main() -> None:
    rs = runs()
    out = dict(zip(rs, run_all(one, rs)))
    print("# 17. Width by contention class: results")
    print()
    print(f"Generated by `experiments/17-contention-classes/run.py`, seed {SEED}, {NODES} nodes, {HOURS} "
          "simulated hours a run unless a section says otherwise, experiment 02's network and spend. Policies "
          "are FP-12's `one` and `disjoint-keys`, and MATCHA (safety factor 2, cap $2^{24}$, lifetime 3 h, "
          "balance reuse on) under MA-14's `contention` of `sender`, `storage` and `slot`. Do not edit by hand.")
    for section in (section_1, section_2, section_3):
        print()
        print(section(out))


if __name__ == "__main__":
    main()
