#!/usr/bin/env python3
"""Experiment 13: MATCHA's load floor. Prints results.md on standard output.

MATCHA's optional linear fees (MA-13, `docs/spec/04-matcha.md` version 2) ask
each additional transaction from a sender for an effective tip that rises with
the charges of the sender's other pending additional transactions. For a
privacy pool that is the sender of every spend, those are the other users'
spends, which prices a user by how busy their anonymity set is. This sends the same spends at the same rate from one shared
sender and from senders of their own, and measures what the floor adds to the
tip each user drew, how often it binds, how often other nodes refuse a spend
for it, and the delay, against `load_price` and demand; and, for wallets that
do not read the floor, what it costs them in delay instead. Decision record
0022.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "ref" / "python"), str(ROOT / "sim")]

from emem import MATCHA, Head  # noqa: E402
from emem import errors as E  # noqa: E402
from emem_sim import (ChainConfig, NetworkConfig, Scenario, SharedSenderLoad, Simulation, percentile,  # noqa: E402
                      run_all, table)

SEEDS = (1, 2, 3)  # each draws its own topology, latencies and arrivals
NODES = 50
DEGREE = 8
SLOT = 12
GAS_LIMIT = 30_000_000
BASE_FEE = 1_000_000_000
RUN = 1800.0
SEND = (12.0, 1680.0)  # when users send spends
GWEI = 10**9
PRICES = (0, GWEI // 100, GWEI // 10, GWEI)  # load_price, 0 for the matcha profile
RATES = (1, 2, 3)  # spends a slot, from each population
POOL = "pool"
ALONE = [f"alone-{i}" for i in range(20000)]


@dataclass(frozen=True)
class Run:
    seed: int
    price: int
    rate: int
    floor: bool = True  # whether wallets read the floor


def one(run: Run) -> dict:
    accounts = {POOL: 10**24} | {a: 10**21 for a in ALONE}
    sim = Simulation(Scenario(
        seed=run.seed,
        nodes=NODES,
        network=NetworkConfig(degree=DEGREE, latency=(0.02, 0.10), arrive_timeout=0.5),
        chain=ChainConfig(slot_time=SLOT, block_delay=(0.1, 1.0)),
        frame_pool=MATCHA.with_(load_price=run.price),
        genesis=Head(timestamp=0, gas_limit=GAS_LIMIT, gas_used=GAS_LIMIT // 2, base_fee=BASE_FEE),
        accounts=accounts,
        code={a: "privacy-pool" for a in accounts},
    ))
    for node in sim.net.nodes.values():  # the shared sender has been busy before the run (decision record 0022)
        node.pool.frame.finalize([(0, {POOL: MATCHA.width_cap})])
    loads = {
        "shared": SharedSenderLoad("s", rate=run.rate / SLOT, senders=[POOL], rule="direct", floor=run.floor,
                                   start=SEND[0], stop=SEND[1]),
        "alone": SharedSenderLoad("a", rate=run.rate / SLOT, senders=ALONE, rule="direct", floor=run.floor,
                                  start=SEND[0], stop=SEND[1]),
    }
    for load in loads.values():
        sim.add_load(load)
    rec = sim.run(RUN)
    out = {}
    for who, load in loads.items():
        o = {"spends": 0, "landed": 0, "delays": [], "drawn": 0, "offered": 0, "raised": 0, "premiums": [],
             "floor_refusals": 0, "width_refusals": 0}
        for sp in load.spends:
            r = rec.txs[sp.tx.hash]
            o["spends"] += 1
            o["drawn"] += sp.drawn
            o["offered"] += sp.tip
            o["raised"] += sp.tip > sp.drawn
            o["premiums"].append(sp.tip - sp.drawn)
            o["floor_refusals"] += r.results[E.ErrFrameLoadUnderpriced]
            o["width_refusals"] += r.results[E.ErrFrameInsufficientWidth]
            if r.included_at is not None:
                o["landed"] += 1
                o["delays"].append(r.included_at - sp.requested_at)
        out[who] = o
    return out


def pooled(outs: list[dict], who: str) -> dict:
    o = {k: [] if isinstance(v, list) else 0 for k, v in outs[0][who].items()}
    for x in outs:
        for k, v in x[who].items():
            o[k] += v
    return o


def gwei(wei: float) -> str:
    return f"{wei / GWEI:.3f}"


def section_1(out) -> str:
    rows = []
    for price in PRICES:
        for rate in RATES:
            for who in ("shared", "alone"):
                o = pooled(out[(price, rate, True)], who)
                n = o["spends"]
                rows.append([gwei(price), rate, who, n, o["landed"], percentile(o["delays"], 50),
                             percentile(o["delays"], 90), gwei(o["drawn"] / n), gwei(o["offered"] / n),
                             gwei(sum(o["premiums"]) / n), gwei(percentile(o["premiums"], 90)),
                             gwei(max(o["premiums"])), o["raised"] / n, o["floor_refusals"] / n,
                             o["width_refusals"] / n])
    lines = [
        "## 1. Wallets that meet the floor",
        "",
        f"{NODES} nodes, {DEGREE} peers each, one-way link latency uniform in 20 to 100 ms, a block every {SLOT} s "
        f"from a proposer that rotates through every node, gas limit {GAS_LIMIT}, base fee from 1 gwei. Frame pool "
        "profile `matcha` with MA-13's `load_price` as in the table, 0 being the profile's own. From "
        f"{SEND[0]:.0f} s to {SEND[1]:.0f} s two populations send the same spend at the same rate, each to a random "
        "node: users of one shared sender, which every node credits with the width cap before the run, and users "
        f"who each have a sender of their own, drawn from {len(ALONE)}. Each user draws a tip uniform in 0.001 to "
        "3 gwei and offers the higher of it and the floor the node it sends to asks of it; the fee cap is twice "
        "the next base fee plus the tip, and a spend a block leaves out is sent again to a random node at the "
        f"same fees. The run lasts {RUN:.0f} s. Rows pool {len(SEEDS)} runs, seeds "
        f"{', '.join(map(str, SEEDS))}, each with its own topology.",
        "",
        "Tips are in gwei a gas and are means per spend. Premium is what a user offered over what it drew; raised, "
        "the share of spends whose floor was above the tip drawn. Refusals are per spend and summed over nodes: "
        "for the floor (`ErrFrameLoadUnderpriced`) where a node's load was higher than at the node the user "
        "read, and for width (`ErrFrameInsufficientWidth`). Delay is from asking to inclusion, in seconds.",
        "",
        table(["load price, gwei", "spends a slot", "users", "spends", "landed", "delay p50", "p90", "drawn",
               "offered", "premium", "premium p90", "max", "raised", "refused for the floor",
               "refused for width"], rows),
    ]
    return "\n".join(lines)


def section_2(out) -> str:
    rows = []
    for price in PRICES[1:]:
        for rate in RATES:
            o = pooled(out[(price, rate, False)], "shared")
            b = pooled(out[(price, rate, True)], "shared")
            n = o["spends"]
            rows.append([gwei(price), rate, n, o["landed"], percentile(o["delays"], 50), percentile(o["delays"], 90),
                         max(o["delays"]) if o["delays"] else None, percentile(b["delays"], 90),
                         o["floor_refusals"] / n])
    lines = [
        "## 2. Wallets that do not read the floor",
        "",
        "Section 1's network and populations, with every user offering the tip it drew, at the `load_price` "
        "values above 0. A spend refused for the floor waits for the next block that leaves it out, and is sent "
        "again to a random node, whose pool may by then hold none of the shared sender's spends. The shared "
        "sender's users only; delay is in seconds, and the column from section 1 is the p90 of the same users "
        "who meet the floor.",
        "",
        table(["load price, gwei", "spends a slot", "spends", "landed", "delay p50", "p90", "max",
               "p90 meeting the floor", "refused for the floor"], rows),
    ]
    return "\n".join(lines)


def main() -> None:
    keys = [(p, r, True) for p in PRICES for r in RATES] + [(p, r, False) for p in PRICES[1:] for r in RATES]
    runs = [Run(seed, *key) for key in keys for seed in SEEDS]
    results = dict(zip(runs, run_all(one, runs)))
    out = {key: [results[Run(seed, *key)] for seed in SEEDS] for key in keys}
    print("# 13. MATCHA's load floor: results")
    print()
    print(f"Generated by `experiments/13-load-floor/run.py`, seeds {', '.join(map(str, SEEDS))}, {NODES} nodes, "
          f"{DEGREE} peers each, {SLOT} s slots, {RUN:.0f} s a run, frame pool profile `matcha` with MA-13's "
          "`load_price`. Do not edit by hand.")
    for section in (section_1, section_2):
        print()
        print(section(out))


if __name__ == "__main__":
    main()
