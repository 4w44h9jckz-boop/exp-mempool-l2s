import unittest

from emem import Tx
from emem.noncepool.priced import PricedList
from emem.noncepool.txlist import NonceList


def tx(nonce, max_fee=100, tip=10, sender="a", gas=21000, label=""):
    return Tx(sender, nonce=nonce, max_fee=max_fee, tip=tip, gas=gas, label=label or f"{sender}{nonce}-{tip}")


class TestNonceList(unittest.TestCase):
    def test_strict_filter_demotes_everything_above_the_lowest_removed(self):
        l = NonceList(strict=True)
        for n, fee in [(0, 100), (1, 300), (2, 100), (3, 100)]:
            l.add(tx(n, max_fee=fee), 10)
        removed, invalids = l.filter(cost_limit=21000 * 200, gas_limit=10**9)
        self.assertEqual([t.nonce for t in removed], [1])
        self.assertEqual([t.nonce for t in invalids], [2, 3])
        self.assertEqual([t.nonce for t in l.flatten()], [0])
        self.assertEqual(l.total_cost, 21000 * 100)

    def test_queue_filter_is_not_strict(self):
        l = NonceList(strict=False)
        for n, fee in [(3, 100), (4, 300), (5, 100)]:
            l.add(tx(n, max_fee=fee), 10)
        removed, invalids = l.filter(cost_limit=21000 * 200, gas_limit=10**9)
        self.assertEqual(([t.nonce for t in removed], invalids), ([4], []))

    def test_cap_drops_highest_first(self):
        l = NonceList(strict=False)
        for n in (5, 1, 3, 9):
            l.add(tx(n), 10)
        self.assertEqual([t.nonce for t in l.cap(2)], [9, 5])
        self.assertEqual([t.nonce for t in l.flatten()], [1, 3])

    def test_ready_takes_the_consecutive_run_only_from_a_low_enough_start(self):
        l = NonceList(strict=False)
        for n in (2, 3, 5):
            l.add(tx(n), 10)
        self.assertEqual(l.ready(1), [])
        self.assertEqual([t.nonce for t in l.ready(2)], [2, 3])
        self.assertEqual([t.nonce for t in l.flatten()], [5])

    def test_total_cost_follows_replacement(self):
        l = NonceList(strict=True)
        l.add(tx(0), 10)
        ok, old = l.add(tx(0, max_fee=110, tip=11), 10)
        self.assertTrue(ok)
        self.assertEqual(old.max_fee, 100)
        self.assertEqual(l.total_cost, 21000 * 110)


class TestPricedList(unittest.TestCase):
    def make(self, txs):
        live = {t.hash: t for t in txs}
        order = {t.hash: i for i, t in enumerate(txs)}
        p = PricedList(lambda h: h in live, lambda: list(live.values()), lambda t: order[t.hash], lambda t: 1)
        p.set_base_fee(10)
        return p, live

    def test_reheap_moves_the_cheapest_fifth_to_floating(self):
        txs = [tx(0, sender=f"s{i}", tip=i + 1) for i in range(10)]
        p, _ = self.make(txs)
        self.assertEqual((len(p.urgent), len(p.floating)), (8, 2))
        self.assertEqual(sorted(e[-1].tip for e in p.floating), [1, 2])

    def test_equal_price_is_underpriced(self):
        p, _ = self.make([tx(0, sender="s", tip=10)])
        self.assertTrue(p.underpriced(tx(0, sender="t", tip=10)))
        self.assertFalse(p.underpriced(tx(0, sender="t", tip=11)))

    def test_underpriced_needs_every_non_empty_heap(self):
        # the rebuild puts the lowest effective tip (cheapcap, 5) in floating
        txs = [tx(0, sender=f"s{i}", tip=20) for i in range(4)] + [tx(0, sender="cheapcap", max_fee=50, tip=5)]
        p, _ = self.make(txs)
        candidate = tx(0, sender="new", max_fee=60, tip=15)
        # effective tip 15 is below urgent's cheapest (20), but its fee cap 60 beats floating's 50
        self.assertFalse(p.underpriced(candidate))

    def test_stale_entries_are_skipped_and_counted(self):
        txs = [tx(0, sender=f"s{i}", tip=i + 1) for i in range(5)]
        p, live = self.make(txs)
        del live[txs[0].hash]
        drop, ok = p.discard(1)
        self.assertTrue(ok)
        self.assertNotIn(txs[0], drop)

    def test_failed_discard_puts_back_into_urgent(self):
        txs = [tx(0, sender=f"s{i}", tip=i + 1) for i in range(2)]
        p, _ = self.make(txs)
        before = len(p.urgent) + len(p.floating)
        drop, ok = p.discard(5)
        self.assertFalse(ok)
        self.assertEqual(drop, [])
        self.assertEqual(len(p.urgent) + len(p.floating), before)


if __name__ == "__main__":
    unittest.main()
