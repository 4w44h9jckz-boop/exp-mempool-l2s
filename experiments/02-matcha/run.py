#!/usr/bin/env python3
"""Experiment 02: MATCHA against one pending transaction per sender. Prints results.md on standard output.

A shared sender, a privacy pool that is the sender of every user's spend, under
FP-12's `one` and `disjoint-keys` and under the MATCHA proposal of
`docs/spec/04-matcha.md`: its honest throughput as demand rises, what its
safety factor, cap and balance reuse decide, and the post's two attacks,
mass invalidation by a malicious application and width draining of an honest
one.
"""

from __future__ import annotations

import sys
from collections import Counter
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "ref" / "python"), str(ROOT / "sim")]

from emem import EIP_8141, MATCHA, Head  # noqa: E402
from emem.framepool.matcha import admission_gas, charge  # noqa: E402
from emem.framepool.prefix import analyse  # noqa: E402
from emem_sim import (ChainConfig, JunkLoad, NetworkConfig, Scenario, SharedSenderLoad, Simulation,  # noqa: E402
                      percentile, table)

SEED = 1
NODES = 20
HOURS = 4
GAS_LIMIT = 2_100_000
SLOT = 12
ONE = EIP_8141
DISJOINT = replace(EIP_8141, name="eip-8141, disjoint-keys", per_sender="disjoint-keys")
NO_REUSE = MATCHA.with_(name="matcha, no reuse", reuse_balance=False)
# The voucher-pool spend of an earlier design study: an expiry frame, the pool's
# voucher check (ECRECOVER and glue, 5000 gas, 260 bytes), the transfer
# (41000 gas, 68 bytes), and a 256-bit nullifier as its nonce key.
SHAPE = dict(verify_gas=5000, verify_bytes=260, exec_gas=41000, exec_bytes=68, expiry=86400, key_bytes=32)
EXPIRY = EIP_8141.expiry_verifier
EPOCH = ChainConfig().slots_per_epoch
ATTACK = 2 * 3600  # section 4's adversary starts here, and its delays count spends asked from here


def label(profile) -> str:
    if profile.per_sender != "matcha":
        return profile.per_sender
    reuse = "" if profile.reuse_balance else ", no reuse"
    return f"matcha {profile.safety_factor:g}, cap 2^{profile.width_cap.bit_length() - 1}{reuse}"


def simulation(profile, senders: list[str], code: str) -> Simulation:
    return Simulation(Scenario(
        seed=SEED,
        nodes=NODES,
        network=NetworkConfig(degree=8, latency=(0.02, 0.10), arrive_timeout=0.5),
        chain=ChainConfig(slot_time=SLOT, proposer="rotate", block_delay=(0.1, 1.0)),
        frame_pool=profile,
        genesis=Head(timestamp=0, gas_limit=GAS_LIMIT, gas_used=GAS_LIMIT // 2, base_fee=1_000_000_000),
        accounts={**{s: 10**24 for s in senders}, EXPIRY: 0},
        code={**{s: code for s in senders}, EXPIRY: "expiry-verifier"},
    ))


def relayer(name: str, profile, demand: float, sender: str, **kwargs) -> SharedSenderLoad:
    """Section 1's relayer: serial under `one` (experiment 01), otherwise at once, taking back what is dropped."""
    serial = profile.per_sender == "one"
    return SharedSenderLoad(name, rate=demand / 3600, senders=[sender], serial=serial, resend=not serial,
                            **SHAPE, **kwargs)


def landed(rec, spends) -> dict[int, float]:
    return {sp.index: rec.txs[sp.tx.hash].included_at for sp in spends
            if sp.tx is not None and rec.txs[sp.tx.hash].included_at is not None}


def ceiling(profile, c: int) -> float:
    """Spends an hour the cap allows: a baseline a slot, and a capped epoch's width of additional ones (MA-4)."""
    return (EPOCH + profile.width_cap // c) * 3600 / (EPOCH * SLOT)


def sustained(c: int, g: int) -> float | str:
    """Spends a slot whose included gas pays for their charges, with one free baseline a slot: k g >= (k - 1) c."""
    return c / (c - g) if c > g else "no limit"


_honest: dict = {}


def honest(profile, demand: float, hours: float = HOURS, junk: dict | None = None) -> dict:
    """Section 1's run, once for each policy and demand, unless an adversary is added."""
    key = (label(profile), demand, hours)
    if junk is not None:
        return run_honest(profile, demand, hours, junk)
    if key not in _honest:
        _honest[key] = run_honest(profile, demand, hours, None)
    return _honest[key]


def run_honest(profile, demand: float, hours: float, junk: dict | None) -> dict:
    """One shared sender, `pool0`, its relayer at n00; optionally an adversary sending junk spends from it."""
    sim = simulation(profile, ["pool0"], "privacy-pool")
    load = relayer("spend", profile, demand, "pool0")
    sim.add_load(load)
    adversary = None
    if junk is not None:
        adversary = JunkLoad("junk", senders=["pool0"], **SHAPE, **junk)
        sim.add_load(adversary)
    first_width = []
    home = sim.net.nodes["n00"]
    home.import_hooks.append(lambda node, block: first_width or node.pool.frame.width("pool0") == 0
                             or first_width.append(sim.sched.now))
    rec = sim.run(hours * 3600)
    times = landed(rec, load.spends)
    delays = [times[sp.index] - sp.requested_at for sp in load.spends if sp.index in times]
    per_block = Counter(times.values())
    multi = [b["at"] for b in rec.blocks if per_block[b["at"]] > 1]
    answers = Counter(a for sp in load.spends for a in sp.answers)
    nodes = sim.net.nodes.values()
    blocks = len(rec.blocks)
    out = {
        "tx": load.spends[0].tx, "asked": len(load.spends), "per_hour": len(times) / hours,
        "by_hour": [sum(1 for t in times.values() if h * 3600 <= t < (h + 1) * 3600) for h in range(int(hours))],
        "delays": delays, "multi": multi[0] / 60 if multi else None,
        "late": [times[sp.index] - sp.requested_at for sp in load.spends
                 if sp.requested_at >= ATTACK and sp.index in times],
        "first_width": first_width[0] / 60 if first_width else None,
        "resims": sum(n.pool.frame.resimulations for n in nodes) / NODES / blocks,
        "work": sum(n.pool.frame.work["pool0"] for n in nodes) / NODES / blocks,
        "width_refused": answers["ErrFrameInsufficientWidth"] / max(1, len(load.spends)),
        "width": home.pool.frame.width("pool0"),
        "waiting": len(load.spends) - len(times),
    }
    if adversary is not None:
        out["junk_admitted"] = sum(1 for sp in adversary.spends if "ok" in sp.answers)
        out["junk_landed"] = len(landed(rec, adversary.spends))
        out["junk_held"] = sum(1 for n in nodes for tx in n.pool.frame.content().get("pool0", [])
                               if tx.label.startswith("junk")) / NODES
    return out


def invalidation(profile, burst: int, earn: float = 600, earn_until: float = 2700, start: float = 3600,
                 stop: float = 4800) -> dict:
    """The first attack: an application whose every pending spend reads one setting, flipped every block."""
    sim = simulation(profile, ["evil", "admin"], "evil-app")
    paid = relayer("paid", profile, earn, "evil", stop=earn_until)
    junk = JunkLoad("junk", senders=["evil"], node="n05", burst=burst, setting=("evil", 1), flipper="admin",
                    start=start, stop=stop, **SHAPE)
    sim.add_load(paid)
    sim.add_load(junk)
    marks = {}

    def mark(name):
        marks[name] = {n.name: (n.pool.frame.work["evil"], n.pool.frame.resimulations) for n in sim.net.nodes.values()}
        marks[name + " width"] = sim.net.nodes["n05"].pool.frame.width("evil")

    sim.sched.at(start - 0.001, lambda: mark("start"))
    sim.sched.at(stop + SLOT - 0.001, lambda: mark("stop"))
    rec = sim.run(stop + 2 * SLOT)
    blocks = sum(1 for b in rec.blocks if start < b["at"] <= stop + SLOT)
    work = sum(marks["stop"][n][0] - marks["start"][n][0] for n in marks["stop"]) / NODES
    resims = sum(marks["stop"][n][1] - marks["start"][n][1] for n in marks["stop"]) / NODES
    flips = [f for f in junk.flips if rec.txs[f.hash].included_at is not None]
    flip_gas = sum(f.used for f in flips)
    paid_gas = sum(paid.spends[i].tx.used for i in landed(rec, paid.spends))
    admitted = sum(1 for sp in junk.spends if sp.answers and sp.answers[0] == "ok")
    return {"blocks": blocks, "admitted": admitted / blocks, "work": work / blocks, "resims": resims / blocks,
            "flips": len(flips), "flip_gas": flip_gas / blocks, "paid_gas": paid_gas,
            "ratio": work / flip_gas if flip_gas else None,
            "width_start": marks["start width"], "width_stop": marks["stop width"]}


def main() -> None:
    out = ["# 02. MATCHA against one pending transaction per sender: results", "",
           f"Generated by `experiments/02-matcha/run.py`, seed {SEED}, {NODES} nodes, {HOURS} simulated hours a "
           "run unless a section says otherwise. Do not edit by hand.", ""]

    tx = honest(MATCHA, 60, hours=0.05)["tx"]
    prefix = analyse(tx, MATCHA)
    a = admission_gas(tx, prefix)
    out += ["## The spend", "",
            "The voucher-pool spend of an earlier design study: an expiry frame, the pool's `self_verify` frame, "
            "a `SENDER` frame calling a token, "
            "a 256-bit nullifier as its EIP-8250 nonce key at sequence 0, and one signature entry by the user. "
            "Every spend is the same apart from its key, its deadline, its tip and its fee cap. Admission gas and "
            "the charge are MA-2's; the included gas is what the sender earns as width when the block is final, "
            "here its whole `max_gas`. In the second table, what width sustains assumes every additional spend "
            "is charged once and lands, with one free baseline in every slot; the cap's ceiling is a baseline a "
            f"slot plus the additional spends one cap of width pays for, because finality, and so width, arrives "
            f"once an epoch of {EPOCH} slots.", ""]
    out.append(table(["frames", "data bytes", "intrinsic gas", "admission gas", "included gas",
                      "spends per block at the limit"],
                     [[len(tx.frames), tx.data_bytes, tx.gas.intrinsic, a, tx.max_gas, GAS_LIMIT // tx.max_gas]]))
    out.append("")
    rows = []
    for sf in (1, 2, 3):
        c = charge(tx, prefix, sf)
        rows.append([sf, c, tx.max_gas / c, sustained(c, tx.max_gas), MATCHA.width_cap // c,
                     ceiling(MATCHA, c)])
    out.append(table(["safety factor", "charge", "additional admissions one included spend pays for",
                      "spends a slot width sustains", "charges in a cap of 2^24", "cap's ceiling, spends an hour"],
                     rows))

    out += ["", "## 1. Honest throughput against demand", "",
            "One shared sender and its relayer at node n00. Under `one` the relayer keeps one spend outstanding "
            "and sends the next when its node imports the block that included the last (experiment 01's relayer); "
            "otherwise it sends each spend at once, and after every block takes back and sends again any spend "
            "its node refused or no longer holds. Landed and demand are spends an hour, over the run and over its "
            "last two hours. Delays are seconds from the user's request to the block that included the spend. "
            "The first multi-spend block is when a block first carried more than one spend, and first width when "
            "n00 was first credited, both in minutes from the start. Re-simulations and work are per node per "
            "block: work is the admission gas of every prefix the pools ran for the sender, at admission or after "
            "a head change. Width refusals are `ErrFrameInsufficientWidth` answers at n00, per spend asked.", ""]
    rows = []
    for demand in (600, 1200, 2400):
        for profile in (ONE, DISJOINT, MATCHA, NO_REUSE):
            r = honest(profile, demand)
            rows.append([label(profile), demand, r["per_hour"], sum(r["by_hour"][-2:]) / 2,
                         percentile(r["delays"], 50), percentile(r["delays"], 90), percentile(r["delays"], 99),
                         r["multi"], r["first_width"], r["resims"], r["work"], r["width_refused"], r["waiting"]])
    out.append(table(["policy", "demand", "landed", "last 2 h", "delay p50", "p90", "p99", "first multi-spend block",
                      "first width", "re-simulations", "work", "width refusals", "waiting at end"], rows))

    out += ["", "## 2. Safety factor, cap and balance reuse", "",
            "MATCHA only, at 1200 spends an hour, columns as in section 1; width is n00's at the end, and the "
            "cap's ceiling is as in the second table above.", ""]
    rows = []
    for profile in (MATCHA.with_(safety_factor=1), MATCHA, MATCHA.with_(safety_factor=3),
                    MATCHA.with_(width_cap=2**22), NO_REUSE.with_(safety_factor=1)):
        r = honest(profile, 1200)
        rows.append([label(profile), r["per_hour"], sum(r["by_hour"][-2:]) / 2, percentile(r["delays"], 50),
                     percentile(r["delays"], 90), r["multi"], r["work"], r["width_refused"], r["width"],
                     ceiling(profile, charge(tx, analyse(tx, profile), profile.safety_factor))])
    out.append(table(["policy", "landed", "last 2 h", "delay p50", "p90", "first multi-spend block", "work",
                      "width refusals", "width at end", "cap's ceiling"], rows))

    out += ["", "## 3. Mass invalidation", "",
            "A malicious application `evil` is its own shared sender. Its relayer sends 600 paid spends an hour, "
            "at the honest tips, for the first 45 minutes, so that under MATCHA it earns width. From minute 60 to "
            "minute 80, after every block its node n05 imports, it sends up to 100 junk spends whose prefix reads "
            "a setting slot of `evil` and whose tip, 1 wei, is below every builder's minimum, and an account it "
            "controls sends a 26,000-gas transaction that changes the setting in the next block, invalidating "
            "every junk spend pending anywhere. Per block of the attack: junk admitted at n05, and per node the "
            "re-simulations and the work (as in section 1, for `evil`, in gas). The attacker's gas is what its "
            "flips used per block of the attack; its paid spends used the gas in the last column before it, "
            "under every policy. The ratio is work per node against the attacker's flip gas, over the attack; "
            "width is n05's for `evil` at its start and end.", ""]
    rows = []
    for profile in (ONE, DISJOINT, MATCHA):
        r = invalidation(profile, 100)
        rows.append([label(profile), r["blocks"], r["admitted"], r["resims"], r["work"], r["flips"], r["flip_gas"],
                     r["ratio"], r["width_start"], r["width_stop"], r["paid_gas"]])
    out.append(table(["policy", "blocks", "junk admitted", "re-simulations", "work", "flips landed",
                      "attacker gas", "work per attacker gas", "width at start", "width at end",
                      "paid spends' gas before"], rows))

    out += ["", "## 4. Width draining", "",
            "Section 1's honest pool at 1200 spends an hour, and for the last two hours an adversary holding "
            "vouchers for it: after every block its node n05 imports, it sends up to 20 junk spends from the "
            "honest pool, valid, with a fee cap over the next base fee and a tip of 1 wei, below every builder's "
            "minimum, to n05 alone or to every node. The rows with no adversary are section 1's runs. Landed is "
            "honest spends by hour of the run, so the adversary acts in hours 3 and 4; delay is over spends asked "
            "in those hours, and is n/a when none of them had landed by the end. Junk admitted counts the junk "
            "spends some target took; junk held is the mean number pending per node at the end. `disjoint-keys` "
            "is not run: there every junk spend is re-run at every node at every block, because each included "
            "honest spend moves the pool's balance.", ""]
    rows = []
    for profile in (ONE, MATCHA):
        for targets in ("no adversary", "n05", "every node"):
            if targets == "no adversary":
                r = honest(profile, 1200)
            else:
                junk = {"node": "n05", "burst": 20, "start": ATTACK,
                        "targets": list(f"n{i:02d}" for i in range(NODES)) if targets == "every node" else None}
                r = honest(profile, 1200, junk=junk)
            rows.append([label(profile), targets] + r["by_hour"] + [
                percentile(r["late"], 50), percentile(r["late"], 90), r.get("junk_admitted"), r.get("junk_landed"),
                r.get("junk_held"), r["width_refused"]])
    out.append(table(["policy", "junk sent to", "hour 1", "hour 2", "hour 3", "hour 4", "delay p50 from hour 2",
                      "p90", "junk admitted", "junk landed", "junk held", "width refusals"], rows))
    print("\n".join(out))


if __name__ == "__main__":
    main()
