import unittest

from emem import EIP_8141, GETH, HEGOTA_TESTNET, Account, Frame, FrameTx, Head, SealedTx, State, Tx, TxPool, build_block

HEAD = Head(timestamp=1000, gas_limit=30_000_000, gas_used=15_000_000, base_fee=10)


def simple(sender, label, **kw):
    frames = kw.pop("frames", (Frame(mode=1, flags=3, exec_gas=30000), Frame(mode=2, exec_gas=50000)))
    return FrameTx(sender, frames, label=label, **kw)


class TestBuilder(unittest.TestCase):
    def test_disjoint_keys_from_one_sender_land_in_one_block(self):
        state = State({"alice": Account(balance=10**9)})
        pool = TxPool(HEAD, state, GETH, HEGOTA_TESTNET)
        results = pool.add([simple("alice", "k5", nonce_keys=(5,)), simple("alice", "k6", nonce_keys=(6,))])
        self.assertEqual(results, ["ok", "ok"])
        block, post = build_block(pool, HEAD, state, min_tip=1)
        self.assertEqual([t.label for t in block.txs], ["k5", "k6"])
        self.assertEqual((post.nonce_seq("alice", 5), post.nonce_seq("alice", 6), post.nonce("alice")), (1, 1, 0))

    def test_sender_frames_move_value_and_deploy_installs_code(self):
        state = State({"alice": Account(balance=10**9), "factory": Account(code="factory-v1")})
        frames = (Frame(mode=0, target="factory", exec_gas=30000, installs_code="account-v1", writes=(("alice", 1, 7),)),
                  Frame(mode=1, flags=3, exec_gas=30000, approves=3),
                  Frame(mode=2, target="bob", value=500, exec_gas=50000))
        pool = TxPool(HEAD, state)
        self.assertEqual(pool.add([FrameTx("alice", frames, label="deploy")]), ["ok"])
        block, post = build_block(pool, HEAD, state, min_tip=1)
        self.assertEqual(len(block.txs), 1)
        self.assertEqual(post.code("alice"), "account-v1")
        self.assertEqual(post.storage("alice", 1), 7)
        self.assertEqual(post.balance("bob"), 500)

    def test_equal_tips_across_subpools_go_by_arrival(self):
        state = State({"alice": Account(balance=10**9), "bob": Account(balance=10**9)})
        pool = TxPool(HEAD, state)
        pool.add([simple("bob", "frame-first", tip=10)])
        pool.add([Tx("alice", tip=10, label="plain-second")])
        block, _ = build_block(pool, HEAD, state, min_tip=1)
        self.assertEqual([t.label for t in block.txs], ["frame-first", "plain-second"])

    def test_the_new_head(self):
        state = State({"alice": Account(balance=10**9)})
        pool = TxPool(HEAD, state)
        pool.add([Tx("alice", nonce=n, label=str(n)) for n in range(3)])
        block, _ = build_block(pool, HEAD, state, min_tip=1, slot_time=12)
        self.assertEqual((block.head.number, block.head.timestamp, block.head.gas_used, block.head.base_fee),
                         (1, 1012, 63000, 10))

    def test_reset_after_build_empties_the_pool(self):
        state = State({"alice": Account(balance=10**9), "bob": Account(balance=10**9)})
        pool = TxPool(HEAD, state, GETH, EIP_8141)
        pool.add([Tx("alice", label="a"), simple("bob", "b")])
        block, post = build_block(pool, HEAD, state, min_tip=1)
        pool.reset(block.head, post, 12)
        self.assertEqual(len(pool), 0)


if __name__ == "__main__":
    unittest.main()


class TestTwoDimensions(unittest.TestCase):
    """BB-6, against random pools: neither sum passes the gas limit, the header's gas used is the larger,
    every head left out did not fit or came after the loop stopped, and `one` is unchanged by the field."""

    def random_pool(self, rng, limit):
        head = Head(timestamp=1000, gas_limit=limit, gas_used=limit // 2, base_fee=10)
        senders = [f"s{i}" for i in range(40)]
        state = State({s: Account(balance=10**12) for s in senders})
        pool = TxPool(head, state, GETH, EIP_8141)
        txs = []
        for i, s in enumerate(senders):
            tip = rng.randint(1, 90)
            if rng.random() < 0.5:
                gas = rng.randint(21000, limit // 4)
                state_gas = rng.choice((0, rng.randint(0, gas - 21000)))
                txs.append(Tx(s, gas=gas, tip=tip, state_gas_used=state_gas or None, label=f"t{i}"))
            else:
                state_gas = rng.choice((0, 97920))
                frames = (Frame(mode=1, flags=3, exec_gas=rng.randint(1000, 30000)),
                          Frame(mode=2, exec_gas=rng.randint(1000, 60000), state_gas=state_gas))
                txs.append(FrameTx(s, frames, tip=tip, label=f"f{i}"))
        self.assertEqual(pool.add(txs), ["ok"] * len(txs))
        return head, state, pool, txs

    def test_random_blocks(self):
        import random
        rng = random.Random(8037)
        for _ in range(60):
            limit = rng.choice((300_000, 1_000_000, 2_100_000))
            head, state, pool, txs = self.random_pool(rng, limit)
            block, _ = build_block(pool, head, state, min_tip=1, dimensions="two")
            gas = block.gas
            x = sum(t.used - t.state_used for t in block.txs)
            s = sum(t.state_used for t in block.txs)
            self.assertEqual((gas.execution, gas.state), (x, s))
            self.assertLessEqual(max(x, s), limit)
            self.assertEqual(block.head.gas_used, max(x, s))
            # the sums only grow, so a head dropped for not fitting still does not fit at the end, and
            # anything else left out came after the loop stopped
            self.assertEqual(block.failed, ())
            for t in txs:
                if t not in block.txs:
                    self.assertTrue(not gas.fits(t) or not gas.more())

    def test_one_ignores_state_gas(self):
        import random
        rng = random.Random(1)
        for _ in range(30):
            head, state, pool, txs = self.random_pool(rng, 1_000_000)
            block, _ = build_block(pool, head, state, min_tip=1)
            self.assertEqual(block.head.gas_used, sum(t.used for t in block.txs))
            self.assertLessEqual(block.head.gas_used, 1_000_000)

    def test_state_gas_used_leaves_the_hash_alone_at_its_default(self):
        self.assertEqual(Tx("alice").hash, Tx("alice", state_gas_used=None).hash)
        self.assertNotEqual(Tx("alice").hash, Tx("alice", state_gas_used=0).hash)
        frames = (Frame(mode=1, flags=3, exec_gas=1000), Frame(mode=2, exec_gas=1000, state_gas=97920))
        self.assertEqual(FrameTx("alice", frames).state_used, 97920)
        self.assertEqual(FrameTx("alice", frames).hash, FrameTx("alice", frames, state_gas_used=None).hash)


class TestReverts(unittest.TestCase):
    """BB-5 and BB-7 against random rounds: value is conserved, a revert moves nothing but the fee, and a builder
    that drops what reverts leaves exactly the state the rest of the block makes."""

    def rounds(self, rng):
        head = Head(timestamp=1000, gas_limit=30_000_000, gas_used=15_000_000, base_fee=10)
        inputs = [f"i{k}" for k in range(12)]
        state = State({"pub": Account(balance=10**12), **{i: Account(balance=rng.choice((0, 500, 1000, 5000)))
                                                          for i in inputs}})
        pool = TxPool(head, state, GETH, EIP_8141)
        n = rng.randint(1, 6)
        picked = rng.sample(inputs, n)
        tx = Tx("pub", to="round", gas=100_000, revert_gas_used=rng.randint(21000, 100_000),
                atomic=rng.choice((None, False)), pulls=tuple((i, 1000) for i in picked),
                pays=tuple((f"o{k}", 1000) for k in range(rng.randint(0, n))))
        self.assertEqual(pool.add([tx]), ["ok"])
        return head, state, pool, tx

    def test_value_is_conserved_and_a_revert_moves_only_the_fee(self):
        import random
        rng = random.Random(3009)
        for _ in range(200):
            head, state, pool, tx = self.rounds(rng)
            block, post = build_block(pool, head, state, min_tip=1, coinbase="cb")
            self.assertEqual(block.txs, (tx,))
            reverted = tx in block.reverted
            used = tx.revert_gas_used if reverted else tx.gas
            self.assertEqual(block.head.gas_used, used)
            burned = used * block.head.base_fee
            total = lambda st: sum(st.balance(a) for a in set(st.addresses()) | set(state.addresses()))
            self.assertEqual(total(post), total(state) - burned)
            if reverted:
                for a in state.addresses():
                    if a != "pub":
                        self.assertEqual(post.balance(a), state.balance(a))
                self.assertEqual(post.balance("round"), 0)
            covered = sum(1 for i, _ in tx.pulls if state.balance(i) >= 1000)
            atomic = tx.atomic is not False
            self.assertEqual(reverted, (atomic and covered < len(tx.pulls)) or len(tx.pays) > covered)

    def test_dropping_what_reverts_leaves_the_rest_of_the_block_alone(self):
        import random
        rng = random.Random(7)
        for _ in range(100):
            head, state, pool, tx = self.rounds(rng)
            block, post = build_block(pool, head, state, min_tip=1, coinbase="cb", drop_reverting=True)
            if block.txs:
                self.assertEqual(block.reverted, ())
            else:
                self.assertEqual([err for _, err in block.failed], ["ErrExecutionReverted"])
                self.assertEqual({a: post.balance(a) for a in post.addresses()},
                                 {a: state.balance(a) for a in post.addresses()})
                self.assertEqual(post.nonce("pub"), 0)

    def test_the_new_fields_leave_the_hash_alone_at_their_defaults(self):
        # computed by the version 7 model, before the fields existed: every earlier result keeps its order
        self.assertEqual(Tx("alice").hash, "0x8828399c233038ef555f7ce0ff129934d77520e875cded123b98cff702aebfa0")
        self.assertEqual(SealedTx("alice").hash, "0x70890ba8ad1386a857577eceb07625ee526f91ffbba70dc859fe9aa07d8483f6")
        self.assertNotEqual(Tx("alice").hash, Tx("alice", pulls=()).hash)

