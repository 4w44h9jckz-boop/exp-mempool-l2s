#!/usr/bin/env python3
"""Experiment 14: recent roots that expire in the pool. Prints results.md on standard output.

A spend proved against an EIP-8272 recent root must be proved again once the
root leaves the window, and a builder that delays its inclusion can force that.
This runs spends from senders of their own, each proved against
the latest root a root source has written, under `docs/spec/08-recent-roots.md`
(profile `eip-8272`), and measures how old their roots are when they land,
how many outlive their root in pools, what proving again costs them, and what
each node does when a root leaves the window: against the window's length,
congestion, builders that leave the spends out, builders that leave the root
writes out, and the margin a node keeps. Decision record 0023.
"""

from __future__ import annotations

import random
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "ref" / "python"), str(ROOT / "sim")]

from emem import EIP_8272, FOCIL_PROFILES, Head  # noqa: E402
from emem import errors as E  # noqa: E402
from emem_sim import (ChainConfig, NetworkConfig, RootSpendLoad, RootWriter, Scenario, Simulation,  # noqa: E402
                      TransferLoad, percentile, run_all, table)

SEEDS = (1, 2, 3, 4, 5)  # each draws its own topology, latencies, builders, proposers and arrivals
NODES = 50
DEGREE = 8
SLOT = 12
BUILDERS = 10  # the nodes that build blocks; each slot's is drawn from them
GAS_LIMIT = 30_000_000
BASE_FEE = 1_000_000_000
RUN = 1800.0
SEND = (60.0, 1500.0)  # when users ask for spends
RATE = 1 / SLOT  # spends a second, one a slot
PROVE = 12.0  # seconds a wallet takes to prove a spend
ROOT_GAS = 10_000  # the verifier frame's limit, above the 7,588 an earlier study measured for one tuple
WRITE_START = 3.0  # the root source writes every slot from here
USERS = [f"u-{i}" for i in range(600)]
WRITER = "writer"
WINDOW = EIP_8272.recent_root_length  # 8192
WINDOWS = (4, 8, 16, 32, 64)  # section 2's, scaled down so that a run of 150 slots can reach them
SHARES = (0.0, 0.5, 0.9)
MARGINS = (0, 8, 16, 32)
MARGIN_WINDOW = 64
BACKGROUND_GAS = 1_000_000
BACKGROUND_RATE = GAS_LIMIT / 2 / BACKGROUND_GAS / SLOT  # the gas target, for the whole run
PULSE = (600.0, 900.0)
PULSE_RATE = 3.0  # extra 1,000,000-gas transfers a second during the pulse
STOP = 600.0  # section 3: from here every builder leaves the root writes out


@dataclass(frozen=True)
class Run:
    seed: int
    length: int = WINDOW  # RR-1's recent_root_length
    share: float = 0.0  # of the builders, which leave out `what`
    what: str = "spends"  # "spends" or "writes"
    focil: str = "off"
    margin: int = 0  # RR-1's root_margin
    pulse: bool = False  # background demand at the gas target, and a pulse above the gas limit
    stop: bool = False  # every builder leaves the root writes out from STOP


def placement(run: Run) -> tuple[tuple[str, ...], frozenset[str]]:
    """The builders, and those that filter."""
    rng = random.Random(f"{run.seed}/placement")
    builders = tuple(sorted(rng.sample([f"n{i:02d}" for i in range(NODES)], BUILDERS)))
    if run.stop:
        return builders, frozenset(builders)
    return builders, frozenset(rng.sample(builders, round(run.share * BUILDERS)))


def one(run: Run) -> dict:
    """One simulation, summarised."""
    builders, filtering = placement(run)
    background = [f"g-{i}" for i in range(2000)] if run.pulse else []
    pulse = [f"p-{i}" for i in range(2000)] if run.pulse else []
    clock = {}
    if run.what == "spends":
        def censored(tx):
            return tx.sender.startswith("u-")
    else:
        def censored(tx):
            return tx.sender == WRITER and (not run.stop or clock["sim"].sched.now >= STOP)
    sim = Simulation(Scenario(
        seed=run.seed,
        nodes=NODES,
        network=NetworkConfig(degree=DEGREE, latency=(0.02, 0.10), arrive_timeout=0.5),
        chain=ChainConfig(slot_time=SLOT, proposer=builders, draw=True, block_delay=(0.1, 1.0),
                          focil=FOCIL_PROFILES[run.focil], censored=censored, filtering=filtering, strategy="yield"),
        frame_pool=EIP_8272.with_(recent_root_length=run.length, root_margin=run.margin),
        genesis=Head(timestamp=0, gas_limit=GAS_LIMIT, gas_used=GAS_LIMIT // 2, base_fee=BASE_FEE),
        accounts={a: 10**21 for a in USERS + [WRITER] + background + pulse},
        code={**{u: "privacy-account" for u in USERS}, EIP_8272.recent_root_address: EIP_8272.recent_root_code},
    ))
    clock["sim"] = sim
    writer = RootWriter("root", senders=[WRITER], address="pool", start=WRITE_START)
    spends = RootSpendLoad("spend", RATE, USERS, writer=writer, prove=PROVE, root_gas=ROOT_GAS,
                           start=SEND[0], stop=SEND[1])
    sim.add_load(writer)
    sim.add_load(spends)
    if run.pulse:
        sim.add_load(TransferLoad("background", BACKGROUND_RATE, background, gas=BACKGROUND_GAS))
        sim.add_load(TransferLoad("pulse", PULSE_RATE, pulse, gas=BACKGROUND_GAS, start=PULSE[0], stop=PULSE[1]))
    seen = {name: 0 for name in sim.net.nodes}
    burst = [0]

    def count(node, block) -> None:  # evictions for a root's age at each import, at each node
        now = node.pool.frame.dropped["root_expired"]
        burst[0] = max(burst[0], now - seen[node.name])
        seen[node.name] = now
    for node in sim.net.nodes.values():
        node.import_hooks.append(count)
    rec = sim.run(RUN)
    out = []
    for sp in spends.spends:
        records = [rec.txs[tx.hash] for tx, _ in sp.versions]
        landed = [r.included_at for r in records if r.included_at is not None]
        out.append({
            "landed": sp.landed_slot is not None,
            "delay": min(landed) - sp.requested_at if landed else None,
            "landed_at": min(landed) if landed else None,
            "age_sent": sp.ages[0] if sp.ages else None,
            "age_landed": sp.landed_slot - sp.landed_root if sp.landed_slot is not None else None,
            "proofs": sp.proofs,
            "evicted": sum(r.dropped["root_expired"] for r in records),
            "refused": sum(r.results[E.ErrFrameRootExpired] for r in records),
        })
    return {
        "spends": out,
        "burst": burst[0],
        "reruns": sum(n.pool.frame.resimulations for n in sim.net.nodes.values()),
        "written": len(writer.slots),
        "last_root": writer.slots[-1] if writer.slots else None,
    }


def pooled(outs: list[dict]) -> dict:
    spends = [s for o in outs for s in o["spends"]]
    landed = [s for s in spends if s["landed"]]
    n = len(spends)

    def vals(key, among=spends):
        return [s[key] for s in among if s[key] is not None]
    return {
        "n": n, "landed": len(landed), "delays": vals("delay", landed), "sent": vals("age_sent"),
        "aged": vals("age_landed", landed), "proofs": vals("proofs"),
        "again": sum(s["proofs"] > 1 for s in spends) / n,
        "evicted_spends": sum(s["evicted"] > 0 for s in spends) / n,
        "evictions": sum(s["evicted"] for s in spends) / n,
        "refused": sum(s["refused"] for s in spends) / n,
        "burst": max(o["burst"] for o in outs),
        "reruns": sum(o["reruns"] for o in outs),
        "written": sum(o["written"] for o in outs) / len(outs),
        "last_landed": max(vals("landed_at", landed)) if landed else None,
    }


def mean(xs) -> str:
    return f"{sum(xs) / len(xs):.2f}" if xs else "-"


def pct(xs, q):
    return percentile(xs, q) if xs else None


def setup() -> str:
    return (f"{NODES} nodes, {DEGREE} peers each, one-way link latency uniform in 20 to 100 ms, gas limit {GAS_LIMIT}, "
            f"base fee from 1 gwei. Each slot ({SLOT} s) one of {BUILDERS} builders is drawn at random to build the "
            "block, and those named filtering leave out what the row says. Frame pool profile `eip-8272`, with "
            "`recent_root_length` and `root_margin` as given. A root source writes a fresh root every slot from "
            f"{WRITE_START:.0f} s. From {SEND[0]:.0f} s to {SEND[1]:.0f} s users ask for one spend a slot on average, "
            "each from a sender of its own; a user reads the latest root written at or before the head of a random "
            f"node it then watches, proves for {PROVE:.0f} s, and sends the spend to a random node, again after every "
            "block its node imports without including it, and proves again against the latest root when a node "
            f"refuses the spend for its root. The run lasts {RUN:.0f} s. Rows pool {len(SEEDS)} runs, seeds "
            f"{', '.join(map(str, SEEDS))}, each with its own topology, builders and draw of proposers.")


def section_1(out) -> str:
    rows = []
    for label, key in ROWS_1:
        o = pooled(out[key])
        rows.append([label, o["n"], o["landed"], pct(o["delays"], 50), pct(o["delays"], 90),
                     max(o["delays"]) if o["delays"] else None, pct(o["sent"], 50), max(o["sent"]),
                     pct(o["aged"], 50), pct(o["aged"], 90), max(o["aged"]) if o["aged"] else None,
                     WINDOW - 1 - max(o["aged"] + o["sent"]), mean(o["proofs"]), o["evictions"]])
    return "\n".join([
        "## 1. The EIP's window",
        "",
        setup() + " Here `recent_root_length` is the EIP's 8192, so the usable window is 8191 slots. The congested "
        f"row adds 1,000,000-gas transfers at the gas target for the whole run and {PULSE_RATE:.0f} a second more "
        f"from {PULSE[0]:.0f} s to {PULSE[1]:.0f} s, when demand is 1.7 times the gas limit; with `eip-8369` a "
        "filtering builder whose block would leave a listed spend out yields the slot to the next builder that does "
        f"not filter (decision record 0018). In the last row every builder leaves the root writes out from {STOP:.0f} s.",
        "",
        "Delay is from asking to inclusion, in seconds, proving included. Ages are in slots: a root's when its "
        "spend is first sent, at the node the user watches, and when the spend lands. Slots to spare is 8191 less "
        "the oldest root that was sent or landed. Proofs are per spend, and evictions are the pools that dropped "
        "one of its versions for its root's age (RR-7), per spend.",
        "",
        table(["builders that filter", "spends", "landed", "delay p50", "p90", "max", "age sent p50", "max",
               "age landed p50", "p90", "max", "slots to spare", "proofs", "evictions"], rows),
    ])


def section_2(out) -> str:
    rows = []
    for length in WINDOWS:
        for share in SHARES:
            o = pooled(out[("spends", length, share, "off", 0, False, False)])
            rows.append([length, f"{share:.1f}", o["n"], o["landed"], pct(o["delays"], 50), pct(o["delays"], 90),
                         max(o["delays"]) if o["delays"] else None, max(o["aged"]) if o["aged"] else None,
                         mean(o["proofs"]), max(o["proofs"]), f"{o['again']:.2f}", f"{o['evicted_spends']:.2f}",
                         f"{o['evictions']:.1f}", o["burst"], o["reruns"]])
    return "\n".join([
        "## 2. Shorter windows, and builders that leave the spends out",
        "",
        "Section 1's network and users with `recent_root_length` scaled down, so that the window is within a run's "
        "reach, and a share of the builders leaving every spend out, without inclusion lists. Proved again is the "
        "share of spends that took more than one proof; evicted, the share with a version some pool dropped for "
        "its root's age; evictions, the pools that did, per spend. Largest burst is the most spends one node "
        "dropped for a root's age at one block, over every node and run, and re-runs the prefixes all nodes ran "
        "again at head changes (FP-15 step 3), summed over the runs.",
        "",
        table(["length", "share", "spends", "landed", "delay p50", "p90", "max", "age landed max", "proofs",
               "max", "proved again", "evicted", "evictions", "largest burst", "re-runs"], rows),
    ])


def section_3(out) -> str:
    rows = []
    for length in (16, 64, WINDOW):
        for label, share, stop in (("0.9 of the builders", 0.9, False), (f"every builder from {STOP:.0f} s", 0.0, True)):
            o = pooled(out[("writes", length, share, "off", 0, False, stop)])
            rows.append([length, label, f"{o['written']:.1f}", pct(o["sent"], 50), max(o["sent"]), o["n"],
                         o["landed"], o["last_landed"], mean(o["proofs"]), max(o["proofs"]), f"{o['refused']:.1f}",
                         f"{o['evictions']:.1f}", o["burst"]])
    return "\n".join([
        "## 3. Builders that leave the root writes out",
        "",
        "Section 1's network and users, with builders that leave the root source's writes out and include the "
        "spends. A write left out waits in the pools and the next ones queue behind it on its nonce, so a root "
        "lands only in a block whose builder does not filter. Slots with a root is the mean per run, out of 150. "
        "Last landed is the latest any spend landed, in seconds, over every run; users stop asking at "
        f"{SEND[1]:.0f} s. Refused is per spend and summed over nodes: admissions refused for the root's age "
        "(`ErrFrameRootExpired`).",
        "",
        table(["length", "builders that leave writes out", "slots with a root", "age sent p50", "max", "spends",
               "landed", "last landed", "proofs", "max", "refused", "evictions", "largest burst"], rows),
    ])


def section_4(out) -> str:
    rows = []
    for margin in MARGINS:
        o = pooled(out[("writes", MARGIN_WINDOW, 0.0, "off", margin, False, True)])
        rows.append([margin, o["n"], o["landed"], o["last_landed"], max(o["aged"]) if o["aged"] else None,
                     mean(o["proofs"]), max(o["proofs"]), f"{o['refused']:.1f}", f"{o['evictions']:.1f}"])
    return "\n".join([
        "## 4. The margin a node keeps",
        "",
        f"Section 3's row with `recent_root_length` {MARGIN_WINDOW}, so a usable window of {MARGIN_WINDOW - 1} "
        f"slots, and every builder leaving the root writes out from {STOP:.0f} s, with every node keeping "
        "`root_margin` as given: it refuses a spend whose root it would evict within that many slots (RR-5), and "
        "evicts at the window's end as before (RR-7). A spend reaches every node within a second of being sent, so "
        "a margin acts only on the age of a root when its spend is first sent, which grows once the writes stop. "
        "Last landed is as in section 3; refused and evictions are per spend and summed over nodes.",
        "",
        table(["margin", "spends", "landed", "last landed", "age landed max", "proofs", "max", "refused",
               "evictions"], rows),
    ])


def key(run: Run) -> tuple:
    return (run.what, run.length, run.share, run.focil, run.margin, run.pulse, run.stop)


ROWS_1 = [
    ("none", ("spends", WINDOW, 0.0, "off", 0, False, False)),
    ("none, congested", ("spends", WINDOW, 0.0, "off", 0, True, False)),
    ("0.5, spends", ("spends", WINDOW, 0.5, "off", 0, False, False)),
    ("0.9, spends", ("spends", WINDOW, 0.9, "off", 0, False, False)),
    ("0.9, spends, `eip-8369`", ("spends", WINDOW, 0.9, "eip-8369", 0, False, False)),
    ("0.5, root writes", ("writes", WINDOW, 0.5, "off", 0, False, False)),
    ("0.9, root writes", ("writes", WINDOW, 0.9, "off", 0, False, False)),
    (f"every one, root writes from {STOP:.0f} s", ("writes", WINDOW, 0.0, "off", 0, False, True)),
]


def keys() -> list[tuple]:
    ks = [k for _, k in ROWS_1]
    ks += [("spends", length, share, "off", 0, False, False) for length in WINDOWS for share in SHARES]
    ks += [("writes", length, share, "off", 0, False, stop) for length in (16, 64, WINDOW)
           for share, stop in ((0.9, False), (0.0, True))]
    ks += [("writes", MARGIN_WINDOW, 0.0, "off", margin, False, True) for margin in MARGINS]
    return list(dict.fromkeys(ks))


def main() -> None:
    ks = keys()
    runs = [Run(seed, length=k[1], share=k[2], what=k[0], focil=k[3], margin=k[4], pulse=k[5], stop=k[6])
            for k in ks for seed in SEEDS]
    results = dict(zip(runs, run_all(one, runs)))
    out = {k: [results[r] for r in runs if key(r) == k] for k in ks}
    print("# 14. Recent roots that expire in the pool: results")
    print()
    print(f"Generated by `experiments/14-recent-roots/run.py`, seeds {', '.join(map(str, SEEDS))}, {NODES} nodes, "
          f"{DEGREE} peers each, {SLOT} s slots, {RUN:.0f} s a run, frame pool profile `eip-8272`. Do not edit by "
          "hand.")
    for section in (section_1, section_2, section_3, section_4):
        print()
        print(section(out))


if __name__ == "__main__":
    main()
