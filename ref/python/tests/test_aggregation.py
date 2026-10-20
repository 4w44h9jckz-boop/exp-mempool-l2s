"""Randomised wrappers, aggregates and blocks under `eip-8288`, against what AG-5 to AG-10 together imply.

Like `test_invariants.py`, these check bookkeeping under sequences nobody wrote
by hand, not that the code follows a clause; the vectors do that.
"""

import random
import unittest

from emem import EIP_8288, Aggregator, Dependency, Frame, FrameTx, Head, State, TxPool, Wrapper, build_block, wrap
from emem.dependencies import counts, union
from emem.tx import LEANSPHINCS, LEANSTARK

SENDERS = ["s%d" % i for i in range(8)]


def dep_tx(rng, sender, nonce, label):
    deps = []
    for _ in range(rng.randint(1, 3)):
        if rng.random() < 0.5:
            deps.append(Dependency(LEANSTARK, "pub-%d" % rng.randrange(6), "vk"))
        else:
            deps.append(Dependency(LEANSPHINCS, "msg-%d" % rng.randrange(12), "pk"))
    gas = sum(30000 if d.scheme == LEANSTARK else 3000 for d in deps)
    dep = Frame(mode=3, deps=tuple(deps), exec_gas=gas, data_size=96 * len(deps))
    verify = Frame(mode=1, flags=3)
    frames = (dep, verify) if rng.random() < 0.5 else (verify, dep)
    return FrameTx(sender, frames, nonce_seq=nonce, max_fee=rng.choice([50, 100, 200]),
                   tip=rng.choice([1, 10, 20]), label=label)


def check(test, pool, agg, w):
    f = pool.frame
    bounded = f.config.proving_budget is not None or f.config.memory_budget is not None  # AG-9, AG-10: a budget
    # may leave anything out
    for e in f.entries.values():
        test.assertTrue(f.proven.issuperset(e.tx.dependencies), "pending with an unproven dependency")
    if w is None:
        if not bounded:
            test.assertFalse(any(e.tx.dependencies for e in f.entries.values()),
                             "no aggregate but something to aggregate")
        return
    hashes = [e if isinstance(e, str) else e.hash for e in w.txs]
    test.assertEqual(len(hashes), len(set(hashes)), "a transaction listed twice")
    txs = [f.entries[h].tx for h in hashes]
    test.assertTrue(all(tx.dependencies for tx in txs), "a transaction without dependencies listed")
    test.assertEqual(w.deps, union(txs))
    test.assertEqual(w.stark.covers, w.deps)
    held = {h for h, e in f.entries.items() if e.tx.dependencies}
    if f.config.cap_aggregates:
        sigs, starks = counts(w.deps)
        test.assertLessEqual(sigs, f.config.max_sig_deps_per_wrapper)
        test.assertLessEqual(starks, f.config.max_stark_deps_per_wrapper)
    if bounded:
        test.assertLessEqual(set(hashes), held)
    elif f.config.cap_aggregates:
        test.assertTrue(set(hashes) or not held, "an empty aggregate though one transaction would fit")
    else:
        test.assertEqual(set(hashes), held, "an uncapped aggregate missed a transaction")


def check_time(test, agg, w, cfg):
    """AG-9's count: a base, one recursive input per source taken, one verification per triple proven directly."""
    if w is None:
        test.assertEqual((agg.proving_time, agg.inputs, agg.verified), (0, 0, 0))
        return
    test.assertLessEqual(agg.verified, len(w.deps))
    test.assertTrue(agg.inputs or agg.verified, "an aggregate with nothing proven into it")
    test.assertEqual(agg.proving_time, cfg.prove_base + cfg.prove_recursive * agg.inputs + cfg.prove_sig * agg.verified)
    if cfg.proving_budget is not None:
        test.assertLessEqual(agg.proving_time, cfg.proving_budget)


def check_memory(test, agg, w, cfg):
    """AG-10's count, over AG-9's inputs and direct triples."""
    if w is None:
        test.assertEqual(agg.memory, 0)
        return
    test.assertEqual(agg.memory, cfg.memory_base + cfg.memory_recursive * agg.inputs + cfg.memory_sig * agg.verified)
    if cfg.memory_budget is not None:
        test.assertLessEqual(agg.memory, cfg.memory_budget)


class AggregationInvariants(unittest.TestCase):
    def test_random_sequences(self):
        self.run_sequences(timed=False)

    def test_random_sequences_with_proving_time(self):
        """Costs alone change no listing (`check` holds unweakened); a budget bounds every aggregate."""
        self.run_sequences(timed=True)

    def test_random_sequences_with_memory(self):
        """A memory budget bounds every aggregate, alone and with a proving budget; costs alone change nothing."""
        self.run_sequences(timed=True, held=True)

    def run_sequences(self, timed, held=False):
        for seed in range(30):
            rng = random.Random(seed)
            cfg = EIP_8288.with_(cap_aggregates=rng.random() < 0.6,
                                 max_sig_deps_per_wrapper=rng.choice([2, 16]))
            if timed:  # prove_stark == prove_sig, so the time is a function of the three counts
                budget = rng.choice([None, 0, 150, 400, 1000]) if not held or rng.random() < 0.5 else None
                cfg = cfg.with_(prove_base=100, prove_recursive=rng.choice([50, 300]), prove_sig=20, prove_stark=20,
                                proving_budget=budget)
            if held:  # memory_stark == memory_sig, likewise
                cfg = cfg.with_(memory_base=1000, memory_recursive=rng.choice([500, 1200]), memory_sig=40,
                                memory_stark=40, memory_budget=rng.choice([None, 0, 1100, 2500, 6000]))
            state = State()
            for s in SENDERS:
                state.edit(s).balance = 10**12
            head = Head(0, 1000, 30_000_000, 15_000_000, 10)
            pool = TxPool(head, state, frame_config=cfg)
            agg = Aggregator(pool)
            nonces = {s: 0 for s in SENDERS}
            listed = set()  # every triple an aggregate has listed
            for step in range(120):
                r = rng.random()
                if r < 0.45:
                    sender = rng.choice(SENDERS)
                    txs = [dep_tx(rng, sender, nonces[sender], "t%d-%d" % (seed, step))]
                    w = wrap(txs, mode=rng.choice([0, 1]))
                    if rng.random() < 0.2:
                        w = Wrapper(w.txs, w.mode, w.deps, tuple(False for _ in w.proofs), w.stark)
                    agg.receive(w, step)
                elif r < 0.85:
                    folds = agg.work["fold"]
                    w = agg.aggregate()
                    check(self, pool, agg, w)
                    check_time(self, agg, w, cfg)
                    check_memory(self, agg, w, cfg)
                    # decision record 0037: a first listing is a fold if proven directly, else a cover
                    self.assertLessEqual(agg.work["fold"] - folds, agg.verified)
                    listed.update(w.deps if w is not None else ())
                    self.assertEqual(agg.work["fold"] + agg.work["cover"], len(listed))
                else:
                    block, state = build_block(pool, head, state, min_tip=1)
                    used = sum(min(t.used, t.gas_limit) + 30000 * getattr(t, "declared", 0) for t in block.txs)
                    self.assertEqual(block.head.gas_used, used)
                    head = block.head
                    pool.reset(head, state, step)
                    for s in SENDERS:
                        nonces[s] = state.nonce(s)


if __name__ == "__main__":
    unittest.main()
