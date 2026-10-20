#!/usr/bin/env python3
r"""Experiment 26: a bond on the ticket paymaster, a third defence against a self-issuer's junk proofs. Prints
results.md.

Experiment 25 priced version 4 of claim-gated admission as written, issuer
memory and a node list against a self-issuer's junk proofs. This prices a
third defence: stake and reputation for the ticket paymaster as an operator,
the way `docs/spec/14-erc-8421.md` reads ERC-8421's standard ruleset and
`docs/spec/descriptors/erc-8421.json` gives its parameters. A node accepts
tickets only from a staked paymaster and keeps the ruleset's `seen` and
`included` counters for each, refreshed every hour; a `BANNED` paymaster's
tickets are refused before any check, and a `THROTTLED` one backs at most
four pending transactions at the node. It prices, against experiment 25's
network and wallets over two hours:

1. a self-issuer's junk proofs, with one and with four bonded paymasters,
   against version 4 as written and against an unbonded paymaster;
2. a holder of honest tickets who attaches junk proofs to them, against a
   busy honest issuer and a small one;
3. what the bond costs a small honest issuer: the stake it locks, and the
   junk an attacker needs to throttle or ban it, from the ruleset's counters.

The bond is modelled in the simulator, around the clauses
(`sim/emem_sim/issuers.py`, decision record 0062), as experiment 25's
defences are; none is a clause.
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "ref" / "python"), str(ROOT / "sim")]

from emem import EIP_8288, Head  # noqa: E402
from emem.descriptor import Store, compile_config  # noqa: E402
from emem_sim import (Bond, ChainConfig, Defence, Issuers, JunkProofs, NetworkConfig, Scenario, Simulation,  # noqa: E402
                      WalletLoad, guard, percentile, run_all, table, uniform)
from emem_sim.issuers import BANNED, THROTTLED  # noqa: E402

SEED = 1
NODES = 30
DEGREE = 8
SLOT = 12
EPOCH = EIP_8288.claim_epoch  # 384 s
HOUR = 3600
RUN = 19 * EPOCH  # 7296 s: two hours and the refresh at 7200 s
DEMAND = RUN - 300  # honest spends stop here, and the run drains
START = 60
END = 18 * EPOCH  # 6912 s: every attacker stops at the start of the last epoch
GAS_LIMIT = 30_000_000
BASE_FEE = 1_000_000_000
MIN_TIP = 1_000_000
TIPS = (1_000_000, 3_000_000_000)
EXEC_GAS = 50_000
WALLETS = 8000
PER_SLOT = 8  # spends a slot across the four busy issuers, as in experiment 25
HONEST = [f"h{i}" for i in range(4)]  # the busy honest issuers; wallet u<i> holds tickets of h<i mod 4>
SMALL = "s0"  # a small honest issuer; wallet v<i> holds its tickets
SMALL_WALLETS = 1000
SMALL_PER_EPOCH = 4
JUNK_PER_SLOT = 4  # a self-issuer's wrappers to every node, every slot, as in experiment 25
OFFSET = 5  # seconds into an epoch at which a holder of honest tickets sends

# Measured, and cited in the README, as in experiment 25
DEPLOY_GAS = 2_443_085  # eth_estimateGas of a ticket paymaster's deployment
TICKET_WEI = 10**15  # the denomination: what one honest ticket costs its buyer
VERIFY_MS = 11.442  # verifying one leanVM proof on this machine (bench/results/2026-10-13-leanvm.md)


def erc_8421():
    """The `erc-8421` descriptor's ruleset (`docs/spec/13-descriptors.md`, DS-6), after its parent."""
    store = Store()
    spec = ROOT / "docs" / "spec" / "descriptors"
    store.load((spec / "eip-8141.json").read_text())
    return compile_config(store.load((spec / "erc-8421.json").read_text()))


RULESET = erc_8421()
GATED = EIP_8288.with_(cap_aggregates=False, claims=True)


def issuer_of(sender: str) -> str | None:
    if sender.startswith("u"):
        return HONEST[int(sender[1:]) % len(HONEST)]
    return SMALL if sender.startswith("v") else None


def simulate(key: tuple) -> dict:
    """One run: (section, defence, the attacker's paymasters or the issuer it holds tickets of, n)."""
    section, name, target, n = key
    senders = [f"u{i}" for i in range(WALLETS)]
    small = [f"v{i}" for i in range(SMALL_WALLETS)]
    junk = [f"x{i}" for i in range(n)] if section == 1 else []
    accounts = {s: 10**18 for s in senders + small} | {p: 10**20 for p in HONEST + [SMALL] + junk}
    sim = Simulation(Scenario(
        seed=SEED, nodes=NODES,
        network=NetworkConfig(degree=DEGREE, latency=(0.02, 0.10), arrive_timeout=0.5),
        chain=ChainConfig(slot_time=SLOT, proposer="rotate", block_delay=(0.1, 1.0), min_tip=MIN_TIP),
        frame_pool=GATED,
        genesis=Head(timestamp=0, gas_limit=GAS_LIMIT, gas_used=GAS_LIMIT // 2, base_fee=BASE_FEE),
        accounts=accounts))
    registry = Issuers(issuer_of)
    wallets = WalletLoad("u", rate=PER_SLOT / SLOT, senders=senders, tip=uniform(*TIPS), expiring=0.0,
                         exec_gas=EXEC_GAS, scheme="stark", stop=DEMAND, claims=True)
    smalls = WalletLoad("v", rate=SMALL_PER_EPOCH / EPOCH, senders=small, tip=uniform(*TIPS), expiring=0.0,
                        exec_gas=EXEC_GAS, scheme="stark", stop=DEMAND, claims=True)
    sim.add_load(wallets)
    sim.add_load(smalls)
    bonded = frozenset(HONEST + [SMALL] + (junk if name == "bond" else []))
    defence = Defence() if name == "none" else Defence(bond=Bond(bonded, RULESET))
    guards = guard(sim, lambda _: defence, registry)
    if section == 1:  # a self-issuer, its paymasters in the order it deploys them
        attacker = JunkProofs("x", issuers=junk, registry=registry, count=JUNK_PER_SLOT, every=SLOT,
                              rotate=True, start=START, stop=END)
    else:  # a holder of `target`'s tickets, n of them an epoch
        attacker = JunkProofs("g", issuers=[target], registry=registry, count=n, every=EPOCH, offset=OFFSET,
                              start=START, stop=END)
    sim.add_load(attacker)
    failed: Counter = Counter()  # (node, hour): the attacker's proofs that failed there

    def seen(node, wrapper, results, origin) -> None:
        if origin == attacker.name and results == "ErrWrapperProof":
            failed[node.name, int(node.now // HOUR)] += 1

    for node in sim.net.nodes.values():
        node.wrapper_hooks.append(seen)
    rec = sim.run(RUN)

    counts: Counter = Counter()
    for g in guards.values():
        counts.update(g.counts)
    proofs = Counter()
    for node in sim.net.nodes.values():
        for (origin, event, _), c in node.work.items():
            if event == "proof":
                proofs[origin] += c

    def landed(load: WalletLoad, issuers: set[str]) -> tuple[int, int, list[float]]:
        sent, done, delays = 0, 0, []
        for first in load.txs:
            if issuer_of(first.sender) not in issuers:
                continue
            sent += 1
            times = [rec.txs[v.hash].included_at for v in load.versions.get(first.hash, [first])
                     if v.hash in rec.txs and rec.txs[v.hash].included_at is not None]
            if times:
                done += 1
                delays.append(min(times) - rec.txs[first.hash].submitted_at)
        return sent, done, delays

    def first(issuer: str, state: str) -> list[float]:
        """By node, when `issuer` first entered `state` there; nodes where it never did are left out."""
        out = []
        for g in guards.values():
            times = [t for t, who, s in g.states if who == issuer and s == state]
            if times:
                out.append(times[0])
        return out

    window = END - START
    watched = junk if section == 1 else [target]
    share = {state: sum(g.time_in(i, state, END) - g.time_in(i, state, START) for g in guards.values()
                        for i in watched) / (len(guards) * len(watched) * window)
             for state in (THROTTLED, BANNED)} if defence.bond is not None else {THROTTLED: 0.0, BANNED: 0.0}
    a = attacker.name
    return {
        "busy": landed(wallets, set(HONEST)), "h0": landed(wallets, {"h0"}),
        "others": landed(wallets, set(HONEST) - {"h0"}), "small": landed(smalls, {SMALL}),
        "sent": attacker.sent, "tickets": attacker.tickets, "used": len(attacker.used),
        "ticket checks": counts["ticket", a], "prefixes": counts["prefix", a], "proofs": proofs[a],
        "unbonded": counts["unbonded", a], "banned": counts["banned", a], "throttled": counts["throttled", a],
        "hours": [sum(c for (_, h), c in failed.items() if h == hour) / NODES for hour in (0, 1)],
        "first throttled": first(watched[0], THROTTLED) if watched else [],
        "first banned": first(watched[0], BANNED) if watched else [],
        "share": share,
        "honest refused": {who: counts["throttled", who] + counts["banned", who] for who in ("u", "v")},
    }


S1 = [(1, "none", None, 1), (1, "bond, unbonded", None, 1), (1, "bond", None, 1), (1, "bond", None, 4)]
S2 = [(2, "bond", "h0", 8), (2, "bond", "h0", 64), (2, "bond", SMALL, 8), (2, "bond", SMALL, 64)]


def honest(r: dict, part: str) -> list:
    sent, done, delays = r[part]
    return [done, sent, percentile(delays, 50), percentile(delays, 90)]


def med(xs: list[float]) -> float | None:
    return median(xs) if xs else None


def section_1(out: dict) -> str:
    days = (END - START + RULESET.min_unstake_delay) / 86_400
    rows = []
    for key in S1:
        _, name, _, n = key
        r = out[key]
        bonded = r["used"] if name == "bond" else 0
        stake = bonded * RULESET.min_stake_value
        rows.append([name, n, r["used"], r["sent"], r["ticket checks"], r["prefixes"], r["proofs"],
                     r["hours"][0], r["hours"][1], len(r["first banned"]), med(r["first banned"]),
                     r["share"][BANNED], r["unbonded"] + r["banned"] + r["throttled"], r["used"] * DEPLOY_GAS,
                     stake, stake * days / 10**18, r["proofs"] * VERIFY_MS / 1000,
                     r["honest refused"]["u"] + r["honest refused"]["v"]] + honest(r, "busy"))
    return "\n".join([
        "## 1. A self-issuer's junk proofs against a bond",
        "",
        f"Experiment 25's network: {NODES} nodes, {DEGREE} peers each, a block every {SLOT} s from a rotating "
        f"proposer, under EIP-8288 with claims (CG-1). Wallets send {PER_SLOT} spends a slot, each with one "
        f"leanSTARK dependency, as mode 0 wrappers, with valid tickets of {len(HONEST)} busy honest issuers, "
        f"and {SMALL_PER_EPOCH} spends an epoch with tickets of a small one, {SMALL}, for {DEMAND} s of a "
        f"{RUN} s run. From second {START} until second {END} a self-issuer hands every node "
        f"{JUNK_PER_SLOT} wrappers a slot, each from a fresh sender with a valid ticket it signed, whose proof "
        f"fails, moving to its next paymaster at a node that refuses the current one. `none` is version 4 as "
        f"written. Under `bond` every node runs the `erc-8421` descriptor's reputation for ticket paymasters: "
        f"it refuses an unstaked paymaster's tickets, and a paymaster's state is `BANNED` once "
        f"`seen // {RULESET.min_inclusion_rate_denominator}` exceeds `included + {RULESET.ban_slack}`, with "
        f"both counters multiplied by 23/24 every {RULESET.refresh_seconds} s. In `bond, unbonded` the "
        f"self-issuer's paymaster has no stake; in `bond` each has {RULESET.min_stake_value} wei staked with an "
        f"unstake delay of {RULESET.min_unstake_delay} s. Hour 1 and hour 2 are the junk proofs one node "
        f"verified in each, the mean over nodes; banned at is the median time a node first banned the first "
        f"paymaster, over the nodes that did; banned share is the share of the attack's node-time its "
        f"paymasters spent banned. Stake ETH-days is what it locks, from the attack's start to the end of the "
        f"unstake delay after it stops. Proof s prices the proofs at {VERIFY_MS} ms each.",
        "",
        table(["defence", "paymasters", "used", "wrappers", "ticket checks", "prefixes", "proofs",
               "hour 1 a node", "hour 2 a node", "nodes that banned", "banned at s", "banned share",
               "refused before the ticket", "deployment gas", "stake wei", "stake ETH-days", "proof s",
               "honest refused", "landed", "sent", "delay p50", "p90"], rows),
    ])


def section_2(out: dict) -> str:
    rows = []
    for key in S2:
        _, _, target, n = key
        r = out[key]
        part = "h0" if target == "h0" else "small"
        rows.append([target, n, r["tickets"], r["tickets"] * TICKET_WEI, r["proofs"], r["hours"][0],
                     r["hours"][1], len(r["first throttled"]), med(r["first throttled"]), len(r["first banned"]),
                     med(r["first banned"]), r["share"][THROTTLED], r["share"][BANNED],
                     r["honest refused"]["u" if target == "h0" else "v"]] + honest(r, part)
                    + honest(r, "others")[2:])
    return "\n".join([
        "## 2. A holder of honest tickets against a bond",
        "",
        f"Section 1's network and wallets, every node under `bond`, and no self-issuer. A holder of the "
        f"target's tickets, bought at {TICKET_WEI} wei each, hands every node, {OFFSET} s into each epoch from "
        f"second {START} until second {END}, wrappers of its own whose proofs fail, one for each ticket, n "
        f"tickets an epoch. h0 is a busy issuer, with {PER_SLOT // len(HONEST)} of its spends a slot; {SMALL} "
        f"is the small one, with {SMALL_PER_EPOCH} an epoch. Throttled at and banned at are the median times a "
        f"node first throttled or banned the target, over the nodes that did, and the shares the share of the "
        f"attack's node-time it spent in each. Honest refused counts the times a node refused one of the "
        f"target's spends because the target was throttled or banned. The last two columns are the delays of "
        f"the spends of the busy issuers other than h0.",
        "",
        table(["target", "tickets an epoch", "tickets", "wei", "proofs", "hour 1 a node", "hour 2 a node",
               "nodes that throttled", "throttled at s", "nodes that banned", "banned at s", "throttled share",
               "banned share", "honest refused", "target landed", "sent", "delay p50", "p90", "others p50",
               "others p90"], rows),
    ])


def section_3() -> str:
    """AM-13's thresholds for an issuer whose spends are all included, on fresh counters within one refresh."""
    k, throttle, ban = RULESET.min_inclusion_rate_denominator, RULESET.throttling_slack, RULESET.ban_slack
    rows = []
    for r in (0, 10, 100, 1000):  # spends of the issuer's a node counts as seen and included in the hour
        to_throttle = k * (r + throttle + 1) - r  # least junk J with (r + J) // k > r + throttle
        to_ban = k * (r + ban + 1) - r
        rows.append([r, to_throttle, to_throttle * TICKET_WEI, to_ban, to_ban * TICKET_WEI])
    bond = RULESET.min_stake_value
    return "\n".join([
        "## 3. What a bond costs a small honest issuer",
        "",
        f"Derived from the descriptor's parameters, not simulated. The bond is {bond} wei, which is "
        f"{bond // TICKET_WEI} tickets' face value at {TICKET_WEI} wei, locked from the first ticket to "
        f"{RULESET.min_unstake_delay} s after the last. Against griefing, an issuer whose spends a node "
        f"counts r times in an hour, every one included, is throttled there by the least J junk proofs with "
        f"`(r + J) // {k} > r + {throttle}` and banned by the least with `(r + J) // {k} > r + {ban}`, on "
        f"counters that start at zero and before a refresh. A ticket buys one junk proof at each node an epoch "
        f"(CG-4 refuses its slot after it fails), so J is also the tickets an attacker needs, sent to every "
        f"node within the hour, at {TICKET_WEI} wei each. Section 2 checks two points of it by simulation.",
        "",
        table(["spends counted an hour", "junk to throttle", "wei", "junk to ban", "wei"], rows),
        "",
        f"Sustained, the same counters epoch by epoch, with the refresh every {RULESET.refresh_seconds} s: when "
        f"a node first throttles and first bans an issuer whose spends it counts n an epoch, each included in "
        f"the epoch, while a holder of its tickets sends t an epoch, for up to 30 days. The rows are section "
        f"2's: h0 with {PER_SLOT // len(HONEST) * EPOCH // SLOT} spends an epoch, {SMALL} with "
        f"{SMALL_PER_EPOCH}. Bond days is how many days of the issuer's own ticket sales at face value, one "
        f"ticket a spend, the bond is; n/a is not within 30 days.",
        "",
        table(["issuer", "spends an epoch", "tickets an epoch", "wei an epoch", "throttled after hours",
               "banned after hours", "bond days"],
              [[name, n, t, t * TICKET_WEI, *sustained(n, t), bond / (n * 86_400 // EPOCH * TICKET_WEI)]
               for name, n in (("h0", PER_SLOT // len(HONEST) * EPOCH // SLOT), (SMALL, SMALL_PER_EPOCH))
               for t in (8, 64)]),
    ])


def sustained(honest_per_epoch: int, junk_per_epoch: int, days: int = 30) -> tuple:
    """When, in hours, a node first throttles and first bans a paymaster whose honest spends it counts
    `honest_per_epoch` times an epoch, every one included in the same epoch, while it fails `junk_per_epoch` junk
    proofs an epoch, on counters from zero refreshed every `refresh_seconds` (AM-13); None for not within `days`."""
    k, cfg = RULESET.min_inclusion_rate_denominator, RULESET
    seen = included = refreshed = 0
    first = {THROTTLED: None, BANNED: None}
    for e in range(days * 86_400 // EPOCH):
        end = (e + 1) * EPOCH
        seen += honest_per_epoch + junk_per_epoch
        included += honest_per_epoch
        m = seen // k
        for state, slack in ((THROTTLED, cfg.throttling_slack), (BANNED, cfg.ban_slack)):
            if first[state] is None and m > included + slack:
                first[state] = end / HOUR
        while refreshed < end // cfg.refresh_seconds:
            refreshed += 1
            seen, included = seen * 23 // 24, included * 23 // 24
    return first[THROTTLED], first[BANNED]


def main() -> None:
    keys = S1 + S2
    out = dict(zip(keys, run_all(simulate, keys)))
    print("# Experiment 26: a bond on the ticket paymaster")
    print()
    print(f"Generated by `experiments/26-ticket-bond/run.py`, seed {SEED}. Clauses in "
          "`docs/spec/10-claim-gated-admission.md` version 4; the bond's parameters are those of "
          "`docs/spec/descriptors/erc-8421.json` (`docs/spec/14-erc-8421.md`), and the bond is modelled in the "
          "simulator, not specified (decision record 0062).")
    print()
    for section in (section_1(out), section_2(out), section_3()):
        print(section)
        print()


if __name__ == "__main__":
    main()
