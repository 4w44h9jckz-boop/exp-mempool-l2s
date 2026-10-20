"""Properties of `07-focil.md` over random pools: what IL-7 appends satisfies IL-6, and a builder that leaves
senders out can only be caught leaving out theirs."""

import random
import unittest

from emem import EIP_7805, Account, Head, State, Tx, TxPool, build_block, build_il, omission

HEAD = Head(timestamp=1000, gas_limit=1_000_000, gas_used=500_000, base_fee=10)
SENDERS = [f"s{i}" for i in range(12)]


def scene(rng: random.Random):
    """A pool of transfers, some with gaps, some underfunded, and the ILs four includers build from it."""
    state = State({s: Account(balance=rng.choice((10**6, 10**9)), nonce=rng.randint(0, 2)) for s in SENDERS})
    pool = TxPool(HEAD, state)
    for s in SENDERS:
        start = state.nonce(s) + rng.choice((0, 0, 0, 1))
        for n in range(start, start + rng.randint(1, 4)):
            pool.add([Tx(s, nonce=n, gas=rng.choice((21_000, 60_000, 200_000)), max_fee=rng.randint(9, 40),
                         tip=rng.randint(0, 5), label=f"{s}-{n}")])
    config = EIP_7805.with_(max_bytes=rng.choice((300, 800, 8192)), policy=rng.choice(("fee", "age")))
    base_fee = HEAD.next_base_fee()
    ils = tuple(build_il(pool, base_fee, config) for _ in range(4))
    return state, pool, config, ils


class TestFocilProperties(unittest.TestCase):
    def test_an_honest_build_satisfies_its_lists(self):
        for seed in range(200):
            rng = random.Random(seed)
            state, pool, config, ils = scene(rng)
            block, post = build_block(pool, HEAD, state, min_tip=rng.choice((0, 3)), ils=ils, focil=config)
            gas_left = block.head.gas_limit - block.head.gas_used
            self.assertIsNone(omission(block.txs, post, block.head, gas_left, ils, pool.frame.config, config),
                              f"seed {seed}")

    def test_only_a_skipped_sender_is_an_omission(self):
        for seed in range(200):
            rng = random.Random(seed)
            state, pool, config, ils = scene(rng)
            left_out = set(rng.sample(SENDERS, 3))
            block, post = build_block(pool, HEAD, state, min_tip=1, ils=ils, focil=config,
                                      skip=lambda tx: tx.sender in left_out)
            self.assertFalse(any(tx.sender in left_out for tx in block.txs), f"seed {seed}")
            gas_left = block.head.gas_limit - block.head.gas_used
            missing = omission(block.txs, post, block.head, gas_left, ils, pool.frame.config, config)
            self.assertTrue(missing is None or missing.sender in left_out, f"seed {seed}")

    def test_a_list_keeps_nonce_order_and_its_byte_cap(self):
        for seed in range(200):
            rng = random.Random(seed)
            _, _, config, ils = scene(rng)
            for il in ils:
                self.assertLessEqual(sum(tx.encoded_size for tx in il), config.max_bytes)
                for s in SENDERS:
                    nonces = [tx.nonce for tx in il if tx.sender == s]
                    self.assertEqual(nonces, sorted(nonces))
                    self.assertEqual(nonces, list(range(nonces[0], nonces[0] + len(nonces))) if nonces else [])


if __name__ == "__main__":
    unittest.main()
