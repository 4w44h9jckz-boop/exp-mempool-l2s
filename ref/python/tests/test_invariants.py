"""Randomised operation sequences against invariants that every clause together implies.

Not a substitute for the vectors: these check that the bookkeeping stays
consistent under sequences nobody wrote by hand, not that it follows a clause.
"""

import random
import unittest

from emem import (EIP_8141, GETH, HEGOTA_TESTNET, MATCHA, Account, Frame, FrameTx, Head, Signature, State, Tx, TxPool,
                  build_block)
from emem.tx import authority_addresses

SENDERS = ["s%d" % i for i in range(6)]


def check_nonce_pool(test, pool):
    p = pool.nonce
    seen = set()
    for addr, l in p.pending.items():
        test.assertFalse(l.empty(), "empty pending list kept")
        nonces = sorted(l.txs)
        test.assertEqual(nonces[0], p.state.nonce(addr), f"pending of {addr} does not start at the account nonce")
        test.assertEqual(nonces, list(range(nonces[0], nonces[0] + len(nonces))), "pending has a gap")
        test.assertEqual(p._pending_nonce(addr), nonces[-1] + 1, "pending nonce out of step")
        test.assertEqual(l.total_cost, sum(t.cost for t in l.txs.values()))
        for t in l.txs.values():
            seen.add(t.hash)
    for addr, q in p.queue.items():
        test.assertFalse(q.empty(), "empty queue kept")
        test.assertIn(addr, p.beats, "queued sender without a heartbeat")
        for t in q.txs.values():
            test.assertNotIn(t.hash, seen, "transaction both pending and queued")
            test.assertGreaterEqual(t.nonce, p.state.nonce(addr))
            seen.add(t.hash)
    test.assertEqual(seen, set(p.all), "lookup out of step with pending and queue")
    test.assertEqual(p.slots, sum(p.num_slots(t) for t in p.all.values()))
    test.assertLessEqual(sum(len(q) for q in p.queue.values()), p.config.global_queue)
    auths = {}
    for t in p.all.values():
        for a in authority_addresses(t):
            auths.setdefault(a, set()).add(t.hash)
    test.assertEqual(auths, p.auths)


def check_frame_pool(test, pool):
    f = pool.frame
    reserved, count = {}, {}
    for e in f.entries.values():
        reserved[e.sim.payer] = reserved.get(e.sim.payer, 0) + e.tx.max_cost
        count[e.sim.payer] = count.get(e.sim.payer, 0) + 1
        test.assertEqual(f.by_identity[(e.tx.sender, e.tx.nonce_keys, e.tx.nonce_seq)], e.tx.hash)
    test.assertEqual(reserved, f.reserved)
    test.assertEqual(count, f.payer_count)
    view = f.pending_view(1, f.head.next_base_fee())
    for payer, r in reserved.items():
        withdrawal = f.state.withdrawal(payer) if f.config.canonical_paymaster_code == f.state.code(payer) else 0
        if not f.matcha:
            test.assertLessEqual(r + withdrawal, f.state.balance(payer), "payer over-committed")
        elif r + withdrawal > f.state.balance(payer):
            test.assertFalse(any(e.sim.payer == payer and e.tx in view for e in f.entries.values()),
                             "an over-reserved payer's transaction is offered (MA-11)")
    test.assertEqual(sum(len(v) for v in f.by_sender.values()), len(f.entries))
    keys = {}
    for e in f.entries.values():
        for k in e.tx.nonce_keys:
            keys.setdefault(e.tx.sender, {}).setdefault(k, 0)
            keys[e.tx.sender][k] += 1
    test.assertEqual(keys, f.keys, "key index out of step with the pending transactions")
    readers = {}
    for h, e in f.entries.items():
        for a in {e.tx.sender, e.sim.payer, *(k[1] for k in e.sim.deps)}:
            readers.setdefault(a, set()).add(h)
    test.assertEqual(readers, f.readers, "dependency index out of step with the pending transactions (FP-15)")
    for e in f.entries.values():
        if e.sim.deadline is not None:
            test.assertGreaterEqual(e.sim.deadline, f.head.timestamp + f.config.expiry_margin, "expired (FP-8, FP-15)")
    if f.matcha:
        test.assertLessEqual(f.bases, set(f.entries), "a baseline not pending (MA-5)")
        claims = {}
        for e in f.entries.values():
            for x in e.cls:
                claims.setdefault(e.tx.sender, {}).setdefault(x, 0)
                claims[e.tx.sender][x] += 1
        test.assertEqual(claims, {s: dict(c) for s, c in f.claims.items()}, "class index out of step (MA-14)")
        for sender in f.by_sender:
            seen = set()
            for h in f.baselines(sender):
                test.assertFalse(seen & f.entries[h].cls, "two baselines share a class (MA-14)")
                seen |= f.entries[h].cls
        for sender, w in f.widths.items():
            test.assertGreaterEqual(w, 0, "width below zero (MA-3)")
            test.assertLessEqual(w, f.config.width_cap)
        for sender, hashes in f.by_sender.items():
            if len(hashes) > 1:
                keys = [k for h in hashes for k in f.entries[h].tx.nonce_keys]
                test.assertNotIn(0, keys, "key 0 beside another transaction (MA-6)")
                test.assertEqual(len(keys), len(set(keys)), "a key shared by two pending transactions (MA-6)")


def check_reservations(test, pool):
    holders = pool.reserver._owner
    for addr in set(pool.nonce.pending) | set(pool.nonce.queue):
        test.assertIs(holders.get(addr), pool.nonce)
    for addr in pool.frame.by_sender:
        test.assertIs(holders.get(addr), pool.frame)
    for addr, owner in holders.items():
        if owner is pool.nonce:
            test.assertTrue(addr in pool.nonce.pending or addr in pool.nonce.queue, f"{addr} held but empty")
        else:
            test.assertIn(addr, pool.frame.by_sender)


def random_tx(rng, state):
    sender = rng.choice(SENDERS)
    base = state.nonce(sender)
    if state.code(sender) == "app":  # a contract sender whose prefix reads up to two of its slots (MA-14)
        reads = tuple((sender, slot, None) for slot in rng.sample([1, 2, 3, 4], rng.randint(0, 2)))
        frames = (Frame(mode=1, flags=3, exec_gas=30000, approves=3, reads=reads), Frame(mode=2, exec_gas=20000))
        keys = rng.choice([(5,), (6,), (7,), (5, 7), (8,), (9,)])
        return FrameTx(sender, frames, nonce_keys=keys, nonce_seq=state.nonce_seq(sender, keys[0]),
                       max_fee=rng.randint(5, 60), tip=rng.randint(1, 5), label="f%d" % rng.randrange(10**6))
    if rng.random() < 0.3:
        frames = (Frame(mode=1, flags=3, exec_gas=30000), Frame(mode=2, exec_gas=rng.choice([20000, 50000])))
        keys = rng.choice([(0,), (0,), (5,), (6,), (5, 7), (8,)])
        return FrameTx(sender, frames, nonce_keys=keys, nonce_seq=state.nonce_seq(sender, keys[0]),
                       max_fee=rng.randint(5, 60), tip=rng.randint(1, 5), label="f%d" % rng.randrange(10**6))
    kind = rng.random()
    authorities = ()
    if kind < 0.1:
        authorities = (rng.choice(SENDERS),)
    fee = rng.randint(5, 60)
    return Tx(sender, nonce=base + rng.randint(0, 5), max_fee=fee, tip=rng.randint(1, min(fee, 8)),
              type=4 if authorities else 2, gas=46000 if authorities else 21000, authorities=authorities,
              delegate="impl" if authorities else None, size=rng.choice([110, 110, 110, 40000]),
              label="t%d" % rng.randrange(10**6))


class TestInvariants(unittest.TestCase):
    def run_sequence(self, seed, frame_config, contracts=0):
        rng = random.Random(seed)
        state = State({s: Account(balance=rng.choice([10**7, 10**8, 10**9]), code="app" if i < contracts else "")
                       for i, s in enumerate(SENDERS)})
        head = Head(timestamp=1000, gas_limit=200_000, gas_used=100_000, base_fee=10)
        nonce_config = GETH.with_(global_slots=5, global_queue=6, account_slots=1, account_queue=3, lifetime=600)
        pool = TxPool(head, state, nonce_config, frame_config.with_(max_pending=5))
        now = 0
        for _ in range(150):
            r = rng.random()
            if r < 0.6:
                pool.add([random_tx(rng, state) for _ in range(rng.randint(1, 4))], now)
            elif r < 0.8:
                block, state = build_block(pool, head, state, min_tip=1, coinbase="cb")
                head = block.head
                now += 12
                pool.reset(head, state, now)
            elif r < 0.85 and frame_config.per_sender == "matcha":
                gas = {s: rng.choice([0, 50_000, 200_000]) for s in rng.sample(SENDERS, 2)}
                pool.finalize([(head.number, gas)], now)
            elif r < 0.9:
                state = state.copy()
                state.edit(rng.choice(SENDERS)).balance = rng.choice([0, 10**6, 10**7, 10**9])
                if contracts:
                    state.edit(rng.choice(SENDERS[:contracts])).storage[rng.choice([1, 2, 3, 4])] = rng.randrange(3)
                now += 1
                pool.reset(head, state, now)
            else:
                now += rng.choice([60, 300, 900])
                pool.tick(now)
            check_nonce_pool(self, pool)
            check_frame_pool(self, pool)
            check_reservations(self, pool)

    def test_eip_8141_profile(self):
        for seed in range(25):
            with self.subTest(seed=seed):
                self.run_sequence(seed, EIP_8141)

    def test_hegota_profile(self):
        for seed in range(25):
            with self.subTest(seed=seed):
                self.run_sequence(1000 + seed, HEGOTA_TESTNET)

    def test_matcha_profile(self):
        for seed in range(25):
            with self.subTest(seed=seed):
                self.run_sequence(2000 + seed, MATCHA.with_(width_cap=300_000, lifetime=400))

    def test_matcha_classes(self):
        """MA-14 with contract senders whose prefixes read slots that change: baselines never share a class."""
        for seed in range(25):
            for contention in ("sender", "storage", "slot"):
                with self.subTest(seed=seed, contention=contention):
                    self.run_sequence(5000 + seed, MATCHA.with_(width_cap=300_000, lifetime=400,
                                                                contention=contention), contracts=4)

    def test_balance_reuse_changes_nothing_but_the_work(self):
        """FP-15 under `reuse_balance`: a prefix cannot read a balance, so reuse keeps exactly what re-running keeps."""
        saved = 0
        for seed in range(25):
            for profile in (EIP_8141, HEGOTA_TESTNET):
                with self.subTest(seed=seed, profile=profile.name):
                    saved += self.run_lockstep(3000 + seed, profile)
        self.assertGreater(saved, 0, "no sequence exercised the reuse")

    def run_lockstep(self, seed, frame_config):
        rng = random.Random(seed)
        state = State({s: Account(balance=rng.choice([10**7, 10**8, 10**9])) for s in SENDERS})
        head = Head(timestamp=1000, gas_limit=200_000, gas_used=100_000, base_fee=10)
        nonce_config = GETH.with_(global_slots=5, global_queue=6, account_slots=1, account_queue=3, lifetime=600)
        pools = [TxPool(head, state, nonce_config, frame_config.with_(max_pending=5, reuse_balance=reuse))
                 for reuse in (False, True)]
        now, saved = 0, 0
        for _ in range(150):
            r = rng.random()
            if r < 0.6:
                txs = [random_tx(rng, state) for _ in range(rng.randint(1, 4))]
                answers = [pool.add(txs, now) for pool in pools]
                self.assertEqual(answers[0], answers[1])
                continue
            if r < 0.8:
                block, state = build_block(pools[0], head, state, min_tip=1, coinbase="cb")
                head = block.head
                now += 12
            else:
                state = state.copy()
                state.edit(rng.choice(SENDERS)).balance = rng.choice([0, 10**6, 10**7, 10**9])
                now += 1
            for pool in pools:
                pool.reset(head, state, now)
            plain, reused = (set(pool.frame.entries) for pool in pools)
            self.assertEqual(plain, reused, "balance reuse kept a different set of transactions")
            self.assertLessEqual(len(pools[1].frame.resimulated), len(pools[0].frame.resimulated))
            saved += len(pools[0].frame.resimulated) - len(pools[1].frame.resimulated)
            check_frame_pool(self, pools[1])
        return saved

    def test_static_first_admits_what_the_eip_order_admits(self):
        """Admission under `static_first`: FP-11 and FP-12 read nothing the prefix computes, so the order moves
        only the answer to a transaction that both orders refuse."""
        moved = 0
        for seed in range(25):
            for profile in (EIP_8141, HEGOTA_TESTNET):
                with self.subTest(seed=seed, profile=profile.name):
                    moved += self.run_orders(4000 + seed, profile)
        self.assertGreater(moved, 0, "no sequence refused a transaction in a different place")

    def run_orders(self, seed, frame_config):
        rng = random.Random(seed)
        state = State({s: Account(balance=rng.choice([10**7, 10**8, 10**9])) for s in SENDERS})
        head = Head(timestamp=1000, gas_limit=200_000, gas_used=100_000, base_fee=10)
        nonce_config = GETH.with_(global_slots=5, global_queue=6, account_slots=1, account_queue=3, lifetime=600)
        pools = [TxPool(head, state, nonce_config, frame_config.with_(max_pending=5, static_first=early))
                 for early in (False, True)]
        now, moved = 0, 0
        for _ in range(150):
            r = rng.random()
            if r < 0.6:
                txs = [random_tx(rng, state) for _ in range(rng.randint(1, 4))]
                eip, early = (pool.add(txs, now) for pool in pools)
                for a, b in zip(eip, early):
                    self.assertEqual(a == "ok", b == "ok", "the orders admitted different transactions")
                    moved += a != b
            else:
                if r < 0.8:
                    block, state = build_block(pools[0], head, state, min_tip=1, coinbase="cb")
                    head = block.head
                    now += 12
                else:
                    state = state.copy()
                    state.edit(rng.choice(SENDERS)).balance = rng.choice([0, 10**6, 10**7, 10**9])
                    now += 1
                for pool in pools:
                    pool.reset(head, state, now)
            self.assertEqual(set(pools[0].frame.entries), set(pools[1].frame.entries))
            check_frame_pool(self, pools[1])
        return moved

    def test_eviction_index_picks_what_a_scan_picks(self):
        """FP-14 under both orders and both expiry readings: the heap of eviction keys agrees with a scan."""
        checked = 0
        for seed in range(25):
            for order in ("expiry", "tip"):
                for margin in (0, 12):
                    with self.subTest(seed=seed, order=order, margin=margin):
                        config = EIP_8141.with_(max_pending=4, evict_first=order, expiry_margin=margin)
                        checked += self.run_eviction(4000 + seed, config)
        self.assertGreater(checked, 100, "too few evictions exercised")

    def run_eviction(self, seed, frame_config):
        rng = random.Random(seed)
        senders = ["e%d" % i for i in range(12)]
        accounts = {s: Account(balance=10**9) for s in senders}
        accounts[EIP_8141.expiry_verifier] = Account(code=EIP_8141.expiry_verifier_code)
        state = State(accounts)
        head = Head(timestamp=1000, gas_limit=400_000, gas_used=200_000, base_fee=10)
        pool = TxPool(head, state, GETH, frame_config)
        f, checked = pool.frame, 0

        def key(deadline, tx, received):
            nearest = float("inf") if deadline is None else deadline
            tip = tx.effective_tip(f.head.next_base_fee())
            return (nearest, tip, -received) if frame_config.evict_first == "expiry" else (tip, nearest, -received)

        for _ in range(200):
            if rng.random() < 0.15:
                block, state = build_block(pool, head, state, min_tip=1, coinbase="cb")
                head = Head(head.number + 1, head.timestamp + 12, head.gas_limit, rng.choice([0, 200_000, 400_000]),
                            block.head.base_fee)
                pool.reset(head, state, head.timestamp)
                continue
            sender = rng.choice(senders)
            frames = (Frame(mode=1, flags=3, exec_gas=30000), Frame(mode=2, exec_gas=50000))
            deadline = rng.choice([None, None, head.timestamp + rng.randint(0, 3) * 12])
            if deadline is not None:
                frames = (Frame(mode=1, target=EIP_8141.expiry_verifier, exec_gas=100, data_size=8,
                                deadline=deadline),) + frames
            fee = rng.randint(5, 30)
            tx = FrameTx(sender, frames, nonce_seq=state.nonce(sender), max_fee=fee, tip=rng.randint(1, min(fee, 8)),
                         label="v%d" % rng.randrange(10**6))
            full = len(f.entries) >= frame_config.max_pending and tx.sender not in f.by_sender
            held = {h: key(e.sim.deadline, e.tx, e.seq) for h, e in f.entries.items()}
            logged = len(f.log)
            answer = pool.add([tx], head.timestamp)[0]
            if not full or answer not in ("ok", "ErrTxPoolOverflow"):
                continue
            expected = min(held, key=held.get)
            if held[expected] > key(deadline, tx, float("inf")):
                expected = None
            evicted = [t.hash for kind, t, reason in f.log[logged:] if reason == "capacity"]
            self.assertEqual(evicted, [] if expected is None else [expected])
            self.assertEqual(answer, "ErrTxPoolOverflow" if expected is None else "ok")
            checked += 1
            check_frame_pool(self, pool)
        return checked


if __name__ == "__main__":
    unittest.main()
