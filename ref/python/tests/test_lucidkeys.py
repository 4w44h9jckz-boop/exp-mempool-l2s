"""The key round (`docs/spec/06-lucid.md`, LU-14 to LU-19): what is read, and when."""

from __future__ import annotations

import itertools
import random
import unittest

from emem import EIP_8184, SealedTx
from emem import lucidkeys as lk


def key(b: int) -> bytes:
    return bytes([b]) * 32


def block(*publishers: str, decrypts=None, root="B", slot=1) -> lk.SchedulingBlock:
    decrypts = decrypts or [True] * len(publishers)
    sts = tuple(SealedTx(sender=f"s{j}", key_publisher=p, k_dem=key(j + 1), decrypts=None if d else False, label=f"c{j}")
                for j, (p, d) in enumerate(zip(publishers, decrypts)))
    return lk.SchedulingBlock(root, slot, sts)


class Reads:
    """A `Decrypt` that records every ciphertext it is asked to read."""

    def __init__(self):
        self.asked: list[tuple[int, bytes]] = []

    def __call__(self, b, j, k):
        self.asked.append((j, k))
        return lk.read_decrypts(b, j, k)


class TestNoContentBeforeRelease(unittest.TestCase):
    def test_commitments_release_and_tally_read_no_ciphertext(self):
        b = block("kp1", "kp2", "kp1", decrypts=[True, True, False])
        reads = Reads()
        b.commitments()
        lk.release(b, "kp1", EIP_8184)
        lk.tally(3, ["m1", "m2"], 6000, 9000, [("m1", (1, 0, 1), 100), ("m2", (0, 0, 1), 7000)])
        self.assertEqual(reads.asked, [])

    def test_the_ciphertext_is_read_only_with_the_committed_key(self):
        """LU-15: step 6 is reached only by a message whose key hashes to the commitment's key."""
        b = block("kp1", "kp2", decrypts=[True, False])
        blocks = lk.Blocks([b])
        rng = random.Random(70)
        for _ in range(500):
            j = rng.randrange(-1, 3)
            keys = tuple(key(rng.randrange(0, 4)) for _ in range(rng.randrange(0, 3)))
            msg = lk.KeyMessage(rng.choice([1, 1, 1, 2]), rng.choice(["B", "B", "C"]), rng.choice([1, 1, 2]), j, keys)
            reads = Reads()
            reason = lk.check(msg, blocks, reads)
            if reads.asked:
                ((jj, k),) = reads.asked
                self.assertEqual(k, b.sealed[jj].dem_key)
                self.assertIn(reason, (lk.VALID, lk.DECRYPT))
            else:
                self.assertNotIn(reason, (lk.VALID, lk.DECRYPT))

    def test_no_key_message_before_the_block_is_observed(self):
        b = block("kp1", "kp2")
        for p in ("kp1", "kp2", "s0", "s1"):
            self.assertEqual(lk.release(b, p, EIP_8184, observed=False), [])

    def test_a_vote_reads_only_keys_received_in_time(self):
        b = block("kp1", "kp2", "kp1")
        msgs = lk.release(b, "kp1", EIP_8184) + lk.release(b, "kp2", EIP_8184)
        reads = Reads()
        lk.vote(b, lk.Blocks([b]), [(m, 500 + 400 * m.commit_index) for m in msgs], 1000, reads)
        self.assertEqual(sorted(j for j, _ in reads.asked), [0, 1])


class TestTally(unittest.TestCase):
    def test_one_treatment_is_always_allowed(self):
        for t1, t0, l1, l0, e in itertools.product(range(5), repeat=5):
            c = lk.Counts(t1, t0, l1, l0, e)
            self.assertTrue(c.allowed(), c)

    def test_a_key_every_member_votes_against_in_time_is_missing_only(self):
        for n in range(1, 20):
            (c,) = lk.tally(1, [f"m{i}" for i in range(n)], 6000, 9000, [(f"m{i}", (0,), 100) for i in range(n)])
            self.assertEqual(c.allowed(), (lk.MISSING,))


class TestRound(unittest.TestCase):
    def test_a_withheld_key_is_a_missing_vote_that_names_its_publisher(self):
        b = block("kp1", "kp2", "kp1")
        blocks = lk.Blocks([b])
        sent = [(m, 300) for m in lk.release(b, "kp1", EIP_8184)]  # kp2 withholds
        ptc = [f"m{i}" for i in range(8)]
        votes = [(m, lk.vote(b, blocks, sent, 1000), 2000) for m in ptc]
        counts = lk.tally(3, ptc, 6000, 9000, votes)
        self.assertEqual([c.allowed() for c in counts], [(lk.OBSERVED,), (lk.MISSING,), (lk.OBSERVED,)])
        revealed, missing = lk.blame(b, blocks, counts, sent, 1000)
        self.assertEqual((revealed, missing), ([0, 2], {1: lk.WITHHELD}))
        self.assertEqual(b.sealed[1].key_publisher, "kp2")


if __name__ == "__main__":
    unittest.main()
