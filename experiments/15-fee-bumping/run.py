#!/usr/bin/env python3
"""Experiment 15: wallets that bump fees, and users who stop paying. Prints results.md on standard output.

Experiment 00 found that the backlog a burst leaves does not unwind, because
its wallets never re-price a transaction the base fee has passed. This runs
the same network and burst with wallets that replace such a transaction, and
users who do not pay above a price, and measures how fast the backlog clears,
what it costs, and what a shared sender under FP-12's `one` does when its
stranded spend can be re-priced only by its own user (experiment 01, "What
it does not show"). Decision record 0024.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "ref" / "python"), str(ROOT / "sim")]

from emem import Head  # noqa: E402
from emem_sim import (BumpLoad, ChainConfig, FrameLoad, NetworkConfig, Scenario, SharedSenderLoad,  # noqa: E402
                      Simulation, percentile, run_all, table, uniform)

SEEDS = (1, 2, 3, 4, 5)  # experiment 00 ran seed 1 only
NODES = 30
GAS_LIMIT = 2_100_000  # 100 plain transfers; the target is 50
QUIET, BURST = 2.5, 12.0  # transfers a second, as in experiment 00
PHASES = [("quiet", 0, 600), ("burst", 600, 900), ("after", 900, 1800)]
RUN = 1800
GWEI = 1_000_000_000
WALLETS = {  # label: (patience in blocks, reprice, every pending transaction rather than the oldest)
    "never": (None, False, False),
    "oldest, 10% after 1 block": (1, False, False),
    "oldest, 10% after 3 blocks": (3, False, False),
    "every one, 10% after 1 block": (1, False, True),
    "oldest, to the market after 1 block": (1, True, False),
    "oldest, to the market after 3 blocks": (3, True, False),
    "every one, to the market after 1 block": (1, True, True),
}
MARKET = "oldest, to the market after 1 block"  # the wallets sections 2 and 3 set against never
LIMITS = {  # label: the range a user's most a gas is drawn from, in gwei
    "none": None,
    "1 to 10 gwei": (1, 10),
    "0.5 to 3 gwei": (0.5, 3),
}
SPEND_RATE = 1 / 36  # section 3: spends a second through the shared sender, a third of `one`'s ceiling
SPENDERS = {"never": (None, False), "10% after 3 blocks": (3, False), "to the market after 1 block": (1, True)}


@dataclass(frozen=True)
class Run:
    seed: int
    wallet: str = "never"
    limit: str = "none"
    spender: str | None = None  # section 3: how the shared sender's users re-price


def one(run: Run) -> dict:
    """One simulation, summarised."""
    plain = [f"p{i:03d}" for i in range(400)]
    framed = [f"f{i:03d}" for i in range(100)]
    pool = ["pool"] if run.spender is not None else []
    sim = Simulation(Scenario(
        seed=run.seed,
        nodes=NODES,
        network=NetworkConfig(degree=8, latency=(0.02, 0.10), arrive_timeout=0.5),
        chain=ChainConfig(slot_time=12, proposer="rotate", block_delay=(0.1, 1.0)),
        genesis=Head(timestamp=0, gas_limit=GAS_LIMIT, gas_used=GAS_LIMIT // 2, base_fee=GWEI),
        accounts={a: 10**21 for a in plain + framed} | {p: 10**24 for p in pool},
        code={p: "privacy-pool" for p in pool},
    ))
    patience, reprice, every = WALLETS[run.wallet]
    span = LIMITS[run.limit]
    limit = uniform(int(span[0] * GWEI), int(span[1] * GWEI)) if span else None
    kw = dict(patience=patience, reprice=reprice, every=every, limit=limit)
    loads = [BumpLoad("quiet", QUIET, plain, stop=PHASES[0][2], **kw),
             BumpLoad("burst", BURST, plain, start=PHASES[1][1], stop=PHASES[1][2], **kw),
             BumpLoad("after", QUIET, plain, start=PHASES[2][1], **kw)]
    for load in loads:
        sim.add_load(load)
    sim.add_load(FrameLoad("frames", rate=0.2, senders=framed))
    spends = None
    if run.spender is not None:
        sp_patience, sp_reprice = SPENDERS[run.spender]
        spends = SharedSenderLoad("spend", SPEND_RATE, pool, rule="relayer", serial=True, patience=sp_patience,
                                  reprice=sp_reprice, stop=PHASES[2][2] - 300)
        sim.add_load(spends)
    rec = sim.run(RUN)
    fees = {b["number"]: b["base_fee"] for b in rec.blocks}

    def landing(versions):
        """When the first version of these was included, and the gas price it paid."""
        hits = [(rec.txs[v.hash].included_at, v) for v in versions if rec.txs[v.hash].included_at is not None]
        if not hits:
            return None, None
        at, v = min(hits, key=lambda h: h[0])
        base = fees[rec.txs[v.hash].block]
        return at, base + min(v.tip, v.max_fee - base)

    phases = {}
    for load, (name, _, _) in zip(loads, PHASES):
        rows = []
        for t in load.transfers:
            at, price = landing(t.versions)
            rows.append((None if at is None else at - t.requested_at, price, len(t.versions) - 1))
        phases[name] = {"asked": len(load.transfers) + load.priced_out, "priced_out": load.priced_out, "rows": rows}
    node = sim.net.nodes["n00"]
    base_fee = sim.chain.head.next_base_fee()
    pending, _ = node.pool.content()
    senders = set(plain)
    stuck = sum(any(tx.max_fee < base_fee for tx in txs) for sender, txs in pending.items() if sender in senders)
    after = [s for s in rec.samples if s["at"] > PHASES[1][2]]
    quiet = [s["pending_mean"] for s in rec.samples if s["at"] <= PHASES[0][2]]
    level = max(quiet)
    cleared = next((s["at"] - PHASES[1][2] for s in after if s["pending_mean"] <= level), None)
    out = {
        "phases": phases,
        "stuck": stuck,
        "pool_end": rec.samples[-1]["pending_mean"],
        "base_fee_end": base_fee,
        "base_fee_peak": max(fees.values()),
        "cleared": cleared,
        "refused": sum(sum(load.answers.values()) - load.answers["ok"] for load in loads),
    }
    if spends is not None:
        times, rows = [], []
        for sp in spends.spends:
            versions = sp.versions
            at, price = landing(versions) if versions else (None, None)
            rows.append((None if at is None else at - sp.requested_at, len(versions) - 1 if versions else 0))
            if at is not None:
                times.append(at)
        times.sort()
        if len(times) < len(spends.spends):  # a spend that never landed holds the sender to the end of the run
            times.append(RUN)
        gaps = [b - a for a, b in zip(times, times[1:])]
        out["spends"] = {"rows": rows, "longest": max(gaps) if gaps else None}
    return out


def setup() -> str:
    return (f"Experiment 00's network and demand: {NODES} nodes, 8 peers each, link latency 20 to 100 ms, a block "
            f"every 12 s from a proposer that rotates through every node, gas limit {GAS_LIMIT} (100 transfers, a "
            f"target of 50), base fee from 1 gwei; 400 senders of plain transfers at {QUIET} a second from 0 to "
            f"{PHASES[0][2]} s, {BURST} a second to {PHASES[1][2]} s and {QUIET} a second to {RUN} s, and 100 of "
            "frame transactions at 0.2 a second. Each sender's wallet sends to one node, drawn when it first sends, "
            "with a tip uniform in 0.001 to 3 gwei and a fee cap of twice the next base fee plus the tip. A wallet "
            "that bumps replaces its oldest pending transaction, or every one, after the given number of blocks its "
            "node imports without it, raising tip and fee cap by 10%, the least NP-11 admits, and to the market "
            "raises the fee cap further to twice the next base fee plus the new tip. Rows pool five runs, seeds 1 "
            "to 5. Experiment 00 sent each transfer to a random node, so its run and seed 1 with wallets that never "
            "bump are close but not the same.")


def phase_cells(outs, name):
    rows = [r for o in outs for r in o["phases"][name]["rows"]]
    delays = [d for d, _, _ in rows if d is not None]
    return [len(rows), len(delays), percentile(delays, 50), percentile(delays, 90), percentile(delays, 99)]


def mean(xs, fmt="{:.2f}"):
    xs = [x for x in xs if x is not None]
    return fmt.format(sum(xs) / len(xs)) if xs else "-"


def spread(xs, fmt="{:.2f}"):
    """Mean, and the range over runs."""
    xs = [x for x in xs if x is not None]
    if not xs:
        return "-"
    return f"{fmt.format(sum(xs) / len(xs))} ({fmt.format(min(xs))} to {fmt.format(max(xs))})"


def cleared(outs) -> str:
    done = [o["cleared"] for o in outs if o["cleared"] is not None]
    return f"{len(done)} of {len(outs)}" + (f", {max(done):.0f} s at most" if done else "")


def section_1(out) -> str:
    rows = []
    for wallet in WALLETS:
        outs = out[(wallet, "none", None)]
        burst = [r for o in outs for r in o["phases"]["burst"]["rows"]]
        prices = [p for _, p, _ in burst if p is not None]
        rows.append([wallet, *phase_cells(outs, "burst")[1:], *phase_cells(outs, "after")[2:],
                     mean([b for _, _, b in burst]), mean([p / GWEI for p in prices]),
                     spread([o["stuck"] for o in outs], "{:.0f}"), spread([o["pool_end"] for o in outs], "{:.0f}"),
                     spread([o["base_fee_end"] / GWEI for o in outs]), cleared(outs)])
    return "\n".join([
        "## 1. Wallets that bump",
        "",
        setup(),
        "",
        "Delays are in seconds from a user's asking to the block that included any version of its transfer, for "
        "transfers asked for in the burst and after it. Replacements and the gas price paid, in gwei, are means "
        "over the burst's transfers. Stuck senders are node n00's senders of plain transfers with a pending "
        "transaction whose fee cap is below the next base fee after the last block, as in experiment 00; they, the "
        "pool, which is pending transactions per node, and the base fee are at the end of the run, as a mean and "
        "the range over runs. Cleared is the runs in which the pool fell back to the most it held in the quiet "
        "phase, and the latest it did so, in seconds after the burst.",
        "",
        table(["wallets", "burst landed", "p50", "p90", "p99", "after p50", "p90", "p99", "replacements",
               "price paid", "stuck senders", "pool at end", "base fee at end", "cleared"], rows),
        "",
        f"Replacements the wallet's node refused, over every run in this section: "
        f"{sum(o['refused'] for wallet in WALLETS for o in out[(wallet, 'none', None)])}.",
    ])


def section_2(out) -> str:
    rows = []
    for limit in LIMITS:
        for wallet in ("never", MARKET):
            outs = out[(wallet, limit, None)]
            asked = sum(o["phases"]["burst"]["asked"] for o in outs)
            priced = sum(o["phases"]["burst"]["priced_out"] for o in outs)
            rows.append([limit, wallet, asked, f"{priced / asked:.2f}", *phase_cells(outs, "burst")[1:4],
                         *phase_cells(outs, "after")[3:], spread([o["base_fee_peak"] / GWEI for o in outs]),
                         spread([o["stuck"] for o in outs], "{:.0f}"), spread([o["pool_end"] for o in outs], "{:.0f}"),
                         cleared(outs)])
    return "\n".join([
        "## 2. Users who stop paying",
        "",
        "Section 1's runs with each user drawing the most it pays a gas, base fee and tip together, uniform in "
        "the range given. A user does not send while the next base fee plus its tip is above it, sets a fee cap "
        "no higher, and its wallet bumps no higher. Asked and the share priced out are for the burst; the peak "
        "base fee is the highest of any block, in gwei.",
        "",
        table(["most a gas", "wallets", "burst asked", "priced out", "landed", "p50", "p90", "after p90", "p99",
               "peak base fee", "stuck senders", "pool at end", "cleared"], rows),
    ])


def section_3(out) -> str:
    rows = []
    for wallet in ("never", MARKET):
        for spender in SPENDERS:
            outs = out[(wallet, "none", spender)]
            sp = [r for o in outs for r in o["spends"]["rows"]]
            delays = [d for d, _ in sp if d is not None]
            rows.append([wallet, spender, len(sp), len(delays), percentile(delays, 50), percentile(delays, 90),
                         max(delays) if delays else None, mean([b for _, b in sp]),
                         spread([o["spends"]["longest"] for o in outs], "{:.0f}")])
    return "\n".join([
        "## 3. A shared sender under `one`",
        "",
        "Section 1's runs with a shared sender as well, under `eip-8141`, whose users ask for a spend every "
        f"{1 / SPEND_RATE:.0f} s on average until {PHASES[2][2] - 300} s, a third of the one spend a slot that "
        "`one` allows (experiment 01). Its relayer sends one spend at a time and the next once that one is "
        "included, so every user waits behind the spend that is pending. The spend's fees are committed by its "
        "user's signature entry, so only its user can re-price it, which it does as the second column says, and "
        "the relayer sends the new version in place of the old. Delays are from asking to inclusion, in seconds; "
        "replacements are per spend; the longest hold is the longest time between two of the sender's spends "
        "landing, or from the last to the end of the run if a spend never landed, as a mean and the range over "
        "runs.",
        "",
        table(["transfer wallets", "spend users", "spends", "landed", "delay p50", "p90", "max", "replacements",
               "longest hold"], rows),
    ])


def keys() -> list[tuple]:
    ks = [(wallet, "none", None) for wallet in WALLETS]
    ks += [(wallet, limit, None) for limit in LIMITS for wallet in ("never", MARKET)]
    ks += [(wallet, "none", spender) for wallet in ("never", MARKET) for spender in SPENDERS]
    return list(dict.fromkeys(ks))


def main() -> None:
    ks = keys()
    runs = [Run(seed, wallet=k[0], limit=k[1], spender=k[2]) for k in ks for seed in SEEDS]
    results = dict(zip(runs, run_all(one, runs)))
    out = {k: [results[r] for r in runs if (r.wallet, r.limit, r.spender) == k] for k in ks}
    print("# 15. Wallets that bump fees: results")
    print()
    print(f"Generated by `experiments/15-fee-bumping/run.py`, seeds {', '.join(map(str, SEEDS))}, {NODES} nodes, "
          f"{RUN} simulated seconds a run. Do not edit by hand.")
    for section in (section_1, section_2, section_3):
        print()
        print(section(out))


if __name__ == "__main__":
    main()
