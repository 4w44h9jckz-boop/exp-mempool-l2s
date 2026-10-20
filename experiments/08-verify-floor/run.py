#!/usr/bin/env python3
"""Experiment 08: the verification gas floor. Prints results.md on standard output.

ethereum/EIPs pull request 12301, open, turns EIP-8141's `MAX_VERIFY_GAS` of
100,000 from a cap into a floor: no node may refuse a frame transaction for
its validation work at or below it, and a node may admit more as headroom of
its own. The cheapest private spend measured on ethresear.ch (topic 25889) has
a validation budget of 211,828. This measures how far such a spend reaches and
how long it waits for a block, against the share of nodes with headroom and
where those nodes sit; what a gradient of headroom does to spends of 1 to 16
nullifiers; and what a budget carried in announcements, which the pull request
leaves to a future eth wire protocol, saves and lets a lying node do.
Decision record 0016.
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "ref" / "python"), str(ROOT / "sim")]

from emem import EIP_8141, Head, Signature  # noqa: E402
from emem_sim import ChainConfig, NetworkConfig, Scenario, Simulation, WalletLoad, percentile, table  # noqa: E402

SEEDS = (1, 2, 3)  # each draws its own topology, latencies, placement and arrivals
NODES = 100
DEGREE = 8
SLOT = 12
GAS_LIMIT = 30_000_000
BASE_FEE = 1_000_000_000
MIN_TIP = 1_000_000  # BB-1, go-ethereum's miner default
RUN = 2400.0
SEND = 1200.0  # wallets send for the first 1200 s of a run
RATE = 1 / 6  # spends a second, of each kind a run sends
SENDERS = 600  # a sender for each spend, more than a run's arrivals

FLOOR = EIP_8141.max_verify_gas  # 100,000
HEADROOM = 250_000  # topic 25889's recommended value, which admits a spend of up to two nullifiers
SPENDS = {1: 211_828, 2: 231_828, 8: 351_828, 16: 511_828}  # topic 25889, section 3, by nullifier count
SHARES = (0.05, 0.1, 0.15, 0.2, 0.3, 0.5, 0.75, 1.0)
RESEND_SHARES = (0.05, 0.1, 0.2)
PLACED_SHARES = (0.1, 0.3)
BUILDERS = 10  # the nodes that build every block, where a row says so
TIERS = ((525_000, 0.1), (400_000, 0.2), (250_000, 0.4))  # topic 25889's cap values; the rest sit at the floor
HINT_SHARE = 0.5
LIAR_SHARES = (0.1, 0.3)
SMALL = Signature(scheme="arbitrary", length=256)  # pushed: under txMaxBroadcastSize
LARGE = Signature(scheme="arbitrary", length=6000)  # only announced: over it
CODE = "verifier"  # every spender holds code that its self_verify frame runs


def roomy(budget: int):
    return EIP_8141.with_(max_verify_gas=budget)


def ball(sim, start: str, k: int, among: set[str]) -> list[str]:
    """The first `k` nodes of `among` that a breadth-first walk from `start` meets."""
    out, frontier, seen = [], [start], {start}
    while frontier and len(out) < k:
        n = frontier.pop(0)
        if n in among:
            out.append(n)
        for p in sim.net.nodes[n].peers:
            if p not in seen:
                seen.add(p)
                frontier.append(p)
    return out


class Setup:
    """Who builds, who has headroom and who lies, drawn from a stream of the seed's own.

    Everything but a cluster is drawn from the node names alone; a cluster
    grows from a node drawn here once the simulation has drawn its topology.
    """

    def __init__(self, seed: int, share: float = 0.0, placement: str = "random", builders: str | None = None,
                 tiers: tuple = (), liars: float = 0.0):
        assert placement == "random" or not (tiers or liars or builders)
        rng = random.Random(f"{seed}/placement")
        names = [f"n{i:02d}" for i in range(NODES)]
        self.seed, self.placement, self.k = seed, placement, round(share * NODES)
        self.building = tuple(sorted(rng.sample(names, BUILDERS))) if builders else None
        others = [n for n in names if n not in (self.building or ())]
        self.start = rng.choice(others)
        if builders == "with":
            chosen = list(self.building) + rng.sample(others, self.k - BUILDERS)
        elif placement == "random":
            chosen = rng.sample(others, self.k)
        else:
            chosen = []
        budgets = {n: HEADROOM for n in chosen}
        rest = [n for n in names if n not in budgets]
        for budget, part in tiers:
            for n in rng.sample(rest, round(part * NODES)):
                budgets[n] = budget
            rest = [n for n in rest if n not in budgets]
        self.liars = tuple(sorted(rng.sample(rest, round(liars * NODES))))
        for n in self.liars:
            budgets[n] = 0  # a liar admits nothing, so it relays and includes nothing
        self.budgets = {n: budgets.get(n, FLOOR) for n in names}

    def pools(self, sim) -> dict:
        if self.placement == "cluster":
            for n in ball(sim, self.start, self.k, set(sim.net.nodes)):
                self.budgets[n] = HEADROOM
        return {n: roomy(b) for n, b in self.budgets.items() if b != FLOOR}


def simulate(setup: Setup, loads: dict[str, tuple[int, Signature, str]], *, resend: bool = False,
             hints: bool = False, remember: bool = False):
    """One run. `loads` names each kind of spend: its budget, its signature, and where its wallets send it."""
    users = {name: [f"{name}-{i}" for i in range(SENDERS)] for name in loads}
    every = [u for us in users.values() for u in us]
    net = NetworkConfig(degree=DEGREE, latency=(0.02, 0.10), arrive_timeout=0.5, announce_budget=hints,
                        remember_budget=300.0 if remember else 0.0, liars=setup.liars)
    sim = Simulation(Scenario(
        seed=setup.seed,
        nodes=NODES,
        network=net,
        chain=ChainConfig(slot_time=SLOT, proposer=setup.building or "rotate", block_delay=(0.1, 1.0),
                          min_tip=MIN_TIP),
        frame_pool=EIP_8141,
        genesis=Head(timestamp=0, gas_limit=GAS_LIMIT, gas_used=GAS_LIMIT // 2, base_fee=BASE_FEE),
        accounts={u: 10**18 for u in every},
        code={u: CODE for u in every},
        frame_pools=setup.pools,
    ))
    made = {}
    honest = [n for n in setup.budgets if n not in setup.liars]
    for name, (budget, sig, where) in loads.items():
        admits = [n for n in honest if setup.budgets[n] >= budget]
        load = WalletLoad(name, rate=RATE, senders=users[name], verify_gas=budget - sig.verify_gas, expiring=0.0,
                          resend=resend, targets=admits if where == "admits" else honest, signature=sig,
                          fresh=True, stop=SEND)
        sim.add_load(load)
        made[name] = (load, set(admits))
    rec = sim.run(RUN)
    return rec, made


def outcome(rec, load, eligible: set[str]) -> dict:
    txs = [rec.txs[tx.hash] for tx in load.txs]
    delays = [r.included_at - r.submitted_at for r in txs if r.included_at is not None]
    reach = [len(set(r.first_seen) & eligible) / len(eligible) for r in txs]
    return {"sent": len(txs), "included": len(delays), "delays": delays, "reach": reach,
            "everywhere": sum(1 for x in reach if x == 1.0),
            "refused": sum(r.results["ErrFrameVerifyGas"] for r in txs), "skipped": sum(r.skipped for r in txs),
            "eligible": len(eligible)}


def pooled(outs: list[dict]) -> dict:
    out = {"sent": sum(o["sent"] for o in outs), "included": sum(o["included"] for o in outs),
           "delays": [d for o in outs for d in o["delays"]], "reach": [x for o in outs for x in o["reach"]],
           "everywhere": sum(o["everywhere"] for o in outs), "refused": sum(o["refused"] for o in outs),
           "skipped": sum(o["skipped"] for o in outs), "eligible": sum(o["eligible"] for o in outs) / len(outs)}
    return out


def row(o: dict) -> list:
    d = o["delays"]
    return [o["sent"], o["included"], percentile(d, 50), percentile(d, 90), max(d) if d else None,
            sum(o["reach"]) / len(o["reach"]), o["everywhere"] / o["sent"], o["refused"] / o["sent"]]


def runs(make, loads, **kwargs) -> dict[str, dict]:
    """`make(seed)` gives a setup; the result pools each load's outcome over the seeds."""
    per: dict[str, list] = {name: [] for name in loads}
    for seed in SEEDS:
        setup = make(seed)
        rec, made = simulate(setup, loads, **kwargs)
        for name, (load, eligible) in made.items():
            per[name].append(outcome(rec, load, eligible))
    return {name: pooled(outs) for name, outs in per.items()}


HEADERS = ["sent", "included", "delay p50", "p90", "max", "reached", "reached all", "refused copies"]


# --- 1. The share of nodes with headroom ----------------------------------------------------------

def section_1() -> tuple[str, dict]:
    loads = {"s": (SPENDS[1], SMALL, "admits"), "f": (FLOOR, SMALL, "any")}
    rows, floor_rows, kept = [], [], {}
    for share in SHARES:
        out = runs(lambda seed: Setup(seed, share), loads)
        kept[share] = out["s"]
        rows.append([share, round(share * NODES)] + row(out["s"]))
        floor_rows.append(row(out["f"]))
    sent = {r[0] for r in floor_rows}
    assert len(sent) == 1  # the same spends at every share
    landed = (f"all {floor_rows[0][0]}" if all(r[1] == r[0] for r in floor_rows)
              else f"between {min(r[1] for r in floor_rows)} and {max(r[1] for r in floor_rows)}")

    def span(i: int) -> str:
        lo, hi = min(r[i] for r in floor_rows), max(r[i] for r in floor_rows)
        return f"{lo:.2f}" if f"{lo:.2f}" == f"{hi:.2f}" else f"between {lo:.2f} and {hi:.2f}"
    resent = []
    for share in RESEND_SHARES:
        out = runs(lambda seed: Setup(seed, share), {"s": loads["s"]}, resend=True)
        resent.append([share, round(share * NODES)] + row(out["s"]))
    lines = [
        "## 1. The share of nodes with headroom",
        "",
        f"A network of {NODES} nodes, {DEGREE} peers each, a block every {SLOT} s from a proposer that rotates "
        f"through every node, gas limit {GAS_LIMIT}. Every node runs `eip-8141` with `max_verify_gas` at the "
        f"floor, {FLOOR}, except the share in the table, drawn at random, which admits up to {HEADROOM}. "
        f"Wallets send spends whose structural rule 6 budget is {SPENDS[1]}, the single-nullifier spend of topic "
        f"25889, its proof in a {SMALL.length}-byte ARBITRARY entry, each from a sender of its own, at "
        f"{RATE * SLOT:.0f} a slot for the first {SEND:.0f} s of a {RUN:.0f} s run, to a random node with "
        "headroom, which is where a wallet that tries random nodes until one accepts ends up; they send each "
        f"once. Rows pool {len(SEEDS)} runs, seeds {', '.join(map(str, SEEDS))}, each with its own topology and "
        "placement. Delays are from sending to inclusion, in seconds, over the spends included in the run; "
        "reached is the mean share of the nodes with headroom that held a spend pending, reached all the share "
        "of spends that reached every one, and refused copies the mean number of times a node was handed a "
        "spend and refused it as `ErrFrameVerifyGas`.",
        "",
        table(["share", "nodes with headroom"] + HEADERS, rows),
        "",
        f"The same runs carried spends at the floor, a budget of {FLOOR}, sent to random nodes. At every share, "
        f"{landed} were included, with a delay p50 {span(2)} s, p90 {span(3)} and max "
        f"{span(4)}, and reached a share of the nodes {span(5)} on average.",
        "",
        "With wallets that send again, after every block that leaves the spend out, to another random node with "
        "headroom:",
        "",
        table(["share", "nodes with headroom"] + HEADERS, resent),
    ]
    return "\n".join(lines), kept


# --- 2. Where the headroom sits ------------------------------------------------------------------

def section_2(kept: dict) -> str:
    loads = {"s": (SPENDS[1], SMALL, "admits")}
    rows = []
    for share in PLACED_SHARES:
        rows.append(["random", "every node", share] + row(kept[share]))
        for label, make in (
            ("one cluster", lambda seed: Setup(seed, share, placement="cluster")),
            ("random, not at builders", lambda seed: Setup(seed, share, builders="without")),
            ("at builders first", lambda seed: Setup(seed, share, builders="with")),
        ):
            out = runs(make, loads)
            rows.append([label, "every node" if "builders" not in label else f"{BUILDERS} builders", share]
                        + row(out["s"]))
    lines = [
        "## 2. Where the headroom sits",
        "",
        "Section 1's spends and network, with the same share of nodes with headroom placed differently: at "
        "random, as in section 1; as one cluster, the first nodes a breadth-first walk from a random node meets; "
        f"or with blocks built only by {BUILDERS} nodes, drawn at random, in turn, and the headroom either "
        "elsewhere, at random, or at those builders first and the rest at random. A share of "
        f"{PLACED_SHARES[0]} at builders first is the builders alone.",
        "",
        table(["headroom", "blocks built by", "share"] + HEADERS, rows),
    ]
    return "\n".join(lines)


# --- 3. A gradient -------------------------------------------------------------------------------

def section_3() -> str:
    loads = {f"g{nu}": (budget, SMALL, "admits") for nu, budget in SPENDS.items()}
    out = runs(lambda seed: Setup(seed, tiers=TIERS), loads)
    rows = []
    for nu, budget in SPENDS.items():
        o = out[f"g{nu}"]
        rows.append([nu, budget, round(o["eligible"])] + row(o)[:7])
    tiers = ", ".join(f"{part:.0%} at {budget}" for budget, part in TIERS)
    lines = [
        "## 3. A gradient of headroom",
        "",
        f"Section 1's network with headroom in tiers: {tiers}, drawn at random, and the remaining "
        f"{1 - sum(p for _, p in TIERS):.0%} at the floor. The tiers are the values topic 25889's recommendation "
        "table names; the shares are this experiment's choice. Wallets send spends of 1, 2, 8 and 16 "
        "nullifiers, with topic 25889's budgets, each kind at the rate of section 1 and to a random node that "
        "admits it. Reached is the mean share of the nodes that admit a spend that held it pending.",
        "",
        table(["nullifiers", "budget", "nodes that admit it"] + HEADERS[:7], rows),
    ]
    return "\n".join(lines)


# --- 4. Budget hints -----------------------------------------------------------------------------

def section_4() -> str:
    loads = {"as": (SPENDS[1], SMALL, "admits"), "al": (SPENDS[1], LARGE, "admits"),
             "fs": (FLOOR, SMALL, "any"), "fl": (FLOOR, LARGE, "any")}
    kinds = {"as": ("above the floor", "pushed"), "al": ("above the floor", "announced"),
             "fs": ("at the floor", "pushed"), "fl": ("at the floor", "announced")}
    saved = []
    for hints in (False, True):
        out = runs(lambda seed: Setup(seed, HINT_SHARE), loads, hints=hints)
        for k in ("as", "al"):
            o = out[k]
            saved.append(["yes" if hints else "no", *kinds[k], o["refused"] / o["sent"], o["skipped"] / o["sent"],
                          percentile(o["delays"], 50), sum(o["reach"]) / len(o["reach"])])
    lied = []
    for share in LIAR_SHARES:
        for label, kwargs in (("keep quiet", {}), ("lie, forgotten", {"hints": True}),
                              ("lie, remembered", {"hints": True, "remember": True})):
            out = runs(lambda seed: Setup(seed, HINT_SHARE, liars=share), loads, **kwargs)
            for k in ("as", "al", "fs", "fl"):
                o = out[k]
                d = o["delays"]
                lied.append([share, label, *kinds[k], o["sent"], o["included"], percentile(d, 50),
                             percentile(d, 90), sum(o["reach"]) / len(o["reach"]), o["everywhere"] / o["sent"]])
    lines = [
        "## 4. Budget hints",
        "",
        f"Section 1's network with {HINT_SHARE:.0%} of nodes at random with headroom. Each run carries four "
        f"kinds of spend: budgets of {SPENDS[1]} and of {FLOOR}, each with a {SMALL.length}-byte proof, which a "
        f"node pushes to some peers in full, and with a {LARGE.length}-byte one, over go-ethereum's "
        "4096-byte `txMaxBroadcastSize`, which it only announces. Spends above the floor go to a random node with "
        "headroom, spends at the floor to a random honest node. With hints, every announcement carries the "
        "spend's rule 6 budget, and a node does not fetch a spend announced above its own `max_verify_gas`; it "
        "does not refuse what it is pushed.",
        "",
        "What hints save, against the same runs without them: refused copies and announcements not fetched, per "
        "spend.",
        "",
        table(["hints", "spend", "sent as", "refused copies", "not fetched", "delay p50", "reached"], saved),
        "",
        "Nodes that do not want spends to travel, drawn at random from those at the floor, in the share the table "
        "names: they admit nothing, so they relay nothing, and the blocks they propose carry no spend. Without "
        "hints that is all they can do "
        "(*keep quiet*). With hints they announce every spend they hear of to every peer with a budget above "
        "any node's (*lie*), and a node that hears the lie either forgets it once it has not fetched (*lie, "
        "forgotten*) or, as it does an underpriced transaction, ignores every announcement of the spend for "
        "300 s (*lie, remembered*). Reached is the mean share of the honest nodes that admit a spend that held it "
        "pending.",
        "",
        table(["liars", "they", "spend", "sent as", "sent", "included", "delay p50", "p90", "reached",
               "reached all"], lied),
    ]
    return "\n".join(lines)


def main() -> None:
    print("# 08. The verification gas floor: results")
    print()
    print(f"Generated by `experiments/08-verify-floor/run.py`, seeds {', '.join(map(str, SEEDS))}, {NODES} nodes, "
          f"{DEGREE} peers each, {SLOT} s slots, gas limit {GAS_LIMIT}, {RUN:.0f} s a run, frame pool profile "
          f"`eip-8141` with `max_verify_gas` set per node. Do not edit by hand.")
    print()
    text, kept = section_1()
    print(text)
    print()
    print(section_2(kept))
    print()
    print(section_3())
    print()
    print(section_4())


if __name__ == "__main__":
    main()
