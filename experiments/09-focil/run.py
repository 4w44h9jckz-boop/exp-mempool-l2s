#!/usr/bin/env python3
"""Experiment 09: inclusion lists and builders that filter. Prints results.md on standard output.

A share of the builders leaves out a set of senders' transactions. Without
inclusion lists, such a transaction waits for a builder that does not filter.
With them (EIP-7805, `docs/spec/07-focil.md`), a committee lists it and a
block that leaves it out while it would fit is not canonical, so a filtering
builder has to buy the gas that excuses it, lose the slot, or give up. This
measures the delay of a filtered transaction and what filtering costs the
builder, by the share that filters, the share of includers that filter too,
whether blocks are full, and for private spends whose
validation only EIP-8369's Profile 2 enforces. Decision record 0018.
"""

from __future__ import annotations

import random
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "ref" / "python"), str(ROOT / "sim")]

from emem import EIP_8141, FOCIL_PROFILES, Head, Signature  # noqa: E402
from emem_sim import (ChainConfig, NetworkConfig, Scenario, Simulation, TransferLoad, WalletLoad,  # noqa: E402
                      percentile, run_all, table)

SEEDS = (1, 2, 3)  # each draws its own topology, latencies, placement and arrivals
NODES = 100
DEGREE = 8
SLOT = 12
GAS_LIMIT = 30_000_000
BASE_FEE = 1_000_000_000
MIN_TIP = 1_000_000  # BB-1, go-ethereum's miner default
RUN = 900.0
SEND = 450.0  # transfers and spends are sent for the first 450 s of a run
BUILDERS = 10  # the nodes that build every block, in turn

BACKGROUND_GAS = 1_000_000
BACKGROUND_RATE = GAS_LIMIT / 2 / BACKGROUND_GAS / SLOT  # the gas target, on average, for the whole run
HONEST_RATE = 0.5  # 21,000-gas transfers a second
TARGET_RATE = 1 / 6  # filtered transactions a second, two a slot
PULSE = (240.0, 390.0)  # section 3: when the extra demand is sent
PULSE_RATE = 3.0  # section 3: extra 1,000,000-gas transfers a second
HIGH_TIP = 10_000_000_000  # section 3: above every tip the wallets draw, which is at most 3 gwei
DRAWN = (1_000_000, 3_000_000_000)  # the tips every wallet draws from (`Load`)
WEI_PER_ETH = 10**18

SHARES = (0.0, 0.5, 0.9, 1.0)
INCLUDER_SHARES = (0.5, 0.9, 0.97)
SPEND = 211_828  # ethresear.ch topic 25889's single-nullifier spend, as in experiment 08
FLOOR = EIP_8141.max_verify_gas  # 100,000
HEADROOM = 250_000
HEADROOM_SHARE = 0.1
SMALL = Signature(scheme="arbitrary", length=256)
CODE = "verifier"


@dataclass(frozen=True)
class Run:
    seed: int
    focil: str = "off"
    share: float = 0.0  # of the builders, which filter
    strategy: str = "yield"
    includers: float = 0.0  # share of every node that filters as an includer
    policy: str = "fee"
    pulse: bool = False
    tip: int | None = None  # the filtered transfers' tip, or the wallets' draw
    gas: int = 21_000  # the filtered transfers' gas
    spends: str = ""  # "" for filtered transfers; "filtered" or "floor" for section 4's spends


def placement(run: Run) -> tuple[tuple[str, ...], frozenset[str], frozenset[str], frozenset[str]]:
    """The builders, those that filter, the includers that filter and the nodes with headroom."""
    rng = random.Random(f"{run.seed}/placement")
    names = [f"n{i:02d}" for i in range(NODES)]
    builders = tuple(sorted(rng.sample(names, BUILDERS)))
    filtering = frozenset(rng.sample(builders, round(run.share * BUILDERS)))
    includers = frozenset(rng.sample(names, round(run.includers * NODES)))
    others = [n for n in names if n not in builders]
    headroom = frozenset(rng.sample(others, round(HEADROOM_SHARE * NODES)))
    return builders, filtering, includers, headroom


def high(tip: int):
    """A fixed tip that still takes the draw a wallet's tip would, so that arrivals stay those of every row."""
    return lambda rng: (rng.randint(*DRAWN), tip)[1]


def one(run: Run) -> dict:
    """One simulation, summarised."""
    builders, filtering, includers, headroom = placement(run)
    prefix = "p-" if run.spends else "c-"
    honest = [f"h-{i}" for i in range(400)]
    background = [f"g-{i}" for i in range(4000)]
    pulse = [f"u-{i}" for i in range(2000)]
    targets = [f"{prefix}{i}" for i in range(200)]
    accounts = {a: 10**21 for a in honest + background + pulse + targets}
    accounts.update({b: 10**24 for b in builders})  # enough to stuff every block of a run
    roomy = EIP_8141.with_(max_verify_gas=HEADROOM)
    if run.spends == "floor":
        frame_pools = lambda sim: {n: roomy for n in headroom}  # noqa: E731
    elif run.spends == "filtered":
        frame_pools = lambda sim: {n: roomy for n in sim.net.nodes}  # noqa: E731
    else:
        frame_pools = None
    chain = ChainConfig(slot_time=SLOT, proposer=builders, block_delay=(0.1, 1.0), min_tip=MIN_TIP,
                        focil=FOCIL_PROFILES[run.focil].with_(policy=run.policy),
                        censored=lambda tx: tx.sender.startswith(prefix), filtering=filtering,
                        filtering_includers=includers, strategy=run.strategy)
    sim = Simulation(Scenario(
        seed=run.seed,
        nodes=NODES,
        network=NetworkConfig(degree=DEGREE, latency=(0.02, 0.10), arrive_timeout=0.5),
        chain=chain,
        genesis=Head(timestamp=0, gas_limit=GAS_LIMIT, gas_used=GAS_LIMIT // 2, base_fee=BASE_FEE),
        accounts=accounts,
        code={a: CODE for a in targets} if run.spends else {},
        frame_pools=frame_pools,
    ))
    sim.add_load(TransferLoad("background", BACKGROUND_RATE, background, gas=BACKGROUND_GAS, stop=RUN))
    sim.add_load(TransferLoad("honest", HONEST_RATE, honest, stop=SEND))
    if run.pulse:
        sim.add_load(TransferLoad("pulse", PULSE_RATE, pulse, gas=BACKGROUND_GAS, start=PULSE[0], stop=PULSE[1]))
    if run.spends:
        sent_to = sorted(headroom) if run.spends == "floor" else None
        sim.add_load(WalletLoad("spends", rate=TARGET_RATE, senders=targets, verify_gas=SPEND - SMALL.verify_gas,
                                expiring=0.0, targets=sent_to, signature=SMALL, fresh=True, stop=SEND))
    else:
        tip = {} if run.tip is None else {"tip": high(run.tip)}
        sim.add_load(TransferLoad("filtered", TARGET_RATE, targets, gas=run.gas, stop=SEND, **tip))
    rec = sim.run(RUN)

    def kind(p: str) -> list:
        return [r for r in rec.txs.values() if r.tx.sender.startswith(p)]
    slots = [s for s in rec.blocks + rec.missed_slots if s.get("filtering")]
    return {
        "target": [(r.submitted_at, r.included_at, r.listed) for r in kind(prefix)],
        "honest": [(r.submitted_at, r.included_at) for r in kind("h-")],
        "background": [(r.submitted_at, r.included_at) for r in kind("g-")],
        "slots": [(s["at"], s["honest_tips"], s["tips"], s["burn"], "stuffed" in s, "yielded" in s,
                   "number" not in s, s["left"]) for s in slots],
        "blocks": len(rec.blocks),
        "missed": len(rec.missed_slots),
        "base_fees": [b["base_fee"] for b in rec.blocks],
    }


# --- Pooling ---------------------------------------------------------------------------------------

def delays(pairs: list, since: tuple[float, float] | None = None) -> tuple[int, list[float]]:
    sent = [p for p in pairs if since is None or since[0] <= p[0] < since[1]]
    return len(sent), [p[1] - p[0] for p in sent if p[1] is not None]


def eth(wei: float) -> str:
    return f"{wei / WEI_PER_ETH:.3g}"


def cost(slots: list) -> float:
    return sum(h - t + b for _, h, t, b, *_ in slots)


def target_cells(outs: list[dict], since=None) -> list:
    sent, d = 0, []
    listed = 0
    for o in outs:
        n, ds = delays([(a, b) for a, b, _ in o["target"]], since)
        sent, d = sent + n, d + ds
        listed += sum(1 for a, _, k in o["target"] if k and (since is None or since[0] <= a < since[1]))
    return [sent, len(d), percentile(d, 50), percentile(d, 90), max(d) if d else None, listed / sent if sent else None]


def honest_p50(outs: list[dict]) -> float | None:
    return percentile([d for o in outs for d in delays(o["honest"])[1]], 50)


def background_share(outs: list[dict]) -> float:
    sent = [p for o in outs for p in o["background"] if p[0] < SEND]
    return sum(1 for p in sent if p[1] is not None) / len(sent)


def slot_cells(outs: list[dict], since=None) -> list:
    """Over the slots a filtering builder was due: how many, how many it stuffed, yielded and missed, and what
    filtering cost it in all and as a share of the priority fees honest blocks would have paid it."""
    slots = [s for o in outs for s in o["slots"] if since is None or since[0] <= s[0] < since[1]]
    honest = sum(s[1] for s in slots)
    return [len(slots), sum(s[4] for s in slots), sum(s[5] for s in slots), sum(s[6] for s in slots),
            eth(cost(slots)), cost(slots) / honest if honest else None]


def base_fee_cells(outs: list[dict]) -> list:
    peak = max(max(o["base_fees"]) for o in outs)
    last = sorted(o["base_fees"][-1] for o in outs)[len(outs) // 2]
    return [f"{peak / 1e9:.3g}", f"{last / 1e9:.3g}"]


# --- The runs --------------------------------------------------------------------------------------

def section_1_runs() -> list[list[Run]]:
    rows = []
    for share in SHARES:
        rows.append(("off", share, "", Run(0, "off", share)))
        strategies = ("yield",) if share == 0 else ("stuff", "miss", "yield", "cheapest")
        for strategy in strategies:
            if share == 1.0 and strategy == "yield":
                continue  # with no builder to yield to it is `miss`
            rows.append(("eip-7805", share, strategy if share else "", Run(0, "eip-7805", share, strategy)))
    return rows


def section_2_runs() -> list:
    return [(share, Run(0, "eip-7805", 0.9, "yield", includers=share)) for share in INCLUDER_SHARES]


def section_3_runs() -> list:
    rows = [("off", "", "drawn", 21_000, "fee", Run(0, "off", 0.9, pulse=True))]
    for strategy in ("stuff", "yield", "cheapest"):
        rows.append(("eip-7805", strategy, "drawn", 21_000, "fee", Run(0, "eip-7805", 0.9, strategy, pulse=True)))
    rows.append(("eip-7805", "cheapest", "high", 21_000, "fee",
                 Run(0, "eip-7805", 0.9, "cheapest", pulse=True, tip=HIGH_TIP)))
    rows.append(("eip-7805", "cheapest", "drawn", BACKGROUND_GAS, "fee",
                 Run(0, "eip-7805", 0.9, "cheapest", pulse=True, gas=BACKGROUND_GAS)))
    rows.append(("eip-7805", "cheapest", "drawn", 21_000, "age",
                 Run(0, "eip-7805", 0.9, "cheapest", policy="age", pulse=True)))
    return rows


def section_4_runs() -> list:
    rows = []
    for focil in ("off", "eip-7805", "eip-8369"):
        rows.append(("filtered", focil, Run(0, focil, 0.9, "yield", spends="filtered")))
    for focil in ("off", "eip-8369"):
        rows.append(("floor", focil, Run(0, focil, 0.0, spends="floor")))
    return rows


def seeded(run: Run) -> list[Run]:
    return [Run(seed, *(getattr(run, f) for f in list(Run.__dataclass_fields__)[1:])) for seed in SEEDS]


# --- The sections ----------------------------------------------------------------------------------

def section_1(rows, out) -> str:
    body = []
    for focil, share, strategy, run in rows:
        o = out[run]
        body.append([focil, share, strategy] + target_cells(o) + [honest_p50(o), background_share(o)]
                    + slot_cells(o)[:4] + slot_cells(o)[4:] + base_fee_cells(o))
    lines = [
        "## 1. The share of builders that filter",
        "",
        f"A network of {NODES} nodes, {DEGREE} peers each, a block every {SLOT} s, gas limit {GAS_LIMIT}. Blocks "
        f"are built by {BUILDERS} of the nodes, drawn at random, in turn; the share in the table of those, drawn "
        f"at random, filter. Three loads: background {BACKGROUND_GAS}-gas transfers at {BACKGROUND_RATE * SLOT:.0f} "
        f"a slot for the whole {RUN:.0f} s run, the gas target on average; honest 21000-gas transfers at "
        f"{HONEST_RATE * SLOT:.0f} a slot; and filtered 21000-gas transfers at {TARGET_RATE * SLOT:.0f} a slot, "
        f"from senders that every filtering builder leaves out. The last two are sent for the first {SEND:.0f} s; "
        "every wallet draws its tip from 0.001 to 3 gwei, caps its fee at twice the next base fee plus the tip, "
        "sends to a random node, and sends once. Under `eip-7805` a committee of 16 nodes, drawn each slot, lists "
        "by fee 8 s into the slot, and a filtering builder whose block would leave a listed transaction out "
        "follows its strategy: *stuff* buys the gas that excuses it, *miss* loses the slot, *yield* lets the next "
        "builder in turn that does not filter build it, *cheapest* stuffs when the stuffed block's tips cover "
        f"the burn and yields otherwise. Rows pool {len(SEEDS)} runs, seeds {', '.join(map(str, SEEDS))}.",
        "",
        "Delays are from sending to inclusion, in seconds, over the transactions included; listed is the share "
        "of filtered transactions any includer listed. Honest p50 is the honest transfers' delay, background "
        f"included the share of background transfers sent in the first {SEND:.0f} s that were included by the end "
        "of the run. Slots are those a filtering "
        "builder was due, with how many it stuffed, yielded and missed, and what filtering cost it: the priority "
        "fees of the block it would have built honestly from the same pool and lists, less those it was paid, "
        "plus the base fee it burned, in ETH and as a share of those honest fees. Base fees are in gwei: the "
        "highest in any run, and the median of the runs' last.",
        "",
        table(["profile", "share", "strategy", "sent", "included", "delay p50", "p90", "max", "listed",
               "honest p50", "background included", "slots", "stuffed", "yielded", "missed", "cost, ETH",
               "cost share", "base fee peak", "base fee last"], body),
    ]
    return "\n".join(lines)


def section_2(rows, out, reference) -> str:
    body = [["0.00 (section 1)"] + target_cells(out[reference]) + slot_cells(out[reference])]
    for share, run in rows:
        body.append([share] + target_cells(out[run]) + slot_cells(out[run]))
    lines = [
        "## 2. Includers that filter too",
        "",
        "Section 1's network under `eip-7805`, with 0.9 of the builders filtering and yielding, and the share of "
        "all nodes in the table, drawn at random, leaving the filtered transfers out of the lists they build "
        "when drawn to the committee.",
        "",
        table(["includers that filter", "sent", "included", "delay p50", "p90", "max", "listed", "slots",
               "stuffed", "yielded", "missed", "cost, ETH", "cost share"], body),
    ]
    return "\n".join(lines)


def section_3(rows, out) -> str:
    body, costs = [], []
    window = (PULSE[0], SEND)
    for focil, strategy, tip, gas, policy, run in rows:
        o = out[run]
        label = [focil, strategy, tip, gas, policy]
        body.append(label + target_cells(o, PULSE))
        due = [s for x in o for s in x["slots"] if window[0] <= s[0] < window[1]]
        inside, outside = slot_cells(o, window), slot_cells(o, (0, window[0]))
        costs.append(label + [sum(1 for s in due if s[7] < gas) / len(due)] + inside[:5]
                     + [inside[5], outside[0], outside[4], outside[5]])
    lines = [
        "## 3. Full blocks",
        "",
        f"Section 1's network with 0.9 of the builders filtering, and extra demand: {BACKGROUND_GAS}-gas transfers "
        f"at {PULSE_RATE * SLOT:.0f} a slot from {PULSE[0]:.0f} s to {PULSE[1]:.0f} s, priced as every wallet "
        f"prices. The filtered transfers either draw their tip as every wallet does or pay {HIGH_TIP / 1e9:.0f} "
        "gwei, above any other tip, with the same arrivals, and are either 21000-gas transfers or as large as "
        "the demand's. One row's includers list by age rather than by fee. The first table is over the filtered "
        f"transactions sent during the extra demand, from {PULSE[0]:.0f} s to {PULSE[1]:.0f} s.",
        "",
        table(["profile", "strategy", "tip", "gas", "lists by", "sent", "included", "delay p50", "p90", "max",
               "listed"], body),
        "",
        f"What filtering cost, in the slots a filtering builder was due from {window[0]:.0f} s until sending "
        f"stopped at {window[1]:.0f} s, and before {window[0]:.0f} s. Full is the share of those slots in the "
        "window in which the block the builder built without the filtered transactions, before it did anything "
        "about the lists, left less gas unused than a filtered transaction needs, so that IL-6 excused leaving "
        "one out.",
        "",
        table(["profile", "strategy", "tip", "gas", "lists by", "full", "slots", "stuffed", "yielded", "missed",
               "cost, ETH", "cost share", "slots before", "cost before, ETH", "cost share before"], costs),
    ]
    return "\n".join(lines)


def section_4(rows, out) -> str:
    body = []
    for spends, focil, run in rows:
        o = out[run]
        body.append([spends, focil] + target_cells(o) + [honest_p50(o)])
    lines = [
        "## 4. Private spends",
        "",
        f"Section 1's network and loads, with the filtered transfers replaced by spends: self-paying frame "
        f"transactions whose structural rule 6 budget is {SPEND}, topic 25889's single-nullifier spend as in "
        f"experiment 08, the proof in a {SMALL.length}-byte ARBITRARY entry, each from a sender of its own, at "
        f"{TARGET_RATE * SLOT:.0f} a slot for the first {SEND:.0f} s, sent once. *Filtered*: every node admits up "
        f"to {HEADROOM}, every spend goes to a random node, and 0.9 of the builders leave spends out and yield. "
        f"*Floor*: experiment 08's regime, with every node at the floor, {FLOOR}, except {HEADROOM_SHARE:.0%} of "
        f"the nodes, drawn at random from those that do not build, which admit up to {HEADROOM}; every spend goes "
        "to one of those, and no builder filters. Under `eip-8369` includers list a spend as a Profile 2 "
        "candidate within their list's budget (IL-2 to IL-4); `eip-7805` lists no frame transaction.",
        "",
        table(["spends", "profile", "sent", "included", "delay p50", "p90", "max", "listed", "honest p50"], body),
    ]
    return "\n".join(lines)


def main() -> None:
    s1, s2, s3, s4 = section_1_runs(), section_2_runs(), section_3_runs(), section_4_runs()
    templates = [r[-1] for r in s1 + s2 + s3 + s4]
    runs = [run for t in templates for run in seeded(t)]
    results = dict(zip(runs, run_all(one, runs)))
    out = {t: [results[run] for run in seeded(t)] for t in templates}
    reference = next(r[-1] for r in s1 if r[0] == "eip-7805" and r[1] == 0.9 and r[2] == "yield")
    print("# 09. Inclusion lists and builders that filter: results")
    print()
    print(f"Generated by `experiments/09-focil/run.py`, seeds {', '.join(map(str, SEEDS))}, {NODES} nodes, "
          f"{DEGREE} peers each, {SLOT} s slots, gas limit {GAS_LIMIT}, {RUN:.0f} s a run, {BUILDERS} builders. "
          "Do not edit by hand.")
    print()
    print(section_1(s1, out))
    print()
    print(section_2(s2, out, reference))
    print()
    print(section_3(s3, out))
    print()
    print(section_4(s4, out))


if __name__ == "__main__":
    main()
