#!/usr/bin/env python3
r"""Experiment 27: the relaxed alternative mempool's bound and its tiers. Prints results.md.

`docs/spec/15-relaxed-mempool.md` admits behind the canonical rules what they
refuse to a contract that sends or pays for its own transactions: write-once
reads declared per code (RM-3), several pending per declared contract on
disjoint keys (RM-4), and the non-canonical payer's count lifted against a
reserve (RM-5), with reputation per declared code from each block's access
list (RM-6) and three tiers (RM-8). Its claim is that one write, other than
one that breaks a declaration, invalidates at most one pending transaction
that only the relaxations admitted (RM-9). This measures, with the reference
pool and the descriptors themselves:

1. the worst-case invalidation from one write, over every write the pool
   knows a key for, under the canonical descriptor, under `relaxed.json` with
   declarations, and under `relaxed.json` with `sender_bound` and
   `outflow_bound` false, the relaxations as first asked (decision record
   0082);
2. whether each kind of violated declaration is seen in the access list of
   the block that carries it, and what the declared code's rate is after;
3. what each tier needs at a stated rate of proof-carrying transactions,
   state, CPU and bandwidth, for a network of relays and verifiers against
   one in which every node verifies, and what a relay that checks no proof
   charges a sender for junk.

A child descriptor of `relaxed.json` replaces RM-3 to name the declarations
(DS-5); the literal variant is a child of that one. Nothing here is a clause.
"""

from __future__ import annotations

import copy
import random
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "ref" / "python"), str(ROOT / "sim"), str(ROOT / "bench" / "leanvm")]

from emem import Aggregator, Head, State, TxPool, Wrapper  # noqa: E402
from emem.descriptor import Store, compile_config  # noqa: E402
from emem.framepool.pool import FramePool  # noqa: E402
from emem.reserver import Reserver  # noqa: E402
from emem.tx import Claim, Dependency, Frame, FrameTx  # noqa: E402
from emem_sim import table  # noqa: E402
import fit  # noqa: E402  bench/leanvm/fit.py, decision record 0033

SEED = 27
SPEC = ROOT / "docs" / "spec" / "descriptors"
EPOCH = 384  # CG-1's claim_epoch
HEAD = Head(number=1, timestamp=2 * EPOCH)
GWEI = 10**9

# --- the accounts --------------------------------------------------------------------------------------------
ROOTS = "roots"  # a shared pool's root contract: past roots set, future ones unset
NOTES = "notes"  # a note pool that sends its own withdrawals, one nonce key and one nullifier slot each
TPM = "tpm"  # a ticket paymaster
UPM = "upm"  # a paymaster that declares nothing
EOA, DELEG, WALLET = "e0", "d0", "c0"  # an account with no code, a delegated one, an undeclared contract
ROOT_FIRST, ROOTS_SET, ROOTS_UNSET = 0x100, 16, 16
NULL_FIRST, NULLIFIERS = 0x1000, 128
NOTES_OWN = 1  # a slot of the note pool's that it does not declare
WALLET_OWN = 5
DELEGATION = "0xef0100" + "11" * 20

# --- section 3: the network and the measured costs -------------------------------------------------------------
NODES, DEGREE = 40, 8
MIXES = (("every node verifies", 0), ("one verifier in two", 20), ("one verifier in five", 32))
RATES = (1, 5, 10, 25)  # proof-carrying transactions a second, across the network
RUN = 4 * EPOCH  # seconds of the stream in section 3
SLOT = 12
UPLINK_MBPS = 50
PROOF_KIB = [r["kib"] for r in fit.parse()[1] if "kib" in r]  # every proof the benchmark measured
SMALL_KIB, MEAN_KIB, LARGE_KIB = min(PROOF_KIB), fit.proof_kib(), max(PROOF_KIB)
VERIFY_MS = fit.verify_ms()  # the mean over the recursions whose proofs weigh MEAN_KIB
SPEND_DATA = 320  # bytes a spend's call carries, besides its ticket and its dependency frame
JUNK_TICKETS, JUNK_COPIES = 20, 5
HISTORY = (100_000, 100_000)  # the ticket paymaster's seen and included (AM-13), as given to each node


def descriptors():
    """The canonical descriptor, and `relaxed.json` with RM-3 naming the declarations, and its literal child."""
    store = Store()
    canonical = store.load((SPEC / "eip-8141.json").read_text())
    relaxed = store.load((SPEC / "relaxed.json").read_text())
    child = store.load_value({"format": 1, "name": "relaxed, with declarations", "source": "experiment 27",
                              "parent": relaxed.id, "remove": [], "rules": {"RM-3": {"declarations": DECLARATIONS}}})
    literal = store.load_value({"format": 1, "name": "relaxed, as first asked", "source": "experiment 27",
                                "parent": child.id, "remove": [],
                                "rules": {"RM-4": {"sender_bound": False}, "RM-5": {"outflow_bound": False}}})
    return {"canonical": compile_config(canonical), "relaxed": compile_config(child),
            "relaxed, as first asked": compile_config(literal)}, child.id


def verify(approves=3, reads=(), target=None, flags=3, data=0) -> Frame:
    return Frame(mode=1, flags=flags, target=target, exec_gas=30000, approves=approves, reads=tuple(reads),
                 data_size=data)


SEND = Frame(mode=2, exec_gas=50000, data_size=SPEND_DATA)


def self_tx(sender, key=0, reads=(), **kw) -> FrameTx:
    return FrameTx(sender=sender, frames=(verify(reads=reads), SEND), nonce_keys=(key,), **kw)


def eoa_tx(sender, key=0, **kw) -> FrameTx:
    return FrameTx(sender=sender, frames=(Frame(mode=1, flags=3, exec_gas=30000), SEND), nonce_keys=(key,), **kw)


def paid_tx(sender, payer, key=0, claim=None, data=0, deps=(), **kw) -> FrameTx:
    frames = [verify(approves=2, flags=2), verify(approves=1, flags=1, target=payer, data=data), SEND]
    if deps:
        frames.insert(0, Frame(mode=3, deps=tuple(deps), exec_gas=30000, data_size=96))
    return FrameTx(sender=sender, frames=tuple(frames), nonce_keys=(key,), claim=claim, **kw)


def claim(sender, salt, epoch=HEAD.timestamp // EPOCH) -> Claim:
    return Claim(sender=sender, nonce_seq=0, epoch=epoch, salt=salt, binder="b1")


M_SELF = self_tx("x").max_cost
M_PAID = paid_tx("x", TPM, claim=claim("x", "s"), data=188).max_cost  # CG-10's bound ticket, 188 bytes
TX_BYTES = paid_tx("w", TPM, claim=claim("w", "h"), data=188, deps=[Dependency(17, "d", "vk")]).encoded_size
DECLARATIONS = [
    {"code": "root-pool", "write_once": [[hex(ROOT_FIRST), ROOTS_SET + ROOTS_UNSET]], "max_outflow": None},
    {"code": "note-pool", "write_once": [[hex(NULL_FIRST), NULLIFIERS]], "max_outflow": str(M_SELF)},
    {"code": "ticket-pm", "write_once": [], "max_outflow": str(M_PAID)},
]


# --- section 1: the bound --------------------------------------------------------------------------------------

def workload(rng: random.Random):
    """The state and the stream, in a seeded order: who reads what, and who pays."""
    roots = {ROOT_FIRST + i: rng.randrange(1, 2**64) for i in range(ROOTS_SET)}
    users = (f"u{i}" for i in range(10**6))
    txs: list[tuple[str, FrameTx]] = []

    def root_read():
        slot = rng.choice(sorted(roots))
        return (ROOTS, slot, roots[slot])

    for _ in range(120):  # spends that read a past root of the shared pool
        txs.append(("reads a set root", self_tx(next(users), reads=[root_read()])))
    for i in range(32):  # spends that read a note's nullifier, unset, and a second reader of half of them
        txs.append(("reads an unset nullifier", self_tx(next(users), reads=[(NOTES, NULL_FIRST + i, 0)])))
    for i in range(16):
        txs.append(("reads an unset nullifier", self_tx(next(users), reads=[(NOTES, NULL_FIRST + i, 0)])))
    for i in range(32, 96):  # the note pool's own withdrawals, one key and one nullifier each
        txs.append(("note pool withdraws", self_tx(NOTES, key=i + 1,
                                                    reads=[(NOTES, NULL_FIRST + i, 0), root_read()])))
    for i in range(10):  # withdrawals that also read a slot the note pool does not declare
        txs.append(("note pool reads its undeclared slot", self_tx(NOTES, key=200 + i,
                                                                    reads=[(NOTES, NOTES_OWN, 7)])))
    for i in range(60):  # ticket-paid transactions, each reserving the ticket paymaster's bound
        s = next(users)
        txs.append(("paid by tickets", paid_tx(s, TPM, claim=claim(s, f"t{i}"), data=188)))
    for i in range(10):  # and some whose max_cost is below it
        s = next(users)
        txs.append(("paid by tickets, under the bound", paid_tx(s, TPM, claim=claim(s, f"l{i}"), data=188,
                                                                max_fee=50)))
    for _ in range(20):
        txs.append(("paid by an undeclared payer", paid_tx(next(users), UPM)))
    for k in range(1, 11):
        txs.append(("account with no code", eoa_tx(EOA, key=k)))
        txs.append(("delegated account", self_tx(DELEG, key=k)))
        txs.append(("undeclared contract", self_tx(WALLET, key=k, reads=[(WALLET, WALLET_OWN, 3)])))
    for _ in range(40):
        txs.append(("plain", self_tx(next(users))))
    rng.shuffle(txs)

    state = State()
    for _, tx in txs:
        if tx.sender.startswith("u"):
            state.edit(tx.sender).code, state.edit(tx.sender).balance = "account-v1", 10**12
    acc = state.edit(ROOTS)
    acc.code, acc.storage = "root-pool", dict(roots)
    acc = state.edit(NOTES)
    acc.code, acc.storage = "note-pool", {NOTES_OWN: 7}
    acc.balance = 64 * M_SELF
    acc = state.edit(TPM)
    acc.code, acc.stake, acc.unstake_delay = "ticket-pm", 10**18, 86400
    acc.balance = 60 * M_PAID + 10 * (M_PAID // 2)
    acc = state.edit(UPM)
    acc.code, acc.balance = "plain-pm", 20 * M_PAID
    for addr, code in ((EOA, ""), (DELEG, DELEGATION), (WALLET, "plain-wallet")):
        acc = state.edit(addr)
        acc.code, acc.balance = code, 10**12
    state.edit(WALLET).storage = {WALLET_OWN: 3}
    return state, txs


def writes(state: State):
    """Every write the pool knows a key for: (kind, whether it breaks a declaration, address, field, value). It
    breaks one as RM-6 reads it: a declared slot whose value before is not 0, or a payment beyond max_outflow. A
    payment's value is what it takes, from a balance set to what the payer's pending transactions reserve; a
    payer that declares no bound can pay out anything without breaking one."""
    out = []
    for i in range(ROOTS_SET):
        s = ROOT_FIRST + i
        out.append(("a set root rewritten", True, ROOTS, ("storage", s), state.storage(ROOTS, s) + 1))
    for i in range(96):
        out.append(("a nullifier written", False, NOTES, ("storage", NULL_FIRST + i), 1))
    out.append(("a nullifier written twice in one block", True, NOTES, ("storage2", NULL_FIRST + 40), 2))
    out.append(("the note pool's undeclared slot", False, NOTES, ("storage", NOTES_OWN), 8))
    out.append(("the undeclared contract's slot", False, WALLET, ("storage", WALLET_OWN), 4))
    out.append(("the account with no code delegates", False, EOA, ("code", None), DELEGATION))
    for payer, x in ((TPM, M_PAID), (NOTES, M_SELF)):
        out.append((f"{payer} pays out its declared bound", False, payer, ("balance", None), x))
        out.append((f"{payer} pays out twice its bound", True, payer, ("balance", None), 2 * x))
    out.append(("upm, which declares nothing, pays out all it has", False, UPM, ("balance", None), None))
    return out


def apply(pool: FramePool, write) -> tuple[Counter, int]:
    """The write at the next head, with its block's access list; what the pool removed, by class, and RM-6's
    count of violations after."""
    kind, _, addr, (field, slot), value = write
    state = pool.state.copy()
    acc = state.edit(addr)
    changes: dict = {}
    if field in ("storage", "storage2"):
        acc.storage[slot] = value
        posts = [(0, 1), (1, value)] if field == "storage2" else [(0, value)]
        changes["storage_changes"] = {slot: posts}
    elif field == "code":
        acc.code = value
    else:  # from a balance just covering what the payer's pending transactions reserve
        pre = pool.reserved.get(addr, pool.state.balance(addr))
        pool.state.edit(addr).balance = pre
        acc = state.edit(addr)
        acc.balance = 0 if value is None else pre - value
        changes["balance_changes"] = [(0, acc.balance)]
    before = {h: bool(e.relaxed) for h, e in pool.entries.items()}
    head = Head(number=pool.head.number + 1, timestamp=pool.head.timestamp + SLOT)
    pool.reset(head, state, access_lists=[{addr: changes}] if changes else [])
    removed = Counter()
    for h, relaxed in before.items():
        if h not in pool.entries:
            removed["relaxed" if relaxed else "canonical"] += 1
    return removed, sum(pool.violations.values())


def bound(configs: dict) -> tuple[list, dict]:
    rows, detail = [], {}
    for name, cfg in configs.items():
        state, txs = workload(random.Random(SEED))
        pool = FramePool(HEAD, state, cfg, Reserver())
        results = Counter()
        admitted = Counter()
        for kind, tx in txs:
            code = pool.add([tx])[0]
            results[code] += 1
            if code == "ok":
                admitted["relaxed" if pool.entries[tx.hash].relaxed else "canonical"] += 1
        worst = {"relaxed": (0, ""), "all": (0, ""), "violating": (0, "")}
        by_kind: dict[str, Counter] = {}
        seen = 0
        for w in writes(state):
            p = copy.deepcopy(pool)
            removed, violations = apply(p, w)
            kind, violating = w[0], w[1]
            k = by_kind.setdefault(kind, Counter())
            k["relaxed"] = max(k["relaxed"], removed["relaxed"])
            k["all"] = max(k["all"], removed["relaxed"] + removed["canonical"])
            if violating:
                seen += violations > 0
                if removed["relaxed"] + removed["canonical"] > worst["violating"][0]:
                    worst["violating"] = (removed["relaxed"] + removed["canonical"], kind)
                continue
            if removed["relaxed"] > worst["relaxed"][0]:
                worst["relaxed"] = (removed["relaxed"], kind)
            if removed["relaxed"] + removed["canonical"] > worst["all"][0]:
                worst["all"] = (removed["relaxed"] + removed["canonical"], kind)
        violating = sum(1 for w in writes(state) if w[1])
        rows.append([name, admitted["canonical"], admitted["relaxed"], sum(results.values()) - sum(admitted.values()),
                     *worst["relaxed"], *worst["all"], *worst["violating"],
                     f"{seen} of {violating}" if cfg.relaxed else "n/a"])
        detail[name] = (by_kind, results)
    return rows, detail


# --- section 2: violations seen, and the rate after -----------------------------------------------------------

def rate_after(cfg) -> list:
    """A pool whose declared root contract has been violated 0 to 3 times, then 20 new readers of its set roots;
    and how many it admits after each refresh of RM-6, an hour apart."""
    rng = random.Random(SEED + 1)
    rows = []
    for violations in range(4):
        state, _ = workload(random.Random(SEED))
        pool = FramePool(HEAD, state, cfg, Reserver())
        for v in range(violations):  # one block each, each rewriting a set root
            slot = ROOT_FIRST + v
            new = pool.state.copy()
            new.edit(ROOTS).storage[slot] = pool.state.storage(ROOTS, slot) + 1
            head = Head(number=pool.head.number + 1, timestamp=pool.head.timestamp + SLOT)
            pool.reset(head, new, access_lists=[{ROOTS: {"storage_changes": {slot: [(0, new.storage(ROOTS, slot))]}}}])
        row = [violations, pool.declaration_status("root-pool")["state"]]
        for hour in range(3):
            now = hour * 3600
            pool.tick(now)
            for h in list(pool.entries):
                pool._remove(h, "test")
            ok = 0
            for i in range(20):
                slot = ROOT_FIRST + ROOTS_SET - 1 - rng.randrange(4)  # roots no violation rewrote
                user = f"r{violations}-{hour}-{i}"
                pool.state.edit(user).code, pool.state.edit(user).balance = "account-v1", 10**12
                tx = self_tx(user, reads=[(ROOTS, slot, pool.state.storage(ROOTS, slot))])
                ok += pool.add([tx], now)[0] == "ok"
            row += [pool.declaration_status("root-pool")["violations"], ok]
        rows.append(row)
    return rows


# --- section 3: the tiers --------------------------------------------------------------------------------------

def graph(rng: random.Random) -> dict[int, set[int]]:
    """A connected graph of NODES nodes, each with at least DEGREE peers."""
    peers = {n: set() for n in range(NODES)}
    order = list(range(NODES))
    for a, b in zip(order, order[1:] + order[:1]):  # a ring first, so it is connected
        peers[a].add(b)
        peers[b].add(a)
    while any(len(p) < DEGREE for p in peers.values()):
        a = min((n for n in peers if len(peers[n]) < DEGREE), key=lambda n: (len(peers[n]), n))
        b = rng.choice([n for n in peers if n != a and n not in peers[a]])
        peers[a].add(b)
        peers[b].add(a)
    return peers


def copies(peers: dict[int, set[int]], rng: random.Random, n: int = 200) -> float:
    """The copies of a transaction a node receives when every node forwards it to every peer once."""
    total = 0
    for _ in range(n):
        origin = rng.randrange(NODES)
        got = Counter()
        frontier, seen = [origin], {origin}
        while frontier:
            nxt = []
            for a in frontier:
                for b in peers[a]:
                    got[b] += 1
                    if b not in seen:
                        seen.add(b)
                        nxt.append(b)
            frontier = nxt
        total += sum(got.values())
    return total / (n * NODES)


def stream(rng: random.Random, rate: float):
    """Honest spends paid by tickets, each with one proof, at `rate` a second over RUN seconds, and a junk sender
    who spends JUNK_TICKETS tickets on transactions whose proofs fail, JUNK_COPIES of each; then transactions
    with neither a claim nor a prefix of protocol-defined frames."""
    t, i, out = 0.0, 0, []
    while True:
        t += rng.expovariate(rate)
        if t >= RUN:
            break
        sender = f"w{i}"
        epoch = (HEAD.timestamp + int(t)) // EPOCH
        dep = Dependency(17, f"spend-{i}", "vk")
        tx = paid_tx(sender, TPM, claim=claim(sender, f"h{i}", epoch), data=188, deps=[dep])
        out.append((t, "honest", tx, True))
        i += 1
    for j in range(JUNK_TICKETS):
        t = RUN * (j + 0.5) / JUNK_TICKETS
        epoch = (HEAD.timestamp + int(t)) // EPOCH
        for c in range(JUNK_COPIES):
            dep = Dependency(17, f"junk-{j}-{c}", "vk")
            junk_claim = Claim(sender="j0", nonce_seq=0, epoch=epoch, salt=f"j{j}", binder="b1", nonce_keys=(j + 1,))
            tx = paid_tx("j0", TPM, key=j + 1, claim=junk_claim, data=188, deps=[dep])
            out.append((t + c, "junk", tx, False))
    for j in range(20):
        out.append((RUN * (j + 0.5) / 20, "unchecked", self_tx(f"z{j}"), True))
    out.sort(key=lambda x: x[0])
    return out


def tier_run(cfg, tier: str, events) -> dict:
    """One node of a tier fed the whole stream, a block every SLOT seconds including what it holds."""
    state = State()
    acc = state.edit(TPM)
    acc.code, acc.stake, acc.unstake_delay, acc.balance = "ticket-pm", 10**18, 86400, 10**15
    for _, _, tx, _ in events:
        if tx.sender != TPM:
            state.edit(tx.sender).code, state.edit(tx.sender).balance = "account-v1", 10**12
    pool = TxPool(HEAD, state, frame_config=cfg.with_(tier=tier))
    agg = Aggregator(pool)
    frame = pool.frame
    frame.give(TPM, *HISTORY)  # CG-11: a ticket paymaster with a record, not one the node has just met
    out = Counter()
    next_block, number = SLOT, HEAD.number
    peak_pending = peak_keys = peak_claims = 0
    for t, kind, tx, valid in events:
        while t >= next_block:  # a block including everything pending
            peak_keys = max(peak_keys, len({k for e in frame.entries.values() for k in e.sim.deps}))
            peak_claims = max(peak_claims, sum(1 for c in frame.forwarded if c.epoch == frame.epoch()))
            number += 1
            new = frame.state.copy()
            for txs in frame.content().values():
                for p in txs:
                    for k in p.nonce_keys:
                        new.bump_nonce_seq(p.sender, k)
            frame.reset(Head(number=number, timestamp=HEAD.timestamp + next_block), new, next_block)
            next_block += SLOT
        before = agg.work["proof"], sum(frame.work.values())
        if cfg.dependency_frames and tx.claim is not None and any(f.mode == 3 for f in tx.frames):
            answer = agg.receive(Wrapper(txs=(tx,), mode=0, deps=tuple(tx.frames[0].deps), proofs=(valid,)), t)
            answer = answer if isinstance(answer, str) else answer[0]
        else:
            answer = pool.add([tx], t)[0]
        out[(kind, answer)] += 1
        out[(kind, "proofs")] += agg.work["proof"] - before[0]
        out[(kind, "prefixes")] += sum(frame.work.values()) > before[1]
        peak_pending = max(peak_pending, len(frame.entries))
    out["peak pending"], out["peak keys"] = peak_pending, peak_keys
    out["peak claims"] = peak_claims
    return out


NODE_KINDS = (("canonical", "canonical", "verifier"), ("relay", "relaxed", "relay"),
              ("verifier", "relaxed", "verifier"))


def tiers(configs: dict, rng: random.Random) -> tuple[list, list, float, dict]:
    peers = graph(rng)
    c = copies(peers, rng)
    runs = {}
    for rate in RATES:
        events = stream(random.Random(SEED + rate), rate)
        runs[rate] = {kind: tier_run(configs[name], tier, events) for kind, name, tier in NODE_KINDS}
        runs[rate]["n"] = sum(1 for e in events if e[1] == "honest")
    rows = []
    for rate in RATES:
        r = runs[rate]
        honest = r["n"]
        for tier, _, _ in NODE_KINDS:
            o = r[tier]
            proofs = o[("honest", "proofs")] + o[("junk", "proofs")]
            prefixes = o[("honest", "prefixes")] + o[("junk", "prefixes")] + o[("unchecked", "prefixes")]
            kib_in = (o[("honest", "ok")] / RUN) * (TX_BYTES * c / 1024 + (MEAN_KIB if tier == "verifier" else 0))
            held = o["peak pending"] * MEAN_KIB / 1024 if tier == "verifier" else 0
            rows.append([rate, tier, o[("honest", "ok")], honest, prefixes, proofs,
                         f"{proofs * VERIFY_MS / RUN:.1f}", o["peak pending"], o["peak keys"], o["peak claims"],
                         f"{held:.1f}", f"{kib_in:.1f}"])
    junk = []
    for rate in RATES:
        r = runs[rate]
        for tier, _, _ in NODE_KINDS:
            o = r[tier]
            junk.append([rate, tier, JUNK_TICKETS * JUNK_COPIES, o[("junk", "ok")], o[("junk", "proofs")],
                         f"{o[('junk', 'ok')] / JUNK_TICKETS:.2f}", o[("unchecked", "ok")]])
    return rows, junk, c, runs


def network(c: float) -> list:
    """Per node, at a rate of proof-carrying transactions across the network: what each tier receives, at the
    benchmark's mean proof and its smallest and largest, and the rate one 50 Mbps uplink carries."""
    rows = []
    tx = TX_BYTES
    uplink = UPLINK_MBPS * 10**6 / 8
    for mix, relays in MIXES:
        verifiers = NODES - relays
        for rate in RATES:
            relay_in = rate * tx * c
            fetched = rate * (tx * c + MEAN_KIB * 1024)  # a verifier's proof fetched once
            pushed = rate * (tx + MEAN_KIB * 1024) * c  # a proof that travels with its transaction
            rows.append([mix, verifiers, rate, f"{relay_in / 1024:.1f}" if relays else "n/a",
                         f"{fetched / 1024:.0f}", f"{pushed / 1024:.0f}", f"{rate * VERIFY_MS:.0f}",
                         f"{rate * VERIFY_MS * verifiers / 1000:.1f}"])
    limits = []
    for kib in (SMALL_KIB, MEAN_KIB, LARGE_KIB):
        once = uplink / (tx * c + kib * 1024)
        pushed = uplink / ((tx + kib * 1024) * c)
        relay = uplink / (tx * c)
        limits.append([f"{kib:.1f}", f"{relay:.0f}", f"{once:.1f}", f"{pushed:.1f}"])
    return rows, limits, tx


STREAM = len(workload(random.Random(SEED))[1])


def main() -> None:
    configs, child = descriptors()
    rows, detail = bound(configs)
    kinds = sorted({k for by_kind, _ in detail.values() for k in by_kind})
    per_kind = [[k] + [f"{detail[n][0][k]['relaxed']} / {detail[n][0][k]['all']}" for n in configs] for k in kinds]
    refusals = sorted({c for _, results in detail.values() for c in results if c != "ok"})
    codes = [[c] + [detail[n][1][c] for n in configs] for c in refusals]
    after = rate_after(configs["relaxed"])
    trows, junk, c, _ = tiers(configs, random.Random(SEED + 2))
    nrows, limits, tx_bytes = network(c)
    out = [
        "# Experiment 27: results",
        "",
        "Produced by `python3 experiments/27-relaxed-tiers/run.py` (seed 27). Do not edit by hand. The declarations "
        f"are a child of `relaxed.json` that replaces RM-3 (DS-5), `{child}`.",
        "",
        "## 1. The worst-case invalidation from one write",
        "",
        f"The same seeded stream of {STREAM} transactions into one pool under each descriptor, then, one at a time on a "
        "copy of that pool, every write it knows a key for, at the next head with its block's access list. "
        "Admitted counts what the canonical modules admitted and what only the relaxations did (RM-2); the worst "
        "write is the one that removed the most, over the writes that break no declaration, and then over those "
        "that do (RM-6). Seen counts the violating writes whose block raised the declared code's count.",
        "",
        table(["descriptor", "canonical", "relaxed", "refused", "relaxed removed", "by", "all removed", "by",
               "violating: removed", "by", "seen"], rows),
        "",
        "Removed by the worst write of each kind, relaxed / all:",
        "",
        table(["write"] + list(configs), per_kind),
        "",
        "Refusals in the stream, by code:",
        "",
        table(["code"] + list(configs), codes),
        "",
        "## 2. A violated declaration's rate after",
        "",
        "A pool under `relaxed.json` with declarations whose root contract was violated 0 to 3 times, one block "
        "each, then 20 new readers of roots no violation rewrote, at the start and after one and two of RM-6's "
        "hourly refreshes; the pool is emptied before each 20.",
        "",
        table(["violations", "state", "count at 0 h", "admitted", "count at 1 h", "admitted", "count at 2 h",
               "admitted"], after),
        "",
        "## 3. The tiers",
        "",
        f"A node under the canonical descriptor, and one of each tier under `relaxed.json` with declarations, fed "
        f"the same seeded stream over {RUN} s: honest spends paid by tickets, one proof "
        f"each, arriving as a Poisson process at the rate shown; a junk sender's {JUNK_TICKETS} tickets, each sent "
        f"{JUNK_COPIES} times, each time with another failing proof; and 20 transactions with neither a claim nor "
        "a protocol-defined prefix. Every slot a block includes what the node holds. Prefixes counts the "
        "transactions whose prefix the node ran at admission, proofs the proofs it verified, CPU the verifying "
        f"time a second at {VERIFY_MS} ms a proof; pending, keys and claims are peaks at a block: keys are the "
        "state the pending transactions' recorded dependencies name, claims RM-8's forwarded claims of the "
        f"current epoch; proofs held is what the pending transactions' proofs weigh, in MiB, at {MEAN_KIB} KiB "
        "each; KiB in a second counts each transaction's "
        f"{tx_bytes} bytes {c:.2f} times, the copies a node of a {NODES}-node network of degree {DEGREE} receives "
        f"when every node sends it to every peer, and a verifier's proof once at {MEAN_KIB} KiB.",
        "",
        table(["rate /s", "tier", "honest admitted", "honest sent", "prefixes", "proofs", "CPU ms/s",
               "pending", "keys", "claims", "proofs held", "KiB/s in"], trows),
        "",
        "Junk against each tier: what a relay carried per junk ticket, and what a verifier verified; and the "
        "transactions with neither a claim nor a protocol-defined prefix that each carried.",
        "",
        table(["rate /s", "tier", "junk sent", "junk carried", "junk proofs verified", "carried per ticket",
               "unchecked carried"], junk),
        "",
        f"Per node, by mix, at a rate across the network, in KiB a second: a relay; a verifier that fetches each "
        f"proof once; a verifier that receives each proof with its transaction, {c:.2f} times; one verifier's CPU, "
        "and the network's verifying in CPU seconds a second.",
        "",
        table(["mix", "verifiers", "rate /s", "relay KiB/s", "verifier, fetched once", "verifier, pushed",
               "verifier CPU ms/s", "network CPU s/s"], nrows),
        "",
        f"The rate of proof-carrying transactions one {UPLINK_MBPS} Mbps link carries into a node, by proof size, "
        "from the benchmark's smallest, mean and largest proof:",
        "",
        table(["proof KiB", "relay", "verifier, fetched once", "verifier, pushed"], limits),
        "",
    ]
    print("\n".join(out))


if __name__ == "__main__":
    main()
