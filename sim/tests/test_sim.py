import random
from collections import Counter
import unittest
from unittest import mock
from dataclasses import replace

from emem import (CLAIM_GATED, EIP_8141, EIP_8184, EIP_8266, EIP_8272, EIP_8288, GETH, HEGOTA_TESTNET, MATCHA, Account, Block, Frame, FrameTx, Head,
                  Signature, State, TxPool)
from emem_sim import (BumpLoad, ChainConfig, Clearing, Committee, CopiesLoad, FanOutLoad, FloodLoad, FrameLoad, FramingLoad,
                      HotWallet,
                      InvalidProofLoad, JunkLoad, KeyCommittee,
                      Network, NetworkConfig, Node, ProofLoad, Recorder, RootSpendLoad, RootWriter, Scenario, Scheduler, SealedFlood, SealedLoad, SharedSenderLoad, SlotWriter,
                      ShuffleRounds, Simulation, SponsoredLoad, Spend,
                      SybilLoad, Tickets, TransferLoad, Updater, Upgrade, WalletLoad, backed_tx, bump_fees, fixed, one_of, uniform)
from emem_sim.batch import MEASURED, SINGLE_MS, batch_ms, verify
from emem_sim.issuers import BANNED, THROTTLED, Bond, Defence, Issuers, JunkProofs, guard
from emem_sim.network import INFLATED, budget


def small(seed=3, nodes=8):
    senders = [f"u{i}" for i in range(40)]
    sc = Scenario(seed=seed, nodes=nodes, network=NetworkConfig(degree=3),
                  genesis=Head(timestamp=0, gas_limit=2_100_000, gas_used=1_050_000, base_fee=10**9),
                  accounts={s: 10**20 for s in senders + [f"f{i}" for i in range(5)]})
    sim = Simulation(sc)
    sim.add_load(TransferLoad("t", rate=1.0, senders=senders))
    sim.add_load(FrameLoad("f", rate=0.2, senders=[f"f{i}" for i in range(5)]))
    return sim


class TestScheduler(unittest.TestCase):
    def test_time_then_insertion_order(self):
        s, seen = Scheduler(), []
        s.at(2, lambda: seen.append("b"))
        s.at(1, lambda: seen.append("a"))
        s.at(2, lambda: seen.append("c"))
        s.run(10)
        self.assertEqual(seen, ["a", "b", "c"])
        self.assertEqual(s.now, 10)

    def test_refuses_the_past(self):
        s = Scheduler()
        s.run(5)
        with self.assertRaises(ValueError):
            s.at(4, lambda: None)


class TestSimulation(unittest.TestCase):
    def test_same_seed_same_run(self):
        a, b = small().run(240), small().run(240)
        self.assertEqual([(r.tx.hash, r.included_at) for r in a.txs.values()],
                         [(r.tx.hash, r.included_at) for r in b.txs.values()])
        self.assertEqual(a.blocks, b.blocks)

    def test_transactions_spread_and_are_included(self):
        sim = small()
        rec = sim.run(300)
        settled = [r for r in rec.txs.values() if r.submitted_at < 250]
        self.assertTrue(settled)
        for r in settled:
            self.assertIsNotNone(r.included_at, r.tx.label)
        # A transaction included before it reaches a node is refused there as
        # ErrNonceTooLow and goes no further, so not every one reaches all eight.
        everywhere = sum(len(r.first_seen) == 8 for r in settled)
        self.assertGreaterEqual(everywhere / len(settled), 0.9)

    def test_pools_agree_with_the_chain_after_a_block(self):
        sim = small()
        sim.run(126)  # every node has imported the block of slot 120 by 121
        for node in sim.net.nodes.values():
            for txs in node.pool.content()[0].values():
                for tx in txs:
                    self.assertGreaterEqual(tx.nonce, sim.chain.state.nonce_seq(tx.sender, 0))

    def test_topology_is_connected(self):
        sim = small(nodes=12)
        seen, todo = set(), ["n00"]
        while todo:
            n = todo.pop()
            if n not in seen:
                seen.add(n)
                todo.extend(sim.net.nodes[n].peers)
        self.assertEqual(len(seen), 12)



def spend(key, tip=10):
    frames = (Frame(mode=1, flags=3, exec_gas=15000, approves=3), Frame(mode=2, exec_gas=30000))
    return FrameTx("pool", frames, nonce_keys=(key,), signatures=(), max_fee=100, tip=tip, label=f"s{key}")


class TestGossip(unittest.TestCase):
    """The fetcher of go-ethereum `eth/fetcher/tx_fetcher.go`, as `network.py` describes it."""

    def setUp(self):
        self.sched = Scheduler()
        self.net = Network(self.sched, random.Random(1), Recorder(), NetworkConfig())
        self.head = Head(timestamp=0, gas_limit=30_000_000, gas_used=15_000_000, base_fee=10)
        self.state = State({"pool": Account(balance=10**18, code="privacy-pool")})
        for name in ("a", "b", "c"):
            self.net.add(Node(name, TxPool(self.head, self.state), self.net))
        self.net.connect("a", "b")
        self.net.connect("a", "c")
        self.a, self.b, self.c = (self.net.nodes[n] for n in "abc")

    @staticmethod
    def hold(node, tx):
        """Put `tx` in `node`'s pool without the node gossiping it."""
        node.pool.add([tx])
        node.pool.frame.log.clear()

    def included(self, tx):
        post = self.state.copy()
        post.bump_nonce_seq(tx.sender, tx.nonce_keys[0])
        return Block(Head(1, 12, self.head.gas_limit, 0, self.head.next_base_fee()), (tx,), ()), post

    def test_a_refused_transaction_is_fetched_again_on_a_new_announcement(self):
        s1, s2 = spend(1), spend(2)
        self.hold(self.a, s1)
        self.hold(self.b, s2)
        self.a.receive([s2], "b")  # refused: a still holds s1
        self.assertIsNone(self.a.pool.get(s2.hash))
        self.a.on_block(*self.included(s1))
        self.hold(self.c, s2)
        self.a.on_announce([s2.hash], "c")
        self.sched.run(0.4)
        self.assertIsNone(self.a.pool.get(s2.hash))  # waiting for a push, txArriveTimeout
        self.sched.run(1.0)
        self.assertIsNotNone(self.a.pool.get(s2.hash))

    def test_an_underpriced_refusal_is_not_fetched_again(self):
        held = spend(1)
        underbid = replace(held, max_fee=105)  # a 5 percent bump on one fee only
        self.hold(self.a, held)
        self.a.receive([underbid], "b")
        self.hold(self.c, underbid)
        self.a.on_announce([underbid.hash], "c")
        self.assertEqual(self.a.fetching, {})
        self.sched.run(2.0)
        self.assertEqual(self.a.pool.get(held.hash), held)
        self.assertIsNone(self.a.pool.get(underbid.hash))

    def test_nothing_in_an_imported_block_is_fetched(self):
        s1 = spend(1)
        self.a.on_block(*self.included(s1))
        self.hold(self.c, s1)
        self.a.on_announce([s1.hash], "c")
        self.sched.run(2.0)
        self.assertEqual(self.a.fetching, {})
        self.assertIsNone(self.a.pool.get(s1.hash))

    def test_a_sender_always_takes_the_same_first_hops(self):
        node = self.net.nodes["a"]
        self.assertEqual(node.direct_peers("x"), node.direct_peers("x"))
        self.assertEqual(len(node.direct_peers("x")), 2)  # ceil(sqrt(2))


def shared(profile, rule="relayer", rate=0.2, nodes=8, seed=5, **kwargs):
    sc = Scenario(seed=seed, nodes=nodes, network=NetworkConfig(degree=3), frame_pool=profile,
                  genesis=Head(timestamp=0, gas_limit=2_100_000, gas_used=1_050_000, base_fee=10**9),
                  accounts={"pool": 10**24, "admin": 10**24, EIP_8141.expiry_verifier: 0},
                  code={"pool": "privacy-pool", EIP_8141.expiry_verifier: "expiry-verifier"})
    sim = Simulation(sc)
    kwargs.setdefault("serial", profile.per_sender == "one")
    load = SharedSenderLoad("s", rate=rate, senders=["pool"], rule=rule, **kwargs)
    sim.add_load(load)
    return sim, load


def landed_per_block(sim, load):
    rec = sim.recorder
    times = [rec.txs[sp.tx.hash].included_at for sp in load.spends
             if sp.tx is not None and sp.tx.hash in rec.txs and rec.txs[sp.tx.hash].included_at is not None]
    return [times.count(b["at"]) for b in rec.blocks]


class TestSharedSender(unittest.TestCase):
    DISJOINT = replace(EIP_8141, per_sender="disjoint-keys")

    def test_under_one_a_block_carries_at_most_one_spend(self):
        sim, load = shared(EIP_8141)
        sim.run(600)
        self.assertEqual(max(landed_per_block(sim, load)), 1)
        self.assertGreater(load.backlog(), 0)

    def test_a_successor_sent_as_its_proposer_imports_is_refused_by_peers_that_have_not(self):
        # n00 proposes block 41 and imports it at once; its relayer sends the
        # next spend while every peer still holds the one just included.
        sim, load = shared(EIP_8141)
        sim.run(600)
        per_block = landed_per_block(sim, load)
        self.assertEqual(per_block[41:48], [0] * 7)
        successor = load.spends[40]
        self.assertEqual(sim.recorder.txs[successor.tx.hash].submitted_at, 492.0)
        self.assertEqual(sim.recorder.txs[successor.tx.hash].results["ErrFrameSenderBusy"],
                         len(sim.net.nodes["n00"].peers))

    def test_a_relayer_that_waits_for_the_network_loses_no_slot(self):
        sim, load = shared(EIP_8141)
        load.wait = 1.0  # the latest a node imports a block, ChainConfig.block_delay
        sim.run(600)
        per_block = landed_per_block(sim, load)
        first = per_block.index(1)
        self.assertEqual(per_block[first:], [1] * (len(per_block) - first))

    def test_under_disjoint_keys_every_spend_lands_and_blocks_carry_several(self):
        sim, load = shared(self.DISJOINT)
        sim.run(600)
        asked_early = [sp for sp in load.spends if sp.requested_at < 580]
        self.assertTrue(all(sim.recorder.txs[sp.tx.hash].included_at is not None for sp in asked_early))
        self.assertGreater(max(landed_per_block(sim, load)), 1)

    def test_the_demand_does_not_depend_on_the_profile_or_the_rule(self):
        runs = [shared(EIP_8141), shared(self.DISJOINT), shared(EIP_8141, "direct")]
        for sim, _ in runs:
            sim.run(300)
        asked = [[(sp.requested_at, sp.sender, sp.tip) for sp in load.spends] for _, load in runs]
        self.assertEqual(asked[0], asked[1])
        self.assertEqual(asked[0], asked[2])

    def test_direct_users_are_refused_and_retry(self):
        sim, load = shared(EIP_8141, "direct")
        sim.run(600)
        answers = [a for sp in load.spends for a in sp.answers]
        self.assertIn("ErrFrameSenderBusy", answers)
        self.assertTrue(any(len(sp.answers) > 1 for sp in load.spends))
        self.assertEqual(max(landed_per_block(sim, load)), 1)


class TestExpiringSpends(unittest.TestCase):
    def test_a_relayer_lands_several_a_block_and_no_sequence_moves(self):
        sim, load = shared(EIP_8266, serial=False, expiring=48, key_bytes=32)
        sim.run(600)
        asked_early = [sp for sp in load.spends if sp.requested_at < 580]
        self.assertTrue(all(sim.recorder.txs[sp.tx.hash].included_at is not None for sp in asked_early))
        self.assertGreater(max(landed_per_block(sim, load)), 1)
        state = sim.chain.state
        self.assertEqual(state.account("pool").nonce_seqs, {})
        self.assertTrue(all(state.storage("pool", load.nullifier(sp)) == 1 for sp in asked_early))
        self.assertTrue(all(sp.tx.nonce_keys == (EIP_8266.expiring_key,) for sp in load.spends))

    def test_a_spend_that_waits_past_its_deadline_is_signed_again_and_lands_once(self):
        # Four spends a second for two minutes, against 25 a block.
        sim, load = shared(EIP_8266, rate=4.0, serial=False, expiring=48, key_bytes=32, stop=120)
        sim.run(900)
        rec = sim.recorder
        landed = [[v for v in sp.versions if rec.txs[v.hash].included_at is not None] for sp in load.spends]
        self.assertTrue(all(len(v) == 1 for v in landed))
        self.assertTrue(any(len(sp.versions) > 1 for sp in load.spends))
        for sp in load.spends:
            deadlines = [v.frames[0].deadline for v in sp.versions]
            self.assertEqual(deadlines, sorted(set(deadlines)))

    def test_under_one_a_serial_relayer_still_lands_one_a_block(self):
        sim, load = shared(replace(EIP_8266, expiring_per_sender="one"), serial=True, expiring=48, key_bytes=32)
        sim.run(600)
        self.assertEqual(max(landed_per_block(sim, load)), 1)
        self.assertGreater(load.backlog(), 0)


class TestMatcha(unittest.TestCase):
    """Finality, width and the junk adversary: `docs/spec/04-matcha.md` in the simulator."""

    DISJOINT = replace(EIP_8141, per_sender="disjoint-keys")

    def test_a_block_is_final_two_epochs_after_its_epoch_starts(self):
        sim, _ = shared(MATCHA, rate=0.01)
        sim.run(100 * 12 + 1)
        self.assertEqual(sim.chain.head.number, 100)
        self.assertEqual(sim.chain.final, 32 * (100 // 32 - 2))

    def test_width_is_the_gas_of_the_final_spends_when_none_was_additional(self):
        sim, load = shared(MATCHA, rate=0.05, serial=True)  # one outstanding at a time: every spend a baseline
        sim.run(130 * 12 + 2)
        final = sim.chain.final
        blocks = {b["at"]: b["number"] for b in sim.recorder.blocks}
        gas = sum(sp.tx.used for sp in load.spends if sp.tx is not None
                  and sim.recorder.txs[sp.tx.hash].included_at is not None
                  and blocks[sim.recorder.txs[sp.tx.hash].included_at] <= final)
        self.assertGreater(gas, 0)
        self.assertEqual(sim.net.nodes["n00"].pool.frame.width("pool"), gas)

    def test_several_spends_a_block_only_once_width_has_been_earned(self):
        sim, load = shared(MATCHA, rate=1.0, serial=False, resend=True)
        credited = []
        sim.net.nodes["n00"].import_hooks.append(
            lambda node, block: credited or node.pool.frame.width("pool") == 0 or credited.append(sim.sched.now))
        sim.run(1800)
        per_block = landed_per_block(sim, load)
        times = [b["at"] for b in sim.recorder.blocks]
        self.assertTrue(credited)
        self.assertGreaterEqual(credited[0], 64 * 12)
        self.assertEqual(max(n for n, t in zip(per_block, times) if t < credited[0]), 1)
        self.assertGreater(max(per_block), 1)

    def test_the_spend_shape_of_experiment_02(self):
        load = SharedSenderLoad("s", rate=1, senders=["pool"], verify_gas=5000, verify_bytes=260, exec_gas=41000,
                                exec_bytes=68, expiry=86400, key_bytes=32)
        sim, _ = shared(MATCHA)
        tx = load.spend_tx(sim, Spend(0, "s-0", "pool", 0.0, 10))
        self.assertEqual(tx.nonce_keys[0].bit_length(), 256)
        self.assertEqual((len(tx.frames), tx.data_bytes, tx.gas.intrinsic, tx.max_gas), (3, 456, 23521, 69621))

    def test_one_flip_invalidates_every_junk_spend_under_disjoint_keys(self):
        sim, load = shared(self.DISJOINT, rate=0.001)
        junk = JunkLoad("junk", senders=["pool"], node="n01", burst=5, setting=("pool", 1), flipper="admin",
                        start=0, stop=13)
        sim.add_load(junk)
        sim.run(12 * 3 + 2)
        flip = junk.flips[0]
        self.assertIsNotNone(sim.recorder.txs[flip.hash].included_at)
        for node in sim.net.nodes.values():
            self.assertEqual([tx for tx in node.pool.frame.content().get("pool", []) if tx.label.startswith("junk")],
                             [])
            self.assertGreaterEqual(node.pool.frame.resimulations, 5)

    def test_under_matcha_junk_beyond_the_baseline_needs_width(self):
        sim, load = shared(MATCHA, rate=0.001)
        junk = JunkLoad("junk", senders=["pool"], node="n01", burst=5, start=0, stop=13)
        sim.add_load(junk)
        sim.run(14)
        self.assertEqual([sp.answers for sp in junk.spends], [["ok"], ["ErrFrameInsufficientWidth"]])

    def test_a_slot_writer_rewrites_its_slot_once_a_block(self):
        sim, _ = shared(MATCHA, rate=0.001)
        writer = SlotWriter("deposit", senders=["admin"], node="n00", address="pool", slot=0)
        sim.add_load(writer)
        sim.run(12 * 6 + 2)
        landed = [tx for tx in writer.writes if sim.recorder.txs[tx.hash].included_at is not None]
        self.assertGreaterEqual(len(landed), 4)
        self.assertEqual([tx.nonce for tx in writer.writes], list(range(len(writer.writes))))
        self.assertEqual(sim.chain.state.storage("pool", 0), len(landed))
        self.assertEqual({tx.gas for tx in writer.writes}, {26_000})

    def test_a_spend_reads_nothing_its_own_nullifier_or_the_root(self):
        sim, _ = shared(MATCHA)
        spend = Spend(0, "s-0", "pool", 0.0, 10)
        for reads, want in (("none", ()), ("own", (("pool", 1, 0),)), ("root", (("pool", 7, None),))):
            load = SharedSenderLoad("s", rate=1, senders=["pool"], reads=reads, root_slot=7)
            self.assertEqual(load.spend_tx(sim, spend).frames[0].reads, want, reads)

    def test_junk_reading_a_setting_each_is_all_baseline_under_slot_only(self):
        for contention in ("slot", "storage"):
            sim, _ = shared(replace(MATCHA, contention=contention), rate=0.001)
            junk = JunkLoad("junk", senders=["pool"], node="n01", burst=5, setting=("pool", 1), flipper="admin",
                            slots=5, flip_held=True, start=0, stop=13)
            sim.add_load(junk)
            sim.run(14)
            flip = junk.flips[0]
            if contention == "slot":
                self.assertEqual([sp.answers for sp in junk.spends], [["ok"]] * 5)
                self.assertEqual(sorted(k for _, k, _ in flip.writes), [1, 2, 3, 4, 5])
                self.assertEqual(flip.gas, 21_000 + 5 * 5_000)  # a slot each, one account
            else:
                self.assertEqual([sp.answers for sp in junk.spends], [["ok"], ["ErrFrameInsufficientWidth"]])
                self.assertEqual((flip.writes, flip.gas), ((("pool", 1, 1),), 26_000))  # the one setting held



def fanned(profile, shape, k=12, verify_gas=20000, nodes=6, touches=3):
    senders = FanOutLoad.sender_names("fan", shape, k, "payer")
    code = {"sponsor": {}, "paymaster": {"payer": "canonical-paymaster"}, "noncanonical": {"payer": "paymaster"},
            "shared-sender": {"payer": "account"}}[shape]
    if shape != "shared-sender":
        code = {**code, **{s: "account" for s in senders}}
    sim = Simulation(Scenario(seed=2, nodes=nodes, network=NetworkConfig(degree=3), frame_pool=profile,
                              genesis=Head(timestamp=0, gas_limit=2_100_000, gas_used=1_050_000, base_fee=10**9),
                              accounts={"payer": 10**18, "toucher": 10**20}, code=code))
    load = FanOutLoad("fan", shape=shape, k=k, payer="payer", node="n00", verify_gas=verify_gas, toucher="toucher",
                      targets=[f"n{i:02d}" for i in range(nodes)], start=5, touch_from=13, stop=13 + 12 * touches)
    sim.add_load(load)
    imports = []
    for node in sim.net.nodes.values():
        node.import_hooks.append(lambda node, block: imports.append((block, len(node.pool.frame.resimulated))))
    sim.run(13 + 12 * touches + 24)
    touched = {tx.hash for tx in load.touches}
    counts = [n for block, n in imports if any(tx.hash in touched for tx in block.txs)]
    return sim, load, counts


class TestFanOut(unittest.TestCase):
    def test_backed_tx_shapes_pass_static_checks(self):
        from emem.framepool.prefix import check_static
        for shape in ("sponsor", "paymaster", "noncanonical", "shared-sender"):
            tx = backed_tx(shape, "s" if shape != "shared-sender" else "payer", "payer", max_fee=1, tip=1, label=shape,
                           key=1 if shape == "shared-sender" else 0, verify_gas=80000)
            self.assertNotIsInstance(check_static(tx, Head(timestamp=0, gas_limit=2_100_000), EIP_8141), str, shape)

    def test_one_touch_re_simulates_every_backed_transaction_at_every_node(self):
        sim, load, counts = fanned(EIP_8141, "sponsor")
        self.assertEqual(sim.chain.state.code(load.senders[0]), "account")  # an address with code and no balance
        self.assertEqual(len(load.touches), 3)
        self.assertEqual(counts, [12] * (6 * 3))
        for node in sim.net.nodes.values():
            self.assertEqual(len(node.pool.frame.entries), 12)

    def test_the_testnet_caps_a_codeless_sponsor_and_opens_a_shared_sender(self):
        _, load, counts = fanned(HEGOTA_TESTNET, "sponsor")
        self.assertEqual(sum(1 for a in load.answers if "ok" in a), 1)
        self.assertEqual(set(counts), {1})
        _, load, counts = fanned(HEGOTA_TESTNET, "shared-sender")
        self.assertEqual(set(counts), {12})
        _, load, _ = fanned(EIP_8141, "shared-sender")
        self.assertEqual(sum(1 for a in load.answers if "ok" in a), 1)

    def test_balance_reuse_re_simulates_nothing(self):
        sim, _, counts = fanned(EIP_8141.with_(reuse_balance=True), "paymaster")
        self.assertEqual(set(counts), {0})
        self.assertEqual(len(sim.net.nodes["n03"].pool.frame.entries), 12)


class TestSponsored(unittest.TestCase):
    def run_sponsored(self, profile, shape, payer_code):
        users = [f"u{i}" for i in range(200)]
        code = {u: "account" for u in users}
        if payer_code:
            code["payer"] = payer_code
        sim = Simulation(Scenario(seed=4, nodes=6, network=NetworkConfig(degree=3), frame_pool=profile,
                                  genesis=Head(timestamp=0, gas_limit=2_100_000, gas_used=1_050_000, base_fee=10**9),
                                  accounts={"payer": 10**20}, code=code))
        load = SponsoredLoad("use", rate=0.25, senders=users, shape=shape, payer="payer")
        sim.add_load(load)
        rec = sim.run(600)
        return [rec.txs[tx.hash].included_at for tx in load.txs if rec.txs[tx.hash].included_at is not None], load

    def test_a_paymaster_lands_its_users_as_they_ask(self):
        landed, load = self.run_sponsored(EIP_8141, "paymaster", "canonical-paymaster")
        self.assertGreaterEqual(len(landed), len(load.txs) - 6)

    def test_a_capped_sponsor_lands_one_a_block_and_its_users_try_again(self):
        landed, load = self.run_sponsored(HEGOTA_TESTNET, "sponsor", None)
        self.assertLessEqual(max(Counter(landed).values()), 1)
        self.assertIn("ErrFramePaymasterBusy", {a for v in load.answers.values() for a in v})
        self.assertGreater(len(landed), 30)


def flooded(profile, kind=None, max_pending=48, nodes=4, start=30, stop=270):
    users = [f"u{i}" for i in range(60)]
    profile = profile.with_(max_pending=max_pending)
    sponsors = {f"pm-{n}": 10**20 for n in range(int(stop // 12) + 2)}  # a `drained` flood's, one per head
    sim = Simulation(Scenario(seed=5, nodes=nodes, network=NetworkConfig(degree=3), frame_pool=profile,
                              genesis=Head(timestamp=0, gas_limit=2_100_000, gas_used=1_050_000, base_fee=10**9),
                              accounts={**{u: 10**18 for u in users}, "pm": 10**20, **sponsors},
                              code={"pm": profile.canonical_paymaster_code,
                                    profile.expiry_verifier: profile.expiry_verifier_code}))
    wallets = WalletLoad("w", rate=0.3, senders=users, expiring=0.5, expiry=120)
    sim.add_load(wallets)
    flood = None
    if kind:
        flood = FloodLoad("flood", kind=kind, k=max_pending + 16, payer="pm", surplus=16, start=start, stop=stop)
        sim.add_load(flood)
    rec = sim.run(stop + 120)
    during = [tx for tx in wallets.txs if start <= rec.txs[tx.hash].submitted_at < stop - 120]
    landed = {cls: sum(1 for tx in during if (tx.hash in wallets.deadlines) == (cls == "deadline")
                       and (rec.txs[tx.hash].included_at or float("inf")) < stop) for cls in ("pays", "deadline")}
    return sim, wallets, flood, landed


class TestFlood(unittest.TestCase):
    def test_the_self_shape_and_a_deadline_pass_static_checks(self):
        from emem.framepool.prefix import check_static
        head = Head(timestamp=0, gas_limit=2_100_000)
        for profile in (EIP_8141, HEGOTA_TESTNET):
            for deadline in (None, 600):
                tx = backed_tx("self", "u", None, max_fee=10**9, tip=1, label="s", deadline=deadline,
                               expiry_verifier=profile.expiry_verifier)
                self.assertNotIsInstance(check_static(tx, head, profile), str)
                self.assertEqual(tx.frames[0].target == profile.expiry_verifier, deadline is not None)

    def test_a_free_flood_keeps_every_deadline_out_under_the_eips_order(self):
        sim, wallets, flood, landed = flooded(EIP_8141, "free")
        self.assertEqual(landed["deadline"], 0)
        self.assertGreater(landed["pays"], 10)
        self.assertTrue(wallets.expired)
        self.assertEqual(sum(sim.chain.state.nonce(s) for s in flood.senders), 0)  # it never paid
        for node in sim.net.nodes.values():  # nothing removes it afterwards
            self.assertGreater(sum(e.tx.label.startswith("flood") for e in node.pool.frame.entries.values()), 40)

    def test_tip_first_lets_deadlines_through_the_same_flood(self):
        _, _, _, landed = flooded(EIP_8141.with_(evict_first="tip"), "free")
        _, _, _, calm = flooded(EIP_8141.with_(evict_first="tip"))
        self.assertEqual(landed, calm)

    def test_an_expiring_flood_is_harmless_under_the_eips_order_and_not_under_tip_first(self):
        _, _, _, calm = flooded(EIP_8141)
        sim, _, flood, landed = flooded(EIP_8141, "expiring")
        self.assertEqual(landed, calm)
        sim, _, flood, landed = flooded(EIP_8141.with_(evict_first="tip"), "expiring")
        self.assertEqual(landed, {"pays": 0, "deadline": 0})
        self.assertEqual(sum(sim.chain.state.nonce(s) for s in flood.senders), 0)
        self.assertGreater(flood.admitted, 20 * 48 * 4)  # a fresh batch every block

    def test_the_next_slot_check_makes_an_expiring_flood_pay(self):
        sim, _, flood, _ = flooded(EIP_8141.with_(evict_first="tip"), "expiring")
        flooding = [b for b in sim.recorder.blocks if 30 < b["at"] <= 270]
        self.assertTrue(all(b["failed"]["ErrFrameExpired"] > 0 for b in flooding[1:]))  # skipped, never paid
        sim, _, flood, landed = flooded(EIP_8141.with_(evict_first="tip", expiry_margin=12), "expiring")
        flooding = [b for b in sim.recorder.blocks if 30 < b["at"] <= 270]
        self.assertEqual(sum(b["failed"]["ErrFrameExpired"] for b in sim.recorder.blocks), 0)
        self.assertGreater(sum(sim.chain.state.nonce(s) for s in flood.senders), 20 * 30)  # it pays, every block
        self.assertTrue(all(b["gas_used"] > 2_000_000 for b in flooding[1:]))
        self.assertEqual(landed, {"pays": 0, "deadline": 0})  # but it still keeps them out

    def test_a_drained_sponsor_empties_the_pool_for_one_transfer_a_block(self):
        for profile in (EIP_8141, EIP_8141.with_(evict_first="tip", expiry_margin=12)):
            sim, _, flood, landed = flooded(profile, "drained")
            self.assertEqual(landed, {"pays": 0, "deadline": 0})
            self.assertEqual(sum(sim.chain.state.nonce(s) for s in flood.senders), 0)
            drains = sum(sim.chain.state.nonce(flood.sponsor(n)) for n in range(25))
            self.assertGreater(drains, 15)  # what it paid for
            self.assertGreater(sum(b["failed"]["ErrInsufficientFunds"] for b in sim.recorder.blocks), 15 * 48)
        _, _, _, calm = flooded(HEGOTA_TESTNET)
        _, _, flood, landed = flooded(HEGOTA_TESTNET, "drained")  # one transaction per codeless payer (FP-11)
        self.assertGreater(landed["deadline"], calm["deadline"] // 2)
        self.assertGreater(landed["pays"], calm["pays"] // 2)


def sybil(profile, kind, k=4, nodes=6, run=96):
    """Experiment 10's adversary from 24 s to 72 s, alone on a small network."""
    adversary = SybilLoad("a", kind=kind, rate=1.0, k=k, start=24, stop=72)
    accounts = {adversary.payer(0): adversary.funding(4 * 10**9, rounds=5)} if kind == "drained" else {}
    sim = Simulation(Scenario(seed=5, nodes=nodes, network=NetworkConfig(degree=3), frame_pool=profile,
                              genesis=Head(timestamp=0, gas_limit=30_000_000, gas_used=15_000_000, base_fee=10**9),
                              accounts=accounts))
    sim.add_load(adversary)
    return adversary, sim.run(run)


class TestSybil(unittest.TestCase):
    def test_a_sponsor_that_holds_nothing_is_refused_where_it_is_handed_over(self):
        for profile in (EIP_8141, HEGOTA_TESTNET):
            adversary, rec = sybil(profile, "empty")
            self.assertGreater(adversary.sent, 20)
            for tx in adversary.txs:
                self.assertEqual(rec.txs[tx.hash].results, Counter({"ErrInsufficientFunds": 1}))  # FP-8
                self.assertEqual(rec.txs[tx.hash].first_seen, {})  # never pending, so never relayed

    def test_a_drained_sponsor_reaches_every_pool_and_lands_nothing(self):
        adversary, rec = sybil(EIP_8141, "drained")
        self.assertGreaterEqual(len(adversary.transfers), 4)
        self.assertTrue(all(rec.txs[t.hash].block is not None for t in adversary.transfers[:-1]))
        self.assertTrue(all(rec.txs[tx.hash].block is None for tx in adversary.txs))
        reached = Counter(len(rec.txs[tx.hash].first_seen) for tx in adversary.txs)
        self.assertEqual(reached.most_common(1)[0][0], 6)

    def test_the_testnet_holds_one_transaction_a_drained_sponsor_backs_per_pool(self):
        adversary, rec = sybil(HEGOTA_TESTNET, "drained")
        rounds: dict[str, int] = {}
        for tx in adversary.txs:
            sponsor = tx.label.rsplit("-", 1)[0]
            rounds[sponsor] = rounds.get(sponsor, 0) + len(rec.txs[tx.hash].first_seen)
        self.assertGreaterEqual(len(rounds), 4)
        self.assertTrue(all(0 < held <= 6 for held in rounds.values()))
        self.assertGreater(sum(rec.txs[tx.hash].results["ErrFramePaymasterBusy"] for tx in adversary.txs), 0)


def copied(record, copies, static_first=False, nodes=8, run=96):
    """Experiment 11's spends, three a slot from 12 s to 60 s, each handed out as copies."""
    sim = Simulation(Scenario(seed=5, nodes=nodes, network=NetworkConfig(degree=3),
                              frame_pool=HEGOTA_TESTNET.with_(static_first=static_first),
                              genesis=Head(timestamp=0, gas_limit=30_000_000, gas_used=15_000_000, base_fee=10**9),
                              accounts={"pool": 10**24}, code={"pool": "privacy-pool"}))
    load = CopiesLoad("t", rate=0.25, senders=["pool"], copies=copies, record=record, tip=fixed(10**9),
                      start=12, stop=60)
    sim.add_load(load)
    return sim, load, sim.run(run)


class TestCopies(unittest.TestCase):
    def test_copies_under_a_nonce_key_share_one_identity_and_one_lands(self):
        sim, load, rec = copied("nonce", 0)
        self.assertGreaterEqual(len(load.spends), 3)
        for spend in load.spends:
            self.assertEqual(len(spend.copies), 8)
            self.assertEqual(len({(tx.sender, tx.nonce_keys, tx.nonce_seq) for tx in spend.copies}), 1)
            self.assertEqual(sum(rec.txs[tx.hash].block is not None for tx in spend.copies), 1)
            refused = Counter()
            for tx in spend.copies:
                refused.update(rec.txs[tx.hash].results)
            self.assertGreater(refused["ErrReplaceUnderpriced"], 0)  # FP-12: a pool holds one of them
        self.assertEqual(sum(b["failed"].total() for b in rec.blocks), 0)
        for node in sim.net.nodes.values():
            self.assertEqual(node.pool.frame.entries, {})

    def test_copies_under_a_slot_share_a_pool_and_one_lands(self):
        sim, load, rec = copied("slot", 4)
        for spend in load.spends:
            self.assertEqual(len({tx.nonce_keys for tx in spend.copies}), 4)
            self.assertEqual(sum(rec.txs[tx.hash].block is not None for tx in spend.copies), 1)
            self.assertEqual(sim.chain.state.storage("pool", spend.index + 1), 1)
        self.assertGreater(sum(b["failed"]["ErrFramePrefixReverted"] for b in rec.blocks), 0)  # BB-3
        for node in sim.net.nodes.values():
            self.assertEqual(node.pool.frame.entries, {})

    def test_static_first_changes_no_answer_a_copy_gets(self):
        _, plain, a = copied("nonce", 0)
        _, early, b = copied("nonce", 0, static_first=True)
        for x, y in zip(plain.spends, early.spends):
            self.assertEqual([a.txs[tx.hash].results for tx in x.copies], [b.txs[tx.hash].results for tx in y.copies])
            self.assertEqual([a.txs[tx.hash].block for tx in x.copies], [b.txs[tx.hash].block for tx in y.copies])


def observed(spies=("n08",), targets=None, record=True, nodes=9, run=72):
    """Experiment 12's spends, from 12 s to 48 s, on a network whose last node is a spy."""
    honest = [f"n{i:02d}" for i in range(nodes - len(spies))]
    sim = Simulation(Scenario(seed=5, nodes=nodes,
                              network=NetworkConfig(degree=3, record_heard=record, spies=spies),
                              chain=ChainConfig(proposer=tuple(honest)), frame_pool=HEGOTA_TESTNET,
                              genesis=Head(timestamp=0, gas_limit=30_000_000, gas_used=15_000_000, base_fee=10**9),
                              accounts={"pool": 10**24}, code={"pool": "privacy-pool"}))
    load = SharedSenderLoad("s", rate=0.25, senders=["pool"], rule="direct", tip=fixed(10**9),
                            targets=honest if targets is None else targets, start=12, stop=48)
    sim.add_load(load)
    return sim, load, sim.run(run)


class TestObservers(unittest.TestCase):
    def test_every_node_records_when_and_from_whom_it_first_heard(self):
        sim, load, rec = observed()
        self.assertGreaterEqual(len(load.spends), 3)
        for spend in load.spends:
            r = rec.txs[spend.tx.hash]
            for name, node in sim.net.nodes.items():
                at, peer = node.heard[spend.tx.hash]
                self.assertEqual(peer == "", name == r.origin)  # a local client, only at the origin
                self.assertTrue(peer == "" or peer in node.peers)
                self.assertGreaterEqual(at, r.submitted_at)
                if name in r.first_seen:
                    self.assertLessEqual(at, r.first_seen[name])

    def test_a_spy_hears_from_every_node_and_relays_nothing(self):
        sim, load, rec = observed()
        spy = sim.net.nodes["n08"]
        self.assertEqual(sorted(spy.peers), [f"n{i:02d}" for i in range(8)])
        for spend in load.spends:
            self.assertIn(spend.tx.hash, spy.heard)
            for name, node in sim.net.nodes.items():
                self.assertNotEqual(node.heard[spend.tx.hash][1], "n08")
        self.assertTrue(all(rec.txs[sp.tx.hash].origin != "n08" for sp in load.spends))

    def test_a_spy_takes_no_part_in_the_random_topology(self):
        sim, _, _ = observed()
        for i in range(8):  # the spy fills no node's dialled peers
            self.assertGreaterEqual(len(set(sim.net.nodes[f"n{i:02d}"].peers) - {"n08"}), 3)

    def test_without_record_heard_nothing_is_recorded(self):
        sim, _, _ = observed(record=False)
        self.assertTrue(all(node.heard == {} for node in sim.net.nodes.values()))

    def test_direct_spends_go_only_to_the_targets(self):
        _, load, rec = observed(targets=["n01", "n02"])
        self.assertTrue(all(rec.txs[sp.tx.hash].origin in ("n01", "n02") for sp in load.spends))

def floored(price, floor=True, rate=0.5, run=72):
    """Spends from one shared sender under `matcha` with MA-13's floor, the sender starting at the width cap, at a
    tip of 0.002 gwei, above the builders' minimum, so that the baseline lands."""
    sim = Simulation(Scenario(seed=5, nodes=6, network=NetworkConfig(degree=3),
                              frame_pool=MATCHA.with_(load_price=price),
                              genesis=Head(timestamp=0, gas_limit=30_000_000, gas_used=15_000_000, base_fee=10**9),
                              accounts={"pool": 10**24}, code={"pool": "privacy-pool"}))
    for node in sim.net.nodes.values():
        node.pool.frame.finalize([(0, {"pool": MATCHA.width_cap})])
    load = SharedSenderLoad("s", rate=rate, senders=["pool"], rule="direct", tip=fixed(2_000_000), floor=floor,
                            start=12, stop=60)
    sim.add_load(load)
    return sim, load, sim.run(run)


class TestLoadFloor(unittest.TestCase):
    def test_a_user_meets_the_floor_of_the_node_it_sends_to(self):
        sim, load, rec = floored(10**9)
        raised = [sp for sp in load.spends if sp.tip > sp.drawn]
        self.assertGreater(len(raised), 0)
        for sp in raised:
            self.assertEqual(sp.tip % 10**9, 0)  # equal charges: a whole multiple of load_price
            self.assertEqual(sp.tx.tip, sp.tip)
            self.assertNotIn("ErrFrameLoadUnderpriced", sp.answers[:1])
        self.assertTrue(all(rec.txs[sp.tx.hash].block is not None for sp in load.spends))

    def test_without_the_floor_a_user_keeps_its_tip_and_is_refused(self):
        _, load, rec = floored(10**9, floor=False)
        self.assertTrue(all(sp.tip == sp.drawn == 2_000_000 for sp in load.spends))
        refused = Counter()
        for sp in load.spends:
            refused.update(rec.txs[sp.tx.hash].results)
        self.assertGreater(refused["ErrFrameLoadUnderpriced"], 0)

    def test_with_no_load_price_nothing_is_raised(self):
        _, load, _ = floored(0)
        self.assertTrue(all(sp.tip == sp.drawn for sp in load.spends))

def aggregating(profile, rate=0.3, resend=True, nodes=8, run=300, before=None, claims=False, accounts=None,
                frame_pools=None, chain=None):
    """EIP-8288 wallets, each transaction with one leanSTARK dependency, on a small network; `before` sees the
    simulation before it runs."""
    senders = [f"d{i}" for i in range(200)]
    sim = Simulation(Scenario(seed=5, nodes=nodes, network=NetworkConfig(degree=3), frame_pool=profile,
                              genesis=Head(timestamp=0, gas_limit=6_300_000, gas_used=3_150_000, base_fee=10**9),
                              accounts={s: 10**20 for s in senders} | (accounts or {}), frame_pools=frame_pools,
                              chain=chain or ChainConfig()))
    load = WalletLoad("d", rate=rate, senders=senders, expiring=0.0, scheme="stark", resend=resend, stop=run - 60,
                      claims=claims)
    sim.add_load(load)
    if before is not None:
        before(sim)
    return sim, load, sim.run(run)


class TestAggregation(unittest.TestCase):
    def test_uncapped_aggregates_carry_every_transaction_to_every_node(self):
        sim, load, rec = aggregating(EIP_8288.with_(cap_aggregates=False))
        self.assertGreater(len(load.txs), 50)
        for tx in load.txs:
            r = rec.txs[tx.hash]
            self.assertIsNotNone(r.included_at, tx.label)
            self.assertNotIn("ErrFrameDepsUnproven", r.results)  # never gossiped alone
            self.assertIn("aggregate", r.via.values())
        self.assertEqual(rec.wrappers[("aggregate", "proofs")], 0)
        self.assertEqual(rec.wrappers[("forwarded", "messages")], 0)

    def test_a_capped_aggregate_holds_one_stark(self):
        sim, load, rec = aggregating(EIP_8288)
        w = rec.wrappers
        self.assertEqual(w[("aggregate", "dep_bytes")], 96 * w[("aggregate", "messages")])
        self.assertEqual(w[("aggregate", "starks")], w[("aggregate", "messages")])
        spread = [len(rec.txs[tx.hash].first_seen) for tx in load.txs]
        _, uncapped, urec = aggregating(EIP_8288.with_(cap_aggregates=False))
        self.assertLess(sum(spread), sum(len(urec.txs[tx.hash].first_seen) for tx in uncapped.txs))

    def test_forwarding_relays_each_user_wrapper_once_a_node(self):
        sim, load, rec = aggregating(EIP_8288.with_(forward_wrappers=True), resend=False)
        links = sum(len(n.peers) for n in sim.net.nodes.values())
        self.assertGreater(rec.wrappers[("forwarded", "messages")], 0)
        self.assertLessEqual(rec.wrappers[("forwarded", "messages")], len(load.txs) * links)
        self.assertEqual(rec.wrappers[("forwarded", "proofs")], rec.wrappers[("forwarded", "messages")])
        for tx in load.txs:
            self.assertEqual(len(rec.txs[tx.hash].first_seen), len(sim.net.nodes), tx.label)

    def test_a_wallet_that_sends_once_watches_one_node(self):
        sim, load, rec = aggregating(EIP_8288, resend=False)
        self.assertEqual(sum(len(a) for a in load.answers.values()), len(load.txs))

    def test_a_budget_bounds_every_aggregate_and_a_node_is_never_busy(self):
        costs = dict(cap_aggregates=False, prove_base=300, prove_recursive=250, prove_sig=10, prove_stark=250)
        times = []

        def record(sim):
            for node in sim.net.nodes.values():
                agg = node.aggregator
                inner = agg.aggregate
                agg.aggregate = lambda inner=inner, agg=agg: (w := inner(), times.append(agg.proving_time))[0]

        sim, load, rec = aggregating(EIP_8288.with_(proving_budget=1000, **costs), rate=1.0, before=record)
        self.assertGreater(len(times), 100)
        self.assertTrue(all(t <= 1000 for t in times))
        self.assertGreater(max(times), 1000 - 250)  # some aggregate had more than it could prove
        self.assertTrue(all(n.busy == 0 for n in sim.net.nodes.values()))
        self.assertTrue(all(rec.txs[tx.hash].included_at is not None for tx in load.txs[:50]))

    def test_without_a_budget_a_slow_node_skips_the_ticks_it_spends_proving(self):
        costs = dict(cap_aggregates=False, prove_base=300, prove_recursive=250, prove_sig=10, prove_stark=250)
        sim, load, rec = aggregating(EIP_8288.with_(**costs), rate=1.0)
        self.assertGreater(sum(n.busy for n in sim.net.nodes.values()), 0)
        free, _, frec = aggregating(EIP_8288.with_(cap_aggregates=False), rate=1.0)
        self.assertEqual(sum(n.busy for n in free.net.nodes.values()), 0)

    def test_a_node_with_no_budget_for_one_transaction_sends_nothing(self):
        sim, load, rec = aggregating(EIP_8288.with_(cap_aggregates=False, proving_budget=0, prove_base=1))
        self.assertEqual(rec.wrappers[("aggregate", "messages")], 0)
        for tx in load.txs:
            self.assertNotIn("aggregate", rec.txs[tx.hash].via.values())


def work(sim, origin=None, event=None, load=None) -> int:
    """The nodes' aggregator events (decision record 0037), summed over what matches."""
    return sum(n for node in sim.net.nodes.values() for (o, e, l), n in node.work.items()
               if (origin is None or o == origin) and (event is None or e == event) and (load is None or l == load))


class TestClaims(unittest.TestCase):
    """Claim-gated admission (`docs/spec/10-claim-gated-admission.md`, decision record 0037)."""

    GATED = CLAIM_GATED.with_(cap_aggregates=False)

    def test_wallets_with_claims_land_and_each_node_verifies_a_proof_of_each_once(self):
        sim, load, rec = aggregating(self.GATED, claims=True)
        self.assertGreater(len(load.txs), 50)
        self.assertTrue(all(rec.txs[tx.hash].included_at is not None for tx in load.txs))
        self.assertTrue(all(len(v) == 1 for v in load.versions.values()))
        self.assertEqual(load.claims_bought, len(load.txs))
        # a wallet's wrapper is verified where it is sent, unless the node holds the transaction (FP-2 in CG-3);
        # every other node learns of it in an aggregate
        answers = Counter(a for v in load.answers.values() for a in v)
        self.assertEqual(work(sim, origin="d", event="proof"), answers["ok"])
        self.assertEqual(sum(answers.values()), answers["ok"] + answers["ErrAlreadyKnown"])
        self.assertEqual(work(sim, origin="peer", event="proof"), 0)
        self.assertGreater(work(sim, event="fold") + work(sim, event="cover"), 0)

    def test_without_a_claim_a_wallet_is_refused_before_its_proof(self):
        sim, load, rec = aggregating(self.GATED, run=120)
        self.assertTrue(all(set(a) == {"ErrClaimMissing"} for a in load.answers.values()))
        self.assertEqual(work(sim, event="proof"), 0)

    def framed(self, profile, kind):
        framer = FramingLoad("f", kind=kind, target="d", delay=0.05)
        sim, load, rec = aggregating(profile, claims=True, before=lambda sim: sim.add_load(framer))
        return sim, load, rec, framer

    def test_a_copier_is_refused_on_its_claim_and_costs_no_proof(self):
        sim, load, rec, framer = self.framed(self.GATED, "copy")
        self.assertGreater(framer.sent, 0)
        self.assertEqual(framer.answers, Counter({"ErrClaimWrongSlot": framer.sent}))
        self.assertEqual(work(sim, origin="f", event="proof"), 0)
        self.assertTrue(all(rec.txs[tx.hash].included_at is not None for tx in load.txs))

    def test_a_rewrapper_frames_honest_senders_and_costs_proofs_with_no_claim(self):
        sim, load, rec, framer = self.framed(self.GATED, "rewrap")
        self.assertGreater(framer.answers["ErrWrapperProof"], 0)
        self.assertGreater(work(sim, origin="f", event="proof"), 0)
        refused = Counter(a for answers in load.answers.values() for a in answers)
        self.assertGreater(refused["ErrSlotRefused"], 0)

    def test_signed_proofs_refuse_a_rewrapper_before_anything_is_checked(self):
        sim, load, rec, framer = self.framed(self.GATED.with_(signed_proofs=True), "rewrap")
        self.assertEqual(framer.answers, Counter({"ErrProofUnsigned": framer.sent}))
        self.assertEqual(work(sim, origin="f"), 0)
        refused = Counter(a for answers in load.answers.values() for a in answers)
        self.assertEqual(refused["ErrSlotRefused"] + refused["ErrClaimUsed"], 0)

    def test_a_flood_costs_each_node_one_proof_a_claim_and_none_without(self):
        payers = {f"pm-{n}": 10**20 for n in range(40)}
        for claims in (0, 24):
            flood = FloodLoad("junk", kind="drained", k=8, payer="pm", surplus=0, start=60, stop=240,
                              scheme="stark", claims=claims)
            sim, load, rec = aggregating(self.GATED, claims=True, accounts=payers,
                                         before=lambda sim: sim.add_load(flood))
            self.assertEqual(flood.claimed, claims)
            self.assertGreater(flood.sent, claims)
            self.assertEqual(work(sim, event="proof", load="junk"), claims * len(sim.net.nodes))
            self.assertLessEqual(work(sim, event="fold", load="junk") + work(sim, event="cover", load="junk"),
                                 claims * len(sim.net.nodes))

    VERIFIERS = ("n00", "n01")

    def relayed(self, before=None, accounts=None):
        """Two verifiers of eight nodes, the rest relays (CG-7), every node forwarding mode 0 wrappers."""
        profile = self.GATED.with_(forward_wrappers=True)
        relay = profile.with_(verifies=False)
        return aggregating(profile, claims=True, accounts=accounts, before=before,
                           frame_pools=lambda sim: {n: relay for n in sim.net.nodes if n not in self.VERIFIERS},
                           chain=ChainConfig(proposer=self.VERIFIERS))

    def test_relays_verify_nothing_and_honest_transactions_land(self):
        sim, load, rec = self.relayed()
        self.assertGreater(len(load.txs), 50)
        self.assertTrue(all(rec.txs[tx.hash].included_at is not None for tx in load.txs))
        for name, node in sim.net.nodes.items():
            events = Counter(e for (_, e, _), n in node.work.items() for _ in range(n))
            if name in self.VERIFIERS:
                self.assertGreater(events["proof"], 0)
                self.assertLessEqual(events["proof"], len(load.txs))  # one wrapper under each claim
            else:
                self.assertEqual(events["proof"] + events["stark"] + events["fold"] + events["cover"], 0)
                self.assertGreater(events["check"], 0)
        self.assertEqual(rec.refused_wrappers["ErrWrapperProof"], 0)

    def test_junk_handed_to_one_relay_reaches_every_verifier_once_a_claim(self):
        payers = {f"pm-{n}": 10**20 for n in range(40)}
        flood = FloodLoad("junk", kind="drained", k=8, payer="pm", surplus=0, start=60, stop=240, scheme="stark",
                          claims=10**9, proofs=False, rotate=True, targets=["n05"])  # rotating: R3 never fires
        sim, load, rec = self.relayed(accounts=payers, before=lambda sim: sim.add_load(flood))
        self.assertGreater(flood.claimed, 0)
        self.assertEqual(flood.sent, flood.claimed)  # one node, so one message a claim
        self.assertEqual(work(sim, event="proof", load="junk"), flood.claimed * len(self.VERIFIERS))
        relays = [n for n in sim.net.nodes if n not in self.VERIFIERS]
        reached = sum(sim.net.nodes[n].inbound[("forwarded", "junk")] > 0 for n in relays)
        self.assertEqual(reached, len(relays) - 1)  # every relay but the one handed it hears of it from a peer
        self.assertTrue(all(rec.txs[tx.hash].included_at is not None for tx in load.txs))


def sealing(cfg, rate=1.0, flood=None, reseal=False, nodes=6, run=360, revealed=True, **paying):
    """Sealed payments and trades on a small network under `cfg`, with a flood from second 60 if asked;
    `paying` goes to the payments' load."""
    pays, trades = [f"s{i}" for i in range(300)], [f"t{i}" for i in range(50)]
    accounts = {a: 10**20 for a in pays + trades}
    adversary = None
    if flood:
        adversary = SealedFlood("x", kind=flood, k=cfg.st_slots + 8, tob=1 if flood == "cheap" else 10**15 + 1,
                                surplus=4, start=60, revealed=revealed)
        accounts.update({s: 10**18 for s in adversary.senders})
    sim = Simulation(Scenario(seed=7, nodes=nodes, network=NetworkConfig(degree=3), sealed_pool=cfg,
                              genesis=Head(timestamp=0, gas_limit=60_000_000, gas_used=30_000_000, base_fee=10**9),
                              accounts=accounts))
    pay = SealedLoad("pay", rate=rate, senders=pays, reseal=reseal, stop=run - 60, **paying)
    trade = SealedLoad("trade", rate=0.1, senders=trades, tob=uniform(10**12, 10**15), preceding=uniform(1, 8),
                       gas=300_000, stop=run - 60)
    for load in (pay, trade, adversary):
        if load is not None:
            sim.add_load(load)
    return sim, pay, trade, adversary, sim.run(run)


def committed(rec, load, after=0.0):
    """Of `load`'s sealed transactions first sent after `after`: how many, and how many were committed."""
    sent = [v for v in load.sent if rec.txs[v[0].hash].submitted_at > after]
    return len(sent), sum(1 for v in sent if any(rec.txs[t.hash].included_at is not None for t in v))


class TestUpdater(unittest.TestCase):
    """The plan's item 31, decision record 0039: an open role proves the pool's root from its chained outputs."""

    @staticmethod
    def updating(holders, every=1, backoff=0.0):
        made = {}

        def before(sim):
            made["u"] = Updater("upd", senders=[f"up{i}" for i in range(len(holders))], outputs=sim.loads[0],
                                holders=holders, prove=lambda k: 0.1 + 0.001 * k, every=every, backoff=backoff)
            sim.add_load(made["u"])

        accounts = {f"up{i}": 10**20 for i in range(len(holders))}
        sim, load, rec = aggregating(EIP_8288.with_(cap_aggregates=False), rate=0.05, run=600, before=before,
                                     accounts=accounts)
        return made["u"], load, rec

    def test_one_holder_covers_every_output_in_order_and_each_is_spendable_after_its_update(self):
        u, load, rec = self.updating(["n00"])
        self.assertEqual(len(u.carried), 2 * sum(1 for tx in load.txs if rec.txs[tx.hash].included_at is not None))
        self.assertGreater(len(u.carried), 20)
        self.assertEqual(u.coverage, len(u.carried))
        self.assertTrue(all(x.effect for x in u.updates))
        ends = 0
        for x in u.updates:
            self.assertEqual(x.start, ends)  # contiguous: each starts where the last in effect ended
            ends = x.end
            for i in range(x.start, x.end):
                self.assertEqual(u.spendable[i], x.slot + 1)  # RR-2, RR-3: referenceable from the next slot
                self.assertGreater(x.slot, u.carried[i])  # an update follows the block that carried its outputs
        self.assertTrue(all(u.spendable[i] - s >= 2 for i, s in enumerate(u.carried)))

    def test_racing_holders_land_one_update_of_a_start_and_the_rest_revert(self):
        u, load, rec = self.updating(["n00", "n01", "n02"])
        self.assertEqual(u.coverage, len(u.carried))
        effective = [x for x in u.updates if x.effect]
        reverted = [x for x in u.updates if x.effect is False]
        self.assertGreater(len(reverted), 0)
        self.assertEqual(len({x.start for x in effective}), len(effective))
        self.assertTrue(all(x.slot is not None for x in u.updates))
        self.assertGreater(max(Counter(x.slot for x in u.updates).values()), 1)

    def test_a_holder_waits_for_k_outputs(self):
        u, load, rec = self.updating(["n00"], every=6)
        self.assertGreater(len(u.updates), 2)
        self.assertTrue(all(x.end - x.start >= 6 for x in u.updates))

    def test_backing_off_stands_some_holders_down(self):
        race, _, _ = self.updating(["n00", "n01", "n02"])
        calm, _, _ = self.updating(["n00", "n01", "n02"], backoff=4.0)
        self.assertGreater(calm.deferred, 0)
        self.assertLess(len(calm.updates), len(race.updates))
        self.assertEqual(calm.coverage, len(calm.carried))



def ticketed(entry, hold=30.0, rate=0.2, run=240, nodes=9):
    """Tickets under three keys, bought until a minute before the end, on a network whose last node is a spy."""
    honest = [f"n{i:02d}" for i in range(nodes - 1)]
    buyers = [f"b{i}" for i in range(20)]
    sim = Simulation(Scenario(seed=5, nodes=nodes,
                              network=NetworkConfig(degree=3, record_heard=True, spies=(f"n{nodes - 1:02d}",)),
                              chain=ChainConfig(proposer=tuple(honest)), frame_pool=HEGOTA_TESTNET,
                              genesis=Head(timestamp=0, gas_limit=30_000_000, gas_used=15_000_000, base_fee=10**9),
                              accounts={"pool": 10**24, **{b: 10**21 for b in buyers}}, code={"pool": "privacy-pool"}))
    spender = SharedSenderLoad("s", rate=0.0, senders=["pool"], rule="direct", tip=fixed(10**9), targets=honest,
                               key_bytes=32)
    load = Tickets("t", rate=rate, senders=buyers, tip=fixed(10**9), keys=3, hold=lambda rng: hold, spender=spender,
                   entry=entry, targets=honest, stop=run - 60)
    sim.add_load(load)
    return sim, load, sim.run(run)


class TestTickets(unittest.TestCase):
    """The plan's item 30, decision record 0040: tickets bought in public and spent from a shared sender."""

    def test_a_wallet_spends_its_holding_time_after_its_node_imports_the_purchase(self):
        _, load, rec = ticketed("same")
        self.assertGreater(len(load.purchases), 20)
        self.assertEqual({p.key for p in load.purchases}, {0, 1, 2})
        for p in load.purchases:
            bought = rec.txs[p.tx.hash]
            self.assertEqual(bought.origin, p.home)
            self.assertIsNotNone(bought.included_at)
            self.assertGreaterEqual(p.seen, bought.included_at)
            self.assertLess(p.seen, bought.included_at + 1.0)  # its node imports the block within a second
            self.assertAlmostEqual(p.spend.requested_at, p.seen + 30.0)
            spent = rec.txs[p.spend.tx.hash]
            self.assertEqual(spent.origin, p.home)  # entry `same`
            self.assertGreater(spent.included_at, bought.included_at + 30.0)

    def test_with_a_random_entry_the_spend_goes_to_any_of_the_targets(self):
        _, load, rec = ticketed("random")
        pairs = [(p.home, rec.txs[p.spend.tx.hash].origin) for p in load.purchases]
        self.assertTrue(all(spent in [f"n{i:02d}" for i in range(8)] for _, spent in pairs))
        self.assertTrue(any(bought != spent for bought, spent in pairs))

    def test_the_spender_has_no_arrivals_of_its_own(self):
        spender = SharedSenderLoad("s", rate=0.1, senders=["pool"], rule="direct")
        with self.assertRaises(ValueError):
            Tickets("t", rate=0.1, senders=["b"], keys=1, hold=lambda rng: 1.0, spender=spender)

class TestSealed(unittest.TestCase):
    def test_every_payment_is_committed_and_decrypted_in_the_next_block(self):
        sim, pay, trade, _, rec = sealing(EIP_8184)
        sent, landed = committed(rec, pay)
        self.assertGreater(sent, 200)
        self.assertEqual(landed, sent)
        self.assertEqual(committed(rec, trade)[1], committed(rec, trade)[0])
        for prev, block in zip(rec.blocks, rec.blocks[1:]):
            self.assertLessEqual(len(block["commitments"]), 32)
            self.assertEqual(block["decrypted"], len(prev["commitments"]))  # every key is released
        spread = [len(rec.txs[v[0].hash].first_seen) for v in pay.sent]
        self.assertGreater(sum(spread) / len(spread), 5.5)  # gossiped to nearly every node

    def test_a_cheap_flood_shuts_payments_out_under_any_and_not_under_next_block(self):
        small = EIP_8184.with_(st_slots=64)
        sim, pay, _, flood, rec = sealing(small, flood="cheap")
        sent, landed = committed(rec, pay, after=72)
        self.assertGreater(sent, 100)
        self.assertLess(landed, sent // 10)
        self.assertGreater(flood.admitted, 64)
        sim, pay, _, flood, rec = sealing(small.with_(policy="next-block"), flood="cheap")
        sent, landed = committed(rec, pay, after=72)
        self.assertEqual(landed, sent)
        self.assertLess(flood.admitted, 6 * 64)

    def test_unplaced_keeps_payments_against_an_escalating_flood(self):
        small = EIP_8184.with_(st_slots=64, policy="next-block")
        _, pay, _, _, rec = sealing(small, flood="escalating")
        sent, landed = committed(rec, pay, after=72)
        self.assertLess(landed, sent // 10)
        _, pay, _, flood, rec = sealing(small.with_(evict_first="unplaced"), flood="escalating")
        sent, landed = committed(rec, pay, after=72)
        self.assertEqual(landed, sent)
        theirs = [sum(1 for c in b["commitments"] if c.tx.label.startswith("x")) for b in rec.blocks if b["at"] > 72]
        self.assertTrue(all(n == 1 for n in theirs), theirs)  # it buys the first commitment of every block

    def test_a_withheld_key_is_charged_runs_nothing_and_the_sender_seals_again(self):
        _, pay, _, _, rec = sealing(EIP_8184, publishers=4, withholding=2)
        self.assertGreater(sum(pay.withheld.values()), 50)
        for prev, block in zip(rec.blocks, rec.blocks[1:]):
            self.assertEqual(block["decrypted"], sum(1 for c in prev["commitments"] if c.tx.revealed))
        for versions in pay.sent:
            landed = [v for v in dict.fromkeys(versions) if rec.txs[v.hash].included_at is not None]
            if not landed or not landed[-1].revealed:
                continue  # still in flight at the end
            withheld = landed[:-1]
            self.assertEqual(len(withheld), pay.withheld[versions[0].hash])
            self.assertTrue(all(not v.revealed and v.key_publisher in pay.withholders for v in withheld))
            self.assertEqual(len({v.key_publisher for v in withheld}), len(withheld))  # it names each once
            self.assertEqual([v.nonce for v in landed], list(range(landed[0].nonce, landed[0].nonce + len(landed))))
        self.assertFalse(pay.public)

    def test_a_public_response_sends_the_payment_as_a_regular_transaction(self):
        _, pay, _, _, rec = sealing(EIP_8184, publishers=4, withholding=2, response="public")
        self.assertGreater(len(pay.public), 50)
        for versions in pay.sent:
            tx = pay.public.get(versions[0].hash)
            if tx is None:
                continue
            self.assertEqual(pay.withheld[versions[0].hash], 1)
            self.assertEqual((tx.nonce, tx.gas), (versions[-1].nonce + 1, versions[-1].gas_limit))
            self.assertFalse(versions[-1].revealed)
            self.assertIsNotNone(rec.txs[tx.hash].included_at)

    def test_a_flood_that_withholds_runs_nothing(self):
        _, _, _, flood, rec = sealing(EIP_8184.with_(st_slots=64), flood="escalating", revealed=False)
        theirs = [c.tx for b in rec.blocks for c in b["commitments"] if c.tx.label.startswith("x")]
        self.assertTrue(theirs)
        self.assertTrue(all(not st.revealed for st in theirs))
        for prev, block in zip(rec.blocks, rec.blocks[1:]):
            self.assertEqual(block["decrypted"], sum(1 for c in prev["commitments"] if not c.tx.label.startswith("x")))

    def test_a_resealed_payment_has_versions_and_one_is_committed(self):
        _, pay, _, _, rec = sealing(EIP_8184.with_(policy="every-head", max_st_commits=4), rate=0.5, reseal=True)
        self.assertTrue(any(len(v) > 1 for v in pay.sent))
        for versions in pay.sent:
            self.assertLessEqual(sum(1 for t in versions if rec.txs[t.hash].included_at is not None), 1)


def keyed(run=360, rate=1.0, filtering=(), **committee):
    """Sealed payments that name a committee of 8, threshold 6, on `sealing`'s network; `committee` goes to
    `KeyCommittee` and to the payments' load, by name."""
    paying = {k: committee.pop(k) for k in ("response", "committee_share", "rotation") if k in committee}
    c = KeyCommittee("mpc", members=8, threshold=6, **committee)
    pays, trades = [f"s{i}" for i in range(300)], [f"t{i}" for i in range(50)]
    leave_out = {"censored": lambda tx: getattr(tx, "key_publisher", None) == "mpc",
                 "filtering": frozenset(filtering)} if filtering else {}
    sim = Simulation(Scenario(seed=7, nodes=6, network=NetworkConfig(degree=3), sealed_pool=EIP_8184,
                              chain=ChainConfig(slot_time=12, **leave_out),
                              genesis=Head(timestamp=0, gas_limit=60_000_000, gas_used=30_000_000, base_fee=10**9),
                              accounts={a: 10**20 for a in pays + trades}))
    pay = SealedLoad("pay", rate=rate, senders=pays, stop=run - 60, committee=c, **paying)
    sim.add_load(pay)
    sim.add_load(SealedLoad("trade", rate=0.1, senders=trades, tob=uniform(10**12, 10**15),
                            preceding=uniform(1, 8), gas=300_000, stop=run - 60))
    return sim, c, pay, sim.run(run)


def ran(c, pay, rec):
    """Of the payments whose last attempt was committed in time to be checked: how many, how many ran."""
    done = total = 0
    for versions in pay.sent:
        landed = [v for v in dict.fromkeys(versions) if rec.txs[v.hash].block is not None]
        if not landed or landed[-1].hash not in c.outcome:
            continue
        total += 1
        done += c.outcome[landed[-1].hash] in c.RELEASED or versions[0].hash in pay.public
    return total, done


class TestKeyCommittee(unittest.TestCase):
    def test_a_full_committee_releases_every_key(self):
        sim, c, pay, rec = keyed()
        self.assertGreater(len(c.outcome), 200)
        self.assertEqual(set(c.outcome.values()), {"released"})
        for prev, block in zip(rec.blocks, rec.blocks[1:]):
            self.assertEqual(block["decrypted"], len(prev["commitments"]))
        self.assertFalse(pay.withheld)
        self.assertTrue(all(s["serving"] == 8 and s["shares"] == 8 * s["commitments"]
                            and s["batched"] == (8 if s["commitments"] else 0) for s in c.slots.values()))

    def test_more_than_n_minus_t_withholding_stops_every_key_and_senders_seal_again_after_the_deadline(self):
        sim, c, pay, rec = keyed(withholding=3)
        self.assertEqual(set(c.outcome.values()), {"quorum"})
        for prev, block in zip(rec.blocks, rec.blocks[1:]):
            mine = sum(1 for x in prev["commitments"] if x.tx.key_publisher == "mpc")
            self.assertEqual(block["decrypted"], len(prev["commitments"]) - mine)
        at = {b["number"]: b["at"] for b in rec.blocks}
        for versions in pay.sent:
            for v, nxt in zip(versions, versions[1:]):
                self.assertEqual(nxt.nonce, v.nonce + 1)
                self.assertEqual(nxt.key_publisher, "mpc")
                self.assertGreaterEqual(rec.txs[nxt.hash].submitted_at, at[rec.txs[v.hash].block] + 9.0)

    def test_online_senders_release_their_own_keys(self):
        sim, c, pay, rec = keyed(withholding=3, online=1.0)
        self.assertEqual(set(c.outcome.values()), {"self"})
        total, done = ran(c, pay, rec)
        self.assertEqual(done, total)
        self.assertFalse(pay.withheld)

    def test_late_members_fail_whole_slots_and_a_fresh_draw_fails_keys_alone(self):
        sim, c, pay, rec = keyed(late=0.25, rate=2.0)
        mixed = [s for s in c.slots.values() if 0 < s["withheld"] < s["commitments"]]
        self.assertFalse(mixed)  # one draw a slot: all or none
        self.assertTrue(any(s["withheld"] for s in c.slots.values()))
        sim, c, pay, rec = keyed(late=0.25, rate=2.0, per="commitment")
        self.assertTrue(any(0 < s["withheld"] < s["commitments"] for s in c.slots.values()))

    def test_a_rotated_key_is_gone_after_its_committee_stops_serving(self):
        sim, c, pay, rec = keyed(epoch=4, handover="rotate", rate=3.0)
        gone = [h for h, o in c.outcome.items() if o == "gone"]
        self.assertTrue(gone)
        slot = {x.tx.hash: b["number"] for b in rec.blocks for x in b["commitments"]}
        for h in gone:
            self.assertLess(c.sealed_to[h], c.key_epoch(slot[h]))
        for h, o in c.outcome.items():
            if o == "released":
                self.assertTrue(c.sealed_to[h] == c.key_epoch(slot[h]))
        sim, c, pay, rec = keyed(epoch=4, handover="reshare", rate=3.0)
        self.assertEqual(set(c.outcome.values()), {"released"})

    def test_a_sender_that_reseals_replaces_its_old_key_with_the_new(self):
        sim, c, pay, rec = keyed(epoch=4, handover="rotate", rate=3.0, rotation="reseal")
        bumped = [(a, b) for v in pay.sent for a, b in zip(v, v[1:]) if b.nonce == a.nonce]
        self.assertTrue(bumped)
        for a, b in bumped:
            self.assertEqual((b.max_fee, b.tip), (-(-a.max_fee * 110 // 100), -(-a.tip * 110 // 100)))
            self.assertEqual(c.sealed_to[b.hash], c.sealed_to[a.hash] + 1)

    def test_a_builder_that_filters_commits_none_of_the_committee_s(self):
        sim, c, pay, rec = keyed(committee_share=0.5, filtering=("n00", "n01", "n02"))
        theirs = [b for b in rec.blocks if b["proposer"] in ("n00", "n01", "n02")]
        self.assertTrue(theirs)
        for b in theirs:
            self.assertFalse([x for x in b["commitments"] if x.tx.key_publisher == "mpc"])
        self.assertGreater(sum(1 for b in theirs for x in b["commitments"] if x.tx.key_publisher == "kp"), 20)
        self.assertTrue([x for b in rec.blocks for x in b["commitments"] if x.tx.key_publisher == "mpc"])


def committee(sender, tip=2_000_000_000, burst=False, patience=None, rule="every", run=900, nodes=5):
    """Intents of 873,716 gas at 2 a slot and a committee at n00 that settles them, on a 60M-gas chain."""
    profile = replace(EIP_8141, per_sender="disjoint-keys" if sender == "keys" else "one")
    users, background = [f"u{i}" for i in range(500)], [f"b{i}" for i in range(500)]
    sim = Simulation(Scenario(seed=3, nodes=nodes, network=NetworkConfig(degree=3), frame_pool=profile,
                              chain=ChainConfig(slot_time=12, proposer="rotate", block_delay=(0.1, 1.0)),
                              genesis=Head(timestamp=0, gas_limit=60_000_000, gas_used=30_000_000, base_fee=10**9),
                              accounts={**{a: 10**22 for a in users + background}, "mpc": 10**24},
                              code={} if sender == "account" else {"mpc": "committee"}))
    sim.add_load(TransferLoad("bg", rate=1.0, senders=background, gas=1_000_000))
    if burst:
        sim.add_load(TransferLoad("burst", rate=10.0, senders=background, gas=1_000_000, start=120, stop=300))
    sim.add_load(TransferLoad("intent", rate=2 / 12, senders=users, gas=873_716, tip=fixed(3_000_000_000),
                              fee_multiplier=100, stop=run - 120))
    c = Committee("settle", address="mpc", node="n00", intents="intent-", sender=sender, settle_tip=tip,
                  patience=patience, rule=rule)
    sim.add_load(c)
    return sim, c, sim.run(run)


class TestCommittee(unittest.TestCase):
    def settled_once(self, c):
        good = sorted((s for s in c.settlements if s.included_at is not None and not s.reverted),
                      key=lambda s: s.start)
        self.assertEqual([s.start for s in good], [0] + [s.end for s in good[:-1]])  # a chain from the start
        self.assertEqual(c.applied, good[-1].end if good else 0)
        self.assertTrue(all(0 < s.size <= c.batch for s in c.settlements))
        return good

    def test_an_account_settles_each_block_s_intents_in_the_next(self):
        sim, c, rec = committee("account")
        good = self.settled_once(c)
        self.assertEqual(c.applied, len(c.queue))
        blocks = {b["at"]: b["number"] for b in rec.blocks}
        for s in good:
            for h in c.queue[s.start:s.end]:
                self.assertEqual(s.block, blocks[rec.txs[h].included_at] + 1)
        self.assertTrue(all(s.versions[0].gas == 1_125_950 for s in c.settlements))

    def test_a_frame_committee_has_one_settlement_in_flight_and_its_gas(self):
        sim, c, rec = committee("frame")
        self.settled_once(c)
        self.assertEqual(c.applied, len(c.queue))
        sent = sorted((s.cut_at, s.included_at) for s in c.settlements)
        self.assertTrue(all(a[1] <= b[0] for a, b in zip(sent, sent[1:])))  # cut only once the last landed
        self.assertEqual([s.versions[0].nonce_seq for s in c.settlements], list(range(len(c.settlements))))
        self.assertTrue(all(s.versions[0].max_gas == 1_125_950 for s in c.settlements))

    def test_full_batches_wait_for_fifty_or_the_oldest(self):
        sim, c, rec = committee("account", rule="full")
        self.settled_once(c)
        for s in c.settlements:
            if s.size < c.batch:
                cut = max(b["number"] for b in rec.blocks if b["at"] <= s.cut_at)
                self.assertGreaterEqual(cut - c.queued_in[s.start], c.wait)

    def test_under_a_burst_keys_reorder_and_revert_where_one_key_waits(self):
        _, keys, _ = committee("keys", tip=100_000_000, burst=True)
        self.assertTrue(any(s.reverted for s in keys.settlements))
        self.settled_once(keys)
        _, frame, _ = committee("frame", tip=100_000_000, burst=True)
        self.assertFalse(any(s.reverted for s in frame.settlements))
        self.settled_once(frame)

    def test_a_committee_that_re_prices_settles_through_a_burst(self):
        _, c, _ = committee("account", tip=100_000_000, burst=True, patience=1)
        self.settled_once(c)
        self.assertEqual(c.applied, len(c.queue))
        self.assertTrue(any(len(s.versions) > 1 for s in c.settlements))


def clearing(channel, rounds, rtt=0.08, slot=4, margin=1.0, run=240):
    """Orders at 0.5 a second and a committee of n05 to n07 that clears them every block; n00 to n04 propose."""
    names = [f"n{i:02d}" for i in range(8)]
    users, background = [f"u{i}" for i in range(500)], [f"b{i}" for i in range(500)]
    leave_out = {"censored": lambda tx: tx.label.startswith("order"), "filtering": frozenset(names)}
    sim = Simulation(Scenario(seed=3, nodes=8, network=NetworkConfig(degree=3), frame_pool=EIP_8141,
                              chain=ChainConfig(slot_time=slot, proposer=tuple(names[:5]),
                                                **(leave_out if channel == "pool" else {})),
                              genesis=Head(timestamp=0, gas_limit=60_000_000, gas_used=30_000_000, base_fee=10**9),
                              accounts={**{a: 10**22 for a in users + background}, "mm": 10**24}))
    sim.add_load(TransferLoad("bg", rate=1.0, senders=background, gas=1_000_000))
    sim.add_load(TransferLoad("order", rate=0.5, senders=users, gas=100_000, tip=fixed(3_000_000_000),
                              fee_multiplier=100, stop=run - 40))
    c = Clearing("mm", address="mm", members=("n05", "n06", "n07"), orders="order", channel=channel, rounds=rounds,
                 rtt=rtt, margin=margin)
    sim.add_load(c)
    return sim, c, sim.run(run)


class TestClearing(unittest.TestCase):
    def test_from_the_chain_a_batch_is_a_block_s_orders_after_every_member_imports_it(self):
        sim, c, rec = clearing("chain", 2)
        blocks = {b["number"]: b for b in rec.blocks}
        self.assertEqual([b.target for b in c.batches], list(range(2, 2 + len(c.batches))))  # one every block
        taken = [h for b in c.batches for h in b.orders]
        self.assertEqual(len(taken), len(set(taken)))
        for b in c.batches:
            self.assertTrue(all(rec.txs[h].block == b.target - 1 for h in b.orders))
            self.assertGreater(b.cut_at, blocks[b.target - 1]["at"])  # every member imported it first
            self.assertAlmostEqual(b.ended_at - b.started_at, 2 * 0.08)
        self.assertEqual([b.tx.nonce for b in c.batches if b.tx], list(range(sum(1 for b in c.batches if b.tx))))
        ordered = [h for h, t in rec.txs.items() if t.tx.label.startswith("order") and t.block is not None
                   and t.block + 1 <= c.batches[-1].target]
        self.assertEqual(sorted(taken), sorted(ordered))

    def test_a_short_computation_settles_in_the_next_block_and_a_long_one_late(self):
        _, quick, rec = clearing("chain", 2)
        self.assertTrue(all(rec.txs[b.tx.hash].block == b.target for b in quick.batches[:-2]))
        _, slow, rec = clearing("chain", 49)  # 3.92 s of rounds after the import, in a 4 s slot
        self.assertTrue(all(rec.txs[b.tx.hash].block > b.target for b in slow.batches[:-2]))
        starts = [b.started_at for b in slow.batches]
        self.assertTrue(all(b.started_at >= a.ended_at for a, b in zip(slow.batches, slow.batches[1:])))
        self.assertEqual(starts, sorted(starts))

    def test_from_the_pool_a_batch_is_what_every_member_held_at_its_cutoff(self):
        sim, c, rec = clearing("pool", 17)
        self.assertTrue(all(t.block is None for t in rec.txs.values() if t.tx.label.startswith("order")))
        for b in c.batches:
            self.assertAlmostEqual(b.cut_at, b.target * 4 - 17 * 0.08 - 1.0)
            for h in b.orders:
                self.assertTrue(all(rec.txs[h].first_seen[m] <= b.cut_at for m in c.members))
        taken = [h for b in c.batches for h in b.orders]
        self.assertEqual(len(taken), len(set(taken)))
        late = [h for h, t in rec.txs.items() if t.tx.label.startswith("order") and h not in taken]
        last = c.batches[-1].cut_at
        self.assertTrue(all(any(rec.txs[h].first_seen.get(m, last + 1) > last for m in c.members) for h in late))
        self.assertTrue(all(rec.txs[b.tx.hash].block == b.target for b in c.batches[:-2]))

    def test_a_cutoff_more_than_a_slot_ahead_still_clears_every_block(self):
        _, c, rec = clearing("pool", 49, margin=1.0)  # 4.92 s ahead of a 4 s slot
        self.assertTrue(all(b.started_at == b.cut_at for b in c.batches))
        self.assertTrue(all(rec.txs[b.tx.hash].block == b.target for b in c.batches[:-2]))


ROOMY = EIP_8141.with_(max_verify_gas=250_000)
PROOF = Signature(scheme="arbitrary", length=256)


def heavy(n, verify=211_828, length=256):
    """A self-paying spend whose structural rule 6 budget is `verify`, its proof in an ARBITRARY entry."""
    sig = Signature(scheme="arbitrary", length=length)
    return backed_tx("self", f"h{n}", None, max_fee=10**12, tip=10**9, label=f"h{n}", verify_gas=verify - 100,
                     signature=sig)


def headroom(roomy, proposer="rotate", nodes=6, liars=(), users=4, **network):
    users = [f"h{i}" for i in range(users)]
    return Simulation(Scenario(seed=2, nodes=nodes, network=NetworkConfig(degree=nodes - 1, liars=liars, **network),
                               chain=ChainConfig(proposer=proposer),
                               genesis=Head(timestamp=0, gas_limit=30_000_000, gas_used=15_000_000, base_fee=10**9),
                               accounts={u: 10**18 for u in users}, code={u: "verifier" for u in users},
                               frame_pools=lambda sim: {n: ROOMY for n in roomy}))


class TestHeadroom(unittest.TestCase):
    """Per-node budgets (EIPs pull request 12301), and the budget hints it leaves to the wire protocol."""

    def send(self, sim, tx, node="n00"):
        sim.recorder.submitted(tx, sim.sched.now, node)
        return sim.net.nodes[node].submit(tx)

    def test_a_spend_above_the_floor_travels_only_among_nodes_with_headroom(self):
        self.assertEqual(budget(heavy(0), EIP_8141), 211_828)
        sim = headroom(("n00", "n01"), proposer=("n02", "n01"))
        tx = heavy(0)
        self.assertEqual(self.send(sim, tx), "ok")
        rec = sim.run(30)
        r = rec.txs[tx.hash]
        self.assertEqual(set(r.first_seen), {"n00", "n01"})
        self.assertGreaterEqual(r.results["ErrFrameVerifyGas"], 4)  # every floor node was handed it and refused it
        self.assertEqual(r.block, 2)  # n02 cannot include it; n01 does, in the next slot
        floor = budget(heavy(1, verify=100_000), EIP_8141)
        self.assertEqual(floor, EIP_8141.max_verify_gas)  # at the floor itself every node admits it

    def test_fresh_wallets_offer_two_networks_the_same_spends(self):
        sent = []
        for roomy in (("n00",), ("n00", "n01", "n02")):
            sim = headroom(roomy, users=60)
            load = WalletLoad("w", rate=0.5, senders=[f"h{i}" for i in range(60)], verify_gas=211_728,
                              expiring=0.0, resend=False, targets=list(roomy), signature=PROOF, fresh=True, stop=60)
            sim.add_load(load)
            rec = sim.run(90)
            self.assertEqual(load.skipped, 0)
            self.assertTrue(all(rec.txs[tx.hash].included_at for tx in load.txs))
            sent.append([(tx.sender, rec.txs[tx.hash].submitted_at) for tx in load.txs])
        self.assertGreater(len(sent[0]), 20)
        self.assertEqual(sent[0], sent[1])  # the same senders at the same times, whatever the network does

    def test_budget_hints_save_fetches_and_not_pushes(self):
        waste = {}
        for hints in (False, True):
            sim = headroom(("n00",), proposer=("n05",), announce_budget=hints)
            tx = heavy(0)
            self.send(sim, tx)
            r = sim.run(10).txs[tx.hash]
            waste[hints] = (r.results["ErrFrameVerifyGas"], r.skipped)
        self.assertEqual(waste[False], (5, 0))  # three pushed, two fetched, all refused
        self.assertEqual(waste[True], (3, 2))  # the two announced ones are not fetched

    def test_a_remembered_lie_blocks_later_announcements_and_not_pushes(self):
        tx = heavy(0, length=6000)  # only announced, over txMaxBroadcastSize
        for remember, fetched in ((0.0, True), (300.0, False)):
            sched = Scheduler()
            net = Network(sched, random.Random(1), Recorder(),
                          NetworkConfig(announce_budget=True, remember_budget=remember, liars=("l",)))
            head = Head(timestamp=0, gas_limit=30_000_000, gas_used=15_000_000, base_fee=10**9)
            state = State({"h0": Account(balance=10**18, code="verifier")})
            for name in ("a", "l", "b"):
                net.add(Node(name, TxPool(head, state, GETH, ROOMY), net))
            for x, y in (("a", "b"), ("a", "l"), ("l", "b")):
                net.connect(x, y)
            a, b = net.nodes["a"], net.nodes["b"]
            b.on_announce([tx.hash], "l", [INFLATED])
            self.assertEqual(b.fetching, {})
            a.pool.add([tx])
            a.pool.frame.log.clear()
            b.on_announce([tx.hash], "a", [budget(tx, ROOMY)])
            self.assertEqual(tx.hash in b.fetching, fetched)
            b.receive([tx], "a")  # a push is not an announcement
            self.assertIsNotNone(b.pool.get(tx.hash))

    def test_a_liar_announces_what_it_hears_once_and_relays_nothing(self):
        tx = heavy(0)
        for hints in (False, True):
            sched = Scheduler()
            net = Network(sched, random.Random(1), Recorder(), NetworkConfig(announce_budget=hints, liars=("l",)))
            head = Head(timestamp=0, gas_limit=30_000_000, gas_used=15_000_000, base_fee=10**9)
            state = State({"h0": Account(balance=10**18, code="verifier")})
            for name in ("a", "l", "b"):
                net.add(Node(name, TxPool(head, state, GETH, ROOMY), net))
            net.connect("a", "l")
            net.connect("l", "b")
            net.nodes["a"].submit(tx)
            sched.run(5)
            liar = net.nodes["l"]
            self.assertIsNotNone(liar.pool.get(tx.hash))
            self.assertIsNone(net.nodes["b"].pool.get(tx.hash))  # nothing gets past it
            self.assertEqual(liar.lied, {tx.hash} if hints else set())  # without hints it can only keep quiet
            self.assertEqual(net.nodes["b"].heavy, {})  # b forgets, and would fetch from an honest announcer

def rooted(length=8192, filtering=(), draw=False, seed=1, run=600.0):
    """Spends against a root source that writes every slot, built by four builders, `filtering` of which leave
    the spends out (`08-recent-roots.md`)."""
    users = [f"u{i}" for i in range(200)]
    sim = Simulation(Scenario(
        seed=seed, nodes=8, network=NetworkConfig(degree=3),
        chain=ChainConfig(proposer=("n00", "n01", "n02", "n03"), draw=draw, filtering=frozenset(filtering),
                          censored=lambda tx: tx.sender.startswith("u")),
        frame_pool=EIP_8272.with_(recent_root_length=length),
        genesis=Head(timestamp=0, gas_limit=30_000_000, gas_used=15_000_000, base_fee=10**9),
        accounts={a: 10**21 for a in users + ["writer"]},
        code={**{u: "privacy-account" for u in users}, EIP_8272.recent_root_address: "recent-root"}))
    writer = RootWriter("root", senders=["writer"], address="pool", start=1.0)
    spends = RootSpendLoad("s", 1 / 12, users, writer=writer, prove=6.0, start=30.0, stop=run - 120)
    sim.add_load(writer)
    sim.add_load(spends)
    return sim, sim.run(run), writer, spends


class TestRecentRoots(unittest.TestCase):
    def test_every_slot_holds_a_root_and_spends_land_against_a_recent_one(self):
        sim, rec, writer, spends = rooted()
        self.assertEqual(writer.slots[:10], list(range(1, 11)))
        self.assertEqual(writer.latest(5), (5, writer.roots[4]))
        self.assertGreater(len(spends.spends), 20)
        for sp in spends.spends:
            self.assertEqual(sp.proofs, 1)
            self.assertIsNotNone(sp.landed_slot)
            self.assertTrue(1 <= sp.landed_slot - sp.landed_root <= 3, sp.label)

    def test_a_short_window_and_builders_that_filter_force_proofs_again_and_no_re_run(self):
        sim, rec, writer, spends = rooted(length=4, filtering=("n00", "n01", "n02"), draw=True)
        self.assertTrue(any(sp.proofs > 1 for sp in spends.spends))
        self.assertGreater(sum(n.pool.frame.dropped["root_expired"] for n in sim.net.nodes.values()), 0)
        self.assertEqual(sum(n.pool.frame.resimulations for n in sim.net.nodes.values()), 0)  # RR-7 re-runs nothing
        for sp in spends.spends:
            if sp.landed_slot is not None:
                self.assertLessEqual(sp.landed_slot - sp.landed_root, 3)  # no block takes a root older than W (RR-8)
                self.assertIn(sp.landed_root, [slot for _, slot in sp.versions])

    def test_drawn_proposers_follow_the_seed_and_not_the_turn(self):
        def proposers(draw, seed=1):
            return [b["proposer"] for b in rooted(draw=draw, seed=seed, run=240.0)[1].blocks]
        self.assertEqual(proposers(True), proposers(True))
        self.assertNotEqual(proposers(True), proposers(True, seed=2))
        self.assertEqual(proposers(False), ["n00", "n01", "n02", "n03"] * 5)
        self.assertNotEqual(proposers(True), proposers(False))



def congested(patience=None, reprice=False, limit=None, spend=None, seed=3, every=False):
    """Transfers at 12 a block for 240 s into blocks that hold 8, and a shared sender if `spend` says how its users
    re-price."""
    senders = [f"u{i}" for i in range(20)]
    pool = ["pool"] if spend is not None else []
    sc = Scenario(seed=seed, nodes=6, network=NetworkConfig(degree=3),
                  genesis=Head(timestamp=0, gas_limit=168_000, gas_used=84_000, base_fee=10**9),
                  accounts={s: 10**20 for s in senders} | {p: 10**24 for p in pool},
                  code={p: "privacy-pool" for p in pool})
    sim = Simulation(sc)
    load = BumpLoad("t", rate=1.0, senders=senders, stop=240, patience=patience, reprice=reprice, limit=limit,
                    every=every)
    sim.add_load(load)
    spends = None
    if spend is not None:
        spends = SharedSenderLoad("s", rate=0.05, senders=pool, rule="relayer", serial=True, patience=spend[0],
                                  reprice=spend[1], stop=600)
        sim.add_load(spends)
    return sim, load, spends


def landed_any(sim, versions):
    return any(sim.recorder.txs[v.hash].included_at is not None for v in versions)


class TestIssuers(unittest.TestCase):
    """Ticket issuers, and the two defences modelled around CG-2 and CG-4 (decision record 0059)."""

    GATED = CLAIM_GATED.with_(cap_aggregates=False)
    PAYERS = {f"x{i}": 10**20 for i in range(4)} | {"h": 10**20}

    def guarded(self, defence, *junk, run=300):
        registry = Issuers(lambda s: "h" if s.startswith("d") else None)
        loads, guards = [], {}

        def before(sim):
            guards.update(guard(sim, lambda name: defence, registry))
            for kwargs in junk:
                loads.append(JunkProofs(registry=registry, **kwargs))
                sim.add_load(loads[-1])

        sim, wallets, rec = aggregating(self.GATED, claims=True, accounts=self.PAYERS, run=run, before=before)
        counts = Counter()
        for g in guards.values():
            counts.update(g.counts)
        return sim, wallets, rec, loads, guards, counts

    def test_without_a_defence_every_junk_proof_costs_every_node_a_ticket_a_prefix_and_a_proof(self):
        sim, wallets, rec, (x,), _, counts = self.guarded(
            Defence(), dict(name="x", issuers=["x0"], count=1, every=12, start=60, stop=240))
        self.assertEqual(x.answers, Counter({"ErrWrapperProof": x.sent}))
        self.assertEqual(x.sent, 15 * len(sim.net.nodes))
        self.assertEqual(x.tickets, 15)
        self.assertEqual(counts["ticket", "x"], x.sent)
        self.assertEqual(counts["prefix", "x"], x.sent)
        self.assertEqual(work(sim, origin="x", event="proof"), x.sent)
        self.assertTrue(all(rec.txs[tx.hash].included_at is not None for tx in wallets.txs))

    def test_issuer_memory_closes_an_issuer_after_k_failures_until_the_epoch_ends(self):
        sim, _, _, (x,), guards, counts = self.guarded(
            Defence(memory=2), dict(name="x", issuers=["x0"], count=1, every=12, start=60, stop=480), run=500)
        nodes = len(sim.net.nodes)
        # two failures a node in each of epochs 0 and 1, the rest refused before the ticket is checked
        self.assertEqual(work(sim, origin="x", event="proof"), 4 * nodes)
        self.assertEqual(x.answers["ErrWrapperProof"], 4 * nodes)
        self.assertEqual(x.answers["ErrIssuerRefused"], x.sent - 4 * nodes)
        self.assertEqual(counts["ticket", "x"], 4 * nodes)
        self.assertEqual(counts["refused", "x"], x.sent - 4 * nodes)
        for g in guards.values():
            self.assertEqual(sorted(g.closed), [("x0", 0), ("x0", 1)])

    def test_a_self_issuer_with_more_issuers_gets_k_proofs_from_each_every_epoch(self):
        sim, _, _, (x,), _, _ = self.guarded(
            Defence(memory=1), dict(name="x", issuers=["x0", "x1", "x2"], count=1, every=12, start=60, stop=480,
                                    rotate=True), run=500)
        nodes = len(sim.net.nodes)
        self.assertEqual(x.used, {"x0", "x1", "x2"})
        self.assertEqual(work(sim, origin="x", event="proof"), 2 * 3 * nodes)  # epochs 0 and 1

    def test_issuer_memory_lets_a_holder_of_honest_tickets_close_an_honest_issuer(self):
        sim, wallets, rec, (g,), guards, counts = self.guarded(
            Defence(memory=1), dict(name="g", issuers=["h"], count=1, every=384, offset=100, start=60), run=500)
        self.assertEqual(g.tickets, 2)  # one in each epoch it ran in
        self.assertGreater(counts["refused", "d"], 0)
        refused = Counter(a for answers in wallets.answers.values() for a in answers)
        self.assertGreater(refused["ErrIssuerRefused"], 0)
        for gd in guards.values():
            self.assertIn(("h", 0), gd.closed)

    def test_a_node_list_refuses_an_unlisted_issuer_before_any_check(self):
        sim, wallets, rec, (x,), _, counts = self.guarded(
            Defence(listed=frozenset({"h"})), dict(name="x", issuers=["x0"], count=1, every=12, start=60, stop=240))
        self.assertEqual(x.answers, Counter({"ErrIssuerUnlisted": x.sent}))
        self.assertEqual(counts["ticket", "x"] + counts["prefix", "x"], 0)
        self.assertEqual(work(sim, origin="x", event="proof"), 0)
        self.assertTrue(all(rec.txs[tx.hash].included_at is not None for tx in wallets.txs))


class TestBond(unittest.TestCase):
    """The third defence: ERC-8421's stake and reputation for ticket paymasters (decision record 0062)."""

    GATED, PAYERS = TestIssuers.GATED, TestIssuers.PAYERS
    # AM-1's parameters, made small: banned once seen // 1 > included + 3, refreshed every 120 s
    SMALL = EIP_8141.with_(min_inclusion_rate_denominator=1, throttling_slack=1, ban_slack=3, refresh_seconds=120)

    def bonded(self, *junk, bonded=frozenset({"h", "x0", "x1"}), config=SMALL, run=300):
        return TestIssuers.guarded(self, Defence(bond=Bond(bonded, config)), *junk, run=run)

    def test_an_unbonded_paymasters_tickets_are_refused_before_any_check(self):
        sim, wallets, rec, (x,), _, counts = self.bonded(
            dict(name="x", issuers=["x3"], count=1, every=12, start=60, stop=240), config=EIP_8141)
        self.assertEqual(x.answers, Counter({"ErrIssuerUnbonded": x.sent}))
        self.assertEqual(counts["ticket", "x"] + counts["prefix", "x"], 0)
        self.assertEqual(work(sim, origin="x", event="proof"), 0)
        self.assertTrue(all(rec.txs[tx.hash].included_at is not None for tx in wallets.txs))

    def test_a_bonded_self_issuer_is_banned_after_its_failures_and_moves_on(self):
        sim, _, _, (x,), guards, counts = self.bonded(
            dict(name="x", issuers=["x0", "x1"], count=1, every=12, start=60, stop=110, rotate=True), run=118)
        nodes = len(sim.net.nodes)
        # five rounds: x0 is throttled at seen 2 (2 > 0 + 1) and banned at 4 (4 > 0 + 3), the fifth goes to x1
        self.assertEqual(work(sim, origin="x", event="proof"), 5 * nodes)
        self.assertEqual(x.answers["ErrEntityBanned"], nodes)
        self.assertEqual(counts["banned", "x"], nodes)
        for g in guards.values():
            self.assertEqual(g.counters["x0"], [4, 0])
            self.assertEqual(g.counters["x1"], [1, 0])
            self.assertEqual([s for _, who, s in g.states if who == "x0"], [THROTTLED, BANNED])
            self.assertGreater(g.time_in("x0", BANNED, 118), 0)

    def test_a_refresh_reopens_a_banned_paymaster(self):
        sim, _, _, (x,), guards, _ = self.bonded(
            dict(name="x", issuers=["x0"], count=1, every=12, start=60, stop=110), run=130)
        for g in guards.values():
            g.refresh(130)
            self.assertEqual(g.counters["x0"], [3, 0])  # 4 seen, then 4 * 23 // 24 at 120 s: throttled again
            states = [(t, s) for t, who, s in g.states if who == "x0"]
            self.assertEqual([s for _, s in states], [THROTTLED, BANNED, THROTTLED])
            self.assertEqual(states[2][0], 120)
            self.assertEqual(g.time_in("x0", BANNED, 130), 120 - states[1][0])

    def test_a_throttled_paymaster_backs_only_so_many_pending_spends(self):
        # a holder of h's tickets fails four proofs a node a slot; h is throttled and never banned
        config = EIP_8141.with_(min_inclusion_rate_denominator=1, throttling_slack=2, ban_slack=10**6,
                                throttled_entity_mempool_count=1)
        sim, wallets, _, (g,), guards, counts = self.bonded(
            dict(name="g", issuers=["h"], count=4, every=12, start=60, stop=240), config=config)
        self.assertGreater(counts["throttled", "d"], 0)
        self.assertGreater(g.answers["ErrEntityThrottled"], 0)  # junk too, while h backs a pending spend
        refused = Counter(a for answers in wallets.answers.values() for a in answers)
        self.assertGreater(refused["ErrEntityThrottled"], 0)
        for gd in guards.values():
            self.assertIn(THROTTLED, [s for _, who, s in gd.states if who == "h"])
            self.assertNotIn(BANNED, [s for _, who, s in gd.states if who == "h"])

    def test_an_honest_paymasters_spends_count_as_seen_and_included(self):
        sim, wallets, rec, _, guards, _ = self.bonded(config=EIP_8141)
        landed = sum(rec.txs[tx.hash].included_at is not None for tx in wallets.txs)
        self.assertGreater(landed, 20)
        for g in guards.values():
            seen, included = g.counters["h"]
            self.assertEqual(seen, len(wallets.txs))  # every node admits every spend once
            self.assertGreaterEqual(included, landed - 2)  # all but the last blocks' spends
            self.assertEqual(g.state("h"), "ACTIVE")


class TestBumping(unittest.TestCase):
    def test_a_bump_raises_both_fields_by_the_percent_and_the_cap_to_the_market(self):
        self.assertEqual(bump_fees(100, 200, 10), (110, 220))
        self.assertEqual(bump_fees(100, 200, 10, base=1000), (110, 1110))
        self.assertEqual(bump_fees(100, 200, 10, base=1000, limit=230), (110, 230))
        self.assertIsNone(bump_fees(100, 200, 10, limit=219))  # NP-11 would refuse it

    def test_the_demand_does_not_depend_on_the_wallet(self):
        runs = [congested(), congested(patience=1, reprice=True)]
        for sim, _, _ in runs:
            sim.run(300)
        asked = [[(t.requested_at, t.sender, t.versions[0].tip) for t in load.transfers] for _, load, _ in runs]
        self.assertEqual(asked[0], asked[1])

    def test_a_wallet_that_bumps_clears_the_backlog_sooner_with_replacements_the_pool_admits(self):
        never, bumping = congested(), congested(patience=1, reprice=True)
        for sim, _, _ in (never, bumping):
            sim.run(360)
        waiting = [sum(not landed_any(sim, t.versions) for t in load.transfers) for sim, load, _ in (never, bumping)]
        self.assertLess(waiting[1], waiting[0] / 2)
        load = bumping[1]
        self.assertEqual(set(load.answers), {"ok"})
        for t in load.transfers:
            for old, new in zip(t.versions, t.versions[1:]):
                self.assertGreaterEqual(new.tip, old.tip * 110 // 100)
                self.assertGreaterEqual(new.max_fee, old.max_fee * 110 // 100)
        self.assertTrue(all(len(t.versions) == 1 for t in never[1].transfers))

    def test_a_wallet_that_re_prices_every_transaction_re_prices_more_than_the_oldest(self):
        oldest, every = congested(patience=1), congested(patience=1, every=True)
        for sim, _, _ in (oldest, every):
            sim.run(360)
        self.assertEqual(set(every[1].answers), {"ok"})
        self.assertGreater(sum(every[1].answers.values()), sum(oldest[1].answers.values()))
        waiting = [sum(not landed_any(sim, t.versions) for t in load.transfers) for sim, load, _ in (oldest, every)]
        self.assertLessEqual(waiting[1], waiting[0])

    def test_a_limit_prices_users_out_and_caps_every_version(self):
        sim, load, _ = congested(patience=1, reprice=True, limit=fixed(3 * 10**9))
        sim.run(600)
        self.assertGreater(load.priced_out, 0)
        self.assertLessEqual(max(v.max_fee for t in load.transfers for v in t.versions), 3 * 10**9)

    def test_only_a_spends_user_re_prices_it_and_the_relayer_sends_the_new_version(self):
        sim, _, spends = congested(spend=(1, True))
        sim.run(900)
        bumped = [sp for sp in spends.spends if len(sp.versions) > 1]
        self.assertTrue(bumped)
        for sp in bumped:
            self.assertTrue(landed_any(sim, sp.versions))
            self.assertEqual({v.signatures for v in sp.versions}, {sp.versions[0].signatures})
            self.assertEqual({v.nonce_keys for v in sp.versions}, {sp.versions[0].nonce_keys})
        sim, _, spends = congested(spend=(None, False))
        sim.run(900)
        self.assertTrue(all(len(sp.versions) == 1 for sp in spends.spends))

if __name__ == "__main__":
    unittest.main()


def proved(window, rate=4.0, invalid=0.0, run=60, nodes=8):
    """Proof-carrying frame transactions from many senders, and optionally invalid proofs handed to every node."""
    senders = [f"p{i}" for i in range(400)]
    sim = Simulation(Scenario(seed=7, nodes=nodes, network=NetworkConfig(degree=3, batch_window=window),
                              genesis=Head(timestamp=0, gas_limit=30_000_000, gas_used=15_000_000, base_fee=10**9),
                              accounts={s: 10**20 for s in senders}))
    load = ProofLoad("p", rate=rate, senders=senders, start=1, stop=run - 12)
    sim.add_load(load)
    if invalid:
        sim.add_load(InvalidProofLoad("x", rate=invalid, senders=["x"], start=1, stop=run - 12))
    return sim, sim.run(run)


class TestBatches(unittest.TestCase):
    def test_the_cost_of_a_batch_is_the_measured_one_and_grows_slower_than_its_size(self):
        for n, (_, batch) in MEASURED.items():
            self.assertAlmostEqual(batch_ms(n), batch)
        self.assertEqual(batch_ms(1), SINGLE_MS)
        sizes = [1, 2, 3, 8, 32, 100, 512, 4096, 65536]
        costs = [batch_ms(n) for n in sizes]
        self.assertEqual(costs, sorted(costs))
        per_proof = [c / n for c, n in zip(costs, sizes)]
        self.assertEqual(per_proof, sorted(per_proof, reverse=True))

    def test_a_failed_batch_is_bisected_down_to_the_bad_proof(self):
        self.assertEqual(verify([True] * 8), (batch_ms(8), 1))
        cost, checks = verify([True] * 7 + [False])
        self.assertEqual(checks, 7)  # 8, then 4 and 4, then 2 and 2, then 1 and 1
        self.assertAlmostEqual(cost, batch_ms(8) + 2 * batch_ms(4) + 2 * batch_ms(2) + 2 * batch_ms(1))
        self.assertEqual(verify([False])[1], 1)

    def test_every_proof_is_verified_once_a_node_and_every_transaction_lands(self):
        for window in (0.0, 0.5):
            sim, rec = proved(window)
            proofs = [r for r in rec.txs.values() if r.tx.hash in sim.net.proofs]
            self.assertTrue(proofs)
            for r in proofs:
                self.assertIsNotNone(r.included_at, r.tx.label)
            for node in sim.net.nodes.values():
                self.assertFalse(node.held)
                self.assertFalse(node.holding)
                # One included before it arrived is not verified; one the pool refused, here as ErrNonceTooHigh
                # because the node had not imported its predecessor's block, is fetched and verified again.
                self.assertLessEqual(abs(sum(node.batches) - len(proofs)), 2)
                if window == 0:
                    self.assertEqual(set(node.batches), {1})

    def test_a_window_forms_batches_saves_verification_and_slows_propagation(self):
        (alone, a), (batched, b) = proved(0.0), proved(0.5)
        self.assertGreater(max(max(n.batches) for n in batched.net.nodes.values()), 1)
        self.assertLess(sum(n.verify_ms for n in batched.net.nodes.values()),
                        sum(n.verify_ms for n in alone.net.nodes.values()))
        slow = sum(b.propagation_times(8, 1.0)) / len(b.propagation_times(8, 1.0))
        fast = sum(a.propagation_times(8, 1.0)) / len(a.propagation_times(8, 1.0))
        self.assertGreater(slow, fast + 0.5)

    def test_an_invalid_proof_is_refused_everywhere_and_spoils_batches(self):
        sim, rec = proved(0.5, invalid=1.0)
        bad = [r for r in rec.txs.values() if sim.net.proofs.get(r.tx.hash) is False]
        self.assertTrue(bad)
        for r in bad:
            self.assertEqual(r.results, Counter({"ErrInvalidProof": 8}))
            self.assertFalse(r.first_seen)
            self.assertIsNone(r.included_at)
        for node in sim.net.nodes.values():
            self.assertGreater(node.checks, len(node.batches))
        good = [r for r in rec.txs.values() if sim.net.proofs.get(r.tx.hash)]
        self.assertTrue(all(r.included_at is not None for r in good))


def hot(rate, senders=("hot0",), with_code=False, upgrade=None, **kwargs):
    """A `HotWallet` on eight nodes, its senders delegated from genesis `with_code`, with an `Upgrade` of `upgrade`
    authorizations a transaction from second 120 if given."""
    senders = list(senders)
    sc = Scenario(seed=5, nodes=8, network=NetworkConfig(degree=3),
                  genesis=Head(timestamp=0, gas_limit=30_000_000, gas_used=15_000_000, base_fee=10**9),
                  accounts={s: 10**22 for s in senders + ["sponsor"]},
                  code={s: "0xef0100wallet-v1" for s in senders} if with_code else {})
    sim = Simulation(sc)
    load = HotWallet("hot", rate=rate, senders=senders, **kwargs)
    sim.add_load(load)
    up = None
    if upgrade is not None:
        up = Upgrade("up", sponsor="sponsor", wallet=load, batch=upgrade, start=120)
        sim.add_load(up)
    return sim, load, up


class TestDelegatedAccounts(unittest.TestCase):
    """NP-6 and NP-7 against a hot wallet, and BB-5's authorizations, in the simulator (decision record 0031)."""

    def test_a_delegated_wallet_lands_one_transaction_a_block_and_an_eoa_more(self):
        sim, load, _ = hot(0.5, with_code=True, rule="serial")
        sim.run(600)
        rec = sim.recorder
        txs = {t.versions[-1].hash for t in load.transfers if t.versions}
        per_block = Counter(rec.txs[h].block for h in txs if rec.txs[h].included_at is not None)
        self.assertEqual(max(per_block.values()), 1)
        self.assertGreater(len(load.queue["hot0"]), 100)
        sim, load, _ = hot(0.5, rule="at once")
        sim.run(600)
        rec = sim.recorder
        per_block = Counter(rec.txs[t.versions[-1].hash].block for t in load.transfers
                            if rec.txs[t.versions[-1].hash].included_at is not None)
        self.assertGreater(max(per_block.values()), 1)

    def test_a_delegated_wallet_sending_at_once_is_refused_by_np6(self):
        sim, load, _ = hot(0.5, with_code=True, rule="at once")
        sim.run(300)
        self.assertGreater(load.answers["ErrInflightTxLimitReached"], 0)

    def test_a_batching_wallet_carries_every_transfer_waiting_in_one_transaction(self):
        sim, load, _ = hot(0.5, with_code=True, rule="batch")
        sim.run(600)
        rec = sim.recorder
        asked = [t for t in load.transfers if t.requested_at < 560]
        self.assertTrue(all(t.versions and rec.txs[t.versions[-1].hash].included_at is not None for t in asked))
        sizes = Counter(t.versions[-1].hash for t in load.transfers if t.versions)
        self.assertGreater(max(sizes.values()), 1)
        for h, n in sizes.items():
            self.assertEqual(rec.txs[h].tx.gas, 21000 * n)
        per_block = Counter(rec.txs[h].block for h in sizes)
        self.assertEqual(max(per_block.values()), 1)

    def test_a_draining_wallet_is_upgraded_without_a_skipped_authorization(self):
        senders = [f"hot{i}" for i in range(4)]
        sim, load, up = hot(1.0, senders=senders, rule="at once", delegated="batch", upgrade=4, sign="drain")
        sim.run(600)
        self.assertEqual(sorted(up.done_at), senders)
        self.assertFalse(any(b["skipped"] for b in up.batches))
        self.assertTrue(all(sim.chain.state.code(s) == "0xef0100wallet-v1" for s in senders))
        self.assertTrue(all(isinstance(a, tuple) for b in up.batches for tx in b["txs"] for a in tx.authorities))
        self.assertFalse(load.paused)
        self.assertEqual(load.lost, 0)

    def test_a_wallet_that_keeps_sending_spends_its_own_authorization(self):
        sim, load, up = hot(1.0, rule="at once", delegated="batch", upgrade=1, sign="next")
        sim.run(600)
        skipped = sum(len(b["skipped"]) for b in up.batches)
        self.assertGreater(skipped, 0)
        included = [b for b in up.batches if b["included_at"] is not None]
        self.assertEqual(sum(len(b["applied"]) + len(b["skipped"]) for b in included), len(included))



def state_priced(dimensions: str, seconds: float = 240.0):
    """Item 34: transfers that fill blocks, beside spends with a nullifier's state gas in a frame
    transaction and in a type 2 transaction."""
    senders = [f"b{i}" for i in range(200)] + [f"r{i}" for i in range(50)]
    scenario = Scenario(seed=3, nodes=8, network=NetworkConfig(degree=4, latency=(0.02, 0.05)),
                        chain=ChainConfig(dimensions=dimensions),
                        frame_pool=replace(EIP_8141, per_sender="disjoint-keys"),
                        genesis=Head(timestamp=0, gas_limit=1_000_000, gas_used=500_000, base_fee=1_000_000_000),
                        accounts={**{s: 10**24 for s in senders}, "pool": 10**24}, code={"pool": "privacy-pool"})
    sim = Simulation(scenario)
    background = TransferLoad("bg", rate=1.0, senders=[f"b{i}" for i in range(200)], gas=uniform(21000, 200000),
                              fee_multiplier=1000)
    relayed = TransferLoad("t2", rate=0.1, senders=[f"r{i}" for i in range(50)], gas=70000, state=97920,
                           fee_multiplier=1000)
    spends = SharedSenderLoad("spend", rate=0.1, senders=["pool"], serial=False, key_bytes=32, state_gas=97920,
                              fee_multiplier=1000)
    for load in (background, relayed, spends):
        sim.add_load(load)
    return sim, spends, sim.run(seconds)


class TestStateGas(unittest.TestCase):
    """The plan's item 34, decision record 0043: BB-6's two dimensions in the chain."""

    def test_two_dimensions_count_state_apart_and_head_the_larger(self):
        _, spends, rec = state_priced("two")
        self.assertTrue(all(b["gas_used"] == max(b["execution"], b["state"]) for b in rec.blocks))
        self.assertTrue(all(b["execution"] <= b["gas_limit"] and b["state"] <= b["gas_limit"] for b in rec.blocks))
        self.assertTrue(any(b["state"] > 0 for b in rec.blocks))
        spend = spends.spends[0].tx
        self.assertEqual(spend.state_used, 97920)
        self.assertEqual(spend.frames[0].state_gas, 97920)  # a nonce key's first use, charged at APPROVE

    def test_one_counts_one_sum(self):
        _, _, rec = state_priced("one")
        self.assertTrue(all("execution" not in b for b in rec.blocks))
        self.assertTrue(all(b["gas_used"] <= b["gas_limit"] for b in rec.blocks))

    def test_a_storage_nullifier_is_the_sender_frames(self):
        load = SharedSenderLoad("s", rate=0.1, senders=["pool"], expiring=48, state_gas=97920)
        sim = Simulation(Scenario(nodes=2, frame_pool=EIP_8266, accounts={"pool": 10**24},
                                  code={"pool": "privacy-pool", EIP_8266.expiry_verifier: "expiry-verifier"}))
        node = next(iter(sim.net.nodes.values()))
        tx = load.spend_tx(sim, Spend(0, "s-0", "pool", 0.0, 10**9), node=node)
        self.assertEqual([f.state_gas for f in tx.frames], [0, 0, 97920])
        self.assertEqual(tx.state_used, 97920)

    def test_a_transfer_adds_its_state_gas_to_its_limit(self):
        load = TransferLoad("t", rate=1.0, senders=["a"], gas=70000, state=97920)
        sim = Simulation(Scenario(nodes=2, accounts={"a": 10**24}))
        load.attach(sim)
        tx = load.make(sim, "a")
        self.assertEqual((tx.gas, tx.state_used), (167920, 97920))

    def test_a_transfer_draws_its_state_gas(self):
        load = TransferLoad("t", rate=1.0, senders=["a"], gas=70000, state=one_of(97920, 183600))
        sim = Simulation(Scenario(nodes=2, accounts={"a": 10**24}))
        load.attach(sim)
        txs = [load.make(sim, "a") for _ in range(40)]
        self.assertEqual({t.state_used for t in txs}, {97920, 183600})
        self.assertTrue(all(t.gas == 70000 + t.state_used for t in txs))


def shuffled(mode="public", griefer=False, size=16, drop=False, count=3, run=400.0, seed=2):
    """`ShuffleRounds` on a small network: a contract round's gas, 0.1 ether a seat."""
    rounds = ShuffleRounds("s", address="pub", node="n00", size=size, mode=mode,
                           gas=lambda n: 28078 + 67041 * n, revert_gas=lambda m: 28078 + 342675 * m // 8,
                           data_size=lambda n: 132 + 224 * n, coordination=lambda rng: rng.uniform(6, 18),
                           unit=10**17, spare=10**15, griefer=griefer, count=count)
    sim = Simulation(Scenario(seed=seed, nodes=6, network=NetworkConfig(degree=3),
                              chain=ChainConfig(drop_reverting=drop),
                              sealed_pool=EIP_8184 if mode == "sealed" else Scenario.sealed_pool,
                              genesis=Head(timestamp=0, gas_limit=60_000_000, gas_used=30_000_000, base_fee=10**9),
                              accounts={"pub": 10**22, **rounds.accounts()}))
    sim.add_load(rounds)
    rec = sim.run(run)
    return sim, rounds, rec


class TestShuffleRounds(unittest.TestCase):
    """The plan's item 21, decision records 0045 and 0046: shuffle rounds, and an input that spends first."""

    def test_an_honest_round_settles_at_once_and_pays_every_output(self):
        sim, load, rec = shuffled()
        self.assertEqual([r.outcome for r in load.rounds], ["settled"] * 3)
        for r in load.rounds:
            [a] = r.attempts
            self.assertEqual(a.outcome, "settled")
            self.assertTrue(all(sim.chain.state.balance(i) == 10**15 for i in r.inputs))
            self.assertTrue(all(sim.chain.state.balance(o) == 10**17 for o, _ in a.tx.pays))
            self.assertEqual(sim.chain.state.balance(a.tx.to), 0)
        self.assertFalse(any(b.get("reverted") for b in rec.blocks))

    def test_a_griefer_reverts_the_round_at_its_seat_and_the_next_attempt_settles_without_it(self):
        sim, load, rec = shuffled(griefer=True)
        reverted = {h for b in rec.blocks for h in b.get("reverted", ())}
        for r in load.rounds:
            first, second = r.attempts
            self.assertEqual((first.outcome, second.outcome, r.outcome), ("reverted", "settled", "settled"))
            self.assertIn(first.tx.hash, reverted)
            self.assertEqual(rec.txs[first.tx.hash].block, rec.txs[r.grief.hash].block)  # the grief went first
            self.assertEqual(first.gas_lost, 28078 + 342675 * (first.tx.pulls.index((r.griefer, 10**17)) + 1) // 8)
            self.assertEqual((first.size, second.size), (16, 15))
            self.assertNotIn(r.griefer, r.inputs)
            self.assertEqual(sim.chain.state.balance(f"s-{r.index}-round"), 0)
            self.assertTrue(all(sim.chain.state.balance(o) == 0 for o, _ in first.tx.pays))
            self.assertTrue(all(sim.chain.state.balance(o) == 10**17 for o, _ in second.tx.pays))

    def test_a_round_given_up_before_it_reverts_is_coordinated_once_an_attempt(self):
        coordinated = Counter()
        coordinate = ShuffleRounds._coordinate

        def counting(load, r):
            coordinated[r.index] += 1
            coordinate(load, r)

        with mock.patch.object(ShuffleRounds, "_coordinate", counting):
            sim, load, rec = shuffled(griefer=True, count=20, run=1500.0, seed=4)
        late = [r for r in load.rounds if rec.txs[r.attempts[0].tx.hash].block > rec.txs[r.grief.hash].block]
        self.assertTrue(late)  # the grief landed first, the round was given up, and then it was included
        for r in load.rounds:
            first, second = r.attempts
            self.assertEqual((first.outcome, second.outcome, r.outcome), ("reverted", "settled", "settled"))
            self.assertEqual(coordinated[r.index], 2)

    def test_builders_that_drop_it_leave_the_round_out_and_its_replacement_settles(self):
        sim, load, rec = shuffled(griefer=True, drop=True)
        self.assertFalse(any(b.get("reverted") for b in rec.blocks))
        for r in load.rounds:
            first, second = r.attempts
            self.assertEqual((first.outcome, second.outcome, first.gas_lost), ("dropped", "settled", 0))
            self.assertIsNone(rec.txs[first.tx.hash].block)
            self.assertEqual(second.tx.nonce, first.tx.nonce)  # it replaced the dropped round
            self.assertGreater(second.tx.tip, first.tx.tip)

    def test_a_sealed_round_reverts_at_the_top_of_the_next_block(self):
        sim, load, rec = shuffled("sealed", griefer=True)
        blocks = {b["number"]: b for b in rec.blocks}
        for r in load.rounds:
            first, second = r.attempts
            self.assertEqual((first.outcome, second.outcome), ("reverted", "settled"))
            committed_in = rec.txs[first.tx.hash].block
            self.assertEqual(rec.txs[r.grief.hash].block, committed_in)
            self.assertIn(first.tx.hash, blocks[committed_in + 1]["reverted"])

    def test_a_sealed_round_above_the_tob_segment_is_refused(self):
        _, load, _ = shuffled("sealed", size=128, count=1, run=60.0)
        self.assertEqual(load.rounds[0].outcome, "refused")  # 28078 + 67041 * 128 > 60M / 8 (LU-4)

    def test_a_lock_skips_the_griefer_and_settles_the_rest(self):
        sim, load, rec = shuffled("lock", griefer=True)
        self.assertFalse(any(b.get("reverted") for b in rec.blocks))
        for r in load.rounds:
            [a] = r.attempts
            self.assertEqual((a.outcome, r.outcome, len(r.inputs)), ("settled", "settled", 15))
            self.assertLess(rec.txs[a.lock.hash].block, rec.txs[a.tx.hash].block)
            self.assertEqual(sim.chain.state.balance(f"s-{r.index}-escrow"), 0)
            self.assertEqual(len(a.tx.pays), 15)

    def test_a_lock_that_leaves_too_few_is_abandoned(self):
        _, load, _ = shuffled("lock", griefer=True, size=8)
        self.assertEqual([(r.outcome, r.attempts[0].outcome) for r in load.rounds], [("abandoned", "short")] * 3)
