import random
import unittest

from emem import Frame, FrameTx, Head, State, Tx
from emem.model import Account, effective_tip, next_base_fee


class TestBaseFee(unittest.TestCase):
    def test_never_moves_more_than_an_eighth(self):
        for base in (7, 8, 100, 10**9):
            up = next_base_fee(30_000_000, 30_000_000, base)
            down = next_base_fee(30_000_000, 0, base)
            self.assertLessEqual(up - base, max(1, base // 8))
            self.assertLessEqual(base - down, base // 8)

    def test_head_uses_its_own_fields(self):
        self.assertEqual(Head(gas_limit=30_000_000, gas_used=30_000_000, base_fee=1000).next_base_fee(), 1125)

    def test_effective_tip_can_be_negative(self):
        self.assertEqual(effective_tip(max_fee=5, tip=3, base_fee=10), -5)
        self.assertEqual(effective_tip(max_fee=100, tip=3, base_fee=10), 3)


class TestState(unittest.TestCase):
    def test_absent_accounts_read_as_default_and_are_not_created(self):
        s = State()
        self.assertEqual(s.balance("nobody"), 0)
        self.assertEqual(s.addresses(), [])

    def test_copy_is_deep(self):
        s = State({"a": Account(storage={1: 2})})
        t = s.copy()
        t.edit("a").storage[1] = 3
        self.assertEqual(s.storage("a", 1), 2)

    def test_key_zero_is_the_account_nonce(self):
        s = State({"a": Account(nonce=4, nonce_seqs={7: 2})})
        self.assertEqual(s.nonce_seq("a", 0), 4)
        self.assertEqual(s.nonce_seq("a", 7), 2)
        s.bump_nonce_seq("a", 0)
        s.bump_nonce_seq("a", 9)
        self.assertEqual((s.nonce("a"), s.nonce_seq("a", 9)), (5, 1))


    def test_changed_since_takes_its_shortcut_only_when_the_slow_answer_agrees(self):
        rng = random.Random(7)
        addrs = [f"a{i}" for i in range(8)]
        states = [State({a: Account(balance=1) for a in addrs[:4]})]
        parents, shortcuts = {}, 0
        for _ in range(2000):
            s = rng.choice(states[-3:])
            if rng.random() < 0.5:
                child = s.copy()
                parents[id(child)] = s
                states.append(child)
                s = child if rng.random() < 0.8 else s
            for a in rng.sample(addrs, rng.choice((0, 0, 1, 3))):
                s.edit(a).balance += 1
            new = rng.choice(states[-4:])
            old = parents.get(id(new)) if rng.random() < 0.7 else rng.choice(states)
            if old is None:
                continue
            slow = {a for a, acc in new._accounts.items() if old._accounts.get(a) is not acc}
            slow |= {a for a in old._accounts if a not in new._accounts}
            shortcuts += new._base == old._version and not old._own
            self.assertEqual(new.changed_since(old), slow)
        self.assertGreater(shortcuts, 200)


class TestIdentity(unittest.TestCase):
    def test_hash_is_deterministic_and_label_sensitive(self):
        self.assertEqual(Tx("a", label="x").hash, Tx("a", label="x").hash)
        self.assertNotEqual(Tx("a", label="x").hash, Tx("a", label="y").hash)
        self.assertEqual(Tx("a"), Tx("a"))

    def test_opcode_sets_hash_independently_of_order(self):
        f1 = Frame(mode=1, flags=3, opcodes=frozenset(["GAS", "NUMBER", "BALANCE"]))
        f2 = Frame(mode=1, flags=3, opcodes=frozenset(["BALANCE", "GAS", "NUMBER"]))
        self.assertEqual(FrameTx("a", (f1,)).hash, FrameTx("a", (f2,)).hash)

    def test_cost(self):
        self.assertEqual(Tx("a", gas=21000, max_fee=100, value=5).cost, 2_100_005)


if __name__ == "__main__":
    unittest.main()
