#!/usr/bin/env python3
"""Experiment 12: propagation as a timing channel. Prints results.md on standard output.

An earlier design study argues that a funder who runs a node learns when a
transaction first appeared, to within the arrive timeout of its first hop,
and from which peer; an earlier analysis asks, as its last open test, whether what a mempool observer
learns about a spend before inclusion is any more than the block tells. This
puts observers into the gossip of `sim/emem_sim/network.py`, a spy connected
to every node or honest nodes that log, and has them guess which node a user
handed each spend to, as the peer from which they first heard of it. It
measures how often the guess is right, how soon the observers hear, and how
long they hold the spend before a block includes it, against the share of
nodes that observe, the peer count, the arrive timeout, the network's size,
and builders that filter spends with and without inclusion lists. Decision
record 0021.
"""

from __future__ import annotations

import random
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "ref" / "python"), str(ROOT / "sim")]

from emem import FOCIL_PROFILES, HEGOTA_TESTNET, Head  # noqa: E402
from emem_sim import (ChainConfig, NetworkConfig, Scenario, SharedSenderLoad, Simulation, fixed,  # noqa: E402
                      percentile, run_all, table)

SEEDS = (1, 2, 3, 4, 5)  # each draws its own topology, latencies, observers and arrivals
NODES = 50
DEGREE = 8
TIMEOUT = 0.5  # txArriveTimeout
DEGREES = (4, 8, 16)
TIMEOUTS = (0.1, 0.5, 2.0)
SIZES = (25, 50, 100, 200)
SLOT = 12
GAS_LIMIT = 30_000_000
BASE_FEE = 1_000_000_000
RUN = 720.0
SEND = (12.0, 420.0)  # when users send spends
RATE = 0.25  # spends a second, three a slot
TIP = 1_000_000_000
SENDER = "pool"
SHARES = (0.02, 0.05, 0.1, 0.2, 0.5)  # of the nodes, which observe
SHARE = 0.1  # sections 2 and 3
BUILDERS = 10  # section 4: the nodes that build every block, in turn
FILTERING = 0.9  # section 4: of the builders, which leave spends out
SPY = "spy"


@dataclass(frozen=True)
class Run:
    seed: int
    nodes: int = NODES
    degree: int = DEGREE
    timeout: float = TIMEOUT
    focil: str = ""  # "": every node builds in turn and nobody filters; else section 4's builders and IL profile
    filtering: float = 0.0


def names(n: int) -> list[str]:
    return [f"n{i:02d}" for i in range(n)]


def observers(run: Run, share: float) -> set[str]:
    """`share` of the nodes, at least one, drawn from a stream of their own; a smaller share is a subset."""
    order = names(run.nodes)
    random.Random(f"{run.seed}/observers").shuffle(order)
    return set(order[:max(1, round(share * run.nodes))])


def one(run: Run) -> dict:
    honest = names(run.nodes)
    spy = f"n{run.nodes:02d}"
    if run.focil:
        rng = random.Random(f"{run.seed}/placement")
        builders = tuple(sorted(rng.sample(honest, BUILDERS)))
        filtering = frozenset(rng.sample(builders, round(run.filtering * BUILDERS)))
        chain = ChainConfig(slot_time=SLOT, proposer=builders, block_delay=(0.1, 1.0),
                            focil=FOCIL_PROFILES[run.focil], censored=lambda tx: tx.sender == SENDER,
                            filtering=filtering, strategy="yield")
    else:
        chain = ChainConfig(slot_time=SLOT, proposer=tuple(honest), block_delay=(0.1, 1.0))
    sim = Simulation(Scenario(
        seed=run.seed,
        nodes=run.nodes + 1,
        network=NetworkConfig(degree=run.degree, latency=(0.02, 0.10), arrive_timeout=run.timeout,
                              record_heard=True, spies=(spy,)),
        chain=chain,
        frame_pool=HEGOTA_TESTNET,
        genesis=Head(timestamp=0, gas_limit=GAS_LIMIT, gas_used=GAS_LIMIT // 2, base_fee=BASE_FEE),
        accounts={SENDER: 10**24},
        code={SENDER: "privacy-pool"},
    ))
    load = SharedSenderLoad("s", rate=RATE, senders=[SENDER], rule="direct", tip=fixed(TIP), targets=honest,
                            start=SEND[0], stop=SEND[1])
    sim.add_load(load)
    rec = sim.run(RUN)
    nodes = sim.net.nodes
    peers = {n: set(nodes[n].peers) - {spy} for n in honest}
    kinds = {SPY: {spy}} | {share: observers(run, share) for share in SHARES}
    out = {"spends": len(load.spends), "included": 0, "delays": [],
           "kinds": {k: {"spends": 0, "at": 0, "found": 0, "near": 0, "lags": [], "windows": []} for k in kinds}}
    for sp in load.spends:
        r = rec.txs[sp.tx.hash]
        if r.included_at is not None:
            out["included"] += 1
            out["delays"].append(r.included_at - r.submitted_at)
        for kind, watch in kinds.items():
            o = out["kinds"][kind]
            if r.origin in watch:
                o["at"] += 1
                continue
            heard = [(nodes[w].heard[sp.tx.hash], w) for w in sorted(watch) if sp.tx.hash in nodes[w].heard]
            o["spends"] += 1
            if not heard:
                continue
            (at, guess), _ = min(heard)
            o["found"] += guess == r.origin
            o["near"] += guess == r.origin or guess in peers[r.origin]
            o["lags"].append(at - r.submitted_at)
            if r.included_at is not None:
                o["windows"].append(r.included_at - at)
    out["watched"] = {kind: len(watch) for kind, watch in kinds.items()}
    out["blocks"] = len(rec.blocks)
    return out


def pooled(outs: list[dict], kind) -> dict:
    o = {k: [] if isinstance(v, list) else 0 for k, v in outs[0]["kinds"][kind].items()}
    for x in outs:
        for k, v in x["kinds"][kind].items():
            o[k] += v
    o["watched"] = sum(x["watched"][kind] for x in outs) / len(outs)
    return o


def label(kind) -> str:
    return "spy" if kind == SPY else f"{kind:.0%} of nodes"


def chance(kind, o: dict, nodes: int) -> float:
    """The chance that a guess with no information names the node: one over the nodes it could be."""
    return 1 / (nodes - (0 if kind == SPY else o["watched"]))


def cells(kind, o: dict, nodes: int) -> list:
    return [o["spends"], o["found"] / o["spends"], o["near"] / o["spends"], chance(kind, o, nodes),
            percentile(o["lags"], 50), percentile(o["lags"], 90)]


HEAD = ["spends", "origin found", "origin or a peer of it", "chance", "heard after p50", "p90"]


def section_1(out) -> str:
    runs = out[(NODES, DEGREE, TIMEOUT, "", 0.0)]
    rows = []
    for kind in [SPY] + list(SHARES):
        o = pooled(runs, kind)
        rows.append([label(kind), f"{o['watched']:.0f}" if kind != SPY else 1, o["at"]] + cells(kind, o, NODES)
                    + [max(o["lags"]), percentile(o["windows"], 50), percentile(o["windows"], 90)])
    delays = [d for x in runs for d in x["delays"]]
    spends = sum(x["spends"] for x in runs)
    included = sum(x["included"] for x in runs)
    lines = [
        "## 1. Who the observers find, and how soon",
        "",
        f"{NODES} nodes, each dialling random peers until it has {DEGREE}, one-way link latency uniform in 20 to "
        f"100 ms, arrive timeout {TIMEOUT} s, frame pool profile `hegota-testnet`, a block every {SLOT} s from a "
        f"proposer that rotates through the nodes, gas limit {GAS_LIMIT}. From {SEND[0]:.0f} s to {SEND[1]:.0f} s "
        f"users send spends from one shared sender, {RATE * SLOT:.0f} a slot, each to a random node, with a "
        f"{TIP // 10**9} gwei tip; the run lasts {RUN:.0f} s. A spy is connected to every node and relays "
        "nothing; observers are a share of the nodes, drawn at random, which relay as every node does. Rows pool "
        f"{len(SEEDS)} runs, seeds {', '.join(map(str, SEEDS))}, each with its own topology and observers.",
        "",
        "For each spend the observers take the first time any of them heard of it, by a push, an announcement or "
        "a fetch's answer, and guess that the peer they heard it from is the node the user handed it to. At an "
        "observer counts spends handed to an observer, which it knows for certain and which the other columns "
        "leave out. Origin found is the share of the rest the guess names; origin or a peer of it, the share it "
        "names the node or one of its peers; chance, one over the nodes the origin could be. Heard after is from "
        "the user's hand-over to the observers' first hearing, in seconds, and held before inclusion from then "
        "until the block that includes the spend.",
        "",
        table(["observer", "observers", "at an observer"] + HEAD + ["max", "held before inclusion p50",
                                                                           "p90"], rows),
        "",
        "What the block alone tells about when a spend was handed over: its delay from the hand-over to the block "
        "that includes it, which nobody watching only blocks can see behind.",
        "",
        table(["spends", "included", "delay p50", "p90", "max"],
              [[spends, included, percentile(delays, 50), percentile(delays, 90), max(delays)]]),
    ]
    return "\n".join(lines)


def section_2(out) -> str:
    rows = []
    for kind in (SPY, SHARE):
        for degree in DEGREES:
            for timeout in TIMEOUTS:
                o = pooled(out[(NODES, degree, timeout, "", 0.0)], kind)
                rows.append([label(kind), degree, timeout] + cells(kind, o, NODES))
    lines = [
        "## 2. Against the peer count and the arrive timeout",
        "",
        f"Section 1's network and spends, with each node dialling until it has the peers in the table and "
        "waiting the arrive timeout in the table for a push before it fetches an announced hash. The spy, and "
        f"observers at {SHARE:.0%} of the nodes.",
        "",
        table(["observer", "peers", "arrive timeout"] + HEAD, rows),
    ]
    return "\n".join(lines)


def section_3(out) -> str:
    rows = []
    for kind in (SPY, SHARE):
        for n in SIZES:
            o = pooled(out[(n, DEGREE, TIMEOUT, "", 0.0)], kind)
            rows.append([label(kind), n, f"{o['watched']:.0f}" if kind != SPY else 1] + cells(kind, o, n))
    lines = [
        "## 3. Against the network's size",
        "",
        f"Section 1's spends on networks of the size in the table, {DEGREE} peers each, arrive timeout "
        f"{TIMEOUT} s. The spy, and observers at {SHARE:.0%} of the nodes.",
        "",
        table(["observer", "nodes", "observers"] + HEAD, rows),
    ]
    return "\n".join(lines)


def section_4(out) -> str:
    rows = []
    for focil, share in (("off", 0.0), ("off", FILTERING), ("eip-8369", FILTERING)):
        runs = out[(NODES, DEGREE, TIMEOUT, focil, share)]
        o = pooled(runs, SPY)
        spends = sum(x["spends"] for x in runs)
        included = sum(x["included"] for x in runs)
        rows.append([focil, share, spends, included, o["found"] / o["spends"], percentile(o["lags"], 50),
                     percentile(o["windows"], 50), percentile(o["windows"], 90), max(o["windows"])])
    lines = [
        "## 4. How long the spy holds a spend, with builders that filter",
        "",
        f"Section 1's network and spends, with {BUILDERS} nodes, drawn at random, building every block in turn. "
        "A share of them leaves every spend out and yields its slot to the next builder that does not, as in "
        "experiment 09; under `eip-8369` a committee lists spends as EIP-8369 Profile 2 candidates (IL-2 to "
        "IL-4) and a block that leaves out a listed spend it had room for is not canonical (IL-6). Held before "
        "inclusion is from the spy's first hearing until the block that includes the spend.",
        "",
        table(["inclusion lists", "builders that filter", "spends", "included", "origin found", "heard after p50",
               "held before inclusion p50", "p90", "max"], rows),
    ]
    return "\n".join(lines)


def main() -> None:
    keys = [(NODES, d, t, "", 0.0) for d in DEGREES for t in TIMEOUTS]
    keys += [(n, DEGREE, TIMEOUT, "", 0.0) for n in SIZES if n != NODES]
    keys += [(NODES, DEGREE, TIMEOUT, f, s) for f, s in (("off", 0.0), ("off", FILTERING), ("eip-8369", FILTERING))]
    runs = [Run(seed, *key) for key in keys for seed in SEEDS]
    results = dict(zip(runs, run_all(one, runs)))
    out = {key: [results[Run(seed, *key)] for seed in SEEDS] for key in keys}
    print("# 12. Propagation as a timing channel: results")
    print()
    print(f"Generated by `experiments/12-timing-channel/run.py`, seeds {', '.join(map(str, SEEDS))}, {NODES} nodes "
          f"and in section 3 {', '.join(map(str, SIZES))}, {DEGREE} peers each and in section 2 "
          f"{', '.join(map(str, DEGREES))}, {SLOT} s slots, {RUN:.0f} s a run, frame pool profile "
          "`hegota-testnet`. Do not edit by hand.")
    for section in (section_1, section_2, section_3, section_4):
        print()
        print(section(out))


if __name__ == "__main__":
    main()
