"""Randomised sealed transactions, heads and blocks under `eip-8184`, against what LU-5 to LU-13 together imply.

Like `test_invariants.py`, these check bookkeeping under sequences nobody wrote
by hand, not that the code follows a clause; the vectors do that.
"""

import random
import unittest

from emem import EIP_8184, Head, SealedTx, State, Tx, TxPool, build_block
from emem.sealed import EVICTIONS, POLICIES, fees, order_key, select

SENDERS = ["s%d" % i for i in range(10)]


def sealed(rng, sender, nonce, label):
    gas = rng.choice([40_000, 100_000, 400_000, 1_000_000])
    return SealedTx(sender, nonce=nonce, max_fee=rng.choice([9, 12, 50, 100]), tip=rng.choice([0, 1, 5, 10]),
                    gas_limit=gas, max_tob_fee=rng.choice([0, 0, 100, 10_000, 10**6]),
                    max_preceding=rng.choice([0, 1, 3, 31]), key_fee=rng.choice([0, 0, 1000]),
                    revealed=rng.random() < 0.8, used=rng.randint(gas // 2, gas), label=label)


def check_pool(test, pool):
    s = pool.sealed
    base_fee = pool.head.next_base_fee()
    test.assertLessEqual(len(s.entries), s.config.st_slots)
    for h, e in s.entries.items():
        tx = e.tx
        test.assertEqual(s.by_sender[tx.sender], h)
        test.assertEqual(tx.nonce, pool.state.nonce(tx.sender), "a sealed transaction off its sender's nonce")
        test.assertGreaterEqual(pool.state.balance(tx.sender), tx.cost)
        test.assertIsNotNone(fees(tx, base_fee), "a sealed transaction that can not pay")
        test.assertLessEqual(tx.gas_limit, s.config.tob_gas_limit(pool.head.gas_limit))
        test.assertNotIn(tx.sender, pool.nonce.pending, "a sender in two subpools")
        test.assertNotIn(tx.sender, pool.nonce.queue, "a sender in two subpools")


def victim(s, st):
    """LU-10 read directly: the victim for `st` in the full sealed pool `s`, and whether `st` is admitted."""
    b = s.head.next_base_fee()
    held = s.txs()
    ranked = sorted(held, key=lambda t: order_key(t, b))
    if s.config.evict_first == "last":
        return ranked[-1].hash, order_key(st, b) < order_key(ranked[-1], b)
    chosen = {t.hash for t in select(held + [st], s.state, b, 0, s.head.gas_limit, s.config)}
    passed = [t for t in ranked if t.hash not in chosen]
    v = passed[-1] if passed else ranked[-1]
    return v.hash, order_key(st, b) < order_key(v, b) or (st.hash in chosen and v.hash not in chosen)


class SealedInvariants(unittest.TestCase):
    def test_random_sequences(self):
        victims = {e: 0 for e in EVICTIONS}
        for seed in range(30):
            rng = random.Random(seed)
            cfg = EIP_8184.with_(policy=rng.choice(POLICIES), st_slots=rng.choice([4, 64]),
                                 max_st_commits=rng.choice([2, 32]), evict_first=EVICTIONS[seed % 2])
            state = State()
            for s in SENDERS:
                state.edit(s).balance = rng.choice([10**6, 10**8])
            head = Head(0, 1000, 8_000_000, 4_000_000, 10)
            pool = TxPool(head, state, sealed_config=cfg)
            scheduled = ()
            for step in range(150):
                r = rng.random()
                sender = rng.choice(SENDERS)
                if r < 0.55:
                    st = sealed(rng, sender, state.nonce(sender), "t%d-%d" % (seed, step))
                    old = pool.sealed.by_sender.get(sender)
                    others = [t for t in pool.sealed.txs() if t.hash != old] + [st]
                    expect = st in select(others, pool.state, head.next_base_fee(), 0, head.gas_limit, cfg)
                    if old is not None or len(pool.sealed.entries) < cfg.st_slots:
                        self.assertEqual(pool.sealed._takes(st, old), expect, "LU-8's walk against LU-7")
                    elif fees(st, head.next_base_fee()) is not None:
                        self.assertEqual(pool.sealed._victim(st), victim(pool.sealed, st), "LU-10's victim")
                        victims[cfg.evict_first] += 1
                    pool.add([st], step)
                elif r < 0.65:
                    pool.add([Tx(sender, nonce=state.nonce(sender), max_fee=50, tip=5, label="p%d" % step)], step)
                elif r < 0.75:
                    gas_used = rng.choice([0, 4_000_000, 8_000_000])
                    head = Head(head.number, head.timestamp, head.gas_limit, gas_used, head.base_fee)
                    pool.reset(head, state, step)
                    if cfg.policy == "every-head":
                        kept = {t.hash for t in pool.sealed.selection(head.next_base_fee())}
                        self.assertEqual(set(pool.sealed.entries), kept, "every-head kept what has no place")
                else:
                    held = set(pool.sealed.entries)
                    block, post = build_block(pool, head, state, min_tip=1, scheduled=scheduled)
                    base_fee = block.head.base_fee
                    tob = cfg.tob_gas_limit(head.gas_limit)
                    commits = [c.tx for c in block.commitments]
                    self.assertTrue({t.hash for t in commits} <= held)
                    self.assertLessEqual(len(commits), cfg.max_st_commits)
                    self.assertLessEqual(sum(t.gas_limit for t in commits), tob)
                    keys = [order_key(t, base_fee) for t in commits]
                    self.assertEqual(keys, sorted(keys), "commitments out of order")
                    for i, t in enumerate(commits):
                        self.assertLessEqual(i, t.max_preceding)
                        self.assertEqual(post.nonce(t.sender), t.nonce + 1)
                    self.assertEqual([t.hash for t in block.decrypted],
                                     [c.tx.hash for c in scheduled if c.tx.revealed])
                    used = sum(t.dual_gas_used for t in block.decrypted)
                    used += sum(min(t.used, t.gas_limit) for t in block.txs)
                    self.assertEqual(block.head.gas_used, used)
                    scheduled = block.commitments
                    head, state = block.head, post
                    pool.reset(head, state, step)
                    if cfg.policy == "every-head":
                        kept = {t.hash for t in pool.sealed.selection(head.next_base_fee())}
                        self.assertEqual(set(pool.sealed.entries), kept, "every-head kept what has no place")
                check_pool(self, pool)
        self.assertTrue(all(n > 50 for n in victims.values()), victims)

    def test_a_builder_s_skip_reaches_the_sealed_selection(self):
        state = State()
        for s in SENDERS[:3]:
            state.edit(s).balance = 10**8
        head = Head(0, 1000, 8_000_000, 4_000_000, 10)
        pool = TxPool(head, state, sealed_config=EIP_8184)
        sts = [SealedTx(s, max_fee=50, tip=5, key_publisher="mpc" if i == 1 else "kp") for i, s in enumerate(SENDERS[:3])]
        pool.add(sts, 0)
        block, _ = build_block(pool, head, state, min_tip=1)
        self.assertEqual({c.tx.sender for c in block.commitments}, set(SENDERS[:3]))
        block, post = build_block(pool, head, state, min_tip=1, skip=lambda tx: getattr(tx, "key_publisher", "") == "mpc")
        self.assertEqual({c.tx.sender for c in block.commitments}, {SENDERS[0], SENDERS[2]})
        self.assertEqual(post.nonce(SENDERS[1]), 0)


if __name__ == "__main__":
    unittest.main()
