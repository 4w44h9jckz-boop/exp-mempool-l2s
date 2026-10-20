"""The price list of NP-10: go-ethereum `legacypool/list.go`, `priceHeap` and `pricedList`.

Two min-heaps over the pool's transactions, cheapest first. `urgent` orders by
effective tip at the pending base fee, then fee cap, then tip; `floating` by fee
cap, then tip. Among equal prices the higher nonce is cheaper, and then the
later-received (MD-10). Removed transactions stay in the heaps as stale entries
until they surface or a rebuild happens.
"""

from __future__ import annotations

import heapq
import itertools
from typing import Callable, Iterable

from ..tx import Tx

URGENT_RATIO = 4
FLOATING_RATIO = 1


class PricedList:
    def __init__(self, live: Callable[[str], bool], everything: Callable[[], Iterable[Tx]],
                 arrival: Callable[[Tx], int], slots: Callable[[Tx], int]):
        self._live = live
        self._everything = everything
        self._arrival = arrival
        self._slots = slots
        self.base_fee: int | None = None
        self.urgent: list = []
        self.floating: list = []
        self.stales = 0
        self._tiebreak = itertools.count()

    # Price keys. Smaller is cheaper.

    def _price(self, tx: Tx, base_fee: int | None) -> tuple:
        if base_fee is None:
            return (tx.max_fee, tx.tip)
        return (tx.effective_tip(base_fee), tx.max_fee, tx.tip)

    def _entry(self, tx: Tx, base_fee: int | None) -> tuple:
        return (self._price(tx, base_fee), -tx.nonce, -self._arrival(tx), next(self._tiebreak), tx)

    def _push_urgent(self, tx: Tx) -> None:
        heapq.heappush(self.urgent, self._entry(tx, self.base_fee))

    def _push_floating(self, tx: Tx) -> None:
        heapq.heappush(self.floating, self._entry(tx, None))

    # Operations

    def put(self, tx: Tx) -> None:
        """New transactions go to urgent; `discard` rebalances."""
        self._push_urgent(tx)

    def removed(self, count: int) -> None:
        """Count stale entries; rebuild once they exceed a quarter of both heaps."""
        self.stales += count
        if self.stales <= (len(self.urgent) + len(self.floating)) // 4:
            return
        self.reheap()

    def _underpriced_for(self, heap: list, base_fee: int | None, tx: Tx) -> bool:
        while heap and not self._live(heap[0][-1].hash):
            heapq.heappop(heap)
            self.stales -= 1
        if not heap:
            return False
        return self._price(heap[0][-1], base_fee) >= self._price(tx, base_fee)

    def underpriced(self, tx: Tx) -> bool:
        """Not cheaper than the cheapest live entry of every non-empty heap; equal counts."""
        u = self._underpriced_for(self.urgent, self.base_fee, tx) or not self.urgent
        f = self._underpriced_for(self.floating, None, tx) or not self.floating
        return u and f and bool(self.urgent or self.floating)

    def discard(self, slots: int) -> tuple[list[Tx], bool]:
        drop: list[Tx] = []
        while slots > 0:
            if len(self.urgent) * FLOATING_RATIO > len(self.floating) * URGENT_RATIO:
                tx = heapq.heappop(self.urgent)[-1]
                if not self._live(tx.hash):
                    self.stales -= 1
                    continue
                self._push_floating(tx)
            else:
                if not self.floating:
                    break
                tx = heapq.heappop(self.floating)[-1]
                if not self._live(tx.hash):
                    self.stales -= 1
                    continue
                drop.append(tx)
                slots -= self._slots(tx)
        if slots > 0:
            for tx in drop:
                self._push_urgent(tx)
            return [], False
        return drop, True

    def reheap(self) -> None:
        """Everything into urgent, then the cheapest fifth by urgent order into floating."""
        self.stales = 0
        self.urgent = [self._entry(tx, self.base_fee) for tx in self._everything()]
        heapq.heapify(self.urgent)
        floating_count = len(self.urgent) * FLOATING_RATIO // (URGENT_RATIO + FLOATING_RATIO)
        moved = [heapq.heappop(self.urgent)[-1] for _ in range(floating_count)]
        self.floating = [self._entry(tx, None) for tx in moved]
        heapq.heapify(self.floating)

    def set_base_fee(self, base_fee: int) -> None:
        self.base_fee = base_fee
        self.reheap()
