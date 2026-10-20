"""A sender's transactions by nonce: go-ethereum `legacypool/list.go`, `list` and `SortedMap`.

A strict list (pending) treats a removal as invalidating every higher nonce
(NP-13); a non-strict one (the queue) does not.
"""

from __future__ import annotations

from ..tx import Tx, replaces


class NonceList:
    def __init__(self, strict: bool):
        self.strict = strict
        self.txs: dict[int, Tx] = {}
        self.total_cost = 0

    def __len__(self) -> int:
        return len(self.txs)

    def empty(self) -> bool:
        return not self.txs

    def get(self, nonce: int) -> Tx | None:
        return self.txs.get(nonce)

    def contains(self, nonce: int) -> bool:
        return nonce in self.txs

    def flatten(self) -> list[Tx]:
        return [self.txs[n] for n in sorted(self.txs)]

    def last(self) -> Tx:
        return self.txs[max(self.txs)]

    def add(self, tx: Tx, price_bump: int) -> tuple[bool, Tx | None]:
        """`list.Add`: insert, replacing a same-nonce transaction only under NP-11."""
        old = self.txs.get(tx.nonce)
        if old is not None and not replaces(old, tx, price_bump):
            return False, None
        self.total_cost += tx.cost
        if old is not None:
            self.total_cost -= old.cost
        self.txs[tx.nonce] = tx
        return True, old

    def _take(self, nonces: list[int]) -> list[Tx]:
        taken = [self.txs.pop(n) for n in sorted(nonces)]
        self.total_cost -= sum(t.cost for t in taken)
        return taken

    def forward(self, threshold: int) -> list[Tx]:
        """Remove and return every transaction with a nonce below `threshold`."""
        return self._take([n for n in self.txs if n < threshold])

    def filter(self, cost_limit: int, gas_limit: int) -> tuple[list[Tx], list[Tx]]:
        """Remove transactions costing more than `cost_limit` or with more gas than
        `gas_limit`, each on its own. A strict list also returns, as invalids, every
        transaction above the lowest removed nonce."""
        removed = self._take([n for n, t in self.txs.items() if t.gas > gas_limit or t.cost > cost_limit])
        invalids: list[Tx] = []
        if removed and self.strict:
            lowest = min(t.nonce for t in removed)
            invalids = self._take([n for n in self.txs if n > lowest])
        return removed, invalids

    def cap(self, threshold: int) -> list[Tx]:
        """Remove and return the highest-nonce transactions beyond `threshold`."""
        if len(self.txs) <= threshold:
            return []
        nonces = sorted(self.txs)
        return list(reversed(self._take(nonces[threshold:])))

    def remove(self, tx: Tx) -> tuple[bool, list[Tx]]:
        """Remove the transaction at `tx.nonce` (by nonce, as go-ethereum does). A strict
        list also removes and returns every higher nonce."""
        if tx.nonce not in self.txs:
            return False, []
        self._take([tx.nonce])
        if self.strict:
            return True, self._take([n for n in self.txs if n > tx.nonce])
        return True, []

    def ready(self, start: int) -> list[Tx]:
        """Remove and return the run of consecutive nonces from the lowest, if the
        lowest is at or below `start`."""
        if not self.txs or min(self.txs) > start:
            return []
        run = []
        nonce = min(self.txs)
        while nonce in self.txs:
            run.append(nonce)
            nonce += 1
        return self._take(run)
